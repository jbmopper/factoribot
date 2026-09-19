# 21 — Independent model and release review

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

Recommended: Astra high in a fresh session, separate from task 20's implementer.
Two passes: design review when task 20 supplies a concrete design; implementation
review after integrated tasks 15–20 are ready. Do not substitute a generic review
for either pass. No need to run this before task 20 has a design artifact.

## Ownership

Own dedicated adversarial review tests and
`docs/blueprint-routing-handoffs/21-independent-throughput-review.md`.
Do not repair production code during the review. Give each finding an exact
reproduction, impact and owning task. Use independent expectations before reading
the implementation wherever practical.

## Design pass

Assess whether the selected analytic/event/tick/engine-trial approach can support
its claimed rates for the stated subset. Check how it defines competing-consumer
allocation, splitter priorities, lane mixing, inserter research/timing, back-pressure,
finite inventory, cycles, warmup and convergence. Reject any reasoning that turns
an optimistic allocation into an achievable steady state without a justified
operating model. Review the reuse evaluation's evidence and bounded work limits.
Return accepted scope, concrete required changes and remaining uncertainties.
This pass is not a declaration that an unimplemented engine works.

## Implementation pass

Trace a real user operation from marking a full belt through draft export, CLI
sealing, furnace inference, flow analysis and regenerated page. Check supply is
neither doubled nor forced; shared capacities, conservation including storage,
output-removal requirements, recipe identity and inference provenance survive.
Test mixed/unknown feeds, stale edits, blocked outputs, cycles, transient inventory,
nonconvergence and unsupported mechanics. Verify that recipe visibility matches
blueprint data and the page does not present old results as current.

Cross-check predicted rates against independent Factorio observations with exact
build/mod/research/environment metadata. A synthetic fixture cannot close the
measurement gate. Inspect error tolerances and all advertised result wording.
Record mathematical correctness, engine agreement and actual pilot usefulness as
separate gates. State what was tested on fresh subprocesses versus the connected
MCP server. Run targeted adversarial cases and the full suite; document skipped or
unavailable external checks. Finish with a release decision scoped to evidence,
not the number of passing tests, and a precise remaining-work list.
