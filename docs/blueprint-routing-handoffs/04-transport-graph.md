# Task 04 handoff — supported lane connections and structural findings

## 1. Identity

- Task: 04, *Build supported lane connections and structural findings*
  (`docs/blueprint-routing-prompts/04-transport-graph.md`), under
  `docs/blueprint-routing-prompts/WORKING-RULES.md`.
- Starting snapshot: HEAD `664662e` ("codex review and next steps") on top of the
  reviewed `76fd016`, plus the working tree. Fix A, Fix B and Fix C had already
  landed their files when this task finished; their modified files and new
  regression suites are outside this diff.
- Contract version read in full: **1.1.1** (`docs/blueprint-routing-contract.md`).
- Prerequisites verified present in this checkout before starting:
  `blueprint_contract.py` / `findings.py` at `SCHEMA_VERSION = "1.1.1"` and
  `MECHANICS_PROFILE = "base-2.0.76-normal-v1"`; `transport_prototypes.py` with
  `daemon/tests/fixtures/routing_prototypes/` and
  `daemon/tests/fixtures/routing_mechanics_observations/` (16 records, still
  **0 observed**); `spatial.py` with the task 03 API; `blueprint_plan.py` /
  `routing_lp.py`; the pilot `daemon/tests/fixtures/wip_science.txt`; and the
  02/03/05 handoffs.
- Model: Claude Opus 5 (`claude-opus-5[1m]`).
- Nothing committed, stashed, reset or cleaned. No game, save, MCP server or
  public surface was touched.

## 2. What changed

Owned and new:

| File | Lines | What |
| --- | --- | --- |
| `daemon/factoribot/transport.py` | 666 | Mechanics layer: evidence status → arc semantics, the named condition catalogue, belt/splitter/underground/inserter geometry, handover classification, tunnel pairing. Builds no contract records. |
| `daemon/factoribot/routing.py` | 1186 | Graph layer: `build_transport_graph(view, options) -> TransportGraph` (contract `SpatialGraph` + findings + stats), `possible_items`, `reachable_from`, `RecipeSource`. |
| `daemon/tests/test_transport.py` | 347 | 29 tests of the mechanics/geometry layer. |
| `daemon/tests/test_routing.py` | 858 | 112 tests: acceptance cases, invariants, LP integration, pilot. |
| `daemon/tests/fixtures/routing_transport/` | 476 | `README.md`, `layouts.py` (hand-placed blueprints + translate/rotate), `requests.py` (explicit request builders). |
| this handoff | | |

**No file owned by another task was opened for writing.** `blueprint_contract.py`,
`findings.py`, `spatial.py`, `blueprint.py`, `transport_prototypes.py`,
`gamedata.py`, `model.py`, `blueprint_plan.py`, `routing_lp.py`,
`blueprint_view.py`, `view.js`, `tools.py`, `mcp_server.py`, `cli.py` and the
skills are unchanged (`git status` shows them as another agent's modifications or
untouched). `blueprint_plan.resolve_model_inputs` / `analyze_delivery` are called,
never edited.

### Proposed shared edits

**None.** No contract change is needed: everything task 04 emits fits 1.1.1 as
written, including the nullable-condition and lane-alias rules. Two observations
for whoever owns the shared surface later, neither applied:

1. `spatial.py` keeps its rotation of prototype offsets private (`_rotate`).
   `transport.rotate` re-implements the same eight lines rather than importing a
   private name; `test_transport.py::test_rotation_matches_the_spatial_inserter_candidates`
   pins the two together on every cardinal direction so they cannot drift. If
   task 13 wants one copy, exporting `spatial.rotate_offset` is the one-line fix.
