"""Feed-driven furnace recipe inference for the routing audit.

This module deliberately does not solve rates.  It propagates possible item
identities from explicit feeds and fixed recipe activities, then assigns a
recipe-less furnace only when one compatible candidate remains and every input
has a supported, exact evidence path.  Relaxed/conditional arcs and unsupported
possible bridges expand possibility but never establish uniqueness.

Inference provenance is a host artifact layered around the frozen routing
contract.  The resulting assignments remain ordinary ``FurnaceAssignment``
records so the existing analyzer can replay them unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .blueprint_contract import (
    Activity,
    AssignmentSet,
    Budget,
    Capacity,
    ContractError,
    EndpointId,
    EntityId,
    Feed,
    FurnaceAssignment,
    Material,
    SpatialGraph,
    content_hash,
    parse_assignments,
    to_dict,
    validate_assignments,
)


INFERENCE_VERSION = "factoribot-furnace-inference-1"
INFERENCE_DOCUMENT_KIND = "factoribot.routing.furnace_inference"
INFERENCE_ASSUMPTIONS = (
    "Only explicit positive-capacity feeds introduce external material.",
    "Only exact arcs and fixed/inferred recipe activities establish inference evidence.",
    "Relaxed or conditional arcs and unsupported possible bridges expand candidates but never establish uniqueness.",
    "Reachability establishes possible item identity, not rate or runtime recipe selection.",
)


class FurnaceInferenceError(ValueError):
    """A bounded or malformed inference request."""

    def __init__(self, code: str, message: str, **detail):
        super().__init__(message)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class InferenceLimits:
    """Explicit work limits for the two monotone fixed points."""

    max_iterations: int = 4096
    max_states: int = 200_000
    max_steps_per_trace: int = 4096

    def __post_init__(self):
        if min(self.max_iterations, self.max_states, self.max_steps_per_trace) <= 0:
            raise FurnaceInferenceError("bad_inference_limits", "inference limits must be positive")


@dataclass(frozen=True)
class _Trace:
    sources: tuple[str, ...]
    steps: tuple[str, ...]
    arc_path: tuple[str, ...]
    entity_path: tuple[EntityId, ...]
    uncertainty: tuple[str, ...] = ()

    @property
    def exact(self) -> bool:
        return not self.uncertainty


def _material_key(material: Material) -> tuple[str, str, str]:
    return material.kind, material.name, material.quality or ""


def _trace_key(trace: _Trace) -> tuple:
    return (
        bool(trace.uncertainty),
        len(trace.steps),
        trace.sources,
        trace.steps,
        trace.uncertainty,
        tuple(entity.key for entity in trace.entity_path),
    )


def _unique(values: Iterable) -> tuple:
    return tuple(dict.fromkeys(values))


def _combine(traces: Sequence[_Trace], step: str, entity: EntityId, limits: InferenceLimits,
             uncertainty: Iterable[str] = ()) -> _Trace:
    traces = tuple(traces)
    result = _Trace(
        sources=tuple(sorted({value for trace in traces for value in trace.sources})),
        steps=_unique(value for trace in traces for value in trace.steps) + (step,),
        arc_path=_unique(value for trace in traces for value in trace.arc_path),
        entity_path=_unique(value for trace in traces for value in trace.entity_path) + (entity,),
        uncertainty=tuple(sorted({value for trace in traces for value in trace.uncertainty} | set(uncertainty))),
    )
    if len(result.steps) > limits.max_steps_per_trace:
        raise FurnaceInferenceError(
            "inference_limit",
            "an inference evidence path exceeded max_steps_per_trace",
            limit=limits.max_steps_per_trace,
        )
    return result


def _through_arc(trace: _Trace, arc, limits: InferenceLimits, *, exact_only: bool) -> _Trace | None:
    if exact_only and arc.semantics != "exact":
        return None
    uncertainty = ()
    if arc.semantics != "exact":
        named = tuple(f"condition:{name}" for name in arc.conditions)
        uncertainty = (f"arc_semantics:{arc.semantics}:{arc.id}",) + named
    result = _Trace(
        sources=trace.sources,
        steps=trace.steps + (f"arc:{arc.id}",),
        arc_path=trace.arc_path + (arc.id,),
        entity_path=_unique(trace.entity_path + (arc.target.entity,)),
        uncertainty=tuple(sorted(set(trace.uncertainty) | set(uncertainty))),
    )
    if len(result.steps) > limits.max_steps_per_trace:
        raise FurnaceInferenceError(
            "inference_limit",
            "an inference evidence path exceeded max_steps_per_trace",
            limit=limits.max_steps_per_trace,
        )
    return result


def parse_budget_documents(documents: Sequence[Mapping]) -> tuple[Budget, ...]:
    """Parse just the existing budget records needed before request sealing."""
    budgets = []
    for value in documents:
        if not isinstance(value, Mapping) or set(value) != {"id", "material", "capacity"}:
            raise FurnaceInferenceError("bad_inference_input", "each budget must use the routing budget shape")
        material = value["material"]
        capacity = value["capacity"]
        if not isinstance(material, Mapping) or set(material) != {"kind", "name", "quality"}:
            raise FurnaceInferenceError("bad_inference_input", "budget material has the wrong shape")
        if not isinstance(capacity, Mapping) or set(capacity) != {"kind", "value"}:
            raise FurnaceInferenceError("bad_inference_input", "budget capacity has the wrong shape")
        try:
            budgets.append(Budget(
                str(value["id"]),
                Material(material["kind"], material["name"], material["quality"]),
                Capacity(capacity["kind"], capacity["value"]),
            ))
        except (ContractError, TypeError, ValueError) as exc:
            raise FurnaceInferenceError("bad_inference_input", f"invalid budget: {exc}") from exc
    if len({budget.id for budget in budgets}) != len(budgets):
        raise FurnaceInferenceError("bad_inference_input", "duplicate budget ID")
    return tuple(budgets)


def compatible_furnace_recipes(recipe_source, available_recipes: Iterable[str],
                                prototype: str = "electric-furnace") -> tuple[str, ...]:
    """Derive item-only recipes accepted by a furnace's crafting categories."""
    available_recipes = tuple(available_recipes)
    if any(not isinstance(name, str) for name in available_recipes):
        raise FurnaceInferenceError(
            "bad_inference_input", "available recipe names must be strings"
        )
    machine = recipe_source.db.machines.get(prototype)
    if machine is None:
        raise FurnaceInferenceError(
            "bad_inference_input", f"recipe data has no machine prototype {prototype!r}"
        )
    found = []
    for name in sorted(set(available_recipes)):
        recipe = recipe_source.db.recipes.get(name)
        if recipe is None or recipe.category not in machine.categories:
            continue
        stacks = tuple(recipe.ingredients) + tuple(recipe.results)
        if not recipe.ingredients or not recipe.results or any(stack.type != "item" for stack in stacks):
            continue
        if recipe_source.activity(prototype, name) is not None:
            found.append(name)
    return tuple(found)


