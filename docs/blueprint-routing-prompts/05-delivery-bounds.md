# 05 — Couple local transport flows to installed production

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 00 and 01.
Develop against contract-defined synthetic graphs while 02–04 proceed. Production
integration requires their actual adapters and graph; report that dependency.

Own new `blueprint_plan.py`, a private sparse model/verification helper if needed,
and numerical routing tests. Consume `routing.py`; do not edit its topology or
duplicate shared recipes/effect arithmetic.

Use SciPy/HiGHS with sparse matrices. Create per-machine craft variables and only
eligible item-flow variables at local ports/inventories. Aggregate machines or
transport segments only under a documented equivalence that preserves location,
yield, eligibility, and every shared capacity. Bound model construction work,
variables, constraints, and solve time before large allocations.

Enforce local conservation, installed machine capacities, shared lane/splitter/
inserter resources, explicitly located imports/exports/surplus, and global budgets.
Permit manual per-entity furnace assignments with recipe compatibility validation.
Unknown inserter rates use the explicit optimistic relaxation in the contract.
Unknown topology follows the contract's conditional/unsupported policy. Never add
an implicit supply/sink or use an estimate as a certified capacity upper bound.

Derive machine-only, budget-constrained, and route-constrained bounds from the same
per-entity model by relaxing named constraints. Do not use legacy aggregate output
as an equivalent baseline when recipes, modules, yields, or boundaries differ.
Verify conservation, capacity, output constraints, objective, and finite values
independently of optimizer success. Remove gratuitous flow cycles with a secondary
objective without changing the primary optimum; report solver limits honestly.

Acceptance: hand-solved tests cover disconnected producers, competing items on
one lane, two ports sharing one budget, blocked exports/byproducts, direct input
pass-through, mixed machine/module variants, an explicit furnace assignment, and
an unsupported possible bridge. Relaxing routing recovers the matching budget
bound; increasing a budget cannot reduce the otherwise identical optimum. Include
an infeasible case and a deliberately unverifiable/conditional case.

Produce evidence grounded in model constraints and graph paths. A multi-item
capacity explanation needs more than a single-item shortest path. Do not claim
an upgrade helps merely because a constraint is tight; solve its counterfactual.
Report model sizes, solve/verification timing, tolerance, assumptions, and which
quantities are certified upper bounds versus estimates or unknowns.
