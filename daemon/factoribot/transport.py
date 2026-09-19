"""Supported transport mechanics: geometry, candidate connections, evidence status.

This module is the *mechanics* half of routing task 04. It answers geometric
questions about a `spatial.SpatialIndex` -- which belt hands over to which,
which underground entrance can reach which exit, which tiles an inserter can
reach -- and it carries the evidence status of every engine rule those answers
depend on. It builds no contract records; `routing.py` does that.

Two rules govern everything here.

**Nothing is asserted beyond its evidence.** Task 02's mechanics records are
the authority (`daemon/factoribot/evidence/routing_mechanics_observations/`). At the
time of writing every one of the sixteen rules is `documented-only` or
`pending`; none is `observed`. A candidate connection therefore never carries
`exact` semantics: `semantics_for()` maps `observed` to `exact` and everything
else to `relaxed`, so the profile upgrades itself when a capture lands and
never before.

**An ambiguity stays open on both sides.** Where a rule leaves two readings
possible -- the inserter's rotation sense, the underground `max_distance`
gap-versus-separation reading, which lane a side-load feeds -- both readings
are emitted as separate candidates under named conditions from `CONDITIONS`.
The optimistic model (`relax_open`) opens all of them, which is sound for an
upper bound; an `explicit` request must state each one. Nothing here silently
picks a convention, and nothing here deletes a possible link.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import math
from typing import Iterable, Mapping

from .blueprint_contract import EntityId
from .spatial import SpatialEntity, SpatialIndex, rotate_offset
from .transport_prototypes import (
    EVIDENCE_STATUSES, TARGET_MECHANICS_PROFILE, PrototypeExtract,
    load_observations, load_pinned_extract,
)


class TransportError(ValueError):
    """A transport-geometry question that cannot be answered as asked."""

    def __init__(self, code: str, message: str, **detail):
        super().__init__(message)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# Mechanics evidence
# ---------------------------------------------------------------------------

#: Engine rules this module relies on, in the order they are reported.
MECHANICS_RULES = (
    "belt.straight.lane_capacity",
    "belt.transfer.belt_to_belt",
    "belt.turn.lane_behavior",
    "belt.side_load.lane_assignment",
    "underground.pairing.range",
    "underground.pairing.conflict",
    "underground.lane_mapping",
    "splitter.lane_split",
    "splitter.priority_and_filter",
    "inserter.endpoints.pickup_drop_tiles",
    "inserter.rate.cycle_and_stack",
    "circuit.control_state",
    "machine.activity.assembling_machine_2",
    "machine.activity.electric_furnace",
    "unsupported.entity_visibility",
)


@dataclass(frozen=True)
class MechanicsRule:
    """One engine rule plus the evidence status recorded for it by task 02."""

    id: str
    status: str  # observed | documented-only | pending
    title: str
    expected_behavior: str
    blocking_gate: str | None
    evidence_profile: str
    compatible: bool

    @property
    def observed(self) -> bool:
        return self.compatible and self.status == "observed"


@lru_cache(maxsize=4)
def load_mechanics(directory: str | None = None) -> Mapping[str, MechanicsRule]:
    """Read task 02's observation records; the evidence status is theirs, not ours."""
    rules = {}
    for record in load_observations(directory):
        compatible = record.profile == TARGET_MECHANICS_PROFILE
        rules[record.record_id] = MechanicsRule(
            id=record.record_id,
            # Historical evidence keeps its original profile and advertised
            # provenance. Compatibility is enforced by ``observed``/semantics.
            status=record.evidence_status,
            title=record.title,
            expected_behavior=record.expected_behavior,
            blocking_gate=(record.blocking_gate if compatible else
                           f"legacy evidence targets {record.profile}; obtain a compatible {TARGET_MECHANICS_PROFILE} observation"),
            evidence_profile=record.profile,
            compatible=compatible,
        )
    missing = [r for r in MECHANICS_RULES if r not in rules]
    if missing:
        raise TransportError(
            "missing_mechanics_record",
            "transport mechanics records absent: " + ", ".join(missing),
            missing=missing,
        )
    return rules