def rebase_assignments(assignments: AssignmentSet, source_graph: SpatialGraph,
                       target_graph: SpatialGraph) -> AssignmentSet:
    """Rebind a checked assignment set after candidate expansion rebuilt the graph.

    This is allowed only for the exact source graph and the same decoded blueprint
    and prototype documents.  Endpoint/entity identities are then revalidated
    against the rebuilt graph; hashes are never patched to rescue a stale input.
    """
    validate_assignments(assignments, source_graph)
    if (source_graph.blueprint_hash, source_graph.prototype_hash) != (
        target_graph.blueprint_hash, target_graph.prototype_hash
    ):
        raise FurnaceInferenceError(
            "stale_inference",
            "candidate expansion changed the blueprint or prototype identity",
        )
    document = to_dict(assignments)
    document["blueprint_hash"] = target_graph.blueprint_hash
    document["graph_hash"] = target_graph.graph_hash
    try:
        return parse_assignments(document, target_graph)
    except ContractError as exc:
        raise FurnaceInferenceError(
            "stale_inference",
            f"declarations do not survive the rebuilt graph: {exc}",
        ) from exc


def _endpoint_resolver(graph: SpatialGraph):
    lanes = {lane.id: lane for lane in graph.lanes}

    def resolve(endpoint: EndpointId, role: str) -> EndpointId:
        lane = lanes.get(endpoint)
        return endpoint if lane is None else (lane.incoming if role == "in" else lane.outgoing)

    return resolve


