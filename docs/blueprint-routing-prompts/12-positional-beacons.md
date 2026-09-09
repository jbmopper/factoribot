# 12 — Apply validated beacon effects from actual positions

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 08. Own
`beacon_analysis.py`, beacon geometry/effect fixtures/tests, and an extension
note. Reuse existing recipe/module effect calculations. Coordinate any needed
shared effect-helper change and LP integration; do not duplicate that arithmetic.

Freeze supported game/mod versions, beacon prototypes, module inventories, and
quality levels. Resolve actual machine coverage and the supported effect/profile
rules from pinned primary documentation and game fixtures. Different per-entity
module layouts must remain distinct even when machines share a recipe.

Calculate each machine's effective configuration from positioned beacons. Unknown
quality, geometry, or unsupported profile semantics must be reported instead of
silently applying normal-quality or fixed-count assumptions. Preserve effect
eligibility and existing module-slot/recipe checks. All three bound scenarios
must use the same resulting machine coefficients.

Acceptance: fixtures cover one beacon, overlapping beacons, a machine just outside
coverage, heterogeneous modules, supported profile behavior, ineligible effects,
and unsupported quality. Confirm coverage and effective speeds/yields with pinned
reference observations. A translated or supported-rotated layout preserves its
effect mapping. Test a case where identical recipe machines must not be grouped
because their effects differ.

If beacon power is included, count each physical beacon once and expose the load
separately; do not count it once per affected machine. Integrate with 11 only if
its interface is already available, otherwise return a standalone supported load
field. Run focused tests, `make test`, and coordinated public checks. Do not
optimize beacon placement or infer the live save's research/access state.