def semantics_for(status: str) -> str:
    """Contract arc semantics justified by an evidence status.

    Only an `observed` rule may claim `exact`. A `documented-only` rule rests on
    version-pinned documentation, which task 02 explicitly says is not enough to
    close the release gate, so it produces a `relaxed` arc. Callers add
    `conditional` themselves when the arc also carries named conditions.
    """
    if status not in EVIDENCE_STATUSES:
        raise TransportError("unknown_evidence_status", f"unknown evidence status {status!r}")
    return "exact" if status == "observed" else "relaxed"


def evidence_kind_for(status: str, *, bound: bool = False) -> str:
    """Contract evidence kind for a rule of this status.

    `observed` records are `observed`. A finite ceiling read from documentation
    is an `upper_bound`. Everything else is `estimated`: a pending rule may not
    masquerade as structural, because `unresolved_reasons` treats structural
    evidence as strong enough to prove a disconnection.
    """
    if status not in EVIDENCE_STATUSES:
        raise TransportError("unknown_evidence_status", f"unknown evidence status {status!r}")
    if status == "observed":
        return "observed"
    return "upper_bound" if bound else "estimated"


# ---------------------------------------------------------------------------
# Named mechanics conditions
# ---------------------------------------------------------------------------

#: Engine-wide ambiguities, each expressed as a contract condition name. These
#: are conventions of the engine, not of one entity, so a single name covers
#: every entity that depends on it: one control assignment settles all of them.
INSERTER_ROTATION_DOCUMENTED = "inserter_rotation_documented"
INSERTER_ROTATION_REVERSED = "inserter_rotation_reversed"
SIDE_LOAD_NEAR_LANE = "side_load_feeds_near_lane"
SIDE_LOAD_FAR_LANE = "side_load_feeds_far_lane"
UNDERGROUND_REACH_EXTENDED = "underground_reach_extended"
UNDERGROUND_PAIRING_BEYOND = "underground_pairing_beyond_intervening"
UNDERGROUND_LANE_CROSSING = "underground_lane_crossing"
UNDERGROUND_EXIT_REAR_FEED = "underground_exit_rear_feed"

CONDITIONS: Mapping[str, str] = {
    INSERTER_ROTATION_DOCUMENTED: (
        "The prototype's pickup_position/insert_position rotate into the entity "
        "direction under the documented (clockwise) sense."
    ),
    INSERTER_ROTATION_REVERSED: (
        "The same two tiles with the roles exchanged, i.e. the opposite rotation "
        "sense. inserter.endpoints.pickup_drop_tiles does not state the sense."
    ),
    SIDE_LOAD_NEAR_LANE: (
        "A perpendicular side-load feeds the target lane on the side the load "
        "arrives from."
    ),
    SIDE_LOAD_FAR_LANE: (
        "A perpendicular side-load feeds the target lane away from the side the "
        "load arrives from."
    ),
    UNDERGROUND_REACH_EXTENDED: (
        "The prototype's max_distance counts the tiles between the pair (so the "
        "reach is one tile longer) rather than the centre-to-centre separation."
    ),
    UNDERGROUND_PAIRING_BEYOND: (
        "A tunnel reaches past a nearer same-tier underground endpoint instead of "
        "being captured by it."
    ),
    UNDERGROUND_LANE_CROSSING: (
        "A tunnel exchanges left and right lane identity between its ends."
    ),
    UNDERGROUND_EXIT_REAR_FEED: (
        "A surface belt directly behind an underground exit hands over into it."
    ),
}


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

CARDINAL = (0, 4, 8, 12)
LANE_SIDES = ("left", "right")
#: Lateral offset of a belt lane centre from the belt centre, in tiles.
LANE_OFFSET = 0.25

_FORWARD = {0: (0.0, -1.0), 4: (1.0, 0.0), 8: (0.0, 1.0), 12: (-1.0, 0.0)}


def rotate(dx: float, dy: float, direction: int) -> tuple[float, float]:
    """Rotate a north-frame offset clockwise into `direction` (screen y grows south).

    One definition, shared: this delegates to `spatial.rotate_offset`, which is
    the same rotation `SpatialIndex.inserter_candidates` applies to the
    prototype's pickup/drop offsets. `test_transport.py` still cross-checks the
    two end to end. The direction check stays here so callers keep seeing a
    `TransportError` for a non-cardinal direction.
    """
    if direction not in (0, 4, 8, 12):
        raise TransportError("non_cardinal_direction", f"cannot rotate by direction {direction}")
    return rotate_offset(dx, dy, direction)


