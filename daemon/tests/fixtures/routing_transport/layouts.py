"""Hand-placed blueprint layouts for the transport-graph acceptance cases.

Every layout here is written by hand from the entity geometry, tile by tile, and
is SYNTHETIC: it is schema and topology test input, never a game observation and
never a measurement. The *expectations* live in `daemon/tests/test_routing.py`
and are written out by hand from these coordinates; nothing in this file records
what the implementation happens to produce.

Positions follow the contract: tiles, x east, y south, absolute world
coordinates, one-tile entities centred on tile centres (`n + 0.5`). Directions
are Factorio 2.0's 16-step clockwise integers, north 0, east 4, south 8,
west 12.

Run this module to print each layout's entity table:

    .venv/bin/python daemon/tests/fixtures/routing_transport/layouts.py
"""
from __future__ import annotations

NORTH, EAST, SOUTH, WEST = 0, 4, 8, 12

BELT = "fast-transport-belt"
UNDERGROUND = "fast-underground-belt"
SPLITTER = "fast-splitter"
INSERTER = "bulk-inserter"
MACHINE = "assembling-machine-2"
FURNACE = "electric-furnace"
#: A real Factorio prototype that task 02's pinned extract does not describe, so
#: the spatial adapter classifies it `unknown` / `unsupported` with an assumed
#: unit footprint. Used for the "unsupported possible bridge" case.
UNKNOWN_PROTOTYPE = "steel-chest"
#: Classified `power` by the extract: not an item subsystem, so it is admitted
#: through a request-level irrelevance declaration, not through a topology gap.
MODDED_POLE = "ee-super-substation"


def entity(number, name, x, y, direction=EAST, **extra):
    """One raw blueprint entity record at tile centre (x, y)."""
    record = {"entity_number": number, "name": name, "position": {"x": x, "y": y}}
    if direction:
        record["direction"] = direction
    record.update(extra)
    return record


def blueprint(entities, label="SYNTHETIC transport layout"):
    return {"blueprint": {
        "item": "blueprint", "version": 562949958402048, "label": label,
        "description": "SYNTHETIC hand-placed layout. Not a game observation.",
        "entities": list(entities),
    }}


def book(leaves, label="SYNTHETIC transport book"):
    """A two-level book so book paths, not array offsets, address the leaves."""
    return {"blueprint_book": {
        "item": "blueprint-book", "active_index": 0, "label": label,
        "blueprints": [
            {"index": index, "blueprint": blueprint(entities)["blueprint"]}
            for index, entities in leaves
        ],
    }}


# ---------------------------------------------------------------------------
# Transforms (translation and supported rotation invariance)
# ---------------------------------------------------------------------------

def translate(entities, dx, dy):
    out = []
    for record in entities:
        moved = dict(record)
        moved["position"] = {"x": record["position"]["x"] + dx, "y": record["position"]["y"] + dy}
        out.append(moved)
    return out


def rotate(entities, quarter_turns=1):
    """Rotate the whole layout clockwise about the origin by 90 degrees a turn.

    A clockwise world rotation maps (x, y) -> (-y, x) with y growing south, and
    adds 4 to every entity direction. Half-tile splitter centres map onto
    half-tile centres, so the layout stays on the grid.
    """
    out = [dict(record) for record in entities]
    for _ in range(quarter_turns % 4):
        rotated = []
        for record in out:
            moved = dict(record)
            x, y = record["position"]["x"], record["position"]["y"]
            moved["position"] = {"x": -y, "y": x}
            moved["direction"] = (record.get("direction", 0) + 4) % 16
            rotated.append(moved)
        out = rotated
    return out


# ---------------------------------------------------------------------------
# Layouts
# ---------------------------------------------------------------------------

def straight_run(length=3, y=0.5, start=0, first=1, name=BELT):
    """`length` east-facing belts in a row starting at tile (start, y - 0.5)."""
    return [entity(first + i, name, start + i + 0.5, y, EAST) for i in range(length)]


