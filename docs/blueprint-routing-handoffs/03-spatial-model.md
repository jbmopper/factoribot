# Task 03 handoff — preserve blueprints and index individual entities

## 1. Identity

- Task: 03, *Preserve blueprints and index individual entities*
  (`docs/blueprint-routing-prompts/03-spatial-model.md`).
- Starting snapshot: HEAD `0b0f3da6499fcea21e100fec494c54e7dc979b01` plus the
  pre-existing uncommitted working tree. Prerequisites verified present in this
  checkout before starting: `blueprint_contract.py` + `findings.py` reporting
  `SCHEMA_VERSION = "1.1.1"` and `MECHANICS_PROFILE = "base-2.0.76-normal-v1"`
  (task 00), `transport_prototypes.py` with
  `daemon/tests/fixtures/routing_prototypes/` and
  `daemon/tests/fixtures/routing_mechanics_observations/` (task 02),
  `blueprint_plan.py` / `routing_lp.py` (task 05), the pilot
  `daemon/tests/fixtures/wip_science.txt`, and both prior handoffs.
- Contract version read in full: **1.1.1** (`docs/blueprint-routing-contract.md`).
- Model: Claude Opus 5 (`claude-opus-5[1m]`).
- Nothing committed, stashed, reset or cleaned. No game, save, server or public
  surface was touched.

## 2. What changed

Owned and new:

- `daemon/factoribot/spatial.py` — the spatial model: normalization, index,
  queries, contract-`Entity` emission.
- `daemon/tests/test_spatial.py` — 50 tests.
- `daemon/tests/fixtures/routing_spatial/` — `README.md`, `generate.py`,
  `odd_document.json` (synthetic round-trip/selection fixture),
  `pilot_sample.json` (the compact spatial sample for task 06). 104 KB total.
- This handoff.

Owned and strictly additive (`git diff --numstat` on the file: **330 added, 0
removed**; no existing signature or behaviour changed):

- `daemon/factoribot/blueprint.py` — `BlueprintDecodeError` (a `BlueprintError`
  subclass carrying `code` and `detail`), `DecodeLimits`, `decode_blueprint`,
  `encode_blueprint`, `walk_entries`, `BookEntry`, `parse_selection_path`,
  `select_blueprint`, `blueprint_leaves`.

`summarize_blueprint`, `decode_blueprint_string`, `iter_blueprints`,
`find_blueprint_string`, `_parse_modules`, `MachineGroup` and
`BlueprintSummary` are untouched, and `daemon/tests/test_blueprint.py` was not
edited at all. `test_spatial.py` adds
`test_new_decoder_agrees_with_the_legacy_entry_point`, which asserts the two
decoders return equal documents for the pilot.

No file owned by another task was opened for writing: `blueprint_contract.py`,
`findings.py`, `transport_prototypes.py`, `gamedata.py`, `model.py`,
`blueprint_plan.py`, `routing_lp.py`, `blueprint_view.py`, `tools.py`,
`mcp_server.py`, `cli.py` and the skills are unchanged.

### Proposed shared edits (described, not applied)

1. **`decode_blueprint_string` is still unbounded.** It is the entry point used
   by `tools.py` / `cli.py`, and it inflates the whole payload before looking at
   it, so a zip bomb pasted into chat expands in full. The one-line fix is to
   delegate: `return decode_blueprint(s, DEFAULT_LIMITS)`. Behaviour is
   identical for every valid input and for garbage (the new errors are
   `BlueprintError` subclasses); only oversized input changes, from "expands"
   to "structured error". I did not apply it because it is a behaviour change
   to an existing public path — integration owner's call (task 07/13).
2. **Contract, if anyone wants it.** Nothing is required of `blueprint_contract.py`.
   `Entity`'s free-form `mod` string already expresses the pilot's situation
   (see §5); no schema change is proposed.

## 3. Commands run and results

```sh
.venv/bin/python daemon/tests/fixtures/routing_spatial/generate.py
.venv/bin/python daemon/tests/fixtures/routing_spatial/generate.py --benchmark
.venv/bin/python -m pytest daemon/tests/test_spatial.py -q
.venv/bin/python -m pytest daemon/tests/test_spatial.py daemon/tests/test_blueprint.py \
    daemon/tests/test_bpanalyze.py daemon/tests/test_transport_prototypes.py -q
make test
```

