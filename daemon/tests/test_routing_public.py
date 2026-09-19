"""Task 07: the public routing surface (tools/CLI adapter layer).

These tests exercise `routing_public` and the `Toolbox` handlers directly. The
real stdio MCP acceptance lives in `test_mcp_routing.py`; the two agree on the
same structured values by construction (a cross-check test there asserts it).

Nothing here re-asserts another task's numbers except where a value is derived
by hand in the test itself.
"""
from __future__ import annotations

import json
import re
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "daemon/tests/fixtures/routing_transport"))

import layouts as L  # noqa: E402
import requests as R  # noqa: E402

from factoribot import routing_public as rp  # noqa: E402
from factoribot.blueprint import decode_blueprint_string, encode_blueprint, BlueprintDecodeError  # noqa: E402
from factoribot.blueprint_contract import EndpointId, EntityId, to_dict  # noqa: E402
from factoribot.gamedata import find_dump  # noqa: E402
from factoribot.model import Database  # noqa: E402
from factoribot.tools import TOOL_SCHEMAS, Toolbox  # noqa: E402

CONTRACT_FIXTURES = ROOT / "daemon/tests/fixtures/routing_contracts"
PUBLIC_FIXTURES = ROOT / "daemon/tests/fixtures/routing_public"


def empty_db() -> Database:
    """A database with no recipes: the belt layouts need none."""
    from factoribot.gamedata import build_database

    return build_database({"item": {}, "recipe": {}, "assembling-machine": {}})


@pytest.fixture(scope="module")
def toolbox() -> Toolbox:
    return Toolbox(empty_db(), data_source={"path": "synthetic", "sha256": "0" * 64})


def bp_string(entities) -> str:
    return encode_blueprint(L.blueprint(entities))


@pytest.fixture(scope="module")
def belt() -> str:
    return bp_string(L.two_lane_run())


def fixture(name: str) -> dict:
    return json.loads((CONTRACT_FIXTURES / f"{name}.json").read_text())


# ---------------------------------------------------------------------------
# Layout inspection
# ---------------------------------------------------------------------------

def test_layout_summary_counts_are_hand_derivable(toolbox, belt):
    """Three east-facing fast belts: 2 lanes/4 ports/2 groups each, hand-counted.

    A plausible wrong implementation returning one lane per belt would report
    3 lanes and 3 groups; per-arc capacity copies would report more than 7
    groups (6 lane groups plus the single graph-wide handover group).
    """
    out = toolbox.call("inspect_blueprint_layout", {"blueprint_string": belt})
    assert out["counts"]["entities"] == 3
    assert out["counts"]["lanes"] == 6
    assert out["counts"]["ports"] == 12
    assert out["counts"]["capacity_groups"] == 7
    assert out["identity"]["schema_version"] == "1.1.1"
    assert out["identity"]["mechanics_profile"] == "base-2.0.77-normal-v1"
    # The mechanics gate is unmet, so nothing may claim `exact`.
    assert "exact" not in out["arc_semantics"]
    assert out["mechanics_evidence"]["observed"] == 0
    assert out["mechanics_evidence"]["gate"] == "unmet"


def test_layout_identity_is_the_graph_hash_and_can_be_pinned(toolbox, belt):
    first = toolbox.call("inspect_blueprint_layout", {"blueprint_string": belt})
    again = toolbox.call("inspect_blueprint_layout", {"blueprint_string": belt})
    assert first["identity"]["graph_hash"] == again["identity"]["graph_hash"]
    pinned = toolbox.call("inspect_blueprint_layout",
                          {"blueprint_string": belt, "expect_graph_hash": first["identity"]["graph_hash"]})
    assert pinned["identity"]["graph_hash"] == first["identity"]["graph_hash"]
    other = toolbox.call("inspect_blueprint_layout",
                         {"blueprint_string": bp_string(L.turn_layout()),
                          "expect_graph_hash": first["identity"]["graph_hash"]})
    assert other["error"] == "stale_identity"


