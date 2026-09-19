# Task 20 design handoff — bounded sustained-throughput model

## Review status

This is the required **first deliverable**, not a completed throughput engine.
It freezes a narrow design and reusable validation cases for task 21's independent
design pass. Substantial operating-model implementation is intentionally gated on
that review. The existing `blueprint_plan.py` / `routing_lp.py` solver remains a
separate optimistic-capacity-bound implementation and is not changed or relabelled.

Task 17 contains no `game-observation` capture. Its only capture is explicitly
`synthetic-recorder-test`, so no prediction-versus-Factorio comparison can yet be
made and the validated-throughput gate remains open.

## Selected approach and reuse decision

Use task 16's recommended three-layer architecture:

1. Keep the existing lane-aware graph, explicit feeds/removals, identity checks,
   furnace-assignment provenance and certified LP upper bound unchanged.
2. Add a dedicated, deterministic restricted tick model in
   `daemon/factoribot/sustained_throughput.py` after design review. It consumes a
   validated `SpatialGraph` and `RoutingRequest`; it does not rebuild blueprint
   parsing, topology, recipe arithmetic, or the LP.
3. Compare a prediction only with task 17 captures whose
   `record_kind == "game-observation"`, environment is compatible, stability has
   passed, and a separate comparison binding hashes the capture, graph, request,
   prediction, and feed/export mapping.

No evaluated task 16 project is imported. In particular, no implicit source or
sink, whole-belt collapse, traversal-order allocation, automatic furnace bridge,
or unvalidated inserter-rate shortcut enters this model.

## Frozen first implementation scope

The first approved implementation should be smaller than a general Factorio
simulator. It is an item-only, normal-quality, base-game 2.0.76 adapter over one
selected blueprint leaf.

| Concern | Initially numeric only when | Otherwise |
| --- | --- | --- |
| Straight belts | cardinal, supported base belt; two explicit lanes; exact feed and removal ports; fixed tier | `conditional` while lane motion is documented-only |
| Rear handover / turn / side-load | every used mapping has an observed compatible mechanics record | `unsupported`, with the precise record IDs |
| Splitter | lane mapping, arbitration and any priority/filter behavior have compatible observed records | `unsupported`; never fall back to free LP allocation |
| Inserter | endpoint pair, prototype, research, hand size, control state and finite per-phase timing are all identified by compatible observations | `unsupported`; unknown capacity is not a simulated infinity |
| AM2 / electric furnace | fixed item-only recipe, known finite inventories, powered/no modules/no beacons, and start/completion/output-blocking rules are supported | `unsupported`; recipe-rate arithmetic alone is insufficient |
| Furnace recipe | explicit assignment or current task 19 inference artifact matches the final graph/request identities | `unsupported` or stale; reachability alone never chooses it |
| Underground, circuits, filters, mixed lane items, fluids, qualities, modules, beacons, logistics entities, item-altering mods | not in the first implementation | `unsupported` |

`conditional` may contain a numerical result only for a complete declared
operating semantics resting on documented-only evidence. `supported` requires
all mechanics used by the prediction to have compatible reviewed observations.
`unsupported` contains no predicted sustained rate. Neither status changes the
meaning or availability of a separately computed capacity upper bound.

## Adapter and identity contract

The future internal `ThroughputScenarioV1` is additive; it does not modify routing
schema `1.1.1`. It contains:

- graph, blueprint, prototype, routing-request and mechanics-profile hashes;
- the final task 19 inference-artifact hash when inferred furnaces are used;
- exact initial state and run limits described below;
- an exact base 2.0.76/mod/research/power/control declaration;
- a scenario hash over all of the above.

The adapter rejects a stale hash, `relax_open`, any live conditional arc without
one explicit supported operating choice, a `may_connect` item topology gap,
unknown finite storage, an unknown service time, or an entity/material outside
the frozen subset. It may still request the existing bound report independently;
failure to construct a prediction must not suppress or reinterpret that report.

## Item, lane and state representation

- Time is integer game ticks at 60 ticks/s. Prototype speeds and recipe progress
  are represented as exact rational values; no binary floating-point value is
  used to decide an event or break a tie.
