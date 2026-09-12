# Fix B handoff — duplicate finding IDs in delivery reporting

## 1. Identity

- Task: Fix B in `docs/blueprint-routing-prompts/NEXT-STEPS.md` (duplicate finding IDs).
- Starting snapshot: reviewed commit `76fd016`, working tree at `664662e` (clean at start;
  Fix C's viewer edits appeared in the shared checkout while this ran).
- Contract version consumed: **1.1.1** (`SCHEMA_VERSION`); no contract change was needed
  and none is proposed.
- Model: Claude (Opus 5).

## 2. What changed

Owned and changed:

- `daemon/factoribot/blueprint_plan.py` — semantic codes for the two colliding categories
  plus a deliberate merge step for identities the contract cannot express.
- `daemon/tests/test_routing_reporting_regressions.py` (new) — 13 tests.
- `docs/blueprint-routing-handoffs/fix-b-finding-ids.md` — this document.

Changed outside the owned set (one line, unavoidable, coordinate if it conflicts):

- `daemon/tests/test_blueprint_plan.py:288` asserted the literal code `unresolved_model`,
  which no longer exists for that case; it now asserts `f.code.startswith("unresolved_")`.
  No other assertion in the repository names a renamed code. `routing_lp.py`, the viewer,
  transport files, `tools.py`, `mcp_server.py`, `cli.py` and the skills are untouched.

### The defect

`finding_id` hashes **code + sorted entity/endpoint scope + material + sorted evidence**;
severity and message text are outside identity by design. Reporting emitted several
findings per result whose only difference lived outside that identity, so `parse_result`
rejected the whole result with `ContractError: duplicate finding ID` — a reporting bug that
destroyed an otherwise valid analysis.

### The rule now implemented

1. **Distinct semantics get distinct codes**, so the identity the contract already hashes
   separates them:
   - unresolved reasons: `unresolved_topology_gap`, `unresolved_unsupported_entity`,
     `unresolved_ambiguous_furnace`, `unresolved_power`, `unresolved_mod_mechanics`
     (`unresolved_model` remains the fallback for any reason class a future contract adds,
     and such a class merges rather than colliding);
   - per-stage solver limits: `solver_limit_aggregate`, `solver_limit_budget`,
     `solver_limit_routing`. The two whole-analysis limit findings (a relaxed stage
     infeasible while routing is not; a rejected routing witness) keep the generic
     `solver_limit` code — they are single records and mutually exclusive.
2. **Everything still sharing an identity is merged on purpose** by `_merge_findings`,
   applied at the single choke point `_base_result`. A collision there means the
   discriminator is something the contract's identity cannot carry (a capacity-group ID, a
   mod name, an activity ID), so the group is combined instead of duplicated or dropped:
   messages are concatenated in generation order (nothing discarded), severity becomes the
   strongest of the group, a structured rate/bound survives only if the group agrees, and a
   mixed evidence kind degrades to `conditional` (never to `observed` or `upper_bound`).
   Scope and evidence are identical across a group by construction, so entity/endpoint/
   evidence references are preserved exactly.

No `ContractError` is caught anywhere, no ID is generated randomly, no message is dropped,
and identity still ignores translated message text — verified directly in
`test_identity_ignores_message_text_and_severity`.