def test_provenance_is_exposed_as_a_tool_argument_and_changes_identity(toolbox, belt):
    """F-1: provenance is hashed into graph_hash but was unreachable through the MCP schema.

    Before the fix, `additionalProperties: False` on both routing tool schemas
    rejected `provenance` outright, so a request sealed by
    `factoribot routes request --provenance development_pilot` could never be
    replayed over MCP (see test_mcp_routing.py for the real stdio replay).
    """
    for name in ("inspect_blueprint_layout", "analyze_blueprint_routes"):
        schema = next(t for t in TOOL_SCHEMAS if t["name"] == name)
        prop = schema["parameters"]["properties"]["provenance"]
        assert prop["enum"] == ["game_export", "development_pilot", "synthetic"]
        assert prop["default"] == "game_export"

    default = toolbox.call("inspect_blueprint_layout", {"blueprint_string": belt})
    pilot = toolbox.call("inspect_blueprint_layout",
                         {"blueprint_string": belt, "provenance": "development_pilot"})
    assert "error" not in pilot
    # provenance is part of the graph identity, so it changes graph_hash...
    assert default["identity"]["graph_hash"] != pilot["identity"]["graph_hash"]
    # ...deterministically, so the same provenance replays the same identity.
    again = toolbox.call("inspect_blueprint_layout",
                         {"blueprint_string": belt, "provenance": "development_pilot"})
    assert again["identity"]["graph_hash"] == pilot["identity"]["graph_hash"]

    bad = toolbox.call("inspect_blueprint_layout",
                       {"blueprint_string": belt, "provenance": "not_a_real_provenance"})
    assert bad["error"] == "bad_request"


def test_pagination_is_deterministic_and_covers_every_row(toolbox, belt):
    whole = toolbox.call("inspect_blueprint_layout",
                         {"blueprint_string": belt, "section": "arcs", "detail": {"kind": "full", "limit": 200}})
    total = whole["page"]["total"]
    assert total == len(whole["arcs"]) == 10
    collected, cursor, pages = [], None, 0
    while True:
        page = toolbox.call("inspect_blueprint_layout", {
            "blueprint_string": belt, "section": "arcs",
            "detail": {"kind": "full", "limit": 3, "cursor": cursor},
        })
        collected += page["arcs"]
        pages += 1
        cursor = page["page"]["cursor"]
        if cursor is None:
            break
        assert pages < 10, "cursor did not terminate"
    assert collected == whole["arcs"]
    assert pages == 4


def test_a_cursor_from_another_graph_is_refused(toolbox, belt):
    page = toolbox.call("inspect_blueprint_layout",
                        {"blueprint_string": belt, "section": "arcs", "detail": {"kind": "full", "limit": 2}})
    other = toolbox.call("inspect_blueprint_layout", {
        "blueprint_string": bp_string(L.turn_layout()), "section": "arcs",
        "detail": {"kind": "full", "limit": 2, "cursor": page["page"]["cursor"]},
    })
    assert other["error"] == "stale_cursor"


def test_entity_scope_returns_the_original_blueprint_record(toolbox, belt):
    out = toolbox.call("inspect_blueprint_layout", {
        "blueprint_string": belt, "section": "entities",
        "detail": {"kind": "entities", "entity_ids": [{"book_path": [], "entity_number": 2}]},
    })
    assert out["page"]["total"] == 1
    row = out["entities"][0]
    assert row["id"] == {"book_path": [], "entity_number": 2, "key": "bp/root/e/2"}
    assert row["position"] == {"x": 1.5, "y": 0.5}
    assert row["original_record"]["name"] == "fast-transport-belt"
    assert row["original_record"]["position"] == {"x": 1.5, "y": 0.5}


def test_unknown_scope_entity_is_a_structured_error(toolbox, belt):
    out = toolbox.call("inspect_blueprint_layout", {
        "blueprint_string": belt, "section": "entities",
        "detail": {"kind": "entities", "entity_ids": [{"book_path": [], "entity_number": 99}]},
    })
    assert out["error"] == "bad_request" and out["entities"] == ["bp/root/e/99"]


