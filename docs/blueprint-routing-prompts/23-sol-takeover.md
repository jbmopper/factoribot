# Sol takeover — finish the deterministic routing workflow

Use Sol with extra-high reasoning for the complete takeover; high is reasonable
for the bounded migration alternative at the end. These are task-complexity
recommendations, not benchmark claims. Select the model/effort in the session UI.

## Paste this into the new session

```text
Take over the Factoribot deterministic throughput work in
/Users/juliusmopper/Dev/factoribot. Continue the implementation through a small
working, validated end-to-end case. Do not merely write another plan or send me
another list of agent assignments. You own integration and routine corrections.

USER OBJECTIVE AND ACCEPTED DECISIONS
- Import a blueprint through the CLI, inspect a page with existing assembler
  recipes, mark input belts and their carried items, and assume those designated
  belts are fully supplied at the imported tier/lane capacity.
- Full supply means available up to capacity, not mandatory consumption. Preserve
  both-lane sharing and finite output storage/removal; never add implicit sinks.
- Infer furnace recipes from sufficient feed evidence, retaining ambiguity and
  user overrides. Calculate credible sustained throughput before optimizing layout.
- Keep page -> assignment export -> CLI analysis -> regenerated page for now.
  Browser blueprint upload, a local web service, and layout optimization are deferred.
- Target Factorio 2.0.77. The user explicitly selected it. Do not ask again.
- MCP exposes the same deterministic calculations to chat; no model should compute
  numerical rates or be used as a test oracle.

CHECKOUT AND STATE
- Last committed base is ab25b2a. Tasks 15-21, coordinator corrections, prompts
  and staged 2.0.77 evidence are already in this shared checkout as modified and
  untracked files. There is nothing to retrieve from other agents.
- Inspect actual HEAD, git status, tracked diffs AND untracked files before editing.
  Do not reset, stash, discard or indiscriminately commit the supplied work.
  A fresh worktree from HEAD alone omits required implementation and documentation.
  Prefer the existing checkout; use an isolated copy only if it includes all the
  relevant dirty/untracked files. No extra agents or paid model calls are requested.
- Read applicable repository instructions and the Factoribot skill, then:
  docs/blueprint-routing-prompts/NEXT-STEPS.md
  docs/blueprint-routing-deterministic-roadmap.md
  docs/blueprint-routing-handoffs/22-coordinator-integration.md
  docs/blueprint-routing-handoffs/21-independent-throughput-review.md
  docs/blueprint-routing-handoffs/20-sustained-throughput-model.md
  experiments/routing-measurements/profiles/base-2.0.77-normal-v1/README.md
  Read tasks 15-19 handoffs/code as needed. Historical findings are not automatically
  current defects; coordinator corrections supersede the original expected failures.

WHAT EXISTS
- Full-input page controls, recipe visibility and CLI draft/request/result replay.
- Page settings own budgets/exports/surplus/objective. Conflicting host-template
  values now fail explicitly instead of silently overriding the page.
- furnace_inference.py plus `factoribot routes infer`, inference provenance and
  replay. It retains uncertainty; the illustrative pilot got ZERO assignments,
  not a solved factory. Its feeds are arbitrary test declarations, not user facts.
- The conservative routing LP and certificates remain available. Its relaxed
  witness is not a prediction of how the game actually allocates items.
- sustained_throughput.py currently validates a design corpus and tolerances;
  IT DOES NOT CONTAIN A SIMULATOR OR PUBLIC OPERATING-RATE PREDICTOR.
- Task 16 actually evaluated existing analyzers. Retained failures include a
  virtual sink for blocked output, greedy competing-consumer allocation and
  ignored splitter priority. Do not restart that investigation from README claims.
- experiments/routing-measurements/harness.py has transport capture v1 and basic
  crafting/per-boundary capture v2. V2 checks recorded recipe starts/completions
  against loaded coefficients, but rich scenario/profile/timing binding and v2
  repeat validation remain unfinished. It is an offline validator, not a game runner.

FIXES ALREADY COMPLETED
- The unequal-consumer reference explicitly allocates 3/6 plates per second,
  yielding 1.5 gears and 6 pipes per second; conservation alone does not choose it.
- Design corpus v2 binds craft rates to loaded recipe coefficients and rejects
  internally balanced but recipe-inconsistent reference data.
- Recorder checks inventory continuity at shared ticks, scenario warmup/window
  settings, frozen tolerance, matching setup/research/control and across-run rates.
- Stable finite windows no longer establish sustained production. Outputs distinguish
  window-stable/window-variable and sustained_rate_established:false.
- Five expected-failure markers were removed after repairing their causes.
- Last full suite: 686 passed in 152.96 seconds, no expected failures or skips.
  This predates the later prototype export, not a guarantee for your next edits.

GAME AND EVIDENCE
- Executable:
  /Volumes/Spess/SteamLibrary/steamapps/common/Factorio/factorio.app/Contents/MacOS/factorio
- Verified `--version`: 2.0.77 build 84539, mac-arm64 Steam. It successfully ran
  headlessly with --dump-data. Older handoffs claiming no executable are obsolete.
- Fresh full base-only dump, gitignored:
  data/data-raw-dump-2.0.77-base.json
  SHA256 be65dc3615d5939e522b00543b2925a02cfa890dbc9c00882dfe1c4629670f60
- Pinned slice/extract/manifest/mod-list/export log/comparison:
  experiments/routing-measurements/profiles/base-2.0.77-normal-v1/
- Export used isolated config, mod and write directories; only base was enabled.
  The scratch workspace was removed after retaining artifacts. Existing saves,
  global mods and the original data/data-raw-dump.json were not changed.
- Overlapping SELECTED prototype fields match the previous slice; the modded
  ee-super-substation is absent from base-only data. This is not proof of identical
  engine behavior. The old runtime still enforces the 2.0.76 profile.
- Historical 2.0.76 references/records must retain their true provenance. Do not
  globally replace version strings in evidence or promote unobserved rules.

DO THE WORK IN THIS ORDER
1. Migrate runtime/profile/request validation and fixtures to the verified 2.0.77
   data coherently. Update generators, profile identity and capability/skill wording
   together. Rebuild sealed fixtures through their generators rather than hand-editing
   hashes. Preserve unsupported entities from the modded pilot; no entity becomes
   invisible because it is absent from the base-only export. Preserve legacy behavior
   where intentionally supported and explain any explicit version incompatibility.
2. Finish the capture-to-model binding needed for a SMALL reproducible validation
   case. Use versioned scenarios, named boundary/lane counters, loaded recipe-data
   identity, recorded craft events and initial/final inventories including hands.
   Do not derive observed internal consumption from the predictor being tested.
3. Use the actual Factorio executable for isolated controlled trials: begin with
   straight single/dual lanes, then a fixed-research inserter and a furnace chain.
   Use temporary config/write/mod directories and a NEW explicitly named disposable
   save/scenario. Never load/migrate/overwrite the player's saves or global config.
   Reuse game CLI facilities and existing code where appropriate. Capture warmup,
   ticks, raw counts, inventories, exact build/mod/research/power/control conditions
   and setup blueprint; retain small reproducible artifacts and clean up your own
   temporary processes/files. Do not install or downgrade Factorio.
4. Implement the smallest credible deterministic operating predictor/adapter for
   that measured subset, and integrate it with the CLI report. Automated actual-game
   trials are also a valid measured-throughput path if labelled clearly. Do not write
   a broad simulator merely to cover every pilot entity. Keep the existing certified
   upper-bound analysis separately available.
5. Exercise blueprint -> input draft -> optional furnace inference -> CLI report
   on one meaningful small factory, using explicit supplies and removal conditions.
   Compare predicted and measured rates under the same scenario, with tolerances
   fixed before comparing. Then report which pilot cases remain unsupported.
6. Run focused regression tests and make test after final changes, update the
   handoffs/current-status docs, and provide exact reproduction commands plus the
   resulting report/page paths. Review the final combined diff. Do not commit all
   unrelated files or claim a commit was made unless you actually made one.

OPERATING-MODEL REQUIREMENTS FROM THE REVIEW
- Three equal measurement windows do not prove a sustained rate. A delayed source
  can produce after an apparent zero plateau. Finite-window estimates must say so.
- For a recurrence-based sustained claim, include every future-affecting state:
  source/removal phases and credits, arbiters, timers, machine progress, hand contents,
  ordered lane positions and inventories. Compare canonical states on hash matches.
  A sampled return interval is not necessarily the minimum period or a fixed point.
- Shared external budgets specify ceilings, not physical scheduling. Reject competing
  feeds unless an explicit allocator/emission/removal schedule is in scenario identity,
  or use a demonstrably noncompeting subset. No entity-order or LP-witness allocator.
- Intent/resolve/commit is organization, not a validated Factorio tick order. Restrict
  merges, cycles, splitters or machine/inserter interactions until exact vacancy,
  blocking, phase and scheduling rules are justified for the advertised subset.
- Name output kinds honestly: capacity upper bound, predicted operating rate, actual
  measured interval rate. Preserve conservation including storage and initial stock.
  A tight constraint alone is not proof that increasing it improves production.

BROWSER CHECK: REAL KNOWN BLOCKER
The prior browser tool rejected file:///tmp/factoribot-integration-check.html and
explicitly prohibited alternate browsers, localhost serving or other workarounds
to achieve that same blocked navigation. Do not circumvent that restriction.
The actual browser click/export/import acceptance is STILL OPEN. Continue all
independent CLI/model/game work. If the restriction still applies, report it
precisely and provide a short manual check; do not let it silently become a pass
or block unrelated engine work. No in-page upload service is requested.

COMPLETION STANDARD
A task number, handoff, passing test count or new design note is not completion.
Deliver one reproducible useful small-factory result with preserved inputs,
correct furnace behavior within scope, and throughput evidence of the stated kind.
State remaining unsupported mechanics and any blocked check plainly. If external
information is genuinely required, finish independent work and ask one concrete
question. Do not ask me to choose the game version or redispatch agents again.
```

## Optional bounded Sol-high session

Use this instead if you want the first session to finish migration only. It does
not claim the predictor is delivered. Do not run this concurrently with the full
prompt above: they own the same shared runtime and fixtures.

```text
Read docs/blueprint-routing-prompts/23-sol-takeover.md in
/Users/juliusmopper/Dev/factoribot. Apply its current-state facts, existing-work
preservation rules, accepted 2.0.77 target, evidence provenance and browser
restriction. Execute only step 1: coherently migrate the runtime, evidence loading,
request/profile identity, generators, sealed fixtures, public CLI/MCP metadata and
skill wording to the fresh verified 2.0.77 export. Preserve unsupported pilot
entities and historical evidence. Verify correct-profile requests, stale-profile
rejection, fixture regeneration, focused checks and make test. Return a concrete
migration handoff with exact files and commands. Do not implement a simulator,
start game trials or mark the throughput milestone complete in this bounded task.
```
