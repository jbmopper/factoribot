# Deterministic updates — paste-ready dispatch

Prepared 2026-09-11. These prompts implement the
[revised roadmap](../blueprint-routing-deterministic-roadmap.md), not the old
00–14 launch order. Recommended models/efforts are workload judgments from the
current discussion, not measured Factoribot model benchmarks.

Use a separate checkout per concurrent writer. Starting implementation is
`ab25b2a`; the roadmap and new prompt files may still be uncommitted, so copy the
relevant documentation into each checkout or provide it with the assignment.
Do not assume a worktree from HEAD contains uncommitted files. Choose the model
in Codex/Cursor's picker; mentioning it in a prompt does not select it.

## Current takeover

Tasks 15–21 have landed and coordinator corrections have been applied. The old
launch instructions below are historical. For the next session, use
[23-sol-takeover.md](23-sol-takeover.md): complete Sol extra-high takeover or a
bounded Sol-high 2.0.77 migration. Do not restart the completed assignments.

## Start these three together

### 15 — Page controls: Cursor Grok 4.6 high (or Terra high)

```text
Implement docs/blueprint-routing-prompts/15-full-belt-input-ui.md in Factoribot.
Read that complete prompt, WORKING-RULES.md and the deterministic roadmap first.
Keep the CLI workflow. Make it easy to select an input belt, choose its items,
and declare full supply using imported lane capacities. Show existing assembler
recipes clearly. Preserve shared budgets, safe rendering and result staleness.
Own the viewer and dedicated UI tests only; return the exported draft example
and handoff requested by task 15. Perform real browser interaction checks.
Do not build a web backend or implement throughput/furnace inference in this task.
```

### 16 — Existing-tool evaluation: Sol high

```text
Execute docs/blueprint-routing-prompts/16-existing-engine-evaluation.md in
Factoribot. Read the complete prompt, WORKING-RULES.md and deterministic roadmap.
Actually test the relevant existing blueprint analyzer on small known-answer
layouts in an isolated local environment. Assess reusable UI, inference, flow
and game-trial components. Record versions, licenses, concrete failures and a
reuse/adapt/reject recommendation. Own experiments/routing-reuse and your handoff;
do not change production code or upload the user's blueprint to a hosted demo.
```

### 17 — Measurement harness: Terra medium

```text
Implement docs/blueprint-routing-prompts/17-throughput-measurement-harness.md in
Factoribot. Read the complete prompt, WORKING-RULES.md and deterministic roadmap.
Build a bounded, reproducible capture harness for a straight belt, a fixed-research
inserter transfer and blocked output. Use an explicitly named disposable game
environment only, preserving existing saves and global mod configuration.
If game access is unavailable, finish runnable scenarios, record validation and
exact operator commands, and identify the measurements that remain unexecuted.
Do not edit shared evidence manifests or claim synthetic records are observations.
```

## Then run these in dependency order

| Task | Model | Start condition |
| --- | --- | --- |
| [18 — CLI integration](18-input-cli-integration.md) | Terra high | 15 code and exported draft integrated |
| [19 — Furnace inference](19-feed-driven-furnace-inference.md) | Sol high | Input contract fixed; land shared integration after 18 |
| [20 — Sustained throughput](20-sustained-throughput-model.md) | Sol high | 16 evaluation and 17 capture interface available; consume integrated 19 when needed |
| [21 — Independent review](21-independent-throughput-review.md) | Astra high | First: concrete 20 design. Second: integrated implementation |

Task 19's core module can proceed while task 18 handles CLI integration, using
separate owned files. Task 20 must account for unfinished game observations;
code may proceed, but validated throughput cannot be declared without evidence.
Have task 21 review the design before task 20 commits to substantial mechanics
implementation. After the review, send the concrete findings back to task 20.
Only one owner edits CLI/MCP/public request integration at a time.

### 18 — Paste after 15

```text
Implement docs/blueprint-routing-prompts/18-input-cli-integration.md. Read its
complete requirements and task 15's actual code, draft example and handoff.
Complete and verify page draft → CLI request → analysis → regenerated page.
Make host-template conflicts explicit. Preserve every declared input, output,
lane/shared capacity and provenance. Do not modify solver semantics. Return
reproducible CLI examples, fresh MCP replay evidence and the required handoff.
```

### 19 — Paste for furnace inference

```text
Implement docs/blueprint-routing-prompts/19-feed-driven-furnace-inference.md.
Read its complete requirements, the revised roadmap and task 10's inference
cases. Use explicit feeds and recipe data, retain uncertain candidates, preserve
overrides, and record evidence for each inferred recipe. Core work can proceed
separately, but wait for task 18 to finish before editing shared CLI/public files.
Verify chained furnaces, mixed feeds, cycles, changed-input invalidation and
inferred/manual request equivalence. Return the required handoff.
```

### 20 — Paste after the evaluation and harness

```text
Implement docs/blueprint-routing-prompts/20-sustained-throughput-model.md using
task 16's concrete reuse findings and task 17's capture interface. Read the full
prompt. First produce the bounded model design and validation cases for task 21
review; do not prematurely build a broad simulator. Preserve the existing bound
solver separately. Implement supported operating semantics, compare against
recorded Factorio results, and distinguish predictions, measurements and bounds.
Follow the shared-integration order and return the required handoff.
```

### 21 — Paste when the design or implementation is ready

```text
Perform docs/blueprint-routing-prompts/21-independent-throughput-review.md in a
fresh review session. Read its full requirements and inspect which review pass
is ready: task 20's concrete design, or the integrated implementation. Review that
pass explicitly. Derive independent counterexamples, report exact failures and
owners, and keep mathematical correctness, Factorio agreement and pilot usefulness
as separate gates. Do not repair production code or infer missing observations.
Write the required review handoff.
```

## Smaller work and later layout work

Use Luna medium for isolated documentation, display or fixture-formatting follow-ups
only after their exact requirements are known. Keep it out of shared files while
another owner is editing them. No generic "help wherever useful" assignment.

Layout optimization is deliberately not dispatched here. After task 21 accepts
a useful evaluator, define specific candidate changes and aesthetic preferences;
then assign visualization/UI to Grok or Terra, candidate search to Sol, and
correctness review to Astra. A passing static bound alone does not establish
that a rearranged factory behaves equivalently.
