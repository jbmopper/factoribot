# Blueprint routing — independent release review (task 08)

Independent adversarial audit of the first routing release. The reviewer did not
implement the graph, the LP, the viewer or the public surface. The contract,
design, prior review, mechanics evidence and fixture READMEs were read **before**
any implementation module, so the expectations below are derived from the
specification rather than inherited from the code.

Date: 2026-09-09. Model: Claude (Opus 5). Contract version reviewed: **1.1.1**.

## Follow-up status — 2026-09-11

Coordinator status update, not a replacement for the independent audit below.
Checked HEAD `664662e` plus the current uncommitted tranche. A fresh `make test`
completed with **625 passed, 0 failed, 0 skipped in 129.72 seconds**. The original
review's revision manifest and reproduction observations remain historical.

| Finding | Current disposition |
| --- | --- |
| F-1 (medium) | Fixed: both MCP schemas accept provenance; pilot replay and mismatched-provenance regression coverage pass. |
| F-2 (medium) | Fixed: capability reason is derived from evidence counts; zero/one-observation regression coverage passes. |
| F-3 (low) | Fixed: unknown capacities aggregate by kind; the declared-assumption pilot example now has five findings, with bounds and relaxations unchanged. |
| F-4 (low) | Open: internal non-finite RHS can raise a bare SciPy error; no valid public-request path was found. |

Fix evidence is in the [07 follow-up](blueprint-routing-handoffs/07-public-integration.md)
and [05 follow-up](blueprint-routing-handoffs/05-delivery-bounds.md). Evidence
packaging is complete per the [02b handoff](blueprint-routing-handoffs/02b-evidence-packaging.md).
The release decision stays **conditional**: 0 of 16 rules have observations,
the real pilot declarations remain missing, and the connected MCP process has
not been verified after a reload. See the
[next-run checklist](blueprint-routing-next-run.md) for remaining acceptance work.

## 1. Exact revision reviewed

`git rev-parse HEAD` → **`664662e975dba2092aabeade322a27cb86bb0af3`**

The working tree is dirty; the review covers HEAD **plus** the uncommitted patch
manifest below (`git status --short`). Nothing was committed.

