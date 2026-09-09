# 03 — Preserve blueprints and index individual entities

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 00 and 02.
Read their contract/adapters, `blueprint.py`, and blueprint tests.

Own additive decode/encode and selection changes in `blueprint.py`, new
`spatial.py`, spatial/round-trip tests, and task-specific fixture files. Preserve
the legacy aggregate entry point. Do not implement transport rules or a viewer.

Keep the entire decoded document as the preservation boundary. Analysis views
reference original records without rebuilding the document from reduced fields.
Select nested books explicitly using the agreed path and retain unselected entries,
unknown fields, tiles, schedules, wires, tags, filters, quality, and metadata.
Preserve coordinate precision and distinguish orientation from discrete direction.

Build an indexed per-entity spatial view using validated prototype geometry. It
must resolve local neighbors and inserter target candidates without all-pairs
scanning. Unknown geometry stays visible with an explicit limitation. Reject
duplicate entity IDs within one blueprint, invalid positions, and malformed
selection paths with structured errors.

Bound encoded input, decompressed bytes, nesting, entities, and analysis work.
Enforce the decompression limit during decompression, not after an unbounded
allocation. Preserve clear behavior for supported raw JSON and encoded strings.

Acceptance: semantic decode/encode/decode equality preserves all fields, including
nested books and deliberately unfamiliar keys; byte-for-byte compressed equality
is not required. Cover noninteger coordinates, supported rotations/translations,
non-square footprints, malformed input, decompression limits, and deterministic
identity. Benchmark index construction and queries on the pinned pilot, reporting
entity count, elapsed time, and measurement method for memory. Provide a compact
spatial sample for 06 and the entity/lookup APIs for 04. Clean temporary outputs.
