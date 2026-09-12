# Task 07 handoff — public integration of the routing audit

## 1. Identity

- Task: 07, *Integrate the first usable routing audit*
  (`docs/blueprint-routing-prompts/07-public-integration.md`), under
  `docs/blueprint-routing-prompts/WORKING-RULES.md`.
- Starting snapshot: commit `664662e` ("codex review and next steps") plus the
  uncommitted working tree containing task 04 and fixes A/B/C. `make test`
  reported **503 passed, 0 skipped** before this task.
- Contract version read in full: **1.1.1** (`docs/blueprint-routing-contract.md`),
  plus every handoff in `docs/blueprint-routing-handoffs/` (02, 03, 04, 05, 06,
  fix-a, fix-b, fix-c) and the three task 00 handoffs at the end of the contract.
  Prerequisites were verified by reading the files and running the suites, not by
  accepting completion claims.
- Model: Claude Opus 5 (`claude-opus-5[1m]`).
- Nothing committed, stashed, reset or cleaned. No live save, no game
  modification, and **the user's running MCP server was not reloaded** (§8).

## 2. What changed

Owned and new:

| File | Lines | What |
| --- | --- | --- |
| `daemon/factoribot/routing_public.py` | 1055 | The public surface: layout building + bounded cache, contract `DetailScope` handling, deterministic pagination, compact row projections, analysis summaries, request sealing, capability metadata. Adds no mechanics and no arithmetic. |
| `daemon/tests/test_routing_public.py` | 34 tests | Tool-level integration, identity, paging, errors, purity, capability drift guard, adopted shared edits. |
| `daemon/tests/test_mcp_routing.py` | 2 tests | Real stdio MCP acceptance, cross-checked against direct Python calls. |
| `daemon/tests/test_routing_public_pilot.py` | 5 tests | The pinned pilot end to end. |
| `daemon/tests/fixtures/routing_public/` | 4 files | `generate.py`, `pilot_assignments.json`, `pilot_request_template.json`, `pilot_provenance.json`, `README.md`. |
| `skills/factoribot/references/routing.md` | — | The routing audit's advertised scope for the skill. |
| this handoff | — | |

Owned and changed:

- `daemon/factoribot/tools.py` — two new tool schemas
  (`inspect_blueprint_layout`, `analyze_blueprint_routes`), their handlers, a
  bounded per-`Toolbox` layout cache, `PublicError` → structured error mapping,
  and `get_capabilities` gaining a `blueprint_routing` block plus a
  `blueprint_tools` note. **No existing tool, schema or field was removed or
  renamed.**
- `daemon/factoribot/cli.py` — the `factoribot routes {inspect,request,analyze,finding}`
  command group. Existing subcommands untouched.
- `daemon/pyproject.toml` — the `[tool.setuptools.package-data]` stanza from the
  06 handoff (§7 verifies it from a real wheel).
- `README.md`, `skills/factoribot/SKILL.md`,
  `skills/factoribot/references/development.md` — the routing audit's scope,
  commands and limits.

Adopted parked shared edits (each with a test in `test_routing_public.py`):

| # | From | Change | Test |
| --- | --- | --- | --- |
| 1 | 03 §"Proposed shared edits" 1 | `blueprint.decode_blueprint_string` now delegates to `decode_blueprint(s, DEFAULT_LIMITS)`. | `test_the_legacy_decoder_is_now_bounded` |
| 2 | 02 §"Proposed shared edits" 1 | `mcp_server.load_toolbox` reuses `gamedata.read_dump` instead of inlining the SHA. | `test_the_mcp_loader_reuses_the_shared_dump_digest` |
| 3 | 06 §"Proposed shared edit" | `[tool.setuptools.package-data]` ships `blueprint_view_assets/`. | wheel check, §7 |
| 4 | fix B §5 | The finding-code set is listed in capability/tool documentation. | `test_capability_metadata_lists_every_emitted_finding_code` |
| 5 | 04 §"Proposed shared edits" 1 | `spatial.rotate_offset` is public; `transport.rotate` delegates to it (keeping its own `TransportError` for a non-cardinal direction, so no behaviour changed). `_rotate` remains as an alias. | `test_rotation_has_one_definition` |

