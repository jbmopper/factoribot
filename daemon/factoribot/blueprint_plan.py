"""Couple local transport flows to installed production (routing task 05).

Consumes a contract ``SpatialGraph`` plus ``RoutingRequest`` and returns a
contract ``AnalysisResult`` together with per-stage diagnostics. Three nested
upper bounds (``aggregate`` >= ``budget`` >= ``routing``) come from one
per-entity model by relaxing named constraints (see ``routing_lp``).

Soundness rules implemented here:

* nothing is imported or removed except declared feeds, exports and surplus;
* unknown capacities are relaxed to unlimited and the relaxation is recorded;
* ``unresolved_reasons`` (contract) decides whether bounds may be advertised;
* every reported value is a weak-duality certificate recomputed from the
  multipliers, never the optimizer's status word;
* every published allocation is re-checked by ``verify_allocation``, which walks
  the graph and request directly and shares no code with the LP builder.

No achievable-rate claim is made anywhere: a feasible relaxation is only a
continuous allocation, and a bound is only an upper bound.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
import math
import time

from .blueprint_contract import (
    SCHEMA_VERSION, ContractError, EndpointId, Material, Capacity, Lane, DetailScope,
    SpatialGraph, RoutingRequest, to_dict, content_hash, parse_request,
    unresolved_reasons, declared_assumptions,
)
from .findings import AnalysisResult, parse_result, finding_id, comparison_hash
from .routing_lp import (
    STAGES, STAGE_RELAXATIONS, POOL, ArcTerm, ActivityPart, ActivityTerm, ImportTerm, OutletTerm,
    ModelInputs, LPModel, count_model, build_lp, objective_vector, cleanup_vector, solve_lp,
    dual_bound, shortfall_model, describe_label, DualCertificate, CutTerm,
)

ANALYZER_VERSION = "blueprint-plan-0.1.0"
TOLERANCE = 1e-7
LIMITATIONS = (
    "Upper bounds from a continuous steady-state relaxation; no achieved-rate or positive lower bound is claimed.",
    "Only declared feeds, exports and surplus outlets move material across the boundary; nothing is inferred.",
    "Splitter scheduling, lane ordering, inserter timing and back-pressure are not modeled; feasibility of the relaxation does not prove game behaviour.",
    "Unknown capacities are relaxed to unlimited where recorded; they are never used as restrictive ceilings.",
)


@dataclass(frozen=True)
class PlanOptions:
    time_limit_s: float = 20.0
    max_variables: int = 2_000_000
    max_nonzeros: int = 8_000_000
    tolerance: float = TOLERANCE
    stages: tuple[str, ...] = STAGES


@dataclass(frozen=True)
class Allocation:
    """A candidate allocation in graph terms (the witness form)."""
    flows: dict[tuple[str, Material], float]
    crafts: dict[str, float]
    imports: dict[str, float]
    exports: dict[str, float]
    surplus: dict[str, float]


@dataclass(frozen=True)
class Verification:
    ok: bool
    violations: tuple[str, ...]
    max_conservation_residual: float
    max_capacity_excess: float
    objective_value: float | None
    seconds: float


@dataclass
class StageSolution:
    stage: str
    state: str  # optimal | unlimited | feasible | infeasible | limit | size_limit | uncertified
    value: float | None  # certified upper bound (math.inf for unlimited), None if none
    primal: float | None
    dual: float | None
    sizes: dict
    timings: dict
    relaxations: tuple[str, ...]
    certificate: str
    cut: tuple[CutTerm, ...]
    allocation: Allocation | None
    verification: Verification | None
    shortfall: float | None
    notes: tuple[str, ...] = ()


@dataclass
class DeliveryReport:
    result: AnalysisResult
    stages: dict[str, StageSolution]
    unresolved: tuple[str, ...]
    inputs: ModelInputs | None


# --------------------------------------------------------------------------
# Adapter boundary: contract graph + request -> ModelInputs
# --------------------------------------------------------------------------

def _endpoints(graph: SpatialGraph):
    return {p.id: p for p in graph.ports + graph.lanes + graph.inventories}


def resolve_endpoint(endpoints, endpoint: EndpointId, role: str) -> EndpointId:
    """Lane aliases: entering material uses the lane's incoming port, leaving uses outgoing."""
    obj = endpoints[endpoint]
    if isinstance(obj, Lane):
        return obj.incoming if role == "in" else obj.outgoing
    return endpoint


def _capacity_value(capacity: Capacity) -> float:
    return capacity.value if capacity.kind == "finite" else math.inf


def _arc_enabled(arc, request: RoutingRequest) -> bool:
    if arc.semantics != "conditional":
        return True
    if request.assumptions.control_policy == "relax_open":
        return True
    state = {c.condition: c.enabled for c in request.assignments.controls}
    return all(state.get(name, False) for name in arc.conditions)