def forward(direction: int) -> tuple[float, float]:
    """Unit vector the entity moves items along."""
    try:
        return _FORWARD[direction]
    except KeyError:
        raise TransportError("non_cardinal_direction", f"direction {direction} is not cardinal") from None


def right_of(direction: int) -> tuple[float, float]:
    """Unit vector to the right of an observer looking along `direction`."""
    fx, fy = forward(direction)
    return (-fy, fx)


def lane_offset(side: str, direction: int) -> tuple[float, float]:
    """Offset of one lane centre from the entity centre."""
    if side not in LANE_SIDES:
        raise TransportError("unknown_lane_side", f"unknown lane side {side!r}")
    rx, ry = right_of(direction)
    sign = LANE_OFFSET if side == "right" else -LANE_OFFSET
    return (rx * sign, ry * sign)


def other_lane(side: str) -> str:
    return "right" if side == "left" else "left"


def tile_of(x: float, y: float) -> tuple[int, int]:
    return (math.floor(x), math.floor(y))


def step(tile: tuple[int, int], direction: int, distance: int = 1) -> tuple[int, int]:
    fx, fy = forward(direction)
    return (tile[0] + int(fx) * distance, tile[1] + int(fy) * distance)


def opposite(direction: int) -> int:
    return (direction + 8) % 16


# ---------------------------------------------------------------------------
# Entity roles
# ---------------------------------------------------------------------------

BELT = "belt"
UNDERGROUND_IN = "underground_in"
UNDERGROUND_OUT = "underground_out"
SPLITTER = "splitter"
INSERTER = "inserter"
MACHINE = "machine"
OTHER = "other"

#: Roles that carry belt lanes and take part in surface handovers.
BELT_LIKE = (BELT, UNDERGROUND_IN, UNDERGROUND_OUT, SPLITTER)

_PROTOTYPE_ROLE = {
    "transport-belt": BELT,
    "underground-belt": UNDERGROUND_IN,  # refined by the record's `type`
    "splitter": SPLITTER,
    "inserter": INSERTER,
    "assembling-machine": MACHINE,
    "furnace": MACHINE,
}


def entity_role(entity: SpatialEntity, extract: PrototypeExtract) -> str:
    """Classify a supported entity by what it does to items.

    An entity the first profile does not support is always `OTHER`, whatever its
    prototype type says: `unsupported.entity_visibility` requires that such an
    entity stays visible and never becomes a supported transport link.
    """
    if entity.support != "supported":
        return OTHER
    proto = extract.get(entity.prototype)
    if proto is None:
        return OTHER
    role = _PROTOTYPE_ROLE.get(proto.prototype_type, OTHER)
    if role is UNDERGROUND_IN:
        kind = entity.record.get("type")
        if kind == "output":
            return UNDERGROUND_OUT
        if kind in (None, "input"):
            return UNDERGROUND_IN
        raise TransportError(
            "unknown_underground_type",
            f"{entity.key}: underground belt type {kind!r} is neither input nor output",
            entity=entity.key, type=kind,
        )
    return role


def entity_roles(index: SpatialIndex, extract: PrototypeExtract) -> dict[EntityId, str]:
    return {e.id: entity_role(e, extract) for e in index}


def is_supported_cardinal(entity: SpatialEntity) -> bool:
    return entity.support == "supported" and entity.direction in CARDINAL


# ---------------------------------------------------------------------------
# Occupied tiles and faces
# ---------------------------------------------------------------------------

def half_tiles(entity: SpatialEntity, role: str) -> tuple[tuple[str, tuple[int, int]], ...]:
    """The named lateral halves of a belt-like entity and the tile each covers.

    A belt or underground belt is one tile and has a single half named `centre`.
    A splitter is two tiles side by side; the halves are named by the side they
    sit on looking along the movement direction.
    """
    if role == SPLITTER:
        rx, ry = right_of(entity.direction)
        out = []
        for side, sign in (("left", -0.5), ("right", 0.5)):
            out.append((side, tile_of(entity.position.x + rx * sign, entity.position.y + ry * sign)))
        return tuple(out)
    return (("centre", tile_of(entity.position.x, entity.position.y)),)