2. `build_transport_graph` spends 5.7 s of its 6.2 s on the pilot canonicalising
   and re-validating the 12 MB graph (three passes over the canonical JSON:
   `graph_hash`, `from_dict`, and `_validate`'s `record_hash`). Nothing is wrong;
   if a public tool ever needs this on a hot path, a `SpatialGraph` constructor
   that accepts a precomputed `graph_hash` would remove one pass. Task 07's call.

## 3. Model

### 3.1 Endpoints

| Role | Endpoints | Notes |
| --- | --- | --- |
| belt, underground entrance, underground exit | ports `in_left`, `out_left`, `in_right`, `out_right`; lanes `left`, `right` | Ports sit on the rear/front face, ±0.25 tiles laterally. The `Lane` record aliases the pair, exactly as the contract defines aliases. |
| splitter | ports `in_<half>_<side>` / `out_<half>_<side>`, 8 in total | Halves are named by the side they occupy looking along the movement direction. No `Lane` record: a splitter has no single internal path, and an alias would imply one. |
| inserter | one bidirectional port `hand` | The two candidate *tiles* are role-free (§3.3). |
| assembling machine, furnace | inventories `input`, `output` | Conserved local pools, never implicit sources or sinks. |
| anything unsupported | none | Visible as an entity, and as a `TopologyGap` when it could carry items (§3.5). |

### 3.2 Capacity: one resource, charged once

| Group | Kind | Capacity | Charged by |
| --- | --- | --- | --- |
| `<entity>_<side>` | `lane` | finite, tier per-lane items/s | that belt's own `in_<side> -> out_<side>` traversal arc, and nothing else |
| `<splitter>_in_<half>_<side>`, `<splitter>_out_<half>_<side>` | `lane` | finite, tier per-lane | each of the splitter's internal paths that crosses it |
| `<splitter>_split` | `splitter` | **unknown** | all sixteen internal paths |
| `<inserter>_hand` | `inserter` | **unknown** | the pickup leg only, under either rotation sense |
| `<machine>_time` | `machine_time` | finite 1.0 s/s | every alternative activity of that machine |
| `handover` | `other` | **unlimited** | every surface handover, tunnel and inserter drop leg |

The canonical crossing of a belt lane is the belt's own traversal arc. A handover
is a boundary between two lanes that are each already charged, so charging it
again would double-count: a three-belt chain fed without limit delivers **15/s**,
not 7.5 (per-segment double charge) and not 45 (per-arc capacity copy). That is
`test_a_belt_chain_is_bounded_by_one_lane_not_by_a_per_segment_charge`, and both
wrong answers are named in it.

The `handover` group is a single graph-wide `unlimited` resource with evidence.
The contract requires every arc to name a resource; an explicitly unlimited,
evidenced group hides no ceiling, and `resolve_model_inputs` gives it an infinite
row that never binds.

### 3.3 Evidence drives semantics; ambiguity stays open on both sides

`transport.semantics_for` maps `observed` → `exact` and everything else →
`relaxed`, reading the status straight out of task 02's records. **Today no rule
is observed, so no arc in any graph this module builds claims `exact`** — asserted
for every acceptance layout and for the pilot. When a capture lands, the profile
tightens itself; nothing here has to be edited to make that happen.

Where a rule leaves two readings live, both are emitted as `conditional` arcs
under engine-wide condition names. These are conventions of the engine, not of
one entity, so one control assignment settles every entity that depends on them:

| Condition | Ambiguity it keeps open | Record |
| --- | --- | --- |
| `inserter_rotation_documented` / `inserter_rotation_reversed` | which candidate tile is the pickup (task 03 §4) | `inserter.endpoints.pickup_drop_tiles`, documented-only, sense unstated |
| `underground_reach_extended` | `max_distance` = tiles-between vs centre-to-centre (task 02 §4) | `underground.pairing.range`, pending |
| `underground_pairing_beyond_intervening` | whether a nearer same-tier endpoint captures the pairing | `underground.pairing.conflict`, pending |
| `underground_lane_crossing` | whether a tunnel preserves lane identity | `underground.lane_mapping`, pending |
| `side_load_feeds_near_lane` / `side_load_feeds_far_lane` | which lane a perpendicular load feeds | `belt.side_load.lane_assignment`, pending |
| `underground_exit_rear_feed` | whether a belt behind an exit hands over | no primary document either way |
| `circuit_<entity>` | a circuit-controlled entity's enable state | `circuit.control_state`, pending |

Under `relax_open` every one is open (sound for an upper bound, flagged
`conditional_connections_open`); under `explicit` the request must state each.
**No convention is picked silently anywhere**, and no candidate link is deleted.

A *turn* is deliberately not conditional: `belt.turn.lane_behavior` questions
throughput, not lane identity, so the arc is lane-preserving and `relaxed`.

Evidence kinds: `structural` only for geometry read losslessly from the blueprint
and for the prototype extract; `upper_bound` for the documented finite lane
ceiling; `estimated` for every pending rule. A pending rule is never `structural`,
because `unresolved_reasons` accepts structural evidence as proof of a
disconnection.

### 3.4 Filters and priorities are recorded and relaxed, never applied

No mechanics record covers inserter or splitter filtering, and the contract
explicitly says splitter priorities must be relaxed for an optimistic bound. So
arc eligibility stays `any_item`, the declaration is reported
(`item_filter_relaxed`, `splitter_distribution_relaxed`, naming the items and
priorities), and the raw record keeps it verbatim. A copper plate is therefore
still deliverable at 15/s through a splitter filtered to iron; an implementation
that applied the filter would report 0 and could turn a satisfiable request into a
false shortfall.

### 3.5 Unsupported topology

- An unsupported entity whose subsystem **can** carry items (`transport`,
  `inserter`, `production`, `logistics`, `other`, `unknown`) becomes a
  `TopologyGap`. `may_connect` is `true` whenever any supported endpoint is
  adjacent, or whenever the geometry is an assumed unit footprint, which can
  under-cover. Only a real recorded footprint with no candidate endpoint at all
  yields `may_connect: false` with structural evidence.
- An unsupported entity of a **non-item** subsystem (`power`, `circuit`, `rail`,
  `fluid`) gets **no gap at all**, only a `unsupported_non_item_entity` finding.
  Writing `may_connect: true` would withhold every bound whatever the request
  declares — which would make the contract's own documented pilot path (declare
  the mod, declare `power_assumed_available` irrelevant) permanently unusable —
  and `may_connect: false` would assert a disconnection this module cannot prove.
  `unresolved_reasons` still withholds until the request declares them.

