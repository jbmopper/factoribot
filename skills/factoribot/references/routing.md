# The blueprint routing audit

This is the strict, geometry-aware analysis exposed by `inspect_blueprint_layout`
and `analyze_blueprint_routes`. It is a different question from
`analyze_blueprint`, which stays available and models machine speeds only.

Call `get_capabilities` and read `blueprint_routing` before promising anything:
it reports the live evidence state, the finding-code set, the error codes and
the paging rules. Everything below is what that block currently says.

## What it can and cannot claim

- Every advertised value is an **upper bound under the stated relaxations**.
  It is never an achievable, measured or current rate. There are no lower
  bounds and no starvation claims.
- A bound appears only when `unresolved_reasons` is empty **and** a stage
  returns a certified dual bound. Otherwise the status is `partial`,
  `solver_limit`, `insufficient` or `invalid_request` and no bound is reported.
- **The game-mechanics gate is unmet.** Sixteen historical 2.0.76 mechanics rules
  are recorded: 0 observed, 6 documented-only, 10 pending. They are incompatible
  legacy evidence for the current 2.0.77 profile. So no arc claims `exact`
  semantics, every transport arc is `relaxed` or `conditional`, inserter
  throughput is `unknown` (relaxed upward), and the underground reach, splitter
  distribution, side-load lane and inserter rotation sense all stay open as
  named conditions. Say this when a user asks how much to trust a number.
- Filters and splitter priorities are **recorded and relaxed, never applied**:
  an optimistic bound must not remove a possible path.
- Unsupported entities, unknown prototypes and possible bridges stay **visible**.
  An unsupported possible bridge (`may_connect: true`) withholds every bound and
  every insufficiency claim, whatever the request declares. Unknown connectivity
  can never be deleted and then used to prove impossibility.
- Fluids, non-normal quality, modules, beacons and any game version other than
  2.0.77 are rejected by the contract. Power is an explicit request assumption;
  no coverage, generation or network claim is made anywhere. Rails, logistic
  bots and circuit item behaviour are unsupported.
- MCP analysis never infers a recipe. The optional host-side `routes infer` pass
  derives item-only furnace candidates from the loaded recipe data, explicit
  feeds and exact supported paths. It assigns only an evidence-unique candidate;
  relaxed/conditional paths, unsupported possible bridges, mixed feeds and no
  feed stay grouped for manual assignment. Its additive provenance artifact is
  revalidated before request sealing and makes no rate/runtime-selection claim.
- `evaluate_blueprint_operating_rate` is a separate read-only MCP calculation for
  one sealed, noncompeting serial electric-furnace scenario. It returns a
  conditional analytic operating rate from loaded recipe data, and optionally
  validates the exact required v3 Factorio captures. It is not the routing LP,
  a general simulator, a measured maximum, or a recurrence-proved sustained rate.
- The synthetic fixtures under `daemon/tests/fixtures/` are schema and
  interaction test data. They are not game evidence and validate no mechanic.
- The pinned prototype extract and mechanics records ship as package data under
  `factoribot/evidence/` (source: `daemon/factoribot/evidence/`). Installed builds
  can use them outside the checkout. Missing evidence still produces
  `evidence_unavailable` rather than guessed mechanics.

## Explicit declarations and scoped furnace inference

No feed, export, disposal, research level, mod, control state or power assumption
is ever added for the user. `analyze_blueprint_routes` takes a complete sealed
contract `RoutingRequest`; it performs no inference, and a request that omits
something comes back as `invalid_request` with no numerical claim. Never relax a
budget, invent a removal service or declare an entity irrelevant to make an
answer appear.

`factoribot routes infer` is a preparatory host action. It rebuilds the graph with
the item-only furnace recipes allowed by both the machine's crafting categories
and `assumptions.available_recipes`, propagates possible materials from the saved
feeds to a bounded fixed point, and writes a
`factoribot.routing.furnace_inference` artifact. Every inferred assignment records
its inputs, quantities, feed sources, entity/arc path and assumptions. Existing
manual assignments take precedence; confirmed conflicts are reported. Rerunning
after a feed change discards the old inferred subset and derives a new input hash.
Passing a stale artifact directly to `routes request` fails with
`stale_inference`; stripping the envelope deliberately converts the contained
assignments into ordinary manual declarations and discards inference provenance.

## Restricted operating adapter

`factoribot routes throughput` accepts a sealed v2 operating scenario and its
complete set of sealed v3 captures. The supported model is only a serial chain
of electric furnaces with one item ingredient and one item result per recipe,
one periodic noncompeting supply, counted unbounded removal, normal quality, no
modules/beacons, fixed research, and explicit power/control. It derives machine
craft rates from the exact recipe dump hash and preserves unused supply.

