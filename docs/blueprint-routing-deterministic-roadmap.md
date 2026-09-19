# Deterministic throughput and layout roadmap

Accepted direction: 2026-09-11. Starting implementation: `ab25b2a`.
Milestones 1 and 2 and the restricted measured subset of milestone 3 were
implemented in the shared uncommitted task 15–23 tranche. Broader milestone-3
mechanics and milestone 4 remain roadmap work.
The original [design](blueprint-routing-design.md) and
[contracts](blueprint-routing-contract.md) remain references.

The [paste-ready dispatch](blueprint-routing-prompts/DETERMINISTIC-DISPATCH.md)
provides tasks 15–21, ownership, model recommendations and launch order.

## Product objective

Given a blueprint and user-designated full input belts, explain the factory's
sustained production, where items are restricted, and which changes improve it.
Then help produce efficient, readable, aesthetically consistent layouts.

Keep the CLI-based workflow for now. The page edits declarations and displays
results; the CLI imports blueprints, runs the deterministic engine, and regenerates
the page. MCP exposes the same engine to a conversational agent. No model is
needed to compute rates, infer supported recipes, or evaluate a candidate layout.
Blueprint upload in the browser and a local web service are deferred.

The first usable loop is:

1. Load a blueprint through the CLI; display its existing machine recipes.
2. Click a belt in the page, mark it Input, and choose the carried item (or one
   item per lane). Default to a fully supplied belt.
3. Designate desired exports and review output-removal and operating assumptions.
4. Export the scenario draft, run the CLI, and reopen the resulting page.
5. Inspect inferred furnace recipes, item flow and bottlenecks, including any
   ambiguity or unsupported behavior. Change declarations and repeat.

## Meaning of full input

A designated input has supply **available up to its belt capacity**. This is an
external supply declaration, not a requirement that the factory consume it all.
If outputs block or demand is lower, report unused supply and accumulation/back-
pressure as appropriate to the model. Do not force surplus disposal to balance
an otherwise blocked factory.

The application obtains tier and capacity from the pinned prototype data, never
from a hardcoded color table. Both lanes of a single-item full belt share the
belt's total capacity; selecting one lane receives only that lane's capacity.
For a two-item belt, choose an item per lane. Arbitrary mixed-item ratios within
a lane are outside the initial convenience control.

A repeated designation replaces the existing declaration for that entry; it must
not add another supply on top. Two consecutive segments of the same belt are not
automatically two independent sources. Initially permit full-input shortcuts at
supported incoming boundary ports only; an internal entry requires an explicit
external-interface decision and a warning about its existing upstream path.

## Milestone 1 — usable input declarations, retaining the CLI

Implement in the viewer/view model and request-draft integration. Keep existing
strict request and assignment contracts; generate their budgets and feed records
behind the controls instead of asking the player to invent IDs.

- Display blueprint assembler recipes in selection details and on the schematic
  at readable zoom. Missing recipes must be visibly missing, not blank machines.
- Offer Mark as input on an eligible selected belt, an item selector, whole-belt
  or per-lane choice, and a Full supply default with its items/s displayed.
- Permit changing/removing a designation, show assigned items on the map, and
  retain advanced shared-budget controls for genuinely shared external supplies.
- Export a complete draft carrying feeds and their budgets. Importing it must
  restore those declarations. Warn if a host template overrides page settings;
  do not silently analyze different budgets from the ones shown in the page.
- Preserve the current explicit output selection; do not silently create sinks
  at every dangling belt. Make the CLI export/reanalyze loop obvious in the UI.
- Any edit to feeds, budgets, exports, objective or furnace overrides marks the
  displayed result stale. Preserve identity checks and hostile-text safety.

Acceptance: full belt versus one lane; different items on opposite lanes; changing
belt tier; repeated edits without doubled supply; two entries sharing one budget;
rejection of outgoing/internal ports by the shortcut; blocked output; and draft →
CLI request → analysis → regenerated page replay with identical declarations.
Exercise real browser clicks as well as the public CLI. Existing assembler
recipes must survive without user input. Test a tiny hand-checkable case and the
pilot's selection/display behavior.

This milestone improves declaration ergonomics. Its output remains the existing
upper-bound model until the later throughput milestone is validated.

## Milestone 2 — material propagation and furnace inference

Bring forward [task 10](blueprint-routing-prompts/10-furnace-inference.md) for a
bounded supported subset. Inference is deterministic and its provenance must be
saved with the scenario. The blanket old sequencing of all tasks 09–14 after
all first-release gates no longer prevents implementing this scoped milestone.
It does not waive mechanics evidence needed to make an inference sound.

- Start from declared external materials and known assembler recipes; propagate
  possible material sets through supported routes to a bounded fixed point.
- Use the loaded recipe database and furnace crafting categories to derive
  compatible candidates. Handle iron ore → iron plate → steel and stone → brick.
- Infer an assignment only when sufficient evidence leaves exactly one compatible
  recipe. Report the inputs/path that justify it. Candidate reachability alone
  does not prove a particular rate, scheduling choice or real recipe selection.
- Mixed ores, uncertain routing, possible unsupported bridges, and incomplete
  boundary information retain ambiguity. Do not let the throughput optimizer
  choose a convenient furnace recipe and call that inference.
- Explicit user overrides take precedence, with conflicts reported. Recompute
  inference after feed changes; invalidate stale inferred assignments.
- Use a preparatory CLI pass if candidates alter graph identity: rebuild once,
  record inferred assignments against the final graph, then seal and solve.
  Never patch hashes to reuse a stale assignment document.

