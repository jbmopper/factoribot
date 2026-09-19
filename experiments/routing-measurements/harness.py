#!/usr/bin/env python3
"""Offline validator and rate calculator for controlled Factorio trials.

This module validates capture bundles after a trial in a named disposable
scenario. The separate ``run_trials.py`` launcher owns isolated game execution. A
record is either a ``game-observation`` supplied by an operator or an explicitly
``synthetic-recorder-test``; the latter can exercise this recorder but is never
reported as game evidence.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "factoribot-routing-measurement-capture-1"
TICKS_PER_SECOND = 60
DISPOSABLE_SAVE_PREFIX = "routing-measurement-17-"
ROOT = Path(__file__).resolve().parent


class CaptureError(ValueError):
    """A capture is not complete enough to be a reproducible measurement."""


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CaptureError(f"{field} must be an object")
    return value


def _number(value: Any, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise CaptureError(f"{field} must be a finite number")
    if minimum is not None and value < minimum:
        raise CaptureError(f"{field} must be at least {minimum}")
    return float(value)


def _required(doc: Mapping[str, Any], names: tuple[str, ...], label: str) -> None:
    missing = [name for name in names if name not in doc]
    if missing:
        raise CaptureError(f"{label} is missing {', '.join(missing)}")


def _inventory(value: Any, field: str) -> dict[str, int]:
    doc = _mapping(value, field)
    result: dict[str, int] = {}
    for item, count in doc.items():
        if not isinstance(item, str) or not item:
            raise CaptureError(f"{field} item names must be non-empty strings")
        number = _number(count, f"{field}.{item}", minimum=0)
        if number != int(number):
            raise CaptureError(f"{field}.{item} must be an integer item count")
        result[item] = int(number)
    return result


def _validate_metadata(capture: Mapping[str, Any]) -> None:
    """Validate one raw capture and return deterministic derived values.

    Conservation is intentionally local to the measured setup: items extracted
    from the declared source during each window equal items collected before the
    sink plus the retained inventory delta.  A deletion-only sink cannot satisfy
    this contract because it provides no collected count.
    """
    _required(capture, (
        "schema_version", "record_kind", "scenario_id", "run_id", "environment",
        "setup_blueprint", "research", "power_control", "supply", "removal",
        "warmup_ticks", "measurement_windows", "stability_tolerance_items_per_s",
    ), "capture")
    if capture["schema_version"] != SCHEMA_VERSION:
        raise CaptureError("unsupported capture schema version")
    if capture["record_kind"] not in {"game-observation", "synthetic-recorder-test"}:
        raise CaptureError("record_kind must be game-observation or synthetic-recorder-test")
    for name in ("scenario_id", "run_id", "setup_blueprint"):
        if not isinstance(capture[name], str) or not capture[name].strip():
            raise CaptureError(f"{name} must be a non-empty string")

    env = _mapping(capture["environment"], "environment")
    _required(env, ("game_executable", "game_version", "mods", "save_name"), "environment")
    if capture["record_kind"] == "game-observation":
        for name in ("game_executable", "game_version", "save_name"):
            if not isinstance(env[name], str) or not env[name].strip():
                raise CaptureError(f"environment.{name} must identify a game observation")
        if not env["save_name"].startswith(DISPOSABLE_SAVE_PREFIX):
            raise CaptureError(f"environment.save_name must start with {DISPOSABLE_SAVE_PREFIX!r}")
        if not isinstance(env["mods"], list):
            raise CaptureError("environment.mods must be the exact enabled mod list")
    else:
        if env["game_version"] != "SYNTHETIC-NOT-GAME-EVIDENCE":
            raise CaptureError("synthetic recorder tests must say SYNTHETIC-NOT-GAME-EVIDENCE")

    research = _mapping(capture["research"], "research")
    if "inserter-capacity-bonus" not in research:
        raise CaptureError("research must explicitly include inserter-capacity-bonus (zero if none)")
    _number(research["inserter-capacity-bonus"], "research.inserter-capacity-bonus", minimum=0)
    power = _mapping(capture["power_control"], "power_control")
    _required(power, ("power_available", "circuit_state"), "power_control")
    if power["power_available"] is not True:
        raise CaptureError("capture is not a powered control-state measurement")
    if not isinstance(power["circuit_state"], str) or not power["circuit_state"].strip():
        raise CaptureError("power_control.circuit_state must be explicit")

    supply = _mapping(capture["supply"], "supply")
    _required(supply, ("item", "available_capacity_items_per_s", "source_counter"), "supply")
    if not isinstance(supply["item"], str) or not supply["item"]:
        raise CaptureError("supply.item must be non-empty")
    _number(supply["available_capacity_items_per_s"], "supply.available_capacity_items_per_s", minimum=0)
    if not isinstance(supply["source_counter"], str) or not supply["source_counter"].strip():
        raise CaptureError("supply.source_counter must count extracted items")
    removal = _mapping(capture["removal"], "removal")
    _required(removal, ("collector", "count_before_removal"), "removal")
    if removal["count_before_removal"] is not True:
        raise CaptureError("removal.count_before_removal must be true; deleted sink items are uncounted")



def validate_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    if capture.get("schema_version") == "factoribot-routing-measurement-capture-3":
        raise CaptureError("v3 process captures require --scenario for identity validation")
    if capture.get("schema_version") == "factoribot-routing-measurement-capture-2":
        return validate_process_capture(capture)
    _validate_metadata(capture)
    supply = capture["supply"]
    _number(capture["warmup_ticks"], "warmup_ticks", minimum=0)
    tolerance = _number(capture["stability_tolerance_items_per_s"], "stability_tolerance_items_per_s", minimum=0)
    windows = capture["measurement_windows"]
    if not isinstance(windows, list) or not windows:
        raise CaptureError("measurement_windows must be a non-empty list")
    rates: list[float] = []
    details: list[dict[str, Any]] = []
    last_end: int | None = None
    last_inventory: dict[str, int] | None = None
    inventory_stationary = True
    item = supply["item"]
    for index, raw_window in enumerate(windows):
        window = _mapping(raw_window, f"measurement_windows[{index}]")
        _required(window, ("start_tick", "end_tick", "source_extracted", "collected", "inventory_start", "inventory_end"), f"measurement_windows[{index}]")
        start = _number(window["start_tick"], f"window {index} start_tick", minimum=0)
        end = _number(window["end_tick"], f"window {index} end_tick", minimum=0)
        if start != int(start) or end != int(end) or end <= start:
            raise CaptureError(f"window {index} ticks must be integers with end_tick > start_tick")
        if last_end is not None and start != last_end:
            raise CaptureError(f"window {index} must begin at previous end_tick (no hidden interval)")
        if start < capture["warmup_ticks"]:
            raise CaptureError(f"window {index} precedes declared warmup")
        last_end = int(end)
        source = _inventory(window["source_extracted"], f"window {index} source_extracted")
        collected = _inventory(window["collected"], f"window {index} collected")
        before = _inventory(window["inventory_start"], f"window {index} inventory_start")
        after = _inventory(window["inventory_end"], f"window {index} inventory_end")
        if last_inventory is not None and any(
            before.get(key, 0) != last_inventory.get(key, 0)
            for key in set(before) | set(last_inventory)
        ):
            raise CaptureError(f"window {index} inventory is discontinuous at shared tick")
        last_inventory = after
        inventory_stationary &= all(before.get(key, 0) == after.get(key, 0)
                                    for key in set(before) | set(after))
        keys = set(source) | set(collected) | set(before) | set(after)
        for measured_item in keys:
            retained_delta = after.get(measured_item, 0) - before.get(measured_item, 0)
            if source.get(measured_item, 0) != collected.get(measured_item, 0) + retained_delta:
                raise CaptureError(
                    f"window {index} violates conservation for {measured_item}: "
                    "source_extracted != collected + inventory delta")
        ticks = int(end - start)
        count = collected.get(item, 0)
        rates.append(count * TICKS_PER_SECOND / ticks)
        details.append({"start_tick": int(start), "end_tick": int(end), "ticks": ticks,
                        "collected_count": count, "rate_items_per_s": rates[-1]})
    spread = max(rates) - min(rates)
    return {"scenario_id": capture["scenario_id"], "run_id": capture["run_id"],
            "record_kind": capture["record_kind"], "window_rates": details,
            "rate_kind": "measured_interval_rate", "sustained_rate_established": False,
            "inventory_stationary_at_boundaries": inventory_stationary,
            "stability": "window-stable" if len(windows) >= 2 and spread <= tolerance and inventory_stationary else "window-variable",
            "rate_spread_items_per_s": spread, "stability_tolerance_items_per_s": tolerance}



def validate_process_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    """V2 multi-boundary/crafting ledger. Interval evidence, not convergence proof.

    Each boundary counter binds to an entity/lane and one item. Inventory includes
    hands; ingredients are consumed at craft start and products appear at finish.
    Start/completion counts are observed separately so in-progress crafts need not
    balance inside a window. Recipe coefficients come from the loaded database.
    """
    from factoribot.gamedata import load_database
    # Reuse only metadata checks, not v1's transport conservation or rate logic.
    _validate_metadata(dict(capture, schema_version=SCHEMA_VERSION))
    bindings = _mapping(capture.get("counter_bindings"), "counter_bindings")
    if not bindings:
        raise CaptureError("counter_bindings must identify observed boundaries")
    for ident, binding in bindings.items():
        _required(_mapping(binding, ident), ("entity", "lane", "item", "direction"), ident)
        if not all(isinstance(binding[k], str) and binding[k] for k in ("entity", "lane", "item")):
            raise CaptureError("counter entity/lane/item must be explicit")
        if binding["direction"] not in ("import", "export"):
            raise CaptureError("counter direction must be import or export")
    if capture.get("craft_accounting") != "consume-at-start-produce-at-completion":
        raise CaptureError("craft_accounting must name the supported event convention")
    db = load_database()
    rows = []
    last_end = None
    last_inventory = None
    for index, window in enumerate(capture["measurement_windows"]):
        _required(_mapping(window, "window"), ("start_tick", "end_tick", "counters", "inventory_start", "inventory_end", "craft_events"), "window")
        start = _number(window["start_tick"], "start_tick", minimum=capture["warmup_ticks"])
        end = _number(window["end_tick"], "end_tick", minimum=0)
        if start != int(start) or end != int(end) or end <= start or (last_end is not None and start != last_end):
            raise CaptureError("invalid or noncontiguous window ticks")
        before = _inventory(window["inventory_start"], "inventory_start")
        after = _inventory(window["inventory_end"], "inventory_end")
        if last_inventory is not None and any(before.get(k, 0) != last_inventory.get(k, 0) for k in set(before) | set(last_inventory)):
            raise CaptureError("inventory discontinuity")
        counters = _inventory(window["counters"], "counters")
        if set(counters) != set(bindings):
            raise CaptureError("every boundary counter must be recorded exactly once")
        imported, exported, consumed, produced = {}, {}, {}, {}
        for ident, count in counters.items():
            binding = bindings[ident]
            ledger = imported if binding["direction"] == "import" else exported
            item = binding["item"]
            ledger[item] = ledger.get(item, 0) + count
        if not isinstance(window["craft_events"], list):
            raise CaptureError("craft_events must be timestamped observations")
        for event in window["craft_events"]:
            _required(_mapping(event, "craft_event"), ("entity", "recipe", "tick", "kind", "count"), "craft_event")
            if not isinstance(event["entity"], str) or not event["entity"]:
                raise CaptureError("craft event requires an entity identity")
            tick = _number(event["tick"], "event tick")
            if tick != int(tick) or not start <= tick < end:
                raise CaptureError("craft event is outside its half-open window")
            count = _inventory({"count": event["count"]}, "craft count")["count"]
            if event["kind"] not in ("start", "complete") or event["recipe"] not in db.recipes:
                raise CaptureError("unknown recipe or craft event kind")
            recipe = db.recipes[event["recipe"]]
            parts = recipe.ingredients if event["kind"] == "start" else recipe.results
            ledger = consumed if event["kind"] == "start" else produced
            for part in parts:
                from fractions import Fraction
                amount = Fraction(str(part.amount)) * count
                ledger[part.name] = ledger.get(part.name, 0) + amount
        for item in set(imported) | set(exported) | set(consumed) | set(produced) | set(before) | set(after):
            if imported.get(item, 0) + produced.get(item, 0) != consumed.get(item, 0) + exported.get(item, 0) + after.get(item, 0) - before.get(item, 0):
                raise CaptureError(f"window {index} violates recipe conservation for {item}")
        rows.append({"start_tick": int(start), "end_tick": int(end),
                     "boundary_rates": {key: count * 60 / (end-start) for key, count in counters.items()},
                     "export_rates": {key: count * 60 / (end-start) for key, count in exported.items()}})
        last_end, last_inventory = end, after
    if not rows:
        raise CaptureError("measurement_windows must be nonempty")
    return {"schema_version": "factoribot-routing-measurement-result-2",
            "scenario_id": capture["scenario_id"], "run_id": capture["run_id"],
            "record_kind": capture["record_kind"], "rate_kind": "measured_interval_rate",
            "sustained_rate_established": False, "window_rates": rows,
            "counter_bindings": bindings}

def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise CaptureError(f"{path}: invalid JSON: {error}") from error


def validate_scenarios(directory: Path) -> list[str]:
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise CaptureError(f"no scenario files in {directory}")
    names: set[str] = set()
    for path in paths:
        doc = _mapping(load_json(path), str(path))
        if doc.get("schema_version") == "factoribot-routing-throughput-scenario-2":
            from factoribot.sustained_throughput import validate_operating_scenario

            validate_operating_scenario(doc)
            scenario_id = doc["scenario_id"]
            if scenario_id in names:
                raise CaptureError(f"{path}: scenario_id must be unique")
            names.add(scenario_id)
            continue
        _required(doc, ("scenario_version", "scenario_id", "setup", "measurement"), str(path))
        if doc["scenario_version"] != "factoribot-routing-measurement-scenario-1":
            raise CaptureError(f"{path}: unsupported scenario_version")
        scenario_id = doc["scenario_id"]
        if not isinstance(scenario_id, str) or not scenario_id or scenario_id in names:
            raise CaptureError(f"{path}: scenario_id must be unique and non-empty")
        names.add(scenario_id)
        setup = _mapping(doc["setup"], f"{path}.setup")
        _required(setup, ("entities", "supply_conditions", "removal_conditions", "blueprint_export_required"), f"{path}.setup")
        if setup["blueprint_export_required"] is not True:
            raise CaptureError(f"{path}: actual setup blueprint export must be required")
        measurement = _mapping(doc["measurement"], f"{path}.measurement")
        _required(measurement, ("warmup_ticks", "window_ticks", "repeat_runs", "stability_tolerance_items_per_s"), f"{path}.measurement")
        if _number(measurement["window_ticks"], f"{path}.measurement.window_ticks", minimum=1) != int(measurement["window_ticks"]):
            raise CaptureError(f"{path}: window_ticks must be integral")
        if _number(measurement["repeat_runs"], f"{path}.measurement.repeat_runs", minimum=2) != int(measurement["repeat_runs"]):
            raise CaptureError(f"{path}: repeat_runs must be integral and at least 2")
    return sorted(names)


def validate_repeats(scenario_path: Path, capture_paths: list[Path]) -> dict[str, Any]:
    """Validate all required independent runs for one scenario without averaging.

    This reports every rate window and any nonconvergence.  It intentionally
    never manufactures one mean rate from differing runs.
    """
    scenario = _mapping(load_json(scenario_path), str(scenario_path))
    if scenario.get("schema_version") == "factoribot-routing-throughput-scenario-2":
        from factoribot.sustained_throughput import (
            compare_prediction_to_captures,
            predict_operating_rate,
        )

        captures = [_mapping(load_json(path), str(path)) for path in capture_paths]
        prediction = predict_operating_rate(scenario)
        comparison = compare_prediction_to_captures(prediction, scenario, captures)
        return {
            "scenario_id": scenario["scenario_id"],
            "validated_runs": len(captures),
            "all_windows_match_prediction": comparison["all_windows_match"],
            "sustained_rate_established": False,
            "prediction": prediction,
            "comparison": comparison,
        }
    _required(scenario, ("scenario_id", "measurement"), str(scenario_path))
    measurement = _mapping(scenario["measurement"], f"{scenario_path}.measurement")
    _required(measurement, ("repeat_runs",), f"{scenario_path}.measurement")
    required_runs = int(_number(measurement["repeat_runs"], "measurement.repeat_runs", minimum=2))
    if len(capture_paths) < required_runs:
        raise CaptureError(f"{scenario['scenario_id']} requires {required_runs} runs; got {len(capture_paths)}")
    captures = [_mapping(load_json(path), str(path)) for path in capture_paths]
    if any(capture.get("schema_version") != SCHEMA_VERSION for capture in captures):
        raise CaptureError("v2 process captures require a versioned process scenario; v1 repeat validation is transport-only")
    results = [validate_capture(capture) for capture in captures]
    tolerance = _number(measurement["stability_tolerance_items_per_s"], "scenario tolerance", minimum=0)
    for capture in captures:
        if capture["stability_tolerance_items_per_s"] != tolerance:
            raise CaptureError("capture tolerance must match the frozen scenario tolerance")
        if capture["warmup_ticks"] != measurement["warmup_ticks"]:
            raise CaptureError("capture warmup must match scenario")
        windows = capture["measurement_windows"]
        if len(windows) < measurement.get("min_windows", 2):
            raise CaptureError("capture has fewer than the required measurement windows")
        for window in windows:
            if window["end_tick"] - window["start_tick"] != measurement["window_ticks"]:
                raise CaptureError("capture interval must match scenario window_ticks")
        for key in ("research", "power_control"):
            if key in scenario and capture[key] != scenario[key]:
                raise CaptureError(f"capture {key} must match scenario")
        for key in ("record_kind", "setup_blueprint", "research", "power_control", "supply", "removal"):
            if capture[key] != captures[0][key]:
                raise CaptureError(f"repeat {key} differs between captures")
        env = {k: v for k, v in capture["environment"].items() if k != "save_name"}
        first_env = {k: v for k, v in captures[0]["environment"].items() if k != "save_name"}
        if env != first_env:
            raise CaptureError("repeat game environment differs")
    if any(result["scenario_id"] != scenario["scenario_id"] for result in results):
        raise CaptureError("all capture scenario_id values must match the scenario")
    run_ids = [result["run_id"] for result in results]
    if len(run_ids) != len(set(run_ids)):
        raise CaptureError("repeat captures must have unique run_id values")
    statuses = [result["stability"] for result in results]
    rates = [window["rate_items_per_s"] for result in results for window in result["window_rates"]]
    consistent = max(rates) - min(rates) <= tolerance
    return {"scenario_id": scenario["scenario_id"], "required_runs": required_runs,
            "validated_runs": len(results), "run_stability": statuses,
            "all_runs_steady": False,  # finite windows never establish a sustained rate
            "all_windows_stable": consistent and all(status == "window-stable" for status in statuses),
            "sustained_rate_established": False,
            "runs": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scenarios = sub.add_parser("validate-scenarios", help="validate versioned setup plans")
    scenarios.add_argument("directory", type=Path, nargs="?", default=ROOT / "scenarios")
    capture = sub.add_parser("validate-capture", help="validate one raw capture and print rates")
    capture.add_argument("path", type=Path)
    capture.add_argument("--scenario", type=Path,
                         help="required for a v3 hash-bound process capture")
    repeats = sub.add_parser("validate-repeats", help="validate the required independent runs; does not average")
    repeats.add_argument("scenario", type=Path)
    repeats.add_argument("captures", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        if args.command == "validate-scenarios":
            print(json.dumps({"valid_scenarios": validate_scenarios(args.directory)}, indent=2, sort_keys=True))
        elif args.command == "validate-capture":
            document = _mapping(load_json(args.path), str(args.path))
            if document.get("schema_version") == "factoribot-routing-measurement-capture-3":
                if args.scenario is None:
                    raise CaptureError("v3 process captures require --scenario")
                from factoribot.sustained_throughput import validate_process_capture_v3

                result = validate_process_capture_v3(document, _mapping(load_json(args.scenario), str(args.scenario)))
            else:
                result = validate_capture(document)
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(json.dumps(validate_repeats(args.scenario, args.captures), indent=2, sort_keys=True))
    except (CaptureError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
