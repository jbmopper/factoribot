"""Versioned transport prototype extracts and mechanics-evidence records (task 02).

This module is the prototype adapter for blueprint routing. It answers one
question only: *what do the exported Factorio prototypes actually say* about the
entities in the routing contract's first entity set, and *what is not said*.

Three rules shape everything here:

1. Raw prototype fields are copied verbatim and are never invented. A field the
   dump does not define is listed in ``absent_raw_fields``; it does not silently
   acquire the documented default.
2. Every value that is not a raw field is a :class:`Derived` record carrying the
   basis of the derivation, an evidence status and an evidence reference. A
   derived value whose engine semantics are not established is ``None`` with
   status ``pending`` -- never a plausible guess.
3. Provenance is explicit. A dump carries no build number and no mod manifest,
   so ``game_version`` and ``declared_mods`` stay unknown unless a caller can
   supply them from outside the dump. The blueprint format version does not
   identify the prototype environment.

The pinned fixtures under ``daemon/tests/fixtures/routing_prototypes/`` let the
downstream spatial/transport/LP tasks run offline, without the 14 MB dump.
Mechanics evidence records live in
``daemon/tests/fixtures/routing_mechanics_observations/``; a rule with no
recorded game observation is an unmet gate, not a passing default.

Nothing in this module implements belt, splitter, inserter or power mechanics.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .blueprint_contract import canonical_json, content_hash
from .gamedata import BELT_ITEMS_PER_SPEED

# --------------------------------------------------------------------------
# Versions and vocabularies
# --------------------------------------------------------------------------

#: Wire format of the prototype extract produced by this module.
PROTOTYPE_SCHEMA_VERSION = "factoribot-routing-prototypes-1"

#: Wire format of a mechanics observation record.
OBSERVATION_SCHEMA_VERSION = "factoribot-mechanics-observation-1"

#: The routing contract's first mechanics profile. Pinned as a literal so a
#: contract revision cannot silently change an extract's content hash; a rename
#: must be coordinated and the fixtures re-pinned.
TARGET_MECHANICS_PROFILE = "base-2.0.76-normal-v1"

#: Evidence status of a derived value or of a mechanics rule.
#: ``observed``       -- recorded from a controlled game capture.
#: ``documented-only``-- primary documentation only; no game observation yet.
#: ``pending``        -- neither; the semantics are not established here.
EVIDENCE_STATUSES = ("observed", "documented-only", "pending")

#: Per-entity subsystem hints for the contract's per-entity classification.
SUBSYSTEMS = (
    "transport", "inserter", "production", "power", "rail",
    "fluid", "logistics", "circuit", "unknown",
)

#: Support of a prototype under the first transport profile. ``supported``
#: means the prototype is in the frozen first entity set; everything else is
#: ``unsupported`` and may only appear as visible, non-operating topology.
SUPPORT_LEVELS = ("supported", "unsupported")

#: The frozen first entity set (routing contract mechanics table).
FIRST_ENTITY_SET = (
    "transport-belt", "fast-transport-belt", "express-transport-belt",
    "underground-belt", "fast-underground-belt", "express-underground-belt",
    "splitter", "fast-splitter", "express-splitter",
    "inserter", "fast-inserter", "bulk-inserter",
    "assembling-machine-2", "electric-furnace",
)

#: Prototypes outside the first entity set that are retained anyway, so later
#: power/beacon/pole adapters do not need a second extraction pass. They are
#: recorded as ``unsupported``; no mechanics are implied.
RETAINED_UNSUPPORTED = (
    "small-electric-pole", "medium-electric-pole", "big-electric-pole",
    "substation", "ee-super-substation", "beacon",
)

_SUBSYSTEM_BY_PROTOTYPE_TYPE: Mapping[str, str] = {
    # transport
    "transport-belt": "transport", "underground-belt": "transport",
    "splitter": "transport", "lane-splitter": "transport",
    "loader": "transport", "loader-1x1": "transport", "loader-1x2": "transport",
    "linked-belt": "transport",
    # inserter
    "inserter": "inserter",
    # production
    "assembling-machine": "production", "furnace": "production",
    "rocket-silo": "production", "mining-drill": "production", "lab": "production",
    # power
    "electric-pole": "power", "power-switch": "power", "solar-panel": "power",
    "accumulator": "power", "generator": "power", "burner-generator": "power",
    "boiler": "power", "reactor": "power", "heat-pipe": "power",
    "heat-interface": "power", "electric-energy-interface": "power",
    "beacon": "power", "fusion-reactor": "power", "fusion-generator": "power",
    # rail
    "straight-rail": "rail", "curved-rail-a": "rail", "curved-rail-b": "rail",
    "half-diagonal-rail": "rail", "rail-ramp": "rail", "rail-support": "rail",
    "rail-signal": "rail", "rail-chain-signal": "rail", "train-stop": "rail",
    "locomotive": "rail", "cargo-wagon": "rail", "fluid-wagon": "rail",
    "artillery-wagon": "rail", "infinity-cargo-wagon": "rail",
    # fluid
    "pipe": "fluid", "pipe-to-ground": "fluid", "infinity-pipe": "fluid",
    "storage-tank": "fluid", "pump": "fluid", "offshore-pump": "fluid",
    "valve": "fluid",
    # logistics
    "container": "logistics", "logistic-container": "logistics",
    "infinity-container": "logistics", "linked-container": "logistics",
    "proxy-container": "logistics", "roboport": "logistics",
    "logistic-robot": "logistics", "construction-robot": "logistics",
    "car": "logistics", "spider-vehicle": "logistics",
    "cargo-landing-pad": "logistics",
    # circuit
    "arithmetic-combinator": "circuit", "decider-combinator": "circuit",
    "selector-combinator": "circuit", "constant-combinator": "circuit",
    "programmable-speaker": "circuit", "display-panel": "circuit",
    "lamp": "circuit",
}


def subsystem_for(prototype_type: str) -> str:
    """Subsystem hint for a raw prototype ``type``.

    Unmapped types are ``unknown``; the caller must not treat that as a claim
    about the entity's behaviour.
    """
    if not isinstance(prototype_type, str) or not prototype_type:
        raise PrototypeError("prototype type must be a non-empty string")
    return _SUBSYSTEM_BY_PROTOTYPE_TYPE.get(prototype_type, "unknown")


class PrototypeError(ValueError):
    """Invalid prototype extract, manifest, or mechanics observation record."""


# --------------------------------------------------------------------------
# Fixture locations (adapter API for tasks 03/04/05)
# --------------------------------------------------------------------------

_TESTS_ROOT = Path(__file__).resolve().parents[1] / "tests"
PROTOTYPE_FIXTURE_DIR = _TESTS_ROOT / "fixtures" / "routing_prototypes"
OBSERVATION_FIXTURE_DIR = _TESTS_ROOT / "fixtures" / "routing_mechanics_observations"
RAW_SLICE_PATH = PROTOTYPE_FIXTURE_DIR / "raw_prototype_slice.json"
EXTRACT_PATH = PROTOTYPE_FIXTURE_DIR / "prototypes.json"
MANIFEST_PATH = PROTOTYPE_FIXTURE_DIR / "manifest.json"
PILOT_COVERAGE_PATH = PROTOTYPE_FIXTURE_DIR / "pilot_coverage.json"
OBSERVATION_INDEX_PATH = OBSERVATION_FIXTURE_DIR / "manifest.json"
OBSERVATION_RECORD_DIR = OBSERVATION_FIXTURE_DIR / "records"


# --------------------------------------------------------------------------
# Which raw fields are read, per prototype kind
# --------------------------------------------------------------------------

_COMMON_FIELDS = (
    "collision_box", "selection_box", "tile_width", "tile_height",
    "next_upgrade", "fast_replaceable_group",
)
_CIRCUIT = ("circuit_wire_max_distance",)
# Each list names only properties the 2.0.76 prototype documentation defines for
# that prototype type, so an entry in ``absent_raw_fields`` always means "this
# build's prototype leaves a real, documented field undefined".
_FIELDS_BY_TYPE: Mapping[str, tuple[str, ...]] = {
    "transport-belt": _COMMON_FIELDS + _CIRCUIT + ("speed", "related_underground_belt"),
    "underground-belt": _COMMON_FIELDS + ("speed", "max_distance"),
    "splitter": _COMMON_FIELDS + _CIRCUIT + (
        "speed", "related_transport_belt",
        "structure_animation_movement_cooldown",
        "default_input_left_condition", "default_input_right_condition",
        "default_output_left_condition", "default_output_right_condition",
    ),
    "inserter": _COMMON_FIELDS + _CIRCUIT + (
        "pickup_position", "insert_position", "extension_speed", "rotation_speed",
        "bulk", "starting_distance", "filter_count", "hand_size",
        "chases_belt_items", "stack_size_bonus", "uses_inserter_stack_size_bonus",
        "grab_less_to_match_belt_stack", "wait_for_full_hand", "max_belt_stack_size",
        "energy_per_movement", "energy_per_rotation", "energy_source",
        "default_stack_control_input_signal",
    ),
    "assembling-machine": _COMMON_FIELDS + _CIRCUIT + (
        "crafting_categories", "crafting_speed", "energy_usage", "energy_source",
        "module_slots", "allowed_effects", "effect_receiver", "ingredient_count",
        "fluid_boxes_off_when_no_fluid_recipe",
    ),
    "furnace": _COMMON_FIELDS + _CIRCUIT + (
        "crafting_categories", "crafting_speed", "energy_usage", "energy_source",
        "module_slots", "allowed_effects", "effect_receiver",
        "result_inventory_size", "source_inventory_size",
    ),
    "electric-pole": _COMMON_FIELDS + (
        "supply_area_distance", "maximum_wire_distance",
    ),
    "beacon": _COMMON_FIELDS + (
        "supply_area_distance", "distribution_effectivity",
        "distribution_effectivity_bonus_per_quality_level", "module_slots",
        "profile", "allowed_effects", "energy_usage", "energy_source",
    ),
}

#: Raw fields deliberately not copied into the extract, with the reason. They
#: remain in the source dump; the extract records only that they were dropped.
_OMITTED_FIELD_REASONS: Mapping[str, str] = {
    "fluid_boxes": "large structured field; summarised as fluid_box_production_types",
}

# Evidence reference ids an extract must declare. A restatement of a raw field
# cites the dump; a claim about engine behaviour cites the document that makes it.
REF_DUMP = "source:data-raw-dump"
REF_ENTITY_DOCS = "doc:lua-api-2.0.76-entity-prototype"
REF_BELT_DOCS = "doc:lua-api-2.0.76-transport-belt-connectable"
REF_UNDERGROUND_DOCS = "doc:lua-api-2.0.76-underground-belt-prototype"
REF_SPLITTER_DOCS = "doc:lua-api-2.0.76-splitter-prototype"
REF_INSERTER_DOCS = "doc:lua-api-2.0.76-inserter-prototype"
REF_WIKI_LANES = "wiki:transport-belts-physics"

REQUIRED_REFERENCE_IDS = (
    REF_DUMP, REF_ENTITY_DOCS, REF_BELT_DOCS, REF_UNDERGROUND_DOCS,
    REF_SPLITTER_DOCS, REF_INSERTER_DOCS, REF_WIKI_LANES,
)


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------

def _check_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise PrototypeError(f"{label} must be a non-empty string")
    return value


def _check_choice(value: Any, allowed: Sequence[str], label: str) -> str:
    if value not in allowed:
        raise PrototypeError(f"{label} must be one of {list(allowed)}, got {value!r}")
    return value


def _check_keys(value: Any, required: Sequence[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PrototypeError(f"{label} must be an object")
    missing = [k for k in required if k not in value]
    unknown = [k for k in value if k not in required]
    if missing:
        raise PrototypeError(f"{label} is missing keys: {sorted(missing)}")
    if unknown:
        raise PrototypeError(f"{label} has unknown keys: {sorted(unknown)}")
    return value


@dataclass(frozen=True)
class Box:
    """An axis-aligned box in tiles; x east, y south (entity-relative here)."""

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @classmethod
    def from_raw(cls, value: Any) -> "Box":
        """Read Factorio's ``[[x1, y1], [x2, y2]]`` bounding box form."""
        try:
            (x1, y1), (x2, y2) = value
            box = cls(float(x1), float(y1), float(x2), float(y2))
        except Exception as exc:  # noqa: BLE001 - explicit failure, no guessing
            raise PrototypeError(f"unreadable bounding box: {value!r}") from exc
        if not (box.width > 0 and box.height > 0):
            raise PrototypeError(f"bounding box has non-positive area: {value!r}")
        return box

    def to_dict(self) -> dict:
        return {"min_x": self.min_x, "min_y": self.min_y,
                "max_x": self.max_x, "max_y": self.max_y}


