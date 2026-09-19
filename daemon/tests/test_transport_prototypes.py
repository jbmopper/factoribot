"""Prototype normalization, provenance and mechanics-evidence tests (task 02).

Every test here runs offline from the pinned fixtures. The two tests that need
the full 14 MB dump skip when it is absent, and they only cross-check that the
pinned slice agrees with the dump; nothing else depends on it.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from factoribot import gamedata
from factoribot.blueprint import decode_blueprint_string
from factoribot.blueprint_contract import content_hash
from factoribot.transport_prototypes import (
    DEFAULT_REFERENCES, EXTRACT_PATH, FIRST_ENTITY_SET, MANIFEST_PATH,
    OBSERVATION_FIXTURE_DIR, OBSERVATION_INDEX_PATH, PILOT_COVERAGE_PATH,
    PROTOTYPE_FIXTURE_DIR, PROTOTYPE_SCHEMA_VERSION,
    RAW_SLICE_PATH, REQUIRED_MECHANICS_RULES, REQUIRED_REFERENCE_IDS,
    TARGET_MECHANICS_PROFILE, Provenance, PrototypeError, build_observation_index,
    extract_prototypes, load_json, load_observations, load_pinned_extract,
    parse_extract, parse_observation, raw_from_slice, slice_raw_dump,
    subsystem_for, validate_observation_index, verify_manifest,
)

PILOT_PATH = Path(__file__).resolve().parent / "fixtures" / "wip_science.txt"


@pytest.fixture(scope="module")
def slice_doc():
    return load_json(RAW_SLICE_PATH)


@pytest.fixture(scope="module")
def extract():
    return load_pinned_extract()


@pytest.fixture(scope="module")
def manifest():
    return load_json(MANIFEST_PATH)


@pytest.fixture(scope="module")
def observations():
    return load_observations()


def full_dump_or_skip() -> dict:
    try:
        return json.loads(Path(gamedata.find_dump()).read_bytes())
    except (FileNotFoundError, OSError):
        pytest.skip("full data-raw-dump.json not present; pinned slice covers CI")


# ---------------------------------------------------------------- extraction

def test_extract_rebuilds_from_pinned_slice_without_the_full_dump(slice_doc, extract):
    """Normalization is reproducible offline: slice in, identical extract out."""
    rebuilt = extract_prototypes(raw_from_slice(slice_doc), extract.provenance)
    assert rebuilt.to_dict() == extract.to_dict()
    assert rebuilt.content_hash() == extract.content_hash()


def test_extract_round_trips_and_rejects_unknown_keys(extract):
    assert parse_extract(extract.to_dict()).to_dict() == extract.to_dict()
    broken = extract.to_dict()
    broken["surprise"] = 1
    with pytest.raises(PrototypeError, match="unknown keys"):
        parse_extract(broken)
    stale = extract.to_dict()
    stale["schema_version"] = "factoribot-routing-prototypes-0"
    with pytest.raises(PrototypeError, match="unsupported extract schema"):
        parse_extract(stale)


def test_first_entity_set_is_complete_and_only_it_is_supported(extract):
    assert extract.missing_from_first_entity_set == ()
    assert set(extract.supported_names()) == set(FIRST_ENTITY_SET)
    for proto in extract.prototypes:
        if proto.name not in FIRST_ENTITY_SET:
            assert proto.support == "unsupported"


def test_belt_rates_match_an_independent_hand_derivation(extract):
    """0.0625 tiles/tick * 480 = 30 items/s on both lanes, 15 per lane.

    The multiplier is the documented belt speed formula and is shared with
    gamedata rather than forked here; the per-lane figure is the number the wiki
    physics page lists for the fast belt.
    """
    assert gamedata.BELT_ITEMS_PER_SPEED == 480.0
    expected = {"transport-belt": (0.03125, 15.0, 7.5),
                "fast-transport-belt": (0.0625, 30.0, 15.0),
                "express-transport-belt": (0.09375, 45.0, 22.5)}
    for name, (speed, total, per_lane) in expected.items():
        proto = extract.by_name(name)
        assert proto.raw_field("speed") == speed
        assert proto.derived["items_per_second_total"].value == total
        assert proto.derived["items_per_second_per_lane"].value == per_lane
        assert proto.derived["lane_count"].value == 2


def test_belt_rate_agrees_with_the_existing_database_belt_table():
    """The adapter must not fork gamedata's belt convention."""
    raw = full_dump_or_skip()
    db = gamedata.build_database(raw)
    extract = load_pinned_extract()
    for name, items_per_second in db.belts.items():
        proto = extract.get(name)
        if proto is not None:
            assert proto.derived["items_per_second_total"].value == items_per_second