def _input_traces(activity: Activity, state: Mapping[tuple[EndpointId, Material], _Trace],
                  resolve) -> tuple[_Trace, ...] | None:
    traces = []
    for part in activity.inputs:
        trace = state.get((resolve(part.endpoint, "out"), part.material))
        if trace is None:
            return None
        traces.append(trace)
    return tuple(traces) if traces else None


def _merge_state(state: dict[tuple[EndpointId, Material], _Trace], endpoint: EndpointId,
                 material: Material, trace: _Trace, limits: InferenceLimits) -> bool:
    key = endpoint, material
    previous = state.get(key)
    if previous is not None and _trace_key(previous) <= _trace_key(trace):
        return False
    state[key] = trace
    if len(state) > limits.max_states:
        raise FurnaceInferenceError(
            "inference_limit", "material-state limit exceeded", limit=limits.max_states
        )
    return previous is None or previous != trace


def _propagate(
    graph: SpatialGraph,
    assignments: AssignmentSet,
    budgets: tuple[Budget, ...],
    available_recipes: frozenset[str],
    limits: InferenceLimits,
    *,
    exact_only: bool,
    inferred: Mapping[EntityId, str] = (),
) -> tuple[dict[tuple[EndpointId, Material], _Trace], int]:
    resolve = _endpoint_resolver(graph)
    state: dict[tuple[EndpointId, Material], _Trace] = {}
    budget_by_id = {budget.id: budget for budget in budgets}
    for feed in sorted(assignments.feeds, key=lambda value: value.id):
        budget = budget_by_id.get(feed.budget_id)
        if budget is None:
            raise FurnaceInferenceError(
                "bad_inference_input", f"feed {feed.id!r} references unknown budget {feed.budget_id!r}"
            )
        if ((budget.capacity.kind == "finite" and budget.capacity.value == 0)
                or (feed.capacity.kind == "finite" and feed.capacity.value == 0)):
            continue
        trace = _Trace(
            sources=(f"feed:{feed.id}:budget:{feed.budget_id}",),
            steps=(f"feed:{feed.id}",),
            arc_path=(),
            entity_path=(feed.endpoint.entity,),
        )
        _merge_state(state, resolve(feed.endpoint, "in"), budget.material, trace, limits)

    outgoing: dict[EndpointId, list] = {}
    for arc in sorted(graph.arcs, key=lambda value: value.id):
        outgoing.setdefault(resolve(arc.source, "out"), []).append(arc)

    entities = {entity.id: entity for entity in graph.entities}
    furnace_ids = {
        entity.id for entity in graph.entities
        if entity.furnace_candidates or entity.prototype == "electric-furnace"
    }
    by_entity: dict[EntityId, list[Activity]] = {}
    fixed: list[Activity] = []
    for activity in sorted(graph.activities, key=lambda value: value.id):
        if activity.recipe not in available_recipes:
            continue
        if activity.entity in furnace_ids:
            by_entity.setdefault(activity.entity, []).append(activity)
        else:
            fixed.append(activity)
    explicit = {value.entity: value.recipe for value in assignments.furnaces}

    for iteration in range(1, limits.max_iterations + 1):
        changed = False
        for (endpoint, material), trace in sorted(
            tuple(state.items()), key=lambda item: (item[0][0].key, _material_key(item[0][1]), _trace_key(item[1]))
        ):
            for arc in outgoing.get(endpoint, ()):
                if not arc.eligibility.allows(material):
                    continue
                moved = _through_arc(trace, arc, limits, exact_only=exact_only)
                if moved is not None:
                    changed |= _merge_state(
                        state, resolve(arc.target, "in"), material, moved, limits
                    )

        if not exact_only:
            for gap in sorted(graph.topology_gaps, key=lambda value: value.id):
                if not gap.may_connect:
                    continue
                endpoints = tuple(sorted(
                    {resolve(endpoint, "in") for endpoint in gap.possible_endpoints},
                    key=lambda value: value.key,
                ))
                carried = [
                    (material, trace)
                    for (endpoint, material), trace in tuple(state.items())
                    if endpoint in endpoints
                ]
                for material, trace in sorted(carried, key=lambda value: _material_key(value[0])):
                    for endpoint in endpoints:
                        uncertain = _combine(
                            (trace,), f"topology_gap:{gap.id}", endpoint.entity, limits,
                            (f"unsupported_possible_bridge:{gap.id}",),
                        )
                        changed |= _merge_state(state, endpoint, material, uncertain, limits)

        for activity in fixed:
            traces = _input_traces(activity, state, resolve)
            if traces is None:
                continue
            made = _combine(traces, f"activity:{activity.id}", activity.entity, limits)
            for output in activity.outputs:
                changed |= _merge_state(
                    state, resolve(output.endpoint, "in"), output.material, made, limits
                )

        for entity in sorted(furnace_ids, key=lambda value: value.key):
            selected = explicit.get(entity)
            if selected is None and exact_only:
                selected = inferred.get(entity)
                if selected is None:
                    # An unassigned furnace's alternatives belong only to the
                    # possible-material closure. They must never bootstrap exact
                    # output evidence before uniqueness has been established.
                    continue
            activities = by_entity.get(entity, ())
            if selected is not None:
                activities = tuple(activity for activity in activities if activity.recipe == selected)
            for activity in activities:
                traces = _input_traces(activity, state, resolve)
                if traces is None:
                    continue
                uncertainty = () if exact_only else (f"unassigned_furnace_candidate:{entity.key}",)
                if entity in explicit:
                    uncertainty = ()
                made = _combine(
                    traces, f"activity:{activity.id}", activity.entity, limits, uncertainty
                )
                for output in activity.outputs:
                    changed |= _merge_state(
                        state, resolve(output.endpoint, "in"), output.material, made, limits
                    )
        if not changed:
            return state, iteration
    raise FurnaceInferenceError(
        "inference_limit",
        "material propagation did not converge within max_iterations",
        limit=limits.max_iterations,
    )


