# Blueprint routing — next-run checklist

Updated 2026-09-13. [Current status](blueprint-routing-prompts/NEXT-STEPS.md) and
[task 23 handoff](blueprint-routing-handoffs/23-sol-takeover.md): runtime migration,
the restricted operating adapter, and a real measured small-factory case are
complete. Real-pilot declarations and browser interaction acceptance remain
open. This checklist does not authorize changes to a live Factorio save and does
not treat illustrative pilot fixtures as real inputs.

## Revised direction

The [deterministic roadmap](blueprint-routing-deterministic-roadmap.md) governs
new development. Full-belt supply and bounded furnace inference now exist. The
commands below remain the checklist for collecting real pilot declarations; the
task-23 handoff contains the exact measured-case reproduction.

## 1. Integrated snapshot and connected tools

The tranche is now committed in `ab25b2a`. The latest recorded full run was
`make test`: 625 passed on 2026-09-11 against the preceding working tranche.
Rerun after implementation/evidence changes; this documentation update does not
establish a fresh test result.

The read-only MCP surface exposes `inspect_blueprint_layout`,
`analyze_blueprint_routes`, and `evaluate_blueprint_operating_rate`. The last is
the restricted deterministic serial-furnace adapter/capture validator; it does
not call a model or replace the routing capacity bound. After server-code
changes, verify the connected process again.

Evidence remains 16 records, 0 observed, 6 documented-only and 10 pending. MCP
connectivity does not close that gate.

## 2. Open the pilot and collect its real declarations

This can proceed alongside captures. Start with the existing development pilot:

```sh
cd /Users/juliusmopper/Dev/factoribot
routing_run_dir=$(mktemp -d /tmp/factoribot-routing.XXXXXX)
.venv/bin/factoribot routes inspect \
  --bp daemon/tests/fixtures/wip_science.txt \
  --provenance development_pilot \
  --json "$routing_run_dir/inspection.json" \
  --view "$routing_run_dir/layout.html" --open
```

Keep this shell open so `routing_run_dir` retains its value. Save artifacts you
want to retain to a named project location; remove only this generated scratch
directory after you have saved them. These commands only inspect the blueprint
file and create local artifacts.

Use the viewer to locate the real interface and export an assignment draft as
`assignments.json` into that directory. Have the host agent prepare
`request_template.json` using the contract and the declarations below. The
fixture `daemon/tests/fixtures/routing_public/pilot_request_template.json` is a
schema example only: replace its illustrative values, including its arbitrary
iron feed, zero-rate export, unknown mod and optimistic power declaration.

Provide these facts (or explicitly mark them unknown):

| Input | What to record |
| --- | --- |
| Blueprint | Confirm this is the layout to analyze, or supply the current export; preserve book entry selection |
| Incoming items | Each item, actual entry tile/lane or endpoint, and available items/s; identify shared budgets |
| Desired exports | Each item, exit endpoint, requested rate and objective (one maximized export or the supported declared objective) |
| Output removal | What removes each export or surplus, and its declared capacity; a chest is not automatically an unlimited sink |
| Furnaces | Run the optional inference pass after declaring real feeds; review every ambiguity group and retain explicit owner overrides |
| Environment | Exact game version and enabled mods with versions, especially the source of the three ee-super-substation entities |
| Research/recipes | Relevant research levels and available recipes; an omitted level is unknown |
| Power/control | Actual conditions or an explicitly accepted modeling assumption; record filters, priorities and circuit controls |

Current profile is base 2.0.77, normal quality. If the actual game differs, stop
claiming compatibility and give the integration owner the mismatch. Modules,
beacons and unsupported mechanics require their own scope decisions. Do not
remove unsupported entities or declare them irrelevant just to obtain a bound.

Once both JSON files contain reviewed declarations, seal and analyze them:

```sh
.venv/bin/factoribot routes request \
  --bp daemon/tests/fixtures/wip_science.txt \
  --provenance development_pilot \
  --template "$routing_run_dir/request_template.json" \
  --assignments "$routing_run_dir/assignments.json" \
  --out "$routing_run_dir/request.json"

.venv/bin/factoribot routes analyze \
  --bp daemon/tests/fixtures/wip_science.txt \
  --provenance development_pilot \
  --request "$routing_run_dir/request.json" \
  --result "$routing_run_dir/result.json" \
  --view "$routing_run_dir/audit.html" --open
```

