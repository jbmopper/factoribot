"""Sparse LP layer for delivery bounds: build, solve, certify, clean up.

This module knows nothing about blueprints. ``blueprint_plan`` resolves the
routing contract (lane aliases, eligibility, control state, furnace filtering,
unknown-capacity relaxation) into ``ModelInputs``; this module turns one stage
of that record into a sparse HiGHS model and returns raw solutions plus
weak-duality certificates. Every certificate is recomputed here from the
matrices and the returned multipliers; the optimizer's status word is never
the proof, and neither is the size of a violation: a solver may report
"optimal" while its multipliers are dual-infeasible by less than its own
tolerance, which on a column with no ceiling is the difference between a
finite bound and an unbounded objective. See ``DualCertificate`` and
``implied_upper_bounds``.

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
    >= y_ub.b_ub, the last equals y_eq.b_eq, and
    r.x >= sum_j inf{ r_j t : l_j <= t <= U_j } where ``U_j`` is *any* ceiling
    proven to hold at every feasible point (the declared bound, or one derived by
    interval propagation over the rows -- see ``implied_upper_bounds``).

    That last term is ``-infinity`` as soon as one r_j is negative on a variable
    with no such ceiling, *however small* |r_j| is: x_j may be arbitrarily large,
    so r_j x_j is unbounded below and y proves nothing. Magnitude is therefore
    never a reason to discard a negative reduced cost; only a proven ceiling is.
    A threshold could at best hide the *floating-point error of evaluating r*, so
    that error is removed instead of estimated: each r_j is evaluated exactly
    (error-free products plus ``fsum``, which also reports whether the result is
    the exact value), every product and sum in the bound is rounded against the
    claim, and only a genuinely negative r_j reaches the ceiling question.

    When a genuine violation does appear on a column with no ceiling, the last
    resort is ``_repair_step``: walk the multipliers back towards y = 0, which is
    always dual feasible where the column's own cost is, and re-certify. It can
    only give back a bound the trivial multipliers already supported, so it never
    rescues an unbounded objective.

    ``value`` is a rigorous lower bound on min c.x (pessimistically rounded);
    ``valid`` is False when that bound is -infinity, when the multipliers are not
    finite, or when a row with a non-zero multiplier has an infinite right-hand
    side. ``worst_reduced_cost`` is the most negative reduced cost over the
    columns with no finite ceiling; ``uncertified_variables`` names them.
    """
    value: float
    valid: bool
    worst_reduced_cost: float
    cut: tuple[CutTerm, ...]
    uncertified_variables: tuple[tuple, ...] = ()
    reason: str = ""


# Unit roundoff of IEEE-754 binary64: |fl(a op b) - (a op b)| <= _U * |a op b|.
_U = 2.0 ** -53
# Slack added when a *derived* ceiling is rounded outwards. A derived ceiling may be
# made larger without losing validity (a larger box only weakens the bound), so the
# few floating-point operations that produce it are covered by inflating it.
_BOUND_SLACK = 1e-9

try:  # exact product residual: fma(a, b, -fl(a*b)) is the error of one multiplication
    _fma = math.fma
except AttributeError:  # pragma: no cover - Python < 3.13
    from fractions import Fraction

    def _fma(a, b, c):
        return float(Fraction(a) * Fraction(b) + Fraction(c))


def _gamma(k: int) -> float:
    """Classic k-term dot-product error factor: |fl(sum) - sum| <= gamma_k * sum|terms|."""
    d = 1.0 - k * _U
    return math.inf if d <= 0 else (k * _U) / d


def _inflate(value: float) -> float:
    """Round a derived ceiling outwards (upwards), which never invalidates it."""
    return value + abs(value) * _BOUND_SLACK + 1e-12


def _product_low(a: float, b: float) -> float:
    """The largest float that is provably <= the real product a*b."""
    p = a * b
    if p == 0.0 or not math.isfinite(p):
        return p
    return p if _fma(a, b, -p) >= 0.0 else math.nextafter(p, -math.inf)


def _sum_low(terms) -> float:
    """The largest float that is provably <= the real sum of ``terms``."""
    terms = list(terms)
    total = math.fsum(terms)
    if not math.isfinite(total):
        return total
    # fsum is correctly rounded, so this residual is the exact sum minus ``total``.
    return total if math.fsum(terms + [-total]) >= 0.0 else math.nextafter(total, -math.inf)


