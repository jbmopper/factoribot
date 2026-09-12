"""Contract transport graph and structural findings (routing task 04).

Every expectation below is written out by hand from the tile coordinates in
`daemon/tests/fixtures/routing_transport/layouts.py`, the contract's rules and
task 02's prototype numbers. Where a plausible wrong implementation would give a
different answer, the wrong answer is named in a comment so the test discriminates
rather than merely records.

The delivery numbers come from `blueprint_plan.analyze_delivery` (task 05's LP,
not re-implemented here) and each is derived by hand in the test that asserts it.
"""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "routing_transport"
sys.path.insert(0, str(FIXTURES))
import layouts as L  # noqa: E402
import requests as R  # noqa: E402

from factoribot import transport as tr  # noqa: E402
from factoribot.blueprint_contract import (  # noqa: E402
    ITEM_SUBSYSTEMS, EndpointId, EntityId, Material, endpoint_index, parse_graph,
    to_dict, unresolved_reasons,
)
from factoribot.blueprint_plan import analyze_delivery, resolve_model_inputs  # noqa: E402
from factoribot.routing import (  # noqa: E402
    RecipeSource, RoutingOptions, build_transport_graph, entity_token, possible_items,
    reachable_from,
)
from factoribot.spatial import build_spatial_view  # noqa: E402

IRON = Material("item", "iron-plate", "normal")


@pytest.fixture(scope="module")
def recipes():
    return RecipeSource()


def build(entities, **kw):
    return build_transport_graph(build_spatial_view(L.blueprint(entities)), RoutingOptions(**kw))


def graph_of(entities, **kw):
    return build(entities, **kw).graph


def lane(n, side, path=()):
    return EndpointId(EntityId(path, n), "lane", side)


def port(n, name, path=()):
    return EndpointId(EntityId(path, n), "port", name)


def inventory(n, name, path=()):
    return EndpointId(EntityId(path, n), "inventory", name)


def arcs_by_id(graph):
    return {a.id: a for a in graph.arcs}


def groups_by_id(graph):
    return {g.id: g for g in graph.capacity_groups}


def codes(result):
    return sorted(f.code for f in result.findings)


def maximize(graph, feeds, export_endpoint, **kw):
    """A one-budget, one-export maximisation used for the hand-checked numbers."""
    request = R.make_request(
        graph,
        budgets=[R.budget("iron", "iron-plate", 1000)],
        feeds=[R.feed(f"f{i}", "iron", endpoint) for i, endpoint in enumerate(feeds)],
        exports=[R.export("product", "iron-plate", export_endpoint)],
        objective={"kind": "maximize_export", "export_id": "product"},
        **kw,
    )
    return analyze_delivery(graph, request)


def routing_value(report):
    scenarios = {s.stage: s for s in report.result.bounds}
    routing = scenarios.get("routing")
    if routing is None or routing.value is None:
        return None
    return routing.value.value


# ---------------------------------------------------------------------------
# Both lanes, ports, lanes, groups and the canonical crossing
# ---------------------------------------------------------------------------

def test_a_belt_carries_two_independent_lanes_with_hand_written_geometry():
    graph = graph_of(L.two_lane_run())
    endpoints = endpoint_index(graph)

    # Belt 1 covers tile (0, 0) facing east, so its centre is (0.5, 0.5), its
    # rear face x = 0.0 and its front face x = 1.0. Looking east, left is north
    # (y = 0.25) and right is south (y = 0.75).
    expected = {
        port(1, "in_left"): (0.0, 0.25, "incoming"),
        port(1, "out_left"): (1.0, 0.25, "outgoing"),
        port(1, "in_right"): (0.0, 0.75, "incoming"),
        port(1, "out_right"): (1.0, 0.75, "outgoing"),
    }
    for endpoint, (x, y, role) in expected.items():
        got = endpoints[endpoint]
        assert (got.position.x, got.position.y, got.role) == (x, y, role)
        assert got.direction == L.EAST
        assert got.eligibility.kind == "any_item"

    lanes = {x.id: x for x in graph.lanes}
    left = lanes[lane(1, "left")]
    assert left.side == "left"
    assert (left.incoming, left.outgoing) == (port(1, "in_left"), port(1, "out_left"))
    assert left.polyline == (endpoints[left.incoming].position, endpoints[left.outgoing].position)
    assert set(lanes) == {lane(n, s) for n in (1, 2, 3) for s in ("left", "right")}


def test_each_lane_is_one_group_charged_once_by_its_own_traversal_arc():
    graph = graph_of(L.two_lane_run())
    groups, arcs = groups_by_id(graph), arcs_by_id(graph)

    assert sorted(groups) == [
        "e1_left", "e1_right", "e2_left", "e2_right", "e3_left", "e3_right", "handover"]
    for name in ("e1_left", "e2_left", "e3_left"):
        group = groups[name]
        # fast belt: speed 0.0625 x 480 = 30 items/s over two lanes.
        assert (group.kind, group.unit) == ("lane", "items/s")
        assert group.capacity.kind == "finite" and group.capacity.value == 15.0
        assert group.evidence_ids  # the contract requires evidence for a ceiling

    # The one arc charging e2_left is belt 2's own traversal, not either handover.
    charging = [a.id for a in graph.arcs if any(r.group_id == "e2_left" for r in a.resources)]
    assert charging == ["e2_lane_left"]
    traversal = arcs[
        "e2_lane_left"]
    assert (traversal.source, traversal.target) == (port(2, "in_left"), port(2, "out_left"))
    assert [(r.group_id, r.coefficient) for r in traversal.resources] == [("e2_left", 1.0)]

    handover = arcs["e1_centre_to_e2_centre_left"]
    assert (handover.source, handover.target) == (port(1, "out_left"), port(2, "in_left"))
    assert [r.group_id for r in handover.resources] == ["handover"]
    assert groups["handover"].capacity.kind == "unlimited"


