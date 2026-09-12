"""Task 07 acceptance: the routing tools over a real stdio MCP server.

A fresh server process is launched per test module (never the user's running
server). It is started in an empty working directory so "a pure call writes no
file" is checked by inspecting that directory afterwards, and its stderr is
captured to a file so a diagnostic leaking onto protocol stdout would show up
as a protocol failure rather than passing silently.

Every structured result is cross-checked against a direct in-process Python call
on the same inputs.
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import zlib
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("mcp")
pytest.importorskip("scipy")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "daemon/tests/fixtures/routing_transport"))

import layouts as L  # noqa: E402
import requests as R  # noqa: E402

from factoribot import routing_public as rp  # noqa: E402
from factoribot.blueprint import encode_blueprint  # noqa: E402
from factoribot.blueprint_contract import EndpointId, EntityId, to_dict  # noqa: E402
from factoribot.gamedata import build_database  # noqa: E402
from factoribot.tools import Toolbox  # noqa: E402

CONTRACT_FIXTURES = ROOT / "daemon/tests/fixtures/routing_contracts"

TINY_DUMP = {
    "item": {"ore": {"type": "item"}, "plate": {"type": "item"}},
    "recipe": {"plate": {"ingredients": [{"name": "ore", "amount": 2}],
                         "results": [{"name": "plate", "amount": 1}], "energy_required": 1}},
    "assembling-machine": {"assembler": {"crafting_categories": ["crafting"],
                                         "crafting_speed": 1, "energy_usage": "100W"}},
}


def local_toolbox() -> Toolbox:
    return Toolbox(build_database(TINY_DUMP))


def belt_string() -> str:
    return encode_blueprint(L.blueprint(L.two_lane_run()))


def belt_request() -> dict:
    layout = rp.resolve_layout({"blueprint_string": belt_string()})
    return to_dict(R.make_request(
        layout.graph,
        budgets=[R.budget("iron", "iron-plate", 100.0)],
        feeds=[R.feed("f1", "iron", EndpointId(EntityId((), 1), "lane", "left"))],
        exports=[R.export("out", "iron-plate", EndpointId(EntityId((), 3), "lane", "left"))],
        objective={"kind": "maximize_export", "export_id": "out"},
    ))


def bridge_case() -> tuple[str, dict]:
    text = encode_blueprint(L.blueprint(L.unsupported_bridge()))
    layout = rp.resolve_layout({"blueprint_string": text})
    request = to_dict(R.make_request(
        layout.graph,
        budgets=[R.budget("iron", "iron-plate", 10.0)],
        feeds=[R.feed("f1", "iron", EndpointId(EntityId((), 1), "lane", "left"))],
        exports=[R.export("out", "iron-plate", EndpointId(EntityId((), 3), "lane", "left"), 1.0, "minimum")],
        objective={"kind": "maximize_export", "export_id": "out"},
    ))
    return text, request


def zip_bomb() -> str:
    return "0" + base64.b64encode(zlib.compress(b"\0" * (40 << 20), 9)).decode("ascii")


def test_routing_tools_over_real_stdio(tmp_path):
    data = tmp_path / "data.json"
    data.write_text(json.dumps(TINY_DUMP))
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    errlog = open(tmp_path / "server.stderr", "w+")
    local = local_toolbox()
    calls: dict[str, dict] = {}

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "factoribot.cli", "--data", str(data), "mcp"],
            env={"OPENAI_API_KEY": "", "FACTORIBOT_DATA": str(data)},
            cwd=str(workdir),
        )
        async with stdio_client(params, errlog=errlog) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=120)) as session:
                await session.initialize()

                # ---- discovery -------------------------------------------------
                listed = await session.list_tools()
                names = {tool.name for tool in listed.tools}
                assert {"inspect_blueprint_layout", "analyze_blueprint_routes"} <= names
                # existing callers keep working: no tool disappeared
                assert {"plan_production", "get_capabilities", "analyze_blueprint", "list_belts",
                        "solve_production", "evaluate_throughput", "search_items", "get_recipe",
                        "list_machines", "list_modules"} <= names
                for tool in listed.tools:
                    assert tool.annotations.readOnlyHint is True
                    assert tool.annotations.destructiveHint is False
                routing = {t.name: t for t in listed.tools
                           if t.name in ("inspect_blueprint_layout", "analyze_blueprint_routes")}
                assert all(t.inputSchema.get("additionalProperties") is False for t in routing.values())

                async def call(name, args):
                    result = await session.call_tool(name, args)
                    # the JSON text block and the structured content always agree
                    assert json.loads(result.content[0].text) == result.structuredContent
                    calls[f"{name}:{len(calls)}"] = {"args": args, "result": result.structuredContent,
                                                     "isError": result.isError}
                    return result

                # ---- capability metadata ---------------------------------------
                caps = (await call("get_capabilities", {})).structuredContent
                routing_caps = caps["blueprint_routing"]
                assert routing_caps["mechanics_evidence"]["observed"] == 0
                assert routing_caps["advertisable_bounds"]["pilot"] is False
                assert routing_caps["purity"]["writes_files"] is False
                assert set(routing_caps["finding_codes"]) == {"graph", "delivery"}

                # ---- successful -----------------------------------------------
                belt = belt_string()
                layout = await call("inspect_blueprint_layout", {"blueprint_string": belt})
                assert not layout.isError
                graph_hash = layout.structuredContent["identity"]["graph_hash"]
                analysis = await call("analyze_blueprint_routes",
                                      {"blueprint_string": belt, "request": belt_request(),
                                       "expect_graph_hash": graph_hash})
                assert not analysis.isError
                body = analysis.structuredContent
                assert body["status"] == "feasible_relaxed"
                assert {b["stage"]: b["value"] for b in body["bounds"]}["routing"] == {
                    "kind": "finite", "value": 15.0}

                # ---- follow-up detail under the same identity -------------------
                page = await call("inspect_blueprint_layout", {
                    "blueprint_string": belt, "expect_graph_hash": graph_hash, "section": "arcs",
                    "detail": {"kind": "full", "limit": 4}})
                cursor = page.structuredContent["page"]["cursor"]
                assert cursor
                more = await call("inspect_blueprint_layout", {
                    "blueprint_string": belt, "expect_graph_hash": graph_hash, "section": "arcs",
                    "detail": {"kind": "full", "limit": 4, "cursor": cursor}})
                assert more.structuredContent["page"]["offset"] == 4

                # ---- conditional ------------------------------------------------
                inserter = encode_blueprint(L.blueprint(L.inserter_between_belts()))
                cond = await call("inspect_blueprint_layout", {"blueprint_string": inserter})
                assert set(cond.structuredContent["conditions"]) == {
                    "inserter_rotation_documented", "inserter_rotation_reversed"}
                assert "exact" not in cond.structuredContent["arc_semantics"]

                # ---- insufficient -----------------------------------------------
                blocked = json.loads((CONTRACT_FIXTURES / "blocked_export.json").read_text())
                short = await call("analyze_blueprint_routes",
                                   {"graph": blocked["graph"], "request": blocked["request"]})
                assert short.structuredContent["status"] == "insufficient"
                assert next(b for b in short.structuredContent["bounds"]
                            if b["stage"] == "routing")["solver_state"] == "infeasible"

                # ---- unsupported (possible bridge withholds every bound) ---------
                text, request = bridge_case()
                partial = await call("analyze_blueprint_routes",
                                     {"blueprint_string": text, "request": request})
                assert partial.structuredContent["status"] == "partial"
                assert partial.structuredContent["bounds"] == []
                assert partial.structuredContent["unresolved_reasons"]

                # ---- invalid ------------------------------------------------------
                bad = await call("analyze_blueprint_routes",
                                 {"blueprint_string": belt, "request": {"not": "a request"}})
                assert bad.structuredContent["status"] == "invalid_request"
                assert bad.structuredContent["identity"]["request_hash"] is None
                assert bad.isError  # `ok: false` maps to an MCP error result

                # ---- oversized -----------------------------------------------------
                bomb = await call("inspect_blueprint_layout", {"blueprint_string": zip_bomb()})
                assert bomb.isError
                assert bomb.structuredContent["error"] == "bad_blueprint"
                assert bomb.structuredContent["decode_code"] == "decompressed_limit"
                big_page = await call("inspect_blueprint_layout",
                                      {"blueprint_string": belt, "detail": {"kind": "full", "limit": 9000}})
                assert big_page.structuredContent["error"] == "oversized_page"

                # ---- the server is still usable after every failure ---------------
                assert not (await call("get_recipe", {"name": "plate"})).isError
                assert not (await call("inspect_blueprint_layout", {"blueprint_string": belt})).isError

    asyncio.run(exercise())
    errlog.close()

    # A pure MCP call writes no file anywhere in the server's working directory.
    assert list(workdir.iterdir()) == []

    # Structured results agree with direct in-process Python calls.
    checked = 0
    for entry in calls.values():
        name = entry["args"]
        if "blueprint_string" not in name and "graph" not in name:
            continue
        tool = "analyze_blueprint_routes" if "request" in name else "inspect_blueprint_layout"
        direct = local.call(tool, name)
        remote = entry["result"]
        for key in ("identity", "status", "bounds", "counts", "arc_semantics", "conditions",
                    "error", "decode_code", "unresolved_reasons", "findings", "page"):
            if key in remote or key in direct:
                assert direct.get(key) == remote.get(key), f"{tool}.{key} differs between MCP and Python"
        checked += 1
    assert checked >= 8, f"only {checked} calls cross-checked"


def test_analyze_blueprint_routes_replays_the_cli_sealed_pilot_request_over_mcp(tmp_path):
    """F-1 fix: `provenance` is now a tool argument, so the documented pilot flow
    (docs/blueprint-routing-handoffs/07-public-integration.md §10,
    daemon/tests/fixtures/routing_public/README.md) can be replayed over MCP.

    Before the fix, `additionalProperties: False` on both routing schemas had no
    `provenance` key. A request sealed by `factoribot routes request
    --provenance development_pilot` therefore always came back
    `invalid_request` / "request/graph mismatch" over MCP, because the server
    always built the graph under the default `game_export` provenance while the
    request was sealed against a `development_pilot` graph_hash. See
    test_routing_audit.py::test_mcp_refuses_a_request_sealed_against_a_different_graph,
    which intentionally omits `provenance` and keeps asserting exactly that
    mismatch as the safe fallback behaviour.

    This test supplies the now-available `provenance` argument and asserts the
    MCP result matches a direct in-process Python call on the same inputs:
    `partial`, no bounds, the three unresolved `ee-super-substation` poles.
    """
    from factoribot.gamedata import load_database
    from factoribot.routing import RecipeSource

    pilot_path = ROOT / "daemon/tests/fixtures/wip_science.txt"
    fixtures = ROOT / "daemon/tests/fixtures/routing_public"
    blueprint = pilot_path.read_text().strip()
    template = json.loads((fixtures / "pilot_request_template.json").read_text())
    assignments = json.loads((fixtures / "pilot_assignments.json").read_text())

    try:
        recipes = RecipeSource(load_database(None))
    except (OSError, ValueError) as exc:
        pytest.skip(f"the pilot's assembling-machine activities need the game dump: {exc}")

    # ---- oracle: the direct in-process Python call ------------------------
    layout = rp.build_layout(blueprint, provenance="development_pilot", recipes=recipes)
    document = rp.seal_request(template, layout, assignments)
    direct_report = rp.analyze_layout(layout, document)
    direct_summary = rp.analysis_summary(layout, direct_report)
    assert direct_summary["status"] == "partial"
    assert direct_summary["bounds"] == []
    assert len(direct_summary["unresolved_reasons"]) == 3
    assert all(r.startswith("unsupported entity: bp/root/e/") for r in direct_summary["unresolved_reasons"])

    workdir = tmp_path / "workdir"
    workdir.mkdir()

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "factoribot.cli", "mcp"],
            env={"OPENAI_API_KEY": ""},
            cwd=str(workdir),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=120)) as session:
                await session.initialize()

                # ---- positive: matching provenance replays the sealed request --
                ok = await session.call_tool("analyze_blueprint_routes", {
                    "blueprint_string": blueprint, "request": document,
                    "provenance": "development_pilot", "section": "summary"})
                body = ok.structuredContent
                assert not ok.isError, body
                assert body["status"] == "partial"
                assert body["bounds"] == []
                assert sorted(body["unresolved_reasons"]) == sorted(direct_summary["unresolved_reasons"])
                assert body["identity"]["graph_hash"] == layout.graph_hash

                # ---- negative: identity pinning is not weakened by the fix -----
                # Omitting provenance still defaults to game_export, still a
                # graph mismatch against a request sealed for development_pilot.
                mismatched = await session.call_tool("analyze_blueprint_routes", {
                    "blueprint_string": blueprint, "request": document, "section": "summary"})
                assert mismatched.isError
                assert mismatched.structuredContent["status"] == "invalid_request"
                assert mismatched.structuredContent["bounds"] == []

                # A wrong-but-declared provenance is refused the same way.
                wrong = await session.call_tool("analyze_blueprint_routes", {
                    "blueprint_string": blueprint, "request": document,
                    "provenance": "synthetic", "section": "summary"})
                assert wrong.isError
                assert wrong.structuredContent["status"] == "invalid_request"

    asyncio.run(exercise())

    # A pure MCP call writes no file anywhere in the server's working directory.
    assert list(workdir.iterdir()) == []


def test_stdio_server_without_a_dump_refuses_cleanly(tmp_path):
    """A server started with an unusable dump still lists tools and refuses cleanly."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    missing = tmp_path / "absent.json"

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "factoribot.cli", "--data", str(missing), "mcp"],
            env={"OPENAI_API_KEY": "", "FACTORIBOT_DATA": str(missing)},
            cwd=str(workdir),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=30)) as session:
                await session.initialize()

    with pytest.raises(Exception):  # noqa: B017 - the loader refuses before serving
        asyncio.run(exercise())
    assert list(workdir.iterdir()) == []