def _exact_reduced_cost(cost: float, column) -> tuple[float, float]:
    """``(value, error)`` bracketing r_j = c_j - sum_i a_ij y_i, with error 0 when exact.

    Each product is split into its float part and its exact residual, so ``fsum``
    returns the correctly rounded true value; the second ``fsum`` is that value's
    exact distance from the truth. A zero residual proves ``value`` *is* r_j, which
    is what lets a clean model keep a bit-exact bound instead of a widened one.
    """
    terms = [float(cost)]
    for coefficient, y in column:
        if coefficient == 0.0 or y == 0.0:
            continue
        product = -coefficient * y
        terms.append(product)
        residual = _fma(-coefficient, y, -product)
        if residual:
            terms.append(residual)
    value = math.fsum(terms)
    if not math.isfinite(value):
        return value, math.inf
    error = math.fsum(terms + [-value])
    return value, abs(error) * (1.0 + 2.0 ** -52)


def implied_upper_bounds(model: LPModel, *, rounds: int = 8) -> list[float]:
    """Ceilings that hold at EVERY feasible point of the model, by interval propagation.

    For a row ``sum_j a_j x_j <= b`` (an ``ub`` row, and either direction of an
    ``eq`` row) and a column ``k`` with ``a_k > 0``::

        a_k x_k <= b - sum_{j != k} a_j x_j <= b - (L - a_k l_k)

    where ``L = sum_j inf(a_j x_j)`` over the current box, so
    ``x_k <= l_k + (b - L) / a_k`` whenever ``L`` is finite. The mirrored
    ``>= b`` direction of an equality row bounds the columns with ``a_k < 0``.
    Every derived ceiling is inflated (``_inflate``) so floating-point error in
    its own evaluation cannot make it too small, and is never allowed below the
    column's lower bound. Bounds only ever tighten, so the iteration is monotone
    and is capped at ``rounds`` passes.

    This is a statement about the feasible set alone: it holds whether or not the
    model is optimal, unbounded or empty, and it is what lets a certificate charge
    a negative reduced cost against a real ceiling instead of discarding it.
    """
    a_ub, b_ub, a_eq, b_eq, bounds, rows = model.matrices()
    lower = [float(v) for v in bounds[:, 0]]
    upper = [float(v) for v in bounds[:, 1]]
    if any(not math.isfinite(v) for v in lower):
        return upper  # the propagation formulas assume finite lower bounds
    by_row: list[tuple[str, float, list[tuple[int, float]]]] = []
    for matrix, rhs, sense in ((a_ub, b_ub, "ub"), (a_eq, b_eq, "eq")):
        if matrix is None:
            continue
        csr = matrix.tocsr()
        for local in range(csr.shape[0]):
            span = slice(csr.indptr[local], csr.indptr[local + 1])
            cols = [(int(j), float(v)) for j, v in zip(csr.indices[span], csr.data[span]) if v != 0.0]
            if cols and math.isfinite(rhs[local]):
                by_row.append((sense, float(rhs[local]), cols))
    for _ in range(rounds):
        changed = False
        for sense, rhs, cols in by_row:
            low_activity = high_activity = 0.0
            low_infinite = high_infinite = False
            for col, a in cols:
                if a > 0:
                    low_activity += a * lower[col]
                    if math.isinf(upper[col]):
                        high_infinite = True
                    else:
                        high_activity += a * upper[col]
                else:
                    high_activity += a * lower[col]
                    if math.isinf(upper[col]):
                        low_infinite = True
                    else:
                        low_activity += a * upper[col]
            for col, a in cols:
                if a > 0 and not low_infinite:  # from  sum a_j x_j <= rhs
                    candidate = lower[col] + (rhs - low_activity) / a
                elif a < 0 and sense == "eq" and not high_infinite:  # from  sum a_j x_j >= rhs
                    candidate = lower[col] + (rhs - high_activity) / a
                else:
                    continue
                if not math.isfinite(candidate):
                    continue
                candidate = max(lower[col], _inflate(candidate))
                if candidate < upper[col] * (1.0 - 1e-6) or math.isinf(upper[col]):
                    upper[col] = candidate
                    changed = True
        if not changed:
            break
    return upper