def test_a_belt_chain_is_bounded_by_one_lane_not_by_a_per_segment_charge():
    # Hand derivation: feed the left lane of belt 1 without limit; every belt's
    # left lane is a separate 15 items/s resource crossed once, so the chain
    # delivers 15/s. An implementation that charged the target lane on the
    # handover *as well* as on the traversal would charge belt 2 twice and
    # report 7.5; one that copied the ceiling per arc would report 45.
    graph = graph_of(L.two_lane_run())
    assert routing_value(maximize(graph, [lane(1, "left")], lane(3, "left"))) == pytest.approx(15.0)


def test_a_half_belt_feed_does_not_reach_the_other_lane():
    graph = graph_of(L.two_lane_run())
    assert routing_value(maximize(graph, [lane(1, "left")], lane(3, "left"))) == pytest.approx(15.0)
    # Nothing crosses between lanes on a straight run, so the right lane gets 0.
    assert routing_value(maximize(graph, [lane(1, "left")], lane(3, "right"))) == pytest.approx(0.0)
    # Feeding both lanes and exporting one still yields one lane's worth.
    both = maximize(graph, [lane(1, "left"), lane(1, "right")], lane(3, "left"))
    assert routing_value(both) == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Turns and side-loading
# ---------------------------------------------------------------------------

def test_a_turn_preserves_lane_identity_and_claims_no_condition():
    graph = graph_of(L.turn_layout())
    turn = [a for a in graph.arcs if "turn" in a.id]
    assert {a.id for a in turn} == {
        "e1_centre_to_e2_centre_turn_left", "e1_centre_to_e2_centre_turn_right"}
    left = arcs_by_id(graph)["e1_centre_to_e2_centre_turn_left"]
    assert (left.source, left.target) == (port(1, "out_left"), port(2, "in_left"))
    # belt.turn.lane_behavior is pending about throughput, not about identity,
    # so the arc is relaxed and carries no named condition.
    assert (left.semantics, left.conditions) == ("relaxed", ())


def test_a_side_load_keeps_both_target_lanes_open_under_named_conditions():
    graph = graph_of(L.side_load_layout())
    loads = {a.id: a for a in graph.arcs if "sideload" in a.id}
    assert set(loads) == {
        f"e3_centre_to_e2_centre_sideload_{s}_{t}" for s in ("left", "right") for t in ("left", "right")}
    for arc in loads.values():
        assert arc.semantics == "conditional" and len(arc.conditions) == 1
    # Belt 3 sits on belt 2's left (west) side, so the near lane is `left`.
    near = {a.target for a in loads.values() if a.conditions == (tr.SIDE_LOAD_NEAR_LANE,)}
    far = {a.target for a in loads.values() if a.conditions == (tr.SIDE_LOAD_FAR_LANE,)}
    assert near == {port(2, "in_left")} and far == {port(2, "in_right")}


def test_the_optimistic_model_opens_both_side_load_readings_and_says_so():
    graph = graph_of(L.side_load_layout())
    request = R.make_request(
        graph, budgets=[R.budget("iron", "iron-plate", 1000)],
        feeds=[R.feed("f0", "iron", lane(3, "left"))],
        exports=[R.export("product", "iron-plate", lane(2, "right"))],
        objective={"kind": "maximize_export", "export_id": "product"})
    inputs = resolve_model_inputs(graph, request)
    assert not inputs.disabled_arcs
    assert "conditional_connections_open" in inputs.relaxations["routing"]
    # The far-lane reading alone delivers belt 2's right lane, 15/s.
    assert routing_value(analyze_delivery(graph, request)) == pytest.approx(15.0)

    # Under `explicit` control the reading has to be declared, and declaring only
    # the near lane closes the far arcs instead of silently keeping them.
    states = {c: True for c in {c for a in graph.arcs for c in a.conditions}}
    states[tr.SIDE_LOAD_FAR_LANE] = False
    explicit = R.make_request(
        graph, budgets=[R.budget("iron", "iron-plate", 1000)],
        feeds=[R.feed("f0", "iron", lane(3, "left"))],
        exports=[R.export("product", "iron-plate", lane(2, "right"))],
        objective={"kind": "maximize_export", "export_id": "product"},
        control_policy="explicit", controls=R.all_conditions(graph, states))
    assert routing_value(analyze_delivery(graph, explicit)) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Splitters
# ---------------------------------------------------------------------------

def test_a_splitter_shares_its_lane_groups_across_every_path():
    graph = graph_of(L.splitter_layout())
    groups = groups_by_id(graph)
    halves, sides = ("left", "right"), ("left", "right")
    expected = ({f"e3_in_{h}_{s}" for h in halves for s in sides}
                | {f"e3_out_{h}_{s}" for h in halves for s in sides} | {"e3_split"})
    assert expected <= set(groups)
    for name in expected - {"e3_split"}:
        assert groups[name].capacity.value == 15.0
    # splitter.lane_split is pending, so the body's own ceiling is unknown, not
    # a guessed "two belts' worth".
    assert groups["e3_split"].capacity.kind == "unknown"
    assert groups["e3_split"].kind == "splitter"

    internal = [a for a in graph.arcs if a.id.startswith("e3_split_")]
    assert len(internal) == 16  # 2 halves x 2 lanes in, the same out
    for arc in internal:
        assert {r.group_id for r in arc.resources} == {
            f"e3_in_{arc.source.name.removeprefix('in_')}",
            f"e3_out_{arc.target.name.removeprefix('out_')}",
            "e3_split",
        }
    # Four different paths reach one output lane; all four charge that one group.
    into_left_left = [a for a in internal if a.target == port(3, "out_left_left")]
    assert len(into_left_left) == 4
    assert all(any(r.group_id == "e3_out_left_left" for r in a.resources) for a in into_left_left)


