"""Indexed per-entity spatial view of a preserved blueprint document.

Routing task 03. This module is the bridge between a *losslessly decoded*
blueprint (`blueprint.decode_blueprint`) and the routing wire contract
(`blueprint_contract`): it normalizes geometry per entity, indexes it so local
questions do not scan all pairs, and can emit contract `Entity` records through
the contract's own public constructors.

Deliberately **not** here, because the evidence for them does not exist yet:
belt/underground/splitter transport rules, lane connections, inserter capacity,
recipe activities, or any viewer. `inserter_candidates` answers a *geometric*
question ("which entities sit on the pickup/drop tiles") and says so; which lane
an inserter uses and how fast it swings are gated on
`daemon/factoribot/evidence/routing_mechanics_observations/` records that are still
`pending`.

Prototype geometry comes from task 02's pinned extract
(`transport_prototypes.load_pinned_extract`). No geometry is invented: a
prototype the extract does not describe keeps its position, is flagged with an
explicit limitation, and is classified `unknown` / `unsupported`.

Classification claims (contract 1.1.0 `subsystem` / `mod`):

* `subsystem` is copied from the extract's per-prototype hint.
* `mod` is `base` only for prototypes in the frozen first entity set -- the
  contract's own mechanics table names those as base prototypes, and the
  contract requires `supported` entities to be `base`. Everything else keeps
  `unknown`, because task 02's dump carries no mod manifest and an adapter may
  not assert a mod name its evidence does not support. `declared_origins` lets
  an integrator supply a real manifest later without this module guessing one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from types import MappingProxyType
from typing import Iterable, Iterator, Mapping, Sequence

from .blueprint import (
    DEFAULT_LIMITS,
    BookEntry,
    DecodeLimits,
    blueprint_leaves,
    decode_blueprint,
    encode_blueprint,
    parse_selection_path,
    select_blueprint,
)
from .blueprint_contract import (
    Box,
    Entity,
    EntityId,
    JsonDocument,
    Point,
    content_hash,
)
from .transport_prototypes import (
    FIRST_ENTITY_SET,
    PrototypeExtract,
    load_pinned_extract,
)

#: Mod name recorded when the evidence does not identify one. It is a claim of
#: ignorance, not a mod called "unknown"; a request that wants to analyse such a
#: layout must declare it explicitly (see the task 03 handoff).
UNKNOWN_MOD = "unknown"
BASE_MOD_NAME = "base"

CARDINAL_DIRECTIONS = (0, 4, 8, 12)


class SpatialError(ValueError):
    """A structured spatial-model failure (`code` is machine readable)."""

    def __init__(self, code: str, message: str, **detail):
        super().__init__(message)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class SpatialLimits:
    """Ceilings that bound index construction and query work."""

    #: Contract's provisional normalized-entity ceiling, per selected leaf.
    max_entities: int = 10_000
    #: Refuses an absurd prototype footprint before it fills the tile map.
    max_footprint_tiles: int = 4_096
    #: Refuses an unbounded region scan.
    max_query_tiles: int = 1_000_000


DEFAULT_SPATIAL_LIMITS = SpatialLimits()


# --------------------------------------------------------------------------
# Per-entity limitation codes. These stay attached to the entity so an unknown
# or unsupported thing remains visible instead of silently disappearing.
# --------------------------------------------------------------------------
UNKNOWN_PROTOTYPE = "unknown_prototype"
ASSUMED_UNIT_FOOTPRINT = "assumed_unit_footprint"
NON_CARDINAL_DIRECTION = "non_cardinal_direction"
BOUNDING_FOOTPRINT = "bounding_footprint_for_non_cardinal_direction"
NON_NORMAL_QUALITY = "non_normal_quality"
NON_TOKEN_PROTOTYPE_NAME = "non_token_prototype_name"
UNIDENTIFIED_MOD = "unidentified_mod_origin"


def _number(value, label: str, entity_number):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialError(
            "invalid_position", f"{label} must be a number", entity_number=entity_number
        )
    if not math.isfinite(value):
        raise SpatialError(
            "invalid_position", f"{label} must be finite", entity_number=entity_number
        )
    return value


@dataclass(frozen=True)
class SpatialEntity:
    """One indexed entity: normalized geometry plus its original record.

    `record` is the entity dict from the decoded document, not a rebuild from
    reduced fields, so filters, quality, tags and unknown keys survive.
    """

    id: EntityId
    prototype: str
    position: Point
    footprint: Box
    direction: int
    orientation: float | None
    quality: str
    support: str  # "supported" | "unsupported"
    subsystem: str
    mod: str
    geometry_source: str  # "prototype" | "assumed_unit_tile"
    limitations: tuple[str, ...]
    #: Excluded from equality/hash: the normalized fields above already carry
    #: identity, and a mapping is not hashable.
    record: Mapping = field(compare=False)

    @property
    def entity_number(self) -> int:
        return self.id.entity_number

    @property
    def book_path(self) -> tuple[int, ...]:
        return self.id.book_path

    @property
    def key(self) -> str:
        return self.id.key

    def tiles(self) -> tuple[tuple[int, int], ...]:
        """Tile coordinates the footprint covers, in row-major order."""
        return _box_tiles(self.footprint)

    def to_contract_entity(
        self, evidence_ids: Sequence[str] = (), furnace_candidates: Sequence[str] = ()
    ) -> Entity:
        """Emit the routing-contract record for this entity.

        Uses the contract's public constructor, so every contract invariant
        (raw/normalized agreement, supported-implies-base, cardinal directions)
        is checked there rather than restated here. Raises `ContractError` for
        an entity the contract cannot express, e.g. a prototype name that is
        not a contract name token.
        """
        return Entity(
            id=self.id,
            prototype=self.prototype,
            position=self.position,
            footprint=self.footprint,
            direction=self.direction,
            orientation=self.orientation,
            quality=self.quality,
            support=self.support,
            subsystem=self.subsystem,
            mod=self.mod,
            furnace_candidates=tuple(furnace_candidates),
            raw=JsonDocument.from_value(dict(self.record)),
            evidence_ids=tuple(evidence_ids),
        )


#: The prototype's pickup/insert offsets are stated in the entity's own north
#: frame and rotated by its direction. The rotation *sense* is not settled by
#: the extract: under the opposite convention the two tiles keep their
#: positions but exchange roles. On the pilot both conventions put a supported
#: entity on both tiles for every one of the 608 inserters, so geometry alone
#: cannot discriminate them. Consumers must treat the pair as an unordered
#: candidate pair until the observation record is `observed`.
ROTATION_SENSE_UNVALIDATED = (
    "offset rotation sense documented-only: pickup/drop roles swap under the "
    "opposite convention; treat as an unordered candidate pair until "
    "inserter.endpoints.pickup_drop_tiles is observed"
)


@dataclass(frozen=True)
class InserterCandidates:
    """Geometric pickup/drop candidates for one inserter.

    This is *candidate geometry only*: the offsets come from the prototype's
    `pickup_position` / `insert_position`, rotated by the entity direction.
    Which belt lane is served, and at what rate, needs the pending
    `inserter.endpoints.pickup_drop_tiles` and `inserter.rate.cycle_and_stack`
    observations; `limitations` repeats that.
    """

    inserter: EntityId
    pickup_position: Point | None
    drop_position: Point | None
    pickup_tile: tuple[int, int] | None
    drop_tile: tuple[int, int] | None
    pickup: tuple[SpatialEntity, ...]
    drop: tuple[SpatialEntity, ...]
    evidence_status: str
    limitations: tuple[str, ...]

    @property
    def candidate_tiles(self) -> tuple[tuple[int, int], ...]:
        """Both candidate tiles, sorted -- the role-free view of the pair."""
        return tuple(sorted(t for t in (self.pickup_tile, self.drop_tile) if t is not None))

    @property
    def candidate_entities(self) -> tuple[SpatialEntity, ...]:
        """Entities on either candidate tile, deduplicated by entity number."""
        seen = {e.entity_number: e for e in self.pickup + self.drop}
        return tuple(seen[n] for n in sorted(seen))


def _box_span(box: Box) -> tuple[int, int, int, int]:
    x0, y0 = math.floor(box.minimum.x), math.floor(box.minimum.y)
    x1, y1 = math.ceil(box.maximum.x), math.ceil(box.maximum.y)
    return x0, y0, max(x1, x0 + 1), max(y1, y0 + 1)


def _box_tile_count(box: Box) -> int:
    """Tiles a box covers, computed from its span without materializing them."""
    x0, y0, x1, y1 = _box_span(box)
    return (x1 - x0) * (y1 - y0)


def _box_tiles(box: Box) -> tuple[tuple[int, int], ...]:
    x0, y0, x1, y1 = _box_span(box)
    return tuple((x, y) for y in range(y0, y1) for x in range(x0, x1))


def rotate_offset(dx: float, dy: float, direction: int) -> tuple[float, float]:
    """Rotate a north-facing offset clockwise into `direction` (screen y down).

    Public so the transport layer can share this one definition of the rotation
    sense instead of keeping a second copy of it (task 04 handoff, shared edit 1).
    Cardinal directions only; anything else is unsupported by the first profile.
    """
    if direction == 0:
        return dx, dy
    if direction == 4:
        return -dy, dx
    if direction == 8:
        return -dx, -dy
    if direction == 12:
        return dy, -dx
    raise SpatialError("non_cardinal_direction", f"cannot rotate offset by direction {direction}")


#: Backwards-compatible private alias; `rotate_offset` is the public name.
_rotate = rotate_offset


def _footprint(position: Point, width: int, height: int, direction: int) -> tuple[Box, bool]:
    """Axis-aligned footprint of a `width` x `height` prototype at `position`.

    Returns the box and whether the rotation had to be over-approximated. A
    cardinal east/west direction swaps the tile dimensions; a non-cardinal
    direction is not supported by the first profile, so the square bounding box
    of every rotation is used -- a superset, never a smaller claim.
    """
    approximated = False
    if direction in (4, 12):
        width, height = height, width
    elif direction not in (0, 8):
        width = height = max(width, height)
        approximated = True
    half_w, half_h = width / 2, height / 2
    return (
        Box(
            Point(position.x - half_w, position.y - half_h),
            Point(position.x + half_w, position.y + half_h),
        ),
        approximated,
    )


class PrototypeGeometry:
    """Prototype geometry and classification, read from task 02's extract."""

    def __init__(
        self,
        extract: PrototypeExtract | None = None,
        declared_origins: Mapping[str, str] | None = None,
    ):
        self.extract = extract if extract is not None else load_pinned_extract()
        #: Optional prototype name -> mod name manifest supplied by an
        #: integrator that actually has one. Absent by default: this adapter
        #: never guesses a mod name.
        self.declared_origins = dict(declared_origins or {})
        self._cache: dict[str, dict] = {}

    def describe(self, prototype: str) -> dict:
        cached = self._cache.get(prototype)
        if cached is not None:
            return cached
        proto = self.extract.get(prototype)
        limitations: list[str] = []
        if proto is None:
            info = {
                "tile_width": 1,
                "tile_height": 1,
                "subsystem": "unknown",
                "support": "unsupported",
                "geometry_source": "assumed_unit_tile",
                "pickup_offset": None,
                "drop_offset": None,
                "offset_status": "pending",
                "limitations": (UNKNOWN_PROTOTYPE, ASSUMED_UNIT_FOOTPRINT),
            }
        else:
            width = proto.derived["tile_width"].value
            height = proto.derived["tile_height"].value
            pickup = proto.derived.get("pickup_offset_tiles")
            drop = proto.derived.get("drop_offset_tiles")
            # The weaker of the two offset evidence statuses; "pending" if they
            # disagree, so a half-documented pair never reads as documented.
            order = ("observed", "documented-only", "pending")
            status = "pending"
            if pickup is not None and drop is not None:
                status = max(
                    (pickup.evidence_status, drop.evidence_status), key=order.index
                )
            info = {
                "tile_width": int(width),
                "tile_height": int(height),
                "subsystem": proto.subsystem,
                "support": proto.support,
                "geometry_source": "prototype",
                "pickup_offset": None if pickup is None else (pickup.value["x"], pickup.value["y"]),
                "drop_offset": None if drop is None else (drop.value["x"], drop.value["y"]),
                "offset_status": status,
                "limitations": (),
            }
        info["mod"] = self.mod_for(prototype)
        if info["mod"] == UNKNOWN_MOD:
            limitations.append(UNIDENTIFIED_MOD)
        info["limitations"] = tuple(info["limitations"]) + tuple(limitations)
        self._cache[prototype] = info
        return info

    def mod_for(self, prototype: str) -> str:
        """The mod claim for `prototype`; see this module's docstring."""
        declared = self.declared_origins.get(prototype)
        if declared:
            return declared
        if prototype in FIRST_ENTITY_SET:
            return BASE_MOD_NAME
        return UNKNOWN_MOD


