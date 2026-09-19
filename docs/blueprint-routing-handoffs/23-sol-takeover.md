# Deterministic routing takeover — 2026-09-13

This completes the bounded Factorio 2.0.77 migration and delivers one useful,
reproducible blueprint-to-measurement case. Work was performed on `ab25b2a` plus
the supplied uncommitted task 15–22 files; no unrelated changes were reset,
stashed, or committed.

## Delivered result

The retained case is a one-furnace iron-plate stage feeding a one-furnace
steel-plate stage through fast belts and zero-bonus fast inserters. The page draft
declares one named 15 items/s ore lane as available supply and one named steel
lane with counted unbounded removal. Furnace recipes are explicit user overrides;
the optional inference pass preserves them and records conditional route evidence.

The sealed routing LP result is `feasible_relaxed` and certifies an upper bound of
`0.125 steel-plate/s`. The separate deterministic serial-furnace adapter derives a
conditional operating prediction of `1/8 steel-plate/s` from the exact loaded
recipe and machine coefficients. Two isolated Factorio 2.0.77 build 84539 runs
each recorded three 3,600-tick windows after a 3,600-tick warmup:

| Run | Measured steel counts | Measured rates |
| --- | --- | --- |
| 1 | 7, 8, 7 | `7/60`, `2/15`, `7/60` items/s |
| 2 | 7, 8, 7 | `7/60`, `2/15`, `7/60` items/s |

All six windows match the prediction under the tolerance frozen in the scenario
before the runs: the larger of one item per window and 0.5% relative error. This
is finite-window game evidence, not a maximum-throughput measurement and not a
recurrence-proved sustained rate. Every result document says
`sustained_rate_established: false`.

The same runs also retained aligned, named measurements for the preliminary
mechanics cases. In every post-warmup window and both repeats:

- one fast-belt lane imported and exported exactly 15 items/s;
- two fast-belt lanes imported 15 items/s each and exported 30 items/s total;
- one fast inserter moved 2.5 items/s chest-to-chest at inserter capacity bonus 0.

These observations validate only the exact disposable setup. They were not used
to relabel the 16 historical 2.0.76 mechanics records as current observations.

## Runtime and evidence migration

- Runtime request validation and generated contract fixtures now target
  `base-2.0.77-normal-v1` and base mod 2.0.77.
- The preferred full dump is
  `data/data-raw-dump-2.0.77-base.json`, SHA-256
  `be65dc3615d5939e522b00543b2925a02cfa890dbc9c00882dfe1c4629670f60`.
- The packaged prototype extract is generator-built from that dump and binds its
  full environment. The base-only extract intentionally omits
  `ee-super-substation`; the development pilot still exposes its three instances
  as unsupported topology gaps.
- Mechanics observations retain their true `base-2.0.76-normal-v1` provenance.
  The current 2.0.77 profile reports them as incompatible legacy evidence, so
  none silently tightens routing semantics.

## Operating and capture contracts

`sustained_throughput.py` now contains only a deliberately restricted analytic
adapter for a noncompeting serial electric-furnace chain. It is not a general
simulator. A sealed v2 scenario binds the blueprint, graph, request, inference,
full recipe dump, packaged extract, game version, build expectations, source and
removal schedules, research, power/control, counters, warmup, window lengths,
repeats, and frozen tolerance.

Sealed v3 captures bind the exact trial blueprint and isolated environment. The
validator independently checks timestamped craft starts/completions against
loaded recipe coefficients, every named import/export counter, contiguous
windows, and start/end contents for belt lines, furnace source/result inventories,
and inserter hands. The straight-lane and fixed-research inserter counters are
also scenario-bound and conservation-checked. The predictor is never used to
derive observed internal consumption.

`factoribot routes throughput` writes one report while keeping three meanings
separate: capacity upper bound, conditional operating prediction, and actual
finite-window measurement. The read-only MCP tool
`evaluate_blueprint_operating_rate` performs the same deterministic calculation
from JSON documents and loaded data; it writes no files and calls no model.

## Retained artifacts

- `experiments/routing-measurements/cases/furnace-chain-blueprint.txt`
- `experiments/routing-measurements/cases/furnace-chain-assignment-draft.json`
- `experiments/routing-measurements/cases/furnace-chain-inference.json`
- `experiments/routing-measurements/cases/furnace-chain-request.json`
- `experiments/routing-measurements/cases/furnace-chain-capacity-result.json`
- `experiments/routing-measurements/cases/furnace-chain-throughput-report.json`
- `experiments/routing-measurements/cases/furnace-chain-input.html`
- `experiments/routing-measurements/cases/furnace-chain-result.html`
- `experiments/routing-measurements/scenarios/furnace-chain-base-2.0.77-v2.json`
- `experiments/routing-measurements/captures/routing-measurement-23-base-2077-furnace-chain-run-{1,2}.json`

The headless launcher creates a new scenario inside a temporary config, write
directory, and mod directory with only base enabled. It disables public/LAN
visibility and auto-pause, waits until the complete capture JSON is readable,
stops only its own process, and lets `TemporaryDirectory` remove all scratch
state. It never opens or migrates an existing save or global mod/config directory.

## Exact reproduction

From `/Users/juliusmopper/Dev/factoribot`:

```sh
PYTHONPATH=daemon .venv/bin/python experiments/routing-measurements/run_trials.py \
  blueprints \
  --analysis-out experiments/routing-measurements/cases/furnace-chain-blueprint.txt \
  --trial-out experiments/routing-measurements/cases/furnace-chain-trial-blueprint.txt

.venv/bin/factoribot --data data/data-raw-dump-2.0.77-base.json routes inspect \
  --bp experiments/routing-measurements/cases/furnace-chain-blueprint.txt \
  --provenance synthetic --furnace-candidate iron-plate \
  --furnace-candidate steel-plate \
  --graph experiments/routing-measurements/cases/furnace-chain-graph.json \
  --view experiments/routing-measurements/cases/furnace-chain-input.html

PYTHONPATH=daemon .venv/bin/python experiments/routing-measurements/run_trials.py \
  draft --graph experiments/routing-measurements/cases/furnace-chain-graph.json \
  --draft-out experiments/routing-measurements/cases/furnace-chain-assignment-draft.json \
  --policy-out experiments/routing-measurements/cases/furnace-chain-policy.json

.venv/bin/factoribot --data data/data-raw-dump-2.0.77-base.json routes inspect \
  --bp experiments/routing-measurements/cases/furnace-chain-blueprint.txt \
  --provenance synthetic --furnace-candidate iron-plate \
  --furnace-candidate steel-plate \
  --assignments experiments/routing-measurements/cases/furnace-chain-assignment-draft.json \
  --graph experiments/routing-measurements/cases/furnace-chain-graph.json \
  --view experiments/routing-measurements/cases/furnace-chain-input.html

.venv/bin/factoribot --data data/data-raw-dump-2.0.77-base.json routes infer \
  --bp experiments/routing-measurements/cases/furnace-chain-blueprint.txt \
  --provenance synthetic --furnace-candidate iron-plate \
  --furnace-candidate steel-plate \
  --template experiments/routing-measurements/cases/furnace-chain-policy.json \
  --assignments experiments/routing-measurements/cases/furnace-chain-assignment-draft.json \
  --out experiments/routing-measurements/cases/furnace-chain-inference.json \
  --request-out experiments/routing-measurements/cases/furnace-chain-request.json

.venv/bin/factoribot --data data/data-raw-dump-2.0.77-base.json routes analyze \
  --bp experiments/routing-measurements/cases/furnace-chain-blueprint.txt \
  --provenance synthetic --furnace-candidate iron-plate \
  --furnace-candidate steel-plate \
  --request experiments/routing-measurements/cases/furnace-chain-request.json \
  --result experiments/routing-measurements/cases/furnace-chain-capacity-result.json \
  --view experiments/routing-measurements/cases/furnace-chain-result.html

PYTHONPATH=daemon .venv/bin/python experiments/routing-measurements/run_trials.py \
  prepare --request experiments/routing-measurements/cases/furnace-chain-request.json \
  --inference experiments/routing-measurements/cases/furnace-chain-inference.json \
  --out experiments/routing-measurements/scenarios/furnace-chain-base-2.0.77-v2.json

PYTHONPATH=daemon .venv/bin/python experiments/routing-measurements/run_trials.py \
  run --scenario experiments/routing-measurements/scenarios/furnace-chain-base-2.0.77-v2.json \
  --out-dir experiments/routing-measurements/captures

PYTHONPATH=daemon .venv/bin/python experiments/routing-measurements/harness.py \
  validate-repeats \
  experiments/routing-measurements/scenarios/furnace-chain-base-2.0.77-v2.json \
  experiments/routing-measurements/captures/routing-measurement-23-base-2077-furnace-chain-run-1.json \
  experiments/routing-measurements/captures/routing-measurement-23-base-2077-furnace-chain-run-2.json

.venv/bin/factoribot --data data/data-raw-dump-2.0.77-base.json routes throughput \
  --scenario experiments/routing-measurements/scenarios/furnace-chain-base-2.0.77-v2.json \
  --capture experiments/routing-measurements/captures/routing-measurement-23-base-2077-furnace-chain-run-1.json \
  --capture experiments/routing-measurements/captures/routing-measurement-23-base-2077-furnace-chain-run-2.json \
  --request experiments/routing-measurements/cases/furnace-chain-request.json \
  --result experiments/routing-measurements/cases/furnace-chain-capacity-result.json \
  --out experiments/routing-measurements/cases/furnace-chain-throughput-report.json
```

## Remaining boundaries

- No prediction is offered for merges, splitters or priority/filter behavior,
  turns, side-loading, underground routing, cycles, competing shared budgets,
  general inserter phases, arbitrary machine layouts, modules, beacons, fluids,
  non-normal quality, or modded mechanics.
- The development pilot remains partial: its three `ee-super-substation`
  instances are visible unsupported gaps in the base-only profile, and its real
  supplies, exports/removal, enabled mods, research, controls, power conditions,
  and furnace choices are not owner-confirmed.
- The known browser policy still blocks automated navigation to the local HTML
  page and expressly forbids localhost or alternate-browser workarounds. No click,
  download, or import pass is claimed. In a permitted browser, manually open the
  retained input page, edit/export the draft, run the commands above, and
  open the retained result page to confirm the declarations and stale-state UX.
- Layout optimization remains deferred until candidate mechanics fall inside a
  validated operating subset.

## Verification

Focused final operating/capability regression: **42 passed in 2.71 seconds**.
Final full `make test`: **693 passed in 147.78 seconds**, with no failures,
expected failures, or skips. Every retained experiment JSON document parses;
both captures and the repeat comparison revalidate; `git diff --check` is clean;
and no task-23 Factorio temporary directory remains.
