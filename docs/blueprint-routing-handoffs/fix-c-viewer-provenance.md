# Fix C handoff — viewer prototype provenance matching

## 1. Identification

- Task: Fix C (viewer prototype provenance), from
  `docs/blueprint-routing-prompts/NEXT-STEPS.md`.
- Starting snapshot: HEAD `664662e975dba2092aabeade322a27cb86bb0af3`
  ("codex review and next steps"), which contains the reviewed commit
  `76fd016` as an ancestor, plus the existing uncommitted working tree
  (planner, MCP adapter, skill, other in-flight fix work). Contract/schema
  version in this snapshot: `1.1.1`.
- `make test` at hand-off: **336 passed, 1 failed** (see §3 — the failure is
  outside this task's ownership).
- Model: Claude Sonnet 5.

## 2. What changed

Owned files:

- `daemon/factoribot/blueprint_view.py` — in `build_view_model`:
  - The rendered `result` model now carries `"prototype_hash"` (formatted the
    same way as the existing `blueprint_hash`/`graph_hash` fields), so it is
    no longer dropped between the wire result and the page.
  - `result["graph_match"]` now also requires
    `result.get("prototype_hash") == graph.get("prototype_hash")`, in
    addition to the existing blueprint/graph comparison. A missing hash on
    either side compares unequal via plain `==`, so "missing prototype hash"
    falls out of the same check rather than needing separate handling.
- `daemon/factoribot/blueprint_view_assets/view.js`:
  - The `graph_match === false` banner text was updated from "a different
    graph or blueprint" to explicitly name all three provenance hashes
    (blueprint, prototype, graph) and to state the missing-or-mismatched
    framing, since prototype-only mismatches now trigger it too.
  - Added three `kv` rows in the Findings/Analysis panel — "result blueprint
    hash", "result prototype hash", "result graph hash" — so the result's own
    provenance (not just the graph's, which was already shown in the Model
    tab) is visible next to the result hash/request hash that were already
    there.
- `daemon/tests/test_viewer_provenance_regressions.py` (new, 7 tests):
  reproduces the defect against `daemon/tests/fixtures/routing_contracts/shared_budget.json`
  and pins the fix for: valid matching data, prototype-only mismatch, missing
  prototype hash, blueprint-only mismatch, graph-only mismatch, and all three
  mismatched at once. Each mismatch case also asserts that the authoritative
  path (`findings.parse_result`, which calls `validate_result`) independently
  rejects the same mutated data with `ContractError`, to keep the two checks
  (host-authoritative vs. viewer-defensive) distinguishable.

No solver or shared-contract file was touched (`routing_lp.py`,
`blueprint_plan.py`, `blueprint_contract.py`, `findings.py`, `tools.py`,
`mcp_server.py`, `cli.py`, `skills/` are all unmodified).

## 3. Commands run and results

```sh
.venv/bin/python -m pytest daemon/tests/test_viewer_provenance_regressions.py -q   # 7 passed
.venv/bin/python -m pytest daemon/tests/test_blueprint_view.py -q                  # 33 passed (unchanged suite still green)
make test                                                                          # 337 passed (first run, before rerun below)
```

A second `make test` run later (after no further edits) showed:

```
336 passed, 1 failed
FAILED daemon/tests/test_blueprint_plan.py::test_unsupported_bridge_and_unknown_power_withhold_all_claims
  assert any(f.code == "unresolved_model" for f in report.result.findings)
```

Reran that one file in isolation and it failed the same way both times
(`.venv/bin/python -m pytest daemon/tests/test_blueprint_plan.py -q` →
`1 failed, 31 passed`). This is in `daemon/factoribot/blueprint_plan.py` /
`daemon/tests/test_blueprint_plan.py`, which is Fix B's ownership (duplicate
finding IDs / finding-code identity), not touched by this task and unrelated
to provenance hashing — the assertion is about a finding *code* name
(`unresolved_model`) that Fix B's in-flight identity rework appears to be
changing. Reported by file per the coordinator's instructions; not
investigated or fixed here. No other test in the suite failed in either run,
and `daemon/tests/test_viewer_provenance_regressions.py` and
`daemon/tests/test_blueprint_view.py` were green both times.

### Browser verification (actually performed)

Rendered two standalone pages with `render_view` from a throwaway script
(deleted afterwards) against the `shared_budget` fixture, mutating the raw
result dict directly (not through `parse_result`, since that would reject the
tampered data before it ever reached the page — the point is to check what
the viewer does when it is handed already-tampered/stale wire data):

- `valid.html`: unmodified `shared_budget` result. Confirms the baseline: no
  stale banner, `status` banner "Feasible (relaxed) — …" shown normally,
  "result prototype hash" row shows the correct hash matching the graph's.
- `mismatch.html`: `prototype_hash` flipped to a different validly-formatted
  `sha256:` hash, `result_hash` resealed the same way
  `daemon/tests/fixtures/routing_contracts/generate.py`'s `seal()` helper
  does (pop the field, `content_hash` the rest, set it back), **and** the
  finding's `message` replaced with the hostile payload
  `</script><img src=x onerror="window.__pwned=1"><!--` and the page title
  set to include the same payload, to check the fix doesn't regress existing
  text-safety guarantees while exercising the new banner.

Served both from `127.0.0.1:8791` via `python3 -m http.server` in the
session's scratchpad directory (the Browser pane refuses to script
`file://`, per the task 06 handoff's approach). Opened both pages in the
Browser pane (Chromium) and checked:

- `valid.html`: page text and console are clean (no console messages at
  all); no `STALE` text appears anywhere on the page; "result prototype
  hash" reads `sha256:f00e9b53c3…`, matching the graph's own prototype hash
  shown elsewhere on the page.
