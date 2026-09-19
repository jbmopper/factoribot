"""Task 18: task-15 viewer draft -> CLI request -> analysis replay.

The fixture is a hand-checkable synthetic fast-belt run.  It is deliberately
not game evidence: its 15/s-per-lane expectation comes from the imported
prototype groups and only checks declaration preservation at this boundary.
"""
from __future__ import annotations

import asyncio
import copy
from datetime import timedelta
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from factoribot import routing_public as rp
from factoribot.blueprint import encode_blueprint
from factoribot.blueprint_contract import to_dict
from factoribot.blueprint_view import build_view_model

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "daemon/tests/fixtures/routing_input_drafts"
sys.path.insert(0, str(ROOT / "daemon/tests/fixtures/routing_transport"))
import layouts as L  # noqa: E402


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


def layout():
    return rp.resolve_layout({
        "blueprint_string": (FIXTURES / "two_lane_fast_belt.txt").read_text().strip(),
        "provenance": "synthetic",
    })


def draft():
    return fixture("full_belt_same_item_draft.json")


def policy():
    return fixture("host_policy_template.json")


def test_page_full_belt_draft_is_sealed_without_losing_lanes_or_shared_budget():
    built = layout()
    document = rp.seal_request(policy(), built, draft())

    # Hand check: a 30/s fast belt has two imported 15/s lanes.  The whole-belt
    # declaration must be one global 30/s material ceiling and two 15/s feeds,
    # not two independent 30/s sources.
    assert document["budgets"] == draft()["proposed_request"]["budgets"]
    assert document["exports"] == draft()["proposed_request"]["exports"]
    assert document["objective"] == draft()["proposed_request"]["objective"]
    assert [feed["capacity"]["value"] for feed in document["assignments"]["feeds"]] == [15.0, 15.0]
    assert {feed["budget_id"] for feed in document["assignments"]["feeds"]} == {"full_input_1_iron-plate"}
    assert document["budgets"][0]["capacity"]["value"] == 30.0
    assert (document["blueprint_hash"], document["graph_hash"]) == (
        built.graph.blueprint_hash, built.graph.graph_hash)

    report = rp.analyze_layout(built, document)
    routing = next(bound for bound in report.result.bounds if bound.stage == "routing")
    # Only the left lane reaches the declared outlet.  Right-lane availability
    # must not force a 30/s export or create disposal; the upper bound is 15/s.
    assert routing.value is not None and routing.value.value == 15.0
    assert not document["surplus"]


def test_draft_lane_variants_and_repeated_page_edit_preserve_exact_final_declarations():
    built = layout()
    one_lane = draft()
    one_lane["assignments"]["feeds"] = one_lane["assignments"]["feeds"][:1]
    one_lane["proposed_request"]["budgets"][0]["capacity"]["value"] = 15.0
    sealed_one_lane = rp.seal_request(policy(), built, one_lane)
    assert len(sealed_one_lane["assignments"]["feeds"]) == 1
    assert sealed_one_lane["assignments"]["feeds"][0]["capacity"]["value"] == 15.0

    mixed = draft()
    right = mixed["assignments"]["feeds"][1]
    right["budget_id"] = "full_input_1_copper-plate"
    mixed["proposed_request"]["budgets"] = [
        mixed["proposed_request"]["budgets"][0],
        {"id": "full_input_1_copper-plate",
         "material": {"kind": "item", "name": "copper-plate", "quality": "normal"},
         "capacity": {"kind": "finite", "value": 15.0}},
    ]
    mixed["proposed_request"]["budgets"][0]["capacity"]["value"] = 15.0
    sealed_mixed = rp.seal_request(policy(), built, mixed)
    assert {budget["material"]["name"] for budget in sealed_mixed["budgets"]} == {
        "iron-plate", "copper-plate"}
    assert len(sealed_mixed["assignments"]["feeds"]) == 2

    # A repeated UI edit exports the replacement set, not a second copy.  The
    # contract's uniqueness check is the independent guard against a duplicate.
    repeated = rp.seal_request(policy(), built, draft())
    assert [feed["id"] for feed in repeated["assignments"]["feeds"]] == [
        "full_input_1_left", "full_input_1_right"]


def test_host_policy_conflict_is_actionable_and_identical_migration_copy_is_allowed():
    built = layout()
    conflicting = policy()
    conflicting["budgets"] = [{"id": "host_iron", "material": {
        "kind": "item", "name": "iron-plate", "quality": "normal"},
        "capacity": {"kind": "finite", "value": 999.0}}]
    with pytest.raises(rp.PublicError) as excinfo:
        rp.seal_request(conflicting, built, draft())
    error = excinfo.value
    assert error.code == "draft_conflict"
    assert error.detail["fields"] == ["budgets"]
    assert "Remove" in error.detail["action"]

    identical = policy()
    identical["budgets"] = copy.deepcopy(draft()["proposed_request"]["budgets"])
    document = rp.seal_request(identical, built, draft())
    assert document["budgets"] == draft()["proposed_request"]["budgets"]


