# Task 02 handoff — versioned transport prototypes and fixture evidence

## 1. Identity

- Task: 02, *Supply versioned transport prototypes and fixture evidence*.
- Starting snapshot: HEAD `0b0f3da6499fcea21e100fec494c54e7dc979b01` plus the
  pre-existing uncommitted working tree (planner, plan schema, MCP adapter,
  skill, task 00 contract, task 01 calculation fixes). All prerequisites were
  verified present in this checkout: `blueprint_contract.py`, `findings.py`,
  `planner.py`, `plan_spec.py`, `mcp_server.py`, `.agents/skills/factoribot/`,
  and `docs/blueprint-routing-contract.md`.
- Contract read: `docs/blueprint-routing-contract.md`, whose module already
  reports `SCHEMA_VERSION = "1.1.0"` and
  `MECHANICS_PROFILE = "base-2.0.76-normal-v1"` (the task 00 amendment landed
  while this task ran). Only `canonical_json` and `content_hash` are imported
  from it — public, stable functions — so a further contract revision cannot
  reshape this extract.
- Model: Claude Opus 5 (`claude-opus-5[1m]`).
- Nothing was committed, stashed or reset.

## 2. What changed

Owned and new:

- `daemon/factoribot/transport_prototypes.py` — the prototype adapter: extract,
  provenance, manifest and mechanics-observation records.
- `daemon/tests/test_transport_prototypes.py` — 40 tests, 38 of which run with
  no dump present.
- `daemon/tests/fixtures/routing_prototypes/` — `README.md`, `generate.py`,
  `raw_prototype_slice.json`, `prototypes.json`, `manifest.json`,
  `pilot_coverage.json` (172 KB total).
- `daemon/tests/fixtures/routing_mechanics_observations/` — `README.md`,
  `CAPTURE.md`, `manifest.json`, and 16 records under `records/` (68 KB).
- This handoff.

Owned and additive (no signature or behaviour change):

- `daemon/factoribot/gamedata.py` — `BELT_ITEMS_PER_SPEED` (public alias for the
  existing private 480 constant, so the adapter does not fork the belt-speed
  convention) and `read_dump(path) -> (resolved_path, sha256, raw)`, which
  reuses the MCP loader's file-bytes SHA identity.
- `daemon/factoribot/model.py` — **unchanged.** The extract is self-describing
  and versioned; folding prototype geometry into `Database` would have coupled
  the routing schema to the legacy solver model for no gain. Say so if a later
  task wants it there instead.

Files owned by other agents (`blueprint_contract.py`, `findings.py`,
`blueprint.py`, `blueprint_plan.py`, `blueprint_view.py`, transport algorithms,
`tools.py`, `mcp_server.py`, `cli.py`, skills) were not touched.

### Proposed shared edits (not applied)

1. **`mcp_server.load_toolbox` could reuse `gamedata.read_dump`.** It currently
   inlines `path.read_bytes()` + `hashlib.sha256(...)`. The new helper returns
   exactly that triple. One-line change, identical behaviour, and it removes the
   risk of two SHA conventions drifting. Integration owner's call.
2. **Task 00 / task 03 per-entity subsystem classification.** The extract
   already supplies what the amended contract needs: every prototype record
   carries its raw `prototype_type` plus a derived `subsystem` from
   `{transport, inserter, production, power, rail, fluid, logistics, circuit,
   unknown}`, and `subsystem_for(prototype_type)` classifies any type — anything
   unmapped is explicitly `unknown`. No contract import is needed in either
   direction; task 03 can call `subsystem_for` or read the field.
3. **Declared-mods policy.** `Provenance` refuses to claim a profile match or an
   identified environment without both a known build and an explicit mod list.
   If the amended contract names those request fields differently, only the
   manifest's `environment` block needs renaming.

## 3. Commands run and results

```sh
.venv/bin/python daemon/tests/fixtures/routing_prototypes/generate.py
.venv/bin/python daemon/tests/fixtures/routing_prototypes/generate.py --from-slice
.venv/bin/python -m pytest daemon/tests/test_transport_prototypes.py -q
FACTORIBOT_DATA=/nonexistent/data-raw-dump.json \
  .venv/bin/python -m pytest daemon/tests/test_transport_prototypes.py -q -rs
make test
```

- Generator, both forms: the `--from-slice` run reproduced all four artifacts
  **byte-identically** (`diff -r` against a copy taken before the run).
- Focused suite with the dump present: **40 passed**.
- Focused suite with the dump made unreachable: **38 passed, 2 skipped** — the
  only skips are the two tests that exist to cross-check the pinned slice and
  the recorded SHA against the full dump. Offline CI is therefore covered.