def emission_tiles(entity: SpatialEntity, role: str) -> tuple[tuple[str, tuple[int, int]], ...]:
    """Tiles this entity pushes items onto, by half. Empty when it emits nowhere.

    An underground *entrance* emits into its tunnel, not onto the surface, so it
    contributes no surface emission.
    """
    if role not in (BELT, UNDERGROUND_OUT, SPLITTER):
        return ()
    return tuple((half, step(tile, entity.direction)) for half, tile in half_tiles(entity, role))


def accepts_from(entity: SpatialEntity, role: str, source_direction: int) -> str | None:
    """How `entity` would accept a handover arriving along `source_direction`.

    Returns `"rear"`, `"side"`, or None when the geometry offers no handover at
    all -- a head-on push into the target's own output face.
    """
    if role not in BELT_LIKE:
        return None
    if source_direction == entity.direction:
        return "rear"
    if source_direction == opposite(entity.direction):
        return None
    return "side"


def side_of(entity: SpatialEntity, tile: tuple[int, int]) -> str:
    """Which lateral side of `entity` the tile lies on, looking along its direction."""
    rx, ry = right_of(entity.direction)
    cx, cy = entity.position.x, entity.position.y
    lateral = (tile[0] + 0.5 - cx) * rx + (tile[1] + 0.5 - cy) * ry
    return "right" if lateral > 0 else "left"


# ---------------------------------------------------------------------------
# Surface handovers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Handover:
    """One candidate surface handover between two belt-like entities.

    `kind` is `straight` (rear feed, lane identity preserved), `turn` (a
    perpendicular feed into a target with no rear feeder, which the engine draws
    as a curve) or `side_load` (a perpendicular feed into a target that also has
    a rear feeder). `near_side` is the target lane on the side the load arrives
    from, and is set for `turn` and `side_load` only.
    """

    source: EntityId
    source_half: str
    target: EntityId
    target_half: str
    kind: str
    near_side: str | None
    rear: bool


def belt_handovers(index: SpatialIndex, roles: Mapping[EntityId, str]) -> tuple[Handover, ...]:
    """Every candidate surface handover in this leaf, in deterministic order.

    Cost is proportional to the number of emitting halves, not to entity pairs:
    each emission tile is resolved through the index's tile map.
    """
    rear_fed: set[tuple[EntityId, str]] = set()
    candidates: list[tuple] = []
    for source in index:
        role = roles.get(source.id, OTHER)
        if role not in BELT_LIKE or not is_supported_cardinal(source):
            continue
        for half, tile in emission_tiles(source, role):
            for occupant in index.occupants(*tile):
                if occupant.id == source.id:
                    continue
                target_role = roles.get(occupant.id, OTHER)
                if target_role not in BELT_LIKE or not is_supported_cardinal(occupant):
                    continue
                face = accepts_from(occupant, target_role, source.direction)
                if face is None:
                    continue
                target_half = _half_covering(occupant, target_role, tile)
                if target_half is None:
                    continue
                candidates.append((source, half, occupant, target_role, target_half, face, tile))
                if face == "rear":
                    rear_fed.add((occupant.id, target_half))

    out = []
    for source, half, target, target_role, target_half, face, tile in candidates:
        if face == "rear":
            kind, near = "straight", None
        else:
            source_tile = tile_of(source.position.x, source.position.y)
            near = side_of(target, source_tile) if target_role != SPLITTER else side_of(target, source_tile)
            kind = "side_load" if (target.id, target_half) in rear_fed else "turn"
        out.append(Handover(source.id, half, target.id, target_half, kind, near, face == "rear"))
    out.sort(key=lambda h: (h.source.entity_number, h.source_half, h.target.entity_number, h.target_half, h.kind))
    return tuple(out)


def _half_covering(entity: SpatialEntity, role: str, tile: tuple[int, int]) -> str | None:
    for half, own in half_tiles(entity, role):
        if own == tile:
            return half
    return None