```
 M README.md
 M daemon/factoribot/blueprint.py
 M daemon/factoribot/blueprint_plan.py
 M daemon/factoribot/blueprint_view.py
 M daemon/factoribot/blueprint_view_assets/view.js
 M daemon/factoribot/cli.py
RM daemon/tests/fixtures/routing_mechanics_observations/CAPTURE.md -> daemon/factoribot/evidence/routing_mechanics_observations/CAPTURE.md
RM daemon/tests/fixtures/routing_mechanics_observations/README.md -> daemon/factoribot/evidence/routing_mechanics_observations/README.md
R  daemon/tests/fixtures/routing_mechanics_observations/manifest.json -> daemon/factoribot/evidence/routing_mechanics_observations/manifest.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/belt.side_load.lane_assignment.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/belt.side_load.lane_assignment.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/belt.straight.lane_capacity.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/belt.straight.lane_capacity.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/belt.transfer.belt_to_belt.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/belt.transfer.belt_to_belt.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/belt.turn.lane_behavior.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/belt.turn.lane_behavior.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/circuit.control_state.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/circuit.control_state.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/inserter.endpoints.pickup_drop_tiles.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/inserter.endpoints.pickup_drop_tiles.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/inserter.rate.cycle_and_stack.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/inserter.rate.cycle_and_stack.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/machine.activity.assembling_machine_2.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/machine.activity.assembling_machine_2.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/machine.activity.electric_furnace.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/machine.activity.electric_furnace.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/power.supply_assumption.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/power.supply_assumption.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/splitter.lane_split.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/splitter.lane_split.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/splitter.priority_and_filter.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/splitter.priority_and_filter.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/underground.lane_mapping.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/underground.lane_mapping.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/underground.pairing.conflict.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/underground.pairing.conflict.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/underground.pairing.range.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/underground.pairing.range.json
R  daemon/tests/fixtures/routing_mechanics_observations/records/unsupported.entity_visibility.json -> daemon/factoribot/evidence/routing_mechanics_observations/records/unsupported.entity_visibility.json
RM daemon/tests/fixtures/routing_prototypes/README.md -> daemon/factoribot/evidence/routing_prototypes/README.md
RM daemon/tests/fixtures/routing_prototypes/generate.py -> daemon/factoribot/evidence/routing_prototypes/generate.py
R  daemon/tests/fixtures/routing_prototypes/manifest.json -> daemon/factoribot/evidence/routing_prototypes/manifest.json
R  daemon/tests/fixtures/routing_prototypes/pilot_coverage.json -> daemon/factoribot/evidence/routing_prototypes/pilot_coverage.json
R  daemon/tests/fixtures/routing_prototypes/prototypes.json -> daemon/factoribot/evidence/routing_prototypes/prototypes.json
R  daemon/tests/fixtures/routing_prototypes/raw_prototype_slice.json -> daemon/factoribot/evidence/routing_prototypes/raw_prototype_slice.json
 M daemon/factoribot/mcp_server.py
 M daemon/factoribot/routing_lp.py
 M daemon/factoribot/spatial.py
 M daemon/factoribot/tools.py
 M daemon/factoribot/transport_prototypes.py
 M daemon/pyproject.toml
 M daemon/tests/fixtures/routing_spatial/generate.py
 M daemon/tests/fixtures/routing_spatial/pilot_sample.json
 M daemon/tests/test_blueprint_plan.py
 M daemon/tests/test_transport_prototypes.py
 M docs/blueprint-routing-prompts/NEXT-STEPS.md
 M skills/factoribot/SKILL.md
 M skills/factoribot/references/development.md
?? daemon/factoribot/routing.py
?? daemon/factoribot/routing_public.py
?? daemon/factoribot/transport.py
?? daemon/tests/fixtures/routing_public/
?? daemon/tests/fixtures/routing_transport/
?? daemon/tests/test_mcp_routing.py
?? daemon/tests/test_routing.py
?? daemon/tests/test_routing_certificate_regressions.py
?? daemon/tests/test_routing_public.py
?? daemon/tests/test_routing_public_pilot.py
?? daemon/tests/test_routing_reporting_regressions.py
?? daemon/tests/test_transport.py
?? daemon/tests/test_viewer_provenance_regressions.py
?? docs/blueprint-routing-handoffs/02b-evidence-packaging.md
?? docs/blueprint-routing-handoffs/04-transport-graph.md
?? docs/blueprint-routing-handoffs/07-public-integration.md
?? docs/blueprint-routing-handoffs/fix-a-certificates.md
?? docs/blueprint-routing-handoffs/fix-b-finding-ids.md
?? docs/blueprint-routing-handoffs/fix-c-viewer-provenance.md
?? skills/factoribot/references/routing.md
```

This review adds exactly two files: `daemon/tests/test_routing_audit.py` and this
document. No production module, existing test, fixture or other document was
edited.

## 2. Release decision

**Conditional pass, with the advertised scope narrowed as stated in §6.**

The mathematics is sound: every soundness invariant I attacked held, including
all three defects the prior review found, which are genuinely repaired rather
than papered over. No material (severity-high) defect was found, and I did not
manufacture one to fill the list. Two medium and two low findings are recorded in
§7; none of them can turn an unsound number into an advertised bound.

The release is **not** ready to advertise any validated game mechanic, and it
correctly does not try to. The blocking gate is unchanged and is not this task's
to close: **zero** controlled game observations exist.

| Gate | Verdict | One-line basis |
| --- | --- | --- |
| 1. Mathematical conservation and bounds | **PASS** | 40 hand-derived adversarial cases match the hand value exactly; every unsoundness attempt was refused |
| 2. Validated game mechanics | **FAIL (gate unmet, honestly reported)** | 0 of 16 rules observed; 0 `exact` arcs on the pilot; the system advertises exactly this |
| 3. Usefulness on the pinned real blueprint | **PARTIAL / UNVERIFIED** | The pilot imports, analyses and renders, and correctly withholds every bound; no useful *throughput* claim is reachable, and the one reachable number is structural |

