"""Task 21 DESIGN review: independent witnesses, never game observations.

The tick examples below are mathematical countermodels to proposed rules, not
implementations of Factorio or of task 20's absent simulator. Regression checks
record the prerequisite defects discovered in the original review.
No production file is repaired by these tests.
"""
from __future__ import annotations

from fractions import Fraction
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MEASUREMENTS = ROOT / "experiments" / "routing-measurements"


def capture():
    # Keep the synthetic label, including in every adversarial mutation.
    return json.loads((MEASUREMENTS / "samples" / "synthetic-steady-capture.json").read_text())


@pytest.fixture
def harness():
    spec = importlib.util.spec_from_file_location("task21_capture_review", MEASUREMENTS / "harness.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_r1_three_flat_windows_can_precede_positive_periodic_output():
    # Declared rational source: one item every 18,000 ticks, initial phase 0.
    # An uncongested finite transport delay of 32 ticks changes no long-run rate.
    # All physical inventories remain empty throughout the three tested windows.
    period, delay = 18_000, 32
    boundaries = (3_600, 7_200, 10_800, 14_400)

    def exported(tick):
        return max(0, (tick - delay) // period)

    counts = [exported(end) - exported(start) for start, end in zip(boundaries, boundaries[1:])]
    inventory_deltas = [0, 0, 0]
    assert counts == inventory_deltas == [0, 0, 0]
    assert len({tick % period for tick in boundaries}) == 4  # no repeated full state
    assert exported(18_032) == 1
    assert Fraction(60, period) == Fraction(1, 300) > 0
    # Zero rate/spread/inventory tolerance still accepts this false plateau.
    assert max(counts) - min(counts) == 0


def test_r1_window_boundary_recurrence_does_not_prove_a_fixed_point():
    # A two-state closed cycle returns at every 3,600-tick boundary.
    state = lambda tick: tick % 2
    assert state(3_600) == state(7_200) == state(10_800)
    assert state(3_600) != state(3_601)
    assert state(3_600) == state(3_602)


def test_r2_shared_budget_bounds_do_not_determine_external_allocation():
    # Distinct external ports A/B share 9 items/s. A accepts at most 3/s,
    # B at most 9/s. Even work conservation admits different operating rates.
    allocations = ((3, 6), (0, 9))
    for a, b in allocations:
        assert 0 <= a <= 3 and 0 <= b <= 9 and a + b == 9
    assert allocations[0] != allocations[1]


def test_r2_full_cycle_needs_joint_vacancy_resolution():
    # Two full one-slot resources can rotate simultaneously without overflowing.
    # Start-snapshot free-space eligibility instead rejects both transfers.
    capacity = (1, 1)
    occupied = (1, 1)
    snapshot_eligible = tuple(occupied[(i + 1) % 2] < capacity[(i + 1) % 2] for i in range(2))
    assert snapshot_eligible == (False, False)
    after_joint_commit = tuple(occupied[i] - 1 + 1 for i in range(2))
    assert after_joint_commit == capacity
    # These are alternative abstract transition rules, not a claimed game result.


def test_r3_unequal_consumer_oracle_obeys_loaded_recipe_stoichiometry():
    # Derive expectation from recipes independently of the manifest's ledger.
    from factoribot.gamedata import load_database
    db = load_database()
    plate_costs = {}
    for name in ("iron-gear-wheel", "pipe"):
        recipe = db.recipes[name]
        ingredient = next(i for i in recipe.ingredients if i.name == "iron-plate")
        product = next(i for i in recipe.results if i.name == name)
        plate_costs[name] = Fraction(str(ingredient.amount)) / Fraction(str(product.amount))
    assert plate_costs == {"iron-gear-wheel": 2, "pipe": 1}

    from factoribot.sustained_throughput import load_design_manifest
    cases = load_design_manifest(ROOT / "daemon/tests/fixtures/sustained_throughput/cases.json")
    balance = next(c for c in cases if c["case_id"] == "unequal-competing-consumers")["steady_balance"]
    required = sum(plate_costs[item] * Fraction(rate) for item, rate in balance["gross_production"].items())
    assert required == 9
    assert Fraction(balance["gross_production"]["iron-gear-wheel"]) == Fraction(3, 2)
    assert Fraction(balance["activity_consumption"]["iron-plate"]) == required


def test_r4_capture_rejects_inventory_jump_at_shared_tick(harness):
    doc = capture()
    doc["measurement_windows"][1]["inventory_start"] = {"iron-plate": 100}
    doc["measurement_windows"][1]["inventory_end"] = {"iron-plate": 100}
    # Window 1 ends at tick 7200 with zero; window 2 starts there with 100.
    # Each window locally balances, but the contiguous-run ledger does not.
    with pytest.raises(harness.CaptureError):
        harness.validate_capture(doc)


def test_r4_filling_blocked_capture_is_not_steady(harness):
    doc = capture()
    for index, window in enumerate(doc["measurement_windows"]):
        window["collected"] = {"iron-plate": 0}
        window["inventory_start"] = {"iron-plate": 900 * index}
        window["inventory_end"] = {"iron-plate": 900 * (index + 1)}
    result = harness.validate_capture(doc)
    assert result["record_kind"] == "synthetic-recorder-test"
    assert result["stability"] != "steady-within-tolerance"


def test_r4_repeat_validation_enforces_scenario_tolerance(harness, tmp_path):
    scenario = MEASUREMENTS / "scenarios" / "belt-straight-one-lane.json"
    paths = []
    for index in range(2):
        doc = capture()
        doc["scenario_id"] = "belt-straight-fast-one-lane"
        doc["run_id"] = f"task21-synthetic-{index}"
        doc["stability_tolerance_items_per_s"] = 100
        doc["measurement_windows"][1]["source_extracted"] = {"iron-plate": 0}
        doc["measurement_windows"][1]["collected"] = {"iron-plate": 0}
        path = tmp_path / f"run-{index}.json"
        path.write_text(json.dumps(doc))
        paths.append(path)
    try:
        result = harness.validate_repeats(scenario, paths)
    except harness.CaptureError:
        return  # Explicit scenario mismatch rejection is also correct.
    assert result["all_runs_steady"] is False  # 15 vs 0/s, scenario tolerance 1/60


def test_r4_repeat_validation_enforces_declared_warmup_and_windows(harness, tmp_path):
    scenario = MEASUREMENTS / "scenarios" / "belt-straight-one-lane.json"
    paths = []
    for index in range(2):
        doc = capture()
        doc["scenario_id"] = "belt-straight-fast-one-lane"
        doc["run_id"] = f"task21-short-synthetic-{index}"
        window = doc["measurement_windows"][0]
        window.update(start_tick=0, end_tick=1, source_extracted={}, collected={})
        doc["measurement_windows"] = [window]
        path = tmp_path / f"run-{index}.json"
        path.write_text(json.dumps(doc))
        paths.append(path)
    with pytest.raises(harness.CaptureError):
        harness.validate_repeats(scenario, paths)


def test_r5_transport_capture_v1_cannot_validate_a_conserving_furnace_window(harness):
    # Hand-derived 8 seconds: 5 ore -> 5 intermediate plates -> 1 steel.
    # This is a synthetic interface witness; no engine measurement is invented.
    imported = {"iron-ore": 5}
    produced = {"iron-plate": 5, "steel-plate": 1}
    consumed = {"iron-ore": 5, "iron-plate": 5}
    exported = {"steel-plate": 1}
    for item in set(imported) | set(produced) | set(consumed) | set(exported):
        assert imported.get(item, 0) + produced.get(item, 0) == consumed.get(item, 0) + exported.get(item, 0)
    doc = capture()
    doc["supply"]["item"] = "iron-ore"
    doc["measurement_windows"] = [{
        "start_tick": 3600, "end_tick": 4080,
        "source_extracted": imported, "collected": exported,
        "inventory_start": {}, "inventory_end": {},
    }]
    with pytest.raises(harness.CaptureError, match="violates conservation"):
        harness.validate_capture(doc)


def test_aggregate_inserter_rate_does_not_identify_drop_phase():
    # Both abstract machines move one item every 10 ticks; their first drops
    # differ, affecting a downstream pickup that is eligible only at tick 3.
    phases = ((2, 8), (8, 2))
    assert [Fraction(60, outward + returning) for outward, returning in phases] == [6, 6]
    assert [outward <= 3 for outward, _ in phases] == [True, False]
