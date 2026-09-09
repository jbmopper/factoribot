"""Sparse LP layer for delivery bounds: build, solve, certify, clean up.

This module knows nothing about blueprints. ``blueprint_plan`` resolves the
routing contract (lane aliases, eligibility, control state, furnace filtering,
unknown-capacity relaxation) into ``ModelInputs``; this module turns one stage
of that record into a sparse HiGHS model and returns raw solutions plus
weak-duality certificates. Every certificate is recomputed here from the
matrices and the returned multipliers; the optimizer's status word is never
the proof.

Stages relax *named* constraints of one per-entity model:

* ``routing``   – per-endpoint conservation, every enabled arc, every finite
                  capacity group, feed ceilings, global budgets.
* ``budget``    – ``delivery_unconstrained``: one conservation pool per material,
                  no arcs, only machine-time groups remain; budgets and feed
                  ceilings still apply.
* ``aggregate`` – additionally ``budgets_unlimited``: budgets and feed ceilings
                  are dropped (declared feeds are still the only inputs).

Exports, surplus outlets, activities, craft capacities and machine time are
shared by all stages, so routing <= budget <= aggregate as feasible sets.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import math
import time

from .blueprint_contract import Activity, Arc, EndpointId, Material

STAGES = ("aggregate", "budget", "routing")
STAGE_RELAXATIONS = {
    "aggregate": ("delivery_unconstrained", "budgets_unlimited"),
    "budget": ("delivery_unconstrained",),
    "routing": (),
}
POOL = "*"  # conservation pool key used when delivery is unconstrained


@dataclass(frozen=True)
class ArcTerm:
    """An enabled arc with lane aliases resolved to conservation endpoints."""
    arc: Arc
    source: EndpointId
    target: EndpointId
    materials: tuple[Material, ...]


@dataclass(frozen=True)
class ActivityPart:
    endpoint: EndpointId
    material: Material
    amount_per_craft: float


@dataclass(frozen=True)
class ActivityTerm:
    activity: Activity
    inputs: tuple[ActivityPart, ...]
    outputs: tuple[ActivityPart, ...]
    craft_capacity: float  # math.inf when unlimited or relaxed


@dataclass(frozen=True)
class ImportTerm:
    feed_id: str
    budget_id: str
    material: Material
    endpoint: EndpointId
    ceiling: float  # math.inf when unlimited


@dataclass(frozen=True)
class OutletTerm:
    outlet_id: str
    material: Material
    endpoint: EndpointId
    requirement: str | None  # "exact" | "minimum" for exports, None for surplus
    rate: float
    ceiling: float  # sink ceiling, math.inf when unlimited


@dataclass(frozen=True)
class ModelInputs:
    """Adapter boundary between the contract graph and the LP.

    ``group_capacity`` holds the *effective* ceiling per capacity group after the
    contract's unknown-capacity relaxation (unknown -> inf, recorded in
    ``relaxations``). ``machine_groups`` names the groups that carry activity time
    and therefore survive delivery relaxation.
    """
    materials: tuple[Material, ...]
    arcs: tuple[ArcTerm, ...]
    activities: tuple[ActivityTerm, ...]
    imports: tuple[ImportTerm, ...]
    exports: tuple[OutletTerm, ...]
    surplus: tuple[OutletTerm, ...]
    budget_capacity: dict[str, float]
    budget_material: dict[str, Material]
    group_capacity: dict[str, float]
    machine_groups: frozenset[str]
    objective_export_id: str | None
    relaxations: dict[str, tuple[str, ...]] = field(default_factory=dict)
    disabled_arcs: tuple[str, ...] = ()
    excluded_activities: tuple[str, ...] = ()
    unknown_groups: tuple[str, ...] = ()
    unknown_activities: tuple[str, ...] = ()

    def with_group_capacity(self, overrides: dict[str, float]) -> "ModelInputs":
        unknown = set(overrides) - set(self.group_capacity)
        if unknown:
            raise KeyError(f"unknown capacity group override: {sorted(unknown)}")
        return replace(self, group_capacity={**self.group_capacity, **overrides})


def count_model(inputs: ModelInputs, stage: str) -> dict[str, int]:
    """Cheap size estimate before any allocation happens."""
    flows = sum(len(t.materials) for t in inputs.arcs) if stage == "routing" else 0
    variables = flows + len(inputs.activities) + len(inputs.imports) + len(inputs.exports) + len(inputs.surplus)
    nonzeros = 2 * flows + sum(len(t.materials) * len(t.arc.resources) for t in inputs.arcs) if stage == "routing" else 0
    nonzeros += sum(len(t.inputs) + len(t.outputs) + len(t.activity.resources) for t in inputs.activities)
    nonzeros += 2 * len(inputs.imports) + len(inputs.exports) + len(inputs.surplus)
    return {"variables": variables, "nonzeros_upper_bound": nonzeros}


class LPModel:
    """Sparse LP in scipy form: min c.x, A_ub x <= b_ub, A_eq x = b_eq, l <= x <= u."""

    def __init__(self):
        self.var_keys: list[tuple] = []
        self.var_index: dict[tuple, int] = {}
        self.lower: list[float] = []
        self.upper: list[float] = []
        self.row_keys: list[tuple] = []
        self.row_index: dict[tuple, int] = {}
        self.row_sense: list[str] = []
        self.rhs: list[float] = []
        self.entries: list[tuple[int, int, float]] = []

    def copy(self) -> "LPModel":
        other = LPModel()
        for name in ("var_keys", "lower", "upper", "row_keys", "row_sense", "rhs", "entries"):
            setattr(other, name, list(getattr(self, name)))
        other.var_index = dict(self.var_index)
        other.row_index = dict(self.row_index)
        return other

    def variable(self, key: tuple, lower: float = 0.0, upper: float = math.inf) -> int:
        if key in self.var_index:
            raise ValueError(f"duplicate variable {key}")
        self.var_index[key] = col = len(self.var_keys)
        self.var_keys.append(key)
        self.lower.append(lower)
        self.upper.append(upper)
        return col

    def row(self, key: tuple, sense: str, rhs: float) -> int:
        idx = self.row_index.get(key)
        if idx is None:
            self.row_index[key] = idx = len(self.row_keys)
            self.row_keys.append(key)
            self.row_sense.append(sense)
            self.rhs.append(rhs)
        return idx

    def add(self, row: int, col: int, value: float) -> None:
        self.entries.append((row, col, value))

    @property
    def n_variables(self) -> int:
        return len(self.var_keys)

    @property
    def n_rows(self) -> int:
        return len(self.row_keys)

    @property
    def nonzeros(self) -> int:
        return len(self.entries)

    def matrices(self):
        import numpy as np
        import scipy.sparse as sp

        n = self.n_variables
        rows = {"eq": [], "ub": []}
        local = [0] * self.n_rows
        for i, sense in enumerate(self.row_sense):
            local[i] = len(rows[sense])
            rows[sense].append(i)
        parts = {"eq": ([], [], []), "ub": ([], [], [])}
        for r, c, v in self.entries:
            sense = self.row_sense[r]
            parts[sense][0].append(local[r])
            parts[sense][1].append(c)
            parts[sense][2].append(v)

        def matrix(sense):
            m = len(rows[sense])
            if m == 0:
                return None, None
            data = parts[sense]
            a = sp.coo_matrix((np.array(data[2], dtype=float), (np.array(data[0]), np.array(data[1]))), shape=(m, n)).tocsr()
            b = np.array([self.rhs[i] for i in rows[sense]], dtype=float)
            return a, b

        a_ub, b_ub = matrix("ub")
        a_eq, b_eq = matrix("eq")
        bounds = np.array([self.lower, self.upper], dtype=float).T
        return a_ub, b_ub, a_eq, b_eq, bounds, rows


def _finite(value: float) -> bool:
    return math.isfinite(value)


def build_lp(inputs: ModelInputs, stage: str) -> LPModel:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}")
    routing = stage == "routing"
    budgets_on = stage != "aggregate"
    m = LPModel()

    def node(endpoint: EndpointId, material: Material) -> int:
        key = ("node", endpoint if routing else POOL, material)
        return m.row(key, "eq", 0.0)

    def charge(col: int, resources, materials_count: int = 1) -> None:
        for use in resources:
            cap = inputs.group_capacity[use.group_id]
            if _finite(cap):
                m.add(m.row(("group", use.group_id), "ub", cap), col, use.coefficient)

    if routing:
        for term in inputs.arcs:
            for material in term.materials:
                col = m.variable(("flow", term.arc.id, material))
                m.add(node(term.source, material), col, -1.0)
                m.add(node(term.target, material), col, 1.0)
                charge(col, term.arc.resources)
    for term in inputs.activities:
        col = m.variable(("craft", term.activity.id), 0.0, term.craft_capacity)
        for part in term.inputs:
            m.add(node(part.endpoint, part.material), col, -part.amount_per_craft)
        for part in term.outputs:
            m.add(node(part.endpoint, part.material), col, part.amount_per_craft)
        charge(col, term.activity.resources)
    for term in inputs.imports:
        ceiling = term.ceiling if budgets_on else math.inf
        col = m.variable(("import", term.feed_id), 0.0, ceiling)
        m.add(node(term.endpoint, term.material), col, 1.0)
        if budgets_on:
            cap = inputs.budget_capacity[term.budget_id]
            if _finite(cap):
                m.add(m.row(("budget", term.budget_id), "ub", cap), col, 1.0)
    for term in inputs.exports:
        upper = term.rate if term.requirement == "exact" else term.ceiling
        col = m.variable(("export", term.outlet_id), term.rate, upper)
        m.add(node(term.endpoint, term.material), col, -1.0)
    for term in inputs.surplus:
        col = m.variable(("surplus", term.outlet_id), 0.0, term.ceiling)
        m.add(node(term.endpoint, term.material), col, -1.0)
    return m


def objective_vector(model: LPModel, objective_export_id: str | None):
    import numpy as np

    c = np.zeros(model.n_variables)
    if objective_export_id is not None:
        c[model.var_index[("export", objective_export_id)]] = -1.0
    return c


def cleanup_vector(model: LPModel, objective_export_id: str | None):
    """Secondary cost: total flow, crafts, imports, surplus and non-objective exports."""
    import numpy as np

    c = np.ones(model.n_variables)
    if objective_export_id is not None:
        c[model.var_index[("export", objective_export_id)]] = 0.0
    return c


@dataclass
class LPSolution:
    status: int  # scipy: 0 optimal, 1 iteration limit, 2 infeasible, 3 unbounded, 4 numerical
    message: str
    x: object | None
    fun: float | None
    ineq_marginals: object | None
    eq_marginals: object | None
    seconds: float
    rows: dict


def solve_lp(model: LPModel, c, *, time_limit: float, pin: tuple | None = None) -> LPSolution:
    """Solve min c.x; ``pin=(vector, value)`` adds the equality vector.x = value."""
    import numpy as np
    import scipy.sparse as sp
    from scipy.optimize import linprog

    a_ub, b_ub, a_eq, b_eq, bounds, rows = model.matrices()
    if pin is not None:
        vector, value = pin
        extra = sp.csr_matrix(np.asarray(vector, dtype=float).reshape(1, -1))
        a_eq = extra if a_eq is None else sp.vstack([a_eq, extra]).tocsr()
        b_eq = np.array([value]) if b_eq is None else np.append(b_eq, value)
    started = time.perf_counter()
    res = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs",
                  options={"time_limit": time_limit, "primal_feasibility_tolerance": 1e-9,
                           "dual_feasibility_tolerance": 1e-9})
    seconds = time.perf_counter() - started
    ineq = res.ineqlin.marginals if res.status == 0 and a_ub is not None else None
    eq = res.eqlin.marginals if res.status == 0 and a_eq is not None else None
    if pin is not None and eq is not None:
        eq = eq[:-1]
    return LPSolution(int(res.status), str(res.message), res.x if res.status == 0 else None,
                      float(res.fun) if res.status == 0 else None, ineq, eq, seconds, rows)


@dataclass(frozen=True)
class CutTerm:
    label: tuple
    multiplier: float
    contribution: float


@dataclass(frozen=True)
class DualCertificate:
    """Weak-duality lower bound on min c.x over the model, recomputed from y.

    For any feasible x: c.x = r.x + y_ub.(A_ub x) + y_eq.(A_eq x) with
    r = c - A_ub^T y_ub - A_eq^T y_eq. With y_ub <= 0 the middle term is
    >= y_ub.b_ub, the last equals y_eq.b_eq, and r.x >= sum_j min(r_j l_j, r_j u_j).
    ``valid`` is False when some r_j < -tolerance on a variable without a finite
    upper bound, which would send the bound to -infinity.
    """
    value: float
    valid: bool
    worst_reduced_cost: float
    cut: tuple[CutTerm, ...]


def dual_bound(model: LPModel, c, solution: LPSolution, *, tolerance: float) -> DualCertificate | None:
    import numpy as np

    if solution.status != 0:
        return None
    a_ub, b_ub, a_eq, b_eq, bounds, rows = model.matrices()
    r = np.array(c, dtype=float)
    value = 0.0
    cut: list[CutTerm] = []
    y_ub = solution.ineq_marginals
    if a_ub is not None and y_ub is not None:
        y_ub = np.minimum(np.asarray(y_ub, dtype=float), 0.0)  # sign convention: <= rows have y <= 0
        r -= a_ub.T @ y_ub
        value += float(y_ub @ b_ub)
        for local, mult in enumerate(y_ub):
            if abs(mult) > tolerance:
                cut.append(CutTerm(model.row_keys[rows["ub"][local]], float(mult), float(mult * b_ub[local])))
    y_eq = solution.eq_marginals
    if a_eq is not None and y_eq is not None:
        y_eq = np.asarray(y_eq, dtype=float)
        r -= a_eq.T @ y_eq
        value += float(y_eq @ b_eq)
        for local, mult in enumerate(y_eq):
            if abs(mult) > tolerance:
                cut.append(CutTerm(model.row_keys[rows["eq"][local]], float(mult), float(mult * b_eq[local])))
    worst = 0.0
    valid = True
    for j, rc in enumerate(r):
        lower, upper = bounds[j]
        if rc >= 0:
            if lower != 0 and abs(rc) > tolerance:
                cut.append(CutTerm(("lower",) + model.var_keys[j], float(rc), float(rc * lower)))
            value += rc * lower
        elif math.isfinite(upper):
            if abs(rc) > tolerance:
                cut.append(CutTerm(("upper",) + model.var_keys[j], float(rc), float(rc * upper)))
            value += rc * upper
        else:
            worst = min(worst, float(rc))
            if rc < -tolerance:
                valid = False
    return DualCertificate(float(value), valid, worst, tuple(cut))


def shortfall_model(model: LPModel, exports: tuple[OutletTerm, ...]) -> tuple[LPModel, object]:
    """Minimum total export shortfall; feasible whenever the plain model has any point.

    exact:   export + short - over = rate,  minimum: export + short >= rate.
    Export variables lose their requirement bounds; sink ceilings stay.
    """
    import numpy as np

    m = model.copy()
    slack_cols = []
    for term in exports:
        col = m.var_index[("export", term.outlet_id)]
        m.lower[col] = 0.0
        m.upper[col] = term.ceiling
        short = m.variable(("short", term.outlet_id))
        slack_cols.append(short)
        if term.requirement == "exact":
            over = m.variable(("over", term.outlet_id))
            slack_cols.append(over)
            row = m.row(("shortfall", term.outlet_id), "eq", term.rate)
            m.add(row, col, 1.0)
            m.add(row, short, 1.0)
            m.add(row, over, -1.0)
        else:
            row = m.row(("shortfall", term.outlet_id), "ub", -term.rate)
            m.add(row, col, -1.0)
            m.add(row, short, -1.0)
    c = np.zeros(m.n_variables)
    c[slack_cols] = 1.0
    return m, c


def describe_label(label: tuple) -> str:
    kind = label[0]
    if kind == "node":
        endpoint = label[1]
        where = "pool" if endpoint == POOL else endpoint.key
        return f"conservation of {label[2].name} at {where}"
    if kind == "group":
        return f"capacity group {label[1]}"
    if kind == "budget":
        return f"budget {label[1]}"
    if kind == "shortfall":
        return f"export requirement {label[1]}"
    if kind in ("upper", "lower"):
        inner = label[1:]
        names = {"craft": "craft capacity of activity", "import": "feed ceiling", "export": "export",
                 "surplus": "surplus ceiling", "flow": "flow", "short": "shortfall", "over": "overshoot"}
        what = names.get(inner[0], inner[0])
        ident = inner[1] if len(inner) > 1 else ""
        side = "ceiling" if kind == "upper" else "requirement"
        return f"{what} {ident} {side}"
    return str(label)
