# Task 16 handoff — existing deterministic engine evaluation

## Run identity and scope

- Task: `16-existing-engine-evaluation`
- Date: 2026-09-11
- Starting and final repository HEAD: `ab25b2a9e4c11e31be551da750510fdeb5f7d6c6`
- Model: GPT-5 (Codex)
- Factoribot contract observed through `get_capabilities`: schema `1.1.1`,
  mechanics profile `base-2.0.76-normal-v1`, routing integration
  `factoribot-routing-integration-1`
- Initial relevant dirty state: the revised design/next-run/prompt indexes were
  modified and the deterministic roadmap plus prompts 15–21 were untracked.
  Those files were treated as coordinator-owned inputs. Task 15/17 production,
  test, and handoff files appeared concurrently later; none were edited here.
- Owned changes only: `experiments/routing-reuse/` and this handoff. No production
  code, shared dependency, public contract, or user blueprint was changed or sent
  to a hosted service.

## Decision

Do not adopt any evaluated project as Factoribot's throughput engine. Keep
Factoribot's lossless parser, explicit boundary contract, identity checks,
lane-aware graph, conservative findings, and optimistic LP ceiling. For task 20,
add a restricted deterministic event/tick model for the pinned supported subset,
and validate predictions independently with the local engine-run harness owned by
task 17. Adapt dashboard interaction ideas into Factoribot's existing standalone
viewer. Adapt game-trial orchestration ideas, but do not directly incorporate the
GPLv3 package until license compatibility is deliberately accepted.

The static analyzer returns numerical answers, but the answers are not sustained
Factorio throughput. Its recursive pull model assumes implicit infinite sources
and sinks, collapses two-lane belts, ignores splitter priority, greedily allocates
competing consumers in traversal order, omits furnaces, and uses an unvalidated
inserter-rate shortcut. These defects are structural rather than calibration
errors.

## Versions, licenses, and maintenance signals