class SpatialIndex:
    """Indexed entities of ONE blueprint leaf.

    Leaves never connect implicitly, even at identical world coordinates, so
    every index covers exactly one selection path.

    Query API (the part task 04 needs):

    * `entities` / `by_id` / `by_entity_number` / `by_prototype`
    * `occupants(x, y)` -- entities covering one tile
    * `entities_in_box(box)` -- entities overlapping a region
    * `neighbors(target, distance=1, diagonal=False)` -- local ring, no all-pairs
    * `inserter_candidates(target)` / `inserter_targets()` -- geometric
      pickup/drop candidates with their evidence status
    """

    def __init__(
        self,
        path: tuple[int, ...],
        record: Mapping,
        entities: Sequence[SpatialEntity],
        limits: SpatialLimits = DEFAULT_SPATIAL_LIMITS,
        geometry: PrototypeGeometry | None = None,
    ):
        self.path = tuple(path)
        self.record = record
        self.entities: tuple[SpatialEntity, ...] = tuple(entities)
        self.limits = limits
        self.geometry = geometry
        self._by_number: dict[int, SpatialEntity] = {}
        self._by_prototype: dict[str, list[SpatialEntity]] = {}
        self._tiles: dict[tuple[int, int], list[SpatialEntity]] = {}
        for entity in self.entities:
            self._by_number[entity.entity_number] = entity
            self._by_prototype.setdefault(entity.prototype, []).append(entity)
            # Checked from the span, before the tile list is built.
            covered = _box_tile_count(entity.footprint)
            if covered > limits.max_footprint_tiles:
                raise SpatialError(
                    "footprint_limit",
                    f"entity {entity.key} covers {covered} tiles",
                    entity=entity.key,
                    tiles=covered,
                )
            for tile in entity.tiles():
                self._tiles.setdefault(tile, []).append(entity)

    # -- lookups -----------------------------------------------------------
    def __len__(self) -> int:
        return len(self.entities)

    def __iter__(self) -> Iterator[SpatialEntity]:
        return iter(self.entities)

    def by_entity_number(self, entity_number: int) -> SpatialEntity:
        found = self._by_number.get(entity_number)
        if found is None:
            raise SpatialError(
                "unknown_entity", f"no entity {entity_number} in {list(self.path)}",
                entity_number=entity_number,
            )
        return found

    def by_id(self, entity_id: EntityId) -> SpatialEntity:
        if tuple(entity_id.book_path) != self.path:
            raise SpatialError(
                "unknown_entity",
                f"{entity_id.key} is not in leaf {list(self.path)}",
                entity=entity_id.key,
            )
        return self.by_entity_number(entity_id.entity_number)

    def by_prototype(self, prototype: str) -> tuple[SpatialEntity, ...]:
        return tuple(self._by_prototype.get(prototype, ()))

    def prototype_counts(self) -> dict[str, int]:
        return {name: len(v) for name, v in sorted(self._by_prototype.items())}

    def bounding_box(self) -> Box | None:
        if not self.entities:
            return None
        xs0 = min(e.footprint.minimum.x for e in self.entities)
        ys0 = min(e.footprint.minimum.y for e in self.entities)
        xs1 = max(e.footprint.maximum.x for e in self.entities)
        ys1 = max(e.footprint.maximum.y for e in self.entities)
        return Box(Point(xs0, ys0), Point(xs1, ys1))

    # -- spatial queries ---------------------------------------------------
    def occupants(self, x: int, y: int) -> tuple[SpatialEntity, ...]:
        """Entities whose footprint covers tile `(x, y)`."""
        return tuple(self._tiles.get((int(math.floor(x)), int(math.floor(y))), ()))

    def covering(self, point: Point) -> tuple[SpatialEntity, ...]:
        return self.occupants(math.floor(point.x), math.floor(point.y))

    def _scan(self, tiles: Iterable[tuple[int, int]]) -> list[SpatialEntity]:
        seen: dict[int, SpatialEntity] = {}
        scanned = 0
        for tile in tiles:
            scanned += 1
            if scanned > self.limits.max_query_tiles:
                raise SpatialError(
                    "query_limit",
                    f"region query exceeds {self.limits.max_query_tiles} tiles",
                    limit=self.limits.max_query_tiles,
                )
            for entity in self._tiles.get(tile, ()):
                seen.setdefault(entity.entity_number, entity)
        return [seen[n] for n in sorted(seen)]

    def entities_in_box(self, box: Box) -> tuple[SpatialEntity, ...]:
        """Entities whose footprint overlaps `box`."""
        self._check_work(_box_tile_count(box))
        return tuple(self._scan(_box_tiles(box)))

    def _check_work(self, tiles: int) -> None:
        """Refuse a query before building its tile list, not after."""
        if tiles > self.limits.max_query_tiles:
            raise SpatialError(
                "query_limit",
                f"query covers {tiles} tiles, limit {self.limits.max_query_tiles}",
                limit=self.limits.max_query_tiles, tiles=tiles,
            )

    def neighbors(
        self, target, distance: int = 1, diagonal: bool = False
    ) -> tuple[SpatialEntity, ...]:
        """Entities within `distance` tiles of `target`'s footprint.

        Cost is proportional to the queried ring, not to the entity count: the
        tile map is consulted directly, so there is no all-pairs scan.
        """
        entity = self._resolve(target)
        if distance < 0:
            raise SpatialError("invalid_query", "neighbor distance must be nonnegative")
        own = set(entity.tiles())
        self._check_work(len(own) * ((2 * distance + 1) ** 2 - 1))
        ring: set[tuple[int, int]] = set()
        for (x, y) in own:
            for dx in range(-distance, distance + 1):
                for dy in range(-distance, distance + 1):
                    if dx == 0 and dy == 0:
                        continue
                    if not diagonal and dx != 0 and dy != 0:
                        continue
                    ring.add((x + dx, y + dy))
        ring -= own
        found = self._scan(sorted(ring))
        return tuple(e for e in found if e.entity_number != entity.entity_number)

    def _resolve(self, target) -> SpatialEntity:
        if isinstance(target, SpatialEntity):
            return target
        if isinstance(target, EntityId):
            return self.by_id(target)
        if isinstance(target, int) and not isinstance(target, bool):
            return self.by_entity_number(target)
        raise SpatialError("invalid_query", f"cannot resolve entity from {target!r}")

    def inserter_candidates(self, target) -> InserterCandidates:
        """Geometric pickup/drop candidates for one inserter entity."""
        entity = self._resolve(target)
        if self.geometry is None:
            raise SpatialError("no_geometry", "index was built without prototype geometry")
        info = self.geometry.describe(entity.prototype)
        if info["pickup_offset"] is None or info["drop_offset"] is None:
            raise SpatialError(
                "not_an_inserter",
                f"{entity.key} ({entity.prototype}) has no pickup/drop geometry",
                entity=entity.key, prototype=entity.prototype,
            )
        limitations = [
            "inserter.endpoints.pickup_drop_tiles: "
            + info["offset_status"]
            + " (lane choice unobserved)",
            "inserter.rate.cycle_and_stack: pending (no capacity claim)",
            ROTATION_SENSE_UNVALIDATED,
        ]
        if entity.direction not in CARDINAL_DIRECTIONS:
            return InserterCandidates(
                entity.id, None, None, None, None, (), (),
                info["offset_status"], tuple(limitations + [NON_CARDINAL_DIRECTION]),
            )
        px, py = _rotate(*info["pickup_offset"], entity.direction)
        dx, dy = _rotate(*info["drop_offset"], entity.direction)
        pickup = Point(entity.position.x + px, entity.position.y + py)
        drop = Point(entity.position.x + dx, entity.position.y + dy)
        pickup_tile = (math.floor(pickup.x), math.floor(pickup.y))
        drop_tile = (math.floor(drop.x), math.floor(drop.y))
        return InserterCandidates(
            inserter=entity.id,
            pickup_position=pickup,
            drop_position=drop,
            pickup_tile=pickup_tile,
            drop_tile=drop_tile,
            pickup=tuple(e for e in self.occupants(*pickup_tile) if e.entity_number != entity.entity_number),
            drop=tuple(e for e in self.occupants(*drop_tile) if e.entity_number != entity.entity_number),
            evidence_status=info["offset_status"],
            limitations=tuple(limitations),
        )

    def inserter_targets(self) -> tuple[InserterCandidates, ...]:
        """Candidates for every inserter-subsystem entity of this leaf."""
        return tuple(
            self.inserter_candidates(e) for e in self.entities if e.subsystem == "inserter"
        )

    def contract_entities(self) -> tuple[Entity, ...]:
        return tuple(e.to_contract_entity() for e in self.entities)