Ordering stays deterministic: findings are generated from contract-ordered collections,
merged in first-appearance order, and emitted sorted by ID (`_merge_findings` returns the
sorted list, so `_base_result`'s previous sort is subsumed).

### Other repeated categories checked

| category | discriminator | collides? | handling |
| --- | --- | --- | --- |
| unresolved reasons | reason class, mod name | yes (reproduced) | distinct codes; multiple mods merge |
| per-stage solver limit | stage | yes (reproduced) | one code per stage |
| `unknown_capacity_relaxed` | capacity-group / activity ID | yes | merged (both group IDs kept in the message) |
| `control_disabled_connection` | arc ID (parallel arcs) | yes | merged (both arc IDs and conditions kept) |
| `furnace_alternative_excluded` | activity ID (3+ candidates) | yes | merged (both activity IDs kept) |
| `budget_without_feed` | material | **no** — the contract enforces one budget per material (`unique(... "global material budget")`), so material alone is a sufficient identity | unchanged, covered by a test |
| `delivery_upper_bound`, `zero_objective`, `delivery_insufficient`, `feasibility_only`, `conditional_connections_open` | — | no, one per result | unchanged |

## 3. Commands, results, fixtures

```sh
.venv/bin/python -m pytest daemon/tests/test_routing_reporting_regressions.py -q   # 13 passed
.venv/bin/python -m pytest daemon/tests/test_blueprint_plan.py -q                  # 32 passed
.venv/bin/python daemon/tests/fixtures/routing_plan/cases.py                       # every case prints, unchanged
make test    # before: 330 passed (review baseline) / after: 350 passed, 0 failed, 0 skipped
```

The 350 includes this task's 13 new tests and 7 from Fix C's `test_viewer_provenance_regressions.py`,
which landed in the shared checkout during this work. No failure in a file owned by another
task was observed at the final run.

Fixtures: no new fixture files. Every case is built from the existing synthetic
`daemon/tests/fixtures/routing_plan/cases.py` builders (`pass_through`, `Layout`,
`request_document`); requests are resealed with the fixture's own `seal(...,
"request_hash")` and parsed by `parse_request`, so they are valid contract requests rather
than doctored records. `cases.py` itself was **not** edited.

Pre-fix behaviour is reproducible without reverting the fix, by restoring exactly HEAD's
two decisions at runtime:

```python
blueprint_plan._merge_findings = lambda f: sorted(f, key=lambda x: x["id"])
blueprint_plan._UNRESOLVED_CODES = {}    # -> "unresolved_model" for every reason
blueprint_plan._STAGE_LIMIT_CODES = {}   # -> "solver_limit" for every stage
```

Under those three lines the new tests report:

```
FAIL  unknown power + altering mod: ContractError: duplicate finding ID
FAIL  all stages at size limit: ContractError: duplicate finding ID
FAIL  two excluded furnace alternatives: ContractError: duplicate finding ID
FAIL  two unknown groups on one arc: ContractError: duplicate finding ID
FAIL  two parallel disabled arcs: ContractError: duplicate finding ID
FAIL  two altering mods: ContractError: duplicate finding ID
PASS  unfed budgets by material          (never collided: budgets are unique per material)
```

## 4. Before / after

**Reported case 1** — `pass_through` with `power="unknown"` and a declared mod
`itemtweaks` with `alters_item_mechanics=True` (request rebuilt and resealed).
`unresolved_reasons` returns `("power availability unknown", "mod alters item mechanics:
itemtweaks")`.

- Before: both findings were `unresolved_model` with empty entity/endpoint/material/evidence
  scope → one ID for two records → `ContractError: duplicate finding ID`, no result at all.
- After: `partial`, no bounds, no witness, two findings —
  `finding:0bc2…` `unresolved_power` and `finding:aa76…` `unresolved_mod_mechanics` — each
  carrying its own reason text. With a second altering mod (`quality-rework`) the two mod
  reasons share an identity the contract cannot split, so they merge into one
  `unresolved_mod_mechanics` finding whose message names **both** mods in contract order.

**Reported case 2** — `pass_through` with `PlanOptions(max_variables=0)`.

- Before: three scope-less `solver_limit` findings (aggregate, budget, routing) →
  `ContractError: duplicate finding ID`.
- After: `solver_limit`, no bounds, no witness, three findings
  `solver_limit_aggregate` / `solver_limit_budget` / `solver_limit_routing`, each keeping
  its own stage certificate and size note.

**Counterexample to over-merging**: with `PlanOptions(max_variables=6)` only routing (8
variables) exceeds the limit while the relaxed stages (4 variables) solve normally; the
result carries exactly one finding, `solver_limit_routing`, and the aggregate stage is
still `optimal`. A "merge every solver limit into one finding" fix would blur that.

**Determinism**: `test_repeated_analysis_is_deterministic` runs the normal, unresolved,
solver-limit and merged-finding cases three times each and asserts one `result_hash`, one
finding-ID order and one message sequence per case.

## 5. Assumptions, limitations, unmet gates

- Every case is synthetic (`provenance="synthetic"`); this fix is reporting hygiene and
  changes no number, bound, certificate or status logic. All bound values, statuses and
  witnesses in the existing suite are unchanged.
- Merging is a genuine loss of *structure*, not of information: two unknown capacity groups
  on one arc become one finding whose message names both groups. If a consumer needs
  per-group records, the contract's identity inputs would have to grow a discriminator —
  that change is **not** proposed here, because distinct codes plus merging express
  everything currently reported.
- New finding codes are public surface for consumers that filter by code. No consumer in
  the repository does (the viewer maps result *status*, not finding codes; `planner.py`'s
  `solver_limit` string is the unrelated production planner). Task 07 should list the code
  set when it registers the public surface.
- Unmet gates from `05-delivery-bounds.md` are untouched: no adapter-produced graph, no
  game observations, no MCP/CLI exercise of this path.
- Fix A (`routing_lp.py`) may change which stages come back `uncertified`/`limit`; that
  only changes *which* per-stage code is emitted, not identity, so the two fixes compose.

## 6. Next

Nothing here blocks task 04 or task 07. Task 08 should exercise
`daemon/tests/test_routing_reporting_regressions.py` alongside the certificate and viewer
regressions, and re-check the "other repeated categories" table above against any finding
category task 04 or 07 adds — the rule for a new repeated finding is: give it a code that
names what differs, or accept the merge.
