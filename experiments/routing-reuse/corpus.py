"""Small synthetic blueprint corpus for task 16.

These layouts are mathematical reference cases, not recorded Factorio evidence.
They intentionally use only the legacy names understood by the upstream static
analyser, except where a case is specifically testing unsupported entities.
"""

from __future__ import annotations

import copy


LEGACY_BLUEPRINT_VERSION = 281479275544576


def entity(number: int, name: str, x: float, y: float, **extra):
    value = {
        "entity_number": number,
        "name": name,
        "position": {"x": x, "y": y},
    }
    value.update(extra)
    return value


def blueprint(label: str, entities: list[dict]):
    return {
        "blueprint": {
            "entities": entities,
            "item": "blueprint",
            "label": label,
            "version": LEGACY_BLUEPRINT_VERSION,
        }
    }


def competing_consumers(label: str, output_priority: str | None = None):
    splitter = entity(4, "splitter", 3, 2, direction=2)
    if output_priority is not None:
        splitter["output_priority"] = output_priority

    return blueprint(
        label,
        [
            entity(1, "wooden-chest", 0, 2),
            entity(2, "inserter", 1, 2, direction=6),
            entity(3, "transport-belt", 2, 2, direction=2),
            splitter,
            # North output: iron gear wheel, requiring 2 iron per output.
            entity(5, "transport-belt", 4, 1, direction=2),
            entity(6, "fast-inserter", 5, 1, direction=6),
            entity(7, "assembling-machine-2", 7, 1, recipe="iron-gear-wheel"),
            entity(8, "fast-inserter", 9, 1, direction=6),
            entity(9, "wooden-chest", 10, 1),
            # South output: pipe, requiring 1 iron per output.
            entity(10, "transport-belt", 4, 2, direction=4),
            entity(11, "transport-belt", 4, 3, direction=4),
            entity(12, "transport-belt", 4, 4, direction=4),
            entity(13, "transport-belt", 4, 5, direction=2),
            entity(14, "fast-inserter", 5, 5, direction=6),
            entity(15, "assembling-machine-2", 7, 5, recipe="pipe"),
            entity(16, "fast-inserter", 9, 5, direction=6),
            entity(17, "wooden-chest", 10, 5),
        ],
    )


CASES = {
    "straight_one_lane": {
        "blueprint": blueprint(
            "straight-one-lane",
            [
                entity(1, "transport-belt", 0, 0, direction=2),
                entity(2, "transport-belt", 1, 0, direction=2),
                entity(3, "transport-belt", 2, 0, direction=2),
            ],
        ),
        "expectation": (
            "With one explicitly supplied yellow-belt lane, the declared source "
            "capacity is 7.5 item/s; the other lane is distinct and empty."
        ),
    },
    "lane_merge": {
        "blueprint": blueprint(
            "lane-merge",
            [
                entity(1, "transport-belt", 0, 1, direction=2),
                entity(2, "transport-belt", 1, 0, direction=4),
                entity(3, "transport-belt", 1, 1, direction=2),
                entity(4, "transport-belt", 2, 1, direction=2),
            ],
        ),
        "expectation": (
            "A side-load and straight feed have lane-specific occupancy. Total "
            "yellow-belt capacity is 15 item/s, 7.5 item/s per lane."
        ),
    },
    "inserter_limited_transfer": {
        "blueprint": blueprint(
            "inserter-limited-transfer",
            [
                entity(1, "transport-belt", 0, 0, direction=2),
                entity(2, "inserter", 1, 0, direction=6),
                entity(3, "assembling-machine-2", 3, 0, recipe="iron-gear-wheel"),
                entity(4, "inserter", 5, 0, direction=6),
            ],
        ),
        "expectation": (
            "Under the analyser's own 0.84 item/s inserter approximation and the "
            "2 iron -> 1 gear recipe, the mathematical reference is 0.42 gear/s. "
            "This is not an observed Factorio rate."
        ),
    },
    "blocked_output": {
        "blueprint": blueprint(
            "blocked-output",
            [
                entity(1, "transport-belt", 0, 0, direction=2),
                entity(2, "fast-inserter", 1, 0, direction=6),
                entity(3, "assembling-machine-2", 3, 0, recipe="iron-gear-wheel"),
                entity(4, "fast-inserter", 5, 0, direction=6),
            ],
        ),
        "expectation": (
            "With no declared removal service, a finite output chest eventually "
            "fills and sustained net export is 0 item/s."
        ),
    },
    "unequal_competing_consumers": {
        "blueprint": competing_consumers("unequal-competing-consumers"),
        "expectation": (
            "The 0.84 item/s source feeds an unprioritized splitter with both "
            "outputs open. An ideal alternating split gives 0.42 iron/s per branch: "
            "0.21 gear/s north and 0.42 pipe/s south. This is a mathematical "
            "reference, not a recorded game result."
        ),
    },
    "splitter_priority_right": {
        "blueprint": competing_consumers("splitter-priority-right", "right"),
        "expectation": (
            "The right-priority output should be served before the other branch; "
            "the exact north/south mapping must be validated in-game before use as "
            "a mechanics oracle. The analyser must at minimum react to changing "
            "the blueprint priority field."
        ),
    },
    "furnace_chain": {
        "blueprint": blueprint(
            "furnace-chain",
            [
                entity(1, "wooden-chest", 0, 0),
                entity(2, "fast-inserter", 1, 0, direction=6),
                entity(3, "electric-furnace", 3, 0),
                entity(4, "fast-inserter", 5, 0, direction=6),
                entity(5, "transport-belt", 6, 0, direction=2),
                entity(6, "fast-inserter", 7, 0, direction=6),
                entity(7, "electric-furnace", 9, 0),
                entity(8, "fast-inserter", 11, 0, direction=6),
                entity(9, "wooden-chest", 12, 0),
            ],
        ),
        "expectation": (
            "An iron ore -> iron plate -> steel plate chain requires explicit or "
            "soundly inferred furnace recipes and conservation across both stages."
        ),
    },
}


def get_cases():
    """Return a defensive copy because the upstream analyser mutates entities."""
    return copy.deepcopy(CASES)