def test_page_limits_are_bounded(toolbox, belt):
    out = toolbox.call("inspect_blueprint_layout",
                       {"blueprint_string": belt, "detail": {"kind": "full", "limit": 10000}})
    assert out["error"] == "oversized_page" and out["max_limit"] == rp.MAX_PAGE_LIMIT


def test_book_paths_use_index_values_not_array_offsets(toolbox):
    """`odd`-style book: the leaf with index 2 is not the first array element."""
    document = L.book([(7, L.straight_run(2)), (2, L.straight_run(3, first=10))])
    text = encode_blueprint(document)
    two = toolbox.call("inspect_blueprint_layout", {"blueprint_string": text, "book_path": [2]})
    seven = toolbox.call("inspect_blueprint_layout", {"blueprint_string": text, "book_path": [7]})
    assert two["counts"]["entities"] == 3 and seven["counts"]["entities"] == 2
    assert two["identity"]["selected_paths"] == [[2]]
    assert two["identity"]["graph_hash"] != seven["identity"]["graph_hash"]


def test_bound_prerequisites_name_the_unsupported_bridge(toolbox):
    out = toolbox.call("inspect_blueprint_layout", {"blueprint_string": bp_string(L.unsupported_bridge())})
    kinds = {row["kind"] for row in out["bound_prerequisites"]}
    assert "possible_bridge" in kinds
    bridge = next(r for r in out["bound_prerequisites"] if r["kind"] == "possible_bridge")
    assert "never" not in bridge["requirement"].lower() or "evidence" in bridge["requirement"]
    assert out["counts"]["topology_gaps"] == 1


# ---------------------------------------------------------------------------
# Delivery analysis
# ---------------------------------------------------------------------------

def analyze(toolbox, blueprint_string, request_document, **extra):
    return toolbox.call("analyze_blueprint_routes",
                        {"blueprint_string": blueprint_string, "request": request_document, **extra})


def belt_request(graph, *, budget=100.0):
    """Feed the left lane of belt 1, export off the left lane of belt 3."""
    return to_dict(R.make_request(
        graph,
        budgets=[R.budget("iron", "iron-plate", budget)],
        feeds=[R.feed("f1", "iron", EndpointId(EntityId((), 1), "lane", "left"))],
        exports=[R.export("out", "iron-plate", EndpointId(EntityId((), 3), "lane", "left"))],
        objective={"kind": "maximize_export", "export_id": "out"},
    ))


def test_successful_case_reports_the_hand_derived_lane_bound(toolbox, belt):
    """One fast-belt lane carries 15 items/s (task 02 extract: 30/s over two lanes).

    A per-segment double charge would report 7.5 and a per-arc capacity copy 45;
    the budget stage, which relaxes delivery, reports the declared 100.
    """
    layout = rp.resolve_layout({"blueprint_string": belt})
    out = analyze(toolbox, belt, belt_request(layout.graph))
    assert out["status"] == "feasible_relaxed"
    values = {b["stage"]: b["value"] for b in out["bounds"]}
    assert values["routing"] == {"kind": "finite", "value": 15.0}
    assert values["budget"] == {"kind": "finite", "value": 100.0}
    assert values["aggregate"] == {"kind": "unlimited", "value": None}
    assert out["witness"]["present"] and out["witness"]["exports"] == {"out": 15.0}
    assert all("upper bound" in b["meaning"] for b in out["bounds"] if b["value"])


def test_a_saved_request_replays_with_the_same_hashes(toolbox, belt):
    layout = rp.resolve_layout({"blueprint_string": belt})
    document = belt_request(layout.graph)
    first = analyze(toolbox, belt, document)
    # Round-trip the request through JSON, exactly as a saved file would.
    replay = analyze(toolbox, belt, json.loads(json.dumps(document)))
    assert first["identity"] == replay["identity"]
    assert first["identity"]["request_hash"] == document["request_hash"]
    assert first["bounds"] == replay["bounds"]
    assert first["assumptions"] == replay["assumptions"]


