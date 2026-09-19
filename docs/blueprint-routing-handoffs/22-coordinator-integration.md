# Coordinator integration — 2026-09-12

Work on `ab25b2a` plus all supplied task 15–21 changes; no agent code was fetched
or overwritten wholesale. This is a follow-up, not a replacement of task 21's
historical independent review.

## Implemented corrections

- R3: unequal consumers explicitly receive 3 and 6 plates/s, producing 1.5 gears/s
  and 6 pipes/s. Work conservation alone does not establish that allocation.
  Every recipe-bearing design fixture now declares craft rates and validates
  its production/consumption against the loaded recipe coefficients. A balanced
  but recipe-inconsistent ledger is rejected. Strict design-case schema is v2.
- R4: check cross-window inventory continuity, warmup, minimum window count,
  interval length, frozen scenario tolerance, matching research/control/setup
  and repeat environment. Compare rates across runs, not just inside each run.
- R1 reporting: finite observations are `window-stable` or `window-variable`,
  never established sustained rates. A stationary observed window is explicitly
  insufficient evidence for convergence; the recorder emits
  `sustained_rate_established: false`.
- R5 partial: additive process capture v2 records separate boundary/lane/item
  counters and timestamped recipe starts/completions. It checks recipe-aware
  conservation, interval membership and continuity, and reports actual export
  item identity. V1 stays transport-only. V2 repeat/scenario binding and physical
  timing validation remain unfinished; no measured mechanics record was promoted.

Removed the five strict expected-failure markers after repairing their causes.
The recipe regression now independently checks the corrected 9-plate ledger.
Added counterexamples for internally balanced but false recipe coefficients,
across-run rate disagreement, false flat-window convergence and process records.

## Revised operating-design boundary (R1/R2)

This supersedes task 20's proposed `steady_window` sustained claim. A future
predictor may report finite-window estimates without a sustained assertion. A
sustained cycle result requires recurrence of complete autonomous state, including
source/removal phases, credits, arbiter state, machine/inserter progress and
future-affecting timers. Hash matches must be confirmed by canonical-state equality.
A sampled recurrence proves a return interval, not necessarily the minimum period
or a fixed point; cumulative counters may be omitted only if transitions cannot
read them. A flat sequence of windows is never the proof.

Initially reject competing shared external sources unless an explicit allocator
and emission/removal schedules are included in scenario identity. Merely knowing
ceilings cannot determine allocation. Restrict a first operating implementation
to noninteracting straight routes until vacancy resolution, merge/cycle updates,
source credit handling and physical scheduling have evidence-backed rules.
The declared 3/6 reference allocation is a mathematical test, not such evidence.
No simulator is implemented or released by this correction. Keep all unsupported
mechanics explicit and the current conservative upper-bound solver intact.

## End-to-end and environment checks

The checked-in two-lane input draft seals through `routes request`, then analyzes
through `routes analyze` and generates a result page. Source draft declares one
30/s budget shared by two 15/s lane feeds; no unresolved reasons were introduced.
Result is still the conservative analysis, not an operating-rate prediction.
Fresh full-suite integration tests cover CLI/MCP replay and furnace inference.

Actual browser navigation to the generated file page was rejected by browser
security policy, which expressly forbids alternate routes as a workaround. No
browser click/download/import pass is claimed. The generated check files were
removed after the CLI check.

Located and executed `--version` on the Factorio binary on `/Volumes/Spess`:
2.0.77 build 84539, while the profile is 2.0.76. Requested the user's target-version
choice. No save, mod setting or game observation was changed.

## Remaining work

- Browser interaction acceptance in a permitted environment.
- Target-version decision and compatible controlled captures.
- V2 scenario/recipe/counter binding plus timing observations; R5 is not closed.
- Independent review of narrowed operating semantics, implementation of the
  supported predictor, and comparison with game measurements.
- Real pilot declarations and a useful pilot run. Do not claim this was delivered.


## Final verification

`make test`: **686 passed in 152.96 seconds**, no expected failures or skips.
Focused recorder/design/review suite: 30 passed before the final schema-version
bump; the full run includes that bump. `git diff --check`: clean. CLI request and
analyze both succeeded using the full-belt draft. Only generated integration-check
files were removed from `/tmp`; supplied agent work and user files were preserved.