## 3. Gate 1 — mathematical conservation and bounds: **PASS**

Evidence: `daemon/tests/test_routing_audit.py` (72 tests, all passing). Every
expectation was hand-derived from the contract with the wrong-implementation
value written next to it.

### 3.1 Conservation, connectivity and shared capacity

| Adversarial case | Hand-derived expectation | Plausible-wrong value | Observed |
| --- | --- | --- | --- |
| Producer with no route to the outlet | aggregate 10, budget 10, **routing 0** | 10 everywhere (implicit transport) | exact match |
| Outlet on an unreachable belt | routing 0 | 10 | exact match |
| Unsupported entity with `may_connect: true` | `partial`, no bound, no insufficiency | erase the bridge, certify "disconnected" | exact match |
| `may_connect: false`, **structural** evidence | bound admitted, routing 0 | — | exact match |
| `may_connect: false`, **estimated** evidence | withhold (`partial`) | accept the disconnection proof | exact match |
| Two feed ports, one 10/s budget, 2 iron/craft | budget/routing **5**, aggregate 100 | **10** (budget copied per port) | exact match |
| Two items on one lane, cap ∈ {5,10,15,30,100} | min(10, cap/2) = 2.5/5/**7.5**/10/10 | min(10, cap) = 5/10/**10**/10/10 | exact match at all 5 points |
| Three 15/s belts in series | 15 | 45 (segments summed) | exact match |
| Three arcs naming one 15/s group | 5 (3f ≤ 15) | 15 (charged once per material) | 5.000000000000001 |
| Finite external-removal ceiling 3/s | 3 at every stage | 10 (budget) | exact match |
| `buffer` sink | rejected | accepted as a sink | rejected |
| Export at an incoming port | rejected | accepted | rejected |
| Sink ceiling below the requested rate | rejected | accepted | rejected |
| Two furnaces, one assigned | `partial` (entity 2 ambiguous) | assignment generalised to both | exact match |
| Override outside the candidate set | rejected | accepted | rejected |
| Both furnaces assigned, 10 stone/s at 2/craft | 5 bricks/s, alternative excluded | 10 (both alternatives enabled) | exact match |
| Raising the iron budget 2→40 | monotone non-decreasing | a dip | monotone |
| `pass_through` at budget 20 | aggregate 20, budget 16, **routing 11** | routing 16 (lane ignored) | exact match |

The `5.000000000000001` and the `15.000000045002` in §3.2 are both *above* the
true value. For an `upper` bound that is the safe direction: the implementation
rounds derived ceilings outward, never inward.

### 3.2 Numerical certificates — the prior review's Fix A, re-exercised

Both reproductions from `NEXT-STEPS.md` are genuinely fixed:

1. `LPModel` with `x ≥ 0`, no ceiling, cost `-5e-10`. **Before**: status 0,
   `value 0, valid=True`. **Now**: `valid=False`, `value=-inf`,
   `uncertified_variables=(('x',),)`. The true optimum is −∞ and nothing is
   claimed.
2. Through the task 04/05 builder: one iron per craft, `5e-10` gear per craft,
   unlimited craft capacity, machine time, supply and sink. **Before**: certified
   zero bounds. **Now**: status `solver_limit` with no finite bound. The true
   maximum is unbounded, and withholding is sound.

The fix is not a tolerance change: the control case (identical layout with a
4 crafts/s ceiling) still returns **exactly 2e-09 = 4 × 5e-10** at all three
stages, so ordinary arithmetic is untouched.

New variants I constructed, all refused or sound:

- Tiny negative cost on a **free** column (`lower=-inf`), both sign directions,
  and a denormal-scale cost `-1e-300` → withheld in every case.
- **Near-degenerate yield**: `min -1e-12 x` with `x ≤ 1e12` (true optimum −1.0).
  The derived ceiling is `1.000000001e12` ≥ 1e12 and the certified maximum is
  1.0. Correct and still useful.