- `mismatch.html`:
  - A new red banner reads exactly: `STALE: The displayed result's
    blueprint, prototype or graph provenance does not match what is loaded
    here (missing or mismatched hash).` — confirming the prototype-only
    mismatch is now flagged (before the fix, `graph_match` stayed `true` and
    no such banner would render).
  - "result prototype hash" shows the mutated hash
    (`sha256:000e9b53c3…`), visibly different from the graph's
    `sha256:f00e9b53c3…` shown in the Model tab — the mismatched value is
    preserved and displayed, not hidden or silently corrected.
  - `window.__pwned` is `undefined` (checked via `javascript_tool`; the key
    was absent from the serialized probe result, which only happens for an
    `undefined` value).
  - `document.querySelectorAll('img').length === 0` and
    `document.querySelectorAll('svg').length === 0`; exactly 2 `<script>`
    elements exist (the JSON data island plus the viewer script).
  - The finding card's message renders as the literal text
    `</script><img src=x onerror="window.__pwned=1"><!--`; reading it via
    both `textContent` (raw payload) and `innerHTML` (confirmed to be the
    HTML-entity-escaped form, `&lt;/script&gt;&lt;img …`) verified it went
    through `textContent` assignment, not markup insertion.
  - No console errors or warnings.
  - A screenshot was taken confirming the visual layout: the red STALE
    provenance banner sits above the existing green status banner, and the
    hostile finding text renders inertly inside the finding card with no
    broken layout.

Not performed: no interaction (drag/zoom/selection) beyond loading and
reading the two pages, since the change is confined to a banner condition and
two data fields — task 06's handoff already covers general map interaction
and hostile-label coverage in depth, and this task's own regression file
covers the model-level cases exhaustively in Python. Only Chromium was
checked. The server (`python3 -m http.server 8791`) was stopped
(`pkill -f "http.server 8791"`) and the scratchpad rendering directory was
deleted after the checks; nothing was left running.

Reproducible fixtures: `daemon/tests/fixtures/routing_contracts/shared_budget.json`
(unmodified); the mutation and reseal steps are inlined in
`daemon/tests/test_viewer_provenance_regressions.py` (`reseal_result_hash`,
`flipped_hash`) so they don't depend on the deleted scratchpad script.

## 4. Concrete before/after

Before, from `daemon/tests/test_viewer_provenance_regressions.py::test_reproduction_prototype_only_mismatch_was_shown_as_matching`
(reproduces the exact case in the task): load `shared_budget.json`, set
`result["prototype_hash"]` to a different validly-formatted hash, reseal
`result_hash` the way the fixture generator does, and call
`build_view_model(graph_dict, mutated_result, assignments_dict)`. Before this
change, `model["result"]["graph_match"]` was `True` — the page would show the
result as current even though `findings.validate_result` (and, independently,
`findings.parse_result` called directly on the same mutated dict) reject it
with `ContractError` because `blueprint_hash`/`prototype_hash`/`graph_hash`
must all agree between a result and its graph.

After: the same call now returns `model["result"]["graph_match"] == False`,
and `model["result"]["prototype_hash"]` still reports the mutated (mismatched)
value rather than silently dropping it — confirmed both by the Python
regression test and by the browser check above, where the STALE provenance
banner now renders for exactly this case.

Task-specific diff: `git diff -- daemon/factoribot/blueprint_view.py
daemon/factoribot/blueprint_view_assets/view.js` plus the new file
`daemon/tests/test_viewer_provenance_regressions.py` (not a diff against a
prior version, since it's new).

## 5. Assumptions, unsupported mechanics, unmet gates

- `AssignmentSet` (the operator-editable document the page imports/exports)
  carries only `blueprint_hash` and `graph_hash`, not `prototype_hash` — see
  `daemon/factoribot/blueprint_contract.py`'s `AssignmentSet` dataclass. This
  fix only touches **result**-vs-**graph** provenance (`graph_match`), which
  is the gap the task named; `check_assignment_document`'s assignment-import
  staleness check was left as-is, since it has nothing to gain from a
  prototype hash the assignment schema doesn't carry.
- As before this fix, `graph_match` (and now its prototype-aware form) is a
  page-side convenience derived once in Python and copied into the model; the
  page does not recompute it. The authoritative check remains
  `findings.validate_result` on the host — this change does not touch that
  function or claim to replace it.
- The banner wording change ("blueprint, prototype or graph provenance…")
  necessarily became less specific about *which* hash mismatched, since
  `graph_match` is a single boolean folding three comparisons. Splitting it
  into three independent banners (or reporting which hash(es) actually
  differ) would be a reasonable follow-up but was left out to keep this
  change bounded to the named defect, per the assignment's own instruction to
  defer unrelated viewer redesign. The exact mismatching hash values are
  still visible side-by-side on screen (graph's own hashes in the Model tab,
  result's hashes in the Findings/Analysis panel via the three new rows), so
  an operator can still work out which one disagrees.
- Unmet/unrelated gate observed during verification: `make test` fails
  reproducibely (both runs) on
  `daemon/tests/test_blueprint_plan.py::test_unsupported_bridge_and_unknown_power_withhold_all_claims`,
  inside Fix B's ownership (`blueprint_plan.py` finding-code identity), not
  this task's files. Not investigated further here.

## 6. What can start next

This task's scope (viewer prototype provenance) is complete and independently
testable; nothing here blocks other in-flight work. The one thing worth
flagging to the coordinator: `test_blueprint_plan.py`'s
`test_unsupported_bridge_and_unknown_power_withhold_all_claims` is currently
red on this checkout, in a file owned by the Fix B assignment — that owner
(or the coordinator, before integrating Fix B) should be the one to confirm
whether it's mid-edit breakage or a real regression.
