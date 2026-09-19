"""Task 19 public CLI preparation, stale-input, and fresh MCP replay."""
from __future__ import annotations

import asyncio
import copy
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys

import pytest

from factoribot import routing_public as rp
from factoribot.blueprint import encode_blueprint
from factoribot.blueprint_contract import BASE_MOD, content_hash, to_dict
from factoribot.furnace_inference import INFERENCE_DOCUMENT_KIND
from factoribot.gamedata import load_database
from factoribot.routing import RecipeSource


ROOT = Path(__file__).resolve().parents[2]
ALL_SMELTING = ["copper-plate", "iron-plate", "steel-plate", "stone-brick"]


def setup_documents():
    blueprint = encode_blueprint({
        "blueprint": {
            "item": "blueprint",
            "label": "SYNTHETIC task 19 direct furnace feed",
            "version": 562949958402048,
            "entities": [{
                "entity_number": 1,
                "name": "electric-furnace",
                "position": {"x": 0, "y": 0},
            }],
        }
    })
    recipes = RecipeSource(load_database())
    source = rp.build_layout(blueprint, provenance="synthetic", recipes=recipes)
    entity = {"book_path": [], "entity_number": 1}
    incoming = {"entity": entity, "kind": "inventory", "name": "input"}
    outgoing = {"entity": entity, "kind": "inventory", "name": "output"}
    draft = {
        "document_kind": "factoribot.routing.assignment_draft",
        "assignments": {
            "schema_version": source.graph.schema_version,
            "blueprint_hash": source.graph.blueprint_hash,
            "graph_hash": source.graph.graph_hash,
            "feeds": [{
                "id": "ore_feed",
                "budget_id": "ore",
                "endpoint": incoming,
                "capacity": {"kind": "unlimited", "value": None},
            }],
            "furnaces": [],
            "controls": [],
        },
        "proposed_request": {
            "budgets": [{
                "id": "ore",
                "material": {"kind": "item", "name": "iron-ore", "quality": "normal"},
                "capacity": {"kind": "finite", "value": 100.0},
            }],
            "exports": [{
                "id": "product",
                "material": {"kind": "item", "name": "iron-plate", "quality": "normal"},
                "endpoint": outgoing,
                "requirement": "minimum",
                "rate": 0.0,
                "sink": {
                    "kind": "external",
                    "service": "SYNTHETIC continuous fixture removal; not game evidence",
                    "capacity": {"kind": "unlimited", "value": None},
                },
            }],
            "surplus": [],
            "objective": {"kind": "maximize_export", "export_id": "product"},
        },
    }
    policy = {
        "protected": {
            "entities": [],
            "endpoints": [outgoing],
            "areas": [],
            "preserve_wiring": True,
            "preserve_unknown": True,
            "preserve_boundaries": True,
        },
        "assumptions": {
            "game_version": "2.0.77",
            "mods": [{
                "name": BASE_MOD[0], "version": BASE_MOD[1], "provides": [],
                "alters_item_mechanics": False,
            }],
            "quality": "normal",
            "available_recipes": ALL_SMELTING,
            "research": [],
            "control_policy": "relax_open",
            "power": "assumed_available",
            "modules": "none",
            "beacons": "none",
            "irrelevant": [],
        },
        "detail": {"kind": "full", "entity_ids": [], "cursor": None, "limit": 10000},
    }
    return blueprint, recipes, source, draft, policy


def write_inputs(tmp_path):
    blueprint, recipes, source, draft, policy = setup_documents()
    paths = {
        "blueprint": tmp_path / "furnace.txt",
        "draft": tmp_path / "draft.json",
        "policy": tmp_path / "policy.json",
        "artifact": tmp_path / "inference.json",
        "request": tmp_path / "request.json",
    }
    paths["blueprint"].write_text(blueprint)
    paths["draft"].write_text(json.dumps(draft))
    paths["policy"].write_text(json.dumps(policy))
    return paths, recipes, source, draft, policy


def run_infer(paths, assignments=None, artifact=None, request=None):
    command = [
        sys.executable, "-m", "factoribot.cli", "routes", "infer",
        "--bp", str(paths["blueprint"]),
        "--provenance", "synthetic",
        "--template", str(paths["policy"]),
        "--assignments", str(assignments or paths["draft"]),
        "--out", str(artifact or paths["artifact"]),
        "--request-out", str(request or paths["request"]),
    ]
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True)


