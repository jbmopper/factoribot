# Task 02b handoff — ship the pinned evidence inside the package

## 1. Identity

- Task: cleanup task "make the pinned prototype extract and mechanics-observation
  records ship with the installed package" (coordinator assignment, following
  task 07's §7 defect report), under `docs/blueprint-routing-prompts/WORKING-RULES.md`.
- Starting snapshot: HEAD `664662e` ("codex review and next steps") plus the
  uncommitted working tree containing tasks 02–07, fixes A/B/C, and their
  handoffs. `make test` reported **544 passed, 0 skipped** before this task.
- Read in full before starting: `docs/blueprint-routing-prompts/WORKING-RULES.md`,
  task 07's handoff §7 ("Packaging: one fix, one defect found"),
  `daemon/factoribot/transport_prototypes.py`, both fixture READMEs
  (`routing_prototypes/README.md`, `routing_mechanics_observations/README.md`
  and `CAPTURE.md`), and `daemon/pyproject.toml`.
- Model: Claude (this session).
- Nothing committed, stashed, reset or cleaned. No game, save, or MCP server
  touched. Two scratch venvs and one scratch wheel were created under this
  session's scratchpad directory to verify the fix and were deleted afterward
  (§4).

## 2. The defect (task 07, §7)

`transport_prototypes.py` resolved its pinned evidence relative to the
*source tree*:

```python
_TESTS_ROOT = Path(__file__).resolve().parents[1] / "tests"
PROTOTYPE_FIXTURE_DIR = _TESTS_ROOT / "fixtures" / "routing_prototypes"
OBSERVATION_FIXTURE_DIR = _TESTS_ROOT / "fixtures" / "routing_mechanics_observations"
```

From an installed wheel, `Path(__file__).resolve().parents[1]` lands on
`site-packages/`, so this resolved to `site-packages/tests/fixtures/...`, which
no wheel contains and which `package-data` on the `factoribot` package cannot
reach (setuptools cannot ship files outside the package directory as
package-data). `load_pinned_extract()` raised `PrototypeError`, and the whole
routing surface (`inspect_blueprint_layout`, `analyze_blueprint_routes`,
`get_capabilities().blueprint_routing`) degraded to "evidence unavailable"
outside a checkout. Task 07 named the defect and reported it honestly rather
than compensating for it; this task fixes it, per the coordinator's decision
(task 07 §7, option 1: move the evidence into the package).

## 3. What changed

**Moved (`git mv`, tracked; content byte-identical — see §5 for proof), 25
files:**

| From | To |
| --- | --- |
| `daemon/tests/fixtures/routing_prototypes/{README.md, generate.py, manifest.json, pilot_coverage.json, prototypes.json, raw_prototype_slice.json}` | `daemon/factoribot/evidence/routing_prototypes/` |
| `daemon/tests/fixtures/routing_mechanics_observations/{README.md, CAPTURE.md, manifest.json, records/*.json (16)}` | `daemon/factoribot/evidence/routing_mechanics_observations/` |

**Owned and changed:**

- `daemon/factoribot/transport_prototypes.py` — `PROTOTYPE_FIXTURE_DIR` and
  `OBSERVATION_FIXTURE_DIR` now resolve from
  `Path(__file__).resolve().parent / "evidence" / ...` (i.e. relative to the
  package file itself, not to a `tests/` sibling). Public constant names
  (`PROTOTYPE_FIXTURE_DIR`, `OBSERVATION_FIXTURE_DIR`, `RAW_SLICE_PATH`,
  `EXTRACT_PATH`, `MANIFEST_PATH`, `PILOT_COVERAGE_PATH`,
  `OBSERVATION_INDEX_PATH`, `OBSERVATION_RECORD_DIR`) are unchanged; every
  downstream module (`routing.py`, `test_transport_prototypes.py`,
  `test_routing_public.py`) that imports them needed no further edit beyond
  what's listed below. Docstring updated to match.