@dataclass(frozen=True)
class SpatialView:
    """The preserved document plus one `SpatialIndex` per selected leaf."""

    document: Mapping
    selected_paths: tuple[tuple[int, ...], ...]
    indexes: Mapping[tuple[int, ...], SpatialIndex]
    unselected_paths: tuple[tuple[int, ...], ...]
    limitations: tuple[str, ...] = ()

    def index(self, path=()) -> SpatialIndex:
        wanted = parse_selection_path(path)
        found = self.indexes.get(wanted)
        if found is None:
            raise SpatialError(
                "unknown_selection_path",
                f"leaf {list(wanted)} is not selected",
                path=list(wanted),
                selected=[list(p) for p in self.selected_paths],
            )
        return found

    def entities(self) -> tuple[SpatialEntity, ...]:
        out: list[SpatialEntity] = []
        for path in self.selected_paths:
            out.extend(self.indexes[path].entities)
        return tuple(out)

    def contract_entities(self) -> tuple[Entity, ...]:
        return tuple(e.to_contract_entity() for e in self.entities())

    def blueprint_hash(self) -> str:
        """`content_hash` of the whole preserved source document."""
        return content_hash(self.document)

    def encode(self) -> str:
        return encode_blueprint(dict(self.document))


def normalize_entity(
    record: Mapping,
    path: tuple[int, ...],
    geometry: PrototypeGeometry,
) -> SpatialEntity:
    """Normalize one raw entity record into an indexed `SpatialEntity`."""
    if not isinstance(record, dict):
        raise SpatialError("invalid_entity", "entity record must be an object")
    number = record.get("entity_number")
    if type(number) is not int or number <= 0:
        raise SpatialError(
            "invalid_entity_number",
            f"entity_number must be a positive integer, got {number!r}",
            entity_number=number,
        )
    name = record.get("name")
    if not isinstance(name, str) or not name:
        raise SpatialError(
            "invalid_entity", f"entity {number} has no prototype name", entity_number=number
        )
    position = record.get("position")
    if not isinstance(position, dict) or "x" not in position or "y" not in position:
        raise SpatialError(
            "invalid_position", f"entity {number} has no position", entity_number=number
        )
    x = _number(position["x"], "position.x", number)
    y = _number(position["y"], "position.y", number)
    direction = record.get("direction", 0)
    if type(direction) is not int or not 0 <= direction <= 15:
        raise SpatialError(
            "invalid_direction",
            f"entity {number} direction must be an integer in 0..15, got {direction!r}",
            entity_number=number, direction=direction,
        )
    orientation = record.get("orientation")
    if orientation is not None:
        orientation = _number(orientation, "orientation", number)
        if not 0 <= orientation < 1:
            raise SpatialError(
                "invalid_orientation",
                f"entity {number} orientation must lie in [0,1)",
                entity_number=number,
            )
    quality = record.get("quality", "normal")
    if not isinstance(quality, str) or not quality:
        raise SpatialError(
            "invalid_quality", f"entity {number} has an empty quality", entity_number=number
        )

    info = geometry.describe(name)
    limitations = list(info["limitations"])
    footprint, approximated = _footprint(
        Point(x, y), info["tile_width"], info["tile_height"], direction
    )
    support = info["support"]
    if direction not in CARDINAL_DIRECTIONS:
        support = "unsupported"
        limitations.append(NON_CARDINAL_DIRECTION)
        if approximated:
            limitations.append(BOUNDING_FOOTPRINT)
    if quality != "normal":
        support = "unsupported"
        limitations.append(NON_NORMAL_QUALITY)
    mod = info["mod"]
    if support == "supported" and mod != BASE_MOD_NAME:
        # The contract forbids a supported non-base prototype; an unidentified
        # origin downgrades support rather than inventing a mod name.
        support = "unsupported"
    if not _is_token(name):
        limitations.append(NON_TOKEN_PROTOTYPE_NAME)
        support = "unsupported"
    return SpatialEntity(
        id=EntityId(tuple(path), number),
        prototype=name,
        position=Point(x, y),
        footprint=footprint,
        direction=direction,
        orientation=orientation,
        quality=quality,
        support=support,
        subsystem=info["subsystem"],
        mod=mod,
        geometry_source=info["geometry_source"],
        limitations=tuple(dict.fromkeys(limitations)),
        record=MappingProxyType(record),
    )


