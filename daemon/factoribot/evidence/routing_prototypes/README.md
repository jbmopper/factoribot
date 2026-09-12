# Pinned routing prototype extract (task 02)

Versioned Factorio prototype evidence for blueprint routing. These files let
tasks 03/04/05 and CI work offline: nothing here needs the 14 MB
`data/data-raw-dump.json`.

Adapter: `daemon/factoribot/transport_prototypes.py`.
Schema: `factoribot-routing-prototypes-1`.
Target profile: `base-2.0.76-normal-v1` (a *target*, not a verified property of
this extract -- see "What is unknown" below).

## Files

| File | What it is |
| --- | --- |
| `raw_prototype_slice.json` | Small verbatim slice of the source dump: every field the adapter reads, plus every other field whose canonical JSON is at most 400 bytes. `dropped_fields` lists, per prototype, the names of the larger fields (graphics, sounds, fluid boxes) that were left in the dump. |
| `prototypes.json` | The normalized extract: raw fields, absent fields, omitted fields, labelled derivations, subsystem hints and support levels. This is what downstream tasks read. |
| `manifest.json` | Provenance: source dump path and SHA-256, slice and extract content hashes, environment status, and the mechanics-evidence gate summary. |
| `pilot_coverage.json` | The development pilot (`../wip_science.txt`) measured against the extract: entity counts, per-name coverage, the unresolved modded pole, and what the blueprint does *not* tell us. |
| `generate.py` | Deterministic regeneration. |

## Regenerating

From the repository root:

```sh
# re-cut the slice from the full dump, then rebuild everything from the slice
.venv/bin/python daemon/factoribot/evidence/routing_prototypes/generate.py

# rebuild without a dump, reusing the dump identity already in manifest.json
.venv/bin/python daemon/factoribot/evidence/routing_prototypes/generate.py --from-slice

.venv/bin/python -m pytest daemon/tests/test_transport_prototypes.py -q
```

Both forms produce byte-identical output for the same slice. Re-cutting from a
*different* dump changes `source_dump.sha256` and every content hash; that is
the point of the manifest.

## Reading the extract

Each prototype record separates three different kinds of statement:

- `raw` -- fields copied verbatim from the dump. Read them with
  `Prototype.raw_field(name)`, which raises rather than returning a default.
- `absent_raw_fields` -- fields the 2.0.76 prototype documentation defines for
  that prototype type and which this build leaves undefined. For example no
  inserter here defines `hand_size`, `stack_size_bonus` or `max_belt_stack_size`,
  and `bulk` exists only on `bulk-inserter`. An absent field is **not** silently
  replaced by its documented default.
- `derived` -- everything this adapter computed, each with `value`, `unit`,
  `basis`, `evidence_status` and `evidence_ref`. `evidence_ref` points either at
  a declared reference in `provenance.references` or at a mechanics rule id in
  `../routing_mechanics_observations/`.

A derivation whose engine semantics are not established is `value: null` with
`evidence_status: "pending"`. There are three of them, on purpose:

- `underground_span_tiles` -- `max_distance` is 5 / 7 / 9, but neither the
  prototype documentation nor the wiki says whether that counts the tiles
  between the pair or the centre-to-centre separation. An off-by-one there
  changes which pairs connect, so nothing is guessed.
- `input_output_tile_offsets` (splitter) -- which of the two tiles carries which
  input/output lane is not stated by the prototype.
- `items_per_second` (inserter) -- cycle time depends on swing geometry, source
  and destination, and inserter-capacity research. The contract keeps inserter
  capacity unknown and relaxes it; it does not bound it.

`crafts_per_second_at_speed_1` is also null: recipe arithmetic belongs to the
shared calculation layer (task 01), not to this adapter.

## Subsystem hints and support

Every prototype carries its raw `prototype_type` and a derived `subsystem` hint
from `{transport, inserter, production, power, rail, fluid, logistics, circuit,
unknown}`, for the contract's per-entity classification of unsupported entities.
`unknown` is a real answer, not a fallback to be papered over.

`support` is `supported` only for the frozen first entity set (three belt tiers,
three underground tiers, three splitter tiers, inserter / fast-inserter /
bulk-inserter, assembling-machine-2, electric-furnace). Poles and the beacon are
retained as `unsupported` so the later power/beacon adapters need no second
extraction pass; retaining their fields implies no mechanics.

## What is unknown

The manifest records `environment_status: "unidentified"` and
`matches_target_profile: "unknown"`, and every prototype's `origin` is
`"unknown"`. That is not laziness:

- A `data-raw-dump.json` contains no build number and no mod manifest. The
  blueprint format version does not identify the prototype environment either.
- This dump defines 142 prototypes whose names begin with `ee-`, including the
  `ee-super-substation` the pilot uses. That is consistent with an enabled
  Editor Extensions mod, but the dump names and versions no mod, so the extract
  is **not** certified as `base-2.0.76-normal-v1`.
- It does look like a base-only-plus-mods environment in one respect: its only
  quality prototypes are `normal` and `quality-unknown`, its only planet is
  `nauvis`, and it defines no space platform or elevated rail prototypes.

`verify_manifest` refuses any manifest that claims a profile match or an
identified environment without a known build *and* an explicit mod list.

## Hash conventions

- `source_dump.sha256` is the SHA-256 of the dump file's bytes -- the identity
  the MCP adapter already records for loaded game data.
- `raw_slice.content_hash` and `extract.content_hash` are `sha256:`-prefixed
  canonical-JSON content hashes of the *decoded* documents, the routing
  contract's `factoribot-json-v1` convention. They are stable under
  reformatting; the file-bytes digest is not.

The two are deliberately named apart because they hash different things.
