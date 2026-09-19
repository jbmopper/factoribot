#!/usr/bin/env python3
"""Generate and run isolated base-2.0.77 routing throughput trials.

The launcher creates a temporary Factorio config, write directory, mod list and
scenario, runs only that new scenario, copies the small capture JSON to the
requested output directory, then removes the temporary workspace. It never
opens an existing save or global mod directory.
"""
from __future__ import annotations

import argparse
import json
import platform
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from factoribot.blueprint import encode_blueprint
from factoribot.blueprint_contract import MECHANICS_PROFILE, content_hash
from factoribot.gamedata import read_dump
from factoribot.sustained_throughput import (
    ABSOLUTE_COUNT_QUANTUM,
    PROCESS_CAPTURE_VERSION,
    RELATIVE_ERROR,
    SCENARIO_VERSION,
    seal_document,
    validate_operating_scenario,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FACTORIO = Path(
    "/Volumes/Spess/SteamLibrary/steamapps/common/Factorio/"
    "factorio.app/Contents/MacOS/factorio")
PROFILE_MANIFEST = ROOT / "daemon/factoribot/evidence/routing_prototypes/manifest.json"
BLUEPRINT_VERSION = (2 << 48) | (77 << 16)
ITEMS = ("iron-ore", "iron-plate", "steel-plate")


def _entity(number: int, name: str, x: float, y: float, direction: int | None = None) -> dict:
    value = {"entity_number": number, "name": name, "position": {"x": x, "y": y}}
    if direction is not None:
        value["direction"] = direction
    return value


def analysis_entities() -> list[dict]:
    """The visible ore -> plate -> steel chain used by routing and the trial."""
    return [
        _entity(1, "fast-transport-belt", 0, 14, 4),
        _entity(2, "fast-transport-belt", 1, 14, 4),
        _entity(3, "fast-transport-belt", 2, 14, 4),
        _entity(4, "fast-inserter", 3, 14, 12),
        _entity(5, "electric-furnace", 5, 14),
        _entity(6, "fast-inserter", 7, 14, 12),
        _entity(7, "fast-transport-belt", 8, 14, 4),
        _entity(8, "fast-transport-belt", 9, 14, 4),
        _entity(9, "fast-transport-belt", 10, 14, 4),
        _entity(10, "fast-inserter", 11, 14, 12),
        _entity(11, "electric-furnace", 13, 14),
        _entity(12, "fast-inserter", 15, 14, 12),
        _entity(13, "fast-transport-belt", 16, 14, 4),
        _entity(14, "fast-transport-belt", 17, 14, 4),
        _entity(15, "fast-transport-belt", 18, 14, 4),
    ]


def auxiliary_entities() -> list[dict]:
    entities: list[dict] = []
    number = 100
    for y in (0, 4):
        for x in range(8):
            entities.append(_entity(number, "fast-transport-belt", x, y, 4))
            number += 1
    entities.extend([
        _entity(number, "steel-chest", 0, 9),
        _entity(number + 1, "fast-inserter", 1, 9, 12),
        _entity(number + 2, "steel-chest", 2, 9),
        _entity(150, "electric-energy-interface", 0, 20),
        _entity(151, "substation", 4, 18),
        _entity(152, "substation", 14, 18),
    ])
    return entities


def analysis_blueprint() -> str:
    return encode_blueprint({"blueprint": {
        "item": "blueprint", "label": "Factoribot 2.0.77 measured furnace chain",
        "version": BLUEPRINT_VERSION, "entities": analysis_entities(),
    }})


def trial_blueprint() -> str:
    entities = analysis_entities() + auxiliary_entities()
    return encode_blueprint({"blueprint": {
        "item": "blueprint", "label": "Factoribot disposable 2.0.77 trial setup",
        "version": BLUEPRINT_VERSION, "entities": entities,
    }})


def build_assignment_draft(graph: dict) -> dict:
    return {
        "document_kind": "factoribot.routing.assignment_draft",
        "view_version": "factoribot-blueprint-view-1",
        "blueprint_hash": graph["blueprint_hash"],
        "graph_hash": graph["graph_hash"],
        "assignments": {
            "schema_version": graph["schema_version"],
            "blueprint_hash": graph["blueprint_hash"],
            "graph_hash": graph["graph_hash"],
            "feeds": [{
                "id": "ore_input_left_lane", "budget_id": "iron_ore",
                "endpoint": {"entity": {"book_path": [], "entity_number": 1},
                             "kind": "port", "name": "in_left"},
                "capacity": {"kind": "finite", "value": 15.0},
            }],
            "furnaces": [
                {"entity": {"book_path": [], "entity_number": 5}, "recipe": "iron-plate"},
                {"entity": {"book_path": [], "entity_number": 11}, "recipe": "steel-plate"},
            ],
            "controls": [],
        },
        "proposed_request": {
            "budgets": [{
                "id": "iron_ore",
                "material": {"kind": "item", "name": "iron-ore", "quality": "normal"},
                "capacity": {"kind": "finite", "value": 15.0},
            }],
            "exports": [{
                "id": "steel_output_right_lane",
                "material": {"kind": "item", "name": "steel-plate", "quality": "normal"},
                "endpoint": {"entity": {"book_path": [], "entity_number": 15},
                             "kind": "port", "name": "out_right"},
                "requirement": "minimum", "rate": 0.0,
                "sink": {"kind": "external",
                         "service": "Counted unbounded removal in the named disposable 2.0.77 trial",
                         "capacity": {"kind": "unlimited", "value": None}},
            }],
            "surplus": [],
            "objective": {"kind": "maximize_export", "export_id": "steel_output_right_lane"},
        },
        "notes": [
            "Measured-case declaration: supply is available up to 15/s on one fast-belt lane, never forced.",
            "Furnace recipes are explicit overrides because current inserter paths are conditional, so inference alone cannot justify them.",
        ],
    }


def build_host_policy() -> dict:
    return {
        "protected": {"entities": [], "endpoints": [], "areas": [],
                      "preserve_wiring": True, "preserve_unknown": True,
                      "preserve_boundaries": True},
        "assumptions": {
            "game_version": "2.0.77",
            "mods": [{"name": "base", "version": "2.0.77", "provides": [],
                      "alters_item_mechanics": False}],
            "quality": "normal", "available_recipes": ["iron-plate", "steel-plate"],
            "research": [{"name": "inserter-capacity-bonus", "level": 0}],
            "control_policy": "relax_open", "power": "assumed_available",
            "modules": "none", "beacons": "none", "irrelevant": [],
        },
        "detail": {"kind": "summary", "entity_ids": [], "cursor": None, "limit": 100},
    }


def state_resources() -> list[str]:
    resources = [f"belt-{number}:line-{lane}"
                 for number in (*range(1, 4), *range(7, 10), *range(13, 16))
                 for lane in (1, 2)]
    for number in (5, 11):
        resources.extend([f"furnace-{number}:source", f"furnace-{number}:result"])
    resources.extend(f"inserter-{number}:hand" for number in (4, 6, 10, 12))
    return resources


def build_scenario(request: dict, inference: dict | None) -> dict:
    profile = json.loads(PROFILE_MANIFEST.read_text())
    _path, dump_sha, _raw = read_dump(
        str(ROOT / "data/data-raw-dump-2.0.77-base.json"))
    blueprint = analysis_blueprint()
    if request.get("mechanics_profile") != MECHANICS_PROFILE:
        raise ValueError("request does not use the 2.0.77 mechanics profile")
    scenario = {
        "schema_version": SCENARIO_VERSION,
        "scenario_id": "routing-measurement-23-base-2077-furnace-chain",
        "mechanics_profile": MECHANICS_PROFILE,
        "game_version": "2.0.77",
        "recipe_data": {
            "sha256": dump_sha,
            "profile_extract_hash": profile["extract"]["content_hash"],
        },
        "analysis_blueprint": {
            "blueprint_string": blueprint,
            "blueprint_hash": request["blueprint_hash"],
        },
        "routing": {
            "graph_hash": request["graph_hash"],
            "request_hash": request["request_hash"],
            "inference_artifact_hash": None if inference is None else inference.get("artifact_hash"),
        },
        "model": {
            "kind": "serial-furnace-chain",
            "machines": [
                {"entity": "bp/root/e/5", "prototype": "electric-furnace", "recipe": "iron-plate"},
                {"entity": "bp/root/e/11", "prototype": "electric-furnace", "recipe": "steel-plate"},
            ],
            "external_supply": {
                "item": "iron-ore", "capacity_items_per_s": "15",
                "schedule": {"kind": "periodic-attempt", "interval_ticks": 4, "phase_tick": 0},
                "counter_id": "ore_input_left_lane",
            },
            "external_removal": {
                "item": "steel-plate", "service": "count-before-unbounded-script-removal",
                "counter_id": "steel_output_right_lane",
            },
            "transport_assumption": "noncompeting-services-observed-in-this-exact-scenario",
            "research": {"inserter-capacity-bonus": 0, "steel-processing": 1},
            "power_control": {
                "power_available": True,
                "service": "isolated-electric-energy-interface-network",
                "circuit_state": "none",
            },
        },
        "measurement": {
            "warmup_ticks": 3_600, "window_ticks": 3_600, "windows": 3, "repeat_runs": 2,
            "counter_bindings": {
                "ore_input_left_lane": {
                    "entity": "bp/root/e/1", "lane": "left", "item": "iron-ore", "direction": "import"},
                "steel_output_right_lane": {
                    "entity": "bp/root/e/15", "lane": "right", "item": "steel-plate", "direction": "export"},
            },
            "state_resources": state_resources(),
            "comparison_relative_error": str(RELATIVE_ERROR),
            "comparison_count_quantum": ABSOLUTE_COUNT_QUANTUM,
        },
        "auxiliary_trials": {
            "counter_bindings": {
                "single_lane_import": {
                    "prototype": "fast-transport-belt", "lane": "line-1",
                    "item": "iron-plate", "direction": "import"},
                "single_lane_export": {
                    "prototype": "fast-transport-belt", "lane": "line-1",
                    "item": "iron-plate", "direction": "export"},
                "dual_left_import": {
                    "prototype": "fast-transport-belt", "lane": "line-1",
                    "item": "iron-plate", "direction": "import"},
                "dual_right_import": {
                    "prototype": "fast-transport-belt", "lane": "line-2",
                    "item": "iron-plate", "direction": "import"},
                "dual_lane_export": {
                    "prototype": "fast-transport-belt", "lane": "both",
                    "item": "iron-plate", "direction": "export"},
                "inserter_export": {
                    "prototype": "fast-inserter", "lane": "sink-inventory",
                    "item": "iron-plate", "direction": "export"},
            },
            "source_schedule": {
                "kind": "periodic-attempt", "interval_ticks": 4, "phase_tick": 0},
            "research": {"inserter-capacity-bonus": 0},
            "power_control": {
                "power_available": True,
                "service": "isolated-electric-energy-interface-network",
                "circuit_state": "none",
            },
            "setup": {
                "straight_belts_per_line": 8,
                "inserter_source_items": 4_000,
                "removal": "count-before-unbounded-script-removal",
            },
        },
    }
    return seal_document(scenario, "scenario_hash")


CONTROL_LUA = r'''
local config = helpers.json_to_table(__CONFIG_JSON__)
local items = {"iron-ore", "iron-plate", "steel-plate"}

local function make(surface, name, x, y, direction, extra)
  local spec = {name=name, position={x,y}, force="player", raise_built=false}
  if direction then spec.direction = direction end
  if extra then for k,v in pairs(extra) do spec[k]=v end end
  local entity = surface.create_entity(spec)
  assert(entity, "failed to create " .. name .. " at " .. x .. "," .. y)
  entity.destructible = false
  return entity
end

local function contents(get_count)
  local result = {}
  for _,item in ipairs(items) do
    local count = get_count(item)
    if count > 0 then result[item] = count end
  end
  return result
end

local function snapshot_primary()
  local result = {}
  for _,number in ipairs({1,2,3,7,8,9,13,14,15}) do
    local belt = storage.entities["e" .. number]
    for lane=1,2 do
      local line = belt.get_transport_line(lane)
      result["belt-" .. number .. ":line-" .. lane] = contents(function(item) return line.get_item_count(item) end)
    end
  end
  for _,number in ipairs({5,11}) do
    local furnace = storage.entities["e" .. number]
    local source = furnace.get_inventory(defines.inventory.furnace_source)
    local output = furnace.get_inventory(defines.inventory.furnace_result)
    result["furnace-" .. number .. ":source"] = contents(function(item) return source.get_item_count(item) end)
    result["furnace-" .. number .. ":result"] = contents(function(item) return output.get_item_count(item) end)
  end
  for _,number in ipairs({4,6,10,12}) do
    local inserter = storage.entities["e" .. number]
    result["inserter-" .. number .. ":hand"] = contents(function(item)
      return inserter.held_stack.valid_for_read and inserter.held_stack.name == item and inserter.held_stack.count or 0
    end)
  end
  return result
end

local function totals(state)
  local result = { ["iron-ore"]=0, ["iron-plate"]=0, ["steel-plate"]=0 }
  for _,contents_by_item in pairs(state) do
    for item,count in pairs(contents_by_item) do result[item] = result[item] + count end
  end
  return result
end

local function start_window(tick)
  storage.window = {
    start_tick=tick, end_tick=tick + config.measurement.window_ticks,
    counters={ore_input_left_lane=0, steel_output_right_lane=0},
    state_start=snapshot_primary(), craft_events={}
  }
end

local function add_event(entity, recipe, tick, kind, count)
  if storage.window and tick >= storage.window.start_tick and tick < storage.window.end_tick and count > 0 then
    table.insert(storage.window.craft_events,
      {entity=entity, recipe=recipe, tick=tick, kind=kind, count=count})
  end
end

local function drain(chest, item)
  local inv = chest.get_inventory(defines.inventory.chest)
  local count = inv.get_item_count(item)
  if count > 0 then inv.remove{name=item, count=count} end
  return count
end

local function drain_line(belt, lane, item)
  local line = belt.get_transport_line(lane)
  local count = line.get_item_count(item)
  if count > 0 then line.remove_item{name=item, count=count} end
  return count
end

local function empty_aux_counters()
  return {
    single_lane_import=0, single_lane_export=0,
    dual_left_import=0, dual_right_import=0, dual_lane_export=0,
    inserter_export=0,
  }
end

script.on_init(function()
  storage.entities = {}
  storage.windows = {}
  storage.aux_windows = {}
  game.speed = 64
  local surface = game.surfaces[1]
  surface.always_day = true
  game.forces.player.inserter_stack_size_bonus = 0
  if game.forces.player.technologies["steel-processing"] then
    game.forces.player.technologies["steel-processing"].researched = true
  end

  local defs = config.analysis_entities
  for _,d in ipairs(defs) do
    storage.entities["e" .. d.entity_number] = make(surface, d.name, d.position.x, d.position.y, d.direction)
  end

  for x=0,7 do storage.entities["one_belt_"..x] = make(surface, "fast-transport-belt", x, 0, defines.direction.east) end
  for x=0,7 do storage.entities["dual_belt_"..x] = make(surface, "fast-transport-belt", x, 4, defines.direction.east) end
  storage.entities.ins_source = make(surface, "steel-chest", 0, 9)
  storage.entities.ins = make(surface, "fast-inserter", 1, 9, defines.direction.west)
  storage.entities.ins_sink = make(surface, "steel-chest", 2, 9)
  storage.entities.ins_source.get_inventory(defines.inventory.chest).insert{name="iron-plate", count=4000}
  storage.entities.power = make(surface, "electric-energy-interface", 0, 20)
  storage.entities.power.power_production = 500000000000
  storage.entities.pole_one = make(surface, "substation", 4, 18)
  storage.entities.pole_two = make(surface, "substation", 14, 18)

  storage.finished = {e5=0,e11=0}
  storage.prev_state = snapshot_primary()
  storage.aux = empty_aux_counters()
end)

script.on_event(defines.events.on_tick, function(event)
  local tick = event.tick

  local current_state = snapshot_primary()
  local before = totals(current_state)
  local previous = totals(storage.prev_state)
  local finished5 = storage.entities.e5.products_finished or 0
  local finished11 = storage.entities.e11.products_finished or 0
  local complete5 = finished5 - storage.finished.e5
  local complete11 = finished11 - storage.finished.e11
  storage.finished.e5, storage.finished.e11 = finished5, finished11
  local transition_tick = math.max(0, tick - 1)
  local start5 = previous["iron-ore"] - before["iron-ore"]
  local start11_items = previous["iron-plate"] + complete5 - before["iron-plate"]
  assert(start11_items % 5 == 0, "steel recipe start accounting was not integral")
  local start11 = start11_items / 5
  add_event("bp/root/e/5", "iron-plate", transition_tick, "start", start5)
  add_event("bp/root/e/5", "iron-plate", transition_tick, "complete", complete5)
  add_event("bp/root/e/11", "steel-plate", transition_tick, "start", start11)
  add_event("bp/root/e/11", "steel-plate", transition_tick, "complete", complete11)

  if tick == config.measurement.warmup_ticks then
    storage.aux_warmup = {start_tick=0, end_tick=tick, counters=storage.aux}
    storage.aux = empty_aux_counters()
    start_window(tick)
  end
  if storage.window and tick == storage.window.end_tick then
    table.insert(storage.aux_windows, {
      start_tick=storage.window.start_tick, end_tick=tick, counters=storage.aux})
    storage.window.state_end = current_state
    table.insert(storage.windows, storage.window)
    if #storage.windows == config.measurement.windows then
      local capture = {
        schema_version=config.capture_version, record_kind="game-observation",
        scenario_id=config.scenario_id, scenario_hash=config.scenario_hash,
        run_id=config.run_id, environment={}, setup=config.setup,
        research=config.model.research, power_control=config.model.power_control,
        counter_bindings=config.measurement.counter_bindings,
        craft_accounting="consume-at-start-produce-at-completion",
        warmup_ticks=config.measurement.warmup_ticks,
        measurement_windows=storage.windows,
        runtime_diagnostics={
          e4_energy=storage.entities.e4.energy,
          e4_status=storage.entities.e4.status,
          e5_energy=storage.entities.e5.energy,
          e5_status=storage.entities.e5.status,
          inserter_energy=storage.entities.ins.energy,
          inserter_status=storage.entities.ins.status,
          e4_pickup={x=storage.entities.e4.pickup_position.x, y=storage.entities.e4.pickup_position.y},
          e4_drop={x=storage.entities.e4.drop_position.x, y=storage.entities.e4.drop_position.y},
          inserter_pickup={x=storage.entities.ins.pickup_position.x, y=storage.entities.ins.pickup_position.y},
          inserter_drop={x=storage.entities.ins.drop_position.x, y=storage.entities.ins.drop_position.y},
          power_production=storage.entities.power.power_production,
        },
        auxiliary_trials={scenario=config.auxiliary_trials,
          warmup=storage.aux_warmup, windows=storage.aux_windows,
          meanings={straight_belts="actual boundary counts on named lanes",
                    inserter="actual chest-to-chest output at fixed zero capacity bonus"}}
      }
      helpers.write_file("capture-raw.json", helpers.table_to_json(capture), false)
      return
    end
    storage.aux = empty_aux_counters()
    start_window(tick)
  end

  local measuring = storage.window ~= nil and tick >= storage.window.start_tick and tick < storage.window.end_tick
  if tick % 4 == 0 then
    local line = storage.entities.e1.get_transport_line(1)
    if line.can_insert_at_back() and line.insert_at_back{name="iron-ore", count=1} and measuring then
      storage.window.counters.ore_input_left_lane = storage.window.counters.ore_input_left_lane + 1
    end
    local one = storage.entities.one_belt_0.get_transport_line(1)
    if one.can_insert_at_back() and one.insert_at_back{name="iron-plate", count=1} then
      storage.aux.single_lane_import = storage.aux.single_lane_import + 1
    end
    for lane=1,2 do
      local dual = storage.entities.dual_belt_0.get_transport_line(lane)
      if dual.can_insert_at_back() and dual.insert_at_back{name="iron-plate", count=1} then
        if lane == 1 then storage.aux.dual_left_import = storage.aux.dual_left_import + 1
        else storage.aux.dual_right_import = storage.aux.dual_right_import + 1 end
      end
    end
  end
  local steel = drain_line(storage.entities.e15, 2, "steel-plate")
  if measuring then storage.window.counters.steel_output_right_lane = storage.window.counters.steel_output_right_lane + steel end
  storage.aux.single_lane_export = storage.aux.single_lane_export + drain_line(
    storage.entities.one_belt_7, 1, "iron-plate")
  storage.aux.dual_lane_export = storage.aux.dual_lane_export + drain_line(
    storage.entities.dual_belt_7, 1, "iron-plate")
  storage.aux.dual_lane_export = storage.aux.dual_lane_export + drain_line(
    storage.entities.dual_belt_7, 2, "iron-plate")
  storage.aux.inserter_export = storage.aux.inserter_export + drain(
    storage.entities.ins_sink, "iron-plate")
  storage.prev_state = snapshot_primary()
end)
'''


def write_config(path: Path, write_dir: Path, read_dir: Path) -> None:
    path.write_text(
        "[path]\n"
        f"read-data={read_dir}\n"
        f"write-data={write_dir}\n"
        "[general]\nlocale=en\n")


def run_trial(factorio: Path, scenario: dict, run_id: str, out_path: Path) -> None:
    final_tick = (scenario["measurement"]["warmup_ticks"]
                  + scenario["measurement"]["windows"] * scenario["measurement"]["window_ticks"])
    with tempfile.TemporaryDirectory(prefix="factoribot-routing-2077-") as scratch:
        scratch_path = Path(scratch)
        write_dir = scratch_path / "write"
        mod_dir = scratch_path / "mods"
        scenario_name = f"routing-measurement-23-base-2077-{run_id}"
        scenario_dir = write_dir / "scenarios" / scenario_name
        scenario_dir.mkdir(parents=True)
        mod_dir.mkdir()
        (mod_dir / "mod-list.json").write_text(json.dumps({
            "mods": [{"name": "base", "enabled": True}],
        }, indent=2) + "\n")
        config_path = scratch_path / "config.ini"
        read_dir = factorio.parents[1] / "data"
        write_config(config_path, write_dir, read_dir)
        server_settings_path = scratch_path / "server-settings.json"
        server_settings = json.loads(
            (read_dir / "server-settings.example.json").read_text())
        server_settings.update({
            "name": "Factoribot disposable routing measurement",
            "description": "isolated local task-23 capture; removed after this run",
            "tags": ["factoribot", "disposable", "measurement"],
            "visibility": {"public": False, "lan": False},
            "require_user_verification": False,
            "auto_pause": False,
            "auto_pause_when_players_connect": False,
            "autosave_interval": 0,
        })
        server_settings_path.write_text(json.dumps(server_settings, indent=2) + "\n")
        setup = {
            "analysis_blueprint_hash": scenario["analysis_blueprint"]["blueprint_hash"],
            "trial_blueprint": trial_blueprint(),
            "trial_blueprint_hash": content_hash(trial_blueprint()),
            "fixture_helpers": [
                "scripted periodic source on bp/root/e/1 left lane",
                "count-before-unbounded scripted removal on bp/root/e/15 line 2 (right lane)",
                "isolated electric-energy-interface and two substations",
                "separate straight one-lane, straight dual-lane and fast-inserter trials",
            ],
        }
        payload = {
            "capture_version": PROCESS_CAPTURE_VERSION,
            "scenario_id": scenario["scenario_id"], "scenario_hash": scenario["scenario_hash"],
            "run_id": run_id, "analysis_entities": analysis_entities(),
            "model": scenario["model"], "measurement": scenario["measurement"],
            "auxiliary_trials": scenario["auxiliary_trials"], "setup": setup,
        }
        control = CONTROL_LUA.replace("__CONFIG_JSON__", json.dumps(json.dumps(payload)))
        (scenario_dir / "control.lua").write_text(control)
        command = [
            str(factorio), "--config", str(config_path), "--mod-directory", str(mod_dir),
            "--start-server-load-scenario", scenario_name, "--until-tick", str(final_tick + 1),
            "--server-settings", str(server_settings_path),
            "--console-log", str(scratch_path / "factorio.log"),
        ]
        raw_path = write_dir / "script-output" / "capture-raw.json"
        process = subprocess.Popen(
            command,
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        raw_capture = None
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if raw_path.exists():
                try:
                    raw_capture = json.loads(raw_path.read_text())
                    break
                except json.JSONDecodeError:
                    pass
            if process.poll() is not None:
                break
            time.sleep(0.05)
        if raw_capture is not None and process.poll() is None:
            process.send_signal(signal.SIGINT)
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            stdout, stderr = process.communicate(timeout=10)
        if raw_capture is None:
            log = (scratch_path / "factorio.log").read_text(errors="replace") if (scratch_path / "factorio.log").exists() else ""
            raise RuntimeError(
                f"Factorio trial failed ({process.returncode})\n{stdout[-2000:]}\n"
                f"{stderr[-2000:]}\n{log[-5000:]}")
        capture = raw_capture
        capture["environment"] = {
            "game_executable": str(factorio), "game_version": "2.0.77", "build": 84539,
            "platform": platform.machine() + "-" + platform.system().lower(),
            "mods": [{"name": "base", "version": "2.0.77"}],
            "recipe_data_sha256": scenario["recipe_data"]["sha256"],
            "isolated_write_directory": True, "isolated_mod_directory": True,
            "runner_termination": "SIGINT after complete capture file",
        }
        capture = seal_document(capture, "capture_hash")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    blueprints = sub.add_parser("blueprints", help="write the analysis and exact trial blueprint strings")
    blueprints.add_argument("--analysis-out", type=Path, required=True)
    blueprints.add_argument("--trial-out", type=Path)
    draft = sub.add_parser("draft", help="write the measured-case page draft and host policy")
    draft.add_argument("--graph", type=Path, required=True)
    draft.add_argument("--draft-out", type=Path, required=True)
    draft.add_argument("--policy-out", type=Path, required=True)
    prepare = sub.add_parser("prepare", help="seal the operating scenario around a routing request")
    prepare.add_argument("--request", type=Path, required=True)
    prepare.add_argument("--inference", type=Path)
    prepare.add_argument("--out", type=Path, required=True)
    run = sub.add_parser("run", help="run isolated Factorio repeats and write v3 captures")
    run.add_argument("--factorio", type=Path, default=DEFAULT_FACTORIO)
    run.add_argument("--scenario", type=Path, required=True)
    run.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "blueprints":
        args.analysis_out.write_text(analysis_blueprint() + "\n")
        if args.trial_out:
            args.trial_out.write_text(trial_blueprint() + "\n")
        return 0
    if args.command == "draft":
        graph = json.loads(args.graph.read_text())
        args.draft_out.write_text(json.dumps(build_assignment_draft(graph), indent=2, sort_keys=True) + "\n")
        args.policy_out.write_text(json.dumps(build_host_policy(), indent=2, sort_keys=True) + "\n")
        return 0
    if args.command == "prepare":
        request = json.loads(args.request.read_text())
        inference = json.loads(args.inference.read_text()) if args.inference else None
        scenario = build_scenario(request, inference)
        validate_operating_scenario(scenario)
        args.out.write_text(json.dumps(scenario, indent=2, sort_keys=True) + "\n")
        return 0
    scenario = validate_operating_scenario(json.loads(args.scenario.read_text()))
    if not args.factorio.is_file():
        parser.error(f"Factorio executable not found: {args.factorio}")
    for index in range(1, scenario["measurement"]["repeat_runs"] + 1):
        run_id = f"run-{index}"
        out_path = args.out_dir / f"{scenario['scenario_id']}-{run_id}.json"
        run_trial(args.factorio, scenario, run_id, out_path)
        print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
