# Planning contract

`plan_production` returns structured JSON. For the exact current schema use MCP
tool discovery or `factoribot tools`. This guide describes the semantics that
matter when translating a conversation.

## Inputs, outputs and objectives

`inputs` maps exact item/fluid names to maximum imports per second. `null` means
explicitly unlimited. Zero means unavailable; omitted items cannot be imported.
Inputs are upper budgets, not instructions to consume all supply.

`outputs` maps every requested net export to an object:

- `rate`: exact export rate; cannot combine with `min`/`max`.
- `min` / `max`: bounds on net exports. An omitted lower bound is zero; an
  omitted upper bound is unlimited. `{}` alone does not guarantee positive output.
- `ratio`: positive share of a common output scale, used with `maximize_ratio`.
  May coexist with rate/bounds. Only items with `ratio` join the proportional group;
  other outputs can have independent exact/minimum requirements.

`objective.kind` is required:

| Kind | Meaning |
| --- | --- |
| `maximize_ratio` | Maximize the common scale of declared output ratios. |
| `maximize_outputs` | Maximize the weighted sum of exports; requires `weights` keyed by the outputs to value. Unweighted outputs retain their bounds. |
| `minimize_inputs` | Minimize weighted imports while meeting demands; requires a positive cost for every input. Choose costs explicitly, especially when mixing fluid and item units. |
| `minimize_machines` | Minimize fractional crafting-machine equivalents. |
| `minimize_power` | Minimize modeled active crafting-machine power. |
| `feasible` | Find a feasible plan, preferring fewer fractional machines. |

Optimization does not define the user's priorities. Minimum-cost plans need
positive output demands; otherwise zero production may be the correct solution.

## Recipe scope and machine constraints

Default scope expands canonical/pinned recipes from requested outputs, stopping
at declared inputs. `recipes` maps items to a producer choice, and `use_recipes`
adds candidates such as cracking. The optimizer may use any nonnegative rate,
including zero, for each active recipe. This is optimal within that selected scope.

For an exhaustive, user-appropriate recipe set, pass `available_recipes` instead
of `recipes`/`use_recipes`. There is then no automatic expansion: include the
needed intermediates. Multiple producers can be mixed. This mode also supports
manufacturing an input item in addition to importing some of it. An empty list
allows only direct pass-through of supplied items.

`machines`, `modules` and `beacons` use category keys; `assembler` applies to
assembling categories. Machine defaults come from the data's most capable
available prototype; this can exceed the player's research. Specify an appropriate
machine or disclose the assumption. `machine_limits` maps recipe names to maximum
fractional machine equivalents; it is not a shared machine pool or integer model.

Only `byproducts` explicitly permits surplus sinks. Other intermediates balance
to zero after recipe consumption. Inputs/outputs cannot also be surplus sinks.
Items that are both inputs and outputs can pass through; the result warns about it.

`max_power_w` constrains modeled active crafting-machine power. Power excludes
fuel supply, idle drain, beacons and infrastructure. Power objectives/limits with
beacons return `unsupported_feature` until a sharing/power model exists.

## Example: matched science with extra circuit supply

```json
{
  "inputs": {"iron-plate": 90, "copper-plate": 30},
  "outputs": {
    "automation-science-pack": {"ratio": 1},
    "logistic-science-pack": {"ratio": 1},
    "electronic-circuit": {"min": 5}
  },
  "objective": {"kind": "maximize_ratio"},
  "machines": {"assembler": "assembling-machine-2"}
}
```

If the user instead asks for all six outputs at equal rates, include all six
with `ratio: 1`. See the repository's `daemon/examples/balanced_six_outputs.json`.

## Interpreting responses

Successful responses contain the input `request`, actual net `outputs_per_s`,
`inputs` used and unused, gross production, internal consumption, per-recipe
machine counts, allowed surplus, active limits, numerical verification and a
game-data fingerprint. Retain the request for follow-ups. The optimizer uses
floating-point HiGHS with checked balances/bounds; do not call it exact rational
arithmetic. It performs a secondary cleanup at the same primary optimum.

`infeasible`: no plan satisfies this scope and constraints. Unavailable source
items are diagnostic candidates, not permission to add them. Check recipe scope,
output minima, supply, machine/power limits and surplus restrictions.

`unbounded`: the objective has no finite maximum under the given limits. Establish
a meaningful capacity instead of inventing one.

`bad_request` / `unknown_name` / `ambiguous_recipe`: fix the interpretation or
resolve names using game data. Do not change the user's goal.

`unsupported_feature`: the requested mechanic needs implementation or an explicit
approximation. `numerical_error` / `solver_limit` do not establish an optimum.

Continuous steady-state flow does not prove that the factory can start, that
research unlocks its recipes, or that its physical routing can carry those flows.
