"""Build a contract `SpatialGraph` of supported transport (routing task 04).

`build_transport_graph(view)` turns task 03's `SpatialView` into the routing
contract's graph -- entities, ports, lanes, inventories, capacity groups, arcs,
activities, evidence and topology gaps -- plus structural findings. The result
parses with `blueprint_contract.parse_graph` and is consumed unchanged by
`blueprint_plan.resolve_model_inputs` / `analyze_delivery`. No optimizer lives
here: task 05 owns the LP.

## Capacity accounting

One physical resource is one `CapacityGroup`, charged **once** per traversal at
its canonical crossing.

* Every belt, underground entrance and underground exit owns two lane groups
  (left, right). Its own internal arc `in_<side> -> out_<side>` is the canonical
  crossing of that lane and is the only arc that charges it. A chain of belts
  therefore bounds throughput by the *slowest* lane in the chain, not by their
  sum, and no lane is charged twice for one traversal.
* A surface handover or a tunnel is a boundary between two lanes that are each
  already charged, so it consumes no additional physical resource. It carries
  the single graph-wide `handover` group, which is explicitly `unlimited` with
  evidence, because the contract requires every arc to name a resource and
  forbids hiding a ceiling.
* A splitter charges three resources per traversal: the input lane it crosses,
  the output lane it leaves on, and the splitter body. All sixteen internal
  paths share those groups, so two paths through one output lane cannot each
  claim the full lane ceiling.
* An inserter charges its single `hand` group on the pickup leg only. Both
  rotation-sense alternatives share that one group.

## Evidence and semantics

Task 02 has recorded no `observed` mechanics rule, so no arc here claims
`exact`; `transport.semantics_for` derives that from the record rather than from
this module's opinion. Where a rule leaves two readings live -- the inserter
rotation sense, the underground `max_distance` reading, the side-load lane --
both are emitted as `conditional` arcs under the engine-wide condition names in
`transport.CONDITIONS`. `relax_open` opens them all (sound for an upper bound);
`explicit` must state each. Filters and splitter priorities are relaxed, never
applied, and reported as findings: no mechanics record covers them, and a
restriction taken from an unobserved rule could manufacture a false shortfall.

An unsupported entity that could carry items stays visible as a `TopologyGap`
with `may_connect: true`, which withholds every bound. A gap is only ever
`may_connect: false` when the entity's real prototype geometry shows no
candidate endpoint at all; an assumed unit footprint can under-cover, so it
never proves a disconnection.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
import json
from pathlib import Path
import time
from typing import Iterable, Mapping, Sequence

from .blueprint_contract import (
    ITEM_SUBSYSTEMS, MECHANICS_PROFILE, SCHEMA_VERSION, Activity, ActivityMaterial,
    Arc, Capacity, CapacityGroup, Eligibility, EndpointId, EntityId, Evidence,
    Inventory, JsonDocument, Lane, Material, Point, Port, ResourceUse, SourceRef,
    SpatialGraph, TopologyGap, content_hash, parse_graph, to_dict,
)
from .findings import Finding, finding_id
from .spatial import SpatialEntity, SpatialIndex, SpatialView
from .transport_prototypes import PROTOTYPE_FIXTURE_DIR
from . import transport as tr


class RoutingError(ValueError):
    def __init__(self, code: str, message: str, **detail):
        super().__init__(message)
        self.code = code
        self.detail = detail


EXTRACT_PATH = Path(PROTOTYPE_FIXTURE_DIR) / "prototypes.json"
HANDOVER_GROUP = "handover"
ANY_ITEM = Eligibility("any_item", ())


# ---------------------------------------------------------------------------
# Recipes (shared calculation layer; no recipe arithmetic is invented here)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MachineActivity:
    """One craft option: what it consumes and produces, and how fast."""

    recipe: str
    inputs: tuple[tuple[str, float], ...]
    outputs: tuple[tuple[str, float], ...]
    crafts_per_second: float
    fluids: tuple[str, ...]


class RecipeSource:
    """Adapter over the existing recipe/machine database.

    Amounts per craft, `energy_required` and crafting speed come from the shared
    calculation layer (`gamedata`/`model`), which task 01 owns. This class only
    reshapes them; it computes no new recipe arithmetic.
    """

    def __init__(self, database=None):
        if database is None:
            from .gamedata import load_database

            database = load_database()
        self.db = database

    def speed(self, prototype: str) -> float | None:
        machine = self.db.machines.get(prototype)
        return None if machine is None else machine.speed

    def activity(self, prototype: str, recipe_name: str) -> MachineActivity | None:
        recipe = self.db.recipes.get(recipe_name)
        speed = self.speed(prototype)
        if recipe is None or speed is None or not recipe.energy:
            return None
        fluids = tuple(sorted({s.name for s in recipe.ingredients + recipe.results if s.type == "fluid"}))
        return MachineActivity(
            recipe=recipe_name,
            inputs=tuple((s.name, float(s.amount)) for s in recipe.ingredients if s.type != "fluid"),
            outputs=tuple((s.name, float(s.amount)) for s in recipe.results if s.type != "fluid"),
            crafts_per_second=speed / recipe.energy,
            fluids=fluids,
        )


# ---------------------------------------------------------------------------
# Options and result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RoutingOptions:
    """How to build the graph. Nothing here infers a feed, export or recipe."""

    book_path: tuple[int, ...] = ()
    provenance: str = "game_export"
    #: Recipe candidates for every furnace, which the caller must also declare in
    #: `assumptions.available_recipes`. Empty leaves furnaces without activities
    #: and reports each one; recipe inference is task 10, not this task.
    furnace_candidates: tuple[str, ...] = ()
    recipes: RecipeSource | None = None
    profile: tr.Profile | None = None


@dataclass(frozen=True)
class TransportGraph:
    """The built graph plus everything a caller needs to judge how far to trust it."""

    graph: SpatialGraph
    findings: tuple[Finding, ...]
    unobserved_mechanics: tuple[str, ...]
    unsupported: tuple[EntityId, ...]
    stats: Mapping[str, object]

    def counts(self) -> dict[str, int]:
        g = self.graph
        return {
            "entities": len(g.entities), "ports": len(g.ports), "lanes": len(g.lanes),
            "inventories": len(g.inventories), "capacity_groups": len(g.capacity_groups),
            "arcs": len(g.arcs), "activities": len(g.activities),
            "evidence": len(g.evidence), "topology_gaps": len(g.topology_gaps),
            "findings": len(self.findings),
        }


# ---------------------------------------------------------------------------
# Identifier helpers
# ---------------------------------------------------------------------------

def entity_token(ident: EntityId) -> str:
    """A graph-local name token for an entity, stable and reversible by eye."""
    prefix = "e" if not ident.book_path else "p" + "_".join(str(i) for i in ident.book_path) + "_e"
    return f"{prefix}{ident.entity_number}"


def _port(ident: EntityId, name: str) -> EndpointId:
    return EndpointId(ident, "port", name)


def _lane(ident: EntityId, name: str) -> EndpointId:
    return EndpointId(ident, "lane", name)


def _inventory(ident: EntityId, name: str) -> EndpointId:
    return EndpointId(ident, "inventory", name)


def _condition_token(ident: EntityId) -> str:
    return "circuit_" + entity_token(ident)


# ---------------------------------------------------------------------------
# Evidence catalogue
# ---------------------------------------------------------------------------

MECHANICS_EVIDENCE = {
    "belt.straight.lane_capacity": ("mech_belt_lane_capacity", True),
    "belt.transfer.belt_to_belt": ("mech_belt_transfer", False),
    "belt.turn.lane_behavior": ("mech_belt_turn", False),
    "belt.side_load.lane_assignment": ("mech_belt_side_load", False),
    "underground.pairing.range": ("mech_underground_range", False),
    "underground.pairing.conflict": ("mech_underground_conflict", False),
    "underground.lane_mapping": ("mech_underground_lane_mapping", False),
    "splitter.lane_split": ("mech_splitter_lane_split", False),
    "splitter.priority_and_filter": ("mech_splitter_priority", False),
    "inserter.endpoints.pickup_drop_tiles": ("mech_inserter_endpoints", False),
    "inserter.rate.cycle_and_stack": ("mech_inserter_rate", False),
    "circuit.control_state": ("mech_circuit_control", False),
    "machine.activity.assembling_machine_2": ("mech_machine_am2", False),
    "machine.activity.electric_furnace": ("mech_machine_furnace", False),
    "unsupported.entity_visibility": ("mech_unsupported_visibility", False),
}
GEOMETRY_EVIDENCE = "blueprint_geometry"
PROTOTYPE_EVIDENCE = "prototype_geometry"


def _blueprint_pointer(document: Mapping, book_path: Sequence[int]) -> str:
    """RFC 6901 pointer to a leaf's entity array, by array offset, not book index."""
    node, parts = document, []
    for wanted in book_path:
        book = node.get("blueprint_book")
        if not isinstance(book, dict):
            raise RoutingError("unknown_selection_path", f"no book at {list(book_path)}")
        entries = book.get("blueprints") or []
        for offset, entry in enumerate(entries):
            if entry.get("index") == wanted:
                parts += ["blueprint_book", "blueprints", str(offset)]
                node = entry
                break
        else:
            raise RoutingError("unknown_selection_path", f"no book entry {wanted}")
    if "blueprint" not in node:
        raise RoutingError("unknown_selection_path", f"{list(book_path)} is not a blueprint leaf")
    return "/" + "/".join(parts + ["blueprint", "entities"])