# ---------------------------------------------------------------------------
# Underground pairing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UndergroundReach:
    """The two readings of a prototype's raw `max_distance`.

    `underground.pairing.range` is pending and the 2.0.76 documentation gives
    `max_distance` no description, so both readings stay live: `certain` is the
    separation both readings admit, `extended` is the extra tile the
    tiles-between reading would add.
    """

    prototype: str
    max_distance: int
    certain: int
    extended: int


def underground_reach(prototype: str, extract: PrototypeExtract) -> UndergroundReach:
    raw = extract.by_name(prototype).raw_field("max_distance")
    value = int(raw)
    return UndergroundReach(prototype, value, value, value + 1)


@dataclass(frozen=True)
class TunnelPair:
    """A candidate underground pairing and every reason it is not certain."""

    entrance: EntityId
    exit: EntityId
    separation: int
    conditions: tuple[str, ...]

    @property
    def certain(self) -> bool:
        return not self.conditions


def underground_pairs(
    index: SpatialIndex, roles: Mapping[EntityId, str], extract: PrototypeExtract
) -> tuple[TunnelPair, ...]:
    """Candidate tunnels for every underground entrance, nearest first.

    Every candidate within the longer reading of `max_distance` is kept. The
    nearest exit is the expected pairing; anything past a nearer same-tier
    endpoint is conditional on `UNDERGROUND_PAIRING_BEYOND`, and anything only
    the tiles-between reading admits is conditional on
    `UNDERGROUND_REACH_EXTENDED`. Dropping either would delete a link the
    evidence does not exclude.
    """
    pairs: list[TunnelPair] = []
    for entrance in index:
        if roles.get(entrance.id) != UNDERGROUND_IN or not is_supported_cardinal(entrance):
            continue
        reach = underground_reach(entrance.prototype, extract)
        origin = tile_of(entrance.position.x, entrance.position.y)
        blocked = False
        found = 0
        for distance in range(1, reach.extended + 1):
            tile = step(origin, entrance.direction, distance)
            for occupant in sorted(index.occupants(*tile), key=lambda e: e.entity_number):
                role = roles.get(occupant.id, OTHER)
                if role not in (UNDERGROUND_IN, UNDERGROUND_OUT):
                    continue
                if occupant.prototype != entrance.prototype or occupant.direction != entrance.direction:
                    continue
                if role == UNDERGROUND_OUT:
                    conditions = []
                    if distance > reach.certain:
                        conditions.append(UNDERGROUND_REACH_EXTENDED)
                    if blocked or found:
                        conditions.append(UNDERGROUND_PAIRING_BEYOND)
                    pairs.append(TunnelPair(entrance.id, occupant.id, distance, tuple(conditions)))
                    found += 1
                blocked = True
    pairs.sort(key=lambda p: (p.entrance.entity_number, p.separation, p.exit.entity_number))
    return tuple(pairs)


# ---------------------------------------------------------------------------
# Inserters
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class InserterReach:
    """An inserter's two candidate tiles and their occupants, roles unassigned.

    `documented_tile` is where the prototype's `pickup_position` lands under the
    documented rotation sense and `reversed_tile` where `insert_position` lands.
    The *roles* of the two are exactly what `inserter.endpoints.pickup_drop_tiles`
    leaves open (task 03 §4), so this record never says which is the pickup.
    """

    inserter: EntityId
    documented_tile: tuple[int, int] | None
    reversed_tile: tuple[int, int] | None
    documented_occupants: tuple[EntityId, ...]
    reversed_occupants: tuple[EntityId, ...]
    status: str
    filters: tuple[str, ...]


def inserter_reaches(
    index: SpatialIndex, roles: Mapping[EntityId, str], extract: PrototypeExtract
) -> tuple[InserterReach, ...]:
    out = []
    for entity in index:
        if roles.get(entity.id) != INSERTER:
            continue
        candidates = index.inserter_candidates(entity)
        out.append(InserterReach(
            inserter=entity.id,
            documented_tile=candidates.pickup_tile,
            reversed_tile=candidates.drop_tile,
            documented_occupants=tuple(e.id for e in candidates.pickup),
            reversed_occupants=tuple(e.id for e in candidates.drop),
            status=candidates.evidence_status,
            filters=declared_filters(entity),
        ))
    out.sort(key=lambda r: r.inserter.entity_number)
    return tuple(out)


