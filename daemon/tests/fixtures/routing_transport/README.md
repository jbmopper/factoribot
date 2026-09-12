# Transport-graph fixtures (routing task 04)

Everything in this directory is **SYNTHETIC**: hand-placed blueprint layouts and
hand-written request declarations. Nothing here is a game observation, a
measurement, or a claim about how Factorio behaves. The engine-behaviour
evidence lives in `../../../factoribot/evidence/routing_mechanics_observations/`,
where every rule is still `documented-only` or `pending` and none is `observed`.

## Files

| File | What it is |
| --- | --- |
| `layouts.py` | Blueprint documents built entity by entity from tile coordinates, one function per acceptance case, plus `translate` and `rotate` transforms. |
| `requests.py` | Minimal `RoutingRequest` builders: explicit budgets, feeds, exports with a named external removal service, mods, recipes and control policy. Nothing is inferred. |

The *expected* ports, lanes, arcs, capacity groups and delivery numbers are not
stored here. They are written out by hand in `daemon/tests/test_transport.py`
and `daemon/tests/test_routing.py`, next to the derivation, so a test cannot
pass by agreeing with whatever the implementation emitted.

## Reproduce

```sh
.venv/bin/python daemon/tests/fixtures/routing_transport/layouts.py   # print every layout
.venv/bin/python -m pytest daemon/tests/test_transport.py daemon/tests/test_routing.py -q
```

No JSON artifact is checked in: each layout is a few lines of Python, and the
graph built from it is large (the pilot's graph is about 12 MB of canonical
JSON). To regenerate a graph for inspection:

```sh
.venv/bin/python - <<'PY'
import json
from factoribot.blueprint_contract import to_dict
from factoribot.routing import RecipeSource, RoutingOptions, build_transport_graph
from factoribot.spatial import load_spatial_view

view = load_spatial_view(open("daemon/tests/fixtures/wip_science.txt").read())
built = build_transport_graph(view, RoutingOptions(
    provenance="development_pilot", recipes=RecipeSource()))
print(built.counts(), built.stats["build_seconds"])
json.dump(to_dict(built.graph), open("/tmp/pilot_graph.json", "w"))
PY
```

## The pilot is not a validated factory

`daemon/tests/fixtures/wip_science.txt` is the development pilot named by the
routing contract. Its feeds, exports, research, enabled mods, control state,
power and the 76 furnaces' recipes are all unresolved, and no bound may be
advertised for it. The pilot appears in these tests only as a size, shape and
timing case.