def test_changed_graph_identity_and_blocked_output_stay_rejected_without_implicit_sinks():
    changed = rp.resolve_layout({
        "blueprint_string": encode_blueprint(L.blueprint(L.turn_layout())),
        "provenance": "synthetic",
    })
    with pytest.raises(rp.PublicError) as excinfo:
        rp.seal_request(policy(), changed, draft())
    assert excinfo.value.code == "stale_identity"

    blocked = fixture_from_contract("blocked_export")
    blocked_layout = rp.resolve_layout({"graph": blocked["graph"]})
    report = rp.analyze_layout(blocked_layout, blocked["request"])
    assert report.result.status == "insufficient"
    assert report.result.interpreted_request.surplus == ()


def fixture_from_contract(name: str):
    return json.loads((ROOT / f"daemon/tests/fixtures/routing_contracts/{name}.json").read_text())


def test_real_cli_seal_analyze_and_regenerated_page_replay(tmp_path):
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    page_path = tmp_path / "audit.html"
    base = [sys.executable, "-m", "factoribot.cli", "routes"]
    common = ["--bp", str(FIXTURES / "two_lane_fast_belt.txt"), "--provenance", "synthetic"]
    seal = subprocess.run(base + ["request", *common, "--template", str(FIXTURES / "host_policy_template.json"),
                                  "--assignments", str(FIXTURES / "full_belt_same_item_draft.json"),
                                  "--out", str(request_path)],
                          cwd=ROOT, text=True, capture_output=True, check=True)
    sealed_summary = json.loads(seal.stdout)
    assert sealed_summary["page_declaration_fields"] == ["budgets", "exports", "surplus", "objective"]
    assert sealed_summary["host_policy_fields"] == ["protected", "assumptions", "detail"]

    subprocess.run(base + ["analyze", *common, "--request", str(request_path), "--result", str(result_path),
                           "--view", str(page_path)], cwd=ROOT, text=True, capture_output=True, check=True)
    request = json.loads(request_path.read_text())
    result = json.loads(result_path.read_text())
    assert result["interpreted_request"] == request
    assert result["status"] == "feasible_relaxed"

    island = re.search(r'<script id="factoribot-view-data" type="application/json">(.*?)</script>',
                       page_path.read_text(), re.S)
    assert island
    model = json.loads(island.group(1))
    assert model["assignments"]["document"] == request["assignments"]
    assert model["result"]["request"]["budgets"][0]["capacity"]["value"] == 30.0
    assert [feed["capacity"]["value"] for feed in model["assignments"]["document"]["feeds"]] == [15.0, 15.0]

    replay = build_view_model(to_dict(layout().graph), result, request["assignments"])
    assert replay["assignments"]["document"] == request["assignments"]
    assert replay["result"]["request"]["objective"] == draft()["proposed_request"]["objective"]


def test_real_cli_reports_host_page_budget_conflict(tmp_path):
    command = [sys.executable, "-m", "factoribot.cli", "routes", "request",
               "--bp", str(FIXTURES / "two_lane_fast_belt.txt"), "--provenance", "synthetic",
               "--template", str(FIXTURES / "host_conflicting_budget_template.json"),
               "--assignments", str(FIXTURES / "full_belt_same_item_draft.json"),
               "--out", str(tmp_path / "must-not-exist.json")]
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    assert completed.returncode == 2
    error = json.loads(completed.stderr)
    assert error["error"] == "draft_conflict"
    assert error["fields"] == ["budgets"]
    assert "Remove" in error["action"]


def test_fresh_stdio_mcp_replays_the_cli_sealed_synthetic_request(tmp_path):
    pytest.importorskip("mcp")
    pytest.importorskip("scipy")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    built = layout()
    document = rp.seal_request(policy(), built, draft())
    workdir = tmp_path / "mcp-workdir"
    workdir.mkdir()

    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=["-m", "factoribot.cli", "mcp"],
                                       env={"OPENAI_API_KEY": ""}, cwd=str(workdir))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=120)) as session:
                await session.initialize()
                result = await session.call_tool("analyze_blueprint_routes", {
                    "blueprint_string": (FIXTURES / "two_lane_fast_belt.txt").read_text().strip(),
                    "provenance": "synthetic", "request": document,
                })
                assert not result.isError
                body = result.structuredContent
                assert body["status"] == "feasible_relaxed"
                assert body["identity"]["graph_hash"] == document["graph_hash"]
                assert next(bound for bound in body["bounds"] if bound["stage"] == "routing")["value"] == {
                    "kind": "finite", "value": 15.0}

    asyncio.run(exercise())
    assert list(workdir.iterdir()) == []
