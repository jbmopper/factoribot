"""Regressions for audit finding F-3: aggregated `unknown_capacity_relaxed` findings.

Before this fix, `analyze_delivery` emitted one `unknown_capacity_relaxed` finding
per unknown-capacity *group* and per unknown-capacity *activity*. On the pilot
that is 623 near-identical findings (608 bulk inserters + 15 splitters) burying
the two findings a user actually needs (`docs/blueprint-routing-release-review.md`,
finding F-3). The fix aggregates by a material-independent class -- a capacity
group's own `kind` (`inserter`, `splitter`, ...) or the owning entity's
`prototype` for activities -- into one finding per class, whose `entity_ids`
lists every affected entity in full and whose message states the count, the
relaxation direction, and a capped sample of the raw group/activity IDs.

Every graph here is built with the synthetic `routing_plan` fixture builder
(SYNTHETIC, not a game observation); the pilot case additionally loads the real
pinned `wip_science.txt` blueprint the same way `test_routing_audit.py` does.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "routing_plan"))
import cases  # noqa: E402

from factoribot.blueprint_contract import parse_request  # noqa: E402
from factoribot.blueprint_plan import analyze_delivery  # noqa: E402
from factoribot.findings import validate_result  # noqa: E402

REPO = str(Path(__file__).resolve().parents[2])


def _finding_codes(result):
    return [f.code for f in result.findings]


def _unknown_capacity_findings(result):
    return [f for f in result.findings if f.code == "unknown_capacity_relaxed"]


def unknown_capacity_layout():
    """Three unknown-capacity inserter hand-offs plus one unknown-capacity splitter.

    Each inserter arc uses its own capacity group (`ins_1`, `ins_3`, `ins_5`, all
    `kind="inserter"`) on a distinct entity; the splitter arc uses one more group
    (`split_body`, `kind="splitter"`) on a fifth. All four groups are unknown
    capacity. Machine craft capacities are finite (10/s) and every material
    balances, so the model is fully resolved and bounds are advertisable -- the
    point of this fixture is the *finding count and scope*, not the bound value.
    """
    L = cases.Layout("unknown_capacity_aggregation")
    inserter_entities = []
    feeds = []
    surplus_outlets = []
    for n in (1, 3, 5):
        p, q = L.belt(n, n * 2, 0)
        inv, out = L.machine(n + 1, n * 2 + 1, 0)
        group = L.group(f"ins_{n}", "unknown", "inserter")
        L.arc(f"pickup_{n}", q, inv, group)
        L.activity(f"gears_{n}", n + 1, "synthetic-gear", [(inv, "iron-plate", 1)],
                   [(out, "iron-gear-wheel", 1)], 10, L.group(f"m{n + 1}_time", 1, "machine_time"))
        inserter_entities.append(n)
        feeds.append(cases.feed(f"feed_{n}", "iron", p))
        surplus_outlets.append(cases.surplus(out, "iron-gear-wheel", f"gear_surplus_{n}", ceiling=100))

    p7, q7 = L.belt(7, 14, 0)
    inv8, out8 = L.machine(8, 15, 0)
    L.arc("split_pickup", q7, inv8, L.group("split_body", "unknown", "splitter"))
    L.activity("gears_7", 8, "synthetic-gear", [(inv8, "iron-plate", 1)], [(out8, "iron-gear-wheel", 1)], 10,
               L.group("m8_time", 1, "machine_time"))
    feeds.append(cases.feed("feed_7", "iron", p7))

    graph = L.finish()
    # First machine's output is the objective export; the rest leave via surplus
    # so every material balances without constraining the finding-count assertion.
    first_out = cases.ep(2, "output")
    exports = [cases.export(first_out, "iron-gear-wheel", 0, "gear_out", ceiling=100)]
    surplus_outlets = [s for s in surplus_outlets if s["id"] != "gear_surplus_1"]
    request = cases.request(graph, feeds, [cases.budget("iron", "iron-plate", 40)], exports,
                            surplus_outlets=surplus_outlets, recipes=("synthetic-gear",), objective="gear_out")
    return graph, request, inserter_entities


def test_unknown_groups_aggregate_into_one_finding_per_kind():
    graph, request, inserter_entities = unknown_capacity_layout()
    result = analyze_delivery(graph, request).result
    validate_result(result, graph)

    ucr = _unknown_capacity_findings(result)
    assert len(ucr) == 2, [f.message for f in ucr]

    by_message = {f: f.message for f in ucr}
    inserter_finding = next(f for f in ucr if "inserter" in f.message)
    splitter_finding = next(f for f in ucr if "splitter" in f.message)
    assert inserter_finding is not splitter_finding

    assert {e.entity_number for e in inserter_finding.entity_ids} == set(inserter_entities)
    assert {e.entity_number for e in splitter_finding.entity_ids} == {7}

    assert "3 inserter capacity group" in inserter_finding.message
    assert "ins_1" in inserter_finding.message and "ins_3" in inserter_finding.message and "ins_5" in inserter_finding.message
    assert "1 splitter capacity group" in splitter_finding.message
    assert "split_body" in splitter_finding.message
    assert "unlimited" in inserter_finding.message and "unlimited" in splitter_finding.message

    routing = next(b for b in result.bounds if b.stage == "routing")
    assert "unknown_capacity_unlimited" in routing.relaxations

    # Total finding count stays small even though 4 groups were unknown.
    assert len(result.findings) < 6, _finding_codes(result)


def test_finding_ids_are_unique_and_recomputable():
    from factoribot.findings import finding_id

    graph, request, _ = unknown_capacity_layout()
    result = analyze_delivery(graph, request).result
    ids = [f.id for f in result.findings]
    assert len(set(ids)) == len(ids)
    for f in result.findings:
        assert f.id == finding_id(f.code, f.entity_ids, f.endpoint_ids, f.material, f.evidence_ids)


def test_repeated_analysis_is_deterministic():
    graph, request, _ = unknown_capacity_layout()
    results = [analyze_delivery(graph, request).result for _ in range(3)]
    hashes = {r.result_hash for r in results}
    assert len(hashes) == 1
    id_orders = {tuple(f.id for f in r.findings) for r in results}
    assert len(id_orders) == 1
    message_orders = {tuple(f.message for f in r.findings) for r in results}
    assert len(message_orders) == 1


def unknown_activity_layout():
    """Two unknown-capacity `assembling-machine-2` activities and one `electric-furnace`.

    Activities merge by the owning entity's `prototype`, so the two AM2 machines
    collapse into one finding while the furnace stays separate.
    """
    L = cases.Layout("unknown_activity_aggregation")
    inv1, out1 = L.machine(1, 0, 0, name="assembling-machine-2")
    inv2, out2 = L.machine(2, 2, 0, name="assembling-machine-2")
    inv3, out3 = L.machine(3, 4, 0, name="electric-furnace")
    for n, inv, out in ((1, inv1, out1), (2, inv2, out2), (3, inv3, out3)):
        L.activity(f"craft_{n}", n, "synthetic-gear", [(inv, "iron-plate", 1)], [(out, "iron-gear-wheel", 1)],
                   "unknown", L.group(f"m{n}_time", 1, "machine_time"), seconds_per_craft=0.1)
    graph = L.finish()
    feeds = [cases.feed(f"feed_{n}", "iron", inv) for n, inv in ((1, inv1), (2, inv2), (3, inv3))]
    exports = [cases.export(out1, "iron-gear-wheel", 0, "gear_out", ceiling=100)]
    surplus_outlets = [cases.surplus(out2, "iron-gear-wheel", "gear_surplus_2", ceiling=100),
                       cases.surplus(out3, "iron-gear-wheel", "gear_surplus_3", ceiling=100)]
    request = cases.request(graph, feeds, [cases.budget("iron", "iron-plate", 30)], exports,
                            surplus_outlets=surplus_outlets, recipes=("synthetic-gear",), objective="gear_out")
    return graph, request


def test_unknown_activities_aggregate_by_prototype():
    graph, request = unknown_activity_layout()
    result = analyze_delivery(graph, request).result
    validate_result(result, graph)

    ucr = _unknown_capacity_findings(result)
    assert len(ucr) == 2, [f.message for f in ucr]
    am2 = next(f for f in ucr if "assembling-machine-2" in f.message)
    furnace = next(f for f in ucr if "electric-furnace" in f.message)
    assert {e.entity_number for e in am2.entity_ids} == {1, 2}
    assert {e.entity_number for e in furnace.entity_ids} == {3}
    assert "2 assembling-machine-2 activity" in am2.message
    assert "1 electric-furnace activity" in furnace.message


def test_pilot_finding_count_stays_small_without_hiding_absent_modded_poles():
    """The pilot remains concise when the base profile cannot classify its poles.

    Reproduces `test_pilot_bound_under_a_declaration_is_only_as_good_as_the_declaration`
    from `test_routing_audit.py`, which is the scenario the release review measured
    at 626 findings (623 `unknown_capacity_relaxed`). The base-only 2.0.77 extract
    no longer knows that the absent modded entity is a power pole, so a subsystem
    declaration cannot erase its possible topology gap.
    """
    from factoribot.gamedata import load_database
    from factoribot.routing import RecipeSource
    from factoribot.routing_public import build_layout, request_unresolved, seal_request

    template = copy.deepcopy(json.load(open(os.path.join(
        REPO, "daemon/tests/fixtures/routing_public/pilot_request_template.json"))))
    template["assumptions"]["irrelevant"] = [dict(
        id="audit_power", subsystem="power", entity_ids=[],
        basis="power_assumed_available",
        justification="AUDIT EXPERIMENT: asserts the modded substations move no items.")]
    assignments = json.load(open(os.path.join(
        REPO, "daemon/tests/fixtures/routing_public/pilot_assignments.json")))
    layout = build_layout(open(os.path.join(REPO, "daemon/tests/fixtures/wip_science.txt")).read(),
                          provenance="development_pilot",
                          recipes=RecipeSource(load_database(None)))
    document = seal_request(template, layout, assignments)
    reasons = request_unresolved(document, layout)
    assert sorted(reasons) == [
        "unsupported topology: gap_e162",
        "unsupported topology: gap_e1882",
        "unsupported topology: gap_e255",
    ]

    result = analyze_delivery(layout.graph, parse_request(document, layout.graph)).result
    validate_result(result, layout.graph)

    assert result.status == "partial" and result.bounds == ()
    assert len(result.findings) == 3, _finding_codes(result)
    assert {finding.code for finding in result.findings} == {"unresolved_topology_gap"}
    # The declaration is retained for audit, but cannot classify or dismiss an
    # entity that is absent from the current profile.
    assert "irrelevant:audit_power:power:power_assumed_available" in result.assumptions
