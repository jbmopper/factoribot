# factoribot

An in-game Factorio assistant backed by an LLM. First capability: a factory-design
calculator you can talk to ("purple science, assembly machine 2, no modules").

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

## Usage

```bash
cd daemon && pip install -e '.[dev,openai]'
python -m factoribot.cli solve --spec examples/purple_am2_nomods.json   # offline solve
python -m factoribot.cli ask "purple science, AM2, no modules"          # LLM agent
python -m factoribot.cli serve                                          # UDP daemon for the mod
```

## Status

Phase 2 complete: hardened solver (balance/belts/beacons/throughput) + in-game
chat with per-player conversation memory. Manual in-game GUI test pending.