def resolve_model_inputs(graph: SpatialGraph, request: RoutingRequest) -> ModelInputs:
    """Interpret the contract for the LP. This is the boundary task 04 targets.

    Requirements on the graph (routing.py): one physical resource == one
    capacity group charged once per traversal; lanes are aliases; conditions are
    named; unsupported topology is a TopologyGap; deterministic ordering.
    """
    endpoints = _endpoints(graph)
    entities = {e.id: e for e in graph.entities}
    budgets = {b.id: b for b in request.budgets}
    universe = {b.material for b in request.budgets}
    universe |= {x.material for x in request.exports + request.surplus}
    universe |= {p.material for a in graph.activities for p in a.inputs + a.outputs}
    materials = tuple(sorted((m for m in universe if m.kind == "item"), key=lambda m: (m.kind, m.name, m.quality or "")))

    unknown_groups, relaxed = [], {stage: list(STAGE_RELAXATIONS[stage]) for stage in STAGES}
    group_capacity, machine_groups = {}, set()
    for group in graph.capacity_groups:
        group_capacity[group.id] = _capacity_value(group.capacity)
        if group.unit == "seconds/s":
            machine_groups.add(group.id)
        if group.capacity.kind == "unknown":
            unknown_groups.append(group.id)
            relaxed["routing"].append("unknown_capacity_unlimited")
            if group.unit == "seconds/s":
                relaxed["aggregate"].append("unknown_capacity_unlimited")
                relaxed["budget"].append("unknown_capacity_unlimited")

    arcs, disabled = [], []
    for arc in graph.arcs:
        if not _arc_enabled(arc, request):
            disabled.append(arc.id)
            continue
        source = resolve_endpoint(endpoints, arc.source, "out")
        target = resolve_endpoint(endpoints, arc.target, "in")
        eligible = []
        for material in materials:
            ok = arc.eligibility.allows(material)
            ok &= endpoints[source].eligibility.allows(material) and endpoints[target].eligibility.allows(material)
            for alias in (arc.source, arc.target):
                if isinstance(endpoints[alias], Lane):
                    ok &= endpoints[alias].eligibility.allows(material)
            if ok:
                eligible.append(material)
        arcs.append(ArcTerm(arc, source, target, tuple(eligible)))
        if arc.semantics == "conditional" and request.assumptions.control_policy == "relax_open":
            relaxed["routing"].append("conditional_connections_open")
        if arc.semantics == "relaxed":
            relaxed["routing"].append("transport_semantics_relaxed")

    assigned = {f.entity: f.recipe for f in request.assignments.furnaces}
    activities, excluded, unknown_activities = [], [], []
    for activity in graph.activities:
        candidates = entities[activity.entity].furnace_candidates
        if candidates:
            chosen = assigned.get(activity.entity, candidates[0] if len(candidates) == 1 else None)
            if activity.recipe != chosen:
                excluded.append(activity.id)
                continue
        capacity = _capacity_value(activity.craft_capacity)
        if activity.craft_capacity.kind == "unknown":
            unknown_activities.append(activity.id)
            for stage in STAGES:
                relaxed[stage].append("unknown_capacity_unlimited")
        parts = lambda seq, role: tuple(ActivityPart(resolve_endpoint(endpoints, p.endpoint, role), p.material, p.amount_per_craft) for p in seq)
        activities.append(ActivityTerm(activity, parts(activity.inputs, "out"), parts(activity.outputs, "in"), capacity))

    imports = tuple(ImportTerm(f.id, f.budget_id, budgets[f.budget_id].material, resolve_endpoint(endpoints, f.endpoint, "in"),
                               _capacity_value(f.capacity)) for f in request.assignments.feeds)
    exports = tuple(OutletTerm(e.id, e.material, resolve_endpoint(endpoints, e.endpoint, "out"), e.requirement, e.rate,
                               _capacity_value(e.sink.capacity)) for e in request.exports)
    surplus = tuple(OutletTerm(s.id, s.material, resolve_endpoint(endpoints, s.endpoint, "out"), None, 0.0,
                               _capacity_value(s.sink.capacity)) for s in request.surplus)
    return ModelInputs(
        materials=materials, arcs=tuple(arcs), activities=tuple(activities), imports=imports, exports=exports,
        surplus=surplus, budget_capacity={b.id: _capacity_value(b.capacity) for b in request.budgets},
        budget_material={b.id: b.material for b in request.budgets}, group_capacity=group_capacity,
        machine_groups=frozenset(machine_groups), objective_export_id=request.objective.export_id,
        relaxations={stage: tuple(dict.fromkeys(names)) for stage, names in relaxed.items()},
        disabled_arcs=tuple(disabled), excluded_activities=tuple(excluded),
        unknown_groups=tuple(unknown_groups), unknown_activities=tuple(unknown_activities),
    )


# --------------------------------------------------------------------------
# Independent verification (graph walk; no LP matrices involved)
# --------------------------------------------------------------------------

