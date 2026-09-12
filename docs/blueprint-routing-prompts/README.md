# Blueprint routing implementation prompts

Prepared 2026-09-08. These are implementation assignments, not claims that the
features exist. The parent design is
[blueprint-routing-design.md](../blueprint-routing-design.md).

**Current status and dispatch plan: [NEXT-STEPS.md](NEXT-STEPS.md).**
As of 2026-09-11, tasks 00–07 are implemented (02's game observations remain
unmet), fixes A/B/C and audit F-1/F-2/F-3 are complete, and task 08 has a
conditional pass. The fresh suite has 625 passing tests. Use the
[execution checklist](../blueprint-routing-next-run.md) for the remaining work;
do not redispatch completed tasks from this historical catalog.

Tasks 00–08 deliver the first routing audit; 09–14 are later releases.
Manual furnace assignments and explicit optimistic treatment of unknown inserter
rates belong in the first release.

## How to dispatch

Open the repository in the chosen agent and paste this, replacing the task path:

```text
Implement task 04 from docs/blueprint-routing-prompts/04-transport-graph.md.
Read docs/blueprint-routing-prompts/WORKING-RULES.md first. Work only on this
assignment, verify its prerequisites in this checkout, and return the specified
handoff. Use the current repository files as evidence; no prior chat is required.
```

Every task file also works as a copy-paste prompt when the receiving agent has the
repository. The instructions are host-neutral: Codex and Cursor should use their
own file, shell, test, and browser tools. These prompts do not configure a model
or launch other agents automatically.

The latest status check covers `664662e` plus an uncommitted implementation
tranche. Before dispatch, check for subsequent changes and provide the same
reviewed starting snapshot to each
checkout, including required untracked files if any, and record the revision plus
any patch manifest. A worktree from an older revision may omit required code.
Transfer only relevant files;
keep credentials, environment directories, and large local data out of handoffs.
Do not stash, reset, clean, or commit all existing changes as a setup shortcut.

Use separate checkouts for simultaneous writers. If agents share a checkout,
enforce the ownership below and serialize shared-file changes. Integrate completed
dependencies before starting a dependent task; an agent's status message is not
an available implementation. The coordinator owns merges and dispatch order.

## Agent recommendations

These assignments are engineering judgments, not Factoribot benchmark results.
OpenAI describes Luna as suited to clear repeatable work, Terra as its balanced
option, and Sol/Astra as suited to more complex work. That supports reserving the
stronger models for ambiguous mechanics and solver correctness. [OpenAI model guidance](https://learn.chatgpt.com/docs/models)

Cursor documents Grok 4.6 for complex, long-running coding work and supports
medium, high, and extra-high effort. My suggested uses here are the viewer,
integration, and an independent review; this is not a claim that Grok outperforms
Codex on those tasks. Use the standard speed tier when cost matters: Cursor lists
the Fast tier at twice the standard per-token rates. Check the picker and your
plan rather than assuming API prices equal included-plan consumption. [Cursor Grok 4.6 documentation](https://prod.cursor.com/docs/models/grok-4-6)

| Task | Preferred agent / effort | Alternative | Starts after |
| --- | --- | --- | --- |
| [00 Contracts](00-contracts.md) | Astra high | Sol high; Grok 4.6 high with independent review | Current snapshot available |
| [01 Calculation trust](01-calculation-trust.md) | Terra medium | Sol high if solver scope expands | Current snapshot available |
| [02 Prototypes and fixtures](02-prototypes-and-fixtures.md) | Terra medium | Grok 4.6 high; Luna for an already specified manifest-only subtask | 00 |
| [03 Lossless spatial model](03-spatial-model.md) | Terra medium | Luna high once 00/02 are concrete | 00, 02 |
| [04 Transport graph](04-transport-graph.md) | Sol high | Astra high; Grok 4.6 high with separate mechanics review | 00, 02, 03 |
| [05 Delivery bounds](05-delivery-bounds.md) | Astra high | Sol high; Grok 4.6 high with separate math review | Synthetic core: 00, 01; integrated acceptance: 02–04 |
| [06 Viewer](06-viewer.md) | Cursor Grok 4.6 high | Terra medium | Component: 00 spatial/result samples; real-data acceptance in 07 |
| [07 Public integration](07-public-integration.md) | Terra high | Cursor Grok 4.6 high | 01–06 implemented |
| [08 Independent audit](08-independent-audit.md) | Sol/Astra high | Grok 4.6 high, preferably different from core implementer | 07 |
| [09 Inserter rates](09-inserter-rates.md) | Sol high | Astra high; Grok 4.6 high with timing evidence | 08 release gate passes |
| [10 Furnace inference](10-furnace-inference.md) | Terra high | Grok 4.6 high | 08 release gate passes |
| [11 Power analysis](11-power-analysis.md) | Terra medium | Grok 4.6 high | 08 release gate passes |
| [12 Positional beacons](12-positional-beacons.md) | Sol high | Astra high | 08 release gate passes |
| [13 Cleanup and export](13-cleanup-and-export.md) | Sol high | Grok 4.6 high with independent patch review | 08; any mechanics needed by proposed edits validated |
| [14 Live validation](14-live-validation.md) | Grok 4.6 high | Sol high | 08 and a controlled game test environment |

Reasoning effort is a starting recommendation. Use a higher effort or stronger
model when a concrete counterexample, contract conflict, or unresolved mechanics
question warrants it. Avoid repeatedly retrying the same vague prompt. Give the
next agent the failing case, attempted fix, and remaining question.

## Original dependency schedule

This records the full implementation order. Use [NEXT-STEPS.md](NEXT-STEPS.md)
for the work remaining after the reviewed tranche.

1. Run 00 and 01 independently. Task 00 owns new contracts; 01 owns legacy fixes.
2. After 00 lands, run 02 and 06 against contract examples; start 05 against
   synthetic graphs once both 00 and 01 have landed. Complete 03 after 02, then
   04 after 03. Task 05 can finish its
   mathematical core before 04; its integrated acceptance waits for 02–04.
   Task 06 can pass component checks on 00's samples; real-data acceptance in 07
   requires the outputs of 03–05.
3. Run 07 after dependencies land. Run 08 independently; return defects to the
   owning implementer, then rerun the affected checks and the release gate.
4. After the first release, 09–12 can proceed in separate modules. Serialize
   shared adapter/schema/integration changes through the coordinator. Start 13
   only for mechanics already validated. Task 14 can run alongside these later
   tasks in its controlled test environment. Each extension owner handles its
   public-surface additions in a coordinator-scheduled integration pass using
   07's verification checklist; those shared edits are serialized.

With three workers, a useful initial allocation is **Astra on contracts/math,
Terra on trust/data/spatial work, and Grok on the viewer** as prerequisites become
available. Luna is most economical to try on precise schema fixtures, serialization
edge cases, or presentation changes after interfaces have stabilized. Do not send
it the entire routing design and ask it to discover the architecture.

## Completion and handoffs

The first release passes only after 08 verifies the integrated system against the
frozen contract and fixture evidence. Synthetic correctness, game-mechanics
validation, and real-blueprint usefulness are separate gates. Missing game
observations remain visible release limitations, even when unit tests pass.

Use [WORKING-RULES.md](WORKING-RULES.md) for the common handoff format. Record the
model, approximate elapsed time, retries, and usage if the host exposes it. Compare
cost per accepted change; do not invent usage or savings figures.

Automatic global redesign, trains, fluid simulation, arbitrary circuits, and
general mod/quality support remain outside these assignments.
