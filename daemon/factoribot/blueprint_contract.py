"""Frozen routing wire contract; no transport inference or production solver.

See docs/blueprint-routing-contract.md. Public parse functions validate both
strict types and graph references. Constructors validate local invariants.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
import math
import re
from types import UnionType
from typing import Literal, Union, get_args, get_origin, get_type_hints

SCHEMA_VERSION = "1.1.1"
MECHANICS_PROFILE = "base-2.0.76-normal-v1"
BASE_MOD = ("base", "2.0.76")

# Adapter-supplied classification of what an entity can do to items. It is a
# claim about the prototype, never inferred from labels. Anything that can hold,
# move, insert or transform items must use an item subsystem below.
SUBSYSTEMS = ("transport", "inserter", "production", "logistics", "power", "circuit", "rail", "fluid", "other", "unknown")
Subsystem = Literal["transport", "inserter", "production", "logistics", "power", "circuit", "rail", "fluid", "other", "unknown"]
ITEM_SUBSYSTEMS = frozenset({"transport", "inserter", "production", "logistics", "other", "unknown"})
# Named justification -> the only subsystem it can cover.
IRRELEVANCE_BASES = {
    "power_assumed_available": "power",
    "circuit_control_declared": "circuit",
    "rail_no_item_interface": "rail",
    "fluid_no_item_interface": "fluid",
}


class ContractError(ValueError):
    code = "invalid_request"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def token(value: str) -> None:
    require(re.fullmatch(r"[a-z][a-z0-9_-]*", value) is not None, f"invalid name: {value!r}")


def digest(value: str) -> None:
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None, "invalid SHA-256 ID")


def unique(values, label: str) -> None:
    values = tuple(values)
    require(len(set(values)) == len(values), f"duplicate {label}")


@lru_cache(maxsize=None)
def _hints(cls):
    return get_type_hints(cls)


def _typed(value, annotation, path: str, wire: bool):
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, UnionType):
        for option in args:
            try:
                return _typed(value, option, path, wire)
            except ContractError:
                pass
        raise ContractError(f"{path}: incompatible union value")
    if origin is Literal:
        require(any(type(value) is type(x) and value == x for x in args), f"{path}: unsupported option {value!r}")
        return value
    if origin is tuple:
        require(type(value) is (list if wire else tuple), f"{path}: expected {'array' if wire else 'tuple'}")
        return tuple(_typed(v, args[0], f"{path}[{i}]", wire) for i, v in enumerate(value))
    if annotation is float:
        require(type(value) in (int, float), f"{path}: expected finite number")
        try:
            finite = math.isfinite(value)
        except OverflowError:
            finite = False
        require(finite, f"{path}: expected finite number")
        return value
    if is_dataclass(annotation):
        if wire:
            return from_dict(annotation, value)
        require(type(value) is annotation, f"{path}: expected {annotation.__name__}")
        return value
    require(type(value) is annotation, f"{path}: expected {annotation.__name__}")
    return value


@dataclass(frozen=True)
class Record:
    def __post_init__(self):
        for name, annotation in _hints(type(self)).items():
            _typed(getattr(self, name), annotation, f"{type(self).__name__}.{name}", False)
        self._validate()

    def _validate(self):
        pass


def from_dict(cls, value: dict):
    require(type(value) is dict, f"{cls.__name__}: expected object")
    expected = {f.name for f in fields(cls)}
    require(set(value) == expected, f"{cls.__name__}: missing {sorted(expected-set(value))}, unknown {sorted(set(value)-expected)}")
    return cls(**{k: _typed(v, _hints(cls)[k], k, True) for k, v in value.items()})


def to_dict(value):
    if is_dataclass(value):
        return {f.name: to_dict(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (tuple, list)):
        return [to_dict(v) for v in value]
    if isinstance(value, dict):
        return {k: to_dict(v) for k, v in value.items()}
    return value


def canonical_json(value) -> str:
    """factoribot-json-v1; numeric spelling survives ordinary JSON round-trips."""
    value = to_dict(value)
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ContractError("JSON string is not valid Unicode") from exc
    if value is None or type(value) in (bool, str):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if type(value) in (int, float):
        require(type(value) is int or math.isfinite(value), "nonfinite JSON number")
        number = format(Decimal(str(value)), "f")
        if "." in number:
            number = number.rstrip("0").rstrip(".")
        return "0" if Decimal(number) == 0 else number
    if type(value) is list:
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    require(type(value) is dict and all(type(k) is str for k in value), "expected JSON value with string keys")
    return "{" + ",".join(canonical_json(k) + ":" + canonical_json(value[k]) for k in sorted(value)) + "}"


def content_hash(value) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def record_hash(value, field: str) -> str:
    body = to_dict(value)
    body.pop(field, None)
    return content_hash(body)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _load_json(text):
    try:
        return json.loads(text, object_pairs_hook=_pairs,
                          parse_constant=lambda x: (_ for _ in ()).throw(ContractError(f"invalid JSON constant {x}")))
    except (ValueError, TypeError) as exc:
        raise ContractError(str(exc)) from exc


@dataclass(frozen=True)
class JsonDocument(Record):
    canonical: str

    def _validate(self):
        require(canonical_json(_load_json(self.canonical)) == self.canonical, "document is not canonical JSON")

    @classmethod
    def from_value(cls, value):
        return cls(canonical_json(value))

    def value(self):
        return _load_json(self.canonical)

    @property
    def hash(self):
        return content_hash(self.value())


@dataclass(frozen=True)
class EntityId(Record):
    book_path: tuple[int, ...]
    entity_number: int

    def _validate(self):
        require(all(i >= 0 for i in self.book_path) and self.entity_number > 0, "invalid entity ID")

    @property
    def key(self):
        return "bp/" + ("/".join(map(str, self.book_path)) or "root") + f"/e/{self.entity_number}"


@dataclass(frozen=True)
class EndpointId(Record):
    entity: EntityId
    kind: Literal["port", "lane", "inventory"]
    name: str

    def _validate(self):
        token(self.name)

    @property
    def key(self):
        return self.entity.key + "/" + self.kind + "/" + self.name


@dataclass(frozen=True)
class Point(Record):
    x: float
    y: float


@dataclass(frozen=True)
class Box(Record):
    minimum: Point
    maximum: Point

    def _validate(self):
        require(self.minimum.x < self.maximum.x and self.minimum.y < self.maximum.y, "invalid footprint/area")


@dataclass(frozen=True)
class Material(Record):
    kind: Literal["item", "fluid"]
    name: str
    quality: Literal["normal"] | None

    def _validate(self):
        token(self.name)
        require((self.kind == "item") == (self.quality == "normal"), "items require normal quality; fluids require null")


@dataclass(frozen=True)
class Capacity(Record):
    kind: Literal["finite", "unknown", "unlimited"]
    value: float | None

    def _validate(self):
        require((self.kind == "finite") == (self.value is not None), "capacity value/tag mismatch")
        require(self.value is None or self.value >= 0, "negative capacity")


@dataclass(frozen=True)
class Eligibility(Record):
    kind: Literal["only", "any_item"]
    materials: tuple[Material, ...]

    def _validate(self):
        unique(self.materials, "eligible material")
        require(self.kind == "only" or not self.materials, "any_item must not specify materials")

    def allows(self, material: Material) -> bool:
        return material.kind == "item" if self.kind == "any_item" else material in self.materials


@dataclass(frozen=True)
class SourceRef(Record):
    source: Literal["blueprint", "prototype", "fixture", "observation"]
    uri: str
    pointer: str

    def _validate(self):
        require(bool(self.uri), "empty evidence URI")
        require(self.pointer == "" or self.pointer.startswith("/"), "invalid JSON pointer")
        require(re.search(r"~(?![01])", self.pointer) is None, "invalid JSON pointer escape")


@dataclass(frozen=True)
class Evidence(Record):
    id: str
    kind: Literal["structural", "upper_bound", "estimated", "conditional", "observed"]
    sources: tuple[SourceRef, ...]
    entity_ids: tuple[EntityId, ...]
    endpoint_ids: tuple[EndpointId, ...]
    arc_path: tuple[str, ...]
    description: str

    def _validate(self):
        token(self.id)
        require(bool(self.sources) and bool(self.description), "evidence requires source and description")


@dataclass(frozen=True)
class Entity(Record):
    id: EntityId
    prototype: str
    position: Point
    footprint: Box
    direction: int
    orientation: float | None
    quality: str
    support: Literal["supported", "unsupported", "conditional"]
    subsystem: Subsystem
    mod: str
    furnace_candidates: tuple[str, ...]
    raw: JsonDocument
    evidence_ids: tuple[str, ...]

    def _validate(self):
        token(self.prototype)
        require(bool(self.mod) and self.mod == self.mod.strip() and not any(c.isspace() for c in self.mod), "invalid entity mod name")
        require(self.support != "supported" or self.mod == BASE_MOD[0], "first profile supports base prototypes only")
        require(0 <= self.direction <= 15, "direction outside 0..15")
        require(self.orientation is None or 0 <= self.orientation < 1, "orientation outside [0,1)")
        require(bool(self.quality), "missing entity quality")
        require(self.support != "supported" or self.quality == "normal", "unsupported entity quality")
        require(self.support != "supported" or self.direction in (0, 4, 8, 12), "first profile supports cardinal entity directions only")
        unique(self.furnace_candidates, "furnace recipe")
        raw = self.raw.value()
        require(type(raw) is dict, "entity raw must be an object")
        require(type(raw.get("direction", 0)) is int, "raw direction must be integer")
        position = raw.get("position")
        require(type(position) is dict and all(type(position.get(k)) in (int, float) for k in ("x", "y")),
                "raw position must contain numeric x/y")
        require(raw.get("entity_number") == self.id.entity_number and raw.get("name") == self.prototype,
                "normalized identity differs from raw entity")
        require(raw.get("position") == to_dict(self.position) and raw.get("direction", 0) == self.direction,
                "normalized geometry differs from raw entity")
        require(raw.get("quality", "normal") == self.quality and raw.get("orientation") == self.orientation,
                "normalized quality/orientation differs from raw entity")


@dataclass(frozen=True)
class Port(Record):
    id: EndpointId
    position: Point
    direction: int
    role: Literal["incoming", "outgoing", "bidirectional"]
    eligibility: Eligibility
    boundary_candidate: bool
    evidence_ids: tuple[str, ...]

    def _validate(self):
        require(self.id.kind == "port" and 0 <= self.direction <= 15, "invalid port")


@dataclass(frozen=True)
class Lane(Record):
    id: EndpointId
    side: Literal["left", "right"]
    incoming: EndpointId
    outgoing: EndpointId
    polyline: tuple[Point, ...]
    eligibility: Eligibility
    evidence_ids: tuple[str, ...]

    def _validate(self):
        require(self.id.kind == "lane" and len(self.polyline) >= 2, "invalid lane")
        require(self.incoming.kind == self.outgoing.kind == "port", "lane endpoints must be ports")
        require(self.incoming != self.outgoing, "lane ends must differ")
        require(self.incoming.entity == self.outgoing.entity == self.id.entity, "lane ownership mismatch")


@dataclass(frozen=True)
class Inventory(Record):
    id: EndpointId
    position: Point
    eligibility: Eligibility
    storage_capacity: Capacity
    evidence_ids: tuple[str, ...]

    def _validate(self):
        require(self.id.kind == "inventory", "invalid inventory ID")


@dataclass(frozen=True)
class CapacityGroup(Record):
    id: str
    kind: Literal["lane", "splitter", "inserter", "machine_time", "boundary", "other"]
    unit: Literal["items/s", "fluid_units/s", "seconds/s"]
    capacity: Capacity
    evidence_ids: tuple[str, ...]

    def _validate(self):
        token(self.id)
        require(bool(self.evidence_ids), "capacity requires evidence")
        require((self.kind == "machine_time") == (self.unit == "seconds/s"), "machine resource units mismatch")


@dataclass(frozen=True)
class ResourceUse(Record):
    group_id: str
    coefficient: float

    def _validate(self):
        token(self.group_id)
        require(self.coefficient > 0, "resource coefficient must be positive")


@dataclass(frozen=True)
class Arc(Record):
    id: str
    source: EndpointId
    target: EndpointId
    eligibility: Eligibility
    semantics: Literal["exact", "conditional", "relaxed"]
    conditions: tuple[str, ...]
    resources: tuple[ResourceUse, ...]
    evidence_ids: tuple[str, ...]

    def _validate(self):
        token(self.id)
        require(self.source != self.target, "self-loop arc")
        require(self.source.entity.book_path == self.target.entity.book_path, "cross-blueprint arc")
        require(bool(self.resources) and bool(self.evidence_ids), "arc requires resources and evidence")
        require((self.semantics == "conditional") == bool(self.conditions), "conditional arc requires named conditions")
        for name in self.conditions:
            token(name)
        unique((r.group_id for r in self.resources), "arc resource")


@dataclass(frozen=True)
class ActivityMaterial(Record):
    endpoint: EndpointId
    material: Material
    amount_per_craft: float

    def _validate(self):
        require(self.amount_per_craft > 0, "activity amount must be positive")


@dataclass(frozen=True)
class Activity(Record):
    id: str
    entity: EntityId
    recipe: str
    inputs: tuple[ActivityMaterial, ...]
    outputs: tuple[ActivityMaterial, ...]
    craft_capacity: Capacity
    resources: tuple[ResourceUse, ...]
    evidence_ids: tuple[str, ...]

    def _validate(self):
        token(self.id)
        token(self.recipe)
        require(bool(self.outputs) and bool(self.resources) and bool(self.evidence_ids), "incomplete activity")
        require(all(x.endpoint.entity == self.entity for x in self.inputs + self.outputs), "activity endpoint owner mismatch")
        unique((r.group_id for r in self.resources), "activity resource")
        unique(((x.endpoint, x.material) for x in self.inputs), "activity input")
        unique(((x.endpoint, x.material) for x in self.outputs), "activity output")


@dataclass(frozen=True)
class TopologyGap(Record):
    id: str
    entity_ids: tuple[EntityId, ...]
    possible_endpoints: tuple[EndpointId, ...]
    may_connect: bool
    reason: str
    evidence_ids: tuple[str, ...]

    def _validate(self):
        token(self.id)
        require(bool(self.entity_ids) and bool(self.reason) and bool(self.evidence_ids), "incomplete unsupported topology")


def _source_entities(document):
    found = {}
    leaves = set()

    def walk(node, path):
        require(type(node) is dict, "blueprint node must be object")
        require(not ("blueprint" in node and "blueprint_book" in node), "ambiguous blueprint node")
        if "blueprint" in node:
            leaves.add(path)
            require(type(node["blueprint"]) is dict, "blueprint must be object")
            records = node["blueprint"].get("entities", [])
            require(type(records) is list, "source entities must be array")
            for raw in records:
                require(type(raw) is dict and type(raw.get("entity_number")) is int, "invalid source entity")
                ident = EntityId(path, raw["entity_number"])
                require(ident not in found, "duplicate source entity")
                found[ident] = raw
        elif "blueprint_book" in node:
            require(type(node["blueprint_book"]) is dict, "blueprint book must be object")
            entries = node["blueprint_book"].get("blueprints", [])
            require(type(entries) is list, "book entries must be array")
            indices = []
            for entry in entries:
                require(type(entry) is dict, "book entry must be object")
                index = entry.get("index")
                require(type(index) is int and index >= 0, "invalid book entry index")
                indices.append(index)
            unique(indices, "book entry index")
            for entry, index in zip(entries, indices):
                walk(entry, path + (index,))
        else:
            require("upgrade_planner" in node or "deconstruction_planner" in node, "missing blueprint root")
    walk(document, ())
    return found, leaves


def _pointer(document, pointer):
    node = document
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        try:
            if isinstance(node, list):
                require(re.fullmatch(r"0|[1-9][0-9]*", part) is not None, "invalid array pointer")
                node = node[int(part)]
            else:
                node = node[part]
        except (KeyError, IndexError, TypeError) as exc:
            raise ContractError(f"unresolved source pointer: {pointer}") from exc
    return node


@dataclass(frozen=True)
class SpatialGraph(Record):
    schema_version: Literal["1.1.1"]
    mechanics_profile: str
    provenance: Literal["synthetic", "game_export", "development_pilot"]
    blueprint: JsonDocument
    prototypes: JsonDocument
    blueprint_hash: str
    prototype_hash: str
    graph_hash: str
    selected_paths: tuple[tuple[int, ...], ...]
    entities: tuple[Entity, ...]
    ports: tuple[Port, ...]
    lanes: tuple[Lane, ...]
    inventories: tuple[Inventory, ...]
    capacity_groups: tuple[CapacityGroup, ...]
    arcs: tuple[Arc, ...]
    activities: tuple[Activity, ...]
    evidence: tuple[Evidence, ...]
    topology_gaps: tuple[TopologyGap, ...]

    def _validate(self):
        for h in (self.blueprint_hash, self.prototype_hash, self.graph_hash):
            digest(h)
        require(self.blueprint_hash == self.blueprint.hash and self.prototype_hash == self.prototypes.hash, "inconsistent source hash")
        require(self.graph_hash == record_hash(self, "graph_hash"), "inconsistent graph hash")
        require(bool(self.mechanics_profile) and bool(self.selected_paths), "missing profile/selection")
        unique(self.selected_paths, "selected path")
        source_document, prototype_document = self.blueprint.value(), self.prototypes.value()
        source, leaves = _source_entities(source_document)
        require(set(self.selected_paths) <= leaves, "unknown selected blueprint path")
        entities = {e.id: e for e in self.entities}
        unique((e.id for e in self.entities), "entity")
        selected = {i: r for i, r in source.items() if i.book_path in self.selected_paths}
        require(set(entities) == set(selected), "selected entities differ from source")
        for ident, ent in entities.items():
            require(ent.raw.value() == selected[ident], "entity raw differs from source document")
        endpoints = endpoint_index(self)
        unique((p.id for p in self.ports + self.lanes + self.inventories), "endpoint")
        require(all(p.entity in entities for p in endpoints), "endpoint owner missing")
        for lane in self.lanes:
            require(lane.incoming in endpoints and lane.outgoing in endpoints, "lane port missing")
            require(endpoints[lane.incoming].role in ("incoming", "bidirectional") and
                    endpoints[lane.outgoing].role in ("outgoing", "bidirectional"), "lane port role mismatch")
        groups = {g.id: g for g in self.capacity_groups}
        arcs = {a.id: a for a in self.arcs}
        ev = {e.id: e for e in self.evidence}
        for seq, label in ((self.capacity_groups, "group"), (self.arcs, "arc"),
                           (self.activities, "activity"), (self.evidence, "evidence"), (self.topology_gaps, "gap")):
            unique((x.id for x in seq), label)
        for obj in self.entities + self.ports + self.lanes + self.inventories + self.capacity_groups + self.arcs + self.activities + self.topology_gaps:
            require(set(obj.evidence_ids) <= ev.keys(), "missing evidence reference")
        for arc in self.arcs:
            require(arc.source in endpoints and arc.target in endpoints, "arc endpoint missing")
            require(all(r.group_id in groups for r in arc.resources), "arc resource missing")
            require(all(groups[r.group_id].unit != "seconds/s" for r in arc.resources), "arc uses machine time")
            expected_kinds = {"item" if groups[r.group_id].unit == "items/s" else "fluid" for r in arc.resources}
            require(len(expected_kinds) == 1, "arc mixes resource units")
            require(arc.eligibility.kind != "any_item" or expected_kinds == {"item"}, "item arc uses fluid resource")
            for material in arc.eligibility.materials:
                require(material.kind in expected_kinds, "arc material/resource units mismatch")
                require(endpoints[arc.source].eligibility.allows(material) and endpoints[arc.target].eligibility.allows(material),
                        "arc material/endpoint eligibility mismatch")
        machine_groups = {}
        group_owners = {}
        for activity in self.activities:
            require(activity.entity in entities and entities[activity.entity].support == "supported", "activity on unsupported/missing machine")
            require(all(r.group_id in groups and groups[r.group_id].unit == "seconds/s" for r in activity.resources), "activity needs machine time groups")
            require(len(activity.resources) == 1, "v1 activity needs exactly one physical machine time group")
            group_id = activity.resources[0].group_id
            require(machine_groups.setdefault(activity.entity, group_id) == group_id, "machine alternatives must share time group")
            require(group_owners.setdefault(group_id, activity.entity) == activity.entity, "machine time group has different owners")
            for part in activity.inputs + activity.outputs:
                require(part.endpoint in endpoints and endpoints[part.endpoint].eligibility.allows(part.material), "activity material/endpoint mismatch")
            candidates = entities[activity.entity].furnace_candidates
            require(not candidates or activity.recipe in candidates, "activity outside furnace candidates")
        for gap in self.topology_gaps:
            require(set(gap.entity_ids) <= entities.keys() and set(gap.possible_endpoints) <= endpoints.keys(), "gap scope missing")
        for entity in self.entities:
            if entity.support == "supported" and entity.furnace_candidates:
                require({a.recipe for a in self.activities if a.entity == entity.id} == set(entity.furnace_candidates),
                        "furnace candidates need complete alternative activities")
        for evidence in self.evidence:
            require(set(evidence.entity_ids) <= entities.keys() and set(evidence.endpoint_ids) <= endpoints.keys(), "evidence scope missing")
            require(set(evidence.arc_path) <= arcs.keys(), "evidence arc missing")
            for a, b in zip(evidence.arc_path, evidence.arc_path[1:]):
                require(arcs[a].target == arcs[b].source, "evidence path is not contiguous")
            for ref in evidence.sources:
                if ref.source in ("blueprint", "prototype"):
                    _pointer(source_document if ref.source == "blueprint" else prototype_document, ref.pointer)


def endpoint_index(graph):
    return {p.id: p for p in graph.ports + graph.lanes + graph.inventories}


@dataclass(frozen=True)
class Budget(Record):
    id: str
    material: Material
    capacity: Capacity

    def _validate(self):
        token(self.id)
        require(self.capacity.kind != "unknown", "budget must be declared")


@dataclass(frozen=True)
class Feed(Record):
    id: str
    budget_id: str
    endpoint: EndpointId
    capacity: Capacity

    def _validate(self):
        token(self.id)
        token(self.budget_id)
        require(self.capacity.kind != "unknown", "feed ceiling must be declared")


@dataclass(frozen=True)
class Sink(Record):
    kind: Literal["external"]
    service: str
    capacity: Capacity

    def _validate(self):
        require(bool(self.service.strip()) and self.capacity.kind != "unknown", "sink needs explicit ongoing removal and ceiling")


@dataclass(frozen=True)
class Export(Record):
    id: str
    material: Material
    endpoint: EndpointId
    requirement: Literal["exact", "minimum"]
    rate: float
    sink: Sink

    def _validate(self):
        token(self.id)
        require(self.rate >= 0, "negative export")
        require(self.sink.capacity.value is None or self.rate <= self.sink.capacity.value, "export exceeds sink ceiling")


@dataclass(frozen=True)
class Surplus(Record):
    id: str
    material: Material
    endpoint: EndpointId
    sink: Sink

    def _validate(self):
        token(self.id)


@dataclass(frozen=True)
class Objective(Record):
    kind: Literal["feasible", "maximize_export"]
    export_id: str | None

    def _validate(self):
        require((self.kind == "feasible") == (self.export_id is None), "objective target mismatch")


@dataclass(frozen=True)
class FurnaceAssignment(Record):
    entity: EntityId
    recipe: str

    def _validate(self):
        token(self.recipe)


@dataclass(frozen=True)
class ControlAssignment(Record):
    condition: str
    enabled: bool

    def _validate(self):
        token(self.condition)


@dataclass(frozen=True)
class AssignmentSet(Record):
    schema_version: Literal["1.1.1"]
    blueprint_hash: str
    graph_hash: str
    feeds: tuple[Feed, ...]
    furnaces: tuple[FurnaceAssignment, ...]
    controls: tuple[ControlAssignment, ...]

    def _validate(self):
        digest(self.blueprint_hash)
        digest(self.graph_hash)
        unique((f.id for f in self.feeds), "feed")
        unique(((f.endpoint, f.budget_id) for f in self.feeds), "feed allocation")
        unique((f.entity for f in self.furnaces), "furnace assignment")
        unique((c.condition for c in self.controls), "control assignment")


@dataclass(frozen=True)
class ModDeclaration(Record):
    """Request-level claim about an enabled mod; not prototype provenance evidence."""
    name: str
    version: str
    provides: tuple[Subsystem, ...]
    alters_item_mechanics: bool

    def _validate(self):
        require(bool(self.name) and self.name == self.name.strip() and not any(c.isspace() for c in self.name), "invalid mod name")
        require(bool(self.version) and self.version == self.version.strip(), "mod version must be given or the explicit 'unknown'")
        unique(self.provides, "mod subsystem")


ModVersion = ModDeclaration


@dataclass(frozen=True)
class IrrelevanceDeclaration(Record):
    """Declares unsupported entities of one subsystem irrelevant to item delivery."""
    id: str
    subsystem: Subsystem
    entity_ids: tuple[EntityId, ...]
    basis: Literal["power_assumed_available", "circuit_control_declared", "rail_no_item_interface", "fluid_no_item_interface"]
    justification: str

    def _validate(self):
        token(self.id)
        require(self.subsystem not in ITEM_SUBSYSTEMS,
                f"{self.subsystem} entities can carry, insert or transform items and cannot be declared irrelevant")
        require(IRRELEVANCE_BASES[self.basis] == self.subsystem, "irrelevance basis does not apply to this subsystem")
        require(bool(self.justification.strip()), "irrelevance declaration needs a justification")
        unique(self.entity_ids, "irrelevance entity")


@dataclass(frozen=True)
class Research(Record):
    name: str
    level: int

    def _validate(self):
        token(self.name)
        require(self.level >= 0, "negative research level")


@dataclass(frozen=True)
class Assumptions(Record):
    game_version: Literal["2.0.76"]
    mods: tuple[ModDeclaration, ...]
    quality: Literal["normal"]
    available_recipes: tuple[str, ...]
    research: tuple[Research, ...]
    control_policy: Literal["explicit", "relax_open"]
    power: Literal["assumed_available", "unknown"]
    modules: Literal["none"]
    beacons: Literal["none"]
    irrelevant: tuple[IrrelevanceDeclaration, ...]

    def _validate(self):
        unique((m.name for m in self.mods), "mod")
        base = [m for m in self.mods if m.name == BASE_MOD[0]]
        require(len(base) == 1 and base[0] == ModDeclaration(*BASE_MOD, (), False), "base 2.0.76 must be declared exactly once")
        unique((d.id for d in self.irrelevant), "irrelevance declaration")
        require(all(d.basis != "power_assumed_available" for d in self.irrelevant) or self.power == "assumed_available",
                "power irrelevance requires power assumed available")
        unique(self.available_recipes, "available recipe")
        unique((r.name for r in self.research), "research")
        for name in self.available_recipes:
            token(name)


@dataclass(frozen=True)
class ProtectedInterfaces(Record):
    entities: tuple[EntityId, ...]
    endpoints: tuple[EndpointId, ...]
    areas: tuple[Box, ...]
    preserve_wiring: Literal[True]
    preserve_unknown: Literal[True]
    preserve_boundaries: Literal[True]


@dataclass(frozen=True)
class DetailScope(Record):
    kind: Literal["full", "entities", "summary"]
    entity_ids: tuple[EntityId, ...]
    cursor: str | None
    limit: int

    def _validate(self):
        require(1 <= self.limit <= 10000, "detail limit outside 1..10000")
        require((self.kind == "entities") == bool(self.entity_ids), "detail entity scope mismatch")
        require(self.cursor is None or bool(self.cursor), "empty cursor")
        unique(self.entity_ids, "detail entity")


@dataclass(frozen=True)
class RoutingRequest(Record):
    schema_version: Literal["1.1.1"]
    mechanics_profile: Literal["base-2.0.76-normal-v1"]
    blueprint_hash: str
    prototype_hash: str
    graph_hash: str
    request_hash: str
    budgets: tuple[Budget, ...]
    exports: tuple[Export, ...]
    surplus: tuple[Surplus, ...]
    objective: Objective
    assignments: AssignmentSet
    protected: ProtectedInterfaces
    assumptions: Assumptions
    detail: DetailScope

    def _validate(self):
        for h in (self.blueprint_hash, self.prototype_hash, self.graph_hash, self.request_hash):
            digest(h)
        require(self.request_hash == record_hash(self, "request_hash"), "inconsistent request hash")
        require(bool(self.exports), "request needs exports")
        unique((b.id for b in self.budgets), "budget ID")
        unique((b.material for b in self.budgets), "global material budget")
        unique((x.id for x in self.exports + self.surplus), "outlet ID")
        unique(((x.material, x.endpoint) for x in self.exports + self.surplus), "outlet location")
        require(self.objective.export_id is None or self.objective.export_id in {e.id for e in self.exports}, "unknown objective export")


def validate_assignments(assignments: AssignmentSet, graph: SpatialGraph) -> None:
    require(assignments.blueprint_hash == graph.blueprint_hash and assignments.graph_hash == graph.graph_hash, "stale assignment hashes")
    endpoints, entities = endpoint_index(graph), {e.id: e for e in graph.entities}
    for feed in assignments.feeds:
        require(feed.endpoint in endpoints, "unknown feed endpoint")
        endpoint = endpoints[feed.endpoint]
        require(not isinstance(endpoint, Port) or endpoint.role != "outgoing", "feed targets outgoing port")
    for furnace in assignments.furnaces:
        require(furnace.entity in entities and furnace.recipe in entities[furnace.entity].furnace_candidates, "invalid furnace override")
        require(any(a.entity == furnace.entity and a.recipe == furnace.recipe for a in graph.activities), "override has no activity")
    conditions = {c for arc in graph.arcs for c in arc.conditions}
    require({c.condition for c in assignments.controls} <= conditions, "unknown control condition")


def validate_request(request: RoutingRequest, graph: SpatialGraph) -> None:
    require((request.blueprint_hash, request.prototype_hash, request.graph_hash, request.mechanics_profile) ==
            (graph.blueprint_hash, graph.prototype_hash, graph.graph_hash, graph.mechanics_profile), "request/graph mismatch")
    validate_assignments(request.assignments, graph)
    endpoints, entities = endpoint_index(graph), {e.id: e for e in graph.entities}
    budgets = {b.id: b for b in request.budgets}
    for feed in request.assignments.feeds:
        require(feed.budget_id in budgets, "unknown feed budget")
        require(endpoints[feed.endpoint].eligibility.allows(budgets[feed.budget_id].material), "feed item not eligible")
    for outlet in request.exports + request.surplus:
        require(outlet.endpoint in endpoints, "unknown outlet endpoint")
        endpoint = endpoints[outlet.endpoint]
        require(not isinstance(endpoint, Port) or endpoint.role != "incoming", "export targets incoming port")
        require(endpoint.eligibility.allows(outlet.material), "outlet item not eligible")
    materials = [b.material for b in request.budgets] + [e.material for e in request.exports + request.surplus]
    materials += [p.material for a in graph.activities for p in a.inputs + a.outputs]
    require(all(m.kind == "item" for m in materials), "fluid numerical options unsupported by first profile")
    require(set(request.protected.entities) <= entities.keys() and set(request.protected.endpoints) <= endpoints.keys(), "unknown protected interface")
    require(set(request.detail.entity_ids) <= entities.keys(), "unknown detail scope")
    require({a.recipe for a in graph.activities} <= set(request.assumptions.available_recipes), "activity recipe not available under assumptions")
    mods = {m.name: m for m in request.assumptions.mods}
    for entity in graph.entities:
        require(entity.mod in mods, f"undeclared mod prototype: {entity.prototype} from {entity.mod}")
        require(entity.mod == BASE_MOD[0] or entity.subsystem in mods[entity.mod].provides,
                f"entity subsystem outside declared mod scope: {entity.id.key}")
    for declaration in request.assumptions.irrelevant:
        for ident in declaration.entity_ids:
            require(ident in entities, f"unknown irrelevance entity: {ident.key}")
            require(entities[ident].subsystem == declaration.subsystem, f"irrelevance subsystem mismatch: {ident.key}")
    conditions = {c for a in graph.arcs for c in a.conditions}
    if request.assumptions.control_policy == "explicit":
        require({c.condition for c in request.assignments.controls} == conditions, "explicit control state missing")
    else:
        require(not request.assignments.controls, "relax_open cannot also pin control states")


def declared_irrelevant(request: RoutingRequest, graph: SpatialGraph) -> frozenset[EntityId]:
    """Entities covered by an accepted irrelevance declaration (subsystem-wide or listed)."""
    covered = set()
    for declaration in request.assumptions.irrelevant:
        listed = set(declaration.entity_ids)
        covered |= {e.id for e in graph.entities
                    if e.subsystem == declaration.subsystem and (not listed or e.id in listed)}
    return frozenset(covered)


def declared_assumptions(request: RoutingRequest) -> tuple[str, ...]:
    """Audit strings a result must repeat for declared non-base mods and irrelevance."""
    lines = [f"mod:{m.name}:{m.version}" for m in request.assumptions.mods if m.name != BASE_MOD[0]]
    lines += [f"irrelevant:{d.id}:{d.subsystem}:{d.basis}" for d in request.assumptions.irrelevant]
    return tuple(lines)


def unresolved_reasons(request: RoutingRequest, graph: SpatialGraph) -> tuple[str, ...]:
    """Every reason bounds must be withheld; empty means bounds may be advertised.

    An unsupported/conditional entity withholds unless it is covered by a gap
    whose disconnection is asserted (`may_connect` false) with structural or
    observed evidence, or by an accepted irrelevance declaration. A gap that may
    connect always withholds. Removing unknown links never proves disconnection.
    """
    evidence = {e.id: e for e in graph.evidence}
    reasons, gapped, proven = [], set(), set()
    for gap in graph.topology_gaps:
        gapped |= set(gap.entity_ids)
        if gap.may_connect:
            reasons.append(f"unsupported topology: {gap.id}")
        elif any(evidence[e].kind in ("structural", "observed") for e in gap.evidence_ids):
            proven |= set(gap.entity_ids)
        else:
            reasons.append(f"unsupported topology: {gap.id} (disconnection needs structural or observed evidence)")
    declared = declared_irrelevant(request, graph)
    reasons += [f"unsupported entity: {e.id.key}" for e in graph.entities
                if e.support != "supported" and e.id not in gapped and e.id not in declared]
    assigned = {f.entity for f in request.assignments.furnaces}
    reasons += [f"ambiguous furnace: {e.id.key}" for e in graph.entities if len(e.furnace_candidates) > 1 and e.id not in assigned]
    if request.assumptions.power == "unknown":
        reasons.append("power availability unknown")
    reasons += [f"mod alters item mechanics: {m.name}" for m in request.assumptions.mods if m.alters_item_mechanics]
    return tuple(reasons)


def parse_graph(value: dict) -> SpatialGraph:
    return from_dict(SpatialGraph, value)


def parse_assignments(value: dict, graph: SpatialGraph) -> AssignmentSet:
    assignments = from_dict(AssignmentSet, value)
    validate_assignments(assignments, graph)
    return assignments


def parse_request(value: dict, graph: SpatialGraph) -> RoutingRequest:
    request = from_dict(RoutingRequest, value)
    validate_request(request, graph)
    return request