def test_invalid_request_is_a_result_not_an_exception(toolbox, belt):
    out = analyze(toolbox, belt, {"schema_version": "1.1.1", "not": "a request"})
    assert out["status"] == "invalid_request"
    assert out["ok"] is False
    assert out["identity"]["request_hash"] is None
    assert out["bounds"] == [] and out["bounds_advertised"] is False
    assert out["findings"]["by_code"] == {"invalid_request": 1}


def test_a_stale_request_hash_is_refused_by_the_contract(toolbox, belt):
    layout = rp.resolve_layout({"blueprint_string": belt})
    document = belt_request(layout.graph)
    document["graph_hash"] = "sha256:" + "0" * 64
    out = analyze(toolbox, belt, document)
    assert out["status"] == "invalid_request"


def test_conditional_case_keeps_both_readings_open_and_says_so(toolbox):
    """An inserter's rotation sense is unvalidated: both readings stay open."""
    text = bp_string(L.inserter_between_belts())
    layout = rp.resolve_layout({"blueprint_string": text})
    conditions = sorted({c for arc in layout.graph.arcs for c in arc.conditions})
    assert conditions == ["inserter_rotation_documented", "inserter_rotation_reversed"]
    document = to_dict(R.make_request(
        layout.graph,
        budgets=[R.budget("iron", "iron-plate", 100.0)],
        feeds=[R.feed("f1", "iron", EndpointId(EntityId((), 1), "lane", "left"))],
        exports=[R.export("out", "iron-plate", EndpointId(EntityId((), 2), "lane", "left"))],
        objective={"kind": "maximize_export", "export_id": "out"},
        control_policy="relax_open",
    ))
    out = analyze(toolbox, text, document)
    routing = next(b for b in out["bounds"] if b["stage"] == "routing")
    assert "conditional_connections_open" in routing["relaxations"]
    assert "conditional_connections_open" in out["findings"]["by_code"]


def test_unsupported_possible_bridge_withholds_every_bound(toolbox):
    text = bp_string(L.unsupported_bridge())
    layout = rp.resolve_layout({"blueprint_string": text})
    document = to_dict(R.make_request(
        layout.graph,
        budgets=[R.budget("iron", "iron-plate", 10.0)],
        feeds=[R.feed("f1", "iron", EndpointId(EntityId((), 1), "lane", "left"))],
        exports=[R.export("out", "iron-plate", EndpointId(EntityId((), 3), "lane", "left"), 1.0, "minimum")],
        objective={"kind": "maximize_export", "export_id": "out"},
    ))
    out = analyze(toolbox, text, document)
    assert out["status"] == "partial"
    assert out["bounds"] == [] and out["bounds_advertised"] is False
    assert out["findings"]["by_code"] == {"unresolved_topology_gap": 1}
    assert out["unresolved_reasons"] and out["unresolved_reasons"][0].startswith("unsupported topology")


def test_insufficient_case_from_the_contract_fixture(toolbox):
    """The fixture's own request certifies a routing infeasibility."""
    bundle = fixture("blocked_export")
    out = toolbox.call("analyze_blueprint_routes",
                       {"graph": bundle["graph"], "request": bundle["request"]})
    assert out["status"] == "insufficient"
    routing = next(b for b in out["bounds"] if b["stage"] == "routing")
    assert routing["solver_state"] == "infeasible" and routing["value"] is None
    assert "delivery_insufficient" in out["findings"]["by_code"]


def test_a_fluid_request_is_rejected_rather_than_approximated(toolbox, belt):
    layout = rp.resolve_layout({"blueprint_string": belt})
    document = belt_request(layout.graph)
    document["budgets"][0]["material"] = {"kind": "fluid", "name": "water", "quality": None}
    out = analyze(toolbox, belt, document)
    assert out["status"] == "invalid_request"


def test_analysis_sections_page_independently_of_the_request(toolbox):
    bundle = fixture("blocked_export")
    args = {"graph": bundle["graph"], "request": bundle["request"], "section": "findings"}
    first = toolbox.call("analyze_blueprint_routes", {**args, "page": {"limit": 1}})
    assert first["page"]["returned"] == 1
    # Paging never changes the identity or the numbers.
    whole = toolbox.call("analyze_blueprint_routes", {**args, "page": {"limit": 50}})
    assert first["identity"] == whole["identity"]
    assert first["bounds"] == whole["bounds"]
    if first["page"]["cursor"]:
        second = toolbox.call("analyze_blueprint_routes", {**args, "page": {"limit": 1, "cursor": first["page"]["cursor"]}})
        assert second["findings"]["page"][0] != first["findings"]["page"][0]


