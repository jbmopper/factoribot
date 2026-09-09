# Next steps after the Claude tranche

Updated 2026-09-08 after reviewing commit `76fd016`. This is the current dispatch
plan; [README.md](README.md) retains the full task catalog and model guidance.

## Reviewed state

- Tasks 00/01 are implemented. Prototype fixtures, spatial indexing, the synthetic
  solver core, and viewer components from 02/03/05/06 are present.
- The review reran `make test`: **330 passed**. Additional cases reproduced the
  three defects below; they are not yet fixed by this document.
- Task 04's actual transport connections and task 07's public integration remain.
- Game-mechanics evidence is six documented-only records, ten pending records,
  and zero observed records. Component tests do not close that gate.

## Assignments

| Work | Recommended model / effort | Alternative |
| --- | --- | --- |
| Fix A — numerical certificates | Astra high | Sol high |
| Fix B — duplicate finding IDs | Terra medium | Luna high with the explicit cases below |
| Fix C — viewer provenance | Luna medium | Terra medium |
| [04 — Transport graph](04-transport-graph.md) | Grok 4.6 high for the cost-conscious allocation | Sol high |
| Controlled game-mechanics captures for 02/04 | Terra medium | Grok 4.6 high |
| [07 — Public integration](07-public-integration.md) | Grok 4.6 high | Terra high |
| [08 — Independent audit](08-independent-audit.md) | Astra high or Sol high in a fresh session | Grok 4.6 high |

These are workload-based recommendations, not measured comparisons on Factoribot.
The roles and effort choices follow the previously checked
[OpenAI model guidance](https://learn.chatgpt.com/docs/models) and
[Cursor Grok 4.6 documentation](https://prod.cursor.com/docs/models/grok-4-6).

Run A/B/C in parallel in separate checkouts with distinct new regression test
files. Task 04 can proceed independently against the existing contract. Serialize
any shared contract changes through the coordinator. Integrate the fixes and
task 04 before accepting task 07, then run task 08. Capture mechanics observations
alongside task 04 in a controlled game environment, following the existing
[capture procedure](../../daemon/tests/fixtures/routing_mechanics_observations/CAPTURE.md).
Missing observations must stay explicit in the supported scope.

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

## Handoff and release gate

Use the common handoff format. Keep every complete request, source hash, observed
failure, and reproduction command available to the next agent. Task 08 must
exercise these regressions as well as the new real-layout path. The next useful
deliverable is one blueprint imported, connected, analyzed, and inspected through
the public interface under explicit assumptions.