**Declined** (04 §"Proposed shared edits" 2): a `SpatialGraph` constructor
accepting a precomputed `graph_hash`. It is a change to task 00's frozen contract
that weakens an integrity check, and it is not needed: the pilot's 6.1 s build is
paid once per process and the in-process layout cache takes a repeat detail call
to **1 ms** (§7). Measured, not assumed.

No other task's module was opened for writing. `blueprint_contract.py`,
`findings.py`, `routing.py`, `blueprint_plan.py`, `routing_lp.py`,
`blueprint_view.py`, `view.js`, `transport_prototypes.py`, `gamedata.py` and
`spatial.py`'s behaviour are unchanged (the `spatial.py` diff is a rename plus an
alias; the `blueprint.py` diff is the delegation above).

## 3. The public surface

### Tools

`inspect_blueprint_layout(blueprint_string | graph, book_path?, section?, detail?, expect_graph_hash?, furnace_candidates?)`
returns a compact summary — counts, prototype/support/subsystem tallies, arc
semantics, named conditions, capacity kinds, finding tallies, the live mechanics
gate, build timings — plus **one** paginated section:
`summary | entities | findings | topology_gaps | arcs | endpoints`.

`analyze_blueprint_routes(blueprint_string | graph, request, section?, page?, ...)`
runs a **complete sealed contract `RoutingRequest`** through
`blueprint_plan.analyze_request_document` and returns status, unresolved reasons,
bounds, finding tallies, witness shape, per-stage solver state/sizes/timings, and
one paginated section (`summary | findings | bounds | witness | request`).

Both are pure and annotated read-only. `analyze_blueprint` and every other
existing tool are untouched; the two answer different questions and the
capability block says so.

### Identity for follow-up detail requests

- **Layout identity is `graph_hash`.** A caller repeats a detail request by
  resending the same `blueprint_string` (or `graph` document) and `book_path`,
  and may pin `expect_graph_hash`; a mismatch is `stale_identity`, never a
  silent answer about a different layout.
- **Analysis identity is `request_hash` / `result_hash`.** A caller resends the
  identical request document.
- **Cursors are opaque tokens bound to that identity** (base64url of
  `{h: <last 12 hex of graph/result hash>, o: offset}`). A cursor from another
  graph or result is `stale_cursor`. Page limits are 1..200; the contract's 10000
  is refused with `oversized_page` and the advice to page. `DetailScope` is the
  contract's own type, so the same object can be embedded in a request; response
  paging (`page`) is separate and never touches the request or its hash.

### Advertised scope (capability metadata, computed at call time)

`get_capabilities().blueprint_routing` reports, from the actual evidence rather
than a constant: schema 1.1.1, profile `base-2.0.76-normal-v1`, the 14 supported
prototypes, `mechanics_evidence` **{documented-only 6, pending 10, observed 0,
gate "unmet"}**, `arc_semantics_available ["relaxed", "conditional"]` (no
`exact`), `advertisable_bounds.pilot = false` with the reason,
`purity {writes_files false, calls_a_model false, reads_live_game_state false}`,
the five result statuses, the **40 finding codes** (20 graph + 20 delivery, each
with a one-line meaning), the error codes, the detail/pagination rules, the
unsupported list, and an explicit note that the synthetic fixtures are not game
evidence. The tool descriptions repeat the same limits in prose.

## 4. Commands run and results

```sh
.venv/bin/python -m pytest daemon/tests/test_routing_public.py -q         # 34 passed
.venv/bin/python -m pytest daemon/tests/test_mcp_routing.py -q            # 2 passed
.venv/bin/python -m pytest daemon/tests/test_routing_public_pilot.py -q   # 5 passed, 8.2 s
.venv/bin/python -m pyflakes daemon/factoribot/{routing_public,tools,cli,mcp_server,blueprint,spatial,transport}.py \
    daemon/tests/test_{routing_public,mcp_routing,routing_public_pilot}.py \
    daemon/tests/fixtures/routing_public/generate.py                      # clean
make test                                                                 # 544 passed
```

