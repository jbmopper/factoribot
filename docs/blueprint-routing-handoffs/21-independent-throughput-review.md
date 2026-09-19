# Task 21 — independent throughput review, DESIGN pass

## Decision and snapshot

**Changes requested. Accept the three-layer architecture, but do not approve the
current operating design for substantial mechanics implementation or release of
sustained-rate predictions.** Task 20 can revise its design and fixtures now;
task 17 can repair/extend its capture contract and prepare observations. The
integrated implementation pass must occur later.

This is a fresh independent review of the checked-out artifacts, without the
implementer's conversation, additional agents, paid model calls, or production
repairs. Mathematical countermodels were considered before inspecting the
design-stage module; recipe expectations were derived separately from its
self-balanced ledger. All new witnesses are explicitly synthetic.

- Task: `21-independent-throughput-review`, design pass, 2026-09-12 local date.
- Starting/reviewed HEAD: `ab25b2a9e4c11e31be551da750510fdeb5f7d6c6`.
- Reviewer: Codex, GPT-6-based; no more specific runtime identifier claimed.
- Contracts reviewed: routing `1.1.1`; design cases
  `factoribot-sustained-throughput-design-case-1`; proposed prediction/comparison
  `factoribot-sustained-throughput-{prediction,comparison}-1`; prerequisite
  capture `factoribot-routing-measurement-capture-1`.
- Read the full task 21 prompt, working rules, roadmap, parent design, applicable
  Factoribot skill and development/routing references, and task 16/17/19/20
  handoffs and relevant artifacts. The supplied revised roadmap/prompts exist.
- Pass selection is explicit: task 20's handoff calls itself the first design
  deliverable; `sustained_throughput.py:1` explicitly contains no simulator and
  only supplies constants/tolerance/manifest validation. The public CLI/tool/MCP
  modules contain no sustained-prediction registration. Task 19 integration is
  present in dirty files; that does not make task 20 implemented.

Pre-existing modified files, preserved: `daemon/factoribot/blueprint_contract.py`,
`blueprint_plan.py`, `blueprint_view.py`, `blueprint_view_assets/view.js`, `cli.py`,
`routing_public.py`; `docs/blueprint-routing-design.md`,
`blueprint-routing-next-run.md`, `blueprint-routing-prompts/{NEXT-STEPS,README}.md`;
`skills/factoribot/SKILL.md` and `skills/factoribot/references/routing.md`.
Pre-existing untracked work includes the furnace-inference and sustained-design
modules, task 15–20 fixtures/tests/handoffs, task 15–21 prompts, roadmap/dispatch,
and `experiments/`. None belongs to this review.

Reviewed artifact SHA-256 values (untracked inputs need identity beyond HEAD):

```text
6a78893d1f6f18ec4070f59270af006b74631f1ced09256de23bf2e2a03d1584  docs/blueprint-routing-handoffs/20-sustained-throughput-model.md
c7c26f14c426d596055372721cd0fdfb95d3ad08e9a0919ba7944544070b30b7  daemon/factoribot/sustained_throughput.py
cdce9ef15d5b257def597f10a5dadb452bdb66d57c92307871e6c4b98d1b8fc9  daemon/tests/fixtures/sustained_throughput/cases.json
5eaaa17bc132ceae08a655f425c50371dc8225de342f9df5adc561137637c3fc  experiments/routing-measurements/harness.py
```

## Findings with reproduction, impact, and ownership

Tests below refer to
`daemon/tests/test_independent_throughput_review.py`. Run the whole file with
`--runxfail` to expose current prerequisite failures; `-k r1`, `-k r2`, etc.
select the independent witnesses for each finding. R1/R2 are defects in proposed
rules, not alleged executions of an absent simulator. R3/R4 exercise existing
scaffolding. R5 proves an interface limitation.

### R1 — P1: three flat windows do not establish a sustained rate

Location: task 20 handoff lines 150–157. Owner: **task 20**.