def verify_allocation(graph: SpatialGraph, request: RoutingRequest, allocation: Allocation, *,
                      stage: str = "routing", tolerance: float = TOLERANCE,
                      inputs: ModelInputs | None = None) -> Verification:
    """Re-check conservation, capacities, budgets, outlets and objective from the graph.

    ``inputs`` may be passed to reuse the contract interpretation (enabled arcs,
    filtered activities, effective capacities); the arithmetic below never
    touches the LP builder.
    """
    started = time.perf_counter()
    inputs = inputs or resolve_model_inputs(graph, request)
    routing = stage == "routing"
    violations: list[str] = []
    balance: dict[tuple, float] = defaultdict(float)
    scale: dict[tuple, float] = defaultdict(float)
    use: dict[str, float] = defaultdict(float)

    def node(endpoint: EndpointId, material: Material) -> tuple:
        return (endpoint if routing else POOL, material)

    def move(endpoint: EndpointId, material: Material, amount: float) -> None:
        key = node(endpoint, material)
        balance[key] += amount
        scale[key] += abs(amount)

    def within(value: float, ceiling: float, label: str) -> None:
        if value > ceiling + tolerance * max(1.0, abs(ceiling) if math.isfinite(ceiling) else 1.0):
            violations.append(f"{label}: {value:.12g} exceeds {ceiling:.12g}")

    arcs = {t.arc.id: t for t in inputs.arcs}
    for (arc_id, material), rate in allocation.flows.items():
        if rate < -tolerance:
            violations.append(f"negative flow on {arc_id}")
        if not routing:
            violations.append(f"flow on {arc_id} while delivery is relaxed")
            continue
        term = arcs.get(arc_id)
        if term is None:
            violations.append(f"flow on disabled or unknown arc {arc_id}")
            continue
        if material not in term.materials:
            violations.append(f"{material.name} is not eligible on arc {arc_id}")
            continue
        move(term.source, material, -rate)
        move(term.target, material, rate)
        for res in term.arc.resources:
            use[res.group_id] += res.coefficient * rate

    activities = {t.activity.id: t for t in inputs.activities}
    for activity_id, crafts in allocation.crafts.items():
        term = activities.get(activity_id)
        if term is None:
            if crafts > tolerance:
                violations.append(f"crafts on excluded or unknown activity {activity_id}")
            continue
        if crafts < -tolerance:
            violations.append(f"negative crafts on {activity_id}")
        within(crafts, term.craft_capacity, f"craft capacity {activity_id}")
        for part in term.inputs:
            move(part.endpoint, part.material, -part.amount_per_craft * crafts)
        for part in term.outputs:
            move(part.endpoint, part.material, part.amount_per_craft * crafts)
        for res in term.activity.resources:
            use[res.group_id] += res.coefficient * crafts

    budget_use: dict[str, float] = defaultdict(float)
    feeds = {t.feed_id: t for t in inputs.imports}
    for feed_id, rate in allocation.imports.items():
        term = feeds.get(feed_id)
        if term is None:
            violations.append(f"import through undeclared feed {feed_id}")
            continue
        if rate < -tolerance:
            violations.append(f"negative import {feed_id}")
        if stage != "aggregate":
            within(rate, term.ceiling, f"feed ceiling {feed_id}")
        budget_use[term.budget_id] += rate
        move(term.endpoint, term.material, rate)

    exports = {t.outlet_id: t for t in inputs.exports}
    missing = set(exports) - set(allocation.exports)
    if missing:
        violations.append(f"exports not enumerated: {sorted(missing)}")
    for export_id, rate in allocation.exports.items():
        term = exports.get(export_id)
        if term is None:
            violations.append(f"export through undeclared outlet {export_id}")
            continue
        if rate < term.rate - tolerance * max(1.0, term.rate):
            violations.append(f"export {export_id}: {rate:.12g} below required {term.rate:.12g}")
        if term.requirement == "exact" and rate > term.rate + tolerance * max(1.0, term.rate):
            violations.append(f"export {export_id}: {rate:.12g} above exact {term.rate:.12g}")
        within(rate, term.ceiling, f"sink ceiling {export_id}")
        move(term.endpoint, term.material, -rate)

    outlets = {t.outlet_id: t for t in inputs.surplus}
    for surplus_id, rate in allocation.surplus.items():
        term = outlets.get(surplus_id)
        if term is None:
            violations.append(f"surplus through undeclared outlet {surplus_id}")
            continue
        if rate < -tolerance:
            violations.append(f"negative surplus {surplus_id}")
        within(rate, term.ceiling, f"surplus ceiling {surplus_id}")
        move(term.endpoint, term.material, -rate)

    worst_residual = 0.0
    for key, value in balance.items():
        limit = tolerance * max(1.0, scale[key])
        worst_residual = max(worst_residual, abs(value))
        if abs(value) > limit:
            where = "pool" if key[0] == POOL else key[0].key
            violations.append(f"conservation of {key[1].name} at {where}: residual {value:.3e}")
    worst_excess = 0.0
    for group_id, amount in use.items():
        ceiling = inputs.group_capacity[group_id]
        if math.isfinite(ceiling):
            worst_excess = max(worst_excess, amount - ceiling)
        within(amount, ceiling, f"capacity group {group_id}")
    if stage != "aggregate":
        for budget_id, amount in budget_use.items():
            ceiling = inputs.budget_capacity[budget_id]
            if math.isfinite(ceiling):
                worst_excess = max(worst_excess, amount - ceiling)
            within(amount, ceiling, f"budget {budget_id}")
    objective = None
    if inputs.objective_export_id is not None:
        objective = allocation.exports.get(inputs.objective_export_id)
    return Verification(not violations, tuple(violations), worst_residual, max(0.0, worst_excess), objective,
                        time.perf_counter() - started)


# --------------------------------------------------------------------------
# Stage solving
# --------------------------------------------------------------------------

def _allocation(model: LPModel, x) -> Allocation:
    flows, crafts, imports, exports, surplus = {}, {}, {}, {}, {}
    for j, key in enumerate(model.var_keys):
        value = max(0.0, float(x[j]))
        if key[0] == "flow":
            if value > 0:
                flows[(key[1], key[2])] = value
        elif key[0] == "craft":
            crafts[key[1]] = value
        elif key[0] == "import":
            imports[key[1]] = value
        elif key[0] == "export":
            exports[key[1]] = value
        elif key[0] == "surplus":
            surplus[key[1]] = value
    return Allocation(flows, crafts, imports, exports, surplus)


def _cut_text(cut: tuple[CutTerm, ...], limit: int = 12) -> str:
    ranked = sorted(cut, key=lambda t: (-abs(t.contribution), -abs(t.multiplier), str(t.label)))
    parts = [f"{describe_label(t.label)} (multiplier {t.multiplier:.6g}, contribution {t.contribution:.6g})" for t in ranked[:limit]]
    if len(ranked) > limit:
        parts.append(f"... {len(ranked) - limit} more terms")
    return "; ".join(parts) if parts else "no binding constraint (objective unconstrained at this stage)"