- Focused spatial suite: **50 passed**.
- Legacy + prototype suites alongside it: **108 passed** (nothing regressed in
  `test_blueprint.py` or `test_bpanalyze.py`).
- `make test`: **330 passed, 0 failed, 0 skipped** (277 in the starting
  snapshot; the delta is my 50 plus 3 that landed from another agent while this
  ran). No failure in any other task's file, so nothing to report by file name
  and no rerun was needed.
- `generate.py` run twice: both artifacts reproduced byte-identically
  (`sha256:25105b7f127d…`, `sha256:88254f70cd25…`), and
  `test_checked_in_fixtures_match_their_generator` re-derives both from source
  on every test run.
- No test is skipped and no dependency is missing. `load_pinned_extract()` reads
  the checked-in extract, so nothing here needs `data-raw-dump.json`; the suite
  runs offline. No model call is used anywhere in this code or its tests.
- Temporary files: none left. `pyflakes` was installed into `.venv` to lint the
  four files (clean) and then uninstalled, restoring the environment.

### Pilot benchmark (`generate.py --benchmark`)

Pinned pilot `daemon/tests/fixtures/wip_science.txt`, file SHA-256
`e48fa3fa…55f49a`, **2771 entities**, single leaf, path `[]`. Python 3.14,
darwin, medians of three runs, `time.perf_counter`:

| Step | Elapsed | Per item |
| --- | --- | --- |
| `decode_blueprint` (string → document) | 3.4 ms | — |
| `build_spatial_view` (index construction) | 33 ms | 12 µs/entity |
| `neighbors()` for all 2771 entities | 7.1 ms | 2.5 µs |
| `inserter_targets()` (608 inserters) | 3.0 ms | 4.9 µs |
| `contract_entities()` (2771 contract records) | 129 ms | 47 µs |
| `blueprint_hash()` (`content_hash` of the document) | 47 ms | — |

Memory method: **`tracemalloc`**, started immediately before a second
`build_spatial_view` on the same document and stopped after it, reporting
`get_traced_memory()`. Timing and memory are measured in *separate* runs
because tracing every allocation inflates the build to ~167 ms. Peak traced
allocation for the index over the pilot: **3.60 MiB** (current 3.39 MiB), on top
of the decoded document, which the index references rather than copies.

Contract §"Detail scope" says performance limits need these measurements before
public enforcement. Measured at the provisional ceiling itself — a synthetic
10 000-entity belt grid — the index costs **123 ms and 10.1 MiB traced peak**,
so the 10 000-entity limit is comfortable and no lower one is needed on this
evidence. `contract_entities()` is the expensive step (canonical JSON per
entity), so a public tool should emit contract records for the entities it
actually returns, not for the whole graph.

## 4. Concrete before/after and a counterexample

**Before/after — bounding decompression at the right moment.** The legacy path
is `zlib.decompress(base64.b64decode(body))`: a 40 MB run of zeros compresses to
about 39 KB, and decoding it allocates the full 40 MB before anything can
measure it. `decode_blueprint` drives `zlib.decompressobj().decompress(data,
max_length)` in a loop and stops at the ceiling.
`test_decompression_limit_is_enforced_during_decompression` builds exactly that
bomb, decodes it with a 1 MB ceiling, and asserts both the
`decompressed_limit` error **and** a `tracemalloc` peak under 8 MiB — measured
1.56 MiB, in 0.3 ms. A "check `len(raw)` afterwards" implementation fails that assertion at
~40 MiB while still raising the same error, which is the point of measuring
memory rather than only the exception.

