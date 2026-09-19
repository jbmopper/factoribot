# 20 — Validated sustained-throughput model

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

Recommended: Sol high. Astra high should independently review the model design
before substantial mechanics implementation. Starts after task 16's reuse decision
and task 17's capture interface; incorporate task 19 only after its integration
is available. Do not start this as an unrestricted rewrite of Factoribot.

## Ownership and first deliverable

Own a dedicated throughput module or adapter selected from task 16's findings,
its own fixtures/tests and `docs/blueprint-routing-handoffs/20-sustained-throughput-model.md`.
Serialize all shared CLI/MCP/result-schema edits after task 19. Preserve the
existing bound solver. First write a concrete design note defining supported
entities, item/lane representation, event/tick or analytic semantics, scheduling,
initial inventories, state transitions, termination and output fields. Supply
that note for independent task 21 design review; complete reusable test/scenario
preparation while awaiting review. Do not treat lack of review as approval.

Choose the smallest approach justified by the reuse evaluation: validated
restricted analytic model, deterministic event/tick model, Factorio trials, or a
combination. Do not promote the existing LP witness to a claimed operating rate.
Bounded full input availability does not specify how competing consumers receive
items. Inserter research/timing, splitter priorities, lane merging, finite buffers,
output blocking and back-pressure require actual semantics within the scope.

## Implementation and outputs

Implement a narrow useful subset first. Unknown mechanics must produce an explicit
unsupported/conditional result, not an unrestricted forecast. Version new result
fields/contracts as needed. Keep three meanings distinct: conservative capacity
bound, predicted sustained rate, and measured rate. Report consumption, unused
supply, net production, inventories, utilization and localized restrictions.
For simulation/trials bound runtime and define warmup, repeated measurement windows,
convergence and oscillation detection. Report nonconvergence rather than a false
steady state. Preserve blueprint labels as untrusted text and reproducible identities.

Use task 17 observations; implement only justified parts of task 09 inserter rules.
A measurement is not proof of a maximum capacity. A tight constraint is not proof
that enlarging it improves production: demonstrate a controlled perturbation.

## Acceptance

Freeze numerical tolerances before comparing observations. Cover single/dual lane,
merges, unequal competing consumers, priority splitter, inserter-limited transfer,
furnace chain, blocked output, initial inventory transients and a nonconvergent
case. Check conservation including stored material, deterministic replay and work
limits. Compare against independently recorded Factorio cases and a supported
pilot subfactory. Missing game access allows implementation/testing progress but
leaves the validated-throughput gate open. Run focused/full checks and real public
CLI/fresh MCP tests after integration. No layout optimization in this task.