### 3.6 Boundaries versus internal breaks

An unconnected lane end whose next tile is **empty** is a boundary candidate:
material could cross there, and whether anything does is external context only the
request may declare. An end **blocked by an entity that offers no supported
handover** (a machine wall, an opposing belt, an unsupported prototype) is an
internal break. A tunnel mouth — an entrance's front face, an exit's rear face —
is neither: an unpaired one is `underground_unpaired`, and it is never offered as
a place to declare a feed. The test uses the neighbouring tile, not a bounding
box, so the classification survives translation and rotation.

**No supply is inferred from a dangling belt.** With no declared feed the
maximisation returns 0.

### 3.7 Item propagation

`possible_items(graph, feeds)` propagates from declared feeds and fixed recipe
outputs only. A feed mapped to `None` is one whose identity the caller declared
*unknown*; it stays "anything is possible" all the way downstream, so it satisfies
every recipe input and every filter rather than none of them. That is precisely
what stops an unknown feed from producing a false incompatible-filter or
unreachable-input finding. `reachable_from` counts conditional arcs, so an unknown
link is never removed and then used to prove something unreachable.

### 3.8 Findings

`transport_boundary_candidate`, `transport_internal_break`, `underground_unpaired`,
`underground_pairing_ambiguous`, `unsupported_possible_bridge`,
`unsupported_isolated`, `unsupported_non_item_entity`, `disconnected_producer`,
`blocked_output`, `unreachable_input`, `direct_insertion`,
`inserter_endpoint_missing`, `item_filter_relaxed`,
`splitter_distribution_relaxed`, `inserter_capacity_unknown`,
`inserter_rotation_unresolved`, `machine_recipe_unresolved`, `recipe_unavailable`,
`recipe_uses_fluid`, `mechanics_unobserved`. IDs are the contract's
`finding_id(code, entities, endpoints, material, evidence)`; scope is original
entity/endpoint IDs throughout. `blocked_output` and `unreachable_input` downgrade
from `structural` to `estimated`, with a sentence saying so, whenever any
`may_connect` gap could still supply the missing link.

## 4. Commands run and results

```sh
.venv/bin/python daemon/tests/fixtures/routing_transport/layouts.py
.venv/bin/python -m pytest daemon/tests/test_transport.py -q      # 29 passed
.venv/bin/python -m pytest daemon/tests/test_routing.py -q        # 112 passed
.venv/bin/python -m pyflakes daemon/factoribot/{transport,routing}.py \
    daemon/tests/test_{transport,routing}.py \
    daemon/tests/fixtures/routing_transport/*.py                  # clean
make test                                                          # 503 passed
```

- `make test`: **503 passed, 0 failed, 0 skipped, 38 s.** No failure in any file
  owned by another task, so nothing to report by file name and no rerun was
  needed. The reviewed baseline was 330; the delta is my 141 plus Fix A/B/C's
  new regression suites, which had landed by the final run.
