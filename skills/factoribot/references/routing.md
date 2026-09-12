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
- **The game-mechanics gate is unmet.** Sixteen mechanics rules are recorded:
  0 observed, 6 documented-only, 10 pending. So no arc claims `exact`
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
  2.0.76 are rejected by the contract. Power is an explicit request assumption;
  no coverage, generation or network claim is made anywhere. Rails, logistic
  bots and circuit item behaviour are unsupported.
- Recipe-less furnaces are never inferred. Supply candidates explicitly, and
  assign one per entity, or the model stays unresolved.
- The synthetic fixtures under `daemon/tests/fixtures/` are schema and
  interaction test data. They are not game evidence and validate no mechanic.
- The pinned prototype extract and mechanics records ship as package data under
  `factoribot/evidence/` (source: `daemon/factoribot/evidence/`). Installed builds
  can use them outside the checkout. Missing evidence still produces
  `evidence_unavailable` rather than guessed mechanics.

## Nothing is inferred

No feed, export, disposal, recipe, research level, mod, control state or power
assumption is ever added for the user. `analyze_blueprint_routes` takes a
complete sealed contract `RoutingRequest`; a request that omits something comes
back as `invalid_request` with no numerical claim. Never relax a budget, invent
a removal service or declare an entity irrelevant to make an answer appear.

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
.venv/bin/factoribot routes request  --bp BP.txt --template t.json --assignments export.json --out request.json
.venv/bin/factoribot routes analyze  --bp BP.txt --request request.json --result result.json --view audit.html
.venv/bin/factoribot routes finding  --bp BP.txt --result result.json --finding CODE_OR_ID
```

The viewer page exports an assignment draft (feeds, furnace overrides, control
assignments, plus proposed budgets and outlets); `routes request` seals it into
a request, `routes analyze` re-analyzes and writes a new page carrying the
result. The page never solves and never writes a file by itself.

## The pinned pilot

`daemon/tests/fixtures/wip_science.txt` is a development pilot, **not** a
confirmed factory. Its feeds, exports, research, enabled mods, control state,
power and the 76 furnaces' recipes are unresolved, and its three
`ee-super-substation` poles have an unidentified mod origin. **No bound is
advertisable for it.** Analysis returns `partial` naming those three entities.
