"""Task 19 feed-driven furnace inference and provenance tests."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

from factoribot.blueprint_contract import (
    FurnaceAssignment,
    parse_request,
    to_dict,
    unresolved_reasons,
)
from factoribot.blueprint_plan import analyze_delivery
from factoribot.furnace_inference import (
    FurnaceInferenceError,
    InferenceLimits,
    compatible_furnace_recipes,
    infer_furnace_recipes,
    make_inference_artifact,
    validate_inference_artifact,
)
from factoribot.gamedata import load_database
from factoribot.routing import RecipeSource


HERE = Path(__file__).parent
_spec = importlib.util.spec_from_file_location(
    "furnace_inference_cases", HERE / "fixtures" / "furnace_inference" / "cases.py"
)
cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cases)


def by_entity(report):
    return {record["entity"]["entity_number"]: record for record in report["furnaces"]}


def infer(case, available=cases.ALL_SMELTING, **kwargs):
    graph, assignments, budgets = case()
    return graph, assignments, budgets, infer_furnace_recipes(
        graph, assignments, budgets, available, **kwargs
    )


def test_loaded_recipe_data_derives_only_item_smelting_candidates():
    source = RecipeSource(load_database())
    assert compatible_furnace_recipes(source, source.db.recipes) == cases.ALL_SMELTING
    assert compatible_furnace_recipes(
        source, ("iron-plate", "iron-gear-wheel", "plastic-bar", "missing")
    ) == ("iron-plate",)


def test_iron_plate_then_steel_reaches_a_bounded_unique_fixed_point_with_paths():
    _, _, _, report = infer(cases.iron_steel_chain)
    records = by_entity(report)
    assert [(value["entity"]["entity_number"], value["recipe"])
            for value in report["inferred_assignments"]] == [
                (1, "iron-plate"), (2, "steel-plate")
            ]
    assert records[1]["status"] == records[2]["status"] == "inferred"
    evidence = records[2]["evidence"][0]["inputs"][0]
    assert evidence["material"]["name"] == "iron-plate"
    assert evidence["amount_per_craft"] == 5.0
    assert evidence["evidence"]["sources"] == ["feed:ore_feed:budget:ore"]
    assert "plate_to_steel" in evidence["evidence"]["arc_path"]
    assert any(step.startswith("activity:furnace_1_iron-plate")
               for step in evidence["evidence"]["steps"])
    assert records[2]["assumptions"] == report["assumptions"]
    assert report["iterations"]["furnace_rounds"] >= 3


def test_stone_to_brick_records_the_database_ingredient_quantity():
    _, _, _, report = infer(cases.stone_brick)
    record = by_entity(report)[1]
    assert record["recipe"] == "stone-brick" and record["status"] == "inferred"
    ingredient = record["evidence"][0]["inputs"][0]
    assert (ingredient["material"]["name"], ingredient["amount_per_craft"]) == ("stone", 2.0)


def test_mixed_ores_retain_both_candidates_and_one_actionable_group():
    _, _, _, report = infer(cases.mixed_ores)
    record = by_entity(report)[1]
    assert record["status"] == "ambiguous"
    assert record["matching_candidates"] == ["copper-plate", "iron-plate"]
    assert not report["inferred_assignments"]
    assert len(report["ambiguity_groups"]) == 1
    assert report["ambiguity_groups"][0]["entities"] == [to_dict(cases.eid(1))]
    assert report["ambiguity_groups"][0]["override_path"] == "/assignments/furnaces"


@pytest.mark.parametrize("case", [cases.conditional_source, cases.unknown_bridge])
def test_uncertain_paths_expand_possibility_but_never_establish_inference(case):
    _, _, _, report = infer(case)
    record = next(iter(by_entity(report).values()))
    assert record["status"] == "conditional"
    assert record["matching_candidates"] == ["iron-plate"]
    assert not report["inferred_assignments"]
    uncertainty = record["evidence"][0]["inputs"][0]["evidence"]["uncertainty"]
    assert uncertainty


@pytest.mark.parametrize("case", [cases.no_source, cases.disconnected_cycle])
def test_no_source_and_disconnected_cycles_cannot_bootstrap_material(case):
    _, _, _, report = infer(case, available=cases.ALL_SMELTING + ("smelt-a", "smelt-b"))
    assert not report["inferred_assignments"]
    assert all(record["status"] == "no_evidence" for record in report["furnaces"])
    assert report["state_counts"] == {"possible": 0, "exact": 0}


def test_explicit_override_wins_and_confirmed_incompatible_feed_is_reported():
    _, assignments, _, report = infer(cases.conflicting_override)
    record = by_entity(report)[1]
    assert record["status"] == "conflict"
    assert record["recipe"] == "iron-plate"
    assert "does not contain" in record["detail"]
    assert report["explicit_assignments"] == [to_dict(assignments.furnaces[0])]
    assert not report["inferred_assignments"]


def test_changed_feed_invalidates_the_additive_inference_artifact():
    graph, assignments, budgets = cases.iron_steel_chain()
    artifact = make_inference_artifact(
        graph, assignments, budgets, cases.ALL_SMELTING,
        source_graph_hash=graph.graph_hash,
    )
    assert validate_inference_artifact(
        artifact, graph, [to_dict(value) for value in budgets], cases.ALL_SMELTING
    ).furnaces

    changed = [to_dict(value) for value in budgets]
    changed[0]["material"]["name"] = "copper-ore"
    with pytest.raises(FurnaceInferenceError, match="rerun routes infer") as caught:
        validate_inference_artifact(artifact, graph, changed, cases.ALL_SMELTING)
    assert caught.value.code == "stale_inference"


def test_artifact_replay_uses_its_recorded_nondefault_work_limits():
    graph, assignments, budgets = cases.iron_steel_chain()
    limits = InferenceLimits(
        max_iterations=20, max_states=100, max_steps_per_trace=50
    )
    artifact = make_inference_artifact(
        graph, assignments, budgets, cases.ALL_SMELTING,
        source_graph_hash=graph.graph_hash,
        limits=limits,
    )
    replay = validate_inference_artifact(
        artifact, graph, [to_dict(value) for value in budgets], cases.ALL_SMELTING
    )
    assert len(replay.furnaces) == 2


def test_a_single_declared_candidate_without_feed_stays_out_of_accounting():
    layout = cases.base.Layout("task19_single_candidate_no_source")
    cases.add_furnace(layout, 1, 0, ("iron-plate",))
    graph = layout.finish()
    assignments, budgets = cases.assignments(graph), ()
    report = infer_furnace_recipes(graph, assignments, budgets, ("iron-plate",))
    assert report["inferred_assignments"] == []

    document = cases.base.request_document(
        graph,
        [],
        [],
        [cases.base.export(
            cases.base.ep(1, "output", "inventory"), "iron-plate"
        )],
        recipes=("iron-plate",),
    )
    request = parse_request(document, graph)
    assert unresolved_reasons(request, graph) == (
        "unassigned furnace: bp/3/1/e/1",
    )
    result = analyze_delivery(graph, request).result
    assert result.status == "partial" and result.bounds == ()
    assert result.findings[0].code == "unresolved_unassigned_furnace"


def test_iteration_limit_stops_work_instead_of_returning_partial_inference():
    graph, assignments, budgets = cases.iron_steel_chain()
    with pytest.raises(FurnaceInferenceError) as caught:
        infer_furnace_recipes(
            graph, assignments, budgets, cases.ALL_SMELTING,
            limits=InferenceLimits(max_iterations=1),
        )
    assert caught.value.code == "inference_limit"


def _request(graph, assignments, budgets):
    base = cases.base
    document = base.request_document(
        graph,
        [to_dict(value) for value in assignments.feeds],
        [to_dict(value) for value in budgets],
        [base.export(base.ep(2, "output", "inventory"), "steel-plate")],
        recipes=cases.ALL_SMELTING,
        furnaces=[to_dict(value) for value in assignments.furnaces],
    )
    return parse_request(document, graph)


def test_recorded_inference_replays_as_the_equivalent_manual_request():
    graph, assignments, budgets = cases.iron_steel_chain()
    artifact = make_inference_artifact(
        graph, assignments, budgets, cases.ALL_SMELTING,
        source_graph_hash=graph.graph_hash,
    )
    inferred = validate_inference_artifact(
        artifact, graph, [to_dict(value) for value in budgets], cases.ALL_SMELTING
    )
    manual_document = copy.deepcopy(to_dict(inferred))
    manual = cases.assignments(
        graph,
        inferred.feeds,
        tuple(type(value)(value.entity, value.recipe) for value in inferred.furnaces),
    )
    assert to_dict(manual) == manual_document

    inferred_request = _request(graph, inferred, budgets)
    manual_request = _request(graph, manual, budgets)
    assert inferred_request.request_hash == manual_request.request_hash
    inferred_result = analyze_delivery(graph, inferred_request).result
    manual_result = analyze_delivery(graph, manual_request).result
    assert inferred_result.result_hash == manual_result.result_hash
    routing = next(bound for bound in inferred_result.bounds if bound.stage == "routing")
    # Hand derivation: furnace 1 makes one plate/s; steel consumes five plates,
    # so the two-furnace chain is bounded by 0.2 steel/s.
    assert routing.value.value == pytest.approx(0.2)


def test_explicit_furnaces_use_numeric_entity_order_in_replay_artifact():
    layout = cases.base.Layout("task23_numeric_furnace_order")
    input_five, _ = cases.add_furnace(layout, 5, 0)
    cases.add_furnace(layout, 11, 3)
    layout.arc(
        "plate_to_steel",
        cases.base.ep(5, "output", "inventory"),
        cases.base.ep(11, "input", "inventory"),
        layout.transfer(),
    )
    graph = layout.finish()
    ore = cases.budget("ore", "iron-ore")
    explicit = cases.assignments(
        graph,
        [cases.feed("ore_feed", "ore", input_five)],
        [
            FurnaceAssignment(cases.eid(5), "iron-plate"),
            FurnaceAssignment(cases.eid(11), "steel-plate"),
        ],
    )
    artifact = make_inference_artifact(
        graph,
        explicit,
        [ore],
        cases.ALL_SMELTING,
        source_graph_hash=graph.graph_hash,
    )

    assert [
        value["entity"]["entity_number"]
        for value in artifact["assignments"]["furnaces"]
    ] == [5, 11]
    replayed = validate_inference_artifact(
        artifact,
        graph,
        [to_dict(ore)],
        cases.ALL_SMELTING,
    )
    assert [assignment.entity.entity_number for assignment in replayed.furnaces] == [5, 11]
