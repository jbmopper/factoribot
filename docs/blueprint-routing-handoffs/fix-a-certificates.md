# Fix A handoff — numerical certificate soundness

## 1. Identity

- Task: `docs/blueprint-routing-prompts/NEXT-STEPS.md`, "Fix A — numerical certificates".
- Starting snapshot: reviewed commit `76fd016` (working tree at `664662e` plus the
  uncommitted tranche); `make test` reported 330 passed before other agents' files
  landed, 350 immediately before this change.
- Contract version consumed: **1.1.1** (no contract change proposed or made).
- Model: Claude (Opus 5, `claude-opus-5[1m]`).

## 2. What changed

Owned and changed:

- `daemon/factoribot/routing_lp.py` — the certificate argument (`DualCertificate`,
  `dual_bound`, new `implied_upper_bounds`, `_weak_duality`, `_repair_step`,
  `_exact_reduced_cost`, `_product_low`, `_sum_low`, `_columns`, `describe_label`).
  No change to the model builder, the solve call, HiGHS options, or any tolerance
  passed to the solver.
- `daemon/tests/test_routing_certificate_regressions.py` — new, 12 tests.
- This document.

Not touched: `blueprint_plan.py` (Fix B owns it), the contract modules, the viewer,
transport files, `tools.py`, `mcp_server.py`, `cli.py`, skills. Nothing committed.

## 3. The defect and the mathematical justification

### What was wrong

A certificate is the weak-duality chain: for any feasible `x`,

```
c.x = r.x + y_ub.(A_ub x) + y_eq.(A_eq x)  >=  r.x + y_ub.b_ub + y_eq.b_eq
r   = c - A_ub^T y_ub - A_eq^T y_eq,   y_ub <= 0
r.x >= sum_j inf{ r_j t : l_j <= t <= u_j }
```

The last term is **-infinity** as soon as one `r_j < 0` on a column with `u_j = inf`:
`x_j` may be arbitrarily large, so `r_j x_j` is unbounded below. The magnitude of
`r_j` is irrelevant — `-5e-10` times `2e9` is `-1`, and times `2e18` is `-1e9`.

The old code discarded exactly that case whenever `|r_j| <= 1e-9`:

```python
else:                       # no finite upper bound
    worst = min(worst, float(rc))
    if rc < -tolerance:     # tolerance = 1e-9 as called
        valid = False
```

`1e-9` is also HiGHS's configured `dual_feasibility_tolerance`, so the discarded band
is precisely the band in which the optimizer is permitted to return a dual-infeasible
point labelled "optimal". The certificate therefore rubber-stamped the solver's own
tolerance instead of checking it, and an unbounded objective was reported as a
certified finite bound of 0.

### What replaces it

Four changes, in the order they apply:

1. **The reduced cost is computed exactly, not approximately.** The only thing a
   threshold could ever legitimately absorb is the floating-point error of evaluating
   `r` itself, so that error is *removed* rather than estimated. Each `r_j` is built
   from error-free products (`fma(a, y, -fl(a*y))` is exactly the rounding error of
   one multiplication) summed with `math.fsum`, which is correctly rounded; a second
   `fsum` of the same terms against the result is the exact residual, so a zero
   residual **proves** the value is exactly `r_j`. In every case in the repository
   the residual is zero, so the certificate keeps bit-exact values (see §4 and §7).
   A cheap interval (the classic `gamma_k` dot-product bound over `|A|^T|y|`) is used
   only as a filter to skip columns whose reduced cost is already provably `>= 0`
   while sitting at a zero lower bound — those contribute exactly nothing.
2. **A negative reduced cost is charged to a ceiling that is proven, or not at all.**
   `implied_upper_bounds` derives ceilings valid at *every* feasible point by interval
   propagation over the rows: from `sum_j a_j x_j <= b` and `a_k > 0`,
   `x_k <= l_k + (b - L)/a_k` where `L = sum_j inf(a_j x_j)` over the current box;
   an equality row is used in both directions. Derived ceilings are rounded
   *outwards*, which can only weaken a bound, never strengthen it. Because the
   ceiling holds for the feasible set, using it inside the box term is exactly the
   `U_j` of the inequality above — no double counting with the row's own multiplier.
   This is the "justified conservative bound" branch: a real negative reduced cost
   produces a real, larger, still-valid bound instead of being ignored.
3. **When a genuine violation remains, the multipliers are walked back, not excused.**
   `y(t) = t*y` gives `r(t) = (1-t)c + t*r`, affine in `t`, and `t = 0` (`r = c`) is
   dual feasible on every column whose own cost points the safe way. `_repair_step`
   takes the largest `t` that is provably feasible on the blocking columns and
   re-certifies from scratch at `t*y`. This can only recover a bound the trivial
   multipliers already supported: a column with `c_j <= 0` and no ceiling admits no
   positive step, which is exactly the genuinely unbounded case. The repair therefore
   cannot manufacture a bound for an unbounded objective — proven by construction and
   pinned by a test.