- **NaN and −inf multipliers** → refused ("solver returned non-finite
  multipliers"). **+inf** is clamped to 0, which is legitimate for a `≤` row, and
  yields the weaker-but-true box bound −5.0 ≤ −3.0.
- **Doctored certificate**: multipliers −1000, −0.5, 0, +5 injected into a model
  whose true maximum is 3.0. Every accepted certificate gave an upper bound
  ≥ 3.0 (e.g. 3000). A hostile multiplier can only *weaken* the bound, never
  falsely tighten it, because `r` is recomputed exactly.
- **Equality row with an infinite RHS** is not constructible through any request
  path (RHS come from finite capacities, finite budgets, or 0). Reached directly
  through the internal `LPModel` API, `solve_lp` raises `ValueError` from SciPy
  before `_weak_duality`'s own infinite-RHS guard runs. Recorded as F-4 (low).

**`fix-a-certificates.md`'s two central claims check out.**
`_repair_step` returns exactly `0.0` on a column whose own cost points the unsafe
way — it cannot rescue an unbounded objective — and returns a positive step only
when the violation is strictly smaller than the column's own safe cost.
`implied_upper_bounds` was checked against the whole feasible set by randomised
counterexample hunt: 60 random models, each coordinate maximised by LP, asserting
no derived ceiling ever cuts below the true maximum. No violation found.

Witness handling is independently verified: the published witness passes
`verify_allocation` (a graph walk sharing no code with the LP builder) with
conservation residual < 1e-7, and a fabricated allocation with 5/s added to an
export is rejected.

### 3.3 Finding identity — the prior review's Fix B, re-exercised and extended

Both reproductions are fixed, and the merge preserves every explanation:

- **Three** mechanics-altering mods + unknown power → `partial`, no
  `ContractError`, distinct IDs. The three mods share one contract identity
  (same code, empty scope, no evidence) and are merged into one finding whose
  message names **AlterMod1, AlterMod2 and AlterMod3**. Nothing is dropped.
- **Three** size-limited stages → `solver_limit` with
  `solver_limit_aggregate/_budget/_routing`, three distinct IDs, no bounds.
- **Parallel disabled arcs** (two conditional arcs, identical endpoints and
  evidence) merge into one finding naming **cond1, cond2, gate_a and gate_b**.
- Repeated analysis is byte-identical (`result_hash` stable), findings sorted by
  ID.

**Extending the "other repeated categories" table to task 04's codes** (the
fix-b handoff explicitly asks for this and its table covers only delivery
findings): `routing.py` emits 20 graph finding codes into
`TransportGraph.findings`, which is *not* the `AnalysisResult.findings` list that
`validate_result` checks for uniqueness — so a collision there would not raise,
it would silently merge in the viewer. I tested this on the real 2771-entity
pilot: **529 graph findings, 529 distinct IDs, 0 collisions** across 11 emitted
codes. Every task 04 code carries entity or endpoint scope, which is what keeps
them apart. No defect; the table can be extended with "task 04 graph findings —
entity/endpoint scope — no".

## 4. Gate 2 — validated game mechanics: **FAIL (gate unmet, and honestly reported)**

This is a fail on *evidence*, not on conduct. The system reports its own gate
correctly everywhere I could reach it.

Read directly from `daemon/factoribot/evidence/routing_mechanics_observations/`,
record by record, before reading any code:

| Status | Count | Rules |
| --- | --- | --- |
| `observed` | **0** | — |
| `documented-only` | 6 | belt.straight.lane_capacity, inserter.endpoints.pickup_drop_tiles, inserter.rate.cycle_and_stack, machine.activity.assembling_machine_2, machine.activity.electric_furnace, unsupported.entity_visibility |
| `pending` | 10 | belt turn / side-load / belt-to-belt, all three underground rules, both splitter rules, circuit.control_state, power.supply_assumption |

Every one of the 16 records has `measurement: null`, `environment.game_version:
null` and `environment.save: null`. `manifest.json` sets
`mechanics_gate_unmet: true`.

The **prototype extract is also uncertified**: `routing_prototypes/manifest.json`
records `environment_status: "unidentified"`, `game_version: null`,
`declared_mods: null` and `matches_target_profile: "unknown"`, and its own notes
say the extract "is NOT certified as base-2.0.76-normal-v1". The contract fixes
the profile at exactly 2.0.76, so even the prototype half of the mechanics claim
rests on an unidentified dump.

