"""Restricted deterministic operating-rate and measurement contracts.

The existing routing LP remains the independent capacity-bound solver.  This
module adds only a deliberately small analytic adapter for a serial, noncompeting
furnace chain and a strict capture/comparison contract.  It is not a general
Factorio simulator.  Predictions are conditional analytic operating rates;
captures are actual measured interval rates.  Neither is relabelled as a
certified upper bound or as a recurrence-proved sustained rate.
"""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .blueprint_contract import MECHANICS_PROFILE, content_hash


DESIGN_CASE_VERSION = "factoribot-sustained-throughput-design-case-2"
PREDICTION_VERSION = "factoribot-sustained-throughput-prediction-1"
COMPARISON_VERSION = "factoribot-sustained-throughput-comparison-1"
CAPTURE_VERSION = "factoribot-routing-measurement-capture-1"
PROCESS_CAPTURE_VERSION = "factoribot-routing-measurement-capture-3"
SCENARIO_VERSION = "factoribot-routing-throughput-scenario-2"
OPERATING_MODEL_VERSION = "factoribot-serial-furnace-operating-model-1"
OPERATING_PREDICTION_VERSION = "factoribot-routing-operating-prediction-1"
OPERATING_COMPARISON_VERSION = "factoribot-routing-operating-comparison-1"
OPERATING_REPORT_VERSION = "factoribot-routing-throughput-report-1"
TICKS_PER_SECOND = 60

DEFAULT_WARMUP_TICKS = 3_600
DEFAULT_WINDOW_TICKS = 3_600
MIN_WINDOWS = 3
MAX_WINDOWS = 8
MAX_TICKS = DEFAULT_WARMUP_TICKS + MAX_WINDOWS * DEFAULT_WINDOW_TICKS
MAX_ENTITIES = 2_048
MAX_RESIDENT_TOKENS = 262_144
MAX_STATE_SIGNATURES = 65_536

ABSOLUTE_COUNT_QUANTUM = 1
RELATIVE_ERROR = Fraction(1, 200)  # 0.5%

REQUIRED_CASES = frozenset({
    "single-fast-belt-lane",
    "dual-fast-belt-lanes",
    "two-lane-merge",
    "unequal-competing-consumers",
    "priority-splitter",
    "fast-inserter-chest-to-chest",
    "electric-furnace-chain",
    "blocked-output",
    "initial-inventory-transient",
    "forced-nonconvergence",
    "capacity-perturbation-no-improvement",
    "pilot-subfactory-gate",
})

PREDICTION_GATES = frozenset({
    "conditional",
    "unsupported",
    "convergence-test",
    "integration-gate",
})

_BALANCE_FIELDS = (
    "accepted_import",
    "gross_production",
    "activity_consumption",
    "net_export",
    "stored_delta",
)


class ThroughputDesignError(ValueError):
    """A design fixture is incomplete or its mathematical oracle is invalid."""


class ThroughputError(ValueError):
    """A scenario, capture, prediction, or comparison is invalid."""


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ThroughputDesignError(f"{field} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ThroughputDesignError(
            f"{field} keys differ: missing {sorted(expected - actual)}, "
            f"unknown {sorted(actual - expected)}")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ThroughputDesignError(f"{field} must be a non-empty string")
    return value


def _optional_text(value: Any, field: str) -> str | None:
    return None if value is None else _text(value, field)