def test_an_analysis_cursor_is_bound_to_the_result(toolbox):
    """`furnace_override` carries two findings, so it mints a real cursor."""
    bundle = fixture("furnace_override")
    first = toolbox.call("analyze_blueprint_routes", {
        "graph": bundle["graph"], "request": bundle["request"],
        "section": "findings", "page": {"limit": 1}})
    cursor = first["page"]["cursor"]
    assert cursor and first["page"]["total"] == 2
    second = toolbox.call("analyze_blueprint_routes", {
        "graph": bundle["graph"], "request": bundle["request"],
        "section": "findings", "page": {"limit": 1, "cursor": cursor}})
    assert second["findings"]["page"][0]["id"] != first["findings"]["page"][0]["id"]
    assert second["page"]["cursor"] is None
    other = fixture("disconnected_circuit")
    out = toolbox.call("analyze_blueprint_routes", {"graph": other["graph"], "request": other["request"],
                                                    "section": "findings", "page": {"limit": 1, "cursor": cursor}})
    assert out["error"] == "stale_cursor"


# ---------------------------------------------------------------------------
# Oversized and malformed input
# ---------------------------------------------------------------------------

def test_an_oversized_blueprint_is_refused_during_decompression(toolbox):
    """A 40 MB zip bomb stops at the ceiling instead of inflating."""
    import base64

    bomb = "0" + base64.b64encode(zlib.compress(b"\0" * (40 << 20), 9)).decode("ascii")
    out = toolbox.call("inspect_blueprint_layout", {"blueprint_string": bomb})
    assert out["error"] == "bad_blueprint"
    assert out["decode_code"] == "decompressed_limit"


def test_conflicting_or_missing_sources_are_structured_errors(toolbox, belt):
    assert toolbox.call("inspect_blueprint_layout", {})["error"] == "bad_request"
    assert toolbox.call("inspect_blueprint_layout",
                        {"blueprint_string": belt, "graph": {}})["error"] == "bad_request"
    assert toolbox.call("analyze_blueprint_routes", {"blueprint_string": belt})["error"] == "bad_request"
    assert toolbox.call("inspect_blueprint_layout",
                        {"blueprint_string": belt, "section": "nope"})["error"] == "unknown_section"


def test_a_malformed_graph_document_is_refused(toolbox):
    out = toolbox.call("inspect_blueprint_layout", {"graph": {"schema_version": "1.1.1"}})
    assert out["error"] == "bad_graph"


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_tool_calls_write_no_file_and_call_no_model(toolbox, belt, tmp_path, monkeypatch):
    import factoribot.llm as llm

    def refuse(*args, **kwargs):  # any model client construction is a failure here
        raise AssertionError("a pure tool call must not construct a model client")

    monkeypatch.setattr(llm, "make_client", refuse, raising=False)
    monkeypatch.chdir(tmp_path)
    layout = rp.resolve_layout({"blueprint_string": belt})
    toolbox.call("inspect_blueprint_layout", {"blueprint_string": belt, "section": "entities",
                                              "detail": {"kind": "full", "limit": 5}})
    toolbox.call("analyze_blueprint_routes", {"blueprint_string": belt, "request": belt_request(layout.graph)})
    toolbox.call("get_capabilities", {})
    assert list(tmp_path.iterdir()) == []


def test_the_layout_cache_cannot_change_an_answer(belt):
    """A cache hit must be indistinguishable from a rebuild."""
    box = Toolbox(empty_db())
    first = box.call("inspect_blueprint_layout", {"blueprint_string": belt})
    assert box._layouts.hits == 0
    second = box.call("inspect_blueprint_layout", {"blueprint_string": belt})
    assert box._layouts.hits == 1
    box._layouts.clear()
    third = box.call("inspect_blueprint_layout", {"blueprint_string": belt})
    # Everything except the reported build timings, which are a measurement.
    strip = lambda d: {k: v for k, v in d.items() if k != "build"}  # noqa: E731
    assert strip(first) == strip(second) == strip(third)
    assert set(first["build"]) >= {"seconds", "build_seconds"}