### Supported mechanics that can actually be advertised

**As exact: none.** This is the expected answer and the system produces it.

- `semantics_for(status)` returns `relaxed` for all 16 rules; only `observed`
  would return `exact`.
- On the real pilot the arc semantics are **7848 `relaxed` and 3812
  `conditional`. Zero `exact`.**
- `routing_capabilities()["arc_semantics_available"]` is
  `["relaxed", "conditional"]`.
- 623 of 4576 capacity groups are `unknown` and are relaxed to unlimited with the
  relaxation recorded (623 `unknown_capacity_relaxed` findings). Those are the
  pilot's 608 bulk inserters and 15 splitters: **no inserter or splitter
  throughput is modelled at all.**

What *may* honestly be advertised today is structural, not mechanical:

1. Lossless import, nested-book identity, geometry and unsupported-entity
   visibility (contract-checked; `unsupported.entity_visibility` is a contract
   rule, not an engine claim).
2. Topology: ports, lanes, arcs, underground pairing candidates, boundary
   candidates — as **possible** connections under `relaxed` semantics.
3. Upper bounds and certified infeasibility **under explicitly declared
   assumptions**, never as achievable rates.
4. The declared prototype set (14 supported names) as *prototype identity*, not
   as validated runtime behaviour.

I verified the capability block is genuinely computed rather than hardcoded: a
fully formed fabricated `observed` record in a scratch copy (the checked-in
record was never touched) moves `observed` 0 → 1, the gate to "partially
observed", and adds `exact` to `arc_semantics_available`. I also confirmed a
record **cannot** become an observation by asserting it: flipping only
`evidence_status` raises `PrototypeError: an observed record needs
['measurement_interval_s', 'setup_blueprint']`. That is the right check to have.

## 5. Gate 3 — usefulness on the pinned real blueprint: **PARTIAL / UNVERIFIED**

The pilot `daemon/tests/fixtures/wip_science.txt` (2771 entities) was run end to
end through the documented §10 entry points.

**What works.** Import, spatial model, transport graph (8392 ports, 3832 lanes,
11660 arcs, 4576 capacity groups) build in ~6 s; analysis completes in ~8 s; the
viewer renders and is interactive. `routes request` reports exactly the three
`ee-super-substation` poles as unresolved (`bp/root/e/162`, `/255`, `/1882`) and
`bounds_advertisable: false`; `routes analyze` returns `partial` with **no bounds
and no witness**. That is the correct, contract-mandated outcome, and it is the
single most valuable thing this release does on a real layout: it refuses.

**Why usefulness is only partial.**

- **0 activities are built for the pilot.** All 229 machines (153 AM2 + 76
  furnaces) raise `machine_recipe_unresolved`, so no production is modelled at
  all. The delivery model on this blueprint is pure topology.
- With the three poles declared irrelevant (an experiment, not a claim), the
  bounds become aggregate `unlimited`, budget **60**, routing **0** items/s. The
  0 is a structural fact about two *illustrative* endpoints that are not
  connected — it says nothing about the factory. The fixtures label this
  correctly ("ILLUSTRATIVE DECLARATION, not a measurement") and the result
  repeats the declaration as
  `irrelevant:audit_power:power:power_assumed_available`.
- The motivating question ("can these circuit assemblers deliver?") remains
  **unanswerable** on this blueprint: it needs the real feeds, exports, removal
  services, research, mod manifest, control state, power, and the 76 furnace
  recipes — none of which exist.
- Finding volume is high: the declared-irrelevant run emits **626** findings, 623
  of them `unknown_capacity_relaxed`. Truthful, but see F-3.

Public-surface checks over a **fresh** stdio MCP test server (the user's running
server was never touched or reloaded): both routing tools are exposed; nested
book path `[7, 2]` resolves and `[2, 7]` fails loudly with
`unknown_selection_path`; hostile labels round-trip as escaped JSON string data;
garbage input yields structured `bad_blueprint`; unknown argument keys are
rejected; the 10000-entity and 200-page limits are enforced.

