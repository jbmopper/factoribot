"""Hand-solved delivery-bound tests for blueprint_plan (task 05).

Expected numbers are derived in fixtures/routing_plan/cases.py docstrings or
in comments here; the solver's output is never the expectation. Counterexamples
show where a plausible wrong implementation (per-item capacity copies, double
charging a shared resource, per-port budgets) would differ.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

from factoribot.blueprint_contract import (
    ContractError, Material, parse_graph, parse_request, to_dict, content_hash, unresolved_reasons,
)
from factoribot.findings import validate_result, parse_result
from factoribot.blueprint_plan import (
    PlanOptions, Allocation, analyze_delivery, analyze_request_document, verify_allocation,
    counterfactual_routing, resolve_model_inputs, solve_stage, TOLERANCE,
)
from factoribot.routing_lp import build_lp, count_model

HERE = Path(__file__).parent
CONTRACT_FIXTURES = HERE / "fixtures" / "routing_contracts"
_spec = importlib.util.spec_from_file_location("routing_plan_cases", HERE / "fixtures" / "routing_plan" / "cases.py")
cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cases)


def load_fixture(name):
    sample = json.loads((CONTRACT_FIXTURES / f"{name}.json").read_text())
    graph = parse_graph(sample["graph"])
    return graph, parse_request(sample["request"], graph), sample


def stage_values(report):
    return {stage: solution.value for stage, solution in report.stages.items()}


def close(actual, expected, tol=1e-7):
    if expected == "unlimited":
        return actual is not None and math.isinf(actual)
    if expected == "infeasible":
        return actual is None
    return actual is not None and abs(actual - expected) <= tol * max(1.0, abs(expected))


def check_result_contract(report, graph):
    """Every result must be a valid contract record with independently verified witness."""
    result = report.result
    validate_result(result, graph)
    assert parse_result(json.loads(json.dumps(to_dict(result))), graph) == result
    if result.witness is not None:
        request = result.interpreted_request
        allocation = Allocation({(f.arc_id, f.material): f.rate for f in result.witness.flows},
                                {a.activity_id: a.crafts_per_s for a in result.witness.activities},
                                {i.id: i.rate for i in result.witness.imports}, {e.id: e.rate for e in result.witness.exports},
                                {s.id: s.rate for s in result.witness.surplus})
        verification = verify_allocation(graph, request, allocation)
        assert verification.ok, verification.violations
        assert verification.max_conservation_residual <= TOLERANCE
        assert result.witness.validation == "independent_residual_check"
    finite = {b.stage: b.value.value for b in result.bounds if b.value is not None and b.value.kind == "finite" and b.solver_state == "optimal"}
    for left, right in (("aggregate", "budget"), ("budget", "routing")):
        if left in finite and right in finite:
            assert finite[left] + 1e-8 >= finite[right]


@pytest.mark.parametrize("name", sorted(cases.CASES))
def test_hand_solved_cases(name):
    graph, request, expected = cases.CASES[name]()
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == expected["status"], report.result.findings
    for stage in ("aggregate", "budget", "routing"):
        if stage in expected:
            assert close(report.stages[stage].value, expected[stage]), (stage, report.stages[stage].value, expected[stage])
            solution = report.stages[stage]
            if solution.state == "optimal":
                assert solution.verification.ok and solution.dual is not None
                assert abs(solution.primal - solution.dual) <= 1e-7 * max(1.0, solution.dual)
    if expected["status"] == "feasible_relaxed":
        routing = next(b for b in report.result.bounds if b.stage == "routing")
        assert routing.solver_state == "optimal" and routing.certificate.startswith("Certified upper bound") or routing.value.kind == "unlimited"


def test_competing_items_counterexample_per_item_copies():
    """Wrong model (a <= 15 and b <= 15 separately) gives 10; shared lane gives 7.5."""
    graph, request, expected = cases.competing_items()
    report = analyze_delivery(graph, request)
    routing = report.stages["routing"]
    assert close(routing.value, 7.5) and expected["wrong_per_item_copies"] == 10
    assert close(report.stages["budget"].value, 10)
    # The certificate is grounded in the shared group and both materials' conservation, not one item's path.
    assert "capacity group lane_3" in routing.certificate
    assert "item-a" in routing.certificate and "item-b" in routing.certificate
    finding = next(f for f in report.result.findings if f.code == "delivery_upper_bound")
    assert finding.capacity_upper_bound == pytest.approx(7.5) and finding.material == Material("item", "item-c", "normal")
    assert {e.entity_number for e in finding.entity_ids} >= {3, 4}
    # The independent verifier rejects the per-item-copy allocation a wrong LP would emit.
    a, b, c = Material("item", "item-a", "normal"), Material("item", "item-b", "normal"), Material("item", "item-c", "normal")
    wrong = Allocation({("m1_to_belt", a): 10, ("m2_to_belt", b): 10, ("belt_3", a): 10, ("belt_3", b): 10,
                        ("belt_to_m4", a): 10, ("belt_to_m4", b): 10},
                       {"make_a": 10, "make_b": 10, "make_c": 10}, {"iron_feed": 10, "copper_feed": 10}, {"product": 10}, {})
    verification = verify_allocation(graph, request, wrong)
    assert not verification.ok and any("capacity group lane_3" in v for v in verification.violations)
    assert verification.max_capacity_excess == pytest.approx(5)  # 20 carried on a 15/s lane
    # ... while the same allocation scaled to 7.5 passes (hand-checked feasible point).
    right = Allocation({k: 7.5 for k in wrong.flows}, {k: 7.5 for k in wrong.crafts}, {"iron_feed": 7.5, "copper_feed": 7.5}, {"product": 7.5}, {})
    assert verify_allocation(graph, request, right).ok


def test_shared_resource_not_copied_or_double_charged():
    graph, request, expected = cases.shared_inserter()
    report = analyze_delivery(graph, request)
    assert close(report.stages["routing"].value, 5)
    assert expected["wrong_per_arc_copy"] == 10 and expected["wrong_double_charge"] == 2.5
    # Verifier: 10 through the inserter is a shared-ceiling violation even if per-arc totals are only 5 each.
    iron = Material("item", "iron-plate", "normal")
    per_arc_copy = Allocation({("belt_1", iron): 5, ("belt_3", iron): 5, ("p1", iron): 5, ("p2", iron): 5}, {"gears": 10},
                              {"feed_a": 5, "feed_b": 5}, {"product": 10}, {})
    verification = verify_allocation(graph, request, per_arc_copy)
    assert not verification.ok and any("capacity group ins" in v for v in verification.violations)
    # An arc crossing two resources consumes each: inserter 5 and lane gate 3 -> 3.
    graph2, request2, expected2 = cases.shared_inserter(gate_capacity=3)
    report2 = analyze_delivery(graph2, request2)
    assert close(report2.stages["routing"].value, 3) and expected2["routing"] == 3
    assert close(report2.stages["budget"].value, 10)


def test_shared_budget_fixture_two_ports_one_ceiling():
    """Fixture: feeds a and b share one 10/s budget; reserved exact 5 leaves 5. Per-port budgets would give 10 (15 lane cap)."""
    graph, request, sample = load_fixture("shared_budget")
    assert request.budgets[0].capacity.value == 10 and request.exports[1].rate == 5
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == "feasible_relaxed"
    assert close(report.stages["aggregate"].value, 20)  # sink ceiling of the objective export
    assert close(report.stages["budget"].value, 5) and close(report.stages["routing"].value, 5)
    assert 10 + 5 > request.budgets[0].capacity.value  # the per-port bug would need 15


def test_increasing_a_budget_cannot_reduce_the_optimum():
    graph, request, sample = load_fixture("shared_budget")
    base = analyze_delivery(graph, request).stages["routing"].value
    # Hand: budget 12 - reserved 5 = 7; budget 4 < reserved 5 -> insufficient.
    raised = counterfactual_routing(graph, request, budget_capacities={"iron": 12})
    assert close(base, 5) and close(raised.value, 7) and raised.value >= base
    lowered = counterfactual_routing(graph, request, budget_capacities={"iron": 4})
    assert lowered.state == "infeasible" and "reserved" in lowered.certificate
    # Same monotonicity on a synthetic case: iron 20 -> 40 leaves the lane-bound 7.5 unchanged.
    g, r, _ = cases.competing_items()
    assert close(counterfactual_routing(g, r, budget_capacities={"iron": 40}).value, 7.5)


def test_relaxing_routing_recovers_the_budget_bound():
    graph, request, _ = cases.competing_items()
    full = analyze_delivery(graph, request)
    only_budget = analyze_delivery(graph, request, PlanOptions(stages=("budget",)))
    assert close(only_budget.stages["budget"].value, full.stages["budget"].value) and close(full.stages["budget"].value, 10)
    # Doubling the lane (30/s) removes the only routing restriction: routing == budget == 10.
    widened = counterfactual_routing(graph, request, group_capacities={"lane_3": 30})
    assert close(widened.value, 10)
    # A graph whose lane is already ample gives routing == budget directly.
    g, r, _ = cases.competing_items(lane_capacity=40)
    rep = analyze_delivery(g, r)
    assert close(rep.stages["routing"].value, rep.stages["budget"].value)


def test_tight_constraint_is_not_an_upgrade_claim():
    graph, request, expected = cases.series_tight()
    report = analyze_delivery(graph, request)
    routing = report.stages["routing"]
    assert close(routing.value, 5)
    labels = {t.label for t in routing.cut}
    assert any(l[:2] == ("group", "lane_1") or l[:2] == ("group", "lane_3") or l[:2] == ("group", "m2_time") for l in labels)
    assert close(counterfactual_routing(graph, request, group_capacities={"lane_1": 10}).value, expected["one_relaxed"])
    assert close(counterfactual_routing(graph, request, group_capacities={"lane_1": 10, "lane_3": 10, "m2_time": 2}).value, expected["all_relaxed"])


def test_secondary_objective_removes_gratuitous_cycles():
    graph, request, _ = cases.cycle()
    report = analyze_delivery(graph, request)
    assert close(report.stages["routing"].value, 10)
    flows = {f.arc_id: f.rate for f in report.result.witness.flows}
    assert flows.get("loop_back", 0) == 0 and flows.get("belt_2", 0) == 0 and flows.get("forward", 0) == 0
    assert flows["belt_1"] == pytest.approx(10)
    assert report.stages["aggregate"].state == "unlimited"
    aggregate = next(b for b in report.result.bounds if b.stage == "aggregate")
    assert aggregate.value.kind == "unlimited" and aggregate.solver_state == "optimal"


def test_blocked_export_and_byproduct_cases():
    graph, request, _ = cases.blocked_byproduct()
    report = analyze_delivery(graph, request)
    assert report.result.status == "feasible_relaxed" and close(report.stages["routing"].value, 0)
    assert any(f.code == "zero_objective" for f in report.result.findings)
    graph, request, _ = cases.blocked_byproduct(gear_minimum=1)
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == "insufficient"
    routing = next(b for b in report.result.bounds if b.stage == "routing")
    assert routing.solver_state == "infeasible" and "shortfall of at least 1" in routing.certificate
    assert report.stages["aggregate"].state == "infeasible"  # the byproduct blocks every stage
    graph, request, _ = cases.blocked_byproduct(scrap_sink=3, gear_minimum=1)
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == "feasible_relaxed" and close(report.stages["routing"].value, 3)
    assert {s.id: s.rate for s in report.result.witness.surplus}["scrap_out"] == pytest.approx(3)
    # Contract fixture: the machine has no route to the declared outlet.
    graph, request, _ = load_fixture("blocked_export")
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == "insufficient"
    assert close(report.stages["aggregate"].value, 10) and close(report.stages["budget"].value, 10)
    assert report.stages["routing"].state == "infeasible"


def test_disconnected_producer_fixture_is_insufficient_not_capacity():
    """Producer 10 crafts/s, consumer 5 crafts/s, iron 10/s: aggregate/budget 5, but no arc reaches machine 3."""
    graph, request, _ = load_fixture("disconnected_circuit")
    assert not any(a.target.entity.entity_number == 3 for a in graph.arcs)
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == "insufficient"
    assert close(report.stages["aggregate"].value, 5) and close(report.stages["budget"].value, 5)
    routing = report.stages["routing"]
    assert routing.state == "infeasible" and routing.shortfall == pytest.approx(1)
    assert "conservation of electronic-circuit" in routing.certificate
    finding = next(f for f in report.result.findings if f.code == "delivery_insufficient")
    assert finding.severity == "error" and {e.entity_number for e in finding.entity_ids} >= {3}


def test_pass_through_and_infeasible_budget_certificate_covers_every_export():
    graph, request, _ = cases.pass_through()
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert close(report.stages["routing"].value, 6) and close(report.stages["aggregate"].value, 20)
    exports = {e.id: e.rate for e in report.result.witness.exports}
    assert exports["gear_out"] == pytest.approx(2) and exports["iron_out"] == pytest.approx(6)
    # 8 exact gears need 16 iron > 5 budget: budget and routing infeasible, aggregate unaffected (20).
    graph, request, _ = cases.pass_through(iron_budget=5, gear_exact=8)
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == "insufficient"
    assert report.stages["budget"].state == "infeasible" and report.stages["routing"].state == "infeasible"
    assert close(report.stages["aggregate"].value, 20)
    certificate = report.stages["routing"].certificate
    assert "gear_out (exact 8" in certificate and "iron_out (minimum 0" in certificate
    assert "budget iron" in certificate and "shortfall of at least" in certificate
    assert report.stages["routing"].shortfall == pytest.approx(8 - 2.5)  # 5 iron / 2 per gear = 2.5 gears at best


def test_mixed_variants_and_explicit_furnace_assignment():
    graph, request, _ = cases.mixed_variants()
    report = analyze_delivery(graph, request)
    assert close(report.stages["aggregate"].value, 6.8) and close(report.stages["budget"].value, 5.8) and close(report.stages["routing"].value, 5)
    graph, request, _ = cases.furnace_choice(override=None)
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == "partial" and not report.result.bounds and "ambiguous furnace" in report.unresolved[0]
    graph, request, _ = cases.furnace_choice(override="stone-brick")
    report = analyze_delivery(graph, request)
    assert close(report.stages["routing"].value, 5)
    assert any(f.code == "furnace_alternative_excluded" for f in report.result.findings)
    assert {a.activity_id for a in report.result.witness.activities} == {"bricks"}
    graph, request, _ = cases.furnace_choice(override="iron-plate")
    report = analyze_delivery(graph, request)
    assert close(report.stages["routing"].value, 0) and any(f.code == "zero_objective" for f in report.result.findings)
    # Contract fixture: 10 stone/s at 2 per craft = 5 bricks/s; machine 10 crafts/s bounds the aggregate.
    graph, request, _ = load_fixture("furnace_override")
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert close(report.stages["aggregate"].value, 10) and close(report.stages["budget"].value, 5) and close(report.stages["routing"].value, 5)


def test_unsupported_bridge_and_unknown_power_withhold_all_claims():
    for graph, request, _ in (cases.unsupported_bridge(), load_fixture("unsupported_bridge")):
        assert unresolved_reasons(request, graph)
        report = analyze_delivery(graph, request)
        check_result_contract(report, graph)
        assert report.result.status == "partial" and not report.result.bounds and report.result.witness is None
        assert not any(f.evidence_kind == "upper_bound" for f in report.result.findings)
        # One code per unresolved reason class (see test_routing_reporting_regressions).
        assert any(f.code.startswith("unresolved_") for f in report.result.findings)
    graph = cases.competing_items()[0]
    request = cases.request(graph, [cases.feed("iron_feed", "iron", cases.ep(1, "ingredients", "inventory")),
                                    cases.feed("copper_feed", "copper", cases.ep(2, "ingredients", "inventory"))],
                            [cases.budget("iron", "iron-plate", 20), cases.budget("copper", "copper-plate", 20)],
                            [cases.export(cases.ep(4, "output"), "item-c")], recipes=("synthetic-a", "synthetic-b", "synthetic-c"), power="unknown")
    report = analyze_delivery(graph, request)
    assert report.result.status == "partial" and report.unresolved == ("power availability unknown",)
    with pytest.raises(ContractError):
        counterfactual_routing(graph, request, group_capacities={"lane_3": 30})


def test_conditional_connection_policies():
    graph, request, _ = cases.conditional_gate(policy="explicit", enabled=False)
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == "insufficient" and report.stages["routing"].state == "infeasible"
    assert close(report.stages["budget"].value, 10)
    assert any(f.code == "control_disabled_connection" for f in report.result.findings)
    graph, request, _ = cases.conditional_gate(policy="explicit", enabled=True)
    report = analyze_delivery(graph, request)
    routing = next(b for b in report.result.bounds if b.stage == "routing")
    assert close(report.stages["routing"].value, 10) and "conditional_connections_open" not in routing.relaxations
    graph, request, _ = cases.conditional_gate(policy="relax_open")
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    routing = next(b for b in report.result.bounds if b.stage == "routing")
    assert close(report.stages["routing"].value, 10) and "conditional_connections_open" in routing.relaxations
    assert any(f.code == "conditional_connections_open" for f in report.result.findings)


def test_unknown_inserter_rate_is_relaxed_and_disclosed():
    graph, request, _ = cases.shared_inserter(inserter_capacity="unknown")
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    # Without the inserter ceiling the machine (10 crafts/s) binds; 20 iron and two 15/s lanes are looser.
    assert close(report.stages["routing"].value, 10)
    routing = next(b for b in report.result.bounds if b.stage == "routing")
    budget = next(b for b in report.result.bounds if b.stage == "budget")
    assert "unknown_capacity_unlimited" in routing.relaxations and "unknown_capacity_unlimited" not in budget.relaxations
    finding = next(f for f in report.result.findings if f.code == "unknown_capacity_relaxed")
    assert finding.evidence_kind == "conditional" and finding.capacity_upper_bound is None


def test_verifier_rejects_doctored_witness_and_is_not_solver_status():
    graph, request, _ = cases.pass_through()
    report = analyze_delivery(graph, request)
    witness = report.result.witness
    good = Allocation({(f.arc_id, f.material): f.rate for f in witness.flows}, {a.activity_id: a.crafts_per_s for a in witness.activities},
                      {i.id: i.rate for i in witness.imports}, {e.id: e.rate for e in witness.exports}, {s.id: s.rate for s in witness.surplus})
    assert verify_allocation(graph, request, good).ok
    doctored = Allocation(good.flows, good.crafts, good.imports, {**good.exports, "iron_out": good.exports["iron_out"] + 1}, good.surplus)
    verification = verify_allocation(graph, request, doctored)
    assert not verification.ok and any("conservation of iron-plate" in v for v in verification.violations)
    over_budget = Allocation(good.flows, good.crafts, {"iron_feed": 11}, good.exports, good.surplus)
    assert any("budget iron" in v for v in verify_allocation(graph, request, over_budget).violations)
    missing_export = Allocation(good.flows, good.crafts, good.imports, {"iron_out": good.exports["iron_out"]}, good.surplus)
    assert any("not enumerated" in v for v in verify_allocation(graph, request, missing_export).violations)
    below_exact = Allocation(good.flows, good.crafts, good.imports, {**good.exports, "gear_out": 1}, good.surplus)
    assert any("below required" in v for v in verify_allocation(graph, request, below_exact).violations)


def test_feasibility_objective_and_invalid_request_records():
    graph, request, _ = cases.pass_through(objective=None)
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == "feasible_relaxed" and not report.result.bounds and report.result.witness is not None
    assert report.stages["routing"].state == "feasible"
    graph, request, _ = cases.pass_through(iron_budget=5, gear_exact=8, objective=None)
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == "insufficient" and any(f.code == "delivery_insufficient" for f in report.result.findings)
    # Strict parse failure -> invalid_request record with an error finding, no interpreted request.
    graph, request, _ = cases.furnace_choice()
    document = cases.request_document(graph, [cases.feed("stone_feed", "stone", cases.ep(1, "ingredients", "inventory"))],
                                      [cases.budget("stone", "stone", 10)], [cases.export(cases.ep(2, "left_out"), "stone-brick")],
                                      recipes=("iron-plate", "stone-brick"), furnaces=[dict(entity=cases.eid(1), recipe="steel-plate")])
    report = analyze_request_document(graph, document)
    validate_result(report.result, graph)
    assert report.result.status == "invalid_request" and report.result.interpreted_request is None
    assert report.result.findings[0].severity == "error" and "override" in report.result.findings[0].message


def test_results_are_deterministic_and_findings_sorted():
    graph, request, _ = cases.competing_items()
    a, b = analyze_delivery(graph, request), analyze_delivery(graph, request)
    assert a.result.result_hash == b.result.result_hash
    ids = [f.id for f in a.result.findings]
    assert ids == sorted(ids) and all(i.startswith("finding:") for i in ids)
    assert a.result.request_hash == request.request_hash


def test_large_layout_model_size_and_timing():
    """3200 independent lanes: 3200 flow variables + 1 import + 1 export; 6400 port rows + 3200 lane groups + 1 budget row."""
    graph, request, _ = load_fixture("large_layout")
    inputs = resolve_model_inputs(graph, request)
    estimate = count_model(inputs, "routing")
    assert estimate["variables"] == 3202
    model = build_lp(inputs, "routing")
    assert (model.n_variables, model.n_rows) == (3202, 9601)
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert close(report.stages["routing"].value, 5) and close(report.stages["budget"].value, 5) and close(report.stages["aggregate"].value, 15)
    total = sum(sum(s.timings.values()) for s in report.stages.values())
    assert total < 30, report.stages["routing"].timings
    # Size limit is checked before any allocation.
    limited = analyze_delivery(graph, request, PlanOptions(max_variables=100))
    assert limited.result.status == "solver_limit" and limited.stages["routing"].state == "size_limit"
    validate_result(limited.result, graph)
    assert all(b.solver_state == "certified_limit" for b in limited.result.bounds)


@pytest.fixture(scope="module")
def db():
    from factoribot.gamedata import load_database
    try:
        return load_database()
    except FileNotFoundError:
        pytest.skip("data-raw-dump.json not present; run `factorio --dump-data`")


def test_motivating_budget_scenario_routing_free(db):
    """Stone 30, copper 30, plastic 30, iron 60 (items/s), AM2 no modules, internal steel and bricks.

    Per production-science-pack craft (3 packs): 1 electric-furnace + 1 productivity-module + 30 rail.
      30 rail = 15 crafts: 15 stone, 15 steel, 15 iron-stick (7.5 iron).
      electric-furnace: 10 steel, 5 advanced-circuit, 10 stone-brick (20 stone).
      productivity-module: 5 advanced-circuit, 5 electronic-circuit.
      10 advanced-circuit: 20 electronic-circuit, 20 plastic, 40 cable (20 copper).
      25 electronic-circuit: 25 iron, 75 cable (37.5 copper).
      25 steel: 125 iron.
    Totals per craft: iron 7.5+25+125 = 157.5, copper 57.5, plastic 20, stone 35.
    Per pack: iron 52.5, copper 19.1667, plastic 6.6667, stone 11.6667.
    Budget ratios: iron 60/52.5 = 8/7, copper 30/19.1667 = 1.565, plastic 4.5, stone 2.571 -> 8/7 pack/s.
    Aggregate (budgets and machine time unlimited) is unbounded.
    """
    hand = {
        "production-science-pack": ({"electric-furnace": 1, "productivity-module": 1, "rail": 30}, {"production-science-pack": 3}),
        "electric-furnace": ({"steel-plate": 10, "advanced-circuit": 5, "stone-brick": 10}, {"electric-furnace": 1}),
        "productivity-module": ({"advanced-circuit": 5, "electronic-circuit": 5}, {"productivity-module": 1}),
        "rail": ({"stone": 1, "iron-stick": 1, "steel-plate": 1}, {"rail": 2}),
        "iron-stick": ({"iron-plate": 1}, {"iron-stick": 2}),
        "steel-plate": ({"iron-plate": 5}, {"steel-plate": 1}),
        "stone-brick": ({"stone": 2}, {"stone-brick": 1}),
        "advanced-circuit": ({"electronic-circuit": 2, "plastic-bar": 2, "copper-cable": 4}, {"advanced-circuit": 1}),
        "electronic-circuit": ({"iron-plate": 1, "copper-cable": 3}, {"electronic-circuit": 1}),
        "copper-cable": ({"copper-plate": 1}, {"copper-cable": 2}),
    }
    L = cases.Layout("motivating_budget")
    L.entity(1, "synthetic-aggregate-plant", 0, 0)
    pool = L.inventory(1, "pool", 0, 0)
    machine_time = L.group("plant_time", None, "machine_time")
    for name, (ins, outs) in hand.items():
        recipe = db.recipes[name]
        assert {s.name: s.amount for s in recipe.ingredients} == ins, name  # pinned coefficients agree with the hand table
        assert {s.name: s.amount for s in recipe.results} == outs, name
        L.activity(name.replace("-", "_"), 1, name, [(pool, s.name, s.amount) for s in recipe.ingredients],
                   [(pool, s.name, s.amount) for s in recipe.results], None, machine_time, recipe.energy / 0.75)
    graph = L.finish()
    request = cases.request(graph, [cases.feed(f"{item}_feed", item, pool) for item in ("stone", "copper", "plastic", "iron")],
                            [cases.budget("stone", "stone", 30), cases.budget("copper", "copper-plate", 30),
                             cases.budget("plastic", "plastic-bar", 30), cases.budget("iron", "iron-plate", 60)],
                            [cases.export(pool, "production-science-pack")], recipes=tuple(hand))
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.stages["aggregate"].state == "unlimited"
    assert close(report.stages["budget"].value, 8 / 7) and close(report.stages["routing"].value, 8 / 7)
    imports = {i.id: i.rate for i in report.result.witness.imports}
    assert imports["iron_feed"] == pytest.approx(60) and imports["copper_feed"] == pytest.approx(19.1666667 * 8 / 7, rel=1e-6)
    assert "budget iron" in report.stages["budget"].certificate


def feasible_request(sample, graph):
    """The fixture's request with only the objective switched to `feasible`, re-sealed and strictly re-parsed."""
    document = cases.seal({**sample["request"], "objective": {"kind": "feasible", "export_id": None}}, "request_hash")
    request = parse_request(document, graph)
    assert request.objective.kind == "feasible" and request.objective.export_id is None
    return request


