# Task 05 handoff — delivery bounds (synthetic-core scope)

## 1. Identity

- Task: `docs/blueprint-routing-prompts/05-delivery-bounds.md`, synthetic-core scope only.
- Starting snapshot: HEAD `0b0f3da6499fcea21e100fec494c54e7dc979b01` plus the uncommitted
  working tree (planner, MCP adapter, skill, task 00 contract, task 01 fixes).
- Contract version consumed: **1.1.0** (the contract moved from 1.0.0 to 1.1.0 while
  this task ran; the code adapted to `SCHEMA_VERSION`, entity `subsystem`/`mod`,
  `ModDeclaration`, `irrelevant`, and `declared_assumptions` without hardcoding any
  version string or fixture hash).
- Model: Claude (Fable 5.1, `claude-fable-5-1`).

## 2. What changed (owned files only)

New:

- `daemon/factoribot/routing_lp.py` — sparse LP layer (HiGHS via SciPy 1.18.1):
  `ModelInputs` adapter record, lazy row creation, per-stage build, solve, weak-duality
  certificate (`dual_bound`), minimum-shortfall infeasibility model, secondary cleanup
  cost. No blueprint semantics.
- `daemon/factoribot/blueprint_plan.py` — contract coupling: `resolve_model_inputs`
  (adapter boundary), `verify_allocation` (independent graph-walk verifier, no shared
  code with the matrix builder), `solve_stage`, `analyze_delivery`,
  `analyze_request_document` (strict-parse failures become `invalid_request` records),
  `counterfactual_routing` (re-solve with changed group/budget capacities).
- `daemon/tests/fixtures/routing_plan/cases.py` — synthetic case builder over the public
  contract constructors with hand-derived expectations in docstrings; runnable
  (`.venv/bin/python daemon/tests/fixtures/routing_plan/cases.py`).
- `daemon/tests/test_blueprint_plan.py` — 29 tests.
- This document.

No file owned by another task was edited. No public tool, MCP schema, CLI or skill
change was made.

### Model

One per-entity model; three stages relax *named* constraints of that model:

| stage | conservation | arcs / lane, splitter, inserter, boundary groups | machine time + craft caps | budgets + feed ceilings | exports / surplus / sinks | relaxations recorded |
| --- | --- | --- | --- | --- | --- | --- |
| routing | per resolved endpoint × material | all enabled, every finite group charged once per use | yes | yes | yes | (+ `unknown_capacity_unlimited`, `conditional_connections_open`, `transport_semantics_relaxed` when applicable) |
| budget | one pool per material | none | yes | yes | yes | `delivery_unconstrained` |
| aggregate | one pool per material | none | yes | none (declared feeds only, unlimited) | yes | `delivery_unconstrained`, `budgets_unlimited` |

- Variables: `flow[arc, material]` only for materials eligible at the arc, both resolved
  endpoints and any lane alias; `craft[activity]` per enabled activity; `import[feed]`;
  `export[export]`; `surplus[surplus]`. Materials are the union of budget, outlet and
  activity materials.
- Group constraint exactly as the contract states: `Σ coef·flow + Σ coef·crafts ≤ cap`
  over all uses; an arc with several `ResourceUse`s is charged on each; alternative arcs
  through one group share one ceiling. Unknown capacity → `inf` + relaxation flag.
- Furnace candidates: only the assigned recipe (or the unique candidate) is enabled;
  the entity's machine-time group is shared. Ambiguity is decided by
  `unresolved_reasons` (contract), never here.
- Conditional arcs: `explicit` → enabled iff every named condition is enabled;
  `relax_open` → enabled, flagged. Disabled arcs get a `control_disabled_connection` finding.
- Objective: `maximize_export` → max the objective export (its own requirement stays
  active); `feasible` → c = 0 (feasibility only; scenarios per §5 and §7).
- Secondary objective: with the primary optimum pinned as an equality row, minimise
  total flow + crafts + imports + surplus + non-objective exports. The primary value is
  re-checked after cleanup (`|c·x − opt| ≤ tol`).