# ---------------------------------------------------------------------------
# Capability metadata: advertise validated scope only
# ---------------------------------------------------------------------------

def test_capabilities_advertise_the_unmet_mechanics_gate(toolbox):
    caps = toolbox.call("get_capabilities", {})["blueprint_routing"]
    assert caps["mechanics_profile"] == "base-2.0.77-normal-v1"
    assert caps["mechanics_evidence"]["by_status"] == {"documented-only": 6, "pending": 10}
    assert caps["mechanics_evidence"]["observed"] == 0
    assert caps["mechanics_evidence"]["gate"] == "unmet"
    assert caps["arc_semantics_available"] == ["relaxed", "conditional"]
    assert caps["advertisable_bounds"]["pilot"] is False
    assert caps["purity"] == {**caps["purity"], "writes_files": False, "calls_a_model": False,
                              "reads_live_game_state": False}
    assert len(caps["supported_prototypes"]) == 14
    assert "synthetic" in caps["evidence_note"].lower()


def test_capability_reason_sentence_tracks_the_observed_count_not_hardcoded(tmp_path, monkeypatch):
    """F-2: the capability block's prose must track the evidence, not a fixed string.

    Before the fix, `advertisable_bounds.reason` hardcoded "Zero mechanics rules
    are observed" inside an otherwise evidence-computed structure, so it would
    have gone stale (and self-contradictory) on the first successful capture.
    Uses a scratch copy of the mechanics records; the checked-in evidence under
    daemon/factoribot/evidence/routing_mechanics_observations/ is never touched,
    mirroring the monkeypatch approach in
    test_routing_audit.py::test_capability_block_is_computed_from_the_records_not_hardcoded.
    """
    from factoribot import transport

    baseline = rp.routing_capabilities()
    assert baseline["mechanics_evidence"]["observed"] == 0
    assert baseline["mechanics_evidence"]["gate"] == "unmet"
    assert "Zero mechanics rules are observed" in baseline["advertisable_bounds"]["reason"]
    assert "unmet" in baseline["advertisable_bounds"]["reason"]

    source = ROOT / "daemon/factoribot/evidence/routing_mechanics_observations/records"
    target = tmp_path / "records"
    target.mkdir()
    for path in source.iterdir():
        document = json.loads(path.read_text())
        if document["record_id"] == "belt.straight.lane_capacity":
            document.update(
                evidence_status="observed",
                setup_blueprint="0SYNTHETIC-TEST-FIXTURE",
                measurement={"items_per_s_per_lane": 15.0},
                measurement_interval_s=60.0,
                observation_method="TEST FIXTURE, not a real capture",
                environment={"game_version": "2.0.77", "declared_mods": ["base 2.0.77"],
                             "save": "test-disposable"},
            )
        (target / path.name).write_text(json.dumps(document))

    real_load_mechanics = transport.load_mechanics
    monkeypatch.setattr(transport, "load_mechanics",
                        lambda directory=None: real_load_mechanics(str(target)))

    legacy_observed = rp.routing_capabilities()
    assert legacy_observed["mechanics_evidence"]["by_status"]["observed"] == 1
    assert legacy_observed["mechanics_evidence"]["observed"] == 0
    assert legacy_observed["mechanics_evidence"]["gate"] == "unmet"
    assert "exact" not in legacy_observed["arc_semantics_available"]

    observed_path = next(
        path for path in target.iterdir()
        if json.loads(path.read_text())["record_id"] == "belt.straight.lane_capacity"
    )
    document = json.loads(observed_path.read_text())
    document["profile"] = "base-2.0.77-normal-v1"
    observed_path.write_text(json.dumps(document))
    real_load_mechanics.cache_clear()

    flipped = rp.routing_capabilities()
    assert flipped["mechanics_evidence"]["observed"] == 1
    assert flipped["mechanics_evidence"]["gate"] == "partially observed"
    assert "exact" in flipped["arc_semantics_available"]
    # The sentence changed to match: no more claiming zero observations...
    assert "Zero mechanics rules are observed" not in flipped["advertisable_bounds"]["reason"]
    # ...and it now states the actual count.
    assert "1 of 16" in flipped["advertisable_bounds"]["reason"]
    assert "partially observed" in flipped["advertisable_bounds"]["reason"]