def _is_token(name: str) -> bool:
    """Whether the contract's `token()` would accept this prototype name."""
    return re.fullmatch(r"[a-z][a-z0-9_-]*", name) is not None


def index_blueprint(
    record: Mapping,
    path: tuple[int, ...] = (),
    geometry: PrototypeGeometry | None = None,
    limits: SpatialLimits = DEFAULT_SPATIAL_LIMITS,
) -> SpatialIndex:
    """Build the spatial index for one blueprint leaf record."""
    geometry = geometry if geometry is not None else PrototypeGeometry()
    entities_raw = record.get("entities") or []
    if not isinstance(entities_raw, list):
        raise SpatialError("invalid_entity", "blueprint 'entities' must be an array")
    if len(entities_raw) > limits.max_entities:
        raise SpatialError(
            "entity_limit",
            f"blueprint at {list(path)} has {len(entities_raw)} entities, limit {limits.max_entities}",
            path=list(path), count=len(entities_raw), limit=limits.max_entities,
        )
    seen: set[int] = set()
    entities: list[SpatialEntity] = []
    for raw in entities_raw:
        entity = normalize_entity(raw, path, geometry)
        if entity.entity_number in seen:
            raise SpatialError(
                "duplicate_entity_id",
                f"entity_number {entity.entity_number} appears twice in {list(path)}",
                path=list(path), entity_number=entity.entity_number,
            )
        seen.add(entity.entity_number)
        entities.append(entity)
    return SpatialIndex(path, record, entities, limits, geometry)