- Each physical belt lane is distinct. It is a finite ordered sequence of item
  tokens with exact longitudinal phase/position and a fixed downstream end. No
  lane can carry more than four item positions per tile; the chosen position and
  collision convention must be confirmed by review/observation before it becomes
  supported mechanics.
- A handover never mixes lanes implicitly. Rear, turn, side-load and underground
  mappings come from the graph plus a compatible mechanics profile. A merge has
  persistent local arbitration state; entity-number or traversal order is not an
  allocator.
- A splitter owns persistent arbitration state for each applicable lane/path.
  With both outputs eligible, an unprioritized splitter alternates according to
  that state; a blocked choice gives the other eligible choice an opportunity.
  Input/output priority and filters are explicit rules, not capacities. These
  transitions remain unimplemented/unsupported until their exact 2.0.76 behavior
  is reviewed against observations.
- An inserter is a finite-state machine (`waiting_pickup`, `moving_to_drop`,
  `waiting_drop`, `returning`) with item/hand contents, endpoint-specific phase
  durations and fixed research. Aggregate items/s is an output of those events,
  never the transition rule. Task 17's aggregate chest-to-chest rate alone is not
  enough to infer every phase duration or any belt endpoint timing.
- A machine has finite typed input/output inventories, recipe progress and a
  blocked-completion state. Ingredients are removed at the supported start event;
  products appear only at a supported completion event with available output
  capacity. Exact Factorio start/reservation ordering is a task 21 review item and
  must remain unsupported until justified.
- Scheduler phases, merge/splitter arbitration, inserter phase/hand, machine
  progress, lane tokens, inventories, accepted feed totals and removed export
  totals are all part of state and deterministic replay.

## Tick scheduling and transitions

The proposed update is synchronous intent/resolve/commit, so Python iteration
order cannot decide competing consumers:

1. Snapshot the complete start-of-tick state.
2. Generate eligible removal, machine, inserter, lane, splitter/merge and feed
   intents from that snapshot.
3. Resolve conflicts only with the owning physical resource's persisted
   arbitration state and its explicitly supported rule. No global entity-order
   tie-break may allocate material.
4. Commit the accepted intents simultaneously, then advance rational progress
   and local arbiter state.
5. Verify nonnegative finite inventories and exact per-item conservation.

The relative Factorio order of removal, inserter, machine and belt effects is not
yet established. Task 21 must either accept a specific order backed by evidence
or narrow the first implementation so no claimed case depends on that order.

Feeds expose availability up to both their feed ceiling and globally shared item
budget. A feed creates an item only when its destination accepts it. Rejected
availability is `unused_supply`; it is neither forced intake nor an off-layout
inventory. Exports count only items accepted by an explicit ongoing removal
service. A dangling output, full finite inventory, or missing removal creates
back-pressure and eventually zero sustained export if no other sink exists.

Initial state defaults to explicitly empty only when the scenario says `empty`.
Otherwise it enumerates every nonempty lane position, inventory, machine progress,
inserter hand/phase and arbitration state. Initial material is included in the
conservation ledger and cannot be reported as feed or steady production.

## Bounded execution and termination

Defaults proposed for the first implementation are frozen in
`sustained_throughput.py` and the design-case manifest:

- warmup: 3,600 ticks;
- measurement window: 3,600 ticks;
- at least 3 and at most 8 contiguous windows;
- maximum 32,400 total ticks (warmup plus 8 windows);
- at most 2,048 modeled entities, 262,144 resident item tokens and 65,536 stored
  state signatures.

At every window boundary the engine records a hash of the entire dynamic state
excluding cumulative counters. An exact repeated state establishes a fixed point
or a periodic orbit. A periodic orbit is reported separately with its period and
cycle-total rates; it is not disguised as a fixed point. If no repeat exists,
window rates and every inventory slope must remain within exact model tolerance
for three consecutive windows before `steady_window` is reported. Otherwise the
result is `nonconverged` at the window/tick/state limit and contains no sustained
rate. Hitting entity/token/work limits is `work_limit`, also without a rate.

Internal conservation is exact integer/rational accounting. The only tolerance
used for model checks is zero. Observation comparison is deliberately looser and
is frozen before seeing any game results:

```
allowed_error_items_per_s = max(1 / measurement_window_seconds,
                                0.005 * max(abs(predicted), abs(measured)))
```

Thus a 60-second window permits at least one item's quantization error and a 0.5%
relative error at higher rates. A predicted zero matches only when collected
count is at most one item per window and the capture's retained-inventory change
also satisfies task 17 conservation. Changing these tolerances after observing a
failure requires a version change and rationale, not silent calibration.

## Output meanings

The proposed `ThroughputPredictionV1` fields are separate from the existing
`AnalysisResult` bound and from task 17 capture data:

- identity: schema/model/scenario/graph/request/profile/inference hashes;
- `rate_kind: predicted_sustained_rate` and status
  `supported | conditional | unsupported | nonconverged | work_limit`;
- exact assumptions, required mechanics records and unsupported reasons;
- per item: available supply, accepted import, unused supply, activity
  consumption, gross production, explicit net export and inventory delta;
- per entity/resource: utilization, queue/full/empty time, blocked/starved time,
  and localized restriction candidates;
- termination: ticks, windows, fixed/periodic state information, rate trace,
  work counters and conservation ledger;
- optional reference to an independently produced bound result/hash and a check
  that a numerical prediction does not exceed that bound. The bound is not copied
  into the prediction as an achieved rate.

A separate `ThroughputComparisonV1` binds the prediction hash to the SHA-256 of a
task 17 raw capture plus explicit feed/export-counter mapping. It records
`predicted`, `measured`, `difference`, frozen tolerance and match status per item.
It refuses synthetic records, nonsteady captures, incompatible game/mod/research/
power/control declarations, mismatched scenario/setup identities, or incomplete
counter mappings. A measurement is an observed interval rate, never a maximum.

A localized restriction is descriptive until controlled perturbation shows a
causal improvement. The validation corpus includes a belt-capacity perturbation
that changes no output while supply remains limiting.

## Validation corpus prepared for task 21

`daemon/tests/fixtures/sustained_throughput/cases.json` is a strict, synthetic
mathematical-reference manifest. It does not claim game evidence. Each numerical
steady ledger is independently checked item by item as:

```
accepted_import + gross_production
  = activity_consumption + net_export + stored_delta
```

The cases cover:

| Case | Independent expectation | Current prediction gate |
| --- | --- | --- |
| single fast-belt lane | 15 items/s documented reference | conditional; no observation |
| dual fast-belt lanes | 30 items/s documented reference, 15/lane | conditional; no observation |
| two-lane merge | no more than 15/lane or 30 total | unsupported lane/merge arbitration |
| unequal consumers | with 9/s supply and 3/s cap on A, work-conserving split is A=3, B=6; never first-branch greedy | unsupported splitter rules |
| output priority | priority B receives the under-supplied 9/s before A | unsupported exact priority mapping |
| fast inserter | finite chest-to-chest rate required; no number is invented | unsupported until game capture/timing |
| furnace chain | direct ideal inventories give 0.625 plate/s and 0.125 steel/s from loaded recipe/machine arithmetic | unsupported operational buffers/timing |
| blocked output | after finite storage fills, accepted import/export/delta are all 0 | conditional until finite lane/storage semantics are accepted |
| initial inventory transient | preloaded export is storage depletion, and long-run no-feed output is 0 | convergence test |
| forced oscillation | alternating windows hit `nonconverged`; no average rate | convergence test |
| controlled perturbation | raising lane capacity 15→30 with 10/s supply leaves output 10/s | conditional; demonstrates no causal improvement |
| pilot subfactory gate | no case is selected or claimed until review and compatible observations exist | integration gate |

Task 16 corpus IDs and task 17 scenario IDs are linked where they exist. Missing
splitter/merge/furnace capture plans remain explicit. Deterministic replay, stale
identity rejection, conservation including storage, and work-limit behavior are
also mandatory implementation tests after design acceptance.

## Task 21 design decisions requested

The independent review should explicitly accept, reject or narrow:

1. whether the synchronous intent/resolve/commit semantics can match Factorio for
   the initially claimed cases without relying on unknown cross-entity tick order;
