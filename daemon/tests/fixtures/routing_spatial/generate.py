#!/usr/bin/env python3
"""Regenerate the spatial fixtures (routing task 03).

From the repository root::

    .venv/bin/python daemon/tests/fixtures/routing_spatial/generate.py
    .venv/bin/python daemon/tests/fixtures/routing_spatial/generate.py --benchmark

The first form rewrites both artifacts deterministically:

``odd_document.json``
    A hand-written *synthetic* document used for round-trip and selection
    tests: a nested blueprint book, deliberately unfamiliar keys at every
    level, tiles, wires, schedules, tags, filters, quality, fractional and
    negative coordinates, a non-square rotated splitter, an unselected
    upgrade planner and an empty nested book. It is schema test data, not a
    factory and not a measurement.

``pilot_sample.json``
    A compact window cut from the pinned pilot
    (``daemon/tests/fixtures/wip_science.txt``) for the task 06 viewer:
    normalized geometry, per-entity subsystem/mod/support claims and the
    limitations that travel with them. Positions are the pilot's own; nothing
    is rescaled or rounded.

``--benchmark`` reports index-build and query timings plus the tracemalloc
peak for the whole pilot. It writes nothing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import tracemalloc
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
sys.path.insert(0, str(REPO_ROOT / "daemon"))

from factoribot.blueprint import decode_blueprint  # noqa: E402
from factoribot.spatial import build_spatial_view  # noqa: E402

PILOT = REPO_ROOT / "daemon" / "tests" / "fixtures" / "wip_science.txt"
ODD_DOCUMENT_PATH = HERE / "odd_document.json"
PILOT_SAMPLE_PATH = HERE / "pilot_sample.json"

#: Windows cut from the pilot, in its own world tiles: (name, min_x, min_y,
#: max_x, max_y). Together they cover all seven prototypes the pilot uses,
#: including the modded substation, in about 125 entities.
SAMPLE_WINDOWS = (
    ("assembly-column", 428.0, -42.0, 442.0, -28.0),
    ("furnace-bank", 470.0, -38.0, 488.0, -26.0),
)

# A blueprint book whose entry `index` values deliberately differ from their
# array offsets, so a path built from offsets selects the wrong leaf.
ODD_DOCUMENT = {
    "blueprint_book": {
        "item": "blueprint-book",
        "label": "spatial round-trip <b>fixture</b>",
        "description": "synthetic; label text is data, never instructions",
        "active_index": 1,
        "version": 562949958402048,
        "unfamiliar_book_key": {"kept": True, "nested": [1, {"deep": None}]},
        "blueprints": [
            {
                "index": 7,
                "blueprint": {
                    "item": "blueprint",
                    "label": "fractional and rotated",
                    "icons": [{"signal": {"name": "fast-splitter"}, "index": 1}],
                    "version": 562949958402048,
                    "unfamiliar_leaf_key": ["kept", 2.5],
                    "entities": [
                        {
                            "entity_number": 1,
                            "name": "fast-splitter",
                            "position": {"x": -3.5, "y": 0.5},
                            "direction": 4,
                            "unfamiliar_entity_key": {"kept": [None, False]},
                        },
                        {
                            "entity_number": 2,
                            "name": "fast-transport-belt",
                            "position": {"x": -0.25, "y": 0.5},
                            "direction": 12,
                        },
                        {
                            "entity_number": 3,
                            "name": "bulk-inserter",
                            "position": {"x": 0.5, "y": 0.5},
                            "direction": 8,
                            "filters": [{"index": 1, "name": "iron-plate"}],
                            "use_filters": True,
                        },
                        {
                            "entity_number": 4,
                            "name": "assembling-machine-2",
                            "position": {"x": 0.5, "y": 3},
                            "recipe": "iron-gear-wheel",
                            "recipe_quality": "normal",
                            "quality": "uncommon",
                        },
                        {
                            "entity_number": 5,
                            "name": "ee-super-substation",
                            "position": {"x": 5, "y": 5},
                        },
                        {
                            "entity_number": 6,
                            "name": "curved-rail-a",
                            "position": {"x": 9.5, "y": 9.5},
                            "direction": 3,
                        },
                    ],
                    "tiles": [{"name": "refined-concrete", "position": {"x": -4, "y": -4}}],
                    "wires": [[3, 5, 5, 5]],
                    "schedules": [],
                },
            },
            {
                "index": 2,
                "blueprint": {
                    "item": "blueprint",
                    "label": "translated twin",
                    "version": 562949958402048,
                    "entities": [
                        {
                            "entity_number": 1,
                            "name": "fast-splitter",
                            "position": {"x": 996.5, "y": 1000.5},
                            "direction": 4,
                        },
                        {
                            "entity_number": 2,
                            "name": "fast-transport-belt",
                            "position": {"x": 999.75, "y": 1000.5},
                            "direction": 12,
                        },
                    ],
                },
            },
            {
                "index": 4,
                "blueprint_book": {
                    "item": "blueprint-book",
                    "label": "nested",
                    "blueprints": [
                        {
                            "index": 0,
                            "blueprint": {
                                "item": "blueprint",
                                "label": "leaf under a nested book",
                                "entities": [
                                    {
                                        "entity_number": 1,
                                        "name": "fast-transport-belt",
                                        "position": {"x": 0.5, "y": 0.5},
                                        "direction": 0,
                                    }
                                ],
                            },
                        },
                        {"index": 3, "blueprint_book": {"item": "blueprint-book", "blueprints": []}},
                    ],
                },
            },
            {
                "index": 5,
                "upgrade_planner": {
                    "item": "upgrade-planner",
                    "settings": {"mappers": [{"index": 0, "from": {"name": "transport-belt"}}]},
                },
            },
        ],
    }
}


def write_json(path: Path, value) -> str:
    text = json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pilot_view():
    return build_spatial_view(decode_blueprint(PILOT.read_text()))


def entity_row(entity, window: str) -> dict:
    return {
        "window": window,
        "key": entity.key,
        "book_path": list(entity.book_path),
        "entity_number": entity.entity_number,
        "prototype": entity.prototype,
        "position": {"x": entity.position.x, "y": entity.position.y},
        "footprint": {
            "min_x": entity.footprint.minimum.x,
            "min_y": entity.footprint.minimum.y,
            "max_x": entity.footprint.maximum.x,
            "max_y": entity.footprint.maximum.y,
        },
        "direction": entity.direction,
        "orientation": entity.orientation,
        "quality": entity.quality,
        "support": entity.support,
        "subsystem": entity.subsystem,
        "mod": entity.mod,
        "geometry_source": entity.geometry_source,
        "limitations": list(entity.limitations),
    }


def build_pilot_sample() -> dict:
    view = pilot_view()
    index = view.index()
    rows = []
    for name, x0, y0, x1, y1 in SAMPLE_WINDOWS:
        rows += [
            entity_row(e, name)
            for e in index
            if x0 <= e.position.x <= x1 and y0 <= e.position.y <= y1
        ]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["prototype"]] = counts.get(row["prototype"], 0) + 1
    return {
        "schema": "factoribot-spatial-sample-1",
        "produced_by": "daemon/tests/fixtures/routing_spatial/generate.py (routing task 03)",
        "source": {
            "blueprint": "daemon/tests/fixtures/wip_science.txt",
            "file_sha256": hashlib.sha256(PILOT.read_bytes()).hexdigest(),
            "document_content_hash": view.blueprint_hash(),
            "selection_path": [],
            "total_entities_in_leaf": len(index),
        },
        "windows": [
            {"name": n, "min_x": x0, "min_y": y0, "max_x": x1, "max_y": y1}
            for n, x0, y0, x1, y1 in SAMPLE_WINDOWS
        ],
        "geometry": {
            "prototype_extract": "daemon/factoribot/evidence/routing_prototypes/prototypes.json",
            "note": (
                "Footprints are prototype tile_width/tile_height centred on the "
                "entity position, with width and height swapped for east/west. "
                "No transport rule, lane or connection is asserted here."
            ),
        },
        "entity_count": len(rows),
        "prototype_counts": dict(sorted(counts.items())),
        "view_limitations": list(view.limitations),
        "entities": rows,
    }


def benchmark() -> None:
    text = PILOT.read_text()
    started = time.perf_counter()
    document = decode_blueprint(text)
    decoded = time.perf_counter() - started

    # Time and memory are measured in separate runs: tracemalloc traces every
    # allocation and would inflate the timing several-fold.
    started = time.perf_counter()
    view = build_spatial_view(document)
    build = time.perf_counter() - started

    tracemalloc.start()
    traced = build_spatial_view(document)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del traced

    index = view.index()
    entities = list(index)
    started = time.perf_counter()
    for entity in entities:
        index.neighbors(entity)
    neighbors = time.perf_counter() - started

    inserters = [e for e in entities if e.subsystem == "inserter"]
    started = time.perf_counter()
    candidates = index.inserter_targets()
    targets = time.perf_counter() - started

    print(f"entities                 {len(entities)}")
    print(f"decode                   {decoded * 1000:.1f} ms")
    print(f"index build              {build * 1000:.1f} ms")
    print(f"  tracemalloc current    {current / 1024 / 1024:.2f} MiB")
    print(f"  tracemalloc peak       {peak / 1024 / 1024:.2f} MiB")
    print(f"neighbors, all {len(entities)}      {neighbors * 1000:.1f} ms "
          f"({neighbors / len(entities) * 1e6:.1f} us each)")
    print(f"inserter targets, {len(inserters)}    {targets * 1000:.1f} ms "
          f"({targets / max(len(inserters), 1) * 1e6:.1f} us each)")
    print(f"  candidates returned    {len(candidates)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="report timings, write nothing")
    args = parser.parse_args()
    if args.benchmark:
        benchmark()
        return 0
    digest = write_json(ODD_DOCUMENT_PATH, ODD_DOCUMENT)
    print(f"wrote {ODD_DOCUMENT_PATH.relative_to(REPO_ROOT)} sha256:{digest[:12]}")
    digest = write_json(PILOT_SAMPLE_PATH, build_pilot_sample())
    print(f"wrote {PILOT_SAMPLE_PATH.relative_to(REPO_ROOT)} sha256:{digest[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