def test_feasible_objective_infeasibility_is_one_null_id_routing_scenario():
    """Contract 1.1.1: a feasibility request that cannot be met is `insufficient` with exactly one scenario.

    disconnected_circuit: producer 10 crafts/s, consumer (machine 3) 5 crafts/s, iron 10/s, so aggregate and
    budget would allow 5 science/s; but no arc reaches machine 3, so its 1/s minimum export is short by >= 1
    at the routing stage. Under a feasible objective nothing is maximized: the 5s are not scenarios (a value
    under a null ID is rejected at construction), and only the routing infeasibility certificate is reported.
    """
    graph, maximizing, sample = load_fixture("disconnected_circuit")
    request = feasible_request(sample, graph)
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)  # validate_result + JSON round trip through parse_result
    result = report.result
    assert result.status == "insufficient" and result.witness is None
    # Nothing is maximized at any stage: the looser stages are satisfiable (c = 0, state `feasible`, no value),
    # whereas the maximizing request certifies 5 there; only routing is infeasible, by exactly the missing 1/s.
    assert report.stages["aggregate"].state == "feasible" and report.stages["budget"].state == "feasible"
    assert report.stages["aggregate"].value is None and report.stages["budget"].value is None
    assert report.stages["routing"].state == "infeasible" and report.stages["routing"].shortfall == pytest.approx(1)
    assert len(result.bounds) == 1
    scenario = result.bounds[0]
    assert (scenario.stage, scenario.objective_export_id, scenario.solver_state, scenario.value) == ("routing", None, "infeasible", None)
    assert "conservation of electronic-circuit" in scenario.certificate and "shortfall of at least 1" in scenario.certificate
    assert scenario.evidence_ids and scenario.direction == "upper"
    finding = next(f for f in result.findings if f.code == "delivery_insufficient")
    assert finding.severity == "error" and "1.1.0" not in finding.message and {e.entity_number for e in finding.entity_ids} >= {3}
    assert not any(f.code == "feasibility_only" for f in result.findings)
    assert not any("Feasibility objective infeasible" in line for line in result.limitations)
    # The certificate is the same constraint cut the maximizing request reports: the shortfall model has no maximand.
    assert scenario.certificate == analyze_delivery(graph, maximizing).stages["routing"].certificate
    # Counterexample (contract): smuggling the budget-stage value 5 in as a null-ID scenario is rejected at construction.
    document = to_dict(result)
    document["bounds"].insert(0, {**document["bounds"][0], "stage": "budget", "solver_state": "optimal",
                                  "constraint_hash": content_hash({"comparison_hash": scenario.comparison_hash, "stage": "budget"}),
                                  "value": {"kind": "finite", "value": 5}, "certificate": "Certified upper bound 5"})
    with pytest.raises(ContractError, match="can only certify infeasibility"):
        parse_result(cases.seal(document, "result_hash"), graph)
    # Synthetic blocked case: scrap has no outlet so every stage is infeasible for a 1/s gear minimum; still only
    # the routing certificate is a scenario under the feasible objective (looser stages carry nothing).
    graph, request, expected = cases.blocked_byproduct(gear_minimum=1, objective=None)
    assert expected["status"] == "insufficient"
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.stages["aggregate"].state == "infeasible" and report.stages["budget"].state == "infeasible"
    assert report.result.status == "insufficient"
    assert [(b.stage, b.objective_export_id, b.solver_state, b.value) for b in report.result.bounds] == [("routing", None, "infeasible", None)]
    assert "shortfall of at least 1" in report.result.bounds[0].certificate