Acceptance: iron/steel chain, brick input quantities, ambiguous mixed feed, missing
feed, changed feed, disconnected recipe cycle, unsupported bridge, explicit
conflicting override, and inference/manual-assignment replay equivalence. Ask the
user only about remaining ambiguous furnace groups, not all 76 furnaces.

## Milestone 3 — credible sustained-throughput results

The existing delivery LP proves optimistic bounds. Its witness is an allocation
that satisfies the relaxed equations, not proof that splitter scheduling,
inserter timing or belt back-pressure produces that allocation in Factorio.
A full-supply assumption alone cannot turn that witness into a throughput forecast.

Before implementing another engine, perform a bounded reuse evaluation:

- [Blueprint Analyser](https://github.com/Tomansion/factorio_blueprint_analyser)
  and its [dashboard](https://github.com/Tomansion/factorio_blueprint_analyser_app)
  already target full-input blueprint flow analysis. Check actual code, license,
  version compatibility, lane/splitter semantics, known incorrect results and
  furnace support. Documentation claims are not validation.
- [factorio-analytics](https://github.com/CharacterOverflow/factorio-analytics)
  may supply engine-run trials and measurements. Check current compatibility
  before adopting it; keep experiments separate from existing saves.
- Evaluate on small known-answer layouts first: single lane, lane merge, unequal
  competing consumers, splitter priority, inserter-limited transfer, furnace
  chain, and a blocked output. Then attempt the pilot and record unsupported
  behavior. Compare output rates and conservation, not just successful execution.
- Record a reuse/adapt/reject decision with concrete failures and maintenance
  implications. Reuse compatible components where they save work; do not discard
  the existing strict checks merely to get a numerical answer.

Choose the smallest credible throughput approach supported by that evaluation:
validated analytic rules for a restricted subset, a deterministic event/tick
model where scheduling matters, or automated Factorio trials. Freeze its supported
entities, initial inventory state, research, control assumptions and environment.
For simulation/trials declare warmup, measurement windows, convergence criteria
and a maximum runtime. Oscillating or nonconverged layouts must say so.

Bring forward the relevant subset of [task 09](blueprint-routing-prompts/09-inserter-rates.md)
and controlled observations; do not wait for unrelated mechanics to be complete
before testing a useful restricted factory. Finite inserter timing, lane merging,
splitter/filter priorities and back-pressure need actual treatment for the scope
being advertised. Measurements do not become certified upper bounds by renaming
them, and unsupported behavior must remain explicit.

Expose separate result meanings:

| Result | Meaning |
| --- | --- |
| Capacity upper bound | Existing conservative mathematical ceiling under declared relaxations |
| Predicted operating rate | Supported deterministic operating model, with assumptions and validation coverage; sustained only if recurrence is separately proved |
| Measured rate | Actual counts over a recorded interval in a named Factorio environment |

Report per-item net outputs, actual modeled/observed input consumption, unused
supply, machine utilization and localized restrictions. Do not present a single
LP witness as uniquely determined per-belt flow when multiple allocations exist.
A saturated constraint is only a candidate bottleneck: perturb its capacity or
compare an actual alternative before claiming an improvement.

Acceptance: independently recorded Factorio comparisons on the supported tiny
cases and a useful pilot subfactory; agreed error tolerances before examining
results; bounded work and deterministic replay; conservation and blocked-output
counterexamples; no unsupported layout receiving an unqualified prediction.
Version any new result schema rather than weakening the existing bound contract.

## Milestone 4 — efficient and attractive layout alternatives

Start after a trustworthy evaluator exists for each candidate's mechanics.
Keep proposed edits local and reviewable at first: reduce unnecessary belt runs,
simplify crossings, regularize machine rows and preserve named interfaces.

Treat efficiency and appearance as explicit objectives: sustained output, footprint,
entity cost, belt length, crossings, alignment, repeated spacing and accessibility.
Preserve recipes, required production, external connections and protected areas.
Let the user choose tradeoffs instead of silently maximizing one aesthetic score.
Generate alternatives, rerun the same evaluator with the same supplies and removal
conditions, and show before/after rates, assumptions and layout images. Export a
new blueprint for an accepted candidate. Preserve the original blueprint.

Do not promise global optimality or equivalent game operation based only on graph
reachability. No layout-optimization implementation is authorized by this roadmap
alone beyond the currently requested planning; dispatch concrete edits separately.

## Current facts versus the revised plan

Task 23 migrated the runtime and generated fixtures to the verified base-only
Factorio 2.0.77 profile and completed one sealed ore → iron plate → steel plate
case. Full-input drafts and recipe visibility are implemented; furnace inference
preserves ambiguity and explicit overrides; the routing LP remains a separately
labelled capacity-bound solver.

The new operating adapter is intentionally narrower than this roadmap's eventual
scope. For a serial noncompeting electric-furnace chain it derives a conditional
rate from the exact loaded recipe data, validates independent v3 game captures,
and is exposed through the CLI and read-only MCP tool. Two real Factorio repeats
matched the `1/8 steel-plate/s` prediction over all six finite windows. The same
captures measured 15 items/s on one fast-belt lane, 30 items/s on two lanes, and
2.5 items/s for a fixed zero-bonus fast inserter. No result claims recurrence or
a sustained rate.

The 16 mechanics records remain historical 2.0.76 evidence and therefore do not
make current 2.0.77 arcs exact. The modded pilot's three `ee-super-substation`
entities remain visible unsupported gaps. Browser upload is still deferred and
the known local-file browser acceptance is still open. See
[task 23's handoff](blueprint-routing-handoffs/23-sol-takeover.md) for artifacts,
commands, unsupported mechanics, and the precise blocker.