def _texts(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ThroughputDesignError(f"{field} must be a non-empty array")
    result = tuple(_text(item, f"{field}[]") for item in value)
    if len(set(result)) != len(result):
        raise ThroughputDesignError(f"{field} must not contain duplicates")
    return result


def _fraction(value: Any, field: str, *, nonnegative: bool = True) -> Fraction:
    if not isinstance(value, str):
        raise ThroughputDesignError(f"{field} must be an exact rational string")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ThroughputDesignError(f"{field} is not a rational number") from error
    if nonnegative and result < 0:
        raise ThroughputDesignError(f"{field} must be nonnegative")
    return result


def _int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ThroughputError(f"{field} must be an integer at least {minimum}")
    return value


def _required(value: Mapping[str, Any], names: set[str], field: str) -> None:
    missing = names - set(value)
    if missing:
        raise ThroughputError(f"{field} is missing {sorted(missing)}")


def _sealed(document: Mapping[str, Any], field: str) -> bool:
    value = document.get(field)
    return isinstance(value, str) and value == content_hash(
        {key: item for key, item in document.items() if key != field})


def seal_document(document: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(document)
    result.pop(field, None)
    result[field] = content_hash(result)
    return result


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _state(value: Any, field: str) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict):
        raise ThroughputError(f"{field} must be an object of named inventories")
    result: dict[str, dict[str, int]] = {}
    for resource, contents in value.items():
        if not isinstance(resource, str) or not resource or not isinstance(contents, dict):
            raise ThroughputError(f"{field} contains an invalid resource")
        parsed: dict[str, int] = {}
        for item, count in contents.items():
            if not isinstance(item, str) or not item:
                raise ThroughputError(f"{field}.{resource} has an invalid item")
            parsed[item] = _int(count, f"{field}.{resource}.{item}")
        result[resource] = parsed
    return result


def _state_totals(state: Mapping[str, Mapping[str, int]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for contents in state.values():
        for item, count in contents.items():
            totals[item] = totals.get(item, 0) + count
    return totals


def validate_operating_scenario(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the single supported analytic topology and all bound identities."""
    if not isinstance(value, dict):
        raise ThroughputError("scenario must be a JSON object")
    _required(value, {
        "schema_version", "scenario_id", "mechanics_profile", "game_version",
        "recipe_data", "analysis_blueprint", "routing", "model",
        "measurement", "auxiliary_trials", "scenario_hash",
    }, "scenario")
    if value["schema_version"] != SCENARIO_VERSION:
        raise ThroughputError("unsupported operating scenario version")
    if value["mechanics_profile"] != MECHANICS_PROFILE or value["game_version"] != "2.0.77":
        raise ThroughputError("operating scenario must target base 2.0.77 normal v1")
    if not _sealed(value, "scenario_hash"):
        raise ThroughputError("inconsistent scenario hash")
    if not isinstance(value["scenario_id"], str) or not value["scenario_id"]:
        raise ThroughputError("scenario_id must be non-empty")

    recipe_data = value["recipe_data"]
    if not isinstance(recipe_data, dict):
        raise ThroughputError("recipe_data must be an object")
    _required(recipe_data, {"sha256", "profile_extract_hash"}, "recipe_data")
    for name in ("sha256", "profile_extract_hash"):
        if not isinstance(recipe_data[name], str) or not recipe_data[name]:
            raise ThroughputError(f"recipe_data.{name} must be explicit")

    blueprint = value["analysis_blueprint"]
    if not isinstance(blueprint, dict):
        raise ThroughputError("analysis_blueprint must be an object")
    _required(blueprint, {"blueprint_string", "blueprint_hash"}, "analysis_blueprint")
    if not all(isinstance(blueprint[name], str) and blueprint[name] for name in blueprint):
        raise ThroughputError("analysis blueprint identity is incomplete")
    routing = value["routing"]
    if not isinstance(routing, dict):
        raise ThroughputError("routing must be an object")
    _required(routing, {"graph_hash", "request_hash", "inference_artifact_hash"}, "routing")

    model = value["model"]
    if not isinstance(model, dict) or model.get("kind") != "serial-furnace-chain":
        raise ThroughputError("only the serial-furnace-chain operating model is supported")
    _required(model, {
        "kind", "machines", "external_supply", "external_removal",
        "transport_assumption", "research", "power_control",
    }, "model")
    if model["transport_assumption"] != "noncompeting-services-observed-in-this-exact-scenario":
        raise ThroughputError("transport services must be explicitly scenario-specific")
    machines = model["machines"]
    if not isinstance(machines, list) or not machines:
        raise ThroughputError("model.machines must be a nonempty serial chain")
    seen_entities: set[str] = set()
    for index, machine in enumerate(machines):
        if not isinstance(machine, dict):
            raise ThroughputError(f"model.machines[{index}] must be an object")
        _required(machine, {"entity", "prototype", "recipe"}, f"model.machines[{index}]")
        if machine["prototype"] != "electric-furnace":
            raise ThroughputError("the first operating adapter supports electric furnaces only")
        if not all(isinstance(machine[name], str) and machine[name] for name in machine):
            raise ThroughputError("machine entity/prototype/recipe must be explicit")
        if machine["entity"] in seen_entities:
            raise ThroughputError("machine identities must be unique")
        seen_entities.add(machine["entity"])
    for field in ("external_supply", "external_removal", "research", "power_control"):
        if not isinstance(model[field], dict):
            raise ThroughputError(f"model.{field} must be an object")
    supply = model["external_supply"]
    _required(supply, {"item", "capacity_items_per_s", "schedule", "counter_id"}, "external_supply")
    _fraction(supply["capacity_items_per_s"], "external_supply.capacity_items_per_s")
    schedule = supply["schedule"]
    if not isinstance(schedule, dict) or schedule.get("kind") != "periodic-attempt":
        raise ThroughputError("external supply requires a periodic-attempt schedule")
    _int(schedule.get("interval_ticks"), "schedule.interval_ticks", minimum=1)
    _int(schedule.get("phase_tick"), "schedule.phase_tick")
    removal = model["external_removal"]
    _required(removal, {"item", "service", "counter_id"}, "external_removal")
    if removal["service"] != "count-before-unbounded-script-removal":
        raise ThroughputError("external removal must be counted before unbounded removal")

    measurement = value["measurement"]
    if not isinstance(measurement, dict):
        raise ThroughputError("measurement must be an object")
    _required(measurement, {
        "warmup_ticks", "window_ticks", "windows", "repeat_runs",
        "counter_bindings", "state_resources", "comparison_relative_error",
        "comparison_count_quantum",
    }, "measurement")
    _int(measurement["warmup_ticks"], "measurement.warmup_ticks")
    _int(measurement["window_ticks"], "measurement.window_ticks", minimum=1)
    _int(measurement["windows"], "measurement.windows", minimum=3)
    _int(measurement["repeat_runs"], "measurement.repeat_runs", minimum=2)
    if measurement["comparison_relative_error"] != str(RELATIVE_ERROR):
        raise ThroughputError("scenario changed the frozen relative comparison error")
    if measurement["comparison_count_quantum"] != ABSOLUTE_COUNT_QUANTUM:
        raise ThroughputError("scenario changed the frozen count quantum")
    bindings = measurement["counter_bindings"]
    if not isinstance(bindings, dict) or not bindings:
        raise ThroughputError("measurement.counter_bindings must be nonempty")
    for counter_id, binding in bindings.items():
        if not isinstance(binding, dict):
            raise ThroughputError(f"counter {counter_id} must be an object")
        _required(binding, {"entity", "lane", "item", "direction"}, f"counter {counter_id}")
        if binding["direction"] not in {"import", "export"}:
            raise ThroughputError(f"counter {counter_id} direction is invalid")
        if not all(isinstance(binding[name], str) and binding[name]
                   for name in ("entity", "lane", "item")):
            raise ThroughputError(f"counter {counter_id} identity is incomplete")
    if supply["counter_id"] not in bindings or bindings[supply["counter_id"]]["direction"] != "import":
        raise ThroughputError("supply counter is not bound as an import")
    if removal["counter_id"] not in bindings or bindings[removal["counter_id"]]["direction"] != "export":
        raise ThroughputError("removal counter is not bound as an export")
    resources = measurement["state_resources"]
    if not isinstance(resources, list) or not resources or len(resources) != len(set(resources)):
        raise ThroughputError("state_resources must be a nonempty unique array")
    if not all(isinstance(resource, str) and resource for resource in resources):
        raise ThroughputError("state resource names must be nonempty")
    if not any(resource.endswith(":hand") for resource in resources):
        raise ThroughputError("state resources must include inserter hands")

    auxiliary = value["auxiliary_trials"]
    if not isinstance(auxiliary, dict):
        raise ThroughputError("auxiliary_trials must be an object")
    _required(auxiliary, {
        "counter_bindings", "source_schedule", "research", "power_control", "setup",
    }, "auxiliary_trials")
    expected_aux_counters = {
        "single_lane_import", "single_lane_export", "dual_left_import",
        "dual_right_import", "dual_lane_export", "inserter_export",
    }
    aux_bindings = auxiliary["counter_bindings"]
    if not isinstance(aux_bindings, dict) or set(aux_bindings) != expected_aux_counters:
        raise ThroughputError("auxiliary counter bindings differ from the measured subset")
    if auxiliary["source_schedule"] != schedule:
        raise ThroughputError("auxiliary source schedule differs from the primary source schedule")
    if auxiliary["research"] != {"inserter-capacity-bonus": 0}:
        raise ThroughputError("auxiliary inserter research must be fixed at zero bonus")
    if auxiliary["power_control"] != model["power_control"]:
        raise ThroughputError("auxiliary power/control differs from the primary trial")
    if auxiliary["setup"] != {
        "straight_belts_per_line": 8,
        "inserter_source_items": 4_000,
        "removal": "count-before-unbounded-script-removal",
    }:
        raise ThroughputError("auxiliary setup differs from the measured subset")
    return dict(value)


def predict_operating_rate(
    scenario: Mapping[str, Any], *, database=None, recipe_data_sha256: str | None = None,
) -> dict[str, Any]:
    """Compute the conditional serial-furnace rate from loaded recipe coefficients."""
    scenario = validate_operating_scenario(scenario)
    if database is None:
        from .gamedata import load_database, read_dump

        _path, loaded_sha, _raw = read_dump()
        database = load_database()
    else:
        loaded_sha = recipe_data_sha256
    if not loaded_sha or loaded_sha != scenario["recipe_data"]["sha256"]:
        raise ThroughputError("loaded recipe data identity does not match the scenario")

    available = _fraction(
        scenario["model"]["external_supply"]["capacity_items_per_s"],
        "external_supply.capacity_items_per_s")
    current_item = scenario["model"]["external_supply"]["item"]
    machine_rows = []
    produced: dict[str, Fraction] = {}
    consumed: dict[str, Fraction] = {}
    for entry in scenario["model"]["machines"]:
        recipe = database.recipes.get(entry["recipe"])
        machine = database.machines.get(entry["prototype"])
        if recipe is None or machine is None:
            raise ThroughputError(f"loaded data lacks {entry['prototype']} / {entry['recipe']}")
        ingredients = [part for part in recipe.ingredients if part.type == "item"]
        results = [part for part in recipe.results if part.type == "item"]
        if (len(ingredients), len(results)) != (1, 1) or ingredients[0].name != current_item:
            raise ThroughputError("serial adapter requires one item input and one item output per recipe")
        input_amount = Fraction(str(ingredients[0].amount))
        output_amount = Fraction(str(results[0].amount))
        craft_capacity = Fraction(str(machine.speed)) / Fraction(str(recipe.energy))
        craft_rate = min(craft_capacity, available / input_amount)
        input_rate, output_rate = craft_rate * input_amount, craft_rate * output_amount
        consumed[current_item] = consumed.get(current_item, Fraction()) + input_rate
        produced[results[0].name] = produced.get(results[0].name, Fraction()) + output_rate
        machine_rows.append({
            "entity": entry["entity"], "prototype": entry["prototype"],
            "recipe": entry["recipe"], "crafts_per_s": str(craft_rate),
            "craft_capacity_per_s": str(craft_capacity),
            "input": {current_item: str(input_rate)},
            "output": {results[0].name: str(output_rate)},
        })
        current_item, available = results[0].name, output_rate
    export_item = scenario["model"]["external_removal"]["item"]
    if current_item != export_item:
        raise ThroughputError("serial chain result does not match the declared export")
    supply_item = scenario["model"]["external_supply"]["item"]
    supply_capacity = _fraction(
        scenario["model"]["external_supply"]["capacity_items_per_s"],
        "external_supply.capacity_items_per_s")
    accepted = consumed.get(supply_item, Fraction())
    prediction = {
        "schema_version": OPERATING_PREDICTION_VERSION,
        "model_version": OPERATING_MODEL_VERSION,
        "scenario_id": scenario["scenario_id"],
        "scenario_hash": scenario["scenario_hash"],
        "mechanics_profile": scenario["mechanics_profile"],
        "recipe_data_sha256": loaded_sha,
        "graph_hash": scenario["routing"]["graph_hash"],
        "request_hash": scenario["routing"]["request_hash"],
        "rate_kind": "conditional_analytic_operating_rate",
        "status": "conditional",
        "sustained_rate_established": False,
        "sustained_rate_reason": (
            "Analytic recipe balance assumes the exact scenario's noncompeting services remain nonblocking; "
            "no complete Factorio state recurrence is claimed."),
        "machines": machine_rows,
        "items": {
            "available_supply": {supply_item: str(supply_capacity)},
            "accepted_import": {supply_item: str(accepted)},
            "unused_supply": {supply_item: str(supply_capacity - accepted)},
            "gross_production": {item: str(rate) for item, rate in sorted(produced.items())},
            "activity_consumption": {item: str(rate) for item, rate in sorted(consumed.items())},
            "net_export": {export_item: str(available)},
            "stored_delta": {},
        },
        "assumptions": [
            "empty declared initial state followed by the scenario warmup",
            "normal quality, base 2.0.77, no modules or beacons",
            "periodic noncompeting source schedule and counted unbounded removal",
            "transport/inserter services are nonblocking only for this exact measured setup",
        ],
        "unsupported_scope": [
            "merges, splitters, cycles, turns, side-loading and shared external budgets",
            "general inserter phase prediction or arbitrary belt-to-machine layouts",
            "recurrence-proved sustained rates and layouts without a matching capture",
        ],
    }
    return seal_document(prediction, "prediction_hash")


def validate_process_capture_v3(
    capture: Mapping[str, Any], scenario: Mapping[str, Any], *, database=None,
) -> dict[str, Any]:
    """Validate a hash-bound game capture with named state and recipe events."""
    scenario = validate_operating_scenario(scenario)
    if not isinstance(capture, dict):
        raise ThroughputError("capture must be a JSON object")
    _required(capture, {
        "schema_version", "record_kind", "scenario_id", "scenario_hash", "run_id",
        "environment", "setup", "research", "power_control", "counter_bindings",
        "craft_accounting", "warmup_ticks", "measurement_windows", "auxiliary_trials",
        "capture_hash",
    }, "capture")
    if capture["schema_version"] != PROCESS_CAPTURE_VERSION or capture["record_kind"] != "game-observation":
        raise ThroughputError("capture must be a v3 game observation")
    if not _sealed(capture, "capture_hash"):
        raise ThroughputError("inconsistent capture hash")
    if (capture["scenario_id"], capture["scenario_hash"]) != (
            scenario["scenario_id"], scenario["scenario_hash"]):
        raise ThroughputError("capture scenario identity mismatch")
    if not isinstance(capture["run_id"], str) or not capture["run_id"]:
        raise ThroughputError("capture run_id must be explicit")
    environment = capture["environment"]
    if not isinstance(environment, dict):
        raise ThroughputError("capture environment must be an object")
    _required(environment, {
        "game_executable", "game_version", "build", "platform", "mods",
        "recipe_data_sha256", "isolated_write_directory", "isolated_mod_directory",
    }, "capture.environment")
    if environment["game_version"] != scenario["game_version"] or environment["build"] != 84539:
        raise ThroughputError("capture Factorio build differs from the scenario")
    if environment["mods"] != [{"name": "base", "version": "2.0.77"}]:
        raise ThroughputError("capture must identify the base-only mod set")
    if environment["recipe_data_sha256"] != scenario["recipe_data"]["sha256"]:
        raise ThroughputError("capture recipe-data identity mismatch")
    if environment["isolated_write_directory"] is not True or environment["isolated_mod_directory"] is not True:
        raise ThroughputError("capture did not declare isolated write/mod directories")
    setup = capture["setup"]
    if not isinstance(setup, dict):
        raise ThroughputError("capture setup must be an object")
    _required(setup, {"analysis_blueprint_hash", "trial_blueprint", "trial_blueprint_hash", "fixture_helpers"}, "capture.setup")
    if setup["analysis_blueprint_hash"] != scenario["analysis_blueprint"]["blueprint_hash"]:
        raise ThroughputError("capture analysis blueprint mismatch")
    if not isinstance(setup["trial_blueprint"], str) or not setup["trial_blueprint"]:
        raise ThroughputError("capture must retain the exact trial setup blueprint")
    if setup["trial_blueprint_hash"] != content_hash(setup["trial_blueprint"]):
        raise ThroughputError("trial setup blueprint hash mismatch")
    if not isinstance(setup["fixture_helpers"], list):
        raise ThroughputError("fixture_helpers must be explicit")
    if capture["research"] != scenario["model"]["research"] or capture["power_control"] != scenario["model"]["power_control"]:
        raise ThroughputError("capture research/power/control mismatch")
    if capture["counter_bindings"] != scenario["measurement"]["counter_bindings"]:
        raise ThroughputError("capture counter bindings mismatch")
    if capture["craft_accounting"] != "consume-at-start-produce-at-completion":
        raise ThroughputError("unsupported craft accounting")
    if capture["warmup_ticks"] != scenario["measurement"]["warmup_ticks"]:
        raise ThroughputError("capture warmup mismatch")
    windows = capture["measurement_windows"]
    if not isinstance(windows, list) or len(windows) != scenario["measurement"]["windows"]:
        raise ThroughputError("capture window count mismatch")
    if database is None:
        from .gamedata import load_database

        database = load_database()
    machine_recipes = {entry["entity"]: entry["recipe"] for entry in scenario["model"]["machines"]}
    bindings = scenario["measurement"]["counter_bindings"]
    required_resources = set(scenario["measurement"]["state_resources"])
    previous_end: int | None = None
    previous_state: dict[str, dict[str, int]] | None = None
    rows = []
    for index, window in enumerate(windows):
        if not isinstance(window, dict):
            raise ThroughputError(f"measurement_windows[{index}] must be an object")
        _required(window, {"start_tick", "end_tick", "counters", "state_start", "state_end", "craft_events"}, f"window {index}")
        start = _int(window["start_tick"], f"window {index}.start_tick")
        end = _int(window["end_tick"], f"window {index}.end_tick", minimum=start + 1)
        if end - start != scenario["measurement"]["window_ticks"]:
            raise ThroughputError(f"window {index} length mismatch")
        if start < capture["warmup_ticks"] or (previous_end is not None and start != previous_end):
            raise ThroughputError(f"window {index} is not contiguous after warmup")
        counters = window["counters"]
        if not isinstance(counters, dict) or set(counters) != set(bindings):
            raise ThroughputError(f"window {index} must record every named counter")
        counters = {name: _int(count, f"window {index}.counters.{name}")
                    for name, count in counters.items()}
        before = _state(window["state_start"], f"window {index}.state_start")
        after = _state(window["state_end"], f"window {index}.state_end")
        if set(before) != required_resources or set(after) != required_resources:
            raise ThroughputError(f"window {index} state resources differ from the scenario")
        if previous_state is not None and before != previous_state:
            raise ThroughputError(f"window {index} state is discontinuous at the shared tick")
        imported: dict[str, Fraction] = {}
        exported: dict[str, Fraction] = {}
        for counter_id, count in counters.items():
            binding = bindings[counter_id]
            target = imported if binding["direction"] == "import" else exported
            target[binding["item"]] = target.get(binding["item"], Fraction()) + count
        consumed: dict[str, Fraction] = {}
        produced: dict[str, Fraction] = {}
        events = window["craft_events"]
        if not isinstance(events, list):
            raise ThroughputError(f"window {index}.craft_events must be an array")
        for event in events:
            if not isinstance(event, dict):
                raise ThroughputError("craft event must be an object")
            _required(event, {"entity", "recipe", "tick", "kind", "count"}, "craft event")
            tick = _int(event["tick"], "craft event.tick")
            count = _int(event["count"], "craft event.count", minimum=1)
            if not start <= tick < end:
                raise ThroughputError("craft event falls outside its half-open window")
            if event["entity"] not in machine_recipes or machine_recipes[event["entity"]] != event["recipe"]:
                raise ThroughputError("craft event entity/recipe differs from the scenario")
            if event["kind"] not in {"start", "complete"}:
                raise ThroughputError("craft event kind must be start or complete")
            recipe = database.recipes.get(event["recipe"])
            if recipe is None:
                raise ThroughputError("craft event recipe is absent from loaded data")
            parts = recipe.ingredients if event["kind"] == "start" else recipe.results
            target = consumed if event["kind"] == "start" else produced
            for part in parts:
                if part.type != "item":
                    raise ThroughputError("process capture supports item recipes only")
                target[part.name] = target.get(part.name, Fraction()) + Fraction(str(part.amount)) * count
        before_totals, after_totals = _state_totals(before), _state_totals(after)
        items = set(imported) | set(exported) | set(consumed) | set(produced) | set(before_totals) | set(after_totals)
        for item in items:
            left = imported.get(item, 0) + produced.get(item, 0)
            right = consumed.get(item, 0) + exported.get(item, 0) + after_totals.get(item, 0) - before_totals.get(item, 0)
            if left != right:
                raise ThroughputError(f"window {index} violates recipe conservation for {item}: {left} != {right}")
        ticks = end - start
        rows.append({
            "start_tick": start, "end_tick": end,
            "boundary_rates": {counter_id: str(Fraction(count * TICKS_PER_SECOND, ticks))
                               for counter_id, count in sorted(counters.items())},
            "export_rates": {item: str(rate * TICKS_PER_SECOND / ticks)
                             for item, rate in sorted(exported.items())},
            "inventory_delta": {item: after_totals.get(item, 0) - before_totals.get(item, 0)
                                for item in sorted(items)},
            "craft_event_count": len(events),
        })
        previous_end, previous_state = end, after
    auxiliary = capture["auxiliary_trials"]
    if not isinstance(auxiliary, dict):
        raise ThroughputError("capture auxiliary_trials must be an object")
    _required(auxiliary, {"scenario", "warmup", "windows", "meanings"}, "capture auxiliary_trials")
    if auxiliary["scenario"] != scenario["auxiliary_trials"]:
        raise ThroughputError("capture auxiliary scenario identity mismatch")
    if not isinstance(auxiliary["meanings"], dict) or not auxiliary["meanings"]:
        raise ThroughputError("capture auxiliary meanings must be explicit")
    aux_counter_ids = set(scenario["auxiliary_trials"]["counter_bindings"])

    def auxiliary_interval(value: Any, label: str, start: int, end: int) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ThroughputError(f"{label} must be an object")
        _required(value, {"start_tick", "end_tick", "counters"}, label)
        if value["start_tick"] != start or value["end_tick"] != end:
            raise ThroughputError(f"{label} tick interval mismatch")
        counters = value["counters"]
        if not isinstance(counters, dict) or set(counters) != aux_counter_ids:
            raise ThroughputError(f"{label} counter identity mismatch")
        parsed = {name: _int(count, f"{label}.{name}") for name, count in counters.items()}
        ticks = end - start
        return {
            "start_tick": start,
            "end_tick": end,
            "counts": dict(sorted(parsed.items())),
            "boundary_rates": {
                name: str(Fraction(count * TICKS_PER_SECOND, ticks))
                for name, count in sorted(parsed.items())
            },
        }

    aux_warmup = auxiliary_interval(
        auxiliary["warmup"], "auxiliary warmup", 0, scenario["measurement"]["warmup_ticks"])
    aux_windows = auxiliary["windows"]
    if not isinstance(aux_windows, list) or len(aux_windows) != len(rows):
        raise ThroughputError("capture auxiliary window count mismatch")
    aux_rows = []
    for index, (aux_window, primary) in enumerate(zip(aux_windows, rows)):
        aux_row = auxiliary_interval(
            aux_window,
            f"auxiliary window {index}",
            primary["start_tick"],
            primary["end_tick"],
        )
        counts = aux_row["counts"]
        if counts["single_lane_import"] != counts["single_lane_export"]:
            raise ThroughputError(f"auxiliary window {index} single-lane conservation failed")
        if (counts["dual_left_import"] + counts["dual_right_import"]
                != counts["dual_lane_export"]):
            raise ThroughputError(f"auxiliary window {index} dual-lane conservation failed")
        aux_rows.append(aux_row)
    inserter_total = aux_warmup["counts"]["inserter_export"] + sum(
        row["counts"]["inserter_export"] for row in aux_rows)
    if inserter_total > scenario["auxiliary_trials"]["setup"]["inserter_source_items"]:
        raise ThroughputError("auxiliary inserter exported more than its declared initial stock")

    return {
        "schema_version": "factoribot-routing-measurement-result-3",
        "scenario_id": scenario["scenario_id"], "scenario_hash": scenario["scenario_hash"],
        "run_id": capture["run_id"], "capture_hash": capture["capture_hash"],
        "record_kind": "game-observation", "rate_kind": "actual_measured_interval_rate",
        "sustained_rate_established": False,
        "sustained_rate_reason": "Finite windows do not prove recurrence of complete future-affecting state.",
        "window_rates": rows,
        "auxiliary_measurements": {
            "rate_kind": "actual_measured_interval_rate",
            "warmup": aux_warmup,
            "windows": aux_rows,
        },
    }


def compare_prediction_to_captures(
    prediction: Mapping[str, Any], scenario: Mapping[str, Any],
    captures: list[Mapping[str, Any]], *, database=None,
) -> dict[str, Any]:
    """Compare every observed window independently using the predeclared tolerance."""
    scenario = validate_operating_scenario(scenario)
    if not isinstance(prediction, dict) or not _sealed(prediction, "prediction_hash"):
        raise ThroughputError("prediction is not sealed")
    if prediction.get("scenario_hash") != scenario["scenario_hash"]:
        raise ThroughputError("prediction scenario identity mismatch")
    required = scenario["measurement"]["repeat_runs"]
    if len(captures) != required:
        raise ThroughputError(f"scenario requires exactly {required} independent captures")
    results = [validate_process_capture_v3(capture, scenario, database=database)
               for capture in captures]
    if len({result["run_id"] for result in results}) != len(results):
        raise ThroughputError("capture run ids must be unique")
    environments = [capture["environment"] for capture in captures]
    if any(environment != environments[0] for environment in environments[1:]):
        raise ThroughputError("repeat capture environments differ")
    if any(capture["setup"] != captures[0]["setup"] for capture in captures[1:]):
        raise ThroughputError("repeat capture setups differ")
    supply = scenario["model"]["external_supply"]
    removal = scenario["model"]["external_removal"]
    predicted_boundaries = {
        supply["counter_id"]: {
            "direction": "import",
            "item": supply["item"],
            "rate": Fraction(prediction["items"]["accepted_import"][supply["item"]]),
        },
        removal["counter_id"]: {
            "direction": "export",
            "item": removal["item"],
            "rate": Fraction(prediction["items"]["net_export"][removal["item"]]),
        },
    }
    comparisons = []
    all_match = True
    for result in results:
        for window in result["window_rates"]:
            for counter_id, target in sorted(predicted_boundaries.items()):
                predicted = target["rate"]
                if counter_id not in window["boundary_rates"]:
                    raise ThroughputError(f"capture has no boundary counter {counter_id}")
                measured = Fraction(window["boundary_rates"][counter_id])
                tolerance = observation_error_limit(
                    predicted, measured, scenario["measurement"]["window_ticks"])
                match = abs(predicted - measured) <= tolerance
                all_match &= match
                comparisons.append({
                    "run_id": result["run_id"], "start_tick": window["start_tick"],
                    "end_tick": window["end_tick"], "counter_id": counter_id,
                    "direction": target["direction"], "item": target["item"],
                    "predicted_items_per_s": str(predicted),
                    "measured_items_per_s": str(measured),
                    "difference_items_per_s": str(measured - predicted),
                    "allowed_error_items_per_s": str(tolerance), "match": match,
                })
    comparison = {
        "schema_version": OPERATING_COMPARISON_VERSION,
        "scenario_hash": scenario["scenario_hash"],
        "prediction_hash": prediction["prediction_hash"],
        "capture_hashes": [capture["capture_hash"] for capture in captures],
        "rate_kinds": {
            "prediction": prediction["rate_kind"],
            "measurement": "actual_measured_interval_rate",
        },
        "all_windows_match": all_match,
        "comparisons": comparisons,
        "sustained_rate_established": False,
    }
    return seal_document(comparison, "comparison_hash")


def build_operating_report(
    scenario: Mapping[str, Any], captures: list[Mapping[str, Any]], *,
    routing_request: Mapping[str, Any] | None = None,
    routing_result: Mapping[str, Any] | None = None,
    database=None,
    recipe_data_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the CLI report while preserving the separate result meanings."""
    scenario = validate_operating_scenario(scenario)
    if routing_request is not None:
        if (routing_request.get("request_hash"), routing_request.get("graph_hash")) != (
                scenario["routing"]["request_hash"], scenario["routing"]["graph_hash"]):
            raise ThroughputError("routing request identity differs from the scenario")
    if routing_result is not None and (
            routing_result.get("request_hash"), routing_result.get("graph_hash")) != (
                scenario["routing"]["request_hash"], scenario["routing"]["graph_hash"]):
        raise ThroughputError("routing result identity differs from the scenario")
    prediction = predict_operating_rate(
        scenario, database=database, recipe_data_sha256=recipe_data_sha256)
    comparison = compare_prediction_to_captures(
        prediction, scenario, captures, database=database)
    report = {
        "document_kind": "factoribot.routing.throughput_report",
        "schema_version": OPERATING_REPORT_VERSION,
        "scenario": scenario,
        "capacity_upper_bound": ({
            "result_hash": routing_result.get("result_hash"),
            "status": routing_result.get("status"),
            "bounds": routing_result.get("bounds", []),
            "meaning": "Existing conservative capacity upper bound under its stated relaxations.",
        } if routing_result is not None else None),
        "prediction": prediction,
        "measurements": [validate_process_capture_v3(capture, scenario, database=database)
                         for capture in captures],
        "comparison": comparison,
        "result_meanings": {
            "capacity_upper_bound": "A certified ceiling under declared relaxations; not achieved throughput.",
            "prediction": "Conditional analytic operating rate for this exact restricted scenario.",
            "measurement": "Actual counts over named finite Factorio intervals; not a maximum or recurrence proof.",
        },
    }
    return seal_document(report, "report_hash")


def observation_error_limit(
    predicted_items_per_s: Fraction,
    measured_items_per_s: Fraction,
    window_ticks: int,
) -> Fraction:
    """Frozen task-20 tolerance; this is not an internal model tolerance."""
    if window_ticks <= 0:
        raise ThroughputDesignError("window_ticks must be positive")
    window_seconds = Fraction(window_ticks, TICKS_PER_SECOND)
    quantum = Fraction(ABSOLUTE_COUNT_QUANTUM, 1) / window_seconds
    relative = RELATIVE_ERROR * max(abs(predicted_items_per_s), abs(measured_items_per_s))
    return max(quantum, relative)


def _balance(value: Any, field: str) -> dict[str, dict[str, Fraction]] | None:
    if value is None:
        return None
    doc = _mapping(value, field)
    _exact_keys(doc, set(_BALANCE_FIELDS), field)
    parsed: dict[str, dict[str, Fraction]] = {}
    for name in _BALANCE_FIELDS:
        raw = _mapping(doc[name], f"{field}.{name}")
        parsed[name] = {
            _text(item, f"{field}.{name} item"): _fraction(
                amount,
                f"{field}.{name}.{item}",
                nonnegative=name != "stored_delta",
            )
            for item, amount in raw.items()
        }
    items = set().union(*(values.keys() for values in parsed.values()))
    for item in items:
        left = parsed["accepted_import"].get(item, Fraction()) + parsed["gross_production"].get(item, Fraction())
        right = (
            parsed["activity_consumption"].get(item, Fraction())
            + parsed["net_export"].get(item, Fraction())
            + parsed["stored_delta"].get(item, Fraction())
        )
        if left != right:
            raise ThroughputDesignError(
                f"{field} violates conservation for {item}: {left} != {right}")
    return parsed


def validate_design_manifest(value: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Validate the design corpus without treating it as game evidence."""
    document = _mapping(value, "manifest")
    _exact_keys(document, {"schema_version", "provenance", "defaults", "cases"}, "manifest")
    if document["schema_version"] != DESIGN_CASE_VERSION:
        raise ThroughputDesignError("unsupported design-case schema version")
    if document["provenance"] != "synthetic-mathematical-reference-not-game-evidence":
        raise ThroughputDesignError("design corpus must remain explicitly synthetic")

    defaults = _mapping(document["defaults"], "defaults")
    expected_defaults = {
        "ticks_per_second": TICKS_PER_SECOND,
        "warmup_ticks": DEFAULT_WARMUP_TICKS,
        "window_ticks": DEFAULT_WINDOW_TICKS,
        "min_windows": MIN_WINDOWS,
        "max_windows": MAX_WINDOWS,
        "max_ticks": MAX_TICKS,
        "max_entities": MAX_ENTITIES,
        "max_resident_tokens": MAX_RESIDENT_TOKENS,
        "max_state_signatures": MAX_STATE_SIGNATURES,
        "absolute_count_quantum": ABSOLUTE_COUNT_QUANTUM,
        "relative_error": str(RELATIVE_ERROR),
    }
    _exact_keys(defaults, set(expected_defaults), "defaults")
    if dict(defaults) != expected_defaults:
        raise ThroughputDesignError("manifest defaults differ from the frozen model design")

    raw_cases = document["cases"]
    if not isinstance(raw_cases, list):
        raise ThroughputDesignError("cases must be an array")
    expected_keys = {
        "case_id", "required_features", "mechanics_records", "task16_case",
        "task17_scenario", "prediction_gate", "oracle_basis", "steady_balance",
        "expectations", "perturbation", "recipe_crafts_per_s",
    }
    seen: set[str] = set()
    validated = []
    for index, raw in enumerate(raw_cases):
        case = _mapping(raw, f"cases[{index}]")
        _exact_keys(case, expected_keys, f"cases[{index}]")
        case_id = _text(case["case_id"], f"cases[{index}].case_id")
        if case_id in seen:
            raise ThroughputDesignError(f"duplicate case_id {case_id}")
        seen.add(case_id)
        _texts(case["required_features"], f"{case_id}.required_features")
        _texts(case["mechanics_records"], f"{case_id}.mechanics_records")
        _optional_text(case["task16_case"], f"{case_id}.task16_case")
        _optional_text(case["task17_scenario"], f"{case_id}.task17_scenario")
        if case["prediction_gate"] not in PREDICTION_GATES:
            raise ThroughputDesignError(f"{case_id}.prediction_gate is unsupported")
        _text(case["oracle_basis"], f"{case_id}.oracle_basis")
        balance = _balance(case["steady_balance"], f"{case_id}.steady_balance")
        crafts = _mapping(case["recipe_crafts_per_s"], f"{case_id}.recipe_crafts_per_s")
        if balance is not None:
            from .gamedata import load_database
            db = load_database()
            for field, attr in (("gross_production", "results"), ("activity_consumption", "ingredients")):
                calculated: dict[str, Fraction] = {}
                for recipe_name, raw_rate in crafts.items():
                    if recipe_name not in db.recipes:
                        raise ThroughputDesignError(f"unknown recipe {recipe_name}")
                    rate = _fraction(raw_rate, f"{case_id}.crafts.{recipe_name}")
                    for part in getattr(db.recipes[recipe_name], attr):
                        calculated[part.name] = calculated.get(part.name, Fraction()) + rate * Fraction(str(part.amount))
                if calculated != balance[field]:
                    raise ThroughputDesignError(f"{case_id}.{field} disagrees with loaded recipe coefficients")
        elif crafts:
            raise ThroughputDesignError(f"{case_id}: crafts require a balance")
        _texts(case["expectations"], f"{case_id}.expectations")
        if case["perturbation"] is not None:
            perturbation = _mapping(case["perturbation"], f"{case_id}.perturbation")
            _exact_keys(perturbation, {"change", "before_rate", "after_rate", "conclusion"}, f"{case_id}.perturbation")
            _text(perturbation["change"], f"{case_id}.perturbation.change")
            _fraction(perturbation["before_rate"], f"{case_id}.perturbation.before_rate")
            _fraction(perturbation["after_rate"], f"{case_id}.perturbation.after_rate")
            _text(perturbation["conclusion"], f"{case_id}.perturbation.conclusion")
        validated.append(case)
    if seen != REQUIRED_CASES:
        raise ThroughputDesignError(
            f"case coverage differs: missing {sorted(REQUIRED_CASES - seen)}, "
            f"unknown {sorted(seen - REQUIRED_CASES)}")
    return tuple(validated)


def load_design_manifest(path: Path) -> tuple[Mapping[str, Any], ...]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ThroughputDesignError(f"cannot load {path}: {error}") from error
    return validate_design_manifest(value)


__all__ = [
    "ABSOLUTE_COUNT_QUANTUM", "CAPTURE_VERSION", "COMPARISON_VERSION",
    "DEFAULT_WARMUP_TICKS", "DEFAULT_WINDOW_TICKS", "DESIGN_CASE_VERSION",
    "MAX_ENTITIES", "MAX_RESIDENT_TOKENS", "MAX_STATE_SIGNATURES", "MAX_TICKS",
    "MAX_WINDOWS", "MIN_WINDOWS", "PREDICTION_VERSION", "RELATIVE_ERROR",
    "OPERATING_COMPARISON_VERSION", "OPERATING_MODEL_VERSION",
    "OPERATING_PREDICTION_VERSION", "OPERATING_REPORT_VERSION", "PROCESS_CAPTURE_VERSION",
    "REQUIRED_CASES", "SCENARIO_VERSION", "TICKS_PER_SECOND", "ThroughputDesignError",
    "ThroughputError", "build_operating_report", "compare_prediction_to_captures",
    "file_sha256", "load_design_manifest", "observation_error_limit",
    "predict_operating_rate", "seal_document", "validate_design_manifest",
    "validate_operating_scenario", "validate_process_capture_v3",
]