Declare a source producing one item every 18,000 ticks (1/300 item/s), initial
phase zero, empty finite transport with 32 ticks of latency, and ongoing removal.
After 3,600 warmup ticks, the windows ending at 7,200, 10,800 and 14,400 all have
exactly zero imports/exports and inventory slopes. Source phases differ at all
four boundaries, so there is no repeated complete state. The proposed
`steady_window` rule accepts zero, although the first export occurs at tick
18,032 and the long-run rate is 1/300 item/s. Zero tolerance cannot fix this.
This countermodel needs no circuits or unknown machine recipe.

Reproduction: `test_r1_three_flat_windows_can_precede_positive_periodic_output`.
The additional `test_r1_window_boundary_recurrence_does_not_prove_a_fixed_point`
shows a two-tick cycle sampled every 3,600 ticks: equal sampled states do not
distinguish a fixed point from a periodic orbit.

Required change: report a finite-window estimate separately, without a sustained
claim, unless complete autonomous-state recurrence or a proved restricted
analytic criterion establishes the rate. Include source/removal phase, credits,
arbiter state and every future-affecting timer in recurrence identity; cumulative
counters may be excluded only when transitions do not depend on them. Compare
canonical states on a hash match. A boundary recurrence can prove an orbit with
the sampled return duration, but cannot prove its minimal period or a fixed
point; check intervening transitions or label that limitation. A true periodic
orbit may report cycle totals. Different window rates alone are not proof of
nonconvergence. Replace the vaguely specified forced-oscillation fixture with
explicit complete state/driver and separate periodic and unresolved cases.

### R2 — P1: boundary ceilings and intent phases leave allocation unspecified

Location: task 20 handoff lines 109–131. Owner: **task 20**, with **task 17/09**
providing observations for physical transition rules.

Two independent feed ports share a 9-item/s external budget. A can accept 3/s,
B can accept 9/s. Both allocations `(A=3, B=6)` and `(A=0, B=9)` conserve supply,
respect every ceiling and are work-conserving. No physical merge arbiter owns
these distinct external ports. Banning entity-order allocation does not specify
which output a predictor should report. Rates also do not specify item emission
phase, burst allowance, or whether rejected fractional credit is banked.

Reproduction: `test_r2_shared_budget_bounds_do_not_determine_external_allocation`.
`test_r2_full_cycle_needs_joint_vacancy_resolution` supplies a second ambiguity:
two full one-slot resources cannot move under snapshot-free-space eligibility,
but can rotate simultaneously under a joint departure/arrival resolver. Both
fit the proposed intent/resolve/commit outline. This is an abstract witness, not
a claim about Factorio belt ordering.

Required change: freeze source and removal schedules, initial phases, handling
of blocked opportunities, and arbitration of shared external budgets in the
scenario identity. Initially reject competing external feeds unless a declared
operating allocator exists, or restrict to budgets at least the sum of their
feed ceilings. Specify exact motion distance, collision/vacancy dependencies,
simultaneous handovers and event eligibility. Reject cycles/interactions until
those transitions are defined; do not use an LP allocation to choose them.
The reviewer cannot supply a Factorio tick order from nonexistent observations.

### R3 — P1: the unequal-consumer oracle violates recipe quantities

Location: `daemon/tests/fixtures/sustained_throughput/cases.json:79`–85;
`daemon/factoribot/sustained_throughput.py:128`–155. Owner: **task 20**.

The fixture exports 3 gears/s and 6 pipes/s with 9 plates/s consumed/imported.
The loaded recipes independently require two plates per gear and one per pipe,
so the required consumption is `2*3 + 1*6 = 12`, not 9. The manifest validator
accepts the false oracle because its declared gross production and consumption
are independently supplied numbers rather than coefficients of recipe crafts.

Reproduction: `test_r3_unequal_consumer_oracle_obeys_loaded_recipe_stoichiometry`
fails with `Fraction(9, 1) == Fraction(12, 1)`. For the stated 3-plate/s allocation
to A and 6 to B, the corrected mathematical output is **1.5 gears/s and 6 pipes/s**,
subject to explicitly sufficient consumer machine capacity. Alternatively use
untransformed plate collectors for the arbitration-only test. Declare whether
the 3/s cap measures plates or gears; they are different experiments.

