# 09 — Replace selected inserter relaxations with validated limits

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 08's first
release gate passes. Read the frozen graph/resource contract and current unknown
inserter behavior. Own `inserter_capacity.py`, timing fixtures/tests, and an
extension note. Coordinate the small transport/prototype/schema integration patch
with the owner; do not concurrently edit another extension's shared files.

Select the smallest useful subset from the pilot: its actual inserter prototypes,
supported quality, and a small explicit set of pickup/drop endpoint types. Freeze
that support matrix before coding. Model the relevant rotation/extension, hand
size, research, item/stack, endpoint, and control assumptions from versioned
primary sources and independently recorded game observations.

Keep a proven capacity upper bound separate from a measured rate or timing
estimate. Measurement below a theoretical maximum does not prove the maximum is
lower. If item-dependent service times matter, use a shared service constraint
rather than incorrectly assigning one item/s capacity to every carried item.
Retain the explicit unknown-rate relaxation for unsupported endpoint combinations.

Acceptance: fixtures include inventory-to-inventory, supported belt pickups/drops,
direct insertion, disabled/conditional control, changed research, and shared
different-item service where supported. Observation records include warmup,
measurement ticks, supplies, blocked/unblocked destinations, hand contents, and
inventory changes. Cross-check theoretical bounds against those observations
without relabeling estimates as guarantees.

Demonstrate a route analysis where a newly justified limit changes the bound and
one where missing research keeps it conditional. Reuse public contract types and
independent residual verification. Run focused tests, `make test`, and public
interface checks after coordinated integration. If game timing evidence is absent,
complete the model/fixtures but leave the corresponding certification gate open.
