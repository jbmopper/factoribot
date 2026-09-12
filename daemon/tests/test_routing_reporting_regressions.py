"""Regressions for delivery-report finding identity (Fix B).

Finding identity is `code + sorted entity/endpoint scope + material + sorted evidence`
(contract, "Finding IDs"); severity and message text are outside it. Reporting therefore
has to give semantically different facts different codes, and deliberately merge whatever
the identity cannot express, instead of emitting two records with one ID -- which the
contract rejects with `ContractError: duplicate finding ID`.

Every graph here is built with the synthetic `routing_plan` fixture builder; requests are
built through the fixture's own document builder and resealed, so they are valid contract
requests, not doctored records.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "routing_plan"))
import cases  # noqa: E402

from factoribot.blueprint_contract import ContractError, parse_request, unresolved_reasons  # noqa: E402
from factoribot.blueprint_plan import PlanOptions, analyze_delivery  # noqa: E402
from factoribot.findings import finding_id, validate_result  # noqa: E402

ALTERING_MOD = dict(name="itemtweaks", version="1.2.3", provides=[], alters_item_mechanics=True)
SECOND_MOD = dict(name="quality-rework", version="0.4.0", provides=[], alters_item_mechanics=True)


def codes(result):
    return [f.code for f in result.findings]


def message_for(result, code):
    return next(f.message for f in result.findings if f.code == code)


def check_identity(result):
    """Every ID is unique, sorted, and recomputable from the identity inputs alone."""
    ids = [f.id for f in result.findings]
    assert len(set(ids)) == len(ids), ids
    assert ids == sorted(ids)
    for finding in result.findings:
        assert finding.id == finding_id(finding.code, finding.entity_ids, finding.endpoint_ids,
                                        finding.material, finding.evidence_ids)


def pass_through_request(graph, *, power="assumed_available", mods=None, budgets=None):
    """The `pass_through` request rebuilt through the fixture builder and resealed."""
    document = cases.request_document(
        graph, [cases.feed("iron_feed", "iron", cases.ep(1, "left_in"))],
        budgets or [cases.budget("iron", "iron-plate", 10)],
        [cases.export(cases.ep(1, "left_out"), "iron-plate", 0, "iron_out", ceiling=20),
         cases.export(cases.ep(2, "output"), "iron-gear-wheel", 2, "gear_out", "exact")],
        recipes=("synthetic-gear2",), objective="iron_out", power=power)
    if mods is not None:
        document["assumptions"]["mods"] = [cases.BASE_DECLARATION] + list(mods)
    return parse_request(cases.seal(document, "request_hash"), graph)


# ---------------------------------------------------------------------------
# The two reported failures
# ---------------------------------------------------------------------------

def test_unknown_power_and_altering_mod_report_partial_with_distinct_findings():
    """Two unresolved reasons with no graph scope at all used to hash to one ID.

    `unresolved_reasons` returns ("power availability unknown", "mod alters item
    mechanics: itemtweaks"). Both were reported under code `unresolved_model` with an
    empty entity/endpoint/material/evidence scope, so both findings got the same ID and
    `parse_result` raised ContractError instead of returning the `partial` result.
    """
    graph, _, _ = cases.pass_through()
    request = pass_through_request(graph, power="unknown", mods=[ALTERING_MOD])
    assert unresolved_reasons(request, graph) == ("power availability unknown",
                                                  "mod alters item mechanics: itemtweaks")

    report = analyze_delivery(graph, request)
    result = report.result
    validate_result(result, graph)
    check_identity(result)
    assert result.status == "partial" and not result.bounds and result.witness is None
    assert sorted(codes(result)) == ["unresolved_mod_mechanics", "unresolved_power"]
    # Neither explanation is lost, and each names its own reason.
    assert "power availability unknown" in message_for(result, "unresolved_power")
    assert "itemtweaks" in message_for(result, "unresolved_mod_mechanics")
    assert report.unresolved == unresolved_reasons(request, graph)


def test_every_stage_at_the_size_limit_reports_solver_limit_once_per_stage():
    """Three limited stages used to emit three scope-less `solver_limit` findings.

    `PlanOptions(max_variables=0)` puts aggregate, budget and routing over the size
    limit before any allocation. The three findings differed only in message text, which
    identity ignores, so the result could not be sealed at all.
    """
    graph, request, _ = cases.pass_through()
    report = analyze_delivery(graph, request, PlanOptions(max_variables=0))
    result = report.result
    validate_result(result, graph)
    check_identity(result)
    assert result.status == "solver_limit" and not result.bounds and result.witness is None
    assert sorted(codes(result)) == ["solver_limit_aggregate", "solver_limit_budget",
                                     "solver_limit_routing"]
    for stage in ("aggregate", "budget", "routing"):
        assert report.stages[stage].state == "size_limit"
        message = message_for(result, f"solver_limit_{stage}")
        assert message.startswith(f"Stage {stage}:") and "size limit" in message


def test_partial_size_limit_still_names_only_the_limited_stage():
    """A counterexample to "just merge everything": one limited stage stays one finding."""
    graph, request, _ = cases.pass_through()
    # Routing has 8 variables here, the relaxed stages 4: only routing is over the limit.
    report = analyze_delivery(graph, request, PlanOptions(max_variables=6))
    check_identity(report.result)
    assert report.result.status == "solver_limit"
    assert codes(report.result) == ["solver_limit_routing"]
    assert report.stages["aggregate"].state == "optimal" and report.stages["routing"].state == "size_limit"


# ---------------------------------------------------------------------------
# The same collision in other repeated categories
# ---------------------------------------------------------------------------

def test_two_excluded_furnace_alternatives_on_one_entity_keep_both_messages():
    """Three candidates, one assignment: two `furnace_alternative_excluded` findings.

    Both name the same entity and the same evidence record, and the activity ID is not
    part of the contract's identity, so the two records are merged on purpose and the
    merged message still names both excluded activities.
    """
    L = cases.Layout("duplicate_furnace_alternatives")
    L.entity(1, "electric-furnace", 0, 0, candidates=("copper-plate", "iron-plate", "stone-brick"))
    inv1 = L.inventory(1, "ingredients", 0, 0)
    out1 = L.port(1, "output", .5, 0, "outgoing")
    _, q2 = L.belt(2, 2, 0)
    L.arc("furnace_to_belt", out1, cases.ep(2, "left_in"), L.transfer())
    machine_time = L.group("furnace_time", 1, "machine_time")
    L.activity("plates", 1, "iron-plate", [(inv1, "iron-ore", 1)], [(out1, "iron-plate", 1)], 10, machine_time)
    L.activity("bricks", 1, "stone-brick", [(inv1, "stone", 2)], [(out1, "stone-brick", 1)], 10, machine_time)
    L.activity("copper", 1, "copper-plate", [(inv1, "copper-ore", 1)], [(out1, "copper-plate", 1)], 10, machine_time)
    graph = L.finish()
    request = cases.request(graph, [cases.feed("stone_feed", "stone", inv1)],
                            [cases.budget("stone", "stone", 10)], [cases.export(q2, "stone-brick")],
                            recipes=("copper-plate", "iron-plate", "stone-brick"),
                            furnaces=[dict(entity=cases.eid(1), recipe="stone-brick")])

    result = analyze_delivery(graph, request).result
    validate_result(result, graph)
    check_identity(result)
    excluded = message_for(result, "furnace_alternative_excluded")
    assert "plates" in excluded and "copper" in excluded and "bricks" not in excluded
    # 10 stone/s at 2 stone per brick = 5 bricks/s; the machine allows 10 crafts/s.
    assert abs(report_value(result) - 5) < 1e-6


def report_value(result):
    return next(b.value.value for b in result.bounds if b.stage == "routing")


def test_two_unknown_capacity_groups_on_one_arc_keep_both_messages():
    """Both groups resolve to the same entity and evidence; the group ID is not in the ID."""
    graph, request = unknown_group_case()
    result = analyze_delivery(graph, request).result
    validate_result(result, graph)
    check_identity(result)
    relaxed = message_for(result, "unknown_capacity_relaxed")
    assert "inserter_a" in relaxed and "inserter_b" in relaxed
    routing = next(b for b in result.bounds if b.stage == "routing")
    assert "unknown_capacity_unlimited" in routing.relaxations


def unknown_group_case():
    L = cases.Layout("duplicate_unknown_groups")
    _, q1 = L.belt(1, 0, 0)
    inv2, out2 = L.machine(2, 2, 0)
    L.arc("pickup", q1, inv2, [(L.group("inserter_a", "unknown", "inserter"), 1),
                               (L.group("inserter_b", "unknown", "inserter"), 1)])
    L.activity("gears", 2, "synthetic-gear", [(inv2, "iron-plate", 1)],
               [(out2, "iron-gear-wheel", 1)], 10, L.group("m2_time", 1, "machine_time"))
    graph = L.finish()
    request = cases.request(graph, [cases.feed("iron_feed", "iron", cases.ep(1, "left_in"))],
                            [cases.budget("iron", "iron-plate", 20)],
                            [cases.export(out2, "iron-gear-wheel")], recipes=("synthetic-gear",))
    return graph, request


def test_two_parallel_disabled_connections_keep_both_messages():
    """Parallel conditional arcs share source, target and evidence."""
    L = cases.Layout("duplicate_disabled_arcs")
    _, q1 = L.belt(1, 0, 0)
    inv2, out2 = L.machine(2, 2, 0)
    L.arc("gate_a", q1, inv2, L.transfer(), semantics="conditional", conditions=("circuit_a",))
    L.arc("gate_b", q1, inv2, L.transfer(), semantics="conditional", conditions=("circuit_b",))
    L.activity("gears", 2, "synthetic-gear", [(inv2, "iron-plate", 1)],
               [(out2, "iron-gear-wheel", 1)], 10, L.group("m2_time", 1, "machine_time"))
    graph = L.finish()
    request = cases.request(graph, [cases.feed("iron_feed", "iron", cases.ep(1, "left_in"))],
                            [cases.budget("iron", "iron-plate", 20)],
                            [cases.export(out2, "iron-gear-wheel")], recipes=("synthetic-gear",),
                            controls=(("circuit_a", False), ("circuit_b", False)))

    result = analyze_delivery(graph, request).result
    validate_result(result, graph)
    check_identity(result)
    disabled = message_for(result, "control_disabled_connection")
    assert "gate_a" in disabled and "gate_b" in disabled
    assert "circuit_a" in disabled and "circuit_b" in disabled
    # Both routes are closed, so nothing reaches the machine.
    assert report_value(result) == 0 and any(f.code == "zero_objective" for f in result.findings)


def test_unfed_budgets_are_separated_by_their_material():
    """`budget_without_feed` is scoped by material only, which the contract makes sufficient.

    Budgets are global per material (`unique(... "global material budget")`), so two
    unfed budgets can never share a material and never share an ID. Two unfed budgets of
    *different* materials must stay two findings rather than being merged away.
    """
    graph, _, _ = cases.pass_through()
    request = pass_through_request(graph, budgets=[
        cases.budget("iron", "iron-plate", 10),
        cases.budget("copper", "copper-plate", 3),
        cases.budget("stone", "stone", 5)])

    result = analyze_delivery(graph, request).result
    validate_result(result, graph)
    check_identity(result)
    unfed = [f for f in result.findings if f.code == "budget_without_feed"]
    assert {f.material.name for f in unfed} == {"copper-plate", "stone"}
    assert "copper" in next(f for f in unfed if f.material.name == "copper-plate").message
    assert "stone" in next(f for f in unfed if f.material.name == "stone").message
    # The unfed budgets add nothing: 10 iron - 2 * 2 per exact gear = 6 iron/s exported.
    assert abs(report_value(result) - 6) < 1e-6

    with pytest.raises(ContractError, match="duplicate global material budget"):
        pass_through_request(graph, budgets=[cases.budget("iron", "iron-plate", 10),
                                             cases.budget("spare", "iron-plate", 4)])


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", ["normal", "unresolved", "solver_limit", "merged"])
def test_repeated_analysis_is_deterministic(case):
    """Same inputs, same result hash and same finding order across runs."""
    graph, _, _ = cases.pass_through()
    options = PlanOptions()
    if case == "normal":
        request = pass_through_request(graph)
    elif case == "unresolved":
        request = pass_through_request(graph, power="unknown", mods=[ALTERING_MOD, SECOND_MOD])
    elif case == "solver_limit":
        request, options = pass_through_request(graph), PlanOptions(max_variables=0)
    else:
        graph, request = unknown_group_case()

    results = [analyze_delivery(graph, request, options).result for _ in range(3)]
    hashes = {r.result_hash for r in results}
    assert len(hashes) == 1, hashes
    assert len({tuple(f.id for f in r.findings) for r in results}) == 1
    assert len({tuple(f.message for f in r.findings) for r in results}) == 1
    for result in results:
        check_identity(result)


def test_two_altering_mods_are_merged_without_losing_either_name():
    """Mod names cannot enter the identity, so the two reasons are merged deliberately."""
    graph, _, _ = cases.pass_through()
    request = pass_through_request(graph, power="unknown", mods=[ALTERING_MOD, SECOND_MOD])
    result = analyze_delivery(graph, request).result
    validate_result(result, graph)
    check_identity(result)
    assert result.status == "partial"
    merged = message_for(result, "unresolved_mod_mechanics")
    assert "itemtweaks" in merged and "quality-rework" in merged
    assert merged.index("itemtweaks") < merged.index("quality-rework")  # contract order kept
    assert sorted(codes(result)) == ["unresolved_mod_mechanics", "unresolved_power"]


def test_identity_ignores_message_text_and_severity():
    """The contract's identity inputs are the only thing that separates findings."""
    graph, request, _ = cases.pass_through()
    result = analyze_delivery(graph, request).result
    bound = next(f for f in result.findings if f.code == "delivery_upper_bound")
    same = finding_id(bound.code, bound.entity_ids, bound.endpoint_ids, bound.material, bound.evidence_ids)
    assert same == bound.id
    # A different code is a different finding; a different message is not.
    assert finding_id("zero_objective", bound.entity_ids, bound.endpoint_ids, bound.material,
                      bound.evidence_ids) != bound.id
