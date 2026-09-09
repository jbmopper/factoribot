# 10 — Infer furnace recipes only from sufficient feed evidence

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 08. The
first release already supports explicit manual furnace assignments. Own
`furnace_inference.py`, inference fixtures/tests, and an extension note. Coordinate
request/graph integration rather than changing shared schemas independently.

Infer compatible recipes from supported possible ingredient feeds, machine
categories, and the existing prototype recipe database. Define a deterministic
fixed-point procedure for chained furnaces and cycles; bound its work and retain
all candidates when evidence is incomplete. Unknown upstream items, conditional
routes, and unsupported links cannot be treated as proof an ingredient is absent.

Keep evidence-derived uniqueness distinct from an optimizer choosing whichever
recipe maximizes output. The latter would be a different planning feature.
Explicit compatible user assignments take precedence, retain their provenance,
and must remain replayable. If an explicit assignment conflicts with confirmed
feeds, report the conflict rather than silently replacing the assignment.

Acceptance: cover iron-to-steel and stone-to-brick feeds, a chain of furnace
outputs, mixed compatible feeds, absent boundary declarations, conditional feed,
an unsupported possible bridge, and a recipe cycle. Each inferred recipe has an
evidence path and supported assumption set. Ambiguity returns candidates and a
precise override location; it does not remove the furnace from accounting or
create an external supply.

Verify that inference plus its recorded assignment replays as the equivalent
manual request under unchanged assumptions. A changed feed invalidates stale
inference. Add public interface examples through coordinated integration, run
focused tests and `make test`, and document which mechanics still require manual
assignments. Do not introduce fuel, quality, or fluid semantics beyond the declared
support matrix.