@dataclass(frozen=True)
class Derived:
    """A value this adapter computed, with its basis and evidence status.

    ``value is None`` means the engine semantics are not established here. It is
    an explicit unknown, never a default.
    """

    value: Any
    unit: str
    basis: str
    evidence_status: str
    evidence_ref: str

    def __post_init__(self) -> None:
        _check_str(self.unit, "derived.unit")
        _check_str(self.basis, "derived.basis")
        _check_choice(self.evidence_status, EVIDENCE_STATUSES, "derived.evidence_status")
        _check_str(self.evidence_ref, "derived.evidence_ref")
        if isinstance(self.value, float) and (math.isnan(self.value) or math.isinf(self.value)):
            raise PrototypeError("derived value must be finite")
        if self.value is None and self.evidence_status == "observed":
            raise PrototypeError("an observed derived value cannot be null")

    def to_dict(self) -> dict:
        return {"value": self.value, "unit": self.unit, "basis": self.basis,
                "evidence_status": self.evidence_status,
                "evidence_ref": self.evidence_ref}

    @classmethod
    def from_dict(cls, value: Any) -> "Derived":
        _check_keys(value, ("value", "unit", "basis", "evidence_status", "evidence_ref"),
                    "derived record")
        return cls(value["value"], value["unit"], value["basis"],
                   value["evidence_status"], value["evidence_ref"])


