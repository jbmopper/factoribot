# Task 06 handoff — make the routing audit inspectable

## 1. Identification

- Task: 06 (viewer), component scope against task 00's fixtures. Task 07 still
  owns end-to-end acceptance on real spatial/graph/analysis output.
- Starting snapshot: HEAD `0b0f3da6499fcea21e100fec494c54e7dc979b01` plus the
  existing uncommitted working tree (planner, MCP adapter, skill, task 00
  contract, task 01 fixes). `make test` reported 143 passed at hand-off time.
- Contract version: started against **1.0.0**, finished against **1.1.1**.
  Task 00 amended the contract twice while this task ran (1.0.0 → 1.1.0 →
  1.1.1) and regenerated all fixtures, adding `declared_power.json`. Every
  browser check and every artifact below was **re-run and re-captured against
  the 1.1.1 fixtures**; the earlier 1.1.0 results are superseded, not reported.
- Model: Claude Opus 5 (`claude-opus-5[1m]`).

## 2. What changed

Owned files, all new:

- `daemon/factoribot/blueprint_view.py` (934 lines) — `render_view(graph,
  result=None, assignments=None, *, title=None) -> str` returns one standalone
  HTML document. Also `build_view_model`, `render_model`, `render_bundle`,
  `embed_json`, `assignment_set_from_document`, `check_assignment_document`.
  It accepts either frozen contract records or their `to_dict` wire form;
  `render_view(records) == render_view(to_dict(records))` is asserted by a test.
- `daemon/factoribot/blueprint_view_assets/{view.html,view.css,view.js}`
  (20 / 100 / 1425 lines) — inlined at render time. No framework, build step,
  network access or CDN; the page loads nothing and posts nothing.
- `daemon/tests/test_blueprint_view.py` (356 lines, 33 tests).
- `daemon/tests/fixtures/routing_view/` — `render_examples.py` (regenerates
  every demonstration page including a hostile-label one), `README.md`,
  `edited_assignments.json`, `edited_draft.json`, `screenshots/*.png`,
  and a `.gitignore` so rendered pages are not committed.

Design points that matter to reviewers:

- **No numerical finding is derived in JavaScript.** Every displayed rate,
  ceiling, bound value and coefficient is formatted in Python (`_num` reuses the
  contract's `canonical_json` decimal spelling) and copied into the page as a
  string. JavaScript computes only view state (zoom factor, how many shapes it
  drew) and parses numbers the operator types into the assignment forms.
- **Untrusted text.** The model is embedded in a
  `<script type="application/json">` island with `<`, `>`, `&`, U+2028 and
  U+2029 replaced by their JSON `\uXXXX` escapes, so no `</script`, `<!--` or
  markup can occur; the page renders every label, description, message,
  certificate and raw entity record through `textContent`.
- **No DOM element per arc.** The served document contains exactly one `<div>`
  (asserted by a test); entities, lanes and arcs are drawn on one canvas with
  batched paths and viewport culling. Entity lists in the Model tab are capped
  at 200 rows behind a filter, with the true count shown.
- **Defensive field reading.** Unknown record keys are collected per record and
  displayed generically ("Additional fields ... shown generically") instead of
  being dropped or raising; a missing or empty graph still renders. No schema
  version string is hardcoded anywhere in the module (a test greps for it); the
  exported `AssignmentSet` reuses the graph's own `schema_version`. That is why
  the 1.1.0 → 1.1.1 bump needed no source change: `subsystem`, `mod`, declared
  mods with `provides`/`alters_item_mechanics`, and irrelevance declarations all
  render, the first two first-class and the rest in the request panel.
- **Bounds are labelled, never promoted.** The bounds section header reads
  "Each value is an upper bound under the stated relaxations. It is never an
  achievable or measured rate."; finding bounds are labelled "upper bound under
  stated relaxations"; certificates are labelled "producer attestation, not a
  proof checked here". A test asserts the page never contains "is achievable",
  "achieved rate", "guaranteed rate" or "will produce".
- **Colour is never the only channel.** Severity renders as `✖ ERROR` /
  `▲ WARNING` / `● INFO` plus the word, evidence kind renders as words
  ("conditional - holds only under the named conditions"), and card borders use
  solid / dashed / dotted styles. On the map, unsupported and conditional
  entities get a dashed outline, conditional arcs dashed and relaxed arcs dotted
  strokes; finding evidence gets a thick ring plus cross ticks, the operator's
  own selection a dashed ring, and both sets are also listed as text.
- **No starvation claims.** Every finding whose `evidence_kind` is not
  `observed` carries "Static evidence: no claim about what this machine is doing
  right now."; only `observed` says "Recorded live observation."
- **The page neither solves nor writes.** It produces JSON: a textarea you can
  copy plus an operator-initiated Download button. There is no auto-save, no
  cleanup, no hosted site, no accounts and no telemetry.

### Proposed shared edit (not applied — task 07 owns it)

`daemon/pyproject.toml` currently discovers packages only
(`[tool.setuptools.packages.find] include = ["factoribot*"]`), so the asset
directory ships in an editable install but not in a wheel or sdist. Exact
proposed addition, anywhere after the build-system table:

```toml
[tool.setuptools.package-data]
factoribot = [
    "blueprint_view_assets/*.html",
    "blueprint_view_assets/*.css",
    "blueprint_view_assets/*.js",
]
```

`blueprint_view` reads the assets through `importlib.resources.files`, so no
code change is needed once that stanza exists. Nothing else is proposed: no
public CLI, MCP, capability-metadata or skill change is included, and the
running MCP server was neither changed nor reloaded.

## 3. Commands run and results

```sh
.venv/bin/python -m pytest daemon/tests/test_blueprint_view.py -q     # 33 passed
make test                                                             # 277 passed
.venv/bin/python daemon/tests/fixtures/routing_view/render_examples.py OUTDIR
```

`make test` failed once mid-run with
`daemon/tests/test_blueprint_contract.py::test_schema_version_is_1_1_0_and_fixtures_pin_it`
(`SCHEMA_VERSION == '1.1.1'` asserted against `'1.1.0'`) — task 00's own file
caught mid-edit. Not touched, not fixed; a single rerun after the fixtures
settled gave 277 passed, no skips. No test was skipped and no dependency was
missing. Every file changed is inside this task's ownership.

Python coverage: rendering all seven fixture bundles; rendering with no result
and no assignments; record-vs-dict equivalence; unknown/missing-field tolerance;
"no hardcoded version" grep; `embed_json` escaping; contract-valid hostile
result (message, certificate, limitations, assumptions) and hostile plain-dict
graph (prototype, quality, mod, evidence description, raw record, page title);
asset files carrying no closing-tag sequence; assignment round-trip through
`parse_assignments` for every fixture with book path `[2,7]` preserved; draft
envelope vs bare set; stale blueprint+graph hash detection cross-checked against
`ContractError`; unknown feed endpoint / non-candidate recipe / unknown control
condition; feed on an outgoing port; finding highlight scope; bound labelling;
static-evidence wording; unsupported entities and gaps staying visible with no
bounds; declared irrelevance display.

### Browser verification (actually performed)

Chromium in the Browser pane, pages served from a throwaway
`127.0.0.1:8791` static server (the pane refuses to script `file://`). The
server and the rendered pages were deleted afterwards; no process is left
running.

Performed, all against the 1.1.1 fixtures:

- Opened all six small fixtures plus `large_layout` and the hostile page. No
  console errors on any page.
- `large_layout` (3200 entities / 6400 ports / 3200 lanes / 3200 arcs): the page
  holds **182 DOM elements** total, and a full redraw with all 3200 entities and
  3200 arcs on screen takes **0.46 ms** (mean of 30 forced redraws; 14 MB JS
  heap). Real pointer drag panned the map (centre 79.0,39.0 → 38.2,66.2). Wheel
  zoom-to-cursor took k 4.70 → 11.56 with culling dropping to 672 entities /
  780 arcs drawn; the toolbar Fit / Zoom / Focus buttons were clicked for real.
- Selecting the `large_layout` finding highlights **exactly** entity
  `bp/2/7/e/1`, endpoint `bp/2/7/e/1/lane/left` and arc `belt_1`, and focuses
  the map on them (screenshot `large_layout_finding_highlight.png`).
- `shared_budget`: clicking the `iron` budget row selects both ports that draw
  on it (`bp/2/7/e/1/port/left_in`, `bp/2/7/e/2/port/left_in`) and states
  "2 selected endpoints declare a feed on global budget 'iron'. They share that
  one ceiling; they do not each receive it."
  (screenshot `shared_budget_two_ports_one_budget.png`).
- `furnace_override`: assigned `iron-plate` from the entity's recorded
  candidates through the select; clearing the override shows "Unresolved: this
  entity has several candidates and no assignment."; selected the belt's
  incoming port through the Selection tab and declared a second feed
  (`belt_feed`, budget `stone`, finite ceiling 4) through the form; exported
  both document forms and reimported the `AssignmentSet` through the page's own
  import button ("Imported 2 feed(s), 1 furnace override(s), 0 control
  assignment(s)"). Both exports are checked in and were re-validated in Python:
  `parse_assignments` accepts them against `furnace_override.json`, with
  `bp/2/7/e/1/inventory/ingredients` and `bp/2/7/e/2/port/left_in` and book path
  `[2,7]` intact.
- Stale detection: importing a document with a mutated `graph_hash` or
  `blueprint_hash` is refused with the two hashes printed side by side; ticking
  "load anyway" loads it and raises both a hard banner (stale hash) and a soft
  one ("The displayed analysis was produced for a different assignment set").
- Hostile labels: `window.__pwned` stays `undefined`, the document contains
  **0** `img`/`svg`/`b`/`iframe` elements and exactly 2 `script` elements (the
  data island and the viewer), the finding message renders as the literal text
  `</script><img src=x onerror="window.__pwned=1"><!--`, and the payload also
  appears verbatim in the page title.

Not performed, and why:

- No `file://` interaction test: the Browser pane renders local files as static
  snapshots and refuses to script them, so the localhost server was used
  instead. A plain browser opening the file directly is untested.
- The Download button's actual file write was not exercised (the harness cannot
  observe the browser's download directory); the JSON it hands over is the same
  string the textarea holds, which was validated in Python.
- Wheel zoom was driven by a dispatched `WheelEvent` rather than a hardware
  wheel for part of the session, because the pane was collapsed at that moment
  and the harness cannot deliver scroll to a hidden pane. Drag-pan and all
  button/tab/row clicks were real pointer events.
- Only Chromium was tested. No Firefox or Safari check.
- Touch/pinch input, keyboard-only navigation and a screen reader were not
  tested. Tab buttons carry `role="tab"`/`aria-selected` and finding cards are
  focusable and Enter/Space-activatable, but that is not an accessibility audit.
- Real spatial/graph/analysis output from tasks 03–05 and the pilot does not
  exist yet, so nothing was rendered from real data. That gate belongs to 07.

Reproducible fixtures: `daemon/tests/fixtures/routing_contracts/*.json`
(task 00's, unmodified) and `daemon/tests/fixtures/routing_view/`.

## 4. Concrete counterexample

Every one of the 3200 entities in `large_layout.json` cites evidence record
`fixture_geometry` in its own `evidence_ids`. A plausible implementation that
resolves a finding's highlight by "every entity that references this evidence
ID" would light up the whole factory and tell the operator nothing. The viewer
instead reads the *evidence record's own* scope (`entity_ids`, `endpoint_ids`,
`arc_path`), unioned with the finding's own scope, so selecting that finding
highlights exactly one entity, one lane and one arc out of 3200/3200/3200. The
browser check above and `test_finding_highlight_is_exactly_its_recorded_scope`
both pin that.

Before/after on staleness: `furnace_override.html` opens with no stale banner
and shows the fixture's routing bound of 5 items/s. Changing the furnace
assignment from `stone-brick` to `iron-plate` in the page — a change that
invalidates that number — leaves the number on screen but immediately raises
"STALE: The displayed analysis was produced for a different assignment set. It
no longer describes these edits; re-run the host analysis." The viewer does not
recompute the bound, and it does not hide it either; it marks it as no longer
describing what is on screen.

## 5. Assumptions, unsupported mechanics, unmet gates

- All numbers on screen are copied from the supplied result. The viewer cannot
  tell whether they are sound; it can only repeat the status, relaxations,
  certificate text and limitations the producer attached.
- Staleness is compared by a deterministic key-sorted JSON stringification done
  in the page. Its number spelling matches the contract's for every practical
  capacity value; an exotic magnitude (≥1e21) could spell differently in
  JavaScript and produce a *false* stale warning. That is the safe direction,
  and the authoritative check remains `parse_assignments` on the host.
- Exports and surplus outlets are not part of an `AssignmentSet`. The page keeps
  them in the draft envelope (`document_kind:
  "factoribot.routing.assignment_draft"`) as a *proposed request*; the host must
  assemble and validate the real `RoutingRequest`. The page never builds one.
- The page validates assignment edits structurally (token syntax, duplicate IDs,
  feed not on an outgoing port, outlet not on an incoming port, recipe within
  the entity's recorded candidates, known conditions). It deliberately does not
  reimplement `validate_request`: budget resolution, eligibility against
  materials and fluid rejection stay on the host.
- `large_layout` renders to a 7.5 MiB self-contained page, because each entity
  carries its original blueprint record for viewer/export use (capped at 2000
  characters per entity for display). Source `blueprint`/`prototypes` documents
  are deliberately not embedded; only their hashes are shown. A pilot-sized real
  graph will need a size measurement before 07 ships this to a user.
- Unmet gates that block *this* work from being called finished end-to-end:
  task 02's game evidence, task 03's real spatial import, tasks 04/05's real
  transport graph and bounds, and task 07's public registration plus its
  packaging change above. No game observation, live save or MCP surface was
  touched here, and no synthetic fixture in this task is evidence about
  Factorio.

## 6. What can start next

Task 07 (public integration) can start on the viewer side now: the renderer is a
pure `data -> HTML string` function with no host policy in it, the packaging
stanza above is the only shared edit it needs, and the same function is what a
before/after report should call twice. Its remaining prerequisite is unchanged
and is not a viewer prerequisite: real graph and result output from tasks 03–05
for the end-to-end acceptance run.