def _candidate_matches(activities: Sequence[Activity], state, resolve) -> dict[str, Activity]:
    return {
        activity.recipe: activity
        for activity in activities
        if _input_traces(activity, state, resolve) is not None
    }


def _trace_document(trace: _Trace | None) -> dict:
    if trace is None:
        return {"sources": [], "steps": [], "arc_path": [], "entity_path": [],
                "certainty": "absent", "uncertainty": []}
    return {
        "sources": list(trace.sources),
        "steps": list(trace.steps),
        "arc_path": list(trace.arc_path),
        "entity_path": [to_dict(entity) for entity in trace.entity_path],
        "certainty": "exact" if trace.exact else "conditional",
        "uncertainty": list(trace.uncertainty),
    }


def _activity_evidence(activity: Activity, state, resolve) -> dict:
    return {
        "recipe": activity.recipe,
        "inputs": [
            {
                "material": to_dict(part.material),
                "amount_per_craft": part.amount_per_craft,
                "endpoint": to_dict(part.endpoint),
                "evidence": _trace_document(state.get((resolve(part.endpoint, "out"), part.material))),
            }
            for part in activity.inputs
        ],
        "outputs": [
            {"material": to_dict(part.material), "amount_per_craft": part.amount_per_craft,
             "endpoint": to_dict(part.endpoint)}
            for part in activity.outputs
        ],
    }