@dataclass(frozen=True)
class Reference:
    """A primary source actually consulted, pinned to a version where possible."""

    ref_id: str
    kind: str  # "prototype-docs" | "wiki" | "repository"
    title: str
    locator: str          # URL or repository-relative path
    version: str | None   # documented game version, or None when the source states none
    retrieved: str | None  # ISO date for fetched sources, None for repository files

    def __post_init__(self) -> None:
        _check_str(self.ref_id, "reference.ref_id")
        _check_choice(self.kind, ("prototype-docs", "wiki", "repository"), "reference.kind")
        _check_str(self.title, "reference.title")
        _check_str(self.locator, "reference.locator")

    def to_dict(self) -> dict:
        return {"ref_id": self.ref_id, "kind": self.kind, "title": self.title,
                "locator": self.locator, "version": self.version,
                "retrieved": self.retrieved}

    @classmethod
    def from_dict(cls, value: Any) -> "Reference":
        _check_keys(value, ("ref_id", "kind", "title", "locator", "version", "retrieved"),
                    "reference")
        return cls(value["ref_id"], value["kind"], value["title"], value["locator"],
                   value["version"], value["retrieved"])


@dataclass(frozen=True)
class Provenance:
    """Where an extract came from, and what about that source is unknown.

    ``source_dump_sha256`` is the SHA-256 of the dump file's bytes -- the same
    identity ``mcp_server.load_toolbox`` records for the loaded game data. The
    ``sha256:``-prefixed content hashes elsewhere in this module are canonical
    JSON hashes of decoded documents (the routing contract's convention); the
    two are deliberately named apart because they hash different things.
    """

    schema_version: str
    target_mechanics_profile: str
    game_version: str | None
    declared_mods: tuple[tuple[str, str], ...] | None  # (name, version) pairs
    environment_status: str  # "identified" | "unidentified"
    matches_target_profile: str  # "yes" | "no" | "unknown"
    source_kind: str  # "full-dump" | "pinned-slice"
    source_dump_path: str | None
    source_dump_sha256: str | None
    source_slice_content_hash: str | None
    references: tuple[Reference, ...]
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        _check_str(self.schema_version, "provenance.schema_version")
        _check_str(self.target_mechanics_profile, "provenance.target_mechanics_profile")
        _check_choice(self.environment_status, ("identified", "unidentified"),
                      "provenance.environment_status")
        _check_choice(self.matches_target_profile, ("yes", "no", "unknown"),
                      "provenance.matches_target_profile")
        _check_choice(self.source_kind, ("full-dump", "pinned-slice"),
                      "provenance.source_kind")
        if self.matches_target_profile != "unknown" and (
            self.game_version is None or self.declared_mods is None
        ):
            raise PrototypeError(
                "a profile match claim requires a known game version and an explicit "
                "declared mod list; a dump alone does not identify either"
            )
        if self.environment_status == "identified" and (
            self.game_version is None or self.declared_mods is None
        ):
            raise PrototypeError(
                "environment_status 'identified' requires game_version and declared_mods"
            )
        ids = [r.ref_id for r in self.references]
        if len(ids) != len(set(ids)):
            raise PrototypeError("duplicate reference ids in provenance")

    @property
    def reference_ids(self) -> frozenset[str]:
        return frozenset(r.ref_id for r in self.references)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "target_mechanics_profile": self.target_mechanics_profile,
            "game_version": self.game_version,
            "declared_mods": (None if self.declared_mods is None
                              else [list(m) for m in self.declared_mods]),
            "environment_status": self.environment_status,
            "matches_target_profile": self.matches_target_profile,
            "source_kind": self.source_kind,
            "source_dump_path": self.source_dump_path,
            "source_dump_sha256": self.source_dump_sha256,
            "source_slice_content_hash": self.source_slice_content_hash,
            "references": [r.to_dict() for r in self.references],
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "Provenance":
        _check_keys(value, (
            "schema_version", "target_mechanics_profile", "game_version",
            "declared_mods", "environment_status", "matches_target_profile",
            "source_kind", "source_dump_path", "source_dump_sha256",
            "source_slice_content_hash", "references", "notes"), "provenance")
        mods = value["declared_mods"]
        if mods is not None:
            mods = tuple(tuple(str(x) for x in pair) for pair in mods)
        return cls(
            value["schema_version"], value["target_mechanics_profile"],
            value["game_version"], mods, value["environment_status"],
            value["matches_target_profile"], value["source_kind"],
            value["source_dump_path"], value["source_dump_sha256"],
            value["source_slice_content_hash"],
            tuple(Reference.from_dict(r) for r in value["references"]),
            tuple(value["notes"]),
        )