Required change: fix the oracle and bind material consumption/production to
explicit recipe identities, craft counts and loaded coefficients. Apply the same
check to every recipe-bearing fixture. Keep ideal direct-inventory furnace
arithmetic a mathematical reference; it supplies no actual transport bridge.

### R4 — P1: task 17's stability result is insufficient for task 20's gate

Locations: `experiments/routing-measurements/harness.py:120`–159 and 196–219;
task 20 handoff lines 193–198. Owner: **task 17** for validator fixes;
**task 20** for refusing inadequate captures in the comparison adapter.

Four current failures, all using synthetic-labelled input:

1. `test_r4_capture_rejects_inventory_jump_at_shared_tick`: window 1 ends at tick
   7,200 with zero items; window 2 starts at that same tick with 100. Both windows
   independently balance and the parser accepts the uncounted 100-item jump.
2. `test_r4_filling_blocked_capture_is_not_steady`: contiguous zero-export windows
   import 900 items each and retain 0→900→1,800. The parser calls this
   `steady-within-tolerance`; finite storage is still filling, so this cannot
   establish the proposed sustained imports, unused supply or utilization.
3. `test_r4_repeat_validation_enforces_scenario_tolerance`: two runs have 15/s
   then 0/s, but each capture sets tolerance to 100. The scenario's frozen
   tolerance is 1/60. `validate_repeats` returns `all_runs_steady: true`.
4. `test_r4_repeat_validation_enforces_declared_warmup_and_windows`: two distinct
   runs each contain only tick 0→1, while the plan requires 3,600 warmup and
   3,600-tick windows. `validate_repeats` accepts them as steady.

Required change: validate cross-window inventory continuity (or explicit counted
boundary operations), all retained-material trends, the required window count,
warmup/intervals and immutable scenario tolerance. Bind setup, environment,
research and counter semantics before comparison; a hash binds bytes but does
not establish their adequacy. Preserve raw rates as interval measurements even
when convergence fails. `steady-within-tolerance` currently describes only the
one selected item's collector-rate spread, not an equilibrated factory.

### R5 — P1 for furnace validation: capture v1 cannot carry the required evidence

Locations: `experiments/routing-measurements/harness.py:108`–154; task 20 handoff
lines 183–198 and 225. Owners: **task 17** for a versioned richer capture;
**task 20** for its comparison binding. Coordinate evidence-profile extensions
with the mechanics/integration owner; do not silently change routing `1.1.1`.

Reproduction: `test_r5_transport_capture_v1_cannot_validate_a_conserving_furnace_window`.
An ideal 8-second window with 5 ore imported, 5 plates produced and consumed,
1 steel produced/exported, and zero inventory change conserves each item using
the recipe ledger. Capture v1 rejects it: its equation is only
`source_extracted = collected + inventory_delta`, with no recipe terms. Even if
that check were bypassed, it reports the collected rate for `supply.item`
(`iron-ore`), rather than the steel export.

The same shape aggregates counts by item and has one source/collector descriptor;
it cannot bind two same-item lanes or splitter branches independently. Total
30/s does not distinguish 15/15 from 30/0. There are no typed inserter-phase,
craft-event, hand-state or per-entity inventory traces. Task 20 correctly says
aggregate chest-to-chest rates cannot identify phase durations; the independent
`test_aggregate_inserter_rate_does_not_identify_drop_phase` demonstrates equal
6/s averages with different downstream availability at tick 3.

Required change: retain v1 for its narrow transport recorder role. Add explicit
boundary/entity/lane counters, recipe start/completion counts and stored-material
accounting (including hand contents and the chosen in-progress-craft convention),
plus timestamped observations needed to identify timing. Do not reconstruct
observed internal consumption from the prediction being validated. Until the new
capture and timing observations exist, furnace/inserter/splitter predictions
remain unsupported and the furnace comparison gate cannot close.

## Scope decisions requested by task 20

