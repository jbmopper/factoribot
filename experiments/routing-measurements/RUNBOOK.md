# Throughput measurement harness and isolated runner

`harness.py` is the offline validator for controlled Factorio trials.
`run_trials.py` is the task-23 generator/launcher for the one supported automated
base-2.0.77 furnace-chain scenario. Neither updates the shared mechanics-evidence
manifests or promotes a capture to a general mechanics rule.

## Task 23 automated base-2.0.77 path

The retained scenario, two real captures, and combined report are documented in
[the task-23 handoff](../../docs/blueprint-routing-handoffs/23-sol-takeover.md).
The launcher uses the verified Factorio 2.0.77 build 84539 executable by default.
It creates temporary config/write/mod directories, disables public/LAN
visibility and auto-pause, enables only base, starts a newly named scenario,
stops its own process after the complete capture is readable, and removes all
scratch state. Existing saves, global configuration, and global mods are never
opened or changed.

```sh
PYTHONPATH=daemon .venv/bin/python experiments/routing-measurements/run_trials.py \
  run --scenario experiments/routing-measurements/scenarios/furnace-chain-base-2.0.77-v2.json \
  --out-dir experiments/routing-measurements/captures

PYTHONPATH=daemon .venv/bin/python experiments/routing-measurements/harness.py \
  validate-repeats \
  experiments/routing-measurements/scenarios/furnace-chain-base-2.0.77-v2.json \
  experiments/routing-measurements/captures/routing-measurement-23-base-2077-furnace-chain-run-1.json \
  experiments/routing-measurements/captures/routing-measurement-23-base-2077-furnace-chain-run-2.json
```

The v2 scenario and v3 captures bind recipe-data hashes, blueprint/graph/request
identity, build/mod/research/power/control conditions, named counters, craft
events, inventories and inserter hands. Three equal finite windows remain
finite-window evidence and always report `sustained_rate_established: false`.

## Historical task-17 manual path

The remainder of this runbook records the earlier v1/v2 manual workflow, which
remains supported for legacy fixtures.

## Isolated environment

The only permitted save name prefix is `routing-measurement-17-`; use, for
example, `routing-measurement-17-20260911`. In Factorio's New Game flow, create
a new sandbox/editor save with exactly that name. Do not open, copy, migrate, or
overwrite an existing save. Leave global mod configuration untouched: record the
enabled mod list exactly as the game reports it, including an empty list. Record
the exact executable path and main-menu build before constructing a scenario.

The 2026-09-11 inspection described below predated discovery of the executable
and task-23 game runs. It is retained only as historical context.

## Operator commands

From the repository root, validate the immutable setup plans:

```sh
.venv/bin/python experiments/routing-measurements/harness.py validate-scenarios
```

When a compatible executable is available, start it manually (the command is
only a launch command; it must point at the installed executable):

```sh
FACTORIO_BIN=/absolute/path/to/factorio
"$FACTORIO_BIN"
```

Create the named disposable editor/sandbox save above, then build one scenario
from `scenarios/`. Confirm power, research, and no circuit condition exactly as
the scenario says. After construction, export the exact setup blueprint string.
Warm up for the required ticks. For every contiguous measurement window, record:

- start/end game ticks;
- source extraction count;
- each collector count before any removal;
- all retained setup inventories at both boundaries.

Run each scenario twice. Do not average disagreeing windows or repeats. The
validator reports `window-stable` only for multiple windows with sufficiently
similar collector rates and no retained-inventory change at their boundaries;
otherwise it reports `window-variable`. Neither proves convergence, oscillation
or sustained throughput. Repeats enforce the scenario's tolerance, warmup,
window length, minimum window count and matching setup/operating conditions;
their rates must agree across runs as well as within each run. Save each completed raw capture
outside the evidence manifests, for example in
`experiments/routing-measurements/captures/` (not supplied by this task), then:

```sh
.venv/bin/python experiments/routing-measurements/harness.py validate-capture \
  experiments/routing-measurements/captures/routing-measurement-17-20260911-belt-run-1.json
.venv/bin/python experiments/routing-measurements/harness.py validate-repeats \
  experiments/routing-measurements/scenarios/belt-straight-one-lane.json \
  experiments/routing-measurements/captures/routing-measurement-17-20260911-belt-run-1.json \
  experiments/routing-measurements/captures/routing-measurement-17-20260911-belt-run-2.json
```

Only a reviewed later integration task may decide whether a valid raw
`game-observation` capture closes an evidence gate. Validation is not promotion.

## Capture shape

`samples/synthetic-steady-capture.json` is deliberately labelled
`synthetic-recorder-test`; it proves only parser/calculation behavior. Copy it
as a structural starting point, replace every synthetic field with actual game
facts, and use an actual exported blueprint. The recorder rejects an incomplete
record, an unnamed/non-disposable game save, a deletion-only sink, missing
research/power state, non-contiguous windows, invalid ticks, and conservation
failures.

The conservation invariant for each item in a window is:

```
source_extracted = collected_before_removal + (inventory_end - inventory_start)
```

The blocked-output scenario has `collected = 0`; once fully blocked its source
extraction and retained inventory delta must also be zero. This is the concrete
counterexample to treating available full supply as forced intake.


## Recorder correction — 2026-09-12

Contiguous windows must share identical inventory at their common boundary.
`all_runs_steady` is retained as a compatibility field but is always false:
finite windows cannot establish that assertion. Use `all_windows_stable` for
repeat consistency, and retain every window's measured rate. No inference about
long-run behavior follows from an empty or temporarily blocked collection window.

Capture v2 (`factoribot-routing-measurement-capture-2`) is an additive process
ledger accepted by `validate-capture`. It retains v1 metadata and adds:

- `counter_bindings`: named counters with entity, lane (or inventory), item and
  import/export direction. Each window supplies all counters, including zeros.
- `craft_accounting`: `consume-at-start-produce-at-completion`.
- Window `craft_events`: observed entity, recipe, tick, start/complete kind and
  count. Each timestamp belongs to the half-open [start_tick, end_tick) window.
- `inventory_start`/`inventory_end`: all retained items including inserter hands;
  ingredients already consumed at craft start are not counted twice as inventory.

Consumption/production comes from recorded craft counts and loaded recipe
coefficients, not arbitrary self-balancing ledger numbers. Export rates retain
the exported item's identity. Counter rates remain individually available to
avoid conflating different lanes/branches carrying the same item. These checks
do not validate phase timing or establish that a claimed event was observed.

V1's repeat command deliberately refuses v2 until a process scenario contract
binds recipes, counter placement and timing evidence. Thus R5's basic process
ledger is implemented, but complete timing/profile comparison remains open.
See `process_sample` in the recorder test file for an explicitly synthetic
five-ore-to-one-steel ledger. Do not promote it to game evidence.

A Factorio executable was found at
`/Volumes/Spess/SteamLibrary/steamapps/common/Factorio/factorio.app/Contents/MacOS/factorio`.
Its `--version` reports **2.0.77 build 84539**. Task 23 migrated the routing
profile coherently to 2.0.77 and retained two isolated game captures. Historical
2.0.76 evidence was not relabelled. Existing saves and global mod/configuration
state remained untouched.