def test_multiple_splitter_paths_cannot_each_claim_the_full_capacity():
    # Hand derivation: feed all four input lanes without limit. Every path into
    # the left half's left output crosses `e3_out_left_left`, one 15 items/s
    # resource, so exporting straight off that port yields 15/s. A model that
    # copied the ceiling per arc would report 4 x 15 = 60.
    graph = graph_of(L.splitter_layout())
    feeds = [lane(1, "left"), lane(1, "right"), lane(2, "left"), lane(2, "right")]
    report = maximize(graph, feeds, port(3, "out_left_left"))
    assert routing_value(report) == pytest.approx(15.0)


def test_a_splitter_filter_is_recorded_and_relaxed_never_applied():
    result = build(L.splitter_layout(filters=True))
    graph = result.graph
    internal = [a for a in graph.arcs if a.id.startswith("e3_split_")]
    # The blueprint declares filter "iron-plate" and output_priority "left".
    # Applying either would restrict an optimistic upper bound on unobserved
    # mechanics, so eligibility stays open and the declaration becomes a finding.
    assert all(a.eligibility.kind == "any_item" for a in internal)
    relaxed = [f for f in result.findings if f.code == "splitter_distribution_relaxed"]
    assert len(relaxed) == 1
    assert "iron-plate" in relaxed[0].message and "output_priority" in relaxed[0].message
    assert graph.entities[2].raw.value()["filter"] == "iron-plate"  # retained verbatim

    # A copper plate is therefore still deliverable through a splitter filtered
    # to iron: 15/s, the output lane ceiling. A filter-applying implementation
    # would report 0 and could turn a satisfiable request into a false shortfall.
    request = R.make_request(
        graph, budgets=[R.budget("copper", "copper-plate", 1000)],
        feeds=[R.feed("f0", "copper", lane(1, "left"))],
        exports=[R.export("product", "copper-plate", port(3, "out_left_left"))],
        objective={"kind": "maximize_export", "export_id": "product"})
    assert routing_value(analyze_delivery(graph, request)) == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Underground belts
# ---------------------------------------------------------------------------

def test_a_tunnel_maps_lanes_straight_and_keeps_crossing_conditional():
    graph = graph_of(L.underground_layout(separation=4))
    tunnel = {a.id: a for a in graph.arcs if "tunnel" in a.id}
    assert set(tunnel) == {f"e1_tunnel_e2_{s}_{t}" for s in ("left", "right") for t in ("left", "right")}
    straight = tunnel["e1_tunnel_e2_left_left"]
    assert (straight.source, straight.target) == (port(1, "out_left"), port(2, "in_left"))
    assert (straight.semantics, straight.conditions) == ("relaxed", ())
    crossed = tunnel["e1_tunnel_e2_left_right"]
    assert (crossed.semantics, crossed.conditions) == ("conditional", (tr.UNDERGROUND_LANE_CROSSING,))


def test_the_ambiguous_reach_is_a_condition_not_a_silent_choice():
    # fast underground max_distance is 7; separation 7 is admitted by both
    # readings, separation 8 only by "tiles between", separation 9 by neither.
    inside = graph_of(L.underground_layout(separation=7))
    assert arcs_by_id(inside)["e1_tunnel_e2_left_left"].conditions == ()
    edge = graph_of(L.underground_layout(separation=8))
    assert arcs_by_id(edge)["e1_tunnel_e2_left_left"].conditions == (tr.UNDERGROUND_REACH_EXTENDED,)
    beyond = build(L.underground_layout(separation=9))
    assert not [a for a in beyond.graph.arcs if "tunnel" in a.id]
    assert "underground_unpaired" in codes(beyond)


def test_a_tunnel_mouth_is_never_offered_as_an_external_interface():
    result = build(L.underground_layout(separation=9))  # beyond both readings
    ports = {p.id: p for p in result.graph.ports}
    # The entrance's rear and the exit's front face empty surface tiles, so they
    # are open interfaces; the entrance's front and the exit's rear are the
    # tunnel, and an unpaired tunnel is a break, not a place to declare a feed.
    assert ports[port(1, "in_left")].boundary_candidate
    assert ports[port(2, "out_left")].boundary_candidate
    assert not ports[port(1, "out_left")].boundary_candidate
    assert not ports[port(2, "in_left")].boundary_candidate
    unpaired = [f for f in result.findings if f.code == "underground_unpaired"]
    assert {f.entity_ids[0].entity_number for f in unpaired} == {1, 2}


def test_conflicting_underground_endpoints_stay_available_and_are_reported():
    result = build(L.underground_layout(4, extra_exit_at=6, intervening_at=2))
    tunnels = {a.id for a in result.graph.arcs if "tunnel" in a.id}
    # Four candidate pairings x four lane mappings; none is deleted.
    assert len(tunnels) == 16
    beyond = [a for a in result.graph.arcs
              if tr.UNDERGROUND_PAIRING_BEYOND in a.conditions]
    assert {a.id.split("_tunnel_")[0] for a in beyond} == {"e1", "e3"}
    ambiguous = [f for f in result.findings if f.code == "underground_pairing_ambiguous"]
    assert {f.entity_ids[0].entity_number for f in ambiguous} == {1, 3}