| Design concern | Decision and required boundary |
| --- | --- |
| Approach/reuse | Accept a separate restricted deterministic model plus independent trials and the unchanged LP ceiling. Task 16's retained failures justify declining those engine imports; they do not prove a new tick model correct. |
| Synchronous scheduling | Accept intent/resolve/commit as software organization only. Require R2's full transitions before numeric cases. No evidence-backed Factorio ordering can be approved here. |
| Lanes/mixing/merges | Accept distinct ordered lanes and exact rational position. Four positions/tile is a candidate representation, not a verified collision algorithm. Freeze spacing, endpoints, handover/collision phases and saturation behavior. Mixed items within a lane, merges and turns stay unsupported. Opposite lanes may hold distinct items only with separate state/counters. |
| Splitter priorities | Persistent state is appropriate, but alternation, two-input arbitration, retry/blocked-output state updates and priority-side mapping need complete tables plus observations. Work-conserving alone does not imply A=3/B=6. Filters are listed both as conditionally possible and outside the first scope; resolve this by keeping filters unsupported initially. |
| Inserters/research | Require the exact prototype, endpoint types/positions, pickup lane, capacity/research, hand-size behavior, phase durations and blocked/drop retry state. Chest-to-chest totals do not qualify belt-to-machine or bulk inserters. Task 09/17 own the needed evidence. |
| Machines/back-pressure | Require finite inventory slots and item stack limits, ingredient reservation/consumption events, output-full start/completion behavior and handling of initial in-progress crafts. A consumed ingredient belongs to the consumption ledger even before its product exists; do not count it twice as stored inventory. No invented ideal inter-furnace transfer is allowed. |
| Cycles/initial inventory | Require complete initial phase/arbiter/hand/progress state even when physical inventory is empty. Test empty disconnected cycles, seeded full cycles, blocked cycles and delayed sources. Preserve initial inventory in the ledger and separate depletion from recurring production. |
| Termination/tolerance | Reject the `steady_window` sustained claim (R1). Retain exact internal conservation and predeclared observation error `max(60/window_ticks, 0.005*max(abs(p),abs(m)))`; at 60 seconds this is 0.075/s at 15/s, and 1/60/s at zero. A one-item zero match is tolerance agreement, not proof of structural impossibility or maximum capacity. Apply checks per lane/export and to inventories, not just totals. |
| Work limits | Accept 32,400 ticks, 2,048 entities and 262,144 tokens as provisional hard caps, not a measured practical runtime guarantee. A naive token scan at both maxima entails 8,493,465,600 token visits. Freeze an operation budget/resolver limit and benchmark the narrowed subset before pilot acceptance. Nine post-warmup boundary states fit under the 65,536 signature cap; that cap alone tests no realistic boundary-history pressure. |
| Result wording | Accept separate bound/prediction/measurement identities and conditional/unsupported statuses. Keep nonconverged/work-limit rates absent. Local saturation is descriptive until a controlled perturbation establishes improvement. Scope any prediction-versus-LP check to matching boundaries/recipes and recurring inventory; a transient drain can exceed a steady feed-only ceiling without disproving that ceiling. |

First implementable scope after the design revision: a single straight belt tile
with separate lanes, explicit noncompeting boundary schedules and finite state,
with open-removal and blocked-removal cases. Even this is only a conditional
mathematical model until its motion/source/sink semantics are complete; there is
no currently supported Factorio numeric subset. Extend to rear handovers only
after their compatible observation record exists. This tiny case is a mechanics
milestone, not the useful production pilot.

## Concrete pilot candidate and missing observations

Read-only decoding of `daemon/tests/fixtures/wip_science.txt` found 2,771 entities,
blueprint version integer `562949958402048`, and an actual furnace cell candidate:
furnace **1255** at `(480.5, -57.5)`, bulk inserters **1254/1256** at
`(478.5, -57.5)` / `(482.5, -57.5)`, and adjacent fast belts **1252/1258** at
`(477.5, -57.5)` / `(483.5, -57.5)`. Furnace 1255 has no recipe field.
Pilot file SHA-256:
`e48fa3fad55155c184a63f70db62ff801e9ce39cd358b8c1cabfd9e99655f49a`.