def build_spatial_view(
    document: Mapping,
    paths: Sequence | None = None,
    geometry: PrototypeGeometry | None = None,
    limits: SpatialLimits = DEFAULT_SPATIAL_LIMITS,
    decode_limits: DecodeLimits = DEFAULT_LIMITS,
) -> SpatialView:
    """Index the selected leaves of an already decoded document.

    `paths` is an explicit list of selection paths (book entry index values);
    `None` selects every blueprint leaf. Unselected entries stay listed in
    `unselected_paths` and the document itself is retained untouched.
    """
    document = dict(document) if not isinstance(document, dict) else document
    geometry = geometry if geometry is not None else PrototypeGeometry()
    leaves: list[BookEntry] = blueprint_leaves(document, decode_limits)
    available = {leaf.path: leaf for leaf in leaves}
    if paths is None:
        selected = tuple(leaf.path for leaf in leaves)
    else:
        selected = tuple(dict.fromkeys(parse_selection_path(p) for p in paths))
    indexes: dict[tuple[int, ...], SpatialIndex] = {}
    for path in selected:
        leaf = available.get(path)
        if leaf is None:
            select_blueprint(document, path, decode_limits)  # raises the structured error
        indexes[path] = index_blueprint(leaf.record, path, geometry, limits)
    limitations: list[str] = []
    unselected = tuple(p for p in available if p not in indexes)
    if unselected:
        limitations.append(
            "unselected blueprint leaves retained but not indexed: "
            + ", ".join("/".join(map(str, p)) or "root" for p in unselected)
        )
    flagged = {code: sorted({e.prototype for idx in indexes.values()
                             for e in idx.entities if code in e.limitations})
               for code in (UNKNOWN_PROTOTYPE, UNIDENTIFIED_MOD)}
    unknown = flagged[UNKNOWN_PROTOTYPE]
    if unknown:
        limitations.append(
            "no prototype geometry for: " + ", ".join(unknown)
            + " (unit-tile footprint assumed; classified unknown/unsupported)"
        )
    unidentified = flagged[UNIDENTIFIED_MOD]
    if unidentified:
        limitations.append(
            "mod origin unidentified for: " + ", ".join(unidentified)
            + " (recorded as mod 'unknown'; the prototype extract carries no mod manifest)"
        )
    return SpatialView(
        document=document,
        selected_paths=selected,
        indexes=indexes,
        unselected_paths=unselected,
        limitations=tuple(limitations),
    )


def load_spatial_view(
    text: str,
    paths: Sequence | None = None,
    geometry: PrototypeGeometry | None = None,
    limits: SpatialLimits = DEFAULT_SPATIAL_LIMITS,
    decode_limits: DecodeLimits = DEFAULT_LIMITS,
) -> SpatialView:
    """Decode a blueprint string (or raw JSON) and index its selected leaves."""
    document = decode_blueprint(text, decode_limits)
    return build_spatial_view(document, paths, geometry, limits, decode_limits)
