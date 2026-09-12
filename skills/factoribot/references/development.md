# Extending Factoribot's deterministic model

Use this workflow when the user asks to implement a capability or fix a solver
failure. Existing session authorization carries forward; do not repeatedly ask
for it. Keep development separate from the runtime MCP tool surface.

1. Read repository instructions and inspect local changes. Preserve unrelated
   work. Reproduce the request as a small structured spec, separating unsupported
   mechanics from invalid constraints and mathematically infeasible plans.
2. State the missing mathematical behavior and decide which layer owns it:
   - `daemon/factoribot/plan_spec.py`: validated optimization contract.
   - `planner.py`: continuous optimization, resource budgets and verification.
   - `solver.py`: exact fixed-recipe balances and shared machine/module effects.
   - `model.py` / `gamedata.py`: mechanics missing from normalized prototypes.
   - `bpanalyze.py`: blueprint-specific analysis (speed-only, no geometry).
   - `blueprint_contract.py` / `findings.py`: the frozen routing contract types,
     hashing and validation. Shared: changes need a versioned proposal.
   - `spatial.py` / `transport.py` / `routing.py`: blueprint import, entity
     geometry and the supported transport graph.
   - `blueprint_plan.py` / `routing_lp.py`: the delivery LP, certificates and
     result assembly.
   - `blueprint_view.py`: the standalone viewer page.
   - `routing_public.py`: the public routing surface (summaries, detail scope,
     pagination, request sealing, capability metadata). Add no mechanics here.
   - `tools.py` / `mcp_server.py`: schemas, structured errors and transport.
   A wording problem belongs in the skill/tool descriptions, not in the math.
3. Add a hand-checkable failing case with an independently derived expectation.
   Include the physical invariant affected: conservation, net exports, capacity,
   recipe eligibility, or optimal objective. Add a counterexample/infeasible case
   where it would catch a plausible wrong implementation. Never use the solver's
   own output as the sole expected answer.
4. Implement the smallest coherent extension. Preserve deterministic calculation
   and strict contracts. Unsupported options must fail explicitly, never disappear.
   Choose a suitable algorithm: continuous LP for rates; mixed-integer modeling
   for discrete choices; spatial or dynamic models when flow equations cannot
   represent the request. Avoid encoding one user's example as a special case.
5. Run focused tests, then the existing suite (`make test`). Exercise the changed
   behavior through the public tool/MCP interface, including structured errors.
   Use real-dump/external-planner cross-checks where they test the new mechanic.
   Do not invoke a second paid LLM simply to test deterministic math.
6. Update capability metadata, schemas and the relevant skill reference together.
   Explain what now works, how it was checked and remaining limitations. Reload
   the MCP process so it picks up source/data changes before claiming the running
   server has the new behavior. Clean up temporary files and processes.

Example evaluation requests after an extension:

- Plan equal net exports of both early sciences, gears, inserters, belts and
  circuits from 90 iron plates/s and 30 copper plates/s; then double circuits
  while preserving other constraints.
- Maximize matched science with a minimum circuit export, limited machines and
  an explicitly supplied set of ingredients.
- Explain an impossible plan without adding unrequested supplies or disposal.
- Compare recipe alternatives with a hand-checked resource tradeoff.
- Discuss a routing/quality/startup question honestly when that mechanic remains
  unsupported; use source-editing tools only when development is requested.
