# Task 19 handoff — feed-driven furnace inference and replay

## 1. Snapshot, versions, and coordination

- Task: 19, feed-driven furnace inference and replay.
- Starting/current `HEAD`: `ab25b2a9e4c11e31be551da750510fdeb5f7d6c6`.
- Routing contract: `1.1.1`, unchanged. The new additive artifact is
  `factoribot.routing.furnace_inference`, inference version
  `factoribot-furnace-inference-1`; the host integration surface is now
  `factoribot-routing-integration-2`.
- Loaded base recipe/game data used by the tests and CLI: Factorio `2.0.76`.
  The fresh verification environment reported Python `3.14.7`, pytest `9.0.3`.
- Model: Codex on the GPT-5 family; the exact runtime model identifier was not
  exposed.
- Task 18's completed handoff was present before the shared integration edits.
  Its existing viewer/CLI/public work and all unrelated dirty files were
  preserved. No agents, paid model calls, hosted blueprint demo, live save, or
  production deployment were used.

## 2. Delivered behavior and changed files

Core inference is in `daemon/factoribot/furnace_inference.py`:

- derives item-only electric-furnace recipes from the loaded machine crafting
  categories, recipe ingredients/results, and the request's explicit
  `available_recipes`;
- seeds material only from explicit feeds whose feed and shared budget capacities
  are positive, then computes bounded deterministic possible-material and
  exact-evidence fixed points;
- uses all possible paths, including conditional/relaxed arcs and possible
  unsupported bridges, to retain candidates, but uses only exact paths to justify
  an assignment;
- supports chained furnace output evidence without allowing an unassigned furnace
  or disconnected cycle to bootstrap itself;
- preserves explicit overrides, reports incompatible confirmed feed evidence as
  a conflict, and never silently replaces an override;
- records each furnace's entity, full and matching candidate sets, chosen recipe,
  input material and amount per craft, feed/budget source, activity steps, arc and
  entity paths, certainty/uncertainty, and inference assumptions;
- groups unresolved furnaces with the exact `/assignments/furnaces` override path;
- records explicit/inferred assignments separately, input/report/artifact hashes,
  graph/prototype/blueprint identity, limits, iteration/state counts, and
  assumptions in an additive provenance artifact;
- recomputes that evidence during request sealing. Editing a feed, budget,
  available recipe, prototype, graph, limit, or inferred assignment cannot be
  rescued by refreshing the outer hash.

Owned fixtures/tests:

- `daemon/tests/fixtures/furnace_inference/cases.py`
- `daemon/tests/fixtures/furnace_inference/pilot_policy.json`
- `daemon/tests/fixtures/furnace_inference/README.md`
- `daemon/tests/test_furnace_inference.py`
- `daemon/tests/test_furnace_inference_cli.py`
- this handoff

Coordinated shared edits made after task 18 completed:

- `daemon/factoribot/cli.py`: adds `factoribot routes infer`, derives/rebuilds the
  final candidate graph, accepts a source draft or prior inference artifact,
  writes the artifact and optional equivalent sealed request, and reports compact
  manual-action groups.
- `daemon/factoribot/routing_public.py`: prepares and revalidates inference
  artifacts, preserves task 18's page/host precedence behavior, and advertises
  only the demonstrated inference scope.
- `daemon/factoribot/blueprint_contract.py` and
  `daemon/factoribot/blueprint_plan.py`: a furnace with exactly one graph candidate
  but no recorded manual/inferred assignment is now
  `unresolved_unassigned_furnace`. Candidate-list narrowing alone therefore
  cannot bypass the no-feed evidence rule or enter numerical accounting.
- `skills/factoribot/SKILL.md` and `skills/factoribot/references/routing.md`:
  document the preparatory/replay flow, precise limitations, and pilot result.

No inserter timing, throughput solver, routing schema, MCP tool input schema, or
game-mechanics evidence record was changed. The task-specific diff remains
uncommitted in this shared checkout; inspect it with:

```sh
git diff -- daemon/factoribot/furnace_inference.py daemon/factoribot/cli.py \
  daemon/factoribot/routing_public.py daemon/factoribot/blueprint_contract.py \
  daemon/factoribot/blueprint_plan.py daemon/tests/test_furnace_inference.py \
  daemon/tests/test_furnace_inference_cli.py skills/factoribot/SKILL.md \
  skills/factoribot/references/routing.md
```

The new untracked fixture/module/handoff files must be included explicitly by the
coordinator; ordinary `git diff` does not display untracked contents.

## 3. Reproduction and verification

Focused inference, CLI, task-18 integration, contract, and planner regression:

```sh
.venv/bin/pytest -q daemon/tests/test_furnace_inference.py \
  daemon/tests/test_furnace_inference_cli.py daemon/tests/test_blueprint_contract.py \
  daemon/tests/test_blueprint_plan.py daemon/tests/test_routing_public.py \
  daemon/tests/test_input_cli_integration.py
# 196 passed in 14.36s
```