def test_feeding_an_underground_entrance_is_plain_but_feeding_an_exit_is_conditional():
    entrance = graph_of(L.belt_into_underground(exit_first=False))
    into_entrance = [a for a in entrance.arcs if a.source.entity.entity_number == 1
                     and a.target.entity.entity_number == 2]
    assert len(into_entrance) == 2  # one per lane
    assert all(a.conditions == () and a.semantics == "relaxed" for a in into_entrance)

    exit_ = graph_of(L.belt_into_underground(exit_first=True))
    into_exit = [a for a in exit_.arcs if a.source.entity.entity_number == 1
                 and a.target.entity.entity_number == 2]
    assert len(into_exit) == 2
    assert all(a.conditions == (tr.UNDERGROUND_EXIT_REAR_FEED,) for a in into_exit)
    assert all(a.semantics == "conditional" for a in into_exit)


# ---------------------------------------------------------------------------
# Inserters
# ---------------------------------------------------------------------------

def test_both_inserter_rotation_senses_remain_possible():
    graph = graph_of(L.inserter_between_belts())
    # Documented sense: pick from the belt one tile north (entity 1), drop on the
    # belt two tiles south (entity 2). Reversed: exactly the opposite roles.
    assert {a.source for a in graph.arcs if a.conditions == (tr.INSERTER_ROTATION_DOCUMENTED,)
            and a.target == port(3, "hand")} == {lane(1, "left"), lane(1, "right")}
    assert {a.target for a in graph.arcs if a.conditions == (tr.INSERTER_ROTATION_DOCUMENTED,)
            and a.source == port(3, "hand")} == {lane(2, "left"), lane(2, "right")}
    assert {a.source for a in graph.arcs if a.conditions == (tr.INSERTER_ROTATION_REVERSED,)
            and a.target == port(3, "hand")} == {lane(2, "left"), lane(2, "right")}
    # No arc is unconditional, so neither convention is silently adopted.
    assert all(a.semantics == "conditional" for a in graph.arcs if a.id.startswith("e3_"))


def test_an_inserter_charges_its_one_unknown_group_once_per_traversal():
    result = build(L.inserter_between_belts())
    groups = groups_by_id(result.graph)
    assert groups["e3_hand"].kind == "inserter"
    # inserter.rate.cycle_and_stack yields no items/s from the prototype and hand
    # size depends on unrecorded research, so the ceiling is `unknown`, never a
    # guessed number and never silently omitted.
    assert groups["e3_hand"].capacity.kind == "unknown"
    charging = {a.id for a in result.graph.arcs if any(r.group_id == "e3_hand" for r in a.resources)}
    # Only the pickup legs charge it: a traversal crosses the hand once.
    assert charging == {"e3_pick_doc_0", "e3_pick_doc_1", "e3_pick_rev_0", "e3_pick_rev_1"}
    assert "inserter_capacity_unknown" in codes(result)
    assert "inserter_rotation_unresolved" in codes(result)


def test_an_unknown_inserter_capacity_is_relaxed_upward_not_used_as_a_ceiling():
    graph = graph_of(L.inserter_between_belts())
    report = maximize(graph, [lane(1, "left")], lane(2, "right"))
    inputs = report.inputs
    assert "e3_hand" in inputs.unknown_groups
    assert "unknown_capacity_unlimited" in inputs.relaxations["routing"]
    # Belt 2's right lane still caps the delivery at 15/s.
    assert routing_value(report) == pytest.approx(15.0)


def test_a_circuit_controlled_inserter_adds_a_named_condition_per_entity():
    result = build(L.inserter_between_belts(control=True))
    inserter_arcs = [a for a in result.graph.arcs if a.id.startswith("e3_")]
    assert inserter_arcs
    for arc in inserter_arcs:
        assert "circuit_e3" in arc.conditions and arc.semantics == "conditional"
    # Declaring that condition disabled removes those arcs and nothing else.
    graph = result.graph
    states = {c: True for c in {c for a in graph.arcs for c in a.conditions}}
    states["circuit_e3"] = False
    request = R.make_request(
        graph, budgets=[R.budget("iron", "iron-plate", 1000)],
        feeds=[R.feed("f0", "iron", lane(1, "left"))],
        exports=[R.export("product", "iron-plate", lane(2, "left"))],
        objective={"kind": "maximize_export", "export_id": "product"},
        control_policy="explicit", controls=R.all_conditions(graph, states))
    inputs = resolve_model_inputs(graph, request)
    assert set(inputs.disabled_arcs) == {a.id for a in inserter_arcs}
    assert routing_value(analyze_delivery(graph, request)) == pytest.approx(0.0)


def test_an_inserter_filter_is_recorded_and_relaxed():
    result = build(L.inserter_between_belts(filters=("iron-plate",)))
    relaxed = [f for f in result.findings if f.code == "item_filter_relaxed"]
    assert len(relaxed) == 1 and "iron-plate" in relaxed[0].message
    assert all(a.eligibility.kind == "any_item" for a in result.graph.arcs)


# ---------------------------------------------------------------------------
# Machines, direct insertion, blocked output
# ---------------------------------------------------------------------------

