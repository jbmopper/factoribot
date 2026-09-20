"""Task 07 acceptance: the pinned development pilot, end to end.

One graph build (about 6 s) shared by every test here. If these fail because the
graph changed, regenerate the fixtures with
`daemon/tests/fixtures/routing_public/generate.py` and re-read its README: the
checked-in request pins the pilot's identity on purpose.

Nothing here asserts a delivery number for the pilot, because none is
advertisable: its three `ee-super-substation` poles have an unidentified mod
origin, its 76 furnaces declare no recipe, and no mechanics rule is observed.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from factoribot import routing_public as rp
from factoribot.findings import parse_result
from factoribot.blueprint_contract import to_dict

ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "daemon/tests/fixtures/wip_science.txt"
FIXTURES = ROOT / "daemon/tests/fixtures/routing_public"


@pytest.fixture(scope="module")
def layout():
    from factoribot.routing import RecipeSource

    try:
        recipes = RecipeSource()
    except (OSError, ValueError) as exc:
        pytest.skip(f"the pilot's assembling-machine activities need the game dump: {exc}")
    return rp.resolve_layout(
        {"blueprint_string": PILOT.read_text(), "provenance": "development_pilot"},
        recipes=recipes,
    )


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_the_checked_in_fixtures_still_describe_this_graph(layout):
    provenance = load("pilot_provenance.json")
    assert provenance["graph_hash"] == layout.graph_hash, (
        "the pilot graph changed; rerun daemon/tests/fixtures/routing_public/generate.py")
    assert provenance["counts"] == layout.counts()
    # The contract's own pilot record: 2771 entities in one leaf.
    assert layout.counts()["entities"] == 2771
    assert layout.graph.selected_paths == ((),)


def test_the_saved_pilot_request_seals_and_replays_with_matching_hashes(layout):
    template, assignments = load("pilot_request_template.json"), load("pilot_assignments.json")
    first = rp.seal_request(template, layout, assignments)
    second = rp.seal_request(json.loads(json.dumps(template)), layout,
                             json.loads(json.dumps(assignments)))
    assert first == second
    assert first["graph_hash"] == layout.graph_hash
    assert first["request_hash"].startswith("sha256:")


def test_the_pilot_analysis_is_partial_with_the_reasons_named(layout):
    document = rp.seal_request(load("pilot_request_template.json"), layout, load("pilot_assignments.json"))
    report = rp.analyze_layout(layout, document)
    summary = rp.analysis_summary(layout, report)

    assert summary["status"] == "partial"
    assert summary["bounds_advertised"] is False
    assert summary["bounds"] == []
    assert report.result.witness is None
    # Exactly the three unidentified-mod entities, retained as topology gaps.
    assert len(summary["unresolved_reasons"]) == 3
    assert all(r.startswith("unsupported topology: gap_e") for r in summary["unresolved_reasons"])
    assert summary["findings"]["by_code"] == {"unresolved_topology_gap": 3}
    # The declared mod is repeated in the result's audit assumptions.
    assert "mod:unknown:unknown" in summary["assumptions"]

    # The result document round-trips through the contract validator, so a host
    # can save it and a later `routes finding` can read it back.
    document_out = to_dict(report.result)
    reloaded = parse_result(json.loads(json.dumps(document_out)), layout.graph)
    assert reloaded.result_hash == report.result.result_hash


def test_a_pilot_finding_resolves_to_its_original_entity_location(layout):
    document = rp.seal_request(load("pilot_request_template.json"), layout, load("pilot_assignments.json"))
    report = rp.analyze_layout(layout, document)
    entities = {e.id: e for e in layout.graph.entities}
    findings = [f for f in report.result.findings if f.code == "unresolved_topology_gap"]
    rows = [rp.entity_row(entities[i], include_raw=True)
            for finding in findings for i in finding.entity_ids]
    assert rows and all(r["prototype"] == "ee-super-substation" for r in rows)
    assert all(r["subsystem"] == "unknown" and r["mod"] == "unknown" for r in rows)
    for row in rows:
        # The world position comes back, and so does the untouched blueprint record.
        assert row["original_record"]["position"] == row["position"]
        assert row["original_record"]["name"] == "ee-super-substation"


def test_no_pilot_mechanic_is_observed(layout):
    """The gate that keeps every pilot arc relaxed or conditional."""
    assert "exact" not in {arc.semantics for arc in layout.graph.arcs}
    evidence = rp.mechanics_evidence()
    assert evidence["observed"] == 0 and evidence["gate"] == "unmet"
    assert layout.unobserved_mechanics, "the pilot relies on unobserved mechanics and must say so"


def test_the_task_19_inference_policy_seals_against_this_same_graph(layout):
    """The policy behind the documented `routes infer` pilot run must be sealable.

    Its three `ee-super-substation` poles resolve as mod `unknown` with subsystem
    `unknown`, so that is the scope the declaration has to grant. Naming a
    subsystem the analyzer never assigns to an unidentified prototype (`power`,
    say) rejects every such entity as out of scope.
    """
    policy = json.loads(
        (ROOT / "daemon/tests/fixtures/furnace_inference/pilot_policy.json").read_text())
    unknown = next(mod for mod in policy["assumptions"]["mods"] if mod["name"] == "unknown")
    assert unknown["provides"] == ["unknown"]

    document = rp.seal_request(policy, layout, load("pilot_assignments.json"))
    assert document["graph_hash"] == layout.graph_hash

    unknown["provides"] = ["power"]
    with pytest.raises(rp.PublicError, match="outside declared mod scope"):
        rp.seal_request(policy, layout, load("pilot_assignments.json"))