def infer_furnace_recipes(
    graph: SpatialGraph,
    assignments: AssignmentSet,
    budgets: Sequence[Budget],
    available_recipes: Iterable[str],
    *,
    limits: InferenceLimits = InferenceLimits(),
) -> dict:
    """Return a deterministic provenance report and inferred assignments."""
    validate_assignments(assignments, graph)
    budgets = tuple(sorted(budgets, key=lambda value: value.id))
    available = frozenset(available_recipes)
    resolve = _endpoint_resolver(graph)
    furnace_ids = {
        entity.id for entity in graph.entities
        if entity.furnace_candidates or entity.prototype == "electric-furnace"
    }
    activities: dict[EntityId, tuple[Activity, ...]] = {}
    for entity in furnace_ids:
        activities[entity] = tuple(sorted(
            (activity for activity in graph.activities
             if activity.entity == entity and activity.recipe in available),
            key=lambda value: value.recipe,
        ))
    graph_candidates = {
        entity.id: tuple(recipe for recipe in entity.furnace_candidates if recipe in available)
        for entity in graph.entities if entity.id in furnace_ids
    }
    explicit = {value.entity: value.recipe for value in assignments.furnaces}

    possible_state, possible_iterations = _propagate(
        graph, assignments, budgets, available, limits, exact_only=False
    )
    possible = {
        entity: _candidate_matches(activities[entity], possible_state, resolve)
        for entity in furnace_ids
    }

    inferred_names: dict[EntityId, str] = {}
    exact_state: dict = {}
    exact_iterations = 0
    # Chained furnaces require a bounded outer fixed point because each newly
    # justified recipe may establish exact output evidence for the next one.
    for round_number in range(1, limits.max_iterations + 1):
        exact_state, inner = _propagate(
            graph, assignments, budgets, available, limits,
            exact_only=True, inferred=inferred_names,
        )
        exact_iterations += inner
        newly = {}
        for entity in sorted(furnace_ids, key=lambda value: value.key):
            if entity in explicit or len(possible[entity]) != 1:
                continue
            recipe, activity = next(iter(possible[entity].items()))
            if _input_traces(activity, exact_state, resolve) is not None:
                newly[entity] = recipe
        if newly == inferred_names:
            exact_rounds = round_number
            break
        inferred_names = newly
    else:
        raise FurnaceInferenceError(
            "inference_limit", "chained furnace inference did not converge",
            limit=limits.max_iterations,
        )

    records = []
    inferred_assignments = []
    for entity in sorted(furnace_ids, key=lambda value: value.key):
        candidates = graph_candidates.get(entity, ())
        matching = tuple(sorted(possible[entity]))
        selected = explicit.get(entity)
        status = "no_evidence"
        chosen = None
        evidence_state = possible_state
        detail = None
        if selected is not None:
            chosen = selected
            selected_activity = next(
                (activity for activity in activities[entity] if activity.recipe == selected), None
            )
            at_input = {
                material: trace for (endpoint, material), trace in possible_state.items()
                if selected_activity is not None
                and endpoint in {resolve(part.endpoint, "out") for part in selected_activity.inputs}
            }
            possible_inputs = (_input_traces(selected_activity, possible_state, resolve)
                               if selected_activity is not None else None)
            exact_inputs = (_input_traces(selected_activity, exact_state, resolve)
                            if selected_activity is not None else None)
            if exact_inputs is not None:
                status, evidence_state = "explicit", exact_state
            elif possible_inputs is not None:
                status = "explicit_conditional"
            elif at_input and all(trace.exact for trace in at_input.values()):
                status = "conflict"
                detail = "confirmed feed evidence does not contain every ingredient required by the explicit recipe"
            elif at_input:
                status = "explicit_uncertain"
            else:
                status = "explicit_no_feed_evidence"
        elif entity in inferred_names:
            chosen = inferred_names[entity]
            status, evidence_state = "inferred", exact_state
            inferred_assignments.append(FurnaceAssignment(entity, chosen))
        elif len(matching) > 1:
            status = "ambiguous"
        elif len(matching) == 1:
            status = "conditional"
        elif any(endpoint.entity == entity for endpoint, _ in possible_state):
            status = "incompatible_feed"

        evidence = []
        for activity in activities[entity]:
            if activity.recipe == chosen or activity.recipe in matching:
                evidence.append(_activity_evidence(activity, evidence_state, resolve))
        records.append({
            "entity": to_dict(entity),
            "status": status,
            "candidates": list(candidates),
            "matching_candidates": list(matching),
            "recipe": chosen,
            "detail": detail,
            "evidence": evidence,
            "assumptions": list(INFERENCE_ASSUMPTIONS),
        })

    grouped: dict[tuple, list[EntityId]] = {}
    for record in records:
        if record["status"] in ("inferred", "explicit"):
            continue
        key = (record["status"], tuple(record["matching_candidates"] or record["candidates"]))
        grouped.setdefault(key, []).append(EntityId(
            tuple(record["entity"]["book_path"]), record["entity"]["entity_number"]
        ))
    groups = []
    for number, ((status, candidates), entities) in enumerate(sorted(
        grouped.items(), key=lambda item: (item[0], tuple(entity.key for entity in item[1]))
    ), 1):
        groups.append({
            "id": f"furnace_group_{number}",
            "status": status,
            "candidates": list(candidates),
            "entities": [to_dict(entity) for entity in sorted(entities, key=lambda value: value.key)],
            "override_path": "/assignments/furnaces",
            "action": (
                "review the existing explicit assignment against the recorded feed/path evidence"
                if status.startswith("explicit") or status == "conflict"
                else "assign one recorded candidate per entity or change the explicit feed/path evidence"
            ),
        })

    input_document = {
        "inference_version": INFERENCE_VERSION,
        "blueprint_hash": graph.blueprint_hash,
        "prototype_hash": graph.prototype_hash,
        "graph_hash": graph.graph_hash,
        "feeds": [to_dict(value) for value in assignments.feeds],
        "explicit_furnaces": [to_dict(value) for value in assignments.furnaces],
        "controls": [to_dict(value) for value in assignments.controls],
        "budgets": [to_dict(value) for value in budgets],
        "available_recipes": sorted(available),
        "limits": to_dict(limits),
    }
    report = {
        "inference_version": INFERENCE_VERSION,
        "input_hash": content_hash(input_document),
        "blueprint_hash": graph.blueprint_hash,
        "prototype_hash": graph.prototype_hash,
        "graph_hash": graph.graph_hash,
        "status": "complete",
        "iterations": {
            "possible_materials": possible_iterations,
            "exact_materials_total": exact_iterations,
            "furnace_rounds": exact_rounds,
        },
        "limits": to_dict(limits),
        "state_counts": {"possible": len(possible_state), "exact": len(exact_state)},
        "available_recipes": sorted(available),
        "candidate_recipes": sorted({
            recipe for recipes in graph_candidates.values() for recipe in recipes
        }),
        "explicit_assignments": [to_dict(value) for value in assignments.furnaces],
        "inferred_assignments": [to_dict(value) for value in inferred_assignments],
        "furnaces": records,
        "ambiguity_groups": groups,
        "assumptions": list(INFERENCE_ASSUMPTIONS),
    }
    report["report_hash"] = content_hash(report)
    return report