Nominate those five entities as the smallest **candidate** production cell for
a later isolated extraction. This review does not create the extraction, assign
its real recipe, establish inserter direction semantics, or assert that its
interfaces work. Its bulk inserters remain unsupported until their own endpoint
and timing observations exist; substituting fast inserters would make a different
candidate. The full pilot exceeds the proposed 2,048-entity cap and includes
unsupported mechanics, so it is not the initial simulation target.

For a disposable experiment, task 20 can propose an explicit iron-ore feed,
iron-plate furnace assignment, counted plate removal, empty initial state,
fixed research and powered/no-control conditions. These are proposed test
declarations, not inferred user-factory facts. Freeze and hash an approved
extracted blueprint, exact boundary roles/lanes, final request and manual or
revalidated task 19 assignment provenance. No source, sink, mod policy or research
is inherited silently from the surrounding pilot.

Task 17 must collect two independent runs per selected case, in a named disposable
environment with exact 2.0.76 build/executable identity, enabled mod versions/hashes,
prototype profile, research, power/control state, setup blueprint/hash, initial
state, counted boundary services and contiguous intervals. Minimum capture work:

- One-lane and two-lane straight-belt motion, item spacing, boundary handover,
  saturated supply and counted removal; retain per-lane counts and timed motion.
  The current plan's fast-inserter feed and chest collector do not themselves
  establish a saturated belt or a nonlimiting removal service. Identify and
  measure both interfaces before attributing a limit to the belt.
- Blocked output from empty, through fill, to stable blockage; later unblock
  with counted removal and retained inventories. Do not equate zero exports
  during fill with equilibrium.
- Rear/side-load mapping and unequal competing consumers, then input/output
  priority toggles, blocked preferred output and entity-number permutations;
  keep arbitration and phase traces, not only whole-network totals.
- Fast-inserter chest-to-chest and the candidate's actual bulk-inserter
  belt-to-furnace/furnace-to-belt endpoints: timestamp pickup, drop, return and
  waiting transitions at fixed research, with full-output and empty-input cases.
- Furnace ingredient start, completion/output blocking, inventory/stack limits,
  then an explicitly transported ore→plate→steel chain using the richer R5
  ledger. Repeat the isolated candidate cell with the same identities and
  controlled supply/removal perturbations. Report no improvement if none occurs.

No capture is supplied by this review. The checked-in mechanics manifest still
records **0 observed, 6 documented-only, 10 pending** rules; the only task 17 raw
sample is explicitly synthetic. Existing handoffs report no compatible local
Factorio executable; this pass did not search private saves or attempt a game
launch. An executable/operator plus the reviewed capture work remains external.

## Separate acceptance gates

| Gate | Result for this pass | Evidence needed to close it |
| --- | --- | --- |
| Mathematical correctness | **Not accepted.** Architecture is sound in direction; R1–R3 leave a false convergence rule, unspecified operating schedules and a wrong recipe oracle. No simulator was tested. | Revised complete semantics, corrected recipe-linked corpus, independent conservation/storage/arbitration/recurrence and limit tests, then implementation review. |
| Factorio agreement | **Unmet; no observed agreement claimed.** Zero observed mechanics records and no actual game capture. R4/R5 additionally block trusting the planned comparison. | Repaired/versioned capture contract, independent compatible observations, frozen per-output tolerance and reviewed timing/phase rules. |
| Actual pilot usefulness | **Unmet.** A precise candidate cell is nominated; no operating declarations, validated prediction, measured comparison or user workflow acceptance exists for it. | Explicit candidate scenario, validated endpoint/mechanics evidence, useful per-entity explanation and perturbation, then full page→draft→CLI sealing→inference→analysis→regenerated-page review. |

The design review is complete; none of these gates is closed by test count.
This review gives no new release approval for tasks 15–19 or for a sustained-rate
feature. Their existing upper-bound wording and mechanics limitations remain.

## Verification, ownership and next work

Owned/added only:

