"""Stable evidence, bound and result records for the routing contract."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .blueprint_contract import (
    Record, EntityId, EndpointId, Material, Capacity, RoutingRequest,
    SpatialGraph, DetailScope, ContractError, content_hash, record_hash,
    to_dict, from_dict, require, token, digest, unique, endpoint_index,
    validate_request, unresolved_reasons, declared_assumptions,
)


def finding_id(code: str, entity_ids: tuple[EntityId, ...],
               endpoint_ids: tuple[EndpointId, ...], material: Material | None,
               evidence_ids: tuple[str, ...]) -> str:
    return "finding:" + content_hash({
        "code": code, "entity_ids": sorted(entity_ids, key=lambda e: e.key),
        "endpoint_ids": sorted(endpoint_ids, key=lambda e: e.key),
        "material": material, "evidence_ids": sorted(evidence_ids),
    }).removeprefix("sha256:")


@dataclass(frozen=True)
class Finding(Record):
    id: str
    code: str
    severity: Literal["info", "warning", "error"]
    evidence_kind: Literal["structural", "upper_bound", "estimated", "conditional", "observed"]
    message: str
    entity_ids: tuple[EntityId, ...]
    endpoint_ids: tuple[EndpointId, ...]
    material: Material | None
    required_rate: float | None
    capacity_upper_bound: float | None
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]

    def _validate(self):
        token(self.code)
        require(bool(self.message), "finding message missing")
        unique(self.entity_ids, "finding entity")
        unique(self.endpoint_ids, "finding endpoint")
        unique(self.evidence_ids, "finding evidence")
        require(self.id == finding_id(self.code, self.entity_ids, self.endpoint_ids, self.material, self.evidence_ids), "inconsistent finding ID")
        require(all(x is None or x >= 0 for x in (self.required_rate, self.capacity_upper_bound)), "negative finding rate")
        require(self.capacity_upper_bound is None or self.evidence_kind == "upper_bound", "bound finding needs upper-bound evidence")
        require(self.material is not None or (self.required_rate is None and self.capacity_upper_bound is None), "finding rate needs material units")


def comparison_hash(request: RoutingRequest) -> str:
    body = to_dict(request)
    body.pop("detail")
    body.pop("request_hash")
    return content_hash(body)


def constraint_hash(comparison: str, stage: str) -> str:
    return content_hash({"comparison_hash": comparison, "stage": stage})


@dataclass(frozen=True)
class BoundScenario(Record):
    stage: Literal["aggregate", "budget", "routing"]
    direction: Literal["upper"]
    comparison_hash: str
    constraint_hash: str
    objective_export_id: str | None
    unit: Literal["items/s", "fluid_units/s"]
    value: Capacity | None
    solver_state: Literal["optimal", "certified_limit", "infeasible"]
    certificate: str
    evidence_ids: tuple[str, ...]
    assumptions: tuple[str, ...]
    relaxations: tuple[str, ...]

    def _validate(self):
        digest(self.comparison_hash)
        digest(self.constraint_hash)
        require(self.constraint_hash == constraint_hash(self.comparison_hash, self.stage), "inconsistent constraint hash")
        if self.objective_export_id is None:
            # 1.1.1: a null ID belongs to a `feasible` objective, which maximizes nothing.
            # The only sound scenario is then a certified infeasibility of the whole
            # request; `value` stays null and `certificate` describes the constraint cut.
            require(self.solver_state == "infeasible",
                    "a feasibility-objective scenario can only certify infeasibility, never a bound value")
        else:
            token(self.objective_export_id)
        require((self.solver_state == "infeasible") == (self.value is None), "infeasible bound must have null value")
        require(self.value is None or self.value.kind != "unknown", "unknown is not an advertised bound")
        require(bool(self.certificate.strip()) and bool(self.evidence_ids), "bound requires certificate and evidence")


@dataclass(frozen=True)
class ArcFlow(Record):
    arc_id: str
    material: Material
    rate: float

    def _validate(self):
        token(self.arc_id)
        require(self.rate >= 0, "negative flow")


@dataclass(frozen=True)
class ActivityRate(Record):
    activity_id: str
    crafts_per_s: float

    def _validate(self):
        token(self.activity_id)
        require(self.crafts_per_s >= 0, "negative crafts")


@dataclass(frozen=True)
class BoundaryRate(Record):
    id: str
    rate: float

    def _validate(self):
        token(self.id)
        require(self.rate >= 0, "negative boundary flow")


@dataclass(frozen=True)
class FlowWitness(Record):
    flows: tuple[ArcFlow, ...]
    activities: tuple[ActivityRate, ...]
    imports: tuple[BoundaryRate, ...]
    exports: tuple[BoundaryRate, ...]
    surplus: tuple[BoundaryRate, ...]
    validation: Literal["synthetic_hand_checked", "independent_residual_check"]
    tolerance: float

    def _validate(self):
        require(0 < self.tolerance <= 1e-6, "invalid residual tolerance")
        unique(((f.arc_id, f.material) for f in self.flows), "witness flow")
        unique((a.activity_id for a in self.activities), "witness activity")
        for seq in (self.imports, self.exports, self.surplus):
            unique((x.id for x in seq), "witness boundary")


@dataclass(frozen=True)
class AnalysisResult(Record):
    schema_version: Literal["1.1.1"]
    analyzer_version: str
    blueprint_hash: str
    prototype_hash: str
    graph_hash: str
    request_hash: str | None
    result_hash: str
    interpreted_request: RoutingRequest | None
    status: Literal["partial", "insufficient", "feasible_relaxed", "solver_limit", "invalid_request"]
    findings: tuple[Finding, ...]
    bounds: tuple[BoundScenario, ...]
    witness: FlowWitness | None
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    detail: DetailScope

    def _validate(self):
        require(bool(self.analyzer_version), "analyzer version missing")
        for h in (self.blueprint_hash, self.prototype_hash, self.graph_hash, self.result_hash):
            digest(h)
        require(self.result_hash == record_hash(self, "result_hash"), "inconsistent result hash")
        require((self.status == "invalid_request") == (self.interpreted_request is None), "invalid interpreted request/status combination")
        require(self.request_hash == (self.interpreted_request.request_hash if self.interpreted_request else None), "inconsistent result request hash")
        ids = tuple(f.id for f in self.findings)
        unique(ids, "finding ID")
        require(ids == tuple(sorted(ids)), "findings must be sorted by stable ID")
        unique((b.stage for b in self.bounds), "bound stage")
        if self.status in ("partial", "invalid_request"):
            require(not self.bounds and self.witness is None, "partial/invalid result cannot advertise bounds or witness")
            require(not any(f.evidence_kind == "upper_bound" for f in self.findings), "partial/invalid result cannot advertise upper-bound findings")
        if self.status == "invalid_request":
            require(any(f.severity == "error" for f in self.findings), "invalid request needs error finding")
        if self.status == "insufficient":
            require(any(b.stage == "routing" and b.solver_state == "infeasible" for b in self.bounds), "insufficiency requires routing infeasibility certificate")
            require(self.witness is None, "infeasible result cannot carry witness")
        if self.status == "feasible_relaxed":
            require(self.witness is not None, "feasible relaxation requires witness")
            require(not any(b.solver_state == "infeasible" for b in self.bounds), "feasible result has infeasible scenario")
        if self.status == "solver_limit":
            require(all(b.solver_state == "certified_limit" for b in self.bounds), "solver limit needs certified upper bounds")


def validate_result(result: AnalysisResult, graph: SpatialGraph) -> None:
    require((result.blueprint_hash, result.prototype_hash, result.graph_hash) ==
            (graph.blueprint_hash, graph.prototype_hash, graph.graph_hash), "result/graph hashes mismatch")
    entities, endpoints = {e.id for e in graph.entities}, endpoint_index(graph)
    evidence = {e.id: e for e in graph.evidence}
    require(set(result.detail.entity_ids) <= entities, "unknown result detail scope")
    for finding in result.findings:
        require(set(finding.entity_ids) <= entities and set(finding.endpoint_ids) <= endpoints.keys(), "unknown finding scope")
        require(set(finding.evidence_ids) <= evidence.keys(), "unknown finding evidence")
        require(finding.evidence_kind != "observed" or any(evidence[e].kind == "observed" for e in finding.evidence_ids), "observed finding lacks observation")
    request = result.interpreted_request
    if request is None:
        return
    validate_request(request, graph)
    require(set(declared_assumptions(request)) <= set(result.assumptions),
            "declared mods and irrelevance declarations must be recorded in result assumptions")
    unresolved = unresolved_reasons(request, graph)
    if unresolved:
        require(result.status in ("partial", "solver_limit") and not result.bounds and result.witness is None,
                "unresolved model cannot support global feasibility/bounds")
        require(not any(f.capacity_upper_bound is not None or f.evidence_kind == "upper_bound" for f in result.findings),
                "unresolved model cannot support upper-bound findings")
    fingerprint = comparison_hash(request)
    values = {}
    for bound in result.bounds:
        require(bound.comparison_hash == fingerprint, "incomparable scenario request")
        require(bound.objective_export_id == request.objective.export_id, "bound objective differs from request")
        require(set(bound.evidence_ids) <= evidence.keys(), "unknown bound evidence")
        require(bound.unit == "items/s", "unsupported bound unit")
        unknown_capacity = any(a.craft_capacity.kind == "unknown" for a in graph.activities)
        unknown_capacity |= any(g.capacity.kind == "unknown" and (bound.stage == "routing" or g.kind == "machine_time")
                                for g in graph.capacity_groups)
        if unknown_capacity:
            require("unknown_capacity_unlimited" in bound.relaxations, "unknown capacities must be relaxed for upper bounds")
        if bound.stage == "routing":
            if request.assumptions.control_policy == "relax_open" and any(a.conditions for a in graph.arcs):
                require("conditional_connections_open" in bound.relaxations, "conditional connections omitted from upper bound")
            if any(a.semantics == "relaxed" for a in graph.arcs):
                require("transport_semantics_relaxed" in bound.relaxations, "relaxed transport not disclosed")
        if bound.value is not None and bound.solver_state == "optimal":
            values[bound.stage] = bound.value.value if bound.value.kind == "finite" else float("inf")
    for left, right in (("aggregate", "budget"), ("budget", "routing"), ("aggregate", "routing")):
        if left in values and right in values:
            require(values[left] + 1e-8 >= values[right], "bounds are not nested")
    if result.witness is not None:
        witness = result.witness
        require(witness.validation != "synthetic_hand_checked" or graph.provenance == "synthetic", "synthetic witness on real layout")
        arcs = {a.id: a for a in graph.arcs}
        activities = {a.id: a for a in graph.activities}
        assigned = {f.entity: f.recipe for f in request.assignments.furnaces}
        for flow in witness.flows:
            require(flow.arc_id in arcs and arcs[flow.arc_id].eligibility.allows(flow.material), "witness arc/item missing or ineligible")
        for rate in witness.activities:
            require(rate.activity_id in activities, "witness activity missing")
            activity = activities[rate.activity_id]
            require(activity.entity not in assigned or assigned[activity.entity] == activity.recipe or rate.crafts_per_s == 0, "witness violates furnace override")
        for seq, allowed in ((witness.imports, request.assignments.feeds), (witness.exports, request.exports), (witness.surplus, request.surplus)):
            require({x.id for x in seq} <= {x.id for x in allowed}, "unknown witness boundary")
        require({e.id for e in witness.exports} == {e.id for e in request.exports}, "witness must enumerate every export")


def parse_result(value: dict, graph: SpatialGraph) -> AnalysisResult:
    result = from_dict(AnalysisResult, value)
    validate_result(result, graph)
    return result