- No test is skipped and no dependency is missing. `RecipeSource` reads the local
  `data/data-raw-dump.json` through the existing `gamedata.load_database()`; every
  test that needs recipes uses it, and the graph builds without it (machines then
  get inventories and a `machine_recipe_unresolved` finding rather than an
  invented recipe).
- No model call is used anywhere in this code or its tests.
- Temporary files: none left; the scratch directory was used and is empty.
  `pyflakes` was already installed in `.venv` by an earlier task and is left as it
  was found.

### Reproducible fixtures

`daemon/tests/fixtures/routing_transport/layouts.py` (12 hand-placed layouts plus
`translate`/`rotate`) and `requests.py` (explicit request builders). **No graph
JSON is checked in**: each layout is a few lines of Python, and the pilot's graph
is ~12 MB of canonical JSON. `README.md` in that directory carries the exact
snippet that regenerates a graph for inspection.

The *expected* ports, lanes, arcs, groups and delivery numbers are **not** stored
in the fixtures. Each is written out by hand in the test next to its derivation,
so a test cannot pass merely by agreeing with what the implementation emitted.

### Acceptance coverage

| Case | Where | Hand-derived expectation (wrong answer named where it discriminates) |
| --- | --- | --- |
| both lanes | `test_a_belt_carries_two_independent_lanes_with_hand_written_geometry` | 4 ports at (0.0/1.0, 0.25/0.75), 2 lanes, 2 groups of 15/s per belt |
| half-belt feed | `test_a_half_belt_feed_does_not_reach_the_other_lane` | left→left 15/s, left→right **0** |
| canonical crossing | `test_a_belt_chain_is_bounded_by_one_lane_...` | 15/s; double charge → 7.5, per-arc copy → 45 |
| turn | `test_a_turn_preserves_lane_identity_and_claims_no_condition` | 2 lane-preserving `relaxed` arcs, no condition |
| side-loading | `test_a_side_load_keeps_both_target_lanes_open_...`, `..._opens_both_side_load_readings_and_says_so` | 4 conditional arcs, near lane = left; explicit near-only → 0 |
| filtered/priority splitter | `test_a_splitter_filter_is_recorded_and_relaxed_never_applied` | copper still 15/s; applying the filter → 0 |
| splitter shared capacity | `test_multiple_splitter_paths_cannot_each_claim_the_full_capacity` | **15/s**; per-arc copy → 60 |
| conflicting underground endpoints | `test_conflicting_underground_endpoints_...`, `test_the_ambiguous_reach_is_a_condition_...` | 16 tunnel arcs kept, `beyond_intervening` on 1→2, 1→4, 3→4; sep 7 plain, 8 conditional, 9 unpaired |
| disabled/conditional inserter | `test_a_circuit_controlled_inserter_adds_a_named_condition_per_entity` | all inserter arcs disabled under explicit-false → 0 |
| disconnected producer | `test_a_machine_with_no_inserter_is_a_disconnected_producer` | no arcs, entity still visible with its activity |
| direct insertion | `test_direct_insertion_links_two_machine_inventories` | exactly 4 inventory↔hand arcs |
| blocked output | `test_a_machine_whose_products_cannot_leave_is_reported_as_blocked` | both machines blocked, neither "disconnected" |
| unsupported possible bridge | `test_an_unknown_possible_bridge_never_becomes_a_proven_disconnection` | `partial`, no bounds, no `may_connect: false` gap |
| translation invariance | parametrised over all 10 layouts | identical arc ids, endpoints, semantics, conditions, groups |
| supported rotation invariance | parametrised over all 10 layouts × 3 turns | same, including lane sides |
| determinism | parametrised over all 10 layouts | equal `graph_hash` across builds |
| contract round trip | parametrised over all 10 layouts | `parse_graph(to_dict(graph)) == graph` |
| book paths | `test_a_book_leaf_is_selected_by_book_index_not_array_offset` | leaf index 2, not offset 0 |

## 5. Concrete before/after and a counterexample

**The splitter's shared resource.** `splitter_layout()` is one east-facing
`fast-splitter` at centre (1.5, 1.0), covering tiles (1, 0) and (1, 1), fed by two
belts and feeding two. Its sixteen internal paths each charge three resources: the
input lane crossed, the output lane left on, and the splitter body. Feed all four
input lanes without limit and export straight off `bp/root/e/3/port/out_left_left`:

- **This model:** aggregate `unlimited`, budget 1000, **routing 15.0** — the four
  paths into that output lane share the one 15 items/s group
  `e3_out_left_left`, so they cannot each claim it.
