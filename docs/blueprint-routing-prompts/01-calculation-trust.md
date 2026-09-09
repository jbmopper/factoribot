# 01 — Make existing calculation options and units trustworthy

Implement this task under `docs/blueprint-routing-prompts/WORKING-RULES.md`.
It is independent of 00. Read `spec.py`, `solver.py`, `planner.py`, `plan_spec.py`,
`bpanalyze.py`, `report.py`, `tools.py`, and their tests before editing.

Own the calculation fixes in those existing files, a shared validation helper if
needed, and focused tests. Own the associated legacy schema/capability wording
changes in this task; finish these before task 07 edits `tools.py`. Coordinate
skill/reference changes with the integration owner.

Reproduce the legacy unused machine-option failure with a small case: an invalid
category key currently permits fallback to a default machine while the planner
rejects it. Implement common validation for unused machine/module/beacon category
options and supported aliases without changing intended default-machine semantics.
Make the resolved choices and replayable request visible in numerical results.

Make craft rates unambiguous in text and structured output. For multi-result or
multi-item-yield recipes, report crafts/s and output items/s distinctly. Prefer
additive explicitly named fields with documented legacy aliases over breaking
consumers by silently changing the meaning of `capacity_per_s`.

Acceptance:

- The same unsupported option fails clearly through legacy solve, throughput,
  and planner paths; valid category/assembler aliases still work.
- A two-output-per-craft recipe exposes different craft and item rates. A
  multi-result recipe retains every result instead of selecting one implicitly.
- An independent recipe calculation checks the motivating budget-only case:
  stone 30/s, copper plates 30/s, plastic 30/s, iron plates 60/s, AM2, no modules,
  steel/bricks internal, maximize purple-science net exports. Verify the stated
  8/7 science/s expectation against the pinned recipes; investigate a mismatch
  rather than changing the expected value to match the solver.
- Separate intermediate-export and external-steel variants preserve their scope.
- Public Python/tool and real stdio MCP checks cover errors and units; run
  `make test` and report any dependency/dump-related skips.

Keep aggregate blueprint supply semantics compatible. Do not implement spatial
routing, claim to explain the live factory discrepancy, or redesign unrelated
solver behavior. Handoff includes the shared validation entry point for task 05.
