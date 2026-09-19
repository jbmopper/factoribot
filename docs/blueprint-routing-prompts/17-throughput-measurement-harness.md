# 17 — Controlled throughput measurement harness

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

Recommended: Terra medium; raise to high if game integration is complex.
Starts immediately, independent of tasks 15 and 16.

## Ownership

Own `experiments/routing-measurements/`, a new
`daemon/tests/test_routing_measurement_harness.py` if needed, and
`docs/blueprint-routing-handoffs/17-throughput-measurement-harness.md`.
Do not edit the solver, viewer, CLI registrations or existing evidence manifests.
Return observation bundles for a later integration owner to review/promote.

## Build the smallest useful harness

Read the existing mechanics CAPTURE.md and observation schema under
`daemon/factoribot/evidence/`. Inspect existing repository game launch/export
facilities first; do not create a competing daemon or reinvent existing transport.
Check whether a compatible Factorio executable and an isolated test environment
are actually available. Never touch the player's existing saves. Create and name
any disposable test save explicitly; do not alter global mod configuration.
If task 16 supplies a reusable trial runner, adapt through a small interface;
do not assume it exists or wait idle on its recommendation.

Define versioned scenarios and capture records containing exact executable/game
version, mods, research, power/control state, blueprint, supply/removal conditions,
initial inventories, warmup, start/end ticks, counts and retained inventories.
Full supply is available capacity, not forced intake. Use countable collection or
counters before removal; deleted sink items cannot be counted by final inventory.
Bound runtime, repeat runs, and detect nonconvergence/oscillation rather than
quietly averaging it into a claimed steady-state rate.

Start with three small scenarios: a saturated straight belt with one- and two-lane
variants; an inserter transfer with fixed research and endpoint types; and a
blocked-output case. Record raw observations and calculate rates from counts and
ticks, not screenshots or an LLM. Keep the runner extensible to splitters/furnaces.

## Acceptance and blocked-environment behavior

Demonstrate deterministic parsing, units, interval validation, conservation
accounting including inventory changes, and rejection of incomplete records.
Synthetic data tests the recorder only and must remain labelled synthetic.
When game access exists, run the scenarios twice in the isolated environment and
retain reproducible results. Do not mark any mechanics rule observed automatically.
When game access is absent, finish the runnable harness, sample scenario files,
validation tests and exact operator commands; state which measurements remain
unexecuted and the precise missing prerequisite. Do not install/download a game
or change the user's live environment to work around that blocker.

Clean up processes and disposable scratch files you created; retain the requested
scenario/capture artifacts. Report focused/full tests for implementation changes.