@dataclass(frozen=True)
class Prototype:
    """One normalized prototype: raw fields, absences, and labelled derivations."""

    name: str
    prototype_type: str
    subsystem: str
    in_first_entity_set: bool
    support: str
    origin: str  # "unknown" -- no dump carries a per-prototype mod manifest
    raw: Mapping[str, Any]
    absent_raw_fields: tuple[str, ...]
    omitted_raw_fields: tuple[tuple[str, str], ...]  # (field, reason)
    derived: Mapping[str, Derived]
    unknown_mechanics: tuple[str, ...]

    def __post_init__(self) -> None:
        _check_str(self.name, "prototype.name")
        _check_str(self.prototype_type, "prototype.prototype_type")
        _check_choice(self.subsystem, SUBSYSTEMS, "prototype.subsystem")
        _check_choice(self.support, SUPPORT_LEVELS, "prototype.support")
        _check_str(self.origin, "prototype.origin")
        if self.support == "supported" and not self.in_first_entity_set:
            raise PrototypeError(
                f"{self.name}: only the frozen first entity set may be 'supported'")
        if not isinstance(self.raw, dict):
            raise PrototypeError("prototype.raw must be an object")
        overlap = set(self.raw) & set(self.absent_raw_fields)
        if overlap:
            raise PrototypeError(
                f"{self.name}: fields both present and absent: {sorted(overlap)}")

    def raw_field(self, name: str) -> Any:
        """Raw field value, or raise if the dump does not define it."""
        if name in self.raw:
            return self.raw[name]
        raise PrototypeError(
            f"{self.name}: raw field {name!r} is not defined by the source; it is "
            f"recorded as absent and must not be defaulted here")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "prototype_type": self.prototype_type,
            "subsystem": self.subsystem,
            "in_first_entity_set": self.in_first_entity_set,
            "support": self.support,
            "origin": self.origin,
            "raw": dict(self.raw),
            "absent_raw_fields": list(self.absent_raw_fields),
            "omitted_raw_fields": [list(p) for p in self.omitted_raw_fields],
            "derived": {k: v.to_dict() for k, v in self.derived.items()},
            "unknown_mechanics": list(self.unknown_mechanics),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "Prototype":
        _check_keys(value, (
            "name", "prototype_type", "subsystem", "in_first_entity_set", "support",
            "origin", "raw", "absent_raw_fields", "omitted_raw_fields", "derived",
            "unknown_mechanics"), "prototype")
        return cls(
            value["name"], value["prototype_type"], value["subsystem"],
            bool(value["in_first_entity_set"]), value["support"], value["origin"],
            dict(value["raw"]), tuple(value["absent_raw_fields"]),
            tuple((p[0], p[1]) for p in value["omitted_raw_fields"]),
            {k: Derived.from_dict(v) for k, v in value["derived"].items()},
            tuple(value["unknown_mechanics"]),
        )


@dataclass(frozen=True)
class PrototypeExtract:
    """A versioned, self-contained prototype extract."""

    schema_version: str
    provenance: Provenance
    prototypes: tuple[Prototype, ...]
    missing_from_first_entity_set: tuple[str, ...]

    def __post_init__(self) -> None:
        names = [p.name for p in self.prototypes]
        if len(names) != len(set(names)):
            raise PrototypeError("duplicate prototype names in extract")
        known_refs = self.provenance.reference_ids | set(REQUIRED_MECHANICS_RULES)
        for proto in self.prototypes:
            for key, derived in proto.derived.items():
                if derived.evidence_ref not in known_refs:
                    raise PrototypeError(
                        f"{proto.name}.{key}: evidence_ref {derived.evidence_ref!r} is "
                        f"neither a declared reference nor a mechanics rule id")

    def by_name(self, name: str) -> Prototype:
        for proto in self.prototypes:
            if proto.name == name:
                return proto
        raise PrototypeError(f"prototype {name!r} is not in this extract")

    def get(self, name: str) -> Prototype | None:
        try:
            return self.by_name(name)
        except PrototypeError:
            return None

    def supported_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.prototypes if p.support == "supported")

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "provenance": self.provenance.to_dict(),
            "prototypes": [p.to_dict() for p in self.prototypes],
            "missing_from_first_entity_set": list(self.missing_from_first_entity_set),
        }

    def content_hash(self) -> str:
        return content_hash(self.to_dict())


def parse_extract(value: Any) -> PrototypeExtract:
    """Strictly parse an extract document. Unknown keys and options fail."""
    _check_keys(value, ("schema_version", "provenance", "prototypes",
                        "missing_from_first_entity_set"), "extract")
    if value["schema_version"] != PROTOTYPE_SCHEMA_VERSION:
        raise PrototypeError(
            f"unsupported extract schema {value['schema_version']!r}; "
            f"this build reads {PROTOTYPE_SCHEMA_VERSION!r}")
    return PrototypeExtract(
        value["schema_version"], Provenance.from_dict(value["provenance"]),
        tuple(Prototype.from_dict(p) for p in value["prototypes"]),
        tuple(value["missing_from_first_entity_set"]),
    )


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

#: The sources actually consulted for this extract. Version-pinned prototype
#: documentation where it exists; wiki pages carry whatever version they state,
#: and ``version: null`` means the page states none -- weaker evidence, which is
#: why the mechanics rules that depend on it stay ``pending``.
DEFAULT_REFERENCES: tuple["Reference", ...] = (
    Reference(
        REF_DUMP, "repository", "Local Factorio data-raw dump used for this extract",
        "data/data-raw-dump.json", None, None),
    Reference(
        REF_ENTITY_DOCS, "prototype-docs", "EntityPrototype",
        "https://lua-api.factorio.com/2.0.76/prototypes/EntityPrototype.html",
        "2.0.76", "2026-09-08"),
    Reference(
        REF_BELT_DOCS, "prototype-docs", "TransportBeltConnectablePrototype",
        "https://lua-api.factorio.com/2.0.76/prototypes/"
        "TransportBeltConnectablePrototype.html", "2.0.76", "2026-09-08"),
    Reference(
        REF_UNDERGROUND_DOCS, "prototype-docs", "UndergroundBeltPrototype",
        "https://lua-api.factorio.com/2.0.76/prototypes/UndergroundBeltPrototype.html",
        "2.0.76", "2026-09-08"),
    Reference(
        REF_SPLITTER_DOCS, "prototype-docs", "SplitterPrototype",
        "https://lua-api.factorio.com/2.0.76/prototypes/SplitterPrototype.html",
        "2.0.76", "2026-09-08"),
    Reference(
        REF_INSERTER_DOCS, "prototype-docs", "InserterPrototype",
        "https://lua-api.factorio.com/2.0.76/prototypes/InserterPrototype.html",
        "2.0.76", "2026-09-08"),
    Reference(
        REF_WIKI_LANES, "wiki", "Transport belts/Physics (official Factorio wiki)",
        "https://wiki.factorio.com/Transport_belts/Physics", None, "2026-09-08"),
    Reference(
        "wiki:underground-belt", "wiki", "Underground belt (official Factorio wiki)",
        "https://wiki.factorio.com/Underground_belt", None, "2026-09-08"),
    Reference(
        "wiki:inserters", "wiki", "Inserters (official Factorio wiki)",
        "https://wiki.factorio.com/Inserters",
        "states its data is valid up to 2.0.77", "2026-09-08"),
    Reference(
        "repo:blueprint-routing-contract", "repository",
        "Blueprint routing contract (task 00)",
        "docs/blueprint-routing-contract.md", "1.1.0", None),
)


