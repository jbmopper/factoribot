# 18 — Integrate input drafts with CLI analysis

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

Recommended: Terra high. Starts after task 15's code, draft example and handoff
are available in this checkout. This is the single shared-integration owner.

## Ownership

Own `daemon/factoribot/routing_public.py`, routing commands in
`daemon/factoribot/cli.py`, dedicated integration tests and
`docs/blueprint-routing-handoffs/18-input-cli-integration.md`.
Update routing documentation to match implemented behavior. Change the viewer
only after its task 15 owner has finished and only for round-trip defects.
Do not change solver mathematics or graph contracts in this assignment.

## Implement and verify the complete loop

Consume task 15's actual draft, not a separately invented schema. Ensure its
input items, whole-belt/per-lane capacities, shared budgets and existing assembler
recipes survive CLI request sealing and analysis. The host template currently
wins over proposed_request keys: make collisions explicit so a player's page
changes cannot be silently ignored. Keep a clearly documented precedence rule
and structured actionable errors for conflicting declarations; preserve existing
valid request callers where possible.

Create a minimal documented host-policy template for assumptions/protection/detail
that can take budgets and exports from the page. Do not invent power, research,
mods or output-removal facts; clearly label any illustrative assumptions. Show
exact commands for blueprint file → page → exported draft → sealed request →
analysis JSON + regenerated page. Browser upload stays deferred.

Check assignment import restores proposed budgets and edits after regeneration.
A user-designated full belt declares a maximum external supply; a blocked factory
must not be made feasible through implicit sinks or forced consumption. Preserve
provenance, book path, prototype/graph identity, stale-result rejection and
unsupported-entity refusal.

## Acceptance

Run task 15's small browser-exported draft through the real CLI. Check one lane,
two same-item lanes, different lane items, repeated edits, shared budgets, an
explicit host/page conflict, changed graph identity and blocked output. Save
small reproducible fixtures with expected declarations and independent capacity
checks. Exercise direct Python plus fresh stdio MCP replay of a valid sealed
request, preserving provenance; do not claim the user's connected server was
reloaded. Run focused and full tests. Update the current-work record to mark only
actually satisfied milestone-1 acceptance as complete.
