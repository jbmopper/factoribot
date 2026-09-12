# Blueprint routing — current next steps

Updated 2026-09-11. This is the current dispatch record; the
[task catalog](README.md) retains the original implementation prompts and model
recommendations. Do not redispatch completed work from those prompts.

## Verified state

Status check covered HEAD `664662e` plus the current uncommitted implementation,
fixtures, tests and handoffs. A fresh `make test` completed with **625 passed,
0 failed, 0 skipped in 129.72 seconds** on 2026-09-11. This is software validation,
not a game observation or a verification of the user's running MCP process.

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

Evidence remains **0 observed / 6 documented-only / 10 pending**. The pilot's
actual feeds, exports, removal services, research, mod manifest, control state,
power and 76 furnace recipe assignments remain undeclared. The illustrative
fixtures do not supply those facts.

## Next dispatch

Follow the [execution checklist](../blueprint-routing-next-run.md). The order is:

1. Preserve and review the complete uncommitted tranche; checkpoint only the
   intended files. Verify the connected MCP process exposes the new tools after
   a host restart/reconnect.
2. In parallel: collect the pilot's real declarations and run small, controlled
   mechanics captures in a disposable Factorio environment. Start with the fast
   belt and lane/connection rules used by the pilot. One observation does not
   validate the entire mechanics profile.
3. Have one integration owner validate evidence records, regenerate manifests,
   review model and advertised-scope implications, reseal requests and rerun the
   public pipeline. Evidence changes can change graph identity.
4. Review the resulting pilot findings and remaining conditions. Keep every
   number labelled as an upper bound under stated relaxations.

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