def _tile_dims(box: Box) -> tuple[int, int]:
    """Tile footprint from a collision box.

    ``tile_width``/``tile_height`` default to the collision box dimensions
    rounded up (prototype documentation 2.0.76). The 1e-9 guard keeps binary
    floating point from rounding an exact integer width up a tile.
    """
    return (int(math.ceil(box.width - 1e-9)), int(math.ceil(box.height - 1e-9)))


def _belt_derived(speed: float) -> dict[str, Derived]:
    total = float(speed) * BELT_ITEMS_PER_SPEED
    return {
        "tiles_per_tick": Derived(
            float(speed), "tiles/tick", "raw prototype 'speed' restated with its unit",
            "documented-only", REF_DUMP),
        "items_per_second_total": Derived(
            total, "items/s",
            "speed * 480, the documented belt speed formula (both lanes)",
            "documented-only", REF_BELT_DOCS),
        "items_per_second_per_lane": Derived(
            total / 2.0, "items/s",
            "items_per_second_total / 2 lanes; cross-checked against the wiki's "
            "per-lane tier table (fast belt 15 items/s per lane)",
            "documented-only", REF_WIKI_LANES),
        "lane_count": Derived(
            2, "lanes", "belt-connectable entities carry a left and a right lane",
            "documented-only", REF_WIKI_LANES),
    }


def _geometry_derived(proto: Mapping[str, Any]) -> dict[str, Derived]:
    box = Box.from_raw(proto["collision_box"])
    tw, th = _tile_dims(box)
    out = {
        "collision_box_tiles": Derived(
            box.to_dict(), "tiles", "raw 'collision_box' normalized to named corners",
            "documented-only", REF_DUMP),
        "tile_width": Derived(
            tw, "tiles",
            "collision box width rounded up (documented tile_width default); the "
            "prototype does not define tile_width",
            "documented-only", REF_ENTITY_DOCS),
        "tile_height": Derived(
            th, "tiles",
            "collision box height rounded up (documented tile_height default); the "
            "prototype does not define tile_height",
            "documented-only", REF_ENTITY_DOCS),
    }
    if "selection_box" in proto:
        sbox = Box.from_raw(proto["selection_box"])
        out["selection_box_tiles"] = Derived(
            sbox.to_dict(), "tiles", "raw 'selection_box' normalized to named corners",
            "documented-only", REF_DUMP)
    return out


#: Mechanics rules that the first release must account for. Every one needs a
#: record in the observation fixture directory, marked observed, documented-only
#: or pending.
REQUIRED_MECHANICS_RULES: Mapping[str, str] = {
    "belt.straight.lane_capacity": "Straight belt per-lane capacity and units",
    "belt.turn.lane_behavior": "Behaviour of the two lanes through a turn",
    "belt.side_load.lane_assignment": "Which lane a side-load feeds, and its rate",
    "belt.transfer.belt_to_belt": "End-to-end belt handover and lane preservation",
    "underground.pairing.range": "Entrance/exit pairing distance from max_distance",
    "underground.pairing.conflict": "Interaction with an intervening same-tier pair",
    "underground.lane_mapping": "Lane identity through the tunnel",
    "splitter.lane_split": "Per-lane input/output tiles and shared throughput",
    "splitter.priority_and_filter": "Input/output priority and filter behaviour",
    "inserter.endpoints.pickup_drop_tiles": "Pickup and drop tiles, and belt lane chosen",
    "inserter.rate.cycle_and_stack": "Cycle time and hand size, including research",
    "machine.activity.assembling_machine_2": "AM2 craft rate from crafting_speed",
    "machine.activity.electric_furnace": "Electric furnace craft rate and recipe set",
    "power.supply_assumption": "Externally powered assumption vs actual coverage",
    "circuit.control_state": "Circuit-disabled and unknown-condition behaviour",
    "unsupported.entity_visibility": "Unsupported entities stay visible, never operating",
}