def _prototype_pointer(document: Mapping, prototype: str) -> str:
    for offset, record in enumerate(document.get("prototypes") or []):
        if record.get("name") == prototype:
            return f"/prototypes/{offset}"
    return "/prototypes"


# ---------------------------------------------------------------------------
# The builder
# ---------------------------------------------------------------------------

class _Builder:
    def __init__(self, view: SpatialView, options: RoutingOptions):
        self.view = view
        self.options = options
        self.profile = options.profile or tr.Profile()
        self.extract = self.profile.extract
        self.index: SpatialIndex = view.index(options.book_path)
        self.book_path = tuple(options.book_path)
        self.roles = tr.entity_roles(self.index, self.extract)
        self.document = dict(view.document)
        self.prototypes = json.loads(EXTRACT_PATH.read_text())
        self.ports: dict[EndpointId, Port] = {}
        self.lanes: list[Lane] = []
        self.inventories: list[Inventory] = []
        self.groups: dict[str, CapacityGroup] = {}
        self.arcs: list[Arc] = []
        self.activities: list[Activity] = []
        self.gaps: list[TopologyGap] = []
        self.evidence: dict[str, Evidence] = {}
        self.findings: list[Finding] = []
        self.entity_evidence: dict[EntityId, list[str]] = defaultdict(list)
        self.furnace_candidates: dict[EntityId, tuple[str, ...]] = {}
        self.extra_conditions: dict[EntityId, tuple[str, ...]] = {}
        self.reaches: tuple[tr.InserterReach, ...] = ()
        self._lane_index: dict[EndpointId, Lane] = {}
        #: Lane ends closed by a surface handover or a tunnel. An inserter
        #: dropping onto a belt uses the lane alias, which resolves to that
        #: belt's entrance port, but it does not close the belt's rear tile:
        #: only a handover does, so only handovers are recorded here.
        self.connected: set[EndpointId] = set()
        self.notes: list[str] = []

    # -- evidence ---------------------------------------------------------
    def _build_evidence(self) -> None:
        pointer = _blueprint_pointer(self.document, self.book_path)
        uri = "blueprint:" + self.view.blueprint_hash()
        self.evidence[GEOMETRY_EVIDENCE] = Evidence(
            id=GEOMETRY_EVIDENCE, kind="structural",
            sources=(SourceRef("blueprint", uri, pointer),),
            entity_ids=(), endpoint_ids=(), arc_path=(),
            description=(
                "Entity positions, directions and footprints read losslessly from the "
                "selected blueprint leaf. Geometry only: adjacency is not a claim about "
                "engine behaviour."
            ),
        )
        self.evidence[PROTOTYPE_EVIDENCE] = Evidence(
            id=PROTOTYPE_EVIDENCE, kind="structural",
            sources=(SourceRef("prototype", "prototype-extract:" + content_hash(self.prototypes), "/prototypes"),),
            entity_ids=(), endpoint_ids=(), arc_path=(),
            description=(
                "Task 02's pinned prototype extract: tile dimensions, belt speed, "
                "max_distance and inserter offsets, verbatim with their evidence status."
            ),
        )
        for rule_id in tr.MECHANICS_RULES:
            name, bound = MECHANICS_EVIDENCE[rule_id]
            rule = self.profile.rules[rule_id]
            sources = [SourceRef(
                "observation",
                # NOTE: this string is embedded in Evidence and feeds graph_hash
                # (see SpatialGraph content hashing); it is kept exactly as task 04
                # wrote it so moving the evidence directory to
                # daemon/factoribot/evidence/routing_mechanics_observations/ (see
                # docs/blueprint-routing-handoffs/02b-evidence-packaging.md) does not
                # change any graph_hash. It is a citation label, not a resolved path.
                f"routing_mechanics_observations/records/{rule_id}.json",
                "",
            )]
            self.evidence[name] = Evidence(
                id=name, kind=tr.evidence_kind_for(rule.status, bound=bound),
                sources=tuple(sources), entity_ids=(), endpoint_ids=(), arc_path=(),
                description=(
                    f"{rule_id} [{rule.status}]: {rule.expected_behavior}"
                    + ("" if rule.blocking_gate is None else f" Blocking gate: {rule.blocking_gate}")
                ),
            )

    def _mech(self, *rule_ids: str) -> tuple[str, ...]:
        return tuple(MECHANICS_EVIDENCE[r][0] for r in rule_ids)

    # -- groups -----------------------------------------------------------
    def _group(self, gid: str, kind: str, capacity: Capacity, evidence: Sequence[str]) -> str:
        existing = self.groups.get(gid)
        if existing is None:
            unit = "seconds/s" if kind == "machine_time" else "items/s"
            self.groups[gid] = CapacityGroup(gid, kind, unit, capacity, tuple(evidence))
        return gid

    def _lane_group(self, entity: SpatialEntity, name: str) -> str:
        cap = tr.lane_capacity(entity.prototype, self.extract)
        return self._group(
            f"{entity_token(entity.id)}_{name}", "lane",
            Capacity("finite", cap.items_per_second),
            self._mech("belt.straight.lane_capacity") + (PROTOTYPE_EVIDENCE,),
        )

    # -- endpoints --------------------------------------------------------
    def _add_port(self, ident: EntityId, name: str, position: Point, direction: int, role: str) -> EndpointId:
        endpoint = _port(ident, name)
        self.ports[endpoint] = Port(endpoint, position, direction, role, ANY_ITEM, False, (GEOMETRY_EVIDENCE,))
        return endpoint

    def _belt_endpoints(self, entity: SpatialEntity) -> None:
        fx, fy = tr.forward(entity.direction)
        for side in tr.LANE_SIDES:
            ox, oy = tr.lane_offset(side, entity.direction)
            back = Point(entity.position.x - fx / 2 + ox, entity.position.y - fy / 2 + oy)
            front = Point(entity.position.x + fx / 2 + ox, entity.position.y + fy / 2 + oy)
            incoming = self._add_port(entity.id, f"in_{side}", back, entity.direction, "incoming")
            outgoing = self._add_port(entity.id, f"out_{side}", front, entity.direction, "outgoing")
            self.lanes.append(Lane(
                _lane(entity.id, side), side, incoming, outgoing, (back, front), ANY_ITEM,
                (GEOMETRY_EVIDENCE,) + self._mech("belt.straight.lane_capacity"),
            ))
            self._arc(
                f"{entity_token(entity.id)}_lane_{side}", incoming, outgoing,
                [ResourceUse(self._lane_group(entity, side), 1.0)],
                rule="belt.straight.lane_capacity", entity=entity.id,
                extra_evidence=(GEOMETRY_EVIDENCE,),
            )

    def _splitter_endpoints(self, entity: SpatialEntity) -> None:
        fx, fy = tr.forward(entity.direction)
        token = entity_token(entity.id)
        shared = self._group(
            f"{token}_split", "splitter", Capacity("unknown", None),
            self._mech("splitter.lane_split", "splitter.priority_and_filter"),
        )
        halves = tr.half_tiles(entity, tr.SPLITTER)
        ins: dict[tuple[str, str], EndpointId] = {}
        outs: dict[tuple[str, str], EndpointId] = {}
        for half, tile in halves:
            cx, cy = tile[0] + 0.5, tile[1] + 0.5
            for side in tr.LANE_SIDES:
                ox, oy = tr.lane_offset(side, entity.direction)
                back = Point(cx - fx / 2 + ox, cy - fy / 2 + oy)
                front = Point(cx + fx / 2 + ox, cy + fy / 2 + oy)
                ins[(half, side)] = self._add_port(entity.id, f"in_{half}_{side}", back, entity.direction, "incoming")
                outs[(half, side)] = self._add_port(entity.id, f"out_{half}_{side}", front, entity.direction, "outgoing")
                self._lane_group(entity, f"in_{half}_{side}")
                self._lane_group(entity, f"out_{half}_{side}")
        for (in_half, in_side), source in ins.items():
            for (out_half, out_side), target in outs.items():
                self._arc(
                    f"{token}_split_{in_half}_{in_side}_to_{out_half}_{out_side}", source, target,
                    [
                        ResourceUse(f"{token}_in_{in_half}_{in_side}", 1.0),
                        ResourceUse(f"{token}_out_{out_half}_{out_side}", 1.0),
                        ResourceUse(shared, 1.0),
                    ],
                    rule="splitter.lane_split", entity=entity.id,
                    extra_evidence=self._mech("splitter.priority_and_filter") + (GEOMETRY_EVIDENCE,),
                )

    def _machine_endpoints(self, entity: SpatialEntity) -> None:
        for name in ("input", "output"):
            endpoint = _inventory(entity.id, name)
            self.inventories.append(Inventory(
                endpoint, entity.position, ANY_ITEM, Capacity("unknown", None),
                (GEOMETRY_EVIDENCE, PROTOTYPE_EVIDENCE),
            ))

    def _inserter_endpoints(self, entity: SpatialEntity) -> None:
        self._add_port(entity.id, "hand", entity.position, entity.direction, "bidirectional")
        self._group(
            f"{entity_token(entity.id)}_hand", "inserter", Capacity("unknown", None),
            self._mech("inserter.rate.cycle_and_stack"),
        )

    # -- arcs -------------------------------------------------------------
    def _arc(self, arc_id: str, source: EndpointId, target: EndpointId,
             resources: Sequence[ResourceUse], *, rule: str,
             conditions: Sequence[str] = (), entity: EntityId | None = None,
             extra_evidence: Sequence[str] = ()) -> None:
        names = list(dict.fromkeys(conditions))
        for owner in {source.entity, target.entity} | ({entity} if entity else set()):
            names += [c for c in self.extra_conditions.get(owner, ()) if c not in names]
        semantics = "conditional" if names else self.profile.semantics(rule)
        evidence = tuple(dict.fromkeys(self._mech(rule) + tuple(extra_evidence)
                                       + (self._mech("circuit.control_state") if names and any(
                                           n.startswith("circuit_") for n in names) else ())))
        self.arcs.append(Arc(arc_id, source, target, ANY_ITEM, semantics, tuple(names),
                             tuple(resources), evidence))

    def _handover_group(self) -> str:
        return self._group(
            HANDOVER_GROUP, "other", Capacity("unlimited", None),
            self._mech("belt.transfer.belt_to_belt"),
        )

    # -- entity pass ------------------------------------------------------
    def _entities(self) -> None:
        for entity in self.index:
            role = self.roles[entity.id]
            if role in (tr.BELT, tr.UNDERGROUND_IN, tr.UNDERGROUND_OUT):
                self._belt_endpoints(entity)
            elif role == tr.SPLITTER:
                self._splitter_endpoints(entity)
            elif role == tr.INSERTER:
                self._inserter_endpoints(entity)
            elif role == tr.MACHINE:
                self._machine_endpoints(entity)

    def _controls(self) -> None:
        for entity in self.index:
            if self.roles[entity.id] != tr.OTHER and tr.circuit_controlled(entity):
                self.extra_conditions[entity.id] = (_condition_token(entity.id),)

    # -- connections ------------------------------------------------------
    def _lane_endpoint(self, ident: EntityId, side: str, role: str, half: str, direction: str) -> EndpointId:
        if role == tr.SPLITTER:
            return _port(ident, f"{'in' if direction == 'in' else 'out'}_{half}_{side}")
        return _port(ident, f"{'in' if direction == 'in' else 'out'}_{side}")

    def _handovers(self) -> None:
        handover = self._handover_group()
        for hand in tr.belt_handovers(self.index, self.roles):
            source_role = self.roles[hand.source]
            target_role = self.roles[hand.target]
            rear_into_exit = hand.rear and target_role == tr.UNDERGROUND_OUT
            base = [tr.UNDERGROUND_EXIT_REAR_FEED] if rear_into_exit else []
            prefix = f"{entity_token(hand.source)}_{hand.source_half}_to_{entity_token(hand.target)}_{hand.target_half}"
            def ends(side, target_side):
                return (self._lane_endpoint(hand.source, side, source_role, hand.source_half, "out"),
                        self._lane_endpoint(hand.target, target_side, target_role, hand.target_half, "in"))

            if hand.kind in ("straight", "turn"):
                rule = ("belt.transfer.belt_to_belt" if hand.kind == "straight"
                        else "belt.turn.lane_behavior")
                suffix = "" if hand.kind == "straight" else "turn_"
                for side in tr.LANE_SIDES:
                    source, target = ends(side, side)
                    self._connect(source, target)
                    self._arc(f"{prefix}_{suffix}{side}", source, target,
                              [ResourceUse(handover, 1.0)], rule=rule, conditions=base,
                              extra_evidence=(GEOMETRY_EVIDENCE,))
            else:
                for side in tr.LANE_SIDES:
                    for target_side in tr.LANE_SIDES:
                        near = target_side == hand.near_side
                        source, target = ends(side, target_side)
                        self._connect(source, target)
                        self._arc(
                            f"{prefix}_sideload_{side}_{target_side}", source, target,
                            [ResourceUse(handover, 1.0)], rule="belt.side_load.lane_assignment",
                            conditions=base + [tr.SIDE_LOAD_NEAR_LANE if near else tr.SIDE_LOAD_FAR_LANE],
                            extra_evidence=(GEOMETRY_EVIDENCE,),
                        )

    def _tunnels(self) -> None:
        handover = self._handover_group()
        pairs = tr.underground_pairs(self.index, self.roles, self.extract)
        seen: dict[EntityId, list[tr.TunnelPair]] = defaultdict(list)
        for pair in pairs:
            seen[pair.entrance].append(pair)
            prefix = f"{entity_token(pair.entrance)}_tunnel_{entity_token(pair.exit)}"
            for side in tr.LANE_SIDES:
                for target_side in tr.LANE_SIDES:
                    crossed = side != target_side
                    conditions = list(pair.conditions) + ([tr.UNDERGROUND_LANE_CROSSING] if crossed else [])
                    self._connect(_port(pair.entrance, f"out_{side}"),
                                  _port(pair.exit, f"in_{target_side}"))
                    self._arc(
                        f"{prefix}_{side}_{target_side}",
                        _port(pair.entrance, f"out_{side}"),
                        _port(pair.exit, f"in_{target_side}"),
                        [ResourceUse(handover, 1.0)],
                        rule="underground.lane_mapping", conditions=conditions,
                        extra_evidence=self._mech("underground.pairing.range", "underground.pairing.conflict")
                        + (GEOMETRY_EVIDENCE, PROTOTYPE_EVIDENCE),
                    )
        self._tunnel_findings(seen)

    def _endpoints_at(self, tile: tuple[int, int], direction: str, exclude: EntityId) -> list[EndpointId]:
        """Endpoints an inserter could use on `tile`; `direction` is 'out' or 'in'."""
        out: list[EndpointId] = []
        for occupant in sorted(self.index.occupants(*tile), key=lambda e: e.entity_number):
            if occupant.id == exclude:
                continue
            role = self.roles.get(occupant.id, tr.OTHER)
            if role in (tr.BELT, tr.UNDERGROUND_IN, tr.UNDERGROUND_OUT):
                out += [_lane(occupant.id, side) for side in tr.LANE_SIDES]
            elif role == tr.SPLITTER:
                half = next((h for h, t in tr.half_tiles(occupant, role) if t == tile), None)
                if half is not None:
                    out += [_port(occupant.id, f"{'out' if direction == 'out' else 'in'}_{half}_{side}")
                            for side in tr.LANE_SIDES]
            elif role == tr.MACHINE:
                out.append(_inventory(occupant.id, "output" if direction == "out" else "input"))
        return out

    def _inserters(self) -> None:
        handover = self._handover_group()
        self.reaches = tr.inserter_reaches(self.index, self.roles, self.extract)
        for reach in self.reaches:
            token = entity_token(reach.inserter)
            hand = _port(reach.inserter, "hand")
            group = f"{token}_hand"
            legs = (
                (tr.INSERTER_ROTATION_DOCUMENTED, reach.documented_tile, reach.reversed_tile, "doc"),
                (tr.INSERTER_ROTATION_REVERSED, reach.reversed_tile, reach.documented_tile, "rev"),
            )
            connected = 0
            for condition, pickup_tile, drop_tile, label in legs:
                if pickup_tile is None or drop_tile is None:
                    continue
                sources = self._endpoints_at(pickup_tile, "out", reach.inserter)
                targets = self._endpoints_at(drop_tile, "in", reach.inserter)
                for n, source in enumerate(sources):
                    self._arc(
                        f"{token}_pick_{label}_{n}", source, hand,
                        [ResourceUse(group, 1.0)], rule="inserter.endpoints.pickup_drop_tiles",
                        conditions=[condition], entity=reach.inserter,
                        extra_evidence=self._mech("inserter.rate.cycle_and_stack") + (GEOMETRY_EVIDENCE, PROTOTYPE_EVIDENCE),
                    )
                for n, target in enumerate(targets):
                    self._arc(
                        f"{token}_drop_{label}_{n}", hand, target,
                        [ResourceUse(handover, 1.0)], rule="inserter.endpoints.pickup_drop_tiles",
                        conditions=[condition], entity=reach.inserter,
                        extra_evidence=(GEOMETRY_EVIDENCE, PROTOTYPE_EVIDENCE),
                    )
                connected += bool(sources) and bool(targets)
            self._inserter_findings(reach, connected)

    # -- activities -------------------------------------------------------
    def _activities(self) -> None:
        recipes = self.options.recipes
        for entity in self.index:
            if self.roles[entity.id] != tr.MACHINE:
                continue
            declared = entity.record.get("recipe")
            if isinstance(declared, str):
                candidates: tuple[str, ...] = ()
                wanted = (declared,)
                rule = "machine.activity.assembling_machine_2"
            else:
                candidates = tuple(dict.fromkeys(self.options.furnace_candidates))
                wanted = candidates
                rule = "machine.activity.electric_furnace"
            if recipes is None or not wanted:
                self._finding(
                    "machine_recipe_unresolved", "warning", "structural",
                    f"{entity.key} ({entity.prototype}) has no resolved recipe, so it contributes no activity; "
                    "nothing is inferred from its neighbours.",
                    entity_ids=(entity.id,), evidence_ids=(GEOMETRY_EVIDENCE,),
                )
                continue
            built = []
            for name in wanted:
                activity = recipes.activity(entity.prototype, name)
                if activity is None:
                    self._finding(
                        "recipe_unavailable", "warning", "structural",
                        f"{entity.key}: recipe {name!r} is unknown to the shared calculation layer "
                        f"for {entity.prototype}; no activity is created.",
                        entity_ids=(entity.id,), evidence_ids=(GEOMETRY_EVIDENCE,),
                    )
                    continue
                if activity.fluids:
                    self._finding(
                        "recipe_uses_fluid", "warning", "structural",
                        f"{entity.key}: recipe {name!r} involves fluids ({', '.join(activity.fluids)}), "
                        "which the first profile does not model; no activity is created.",
                        entity_ids=(entity.id,), evidence_ids=(GEOMETRY_EVIDENCE,),
                    )
                    continue
                built.append(activity)
            if not built:
                continue
            token = entity_token(entity.id)
            group = self._group(f"{token}_time", "machine_time", Capacity("finite", 1.0),
                                self._mech(rule) + (PROTOTYPE_EVIDENCE,))
            if candidates:
                self.furnace_candidates[entity.id] = tuple(a.recipe for a in built)
            for activity in built:
                self.activities.append(Activity(
                    id=f"{token}_{activity.recipe}".replace(".", "_"),
                    entity=entity.id, recipe=activity.recipe,
                    inputs=tuple(ActivityMaterial(_inventory(entity.id, "input"), Material("item", n, "normal"), a)
                                 for n, a in activity.inputs),
                    outputs=tuple(ActivityMaterial(_inventory(entity.id, "output"), Material("item", n, "normal"), a)
                                  for n, a in activity.outputs),
                    craft_capacity=Capacity("finite", activity.crafts_per_second),
                    resources=(ResourceUse(group, 1.0 / activity.crafts_per_second),),
                    evidence_ids=self._mech(rule) + (PROTOTYPE_EVIDENCE,),
                ))

    # -- unsupported topology --------------------------------------------
    def _gaps(self) -> None:
        for entity in self.index:
            if self.roles[entity.id] != tr.OTHER:
                continue
            if entity.subsystem not in ITEM_SUBSYSTEMS:
                # Power, circuit, rail and fluid entities are admitted (or not) by an
                # explicit irrelevance declaration in the request under a named basis.
                # Writing a gap for them would either withhold every bound whatever the
                # request declares (`may_connect: true`) or assert a disconnection this
                # module cannot prove (`may_connect: false`); the contract routes them
                # through the declaration instead, and `unresolved_reasons` still
                # withholds when no declaration covers them.
                self._finding(
                    "unsupported_non_item_entity", "warning", "structural",
                    f"{entity.key} ({entity.prototype}) is unsupported and classified "
                    f"{entity.subsystem!r} by the prototype adapter. It carries no supported item "
                    "endpoint here. Bounds stay withheld unless the request declares this "
                    "subsystem irrelevant under its named basis; no disconnection is asserted.",
                    entity_ids=(entity.id,),
                    evidence_ids=(GEOMETRY_EVIDENCE, PROTOTYPE_EVIDENCE)
                    + self._mech("unsupported.entity_visibility"),
                )
                continue
            neighbours = self._nearby_endpoints(entity)
            assumed = entity.geometry_source != "prototype"
            may_connect = bool(neighbours) or assumed
            reason = (
                "unsupported entity adjacent to supported transport endpoints; it may or may "
                "not exchange items with them, so no bound may be advertised"
                if neighbours else
                "unsupported entity with an assumed unit footprint, which can under-cover a "
                "larger prototype, so non-adjacency is not proven"
                if assumed else
                "unsupported entity whose recorded prototype footprint touches no supported endpoint"
            )
            self.gaps.append(TopologyGap(
                id="gap_" + entity_token(entity.id), entity_ids=(entity.id,),
                possible_endpoints=tuple(neighbours), may_connect=may_connect,
                reason=f"{entity.prototype} ({entity.subsystem}, mod {entity.mod}): {reason}",
                evidence_ids=(GEOMETRY_EVIDENCE, PROTOTYPE_EVIDENCE)
                + self._mech("unsupported.entity_visibility"),
            ))
            self._finding(
                "unsupported_possible_bridge" if may_connect else "unsupported_isolated",
                "warning" if may_connect else "info",
                "estimated" if may_connect else "structural",
                f"{entity.key} ({entity.prototype}) is not supported by "
                f"{MECHANICS_PROFILE}: {reason}.",
                entity_ids=(entity.id,), endpoint_ids=tuple(neighbours[:8]),
                evidence_ids=(GEOMETRY_EVIDENCE,) + self._mech("unsupported.entity_visibility"),
            )

    def _nearby_endpoints(self, entity: SpatialEntity) -> list[EndpointId]:
        """Supported endpoints an unsupported entity could conceivably reach.

        Adjacency covers a direct handover; an inserter whose candidate tiles
        cover the entity is included as well, because reaching two tiles away is
        exactly what an inserter does.
        """
        found: list[EndpointId] = []
        own = set(entity.tiles())
        for reach in self.reaches:
            tiles = {t for t in (reach.documented_tile, reach.reversed_tile) if t is not None}
            if tiles & own:
                found.append(_port(reach.inserter, "hand"))
        for neighbour in self.index.neighbors(entity, distance=1, diagonal=True):
            role = self.roles.get(neighbour.id, tr.OTHER)
            if role in (tr.BELT, tr.UNDERGROUND_IN, tr.UNDERGROUND_OUT):
                found += [_lane(neighbour.id, side) for side in tr.LANE_SIDES]
            elif role == tr.SPLITTER:
                found += [_port(neighbour.id, f"{d}_{half}_{side}")
                          for d in ("in", "out") for half, _ in tr.half_tiles(neighbour, role)
                          for side in tr.LANE_SIDES]
            elif role == tr.MACHINE:
                found += [_inventory(neighbour.id, n) for n in ("input", "output")]
            elif role == tr.INSERTER:
                found.append(_port(neighbour.id, "hand"))
        return sorted(dict.fromkeys(found), key=lambda e: e.key)

    # -- boundaries and breaks -------------------------------------------
    def _connect(self, source: EndpointId, target: EndpointId) -> None:
        """Record a lane end closed by a handover, so it is neither break nor boundary."""
        self.connected.add(source)
        self.connected.add(target)

    def _boundaries(self) -> None:
        """Split unconnected lane ends into open interfaces and internal breaks.

        A lane end whose next tile holds nothing is *open*: material could cross
        there, and whether anything actually does is external context only the
        request can declare, so the port is a boundary candidate and nothing is
        imported or removed on its account. A lane end blocked by an entity that
        does not connect -- a machine wall, an opposing belt, an unsupported
        prototype -- is an internal break. The distinction is a property of the
        neighbouring tile, so it survives translation and rotation; a bounding
        box would not.
        """
        used = self.connected
        internal: dict[EntityId, list[EndpointId]] = defaultdict(list)
        boundary: dict[EntityId, list[EndpointId]] = defaultdict(list)
        for endpoint, port in sorted(self.ports.items(), key=lambda kv: kv[0].key):
            if endpoint in used or port.role == "bidirectional":
                continue
            entity = self.index.by_id(endpoint.entity)
            if self._is_tunnel_mouth(entity, port.role):
                # An underground entrance's front face and an exit's rear face are
                # the tunnel, not the surface. An unpaired one is a broken tunnel,
                # reported as `underground_unpaired`, and it must never look like
                # an external interface where a request could declare a feed.
                continue
            direction = entity.direction if port.role == "outgoing" else tr.opposite(entity.direction)
            faced = tr.step(tr.tile_of(port.position.x, port.position.y), direction)
            blocked = [e for e in self.index.occupants(*faced) if e.id != entity.id]
            open_end = not blocked
            self.ports[endpoint] = replace(port, boundary_candidate=open_end)
            (boundary if open_end else internal)[endpoint.entity].append(endpoint)
        for ident, endpoints in sorted(boundary.items(), key=lambda kv: kv[0].entity_number):
            self._finding(
                "transport_boundary_candidate", "info", "structural",
                f"{ident.key}: {len(endpoints)} lane endpoint(s) face an empty tile. External "
                "context is incomplete: this is a candidate interface, not a declared feed or "
                "export, and nothing is imported or removed here unless the request declares it.",
                entity_ids=(ident,), endpoint_ids=tuple(endpoints), evidence_ids=(GEOMETRY_EVIDENCE,),
            )
        for ident, endpoints in sorted(internal.items(), key=lambda kv: kv[0].entity_number):
            self._finding(
                "transport_internal_break", "warning", "structural",
                f"{ident.key}: {len(endpoints)} lane endpoint(s) are blocked by an entity that "
                "offers no supported handover. This is an internal break inside the layout, not a "
                "boundary interface, and no external supply or removal is implied.",
                entity_ids=(ident,), endpoint_ids=tuple(endpoints), evidence_ids=(GEOMETRY_EVIDENCE,),
            )

    def _resolved(self, endpoint: EndpointId, role: str) -> EndpointId:
        lane = self._lane_index.get(endpoint)
        if lane is None:
            return endpoint
        return lane.incoming if role == "in" else lane.outgoing

    def _edges(self) -> tuple[dict[EndpointId, list[EndpointId]], dict[EndpointId, list[EndpointId]]]:
        """Forward and reverse adjacency over every arc, conditional ones included.

        A conditional arc is a link the evidence does not exclude, so it counts
        for reachability: removing unknown links and then declaring something
        unreachable would be exactly the unsound step the contract forbids.
        """
        self._lane_index = {lane.id: lane for lane in self.lanes}
        forward: dict[EndpointId, list[EndpointId]] = defaultdict(list)
        reverse: dict[EndpointId, list[EndpointId]] = defaultdict(list)
        pairs = [(self._resolved(a.source, "out"), self._resolved(a.target, "in")) for a in self.arcs]
        for activity in self.activities:
            for part in activity.inputs:
                for out in activity.outputs:
                    pairs.append((self._resolved(part.endpoint, "out"), self._resolved(out.endpoint, "in")))
        for source, target in pairs:
            forward[source].append(target)
            reverse[target].append(source)
        return forward, reverse

    @staticmethod
    def _closure(edges: Mapping[EndpointId, Sequence[EndpointId]],
                 seeds: Iterable[EndpointId]) -> set[EndpointId]:
        seen = set(seeds)
        queue = list(seen)
        while queue:
            for nxt in edges.get(queue.pop(), ()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return seen

    def _is_tunnel_mouth(self, entity: SpatialEntity, role: str) -> bool:
        kind = self.roles.get(entity.id)
        return ((kind == tr.UNDERGROUND_IN and role == "outgoing")
                or (kind == tr.UNDERGROUND_OUT and role == "incoming"))

    def _machine_findings(self) -> None:
        """Distinguish an isolated machine from one whose products cannot leave.

        `disconnected_producer` is local: no supported endpoint touches either
        inventory. The other two are reachability claims over the whole selected
        area, so they downgrade to `estimated` while any `may_connect` gap could
        still supply the missing link.
        """
        forward, reverse = self._edges()
        entrances = [e for e, p in self.ports.items() if p.boundary_candidate and p.role != "outgoing"]
        exits = [e for e, p in self.ports.items() if p.boundary_candidate and p.role != "incoming"]
        from_boundary = self._closure(forward, entrances)
        to_boundary = self._closure(reverse, exits)
        open_gap = any(g.may_connect for g in self.gaps)
        kind = "estimated" if open_gap else "structural"
        caveat = (
            " An unresolved possible bridge is present, so this is a reachability observation "
            "over the supported topology, not a proven disconnection."
            if open_gap else ""
        )
        incoming: set[EndpointId] = {self._resolved(a.target, "in") for a in self.arcs}
        outgoing: set[EndpointId] = {self._resolved(a.source, "out") for a in self.arcs}
        for entity in self.index:
            if self.roles[entity.id] != tr.MACHINE:
                continue
            source = _inventory(entity.id, "output")
            sink = _inventory(entity.id, "input")
            if sink not in incoming and source not in outgoing:
                self._finding(
                    "disconnected_producer", "warning", "structural",
                    f"{entity.key} ({entity.prototype}) has no supported inserter reaching either "
                    "inventory: no endpoint can supply or empty it. Standing on a machine "
                    "footprint is not itself a valid endpoint.",
                    entity_ids=(entity.id,), evidence_ids=(GEOMETRY_EVIDENCE,),
                )
                continue
            if source not in to_boundary:
                self._finding(
                    "blocked_output", "warning", kind,
                    f"{entity.key} ({entity.prototype}): nothing this machine produces can reach a "
                    f"boundary endpoint of the selected area through supported transport.{caveat}",
                    entity_ids=(entity.id,), endpoint_ids=(source,),
                    evidence_ids=(GEOMETRY_EVIDENCE,),
                )
            if sink not in from_boundary:
                self._finding(
                    "unreachable_input", "warning", kind,
                    f"{entity.key} ({entity.prototype}): no boundary endpoint of the selected area "
                    f"can reach this machine's input inventory through supported transport. This "
                    f"is incomplete external context, not a claim that the machine is starved.{caveat}",
                    entity_ids=(entity.id,), endpoint_ids=(sink,),
                    evidence_ids=(GEOMETRY_EVIDENCE,),
                )

    def _inserter_findings(self, reach: tr.InserterReach, connected: int) -> None:
        machines = [
            t for t in (reach.documented_tile, reach.reversed_tile) if t is not None
            and any(self.roles.get(o.id) == tr.MACHINE for o in self.index.occupants(*t))
        ]
        if len(machines) == 2:
            self._finding(
                "direct_insertion", "info", "estimated",
                f"{reach.inserter.key} reaches a machine inventory on both candidate tiles: a "
                "direct machine-to-machine insertion under either rotation sense.",
                entity_ids=(reach.inserter,), evidence_ids=self._mech("inserter.endpoints.pickup_drop_tiles"),
            )
        if not connected:
            self._finding(
                "inserter_endpoint_missing", "warning", "structural",
                f"{reach.inserter.key} has no candidate tile pair with both a source and a "
                "destination endpoint; being on a footprint is not itself a valid endpoint.",
                entity_ids=(reach.inserter,), evidence_ids=(GEOMETRY_EVIDENCE,),
            )
        if reach.filters:
            self._finding(
                "item_filter_relaxed", "info", "estimated",
                f"{reach.inserter.key} declares item filter(s) {', '.join(reach.filters)}. "
                "No mechanics record covers inserter filtering, so the filter is recorded and "
                "relaxed rather than applied: applying an unobserved restriction could turn a "
                "satisfiable request into a false shortfall.",
                entity_ids=(reach.inserter,),
                evidence_ids=(GEOMETRY_EVIDENCE,) + self._mech("splitter.priority_and_filter"),
            )

    def _tunnel_findings(self, pairs: Mapping[EntityId, Sequence[tr.TunnelPair]]) -> None:
        paired_exits = {p.exit for found in pairs.values() for p in found}
        for entity in self.index:
            if self.roles[entity.id] == tr.UNDERGROUND_OUT and entity.id not in paired_exits:
                self._finding(
                    "underground_unpaired", "warning", "structural",
                    f"{entity.key}: no same-tier underground entrance behind it pairs with this "
                    "exit under either reading of max_distance; its tunnel has no supported near "
                    "end.",
                    entity_ids=(entity.id,),
                    evidence_ids=(GEOMETRY_EVIDENCE,) + self._mech("underground.pairing.range"),
                )
            if self.roles[entity.id] != tr.UNDERGROUND_IN:
                continue
            found = pairs.get(entity.id, ())
            if not found:
                self._finding(
                    "underground_unpaired", "warning", "structural",
                    f"{entity.key}: no same-tier underground exit lies ahead within either "
                    "reading of max_distance; the tunnel has no supported far end.",
                    entity_ids=(entity.id,),
                    evidence_ids=(GEOMETRY_EVIDENCE,) + self._mech("underground.pairing.range"),
                )
            elif len(found) > 1 or any(p.conditions for p in found):
                self._finding(
                    "underground_pairing_ambiguous", "warning", "estimated",
                    f"{entity.key}: {len(found)} candidate exit(s) at separation "
                    f"{', '.join(str(p.separation) for p in found)}. max_distance is "
                    f"{tr.underground_reach(entity.prototype, self.extract).max_distance} and the "
                    "documentation does not say whether it counts the gap or the separation, so "
                    "every candidate stays available under a named condition rather than one "
                    "being chosen.",
                    entity_ids=(entity.id,) + tuple(p.exit for p in found),
                    evidence_ids=self._mech("underground.pairing.range", "underground.pairing.conflict"),
                )

    def _splitter_findings(self) -> None:
        for entity in self.index:
            if self.roles[entity.id] != tr.SPLITTER:
                continue
            filters = tr.declared_filters(entity)
            record = entity.record
            priority = [k for k in ("input_priority", "output_priority") if k in record]
            self._finding(
                "splitter_distribution_relaxed", "info", "estimated",
                f"{entity.key}: all sixteen lane paths stay open and share one splitter resource. "
                f"Declared filter(s): {', '.join(filters) or 'none'}; declared priorit(ies): "
                f"{', '.join(priority) or 'none'}. splitter.lane_split and "
                "splitter.priority_and_filter are pending, so priorities and filters are relaxed "
                "and recorded, never modelled as a hard split.",
                entity_ids=(entity.id,),
                evidence_ids=self._mech("splitter.lane_split", "splitter.priority_and_filter"),
            )

    def _used_evidence(self) -> set[str]:
        used: set[str] = set()
        for obj in (list(self.arcs) + list(self.groups.values()) + list(self.activities)
                    + list(self.lanes) + list(self.gaps) + list(self.inventories)):
            used |= set(obj.evidence_ids)
        return used

    def _profile_findings(self) -> None:
        """Report every unobserved rule this graph actually relies on.

        Scoped to rules in use: a layout with no splitter should not be told that
        splitter distribution is unobserved.
        """
        used = self._used_evidence()
        for rule_id in self.profile.unobserved():
            name, _ = MECHANICS_EVIDENCE[rule_id]
            if name not in used:
                continue
            rule = self.profile.rules[rule_id]
            self._finding(
                "mechanics_unobserved", "warning", "estimated",
                f"{rule_id} is {rule.status}, not observed in a controlled game capture. "
                f"{rule.expected_behavior} Arcs relying on it are relaxed, never exact.",
                evidence_ids=(name,),
            )
        if any(g.kind == "inserter" for g in self.groups.values()):
            self._finding(
                "inserter_capacity_unknown", "info", "estimated",
                "Every inserter capacity group is `unknown`: inserter.rate.cycle_and_stack gives "
                "no items/s from the prototype, and hand size depends on research the blueprint "
                "does not record. An optimistic model relaxes these to unlimited; detailed "
                "inserter timing is task 09.",
                evidence_ids=self._mech("inserter.rate.cycle_and_stack"),
            )
        if any(c.startswith("inserter_rotation") for arc in self.arcs for c in arc.conditions):
            self._finding(
                "inserter_rotation_unresolved", "warning", "conditional",
                "The rotation sense of pickup_position/insert_position is not observed, so both "
                f"role assignments stay available as conditions {tr.INSERTER_ROTATION_DOCUMENTED} "
                f"and {tr.INSERTER_ROTATION_REVERSED}. No convention is chosen here; on the pilot "
                "the layout's own geometry cannot discriminate them (task 03 handoff, section 4).",
                evidence_ids=self._mech("inserter.endpoints.pickup_drop_tiles"),
            )

    # -- findings ---------------------------------------------------------
    def _finding(self, code: str, severity: str, kind: str, message: str, *,
                 entity_ids: Sequence[EntityId] = (), endpoint_ids: Sequence[EndpointId] = (),
                 material: Material | None = None, evidence_ids: Sequence[str] = ()) -> None:
        entity_ids = tuple(dict.fromkeys(entity_ids))
        endpoint_ids = tuple(dict.fromkeys(endpoint_ids))
        evidence_ids = tuple(dict.fromkeys(evidence_ids))
        self.findings.append(Finding(
            id=finding_id(code, entity_ids, endpoint_ids, material, evidence_ids),
            code=code, severity=severity, evidence_kind=kind, message=message,
            entity_ids=entity_ids, endpoint_ids=endpoint_ids, material=material,
            required_rate=None, capacity_upper_bound=None,
            evidence_ids=evidence_ids, assumptions=(),
        ))

    # -- assembly ---------------------------------------------------------
    def build(self) -> TransportGraph:
        started = time.perf_counter()
        self._build_evidence()
        self._controls()
        self._entities()
        self._handovers()
        self._tunnels()
        self._inserters()
        self._activities()
        self._gaps()
        self._boundaries()
        self._machine_findings()
        self._splitter_findings()
        self._profile_findings()
        built = time.perf_counter()

        entities = tuple(
            e.to_contract_entity(
                evidence_ids=(GEOMETRY_EVIDENCE, PROTOTYPE_EVIDENCE),
                furnace_candidates=self.furnace_candidates.get(e.id, ()),
            )
            for e in self.index
        )
        body = dict(
            schema_version=SCHEMA_VERSION,
            mechanics_profile=MECHANICS_PROFILE,
            provenance=self.options.provenance,
            blueprint=to_dict(JsonDocument.from_value(self.document)),
            prototypes=to_dict(JsonDocument.from_value(self.prototypes)),
            blueprint_hash=content_hash(self.document),
            prototype_hash=content_hash(self.prototypes),
            selected_paths=[list(self.book_path)],
            entities=[to_dict(e) for e in entities],
            ports=[to_dict(self.ports[k]) for k in sorted(self.ports, key=lambda e: e.key)],
            lanes=[to_dict(x) for x in sorted(self.lanes, key=lambda x: x.id.key)],
            inventories=[to_dict(x) for x in sorted(self.inventories, key=lambda x: x.id.key)],
            capacity_groups=[to_dict(self.groups[k]) for k in sorted(self.groups)],
            arcs=[to_dict(a) for a in sorted(self.arcs, key=lambda a: a.id)],
            activities=[to_dict(a) for a in sorted(self.activities, key=lambda a: a.id)],
            evidence=[to_dict(self.evidence[k]) for k in sorted(self.evidence)],
            topology_gaps=[to_dict(g) for g in sorted(self.gaps, key=lambda g: g.id)],
        )
        body["graph_hash"] = content_hash(body)
        graph = parse_graph(body)
        findings = tuple(sorted(self.findings, key=lambda f: (f.code, f.id)))
        elapsed = time.perf_counter() - started
        return TransportGraph(
            graph=graph, findings=findings,
            unobserved_mechanics=self.profile.unobserved(),
            unsupported=tuple(e.id for e in self.index if e.support != "supported"),
            stats={
                "build_seconds": elapsed,
                "topology_seconds": built - started,
                "serialize_seconds": elapsed - (built - started),
                "roles": dict(sorted((r, sum(1 for v in self.roles.values() if v == r))
                                     for r in set(self.roles.values()))),
            },
        )


def build_transport_graph(view: SpatialView, options: RoutingOptions = RoutingOptions()) -> TransportGraph:
    """Build the contract graph for one selected blueprint leaf."""
    return _Builder(view, options).build()


# ---------------------------------------------------------------------------
# Item propagation and reachability
# ---------------------------------------------------------------------------

#: A declared feed whose material identity the caller does not know.
UNKNOWN_ITEMS = None


def possible_items(
    graph: SpatialGraph,
    feeds: Mapping[EndpointId, frozenset[Material] | None] = (),
) -> dict[EndpointId, frozenset[Material] | None]:
    """Materials that could reach each endpoint from declared feeds and recipe outputs.

    A value of `None` means "any item is possible here". A feed mapped to `None`
    is a feed whose identity the caller has *declared unknown*, and it stays
    unknown all the way downstream. That is what stops an undeclared identity
    from producing a false incompatible-filter or unreachable-input finding: an
    unknown feed satisfies every recipe input and every arc filter rather than
    none of them.

    Only declared feeds and fixed recipe outputs introduce material. A dangling
    belt is never treated as a supply, and an endpoint absent from the result is
    simply not known to be reachable -- not proven unreachable.
    """
    lanes = {lane.id: lane for lane in graph.lanes}

    def resolve(endpoint: EndpointId, role: str) -> EndpointId:
        lane = lanes.get(endpoint)
        return endpoint if lane is None else (lane.incoming if role == "in" else lane.outgoing)

    reached: dict[EndpointId, frozenset[Material] | None] = {}

    def merge(endpoint: EndpointId, items: frozenset[Material] | None) -> bool:
        current = reached.get(endpoint, ())
        if current is None:
            return False  # already "anything"
        if items is None:
            reached[endpoint] = None
            return True
        merged = frozenset(items) if current == () else current | items
        if current != () and merged == current:
            return False
        reached[endpoint] = merged
        return True

    def available(endpoint: EndpointId, material: Material) -> bool:
        if endpoint not in reached:
            return False
        items = reached[endpoint]
        return items is None or material in items

    outgoing: dict[EndpointId, list[Arc]] = defaultdict(list)
    for arc in graph.arcs:
        outgoing[resolve(arc.source, "out")].append(arc)

    for endpoint, items in dict(feeds or {}).items():
        merge(resolve(endpoint, "in"), items)

    changed = True
    while changed:
        changed = False
        for endpoint in list(reached):
            items = reached[endpoint]
            for arc in outgoing.get(endpoint, ()):
                allowed = items if items is None else frozenset(
                    m for m in items if arc.eligibility.allows(m))
                if allowed is None or allowed:
                    changed |= merge(resolve(arc.target, "in"), allowed)
        for activity in graph.activities:
            if not all(available(resolve(p.endpoint, "out"), p.material) for p in activity.inputs):
                continue
            for part in activity.outputs:
                changed |= merge(resolve(part.endpoint, "in"), frozenset({part.material}))
    return reached


def reachable_from(graph: SpatialGraph, sources: Iterable[EndpointId]) -> frozenset[EndpointId]:
    """Endpoints reachable through supported arcs, ignoring materials and capacities.

    Every arc counts, including conditional ones: an unknown possible link may
    never be removed and then used to prove a disconnection.
    """
    lanes = {lane.id: lane for lane in graph.lanes}

    def resolve(endpoint: EndpointId, role: str) -> EndpointId:
        lane = lanes.get(endpoint)
        return endpoint if lane is None else (lane.incoming if role == "in" else lane.outgoing)

    edges: dict[EndpointId, list[EndpointId]] = defaultdict(list)
    for arc in graph.arcs:
        edges[resolve(arc.source, "out")].append(resolve(arc.target, "in"))
    for activity in graph.activities:
        for part in activity.inputs:
            for out in activity.outputs:
                edges[resolve(part.endpoint, "out")].append(resolve(out.endpoint, "in"))
    seen = {resolve(s, "in") for s in sources}
    queue = list(seen)
    while queue:
        for nxt in edges.get(queue.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return frozenset(seen)


__all__ = [
    "ANY_ITEM", "HANDOVER_GROUP", "MachineActivity", "RecipeSource", "RoutingError",
    "RoutingOptions", "TransportGraph", "build_transport_graph", "entity_token",
    "possible_items", "reachable_from",
]