def make_inference_artifact(
    graph: SpatialGraph,
    assignments: AssignmentSet,
    budgets: Sequence[Budget],
    available_recipes: Iterable[str],
    *,
    source_graph_hash: str,
    proposed_request: Mapping | None = None,
    limits: InferenceLimits = InferenceLimits(),
) -> dict:
    """Build the additive host artifact and its replayable assignment set."""
    report = infer_furnace_recipes(
        graph, assignments, budgets, available_recipes, limits=limits
    )
    inferred = tuple(
        FurnaceAssignment(
            EntityId(tuple(value["entity"]["book_path"]), value["entity"]["entity_number"]),
            value["recipe"],
        )
        for value in report["inferred_assignments"]
    )
    merged = tuple(sorted(
        assignments.furnaces + inferred,
        key=lambda value: (value.entity.book_path, value.entity.entity_number),
    ))
    final_assignments = AssignmentSet(
        assignments.schema_version,
        graph.blueprint_hash,
        graph.graph_hash,
        assignments.feeds,
        merged,
        assignments.controls,
    )
    validate_assignments(final_assignments, graph)
    artifact = {
        "document_kind": INFERENCE_DOCUMENT_KIND,
        "source_graph_hash": source_graph_hash,
        "final_graph_hash": graph.graph_hash,
        "assignments": to_dict(final_assignments),
        "inference": report,
    }
    if proposed_request is not None:
        artifact["proposed_request"] = dict(proposed_request)
    artifact["artifact_hash"] = content_hash(artifact)
    return artifact


