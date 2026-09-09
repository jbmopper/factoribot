# factoribot

A Factorio engineering assistant with a Codex skill, local MCP tools, and
deterministic production planning. The existing API-backed in-game chat is also
available.

## Use the skill in Codex

With `data/data-raw-dump.json` present (see `make dump` below):

```bash
make setup-codex
```

This installs the planning/MCP dependencies, links the repository's
[`factoribot` skill](skills/factoribot/SKILL.md) into `.agents/skills`, and generates
a project-local `.codex/config.toml`. Global Codex settings are untouched. The
generated config contains checkout-specific paths and is gitignored; run setup
again after moving the checkout. Reload the project or restart Codex if the new
tools/skill are not discovered. Check `codex mcp get factoribot` from this project.

Try:

> Use $factoribot. I have one red belt of copper plates and three red belts of
> iron plates. Maximize equal net exports of automation science, logistic
> science, gears, inserters, transport belts and circuits. Use AM2, no modules.

Then: “Double the circuit export ratio and keep the other ratios and input
budgets.” Codex handles conversation and calls the local tools; this path needs
no Factoribot model API key. It does not route the in-game chat into Codex.

The skill also guides solver development when requested: reproduce a capability
gap, implement the appropriate mathematical model, validate against independent
examples, and update the advertised contract. Ordinary planning does not edit the
solver. MCP tools only read data and calculate.

## Multiple inputs and outputs

`plan_production` uses a continuous linear program with explicit imports,
recipe rates, net exports and allowed surplus. It supports any number of inputs
and outputs, exact/min/max output demands, ratios, weighted output/input
objectives, recipe alternatives, fractional machine limits and modeled power
limits. The default expands canonical/pinned recipes; `available_recipes` selects
an exhaustive candidate set that the optimizer can mix. Unlisted inputs are
unavailable, and `null` explicitly declares unlimited supply.

```bash
.venv/bin/factoribot plan --spec daemon/examples/balanced_six_outputs.json
.venv/bin/factoribot tools                       # JSON schemas
.venv/bin/factoribot tool get_capabilities --args - <<'JSON'
{}
JSON
```

The equal six-output example costs 16 iron and 5.5 copper plates per bundle:
90 iron/s and 30 copper/s yield **60/11 ≈ 5.4545 of each net output/s**, using
87.2727 iron/s and all 30 copper/s. Exported intermediates are in addition to
those consumed by downstream recipes. This is a hand-checkable regression case,
not a special-cased recipe list in the solver.

See [the planning contract](skills/factoribot/references/planning.md) for objectives,
constraints and error semantics. HiGHS uses floating point; results are checked
against every material balance, output ratio and capacity bound before reporting.
The original `solve_production` remains an exact rational requirements calculator.
The legacy `evaluate_throughput` supports one output and only bounds listed inputs;
prefer `plan_production` for strict budgets.

Planning is steady-state and continuous. Rounded machines are build estimates,
not integer optimization. The prototype dump does not establish research/planet
access; routing, startup inventory, fluid temperatures, quality and catalyst-specific
productivity exemptions are not represented. Power covers active crafting
machines, excluding fuel supply, idle drain, beacon and infrastructure draw.
Beacon configurations with power limits/objectives currently fail explicitly.

`make test` runs the suite. New planner tests use hand-solvable synthetic factories
without a game dump, and the MCP integration test launches a real stdio server
with no model credentials. Planning/MCP tests require the `planning`/`mcp` extras
installed by `make setup-codex`; the existing dump-dependent tests need game data.

## Why it's split into two pieces

Factorio's runtime Lua is sandboxed and deterministic (multiplayer lockstep), so it
**cannot make network calls**. The LLM therefore lives in an external daemon. The game
exports its real, mod-aware prototype data; the daemon loads it, an LLM interprets
natural-language requests, and a small deterministic solver computes exact production
numbers over the recipe graph.

## Layout

- `mod/` — the Factorio mod: a `Ctrl+K` chat GUI that talks to the daemon over
  localhost UDP (`helpers.send_udp`/`recv_udp`, needs `--enable-lua-udp`), with a
  "New" button to reset the conversation.