def test_footprints_are_derived_from_collision_boxes_not_guessed(extract):
    """A splitter is 2x1 tiles, an AM2 3x3; neither prototype states it."""
    splitter = extract.by_name("fast-splitter")
    assert "tile_width" in splitter.absent_raw_fields
    assert (splitter.derived["tile_width"].value,
            splitter.derived["tile_height"].value) == (2, 1)
    assert splitter.derived["tile_width"].basis.startswith("collision box width")
    machine = extract.by_name("assembling-machine-2")
    assert (machine.derived["tile_width"].value,
            machine.derived["tile_height"].value) == (3, 3)
    belt = extract.by_name("fast-transport-belt")
    assert (belt.derived["tile_width"].value, belt.derived["tile_height"].value) == (1, 1)


def test_unknown_engine_semantics_stay_null_and_pending(extract):
    """The counterexample: an adapter that guessed a reach would pass a naive test.

    ``max_distance`` is recorded verbatim, but the documentation does not say
    whether it counts the gap or the separation, so no span is derived.
    """
    under = extract.by_name("fast-underground-belt")
    assert under.raw_field("max_distance") == 7
    span = under.derived["underground_span_tiles"]
    assert span.value is None and span.evidence_status == "pending"
    assert span.evidence_ref == "underground.pairing.range"
    for name, span_raw in (("underground-belt", 5), ("express-underground-belt", 9)):
        proto = extract.by_name(name)
        assert proto.raw_field("max_distance") == span_raw
        assert proto.derived["underground_span_tiles"].value is None

    inserter = extract.by_name("bulk-inserter")
    rate = inserter.derived["items_per_second"]
    assert rate.value is None and rate.evidence_status == "pending"

    splitter = extract.by_name("fast-splitter")
    assert splitter.derived["input_output_tile_offsets"].value is None


def test_absent_fields_are_explicit_and_never_defaulted(extract):
    """``bulk`` is defined for the bulk inserter and undefined for the others."""
    bulk = extract.by_name("bulk-inserter")
    assert bulk.raw_field("bulk") is True
    assert bulk.derived["is_bulk"].value is True

    fast = extract.by_name("fast-inserter")
    assert "bulk" in fast.absent_raw_fields
    assert "bulk" not in fast.raw
    assert fast.derived["is_bulk"].value is None
    assert fast.derived["is_bulk"].evidence_status == "pending"
    with pytest.raises(PrototypeError, match="recorded as absent"):
        fast.raw_field("bulk")

    # Documented fields this build leaves undefined stay listed, not invented.
    for field in ("hand_size", "stack_size_bonus", "max_belt_stack_size"):
        assert field in fast.absent_raw_fields


def test_inserter_endpoints_are_raw_vectors_with_a_stated_frame(extract):
    fast = extract.by_name("fast-inserter")
    assert fast.raw_field("pickup_position") == [0, -1]
    assert fast.raw_field("insert_position") == [0, 1.2]
    assert fast.derived["pickup_offset_tiles"].value == {"x": 0.0, "y": -1.0}
    assert fast.derived["drop_offset_tiles"].value == {"x": 0.0, "y": 1.2}
    assert "unrotated" in fast.derived["pickup_offset_tiles"].basis