def _columns(model: LPModel, data, y_ub, y_eq):
    """Per-column ``[(a_ij, y_i)]`` taken from the assembled matrices, not the raw entries."""
    import numpy as np

    a_ub, b_ub, a_eq, b_eq, bounds, rows = data
    columns: list[list[tuple[float, float]]] = [[] for _ in range(model.n_variables)]
    for matrix, y in ((a_ub, y_ub), (a_eq, y_eq)):
        if matrix is None or y is None:
            continue
        csc = matrix.tocsc()
        y = np.asarray(y, dtype=float)
        for col in range(csc.shape[1]):
            span = slice(csc.indptr[col], csc.indptr[col + 1])
            for local, value in zip(csc.indices[span], csc.data[span]):
                if value != 0.0 and y[local] != 0.0:
                    columns[col].append((float(value), float(y[local])))
    return columns


def _weak_duality(model: LPModel, c, y_ub, y_eq, data, tolerance: float,
                  cache: dict) -> tuple[DualCertificate, list[tuple[int, float, float, int]]]:
    """One rigorous weak-duality evaluation for the given multipliers.

    Returns the certificate and, when it fails, the blocking columns as
    ``(column, oriented reduced cost, error, direction)`` for the repair step.
    """
    import numpy as np

    a_ub, b_ub, a_eq, b_eq, bounds, rows = data
    n = model.n_variables
    costs = np.array(c, dtype=float)
    approximate = costs.copy()
    magnitude = np.abs(costs)
    counts = np.ones(n)  # the c_j term itself
    terms: list[float] = []
    cut: list[CutTerm] = []
    reasons: list[str] = []

    def rows_block(a, b, y, row_ids):
        """Accumulate y.b, r -= A^T y and the error data for one row block."""
        nonlocal approximate, magnitude, counts
        if a is None or y is None:
            return True
        y = np.asarray(y, dtype=float)
        if not np.all(np.isfinite(y)):
            reasons.append("solver returned non-finite multipliers")
            return False
        if np.any((y != 0.0) & ~np.isfinite(b)):
            reasons.append("a row with an infinite right-hand side carries a non-zero multiplier")
            return False
        approximate = approximate - a.T @ y
        absolute = abs(a)
        magnitude = magnitude + absolute.T @ np.abs(y)
        counts = counts + np.asarray((absolute != 0).sum(axis=0)).ravel()
        for local, multiplier in enumerate(y):
            if multiplier == 0.0:
                continue
            terms.append(_product_low(float(multiplier), float(b[local])))
            if abs(multiplier) > tolerance:
                cut.append(CutTerm(model.row_keys[row_ids[local]], float(multiplier), float(multiplier * b[local])))
        return True

    ok = rows_block(a_ub, b_ub, y_ub, rows["ub"])
    ok = rows_block(a_eq, b_eq, y_eq, rows["eq"]) and ok
    if not ok:
        return DualCertificate(-math.inf, False, -math.inf, tuple(cut), (), "; ".join(reasons)), []

    # Cheap bracket on r, used only to select the columns that must be evaluated exactly:
    # a column pinned at zero by a provably non-negative reduced cost contributes nothing.
    slack = np.array([2.0 * _gamma(int(k) + 1) for k in counts]) * magnitude
    lower_bounds, upper_bounds = bounds[:, 0], bounds[:, 1]
    columns = None
    uncertified: list[tuple] = []
    blockers: list[tuple[int, float, float, int]] = []
    worst = 0.0
    for j in range(n):
        low, high = float(lower_bounds[j]), float(upper_bounds[j])
        if low == 0.0 and approximate[j] - slack[j] >= 0.0:
            continue  # r_j >= 0 is already proven and inf{r_j t : 0 <= t} = 0
        if columns is None:
            columns = _columns(model, data, y_ub, y_eq)
        reduced, error = _exact_reduced_cost(float(costs[j]), columns[j])
        low_r, high_r = reduced - error, reduced + error
        source = "upper"
        if math.isinf(high) and low_r < 0.0:
            # No declared ceiling and a negative reduced cost: this box term is -infinity
            # unless the constraints themselves prove a ceiling for the column.
            if "implied" not in cache:
                cache["implied"] = implied_upper_bounds(model)
            if math.isfinite(cache["implied"][j]):
                high, source = float(cache["implied"][j]), "implied"
        if math.isinf(high) and low_r < 0.0:
            worst = min(worst, low_r)
            uncertified.append(model.var_keys[j])
            blockers.append((j, low_r, error, 1))
            continue
        if math.isinf(low) and high_r > 0.0:  # a free column priced the wrong way
            worst = min(worst, -high_r)
            uncertified.append(model.var_keys[j])
            blockers.append((j, -high_r, error, -1))
            continue
        candidates = []
        if math.isfinite(low):
            candidates += [_product_low(low_r, low), _product_low(high_r, low)]
        if math.isfinite(high):
            candidates += [_product_low(low_r, high), _product_low(high_r, high)]
        if not candidates:  # a free column priced at exactly zero contributes nothing
            continue
        contribution = min(candidates)
        if contribution != 0.0:
            terms.append(contribution)
        if max(abs(low_r), abs(high_r)) > tolerance and contribution != 0.0:
            label = ((source,) if low_r < 0.0 else ("lower",)) + model.var_keys[j]
            cut.append(CutTerm(label, reduced, contribution))
    if uncertified:
        reason = (f"{len(uncertified)} column(s) have a negative reduced cost and no provable ceiling, so these "
                  "multipliers bound nothing: the objective may be unbounded")
        return DualCertificate(-math.inf, False, worst, tuple(cut), tuple(uncertified), reason), blockers
    return DualCertificate(_sum_low(terms), True, worst, tuple(cut), (), ""), []


