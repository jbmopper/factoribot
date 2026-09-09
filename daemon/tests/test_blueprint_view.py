"""Viewer rendering tests (task 06).

These check what the renderer is responsible for: rendering each contract
fixture, keeping hostile imported text inert, round-tripping an assignment
document through `parse_assignments`, and detecting stale hashes and unresolved
identities. They deliberately do not assert fixture hashes or a schema version
string: fixtures are loaded through the contract's own parse functions.
"""
import json
import pathlib
import re

import pytest

from factoribot.blueprint_contract import (
    ContractError, content_hash, parse_assignments, parse_graph, to_dict,
)
from factoribot.findings import parse_result
from factoribot import blueprint_view
from factoribot.blueprint_view import (
    assignment_set_from_document, build_view_model, check_assignment_document,
    embed_json, render_view,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "routing_contracts"
ASSETS = pathlib.Path(blueprint_view.__file__).parent / "blueprint_view_assets"

HOSTILE = [
    "</script><img src=x onerror=\"window.__pwned=1\"><!--",
    "</SCRIPT ><svg/onload=alert(1)>",
    "{\"closing\": \"</script>\"} & <b>markup</b>",
    "line separator paragraph",
]


def bundles():
    for path in sorted(FIXTURES.glob("*.json")):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(bundle, dict) and "graph" in bundle:
            yield path.stem, bundle


def load(name):
    bundle = json.loads((FIXTURES / (name + ".json")).read_text(encoding="utf-8"))
    graph = parse_graph(bundle["graph"])
    result = parse_result(bundle["result"], graph) if bundle.get("result") else None
    assignments = parse_assignments(bundle["assignments"], graph) if bundle.get("assignments") else None
    return bundle, graph, result, assignments


CASES = [name for name, _ in bundles()]


def data_island(html):
    match = re.search(r'<script id="factoribot-view-data" type="application/json">(.*?)</script>',
                      html, re.S)
    assert match, "the embedded data island is missing"
    return match.group(1)


# ----------------------------------------------------------------- rendering

@pytest.mark.parametrize("name", CASES)
def test_renders_every_contract_fixture(name):
    bundle, graph, result, assignments = load(name)
    html = render_view(to_dict(graph),
                       to_dict(result) if result else None,
                       to_dict(assignments) if assignments else None,
                       title="Routing audit - " + name)
    assert html.startswith("<!doctype html>")
    # the served document holds one container element: nothing is emitted per
    # entity, lane or arc, however large the graph is
    assert len(re.findall(r"<div", html)) == 1
    model = json.loads(data_island(html))
    assert model["graph"]["counts"]["entities"] == len(graph.entities)
    assert model["graph"]["counts"]["arcs"] == len(graph.arcs)
    assert len(model["result"]["findings"]) == len(result.findings)
    # the source documents are large and are not needed for display
    assert "blueprint" not in model["graph"]
    assert model["graph"]["blueprint_hash"] == graph.blueprint_hash


def test_renders_without_a_result_or_assignments():
    _, graph, _, _ = load("shared_budget")
    html = render_view(to_dict(graph))
    model = json.loads(data_island(html))
    assert model["result"] is None
    assert model["analyzed_assignments"] is None
    assert model["assignments"]["feeds"] == []


def test_renders_contract_records_directly():
    """The renderer accepts frozen records as well as their wire dicts."""
    _, graph, result, assignments = load("furnace_override")
    from_records = render_view(graph, result, assignments, title="t")
    from_dicts = render_view(to_dict(graph), to_dict(result), to_dict(assignments), title="t")
    assert from_records == from_dicts


def test_defensive_about_unknown_and_missing_fields():
    """A later schema revision must stay inspectable, not crash the page."""
    _, graph, _, _ = load("shared_budget")
    wire = to_dict(graph)
    wire["future_top_level"] = {"added": "in a later revision"}
    wire["entities"][0]["future_entity_field"] = ["a", 1]
    wire["arcs"][0]["future_arc_field"] = "value"
    model = build_view_model(wire)
    assert "future_top_level" in model["graph"]["extra"]
    assert "future_entity_field" in model["graph"]["entities"][0]["extra"]
    assert "future_arc_field" in model["graph"]["arcs"][0]["extra"]
    assert render_view(wire).startswith("<!doctype html>")
    # an empty or partial graph still renders
    assert render_view({}).startswith("<!doctype html>")
    assert render_view({"entities": [{"id": {"book_path": [], "entity_number": 1}}]}).startswith("<!doctype")


def test_schema_version_is_not_hardcoded():
    """Version strings come from the data, never from the viewer."""
    source = pathlib.Path(blueprint_view.__file__).read_text(encoding="utf-8")
    assert not re.search(r'"1\.[01]\.0"', source)
    _, graph, _, _ = load("shared_budget")
    model = build_view_model(to_dict(graph))
    assert model["graph"]["schema_version"] == graph.schema_version
    assert model["assignments"]["schema_version"] == graph.schema_version


# ------------------------------------------------------------------ escaping

def test_embed_json_escapes_markup_and_line_separators():
    text = embed_json({"payload": HOSTILE})
    for character in ("<", ">", "&", " ", " "):
        assert character not in text
    assert json.loads(text)["payload"] == HOSTILE


def hostile_result(name="shared_budget"):
    """A contract-valid result whose free text is hostile.

    Message and certificate text do not take part in the finding identity, so
    only the result hash has to be recomputed.
    """
    bundle, graph, _, _ = load(name)
    raw = json.loads(json.dumps(bundle["result"]))
    raw["findings"][0]["message"] = HOSTILE[0]
    raw["bounds"][0]["certificate"] = HOSTILE[1]
    raw["limitations"] = [HOSTILE[2]]
    raw["assumptions"] = [HOSTILE[3]]
    raw["result_hash"] = content_hash({k: v for k, v in raw.items() if k != "result_hash"})
    return graph, parse_result(raw, graph)


def test_hostile_result_text_is_inert():
    graph, result = hostile_result()
    html = render_view(to_dict(graph), to_dict(result))
    island = data_island(html)
    for payload in HOSTILE:
        assert payload not in html
    assert "</script" not in island.lower()
    assert "<!--" not in island
    assert "\\u003c" in island
    model = json.loads(island)
    assert model["result"]["findings"][0]["message"] == HOSTILE[0]
    assert model["result"]["bounds"][0]["certificate"] == HOSTILE[1]
    assert model["result"]["limitations"] == [HOSTILE[2]]
    # exactly the three script elements the template defines
    assert len(re.findall(r"<script", html)) == 2
    assert html.count("</script>") == 2


def test_hostile_graph_text_is_inert():
    """Labels, prototypes, raw records and titles arriving from a blueprint."""
    graph = {
        "schema_version": HOSTILE[0],
        "provenance": HOSTILE[1],
        "mechanics_profile": HOSTILE[2],
        "entities": [{
            "id": {"book_path": [2, 7], "entity_number": 1},
            "prototype": HOSTILE[0],
            "position": {"x": 0, "y": 0},
            "footprint": {"minimum": {"x": -0.5, "y": -0.5}, "maximum": {"x": 0.5, "y": 0.5}},
            "direction": 4, "orientation": None, "quality": HOSTILE[1],
            "support": "unsupported", "subsystem": "unknown", "mod": HOSTILE[2],
            "furnace_candidates": [HOSTILE[3]],
            "raw": {"canonical": json.dumps({"tags": {"label": HOSTILE[0]}})},
            "evidence_ids": ["fixture"],
        }],
        "evidence": [{
            "id": "fixture", "kind": "structural", "description": HOSTILE[0],
            "sources": [{"source": "blueprint", "uri": HOSTILE[1], "pointer": "/entities"}],
            "entity_ids": [], "endpoint_ids": [], "arc_path": [],
        }],
    }
    html = render_view(graph, title=HOSTILE[0])
    for payload in HOSTILE:
        assert payload not in html
    assert json.loads(data_island(html))["graph"]["entities"][0]["prototype"] == HOSTILE[0]
    # the title reaches the document escaped, not as markup
    assert "<img" not in html
    assert "&lt;/script&gt;" in html


def test_assets_carry_no_closing_tag_sequence():
    for path in (ASSETS / "view.js", ASSETS / "view.css"):
        text = path.read_text(encoding="utf-8").lower()
        assert "</script" not in text and "</style" not in text


# -------------------------------------------------- assignment round-tripping

@pytest.mark.parametrize("name", CASES)
def test_assignment_document_round_trips_through_the_contract(name):
    bundle, graph, result, assignments = load(name)
    model = build_view_model(to_dict(graph), to_dict(result), to_dict(assignments))
    document = model["assignments"]["document"]
    report = check_assignment_document(document, to_dict(graph))
    assert report["ok"], report
    reparsed = parse_assignments(json.loads(json.dumps(document)), graph)
    assert reparsed == assignments
    # identity survives verbatim, including the nested book path
    for original, copy in zip(assignments.feeds, reparsed.feeds):
        assert copy.endpoint.entity.book_path == original.endpoint.entity.book_path


def test_draft_envelope_and_bare_set_both_yield_an_assignment_set():
    _, graph, _, assignments = load("shared_budget")
    bare = to_dict(assignments)
    envelope = {
        "document_kind": blueprint_view.DOCUMENT_KIND,
        "view_version": blueprint_view.VIEW_VERSION,
        "assignments": bare,
        "proposed_request": {"budgets": [], "exports": [], "surplus": [], "objective": {}},
    }
    assert assignment_set_from_document(bare) == bare
    assert assignment_set_from_document(envelope) == bare
    assert parse_assignments(assignment_set_from_document(envelope), graph) == assignments


def test_stale_blueprint_and_graph_hashes_are_detected():
    _, graph, _, assignments = load("shared_budget")
    document = to_dict(assignments)
    document["graph_hash"] = "sha256:" + "0" * 64
    document["blueprint_hash"] = "sha256:" + "1" * 64
    report = check_assignment_document(document, to_dict(graph))
    assert not report["ok"]
    assert len(report["stale"]) == 2
    assert any("graph" in message for message in report["stale"])
    assert any("blueprint" in message for message in report["stale"])
    assert not report["unknown"]
    with pytest.raises(ContractError):
        parse_assignments(document, graph)


def test_unresolved_identities_are_reported_not_silently_dropped():
    _, graph, _, assignments = load("furnace_override")
    document = to_dict(assignments)
    document["feeds"].append({
        "id": "ghost", "budget_id": "stone",
        "endpoint": {"entity": {"book_path": [2, 7], "entity_number": 99},
                     "kind": "port", "name": "left_in"},
        "capacity": {"kind": "unlimited", "value": None},
    })
    document["furnaces"] = [{"entity": {"book_path": [2, 7], "entity_number": 1},
                             "recipe": "rocket-fuel"}]
    document["controls"] = [{"condition": "no-such-condition", "enabled": True}]
    report = check_assignment_document(document, to_dict(graph))
    assert not report["ok"] and not report["stale"]
    assert any("unknown feed endpoint" in m for m in report["unknown"])
    assert any("not a recorded candidate" in m for m in report["unknown"])
    assert any("unknown control condition" in m for m in report["unknown"])
    with pytest.raises(ContractError):
        parse_assignments(document, graph)


def test_a_feed_may_not_target_an_outgoing_port():
    _, graph, _, assignments = load("shared_budget")
    outgoing = next(p for p in graph.ports if p.role == "outgoing")
    document = to_dict(assignments)
    document["feeds"] = [{"id": "bad", "budget_id": "iron", "endpoint": to_dict(outgoing.id),
                          "capacity": {"kind": "unlimited", "value": None}}]
    report = check_assignment_document(document, to_dict(graph))
    assert any("outgoing port" in message for message in report["unknown"])


def test_check_rejects_a_document_that_is_not_an_assignment_set():
    _, graph, _, _ = load("shared_budget")
    report = check_assignment_document({"not": "an assignment set"}, to_dict(graph))
    assert not report["ok"] and report["assignments"] is None


# ------------------------------------------------------- displayed semantics

def test_finding_highlight_is_exactly_its_recorded_scope():
    _, graph, result, _ = load("large_layout")
    model = build_view_model(to_dict(graph), to_dict(result))
    finding = model["result"]["findings"][0]
    assert finding["highlight"]["entities"] == ["bp/2/7/e/1"]
    assert finding["highlight"]["endpoints"] == ["bp/2/7/e/1/lane/left"]
    assert finding["highlight"]["arcs"] == ["belt_1"]
    assert finding["focus"] is not None


def test_bounds_are_labelled_as_upper_bounds_under_relaxations():
    _, graph, result, _ = load("shared_budget")
    html = render_view(to_dict(graph), to_dict(result))
    model = json.loads(data_island(html))
    assert model["result"]["bounds"]
    for bound in model["result"]["bounds"]:
        assert bound["direction"] == "upper"
        assert "relaxed" in bound["stage_text"] or bound["stage"] == "routing"
    assert "never an achievable or measured rate" in html
    assert "upper bound under stated relaxations" in html
    for claim in ("is achievable", "achieved rate", "guaranteed rate", "will produce"):
        assert claim not in html


def test_static_findings_never_claim_current_starvation():
    _, graph, result, _ = load("disconnected_circuit")
    model = build_view_model(to_dict(graph), to_dict(result))
    for finding in model["result"]["findings"]:
        assert finding["evidence_kind"] != "observed"
        assert finding["runtime_note"].startswith("Static evidence")


def test_severity_and_evidence_kind_do_not_depend_on_colour():
    css = (ASSETS / "view.css").read_text(encoding="utf-8")
    for style in ("border-left-style: solid", "border-left-style: dashed", "border-left-style: dotted"):
        assert style in css
    _, graph, result, _ = load("unsupported_bridge")
    html = render_view(to_dict(graph), to_dict(result))
    assert "▲ WARNING" in html or "WARNING" in html
    model = json.loads(data_island(html))
    assert model["result"]["findings"][0]["evidence_kind_text"].startswith("conditional")


def test_unsupported_entities_and_gaps_stay_visible():
    _, graph, result, _ = load("unsupported_bridge")
    model = build_view_model(to_dict(graph), to_dict(result))
    assert model["graph"]["counts"]["unsupported_entities"] >= 1
    assert model["graph"]["topology_gaps"]
    gap = model["graph"]["topology_gaps"][0]
    assert gap["may_connect"] is True
    assert gap["entity_keys"]
    assert model["result"]["status"] == "partial"
    assert model["result"]["bounds"] == []


def test_declared_irrelevance_is_shown_when_the_request_records_it():
    if "declared_power" not in CASES:
        pytest.skip("no fixture declaring an irrelevant subsystem")
    _, graph, result, _ = load("declared_power")
    model = build_view_model(to_dict(graph), to_dict(result))
    declarations = model["result"]["request"]["assumptions"]["irrelevant"]
    assert declarations
    assert declarations[0]["basis"]
    assert declarations[0]["justification"]
    assert any(entity["subsystem"] for entity in model["graph"]["entities"])