- `daemon/factoribot/evidence/routing_prototypes/generate.py` — its module
  docstring's two `.venv/bin/python ...generate.py` commands now name the new
  path. `PILOT_PATH` (the pilot blueprint `wip_science.txt` this generator
  reads) is now computed as `REPO_ROOT / "daemon" / "tests" / "fixtures" /
  "wip_science.txt"` instead of `HERE.parent / "wip_science.txt"` — that
  relative form silently broke when the generator moved, because
  `wip_science.txt` is genuine test data and correctly stays under
  `daemon/tests/fixtures/`, not evidence, so it did not move with the
  generator. `OBSERVATION_DIR = HERE.parent / "routing_mechanics_observations"`
  needed no change: both evidence directories moved together and stayed
  siblings. `REPO_ROOT = HERE.parents[3]` also needed no change: the new
  location (`daemon/factoribot/evidence/routing_prototypes/`) is the same
  depth from the repository root as the old one
  (`daemon/tests/fixtures/routing_prototypes/`).
- `daemon/factoribot/evidence/routing_prototypes/README.md`,
  `daemon/factoribot/evidence/routing_mechanics_observations/README.md`,
  `daemon/factoribot/evidence/routing_mechanics_observations/CAPTURE.md` —
  regeneration commands updated to the new `generate.py` path. The
  `../routing_mechanics_observations/` relative cross-reference inside
  `routing_prototypes/README.md` needed no change (still siblings).
- `daemon/factoribot/routing_public.py` — every prose/error-message path
  reference updated (module docstring, `capture_procedure`,
  `prototype_source`). `_evidence_unavailable()`'s message and its `requires`
  field were rewritten: it no longer says "needs a repository checkout" (that
  claim is now false — a normal `pip install` carries the evidence). It now
  says the evidence ships via package-data at
  `factoribot/evidence/routing_prototypes/` and
  `factoribot/evidence/routing_mechanics_observations/`, and that this error
  firing at all means that package data is missing anyway (stripped or
  corrupted install), not that the surface needs a checkout.
- `daemon/factoribot/spatial.py`, `daemon/factoribot/transport.py` — one
  docstring path reference each, updated.
- `daemon/factoribot/routing.py` — **deliberately left unchanged**, plus a
  comment explaining why (§6): one `SourceRef` path string there
  (`f"routing_mechanics_observations/records/{rule_id}.json"`) is embedded in
  `Evidence` objects that feed `SpatialGraph`'s content hash. Updating that
  string to the new path changes `graph_hash` for every layout, which broke
  the pinned pilot fixtures (`daemon/tests/fixtures/routing_public/
  pilot_assignments.json`, sealed against the old hash) — caught by
  `test_routing_public_pilot.py` failing with `stale_identity`. It is a
  citation label embedded in contract data, not a resolved filesystem path,
  so it is out of scope for a path-reference fix and reverted.
- `daemon/pyproject.toml` — `[tool.setuptools.package-data]` gained entries for
  `factoribot/evidence/routing_prototypes/*.{json,md,py}` and
  `factoribot/evidence/routing_mechanics_observations/*.{json,md}` plus
  `.../records/*.json`, alongside the existing `blueprint_view_assets/` entry.
  `generate.py` stayed inside the package (kept as `*.py` in package-data)
  rather than moving to `daemon/tests/fixtures/`, since it is the tool that
  regenerates the evidence it sits next to and the READMEs' regeneration
  commands read most naturally pointing at the same directory as the data.
- `daemon/tests/fixtures/routing_transport/README.md` — one cross-reference to
  `../routing_mechanics_observations/` updated to
  `../../../factoribot/evidence/routing_mechanics_observations/` (no longer a
  sibling once only one of the two directories moved).