def validate_inference_artifact(
    artifact: Mapping,
    graph: SpatialGraph,
    budget_documents: Sequence[Mapping],
    available_recipes: Iterable[str],
) -> AssignmentSet:
    """Recompute an inference artifact before sealing it as a normal request."""
    if artifact.get("document_kind") != INFERENCE_DOCUMENT_KIND:
        raise FurnaceInferenceError("stale_inference", "not a furnace inference artifact")
    sealed = dict(artifact)
    recorded_hash = sealed.pop("artifact_hash", None)
    if recorded_hash != content_hash(sealed):
        raise FurnaceInferenceError("stale_inference", "inference artifact hash is stale")
    inference = artifact.get("inference")
    output_document = artifact.get("assignments")
    if not isinstance(inference, Mapping) or not isinstance(output_document, Mapping):
        raise FurnaceInferenceError("stale_inference", "inference artifact is incomplete")
    if artifact.get("final_graph_hash") != graph.graph_hash:
        raise FurnaceInferenceError("stale_inference", "inference artifact targets another graph")
    try:
        output = parse_assignments(dict(output_document), graph)
    except ContractError as exc:
        raise FurnaceInferenceError("stale_inference", f"inferred assignments are invalid: {exc}") from exc
    explicit_document = dict(output_document)
    explicit_document["furnaces"] = list(inference.get("explicit_assignments") or ())
    try:
        explicit = parse_assignments(explicit_document, graph)
    except ContractError as exc:
        raise FurnaceInferenceError("stale_inference", f"explicit assignments are invalid: {exc}") from exc
    budgets = parse_budget_documents(budget_documents)
    limit_document = inference.get("limits")
    if not isinstance(limit_document, Mapping) or set(limit_document) != {
        "max_iterations", "max_states", "max_steps_per_trace"
    }:
        raise FurnaceInferenceError("stale_inference", "inference limits are missing or malformed")
    try:
        limits = InferenceLimits(**limit_document)
    except (FurnaceInferenceError, TypeError) as exc:
        raise FurnaceInferenceError("stale_inference", f"inference limits are invalid: {exc}") from exc
    recomputed = infer_furnace_recipes(
        graph, explicit, budgets, available_recipes, limits=limits
    )
    if recomputed != inference:
        raise FurnaceInferenceError(
            "stale_inference",
            "feeds, budgets, recipe availability, graph identity, or inference evidence changed; rerun routes infer",
            expected_input_hash=recomputed["input_hash"],
            recorded_input_hash=inference.get("input_hash"),
        )
    expected_furnaces = list(inference["explicit_assignments"]) + list(inference["inferred_assignments"])
    expected_furnaces.sort(key=lambda value: (
        tuple(value["entity"]["book_path"]), value["entity"]["entity_number"]
    ))
    if output_document.get("furnaces") != expected_furnaces:
        raise FurnaceInferenceError("stale_inference", "assignment list differs from recorded provenance")
    return output


__all__ = [
    "INFERENCE_DOCUMENT_KIND",
    "INFERENCE_ASSUMPTIONS",
    "INFERENCE_VERSION",
    "FurnaceInferenceError",
    "InferenceLimits",
    "compatible_furnace_recipes",
    "infer_furnace_recipes",
    "make_inference_artifact",
    "parse_budget_documents",
    "rebase_assignments",
    "validate_inference_artifact",
]