Capture validation independently checks game/build/mod identity, setup blueprint,
named boundary/lane counters, half-open craft events, contiguous windows, and
start/end belt, furnace inventory, and inserter-hand state. It also validates the
scenario-bound straight one/two-lane and fixed-research inserter measurements.
Finite windows always retain `sustained_rate_established: false`. Keep the report's
capacity upper bound, conditional prediction, and actual interval rates separate.
The retained reproduction is documented in
`docs/blueprint-routing-handoffs/23-sol-takeover.md`.

## Identity and paging

- A layout is identified by `graph_hash`. To ask a follow-up detail question,
  resend the **same** `blueprint_string` (or `graph`) and `book_path`, and pass
  `expect_graph_hash` so a changed input fails loudly.
- Preserve `provenance` too: it is part of graph identity. CLI and MCP both accept
  `game_export`, `development_pilot`, and `synthetic`; use the same value when
  inspecting, sealing and analyzing.
- An analysis is identified by `request_hash` and `result_hash`. Resend the
  identical request document.
- `book_path` entries are **book entry index values, not array offsets**.
- Sections are paged. Follow `page.cursor`; a cursor minted against another
  graph or result is refused. `detail.kind = "entities"` scopes to named
  entities and returns their original blueprint records - that is how to answer
  "where is the entity this finding names?".
- Detail scope selects returned detail only. It never changes the model.

## Typical sequence

1. `inspect_blueprint_layout` - counts, arc semantics, conditions, findings and
   `bound_prerequisites` (what a request would have to declare).
2. Report the prerequisites honestly. If the answer is "no bound is possible for
   this blueprint yet", that is the useful answer.
3. With a request the user (or the host CLI) has assembled,
   `analyze_blueprint_routes`, then page findings and inspect entity locations.

## Host-side commands (not MCP)

MCP calls are pure: they write no file. Artifact writing is an explicit host
action from the repository:

```sh
.venv/bin/factoribot routes inspect  --bp BP.txt --view page.html
.venv/bin/factoribot routes infer    --bp BP.txt --template t.json --assignments export.json \
  --out inference.json --request-out request.json
.venv/bin/factoribot routes request  --bp BP.txt --template t.json --assignments export.json --out request.json
.venv/bin/factoribot routes analyze  --bp BP.txt --request request.json --result result.json --view audit.html
.venv/bin/factoribot routes finding  --bp BP.txt --result result.json --finding CODE_OR_ID
.venv/bin/factoribot routes throughput --scenario scenario.json --capture run-1.json \
  --capture run-2.json --request request.json --result result.json --out throughput.json
```

The viewer page exports an assignment draft (feeds, furnace overrides, control
assignments, plus proposed budgets and outlets). Use `routes infer` when the
draft contains recipe-less furnaces; it writes the provenance artifact and can
seal the equivalent request. Otherwise `routes request` seals the draft directly.
`routes analyze` re-analyzes and writes a new page carrying the result. Repeat
the final candidate list reported by `routes infer` as `--furnace-candidate`
arguments when rebuilding that graph for `routes analyze`. The page never solves
and never writes a file by itself.

For an assignment draft, the page owns its declared `budgets`, `exports`,
`surplus`, and `objective`. The host template supplies only the policy fields
`protected`, `assumptions`, and `detail`. A duplicate page declaration is
accepted only when its canonical JSON is identical; otherwise `routes request`
returns the explicit `draft_conflict` error instead of silently choosing a host
or page value. This preserves each lane feed, shared capacity ID, outlet, and
the draft's graph/blueprint/provenance identity through sealing and analysis.
The reproducible two-lane full-belt example is in
`daemon/tests/fixtures/routing_input_drafts/README.md`.

## The pinned pilot

`daemon/tests/fixtures/wip_science.txt` is a development pilot, **not** a
confirmed factory. Its feeds, exports, research, enabled mods, control state,
power and the 76 furnaces' recipes are unresolved, and its three
`ee-super-substation` poles have an unidentified mod origin. **No bound is
advertisable for it.** Under task 19's explicitly illustrative iron feed and the
four base smelting recipes, the inference pass makes no assignments and reduces
the 76 furnaces to three manual-action groups: 38 conditional steel candidates,
19 incompatible-feed furnaces and 19 with no evidence. Those counts describe the
test declaration, not the owner's factory. Analysis remains `partial` naming the
unresolved entities and declarations.