def declared_filters(entity: SpatialEntity) -> tuple[str, ...]:
    """Item filters written into the blueprint record, if the record enables them.

    Read verbatim from the entity; never applied as a restriction here. No
    mechanics record covers inserter or splitter filtering, and a restriction
    taken from an unobserved rule could turn a satisfiable request into a false
    shortfall, so `routing.py` relaxes it and reports it instead.
    """
    record = entity.record
    names: list[str] = []
    if record.get("use_filters") or "filters" in record:
        for entry in record.get("filters") or ():
            if isinstance(entry, Mapping) and isinstance(entry.get("name"), str):
                names.append(entry["name"])
    single = record.get("filter")
    if isinstance(single, str):
        names.append(single)
    elif isinstance(single, Mapping) and isinstance(single.get("name"), str):
        names.append(single["name"])
    return tuple(dict.fromkeys(names))


def circuit_controlled(entity: SpatialEntity) -> bool:
    """Whether the record shows a circuit control that could disable this entity."""
    behavior = entity.record.get("control_behavior")
    if not isinstance(behavior, Mapping):
        return False
    return bool(
        behavior.get("circuit_enable_disable")
        or behavior.get("circuit_condition")
        or behavior.get("circuit_set_filters")
        or behavior.get("logistic_condition")
    )


# ---------------------------------------------------------------------------
# Capacity numbers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LaneCapacity:
    """A per-lane belt ceiling with the evidence status it rests on."""

    prototype: str
    items_per_second: float
    status: str
    reference: str


def lane_capacity(prototype: str, extract: PrototypeExtract) -> LaneCapacity:
    derived = extract.by_name(prototype).derived.get("items_per_second_per_lane")
    if derived is None or derived.value is None:
        raise TransportError(
            "unknown_lane_capacity",
            f"{prototype} has no recorded per-lane capacity",
            prototype=prototype,
        )
    return LaneCapacity(prototype, float(derived.value), derived.evidence_status, derived.evidence_ref)


@dataclass(frozen=True)
class Profile:
    """The mechanics profile in force: prototypes plus rule evidence statuses."""

    extract: PrototypeExtract = field(default_factory=load_pinned_extract)
    rules: Mapping[str, MechanicsRule] = field(default_factory=load_mechanics)

    def status(self, rule_id: str) -> str:
        try:
            return self.rules[rule_id].status
        except KeyError:
            raise TransportError("unknown_mechanics_rule", f"unknown rule {rule_id!r}") from None

    def semantics(self, rule_id: str) -> str:
        rule = self.rules[rule_id]
        return semantics_for("observed" if rule.observed else "pending")

    def unobserved(self, rule_ids: Iterable[str] = MECHANICS_RULES) -> tuple[str, ...]:
        """Rules in use that are not backed by a game observation."""
        return tuple(r for r in rule_ids if not self.rules[r].observed)


__all__ = [
    "BELT", "BELT_LIKE", "CARDINAL", "CONDITIONS", "Handover", "INSERTER",
    "INSERTER_ROTATION_DOCUMENTED", "INSERTER_ROTATION_REVERSED", "InserterReach",
    "LANE_OFFSET", "LANE_SIDES", "LaneCapacity", "MACHINE", "MECHANICS_RULES",
    "MechanicsRule", "OTHER", "Profile", "SIDE_LOAD_FAR_LANE", "SIDE_LOAD_NEAR_LANE",
    "SPLITTER", "TransportError", "TunnelPair", "UNDERGROUND_EXIT_REAR_FEED",
    "UNDERGROUND_IN", "UNDERGROUND_LANE_CROSSING", "UNDERGROUND_OUT",
    "UNDERGROUND_PAIRING_BEYOND", "UNDERGROUND_REACH_EXTENDED", "UndergroundReach",
    "accepts_from", "belt_handovers", "circuit_controlled", "declared_filters",
    "emission_tiles", "entity_role", "entity_roles", "evidence_kind_for", "forward",
    "half_tiles", "inserter_reaches", "is_supported_cardinal", "lane_capacity",
    "lane_offset", "load_mechanics", "opposite", "other_lane", "right_of", "rotate",
    "semantics_for", "side_of", "step", "tile_of", "underground_pairs",
    "underground_reach",
]
