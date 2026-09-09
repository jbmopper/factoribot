# 00 — Freeze the first-release contracts

Act as the architecture owner. Read `docs/blueprint-routing-prompts/WORKING-RULES.md`
and `docs/blueprint-routing-design.md`. No prior task is required. Work in parallel
with 01 without editing its legacy calculation files.

Own new `daemon/factoribot/blueprint_contract.py`, `findings.py`, contract tests,
`daemon/tests/fixtures/routing_contracts/`, and
`docs/blueprint-routing-contract.md`. These names are proposed ownership
boundaries; make one documented choice and give downstream tasks exact imports.
Create usable schemas/types and validated examples, not empty solver stubs.

Make and document these decisions:

- Entity identity is a nested blueprint-book path plus entity number; a flattened
  list offset is insufficient. Define port/lane/inventory IDs, coordinate and
  direction conventions, and canonical hashing that survives serialization.
- Define immutable spatial graph inputs, item eligibility, shared capacity groups,
  per-machine activities, and evidence references. Several graph arcs may share
  one physical resource; specify how this is represented without double capacity.
- Define strict requests with global item budgets, port/lane feeds, exact/minimum
  exports and objective, explicit export/surplus locations, manual furnace
  assignments, protected interfaces, and version/research/control assumptions.
  Preserve item versus fluid identity and explicitly constrain supported quality.
- Specify unknown versus explicitly unlimited capacities, conditional connections,
  unsupported topology, and statuses for partial, insufficient, feasible-relaxed,
  solver-limit, and invalid requests. State the soundness requirement for every
  advertised bound. A finite buffer is not an unlimited steady-state sink.
- Define result/finding schemas with stable IDs, separate severity/evidence,
  comparable bound scenarios, hashes, interpreted request, and scoped detail.
  Freeze enough fields for the viewer and LP to develop independently. Supply
  complete spatial/result samples with geometry, ports, lanes, evidence paths,
  hashes, and valid assignment round-trips, plus a generated large synthetic
  layout for viewer interaction checks. Label these as synthetic fixtures.
- Pin the first mechanics set and a reproducible pilot. Start from the checked-in
  `wip_science.txt` fixture unless evidence identifies the owner's intended newer
  blueprint. Label this a development pilot, not the confirmed original factory.
  Unknown actual feed assignments remain unresolved; synthetic examples can use
  explicitly illustrative assignments.

Acceptance: validate complete request/result examples for a disconnected circuit
producer, two ports sharing one budget, an unsupported possible bridge, a blocked
export, and an ambiguous furnace with an explicit override. Reject malformed IDs,
duplicate entities, inconsistent hashes, invalid sinks, and unsupported options.
Write the contract before downstream implementation. Include a supported-mechanics
table, API signatures, file ownership, release gates, and a small dependency map.
Do not implement routing algorithms, the LP, or UI here.