- `daemon/tests/test_independent_throughput_review.py` — six passing mathematical
  or interface witnesses and five strict expected failures for R3/R4. Strict
  xfails document open defects; they are not acceptance passes. `--runxfail`
  exposes failures directly, and a future unexpected pass requires retiring the
  marker as part of the owning repair.
- `docs/blueprint-routing-handoffs/21-independent-throughput-review.md` — this
  required review handoff.

No shared schema, production code, evidence record, existing fixture, skill,
blueprint, live save or mod configuration was edited. Proposed shared changes
are only the coordinated task 17 capture extension/task 20 comparison adapter;
public CLI/MCP/schema integration remains serialized after design acceptance.

Commands run from the repository root:

```sh
git rev-parse HEAD
git status --short
git diff --stat
git diff -- daemon/factoribot/blueprint_contract.py daemon/factoribot/blueprint_plan.py docs/blueprint-routing-design.md

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider \
  daemon/tests/test_independent_throughput_review.py \
  daemon/tests/test_sustained_throughput_design.py \
  daemon/tests/test_routing_measurement_harness.py -q -rx
# 20 passed, 5 xfailed in 0.12s; exit 0.

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider \
  daemon/tests/test_independent_throughput_review.py --runxfail -q --tb=short
# 5 failed, 6 passed in 0.08s; exit 1, deliberately exposing R3/R4.

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider \
  experiments/routing-reuse/test_harness.py -q
# 7 passed in 0.01s; exit 0.

shasum -a 256 experiments/routing-reuse/results.json \
  experiments/routing-reuse/factoribot-inspect-results.json \
  experiments/routing-reuse/custom-prototype-result.json \
  experiments/routing-reuse/factorio-analytics-parser-result.json
# All four hashes exactly match task 16's handoff.

PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' make test
# 676 passed, 5 xfailed in 141.27s (0:02:21); exit 0.

git diff --check
# No output; exit 0.
```

Task 16's checked-in corpus/results substantiate its concrete analyzer failures
(implicit sink, greedy consumers, ignored priority and incompatible pilot), and
its refusal to import the engine is accepted. This review reran its retained
seven-test harness and verified artifact hashes. It did not redownload upstream
repositories, re-evaluate current licenses/dependencies, or claim that stored
analyzer output is a Factorio observation. Those bounded reuse checks are enough
for this design choice; no broader engine rewrite or dependency upgrade is needed.

Verification scope: focused review tests are fresh Python subprocesses using
local imports. No new public prediction CLI/MCP endpoint exists to exercise.
The full suite also exercises existing subprocess integration tests; that is
regression coverage, not the requested future implementation-pass user trace.
The connected MCP server was not called, reloaded or verified. No browser
interaction, live game observation, measured prediction comparison, or pilot
operation was performed. Those checks are deferred to their actual prerequisites,
not inferred from synthetic cases or prior handoffs.

A before/after SHA-256 audit of all 222 pre-existing regular files reported no
changes or deletions. Only the two owned regular files were added, and HEAD is
unchanged. Python bytecode and pytest cache writes were disabled for these runs.
The review's temporary baseline-hash file was removed after verification; no
review process or downloaded dependency remains.

Task-specific untracked diff commands (exit 1 means differences, as expected):

```sh
git diff --no-index -- /dev/null daemon/tests/test_independent_throughput_review.py
git diff --no-index -- /dev/null docs/blueprint-routing-handoffs/21-independent-throughput-review.md
```

Next work: **task 20 revise R1–R3 and freeze the narrowed transition/scenario
contract; task 17 address R4/R5 and acquire the named observations; task 09 supply
the endpoint-specific inserter evidence.** Then return the revised design for
acceptance before substantial mechanics implementation. After tasks 15–20 are
actually integrated, task 21 must perform its separate implementation pass,
including mixed/unknown feeds, stale edits/results/inference, blocked outputs,
cycles, transients, nonconvergence, unsupported mechanics, actual public CLI/fresh
MCP replay and the observed candidate pilot. This handoff does not waive it.