| Project | Evaluated revision/package | License evidence | Maintenance/interface observations |
| --- | --- | --- | --- |
| [factorio_blueprint_analyser](https://github.com/Tomansion/factorio_blueprint_analyser/commit/21131f3c4cef564b58386f5fd5438698a7daf13b) | commit `21131f3c4cef564b58386f5fd5438698a7daf13b` (2025-08-12); `setup.py` and PyPI `1.3.6`; no `1.3.6` git tag | Effective repository `LICENCE` is MIT and `setup.py` says MIT. The README badge incorrectly says Apache-2.0. | Python package plus `blueprint_analyser` CLI. Exact dependencies: termcolor 2.0.1, PyYAML 6.0.2, pyvis 0.3.0. Open issues include [known incoherent results](https://github.com/Tomansion/factorio_blueprint_analyser/issues/1) and [blueprint-version compatibility](https://github.com/Tomansion/factorio_blueprint_analyser/issues/3). |
| [factorio_blueprint_analyser_app](https://github.com/Tomansion/factorio_blueprint_analyser_app/commit/70b43cf87a04a4619b4e459c5e5041c30fda72e0) | commit `70b43cf87a04a4619b4e459c5e5041c30fda72e0` (2025-08-12); frontend `1.3.1` (lockfile root still says `1.3.0`) | No `LICENSE`/`COPYING` file and GitHub reports no detected license. The backend OpenAPI metadata saying MIT is not a repository license grant. Do not copy its code without clarification. | Vue 3.2.41, vis-network 9.1.2, Pinia 2.0.23, Axios 1.1.3; Node engine `>=18 <19`. FastAPI backend delegates to analyzer 1.3.6. |
| [factorio-analytics](https://github.com/CharacterOverflow/factorio-analytics/commit/6270a5a3299a57d95c8c0f4f5411138f7a4ee812) | commit `6270a5a3299a57d95c8c0f4f5411138f7a4ee812` (2024-05-28); package/NPM `3.3.4`; README title still says `3.2.0` | GNU GPLv3 in `package.json`, repository `LICENSE`, and GitHub metadata. | Node library, not an analyzer CLI. README requires Linux, Node 16+, curl/tar, a local Factorio executable, and an infinity-chest-equipped blueprint or save. Version defaults to latest stable unless pinned. |

The analyzer's bundled data is a Factorio 1.1-era snapshot: its sample blueprint
encodes 1.1.59.0, it recognizes the legacy 0/2/4/6 directions and `stack-inserter`,
and it lacks Factorio 2.0's `bulk-inserter`. Its README claim that it supports the
“latest” blueprint version is therefore not a version contract. The pilot encodes
2.0.16.0 and demonstrated the mismatch directly.

## Local execution and exact results

All external repositories, virtual environments, npm caches, build outputs, and
the local server lived under
`/private/tmp/factoribot-routing-reuse-20260911`. Only the small reproducible
corpus, probes, and result JSON files were retained in the repository.

Commands used (run from the repository root unless a `-C`/subdirectory is shown):

```sh
git rev-parse HEAD
.venv/bin/factoribot tool get_capabilities --args -

(cd /private/tmp/factoribot-routing-reuse-20260911/factorio_blueprint_analyser && \
  ../analyser-venv/bin/python -m pytest -q)

/private/tmp/factoribot-routing-reuse-20260911/analyser-venv/bin/python \
  experiments/routing-reuse/run_static_analyser.py \
  --upstream /private/tmp/factoribot-routing-reuse-20260911/factorio_blueprint_analyser \
  --pilot daemon/tests/fixtures/wip_science.txt \
  > experiments/routing-reuse/results.json

python3 experiments/routing-reuse/run_factoribot_inspect.py \
  --factoribot .venv/bin/factoribot \
  > experiments/routing-reuse/factoribot-inspect-results.json

/private/tmp/factoribot-routing-reuse-20260911/analyser-venv/bin/python \
  experiments/routing-reuse/probe_custom_prototypes.py \
  --upstream /private/tmp/factoribot-routing-reuse-20260911/factorio_blueprint_analyser \
  > experiments/routing-reuse/custom-prototype-result.json

node experiments/routing-reuse/probe_factorio_analytics.js \
  /private/tmp/factoribot-routing-reuse-20260911/factorio-analytics/dist \
  experiments/routing-reuse/factorio-analytics-sample.jsonl \
  > experiments/routing-reuse/factorio-analytics-parser-result.json

(cd /private/tmp/factoribot-routing-reuse-20260911/factorio_blueprint_analyser_app/frontend && \
  npm_config_cache=/private/tmp/factoribot-routing-reuse-20260911/npm-cache npm ci && \
  npm run build)

(cd /private/tmp/factoribot-routing-reuse-20260911/factorio-analytics && \
  npm_config_cache=/private/tmp/factoribot-routing-reuse-20260911/npm-cache npm ci && \
  npm run build)

(cd /private/tmp/factoribot-routing-reuse-20260911/factorio_blueprint_analyser_app/backend && \
  FASTAPI_ENV=production \
  /private/tmp/factoribot-routing-reuse-20260911/analyser-venv/bin/python websrv.py)

/private/tmp/factoribot-routing-reuse-20260911/analyser-venv/bin/python \
  -m pytest -q experiments/routing-reuse/test_harness.py
```

Results:

- Upstream analyzer tests: `1 passed` in 0.29 s, plus one Python `SyntaxWarning`.
  The sole upstream test is a smoke pass over example blueprints; it asserts no
  rates or mechanics.
- Owned harness: `7 passed` in 0.01 s. The checks cover corpus integrity,
  translation, summarization, recorded counterexamples, lane preservation, and
  explicit uncertainty.
- Analyzer installed and ran in an isolated Python 3.14.7 environment.
- App frontend `npm ci`: 960 packages and 65 reported audit findings (6 low,
  25 moderate, 28 high, 6 critical); Node 26.8.2/npm 11.19.1 also produced engine
  warnings because the project pins Node 18.x. `npm run build` succeeded with four
  build warnings, including a 780 KiB vendor chunk and 818 KiB entrypoint.
- factorio-analytics `npm ci`: 751 packages and 27 reported audit findings (5 low,
  5 moderate, 14 high, 3 critical); `npm run build` succeeded.
- No Factorio executable was found through `command -v`, the normal macOS/Steam
  paths, Spotlight, the task environment variables, or the development tree.
  Consequently no engine-backed trial was run and no game measurement is claimed.
- `make test` was intentionally not run: this task changed no implementation.

Retained-result SHA-256 values:

```text
a42d55193f02aef675929918fa22c272463ffb161a149e51972dfb995cd93bbf  results.json
5783bd32a746e27052962a476dbc98bbb053aaaaed2771a94febe9000727b3a5  factoribot-inspect-results.json
0fd3303f5da41b95a2fe85bfea79fda54f799d11a8b917268a2b3167cabb6fc5  custom-prototype-result.json
c68f359be9f3d50006350afc6c53dcc96ba67f3f5725a015b3bee1be829aac8f  factorio-analytics-parser-result.json
```

### Known-answer corpus

The expectations below are mathematical or documented reference expectations,
not recorded game observations. Belt/lane and ordinary splitter expectations are
based on the current [Factorio belt transport documentation](https://wiki.factorio.com/Belt_transport_system)
and [splitter documentation](https://wiki.factorio.com/Splitter); exact rates and
priority-side placement still require pinned 2.0.76 game fixtures.

| Case | Independently stated expectation | Analyzer 1.3.6 observation | Assessment |
| --- | --- | --- | --- |
| `straight_one_lane` | A yellow belt has two distinct lanes; one explicitly occupied lane is bounded by 7.5 items/s and the other remains distinct. | Three belts were compacted to one input and one output node; no lane records and empty item totals. | Reject for lane analysis. |
| `lane_merge` | Two lanes remain distinct and together cannot exceed the 15 items/s whole-belt reference capacity. | Two roots merged to one output, but no lanes or item rates were represented. | Returned successfully but did not test the mechanic. |
| `inserter_limited_transfer` | For internal consistency only, the analyzer's own 0.84 item/s shortcut implies at most 0.42 gear/s for a 2-plate recipe. This is not a game-rate oracle. | Input 0.84 plate/s; output `0.42000000000000004` gear/s; source inserter marked bottleneck. | Arithmetic is internally consistent but falsely precise as Factorio timing. |
| `blocked_output` | With no removal and finite internal storage, steady-state net export is 0 after the output blocks. | Auto-created a virtual sink and reported 2.4 plate/s consumed and 1.2 gear/s exported forever. | Concrete false positive; reject flow model. |
| `unequal_competing_consumers` | The documented unprioritized splitter alternates/evenly balances available output; the reference allocation is 0.42 plate/s per branch, hence 0.21 gear/s and 0.42 pipe/s before game validation. | Greedy traversal gave `0.41999999999999993` gear/s to the first branch and `1.1102230246251565e-16` pipe/s to the second. | Branch order changes the answer; floating residue is exposed as production. |
| `splitter_priority_right` | Priority must alter eligible output allocation when both branches compete. Exact geometric side mapping awaits the game fixture. | Bit-for-bit identical item output to the unprioritized case. | `output_priority` is parsed but ignored. |
| `furnace_chain` | Ore → plate → steel must either use explicit/proven furnace recipes or remain an explicit unsupported/ambiguous chain. | Both furnaces were skipped; virtual boundaries bridged the gaps; item totals were empty. | Furnace support is absent, not merely incomplete inference. |

### Pilot after the small cases

The unmodified `daemon/tests/fixtures/wip_science.txt` was passed only after all
seven small layouts. The analyzer returned rather than crashing, but emitted
2,033 warnings:

| Warning | Count |
| --- | ---: |
| unknown direction 8, fast transport belt | 850 |
| missing `bulk-inserter` prototype | 608 |
| unknown direction 12, fast underground belt | 285 |
| unknown direction 12, fast transport belt | 196 |
| unsupported electric furnace | 76 |
| unknown direction 8, fast underground belt | 15 |
| missing `ee-super-substation` | 3 |

It then emitted identical aggregate input and output dictionaries—advanced
circuits 0.75/s, electric furnaces 4.800000000000001/s, and production science
12.857142857142868/s—with 569 inferred roots and 552 inferred leaves. This is a
failure, not partial validation: many disconnected assemblers became both an
infinite source and an infinite sink.

### Factoribot comparison

`inspect_blueprint_layout` accepted the translated 2.0 synthetic layouts and
preserved lane topology (six lane records for three straight belts; eight for the
four-entity merge). It did not invent rates. The capability report contains 16
mechanics records, zero game-observed records, six documented-only records, and
ten pending records, so its mechanics evidence gate remains unmet. Inserter
capacity and rotation remain unresolved; splitter allocation is explicitly
relaxed/conditional. The blocked case reports `blocked_output`,
`inserter_capacity_unknown`, and unresolved endpoint/rotation evidence instead of
the analyzer's 1.2 gear/s claim. This conservative behavior is the correct base
to extend.

The furnace case stays explicit: unresolved recipes and unsupported possible
bridges are reported. No current Factoribot result from these cases is a predicted
or measured sustained rate; any future LP value remains an optimistic upper bound
under recorded relaxations.

## Component findings and reuse matrix

| Component | Evidence | Decision |
| --- | --- | --- |
| Blueprint parser | Analyzer accepts JSON or encoded strings, silently selects the first blueprint-book entry, performs no useful version validation, and mutates infinity chests into ordinary iron chests. A custom `dataFilePath` probe loaded a custom belt speed, but only because the custom prototype declared a hard-coded supported entity type; it does not add new semantics or identity provenance. The 2.0 pilot broke direction and prototype interpretation. | **Reject.** Keep Factoribot's lossless, size-bounded parser, explicit book selection, version adapter, and hash identity. |
| UI | Local browser interaction confirmed paste/upload, parameter controls, a spatial icon graph, item/recipe overlays, hover labels, bottleneck/input/output legends, select-for-removal plus restart, and copy/download. It has no lane display, boundary assignment, provenance/staleness, or upper-bound/predicted/measured distinction. A concrete state bug showed the visible inserter-bonus slider at 0 while the submitted request and result page said 1. It also fetches remote wiki/Icon8 images, inherits engine errors, and has no repository license grant. | **Adapt interaction ideas only; reject code import.** Implement the useful map/selection/overlay ideas in Factoribot's existing standalone viewer and retain safe text rendering/identity checks. |
| Item/recipe inference | Analyzer back-propagates assembler purpose from a single recipe result; fluids are ignored, furnace activities are never constructed, and ambiguous routes are resolved by traversal rather than provenance. | **Reject.** Use task 19's feed-driven, provenance-bearing fixed point with explicit ambiguity and overrides. |
| Static flow engine | Whole belts are a single capacity (`speed * 60 * 4 * 2`), splitters have one belt of capacity rather than lane/shared scheduling, filters/priorities are TODO/ignored, inserters are `rotation_speed * 60` with a crude bonus, roots become infinite supplies, leaves become 10,000/s sinks, and recursive leaf pulling is order-dependent. Blocked output and competing-consumer cases fail conservation/operation semantics. | **Reject.** Preserve Factoribot's LP only as an optimistic ceiling, then add a restricted tick/event execution model. |
| Game-trial harness | factorio-analytics has useful separations (`Source`, `ModList`, `Trial`), scenario compilation, headless benchmark launch, JSONL production-stat sampling, parsing, and optional SQLite persistence. The parser probe produced six deterministic rows (including tick-zero padding), totals of six plates consumed and three gears produced over two seconds, and averages of 3/s and 1.5/s. An extra blank line caused a JSON parse failure. The runner requires infinity entities, has no declared warmup/convergence/net-boundary/utilization contract, defaults to a mutable latest game version, and has not been shown compatible with 2.0.76. Direct code reuse also carries GPLv3 obligations. | **Adapt architecture, not yet package code.** Prefer task 17's minimal local harness; consider a process boundary or accepted GPL integration only after legal and 2.0.76 compatibility review. |

## Smallest credible architecture for task 20

Use a three-layer result rather than a replacement monolith:

1. **Structural graph and optimistic ceiling:** retain Factoribot's parser,
   lane graph, explicit feeds/removals, shared capacities, identity hashes, and
   LP upper bound. A relaxed edge can bound a result but cannot establish an
   operating schedule.
2. **Restricted deterministic event/tick prediction:** initially support only the
   pinned 2.0.76 entity/recipe subset whose semantics have versioned evidence.
   Represent two belt lanes, splitter priority/filter decisions, finite inserter
   pickup/drop timing, machine inventories, explicit removals, backpressure, and
   initial state. Unsupported control behavior returns `partial`, never a guessed
   schedule. A bounded warmup, measurement window, convergence rule, and maximum
   tick count are part of the request/result contract.
3. **Independent engine measurement:** task 17 should run disposable local
   2.0.76 trials with frozen game build, mods, research, power/control state,
   initial inventories, feeds, removals, warmup, sample window, and repeated-run
   metadata. Store raw counter artifacts and their hashes. Measurements validate
   or falsify predictions; they do not overwrite them.

This is smaller and more credible than porting the analyzer, while addressing the
scheduling/backpressure gap that the continuous LP intentionally leaves open.

## Interfaces for tasks 20 and 17

No shared schema was changed here. The following is a proposed coordinated
contract shape, to be versioned by the owning integration task rather than copied
silently:

- `ThroughputScenarioV1`: graph/prototype/mechanics hashes; pinned game/mod
  identity; explicit feed ports and globally shared item budgets; explicit
  removal/export ports; recipe/furnace assignments with provenance; research,
  power and control assumptions; initial inventories; warmup, measurement,
  convergence and maximum-tick settings.
- `ThroughputPredictionV1`: request and graph hashes; model version; status
  `supported | partial | nonconverged`; assumptions/unsupported mechanics;
  per-item imports, unused supply, internal consumption and net exports; local
  entity utilization/restrictions; convergence trace summary. This is separate
  from existing optimistic bounds.
- `ThroughputMeasurementV1`: trial ID; game build/version and mod hashes;
  scenario/request hashes; warmup and measurement intervals; repeat/seed data;
  raw artifact hashes; per-item net boundary rates, inventory deltas and error
  statistics. It must identify what was directly observed.

Reusable corpus cases are in `experiments/routing-reuse/corpus.py`. Task 20/17
should add pinned-game observations for: one-lane belt, two-lane merge, finite
inserter transfer, blocked output approaching zero sustained export, competing
consumers under entity-order permutation, splitter priority toggle, and explicit
ore→plate→steel furnace assignments. Also require deterministic replay,
conservation, bounded non-convergence, unsupported-entity partial status, and a
pilot subfactory trial. Priority side mapping and exact inserter/belt rates remain
undecidable here without that game access.

## Owned artifacts

- `experiments/routing-reuse/corpus.py` — seven synthetic layouts and independent
  expectation text.
- `experiments/routing-reuse/run_static_analyser.py` — isolated upstream adapter
  and compact result recorder.
- `experiments/routing-reuse/run_factoribot_inspect.py` — current Factoribot
  comparison through the public CLI tool.
- `experiments/routing-reuse/probe_custom_prototypes.py` — custom-data-path probe.
- `experiments/routing-reuse/probe_factorio_analytics.js` and
  `factorio-analytics-sample.jsonl` — game-independent parser probe.
- `experiments/routing-reuse/test_harness.py` — owned regression checks.
- `results.json`, `factoribot-inspect-results.json`,
  `custom-prototype-result.json`, and `factorio-analytics-parser-result.json` —
  retained exact observations.

Next tasks: task 19 can complete the inference prerequisite independently; task
17 can consume the trial/corpus interface now. Task 20 should wait for the task 19
inference contract and at least the first pinned 2.0.76 game observations from
task 17 before claiming predicted sustained throughput.