4. **Every arithmetic step is rounded against the claim.** Products use
   `_product_low` (drop one ulp unless the `fma` residual proves the product is
   exact), sums use `_sum_low` (`fsum` plus its exact residual, dropping one ulp when
   the residual is negative). The returned `value` is a float that is provably `<=`
   the real weak-duality bound, so `-value` is provably `>=` the true maximum.

Also hardened, per the assignment's "check the other paths too":

- Non-finite multipliers are rejected (`valid=False`, named reason) instead of
  propagating NaN into a bound.
- A row carrying a non-zero multiplier with an infinite right-hand side is rejected;
  `y_i b_i` would be `-infinity`, not a bound.
- The `y_ub <= 0` clamp is kept and is sound (any non-positive `y_ub` is admissible),
  and `r` is recomputed from the clamped vector, not the raw one.
- Free columns (`l_j = -inf`) priced the wrong way are rejected symmetrically. The
  current builder never creates one; the branch exists so a future one cannot slip
  through.
- The **infeasibility** certificate goes through the same `dual_bound`, so the
  minimum-shortfall lower bound is now rigorous as well. `blueprint_plan` already
  required it to exceed a positive margin, and still does.

### What this does *not* do

Not fixed by adjusting HiGHS tolerances (the `linprog` options are untouched), not by
rejecting small recipe amounts (a `5e-10` yield is a legitimate model; the second case
below is refused for being *unbounded*, and the same model with a real ceiling is
still certified — `test_the_same_column_with_a_real_ceiling_is_still_certified`).

## 4. Before / after

Both reported cases reproduced against the pre-fix module first (loaded in-process
from `git show HEAD:...`, no working-tree swap):

| case | before | after |
| --- | --- | --- |
| `LPModel` with `x >= 0`, no upper bound, cost `-5e-10 x` (true optimum `-inf`) | `solve_lp` status 0; `dual_bound(..., tolerance=1e-9)` → `value=0.0`, `valid=True`, `worst_reduced_cost=-5e-10` | `valid=False`, `value=-inf`, `uncertified_variables=(('x',),)`, reason names the possibly unbounded column. `solve_lp` still returns status 0 — the status word is not the proof. |
| Layout: 1 iron per craft → `5e-10` gear per craft, unlimited craft capacity, machine time, iron budget, feed and gear sink (true optimum unbounded) | `feasible_relaxed` with three `optimal` scenarios certifying **0 items/s** | `solver_limit`, **no bound scenarios**, all three stages `uncertified`, one `solver_limit` finding per stage, no `upper_bound` finding |
| Same layout, independent check | — | a hand-built feasible point delivers 1000 gear/s (2e12 crafts/s of iron), verified against the assembled rows and bounds — 10^12 times the value that was certified as a ceiling |
| Normal bounded LP: `min -2a - b`, `a+b<=4`, `a<=3` (hand optimum `-7` at `a=3, b=1`) | `-7.0` | `-7.0`, bit-identical |
| `large_layout.json` (3202 columns) | 15 / 5 / 5 | 15 / 5 / 5, certificate time 3.5 ms → 8.2 ms, whole analysis 0.30 s → 0.33 s |
| motivating budget scenario (real recipe coefficients) | `8/7` | `1.1428571428571432`, one ulp **above** `8/7` — the safe direction, inside the 1e-7 tolerance the test uses |

Counterexample kept in the tests: with `y = 0` on `min -x, x >= 0` plus the row
`x <= 10`, the certificate is `-10` (charged to the ceiling the row proves); delete the
row and the same multipliers must certify nothing. A rule that rejected every small
negative reduced cost would lose the first; the old rule kept the second.

## 5. Interaction with `blueprint_plan.py` (not edited)

Verified by reading `solve_stage` and the result assembly:

- `if certificate is None or not certificate.valid:` → `state="uncertified"`, value
  `None`, certificate text "No certified dual bound; incumbent withheld."
- The bounds loop skips `("limit", "size_limit", "uncertified", "feasible")`, so an
  invalid certificate advertises **no scenario at all**; `limited` then forces
  `status="solver_limit"` with a per-stage warning finding.
- `_certify_infeasible` likewise degrades to `state="limit"` when the shortfall
  certificate is invalid or not above its margin.
- The nesting rule `certified = min(own value, looser stage's value)` still only ever
  sees certified values, so skipping a stage cannot loosen another one unsoundly.