**Counterexample that matters for task 04 — inserter rotation sense.** The
prototype states `pickup_position [0, -1]` and `insert_position [0, 1.2]` in the
entity's own north frame, and the engine rotates them by the entity direction.
The extract records both as `documented-only`; the rotation *sense* is not
stated. Under the opposite (counter-clockwise) convention the two tiles are the
same two tiles — they only exchange roles. On the pilot **all 608 inserters have
a supported entity on both candidate tiles under either convention**, splitting
380 / 228 between the two role orders, with the counts merely swapping. So the
layout's own geometry cannot validate the convention, and a "it looks right on
the pilot" argument would silently reverse the direction of material flow for
every inserter in the factory. `spatial.ROTATION_SENSE_UNVALIDATED` is attached
to every `InserterCandidates`, `candidate_tiles` / `candidate_entities` expose
the role-free pair, and
`test_every_pilot_inserter_has_both_candidate_tiles_occupied` pins the 380/228
split so the fact is visible rather than folded into a claim.

**Before/after — book paths.** `odd_document.json` has entries with `index`
values 7, 2, 4, 5 in that array order. Selecting by array offset returns the
wrong leaf: offset 0 is index 7. `select_blueprint(doc, [2])` returns the
"translated twin", `[7]` the fractional leaf, `[4, 0]` the leaf under the nested
book, and `[0]` raises `unknown_selection_path`. Entities in different leaves at
identical coordinates stay distinct (`bp/7/e/1` vs `bp/2/e/1` vs `bp/4/0/e/1`).

## 5. How the `ee-super-substation` mod claim was handled

The coordinator asked for the mod claim to come from task 02's provenance, which
records `origin: "unknown"` for **every** prototype: a `data-raw-dump.json`
carries no mod manifest, so the extract is explicitly `environment_status:
unidentified`. The contract says `subsystem`/`mod` are adapter claims recorded
from extracts and never inferred from names, so this adapter does **not** write
`EditorExtensions`, even though the contract's pilot narrative anticipates that
name and 142 `ee-` prototypes in the dump are consistent with it. The name is
not in the evidence; only the prototype's own definition is.

What it emits for the pilot's three poles:

```
support   "unsupported"      (extract: not in the frozen first entity set)
subsystem "power"            (extract's per-prototype hint)
mod       "unknown"          (extract: origin unknown; no mod named)
```

plus the per-entity limitation `unidentified_mod_origin` and a view-level note
"mod origin unidentified for: ee-super-substation".

`mod` is `base` **only** for prototypes in `FIRST_ENTITY_SET`. That is not an
inference from the dump: the contract's own mechanics table names those fourteen
prototypes as the base-game first profile, and `Entity._validate` requires a
`supported` entity to be `base`. Every other prototype — including
`small-electric-pole`, `substation` and `beacon`, which are certainly base-game
— keeps `unknown`, because this checkout has no evidence that says so. If an
entity would otherwise be `supported` but its mod is not `base`, the adapter
downgrades it to `unsupported` rather than inventing an origin.

This is analysable rather than a dead end, and I verified it against the
contract in this checkout by taking task 00's `declared_power.json`, rewriting
the entity's mod to `unknown` and the request's declaration to a mod literally
named `unknown` (version `unknown`, `provides: ["power"]`,
`alters_item_mechanics: false`) with the existing `power_assumed_available`
irrelevance declaration:

- `validate_request` accepts it and `unresolved_reasons` returns `()` — bounds
  may be advertised.
- `declared_assumptions` becomes
  `('mod:unknown:unknown', 'irrelevant:modded_power:power:power_assumed_available')`,
  which is an honest audit line: *an unidentified mod provides these power
  prototypes, and the request assumes power is available*.
- Dropping the declaration is rejected with `undeclared mod prototype:
  ee-super-substation from unknown`; keeping the mod but dropping the
  irrelevance declaration yields `unsupported entity: bp/2/7/e/3` and withholds
  every bound. Both are the contract's intended failures.

`PrototypeGeometry(declared_origins={...})` is the seam for closing this: an
integrator holding a real mod manifest passes `{"ee-super-substation":
"EditorExtensions"}` and the claim changes with the evidence, without this
module ever guessing. Nothing in the repository currently supplies such a
manifest.

## 6. API for task 04 (transport graph)