def _prototype_from_raw(name: str, ptype: str, proto: Mapping[str, Any]) -> Prototype:
    fields = _FIELDS_BY_TYPE.get(ptype)
    if fields is None:
        raise PrototypeError(f"no field list for prototype type {ptype!r}")
    raw = {k: proto[k] for k in fields if k in proto}
    absent = tuple(sorted(k for k in fields if k not in proto))
    omitted = tuple(sorted(
        (k, reason) for k, reason in _OMITTED_FIELD_REASONS.items() if k in proto))

    derived: dict[str, Derived] = dict(_geometry_derived(proto))
    unknown: list[str] = []

    if ptype in ("transport-belt", "underground-belt", "splitter"):
        derived.update(_belt_derived(proto["speed"]))

    if ptype == "transport-belt":
        unknown = ["belt.turn.lane_behavior", "belt.side_load.lane_assignment",
                   "belt.transfer.belt_to_belt"]
    elif ptype == "underground-belt":
        derived["underground_span_tiles"] = Derived(
            None, "tiles",
            "raw 'max_distance' is recorded verbatim; whether it counts the tiles "
            "between the pair or the centre-to-centre distance is not stated by the "
            "prototype documentation, so no span is derived here",
            "pending", "underground.pairing.range")
        unknown = ["underground.pairing.range", "underground.pairing.conflict",
                   "underground.lane_mapping"]
    elif ptype == "splitter":
        derived["input_output_tile_offsets"] = Derived(
            None, "tiles",
            "the splitter occupies the derived tile footprint, but which tile carries "
            "which input/output lane is not stated by the prototype",
            "pending", "splitter.lane_split")
        unknown = ["splitter.lane_split", "splitter.priority_and_filter"]
    elif ptype == "inserter":
        pickup = proto["pickup_position"]
        insert = proto["insert_position"]
        derived["pickup_offset_tiles"] = Derived(
            {"x": float(pickup[0]), "y": float(pickup[1])}, "tiles",
            "raw 'pickup_position', entity-relative for the prototype's unrotated "
            "(north) orientation; rotation to world tiles is task 03's mapping",
            "documented-only", REF_INSERTER_DOCS)
        derived["drop_offset_tiles"] = Derived(
            {"x": float(insert[0]), "y": float(insert[1])}, "tiles",
            "raw 'insert_position', entity-relative for the unrotated orientation",
            "documented-only", REF_INSERTER_DOCS)
        derived["items_per_second"] = Derived(
            None, "items/s",
            "cycle time depends on swing geometry, source/destination type and hand "
            "size research; none of that is in the prototype. Capacity stays unknown, "
            "which the routing contract relaxes rather than bounds",
            "pending", "inserter.rate.cycle_and_stack")
        derived["is_bulk"] = Derived(
            bool(proto["bulk"]) if "bulk" in proto else None, "boolean",
            "raw 'bulk' when defined; null when the prototype omits it (the "
            "documented default false is not asserted here)",
            "documented-only" if "bulk" in proto else "pending",
            REF_INSERTER_DOCS if "bulk" in proto else "inserter.rate.cycle_and_stack")
        unknown = ["inserter.rate.cycle_and_stack",
                   "inserter.endpoints.pickup_drop_tiles"]
    elif ptype in ("assembling-machine", "furnace"):
        fluid_boxes = proto.get("fluid_boxes") or []
        derived["fluid_box_production_types"] = Derived(
            sorted({str(fb.get("production_type")) for fb in fluid_boxes
                    if isinstance(fb, dict) and fb.get("production_type")}),
            "production types",
            "production_type values summarised from the omitted 'fluid_boxes' field; "
            "fluid transport itself is out of the first profile",
            "documented-only", REF_DUMP)
        derived["crafts_per_second_at_speed_1"] = Derived(
            None, "crafts/s",
            "craft rate needs a recipe's energy_required; recipe arithmetic belongs "
            "to the shared calculation layer, not to this adapter",
            "pending",
            "machine.activity.assembling_machine_2" if ptype == "assembling-machine"
            else "machine.activity.electric_furnace")
        unknown = ["power.supply_assumption"]
    elif ptype == "electric-pole":
        unknown = ["power.supply_assumption"]
    elif ptype == "beacon":
        unknown = ["power.supply_assumption"]

    in_first = name in FIRST_ENTITY_SET
    return Prototype(
        name=name,
        prototype_type=ptype,
        subsystem=subsystem_for(ptype),
        in_first_entity_set=in_first,
        support="supported" if in_first else "unsupported",
        origin="unknown",
        raw=raw,
        absent_raw_fields=absent,
        omitted_raw_fields=omitted,
        derived=derived,
        unknown_mechanics=tuple(unknown),
    )


def _find_raw(raw: Mapping[str, Any], name: str) -> tuple[str, Mapping[str, Any]] | None:
    """Locate an *entity* prototype by name.

    Item-like prototypes share the name namespace with entities (a dump defines
    both an item and an entity called ``transport-belt``), so only the entity
    types this adapter knows how to read are searched.
    """
    found = [(ptype, protos[name]) for ptype, protos in raw.items()
             if ptype in _FIELDS_BY_TYPE and isinstance(protos, dict)
             and isinstance(protos.get(name), dict)]
    if len(found) > 1:
        raise PrototypeError(
            f"prototype {name!r} is defined by several entity types: "
            f"{sorted(p for p, _ in found)}")
    return found[0] if found else None


def extract_prototypes(raw: Mapping[str, Any], provenance: Provenance) -> PrototypeExtract:
    """Normalize the pinned prototypes present in ``raw``.

    Prototypes absent from the source are reported in
    ``missing_from_first_entity_set``; nothing is fabricated for them.
    """
    undeclared = sorted(set(REQUIRED_REFERENCE_IDS) - provenance.reference_ids)
    if undeclared:
        raise PrototypeError(
            f"provenance is missing required evidence references: {undeclared}")
    prototypes: list[Prototype] = []
    missing: list[str] = []
    for name in list(FIRST_ENTITY_SET) + list(RETAINED_UNSUPPORTED):
        found = _find_raw(raw, name)
        if found is None:
            if name in FIRST_ENTITY_SET:
                missing.append(name)
            continue
        ptype, proto = found
        prototypes.append(_prototype_from_raw(name, ptype, proto))
    return PrototypeExtract(
        PROTOTYPE_SCHEMA_VERSION, provenance, tuple(prototypes), tuple(missing))


# --------------------------------------------------------------------------
# Sources: full dump and pinned slice
# --------------------------------------------------------------------------

#: Raw prototype fields whose canonical JSON is at most this long are kept
#: verbatim in the pinned slice; larger ones (graphics, sounds, fluid boxes) are
#: dropped and their names recorded. The rule is size-based and deterministic so
#: the slice can be regenerated byte-for-byte.
SLICE_FIELD_SIZE_LIMIT = 400


def slice_raw_dump(raw: Mapping[str, Any]) -> dict:
    """Build the small pinned slice of the full dump.

    The slice keeps every field the adapter reads plus every other small field,
    and records the names of the fields it dropped, per prototype.
    """
    out: dict[str, Any] = {"prototypes": {}, "dropped_fields": {}}
    for name in list(FIRST_ENTITY_SET) + list(RETAINED_UNSUPPORTED):
        found = _find_raw(raw, name)
        if found is None:
            continue
        ptype, proto = found
        kept: dict[str, Any] = {"type": ptype, "name": name}
        dropped: list[str] = []
        wanted = set(_FIELDS_BY_TYPE.get(ptype, ())) | {"fluid_boxes"}
        for key in sorted(proto):
            if key in ("type", "name"):
                continue
            value = proto[key]
            if key in wanted or len(canonical_json(value)) <= SLICE_FIELD_SIZE_LIMIT:
                kept[key] = value
            else:
                dropped.append(key)
        out["prototypes"].setdefault(ptype, {})[name] = kept
        out["dropped_fields"][name] = dropped
    return out


def raw_from_slice(slice_doc: Mapping[str, Any]) -> dict:
    """Reconstruct a ``data.raw``-shaped mapping from a pinned slice."""
    if not isinstance(slice_doc, dict) or "prototypes" not in slice_doc:
        raise PrototypeError("pinned slice document is malformed")
    return {ptype: dict(protos) for ptype, protos in slice_doc["prototypes"].items()}