def _repair_step(c, blockers) -> float:
    """Largest provably safe step from the trivial multipliers y = 0 towards y.

    ``y(t) = t*y`` gives ``r(t) = (1 - t)*c + t*r``, affine in ``t``, and ``t = 0``
    is always dual feasible on a column whose own cost points the safe way. So for
    every blocking column solve ``(1 - t)*c_j + t*r_j >= need`` and take the smallest
    root, where ``need`` covers re-evaluating everything at the scaled multipliers.
    A column whose own cost points the wrong way admits no positive step, which is
    exactly the genuinely unbounded case: this repair can only absorb a violation
    smaller than the column's own cost, and can never manufacture a bound for an
    objective that has none (at ``t = 0`` the certificate is the trivial, true one).
    """
    step = 1.0
    for j, reduced, error, direction in blockers:
        # ``cost`` and ``reduced`` are oriented so that both must stay >= 0: a column
        # bounded only from below needs r >= 0, a free column needs r <= 0.
        cost = direction * float(c[j])
        need = 3.0 * error + 8.0 * _U * abs(cost)
        span = cost - reduced
        if cost <= need or span <= 0.0:
            return 0.0
        step = min(step, (cost - need) / span)
    return max(0.0, min(1.0, step) * (1.0 - 1e-12))


def dual_bound(model: LPModel, c, solution: LPSolution, *, tolerance: float) -> DualCertificate | None:
    """Recompute a rigorous weak-duality bound from the returned multipliers.

    ``tolerance`` selects which terms are *reported* in the cut; it is not a licence
    to ignore a negative reduced cost. Soundness comes from the exact evaluation of
    ``r``, from ceilings proven to hold at every feasible point, and from the repair
    step above -- never from a magnitude threshold.
    """
    import numpy as np

    if solution.status != 0:
        return None
    data = model.matrices()
    a_ub, b_ub, a_eq, b_eq, bounds, rows = data
    # Sign convention: <= rows have y <= 0. Clamping is sound -- any y_ub <= 0 is admissible.
    y_ub = (None if a_ub is None or solution.ineq_marginals is None
            else np.minimum(np.asarray(solution.ineq_marginals, dtype=float), 0.0))
    y_eq = None if a_eq is None or solution.eq_marginals is None else np.asarray(solution.eq_marginals, dtype=float)
    cache: dict = {}  # implied ceilings, derived at most once and shared with the repair pass

    certificate, blockers = _weak_duality(model, c, y_ub, y_eq, data, tolerance, cache)
    if certificate.valid or not blockers:
        return certificate
    step = _repair_step(c, blockers)
    if step <= 0.0:
        return certificate
    repaired, _ = _weak_duality(model, c, None if y_ub is None else y_ub * step,
                                None if y_eq is None else y_eq * step, data, tolerance, cache)
    if not repaired.valid:
        return certificate
    return replace(repaired, reason=f"multipliers scaled by {step:.17g} to restore provable dual feasibility on "
                                    f"{len(blockers)} column(s) whose reduced cost had no ceiling to charge")


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
    if kind in ("upper", "lower", "implied"):
        inner = label[1:]
        names = {"craft": "craft capacity of activity", "import": "feed ceiling", "export": "export",
                 "surplus": "surplus ceiling", "flow": "flow", "short": "shortfall", "over": "overshoot"}
        what = names.get(inner[0], inner[0])
        ident = inner[1] if len(inner) > 1 else ""
        side = {"upper": "ceiling", "lower": "requirement", "implied": "ceiling implied by the constraints"}[kind]
        return f"{what} {ident} {side}"
    return str(label)
