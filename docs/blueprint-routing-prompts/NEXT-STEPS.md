# Blueprint routing — current next steps

Updated 2026-09-13. This is the current dispatch record; the
[task catalog](README.md) retains the original implementation prompts and model
recommendations. Do not redispatch completed work from those prompts.

## Task 23 takeover completed — 2026-09-13

The full [task 23 takeover](23-sol-takeover.md) has been executed. The concrete
result, artifacts, reproduction commands, limitations and browser blocker are in
[the task 23 handoff](../blueprint-routing-handoffs/23-sol-takeover.md). Do not
redispatch the takeover prompt as unfinished work.

Runtime and generated fixtures now target base 2.0.77. A sealed small-factory
case completes blueprint → page draft → optional furnace inference → routing
capacity result → restricted operating prediction → two real Factorio captures →
comparison report. The routing upper bound and conditional prediction are both
`0.125 steel-plate/s`; six 3,600-tick measured windows record 7/8/7 steel in each
repeat and all pass the predeclared one-item/window tolerance. The captures also
record 15 items/s on one fast-belt lane, 30 items/s on two lanes, and 2.5 items/s
for a zero-bonus fast inserter. No finite-window result claims sustained recurrence.

Current open product work is the permitted-environment browser click/export/import
acceptance, real owner declarations for the modded pilot, broader mechanics
evidence, and any later layout optimization. The restricted operating adapter
does not support merges, splitters, turns, side-loading, cycles, competing shared
budgets or arbitrary machine/inserter layouts.

Final task-23 verification: **693 passed in 139.61 seconds** via `make test`,
with no failures, expected failures, or skips.

## Target version selected — 2026-09-12

The user selected **2.0.77**. An isolated base-only export from the installed build
84539 is now pinned in
[the 2.0.77 profile staging directory](../../experiments/routing-measurements/profiles/base-2.0.77-normal-v1/README.md).
All overlapping selected prototype fields match the previous slice; the modded
`ee-super-substation` is absent. This closes the target-version decision and the
fresh prototype-export prerequisite, not the mechanics validation gate.
The version-bound runtime/fixture migration is complete. Historical 2.0.76
mechanics records retain their provenance and are reported as incompatible
legacy evidence rather than silently promoted. Do not ask the user to choose the
version again.

## Historical coordinator corrections — 2026-09-12

Follow-up implementation is recorded in
[22-coordinator-integration.md](../blueprint-routing-handoffs/22-coordinator-integration.md).
Fresh final `make test`: **686 passed in 152.96 seconds**, with no expected
failures or skips. The five previously expected failures are repaired: recipe oracles are checked
against loaded craft coefficients, and the recorder validates inventory continuity,
scenario settings and repeat consistency. Flat windows no longer claim sustained
production. Capture v2 adds basic crafting and individual-boundary accounting;
its scenario/timing validation remains incomplete. The original review below is
historical and its test counts predate these corrections.

At that checkpoint the CLI draft/request/result-page loop had been rerun, browser
navigation was blocked by policy, and the discovered Factorio 2.0.77 binary did
not match the then-current 2.0.76 profile. The version decision, migration, game
observations, and restricted predictor were completed by task 23 above; the
browser click/download/import acceptance remains open.

## Historical tranche review — 2026-09-12

Tasks 15–21 have artifacts in the working tree on `ab25b2a`; they are uncommitted.
Their completion levels differ:

| Task | Current acceptance |
| --- | --- |
| 15 / 18 | Full-input UI and CLI draft replay implemented; actual browser click/download/import acceptance remains unexecuted |
| 16 | Reuse evaluation complete; concrete upstream failures support declining the evaluated throughput engine |
| 17 | Offline recorder/scenarios implemented; no game observations; validator and evidence schema need R4/R5 repairs |
| 19 | Furnace inference and CLI preparation implemented; illustrative pilot yields zero inferred assignments, not a solved factory |
| 20 | Design/scaffolding only, no simulator or public sustained-rate prediction; independent review requests changes |
| 21 | Design pass complete with R1–R5 findings; implementation pass not yet ready |

Fresh full suite: **676 passed, 5 xfailed in 145.11 seconds**. The five expected
failures are acknowledged defects, not passing acceptance tests.

Coordinator reran the independent witnesses with `--runxfail`: **5 failed,
6 passed**, confirming the known recipe-oracle and recorder defects. The retained
reuse harness also passed all seven tests. These failures are not regressions in
an already implemented simulator: that simulator does not exist yet.