```python
from factoribot.blueprint import (
    DecodeLimits, BlueprintDecodeError, decode_blueprint, encode_blueprint,
    walk_entries, blueprint_leaves, select_blueprint, parse_selection_path, BookEntry,
)
from factoribot.spatial import (
    SpatialError, SpatialLimits, PrototypeGeometry, SpatialEntity, SpatialIndex,
    SpatialView, InserterCandidates, ROTATION_SENSE_UNVALIDATED,
    build_spatial_view, load_spatial_view, index_blueprint, normalize_entity,
)

view  = load_spatial_view(open("daemon/tests/fixtures/wip_science.txt").read())
index = view.index()                      # or view.index([2, 7]) for a book leaf
```

`SpatialView` — the preservation boundary. `document` is the entire decoded
root (unknown metadata, tiles, wires, unselected leaves and planners included);
`selected_paths` / `unselected_paths` are contract book paths;
`indexes[path]`; `entities()`; `contract_entities()`; `blueprint_hash()`
(`content_hash` of the document, the value a `SpatialGraph.blueprint_hash`
needs); `encode()`; `limitations`.

`SpatialIndex` — one leaf, never merged with another:

| Call | Returns |
| --- | --- |
| `index.entities`, `iter(index)`, `len(index)` | stable document order |
| `by_entity_number(n)` / `by_id(EntityId)` | one `SpatialEntity`, else `SpatialError("unknown_entity")` |
| `by_prototype(name)`, `prototype_counts()` | grouping helpers |
| `occupants(x, y)` / `covering(Point)` | entities whose footprint covers that tile |
| `entities_in_box(Box)` | entities overlapping a region |
| `neighbors(target, distance=1, diagonal=False)` | the local ring only |
| `inserter_candidates(target)` → `InserterCandidates` | geometric pickup/drop candidates |
| `inserter_targets()` | the same for every `subsystem == "inserter"` entity |
| `bounding_box()`, `contract_entities()` | — |

`target` may be a `SpatialEntity`, an `EntityId` or an entity number.

`SpatialEntity` — `id` (contract `EntityId`), `prototype`, `position`,
`footprint` (contract `Point`/`Box`), `direction`, `orientation`, `quality`,
`support`, `subsystem`, `mod`, `geometry_source`, `limitations`, `record` (the
**original** entity dict, as a read-only mapping — filters, `type`, recipe,
quality and unknown keys are all still there), `tiles()`, and
`to_contract_entity(evidence_ids=(), furnace_candidates=())`, which builds the
contract record through `blueprint_contract.Entity` itself. There is no parallel
wire schema here: geometry uses the contract's own `Point`/`Box`/`EntityId`, and
`SpatialEntity` is an index node, not a second serialization format.

Structured errors: `BlueprintDecodeError.code` ∈ {`empty_input`,
`encoded_limit`, `invalid_base64`, `invalid_deflate`, `truncated_stream`,
`decompressed_limit`, `invalid_utf8`, `invalid_json`, `invalid_document`,
`nesting_limit`, `malformed_book`, `duplicate_book_index`,
`malformed_selection_path`, `unknown_selection_path`, `not_a_blueprint`};
`SpatialError.code` ∈ {`invalid_entity`, `invalid_entity_number`,
`invalid_position`, `invalid_direction`, `invalid_orientation`,
`invalid_quality`, `duplicate_entity_id`, `entity_limit`, `footprint_limit`,
`query_limit`, `invalid_query`, `unknown_entity`, `unknown_selection_path`,
`not_an_inserter`, `no_geometry`}. Both carry a `detail` dict.