def test_feasible_objective_satisfiable_has_witness_and_no_scenarios():
    """pass_through, feasible objective: exact 2 gears need 4 iron of the 10 budget; iron_out minimum 0.

    With nothing to maximize the cleanup pass minimises flow + crafts + imports + exports: gears pinned
    at exactly 2 (crafts 2, 4 iron imported through belt 1), iron_out driven to its 0 minimum.
    """
    graph, request, expected = cases.pass_through(objective=None)
    assert expected["status"] == "feasible_relaxed"
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    result = report.result
    assert result.status == "feasible_relaxed" and result.bounds == () and result.witness is not None
    assert report.stages["routing"].state == "feasible" and report.stages["routing"].value is None
    exports = {e.id: e.rate for e in result.witness.exports}
    assert exports["gear_out"] == pytest.approx(2) and exports["iron_out"] == pytest.approx(0)
    assert {i.id: i.rate for i in result.witness.imports}["iron_feed"] == pytest.approx(4)
    assert {a.activity_id: a.crafts_per_s for a in result.witness.activities}["gears"] == pytest.approx(2)
    assert any(f.code == "feasibility_only" and f.severity == "info" for f in result.findings)
    assert not any(f.code in ("delivery_insufficient", "delivery_upper_bound") for f in result.findings)
    # Same on the contract fixture whose maximizing form is feasible: shared_budget (reserved exact 5 of 10 iron).
    graph, _, sample = load_fixture("shared_budget")
    report = analyze_delivery(graph, feasible_request(sample, graph))
    check_result_contract(report, graph)
    assert report.result.status == "feasible_relaxed" and report.result.bounds == () and report.result.witness is not None


def test_maximize_objective_unchanged_by_the_feasible_branch():
    """Regression: disconnected_circuit maximizing `product` keeps three named scenarios (5, 5, infeasible)."""
    graph, request, _ = load_fixture("disconnected_circuit")
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert report.result.status == "insufficient"
    assert [(b.stage, b.objective_export_id, b.solver_state, None if b.value is None else b.value.value) for b in report.result.bounds] == [
        ("aggregate", "product", "optimal", 5), ("budget", "product", "optimal", 5), ("routing", "product", "infeasible", None)]
    # And a feasible maximizing case keeps its certified numbers: pass_through 20 / 6 / 6 with a witness.
    graph, request, expected = cases.pass_through()
    report = analyze_delivery(graph, request)
    check_result_contract(report, graph)
    assert [(b.stage, b.objective_export_id, b.value.value) for b in report.result.bounds] == [
        ("aggregate", "iron_out", 20), ("budget", "iron_out", 6), ("routing", "iron_out", 6)]
    assert expected == dict(aggregate=20, budget=6, routing=6, status="feasible_relaxed")
    assert report.result.witness is not None and any(f.code == "delivery_upper_bound" for f in report.result.findings)