def test_rate_relevant_inserter_fields_are_retained(extract):
    fast = extract.by_name("fast-inserter")
    assert fast.raw_field("extension_speed") == 0.1
    assert fast.raw_field("rotation_speed") == 0.04
    assert fast.raw_field("filter_count") == 5
    assert fast.raw_field("energy_source")["type"] == "electric"


def test_power_and_beacon_fields_are_retained_without_implying_mechanics(extract):
    """Later power/beacon adapters need no second extraction pass."""
    substation = extract.by_name("substation")
    assert substation.raw_field("supply_area_distance") == 9
    assert substation.raw_field("maximum_wire_distance") == 18
    assert substation.support == "unsupported"
    beacon = extract.by_name("beacon")
    assert beacon.raw_field("distribution_effectivity") == 1.5
    assert len(beacon.raw_field("profile")) == 100
    assert beacon.support == "unsupported"
    assert "power.supply_assumption" in beacon.unknown_mechanics


def test_machine_fields_and_fluid_box_summary(extract):
    machine = extract.by_name("assembling-machine-2")
    assert machine.raw_field("crafting_speed") == 0.75
    assert machine.raw_field("module_slots") == 2
    assert "crafting-with-fluid" in machine.raw_field("crafting_categories")
    assert dict(machine.omitted_raw_fields)["fluid_boxes"].startswith("large structured")
    assert machine.derived["fluid_box_production_types"].value == ["input", "output"]
    assert machine.derived["crafts_per_second_at_speed_1"].value is None
    furnace = extract.by_name("electric-furnace")
    assert furnace.raw_field("crafting_speed") == 2
    assert furnace.raw_field("crafting_categories") == ["smelting"]
    assert furnace.raw_field("source_inventory_size") == 1


# ----------------------------------------------------------- classification

def test_subsystem_hints_cover_the_contract_vocabulary():
    assert subsystem_for("transport-belt") == "transport"
    assert subsystem_for("inserter") == "inserter"
    assert subsystem_for("furnace") == "production"
    assert subsystem_for("electric-pole") == "power"
    assert subsystem_for("straight-rail") == "rail"
    assert subsystem_for("pipe") == "fluid"
    assert subsystem_for("roboport") == "logistics"
    assert subsystem_for("decider-combinator") == "circuit"
    # Anything the map does not know stays explicitly unknown.
    assert subsystem_for("simple-entity-with-owner") == "unknown"
    assert subsystem_for("some-modded-type") == "unknown"
    with pytest.raises(PrototypeError):
        subsystem_for("")


def test_modded_pole_is_absent_from_base_extract_but_retained_in_pilot_coverage(extract):
    assert extract.get("ee-super-substation") is None
    coverage = load_json(PILOT_COVERAGE_PATH)
    assert coverage["coverage"]["ee-super-substation"] == {
        "count": 3, "in_extract": False, "origin": None,
        "prototype_type": None, "subsystem": None, "support": None,
    }


# --------------------------------------------------------------- provenance

def test_provenance_identifies_the_verified_base_2077_export(extract):
    prov = extract.provenance
    assert prov.target_mechanics_profile == TARGET_MECHANICS_PROFILE
    assert prov.game_version == "2.0.77"
    assert prov.declared_mods == (("base", "2.0.77"),)
    assert prov.environment_status == "identified"
    assert prov.matches_target_profile == "yes"
    assert prov.source_dump_sha256 and len(prov.source_dump_sha256) == 64
    assert set(REQUIRED_REFERENCE_IDS) <= prov.reference_ids


