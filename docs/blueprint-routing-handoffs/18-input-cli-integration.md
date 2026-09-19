# Task 18 handoff — input-draft CLI integration

## Snapshot and scope

- Starting/current HEAD: `ab25b2a9e4c11e31be551da750510fdeb5f7d6c6`.
- Contract: routing contract `1.1.1`; solver mathematics and graph contracts
  were not changed.
- Task 15's uncommitted viewer/view-model work, task-17 harness work, roadmap
  and prompt documents were already present and were preserved. This task owns
  the public request sealing, route CLI behavior, dedicated integration test and
  this handoff; it also updates the routing reference and the current-work row
  required by the prompt.

## Delivered behavior

- A viewer `factoribot.routing.assignment_draft` is now authoritative for its
  `budgets`, `exports`, `surplus`, and `objective`. The minimal host template
  provides only `protected`, `assumptions`, and `detail`.
- A template may repeat a page-owned value only when its canonical JSON is
  identical. A difference fails with the structured, actionable
  `draft_conflict` error (`fields`, page/host ownership lists, and a removal or
  alignment action); it can no longer silently overwrite the page declaration.
  Bare `AssignmentSet` callers retain the existing full-template workflow.
- `routes request` reports the page declaration fields, the host-policy fields
  and the precedence rule in its success JSON. The CLI help and routing reference
  describe the same rule.
- New synthetic fixture group
  `daemon/tests/fixtures/routing_input_drafts/` contains the task-15-shaped
  two-lane full-belt draft, the minimal policy template and the 999/s conflicting
  host-budget counterexample. It is declaration/topology test data, never game
  evidence.

## Reproducible page → CLI → page loop

From the repository root:

```sh
.venv/bin/factoribot routes inspect --bp daemon/tests/fixtures/routing_input_drafts/two_lane_fast_belt.txt \
  --provenance synthetic --view /tmp/task18-layout.html
# In a permitted local-browser environment, make/export the page draft. The
# deterministic checked-in export is full_belt_same_item_draft.json.
.venv/bin/factoribot routes request --bp daemon/tests/fixtures/routing_input_drafts/two_lane_fast_belt.txt \
  --provenance synthetic --template daemon/tests/fixtures/routing_input_drafts/host_policy_template.json \
  --assignments daemon/tests/fixtures/routing_input_drafts/full_belt_same_item_draft.json \
  --out /tmp/task18-request.json
.venv/bin/factoribot routes analyze --bp daemon/tests/fixtures/routing_input_drafts/two_lane_fast_belt.txt \
  --provenance synthetic --request /tmp/task18-request.json \
  --result /tmp/task18-result.json --view /tmp/task18-page.html
```

Fresh run results:

- inspect wrote the standalone layout page and reported provenance `synthetic`,
  blueprint hash `sha256:4beb99cde1bebd7e05892e44ca21e655b5526a58267fbf0d07e6da732d75ed38`,
  and graph hash `sha256:eb9570f01d8c80ec7b04d73130aec08dc7f60dc28aa7fbd38df09e04e0be6043`;
- request wrote hash `sha256:73c714ace287af34244505dca2e50488a5d6b8e935d0ff4081f5604e4868cffc`,
  listed all four page declaration fields and no unresolved reason;
- analysis wrote a regenerated page and result hash
  `sha256:b10bdf3563df03db649812fbd1126fa2ef364b806bf7d03debf6d6964bd6e36d`.
  It was `feasible_relaxed`; its certified routing upper bound was 15 items/s.
  That is a synthetic relaxed upper bound, never achieved or measured output.

The integration test reads the generated page's JSON island and constructs a
fresh view model from it. It verifies the two exact 15/s feeds, their single
`full_input_1_iron-plate` budget ID, the 30/s shared budget, output/objective,
and graph/blueprint identity. Re-importing the assignments restores the same
declarations. A changed graph fails `stale_identity`; the blocked-output fixture
remains `insufficient` with no implicit surplus sink.

Concrete counterexample: the full-belt page declares one 30/s iron budget for
two 15/s feeds. The checked-in host counterexample declares 999/s instead. The
CLI returns `draft_conflict` for `budgets`; it does not switch the analysis to
999/s. Same-item duplicate JSON is accepted as a migration-compatible copy.

## Verification

```text
.venv/bin/python -m pytest daemon/tests/test_input_cli_integration.py daemon/tests/test_routing_public.py -q
# 43 passed in 3.27s

.venv/bin/python -m pytest daemon/tests/test_input_cli_integration.py::test_fresh_stdio_mcp_replays_the_cli_sealed_synthetic_request -vv
# 1 passed in 1.10s
```

The second command launched a new stdio MCP process from an empty temporary
working directory, submitted the valid sealed request and the same `synthetic`
provenance, and asserted `feasible_relaxed`, the sealed graph hash and the 15/s
routing bound. It does **not** claim that a user's connected MCP server was
reloaded.

`make test` after the final CLI-conflict fixture/test passed: **644 passed in
146.80s**. `git diff --check` passed.

## Milestone and remaining blockers

The current-work record now marks only the implemented declaration/CLI/replay
portion of Milestone 1, explicitly leaving browser interaction acceptance open.
Task 15 could not execute the requested local-file browser click/download/import
flow because desktop browser automation rejected the local artifact URL and its
policy prohibited a local-server workaround. No browser result is claimed here.
Game mechanics evidence and the real pilot's declarations remain separate open
gates. Browser upload, a web backend, furnace inference and sustained-throughput
semantics were not added.
