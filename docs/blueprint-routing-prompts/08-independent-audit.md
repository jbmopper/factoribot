# 08 — Independently challenge the first routing release

Review under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 07. Prefer an
agent/session that did not implement the graph or LP. Read the contract, design,
fixture evidence, and integration instructions before reading implementation
explanations, so the test oracle is not inherited from the code.

Own adversarial tests in a separate routing-audit test file and
`docs/blueprint-routing-release-review.md`. Review production files read-only.
Return defects to their owner; do not quietly rewrite the solver during a review.
Record the exact revision/patch manifest reviewed and rerun affected checks after
fixes before updating the release decision.

Construct independent cases that try to break these invariants:

- A disconnected producer or blocked export cannot contribute flow; an unsupported
  possible bridge cannot be erased to manufacture a proof of disconnection.
- Competing items and multiple splitter arcs share the physical capacity; two
  import ports do not each receive the full global budget.
- Output/surplus locations and finite buffers cannot bypass delivery constraints.
- Different machine modules/yields and manual furnace assignments remain local.
- Relaxed scenarios share recipe/boundary assumptions; numerical residuals and
  limits are checked. Feasible relaxed flow is not advertised as achievable rate.
- Nested-book IDs, hostile labels, unknown records, size limits, and deterministic
  evidence survive the real public interface and viewer workflow.

Separate three gates in the report: mathematical conservation/bounds, validated
game mechanics, and usefulness on the pinned real blueprint. Inspect the recorded
observations behind every mechanic labeled exact; a synthetic test is not a game
observation. Run focused adversarial tests, real stdio MCP scenarios, browser
checks relevant to findings, and `make test`.

Acceptance: report each actionable finding with severity, exact file/line,
counterexample, expected invariant, observed result, and an acceptance test for
the fix. State pass/fail/unverified for each release gate and list the supported
mechanics that can actually be advertised. Do not invent a defect to fill a list
or claim approval based only on the implementer's test summary. The first release
is ready only when material defects are fixed and unresolved evidence is reflected
in its advertised scope.