- `make test`: **240 passed** (the suite has grown from the 143 in the starting
  snapshot as other agents' work landed).
- One earlier `make test` run showed a single failure in
  **`daemon/tests/test_blueprint_plan.py::test_large_layout_model_size_and_timing`**
  (`n_rows` 9601 vs expected 9600). That file is task 05's, not mine; I did not
  touch it. The immediately following rerun passed with 240 tests, so it looks
  like a mid-edit snapshot rather than a standing failure. Flagging it by file
  name as instructed.
- No new dependency, no network service, no MCP registration, no game
  modification, no running server reloaded.

Reproducible fixtures:

- `daemon/tests/fixtures/routing_prototypes/prototypes.json` — the extract
  (content hash `sha256:756af0da…`, 20 prototypes, 14 supported).
- `daemon/tests/fixtures/routing_prototypes/raw_prototype_slice.json` — verbatim
  slice (content hash `sha256:297274bf…`).
- `daemon/tests/fixtures/routing_prototypes/manifest.json` — source dump
  `data/data-raw-dump.json`, file SHA-256
  `42d6dd2f8b39e22123651d3de22fbd8e0f991b50ee40eace1ce54330df83de87`.
- `daemon/tests/fixtures/routing_prototypes/pilot_coverage.json`.
- `daemon/tests/fixtures/routing_mechanics_observations/` — 16 records + index.

## 4. Concrete before/after

**Underground reach.** A plausible wrong implementation reads the raw
`max_distance` (5 / 7 / 9) and calls it the reach — or subtracts one and calls
*that* the reach. Both look right in a synthetic test, and both silently change
which of the pilot's 178 fast underground belts pair with which.

What the sources actually say: the 2.0.76 `UndergroundBeltPrototype` page gives
`max_distance` a type (`uint8`) and **no description**; the wiki's underground
belt page says "4 squares" for the basic tier only and never states whether that
is the gap or the centre-to-centre separation. Basic tier `max_distance` is 5, so
the two readings differ by exactly one tile and the documentation does not
choose between them.

So the extract records:

```json
"max_distance": 7,                              // raw, verbatim
"underground_span_tiles": {
  "value": null,
  "evidence_status": "pending",
  "evidence_ref": "underground.pairing.range"
}
```

and `records/underground.pairing.range.json` states the blocking gate and the
capture that would close it (`CAPTURE.md` 4.5). A downstream task cannot get a
number here without first producing an observation, and
`test_unknown_engine_semantics_stay_null_and_pending` fails if anyone fills it
in anyway.

**Absent field, not a default.** `bulk` is defined only on `bulk-inserter`.

```python
extract.by_name("bulk-inserter").raw_field("bulk")   # True
extract.by_name("fast-inserter").raw_field("bulk")   # PrototypeError: recorded as absent
extract.by_name("fast-inserter").derived["is_bulk"].value   # None, status "pending"
```

The documented default (`false`) is *not* asserted, because this build's
prototype does not state it. The same holds for `hand_size`,
`stack_size_bonus`, `max_belt_stack_size` and `tile_width`/`tile_height`.

**Hand-checkable numbers that are known.** `fast-transport-belt` speed
`0.0625 tiles/tick × 480 = 30 items/s` across both lanes, 15 per lane — derived
from the documented formula, cross-checked against the wiki physics page's
per-lane table (15 items/s, fast belt) *and* against the existing
`gamedata.build_database().belts` table, which must agree because both use the
same constant. Splitter footprint 2×1 and AM2 3×3 come from `ceil` of the
collision box, which the 2.0.76 `EntityPrototype` page documents as the
`tile_width`/`tile_height` default; neither prototype defines them.

## 5. Assumptions, unsupported mechanics, unmet gates

**The mechanics gate is UNMET, and the fixtures say so.** No controlled game
capture was run: this session had no Factorio installation and no disposable
save. `records/` holds 16 rules — 6 `documented-only`, 10 `pending`, **0
`observed`** — and `manifest.json` carries `mechanics_gate_unmet: true`. The
schema refuses an `observed` record that lacks a setup blueprint, measurement,
interval, method, identified build, mod list and named disposable save; a test
asserts the current state is unobserved. No observation was invented.

**The prototype environment is unidentified.** A `data-raw-dump.json` carries no
build number and no mod manifest, so `game_version` is `null`, `declared_mods`
is `null`, `environment_status` is `unidentified`, `matches_target_profile` is
`unknown`, and every prototype's `origin` is `unknown`. Concretely: **this dump
defines 142 prototypes whose names begin with `ee-`, including the
`ee-super-substation` the pilot uses.** That is consistent with an enabled
Editor Extensions mod, but nothing in the dump names or versions a mod, so the
extract is **not** certified as `base-2.0.76-normal-v1`. (Contrary to the
coordinator's note, the modded pole *is* present in this dump; its geometry is
therefore recorded from the dump rather than guessed, while its origin stays
unknown and its support stays `unsupported`.) Corroborating what *is* visible:
the only quality prototypes are `normal` and `quality-unknown`, the only planet
is `nauvis`, and there are no space-platform or elevated-rail prototypes.

**Pilot facts (recorded, not inferred).** `daemon/tests/fixtures/wip_science.txt`,
file SHA-256 `e48fa3fa…55f49a`, encoded version 562949958402048 = 2.0.76.0,
2771 entities: 1738 fast-transport-belt, 608 bulk-inserter, 178
fast-underground-belt, 153 assembling-machine-2, 76 electric-furnace, 15
fast-splitter, 3 ee-super-substation. Exactly the contract's counts, verified by
decoding the checked-in file in the test rather than by trusting the fixture.
2 wire entries, 0 tiles, no label. Unavailable: external feeds and their rates,
exports and their removal services, input budgets, research levels, enabled mods
and build for the originating save, power availability, circuit control state,
and the 76 furnaces' recipes (they carry no `recipe` field). None of these is
inferred anywhere.

**Deliberate non-implementation.** No belt, underground, splitter, inserter,
power or beacon mechanics are implemented here, and no recipe arithmetic:
`crafts_per_second_at_speed_1` is null because that belongs to the shared
calculation layer. Pole supply/wire distances and the beacon profile curve are
retained as `unsupported` data so tasks 11/12 need no second extraction pass;
retaining them implies no mechanics.

**Documentation caveat.** Six rules rest on version-pinned 2.0.76 prototype
documentation plus wiki pages retrieved 2026-09-08. Of the wiki pages, only
*Inserters* states a version bound (valid up to 2.0.77); *Transport
belts/Physics* and *Underground belt* carry none. Rules resting on unversioned
wiki text alone are `pending`, not `documented-only`.

## 6. Adapter API and what can start next

```python
from factoribot.transport_prototypes import (
    load_pinned_extract,          # -> PrototypeExtract, offline, no dump needed
    PrototypeExtract, Prototype, Derived, Provenance, Reference, Box,
    subsystem_for,                # raw prototype type -> subsystem hint
    FIRST_ENTITY_SET, RETAINED_UNSUPPORTED, SUBSYSTEMS, SUPPORT_LEVELS,
    REQUIRED_MECHANICS_RULES, EVIDENCE_STATUSES,
    extract_prototypes, parse_extract, slice_raw_dump, raw_from_slice,
    build_manifest, verify_manifest, load_json,
    parse_observation, load_observations, build_observation_index,
    validate_observation_index,
    PROTOTYPE_FIXTURE_DIR, OBSERVATION_FIXTURE_DIR, EXTRACT_PATH, MANIFEST_PATH,
    RAW_SLICE_PATH, PILOT_COVERAGE_PATH, OBSERVATION_INDEX_PATH,
    PrototypeError,
)

extract = load_pinned_extract()
belt = extract.by_name("fast-transport-belt")
belt.raw_field("speed")                              # 0.0625 (raises if absent)
belt.derived["items_per_second_per_lane"].value      # 15.0
belt.derived["tile_width"].value                     # 1
extract.get("ee-super-substation").support           # "unsupported"
extract.supported_names()                            # the 14 first-set names
```

Each `Derived` carries `value`, `unit`, `basis`, `evidence_status` and
`evidence_ref`; `evidence_ref` resolves either to `provenance.references` or to
a mechanics rule id in `routing_mechanics_observations/`.

**Can start now:** task 03 has geometry, footprints, directions-relevant raw
vectors, subsystem hints and the pilot coverage fixture it needs to build the
spatial model and to classify unsupported entities. Task 04 has per-lane belt
capacities and the shared-resource inputs for supported topology. Task 05 can
consume the extract for machine fields. Tasks 11/12 have the pole and beacon
fields retained.

**Still required before a bound is advertised:** the game observations. Tasks
03/04 may build topology and shape, but they must not claim supported underground
pairing, splitter distribution, side-load lane assignment or any finite inserter
capacity until the corresponding record in
`daemon/tests/fixtures/routing_mechanics_observations/records/` is `observed`.
`CAPTURE.md` is the procedure; it needs a Factorio installation and a disposable
sandbox save, which this session did not have. Separately, certifying the extract
as `base-2.0.76-normal-v1` requires a dump taken from a build whose version and
enabled mod list are recorded outside the dump.