Viewer checks in a real browser (pages served from a scratch localhost server,
since removed): the hostile-label page renders all 6 payload copies as inert
text — 0 injected `<img>`/`<svg>` elements, no handler fired, no console error;
the prototype-only mismatch and missing-prototype-hash pages both display
`STALE: The displayed result's blueprint, prototype or graph provenance does not
match what is loaded here`, while the matching page shows no banner; selecting a
finding highlights exactly its two entities.

## 6. Advertised scope that must be narrowed before release

Not defects in code, but claims the release must not make:

1. No mechanic may be described as *exact*, *validated*, or *game-checked*. The
   correct wording is "possible connections under relaxed semantics".
2. No inserter or splitter throughput number may be presented. Those capacities
   are unknown and relaxed to unlimited.
3. The mechanics profile `base-2.0.76-normal-v1` is a **target**, not a certified
   environment: the prototype extract's own manifest says the build and mod list
   are unidentified.
4. No bound is advertisable for the pilot, and any bound obtained by declaring
   the substations irrelevant must be presented together with that declaration.

## 7. Actionable findings

No finding below can cause an unsound number to be advertised. Ranked by severity.

---

### F-1 (medium) — the MCP surface cannot select a provenance, so the documented pilot flow cannot be replayed over MCP

- **File:line**: `daemon/factoribot/tools.py:362` and `daemon/factoribot/tools.py:418`
  (`"additionalProperties": False` on both routing tool schemas, neither listing
  `provenance`), against `daemon/factoribot/routing_public.py:346`
  (`provenance = str(args.get("provenance") or "game_export")`, which already
  accepts `game_export`, `development_pilot` and `synthetic`).
- **Expected invariant**: the public tools should be able to analyse the requests
  the public CLI seals. `provenance` is part of the graph and therefore of
  `graph_hash`, so it is an identity input, not cosmetic.
- **Counterexample**: seal the pilot request exactly as
  `docs/blueprint-routing-handoffs/07-public-integration.md` §10 and the fixture
  README prescribe (`factoribot routes request --provenance development_pilot`),
  then call `analyze_blueprint_routes` over stdio MCP with that request.
- **Observed**: `isError: true`, `status: "invalid_request"`, finding
  `"Request rejected by the contract validator: request/graph mismatch"`.
  `resolve_layout` never sees a provenance because the JSON-Schema layer rejects
  the key first: passing `provenance` explicitly returns
  `Input validation error: Additional properties are not allowed ('provenance' was unexpected)`.
  Confirmed the hashes differ solely because of provenance: the same blueprint
  gives `graph_hash` `sha256:91e8cf19…` under `development_pilot` and
  `sha256:b7cf71a0…` under `game_export`.
- **Impact**: bounded. Failing loudly is the safe behaviour and no wrong number
  is produced. But the MCP half of the public surface cannot consume the CLI
  half's output, and the only workaround is to ship the whole ~12 MB graph
  document through the `graph` parameter.
- **Owner**: task 07 (integration owner; only it may change MCP schemas).
- **Acceptance test for the fix**: add `provenance` (enum
  `game_export | development_pilot | synthetic`, default `game_export`) to both
  tool schemas, then assert that
  `test_mcp_refuses_a_request_sealed_against_a_different_graph` inverts: the
  sealed pilot request analysed over MCP with `"provenance": "development_pilot"`
  returns `status: "partial"` with the three
  `unsupported entity: bp/root/e/{162,255,1882}` reasons and no bounds. Keep a
  negative case asserting that a *mismatched* provenance still fails with
  `invalid_request`, so identity pinning is not weakened.

---

### F-2 (medium) — the capability block hardcodes "Zero mechanics rules are observed" inside an otherwise evidence-computed structure

- **File:line**: `daemon/factoribot/routing_public.py:1028`.
- **Expected invariant**: the capability block "advertise[s] validated scope
  only" and is documented as "computed from the evidence". A sentence asserting
  the evidence count must not be a constant.
