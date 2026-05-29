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

- `factoribot/` — the Factorio mod. Phase 0: dumps recipe/entity/module data to JSON.
  Phase 2: in-game chat GUI + RCON bridge.
- `daemon/` — Python "brain": data loader, production solver (exact math), and a
  provider-agnostic LLM layer exposing a `solve_production` tool. Terminal-first.

## Status

Phase 0/1 (terminal-first): build and validate the solver against real dumped data,
then layer the LLM on top, then wire it into the game.