Next: task 20 revises R1–R3 (convergence claims, operating allocation/transitions,
and recipe-coefficient-backed oracles); task 17 repairs R4 and versions richer R5
observations. Those owners can work separately. Return the revised design to task
21 before substantial mechanics implementation. Separately close task 15/18's
browser interaction gate. See the
[review's reproductions and required changes](../blueprint-routing-handoffs/21-independent-throughput-review.md).
Do not redispatch the original prompts as though these artifacts were absent.

## Revised product priority

The user now prioritizes deterministic sustained-throughput analysis, convenient
full-belt input declarations in the page, and furnace inference, followed by
efficient/aesthetic layout alternatives. Keep the CLI loop. The
[deterministic roadmap](../blueprint-routing-deterministic-roadmap.md) gives the
new milestones and acceptance criteria. It supersedes the blanket deferral of
09/10: bring forward their relevant supported subsets with explicit evidence
requirements. Browser upload and a web backend remain deferred.

Current checkout is `ab25b2a`; the earlier implementation tranche is committed.
The connected MCP has since returned successful capabilities and a synthetic
layout inspection; both new routing tools are available. The test and audit
observations below retain their original scope and dates.

## Previously verified state

Status check covered HEAD `664662e` plus the current uncommitted implementation,
fixtures, tests and handoffs. A fresh `make test` completed with **625 passed,
0 failed, 0 skipped in 129.72 seconds** on 2026-09-11. This is software validation,
not a game observation or a verification of the user's running MCP process.

Task 18's later fresh full run completed with **644 passed in 146.80 seconds**.
It covers the task-15 draft → CLI request → analysis → regenerated-page replay
and a new stdio-MCP replay; browser interaction acceptance remains open.

| Work | Status |
| --- | --- |
| 00/01 contracts and calculation trust | Implemented |
| 02 prototypes and evidence records | Implemented; game-observation gate remains open |
| 02b installed evidence packaging | Implemented; installed-wheel validation recorded in its handoff |
| 03 spatial model, 04 transport graph | Implemented |
| 05 delivery bounds, 06 viewer | Implemented and integrated |
| Fixes A/B/C | Fixed, regression coverage passes |
| 07 CLI/MCP integration | Implemented; public tools, sealing and viewer workflow available |
| 08 independent audit | Conditional pass; math tests pass, game validation unmet, pilot usefulness unverified |
| Audit F-1 / F-2 | Fixed: MCP provenance argument and evidence-derived capability prose |
| Audit F-3 | Fixed: pilot warning aggregation, 626 findings reduced to five |
| Audit F-4 | Open, low severity: malformed internal LP RHS raises a SciPy error; not reachable from valid public requests |
| 09–14 extensions | Deferred; do not treat the first-release gates as passed |
| 15/18 Milestone-1 declarations and CLI loop | Implemented through draft → sealed request → analysis → regenerated-page replay; browser interaction acceptance remains open |

Evidence remains **0 observed / 6 documented-only / 10 pending**. The pilot's
actual feeds, exports, removal services, research, mod manifest, control state,
power and 76 furnace recipe assignments remain undeclared. The illustrative
fixtures do not supply those facts.

## Historical next dispatch

**Original paste-ready assignments: [DETERMINISTIC-DISPATCH.md](DETERMINISTIC-DISPATCH.md).**
Tasks 15–21 and the task-23 integration now exist in the shared checkout. Retain
this section for provenance; do not launch it as the current work queue.


Use the [deterministic roadmap](../blueprint-routing-deterministic-roadmap.md):

1. Implement recipe visibility and full-belt input designation with a replayable
   page draft → CLI analysis loop. User supplies items; capacities come from the
   imported belt tier, with lane sharing preserved.
2. Add evidence-traceable furnace inference from declared feeds, retaining
   ambiguity and explicit overrides.
3. Evaluate existing analyzers for reuse and validate a bounded sustained-rate
   model against Factorio. Preserve the existing upper-bound analysis separately.
4. Optimize local layout alternatives only when their throughput can be evaluated
   credibly; compare efficiency and appearance explicitly.

The [execution checklist](../blueprint-routing-next-run.md) still describes the
current CLI and capture mechanics. Full input means available supply at belt
capacity, not forced consumption. Captures and real pilot declarations remain
necessary, but the UI should not demand manual reconstruction of known recipes
or numeric belt capacities.

F-4 is a separate bounded robustness patch, not a reason to delay collecting
real inputs. Keep `routing_lp.py` ownership separate from evidence and pilot
work. Use the audit's explicit reproduction and acceptance test; do not redesign
the numerical certificate layer for it.

## Records

- [Release review and current follow-up status](../blueprint-routing-release-review.md)
- [07 integration, including F-1/F-2](../blueprint-routing-handoffs/07-public-integration.md#11-audit-fixes-f-1f-2)
- [05 bounds and F-3 aggregation](../blueprint-routing-handoffs/05-delivery-bounds.md)
- [02b evidence packaging](../blueprint-routing-handoffs/02b-evidence-packaging.md)
- [Controlled capture procedure](../../daemon/factoribot/evidence/routing_mechanics_observations/CAPTURE.md)

## Historical fix prompts — completed, retained for reproduction

The prompts below describe defects at `76fd016`, before their fixes. They are
not outstanding assignments. Current handoffs and passing regressions supersede
their before-state descriptions.

## Fix A — copy-paste prompt

```text
Fix numerical certificate soundness in the Factoribot routing solver. Read
docs/blueprint-routing-prompts/WORKING-RULES.md first. Starting review: 76fd016.

Own daemon/factoribot/routing_lp.py and a new
daemon/tests/test_routing_certificate_regressions.py. Coordinate any necessary
blueprint_plan.py or contract changes with the reporting-fix owner.

Reproduce two cases before changing code:
1. LPModel with x >= 0, no finite upper bound, cost -5e-10*x. solve_lp currently
   returns status 0; dual_bound(..., tolerance=1e-9) returns value 0, valid=True,
   and worst_reduced_cost=-5e-10, despite the true optimum being -infinity.
2. Through the existing routing_plan/cases.py Layout builder, give a machine
   one iron input per craft, 5e-10 gear output per craft, unlimited craft capacity
   and machine time, unlimited iron supply, and an unlimited gear export sink.
   analyze_delivery currently reports certified zero bounds. The true maximum
   is unbounded because the yield is positive and crafting has no finite limit.

Fix the certificate argument, not just these constants. A negative reduced cost
on an unbounded variable cannot be discarded because it is small. Either produce
a justified conservative bound or withhold certification. Check finite-variable
error corrections and infeasibility certificates too; optimizer success alone
is insufficient. Do not fix this merely by adjusting HiGHS tolerances or rejecting
all small recipe amounts.

Add independent regression cases, including a normal bounded case that remains
useful. Run focused tests and make test. Return the mathematical justification,
before/after results, remaining limitations, and task-specific diff.
```

## Fix B — copy-paste prompt

```text
Fix duplicate finding IDs in Factoribot delivery reporting. Read
docs/blueprint-routing-prompts/WORKING-RULES.md first. Starting review: 76fd016.

Own daemon/factoribot/blueprint_plan.py and a new
daemon/tests/test_routing_reporting_regressions.py. Coordinate shared findings.py
or blueprint_contract.py changes; do not edit routing_lp.py or the viewer.

Reproduce these failures using the existing routing_plan/cases.py pass_through
case and valid, resealed requests:
1. Set power to unknown and add a declared mod with alters_item_mechanics=True.
   analyze_delivery raises ContractError: duplicate finding ID instead of partial.
2. Analyze the normal case with PlanOptions(max_variables=0). Multiple limited
   stages raise the same error instead of returning solver_limit.

Distinct reasons/stages currently share the same code and empty identity scope.
Give them stable semantic identities or deliberately aggregate the findings
without losing explanations. Preserve deterministic ordering and meaningful
entity/evidence references. Do not swallow ContractError, randomly generate IDs,
or silently discard all but one message. Keep IDs independent of translated
message text, consistent with the contract.

Check other repeated finding categories for the same collision. Add focused
regressions for both cases and deterministic repeated calls. Run make test and
return the before/after results and task-specific diff.
```

## Fix C — copy-paste prompt

```text
Fix prototype provenance matching in the Factoribot viewer. Read
docs/blueprint-routing-prompts/WORKING-RULES.md first. Starting review: 76fd016.

Own daemon/factoribot/blueprint_view.py, relevant view.js changes if necessary,
and a new daemon/tests/test_viewer_provenance_regressions.py. Do not change the
solver or shared contract.

Load routing_contracts/shared_budget.json. Change result.prototype_hash to a
different validly formatted hash, reseal result_hash, and call build_view_model.
It currently returns result.graph_match=True, although findings.validate_result
requires blueprint, prototype, and graph hashes all to agree.

Preserve prototype_hash in the rendered result and include it in freshness
checks. Missing or mismatched provenance must not be displayed as current.
Cover valid matching data, prototype-only mismatch, missing prototype hash, and
the existing blueprint/graph mismatch cases. Verify that the browser displays
the stale/mismatch state and preserves safe text rendering.

Run focused tests and make test. Return the before/after result and task-specific
diff. Keep this change bounded to provenance; defer unrelated viewer redesign.
```