For a new real export, replace the blueprint path consistently and use
`game_export` throughout. Preserve the same book path and any explicitly
supplied `--furnace-candidate` options across inspect/request/analyze. A change to
blueprint, prototypes, evidence or candidates can change identity: inspect again,
refresh the assignment draft and reseal; never edit hashes to bypass rejection.
When replaying via MCP, send the same provenance used to seal the request.

Completion: an inspection, complete declarations, assignments, sealed request,
result and viewer page with matching identities. Record all remaining unresolved
reasons. `partial` is acceptable evidence of a real blocker, not permission to
invent the missing input. Any numerical bound stays an optimistic upper bound,
not a prediction of measured production.

## 3. Capture game mechanics in a disposable environment

Follow the detailed [capture procedure](../daemon/factoribot/evidence/routing_mechanics_observations/CAPTURE.md)
and [record schema](../daemon/factoribot/evidence/routing_mechanics_observations/README.md).
Create a new sandbox; record its exact game build, mod versions, research,
control state and name. Keep existing saves untouched. Start with the profile's
supported version; do not label observations from another build as 2.0.77.

First capture batch: fast-belt straight/per-lane capacity, turns, side loading,
and belt-to-belt transfers (§4.1–4.4). Then underground range/pairing/lane mapping,
splitter behavior, and inserter pickup/drop geometry. Inserter timing research
matrices can follow; unknown inserter capacity remains explicitly relaxed.
Measure AM2/furnace behavior and power/control cases as required for the scope.

For each case retain the setup blueprint, supplied items, raw counts or topology
observations, ticks/interval, repetitions and environment. For rate tests use a
countable collector with enough capacity, or a recorded counter before removal;
an infinity sink that deletes items cannot supply a final inventory count.
Report disagreements with expected behavior rather than changing expectations
or averaging unexplained differences away.

Only mark the specific measured record observed after checking its evidence.
A fast-belt capture does not validate other tiers, all orientations or a modded
environment. If the current record schema cannot express that limited scope,
leave the gate open and have the integration owner resolve it before promoting
arcs to exact semantics. An agent without access to a game cannot fabricate a
capture from documentation or passing tests.

There are 16 records but only 15 game-capture subsections:
`unsupported.entity_visibility` is explicitly a static adapter/contract rule.
The evidence owner must resolve its appropriate acceptance criteria separately;
do not invent a measurement interval or game observation to close that record.

## 4. Integrate evidence and reassess the pilot

Use one owner for manifests, profile scope and shared-file edits. Other workers
can gather raw observations and pilot declarations independently.

```text
Integrate the supplied routing observations and pilot declarations in Factoribot.
Read docs/blueprint-routing-prompts/WORKING-RULES.md and
docs/blueprint-routing-next-run.md. Preserve the raw evidence. Check exact build,
mods, research, orientation and tier coverage before changing a rule to observed.
Do not generalize a narrow capture to an entire profile. Resolve the static
unsupported.entity_visibility record's acceptance separately. Compare observations
against transport/model assumptions and flag discrepancies; do not merely flip
statuses. Regenerate evidence manifests, run the focused tests and full suite,
inspect capability and tool-description/skill wording, then rebuild the layout
and reseal the real pilot request. Return observed/open rules, supported scope,
identity changes, test results, public-pipeline artifacts and unresolved blockers.
Never claim an upper bound is an achievable or measured production rate.
```

The evidence regeneration and verification entry points, from the repo root:

```sh
.venv/bin/python daemon/factoribot/evidence/routing_prototypes/generate.py --from-slice
.venv/bin/python -m pytest daemon/tests/test_transport_prototypes.py \
  daemon/tests/test_transport.py daemon/tests/test_routing.py \
  daemon/tests/test_routing_public.py -q
make test
```

Review the generated diff: `--from-slice` rebuilds from the pinned slice; it does
not export fresh game prototypes. Tests that intentionally pin today's zero
observations may need evidence-based updates. Preserve their checks that absent
or incomplete observations cannot become exact mechanics. Review static wording
in tool descriptions and skill docs too, even though capability counts are
computed dynamically.

Done means: reproducible evidence for the advertised scope; unchanged conservative
handling of unknowns; passing checks; and a real pilot report whose declarations
can be traced to the owner. Update the release review's gates individually.
Tasks 09–14 remain deferred until their documented prerequisites hold.

## Optional independent patch: audit F-4

A separate worker can fix the low-severity internal LP non-finite-RHS error using
[F-4's reproduction and acceptance criteria](blueprint-routing-release-review.md).
Own `routing_lp.py` and a dedicated regression test. Keep it separate from evidence
and integration edits; the fix must not weaken certificate validation. This patch
is not required to start gathering game observations or pilot declarations.