- `daemon/` — Python "brain": data loader, the production solver (exact math), a
  provider-agnostic LLM layer, and the UDP server. Terminal-first.

## The solver

The LLM picks *which* recipes to use; the solver does only exact arithmetic. It
balances the chosen recipe set as a linear system (`fractions.Fraction`, no deps):

- **Byproducts & cracking** — surplus that's consumed elsewhere is netted; oil
  (advanced + heavy/light cracking) balances to zero leftover.
- **Clear failures** — `ambiguous_recipe`, `overconstrained` (add a consumer /
  allow surplus), `underdetermined` (drop a recipe), `infeasible` (negative rate).
- **Belts** — throughput shown in belts, read mod-aware from the data dump.
- **Beacons** — modeled as a per-category effect using the 2.0 profile curve.
- **Two directions** — `solve_production` (targets → inputs) and
  `evaluate_throughput` (fixed inputs → max output + bottleneck).
- **Planner cross-checks** — JSON fixtures in
  `daemon/tests/fixtures/planner_crosschecks/` compare solver output against
  external planner snapshots from Factory Planner, Helmod, or hand-checked
  recipe math.

## Blueprint analysis

Paste a blueprint string (in `make chat`, or `make analyze BP=file`) and it
decodes the entities, groups machines by recipe, and reports the achievable
throughput, the limiting stage (bottleneck) with per-stage utilization, the
external inputs it must be fed, and recipe-less machines (furnaces). Geometry
(belt routing/beacon coverage) isn't modeled; throughput is speed-only for now.

See the proposed [blueprint routing and design cleanup plan](docs/blueprint-routing-design.md)
for spatial analysis, delivery-capacity checks, smelting/power integration, a visual
inspector, validated cleanup patches, and staged implementation milestones.

## Usage

```bash
make setup          # create .venv and install the package (dev + openai extras)
~/Library/Application\ Support/Steam/steamapps/common/Factorio/factorio.app/Contents/MacOS/factorio --dump-data
make dump           # copy data-raw-dump.json from Factorio's script-output
make test           # run the suite
```


After `make setup`, the `factoribot` command lives on the venv:

```bash
.venv/bin/factoribot solve --spec daemon/examples/purple_am2_nomods.json   # offline solve
.venv/bin/factoribot ask "purple science, AM2, no modules"                 # one-off LLM agent
.venv/bin/factoribot chat                                                   # interactive multi-turn
.venv/bin/factoribot analyze --bp data/bp1.txt                              # blueprint analysis (offline)
.venv/bin/factoribot serve                                                  # UDP daemon for the mod
```

The game data is mod-aware: generate it once in Factorio with `--dump-data`, then
`make dump` copies it into `data/` (it's gitignored; tests skip without it). The
`ask`/`chat`/`serve` commands need an OpenAI key via `OPENAI_API_KEY` or
`--key-file`. Run `make` with no target for the full task list.

### In-game bridge

For the `Ctrl+K` GUI (or the `/factoribot` console command) you need the daemon
running *and* Factorio launched with the UDP feature. On macOS, `make play` (or
double-clicking `scripts/factoribot-play.command`) does both — it starts the daemon
and launches Factorio with the flag, which is the part Steam's launch-options field
can't do. Manually it's:

```bash
make serve ARGS=--verbose                              # daemon on port 25001
factorio --enable-lua-udp=25000                        # game socket on a DIFFERENT port
```

The game's `--enable-lua-udp` port **must differ** from the daemon's port — they're
two separate localhost sockets, and reusing one port collides (silent hang, or a
crash on older 2.0 builds). The mod's "daemon port" setting must point at the
daemon (default 25001). With `--verbose` the daemon prints each request it receives;
if nothing prints when you hit Send, the packet isn't reaching it (wrong port, or
`--enable-lua-udp` missing). Prefer `factoribot chat` while iterating — it skips the
bridge entirely.

## Status

Available: Codex skill and local MCP tools, continuous multi-input/multi-output
optimization, the exact requirements solver, blueprint analysis, and the existing
API-backed in-game chat. Integer machine optimization and physical layout/routing
remain future model extensions.
