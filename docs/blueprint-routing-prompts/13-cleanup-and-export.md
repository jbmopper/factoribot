# 13 — Propose and validate one small class of blueprint edits

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 08 and
after all mechanics affected by the selected edit class are validated. Own new
`blueprint_cleanup.py`, patch/candidate tests, and an extension note. After the
coordinator schedules an integration pass, also own the new cleanup/transform
schemas and handlers in `tools.py`, CLI artifact export wiring, capability/skill
updates, and their stdio MCP tests, following 07's verification checklist.
Serialize these shared-file edits with other extensions and coordinate the
before/after viewer additions with its owner.

Start with a narrowly defined removable internal belt branch. Require explicit
user designation that it is expendable, or sufficient evidence under the declared
scope; empty-looking or unused-in-one-LP-solution is not enough. Protect boundaries,
selected entities, expansion areas, wires, buffers, and unknown mechanics by
default. Do not start global layout optimization.

Implement the contract's entity-level patch with canonical baseline hash,
preconditions, affected IDs, explicit operations, and inverse. Reject stale
baselines or failed preconditions atomically. Preserve unknown and unselected
records. Validate all affected references; where additions or reference rewrites
are supported, allocate IDs without collisions and retain typed reference meaning.
Do not blanket-rewrite every integer that resembles an entity number.

For each candidate, return a readable change list, protected-interface check,
entity/cost/footprint metrics supported by available data, and before/after
analysis under the exact same feeds, budgets, exports, and assumptions. Matching
optimistic bounds alone is not evidence of equivalent game behavior. Label
ordering/timing/buffer uncertainty and provide the game-validation procedure.

Acceptance: patch then inverse restores the original semantic document; stale,
colliding, dangling-reference, protected-boundary, and unknown-field cases fail
or preserve data correctly. A candidate affecting a conditional/unsupported
mechanic must not be certified safe. Exercise `propose_blueprint_cleanup` and
`transform_blueprint` through coordinated stdio MCP integration as pure
calculations returning data/strings. Export a separate local blueprint artifact
through the host, and inspect the before/after viewer. Run `make test` and obtain
an independent patch review before advertising this edit class. Do not place it
in the player's live save.