def test_a_machine_gets_inventories_and_one_shared_machine_time_group(recipes):
    result = build(L.machine_chain(), recipes=recipes)
    graph = result.graph
    assert {i.id for i in graph.inventories} == {inventory(1, "input"), inventory(1, "output")}
    assert len(graph.activities) == 1
    activity = graph.activities[0]
    # assembling-machine-2 crafting speed 0.75, iron-gear-wheel energy 0.5 s:
    # 1.5 crafts/s, 2 iron plates in, 1 gear out, 1/1.5 s of machine time.
    assert activity.recipe == "iron-gear-wheel"
    assert activity.craft_capacity.value == pytest.approx(1.5)
    assert [(m.material.name, m.amount_per_craft) for m in activity.inputs] == [("iron-plate", 2.0)]
    assert [(m.material.name, m.amount_per_craft) for m in activity.outputs] == [("iron-gear-wheel", 1.0)]
    assert activity.resources[0].coefficient == pytest.approx(1 / 1.5)
    time_group = groups_by_id(graph)[activity.resources[0].group_id]
    assert (time_group.kind, time_group.unit) == ("machine_time", "seconds/s")
    assert time_group.capacity.value == 1.0
    assert activity.inputs[0].endpoint == inventory(1, "input")
    assert activity.outputs[0].endpoint == inventory(1, "output")


def test_standing_on_a_machine_footprint_is_not_an_endpoint(recipes):
    # The machine covers tiles 1..3; the supply inserter's own tile is (2, 0),
    # outside it, and its candidate tiles are (2, -1) and (2, 1). Only those two
    # produce endpoints; no arc is created just because a tile is covered.
    graph = graph_of(L.machine_chain(), recipes=recipes)
    touching_machine = {a.source for a in graph.arcs if a.target == inventory(1, "input")}
    assert touching_machine == {port(3, "hand"), port(4, "hand")}
    assert not any(a.source.entity == a.target.entity and a.source.kind == "inventory"
                   for a in graph.arcs)


def test_a_machine_with_no_inserter_is_a_disconnected_producer(recipes):
    result = build(L.machine_chain(supply=False, drain=False), recipes=recipes)
    assert "disconnected_producer" in codes(result)
    assert not result.graph.arcs
    # It is still a visible entity with activities; it is not deleted.
    assert len(result.graph.activities) == 1


def test_a_machine_whose_products_cannot_leave_is_reported_as_blocked(recipes):
    result = build(L.direct_insertion(), recipes=recipes)
    blocked = [f for f in result.findings if f.code == "blocked_output"]
    assert {f.entity_ids[0].entity_number for f in blocked} == {1, 3}
    assert "direct_insertion" in codes(result)
    # The two machines are connected to each other, so neither is "disconnected".
    assert "disconnected_producer" not in codes(result)


def test_direct_insertion_links_two_machine_inventories(recipes):
    graph = graph_of(L.direct_insertion(), recipes=recipes)
    assert {(a.source, a.target) for a in graph.arcs} == {
        (inventory(1, "output"), port(2, "hand")),
        (port(2, "hand"), inventory(3, "input")),
        (inventory(3, "output"), port(2, "hand")),
        (port(2, "hand"), inventory(1, "input")),
    }


def test_a_fluid_recipe_produces_no_activity_and_says_why(recipes):
    result = build(L.machine_with_fluid_recipe(), recipes=recipes)
    # plastic-bar consumes petroleum gas; the first profile rejects fluids, so
    # the machine keeps its inventories and gets no activity at all.
    assert result.graph.activities == ()
    fluid = [f for f in result.findings if f.code == "recipe_uses_fluid"]
    assert len(fluid) == 1 and "petroleum-gas" in fluid[0].message


def test_an_unknown_recipe_name_produces_no_activity(recipes):
    result = build([L.entity(1, L.MACHINE, 1.5, 1.5, L.NORTH, recipe="not-a-real-recipe")],
                   recipes=recipes)
    assert result.graph.activities == ()
    assert "recipe_unavailable" in codes(result)


def test_a_furnace_without_declared_candidates_gets_no_invented_recipe(recipes):
    plain = build([L.entity(1, L.FURNACE, 1.5, 1.5, L.NORTH)], recipes=recipes)
    assert plain.graph.activities == ()
    assert plain.graph.entities[0].furnace_candidates == ()
    assert "machine_recipe_unresolved" in codes(plain)

    declared = build([L.entity(1, L.FURNACE, 1.5, 1.5, L.NORTH)], recipes=recipes,
                     furnace_candidates=("iron-plate", "copper-plate"))
    assert {a.recipe for a in declared.graph.activities} == {"iron-plate", "copper-plate"}
    assert declared.graph.entities[0].furnace_candidates == ("iron-plate", "copper-plate")
    # electric furnace speed 2.0, smelting energy 3.2 s -> 0.625 crafts/s.
    assert all(a.craft_capacity.value == pytest.approx(0.625) for a in declared.graph.activities)
    # Alternatives share the entity's one machine-time group.
    assert len({a.resources[0].group_id for a in declared.graph.activities}) == 1
    # Two candidates and no override: the contract must withhold every bound.
    request = R.make_request(
        declared.graph, budgets=[R.budget("ore", "iron-ore", 10)],
        exports=[R.export("product", "iron-plate", inventory(1, "output"))])
    assert any(r.startswith("ambiguous furnace") for r in unresolved_reasons(request, declared.graph))


# ---------------------------------------------------------------------------
# Boundaries, breaks and unsupported topology
# ---------------------------------------------------------------------------

