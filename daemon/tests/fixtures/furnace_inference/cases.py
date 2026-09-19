"""Synthetic, hand-checkable furnace inference cases for task 19."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from factoribot.blueprint_contract import (
    AssignmentSet,
    Budget,
    Capacity,
    EndpointId,
    EntityId,
    Feed,
    FurnaceAssignment,
    Material,
    SCHEMA_VERSION,
)


_PLAN_CASES = Path(__file__).resolve().parents[1] / "routing_plan" / "cases.py"
_spec = importlib.util.spec_from_file_location("task19_routing_plan_cases", _PLAN_CASES)
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

PATH = tuple(base.PATH)
ALL_SMELTING = ("copper-plate", "iron-plate", "steel-plate", "stone-brick")
RECIPES = {
    "copper-plate": (("copper-ore", 1.0), ("copper-plate", 1.0)),
    "iron-plate": (("iron-ore", 1.0), ("iron-plate", 1.0)),
    "steel-plate": (("iron-plate", 5.0), ("steel-plate", 1.0)),
    "stone-brick": (("stone", 2.0), ("stone-brick", 1.0)),
    "smelt-a": (("item-a", 1.0), ("item-b", 1.0)),
    "smelt-b": (("item-b", 1.0), ("item-a", 1.0)),
}


def eid(number: int) -> EntityId:
    return EntityId(PATH, number)


def endpoint(number: int, name: str, kind: str = "inventory") -> EndpointId:
    return EndpointId(eid(number), kind, name)


def material(name: str) -> Material:
    return Material("item", name, "normal")


def budget(name: str, item: str, capacity: float = 100.0) -> Budget:
    return Budget(name, material(item), Capacity("finite", capacity))


def assignments(graph, feeds=(), furnaces=()) -> AssignmentSet:
    return AssignmentSet(
        SCHEMA_VERSION,
        graph.blueprint_hash,
        graph.graph_hash,
        tuple(feeds),
        tuple(furnaces),
        (),
    )


def feed(name: str, budget_name: str, target: EndpointId) -> Feed:
    return Feed(name, budget_name, target, Capacity("unlimited", None))


def add_furnace(layout, number: int, x: float, recipes=ALL_SMELTING):
    layout.entity(number, "electric-furnace", x, 0, candidates=recipes)
    incoming = layout.inventory(number, "input", x, 0)
    outgoing = layout.inventory(number, "output", x, 0)
    time_group = layout.group(f"furnace_{number}_time", 1, "machine_time")
    for name in recipes:
        ingredient, product = RECIPES[name]
        layout.activity(
            f"furnace_{number}_{name}",
            number,
            name,
            [(incoming, ingredient[0], ingredient[1])],
            [(outgoing, product[0], product[1])],
            1,
            time_group,
        )
    return endpoint(number, "input"), endpoint(number, "output")


def iron_steel_chain():
    layout = base.Layout("task19_iron_steel_chain")
    input_one, output_one = add_furnace(layout, 1, 0)
    input_two, _ = add_furnace(layout, 2, 3)
    layout.arc("plate_to_steel", base.ep(1, "output", "inventory"),
               base.ep(2, "input", "inventory"), layout.transfer())
    graph = layout.finish()
    ore = budget("ore", "iron-ore")
    return graph, assignments(graph, [feed("ore_feed", "ore", input_one)]), (ore,)


def stone_brick():
    layout = base.Layout("task19_stone_brick")
    incoming, _ = add_furnace(layout, 1, 0)
    graph = layout.finish()
    stone = budget("stone", "stone")
    return graph, assignments(graph, [feed("stone_feed", "stone", incoming)]), (stone,)


def mixed_ores():
    layout = base.Layout("task19_mixed_ores")
    incoming, _ = add_furnace(layout, 1, 0)
    graph = layout.finish()
    values = (budget("copper", "copper-ore"), budget("iron", "iron-ore"))
    feeds = (feed("copper_feed", "copper", incoming), feed("iron_feed", "iron", incoming))
    return graph, assignments(graph, feeds), values


def no_source():
    layout = base.Layout("task19_no_source")
    add_furnace(layout, 1, 0)
    graph = layout.finish()
    return graph, assignments(graph), ()


def conditional_source():
    layout = base.Layout("task19_conditional_source")
    layout.entity(1, "transport-belt", -2, 0, subsystem="transport")
    source = layout.port(1, "source", -1.5, 0, "bidirectional")
    incoming, _ = add_furnace(layout, 2, 0)
    layout.arc("conditional_feed", source, base.ep(2, "input", "inventory"),
               layout.transfer(), semantics="conditional", conditions=("gate",))
    graph = layout.finish()
    ore = budget("ore", "iron-ore")
    return graph, assignments(graph, [feed("ore_feed", "ore", endpoint(1, "source", "port"))]), (ore,)


def unknown_bridge():
    layout = base.Layout("task19_unknown_bridge")
    layout.entity(1, "transport-belt", -2, 0, subsystem="transport")
    source = layout.port(1, "source", -1.5, 0, "bidirectional")
    incoming, _ = add_furnace(layout, 2, 0)
    layout.entity(3, "mystery-loader", -1, 0, support="unsupported", subsystem="transport")
    layout.gap("mystery_bridge", [3], [source, base.ep(2, "input", "inventory")])
    graph = layout.finish()
    ore = budget("ore", "iron-ore")
    return graph, assignments(graph, [feed("ore_feed", "ore", endpoint(1, "source", "port"))]), (ore,)


def disconnected_cycle():
    layout = base.Layout("task19_disconnected_cycle")
    in_one, out_one = add_furnace(layout, 1, 0, ("smelt-a",))
    in_two, out_two = add_furnace(layout, 2, 3, ("smelt-b",))
    layout.arc("a_to_b", base.ep(1, "output", "inventory"),
               base.ep(2, "input", "inventory"), layout.transfer())
    layout.arc("b_to_a", base.ep(2, "output", "inventory"),
               base.ep(1, "input", "inventory"), layout.transfer())
    graph = layout.finish()
    return graph, assignments(graph), ()


def conflicting_override():
    graph, base_assignments, budgets = mixed_ores()
    # Retain only the confirmed copper feed, then explicitly select iron plates.
    explicit = FurnaceAssignment(eid(1), "iron-plate")
    value = AssignmentSet(
        base_assignments.schema_version,
        graph.blueprint_hash,
        graph.graph_hash,
        (base_assignments.feeds[0],),
        (explicit,),
        (),
    )
    return graph, value, (budgets[0],)


CASES = {
    "iron_steel_chain": iron_steel_chain,
    "stone_brick": stone_brick,
    "mixed_ores": mixed_ores,
    "no_source": no_source,
    "conditional_source": conditional_source,
    "unknown_bridge": unknown_bridge,
    "disconnected_cycle": disconnected_cycle,
    "conflicting_override": conflicting_override,
}
