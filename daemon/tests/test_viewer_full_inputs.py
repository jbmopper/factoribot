"""Task 15: full-belt input viewer model and draft contract checks.

The task handoff records the browser check status for the same two-lane fixture.
These focused checks keep the non-browser invariants close to the renderer:
capacity is copied from imported lane groups, and the convenient controls still
export ordinary shared-budget/Feed records.
"""
from __future__ import annotations

from pathlib import Path
import sys

from factoribot.blueprint_contract import parse_assignments, to_dict
from factoribot.blueprint_view import build_view_model, check_assignment_document, render_view
from factoribot.routing import RecipeSource, RoutingOptions, build_transport_graph
from factoribot.spatial import build_spatial_view, load_spatial_view

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "daemon/tests/fixtures/routing_transport"))
import layouts as L  # noqa: E402


def graph_for(entities, *, recipes=None):
    return build_transport_graph(
        build_spatial_view(L.blueprint(entities)),
        RoutingOptions(recipes=recipes),
    ).graph


def input_belt(model, number=1):
    return next(entity["input_belt"] for entity in model["graph"]["entities"]
                if entity["key"] == f"bp/root/e/{number}")


def full_draft(graph, *, left="iron-plate", right="iron-plate"):
    """Hand-written expected output; this is not a solver expectation.

    A fast belt is 15 items/s per imported lane in this fixture, so one item on
    both lanes shares one 30 items/s budget while each Feed remains locally
    capped at 15.  A different item per lane receives a separate budget.
    """
    wire = to_dict(graph)
    ports = {port["id"]["name"]: port["id"] for port in wire["ports"]
             if port["id"]["entity"]["entity_number"] == 1}
    assignments = {
        "schema_version": graph.schema_version,
        "blueprint_hash": graph.blueprint_hash,
        "graph_hash": graph.graph_hash,
        "feeds": [], "furnaces": [], "controls": [],
    }
    budgets = []
    if left == right:
        budgets.append({"id": "full_input_1_iron-plate", "material": {
            "kind": "item", "name": left, "quality": "normal"},
            "capacity": {"kind": "finite", "value": 30.0}})
        for side in ("left", "right"):
            assignments["feeds"].append({"id": f"full_input_1_{side}",
                "budget_id": "full_input_1_iron-plate", "endpoint": ports[f"in_{side}"],
                "capacity": {"kind": "finite", "value": 15.0}})
    else:
        for side, material in (("left", left), ("right", right)):
            budget_id = f"full_input_1_{material}"
            budgets.append({"id": budget_id, "material": {
                "kind": "item", "name": material, "quality": "normal"},
                "capacity": {"kind": "finite", "value": 15.0}})
            assignments["feeds"].append({"id": f"full_input_1_{side}", "budget_id": budget_id,
                "endpoint": ports[f"in_{side}"], "capacity": {"kind": "finite", "value": 15.0}})
    return {"document_kind": "factoribot.routing.assignment_draft", "assignments": assignments,
            "proposed_request": {"budgets": budgets, "exports": [], "surplus": [],
                                  "objective": {"kind": "feasible", "export_id": None}}}


def test_full_belt_model_uses_imported_lane_capacity_not_a_tier_table():
    fast = graph_for(L.two_lane_run())
    basic = graph_for(L.straight_run(name="transport-belt"))
    fast_belt = input_belt(build_view_model(to_dict(fast)))
    basic_belt = input_belt(build_view_model(to_dict(basic)))

    assert [lane["capacity"]["value"] for lane in fast_belt["lanes"]] == [15.0, 15.0]
    assert fast_belt["whole_capacity"]["value"] == 30.0
    assert [lane["capacity"]["value"] for lane in basic_belt["lanes"]] == [7.5, 7.5]
    assert basic_belt["whole_capacity"]["value"] == 15.0


def test_full_belt_draft_has_shared_budget_and_lane_feeds():
    graph = graph_for(L.two_lane_run())
    draft = full_draft(graph)
    assignments = draft["assignments"]

    # The counterexample is giving each lane a 30/s budget: that would falsely
    # create 60/s.  The expected draft has one 30/s global budget and two 15/s
    # local feeds, so it remains contract-valid and globally shared.
    assert parse_assignments(assignments, graph).feeds[0].capacity.value == 15.0
    assert [feed["budget_id"] for feed in assignments["feeds"]] == [
        "full_input_1_iron-plate", "full_input_1_iron-plate"]
    assert draft["proposed_request"]["budgets"][0]["capacity"]["value"] == 30.0
    assert check_assignment_document(draft, to_dict(graph))["ok"]


def test_different_lane_items_and_one_lane_are_separate_declared_sources():
    graph = graph_for(L.two_lane_run())
    mixed = full_draft(graph, left="iron-plate", right="copper-plate")
    assert len(mixed["proposed_request"]["budgets"]) == 2
    assert {budget["capacity"]["value"] for budget in mixed["proposed_request"]["budgets"]} == {15.0}
    assert parse_assignments(mixed["assignments"], graph)

    one_lane = full_draft(graph)["assignments"]
    one_lane["feeds"] = one_lane["feeds"][:1]
    one_lane["feeds"][0]["capacity"] = {"kind": "finite", "value": 15.0}
    assert parse_assignments(one_lane, graph).feeds[0].capacity.value == 15.0


def test_internal_and_outgoing_ports_do_not_qualify_for_full_input():
    model = build_view_model(to_dict(graph_for(L.two_lane_run())))
    first = input_belt(model, 1)
    internal = input_belt(model, 2)
    assert first["whole_belt_available"] is True
    assert internal["whole_belt_available"] is False
    # The strict contract is still the final guard for an outgoing declaration.
    graph = graph_for(L.two_lane_run())
    bad = full_draft(graph)["assignments"]
    bad["feeds"][0]["endpoint"]["name"] = "out_left"
    assert not check_assignment_document(bad, to_dict(graph))["ok"]


def test_imported_recipe_is_visible_even_when_analysis_cannot_support_it():
    graph = graph_for([L.entity(1, L.MACHINE, 1.5, 1.5, L.NORTH, recipe="not-a-real-recipe")],
                      recipes=RecipeSource())
    model = build_view_model(to_dict(graph))
    machine = model["graph"]["entities"][0]
    assert machine["blueprint_recipe"] == "not-a-real-recipe"
    assert machine["recipes"] == ["not-a-real-recipe"]
    assert "not-a-real-recipe" in render_view(to_dict(graph))


def test_pilot_keeps_all_153_imported_assembler_recipes_visible():
    view = load_spatial_view((ROOT / "daemon/tests/fixtures/wip_science.txt").read_text())
    graph = build_transport_graph(view, RoutingOptions(
        provenance="development_pilot", recipes=RecipeSource())).graph
    model = build_view_model(to_dict(graph))
    recipes = [entity["blueprint_recipe"] for entity in model["graph"]["entities"]
               if entity["prototype"] == "assembling-machine-2"]
    assert len(recipes) == 153
    assert all(recipes)