def test_open_lane_ends_and_blocked_lane_ends_are_different_findings():
    result = build(L.unsupported_bridge())
    graph = result.graph
    ports = {p.id: p for p in graph.ports}
    # Belt 1's rear faces an empty tile: an open interface, nothing implied.
    assert ports[port(1, "in_left")].boundary_candidate
    # Its front faces the chest, which offers no supported handover: a break.
    assert not ports[port(1, "out_left")].boundary_candidate
    assert {"transport_boundary_candidate", "transport_internal_break"} <= set(codes(result))
    boundary = next(f for f in result.findings if f.code == "transport_boundary_candidate")
    assert "not a declared feed or export" in boundary.message


def test_no_supply_is_inferred_from_a_dangling_belt():
    graph = graph_of(L.two_lane_run())
    # Nothing enters unless a feed is declared: with no feed the export is 0.
    request = R.make_request(
        graph, budgets=[R.budget("iron", "iron-plate", 1000)], feeds=[],
        exports=[R.export("product", "iron-plate", lane(3, "left"))],
        objective={"kind": "maximize_export", "export_id": "product"})
    assert routing_value(analyze_delivery(graph, request)) == pytest.approx(0.0)


def test_an_unsupported_item_capable_entity_is_a_possible_bridge():
    result = build(L.unsupported_bridge())
    assert len(result.graph.topology_gaps) == 1
    gap = result.graph.topology_gaps[0]
    assert gap.may_connect is True
    assert gap.entity_ids == (EntityId((), 2),)
    assert set(gap.possible_endpoints) == {lane(n, s) for n in (1, 3) for s in ("left", "right")}
    assert "unsupported_possible_bridge" in codes(result)


def test_an_unknown_possible_bridge_never_becomes_a_proven_disconnection():
    graph = graph_of(L.unsupported_bridge())
    request = R.make_request(
        graph, budgets=[R.budget("iron", "iron-plate", 1000)],
        feeds=[R.feed("f0", "iron", lane(1, "left"))],
        exports=[R.export("product", "iron-plate", lane(3, "left"), rate=1.0)],
        objective={"kind": "maximize_export", "export_id": "product"})
    reasons = unresolved_reasons(request, graph)
    assert reasons == ("unsupported topology: gap_e2",)
    report = analyze_delivery(graph, request)
    # The two belt runs are not linked by any arc, yet the result must be
    # `partial` with no bound -- never `insufficient`, which would assert that
    # the requested 1/s is impossible.
    assert report.result.status == "partial"
    assert report.result.bounds == ()
    assert not any(g.may_connect is False for g in graph.topology_gaps)
    assert not reachable_from(graph, [port(1, "in_left")]) & {port(3, "in_left")}


def test_a_non_item_subsystem_is_left_to_the_requests_declaration():
    result = build(L.modded_pole_beside_belt())
    graph = result.graph
    # No gap is written for a power entity: writing `may_connect: true` would
    # withhold every bound whatever the request declares, and `may_connect: false`
    # would assert a disconnection this module cannot prove.
    assert graph.topology_gaps == ()
    assert "unsupported_non_item_entity" in codes(result)
    assert graph.entities[3].subsystem == "power"
    assert graph.entities[3].subsystem not in ITEM_SUBSYSTEMS

    plain = R.make_request(
        graph, budgets=[R.budget("iron", "iron-plate", 1000)],
        feeds=[R.feed("f0", "iron", lane(1, "left"))],
        exports=[R.export("product", "iron-plate", lane(3, "left"))],
        objective={"kind": "maximize_export", "export_id": "product"})
    assert unresolved_reasons(plain, graph) == ("unsupported entity: bp/root/e/4",)

    declared = R.make_request(
        graph, budgets=[R.budget("iron", "iron-plate", 1000)],
        feeds=[R.feed("f0", "iron", lane(1, "left"))],
        exports=[R.export("product", "iron-plate", lane(3, "left"))],
        objective={"kind": "maximize_export", "export_id": "product"},
        irrelevant=[R.irrelevance(graph, "power", "power_assumed_available")])
    assert unresolved_reasons(declared, graph) == ()
    assert routing_value(analyze_delivery(graph, declared)) == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Item propagation
# ---------------------------------------------------------------------------

def test_items_propagate_from_declared_feeds_and_fixed_recipe_outputs(recipes):
    graph = graph_of(L.machine_chain(), recipes=recipes)
    reached = possible_items(graph, {lane(2, "left"): frozenset({IRON})})
    gear = Material("item", "iron-gear-wheel", "normal")
    assert reached[inventory(1, "input")] == frozenset({IRON, gear})
    assert reached[inventory(1, "output")] == frozenset({gear})
    assert reached[port(5, "out_left")] == frozenset({gear})
    # Nothing enters at an undeclared endpoint.
    assert possible_items(graph, {}) == {}


def test_an_unknown_feed_identity_never_proves_an_input_unreachable(recipes):
    graph = graph_of(L.machine_chain(), recipes=recipes)
    unknown = possible_items(graph, {lane(2, "left"): None})
    # `None` means "anything is possible here" and stays that way downstream, so
    # no filter or recipe input can be declared incompatible on its account.
    assert unknown[inventory(1, "input")] is None
    assert unknown[port(3, "hand")] is None
    # The machine still fires, so its fixed output propagates as a known item.
    assert unknown[inventory(1, "output")] == frozenset(
        {Material("item", "iron-gear-wheel", "normal")})
    known = possible_items(graph, {lane(2, "left"): frozenset({IRON})})
    assert set(unknown) == set(known)


def test_reachability_counts_conditional_arcs():
    graph = graph_of(L.inserter_between_belts(control=True))
    # Every arc through the inserter is conditional. Dropping them and then
    # calling belt 2 unreachable would be exactly the unsound step the contract
    # forbids, so reachability keeps them.
    assert port(3, "hand") in reachable_from(graph, [port(1, "in_left")])
    assert port(2, "in_left") in reachable_from(graph, [port(1, "in_left")])