def load_json(path: str | Path) -> Any:
    """Read a JSON document, rejecting duplicate object keys."""
    def _no_duplicates(pairs):
        seen: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                raise PrototypeError(f"duplicate JSON key {key!r} in {path}")
            seen[key] = value
        return seen

    with open(path) as handle:
        return json.load(handle, object_pairs_hook=_no_duplicates)


def dump_source_identity(path: str | None = None) -> tuple[str, str]:
    """Resolve the game data dump and return ``(path, sha256)``.

    The digest is the dump file's SHA-256, the identity the MCP loader already
    records for loaded game data.
    """
    from .gamedata import read_dump  # local import keeps the module import cheap

    resolved, sha, _raw = read_dump(path)
    return resolved, sha


def load_pinned_extract(path: str | Path | None = None) -> PrototypeExtract:
    """Load the checked-in extract. This is the adapter entry point for 03/04/05."""
    target = Path(path) if path is not None else EXTRACT_PATH
    if not target.exists():
        raise PrototypeError(
            f"pinned prototype extract not found at {target}; regenerate it with "
            f"{PROTOTYPE_FIXTURE_DIR / 'generate.py'} from a full data dump")
    return parse_extract(load_json(target))


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------

_MANIFEST_KEYS = (
    "schema_version", "target_mechanics_profile", "environment",
    "source_dump", "raw_slice", "extract", "observations", "notes",
)


def build_manifest(
    extract: PrototypeExtract,
    slice_doc: Mapping[str, Any],
    *,
    observation_index: Mapping[str, Any] | None = None,
) -> dict:
    """Build the provenance manifest for the pinned fixtures."""
    prov = extract.provenance
    statuses: dict[str, int] = {}
    unmet = True
    if observation_index is not None:
        for status in observation_index.get("status_counts", {}):
            statuses[status] = int(observation_index["status_counts"][status])
        unmet = bool(observation_index.get("mechanics_gate_unmet", True))
    return {
        "schema_version": PROTOTYPE_SCHEMA_VERSION,
        "target_mechanics_profile": prov.target_mechanics_profile,
        "environment": {
            "game_version": prov.game_version,
            "declared_mods": (None if prov.declared_mods is None
                              else [list(m) for m in prov.declared_mods]),
            "environment_status": prov.environment_status,
            "matches_target_profile": prov.matches_target_profile,
        },
        "source_dump": {
            "path": prov.source_dump_path,
            "sha256": prov.source_dump_sha256,
        },
        "raw_slice": {
            "path": "raw_prototype_slice.json",
            "content_hash": content_hash(slice_doc),
        },
        "extract": {
            "path": "prototypes.json",
            "content_hash": extract.content_hash(),
            "prototype_count": len(extract.prototypes),
            "supported_count": len(extract.supported_names()),
            "missing_from_first_entity_set": list(extract.missing_from_first_entity_set),
        },
        "observations": {
            "path": "../routing_mechanics_observations/manifest.json",
            "status_counts": statuses,
            "mechanics_gate_unmet": unmet,
        },
        "notes": list(prov.notes),
    }


def verify_manifest(
    manifest: Mapping[str, Any],
    *,
    extract: PrototypeExtract,
    slice_doc: Mapping[str, Any],
) -> None:
    """Raise :class:`PrototypeError` when a manifest does not match its artifacts."""
    _check_keys(manifest, _MANIFEST_KEYS, "manifest")
    if manifest["schema_version"] != PROTOTYPE_SCHEMA_VERSION:
        raise PrototypeError(
            f"manifest schema {manifest['schema_version']!r} does not match "
            f"{PROTOTYPE_SCHEMA_VERSION!r}")
    prov = extract.provenance
    if manifest["target_mechanics_profile"] != prov.target_mechanics_profile:
        raise PrototypeError("manifest profile does not match the extract's profile")
    env = _check_keys(manifest["environment"], (
        "game_version", "declared_mods", "environment_status",
        "matches_target_profile"), "manifest.environment")
    if env["matches_target_profile"] != "unknown" and (
        env["game_version"] is None or env["declared_mods"] is None
    ):
        raise PrototypeError(
            "manifest claims a profile match without a known build and mod list")
    if env["environment_status"] != prov.environment_status:
        raise PrototypeError("manifest environment status contradicts the extract")
    slice_hash = content_hash(slice_doc)
    if manifest["raw_slice"]["content_hash"] != slice_hash:
        raise PrototypeError(
            f"raw slice hash mismatch: manifest {manifest['raw_slice']['content_hash']} "
            f"!= actual {slice_hash}")
    if prov.source_slice_content_hash not in (None, slice_hash):
        raise PrototypeError("extract provenance records a different slice hash")
    extract_hash = extract.content_hash()
    if manifest["extract"]["content_hash"] != extract_hash:
        raise PrototypeError(
            f"extract hash mismatch: manifest {manifest['extract']['content_hash']} "
            f"!= actual {extract_hash}")
    if manifest["extract"]["prototype_count"] != len(extract.prototypes):
        raise PrototypeError("manifest prototype count does not match the extract")
    if manifest["source_dump"]["sha256"] != prov.source_dump_sha256:
        raise PrototypeError("manifest source dump sha does not match the extract")


