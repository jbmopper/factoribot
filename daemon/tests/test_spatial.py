"""Round-trip, selection and spatial-index tests (routing task 03).

The acceptance bar for preservation is *semantic* decode/encode/decode
equality, not byte equality: key order and deflate parameters are not part of
the blueprint format.
"""
import base64
import json
import math
import time
import tracemalloc
import zlib
from pathlib import Path

import pytest

from factoribot.blueprint import (
    BlueprintDecodeError,
    BlueprintError,
    DecodeLimits,
    blueprint_leaves,
    decode_blueprint,
    decode_blueprint_string,
    encode_blueprint,
    iter_blueprints,
    parse_selection_path,
    select_blueprint,
    walk_entries,
)
from factoribot.blueprint_contract import Box, ContractError, Point, content_hash
from factoribot.spatial import (
    ROTATION_SENSE_UNVALIDATED,
    SpatialError,
    SpatialLimits,
    build_spatial_view,
    index_blueprint,
    load_spatial_view,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SPATIAL_FIXTURES = FIXTURES / "routing_spatial"
PILOT = FIXTURES / "wip_science.txt"

# The contract's pinned pilot counts (docs/blueprint-routing-contract.md,
# "Development pilot"). Independent of anything this module computes.
PILOT_COUNTS = {
    "fast-transport-belt": 1738,
    "fast-underground-belt": 178,
    "fast-splitter": 15,
    "bulk-inserter": 608,
    "assembling-machine-2": 153,
    "electric-furnace": 76,
    "ee-super-substation": 3,
}


@pytest.fixture(scope="module")
def pilot_document():
    return decode_blueprint(PILOT.read_text())


@pytest.fixture(scope="module")
def pilot_view(pilot_document):
    return build_spatial_view(pilot_document)


@pytest.fixture(scope="module")
def odd_document():
    return json.loads((SPATIAL_FIXTURES / "odd_document.json").read_text())


def _generator():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "routing_spatial_generate", SPATIAL_FIXTURES / "generate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------
# Lossless decode / encode
# --------------------------------------------------------------------------
def test_pilot_round_trip_is_semantically_equal(pilot_document):
    again = decode_blueprint(encode_blueprint(pilot_document))
    assert again == pilot_document
    assert content_hash(again) == content_hash(pilot_document)
    assert len(again["blueprint"]["entities"]) == 2771


def test_odd_document_round_trip_keeps_unknown_fields(odd_document):
    encoded = encode_blueprint(odd_document)
    again = decode_blueprint(encoded)
    assert again == odd_document
    book = again["blueprint_book"]
    assert book["unfamiliar_book_key"] == {"kept": True, "nested": [1, {"deep": None}]}
    leaf = select_blueprint(again, [7])
    assert leaf["unfamiliar_leaf_key"] == ["kept", 2.5]
    assert leaf["entities"][0]["unfamiliar_entity_key"] == {"kept": [None, False]}
    assert leaf["tiles"] and leaf["wires"] == [[3, 5, 5, 5]] and leaf["schedules"] == []
    assert leaf["entities"][2]["filters"] == [{"index": 1, "name": "iron-plate"}]
    assert leaf["entities"][3]["quality"] == "uncommon"
    # The unselected planner survives untouched.
    assert again["blueprint_book"]["blueprints"][3]["upgrade_planner"]["item"] == "upgrade-planner"


def test_round_trip_preserves_noninteger_and_negative_coordinates(odd_document):
    again = decode_blueprint(encode_blueprint(odd_document))
    positions = [e["position"] for e in select_blueprint(again, [7])["entities"]]
    assert {"x": -0.25, "y": 0.5} in positions
    assert {"x": -3.5, "y": 0.5} in positions
    assert {"x": 5, "y": 5} in positions  # integer stays integer


def test_new_decoder_agrees_with_the_legacy_entry_point():
    text = PILOT.read_text()
    assert decode_blueprint(text) == decode_blueprint_string(text)


def test_legacy_flattening_still_works_on_the_odd_document(odd_document):
    labels = [bp.get("label") for bp in iter_blueprints(odd_document)]
    assert labels == ["fractional and rotated", "translated twin", "leaf under a nested book"]


def test_raw_json_documents_are_accepted():
    document = decode_blueprint('{"blueprint": {"entities": []}}')
    assert document == {"blueprint": {"entities": []}}


# --------------------------------------------------------------------------
# Bounds
# --------------------------------------------------------------------------
def test_decompression_limit_is_enforced_during_decompression():
    bomb = "0" + base64.b64encode(zlib.compress(b"\x00" * 40_000_000, 9)).decode()
    limits = DecodeLimits(max_decompressed_bytes=1_000_000)
    tracemalloc.start()
    try:
        with pytest.raises(BlueprintDecodeError) as excinfo:
            decode_blueprint(bomb, limits)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert excinfo.value.code == "decompressed_limit"
    # A plausible wrong implementation inflates all 40 MB and *then* measures.
    assert peak < 8 * 1024 * 1024, f"peak {peak} bytes: the limit was applied too late"


def test_encoded_length_limit():
    with pytest.raises(BlueprintDecodeError) as excinfo:
        decode_blueprint("0" + "A" * 100, DecodeLimits(max_encoded_chars=10))
    assert excinfo.value.code == "encoded_limit"


def test_nesting_limit():
    document = {"blueprint": {"entities": []}}
    node = document["blueprint"]
    for _ in range(80):
        node["deeper"] = {}
        node = node["deeper"]
    with pytest.raises(BlueprintDecodeError) as excinfo:
        decode_blueprint(json.dumps(document))
    assert excinfo.value.code == "nesting_limit"


def test_book_nesting_limit():
    document = {"blueprint_book": {"blueprints": []}}
    node = document["blueprint_book"]
    for _ in range(6):
        child = {"blueprints": []}
        node["blueprints"].append({"index": 0, "blueprint_book": child})
        node = child
    with pytest.raises(BlueprintDecodeError) as excinfo:
        walk_entries(document, DecodeLimits(max_depth=3))
    assert excinfo.value.code == "nesting_limit"


def test_entity_count_limit():
    record = {"entities": [
        {"entity_number": n + 1, "name": "fast-transport-belt",
         "position": {"x": n + 0.5, "y": 0.5}}
        for n in range(12)
    ]}
    with pytest.raises(SpatialError) as excinfo:
        index_blueprint(record, (), limits=SpatialLimits(max_entities=10))
    assert excinfo.value.code == "entity_limit"
    assert excinfo.value.detail["count"] == 12


def test_region_query_is_bounded():
    view = load_spatial_view('{"blueprint": {"entities": []}}',
                             limits=SpatialLimits(max_query_tiles=16))
    with pytest.raises(SpatialError) as excinfo:
        view.index().entities_in_box(Box(Point(0, 0), Point(100, 100)))
    assert excinfo.value.code == "query_limit"


def test_neighbor_query_work_is_bounded():
    record = {"entities": [{"entity_number": 1, "name": "fast-transport-belt",
                            "position": {"x": 0.5, "y": 0.5}}]}
    index = index_blueprint(record, limits=SpatialLimits(max_query_tiles=100))
    assert index.neighbors(1, distance=4) == ()
    with pytest.raises(SpatialError) as excinfo:
        index.neighbors(1, distance=1000)
    assert excinfo.value.code == "query_limit"
    with pytest.raises(SpatialError):
        index.neighbors(1, distance=-1)


def test_malformed_input_raises_structured_errors():
    for text, code in [
        ("", "empty_input"),
        ("0" + base64.b64encode(b"not deflate at all").decode(), "invalid_deflate"),
        ("0" + base64.b64encode(zlib.compress(b"{not json")).decode(), "invalid_json"),
        ("0" + base64.b64encode(zlib.compress(b"[1,2,3]")).decode(), "invalid_document"),
        ("0" + base64.b64encode(zlib.compress(b"\xff\xfe")).decode(), "invalid_utf8"),
    ]:
        with pytest.raises(BlueprintDecodeError) as excinfo:
            decode_blueprint(text)
        assert excinfo.value.code == code, text[:20]
        assert isinstance(excinfo.value, BlueprintError)  # legacy callers still catch it


def test_truncated_deflate_stream():
    payload = zlib.compress(b'{"blueprint": {"entities": []}}' * 100)
    with pytest.raises(BlueprintDecodeError) as excinfo:
        decode_blueprint("0" + base64.b64encode(payload[: len(payload) // 2]).decode())
    assert excinfo.value.code in ("truncated_stream", "invalid_deflate")


# --------------------------------------------------------------------------
# Explicit selection paths
# --------------------------------------------------------------------------
def test_selection_uses_entry_index_values_not_array_offsets(odd_document):
    paths = [entry.path for entry in walk_entries(odd_document)]
    assert paths == [(), (7,), (2,), (4,), (4, 0), (4, 3), (5,)]
    assert select_blueprint(odd_document, [7])["label"] == "fractional and rotated"
    assert select_blueprint(odd_document, [2])["label"] == "translated twin"
    assert select_blueprint(odd_document, [4, 0])["label"] == "leaf under a nested book"
    assert [e.path for e in blueprint_leaves(odd_document)] == [(7,), (2,), (4, 0)]


def test_unknown_and_non_blueprint_paths_are_structured_errors(odd_document):
    for path, code in [
        ([0], "unknown_selection_path"),
        ([7, 2], "unknown_selection_path"),
        ([4], "not_a_blueprint"),
        ([5], "not_a_blueprint"),
        ([4, 3], "not_a_blueprint"),
    ]:
        with pytest.raises(BlueprintDecodeError) as excinfo:
            select_blueprint(odd_document, path)
        assert excinfo.value.code == code, path


def test_malformed_selection_paths(odd_document):
    for path in ["bp/x", [-1], [True], [1.5], 3.5, ["", ""]]:
        with pytest.raises(BlueprintDecodeError) as excinfo:
            select_blueprint(odd_document, path)
        assert excinfo.value.code == "malformed_selection_path", path


def test_selection_path_spellings_agree():
    assert parse_selection_path("bp/2/7") == (2, 7)
    assert parse_selection_path("root") == ()
    assert parse_selection_path(None) == ()
    assert parse_selection_path([2, "7"]) == (2, 7)
    assert parse_selection_path((2, 7)) != parse_selection_path((7, 2))


def test_duplicate_sibling_index_rejected():
    document = {"blueprint_book": {"blueprints": [
        {"index": 1, "blueprint": {"entities": []}},
        {"index": 1, "blueprint": {"entities": []}},
    ]}}
    with pytest.raises(BlueprintDecodeError) as excinfo:
        walk_entries(document)
    assert excinfo.value.code == "duplicate_book_index"


def test_book_entry_without_index_rejected():
    document = {"blueprint_book": {"blueprints": [{"blueprint": {"entities": []}}]}}
    with pytest.raises(BlueprintDecodeError) as excinfo:
        walk_entries(document)
    assert excinfo.value.code == "malformed_book"


def test_unselected_leaves_are_retained_but_not_indexed(odd_document):
    view = build_spatial_view(odd_document, paths=[[7]])
    assert view.selected_paths == ((7,),)
    assert view.unselected_paths == ((2,), (4, 0))
    assert any("unselected blueprint leaves retained" in note for note in view.limitations)
    # The document is still whole: the unselected leaves survive re-encoding.
    assert decode_blueprint(view.encode()) == odd_document
    with pytest.raises(SpatialError) as excinfo:
        view.index([2])
    assert excinfo.value.code == "unknown_selection_path"


def test_leaves_do_not_share_coordinates(odd_document):
    """Identical world coordinates in different leaves never merge."""
    view = build_spatial_view(odd_document)
    assert view.index([7]).by_entity_number(2).position == Point(-0.25, 0.5)
    assert view.index([4, 0]).by_entity_number(1).position == Point(0.5, 0.5)
    keys = {e.key for e in view.entities()}
    assert "bp/7/e/1" in keys and "bp/2/e/1" in keys and "bp/4/0/e/1" in keys
    assert len(keys) == len(view.entities())


# --------------------------------------------------------------------------
# Entity normalization and identity
# --------------------------------------------------------------------------
def test_duplicate_entity_number_within_a_leaf_rejected():
    record = {"entities": [
        {"entity_number": 4, "name": "fast-transport-belt", "position": {"x": 0.5, "y": 0.5}},
        {"entity_number": 4, "name": "fast-transport-belt", "position": {"x": 1.5, "y": 0.5}},
    ]}
    with pytest.raises(SpatialError) as excinfo:
        index_blueprint(record)
    assert excinfo.value.code == "duplicate_entity_id"
    assert excinfo.value.detail["entity_number"] == 4


def test_invalid_positions_and_numbers_rejected():
    def record(entity):
        return {"entities": [entity]}

    cases = [
        ({"entity_number": 1, "name": "x", "position": {"x": "3", "y": 0.5}}, "invalid_position"),
        ({"entity_number": 1, "name": "x", "position": {"x": float("nan"), "y": 0}}, "invalid_position"),
        ({"entity_number": 1, "name": "x", "position": {"x": float("inf"), "y": 0}}, "invalid_position"),
        ({"entity_number": 1, "name": "x", "position": {"y": 0}}, "invalid_position"),
        ({"entity_number": 1, "name": "x"}, "invalid_position"),
        ({"entity_number": 0, "name": "x", "position": {"x": 0, "y": 0}}, "invalid_entity_number"),
        ({"entity_number": True, "name": "x", "position": {"x": 0, "y": 0}}, "invalid_entity_number"),
        ({"name": "x", "position": {"x": 0, "y": 0}}, "invalid_entity_number"),
        ({"entity_number": 1, "position": {"x": 0, "y": 0}}, "invalid_entity"),
        ({"entity_number": 1, "name": "x", "position": {"x": 0, "y": 0}, "direction": 99}, "invalid_direction"),
        ({"entity_number": 1, "name": "x", "position": {"x": 0, "y": 0}, "orientation": 1.0}, "invalid_orientation"),
    ]
    for entity, code in cases:
        with pytest.raises(SpatialError) as excinfo:
            index_blueprint(record(entity))
        assert excinfo.value.code == code, entity


def test_identity_is_deterministic(pilot_document):
    first = build_spatial_view(pilot_document).index()
    second = build_spatial_view(decode_blueprint(encode_blueprint(pilot_document))).index()
    assert [e.id for e in first] == [e.id for e in second]
    assert [e.key for e in first][:3] == ["bp/root/e/1", "bp/root/e/2", "bp/root/e/3"]
    assert first.by_entity_number(1).id == second.by_entity_number(1).id


def test_fractional_coordinates_survive_normalization(odd_document):
    entity = build_spatial_view(odd_document).index([7]).by_entity_number(2)
    assert entity.position == Point(-0.25, 0.5)
    assert entity.footprint.minimum == Point(-0.75, 0.0)
    contract = entity.to_contract_entity()
    assert contract.raw.value()["position"] == {"x": -0.25, "y": 0.5}


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------
def test_non_square_footprint_rotates_with_direction():
    def splitter(direction, x, y):
        record = {"entities": [{"entity_number": 1, "name": "fast-splitter",
                                "position": {"x": x, "y": y}, "direction": direction}]}
        return index_blueprint(record).by_entity_number(1)

    # A 2x1 splitter sits on a half-tile centre along its long axis, exactly as
    # the pilot's do (entity 283 at x=432, y=-93.5).
    north = splitter(0, 0, 0.5)  # 2 wide, 1 tall
    assert (north.footprint.minimum, north.footprint.maximum) == (Point(-1, 0), Point(1, 1))
    assert set(north.tiles()) == {(-1, 0), (0, 0)}
    east = splitter(4, 0.5, 0)  # 1 wide, 2 tall
    assert (east.footprint.minimum, east.footprint.maximum) == (Point(0, -1), Point(1, 1))
    assert set(east.tiles()) == {(0, -1), (0, 0)}
    assert splitter(8, 0, 0.5).footprint == north.footprint
    assert splitter(12, 0.5, 0).footprint == east.footprint
    # A box that straddles a tile boundary covers both tiles, never fewer.
    assert set(splitter(0, 0, 0).tiles()) == {(-1, -1), (0, -1), (-1, 0), (0, 0)}


def test_non_cardinal_direction_is_visible_but_unsupported(odd_document):
    entity = build_spatial_view(odd_document).index([7]).by_entity_number(6)
    assert entity.prototype == "curved-rail-a" and entity.direction == 3
    assert entity.support == "unsupported"
    assert "non_cardinal_direction" in entity.limitations
    # It is still indexed and findable.
    assert entity in build_spatial_view(odd_document).index([7]).occupants(9, 9)


def test_unknown_prototype_keeps_a_visible_limitation(odd_document):
    view = build_spatial_view(odd_document)
    entity = view.index([7]).by_entity_number(6)
    assert entity.geometry_source == "assumed_unit_tile"
    assert "unknown_prototype" in entity.limitations
    assert entity.subsystem == "unknown" and entity.mod == "unknown"
    assert any("no prototype geometry for: curved-rail-a" in n for n in view.limitations)


def test_non_normal_quality_is_unsupported(odd_document):
    entity = build_spatial_view(odd_document).index([7]).by_entity_number(4)
    assert entity.quality == "uncommon"
    assert entity.support == "unsupported"
    assert "non_normal_quality" in entity.limitations


def test_translation_invariance(odd_document):
    """The [2] leaf is the [7] leaf translated by (+1000, +1000)."""
    view = build_spatial_view(odd_document)
    origin, moved = view.index([7]), view.index([2])
    for number in (1, 2):
        a, b = origin.by_entity_number(number), moved.by_entity_number(number)
        assert b.position == Point(a.position.x + 1000, a.position.y + 1000)
        assert b.footprint.minimum == Point(a.footprint.minimum.x + 1000,
                                            a.footprint.minimum.y + 1000)
    assert ([e.entity_number for e in origin.neighbors(1)]
            == [e.entity_number for e in moved.neighbors(1)])


def _rotate_document(record):
    """Rotate a whole blueprint record 90 degrees clockwise about the origin."""
    out = json.loads(json.dumps(record))
    for entity in out["entities"]:
        x, y = entity["position"]["x"], entity["position"]["y"]
        entity["position"] = {"x": -y, "y": x}
        entity["direction"] = (entity.get("direction", 0) + 4) % 16
    return out


def test_rotation_invariance_of_local_adjacency(odd_document):
    record = select_blueprint(odd_document, [7])
    baseline = None
    for turn in range(4):
        index = index_blueprint(record, ())
        adjacency = {
            e.entity_number: sorted(n.entity_number for n in index.neighbors(e, diagonal=True))
            for e in index
        }
        if baseline is None:
            baseline = adjacency
        else:
            assert adjacency == baseline, f"adjacency changed after {turn} quarter turns"
        record = _rotate_document(record)
    # Four quarter turns are the identity, coordinates included.
    assert index_blueprint(record).by_entity_number(1).position == Point(-3.5, 0.5)


# --------------------------------------------------------------------------
# Queries
# --------------------------------------------------------------------------
def test_neighbors_and_occupants_on_the_pilot(pilot_view):
    index = pilot_view.index()
    belt = index.by_entity_number(1)
    assert belt.position == Point(431.5, -107.5)
    assert index.occupants(431, -108) == (belt,)
    assert [e.entity_number for e in index.neighbors(1)] == [2]
    machine = index.by_prototype("assembling-machine-2")[0]
    # A 3x3 machine touches its own tiles plus a 1-tile ring.
    assert len(machine.tiles()) == 9
    assert set(index.entities_in_box(machine.footprint)) >= {machine}


def test_queries_do_not_scan_all_pairs():
    """A local query must consult only its own ring of tiles."""

    class CountingTiles(dict):
        lookups = 0

        def get(self, key, default=None):
            type(self).lookups += 1
            return super().get(key, default)

    def ring_lookups(side):
        record = {"entities": [
            {"entity_number": y * side + x + 1, "name": "fast-transport-belt",
             "position": {"x": x + 0.5, "y": y + 0.5}, "direction": 0}
            for y in range(side) for x in range(side)
        ]}
        index = index_blueprint(record)
        index._tiles = CountingTiles(index._tiles)
        CountingTiles.lookups = 0
        found = index.neighbors(side * (side // 2) + side // 2 + 1)
        return CountingTiles.lookups, len(found), len(index)

    small = ring_lookups(20)  # 400 entities
    large = ring_lookups(100)  # 10000 entities
    assert small[0] == large[0] == 4  # the orthogonal ring of a 1x1 footprint
    assert small[1] == large[1] == 4
    assert small[2] == 400 and large[2] == 10_000


def test_inserter_candidates_are_geometry_with_an_explicit_gate():
    record = {"entities": [
        {"entity_number": 1, "name": "bulk-inserter", "position": {"x": 0.5, "y": 0.5},
         "direction": 0},
        {"entity_number": 2, "name": "fast-transport-belt", "position": {"x": 0.5, "y": -0.5}},
        {"entity_number": 3, "name": "fast-transport-belt", "position": {"x": 0.5, "y": 1.5}},
    ]}
    index = index_blueprint(record)
    candidates = index.inserter_candidates(1)
    # pickup_position [0,-1] and insert_position [0,1.2] in the prototype's own
    # north frame; the entity faces north, so they are not rotated.
    assert candidates.pickup_tile == (0, -1) and candidates.drop_tile == (0, 1)
    assert [e.entity_number for e in candidates.pickup] == [2]
    assert [e.entity_number for e in candidates.drop] == [3]
    assert candidates.candidate_tiles == ((0, -1), (0, 1))
    assert candidates.evidence_status == "documented-only"
    assert ROTATION_SENSE_UNVALIDATED in candidates.limitations
    assert any("inserter.rate.cycle_and_stack: pending" in n for n in candidates.limitations)


def test_inserter_candidates_rotate_with_direction():
    def tiles(direction):
        record = {"entities": [{"entity_number": 1, "name": "bulk-inserter",
                                "position": {"x": 0.5, "y": 0.5}, "direction": direction}]}
        found = index_blueprint(record).inserter_candidates(1)
        return found.pickup_tile, found.drop_tile

    assert tiles(0) == ((0, -1), (0, 1))
    assert tiles(4) == ((1, 0), (-1, 0))
    assert tiles(8) == ((0, 1), (0, -1))
    assert tiles(12) == ((-1, 0), (1, 0))


def test_inserter_candidates_refuse_non_inserters():
    record = {"entities": [{"entity_number": 1, "name": "fast-transport-belt",
                            "position": {"x": 0.5, "y": 0.5}}]}
    with pytest.raises(SpatialError) as excinfo:
        index_blueprint(record).inserter_candidates(1)
    assert excinfo.value.code == "not_an_inserter"


# --------------------------------------------------------------------------
# Contract entities
# --------------------------------------------------------------------------
def test_pilot_entities_match_the_contract_pilot_counts(pilot_view):
    index = pilot_view.index()
    assert len(index) == 2771
    assert index.prototype_counts() == dict(sorted(PILOT_COUNTS.items()))


def test_contract_entities_carry_subsystem_and_mod_claims(pilot_view):
    index = pilot_view.index()
    entities = index.contract_entities()
    assert len(entities) == 2771
    by_prototype = {}
    for entity in entities:
        by_prototype.setdefault(entity.prototype, []).append(entity)

    belt = by_prototype["fast-transport-belt"][0]
    assert (belt.support, belt.subsystem, belt.mod) == ("supported", "transport", "base")
    inserter = by_prototype["bulk-inserter"][0]
    assert (inserter.support, inserter.subsystem, inserter.mod) == ("supported", "inserter", "base")
    machine = by_prototype["assembling-machine-2"][0]
    assert (machine.support, machine.subsystem, machine.mod) == ("supported", "production", "base")

    poles = by_prototype["ee-super-substation"]
    assert len(poles) == 3
    for pole in poles:
        # The base-only 2.0.77 extract cannot classify or size this absent modded
        # prototype. It remains visible with conservative unknown topology.
        assert (pole.support, pole.subsystem, pole.mod) == ("unsupported", "unknown", "unknown")
        assert pole.footprint.maximum.x - pole.footprint.minimum.x == 1.0
        assert pole.raw.value()["name"] == "ee-super-substation"


def test_contract_entity_raw_is_the_original_record(pilot_view):
    index = pilot_view.index()
    machine = index.by_prototype("assembling-machine-2")[0]
    raw = machine.to_contract_entity().raw.value()
    assert raw["recipe"] and raw["recipe_quality"] == "normal"
    assert raw == dict(machine.record)


def test_contract_rejects_an_entity_it_cannot_express():
    record = {"entities": [{"entity_number": 1, "name": "Not-A-Token",
                            "position": {"x": 0.5, "y": 0.5}}]}
    entity = index_blueprint(record).by_entity_number(1)
    assert "non_token_prototype_name" in entity.limitations
    assert entity.support == "unsupported"  # still visible in the index
    with pytest.raises(ContractError):
        entity.to_contract_entity()


def test_odd_document_contract_entities_are_constructible(odd_document):
    view = build_spatial_view(odd_document, paths=[[7]])
    entities = {e.id.entity_number: e for e in view.index([7]).contract_entities()}
    assert entities[1].direction == 4 and entities[1].support == "supported"
    assert entities[4].quality == "uncommon" and entities[4].support == "unsupported"
    assert entities[6].direction == 3 and entities[6].subsystem == "unknown"


# --------------------------------------------------------------------------
# Fixtures and pilot benchmark
# --------------------------------------------------------------------------
def test_checked_in_fixtures_match_their_generator():
    generator = _generator()
    assert json.loads((SPATIAL_FIXTURES / "odd_document.json").read_text()) == generator.ODD_DOCUMENT
    checked_in = json.loads((SPATIAL_FIXTURES / "pilot_sample.json").read_text())
    assert checked_in == json.loads(json.dumps(generator.build_pilot_sample()))


def test_pilot_sample_is_compact_and_covers_the_pilot_prototypes():
    sample = json.loads((SPATIAL_FIXTURES / "pilot_sample.json").read_text())
    assert sample["entity_count"] == len(sample["entities"]) <= 200
    assert set(sample["prototype_counts"]) == set(PILOT_COUNTS)
    pole = [e for e in sample["entities"] if e["prototype"] == "ee-super-substation"]
    assert len(pole) == 1
    assert (pole[0]["support"], pole[0]["subsystem"], pole[0]["mod"]) == (
        "unsupported", "unknown", "unknown")
    assert sample["source"]["file_sha256"].startswith("e48fa3fa")


def test_pilot_index_build_and_queries_are_fast_enough(pilot_document):
    started = time.perf_counter()
    view = build_spatial_view(pilot_document)
    build = time.perf_counter() - started
    index = view.index()

    started = time.perf_counter()
    for entity in index:
        index.neighbors(entity)
    neighbors = time.perf_counter() - started

    started = time.perf_counter()
    candidates = index.inserter_targets()
    targets = time.perf_counter() - started

    assert len(index) == 2771 and len(candidates) == 608
    # Generous ceilings: the measured run is ~33 ms / ~7 ms / ~3 ms. These
    # guard against an accidental all-pairs regression, not machine speed.
    assert build < 5.0, build
    assert neighbors < 5.0, neighbors
    assert targets < 5.0, targets


def test_every_pilot_inserter_has_both_candidate_tiles_occupied(pilot_view):
    """Hand-checkable structural fact, and the reason the rotation sense is a gate.

    Every one of the 608 inserters has a supported entity on *both* candidate
    tiles. The opposite rotation convention keeps the same two tiles and only
    exchanges the roles, so this observation cannot validate the convention --
    which is why `inserter.endpoints.pickup_drop_tiles` stays a release gate.
    """
    index = pilot_view.index()
    pairs = {}
    for candidates in index.inserter_targets():
        assert candidates.pickup and candidates.drop
        key = (candidates.pickup[0].subsystem, candidates.drop[0].subsystem)
        pairs[key] = pairs.get(key, 0) + 1
    assert pairs == {("transport", "production"): 380, ("production", "transport"): 228}
    assert sum(pairs.values()) == 608


def test_view_reports_the_unidentified_mod_limitation(pilot_view):
    assert any("mod origin unidentified for: ee-super-substation" in note
               for note in pilot_view.limitations)


def test_blueprint_hash_is_stable_across_a_round_trip(pilot_view, pilot_document):
    again = build_spatial_view(decode_blueprint(pilot_view.encode()))
    assert again.blueprint_hash() == pilot_view.blueprint_hash()
    assert again.blueprint_hash() == content_hash(pilot_document)


def test_math_helpers_agree_with_tile_floor():
    """Guard the tile convention: a tile owns [n, n+1)."""
    record = {"entities": [{"entity_number": 1, "name": "fast-transport-belt",
                            "position": {"x": -0.5, "y": -0.5}}]}
    index = index_blueprint(record)
    assert index.by_entity_number(1).tiles() == ((-1, -1),)
    assert index.occupants(-1, -1)
    assert not index.occupants(0, 0)
    assert math.floor(-0.5) == -1
