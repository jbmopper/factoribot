# Task 15 handoff — full-belt input UI

## Snapshot and scope

- Starting HEAD: `ab25b2a9e4c11e31be551da750510fdeb5f7d6c6`.
- Contract: frozen routing contract `1.1.1`; no contract/schema/CLI/solver
  changes proposed.
- Work was limited to `daemon/factoribot/blueprint_view.py`,
  `daemon/factoribot/blueprint_view_assets/view.js`, and the new
  `daemon/tests/test_viewer_full_inputs.py`. This handoff is the fourth owned
  path. Existing uncommitted roadmap/prompt/documentation work and the unrelated
  task-17 test/handoff were left untouched.

## Delivered

- The view model exposes a two-lane full-input hint only when it can trace each
  lane to exactly one imported `lane` capacity group. It sums the imported lane
  values for a whole belt in Python; it does not use a belt colour/tier table.
  Missing/unknown capacity disables the shortcut with an explanation.
- An eligible imported incoming boundary belt offers **Full supply** (whole belt
  by default) or selected-lane supply. It can use one item on both lanes or a
  separate item per lane. Known item choices come only from imported activity,
  existing budget, or existing outlet materials; the alternate field is plainly
  labelled as an internal item name and validates the contract token syntax.
- The shortcut emits ordinary deterministic `Feed` IDs and one or two ordinary
  shared `Budget` records. A same-item whole belt uses one total-capacity budget
  and two per-lane-capacity feeds. It is available supply, not forced demand.
  Replacing/removing a designation replaces/removes feeds at exactly those lane
  entrances and prunes only unused shortcut budgets; an advanced shared budget
  used elsewhere remains untouched.
- Imported assembler recipes now appear in selection details even if no analysis
  activity was built for them, and imported activities/assigned inputs label the
  map at readable zoom. Imported text remains `textContent`/escaped JSON only.
- Draft is now the default export. It contains assignments plus proposed budgets,
  exports, surplus, and objective; a matching draft import restores both parts.
  Assignment, budget, outlet, objective, or furnace/control override edits mark
  any displayed result stale. Advanced budget/feed/outlet controls remain.

## Exported draft example

This is the exact draft shape for the hand-checkable two-lane fast-belt fixture
used by the focused test. Each imported lane is 15 items/s; therefore one item
on the full belt is one **shared** 30 items/s budget, never two 30/s budgets.
Its graph identity is fixed by the synthetic fixture construction below.

```json
{
  "document_kind": "factoribot.routing.assignment_draft",
  "assignments": {
    "schema_version": "1.1.1",
    "blueprint_hash": "sha256:797f2dd8eb4e332ae3c47f30d82920aee04dfeb987c6f07d2efbc92d692f192c",
    "graph_hash": "sha256:221da6fd1851b96db41e0996e07b463abd7d03e4609b5c89430ca8559a6bd90d",
    "feeds": [
      {
        "id": "full_input_1_left",
        "budget_id": "full_input_1_iron-plate",
        "endpoint": {"entity": {"book_path": [], "entity_number": 1}, "kind": "port", "name": "in_left"},
        "capacity": {"kind": "finite", "value": 15.0}
      },
      {
        "id": "full_input_1_right",
        "budget_id": "full_input_1_iron-plate",
        "endpoint": {"entity": {"book_path": [], "entity_number": 1}, "kind": "port", "name": "in_right"},
        "capacity": {"kind": "finite", "value": 15.0}
      }
    ],
    "furnaces": [],
    "controls": []
  },
  "proposed_request": {
    "budgets": [
      {
        "id": "full_input_1_iron-plate",
        "material": {"kind": "item", "name": "iron-plate", "quality": "normal"},
        "capacity": {"kind": "finite", "value": 30.0}
      }
    ],
    "exports": [],
    "surplus": [],
    "objective": {"kind": "feasible", "export_id": null}
  }
}
```

The executable expected draft builder is `full_draft` in
`daemon/tests/test_viewer_full_inputs.py`; it verifies the assignment set with
`parse_assignments` against the generated graph. The sample uses synthetic
geometry/capacity input only, not game evidence or a throughput result.

## Verification

Commands and outcomes:

```text
node --check daemon/factoribot/blueprint_view_assets/view.js
.venv/bin/python -m pytest daemon/tests/test_viewer_full_inputs.py daemon/tests/test_blueprint_view.py -q
# 39 passed in 19.74s

.venv/bin/factoribot routes inspect --bp daemon/tests/fixtures/wip_science.txt --view /private/tmp/factoribot-task15-pilot.html
# wrote 14,373,125-byte standalone page; 2,771 entities, 153 activities/AM2 recipes
```

The focused test covers imported fast/basic capacities, a whole belt versus one
lane, opposite-lane materials, the shared-budget counterexample, non-boundary
and outgoing rejection, unsupported declared recipes staying visible, and the
pilot's 153 assembler recipes.

`make test` was started three times, including a final `nohup` run, but this host
terminates individual command captures at roughly 30 seconds before pytest
flushes a final status (the log only contains the pytest invocation). Do not read
that as a passing full suite; rerun `make test` in a normal terminal before
release. `git diff --check` passed.

The requested real browser click/download/import check could not be completed:
the desktop browser automation rejected the local `file:///private/tmp/factoribot-task15-pilot.html`
viewer under its URL policy. Its policy expressly forbids an alternate local
server/browser workaround. No browser assertion is claimed. The generated pilot
page was removed during task cleanup; regenerate it with the recorded CLI command
in a permitted local-browser environment.

## Handoff to task 18

Task 18 can start. Its CLI importer should:

1. recognize `document_kind: factoribot.routing.assignment_draft`, take
   `assignments` through the existing strict `parse_assignments`/identity gate,
   and preserve existing bare assignment imports;
2. merge `proposed_request.budgets`, `exports`, `surplus`, and `objective` into
   the CLI request template, then seal a normal `RoutingRequest` and reject
   invalid/out-of-date identities rather than applying approximate declarations;
3. retain each budget ID exactly: two feeds sharing the full-belt ID are one
   global ceiling; each feed's finite capacity is the single imported lane
   capacity; and
4. regenerate the page from the sealed request/result so the page's draft and
   displayed result agree. Do not add a browser upload/service or turn the
   declared availability into forced consumption.

Remaining gate: run the actual browser click flow (whole belt, lane only, mixed
items, replacement/removal, default draft download and matching/stale reimport)
in an environment permitted to open the local standalone artifact, then rerun
the complete suite.