- **A per-arc capacity copy:** 60, four times the truth.
- The splitter body's own ceiling is `unknown`, not a guessed "two belts' worth",
  because `splitter.lane_split` is pending; the LP relaxes it upward and records
  `unknown_capacity_unlimited`.

**The counterexample that matters most: an unknown bridge is not a
disconnection.** `unsupported_bridge()` is two belt runs with one `steel-chest`
between them — a real prototype the pinned extract does not describe, so it is
`unknown`/`unsupported` with an assumed unit footprint. There is no arc between
the two runs, and `reachable_from` confirms the second run is not reachable from
the first. A model that concluded "therefore 1 item/s is impossible" would report
`insufficient` with an infeasibility certificate. This model emits
`TopologyGap(gap_e2, may_connect=True)` with the four candidate lane endpoints,
`unresolved_reasons` returns `("unsupported topology: gap_e2",)`, and
`analyze_delivery` reports **`partial` with no bounds and no witness**. No
`may_connect: false` gap is produced anywhere by this module except for an entity
with real recorded geometry touching nothing at all.

**The inserter rotation sense, kept open.** For the inserter at (1, 1) facing
north, the documented offsets put one candidate tile at (1, 0) and the other at
(1, 2). Under `inserter_rotation_documented` the arcs run belt 1 → hand → belt 2;
under `inserter_rotation_reversed`, belt 2 → hand → belt 1. Every one of the eight
arcs is `conditional`; none is unconditional, so neither convention is adopted by
default. Both senses' pickup legs charge the same `e3_hand` group, so opening both
does not double the inserter's throughput.

## 6. The development pilot

`daemon/tests/fixtures/wip_science.txt` (SHA-256 `e48fa3fa…55f49a`, 2771
entities, single leaf, path `[]`), built with
`RoutingOptions(provenance="development_pilot", recipes=RecipeSource())`:

| Measure | Value |
| --- | --- |
| decode + spatial index | 0.038 s |
| **graph build total** | **6.18 s** (topology 0.49 s, contract serialization + validation 5.69 s) |
| entities / ports / lanes / inventories | 2771 / 8392 / 3832 / 458 |
| capacity groups | **4729** — 3952 lane, 608 inserter, 153 machine-time, 15 splitter, 1 handover |
| arcs | **11660** — 3832 lane traversals, 3612 handovers (1806 pairs × 2 lanes), 328 tunnel arcs (82 pairings × 4 lane mappings), 240 splitter paths, 3648 inserter legs |
| arc semantics | 7848 `relaxed`, 3812 `conditional`, **0 `exact`** |
| conditions in use | `inserter_rotation_documented` 1824, `inserter_rotation_reversed` 1824, `underground_lane_crossing` 164 |
| activities | 153 (the AM2s' declared recipes); the 76 furnaces stay unresolved |
| topology gaps | 0 |
| findings | 377 |
| canonical graph JSON | ~12 MB (not checked in; `fixtures/routing_transport/README.md` has the regeneration snippet) |

Every count above is re-derived by hand in
`test_the_pilot_graph_has_hand_derivable_counts` and
`test_the_pilot_arc_count_decomposes_by_mechanic`.

**Unsupported mechanics found on the pilot**, all reported by name:

- 11 `mechanics_unobserved` findings, one per rule the pilot's graph actually
  relies on: belt lane capacity, belt-to-belt transfer, turns, underground range,
  underground conflict, underground lane mapping, splitter lane split, splitter
  priority/filter, inserter endpoints, inserter rate, AM2 activity. All are
  `documented-only` or `pending`; **none is observed**.
- 152 `item_filter_relaxed` — filtered bulk inserters, recorded and relaxed.
- 15 `splitter_distribution_relaxed`.
- 76 `machine_recipe_unresolved` — the furnaces carry no `recipe` field and this
  task declares no candidates for them (recipe inference is task 10).
- 14 `underground_unpaired` — 92 entrances and 86 exits form 82 pairings on
  distinct exits, leaving 10 entrances and 4 exits with no far end.
- 3 `unsupported_non_item_entity` — the `ee-super-substation` poles, subsystem
  `power`, mod `unknown`.
- 59 `transport_boundary_candidate`, 44 `transport_internal_break`,
  1 `disconnected_producer`, 1 `inserter_capacity_unknown`,
  1 `inserter_rotation_unresolved`.

**No bound is advertised for the pilot and none can be.** With nothing declared,
`unresolved_reasons` returns three `unsupported entity` reasons for the poles. A
request that declares the unidentified mod and `power: assumed_available`
irrelevant clears those, and `resolve_model_inputs` then consumes the whole graph
(11660 arcs, none disabled, 153 activities, relaxations
`unknown_capacity_unlimited` + `conditional_connections_open`) — but the mechanics
gate is still unmet, the pilot's real feeds, exports, research, control state and
the 76 furnaces' recipes are unresolved, and every arc is `relaxed` or
`conditional`. Anything the LP returned for it would be a shape check, not a
claim about the factory.

## 7. Assumptions, unsupported mechanics, unmet gates

- **The mechanics gate is UNMET and this task does not close it.** 0 observed / 6
  documented-only / 10 pending, unchanged. No controlled game capture was run:
  this session had no Factorio installation and no disposable save. Nothing here
  may be read as a mechanics claim, and
  `test_no_rule_is_observed_yet_so_nothing_may_claim_exact` is the single place
  that will notice when that changes.
- **A turn's lane mapping is asserted to be identity.** That is the one lane
  mapping this module treats as settled without a condition, on the grounds that
  `belt.turn.lane_behavior` questions throughput and path length, not identity.
  If a capture shows otherwise, add a `belt_turn_lane_crossing` condition exactly
  as the other ambiguities are handled.
- **A turn versus a side-load is decided by whether the target has a rear
  feeder.** That is the engine's rendering rule as commonly described, but no
  record states it. It only changes which pending rule is cited and whether the
  lane choice is conditional; both readings stay open in the side-load case.
- **An inserter picking up from a belt is modelled as drawing from that lane's
  exit and dropping at the next lane's entrance** (the contract's lane aliases).
  Physically it acts mid-belt; charging the full lane traversal is the
  conservative structural choice and is noted in the module docstring.