def test_a_profile_match_claim_needs_a_build_and_a_mod_list():
    kwargs = dict(
        schema_version=PROTOTYPE_SCHEMA_VERSION,
        target_mechanics_profile=TARGET_MECHANICS_PROFILE,
        game_version=None, declared_mods=None,
        environment_status="unidentified", matches_target_profile="unknown",
        source_kind="pinned-slice", source_dump_path="data/data-raw-dump.json",
        source_dump_sha256="0" * 64, source_slice_content_hash=None,
        references=DEFAULT_REFERENCES, notes=(),
    )
    Provenance(**kwargs)  # unknown environment is representable
    with pytest.raises(PrototypeError, match="profile match claim"):
        Provenance(**{**kwargs, "matches_target_profile": "yes"})
    with pytest.raises(PrototypeError, match="requires game_version"):
        Provenance(**{**kwargs, "environment_status": "identified"})
    ok = Provenance(**{**kwargs, "matches_target_profile": "yes",
                       "environment_status": "identified",
                       "game_version": "2.0.77",
                       "declared_mods": (("base", "2.0.77"),)})
    assert ok.declared_mods == (("base", "2.0.77"),)


def test_extraction_requires_the_declared_evidence_references(slice_doc, extract):
    thin = Provenance(**{
        **{k: getattr(extract.provenance, k) for k in (
            "schema_version", "target_mechanics_profile", "game_version",
            "declared_mods", "environment_status", "matches_target_profile",
            "source_kind", "source_dump_path", "source_dump_sha256",
            "source_slice_content_hash", "notes")},
        "references": tuple(r for r in DEFAULT_REFERENCES if r.kind == "wiki"),
    })
    with pytest.raises(PrototypeError, match="missing required evidence references"):
        extract_prototypes(raw_from_slice(slice_doc), thin)


def test_manifest_matches_its_artifacts(manifest, extract, slice_doc):
    verify_manifest(manifest, extract=extract, slice_doc=slice_doc)
    assert manifest["extract"]["content_hash"] == content_hash(extract.to_dict())
    assert manifest["raw_slice"]["content_hash"] == content_hash(slice_doc)
    assert manifest["source_dump"]["path"] == "data/data-raw-dump-2.0.77-base.json"


@pytest.mark.parametrize("mutate", [
    lambda m: m.__setitem__("schema_version", "factoribot-routing-prototypes-99"),
    lambda m: m["extract"].__setitem__("content_hash", "sha256:" + "0" * 64),
    lambda m: m["raw_slice"].__setitem__("content_hash", "sha256:" + "0" * 64),
    lambda m: m["extract"].__setitem__("prototype_count", 3),
    lambda m: m["source_dump"].__setitem__("sha256", "f" * 64),
    lambda m: m["environment"].__setitem__("matches_target_profile", "unknown"),
    lambda m: m["environment"].__setitem__("environment_status", "unidentified"),
    lambda m: m.__setitem__("target_mechanics_profile", "base-2.0.76-normal-v1"),
    lambda m: m.pop("observations"),
    lambda m: m.__setitem__("extra", True),
])
def test_a_mismatched_manifest_fails(manifest, extract, slice_doc, mutate):
    broken = copy.deepcopy(manifest)
    mutate(broken)
    with pytest.raises(PrototypeError):
        verify_manifest(broken, extract=extract, slice_doc=slice_doc)


def test_a_mutated_slice_fails_its_manifest(manifest, extract, slice_doc):
    tampered = copy.deepcopy(slice_doc)
    tampered["prototypes"]["transport-belt"]["fast-transport-belt"]["speed"] = 0.125
    with pytest.raises(PrototypeError, match="raw slice hash mismatch"):
        verify_manifest(manifest, extract=extract, slice_doc=tampered)


def test_pinned_slice_agrees_with_the_full_dump():
    raw = full_dump_or_skip()
    assert slice_raw_dump(raw) == load_json(RAW_SLICE_PATH)
    assert load_json(MANIFEST_PATH)["source_dump"]["sha256"] == gamedata.read_dump()[1]


def test_slice_is_small_enough_to_check_in():
    total = sum(p.stat().st_size for p in (RAW_SLICE_PATH, EXTRACT_PATH, MANIFEST_PATH,
                                           PILOT_COVERAGE_PATH))
    assert total < 1_000_000


