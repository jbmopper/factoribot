"""Restricted task-23 operating prediction and measured-capture acceptance."""
from __future__ import annotations

import copy
import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from factoribot.gamedata import load_database, read_dump
from factoribot.cli import main
from factoribot.sustained_throughput import (
    ThroughputError,
    compare_prediction_to_captures,
    predict_operating_rate,
    validate_operating_scenario,
    validate_process_capture_v3,
)
from factoribot.tools import TOOL_SCHEMAS, Toolbox


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/data-raw-dump-2.0.77-base.json"
SCENARIO = ROOT / "experiments/routing-measurements/scenarios/furnace-chain-base-2.0.77-v2.json"
CAPTURES = ROOT / "experiments/routing-measurements/captures"


def dump_or_skip() -> Path:
    """The base-only dump the scenario is sealed against.

    It is a second dump, distinct from the working `data/data-raw-dump.json`
    that `make dump` writes with whatever mods are enabled, and it is too large
    to check in. Absent means "not generated here yet", not a regression.
    """
    if not DATA.exists():
        pytest.skip(f"{DATA.name} is absent; run `make dump-base` to regenerate it")
    return DATA


def _inputs():
    scenario = json.loads(SCENARIO.read_text())
    _path, digest, _raw = read_dump(str(dump_or_skip()))
    return scenario, load_database(str(DATA)), digest


def test_serial_furnace_prediction_is_hash_bound_and_recipe_derived():
    scenario, database, digest = _inputs()
    validate_operating_scenario(scenario)
    prediction = predict_operating_rate(
        scenario,
        database=database,
        recipe_data_sha256=digest,
    )

    assert prediction["rate_kind"] == "conditional_analytic_operating_rate"
    assert prediction["sustained_rate_established"] is False
    assert prediction["items"]["accepted_import"] == {"iron-ore": "5/8"}
    assert prediction["items"]["net_export"] == {"steel-plate": "1/8"}
    assert [row["crafts_per_s"] for row in prediction["machines"]] == ["5/8", "1/8"]


def test_operating_rate_is_available_as_a_pure_deterministic_tool():
    scenario, database, digest = _inputs()
    schema = next(
        value for value in TOOL_SCHEMAS
        if value["name"] == "evaluate_blueprint_operating_rate"
    )
    assert schema["parameters"]["additionalProperties"] is False
    toolbox = Toolbox(database, data_source={"path": str(DATA), "sha256": digest})

    result = toolbox.call("evaluate_blueprint_operating_rate", {"scenario": scenario})

    assert "error" not in result
    assert result["items"]["net_export"] == {"steel-plate": "1/8"}


def test_recipe_data_identity_mismatch_is_rejected():
    scenario, database, _digest = _inputs()

    with pytest.raises(ThroughputError, match="recipe data identity"):
        predict_operating_rate(
            scenario,
            database=database,
            recipe_data_sha256="not-the-scenario-dump",
        )


def test_retained_game_captures_validate_and_match_the_frozen_tolerance():
    scenario, database, digest = _inputs()
    paths = sorted(CAPTURES.glob(f"{scenario['scenario_id']}-run-*.json"))
    assert len(paths) == scenario["measurement"]["repeat_runs"]
    captures = [json.loads(path.read_text()) for path in paths]
    measurements = [
        validate_process_capture_v3(capture, scenario, database=database)
        for capture in captures
    ]
    prediction = predict_operating_rate(
        scenario,
        database=database,
        recipe_data_sha256=digest,
    )
    comparison = compare_prediction_to_captures(
        prediction,
        scenario,
        captures,
        database=database,
    )

    assert all(result["sustained_rate_established"] is False for result in measurements)
    assert comparison["all_windows_match"] is True
    assert all(row["match"] for row in comparison["comparisons"])

    broken = copy.deepcopy(captures[0])
    broken["measurement_windows"][0]["counters"]["steel_output_right_lane"] += 1
    with pytest.raises(ThroughputError, match="capture hash"):
        validate_process_capture_v3(broken, scenario, database=database)


def test_routes_throughput_cli_writes_the_separate_operating_report(tmp_path, capsys):
    dump_or_skip()
    scenario = json.loads(SCENARIO.read_text())
    captures = sorted(CAPTURES.glob(f"{scenario['scenario_id']}-run-*.json"))
    out = tmp_path / "report.json"
    rc = main([
        "--data", str(DATA), "routes", "throughput",
        "--scenario", str(SCENARIO),
        "--capture", str(captures[0]),
        "--capture", str(captures[1]),
        "--out", str(out),
    ])

    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    report = json.loads(out.read_text())
    assert summary["all_windows_match"] is True
    assert report["capacity_upper_bound"] is None
    assert report["prediction"]["items"]["net_export"] == {"steel-plate": "1/8"}
    assert report["measurements"][0]["auxiliary_measurements"]["windows"][0][
        "boundary_rates"
    ]["dual_lane_export"] == "30"


def test_operating_rate_tool_over_real_stdio_mcp(tmp_path):
    dump_or_skip()
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    scenario = json.loads(SCENARIO.read_text())

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "factoribot.cli", "--data", str(DATA), "mcp"],
            env={"OPENAI_API_KEY": "", "FACTORIBOT_DATA": str(DATA)},
            cwd=str(tmp_path),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(
                read,
                write,
                read_timeout_seconds=timedelta(seconds=60),
            ) as session:
                await session.initialize()
                result = await session.call_tool(
                    "evaluate_blueprint_operating_rate", {"scenario": scenario})
                assert not result.isError
                assert result.structuredContent["rate_kind"] == "conditional_analytic_operating_rate"
                assert result.structuredContent["items"]["net_export"] == {
                    "steel-plate": "1/8"}

    asyncio.run(exercise())