def two_lane_run():
    """Three east-facing fast belts at y=0.5, tiles x=0,1,2.

    Both lanes exist independently end to end: six ports, two lanes and two
    15 items/s groups per belt.
    """
    return straight_run(3)


def turn_layout():
    """East belt at (0,0) handing over to a north belt at (1,0), which runs to (1,-1).

    The north belt has no rear feeder (its rear tile (1,1) is empty), so the
    perpendicular handover is a curve, not a side-load.
    """
    return [
        entity(1, BELT, 0.5, 0.5, EAST),
        entity(2, BELT, 1.5, 0.5, NORTH),
        entity(3, BELT, 1.5, -0.5, NORTH),
    ]


def side_load_layout():
    """A north main line with a rear feeder, side-loaded from the west.

    Belts 1 and 2 run north up column x=1 (tiles y=1 then y=0), so belt 2 has a
    rear feeder. Belt 3 faces east at (0,0) and pushes into belt 2's west face:
    a side-load, whose near lane is belt 2's left lane (facing north, left is
    west).
    """
    return [
        entity(1, BELT, 1.5, 1.5, NORTH),
        entity(2, BELT, 1.5, 0.5, NORTH),
        entity(3, BELT, 0.5, 0.5, EAST),
    ]


def splitter_layout(filters=True):
    """One east-facing fast splitter fed by two belts and feeding two belts.

    A splitter is two tiles wide across its movement direction. Facing east at
    centre (1.5, 1.0) it covers tiles (1, 0) and (1, 1); looking east, the left
    half is the north tile (1, 0) and the right half the south tile (1, 1).
    """
    splitter = entity(3, SPLITTER, 1.5, 1.0, EAST)
    if filters:
        splitter["filter"] = "iron-plate"
        splitter["output_priority"] = "left"
    return [
        entity(1, BELT, 0.5, 0.5, EAST),
        entity(2, BELT, 0.5, 1.5, EAST),
        splitter,
        entity(4, BELT, 2.5, 0.5, EAST),
        entity(5, BELT, 2.5, 1.5, EAST),
    ]


def underground_layout(separation=4, extra_exit_at=None, intervening_at=None):
    """An east-facing underground entrance at tile 0 and an exit `separation` east.

    `extra_exit_at` adds a second candidate exit further along the same ray;
    `intervening_at` adds another same-tier entrance between the two, which the
    engine is *expected* to capture the pairing with -- `underground.pairing.conflict`
    is pending, so both readings stay available.
    """
    out = [
        entity(1, UNDERGROUND, 0.5, 0.5, EAST, type="input"),
        entity(2, UNDERGROUND, separation + 0.5, 0.5, EAST, type="output"),
    ]
    if intervening_at is not None:
        out.append(entity(3, UNDERGROUND, intervening_at + 0.5, 0.5, EAST, type="input"))
    if extra_exit_at is not None:
        out.append(entity(4, UNDERGROUND, extra_exit_at + 0.5, 0.5, EAST, type="output"))
    return out


def belt_into_underground(exit_first=False):
    """A belt handing over into an underground endpoint directly ahead of it.

    With `exit_first` the belt pushes into the *exit* of a tunnel, whose rear
    face is the tunnel mouth rather than a belt entrance. No primary document
    states whether that hands over, so it must stay conditional rather than being
    silently allowed or silently dropped.
    """
    kind = "output" if exit_first else "input"
    return [
        entity(1, BELT, 0.5, 0.5, EAST),
        entity(2, UNDERGROUND, 1.5, 0.5, EAST, type=kind),
        entity(3, UNDERGROUND, 5.5, 0.5, EAST, type="output" if not exit_first else "input"),
    ]


def machine_with_fluid_recipe():
    """An assembling machine whose recipe involves a fluid, which v1 cannot model."""
    return [entity(1, MACHINE, 1.5, 1.5, NORTH, recipe="plastic-bar")]