- **Counterexample**: point `transport.load_mechanics` at a record set with one
  complete `observed` record (I used a scratch copy; the checked-in record was
  not modified).
- **Observed**: the same response simultaneously reports
  `mechanics_evidence.observed: 1`, `gate: "partially observed"`,
  `arc_semantics_available: ["exact", "relaxed", "conditional"]` **and** the prose
  "Zero mechanics rules are observed, so every transport arc is relaxed or
  conditional." Self-contradictory.
- **Impact**: latent only. With 0 observed records the sentence is true today, so
  nothing is currently misreported. It becomes wrong on the first successful
  capture — exactly when a reader most needs it to be right.
- **Owner**: task 07.
- **Acceptance test for the fix**: derive the sentence from
  `evidence["observed"]`, then extend
  `test_capability_block_is_computed_from_the_records_not_hardcoded` to assert
  that with one observed record the `advertisable_bounds.reason` no longer
  contains "Zero mechanics rules are observed", and that with the real records it
  still states the unmet gate.

---

### F-3 (low) — 623 near-identical `unknown_capacity_relaxed` findings bury the three that matter

- **File:line**: `daemon/factoribot/blueprint_plan.py:720-730` (one finding per
  unknown capacity group, then one per unknown activity).
- **Expected invariant**: the design requires findings to "explain bottlenecks"
  and the contract requires the relaxation to be disclosed — but disclosure and
  per-entity enumeration are different things. The contract's own guidance is to
  "return compact summaries with paginated detail … rather than forcing the
  entire transport graph into the conversation".
- **Counterexample**: the pilot with the power declaration (§5) returns **626**
  findings, of which 623 are `unknown_capacity_relaxed`, one per bulk inserter
  and splitter.
- **Observed**: `zero_objective` and `delivery_upper_bound` — the two findings a
  user needs — are each 1 row among 626. IDs are distinct and ordering is
  deterministic, so this is presentation, not correctness.
- **Impact**: usability of gate 3 only. No claim is wrong.
- **Owner**: task 05 (`blueprint_plan.py`), coordinated with task 07 for the
  paging/summary presentation.
- **Acceptance test for the fix**: assert that on the pilot the count of
  `unknown_capacity_relaxed` findings is bounded (e.g. one aggregate finding per
  capacity *kind* carrying the entity list, or a capped sample plus a total),
  while `relaxations` still contains `unknown_capacity_unlimited` and
  `validate_result`'s "unknown capacities must be relaxed for upper bounds" check
  still passes.

---

### F-4 (low) — an infinite row RHS crashes `solve_lp` before the certificate layer's own guard

