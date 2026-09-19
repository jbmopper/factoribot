# 19 — Feed-driven furnace inference and replay

Read `docs/blueprint-routing-prompts/WORKING-RULES.md`, the repository's applicable
instructions and Factoribot skill, `docs/blueprint-routing-deterministic-roadmap.md`,
and this prompt before editing. Work on this assignment only. Starting code was
`ab25b2a`; inspect the actual checkout and record HEAD plus any relevant dirty
files. The revised roadmap and these prompts may be uncommitted: ensure they are
present in your checkout. Do not reset, stash or bulk-clean another worker's files.
Do not launch additional agents or paid model calls. No browser-upload service,
layout optimizer, live-save modification or dependency-wide upgrade is requested.

Keep numerical work deterministic. Preserve explicit supply/removal assumptions,
shared capacities, identity checks and the distinction between optimistic upper
bounds, predicted operating rates and measured game results. Do not promote
synthetic test data to game evidence. Use existing contracts unless the task
explicitly requires a coordinated versioned change.

Return the common handoff, including exact commands/results, owned files,
remaining blockers, and one concrete before/after or counterexample. Write it to
the task-specific handoff path below. Implementation tasks run focused tests and
`make test`; document missing external environments instead of inventing results.

Recommended: Sol high. Core work may start once task 15's exported input contract
is fixed. Land shared integration after task 18 finishes. Coordinate ownership:
only one task may edit routing_public.py or cli.py at a time.

## Ownership

Own new `daemon/factoribot/furnace_inference.py`, dedicated inference fixtures/tests,
and `docs/blueprint-routing-handoffs/19-feed-driven-furnace-inference.md`.
After task 18 lands, own the small CLI/public integration and matching documented
capability update. Read task 10's original inference requirements as well as the
revised roadmap. Do not change inserter timing or the throughput solver.

## Implement

From declared feeds, existing assembler recipes, the loaded recipe database and
supported connectivity, compute possible material sets using a bounded fixed-point
procedure. Derive furnace candidates from crafting categories and compatible
ingredients. Infer only when sufficient evidence leaves exactly one recipe;
record entity identity, supporting sources/path, inputs and assumptions.
Reachability is not a prediction of item rate or the furnace's runtime selection.

Unknown upstream items, conditional paths and unsupported possible bridges must
not establish absence of an ingredient. Retain ambiguity and group actionable
manual overrides instead of asking for every furnace. Explicit user assignments
take precedence; report conflicts without silently replacing them. A disconnected
cycle cannot bootstrap its own recipe/material evidence.

Provide a deterministic preparatory CLI inference pass if candidate expansion
changes graph identity. Rebuild final graph, retain explicit declarations,
validate inferred overrides and seal against that identity. Recompute on changed
feeds/prototypes; do not bypass stale checks by editing hashes. Keep inference
provenance separate from explicit assignments, using an additive host artifact or
an explicitly documented versioned contract extension if necessary.

## Acceptance

Cover iron ore → plate → steel, stone → brick with correct ingredient quantities,
chained furnaces, mixed ores, no source declaration, conditional source, unknown
bridge, disconnected recipe cycle, conflicting override, changed feed and bounded
termination. Compare inference plus its recorded assignment with the equivalent
manual request under identical assumptions. Exercise the public CLI and replay
through fresh MCP where appropriate. Show the pilot's remaining ambiguous groups
without inventing its supplies. Run focused/full tests and update capability
wording only for supported, demonstrated inference; game-evidence gaps stay explicit.
