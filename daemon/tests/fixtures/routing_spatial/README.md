# Spatial fixtures (routing task 03)

Regenerate deterministically from the repository root:

```sh
.venv/bin/python daemon/tests/fixtures/routing_spatial/generate.py
.venv/bin/python daemon/tests/fixtures/routing_spatial/generate.py --benchmark
```

`generate.py` is the only writer of these files; `daemon/tests/test_spatial.py`
re-derives both from source and fails if a checked-in artifact drifts.

## `odd_document.json` — synthetic, for round-trip and selection tests

A hand-written blueprint book. Everything in it is schema test data: it is not
a factory, not a measurement, and its label text is data, never instructions.

It deliberately contains what a reduced re-serialization would lose:

* a nested book, an empty nested book, and an unselected `upgrade_planner`;
* entry `index` values (7, 2, 4, 5) that differ from their array offsets, so a
  path built from offsets selects the wrong leaf — `[2]` and `[7]` are
  different leaves and `[7, 2]` is not `[2, 7]`;
* unfamiliar keys at book, blueprint and entity level;
* tiles, wires, schedules, filters, `use_filters`, icons, recipe quality;
* fractional (`-0.25`), negative and integer coordinates in one document;
* a non-square `fast-splitter` rotated east, a non-cardinal `curved-rail-a`
  (direction 3) and an `uncommon`-quality machine, i.e. three different reasons
  an entity is retained but unsupported;
* a leaf at `[2]` that is the leaf at `[7]` translated by (+1000, +1000), so
  translation invariance is checkable without a second hand-built layout.

## `pilot_sample.json` — compact spatial sample for task 06

Two windows cut from the pinned pilot `daemon/tests/fixtures/wip_science.txt`
(SHA-256 `e48fa3fa…55f49a`, 2771 entities): 125 entities covering all seven
prototypes the pilot uses, including the modded `ee-super-substation`.

Each row carries the contract's normalized geometry (`position`, `footprint`,
`direction`, `orientation`, `quality`), the adapter's `subsystem` / `mod` /
`support` claims and the per-entity `limitations` that travel with them.
Positions are the pilot's own; nothing is rescaled, rounded or re-centred.

What the sample does **not** contain, because no evidence supports it: lanes,
ports, connections, capacities, recipes-per-furnace, feeds or exports. The
`ee-super-substation` row is `support: unsupported`, `subsystem: power`,
`mod: unknown` — task 02's extract identifies no mod for it, and this adapter
does not name one it cannot evidence.