- **File:line**: `daemon/factoribot/routing_lp.py:315` (the `linprog` call), with
  the intended guard at `routing_lp.py` `_weak_duality` ("a row with an infinite
  right-hand side carries a non-zero multiplier").
- **Expected invariant**: the module's contract is that the optimizer's status is
  never the proof and non-finite data is refused, not raised through.
- **Counterexample**: `m = LPModel(); m.variable(("x",), 0.0, inf); r = m.row(("eq",), "eq", inf); m.add(r, 0, 1.0); solve_lp(m, [-1.0], time_limit=10)`.
- **Observed**: uncaught
  `ValueError: Invalid input for linprog: b_eq must not contain values inf, nan, or None`.
- **Impact**: **not reachable from any request.** Row RHS come only from finite
  group capacities (infinite ones add no row at all), finite budgets, conservation
  zeros, and contract-validated finite export rates. This is internal-API
  robustness, recorded so the guard's dead-code status is deliberate rather than
  assumed.
- **Owner**: Fix A owner (`routing_lp.py`).
- **Acceptance test for the fix**: assert that `build_lp` never emits a
  non-finite RHS for any contract-valid `ModelInputs`, and that `solve_lp` raises
  a typed internal error (not a bare SciPy `ValueError`) if one is constructed
  directly.

---

### Checked and clean (no defect found)

Recorded so the next reviewer does not repeat the work: budget sharing across
ports; per-item lane capacity copying; sequential-segment capacity summing;
`buffer` sinks; inventory outlets without a declared service; export role
checking; furnace assignment locality and wrong-recipe overrides; alternative
recipes multiplying machine time; supply-ceiling monotonicity; stage nesting;
achievable-rate wording; cursor identity binding and tampering (negative, boolean,
string and missing-scope offsets all refused); `seal_request` neutrality (it adds
only the seven identity keys and leaves `budgets`, `exports`, `surplus`,
`objective`, `protected` and `assumptions` byte-identical to the operator's
template); undeclared unsupported entities becoming bounds (no path found, via
CLI, direct Python and MCP); task 04 graph finding ID collisions; hostile labels
through the real rendered page and the real MCP transport; nested-book identity;
size limits.

Two behaviours I examined and judged **not** defects: a paging cursor binds to
the last 12 hex characters (48 bits) of the scope hash rather than the whole
hash, but `paginate` always slices the *current* identity's rows, so a colliding
cursor could only produce a wrong offset into correct data, never data from
another graph; and a cursor issued for one section replayed on another returns an
honestly labelled page (`section`, `offset`, `total` all correct).

## 8. Commands run

```sh
git rev-parse HEAD                                              # 664662e975dba2092aabeade322a27cb86bb0af3
git status --short                                              # patch manifest in §1

make test                                                       # 617 passed, 0 failed, 0 skipped (baseline 545 + 72 new)
.venv/bin/python -m pytest daemon/tests/test_routing_audit.py -q # 72 passed

# pilot, end to end (task 07 handoff §10)
.venv/bin/python daemon/tests/fixtures/routing_public/generate.py
.venv/bin/factoribot routes request --bp daemon/tests/fixtures/wip_science.txt \
    --provenance development_pilot \
    --template daemon/tests/fixtures/routing_public/pilot_request_template.json \
    --assignments daemon/tests/fixtures/routing_public/pilot_assignments.json \
    --out <scratch>/pilot_request.json                          # 3 unresolved, bounds_advertisable false
.venv/bin/factoribot routes analyze --bp daemon/tests/fixtures/wip_science.txt \
    --provenance development_pilot --request <scratch>/pilot_request.json \
    --result <scratch>/pilot_result.json --view <scratch>/pilot_audit.html   # partial, no bounds/witness
```

Real stdio MCP was exercised by a **fresh** `python -m factoribot.cli mcp`
subprocess (initialize / tools/list / tools/call), both from throwaway scripts and
from the module-scoped `stdio_server` fixture in the audit suite. **The user's
running MCP server was never contacted and never reloaded**, so nothing here
claims that server exposes new behaviour.

Browser checks used a temporary `http.server` on 127.0.0.1:8971 serving
scratch-rendered pages. The server and every temporary file were removed; no
`git clean`, reset or other bulk cleanup was used.

Skipped checks: none. No test in the suite is skipped. No game observation was
captured — no Factorio installation or disposable save is available in this
checkout, which is precisely why gate 2 fails.

## 9. Remaining first-release acceptance work (updated 2026-09-11)

1. F-1/F-2/F-3 are closed; keep their regression tests. F-4 remains a low-severity
   internal robustness follow-up.
2. Keep the advertised scope within §6: mathematical upper bounds under explicit
   relaxations, with no measured/achievable throughput claim. Revisit wording as
   evidence arrives, including tool descriptions and skill references.
3. Run controlled captures following
   [CAPTURE.md](../daemon/factoribot/evidence/routing_mechanics_observations/CAPTURE.md).
   Gate 2 remains unmet until the relevant evidence is collected and reviewed.
   The `unsupported.entity_visibility` record is a static adapter rule, unlike
   the other 15; resolve its acceptance criteria explicitly rather than inventing
   a game measurement to fill its fields.
4. Collect the real pilot interface and environment declarations, then reseal
   and analyze it. The illustrative request's successful schema validation does
   not establish those declarations as facts.
5. Check the connected MCP process after a restart/reconnect and review the
   complete implementation tranche before committing the intended files.

The [execution checklist](blueprint-routing-next-run.md) gives commands, ownership,
inputs and completion criteria. Passing software tests does not close the game
observation or real-pilot usefulness gates.