def test_fixture_locations_resolve_inside_the_installed_package():
    """The evidence must ship with the package, not with the test tree.

    `load_pinned_extract()` previously resolved its evidence relative to
    `daemon/tests/fixtures/`, which no wheel ships -- an installed package has
    no `tests` directory at all. The fixture directories must live inside the
    `factoribot` package directory itself, where `[tool.setuptools.package-data]`
    can (and does) ship them.
    """
    import factoribot

    package_dir = Path(factoribot.__file__).resolve().parent
    for fixture_dir in (PROTOTYPE_FIXTURE_DIR, OBSERVATION_FIXTURE_DIR):
        resolved = Path(fixture_dir).resolve()
        assert resolved.is_relative_to(package_dir), (
            f"{fixture_dir} is not inside the factoribot package directory {package_dir}")
        assert "tests" not in resolved.relative_to(package_dir).parts
        assert resolved.is_dir()
    assert Path(EXTRACT_PATH).resolve().is_relative_to(package_dir)
    assert Path(MANIFEST_PATH).resolve().is_relative_to(package_dir)


# ------------------------------------------------------- mechanics evidence

def test_every_first_release_rule_has_exactly_one_record(observations):
    assert {r.record_id for r in observations} == set(REQUIRED_MECHANICS_RULES)
    for record in observations:
        assert record.profile == "base-2.0.76-normal-v1"
        assert record.title == REQUIRED_MECHANICS_RULES[record.record_id]


def test_observation_index_matches_the_records(observations):
    index = load_json(OBSERVATION_INDEX_PATH)
    validate_observation_index(index, observations)
    assert index["missing_rules"] == []
    assert index["unrecognised_records"] == []
    assert index["record_profiles"] == ["base-2.0.76-normal-v1"]
    assert set(index["incompatible_records"]) == set(REQUIRED_MECHANICS_RULES)


def test_the_game_observation_gate_is_unmet_and_says_so(observations):
    """No capture has been run, so the mechanics gate must report itself unmet."""
    index = build_observation_index(observations)
    assert index["status_counts"]["observed"] == 0
    assert index["mechanics_gate_unmet"] is True
    assert set(index["rules_without_game_observation"]) == set(REQUIRED_MECHANICS_RULES)
    for record in observations:
        assert record.evidence_status in ("documented-only", "pending")
        assert record.measurement is None
        assert record.environment["game_version"] is None


def test_documented_only_records_cite_a_source_and_pending_records_state_a_gate(
        observations):
    for record in observations:
        if record.evidence_status == "documented-only":
            assert record.references
        else:
            assert record.blocking_gate


def _record(**overrides) -> dict:
    base = {
        "schema_version": "factoribot-mechanics-observation-1",
        "record_id": "belt.straight.lane_capacity",
        "title": "test",
        "profile": TARGET_MECHANICS_PROFILE,
        "setup_blueprint": None,
        "supplied_items": [],
        "research_state": None,
        "control_state": None,
        "measurement_interval_s": None,
        "expected_behavior": "test",
        "observation_method": None,
        "evidence_status": "pending",
        "measurement": None,
        "environment": {"game_version": None, "declared_mods": None, "save": None},
        "references": [],
        "blocking_gate": "no capture",
        "notes": [],
    }
    base.update(overrides)
    return base