**No blueprint_plan edit is required for soundness.** One optional, non-soundness
improvement for the coordinator to route if wanted:

- File `daemon/factoribot/blueprint_plan.py`, method `_Scope.collect`, the branch
  `elif kind in ("upper", "lower"):` (line 597 after Fix B landed). Replace that one line with
  `elif kind in ("upper", "lower", "implied"):`. Reason: a cut term charged to a
  ceiling derived from the rows carries the label kind `"implied"`, which `collect`
  does not recognise, so such a term contributes no entity/evidence IDs and the bound
  falls back to the anchor endpoint. Nothing unsound follows (the value and the
  certificate text are unaffected; `describe_label` renders it as
  "... ceiling implied by the constraints"), and no case in the repository currently
  produces such a term — see §7.

## 6. Commands and results

```sh
.venv/bin/python -m pytest daemon/tests/test_routing_certificate_regressions.py -q   # 12 passed
.venv/bin/python -m pytest daemon/tests/test_blueprint_plan.py -q                     # 32 passed
.venv/bin/python daemon/tests/fixtures/routing_plan/cases.py                          # every case value unchanged
make test                                                                             # 362 passed in 23.8 s, 0 skipped, 0 failed
make test                                                                             # 391 passed in 22.4 s, after Fix B and Fix C landed
```

`make test` was 350 passed immediately before the change (330 at the review, plus
other agents' new files) and 362 after, the difference being this task's 12 tests.
A final run once Fix B and Fix C landed in the shared checkout reports 391 passed,
0 failed; their changes to `blueprint_plan.py` keep the consumer behaviour described
in section 5 (re-checked at lines 454-456, 480-481, 764, 790).
No test was skipped: the game data dump is present, so
`test_motivating_budget_scenario_routing_free` ran and passes. No failure in a file
owned by another task was observed at the final run.

Reproductions live in the tests, not in scratch scripts:
`test_tiny_negative_cost_on_an_unbounded_column_is_not_certified` is case 1 and
`tiny_yield_layout()` / `test_unbounded_tiny_yield_layout_advertises_no_bound` is
case 2, built through `daemon/tests/fixtures/routing_plan/cases.py`'s `Layout`.

## 7. Assumptions, limitations, unmet gates

- **Withholding, not detection.** An unbounded model that HiGHS labels "optimal" now
  yields `solver_limit` with no bound, not `unlimited`. That is sound (nothing false
  is claimed) but weaker than the truth. Reporting `unlimited` would need a rigorous
  primal ray certificate — a direction `d` with `A_ub d <= 0`, `A_eq d = 0`,
  `c.d < 0` verified in exact arithmetic — which is not implemented. `unlimited` is
  still reported normally when the optimizer itself returns status 3 and a feasible
  point is confirmed, which is the common case; only the near-degenerate tiny-yield
  regime falls through to `solver_limit`.
- **Ceiling propagation is upper-direction only** and capped at 8 passes. It does not
  propagate lower bounds, so it will miss ceilings that need one (the test documents
  a case where `x <= 5` is derived but the sharper `x <= 3.5` is not). Missing a
  ceiling can only cause withholding, never a false bound.
- **The fallbacks have unit coverage, not corpus coverage.** With exact reduced costs,
  all 43 certificate evaluations across every synthetic case and contract fixture, and
  both stages of the motivating scenario, are "clean": zero implied ceilings and zero
  repairs are needed. The implied-ceiling and repair paths are exercised by the direct
  tests in the new file, which construct the multipliers by hand. They exist because
  HiGHS is contractually allowed to return duals that are infeasible by up to its
  tolerance; without them a single such return would force withholding on a perfectly
  good model.
- **Cost.** One extra pass over the columns in Python. Measured: certificate time on
  the 3202-column routing model 3.5 ms → 8.2 ms; whole `analyze_delivery` 0.30 s →
  0.33 s. `implied_upper_bounds` and the repair solve run only when needed, which in
  the current corpus is never.
- `math.fma` (Python 3.13+) is used for the exact product split, with an exact
  `fractions.Fraction` fallback for older interpreters. The environment runs 3.14.7,
  so the fallback path is untested here.
- Unchanged gates from task 05 §5 remain unchanged: no adapter-produced graph, no
  game validation, no MCP/CLI surface. Every number above is from synthetic contract
  fixtures and hand-derived expectations, and is not game evidence.

## 8. Next

Nothing in this task blocks task 04 or task 07. For task 08 (independent audit) the
useful targets are: the two reproduced defects above as a before/after pair; the claim
in §3 that the repair step cannot rescue an unbounded objective; and the claim that
derived ceilings are valid for the whole feasible set (`implied_upper_bounds`), which
is the only place a wrong derivation could silently *strengthen* a bound.