- `daemon/tests/fixtures/routing_spatial/generate.py` and its checked-in output
  `daemon/tests/fixtures/routing_spatial/pilot_sample.json` — the documentary
  `geometry.prototype_extract` provenance string updated to the new path. This
  field is metadata recording where the extract lived when the sample was
  generated, not a hash or a loaded value (the file's own
  `document_content_hash` hashes the *blueprint*, not this JSON), so updating
  it does not change anything `test_spatial.py` checks other than requiring
  the generator and the checked-in file to still agree — verified (§4).
- `daemon/tests/test_transport_prototypes.py` — new test
  `test_fixture_locations_resolve_inside_the_installed_package`, asserting
  `PROTOTYPE_FIXTURE_DIR`, `OBSERVATION_FIXTURE_DIR`, `EXTRACT_PATH` and
  `MANIFEST_PATH` all resolve under the `factoribot` package directory (via
  `Path.is_relative_to`) and contain no `tests` path component.
- `daemon/tests/test_routing_public.py` —
  `test_absent_pinned_evidence_is_a_named_error_not_a_substitution` (task 07's
  test simulating missing evidence via `monkeypatch`) had its docstring and
  final assertion updated: it no longer claims "no wheel ships [the evidence]"
  (now false) and now asserts `"factoribot/evidence" in out["requires"]`
  instead of `"daemon/tests/fixtures" in out["requires"]`. The test's mechanism
  (monkeypatching `EXTRACT_PATH` to an absent file, and expecting a named
  `evidence_unavailable` error rather than a silent substitution) is
  unchanged.
- `README.md` and `docs/blueprint-routing-prompts/NEXT-STEPS.md` — the one
  clickable `[capture procedure](...)` link in each updated to the new
  `CAPTURE.md` path.

**Left unchanged, deliberately** (historical handoff narrative, per
`WORKING-RULES.md` and the assignment's own instruction to update handoffs
"only where the text is an instruction someone would run"):
`docs/blueprint-routing-handoffs/{02-prototypes-and-fixtures,03-spatial-model,
04-transport-graph,07-public-integration}.md` and
`docs/blueprint-routing-prompts/02-prototypes-and-fixtures.md` still name the
old `daemon/tests/fixtures/routing_prototypes/` /
`routing_mechanics_observations/` paths in their prose and in task 07's
verbatim quotation of the buggy code and its exact `PrototypeError` message —
those are accurate historical records of what those tasks did and found at the
time, not live pointers, and 07's quotation is the evidence for the defect this
task fixes.

**Not touched:** evidence *content* — no `prototypes.json` prototype record,
no `manifest.json` hash, no observation record's `evidence_status`,
`measurement`, or `blocking_gate`, and no line of `routing.py`,
`transport.py`, `spatial.py`, or `blueprint_plan.py`'s actual mechanics or
arithmetic. `extract.content_hash()` is verified identical before and after
(§5).

## 4. Commands run and results

```sh
.venv/bin/python -m pytest daemon/tests/test_transport_prototypes.py -q
# 41 passed (was 40; +1 new test)

.venv/bin/python -m pytest daemon/tests/test_routing_public.py daemon/tests/test_routing.py \
  daemon/tests/test_transport.py daemon/tests/test_spatial.py daemon/tests/test_mcp_routing.py \
  daemon/tests/test_routing_public_pilot.py -q
# 232 passed

.venv/bin/python -m pyflakes daemon/factoribot/{transport_prototypes,routing,routing_public,spatial,transport}.py \
  daemon/tests/test_transport_prototypes.py daemon/tests/test_routing_public.py \
  daemon/factoribot/evidence/routing_prototypes/generate.py
# clean

make test
# 545 passed in 48.15s (544 baseline + 1 new test), 0 skipped

git diff --check
# clean, exit 0
```

### Wheel verification (task 07's exact method, repeated)