def test_a_claimed_observation_without_evidence_is_rejected():
    """A record cannot claim 'observed' by asserting it."""
    with pytest.raises(PrototypeError, match="an observed record needs"):
        parse_observation(_record(evidence_status="observed", blocking_gate=None))
    with pytest.raises(PrototypeError, match="identified game"):
        parse_observation(_record(
            evidence_status="observed", blocking_gate=None,
            setup_blueprint="0eNq...", measurement_interval_s=60.0,
            observation_method="counted chest contents",
            measurement={"items_per_second": 15.0}))
    with pytest.raises(PrototypeError, match="disposable save"):
        parse_observation(_record(
            evidence_status="observed", blocking_gate=None,
            setup_blueprint="0eNq...", measurement_interval_s=60.0,
            observation_method="counted chest contents",
            measurement={"items_per_second": 15.0},
            environment={"game_version": "2.0.77",
                         "declared_mods": [["base", "2.0.77"]], "save": None}))
    complete = parse_observation(_record(
        evidence_status="observed", blocking_gate=None,
        setup_blueprint="0eNq...", measurement_interval_s=60.0,
        observation_method="counted chest contents",
        measurement={"items_per_second": 15.0},
        environment={"game_version": "2.0.77", "declared_mods": [["base", "2.0.77"]],
                     "save": "disposable sandbox routing-02"}))
    assert complete.evidence_status == "observed"


def test_an_unobserved_record_cannot_carry_a_measurement():
    with pytest.raises(PrototypeError, match="only an observed record"):
        parse_observation(_record(measurement={"items_per_second": 15.0}))
    with pytest.raises(PrototypeError, match="needs a reference"):
        parse_observation(_record(evidence_status="documented-only",
                                  blocking_gate=None))
    with pytest.raises(PrototypeError, match="must state its blocking gate"):
        parse_observation(_record(blocking_gate=None))
    with pytest.raises(PrototypeError, match="unknown keys"):
        parse_observation(_record(surprise=1))


def test_index_detects_a_missing_or_stray_rule(observations):
    trimmed = [r for r in observations if r.record_id != "splitter.lane_split"]
    index = build_observation_index(trimmed)
    assert index["missing_rules"] == ["splitter.lane_split"]
    assert index["mechanics_gate_unmet"] is True
    with pytest.raises(PrototypeError, match="does not match the records"):
        validate_observation_index(load_json(OBSERVATION_INDEX_PATH), trimmed)


# -------------------------------------------------------------------- pilot

def test_pilot_coverage_matches_the_checked_in_blueprint(extract):
    """Counts come from decoding the pilot here, not from trusting the fixture."""
    coverage = load_json(PILOT_COVERAGE_PATH)
    blueprint = decode_blueprint_string(PILOT_PATH.read_text().strip())["blueprint"]
    counts: dict[str, int] = {}
    for entity in blueprint["entities"]:
        counts[entity["name"]] = counts.get(entity["name"], 0) + 1
    assert coverage["entity_counts"] == counts
    assert coverage["blueprint"]["entity_count"] == len(blueprint["entities"]) == 2771
    assert coverage["blueprint"]["encoded_version"] == blueprint["version"]
    assert coverage["blueprint"]["encoded_version_decoded"] == "2.0.76.0"
    assert coverage["blueprint"]["file_sha256"] == (
        "e48fa3fad55155c184a63f70db62ff801e9ce39cd358b8c1cabfd9e99655f49a")
    # The counts the routing contract pins for the pilot.
    assert counts == {"fast-transport-belt": 1738, "fast-underground-belt": 178,
                      "fast-splitter": 15, "bulk-inserter": 608,
                      "assembling-machine-2": 153, "electric-furnace": 76,
                      "ee-super-substation": 3}


def test_pilot_records_its_unresolved_prototype_and_missing_feeds(extract):
    coverage = load_json(PILOT_COVERAGE_PATH)
    assert coverage["unsupported_entities"] == ["ee-super-substation"]
    unresolved = coverage["unresolved_prototypes"]["ee-super-substation"]
    assert unresolved["count"] == 3 and unresolved["subsystem"] is None
    joined = " ".join(coverage["unavailable_information"]).lower()
    for missing in ("fed from outside", "budgets", "research", "mods", "power",
                    "circuit", "recipe"):
        assert missing in joined
    for name, entry in coverage["coverage"].items():
        prototype = extract.get(name)
        assert entry["support"] == (None if prototype is None else prototype.support)