- Certification: every finite bound is `−D(y)` where `D(y)` is recomputed from the
  returned multipliers (`r = c − A_ubᵀy_ub − A_eqᵀy_eq`, bound terms from `l`/`u`);
  weak duality makes it a valid upper bound independent of the solver status word.
  A certificate is rejected if any reduced cost is below `−1e-9` on a variable with no
  finite upper bound. Nesting is enforced soundly: each tighter stage reports
  `min(own certified value, looser stage's value)` (a valid bound for a subset model).
- Infeasibility: minimum-total-shortfall LP (two-sided slack for `exact`, one-sided for
  `minimum`); its dual gives a certified positive lower bound on the shortfall; the
  certificate text lists the constraint cut and every requested export.
- Unbounded (`unlimited`): reported only after a separate feasibility solve confirms a
  feasible point; it is a non-claim, not a rate.
- Work bounds: `count_model` estimates variables/nonzeros before any allocation;
  `PlanOptions(max_variables, max_nonzeros, time_limit_s)` → `solver_limit` result with
  all surviving bounds as `certified_limit`.

### Adapter boundary for task 04 (`routing.py`)

The LP never imports `routing.py`. `analyze_delivery(graph, request)` takes the contract
`SpatialGraph` + `RoutingRequest`; `resolve_model_inputs(graph, request) -> ModelInputs`
is the only interpretation step. What the graph produced by task 04 must satisfy:

1. One physical resource = one `CapacityGroup`, charged **once per traversal** at its
   canonical crossing (sequential arcs depicting one traversal must not each carry the
   `ResourceUse`); alternative paths through a splitter/inserter reference the same group.
2. Lanes are aliases only; arcs/feeds/outlets may name a lane, and the LP resolves
   arc source / export / surplus → lane outgoing port, arc target / feed → lane incoming
   port. **Activity endpoints on a lane** (contract says "should" be concrete) are
   resolved the same way: an input on a lane draws from its outgoing port, an output on a
   lane enters its incoming port.
3. Conditional arcs carry named conditions; an arc with several conditions is open only
   when all are enabled under `explicit`. If task 04 needs "any" semantics, split arcs.
4. Anything unsupported is a `TopologyGap` or a non-`supported` entity; the LP calls
   `unresolved_reasons` and withholds every bound when it is non-empty.
5. Arrays are in deterministic order (variable/row order and witness order follow it).
6. Every arc/group/activity has evidence IDs; finding and bound evidence is drawn from
   the constraint cut's objects (falling back to the outlet endpoint, then the first
   graph evidence ID).

Optional direct use: `solve_stage(graph, request, inputs, stage, options)` and
`inputs.with_group_capacity({...})` for what-if analysis.

### Proposed shared edits (adopted in contract 1.1.1; gap closed)

- **`findings.py`, `BoundScenario.objective_export_id: str | None`** was proposed here
  because a `feasible` objective (`export_id` null) could carry no `BoundScenario`, so its
  routing infeasibility certificate was inexpressible and `insufficient` unreachable.
  Task 00 adopted it in 1.1.1 with the infeasibility-only restriction (null ID ⇒
  `solver_state == "infeasible"`, `value` null). `blueprint_plan` now emits that scenario
  and reports the case as `insufficient`; see §7 (Follow-up). The interim `partial` +
  limitation-line workaround is gone.
- No other contract change is needed; `unresolved_reasons` and `declared_assumptions`
  are consumed as-is.

## 3. Commands, results, fixtures

```sh
.venv/bin/python daemon/tests/fixtures/routing_plan/cases.py          # prints every case, expectation, sizes
.venv/bin/python -m pytest daemon/tests/test_blueprint_plan.py -q     # 29 passed in 3.6 s
make test                                                             # 240 passed in 14.1 s, 0 skipped
git diff --check                                                      # clean
```

`make test` baseline was 143; the growth includes other agents' new files
(`test_blueprint_view.py`, `test_transport_prototypes.py`, amended contract tests) plus
these 29. No test was skipped: the game data dump is present, so the motivating-scenario
test ran (it skips with a message when `data-raw-dump.json` is absent). No failures in
files I do not own were observed at the final run.

