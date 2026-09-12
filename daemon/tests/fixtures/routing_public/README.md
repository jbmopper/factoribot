# Public-integration fixtures (routing task 07)

Everything here is an **ILLUSTRATIVE DECLARATION**, not a measurement and not the
pilot's real interface. The pinned development pilot
`daemon/tests/fixtures/wip_science.txt` has unresolved feeds, exports, removal
services, research levels, enabled mods, control state, power availability and 76
recipe-less furnaces. Nothing in this directory resolves any of that, and
**no delivery bound is advertisable for the pilot**.

## Files

| File | What it is |
| --- | --- |
| `generate.py` | Rebuilds the three artifacts below from the pilot blueprint. |
| `pilot_assignments.json` | An assignment draft envelope, shaped exactly like the viewer's export: one declared feed at a boundary endpoint. |
| `pilot_request_template.json` | The host-policy half of a request: budget, export, objective, protected interfaces, assumptions, detail scope. |
| `pilot_provenance.json` | The identity hashes and counts the other two were generated against. |

The feed and export endpoints are chosen by a stated deterministic rule (the
first `transport_boundary_candidate` endpoint resolving to an incoming, resp.
outgoing, port, in graph order), so the choice is reproducible and reviewable
rather than hand-picked. Neither is claimed to be where the real factory is fed
or drained. `available_recipes` is copied from the graph's own activities, which
are the recipes the pilot's assembling machines declare in the blueprint itself.

`assumptions.mods` declares a mod literally named `unknown` providing `power`,
because task 03's adapter records `mod: unknown` for the three
`ee-super-substation` poles (the prototype extract carries no mod manifest) and
the contract rejects a graph entity whose mod is undeclared.
`assumptions.irrelevant` is deliberately **empty**: nothing here asserts those
poles are irrelevant to item delivery, so the analysis withholds every bound.

## Reproduce (from the repository root)

```sh
.venv/bin/python daemon/tests/fixtures/routing_public/generate.py

.venv/bin/factoribot routes inspect --bp daemon/tests/fixtures/wip_science.txt \
    --provenance development_pilot --view /tmp/pilot_layout.html

.venv/bin/factoribot routes request --bp daemon/tests/fixtures/wip_science.txt \
    --provenance development_pilot \
    --template daemon/tests/fixtures/routing_public/pilot_request_template.json \
    --assignments daemon/tests/fixtures/routing_public/pilot_assignments.json \
    --out /tmp/pilot_request.json

.venv/bin/factoribot routes analyze --bp daemon/tests/fixtures/wip_science.txt \
    --provenance development_pilot --request /tmp/pilot_request.json \
    --result /tmp/pilot_result.json --view /tmp/pilot_audit.html

.venv/bin/factoribot routes finding --bp daemon/tests/fixtures/wip_science.txt \
    --provenance development_pilot --result /tmp/pilot_result.json \
    --finding unresolved_unsupported_entity
```

Expected: `routes request` reports three unresolved reasons
(`unsupported entity: bp/root/e/162`, `.../e/255`, `.../e/1882`) and
`bounds_advertisable: false`; `routes analyze` returns status `partial` with
**no bounds and no witness**; `routes finding` shows the
`ee-super-substation` at world position (474, -32) together with its original
blueprint record.

Counterfactual, to see what a declaration changes (an EXPERIMENT, not a claim
about the factory): add an `irrelevant` declaration for subsystem `power` under
basis `power_assumed_available` to the template. `unresolved_reasons` then
becomes empty and the routing stage solves a 128,415-variable / 101,438-row /
304,720-nonzero model, certifying **0 items/s** for the illustrative export —
the two illustrative endpoints are not connected. That is a structural fact
about the chosen endpoints, not a statement about the factory's throughput.