# --------------------------------------------------------------------------
# Mechanics observation records
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Observation:
    """One mechanics rule and the evidence that does (or does not) support it."""

    schema_version: str
    record_id: str            # a REQUIRED_MECHANICS_RULES key
    title: str
    profile: str
    setup_blueprint: str | None       # blueprint string or repository path
    supplied_items: tuple[Mapping[str, Any], ...]  # {item, rate_per_s|count, source}
    research_state: Mapping[str, Any] | None       # named levels, or null = unknown
    control_state: str | None         # circuit/enable state of the setup
    measurement_interval_s: float | None
    expected_behavior: str
    observation_method: str | None
    evidence_status: str
    measurement: Mapping[str, Any] | None
    environment: Mapping[str, Any]    # game_version, declared_mods, save
    references: tuple[str, ...]
    blocking_gate: str | None
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != OBSERVATION_SCHEMA_VERSION:
            raise PrototypeError(
                f"unsupported observation schema {self.schema_version!r}")
        _check_str(self.record_id, "observation.record_id")
        _check_str(self.title, "observation.title")
        _check_str(self.profile, "observation.profile")
        _check_str(self.expected_behavior, "observation.expected_behavior")
        _check_choice(self.evidence_status, EVIDENCE_STATUSES,
                      "observation.evidence_status")
        env = _check_keys(self.environment, ("game_version", "declared_mods", "save"),
                          "observation.environment")
        if self.evidence_status == "observed":
            missing = [name for name, value in (
                ("setup_blueprint", self.setup_blueprint),
                ("measurement_interval_s", self.measurement_interval_s),
                ("observation_method", self.observation_method),
                ("measurement", self.measurement),
            ) if value is None]
            if missing:
                raise PrototypeError(
                    f"{self.record_id}: an observed record needs {sorted(missing)}")
            if env["game_version"] is None or env["declared_mods"] is None:
                raise PrototypeError(
                    f"{self.record_id}: an observed record needs an identified game "
                    f"build and mod list")
            if env["save"] is None:
                raise PrototypeError(
                    f"{self.record_id}: an observed record must name the disposable "
                    f"save it was captured in")
        else:
            if self.measurement is not None:
                raise PrototypeError(
                    f"{self.record_id}: only an observed record may carry a "
                    f"measurement (status is {self.evidence_status!r})")
        if self.evidence_status == "documented-only" and not self.references:
            raise PrototypeError(
                f"{self.record_id}: a documented-only record needs a reference")
        if self.evidence_status == "pending" and not self.blocking_gate:
            raise PrototypeError(
                f"{self.record_id}: a pending record must state its blocking gate")

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "title": self.title,
            "profile": self.profile,
            "setup_blueprint": self.setup_blueprint,
            "supplied_items": [dict(s) for s in self.supplied_items],
            "research_state": (None if self.research_state is None
                               else dict(self.research_state)),
            "control_state": self.control_state,
            "measurement_interval_s": self.measurement_interval_s,
            "expected_behavior": self.expected_behavior,
            "observation_method": self.observation_method,
            "evidence_status": self.evidence_status,
            "measurement": None if self.measurement is None else dict(self.measurement),
            "environment": dict(self.environment),
            "references": list(self.references),
            "blocking_gate": self.blocking_gate,
            "notes": list(self.notes),
        }


_OBSERVATION_KEYS = (
    "schema_version", "record_id", "title", "profile", "setup_blueprint",
    "supplied_items", "research_state", "control_state", "measurement_interval_s",
    "expected_behavior", "observation_method", "evidence_status", "measurement",
    "environment", "references", "blocking_gate", "notes",
)


def parse_observation(value: Any) -> Observation:
    """Strictly parse one observation record."""
    _check_keys(value, _OBSERVATION_KEYS, "observation")
    return Observation(
        value["schema_version"], value["record_id"], value["title"], value["profile"],
        value["setup_blueprint"], tuple(value["supplied_items"]),
        value["research_state"], value["control_state"],
        value["measurement_interval_s"], value["expected_behavior"],
        value["observation_method"], value["evidence_status"], value["measurement"],
        value["environment"], tuple(value["references"]), value["blocking_gate"],
        tuple(value["notes"]),
    )


def load_observations(directory: str | Path | None = None) -> tuple[Observation, ...]:
    """Load every observation record, sorted by record id."""
    target = Path(directory) if directory is not None else OBSERVATION_RECORD_DIR
    if not target.is_dir():
        raise PrototypeError(f"observation record directory not found: {target}")
    records = [parse_observation(load_json(p)) for p in sorted(target.glob("*.json"))]
    return tuple(sorted(records, key=lambda r: r.record_id))


def build_observation_index(records: Iterable[Observation]) -> dict:
    """Summarise coverage of :data:`REQUIRED_MECHANICS_RULES`."""
    records = list(records)
    by_id: dict[str, Observation] = {}
    for record in records:
        if record.record_id in by_id:
            raise PrototypeError(f"duplicate observation record {record.record_id!r}")
        by_id[record.record_id] = record
    counts: dict[str, int] = {status: 0 for status in EVIDENCE_STATUSES}
    for record in records:
        counts[record.evidence_status] += 1
    missing = sorted(set(REQUIRED_MECHANICS_RULES) - set(by_id))
    extra = sorted(set(by_id) - set(REQUIRED_MECHANICS_RULES))
    unobserved = sorted(rid for rid, rec in by_id.items()
                        if rec.evidence_status != "observed")
    return {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "profile": TARGET_MECHANICS_PROFILE,
        "required_rules": sorted(REQUIRED_MECHANICS_RULES),
        "records": sorted(by_id),
        "status_counts": counts,
        "status_by_rule": {rid: by_id[rid].evidence_status for rid in sorted(by_id)},
        "missing_rules": missing,
        "unrecognised_records": extra,
        "rules_without_game_observation": unobserved,
        "mechanics_gate_unmet": bool(missing or extra or unobserved),
    }


def validate_observation_index(index: Mapping[str, Any],
                               records: Iterable[Observation]) -> None:
    """Raise when a stored observation index disagrees with the records."""
    actual = build_observation_index(records)
    if dict(index) != actual:
        differing = sorted(
            k for k in set(index) | set(actual) if index.get(k) != actual.get(k))
        raise PrototypeError(
            f"observation index does not match the records; differing keys: {differing}")


__all__ = [
    "PROTOTYPE_SCHEMA_VERSION", "OBSERVATION_SCHEMA_VERSION",
    "TARGET_MECHANICS_PROFILE", "EVIDENCE_STATUSES", "SUBSYSTEMS", "SUPPORT_LEVELS",
    "FIRST_ENTITY_SET", "RETAINED_UNSUPPORTED", "REQUIRED_MECHANICS_RULES",
    "REQUIRED_REFERENCE_IDS", "DEFAULT_REFERENCES", "SLICE_FIELD_SIZE_LIMIT",
    "PROTOTYPE_FIXTURE_DIR", "OBSERVATION_FIXTURE_DIR", "RAW_SLICE_PATH",
    "EXTRACT_PATH", "MANIFEST_PATH", "PILOT_COVERAGE_PATH",
    "OBSERVATION_INDEX_PATH", "OBSERVATION_RECORD_DIR",
    "PrototypeError", "Box", "Derived", "Reference", "Provenance", "Prototype",
    "PrototypeExtract", "Observation",
    "subsystem_for", "extract_prototypes", "parse_extract", "load_pinned_extract",
    "slice_raw_dump", "raw_from_slice", "load_json", "dump_source_identity",
    "build_manifest", "verify_manifest", "parse_observation", "load_observations",
    "build_observation_index", "validate_observation_index",
]
