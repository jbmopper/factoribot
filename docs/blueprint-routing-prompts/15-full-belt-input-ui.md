# 15 — Full-belt input controls and recipe visibility

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

Recommended: Cursor Grok 4.6 high; alternative Terra high. Starts immediately.

## Ownership

Own `daemon/factoribot/blueprint_view.py`,
`daemon/factoribot/blueprint_view_assets/`, a new
`daemon/tests/test_viewer_full_inputs.py`, and
`docs/blueprint-routing-handoffs/15-full-belt-input-ui.md`.
Do not edit the CLI, MCP schemas, solver, graph builder or contract. Provide
integration requirements to task 18 in the handoff. Keep view-model additions
additive and document the draft fields you export.

## Implement

The current page hides machine recipes and exposes separate technical budget/feed
forms. Make the common case simple while retaining the advanced controls:

1. Show existing blueprint assembler recipes in selection details and on the map
   at readable zoom. Use imported recipes, not inferred guesses. A recipe not
   supported by the analysis still needs to remain visible as blueprint data.
2. Select a supported incoming boundary belt and choose Mark as input. Choose
   one item for both lanes or a separate item per lane. Default to Full supply,
   displaying capacity taken from the imported graph/prototype evidence. Do not
   hardcode belt color/rate mappings. If capacity is unavailable, explain why the
   shortcut cannot apply. Use known item choices when available; otherwise offer
   a clearly labelled internal-item-name field with validation.
3. Generate deterministic budget/feed IDs and valid existing contract records.
   Both lanes share the total belt capacity; one lane gets only its share. A
   full input is available supply, never forced consumption. Unknown items must
   not silently become real recipes or arbitrary material sources.
4. Show assigned inputs/items on the map, allow replacement/removal, and avoid
   double-counting repeated edits. Reject outgoing/internal ports for this
   shortcut; preserve the explicit advanced interface for other declarations.
5. Default export to a draft that contains BOTH assignments and proposed budgets/
   outlets. Reimport restores edits. Changes to budgets, outputs, objective or
   overrides must invalidate displayed results, as changes to feeds already do.
6. Explain that analysis still happens through the CLI and a regenerated page.
   Do not add an HTTP service, browser blueprint upload, or in-page solver.

## Acceptance

Exercise actual browser clicks and download/import, not just HTML string tests.
Test a whole belt versus one lane, different items on two lanes, imported tiers
with different capacities, replacing/removing an input without duplicated supply,
rejection of a non-boundary selection, and safe rendering of hostile labels.
Verify an existing shared budget remains shared. Cover reimport with matching and
stale identities and budget-only/result-staleness changes. Check the real pilot's
153 existing assembler recipes remain available without manual re-entry.

Run browser smoke checks and focused/full Python checks. Include a reproducible
small blueprint and exported draft for task 18; flag any remaining integration
blocker honestly. Preserve the existing analyzer's upper-bound wording.