Reproducible fixtures: `daemon/tests/fixtures/routing_plan/cases.py` (10 synthetic cases,
graph + request + expectation, built through `parse_graph`/`parse_request`), and the
task 00 fixtures in `daemon/tests/fixtures/routing_contracts/` (all five small cases and
`large_layout.json` are analysed in the tests; numbers are re-derived by hand in the
test comments, never read from the fixture's `result`).

Acceptance coverage (all hand-solved, with the plausible-wrong value noted where relevant):

| case | aggregate / budget / routing | status | wrong implementation would give |
| --- | --- | --- | --- |
| competing items on one lane (`competing_items`) | 10 / 10 / **7.5** | feasible_relaxed | per-item lane copies: 10 |
| two pickups through one inserter (`shared_inserter`) | 10 / 10 / **5** | feasible_relaxed | per-arc copy: 10; double charge: 2.5 |
| arc crossing inserter 5 and lane 3 | 10 / 10 / **3** | feasible_relaxed | ignoring one resource: 5 |
| two ports one budget (fixture `shared_budget`) | 20 / 5 / 5 | feasible_relaxed | per-port budgets: 10 |
| blocked byproduct (no scrap outlet) | 0 / 0 / 0; minimum 1 → all stages infeasible | feasible_relaxed / insufficient | implicit sink: 10 |
| byproduct with 3/s surplus outlet | 3 / 3 / 3 | feasible_relaxed | |
| blocked export (fixture) | 10 / 10 / infeasible | insufficient | |
| disconnected producer (fixture) | 5 / 5 / infeasible, shortfall ≥ 1 | insufficient | |
| direct pass-through + exact gear export | 20 / 6 / 6 | feasible_relaxed | |
| budget-infeasible exact export | 20 / infeasible / infeasible, shortfall ≥ 5.5 | insufficient | |
| mixed machine variants (speed + pinned yield 1.2) | 6.8 / 5.8 / 5 | feasible_relaxed | |
| explicit furnace assignment (synthetic + fixture) | 10 / 5 / 5; no override → partial; iron-plate override → 0 | | |
| unsupported possible bridge (synthetic + fixture) | — | partial, no bounds/witness | |
| unknown power | — | partial | |
| conditional gate explicit-disabled / enabled / relax_open | ∞ / 10 / infeasible · 10 · 10 (+flag) | insufficient / feasible_relaxed | |
| unknown inserter capacity | 10 / 10 / 10 with `unknown_capacity_unlimited` on routing only | feasible_relaxed | |
| series of three tight constraints | 5; counterfactual lane_1→10 still 5; all three relaxed → 10 | | "tight ⇒ upgrade helps" |
| belt loop | ∞ / 10 / 10; zero flow on loop arcs after cleanup | feasible_relaxed | |
| motivating budget scenario (DB coefficients, one pool) | unlimited / **8/7** / 8/7 | feasible_relaxed | |
| large 3200-lane fixture | 15 / 5 / 5 | feasible_relaxed | |

Property tests: relaxing routing recovers the budget bound (stage subset run, widened
lane, ample lane); raising a budget never lowers the optimum (10→5, 12→7, 4→infeasible,
competing case 20→40 unchanged); results are deterministic (`result_hash` equal across
runs, findings sorted by stable ID); doctored witnesses (export +1, over-budget import,
missing export, exact export under-delivered) are rejected by the verifier; the
verifier rejects the exact allocation a per-item-copy LP would emit (20 on a 15 lane).

Model sizes and timings (this machine, Apple Silicon, SciPy 1.18.1/HiGHS):

| model | variables | rows | nonzeros | build | solve | cleanup | certificate | verify |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| competing_items routing | 26 | 34 | 60 | 0.04 ms | 0.6 ms | 0.7 ms | 0.1 ms | 0.04 ms |
| large_layout routing | 3202 | 9601 | 9603 | 5 ms | 6 ms | 8 ms | 3.5 ms | 0.3 ms |
| large_layout all three stages + result assembly | | | | **0.30 s** total (contract parse of the fixture: 2.5 s, not part of the LP) | | | | |

Tolerances: HiGHS primal/dual feasibility 1e-9; residual/bound verification relative
1e-7 (`TOLERANCE`, also the witness tolerance); dual-certificate reduced-cost threshold
1e-9; contract nesting 1e-8 satisfied by construction. Default `time_limit_s` 20 per
solve, `max_variables` 2,000,000, `max_nonzeros` 8,000,000.

## 4. Before/after counterexample

`competing_items`: m1 makes `item-a` (10/s), m2 makes `item-b` (10/s), both onto belt 3
(lane 15/s) feeding m4 (`1 a + 1 b → 1 c`, 10/s). A model with a per-item copy of the lane
ceiling (a ≤ 15, b ≤ 15) reports 10 c/s. This model reports **7.5**, and its certificate is
the cut "capacity group lane_3 (multiplier −0.5, contribution −7.5)" together with the
conservation rows of *both* `item-a` and `item-b` at belt 3's exit and m4's inventory — a
multi-item explanation, not one item's shortest path. `verify_allocation` on the wrong
model's allocation reports "capacity group lane_3: 20 exceeds 15". The budget-stage run of
the same model (delivery relaxed) returns 10, matching the wrong model's number, which is
exactly the difference the routing stage is meant to expose.

## 5. Assumptions, unsupported mechanics, unmet gates

Certified vs estimate:

- **Certified upper bounds**: every finite `BoundScenario.value` (dual certificate,
  recomputed) and every `delivery_upper_bound` finding; the positive shortfall lower bound
  in an infeasibility certificate.
- **Non-claims**: `unlimited` values.
- **Estimates / incumbents (labelled as such)**: the witness (a feasible continuous
  allocation, never an achievable rate), the per-export split "minimum-shortfall
  allocation is short by …" inside an infeasibility certificate, and timings.
- **Unknowns**: anything relaxed via `unknown_capacity_unlimited`; results carry no claim
  about it beyond the disclosed relaxation.

Modelling decisions to review:

- Budget stage keeps feed ceilings (quantity constraints), aggregate drops them; only
  declared feeds import at any stage (a budget without a feed gets an info finding and
  imports nothing).
- Activity endpoints on lanes are resolved as described in §2 (adapter boundary).
- Multi-condition arcs use "all enabled".
- `feasible` objective: c = 0 at every stage, so no stage has a value and no optimal
  scenario exists; satisfiable → `feasible_relaxed` with a witness and no scenarios;
  routing-infeasible → `insufficient` with exactly one scenario, the null-ID routing
  infeasibility certificate (1.1.1). Looser stages that are also infeasible carry no
  scenario (the contract would admit them; only the routing certificate is required and
  emitted).
- Finding evidence and scope are derived from the dual cut; when the cut has no graph
  object (e.g. only the sink ceiling), evidence falls back to the outlet endpoint or the
  first graph evidence ID.

Unmet gates (explicit):

- **Integrated acceptance against real graphs is not met**: tasks 02–04 have not landed,
  so no adapter-produced graph, real feed/export assignment, real capacity evidence or
  pilot request was analysed. Every number above is from synthetic contract fixtures and
  is not game validation.
- The motivating 8/7 science/s cross-check uses the existing solver's recipe database
  (coefficients asserted against the hand table) on a single-pool graph; it is a
  budget-only arithmetic check, not a routing result, and it needs the local data dump.
- No inserter/belt/splitter mechanics are modelled beyond the contract's group
  arithmetic; no power, circuits, quality, fluids, modules or beacons.
- Not exercised through MCP/CLI (no public surface registered; integration owner's task).

## 6. Next

Task 04 can target `resolve_model_inputs` directly with the requirements in §2; once its
graphs exist, the integrated acceptance run is `analyze_delivery(graph, request)` on the
pilot request plus a hand-derived cross-check on at least one real sub-block. The
`BoundScenario.objective_export_id` proposal is settled (1.1.1, consumed in §7); nothing
from this task blocks task 07's schema registration.

## 7. Follow-up (1.1.1): nullable objective export consumed

Starting snapshot: same HEAD `0b0f3da` plus the working tree after the task 00 amendment
(contract 1.1.1) and with task 06 (viewer) possibly running. Model: Claude (Fable 5.1).
Contract version consumed: **1.1.1**.

Changed (owned files only): `daemon/factoribot/blueprint_plan.py`,
`daemon/tests/test_blueprint_plan.py`, `daemon/tests/fixtures/routing_plan/cases.py`
(`blocked_byproduct(objective=...)` kwarg only), this document. `routing_lp.py` untouched.

What changed in `analyze_delivery`:

- A certified routing infeasibility is `insufficient` under both objectives (was
  `partial` for `feasible`, which was indistinguishable from unresolved topology).
- Feasible-objective branch: when the routing stage is infeasible, emit exactly one
  scenario — stage `routing`, `objective_export_id` null, `solver_state` `infeasible`,
  `value` null, the routing certificate, evidence from the cut with the first requested
  export's outlet as the fallback anchor (the objective export's outlet under
  `maximize_export`), the stage's relaxations. No aggregate/budget scenario is emitted:
  under c = 0 those stages have no value to claim, and the contract rejects any value
  under a null ID at construction.
- The `delivery_insufficient` error finding stays as the readable explanation (now
  without the "Contract 1.1.0 cannot carry…" clause) and the limitation line is removed;
  the `feasibility_only` info finding remains for the satisfiable case.
- Maximize branch unchanged apart from sharing the evidence-anchor variable.

Before/after: `disconnected_circuit` fixture with only the objective switched to
`feasible` (request re-sealed). Before: `partial`, no scenario, certificate only in the
finding text plus a limitation line. After: `insufficient`, one scenario
`(routing, None, infeasible, None)` whose certificate is the same cut the maximizing
request reports (`conservation of electronic-circuit …`, shortfall ≥ 1). Counterexample
kept in the test: inserting the budget-stage value 5 as a null-ID `optimal` scenario into
that result is rejected by `parse_result` ("can only certify infeasibility").

Tests added (`test_blueprint_plan.py`, hand-derived expectations in comments):

- `test_feasible_objective_infeasibility_is_one_null_id_routing_scenario` — fixture
  above (validate_result + JSON round trip via `parse_result`; looser stages `feasible`
  with no value; no `feasibility_only` finding; no limitation line) plus the synthetic
  `blocked_byproduct(gear_minimum=1, objective=None)` where all three stages are
  infeasible and still only the routing scenario appears.
- `test_feasible_objective_satisfiable_has_witness_and_no_scenarios` — `pass_through`
  feasible: `feasible_relaxed`, no scenarios, witness with gear_out = 2 (exact), iron_out
  = 0 (minimum, cleanup drives it down), iron_feed = 4, crafts = 2; same status shape on
  the `shared_budget` fixture switched to feasible.
- `test_maximize_objective_unchanged_by_the_feasible_branch` — `disconnected_circuit`
  maximizing keeps `(aggregate, product, optimal, 5)`, `(budget, product, optimal, 5)`,
  `(routing, product, infeasible)`; `pass_through` keeps 20 / 6 / 6 with a witness.
- The existing feasibility test now expects `insufficient` for the budget-infeasible
  feasible case (it asserted the interim `partial`).

Commands and results:

```sh
.venv/bin/python daemon/tests/fixtures/routing_plan/cases.py          # all cases print; blocked_byproduct unchanged
.venv/bin/python -m pytest daemon/tests/test_blueprint_plan.py -q     # 32 passed
make test                                                             # 280 passed in 22.2 s, 0 skipped, 0 failed
```

Unchanged gates: everything in §5 (no real graphs, no game validation, no MCP/CLI
surface). The viewer (task 06) may want to render a null-ID routing scenario as
"infeasible under a feasibility request"; that is its file, not changed here.