```sh
# throwaway venv, build isolated from the project .venv
python3 -m venv $SCRATCH/build_venv
$SCRATCH/build_venv/bin/pip install -q --upgrade pip build
cd daemon && $SCRATCH/build_venv/bin/python -m build --wheel --outdir $SCRATCH/wheel_out .
# Successfully built factoribot-0.0.1-py3-none-any.whl
# wheel listing includes, among others:
#   factoribot/evidence/routing_mechanics_observations/{CAPTURE.md,README.md,manifest.json,records/*.json (16)}
#   factoribot/evidence/routing_prototypes/{README.md,generate.py,manifest.json,pilot_coverage.json,prototypes.json,raw_prototype_slice.json}

python3 -m venv $SCRATCH/install_venv
$SCRATCH/install_venv/bin/pip install -q $SCRATCH/wheel_out/factoribot-0.0.1-py3-none-any.whl

cd $SCRATCH   # outside the repository
$SCRATCH/install_venv/bin/python -c "
from factoribot.transport_prototypes import load_pinned_extract
e = load_pinned_extract()
print('prototypes:', len(e.prototypes)); print('supported:', len(e.supported_names()))"
# prototypes: 20
# supported: 14

$SCRATCH/install_venv/bin/python -c "
from factoribot.routing_public import routing_capabilities
c = routing_capabilities()
me = c['mechanics_evidence']
print('available:', me['available'], 'records:', me['records'], 'by_status:', me['by_status'],
      'observed:', me['observed'], 'gate:', me['gate'])
print('supported_prototypes:', len(c['supported_prototypes']))"
# available: True records: 16 by_status: {'documented-only': 6, 'pending': 10} observed: 0 gate: unmet
# supported_prototypes: 14

$SCRATCH/install_venv/bin/python -c "
from factoribot.transport_prototypes import PROTOTYPE_FIXTURE_DIR, OBSERVATION_FIXTURE_DIR
print(PROTOTYPE_FIXTURE_DIR); print(PROTOTYPE_FIXTURE_DIR.is_dir(), OBSERVATION_FIXTURE_DIR.is_dir())"
# .../install_venv/lib/python3.14/site-packages/factoribot/evidence/routing_prototypes
# True True

# extra check beyond task 07's method: the full layout builder, not just the loader
$SCRATCH/install_venv/bin/python -c "
from factoribot.routing_public import build_layout
import json
doc = {'blueprint': {'item': 'blueprint', 'version': 281479277969408,
        'entities': [{'entity_number': 1, 'name': 'fast-transport-belt',
                      'position': {'x': 0.5, 'y': 0.5}, 'direction': 2}]}}
layout = build_layout(json.dumps(doc))
print('graph_hash:', layout.graph.graph_hash[:16])"
# graph_hash: sha256:7d439e382  (no PrototypeError / evidence_unavailable)

rm -rf $SCRATCH/build_venv $SCRATCH/install_venv $SCRATCH/wheel_out
rm -rf daemon/build daemon/*.egg-info
```

$SCRATCH was this session's scratchpad directory. Both venvs and the wheel were
deleted after verification; `git status` shows nothing stray left behind.

## 5. Proof the evidence content itself is unchanged

```sh
git status --porcelain daemon/tests/fixtures/routing_prototypes daemon/tests/fixtures/routing_mechanics_observations \
  daemon/factoribot/evidence
```

`git mv` recorded pure renames (`R`, not `RM`) for every data file — all 6
`routing_prototypes` JSON/data files and 17 of the 19
`routing_mechanics_observations` files (`manifest.json` and all 16
`records/*.json`). Only `README.md` and `CAPTURE.md` in each directory show
`RM` (renamed *and* modified), and the only modification in each is the
regeneration command's path (§3) — confirmed by reading the diff for those two
files specifically; no other line changed.