2. lane slot density/phase and merge arbitration representation;
3. splitter state, priority and blocked-output arbitration;
4. the evidence needed for inserter phase timing beyond task 17's aggregate rate;
5. machine ingredient-start, output reservation/blocking and inventory sizes;
6. fixed/periodic convergence rules, work limits and frozen comparison tolerance;
7. the minimal supported pilot subfactory and exact new game captures required.

No public CLI/MCP/result-schema edits should begin until task 19's shared edits are
integrated and this design pass returns. Shared integration then follows the task
07 checklist: dedicated model/tests first, task 17 comparison adapter second,
public CLI/result/MCP metadata last, serialized against the existing dirty shared
files.

## Phase handoff

- Task: `20-sustained-throughput-model`, design phase.
- Starting/current HEAD: `ab25b2a9e4c11e31be551da750510fdeb5f7d6c6`.
- Model: GPT-5-family Codex; exact runtime model identifier was not exposed.
- Existing routing contract: `1.1.1`; proposed internal design-case contract:
  `factoribot-sustained-throughput-design-case-1`. No shared contract changed.
- Relevant pre-existing dirty files: task 18/19 edits in
  `blueprint_contract.py`, `blueprint_plan.py`, `blueprint_view.py`, viewer JS,
  `cli.py`, `routing_public.py`, shared docs and skill files, plus untracked task
  15–19 artifacts. None are owned or edited by this phase.
- Owned files: this handoff/design note,
  `daemon/factoribot/sustained_throughput.py`,
  `daemon/tests/fixtures/sustained_throughput/{README.md,cases.json}`, and
  `daemon/tests/test_sustained_throughput_design.py`.
- Unmet gates: independent task 21 design review; every actual task 17 game
  measurement; richer splitter/merge/inserter/machine observations; supported
  pilot selection; implementation/public integration/fresh MCP verification.
- Next task: task 21 design pass. Task 20 implementation must wait for its model
  findings; scenario/capture collection can proceed independently.

### Commands and results

```sh
git status --short
git rev-parse HEAD
```

Confirmed HEAD `ab25b2a9e4c11e31be551da750510fdeb5f7d6c6` and the pre-existing
task 15–19/shared dirty files listed above before editing.

```sh
(cd daemon && ../.venv/bin/python - <<'PY'
from factoribot.gamedata import load_database
x = load_database()
for name in ('iron-plate', 'steel-plate'):
    r = x.recipes[name]
    print(name, r.energy,
          [(i.name, i.amount) for i in r.ingredients],
          [(i.name, i.amount) for i in r.results])
print('electric-furnace', x.machines['electric-furnace'].speed)
PY
)
```

Confirmed loaded-data arithmetic used by the independent furnace oracle:
iron plate energy 3.2, steel energy 16 with five iron plates per craft, and
electric-furnace speed 2.0, hence `5/8` plate/s and `1/8` steel/s.

```sh
.venv/bin/python -m pytest daemon/tests/test_sustained_throughput_design.py -q
# 8 passed in 0.02s

make test
# 670 passed in 141.23s (0:02:21)

git diff --check
# no output; exit 0
```

The focused tests validate exact conservation, required case coverage, task 16
corpus links, task 17 scenario/capture-version links, synthetic-capture labeling,
the furnace arithmetic, frozen observation tolerance, and the no-improvement
perturbation. Generated task-20 Python cache files were removed afterward.

No public CLI or fresh MCP check was run because this phase deliberately adds no
public registration or prediction result. No Factorio comparison was run because
there is no compatible `game-observation` capture; the synthetic recorder sample
was checked only for interface compatibility and retained its synthetic label.

### Concrete counterexample

The prepared perturbation holds feed/removal fixed at 10 items/s. Increasing the
modeled lane capacity from 15 to 30 items/s leaves predicted output at 10 items/s.
Therefore merely naming or saturating a capacity is not enough to claim that
enlarging it improves production. Separately, the blocked-output steady ledger is
exactly zero import, zero export and zero stored delta after finite storage fills,
which catches an implicit virtual sink or forced full-supply intake.
