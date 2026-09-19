"""Pre-implementation checks for task 20's task-21 design package."""
from __future__ import annotations

from fractions import Fraction
import importlib.util
import json
from pathlib import Path

import pytest

from factoribot.sustained_throughput import (
    CAPTURE_VERSION,
    DEFAULT_WINDOW_TICKS,
    REQUIRED_CASES,
    ThroughputDesignError,
    load_design_manifest,
    observation_error_limit,
    validate_design_manifest,
)


CASES = Path(__file__).parent / "fixtures" / "sustained_throughput" / "cases.json"
ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_design_cases_are_complete_explicitly_synthetic_and_conserving():
    cases = load_design_manifest(CASES)
    assert {case["case_id"] for case in cases} == REQUIRED_CASES
    assert all(case["oracle_basis"] for case in cases)


def test_unknown_inserter_rate_and_pilot_do_not_invent_numerical_oracles():
    cases = {case["case_id"]: case for case in load_design_manifest(CASES)}
    assert cases["fast-inserter-chest-to-chest"]["steady_balance"] is None
    assert cases["fast-inserter-chest-to-chest"]["prediction_gate"] == "unsupported"
    assert cases["pilot-subfactory-gate"]["steady_balance"] is None
    assert cases["pilot-subfactory-gate"]["prediction_gate"] == "integration-gate"


def test_task16_and_task17_links_resolve_without_promoting_synthetic_capture():
    cases = load_design_manifest(CASES)
    corpus = _load_module(
        "routing_reuse_corpus",
        ROOT / "experiments" / "routing-reuse" / "corpus.py",
    )
    task16_ids = set(corpus.CASES)
    assert {case["task16_case"] for case in cases if case["task16_case"]} <= task16_ids

    scenario_dir = ROOT / "experiments" / "routing-measurements" / "scenarios"
    task17_ids = {
        json.loads(path.read_text(encoding="utf-8"))["scenario_id"]
        for path in scenario_dir.glob("*.json")
    }
    assert {case["task17_scenario"] for case in cases if case["task17_scenario"]} <= task17_ids

    harness = _load_module(
        "routing_measurement_harness",
        ROOT / "experiments" / "routing-measurements" / "harness.py",
    )
    assert CAPTURE_VERSION == harness.SCHEMA_VERSION
    synthetic = json.loads((
        ROOT / "experiments" / "routing-measurements" / "samples"
        / "synthetic-steady-capture.json"
    ).read_text(encoding="utf-8"))
    assert harness.validate_capture(synthetic)["record_kind"] == "synthetic-recorder-test"


def test_furnace_oracle_is_independently_hand_checkable():
    case = {case["case_id"]: case for case in load_design_manifest(CASES)}["electric-furnace-chain"]
    balance = case["steady_balance"]
    assert Fraction(balance["gross_production"]["iron-plate"]) == Fraction(5, 8)
    assert Fraction(balance["activity_consumption"]["iron-plate"]) == Fraction(5, 8)
    assert Fraction(balance["gross_production"]["steel-plate"]) == Fraction(1, 8)
    assert Fraction(balance["net_export"]["steel-plate"]) == Fraction(1, 8)


def test_controlled_perturbation_catches_false_bottleneck_claim():
    case = {case["case_id"]: case for case in load_design_manifest(CASES)}[
        "capacity-perturbation-no-improvement"]
    perturbation = case["perturbation"]
    assert Fraction(perturbation["before_rate"]) == Fraction(10)
    assert Fraction(perturbation["after_rate"]) == Fraction(10)


def test_observation_tolerance_is_frozen_before_game_results():
    assert observation_error_limit(Fraction(15), Fraction(15), DEFAULT_WINDOW_TICKS) == Fraction(3, 40)
    assert observation_error_limit(Fraction(1), Fraction(1), DEFAULT_WINDOW_TICKS) == Fraction(1, 60)


def test_bad_balance_is_rejected_instead_of_becoming_an_oracle():
    document = json.loads(CASES.read_text(encoding="utf-8"))
    document["cases"][0]["steady_balance"]["net_export"]["iron-plate"] = "16"
    with pytest.raises(ThroughputDesignError, match="violates conservation"):
        validate_design_manifest(document)


def test_missing_required_case_is_rejected():
    document = json.loads(CASES.read_text(encoding="utf-8"))
    document["cases"].pop()
    with pytest.raises(ThroughputDesignError, match="case coverage differs"):
        validate_design_manifest(document)


def test_self_balanced_but_recipe_inconsistent_oracle_is_rejected():
    document = json.loads(CASES.read_text())
    case = next(c for c in document['cases'] if c['case_id'] == 'unequal-competing-consumers')
    # Both ledger sides still match, but 3 gears require 6 plates, not 3.
    case['steady_balance']['gross_production']['iron-gear-wheel'] = '3'
    case['steady_balance']['net_export']['iron-gear-wheel'] = '3'
    with pytest.raises(ThroughputDesignError, match='recipe coefficients'):
        validate_design_manifest(document)