def test_capability_metadata_lists_every_emitted_finding_code():
    """Drift guard: a new finding code must be documented before it ships."""
    emitted = set()
    for path, pattern in (
        (ROOT / "daemon/factoribot/routing.py", r"self\._finding\(\s*\n?\s*\"([a-z_]+)\""),
        (ROOT / "daemon/factoribot/blueprint_plan.py", r"_finding\(\s*\n?\s*\"([a-z_]+)\""),
    ):
        emitted |= set(re.findall(pattern, path.read_text()))
    from factoribot import blueprint_plan

    emitted |= set(blueprint_plan._UNRESOLVED_CODES.values())
    emitted |= set(blueprint_plan._STAGE_LIMIT_CODES.values())
    emitted.add("unresolved_model")
    assert emitted, "the drift guard found no finding codes at all"
    assert emitted <= set(rp.FINDING_CODES), sorted(emitted - set(rp.FINDING_CODES))


def test_the_new_tools_are_registered_and_documented():
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert {"inspect_blueprint_layout", "analyze_blueprint_routes"} <= names
    # Every pre-existing tool survives.
    assert {"get_capabilities", "plan_production", "search_items", "get_recipe", "list_machines",
            "list_modules", "list_belts", "solve_production", "evaluate_throughput",
            "analyze_blueprint"} <= names
    for name in ("inspect_blueprint_layout", "analyze_blueprint_routes"):
        schema = next(t for t in TOOL_SCHEMAS if t["name"] == name)
        text = schema["description"].lower()
        assert "upper bound" in text or "never" in text
        assert "observed" in text or "relaxed" in text
        assert schema["parameters"]["additionalProperties"] is False


# ---------------------------------------------------------------------------
# Saved-request assembly (CLI host action)
# ---------------------------------------------------------------------------

def test_seal_request_refuses_a_stale_assignment_document(belt):
    layout = rp.resolve_layout({"blueprint_string": belt})
    template = json.loads((PUBLIC_FIXTURES / "pilot_request_template.json").read_text())
    stale = {"schema_version": "1.1.1", "blueprint_hash": "sha256:" + "0" * 64,
             "graph_hash": "sha256:" + "0" * 64, "feeds": [], "furnaces": [], "controls": []}
    with pytest.raises(rp.PublicError) as excinfo:
        rp.seal_request(template, layout, stale)
    assert excinfo.value.code == "stale_identity"


def test_seal_request_accepts_the_viewer_draft_envelope(belt):
    layout = rp.resolve_layout({"blueprint_string": belt})
    graph = layout.graph
    draft = {
        "document_kind": "factoribot.routing.assignment_draft",
        "assignments": {"schema_version": graph.schema_version, "blueprint_hash": graph.blueprint_hash,
                        "graph_hash": graph.graph_hash, "furnaces": [], "controls": [],
                        "feeds": [{"id": "f1", "budget_id": "iron",
                                   "endpoint": to_dict(EndpointId(EntityId((), 1), "lane", "left")),
                                   "capacity": {"kind": "unlimited", "value": None}}]},
    }
    template = {
        "budgets": [R.budget("iron", "iron-plate", 100.0)],
        "exports": [R.export("out", "iron-plate", EndpointId(EntityId((), 3), "lane", "left"))],
        "surplus": [], "objective": {"kind": "maximize_export", "export_id": "out"},
        "protected": {"entities": [], "endpoints": [], "areas": [], "preserve_wiring": True,
                      "preserve_unknown": True, "preserve_boundaries": True},
        "assumptions": {"game_version": "2.0.77", "mods": [R.BASE_MOD], "quality": "normal",
                        "available_recipes": [], "research": [], "control_policy": "relax_open",
                        "power": "assumed_available", "modules": "none", "beacons": "none",
                        "irrelevant": []},
        "detail": {"kind": "summary", "entity_ids": [], "cursor": None, "limit": 100},
    }
    document = rp.seal_request(template, layout, draft)
    assert document["request_hash"].startswith("sha256:")
    assert rp.request_unresolved(document, layout) == ()
    # Sealing is deterministic and idempotent.
    assert rp.seal_request(template, layout, draft)["request_hash"] == document["request_hash"]


