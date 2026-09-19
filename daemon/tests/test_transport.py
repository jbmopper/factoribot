"""Transport mechanics and geometry (routing task 04).

Expectations are derived by hand from the layouts in
`daemon/tests/fixtures/routing_transport/layouts.py` and from task 02's
prototype extract and mechanics records. Nothing here asserts what the
implementation happens to emit.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "routing_transport"
sys.path.insert(0, str(FIXTURES))
import layouts as L  # noqa: E402

from factoribot import transport as tr  # noqa: E402
from factoribot.spatial import build_spatial_view  # noqa: E402
from factoribot.transport_prototypes import load_pinned_extract  # noqa: E402


@pytest.fixture(scope="module")
def extract():
    return load_pinned_extract()


@pytest.fixture(scope="module")
def profile():
    return tr.Profile()


def index_of(entities):
    return build_spatial_view(L.blueprint(entities)).index()


def roles_of(index, extract):
    return tr.entity_roles(index, extract)


# ---------------------------------------------------------------------------
# Evidence status drives semantics, not the other way round
# ---------------------------------------------------------------------------

def test_every_required_mechanics_rule_has_a_record(profile):
    for rule_id in tr.MECHANICS_RULES:
        assert rule_id in profile.rules
        assert profile.rules[rule_id].status in ("observed", "documented-only", "pending")


def test_no_rule_is_observed_yet_so_nothing_may_claim_exact(profile):
    # Task 02 recorded 0 observed / 6 documented-only / 10 pending. If a capture
    # later lands, this test is the place that says the profile may tighten.
    assert profile.unobserved() == tr.MECHANICS_RULES
    for rule_id in tr.MECHANICS_RULES:
        assert profile.semantics(rule_id) == "relaxed"


def test_semantics_and_evidence_kind_track_the_status():
    assert tr.semantics_for("observed") == "exact"
    assert tr.semantics_for("documented-only") == "relaxed"
    assert tr.semantics_for("pending") == "relaxed"
    assert tr.evidence_kind_for("observed") == "observed"
    assert tr.evidence_kind_for("documented-only", bound=True) == "upper_bound"
    assert tr.evidence_kind_for("documented-only") == "estimated"
    # A pending rule must never pass as structural: `unresolved_reasons` accepts
    # structural evidence as proof of a disconnection.
    assert tr.evidence_kind_for("pending") == "estimated"
    with pytest.raises(tr.TransportError):
        tr.semantics_for("probably")


def test_every_named_condition_is_documented():
    names = {
        tr.INSERTER_ROTATION_DOCUMENTED, tr.INSERTER_ROTATION_REVERSED,
        tr.SIDE_LOAD_NEAR_LANE, tr.SIDE_LOAD_FAR_LANE, tr.UNDERGROUND_REACH_EXTENDED,
        tr.UNDERGROUND_PAIRING_BEYOND, tr.UNDERGROUND_LANE_CROSSING,
        tr.UNDERGROUND_EXIT_REAR_FEED,
    }
    assert names == set(tr.CONDITIONS)
    for name, text in tr.CONDITIONS.items():
        assert name.replace("_", "a").isalnum() and name[0].isalpha()
        assert len(text) > 30


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def test_forward_and_right_vectors_are_the_screen_convention():
    assert tr.forward(0) == (0.0, -1.0)   # north, y grows south
    assert tr.forward(4) == (1.0, 0.0)
    assert tr.forward(8) == (0.0, 1.0)
    assert tr.forward(12) == (-1.0, 0.0)
    # Facing north, your right hand points east.
    assert tr.right_of(0) == (1.0, 0.0)
    assert tr.right_of(4) == (0.0, 1.0)
    with pytest.raises(tr.TransportError):
        tr.forward(2)


def test_lane_offsets_sit_a_quarter_tile_either_side():
    assert tr.lane_offset("left", 4) == (0.0, -0.25)
    assert tr.lane_offset("right", 4) == (0.0, 0.25)
    assert tr.lane_offset("left", 0) == (-0.25, 0.0)
    assert tr.other_lane("left") == "right" and tr.other_lane("right") == "left"


def test_rotation_matches_the_spatial_inserter_candidates(extract):
    """The duplicated rotation convention cannot drift from task 03's.

    `spatial` rotates the prototype's pickup/insert offsets itself; this module
    rotates the same offsets for its own geometry. Comparing the two on every
    cardinal direction pins them together.
    """
    proto = extract.by_name(L.INSERTER)
    pickup = proto.derived["pickup_offset_tiles"].value
    drop = proto.derived["drop_offset_tiles"].value
    for direction in tr.CARDINAL:
        index = index_of([L.entity(1, L.INSERTER, 3.5, 3.5, direction)])
        candidates = index.inserter_candidates(1)
        px, py = tr.rotate(pickup["x"], pickup["y"], direction)
        dx, dy = tr.rotate(drop["x"], drop["y"], direction)
        assert (candidates.pickup_position.x, candidates.pickup_position.y) == (3.5 + px, 3.5 + py)
        assert (candidates.drop_position.x, candidates.drop_position.y) == (3.5 + dx, 3.5 + dy)


def test_splitter_halves_cover_its_two_tiles(extract):
    # Facing east at centre (1.5, 1.0): tiles (1, 0) and (1, 1). Looking east,
    # "left" is north, so the left half is the y=0 tile.
    index = index_of(L.splitter_layout())
    splitter = index.by_entity_number(3)
    assert tr.half_tiles(splitter, tr.SPLITTER) == (("left", (1, 0)), ("right", (1, 1)))
    assert tr.emission_tiles(splitter, tr.SPLITTER) == (("left", (2, 0)), ("right", (2, 1)))


def test_an_underground_entrance_emits_nowhere_on_the_surface(extract):
    index = index_of(L.underground_layout())
    roles = roles_of(index, extract)
    entrance = index.by_entity_number(1)
    exit_ = index.by_entity_number(2)
    assert roles[entrance.id] == tr.UNDERGROUND_IN
    assert roles[exit_.id] == tr.UNDERGROUND_OUT
    assert tr.emission_tiles(entrance, tr.UNDERGROUND_IN) == ()
    assert tr.emission_tiles(exit_, tr.UNDERGROUND_OUT) == (("centre", (5, 0)),)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

def test_roles_follow_the_prototype_and_the_underground_type(extract):
    index = index_of([
        L.entity(1, L.BELT, 0.5, 0.5),
        L.entity(2, L.SPLITTER, 2.5, 1.0),
        L.entity(3, L.INSERTER, 5.5, 0.5),
        L.entity(4, L.MACHINE, 9.5, 1.5),
        L.entity(5, L.FURNACE, 14.5, 1.5),
        L.entity(6, L.UNKNOWN_PROTOTYPE, 17.5, 0.5),
        L.entity(7, L.MODDED_POLE, 20.5, 0.5),
    ])
    roles = roles_of(index, extract)
    got = {e.entity_number: roles[e.id] for e in index}
    assert got == {1: tr.BELT, 2: tr.SPLITTER, 3: tr.INSERTER, 4: tr.MACHINE,
                   5: tr.MACHINE, 6: tr.OTHER, 7: tr.OTHER}


def test_an_unsupported_belt_is_never_a_supported_transport_link(extract):
    # A non-cardinal direction is outside the first profile, so `spatial` marks
    # the belt unsupported and it must not carry lanes or handovers.
    index = index_of([L.entity(1, L.BELT, 0.5, 0.5, 2)])
    entity = index.by_entity_number(1)
    assert entity.support == "unsupported"
    assert tr.entity_role(entity, extract) == tr.OTHER


def test_an_unknown_underground_type_is_loud(extract):
    index = index_of([L.entity(1, L.UNDERGROUND, 0.5, 0.5, L.EAST, type="sideways")])
    with pytest.raises(tr.TransportError) as excinfo:
        tr.entity_role(index.by_entity_number(1), extract)
    assert excinfo.value.code == "unknown_underground_type"


# ---------------------------------------------------------------------------
# Handovers
# ---------------------------------------------------------------------------

def handovers(entities, extract):
    index = index_of(entities)
    return index, tr.belt_handovers(index, roles_of(index, extract))


def test_a_straight_run_hands_over_once_per_adjacent_pair(extract):
    index, found = handovers(L.two_lane_run(), extract)
    assert [(h.source.entity_number, h.target.entity_number, h.kind) for h in found] == [
        (1, 2, "straight"), (2, 3, "straight")]
    assert all(h.rear and h.near_side is None for h in found)


def test_a_perpendicular_feed_with_no_rear_feeder_is_a_turn(extract):
    index, found = handovers(L.turn_layout(), extract)
    kinds = {(h.source.entity_number, h.target.entity_number): h.kind for h in found}
    # Belt 1 (east at (0,0)) pushes into belt 2 (north at (1,0)); belt 2's rear
    # tile (1,1) is empty, so this is the curve, not a side-load.
    assert kinds == {(1, 2): "turn", (2, 3): "straight"}


def test_the_same_geometry_becomes_a_side_load_once_a_rear_feeder_exists(extract):
    index, found = handovers(L.side_load_layout(), extract)
    kinds = {(h.source.entity_number, h.target.entity_number): h for h in found}
    assert kinds[(1, 2)].kind == "straight"
    load = kinds[(3, 2)]
    assert load.kind == "side_load"
    # Belt 3 sits west of belt 2; belt 2 faces north, so west is its left side.
    assert load.near_side == "left"


def test_two_belts_facing_each_other_hand_over_nothing(extract):
    index, found = handovers([
        L.entity(1, L.BELT, 0.5, 0.5, L.EAST),
        L.entity(2, L.BELT, 1.5, 0.5, L.WEST),
    ], extract)
    assert found == ()


def test_handover_classification_survives_translation_and_rotation(extract):
    base = L.side_load_layout()
    reference = [(h.source.entity_number, h.target.entity_number, h.kind, h.near_side)
                 for h in handovers(base, extract)[1]]
    assert reference  # the case is not vacuous
    for moved in (L.translate(base, 37, -19), L.translate(base, -4.0, 8.0)):
        assert [(h.source.entity_number, h.target.entity_number, h.kind, h.near_side)
                for h in handovers(moved, extract)[1]] == reference
    for turns in (1, 2, 3):
        assert [(h.source.entity_number, h.target.entity_number, h.kind, h.near_side)
                for h in handovers(L.rotate(base, turns), extract)[1]] == reference


# ---------------------------------------------------------------------------
# Underground pairing
# ---------------------------------------------------------------------------

def test_both_readings_of_max_distance_stay_live(extract):
    reach = tr.underground_reach(L.UNDERGROUND, extract)
    # 2.0.77 gives max_distance no description and the wiki states "4 squares"
    # only for the basic tier, so the two readings differ by exactly one tile.
    assert (reach.max_distance, reach.certain, reach.extended) == (7, 7, 8)
    assert tr.underground_reach("underground-belt", extract).max_distance == 5
    assert tr.underground_reach("express-underground-belt", extract).max_distance == 9


def pairs(entities, extract):
    index = index_of(entities)
    return tr.underground_pairs(index, roles_of(index, extract), extract)


def test_a_pair_inside_the_shorter_reading_is_unconditional(extract):
    found = pairs(L.underground_layout(separation=4), extract)
    assert len(found) == 1
    assert (found[0].separation, found[0].conditions, found[0].certain) == (4, (), True)


def test_a_pair_only_the_longer_reading_admits_is_conditional(extract):
    found = pairs(L.underground_layout(separation=8), extract)
    assert [(p.separation, p.conditions) for p in found] == [
        (8, (tr.UNDERGROUND_REACH_EXTENDED,))]


def test_a_pair_beyond_the_longer_reading_is_dropped(extract):
    assert pairs(L.underground_layout(separation=9), extract) == ()


def test_an_intervening_endpoint_makes_the_far_pairing_conditional(extract):
    # Entrance 1 at tile 0, entrance 3 at tile 2, exit 2 at tile 4, exit 4 at 6.
    found = pairs(L.underground_layout(4, extra_exit_at=6, intervening_at=2), extract)
    got = {(p.entrance.entity_number, p.exit.entity_number): p for p in found}
    assert set(got) == {(1, 2), (1, 4), (3, 2), (3, 4)}
    # Entrance 3 is nearer to exit 2 than entrance 1 is, so 1 -> 2 crosses it.
    assert got[(1, 2)].conditions == (tr.UNDERGROUND_PAIRING_BEYOND,)
    assert got[(1, 4)].conditions == (tr.UNDERGROUND_PAIRING_BEYOND,)
    assert got[(3, 2)].conditions == ()
    assert got[(3, 4)].conditions == (tr.UNDERGROUND_PAIRING_BEYOND,)


def test_a_different_tier_does_not_pair(extract):
    found = pairs([
        L.entity(1, L.UNDERGROUND, 0.5, 0.5, L.EAST, type="input"),
        L.entity(2, "underground-belt", 3.5, 0.5, L.EAST, type="output"),
    ], extract)
    assert found == ()


def test_pairing_survives_rotation(extract):
    base = L.underground_layout(4, extra_exit_at=6, intervening_at=2)
    reference = [(p.entrance.entity_number, p.exit.entity_number, p.separation, p.conditions)
                 for p in pairs(base, extract)]
    for turns in (1, 2, 3):
        assert [(p.entrance.entity_number, p.exit.entity_number, p.separation, p.conditions)
                for p in pairs(L.rotate(base, turns), extract)] == reference


# ---------------------------------------------------------------------------
# Inserters, filters, controls, capacities
# ---------------------------------------------------------------------------

def test_inserter_reach_keeps_both_candidate_tiles_role_free(extract):
    index = index_of(L.inserter_between_belts())
    found = tr.inserter_reaches(index, roles_of(index, extract), extract)
    assert len(found) == 1
    reach = found[0]
    # Facing north at (1,1): pickup offset (0,-1) -> tile (1,0), drop (0,1.2) -> (1,2).
    assert reach.documented_tile == (1, 0) and reach.reversed_tile == (1, 2)
    assert [e.entity_number for e in reach.documented_occupants] == [1]
    assert [e.entity_number for e in reach.reversed_occupants] == [2]
    assert reach.status == "documented-only"


def test_declared_filters_are_read_verbatim_and_never_applied():
    index = index_of(L.inserter_between_belts(filters=("iron-plate", "copper-plate")))
    assert tr.declared_filters(index.by_entity_number(3)) == ("iron-plate", "copper-plate")
    plain = index_of(L.inserter_between_belts())
    assert tr.declared_filters(plain.by_entity_number(3)) == ()
    splitter = index_of(L.splitter_layout())
    assert tr.declared_filters(splitter.by_entity_number(3)) == ("iron-plate",)


def test_circuit_control_is_detected_from_the_record():
    index = index_of(L.inserter_between_belts(control=True))
    assert tr.circuit_controlled(index.by_entity_number(3))
    assert not tr.circuit_controlled(index.by_entity_number(1))


def test_lane_capacities_are_the_documented_per_tier_numbers(extract):
    # speed x 480 across both lanes, halved per lane: 15 / 30 / 45 items/s total.
    assert tr.lane_capacity("transport-belt", extract).items_per_second == 7.5
    assert tr.lane_capacity("fast-transport-belt", extract).items_per_second == 15.0
    assert tr.lane_capacity("express-transport-belt", extract).items_per_second == 22.5
    assert tr.lane_capacity(L.SPLITTER, extract).items_per_second == 15.0
    for name in ("transport-belt", "fast-transport-belt", "express-transport-belt"):
        assert tr.lane_capacity(name, extract).status == "documented-only"


def test_a_prototype_with_no_recorded_lane_capacity_is_an_error(extract):
    with pytest.raises(tr.TransportError) as excinfo:
        tr.lane_capacity(L.MACHINE, extract)
    assert excinfo.value.code == "unknown_lane_capacity"