The dedicated fresh stdio MCP replay test launches a new server from an empty
temporary working directory, analyzes the CLI-inferred sealed request against the
same final candidate graph, checks graph identity and the hand-derived loaded-data
bound, and verifies that MCP wrote no files:

```sh
.venv/bin/pytest -q \
  daemon/tests/test_furnace_inference_cli.py::test_fresh_stdio_mcp_replays_the_cli_inferred_request -vv
# 1 passed in 1.26s
```

Full repository suite and whitespace check:

```sh
make test
# 662 passed in 140.72s (0:02:20)

git diff --check
# no output; exit 0
```

The real checked-in pilot was exercised locally without uploading it:

```sh
.venv/bin/factoribot routes infer \
  --bp daemon/tests/fixtures/wip_science.txt \
  --provenance development_pilot \
  --template daemon/tests/fixtures/furnace_inference/pilot_policy.json \
  --assignments daemon/tests/fixtures/routing_public/pilot_assignments.json \
  --out /private/tmp/factoribot-task19-pilot-inference.json \
  --request-out /private/tmp/factoribot-task19-pilot-request.json
```

It rebuilt graph
`sha256:9ad0536e3edb3972b8a111b33490f23f7deaf108ffbe60a9afb5d04c48e7cd87`
as
`sha256:0a67e1bf0670db0c406ed3500a9c3505ba8c5c57737506ab08a6501ff02ee974`.
Input hash was
`sha256:ad6a71999ef69fcd8ca985d7fc8e824941b708a988d0641e46ab065b6fd3e9b5`,
report hash
`sha256:c7012273f990c1c4eda8a9b53088f586b30b453a630e0bb325b47d111940459d`,
artifact hash
`sha256:90acd6227ad47ec3430975cbe92ceef5f50d70754d0d17cb60f2f07f1c799a84`,
and sealed request hash
`sha256:e30bae845ee601d489fc0e2ee3b88870a2eca3705328c2d8ef73ab2de5ff8e1c`.

The illustrative policy produced **zero assignments**. It grouped all 76
furnaces as 38 conditional steel candidates, 19 incompatible-feed furnaces, and
19 with no evidence. The sealed request retained 79 unresolved reasons (the 76
furnaces plus three unsupported mod poles), so no bound was advertisable. These
groups describe only the checked-in illustrative task policy, not the owner's
actual factory or supplies.

## 4. Concrete known-answer cases and counterexamples

In the synthetic exact-path chain, one explicit iron-ore feed reaches furnace 1;
its inferred iron-plate output crosses `plate_to_steel` into furnace 2. The fixed
point records `iron-plate` then `steel-plate`, including steel's loaded-data input
of **5 iron plates per craft** and the originating `ore_feed`/`ore` budget path.
The inference artifact and an equivalent manual assignment produce byte-equal
sealed requests and equal result hashes. With fixture capacities of one craft/s,
the independently derived routing upper bound is 1 / 5 = **0.2 steel/s**.

Counterexamples to convenient guessing are explicit in the fixtures:

- mixed copper and iron ore retains both plate recipes in one actionable group;
- a conditional iron path retains iron as a candidate but creates no assignment;
- the disconnected `item-a -> item-b -> item-a` two-furnace cycle has zero
  possible/exact material states and cannot bootstrap a recipe;
- even when the graph has only `iron-plate` as a candidate, no feed produces no
  assignment, `unresolved_unassigned_furnace`, and no bound;
- changing the recorded iron feed to copper makes the old artifact
  `stale_inference`; rerunning from that artifact discards the prior inferred
  subset and records a new copper-plate inference/input hash.

All hand-checkable graph fixtures are explicitly `synthetic`; their coefficients
test conservation and inference logic and are not promoted to game observations.

## 5. Assumptions, unsupported mechanics, and gates

- Scope is normal-quality, item-only recipes on the currently supported electric
  furnace using explicit available-recipe, feed, and budget declarations.
- Reachability proves only a possible recipe identity. It does not predict item
  rate, runtime recipe selection, scheduling, starvation, achieved throughput,
  power availability, or a measured game result.
- Only exact arcs can justify inference. The current mechanics evidence gate is
  still unmet: 0 of 16 rules are observed, so real blueprint transport arcs are
  relaxed/conditional. This is why the pilot correctly inferred nothing.
- Fluids, fuel semantics, non-normal quality, modules, beacons, implicit sources,
  implicit sinks, and unsupported bridges remain outside this inference scope.
- No live Factorio/game trial was performed and no synthetic case is game
  evidence. The user's running MCP process was not reloaded; only a fresh isolated
  stdio server was tested.
- No acceptance check was skipped within the implemented deterministic scope.
  The external mechanics/game-evidence gate remains intentionally unmet.

## 6. Next task

Task 20 may now consume the integrated inference artifact and begin its required
design note and reusable scenario preparation. It must still preserve the
existing upper-bound solver, obtain task 21's independent design review before
substantial mechanics implementation, and cannot claim a validated sustained
rate until task 17 supplies reviewed, versioned Factorio captures. No such real
capture exists in this checkout yet.
