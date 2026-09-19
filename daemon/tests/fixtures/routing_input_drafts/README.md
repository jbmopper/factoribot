# Input-draft CLI integration fixtures

These are **synthetic declarations and topology input**, not Factorio game
observations, throughput measurements, or a claim about a player's factory.

`two_lane_fast_belt.txt` is a three-segment fast-belt run. Its first belt has
two imported incoming-boundary lanes at 15 items/s each. The task-15-shaped
`full_belt_same_item_draft.json` therefore declares two 15/s feeds on one shared
30/s iron budget. It also explicitly declares its export and continuous external
removal service; neither is inferred by the host template.

`host_policy_template.json` deliberately contains **only** assumptions,
protection, and detail scope. With a viewer draft, the page owns budgets, exports,
surplus, and objective. A differing copy of any of those page-owned keys in the
template fails as `draft_conflict`; an identical copy is accepted for migration
compatibility.
`host_conflicting_budget_template.json` is the checked-in 999/s counterexample:
it must fail rather than override the shown 30/s full-belt budget.

Reproduce the full loop from the repository root:

```sh
.venv/bin/factoribot routes inspect --bp daemon/tests/fixtures/routing_input_drafts/two_lane_fast_belt.txt \
  --provenance synthetic --view /tmp/task18-layout.html
# In a permitted local-browser environment, designate the two input lanes and
# export the page draft. The checked-in draft below is that deterministic fixture.
.venv/bin/factoribot routes request --bp daemon/tests/fixtures/routing_input_drafts/two_lane_fast_belt.txt \
  --provenance synthetic --template daemon/tests/fixtures/routing_input_drafts/host_policy_template.json \
  --assignments daemon/tests/fixtures/routing_input_drafts/full_belt_same_item_draft.json --out /tmp/task18-request.json
.venv/bin/factoribot routes analyze --bp daemon/tests/fixtures/routing_input_drafts/two_lane_fast_belt.txt \
  --provenance synthetic --request /tmp/task18-request.json --result /tmp/task18-result.json --view /tmp/task18-page.html
```

The routing result remains an optimistic upper bound under stated relaxations,
never an achieved or measured rate. The right-lane declaration is available
supply; its unused capacity does not force consumption or create an implicit
sink.