def test_seal_request_never_invents_a_feed_or_export(belt):
    layout = rp.resolve_layout({"blueprint_string": belt})
    with pytest.raises(rp.PublicError) as excinfo:
        rp.seal_request({"budgets": [], "exports": []}, layout, None)
    assert excinfo.value.code == "bad_request"


# ---------------------------------------------------------------------------
# Adopted shared edits from earlier handoffs
# ---------------------------------------------------------------------------

def test_the_legacy_decoder_is_now_bounded(tmp_path):
    """Task 03 shared edit 1: `decode_blueprint_string` delegates to the bounded decoder."""
    import base64
    import tracemalloc

    bomb = "0" + base64.b64encode(zlib.compress(b"\0" * (40 << 20), 9)).decode("ascii")
    tracemalloc.start()
    with pytest.raises(BlueprintDecodeError) as excinfo:
        decode_blueprint_string(bomb)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert excinfo.value.code == "decompressed_limit"
    # The old body called zlib.decompress() outright and would peak near 40 MiB.
    assert peak < 40 << 20
    # Valid input is unchanged.
    document = L.blueprint(L.two_lane_run())
    assert decode_blueprint_string(encode_blueprint(document)) == document


def test_rotation_has_one_definition():
    """Task 04 shared edit 1: transport reuses `spatial.rotate_offset`."""
    from factoribot import spatial, transport

    assert transport.rotate.__module__ == "factoribot.transport"
    for direction in (0, 4, 8, 12):
        assert transport.rotate(0.0, -1.0, direction) == spatial.rotate_offset(0.0, -1.0, direction)
    with pytest.raises(transport.TransportError):
        transport.rotate(0.0, -1.0, 2)
    with pytest.raises(spatial.SpatialError):
        spatial.rotate_offset(0.0, -1.0, 2)


def test_the_mcp_loader_reuses_the_shared_dump_digest():
    """Task 02 shared edit 1: one SHA convention, not two."""
    import hashlib

    from factoribot.gamedata import read_dump
    from factoribot.mcp_server import load_toolbox

    try:
        path = find_dump(None)
    except Exception:  # noqa: BLE001
        pytest.skip("no data-raw-dump.json in this checkout")
    resolved, digest, _ = read_dump(path)
    assert digest == hashlib.sha256(Path(resolved).read_bytes()).hexdigest()
    assert load_toolbox(path).data_source == {"path": resolved, "sha256": digest}


def test_absent_pinned_evidence_is_a_named_error_not_a_substitution(toolbox, belt, tmp_path, monkeypatch):
    """If the packaged evidence is ever missing, say so loudly.

    `transport_prototypes` resolves the extract and the mechanics records under
    `factoribot/evidence/` (package-data, so a normal install carries them). If
    that data is missing anyway -- a stripped or corrupted install -- the
    surface must refuse, not invent geometry, capacities or an evidence status.
    """
    from factoribot import routing, transport_prototypes

    monkeypatch.setattr(routing, "EXTRACT_PATH", tmp_path / "absent.json")
    monkeypatch.setattr(transport_prototypes, "EXTRACT_PATH", tmp_path / "absent.json")
    transport_prototypes.load_pinned_extract.cache_clear() if hasattr(
        transport_prototypes.load_pinned_extract, "cache_clear") else None
    box = Toolbox(empty_db())
    out = box.call("inspect_blueprint_layout", {"blueprint_string": belt})
    assert out["error"] == "evidence_unavailable"
    assert "factoribot/evidence" in out["requires"]