# ---------------------------------------------------------------------------
# Invariants of every graph this module builds
# ---------------------------------------------------------------------------

ALL_LAYOUTS = [
    ("two_lane_run", L.two_lane_run()),
    ("turn", L.turn_layout()),
    ("side_load", L.side_load_layout()),
    ("filtered_splitter", L.splitter_layout()),
    ("underground", L.underground_layout(4, extra_exit_at=6, intervening_at=2)),
    ("inserter", L.inserter_between_belts(control=True, filters=("iron-plate",))),
    ("machine_chain", L.machine_chain()),
    ("direct_insertion", L.direct_insertion()),
    ("unsupported_bridge", L.unsupported_bridge()),
    ("modded_pole", L.modded_pole_beside_belt()),
]


@pytest.mark.parametrize("name,entities", ALL_LAYOUTS, ids=[n for n, _ in ALL_LAYOUTS])
def test_no_arc_claims_exact_semantics_while_no_rule_is_observed(name, entities, recipes):
    graph = graph_of(entities, recipes=recipes)
    assert all(a.semantics in ("relaxed", "conditional") for a in graph.arcs)
    for arc in graph.arcs:
        assert arc.resources and arc.evidence_ids
        assert (arc.semantics == "conditional") == bool(arc.conditions)
    for group in graph.capacity_groups:
        assert group.evidence_ids
    for activity in graph.activities:
        assert activity.evidence_ids and len(activity.resources) == 1


@pytest.mark.parametrize("name,entities", ALL_LAYOUTS, ids=[n for n, _ in ALL_LAYOUTS])
def test_the_graph_round_trips_through_the_contract_parser(name, entities, recipes):
    graph = graph_of(entities, recipes=recipes)
    again = parse_graph(to_dict(graph))
    assert again == graph
    assert again.graph_hash == graph.graph_hash


@pytest.mark.parametrize("name,entities", ALL_LAYOUTS, ids=[n for n, _ in ALL_LAYOUTS])
def test_building_the_same_layout_twice_is_deterministic(name, entities, recipes):
    first = graph_of(entities, recipes=recipes)
    second = graph_of(entities, recipes=recipes)
    assert first.graph_hash == second.graph_hash
    assert [a.id for a in first.arcs] == [a.id for a in second.arcs]


@pytest.mark.parametrize("name,entities", ALL_LAYOUTS, ids=[n for n, _ in ALL_LAYOUTS])
def test_translation_preserves_the_whole_graph_structure(name, entities, recipes):
    reference = graph_of(entities, recipes=recipes)
    moved = graph_of(L.translate(entities, 100, -250), recipes=recipes)
    assert [a.id for a in moved.arcs] == [a.id for a in reference.arcs]
    assert [(a.source, a.target, a.semantics, a.conditions) for a in moved.arcs] == \
           [(a.source, a.target, a.semantics, a.conditions) for a in reference.arcs]
    assert to_dict(moved.capacity_groups) == to_dict(reference.capacity_groups)
    assert [g.id for g in moved.topology_gaps] == [g.id for g in reference.topology_gaps]


@pytest.mark.parametrize("name,entities", ALL_LAYOUTS, ids=[n for n, _ in ALL_LAYOUTS])
@pytest.mark.parametrize("turns", (1, 2, 3))
def test_supported_rotation_preserves_the_whole_graph_structure(name, entities, turns, recipes):
    reference = graph_of(entities, recipes=recipes)
    turned = graph_of(L.rotate(entities, turns), recipes=recipes)
    assert [(a.id, a.source, a.target, a.semantics, a.conditions) for a in turned.arcs] == \
           [(a.id, a.source, a.target, a.semantics, a.conditions) for a in reference.arcs]
    assert to_dict(turned.capacity_groups) == to_dict(reference.capacity_groups)
    assert [(x.id, x.side, x.incoming, x.outgoing) for x in turned.lanes] == \
           [(x.id, x.side, x.incoming, x.outgoing) for x in reference.lanes]


def test_entity_tokens_distinguish_book_paths():
    assert entity_token(EntityId((), 7)) == "e7"
    assert entity_token(EntityId((2, 7), 1)) == "p2_7_e1"
    assert entity_token(EntityId((7, 2), 1)) == "p7_2_e1"


def test_a_book_leaf_is_selected_by_book_index_not_array_offset():
    entities = L.two_lane_run()
    document = L.book([(7, entities), (2, L.turn_layout())])
    view = build_spatial_view(document, [[2]])
    result = build_transport_graph(view, RoutingOptions(book_path=(2,)))
    assert result.graph.selected_paths == ((2,),)
    assert {e.id.book_path for e in result.graph.entities} == {(2,)}
    # Leaf 2 holds the turn layout, whose second handover is the curve.
    assert any("turn" in a.id for a in result.graph.arcs)


# ---------------------------------------------------------------------------
# The development pilot: size, shape and unsupported mechanics
# ---------------------------------------------------------------------------

PILOT = Path(__file__).resolve().parent / "fixtures" / "wip_science.txt"


@pytest.fixture(scope="module")
def pilot(recipes):
    from factoribot.spatial import load_spatial_view

    view = load_spatial_view(PILOT.read_text())
    return build_transport_graph(view, RoutingOptions(
        provenance="development_pilot", recipes=recipes))


