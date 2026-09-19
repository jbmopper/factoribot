"""Checks for the task-16 corpus and result summarizer."""

from __future__ import annotations

import json
from pathlib import Path

from corpus import get_cases
from run_factoribot_inspect import as_factorio_2
from run_static_analyser import summarize


HERE = Path(__file__).resolve().parent


def test_corpus_has_required_cases():
    assert set(get_cases()) == {
        "straight_one_lane",
        "lane_merge",
        "inserter_limited_transfer",
        "blocked_output",
        "unequal_competing_consumers",
        "splitter_priority_right",
        "furnace_chain",
    }


def test_blueprints_have_unique_positive_entity_numbers():
    for case in get_cases().values():
        entities = case["blueprint"]["blueprint"]["entities"]
        numbers = [entity["entity_number"] for entity in entities]
        assert numbers == list(range(1, len(numbers) + 1))


def test_get_cases_is_defensive_copy():
    first = get_cases()
    first["straight_one_lane"]["blueprint"]["blueprint"]["entities"][0]["name"] = "bad"
    assert (
        get_cases()["straight_one_lane"]["blueprint"]["blueprint"]["entities"][0]["name"]
        == "transport-belt"
    )


def test_factorio_2_translation_preserves_layout_and_updates_directions():
    legacy = get_cases()["straight_one_lane"]["blueprint"]
    current = as_factorio_2(legacy)
    assert legacy["blueprint"]["entities"][0]["direction"] == 2
    assert current["blueprint"]["entities"][0]["direction"] == 4
    assert current["blueprint"]["version"] == 562949954469888


def test_summarize_preserves_flow_and_priority_fields():
    result = {
        "blueprint": {
            "items_input": {"iron-plate": 1},
            "items_output": {"iron-gear-wheel": 0.5},
            "entities_input": [1],
            "entities_output": [2],
            "entities_bottleneck": [1],
            "entities": [
                {
                    "entity_number": 1,
                    "name": "splitter",
                    "output_priority": "right",
                    "usage_rate": 1,
                    "transpoted_items": {"iron-plate": 1},
                    "parents": [],
                    "children": [2],
                }
            ],
        }
    }
    summary = summarize(result)
    assert summary["items_output"] == {"iron-gear-wheel": 0.5}
    assert summary["entities"][0]["output_priority"] == "right"


def test_recorded_analyser_counterexamples_remain_visible():
    results = json.loads((HERE / "results.json").read_text())
    cases = results["cases"]

    blocked = cases["blocked_output"]["observed"]
    assert blocked["items_output"] == {"iron-gear-wheel": 1.2}

    unprioritized = cases["unequal_competing_consumers"]["observed"]["items_output"]
    prioritized = cases["splitter_priority_right"]["observed"]["items_output"]
    assert unprioritized == prioritized
    assert unprioritized["iron-gear-wheel"] > 0.4
    assert unprioritized["pipe"] < 1e-12

    warning_counts = results["pilot"]["observed"]["warning_counts"]
    assert warning_counts["WARNING: Entity bulk-inserter not found in Factorio data"] == 608
    assert warning_counts["WARNING: Unknown direction 8 for fast-transport-belt"] == 850


def test_recorded_factoribot_comparison_preserves_lanes_and_uncertainty():
    results = json.loads((HERE / "factoribot-inspect-results.json").read_text())
    straight = results["cases"]["straight_one_lane"]
    assert straight["counts"]["lanes"] == 6
    assert "mechanics_unobserved" in {
        finding["code"] for finding in straight["finding_rows"]
    }

    blocked = results["cases"]["blocked_output"]
    codes = {finding["code"] for finding in blocked["finding_rows"]}
    assert {"blocked_output", "inserter_capacity_unknown"} <= codes