def test_cli_rebuilds_once_records_provenance_and_matches_manual_request(tmp_path):
    paths, recipes, source, draft, policy = write_inputs(tmp_path)
    completed = run_infer(paths)
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    artifact = json.loads(paths["artifact"].read_text())
    request = json.loads(paths["request"].read_text())
    assert summary["graph_rebuilt"]
    assert summary["candidate_recipes"] == ALL_SMELTING
    assert summary["furnace_status_counts"] == {"inferred": 1}
    assert artifact["document_kind"] == INFERENCE_DOCUMENT_KIND
    assert artifact["source_graph_hash"] == source.graph_hash
    assert artifact["assignments"]["furnaces"] == [{
        "entity": {"book_path": [], "entity_number": 1}, "recipe": "iron-plate"
    }]

    final = rp.build_layout(
        paths["blueprint"].read_text(), provenance="synthetic", recipes=recipes,
        furnace_candidates=tuple(ALL_SMELTING),
    )
    assert request["graph_hash"] == final.graph_hash == artifact["final_graph_hash"]
    assert rp.seal_request(policy, final, artifact) == request

    manual = copy.deepcopy(artifact["assignments"])
    manual_request = rp.seal_request({**policy, **draft["proposed_request"]}, final, manual)
    assert manual_request == request
    report = rp.analyze_layout(final, request)
    bound = next(value for value in report.result.bounds if value.stage == "routing")
    # Loaded 2.0.77 data: electric furnace speed 2 / 3.2 s = 0.625 crafts/s.
    assert bound.value.value == pytest.approx(0.625)


def test_changed_feed_recomputes_prior_artifact_and_old_provenance_cannot_be_hash_patched(tmp_path):
    paths, recipes, _, _, policy = write_inputs(tmp_path)
    assert run_infer(paths).returncode == 0
    first = json.loads(paths["artifact"].read_text())
    changed = copy.deepcopy(first)
    changed["proposed_request"]["budgets"][0]["material"]["name"] = "copper-ore"

    final = rp.build_layout(
        paths["blueprint"].read_text(), provenance="synthetic", recipes=recipes,
        furnace_candidates=tuple(ALL_SMELTING),
    )
    # Even refreshing the envelope hash cannot make the old evidence record
    # valid; sealing recomputes the fixed point and refuses it.
    changed.pop("artifact_hash")
    changed["artifact_hash"] = content_hash(changed)
    with pytest.raises(rp.PublicError) as caught:
        rp.seal_request(policy, final, changed)
    assert caught.value.code == "stale_inference"

    changed_path = tmp_path / "changed.json"
    second_path = tmp_path / "second-inference.json"
    second_request = tmp_path / "second-request.json"
    changed_path.write_text(json.dumps(changed))
    completed = run_infer(paths, changed_path, second_path, second_request)
    assert completed.returncode == 0, completed.stderr
    second = json.loads(second_path.read_text())
    assert second["inference"]["input_hash"] != first["inference"]["input_hash"]
    assert second["assignments"]["furnaces"] == [{
        "entity": {"book_path": [], "entity_number": 1}, "recipe": "copper-plate"
    }]


def test_cli_does_not_turn_a_single_available_recipe_into_no_feed_evidence(tmp_path):
    paths, _, _, draft, policy = write_inputs(tmp_path)
    draft["assignments"]["feeds"] = []
    draft["proposed_request"]["budgets"] = []
    policy["assumptions"]["available_recipes"] = ["iron-plate"]
    paths["draft"].write_text(json.dumps(draft))
    paths["policy"].write_text(json.dumps(policy))

    completed = run_infer(paths)
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    artifact = json.loads(paths["artifact"].read_text())
    assert summary["furnace_status_counts"] == {"no_evidence": 1}
    assert summary["bounds_advertisable"] is False
    assert summary["unresolved_reasons"] == ["unassigned furnace: bp/root/e/1"]
    assert artifact["assignments"]["furnaces"] == []


def test_fresh_stdio_mcp_replays_the_cli_inferred_request(tmp_path):
    pytest.importorskip("mcp")
    pytest.importorskip("scipy")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    paths, _, _, _, _ = write_inputs(tmp_path)
    completed = run_infer(paths)
    assert completed.returncode == 0, completed.stderr
    request = json.loads(paths["request"].read_text())
    workdir = tmp_path / "mcp-workdir"
    workdir.mkdir()

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "factoribot.cli", "mcp"],
            env={"OPENAI_API_KEY": ""},
            cwd=str(workdir),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(
                read, write, read_timeout_seconds=timedelta(seconds=120)
            ) as session:
                await session.initialize()
                result = await session.call_tool("analyze_blueprint_routes", {
                    "blueprint_string": paths["blueprint"].read_text(),
                    "provenance": "synthetic",
                    "furnace_candidates": ALL_SMELTING,
                    "request": request,
                })
                assert not result.isError
                body = result.structuredContent
                assert body["identity"]["graph_hash"] == request["graph_hash"]
                assert body["status"] == "feasible_relaxed"
                routing = next(value for value in body["bounds"] if value["stage"] == "routing")
                assert routing["value"] == {"kind": "finite", "value": 0.625}

    asyncio.run(exercise())
    assert list(workdir.iterdir()) == []
