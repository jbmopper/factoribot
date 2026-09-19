"""Offline checks for task 17's capture recorder; no Factorio is launched."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HARNESS_PATH = ROOT / "experiments" / "routing-measurements" / "harness.py"
SPEC = importlib.util.spec_from_file_location("routing_measurement_harness", HARNESS_PATH)
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)
SAMPLE_PATH = ROOT / "experiments" / "routing-measurements" / "samples" / "synthetic-steady-capture.json"


def sample() -> dict:
    return json.loads(SAMPLE_PATH.read_text())


def test_versioned_scenarios_are_complete_and_require_two_runs():
    assert harness.validate_scenarios(ROOT / "experiments" / "routing-measurements" / "scenarios") == [
        "belt-straight-fast-one-lane", "belt-straight-fast-two-lane",
        "fast-belt-blocked-output", "fast-inserter-chest-to-chest-fixed-research",
        "routing-measurement-23-base-2077-furnace-chain",
    ]


def test_synthetic_sample_calculates_counts_over_ticks_and_is_not_game_evidence():
    result = harness.validate_capture(sample())
    assert result["record_kind"] == "synthetic-recorder-test"
    assert [window["rate_items_per_s"] for window in result["window_rates"]] == [15.0, 15.0]
    assert result["stability"] == "window-stable"


def test_inventory_delta_is_part_of_conservation_not_an_unexplained_loss():
    capture = sample()
    window = capture["measurement_windows"][0]
    window["source_extracted"] = {"iron-plate": 10}
    window["collected"] = {"iron-plate": 4}
    window["inventory_start"] = {"iron-plate": 2}
    window["inventory_end"] = {"iron-plate": 8}
    capture["measurement_windows"] = [window]
    result = harness.validate_capture(capture)
    assert result["window_rates"][0]["rate_items_per_s"] == pytest.approx(4 / 60)


def test_rejects_deleted_sink_and_incomplete_game_observation():
    capture = sample()
    capture["removal"]["count_before_removal"] = False
    with pytest.raises(harness.CaptureError, match="deleted sink"):
        harness.validate_capture(capture)
    capture = sample()
    capture["record_kind"] = "game-observation"
    capture["environment"]["game_version"] = "2.0.77"
    capture["environment"]["save_name"] = "live-save"
    with pytest.raises(harness.CaptureError, match="routing-measurement-17"):
        harness.validate_capture(capture)


def test_rejects_nonconserving_record_and_labels_oscillation_instead_of_averaging():
    capture = sample()
    capture["measurement_windows"][1]["collected"]["iron-plate"] = 899
    with pytest.raises(harness.CaptureError, match="violates conservation"):
        harness.validate_capture(capture)
    capture = sample()
    capture["measurement_windows"][1]["source_extracted"]["iron-plate"] = 840
    capture["measurement_windows"][1]["collected"]["iron-plate"] = 840
    assert harness.validate_capture(capture)["stability"] == "window-variable"


def test_repeat_validator_requires_two_distinct_runs_and_does_not_average(tmp_path):
    scenario = ROOT / "experiments" / "routing-measurements" / "scenarios" / "belt-straight-one-lane.json"
    first = sample()
    first["scenario_id"] = "belt-straight-fast-one-lane"
    first["power_control"]["circuit_state"] = "no circuit wires or enable condition"
    path1 = tmp_path / "run-1.json"
    path1.write_text(json.dumps(first))
    with pytest.raises(harness.CaptureError, match="requires 2 runs"):
        harness.validate_repeats(scenario, [path1])
    second = sample()
    second["scenario_id"] = "belt-straight-fast-one-lane"
    second["power_control"]["circuit_state"] = "no circuit wires or enable condition"
    second["run_id"] = "synthetic-only-2"
    path2 = tmp_path / "run-2.json"
    path2.write_text(json.dumps(second))
    result = harness.validate_repeats(scenario, [path1, path2])
    assert result["validated_runs"] == 2
    assert result["all_windows_stable"] is True
    assert result["all_runs_steady"] is False
    assert "average" not in result


def test_repeat_rates_must_agree_across_runs(tmp_path):
    scenario = ROOT / 'experiments/routing-measurements/scenarios/belt-straight-one-lane.json'
    paths = []
    for index, count in enumerate((900, 600)):
        doc = sample()
        doc['scenario_id'] = 'belt-straight-fast-one-lane'
        doc['run_id'] = str(index)
        doc['power_control']['circuit_state'] = 'no circuit wires or enable condition'
        for window in doc['measurement_windows']:
            window['source_extracted']['iron-plate'] = count
            window['collected']['iron-plate'] = count
        path = tmp_path / f'{index}.json'
        path.write_text(json.dumps(doc))
        paths.append(path)
    result = harness.validate_repeats(scenario, paths)
    assert result['run_stability'] == ['window-stable', 'window-stable']
    assert not result['all_windows_stable']
    assert not result['sustained_rate_established']


def test_flat_finite_windows_never_prove_sustained_rate():
    doc = sample()
    for window in doc['measurement_windows']:
        window['source_extracted'] = {}
        window['collected'] = {}
    result = harness.validate_capture(doc)
    assert result['stability'] == 'window-stable'
    assert result['sustained_rate_established'] is False


def process_sample():
    doc = sample()
    doc['schema_version'] = 'factoribot-routing-measurement-capture-2'
    doc['craft_accounting'] = 'consume-at-start-produce-at-completion'
    doc['counter_bindings'] = {
        'ore-left': {'entity': 'belt1', 'lane': 'left', 'item': 'iron-ore', 'direction': 'import'},
        'steel-out': {'entity': 'chest1', 'lane': 'inventory', 'item': 'steel-plate', 'direction': 'export'},
    }
    doc['measurement_windows'] = [{
        'start_tick': 3600, 'end_tick': 4080,
        'inventory_start': {}, 'inventory_end': {},
        'counters': {'ore-left': 5, 'steel-out': 1},
        'craft_events': [
            {'entity': 'f1', 'recipe': 'iron-plate', 'tick': 3600, 'kind': 'start', 'count': 5},
            {'entity': 'f1', 'recipe': 'iron-plate', 'tick': 3700, 'kind': 'complete', 'count': 5},
            {'entity': 'f2', 'recipe': 'steel-plate', 'tick': 3750, 'kind': 'start', 'count': 1},
            {'entity': 'f2', 'recipe': 'steel-plate', 'tick': 4079, 'kind': 'complete', 'count': 1},
        ],
    }]
    return doc


def test_process_capture_preserves_export_identity_and_recipe_conservation():
    doc = process_sample()
    result = harness.validate_capture(doc)
    assert result['window_rates'][0]['export_rates'] == {'steel-plate': 0.125}
    assert result['window_rates'][0]['boundary_rates']['ore-left'] == 0.625
    assert result['record_kind'] == 'synthetic-recorder-test'
    assert not result['sustained_rate_established']
    doc['measurement_windows'][0]['counters']['steel-out'] = 2
    with pytest.raises(harness.CaptureError, match='recipe conservation'):
        harness.validate_capture(doc)


def test_process_capture_rejects_unbound_counter_and_out_of_window_event():
    doc = process_sample()
    doc['measurement_windows'][0]['counters']['unbound'] = 1
    with pytest.raises(harness.CaptureError, match='every boundary'):
        harness.validate_capture(doc)
    doc = process_sample()
    doc['measurement_windows'][0]['craft_events'][0]['tick'] = 4080
    with pytest.raises(harness.CaptureError, match='half-open'):
        harness.validate_capture(doc)