def solve_stage(graph: SpatialGraph, request: RoutingRequest, inputs: ModelInputs, stage: str,
                options: PlanOptions = PlanOptions()) -> StageSolution:
    tol = options.tolerance
    relax = inputs.relaxations.get(stage, STAGE_RELAXATIONS[stage])
    timings = {"build_s": 0.0, "solve_s": 0.0, "cleanup_s": 0.0, "certificate_s": 0.0, "verify_s": 0.0}
    estimate = count_model(inputs, stage)
    sizes = {"variables": estimate["variables"], "rows": 0, "nonzeros": estimate["nonzeros_upper_bound"]}
    blank = dict(stage=stage, primal=None, dual=None, sizes=sizes, timings=timings, relaxations=relax,
                 cut=(), allocation=None, verification=None, shortfall=None)
    if estimate["variables"] > options.max_variables or estimate["nonzeros_upper_bound"] > options.max_nonzeros:
        return StageSolution(state="size_limit", value=None, certificate="Model exceeds the configured size limit; no bound is claimed.",
                             notes=(f"estimated {estimate['variables']} variables / {estimate['nonzeros_upper_bound']} nonzeros",), **blank)

    started = time.perf_counter()
    model = build_lp(inputs, stage)
    timings["build_s"] = time.perf_counter() - started
    sizes.update(variables=model.n_variables, rows=model.n_rows, nonzeros=model.nonzeros)
    c = objective_vector(model, inputs.objective_export_id)
    primary = solve_lp(model, c, time_limit=options.time_limit_s)
    timings["solve_s"] = primary.seconds
    maximizing = inputs.objective_export_id is not None

    if primary.status == 2:
        return _certify_infeasible(graph, request, inputs, model, stage, blank, options)
    if primary.status == 3 and maximizing:
        feasibility = solve_lp(model, c * 0.0, time_limit=options.time_limit_s)
        timings["solve_s"] += feasibility.seconds
        if feasibility.status == 2:
            return _certify_infeasible(graph, request, inputs, model, stage, blank, options)
        if feasibility.status != 0:
            return StageSolution(state="limit", value=None, certificate="Unbounded objective reported, but no feasible point was confirmed; no bound is claimed.",
                                 notes=(feasibility.message,), **blank)
        allocation = _allocation(model, feasibility.x)
        verification = verify_allocation(graph, request, allocation, stage=stage, tolerance=tol, inputs=inputs)
        timings["verify_s"] = verification.seconds
        blank.update(allocation=allocation if verification.ok else None, verification=verification)
        return StageSolution(state="unlimited", value=math.inf,
                             certificate="Objective export is unbounded above at this stage: no finite ceiling among machine time, craft capacity, budgets, feeds, sinks or routing constrains it. Unlimited is a non-claim, not a rate.",
                             **blank)
    if primary.status != 0:
        return StageSolution(state="limit", value=None, certificate="Solver reached its work/time limit or reported numerical difficulty; no bound is claimed.",
                             notes=(primary.message,), **blank)

    # Certified upper bound from the primary duals (weak duality), independent of the status word.
    started = time.perf_counter()
    certificate = dual_bound(model, c, primary, tolerance=1e-9) if maximizing else None
    timings["certificate_s"] = time.perf_counter() - started
    primal_value = -primary.fun if maximizing else None

    # Secondary objective: remove gratuitous cycles/imports/waste with the primary optimum pinned.
    started = time.perf_counter()
    x = primary.x
    notes = []
    cleanup = solve_lp(model, cleanup_vector(model, inputs.objective_export_id), time_limit=options.time_limit_s, pin=(c, primary.fun))
    timings["cleanup_s"] = time.perf_counter() - started
    if cleanup.status == 0 and abs(float(c @ cleanup.x) - primary.fun) <= tol * max(1.0, abs(primary.fun)):
        x = cleanup.x
    else:
        notes.append("secondary cleanup did not converge; primary allocation kept (may contain gratuitous cycles)")
    allocation = _allocation(model, x)
    verification = verify_allocation(graph, request, allocation, stage=stage, tolerance=tol, inputs=inputs)
    timings["verify_s"] = verification.seconds
    blank.update(allocation=allocation if verification.ok else None, verification=verification, primal=primal_value)
    if not verification.ok:
        notes.append("independent residual check rejected the allocation: " + "; ".join(verification.violations[:5]))

    if not maximizing:
        return StageSolution(state="feasible" if verification.ok else "uncertified", value=None,
                             certificate="Feasibility only: a continuous allocation satisfying every stage constraint exists; no bound is defined for a feasibility objective.",
                             notes=tuple(notes), **blank)
    if certificate is None or not certificate.valid:
        notes.append("dual certificate unavailable or dual-infeasible beyond tolerance; the incumbent is not an upper bound")
        return StageSolution(state="uncertified", value=None, certificate="No certified dual bound; incumbent withheld.", notes=tuple(notes), **blank)
    dual_value = max(0.0, -certificate.value)
    gap = abs(dual_value - primal_value)
    blank.update(dual=dual_value, cut=certificate.cut)
    if gap > tol * max(1.0, dual_value):
        notes.append(f"primal/dual gap {gap:.3e} exceeds tolerance; reporting the certified dual value")
    text = (f"Certified upper bound {dual_value:.10g} items/s at stage {stage} by weak duality from the constraint cut: "
            f"{_cut_text(certificate.cut)}. Primal witness {primal_value:.10g} items/s, gap {gap:.2e}, tolerance {tol:g}."
            + (f" Relaxations: {', '.join(relax)}." if relax else ""))
    return StageSolution(state="optimal", value=dual_value, certificate=text, notes=tuple(notes), **blank)


def _certify_infeasible(graph, request, inputs, model, stage, blank, options) -> StageSolution:
    tol = options.tolerance
    started = time.perf_counter()
    short_model, c = shortfall_model(model, inputs.exports)
    result = solve_lp(short_model, c, time_limit=options.time_limit_s)
    blank["timings"]["certificate_s"] = time.perf_counter() - started
    requested = sum(t.rate for t in inputs.exports)
    if result.status != 0:
        return StageSolution(state="limit", value=None, certificate="Infeasible per solver, but the shortfall certificate could not be computed; no claim.",
                             notes=(result.message,), **blank)
    certificate = dual_bound(short_model, c, result, tolerance=1e-9)
    margin = tol * max(1.0, requested)
    if certificate is None or not certificate.valid or certificate.value <= margin:
        return StageSolution(state="limit", value=None, certificate="Infeasible per solver, but no dual-feasible shortfall certificate above tolerance; no claim.", **blank)
    per_export = {t.outlet_id: float(result.x[short_model.var_index[("short", t.outlet_id)]]) for t in inputs.exports}
    listing = ", ".join(f"{t.outlet_id} ({t.requirement} {t.rate:g} {t.material.name}/s)" for t in inputs.exports)
    text = (f"Infeasibility certificate at stage {stage}: every allocation satisfying the constraint cut "
            f"[{_cut_text(certificate.cut)}] leaves a total shortfall of at least {certificate.value:.10g} items/s across the "
            f"requested exports [{listing}] (weak duality on the minimum-shortfall model; tolerance {tol:g}). "
            f"Minimum-shortfall allocation is short by " + ", ".join(f"{k}: {v:.10g}" for k, v in per_export.items()) + ".")
    blank.update(cut=certificate.cut, shortfall=float(result.fun))
    return StageSolution(state="infeasible", value=None, certificate=text, **blank)