def test_the_pilot_graph_has_hand_derivable_counts(pilot):
    """2771 entities: 1738 belts, 178 undergrounds, 15 splitters, 608 inserters,
    153 AM2, 76 furnaces, 3 modded poles (contract, "Development pilot").

    Ports: 1916 belt-like entities x 4 + 15 splitters x 8 + 608 inserter hands
    = 7664 + 120 + 608 = 8392. Lanes: 1916 x 2 = 3832. Inventories: 229
    machines x 2 = 458. Groups: 3832 belt lanes + 120 splitter lanes + 608
    inserter hands + 15 splitter bodies + 153 machine-time + 1 handover = 4729.
    """
    counts = pilot.counts()
    assert counts["entities"] == 2771
    assert counts["ports"] == 8392
    assert counts["lanes"] == 3832
    assert counts["inventories"] == 458
    assert counts["capacity_groups"] == 4729
    assert counts["activities"] == 153  # the 153 AM2 recipes; furnaces stay unresolved
    kinds = {}
    for group in pilot.graph.capacity_groups:
        kinds[group.kind] = kinds.get(group.kind, 0) + 1
    assert kinds == {"lane": 3952, "inserter": 608, "splitter": 15,
                     "machine_time": 153, "other": 1}


def test_the_pilot_arc_count_decomposes_by_mechanic(pilot):
    """3832 lane traversals + 240 splitter paths + 3612 handovers (1806 pairs x
    2 lanes) + 328 tunnel arcs (82 pairings x 4 lane mappings) + 3648 inserter
    legs (608 inserters x 2 senses x pickup/drop endpoints) = 11660.
    """
    arcs = pilot.graph.arcs
    assert len(arcs) == 11660
    traversal = [a for a in arcs if "_lane_" in a.id]
    splitter = [a for a in arcs if "_split_" in a.id]
    tunnel = [a for a in arcs if "_tunnel_" in a.id]
    inserter = [a for a in arcs if "_pick_" in a.id or "_drop_" in a.id]
    handover = [a for a in arcs if a not in traversal + splitter + tunnel + inserter]
    assert (len(traversal), len(splitter), len(tunnel), len(inserter)) == (3832, 240, 328, 3648)
    assert len(handover) == 3612
    # No arc claims exact semantics, because no mechanics rule is observed.
    assert {a.semantics for a in arcs} == {"relaxed", "conditional"}


def test_the_pilot_reports_its_unsupported_mechanics_and_advertises_no_bound(pilot):
    # Every rule the graph relies on is unobserved and reported by name.
    reported = {f.message.split(" is ")[0] for f in pilot.findings
                if f.code == "mechanics_unobserved"}
    assert reported == {
        "belt.straight.lane_capacity", "belt.transfer.belt_to_belt",
        "belt.turn.lane_behavior", "underground.pairing.range",
        "underground.pairing.conflict", "underground.lane_mapping",
        "splitter.lane_split", "splitter.priority_and_filter",
        "inserter.endpoints.pickup_drop_tiles", "inserter.rate.cycle_and_stack",
        "machine.activity.assembling_machine_2",
    }
    counted = {}
    for finding in pilot.findings:
        counted[finding.code] = counted.get(finding.code, 0) + 1
    # The three ee-super-substations are power entities: reported, never turned
    # into a topology gap, and never silently declared irrelevant here.
    assert counted["unsupported_non_item_entity"] == 3
    assert pilot.graph.topology_gaps == ()
    assert counted["machine_recipe_unresolved"] == 76   # the furnaces
    assert counted["item_filter_relaxed"] == 152        # filtered bulk inserters
    assert counted["splitter_distribution_relaxed"] == 15
    # 92 entrances and 86 exits form 82 pairings on distinct exits, so 10
    # entrances and 4 exits have no far end at all.
    assert counted["underground_unpaired"] == 14

    # A request that declares nothing about the poles must withhold every bound.
    request = R.make_request(
        pilot.graph, budgets=[R.budget("iron", "iron-plate", 60)],
        exports=[R.export("product", "iron-plate",
                          [p.id for p in pilot.graph.ports if p.boundary_candidate
                           and p.role == "outgoing"][0])])
    reasons = unresolved_reasons(request, pilot.graph)
    assert len(reasons) == 3 and all(r.startswith("unsupported entity") for r in reasons)


def test_the_pilot_graph_is_accepted_by_the_delivery_adapter(pilot):
    """The LP's adapter boundary consumes the real graph unchanged.

    `build_transport_graph` already ran the graph through `parse_graph`, so this
    checks the next hop: `resolve_model_inputs` interprets every arc, group and
    activity without a second schema of its own.
    """
    outgoing = [p.id for p in pilot.graph.ports if p.boundary_candidate and p.role == "outgoing"]
    incoming = [p.id for p in pilot.graph.ports if p.boundary_candidate and p.role == "incoming"]
    assert outgoing and incoming
    request = R.make_request(
        pilot.graph, budgets=[R.budget("iron", "iron-plate", 60)],
        feeds=[R.feed("f0", "iron", incoming[0])],
        exports=[R.export("product", "iron-plate", outgoing[0])],
        irrelevant=[R.irrelevance(pilot.graph, "power", "power_assumed_available")])
    inputs = resolve_model_inputs(pilot.graph, request)
    assert len(inputs.arcs) == len(pilot.graph.arcs)      # relax_open disables none
    assert not inputs.disabled_arcs
    assert len(inputs.activities) == 153
    assert "unknown_capacity_unlimited" in inputs.relaxations["routing"]
    assert "conditional_connections_open" in inputs.relaxations["routing"]
    assert pilot.stats["build_seconds"] > 0