Limits (`DecodeLimits`, `SpatialLimits`, all overridable): 16 MiB encoded, 32 MiB
decompressed (contract's provisional figure, enforced *during* inflation), 64
levels of nesting, 10 000 entities per leaf (contract's provisional figure),
4096 tiles per entity footprint, 1 000 000 tiles per region query. Every one is
checked from the span or the declared size *before* the corresponding
allocation.

**Why there is no all-pairs scan.** The index holds a tile → entities map;
`neighbors` builds only the requested ring and consults that map.
`test_queries_do_not_scan_all_pairs` wraps `_tiles` in a counting dict and
asserts that the same query performs exactly 4 tile lookups on a 400-entity grid
and on a 10 000-entity grid.

## 7. Sample for task 06

`daemon/tests/fixtures/routing_spatial/pilot_sample.json` (76 KB, schema
`factoribot-spatial-sample-1`): two windows cut from the pilot,
**125 entities** covering all seven prototypes it uses, including one
`ee-super-substation`. Each row carries `key` (`bp/root/e/1608`), `book_path`,
`entity_number`, `prototype`, `position`, `footprint`, `direction`,
`orientation`, `quality`, `support`, `subsystem`, `mod`, `geometry_source` and
`limitations`, plus source provenance (file SHA-256, document content hash,
selection path) and the view-level limitations. It contains no lane, port,
connection, capacity, feed or export, because none of those is established yet.
The viewer must render `label`, `description` and every prototype/mod string as
text; blueprint text is untrusted data.

## 8. Assumptions, unsupported mechanics, unmet gates

- **No transport mechanics are implemented.** No lanes, no underground pairing,
  no splitter distribution, no side-loading, no inserter rate, no recipe
  activity, no power or beacon behaviour, no viewer. Task 02's observation
  records are still 0 `observed` / 6 `documented-only` / 10 `pending`, so the
  mechanics gate remains **unmet** and nothing here may be read as a mechanics
  claim.
- **Footprints** are `tile_width` × `tile_height` from task 02's derived values
  (themselves `ceil` of the collision box, per 2.0.76 `EntityPrototype`
  documentation), centred on the entity position, with the two swapped for
  direction 4/12. Verified against the pilot: 3×3 machines and furnaces, 2×1
  splitters at half-tile centres, 2×2 substations, 1×1 belts and inserters.
  For a non-cardinal direction — unsupported by the first profile anyway — the
  square bounding box of every rotation is used, a superset, and the entity is
  flagged `bounding_footprint_for_non_cardinal_direction`.
- **Unknown prototypes stay visible**: a prototype absent from the extract keeps
  its exact position, gets a unit-tile footprint
  (`geometry_source == "assumed_unit_tile"`, limitation `assumed_unit_footprint`),
  and is classified `unknown` /
  `unsupported` with an `unknown_prototype` limitation and a view-level note.
  A unit tile can *under*-cover a large unknown entity, so a neighbour query may
  miss a contact with it — that is why such entities are never `supported` and
  why the limitation travels with them. Task 02's `subsystem_for()` maps
  prototype *types*, and a blueprint records only names, so it cannot be used
  for names the extract does not describe.
- **Quality**: anything other than `normal` is retained and forced
  `unsupported`. **Non-token prototype names** (a modded `Not-A-Token`) are
  retained in the index but cannot become contract entities; `to_contract_entity`
  raises `ContractError` there, which is the contract's rule, not a silent drop.
- **Selection**: a book entry without a nonnegative integer `index` is a
  `malformed_book` error rather than being addressed by array offset. Every
  Factorio 2.0 export writes `index`; if a real book without one turns up, that
  decision needs revisiting, and it is deliberately loud rather than silent.
- **Round-trip** is semantic, as the task specifies. `encode_blueprint` emits
  compact JSON at deflate level 9; the bytes differ from Factorio's, the decoded
  document and its `content_hash` do not.
- Unmet release gates unchanged and untouched by this task: exact-build game
  observations (task 02 `CAPTURE.md`), the real pilot's feeds/exports/mods/
  research/power/control state and the 76 furnaces' recipes, LP certificate and
  residual verification, viewer interaction checks, and public integration. No
  live save, MCP registration or server reload was involved.

## 9. Next

**Task 04 (transport graph) can start now.** It has per-entity identity,
geometry, tile occupancy, local-neighbour and inserter-candidate queries, the
`subsystem`/`mod`/`support` claims, and the original records for anything it
needs to read further. It must not turn candidates into lanes, connections or
capacities until the matching record in
`daemon/tests/fixtures/routing_mechanics_observations/records/` is `observed` —
in particular the inserter rotation sense of §4, underground pairing range, and
splitter lane behaviour. **Task 06** can consume `pilot_sample.json` now.

The prerequisite still required before any bound is advertised for the pilot is
unchanged: task 02's controlled game captures, plus a request that declares the
unidentified power mod and `power: assumed_available` as in §5.