# --------------------------------------------------------------------------
# Result assembly
# --------------------------------------------------------------------------

def _finding(code, severity, kind, message, *, entity_ids=(), endpoint_ids=(), material=None,
             required=None, bound=None, evidence_ids=(), assumptions=()):
    entity_ids = tuple(sorted(set(entity_ids), key=lambda e: e.key))
    endpoint_ids = tuple(sorted(set(endpoint_ids), key=lambda e: e.key))
    evidence_ids = tuple(sorted(set(evidence_ids)))
    return dict(id=finding_id(code, entity_ids, endpoint_ids, material, evidence_ids), code=code, severity=severity,
                evidence_kind=kind, message=message, entity_ids=to_dict(entity_ids), endpoint_ids=to_dict(endpoint_ids),
                material=to_dict(material), required_rate=required, capacity_upper_bound=bound,
                evidence_ids=list(evidence_ids), assumptions=list(assumptions))


# Finding identity is `code + entity/endpoint scope + material + evidence` (contract
# §"Finding IDs"); message text and severity are deliberately outside it. Two rules keep
# the emitted findings unique without inventing identity:
#
# 1. semantically distinct facts carry distinct codes, so what the hash can see already
#    separates them (an unresolved reason class, the stage a solver limit occurred at);
# 2. whatever still shares an identity is a discriminator the contract cannot express
#    (a capacity group ID, a mod name, a budget ID). Those are merged on purpose by
#    `_merge_findings`, which keeps every message rather than dropping all but one.
_UNRESOLVED_CODES = {
    "unsupported topology": "unresolved_topology_gap",
    "unsupported entity": "unresolved_unsupported_entity",
    "ambiguous furnace": "unresolved_ambiguous_furnace",
    "unassigned furnace": "unresolved_unassigned_furnace",
    "power availability unknown": "unresolved_power",
    "mod alters item mechanics": "unresolved_mod_mechanics",
}
_STAGE_LIMIT_CODES = {stage: f"solver_limit_{stage}" for stage in STAGES}
_SEVERITY_ORDER = ("info", "warning", "error")
# F-3 (audit): a real layout can carry hundreds of unknown-capacity groups (the
# pilot has 608 bulk-inserter hand-offs and 15 splitter bodies) that would
# otherwise each mint their own `unknown_capacity_relaxed` finding and bury the
# findings that matter. `_sample_ids` caps how many raw IDs a message spells out
# (a "capped sample plus a total", per the audit's acceptance test); the finding's
# structured `entity_ids` field is never capped, so the full affected scope stays
# machine-readable regardless of the cap.
_ID_SAMPLE_CAP = 20


def _sample_ids(ids) -> str:
    ids = list(ids)
    shown = ", ".join(ids[:_ID_SAMPLE_CAP])
    if len(ids) > _ID_SAMPLE_CAP:
        shown += f", and {len(ids) - _ID_SAMPLE_CAP} more"
    return shown


def _merge_findings(findings: list[dict]) -> list[dict]:
    """Collapse findings that share a contract identity, keeping every explanation.

    Same identity means same code, scope, material and evidence, so the merged record
    keeps those references untouched; only the parts identity ignores are combined:
    messages are concatenated in generation order (deterministic; a message already
    contained in the merged text is not repeated, nothing is dropped), the
    severity becomes the strongest of the group, and a structured rate/bound survives
    only when the whole group agrees on it. A mixed evidence kind degrades to
    ``conditional`` rather than claiming an observation or an upper bound.
    """
    merged: dict[str, dict] = {}
    for finding in findings:
        kept = merged.get(finding["id"])
        if kept is None:
            merged[finding["id"]] = dict(finding)
            continue
        if finding["message"] not in kept["message"]:
            kept["message"] = f"{kept['message']} {finding['message']}"
        kept["severity"] = max(kept["severity"], finding["severity"], key=_SEVERITY_ORDER.index)
        if kept["evidence_kind"] != finding["evidence_kind"]:
            kept["evidence_kind"] = "conditional"
        for field in ("required_rate", "capacity_upper_bound"):
            if kept[field] != finding[field]:
                kept[field] = None
        kept["assumptions"] = list(dict.fromkeys(kept["assumptions"] + finding["assumptions"]))
    return sorted(merged.values(), key=lambda f: f["id"])


class _Scope:
    """Maps constraint-cut labels to graph entities, endpoints and evidence."""

    def __init__(self, graph: SpatialGraph, request: RoutingRequest, inputs: ModelInputs):
        self.endpoints = _endpoints(graph)
        self.entities = {e.id: e for e in graph.entities}
        self.groups = {g.id: g for g in graph.capacity_groups}
        self.activities = {a.id: a for a in graph.activities}
        self.arcs = {a.id: a for a in graph.arcs}
        self.group_users = defaultdict(list)
        for arc in graph.arcs:
            for use in arc.resources:
                self.group_users[use.group_id].append(arc)
        for activity in graph.activities:
            for use in activity.resources:
                self.group_users[use.group_id].append(activity)
        self.feeds = {f.id: f for f in request.assignments.feeds}
        self.outlets = {x.id: x for x in request.exports + request.surplus}
        self.graph_evidence = tuple(sorted(e.id for e in graph.evidence))

    def collect(self, cut):
        entities, endpoints, evidence = set(), set(), set()

        def endpoint(ep):
            endpoints.add(ep)
            entities.add(ep.entity)
            evidence.update(self.endpoints[ep].evidence_ids)

        for term in cut:
            label = term.label
            kind = label[0]
            if kind == "node" and label[1] != POOL:
                endpoint(label[1])
            elif kind == "group":
                evidence.update(self.groups[label[1]].evidence_ids)
                for user in self.group_users[label[1]]:
                    evidence.update(user.evidence_ids)
                    entities.add(user.entity if hasattr(user, "entity") else user.source.entity)
            elif kind == "budget":
                for feed in self.feeds.values():
                    if feed.budget_id == label[1]:
                        endpoint(feed.endpoint)
            elif kind in ("upper", "lower", "implied"):
                inner = label[1:]
                if inner[0] == "craft":
                    activity = self.activities[inner[1]]
                    entities.add(activity.entity)
                    evidence.update(activity.evidence_ids)
                elif inner[0] == "import":
                    endpoint(self.feeds[inner[1]].endpoint)
                elif inner[0] in ("export", "surplus", "short", "over"):
                    endpoint(self.outlets[inner[1]].endpoint)
            elif kind == "shortfall":
                endpoint(self.outlets[label[1]].endpoint)
        return entities, endpoints, evidence

    def evidence_for(self, cut, fallback_endpoint: EndpointId | None):
        _, _, evidence = self.collect(cut)
        if not evidence and fallback_endpoint is not None:
            evidence.update(self.endpoints[fallback_endpoint].evidence_ids)
        if not evidence:
            evidence.update(self.graph_evidence[:1])
        return tuple(sorted(evidence))


