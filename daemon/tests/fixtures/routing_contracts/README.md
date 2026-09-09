# Routing contract fixtures (task 00, schema 1.1.0)

Every layout/result except the pilot manifest is **synthetic**. Geometry, recipes,
capacity coefficients, certificates and assignments are hand-defined schema
examples. They are not solver output or observations of Factorio. In particular,
the furnace example's 10 crafts/s ceiling is illustrative, not its game speed.

Each complete example packages `graph`, `request`, `assignments`, `result`, and a
hand-checkable expectation. The graph contains canonical lossless source JSON,
prototype fixture input, geometry, ports, lanes, capacity groups and evidence.
Use `parse_graph`, `parse_request`, `parse_assignments` and `parse_result` from the
modules documented in [the contract](../../../../docs/blueprint-routing-contract.md).

| File | Independent expectation |
| --- | --- |
| `disconnected_circuit.json` | 10 crafts/s installed circuit capacity cannot supply a consumer with no delivery link; requested 1 science/s is insufficient |
| `shared_budget.json` | Two feeds share one 10 iron/s budget and two arcs share one 15 items/s resource; reserving 5/s leaves at most 5/s for the objective |
| `unsupported_bridge.json` | An unknown entity could bridge the missing link; partial, with no infeasibility or bound claim |
| `blocked_export.json` | 10 crafts/s machine capacity does not deliver to an isolated declared outlet; requested 1 circuit/s is insufficient |
| `furnace_override.json` | Explicit stone-brick override selects one of two activities sharing one furnace; 10 stone/s at 2/craft yields 5 bricks/s |
| `declared_power.json` | Unsupported modded substation (`power`, mod `EditorExtensions`, version `unknown`) declared irrelevant under power assumed available; bounds 10/10/10 permitted, partial without the declaration |
| `large_layout.json` | 3200 entities, 6400 ports, 3200 lanes, 3200 arcs, 3200 capacity groups in an 80 × 40 grid; one illustrative 5 iron/s feed/export |
| `pilot_manifest.json` | Real checked-in 2771-entity development pilot; actual assignments and runtime environment unresolved |

The first six are indented for review; the large fixture is compact JSON to limit
repository size. All IDs use the nested book entry path `[2,7]`, rather than a
flattened leaf offset. Finding evidence identifies source JSON pointers and ordered
arc paths. Selecting the large example's finding should highlight entity 1, its
left lane and its traversal arc; no browser checks have been performed by task 00.

From repository root:

```sh
.venv/bin/python daemon/tests/fixtures/routing_contracts/generate.py
.venv/bin/python -m pytest daemon/tests/test_blueprint_contract.py -q
make test
```

The generator builds immutable records through the public validators and writes
stable hashes. The tests separately check numerical counterexamples and reject
stale/malformed identities, hashes, sinks, unsupported options and unsound claims,
including undeclared mods and irrelevance declarations on item-capable subsystems.
Entity `subsystem`/`mod` values here are fixture-author claims standing in for the
adapter's classification.
No routing algorithm, optimizer or UI is included.