- **Inserter drop lane.** The documented "far lane" rule is *not* applied: both
  target lanes stay open, because restricting on a documented-only rule would
  tighten an optimistic bound.
- **Inserter capacity is `unknown`** for every inserter, relaxed upward by the LP
  with `unknown_capacity_unlimited`. Detailed inserter timing is task 09.
- **Furnace recipes are never inferred.** `RoutingOptions.furnace_candidates` is
  an explicit opt-in; without it a furnace gets inventories, no activity and a
  finding. With candidates, alternatives share the entity's one machine-time
  group and `unresolved_reasons` reports `ambiguous furnace` until the request
  overrides. Task 10 owns inference.
- **Fluids are refused, not approximated**: a recipe touching a fluid produces no
  activity and a `recipe_uses_fluid` finding.
- **No power, beacon, module, quality, rail or logistic-bot behaviour** is
  modelled; those entities stay visible and unsupported.
- Unmet release gates unchanged and untouched by this task: task 02's controlled
  game captures; the pilot's real feeds/exports/mods/research/power/control state
  and the 76 furnaces' recipes; viewer interaction checks; and public
  integration. No live save, MCP registration or server reload was involved, and
  no public tool, MCP schema, CLI registration or skill promise was changed.

## 8. Next

**Task 07 (public integration) and task 08 (independent audit) can proceed on the
transport graph now.** The integrated path exists end to end: a blueprint string →
`load_spatial_view` → `build_transport_graph` → `parse_graph`-valid
`SpatialGraph` → `analyze_delivery`, with hand-checked numbers on twelve
layouts and the real pilot measured for size and time. Task 06 can render the
graph's ports, lanes, arcs, conditions, groups and findings; every one is
contract-shaped and every string in them is untrusted blueprint text to be
rendered as text.

**The prerequisite still required before any bound is advertised for a real
layout is unchanged and is not this task's to close:** task 02's controlled game
captures, following
`daemon/tests/fixtures/routing_mechanics_observations/CAPTURE.md`. Until then
every arc this module builds is `relaxed` or `conditional`, every inserter
capacity is `unknown`, and the pilot in particular additionally needs its declared
mod, power assumption, feeds, exports and furnace recipes.

When captures land, the upgrade path is deliberately narrow: flip a record's
`evidence_status` to `observed` and `semantics_for` starts returning `exact` for
arcs that cite it, `evidence_kind_for` starts returning `observed`, and the
falsified branch of each ambiguity (the reversed rotation sense, the extended
reach, the far side-load lane, the crossing tunnel) can be dropped from
`transport.py` in one place each.