def _constraint_hash(fingerprint: str, stage: str) -> str:
    return content_hash({"comparison_hash": fingerprint, "stage": stage})


def _seal_result(value: dict, graph: SpatialGraph) -> AnalysisResult:
    value.pop("result_hash", None)
    value["result_hash"] = content_hash(value)
    return parse_result(value, graph)


def _base_result(graph: SpatialGraph, request: RoutingRequest | None, detail, status, findings, bounds, witness,
                 assumptions, limitations):
    return dict(schema_version=SCHEMA_VERSION, analyzer_version=ANALYZER_VERSION, blueprint_hash=graph.blueprint_hash,
                prototype_hash=graph.prototype_hash, graph_hash=graph.graph_hash,
                request_hash=request.request_hash if request else None,
                result_hash="sha256:" + "0" * 64,
                interpreted_request=to_dict(request) if request else None, status=status,
                findings=_merge_findings(findings), bounds=bounds, witness=witness,
                assumptions=list(assumptions), limitations=list(limitations), detail=to_dict(detail))


def _witness(allocation: Allocation, inputs: ModelInputs, tolerance: float) -> dict:
    flows = sorted(allocation.flows.items(), key=lambda kv: (kv[0][0], kv[0][1].name))
    return dict(flows=[dict(arc_id=a, material=to_dict(m), rate=r) for (a, m), r in flows],
                activities=[dict(activity_id=k, crafts_per_s=v) for k, v in sorted(allocation.crafts.items())],
                imports=[dict(id=k, rate=v) for k, v in sorted(allocation.imports.items())],
                exports=[dict(id=k, rate=v) for k, v in sorted(allocation.exports.items())],
                surplus=[dict(id=k, rate=v) for k, v in sorted(allocation.surplus.items())],
                validation="independent_residual_check", tolerance=tolerance)


def _request_assumptions(request: RoutingRequest) -> list[str]:
    a = request.assumptions
    lines = [f"power:{a.power}", f"control_policy:{a.control_policy}", f"quality:{a.quality}",
             f"modules:{a.modules}", f"beacons:{a.beacons}", f"game_version:{a.game_version}",
             "boundary: only declared feeds, exports and surplus outlets move material",
             "model: continuous steady-state relaxation with per-entity activities and shared capacity groups"]
    lines += declared_assumptions(request)
    return lines


def analyze_request_document(graph: SpatialGraph, value: dict, options: PlanOptions = PlanOptions()) -> DeliveryReport:
    """Parse a raw request document; strict failures become an ``invalid_request`` result."""
    try:
        request = parse_request(value, graph)
    except ContractError as error:
        detail_value = value.get("detail") if isinstance(value, dict) else None
        detail = _safe_detail(detail_value)
        finding = _finding("invalid_request", "error", "structural", f"Request rejected by the contract validator: {error}")
        result = _seal_result(_base_result(graph, None, detail, "invalid_request", [finding], [], None,
                                           ["request not interpreted"], list(LIMITATIONS)), graph)
        return DeliveryReport(result, {}, (), None)
    return analyze_delivery(graph, request, options)


def _safe_detail(value):
    try:
        if isinstance(value, dict) and value.get("kind") == "full":
            return DetailScope("full", (), None, int(value.get("limit", 10000)))
    except (ContractError, TypeError, ValueError):
        pass
    return DetailScope("full", (), None, 10000)


