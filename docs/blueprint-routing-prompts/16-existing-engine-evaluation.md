# 16 — Evaluate existing deterministic analyzers for reuse

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

Recommended: Sol high. Starts immediately, independent of tasks 15 and 17.

## Ownership

Own `experiments/routing-reuse/` and
`docs/blueprint-routing-handoffs/16-existing-engine-evaluation.md` only.
Do not modify production code, project dependencies or other agents' fixtures.
Use isolated temporary environments for external dependencies, record upstream
commit/package versions, and remove only the scratch files you created. Retain
small reproducible scripts, results and necessary fixtures; not cloned repos or
large generated data in the main checkout.

## Evaluate, do not rebuild

Inspect primary upstream code/docs for:
- https://github.com/Tomansion/factorio_blueprint_analyser
- https://github.com/Tomansion/factorio_blueprint_analyser_app
- https://github.com/CharacterOverflow/factorio-analytics

Determine supported Factorio versions, blueprint parsing, custom prototype data,
license, maintained interfaces, furnace support and modeling of belt lanes,
splitters, priorities, inserters and blocked outputs. Actually execute the closest
static analyzer locally where practical; do not call documentation claims a test.
Do not upload the user's blueprint to a third-party hosted demo.

Build a small comparison corpus: straight belt/one lane, unequal competing
consumers, splitter priority, lane merge, inserter-limited transfer, furnace chain,
and blocked output. State independently justified expectations and distinguish
mathematical reference cases from observed Factorio rates. Attempt the pilot
locally only after the small cases, recording crashes and unsupported entities.
Do not fix or delete those entities merely to obtain a successful result.

Compare the outputs with Factoribot's current conservative model where comparable.
Record invalid flow, duplicated capacity, unsupported assumptions and false
precision, not just whether each command returns successfully. Check whether the
web dashboard can save useful UI work even if its engine is unsuitable.

## Deliver decision

Provide a compact reuse/adapt/reject matrix for parser, UI, inference, flow engine
and game-trial harness. Support it with exact revisions, commands, results,
licenses and concrete failure cases. Recommend the smallest credible architecture
for task 20: restricted analytic model, deterministic event/tick model, engine-run
trials, or a justified combination. State what cannot yet be decided without game
access. Do not implement the replacement engine in this task.

Run checks for your own harness; a documentation-only conclusion does not require
rerunning the whole repository suite. Finish with interfaces and validation cases
that task 20 and task 17 can consume without depending on undocumented assumptions.