`extract.content_hash()` before this task (task 07's handoff, §5's counts
table and task 02's handoff §4): `sha256:756af0daaf0d…`. After the move:

```
sha256:756af0daaf0da4d68e414513bf18144b2638e9e6b76d3319fe1f7e38e126655e
```

Same hash, same 20 prototypes / 14 supported. The manifest, the 16 mechanics
records, and their statuses (6 documented-only / 10 pending / 0 observed) are
untouched — confirmed by the wheel check in §4 reporting the same 6/10/0 split
task 07 reported, and by `make test` passing every existing assertion that
pins specific evidence values (e.g. `test_every_first_release_rule_has_exactly_one_record`,
`test_a_mutated_slice_fails_its_manifest`) unmodified.

## 6. One before/after

**Before** (task 07 §7, reproduced against a wheel built from the pre-move
tree):

```
python -c "from factoribot.transport_prototypes import load_pinned_extract; load_pinned_extract()"
# PrototypeError: pinned prototype extract not found at .../site-packages/tests/fixtures/routing_prototypes/prototypes.json
```

**After** (this task, §4, from a fresh venv, cwd outside the repository):

```
python -c "from factoribot.transport_prototypes import load_pinned_extract; print(len(load_pinned_extract().prototypes))"
# 20
```

**Counterexample this fix must not fall for, and did not:** naively updating
*every* string containing the old path — including the `SourceRef` citation in
`routing.py` line ~312 that is embedded in hashed `Evidence` content — would
have silently changed `graph_hash` for every layout built from that point on,
invalidating every pinned/sealed fixture keyed to the old hash (the pilot's
`pilot_assignments.json`, `pilot_request_template.json`, saved request/result
documents). This was caught by `test_routing_public_pilot.py` failing with
`PublicError: the assignment document does not match this graph`
(`stale_identity`) on the first pass, reverted in `routing.py`, and reproduced
green afterward (§4). The distinction that matters: a string that is *read as
a filesystem path* got updated; a string that is *embedded as content inside a
hashed contract record* did not, even though both mention the same directory
name.

## 7. Assumptions, unsupported mechanics, unmet gates

- This task changes packaging only. The game-mechanics evidence gate is still
  **unmet**: 0 observed, 6 documented-only, 10 pending, exactly as task 02 left
  it and as this task's own wheel check reports (§4). Nothing here moves that
  needle; it only makes the (still incomplete) evidence reachable from an
  installed package.
- `generate.py`'s regeneration commands are the only commands verified to
  still work from their new location conceptually (path arithmetic checked by
  hand in §3); they were not re-run end-to-end against the full 14 MB dump in
  this session (no dump-mutation was needed — the fixtures did not change —
  and re-running the generator is what task 02's own regeneration tests
  already cover in `test_transport_prototypes.py`, which passed).
- Historical handoff documents under `docs/blueprint-routing-handoffs/` and
  `docs/blueprint-routing-prompts/` (other than the two live "capture
  procedure" links fixed in §3) still describe the *old* fixture location, by
  design (§3); a reader following those handoffs' file-listing prose to the
  literal old path will not find the files there. Only `README.md` and
  `NEXT-STEPS.md`'s clickable links, and the regeneration commands inside the
  moved fixture READMEs themselves, were treated as live pointers worth
  correcting.
- Not verified in this session: an *editable* install (`pip install -e`) was
  not separately checked; task 06's precedent (`blueprint_view_assets`) and
  this task both rely on `package-data`, which setuptools honors for editable
  installs project-wide already, and the fixture-location constants resolve
  from `Path(__file__)` regardless of install mode, so no separate case was
  expected — but it was not run as a distinct check.

## 8. Next

The routing surface (`inspect_blueprint_layout`, `analyze_blueprint_routes`,
`get_capabilities().blueprint_routing`) now functions identically whether
Factoribot is run from this checkout or from an installed wheel. Task 08
(independent audit) or any further integration work can proceed; no
prerequisite is newly blocked or newly unblocked by this task beyond the
packaging defect itself being closed. The user's running MCP server (if any)
was not reloaded — it must be, before anyone claims that process reads
evidence from the new location.