def inserter_between_belts(control=False, filters=()):
    """A north-facing inserter at (1,1) between two east-facing belts.

    Facing north, the prototype's pickup offset (0, -1) lands on tile (1, 0) and
    the drop offset (0, 1.2) on tile (1, 2). Which of those two is the pickup is
    exactly what `inserter.endpoints.pickup_drop_tiles` leaves open, so both
    belts must stay reachable in both roles.
    """
    inserter = entity(3, INSERTER, 1.5, 1.5, NORTH)
    if control:
        inserter["control_behavior"] = {
            "circuit_enable_disable": True,
            "circuit_condition": {"first_signal": {"type": "item", "name": "iron-plate"},
                                  "constant": 0, "comparator": ">"},
        }
    if filters:
        inserter["use_filters"] = True
        inserter["filters"] = [{"index": i + 1, "name": name} for i, name in enumerate(filters)]
    return [
        entity(1, BELT, 1.5, 0.5, EAST),
        entity(2, BELT, 1.5, 2.5, EAST),
        inserter,
    ]


def machine_chain(recipe="iron-gear-wheel", supply=True, drain=True):
    """A 3x3 machine at (1,1)..(3,3) with optional supplying and draining inserters.

    The machine centre is (2.5, 2.5) so its footprint covers tiles x,y in 1..3.
    The supply inserter faces north at (2, 0): its two candidate tiles are
    (2, -1) -- a belt -- and (2, 1) -- the machine. The drain inserter faces
    north at (2, 4) with candidate tiles (2, 3) -- the machine -- and (2, 5) --
    a belt.
    """
    out = [entity(1, MACHINE, 2.5, 2.5, NORTH, recipe=recipe)]
    if supply:
        out += [entity(2, BELT, 2.5, -0.5, EAST), entity(3, INSERTER, 2.5, 0.5, NORTH)]
    if drain:
        out += [entity(4, INSERTER, 2.5, 4.5, NORTH), entity(5, BELT, 2.5, 5.5, EAST)]
    return out


def direct_insertion():
    """Two machines with one inserter reaching an inventory on both candidate tiles."""
    return [
        entity(1, MACHINE, 1.5, 1.5, NORTH, recipe="iron-gear-wheel"),
        entity(2, INSERTER, 1.5, 3.5, NORTH),
        entity(3, MACHINE, 1.5, 5.5, NORTH, recipe="electronic-circuit"),
    ]


def unsupported_bridge():
    """Two belt runs separated by one tile holding a prototype the extract lacks.

    Nothing here proves the chest bridges the two runs and nothing proves it does
    not, so it must stay a `may_connect: true` topology gap.
    """
    return [
        entity(1, BELT, 0.5, 0.5, EAST),
        entity(2, UNKNOWN_PROTOTYPE, 1.5, 0.5, 0),
        entity(3, BELT, 2.5, 0.5, EAST),
    ]


def modded_pole_beside_belt():
    """A belt run beside a modded power pole: a non-item subsystem, so no gap."""
    return straight_run(3) + [entity(4, MODDED_POLE, 1.5, 2.5, 0)]


LAYOUTS = {
    "two_lane_run": two_lane_run,
    "turn": turn_layout,
    "side_load": side_load_layout,
    "filtered_splitter": splitter_layout,
    "underground": underground_layout,
    "inserter_between_belts": inserter_between_belts,
    "machine_chain": machine_chain,
    "direct_insertion": direct_insertion,
    "unsupported_bridge": unsupported_bridge,
    "modded_pole_beside_belt": modded_pole_beside_belt,
    "belt_into_underground": belt_into_underground,
    "machine_with_fluid_recipe": machine_with_fluid_recipe,
}


def main():
    for name, factory in LAYOUTS.items():
        print(f"== {name}")
        for record in factory():
            print("  ", record)


if __name__ == "__main__":
    main()