def analyze_delivery(graph: SpatialGraph, request: RoutingRequest, options: PlanOptions = PlanOptions()) -> DeliveryReport:
    unresolved = unresolved_reasons(request, graph)
    assumptions = _request_assumptions(request)
    limitations = list(LIMITATIONS)
    if graph.provenance == "synthetic":
        limitations.append("Synthetic graph: capacities and recipe coefficients are fixture definitions, not game observations.")
    findings: list[dict] = []

    if unresolved:
        gaps = {g.id: g for g in graph.topology_gaps}
        entities = {e.id.key: e for e in graph.entities}
        for reason in unresolved:
            entity_ids, evidence, kind = (), (), "conditional"
            head, _, tail = reason.partition(": ")
            # One code per reason class: an entity-scoped reason is already distinguished by
            # its entity and evidence, while `power`/`mod` reasons have no graph scope at all
            # and would otherwise all hash to the same ID. An unknown future class keeps the
            # generic code and is merged rather than colliding.
            code = _UNRESOLVED_CODES.get(head, "unresolved_model")
            if head == "unsupported topology":
                gap = gaps.get(tail.split(" ")[0])
                if gap is not None:
                    entity_ids, evidence = gap.entity_ids, gap.evidence_ids
            elif head in ("unsupported entity", "ambiguous furnace", "unassigned furnace") and tail in entities:
                entity_ids, evidence = (entities[tail].id,), entities[tail].evidence_ids
            findings.append(_finding(code, "warning", kind,
                                     f"No bound or insufficiency claim: {reason}. Resolve it (assignment, evidence, or a supported adapter) before numerical analysis.",
                                     entity_ids=entity_ids, evidence_ids=evidence))
        result = _seal_result(_base_result(graph, request, request.detail, "partial", findings, [], None, assumptions, limitations), graph)
        return DeliveryReport(result, {}, unresolved, None)

    inputs = resolve_model_inputs(graph, request)
    scope = _Scope(graph, request, inputs)
    stages = {stage: solve_stage(graph, request, inputs, stage, options) for stage in options.stages}

    # Explanatory findings that hold regardless of outcome.
    #
    # F-3: aggregate deliberately instead of one finding per unknown-capacity
    # group/activity. The aggregation key is material-independent (a `CapacityGroup.kind`
    # such as "inserter"/"splitter", or the owning entity's `prototype` for activities),
    # so it is stable and matches the contract's own vocabulary rather than an invented
    # bucket. Every group/activity in a class shares one finding whose `entity_ids`
    # lists every affected entity in full (nothing is dropped) and whose message states
    # the count, the relaxation direction, and a capped sample of the raw group/activity
    # IDs so per-group detail stays retrievable without spelling out hundreds of them.
    groups_by_kind: dict[str, list[str]] = defaultdict(list)
    for group_id in inputs.unknown_groups:
        groups_by_kind[scope.groups[group_id].kind].append(group_id)
    for kind in sorted(groups_by_kind):
        group_ids = sorted(groups_by_kind[kind])
        users = [u for gid in group_ids for u in scope.group_users[gid]]
        entity_ids = sorted({u.entity if hasattr(u, "entity") else u.source.entity for u in users}, key=lambda e: e.key)
        evidence_ids = sorted(set().union(*(set(scope.groups[gid].evidence_ids) for gid in group_ids)))
        findings.append(_finding(
            "unknown_capacity_relaxed", "warning", "conditional",
            f"{len(group_ids)} {kind} capacity group(s) across {len(entity_ids)} entities have unknown capacity; "
            f"bounds treat each as unlimited (optimistic) and none is ever used as a ceiling. "
            f"Group IDs: {_sample_ids(group_ids)}.",
            entity_ids=entity_ids, evidence_ids=evidence_ids))

    activities_by_prototype: dict[str, list[str]] = defaultdict(list)
    for activity_id in inputs.unknown_activities:
        prototype = scope.entities[scope.activities[activity_id].entity].prototype
        activities_by_prototype[prototype].append(activity_id)
    for prototype in sorted(activities_by_prototype):
        activity_ids = sorted(activities_by_prototype[prototype])
        entity_ids = sorted({scope.activities[aid].entity for aid in activity_ids}, key=lambda e: e.key)
        evidence_ids = sorted(set().union(*(set(scope.activities[aid].evidence_ids) for aid in activity_ids)))
        findings.append(_finding(
            "unknown_capacity_relaxed", "warning", "conditional",
            f"{len(activity_ids)} {prototype} activity(ies) across {len(entity_ids)} entities have unknown craft "
            f"capacity; bounds treat each as unlimited (optimistic). "
            f"Activity IDs: {_sample_ids(activity_ids)}.",
            entity_ids=entity_ids, evidence_ids=evidence_ids))
    for arc_id in inputs.disabled_arcs:
        arc = scope.arcs[arc_id]
        findings.append(_finding("control_disabled_connection", "info", "structural",
                                 f"Arc {arc_id} is disabled by the explicit control assignment ({', '.join(arc.conditions)}); it carries no flow.",
                                 entity_ids=[arc.source.entity, arc.target.entity], endpoint_ids=[arc.source, arc.target],
                                 evidence_ids=arc.evidence_ids))
    if "conditional_connections_open" in inputs.relaxations.get("routing", ()):
        conditional = [a for a in graph.arcs if a.semantics == "conditional"]
        findings.append(_finding("conditional_connections_open", "warning", "conditional",
                                 "Control policy relax_open: every conditional connection is assumed open for the upper bound; the bound applies only under that assumption.",
                                 entity_ids=[a.source.entity for a in conditional] + [a.target.entity for a in conditional],
                                 evidence_ids=[e for a in conditional for e in a.evidence_ids]))
    for activity_id in inputs.excluded_activities:
        activity = scope.activities[activity_id]
        findings.append(_finding("furnace_alternative_excluded", "info", "structural",
                                 f"Alternative activity {activity_id} ({activity.recipe}) is excluded by the furnace assignment; the assigned recipe keeps the entity's whole machine time.",
                                 entity_ids=[activity.entity], evidence_ids=activity.evidence_ids))
    fed = {f.budget_id for f in request.assignments.feeds}
    for budget in request.budgets:
        if budget.id not in fed:
            findings.append(_finding("budget_without_feed", "info", "structural",
                                     f"Budget {budget.id} ({budget.material.name}) has no declared feed endpoint, so none of it can enter the layout at any stage.",
                                     material=budget.material))

    # Status and bounds.
    fingerprint = comparison_hash(request)
    objective_id = request.objective.export_id
    routing = stages.get("routing")
    limited = any(s.state in ("limit", "size_limit", "uncertified") for s in stages.values())
    infeasible = any(s.state == "infeasible" for s in stages.values())
    if limited:
        status = "solver_limit"
        for stage, solution in stages.items():
            if solution.state in ("limit", "size_limit", "uncertified"):
                # Per-stage code: the stage is the only thing separating these findings and
                # the contract identity cannot see it (no stage field, no graph scope).
                findings.append(_finding(_STAGE_LIMIT_CODES.get(stage, "solver_limit"), "warning", "structural",
                                         f"Stage {stage}: {solution.certificate} {' '.join(solution.notes)}".strip()))
    elif infeasible and (routing is None or routing.state != "infeasible"):
        status = "solver_limit"  # a looser stage infeasible while routing is not: numerically inconsistent, claim nothing
        # Generic code: this branch and the rejected-witness one below are single findings
        # about the whole analysis, not per-stage records, and they exclude each other.
        findings.append(_finding("solver_limit", "warning", "structural",
                                 "A relaxed stage was reported infeasible while the routing stage was not; stages are nested, so no bound is claimed."))
    elif routing is not None and infeasible:
        status = "insufficient"  # a certified routing infeasibility, under either objective (contract 1.1.1)
    else:
        status = "feasible_relaxed"

    bounds = []
    witness = None
    export = next(e for e in request.exports if e.id == objective_id) if objective_id is not None else None
    # Evidence anchor when a cut names no graph object: the objective export's outlet, or under a
    # feasibility objective (no objective export) the first requested export's outlet.
    anchor = export.endpoint if export is not None else request.exports[0].endpoint
    if objective_id is not None:
        nested_value = math.inf
        for stage in STAGES:
            solution = stages.get(stage)
            if solution is None or solution.state in ("limit", "size_limit", "uncertified", "feasible"):
                continue
            if solution.state == "infeasible":
                value, state = None, "infeasible"
            else:
                certified = min(solution.value, nested_value)  # a looser stage's bound also bounds this stage
                nested_value = certified
                value = {"kind": "unlimited", "value": None} if math.isinf(certified) else {"kind": "finite", "value": certified}
                state = "certified_limit" if status == "solver_limit" else "optimal"
            bounds.append(dict(stage=stage, direction="upper", comparison_hash=fingerprint,
                               constraint_hash=_constraint_hash(fingerprint, stage), objective_export_id=objective_id,
                               unit="items/s", value=value, solver_state=state, certificate=solution.certificate,
                               evidence_ids=list(scope.evidence_for(solution.cut, anchor)),
                               assumptions=assumptions, relaxations=list(solution.relaxations)))
        if routing is not None and routing.state in ("optimal", "unlimited") and status != "solver_limit":
            entities, endpoints, evidence = scope.collect(routing.cut)
            value = None if math.isinf(nested_value) else nested_value
            if value is not None:
                findings.append(_finding("delivery_upper_bound", "info", "upper_bound",
                                         f"Net export {objective_id} of {export.material.name} is at most {value:.10g}/s under the declared feeds, budgets, "
                                         f"machine capacities and supported routing (certified; not an achievable rate). Binding cut: {_cut_text(routing.cut, 6)}.",
                                         entity_ids=entities, endpoint_ids=endpoints | {export.endpoint}, material=export.material,
                                         required=export.rate, bound=value,
                                         evidence_ids=scope.evidence_for(routing.cut, anchor), assumptions=assumptions))
                if value <= options.tolerance:
                    findings.append(_finding("zero_objective", "warning", "structural",
                                             f"The maximum net export of {objective_id} is zero: no declared feed, activity and route chain delivers {export.material.name} to its outlet.",
                                             endpoint_ids=[export.endpoint], material=export.material, required=export.rate))
        if routing is not None and routing.state == "infeasible":
            entities, endpoints, evidence = scope.collect(routing.cut)
            findings.append(_finding("delivery_insufficient", "error", "structural",
                                     f"The requested exports cannot all be met even by the optimistic relaxation. {routing.certificate}",
                                     entity_ids=entities, endpoint_ids=endpoints | {e.endpoint for e in request.exports},
                                     evidence_ids=scope.evidence_for(routing.cut, anchor), assumptions=assumptions))
    else:
        # Feasibility objective (contract 1.1.1): there is no maximand, so no stage may carry a value;
        # the only admissible scenario is the routing stage's infeasibility certificate (null ID, null value).
        if routing is not None and routing.state == "infeasible":
            entities, endpoints, evidence = scope.collect(routing.cut)
            bounds.append(dict(stage="routing", direction="upper", comparison_hash=fingerprint,
                               constraint_hash=_constraint_hash(fingerprint, "routing"), objective_export_id=None,
                               unit="items/s", value=None, solver_state="infeasible", certificate=routing.certificate,
                               evidence_ids=list(scope.evidence_for(routing.cut, anchor)),
                               assumptions=assumptions, relaxations=list(routing.relaxations)))
            findings.append(_finding("delivery_insufficient", "error", "structural",
                                     f"Feasibility objective: the requested exports cannot all be met even by the optimistic relaxation. {routing.certificate}",
                                     entity_ids=entities, endpoint_ids=endpoints | {e.endpoint for e in request.exports},
                                     evidence_ids=scope.evidence_for(routing.cut, anchor), assumptions=assumptions))
        else:
            findings.append(_finding("feasibility_only", "info", "structural",
                                     "Feasibility objective: nothing is maximized, so no bound scenario is reported; the witness is a continuous allocation only."))

    if status == "feasible_relaxed":
        if routing is None or routing.allocation is None:
            status = "solver_limit"
            findings.append(_finding("solver_limit", "warning", "structural", "Routing allocation missing or rejected by the independent residual check; no witness."))
            for bound in bounds:
                if bound["solver_state"] == "optimal":
                    bound["solver_state"] = "certified_limit"
        else:
            witness = _witness(routing.allocation, inputs, options.tolerance)
    result = _seal_result(_base_result(graph, request, request.detail, status, findings, bounds, witness, assumptions, limitations), graph)
    return DeliveryReport(result, stages, (), inputs)


def counterfactual_routing(graph: SpatialGraph, request: RoutingRequest, *, group_capacities: dict[str, float] | None = None,
                           budget_capacities: dict[str, float] | None = None, options: PlanOptions = PlanOptions()) -> StageSolution:
    """Re-solve the routing stage with explicit capacity changes.

    A tight constraint is not evidence that raising it helps; this solves the
    changed scenario so a claim can rest on the counterfactual optimum.
    """
    if unresolved_reasons(request, graph):
        raise ContractError("counterfactual requires a resolved model")
    inputs = resolve_model_inputs(graph, request)
    if group_capacities:
        inputs = inputs.with_group_capacity(group_capacities)
    if budget_capacities:
        unknown = set(budget_capacities) - set(inputs.budget_capacity)
        if unknown:
            raise KeyError(f"unknown budget override: {sorted(unknown)}")
        inputs = replace(inputs, budget_capacity={**inputs.budget_capacity, **budget_capacities})
    return solve_stage(graph, request, inputs, "routing", options)