- `make test`: **544 passed, 0 failed, 0 skipped, 48.7 s** (503 before; the delta
  is this task's 41 tests). No failure in any file owned by another task.
- **No test is skipped.** The pilot suite skips only if `data/data-raw-dump.json`
  is absent (the pilot's 153 assembling-machine activities need it); the dump is
  present here so it ran.
- No model call is used anywhere in this code or its tests.

### Acceptance checklist

| Requirement | Where it is checked | Result |
| --- | --- | --- |
| Real stdio MCP lists the tools | `test_mcp_routing.py`, fresh server | 12 tools, all `readOnlyHint`, both new schemas `additionalProperties: false` |
| successful | belt layout + declared request | `feasible_relaxed`, routing bound **15.0 items/s** |
| invalid | `{"not": "a request"}` | `invalid_request`, null `request_hash`, no bounds, `isError` |
| conditional | inserter layout, `relax_open` | both rotation conditions kept open; `conditional_connections_open` in the routing relaxations |
| insufficient | `blocked_export.json` fixture | `insufficient`, routing scenario `infeasible`, null value |
| oversized | 40 MB zip bomb; `limit: 9000` | `bad_blueprint`/`decompressed_limit`; `oversized_page` |
| unsupported | `unsupported_bridge` layout; fluid budget | `partial` with no bounds; `invalid_request` |
| structured results agree with direct Python | cross-check loop at the end of the stdio test | 8+ calls compared field by field |
| no diagnostics on protocol stdout | the protocol itself; server stderr captured to a file | clean; `factoribot mcp` with closed stdin writes 0 stdout bytes |
| pure calls create no files | server launched with `cwd=<empty tmp dir>` | directory empty afterwards |
| saved request replays with matching hashes | `test_a_saved_request_replays_with_the_same_hashes`, pilot suite, CLI `cmp` of two result documents | byte-identical |
| existing callers keep working | `test_mcp.py`, `test_agent.py`, `test_server.py` unchanged and green in `make test` | pass |
| packaged assets from an installed package | §7 | pass, with one defect reported (§7) |

## 5. The pinned pilot, end to end

`daemon/tests/fixtures/wip_science.txt` (file SHA-256 `e48fa3fa…55f49a`),
provenance `development_pilot`. Reproduce with the five commands in
[`daemon/tests/fixtures/routing_public/README.md`](../../daemon/tests/fixtures/routing_public/README.md).

1. **Import** — `routes inspect`: graph
   `sha256:9ad0536e3edb…`, blueprint `sha256:e2dc8eedceac…`, prototypes
   `sha256:756af0daaf0d…`.
2. **Select ports** — done twice, and both paths agree: a hand-written
   `AssignmentSet`, and the viewer's own export produced by clicking in a real
   browser (§6). The checked-in `pilot_assignments.json` selects the feed by a
   stated deterministic rule (first `transport_boundary_candidate` endpoint
   resolving to an incoming port: `bp/root/e/2586/port/in_left`; export
   `bp/root/e/334/port/out_left`). Both are ILLUSTRATIVE, not the real interface.
3. **Save assignments** — `routes request` seals
   `sha256:e268cb051a9f…`, checking the assignment document's hashes against the
   graph first (a stale document is refused, not repaired).
4. **Analyze** — `routes analyze`: **`partial`, no bounds, no witness**, with the
   three unresolved reasons listed by entity:
   `unsupported entity: bp/root/e/162`, `…/e/255`, `…/e/1882`. One finding per
   reason (`unresolved_unsupported_entity`), and `mod:unknown:unknown` repeated
   in the result's audit assumptions.
5. **Inspect a finding, show its original entity location** — `routes finding`
   returns `ee-super-substation`, subsystem `power`, mod `unknown`, world
   position **(474, −32)**, footprint (473,−33)–(475,−31), and its untouched
   blueprint record. Clicking the same finding in the rendered page focuses the
   map on centre (474, −32) at ×4.50, drawing 39 of 2771 entities: the CLI and
   the viewer resolve the finding to the same entity.

### Counts and model sizes

| Measure | Value |
| --- | --- |
| entities / ports / lanes / inventories | 2771 / 8392 / 3832 / 458 |
| capacity groups / **arcs (edges)** / activities / evidence / topology gaps | 4729 / **11660** / 153 / 17 / 0 |
| graph findings | 377 |
| arc semantics | 7848 relaxed, 3812 conditional, **0 exact** |
| canonical graph JSON | ~11.96 MB |
| viewer page for the pilot | 13.14 MB, 160 DOM elements, 46 MB JS heap, no console errors |

All of these reproduce task 04's independently hand-derived counts exactly, which
is a useful cross-check between the two tasks: the integration layer is reading
the same graph task 04 measured.

### Latency and memory method

`time.perf_counter` around each step (the `build_seconds` /
`topology_seconds` / `serialize_seconds` in the summary come from `routing.py`'s
own stats); peak memory as **maximum resident set size** from
`/usr/bin/time -l` (macOS) and `resource.getrusage(RUSAGE_SELF).ru_maxrss` in a
separate process. Timing and memory are measured in *different* runs on purpose:
`tracemalloc` inflates the pilot build from 6.1 s to 28 s, so a single traced run
would misreport the latency by 4.5×. Machine: Apple Silicon, Python 3.14.7,
SciPy/HiGHS.

| Step | Pilot |
| --- | --- |
| decode + spatial index | 0.037 s |
| graph build total | **6.1 s** (topology 0.48 s, contract serialization + validation 5.64 s) |
| `parse_graph` of the emitted 12 MB document | 3.8 s (so caching the build beats saving the graph) |
| whole `routes analyze` process incl. the 13 MB page | **7.05 s real, 288 MB peak RSS** |
| repeat `inspect_blueprint_layout` in one process | 6.075 s → **0.001 s** (layout cache) |
| small belt layout, whole tool call | ~35 ms |

Declared-power **experiment** (not a claim about the factory): adding a `power`
irrelevance declaration empties `unresolved_reasons`, and the routing stage then
builds and solves **128,415 variables / 101,438 rows / 304,720 nonzeros** in
0.16 s build + 0.29 s solve + 0.30 s cleanup + 0.31 s certificate, certifying
**0 items/s** for the illustrative export — the two illustrative endpoints are
not connected. That is a structural fact about the endpoints I chose, not about
the factory's throughput, and it is exactly why the shipped fixture declares no
irrelevance.

## 6. Viewer loop, verified in a browser

Chromium in the Browser pane, pages served from a throwaway
`127.0.0.1:8797` static server (the pane refuses to script `file://`); the server
was stopped and the pages deleted afterwards. Actually performed, with real
pointer clicks:

1. `routes inspect --view` produced a graph-only page ("No analysis result was
   supplied to this renderer").
2. Clicked belt `bp/root/e/1` on the map → the Selection tab showed its ports,
   lanes, arcs and original record; selected its `left` lane; in Assignments
   declared budget `iron` (iron-plate, ceiling 100) and feed `feed_1`; clicked
   belt `bp/root/e/3`, selected its `left` lane and declared export `out`.
3. Export / import → the draft envelope carried the `AssignmentSet` **and** a
   `proposed_request` with the budgets, exports and objective declared on screen.
4. `routes request` sealed `sha256:8e7bd0e9ef3f…` from that draft plus a
   host-policy template holding only `protected`, `assumptions` and `detail`.
   **This is the change that completes the loop**: the page's `proposed_request`
   fills `budgets`/`exports`/`surplus`/`objective` when the template omits them,
   an explicit template value always wins, and nothing else is ever taken from
   the page (assumptions, protected interfaces and detail scope stay host
   policy).
5. `routes analyze --view` re-analyzed and wrote a new page. Loaded it: status
   banner "Feasible (relaxed)", all five provenance hashes shown and matching,
   **no stale banner**, the `feasibility_only` finding, "No bound is advertised
   for this result", 2 `<script>` elements and 0 `img`/`svg`/`iframe`, no console
   messages. The page reports no bound because the viewer's default objective is
   `feasible`, which names no maximand — the contract's own rule, not a defect.
6. The 13.14 MB pilot audit page also loads cleanly, draws 2771/2771 entities and
   11660/11660 arcs, and focuses the clicked finding as described in §5.

Not performed: only Chromium; no Firefox/Safari; no touch, keyboard-only or
screen-reader audit; the Download button's actual file write is still
unobservable from the harness (the JSON it hands over is the string I read from
the textarea and then fed to the CLI, which is the same content).

## 7. Packaging: one fix, one defect found

**Fixed (owned).** `[tool.setuptools.package-data]` now ships the viewer assets.
Clean before/after, built with `python -m build --wheel` from two copies of
`daemon/` differing only in that stanza:

```
BEFORE (no stanza):  (no blueprint_view_assets in the wheel)
AFTER  (with it):    factoribot/blueprint_view_assets/{view.css,view.html,view.js}
```

`pip install`ing the AFTER wheel into a fresh venv (no repository on the path)
and calling `render_view` on the `shared_budget` fixture produced an 89,634-char
page with the assets inlined. Verified from the installed package, not the source
tree.

**Defect found, reported not compensated.** The routing surface cannot run from
an installed package at all, because task 02's `transport_prototypes.py` resolves
its evidence relative to the *source tree*:

```python
# daemon/factoribot/transport_prototypes.py:150
_TESTS_ROOT = Path(__file__).resolve().parents[1] / "tests"
PROTOTYPE_FIXTURE_DIR = _TESTS_ROOT / "fixtures" / "routing_prototypes"
OBSERVATION_FIXTURE_DIR = _TESTS_ROOT / "fixtures" / "routing_mechanics_observations"
```

From `site-packages/factoribot/` that resolves to `site-packages/tests/…`, which
no wheel contains and which `package-data` on the `factoribot` package cannot
reach. Reproduction, after installing the wheel into a clean venv:

```sh
python -c "from factoribot.transport_prototypes import load_pinned_extract; load_pinned_extract()"
# PrototypeError: pinned prototype extract not found at .../site-packages/tests/fixtures/routing_prototypes/prototypes.json
```

I did **not** work around it (no bundled copy, no fallback geometry, no invented
evidence status). Instead the failure is now named rather than a traceback:
`build_layout` maps `PrototypeError` to a structured
`evidence_unavailable` error saying the surface needs a repository checkout, the
capability block degrades honestly (`mechanics_evidence.available: false`,
`supported_prototypes: []`), and README/skill say so. Test:
`test_absent_pinned_evidence_is_a_named_error_not_a_substitution`.

Deciding where that evidence should live is task 02's (or the cleanup task's)
call. Two options for the coordinator: move the extract and records into the
`factoribot` package with a `package-data` entry (then this stanza covers them
too), or declare the routing surface repository-only and keep the current honest
refusal.

## 8. Concrete before/after

**Before.** No public tool exposed any part of the routing stack. The pilot could
be analysed only by writing Python against four internal modules, and
`get_capabilities` said nothing about routing, so a caller had no way to learn
that zero mechanics rules are observed.

**After.** One MCP call reports the pilot's structure and, crucially, *why no
number is available*:

```
routes analyze --bp daemon/tests/fixtures/wip_science.txt --request pilot_request.json
status  partial
bounds  []                                   bounds_advertised: false
unresolved_reasons
  unsupported entity: bp/root/e/162
  unsupported entity: bp/root/e/255
  unsupported entity: bp/root/e/1882
```

**Counterexample the surface must not fall for.** Take the same pilot request and
declare the three poles irrelevant. The model then solves happily and certifies a
finite bound — and that bound is only as good as the declaration. The shipped
fixture therefore leaves `irrelevant` empty and the tool returns `partial`; an
integration that had quietly added the declaration to "get an answer" would have
turned an unresolved layout into a number with no evidence behind it. The same
trap in the other direction is `unsupported_bridge`: the two belt runs are not
reachable from each other, so a layer that trusted reachability would report
`insufficient` with a certificate. The contract's `unresolved_reasons` runs
first, the result is `partial`, and
`test_unsupported_possible_bridge_withholds_every_bound` pins it.

**Hand-derived successful case.** Three east-facing fast belts: one lane carries
15 items/s (task 02's extract: 30/s across two lanes). The tool reports routing
15.0, budget 100.0 (the declared ceiling, delivery relaxed), aggregate
`unlimited`. A per-segment double charge would say 7.5 and a per-arc capacity
copy 45; both are named in the test.

## 9. Assumptions, unsupported mechanics, unmet gates

- **The game-mechanics gate is UNMET and this task does not close it.** 0
  observed / 6 documented-only / 10 pending, read at call time from task 02's
  records. No arc claims `exact`, inserter capacity is unknown everywhere, and
  the capability block, both tool descriptions, the skill reference and the
  README all say so. If a capture lands, the advertised scope tightens by itself
  — nothing here has to be edited.
- **No bound is advertisable for the pilot**, and the surface reports that as a
  fact (`advertisable_bounds.pilot: false` with the reason).
- **Nothing is inferred.** No feed, export, removal service, furnace recipe,
  research level, mod, control state or power assumption is ever added. The
  request template must supply them; `seal_request` refuses an incomplete one and
  refuses a stale assignment document.
- **This layer adds no arithmetic.** Every number it returns is copied from a
  contract record. Where I found a defect in another task's module (§7) I
  reported it instead of compensating in the adapter.
- **The layout cache is an optimisation only.** It is keyed by the exact inputs,
  a hit is byte-identical to a rebuild, and
  `test_the_layout_cache_cannot_change_an_answer` compares all three of
  miss/hit/rebuild (excluding the reported build timings, which are a
  measurement).
- **The illustrative pilot endpoints are not the factory's interface.** The
  selection rule is stated in the fixture README and the artifacts say
  ILLUSTRATIVE in their own text.
- Synthetic fixtures under `daemon/tests/fixtures/` are schema and interaction
  test data. They validate no mechanic and are labelled as such in the capability
  block.
- **The user's running MCP server was NOT reloaded.** Everything above was
  verified against **fresh stdio test servers launched by
  `daemon/tests/test_mcp_routing.py`** (`python -m factoribot.cli mcp` with a
  temporary dump, in an empty working directory). The user's server still
  exposes the previous ten tools; it must be reloaded before anyone claims that
  process has `inspect_blueprint_layout` or `analyze_blueprint_routes`.
- Not started, as instructed: cleanup patches (task 13) and live telemetry
  (task 14). No `--open` browser launch was performed from an automated run.

## 10. Next

**Task 08 (independent audit) can start now.** The reproducible entry points:

```sh
# whole suite
make test                                                                  # 544 passed

# the public surface, direct and over real stdio MCP
.venv/bin/python -m pytest daemon/tests/test_routing_public.py \
    daemon/tests/test_mcp_routing.py daemon/tests/test_routing_public_pilot.py -q

# the pinned pilot end to end (see the fixture README for the full sequence)
.venv/bin/python daemon/tests/fixtures/routing_public/generate.py
.venv/bin/factoribot routes analyze --bp daemon/tests/fixtures/wip_science.txt \
    --provenance development_pilot --request /tmp/pilot_request.json \
    --result /tmp/pilot_result.json --view /tmp/pilot_audit.html

# tool schemas and advertised scope
.venv/bin/factoribot tools
.venv/bin/factoribot tool get_capabilities --args - <<'JSON'
{}
JSON
```

Artifacts for 08: `daemon/tests/fixtures/routing_public/` (generator, pilot
assignment draft, request template, provenance) and its README, which also
records the declared-power counterfactual and its model sizes.

The most valuable audit targets in *this* task's scope are: (a) that the
capability block never advertises more than the evidence supports — try flipping
a mechanics record to `observed` and check what changes; (b) that paging and
cursors cannot mix two identities; (c) that `seal_request` adds nothing to a
request; and (d) the §8 counterexamples, especially that no code path lets an
undeclared unsupported entity become a bound.

**The prerequisite still required before any bound is advertised for a real
layout is unchanged and is not this task's to close:** task 02's controlled game
captures, following
`daemon/tests/fixtures/routing_mechanics_observations/CAPTURE.md`. For the pilot
specifically, also its real feeds, exports, removal services, research levels,
enabled mod manifest, control state, power availability and the 76 furnaces'
recipes.

## 11. Audit fixes F-1/F-2

Fixed the two medium findings from the task 08 independent audit
(`docs/blueprint-routing-release-review.md`), both within task 07's owned
scope. Contract version unchanged (1.1.1). No evidence, contract or solver file
touched.

### F-1 — `provenance` unreachable through the MCP schema

**Before**: `additionalProperties: False` on both `inspect_blueprint_layout` and
`analyze_blueprint_routes` schemas (`daemon/factoribot/tools.py`, then lines 362
and 418) listed no `provenance` key, even though
`routing_public.resolve_layout` already reads `args.get("provenance")` and
provenance is hashed into `graph_hash`. A request sealed by `factoribot routes
request --provenance development_pilot` always came back over MCP as
`status: "invalid_request"`, `"Request rejected by the contract validator:
request/graph mismatch"` — the server always rebuilt the graph under the
default `game_export` provenance, so the hashes never matched. The documented
pilot flow (§10 above; `daemon/tests/fixtures/routing_public/README.md`) could
not be replayed over MCP; the only workaround was shipping the whole graph
document through the `graph` parameter instead of `blueprint_string`.

**Fix**: added a `provenance` property (`enum: ["game_export",
"development_pilot", "synthetic"]`, `default: "game_export"`) to both tool
schemas in `daemon/factoribot/tools.py`, with the same three values and default
the CLI's `--provenance` flag already uses (`daemon/factoribot/cli.py:461-462`).
No handler change was needed: `Toolbox._resolve_layout` already forwards `args`
unmodified into `resolve_layout`, which already validated and used
`provenance` — the schema was the only place blocking it.

**Tests added**:
- `daemon/tests/test_routing_public.py::test_provenance_is_exposed_as_a_tool_argument_and_changes_identity`
  — asserts both schemas carry the `provenance` enum/default, that supplying
  `provenance="development_pilot"` changes `graph_hash` relative to the
  default, that it replays deterministically, and that an unknown provenance
  string is refused as `bad_request`.
- `daemon/tests/test_mcp_routing.py::test_analyze_blueprint_routes_replays_the_cli_sealed_pilot_request_over_mcp`
  — a **fresh** stdio MCP test server (never the user's running server),
  following the file's existing pattern. Builds the pilot layout and seals the
  request directly in Python (the oracle), then replays the identical sealed
  request over MCP with `"provenance": "development_pilot"` and asserts the
  result matches: `status: "partial"`, `bounds: []`, the same three
  `unsupported entity: bp/root/e/{162,255,1882}` reasons, and the same
  `graph_hash`. Keeps two negative cases so identity pinning is not weakened:
  omitting `provenance` (defaults to `game_export`) and passing
  `provenance="synthetic"` both still return `invalid_request` against the
  `development_pilot`-sealed request. Also asserts the server's working
  directory stays empty (pure call, no file written).
- Left `daemon/tests/test_routing_audit.py::test_mcp_refuses_a_request_sealed_against_a_different_graph`
  untouched (out of this task's file scope, and it does not need to change):
  it deliberately omits `provenance` from its MCP call, so it keeps exercising
  the still-correct negative case — the same one covered again above.

### F-2 — hardcoded "Zero mechanics rules are observed" sentence

**Before**: `routing_public.routing_capabilities()`
(`daemon/factoribot/routing_public.py`, then line 1028) hardcoded the sentence
`"Zero mechanics rules are observed, so every transport arc is relaxed or
conditional."` inside `advertisable_bounds.reason`, even though the rest of the
capability block (`mechanics_evidence`, `arc_semantics_available`) is computed
live from `mechanics_evidence()`. The audit proved this self-contradictory: with
a scratch evidence copy carrying one `observed` record, the same response
reported `mechanics_evidence.observed: 1` and `arc_semantics_available:
["exact", "relaxed", "conditional"]` while still asserting the fixed sentence
that says zero are observed.

**Fix**: `routing_capabilities()` now derives the sentence from the same
`evidence` dict already computed for `mechanics_evidence` — `observed` count,
total `records`, and `gate` — building either:
- `"Zero mechanics rules are observed (gate: unmet), so every transport arc is
  relaxed or conditional."` (unchanged wording, `observed == 0`), or
- `f"{observed} of {total_records} mechanics rules are observed (gate:
  {gate}), so some transport arcs may claim \`exact\` semantics while the rest
  remain relaxed or conditional."` (`observed > 0`).

**Test added**:
`daemon/tests/test_routing_public.py::test_capability_reason_sentence_tracks_the_observed_count_not_hardcoded`
— mirrors the monkeypatch approach in
`test_routing_audit.py::test_capability_block_is_computed_from_the_records_not_hardcoded`
(scratch copy of `daemon/factoribot/evidence/routing_mechanics_observations/records`
in `tmp_path`, one record flipped to `evidence_status="observed"` with the full
set of fields an observed record requires, `transport.load_mechanics`
monkeypatched to read the scratch directory; the checked-in records are never
touched). Asserts the real (unpatched) baseline still says "Zero mechanics
rules are observed" and states the unmet gate, then that with one observed
record the reason no longer contains that phrase and instead reads `"1 of 16
mechanics rules are observed"` with `"partially observed"`.

### Commands run and results

```sh
.venv/bin/python -m pytest daemon/tests/test_routing_public.py -q
# 36 passed

.venv/bin/python -m pytest daemon/tests/test_mcp_routing.py -q
# 3 passed (the new pilot-replay test: ~27s, dominated by two full pilot
# graph builds — one direct, one inside the fresh MCP subprocess)

.venv/bin/python -m pytest daemon/tests/test_routing_audit.py -q
# 72 passed — the audit's own suite is unaffected, including the still-correct
# negative case in test_mcp_refuses_a_request_sealed_against_a_different_graph

make test
# 625 passed, 0 failed, 0 skipped
```

### Before/after (F-1, the audit's own counterexample)

Before: `analyze_blueprint_routes` called with the CLI-sealed
`development_pilot` request and no `provenance` argument (the only option, since
the schema rejected the key) →
```
isError: true, status: "invalid_request"
finding: "Request rejected by the contract validator: request/graph mismatch"
```
After: the same call with `"provenance": "development_pilot"` added →
```
isError: false, status: "partial", bounds: []
unresolved_reasons: [
  "unsupported entity: bp/root/e/162",
  "unsupported entity: bp/root/e/255",
  "unsupported entity: bp/root/e/1882",
]
```
identical to the direct in-process Python call on the same inputs.

### Files changed in this pass

`daemon/factoribot/tools.py` (two schema additions), `daemon/factoribot/routing_public.py`
(one hardcoded sentence replaced with evidence-derived logic),
`daemon/tests/test_routing_public.py` (+2 tests, additive),
`daemon/tests/test_mcp_routing.py` (+1 test, additive). No other file touched;
nothing committed.

### Assumptions and unmet gates (unchanged)

Same as §9: zero mechanics rules are observed, no bound is advertisable for the
pilot, and F-3/F-4 (low severity, owned by tasks 05 and the Fix A owner
respectively) are out of this pass's scope.
