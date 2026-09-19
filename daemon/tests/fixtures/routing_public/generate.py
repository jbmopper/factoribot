"""Regenerate the public-integration fixtures for the pinned development pilot.

Run from the repository root::

    .venv/bin/python daemon/tests/fixtures/routing_public/generate.py

Everything written here is an **ILLUSTRATIVE DECLARATION**, not a measurement
and not the pilot's real interface. The pilot's actual feeds, exports, removal
services, research levels, enabled mods, control state, power availability and
the 76 furnaces' recipes are unresolved (routing contract, "Development pilot"),
and this generator invents none of them. What it does is mechanical:

* it builds the pilot's routing graph exactly as `factoribot routes inspect`
  does, so the identity hashes in the artifacts are the graph's own;
* it selects one feed endpoint and one export endpoint by a **stated
  deterministic rule** (below), so the choice is reproducible and reviewable
  rather than hand-picked;
* it copies the `available_recipes` list out of the graph's own activities,
  which are the recipes the pilot's assembling machines declare in the
  blueprint itself. That is a fact read from the blueprint, not an inference.

Selection rule
--------------
Feed: the first `transport_boundary_candidate` endpoint, in graph order, that
resolves to an **incoming** port; its lane alias is used. Export: the first such
endpoint that resolves to an **outgoing** port. "First in graph order" is
deterministic because the contract requires deterministic array order.

Neither endpoint is claimed to be where the real factory is fed or drained.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "daemon"))

from factoribot.blueprint_contract import MECHANICS_PROFILE, SCHEMA_VERSION, to_dict  # noqa: E402
from factoribot.routing import RecipeSource  # noqa: E402
from factoribot.routing_public import resolve_layout  # noqa: E402

HERE = Path(__file__).resolve().parent
PILOT = ROOT / "daemon/tests/fixtures/wip_science.txt"

ILLUSTRATIVE = (
    "ILLUSTRATIVE DECLARATION, not a measurement: the pilot's real feeds, exports, "
    "removal services, research, enabled mods, control state and power are unresolved."
)


def item(name):
    return {"kind": "item", "name": name, "quality": "normal"}


def build():
    try:
        recipes = RecipeSource()
    except (OSError, ValueError) as exc:  # no dump: the AM2 activities disappear
        raise SystemExit(f"this generator needs data/data-raw-dump.json: {exc}") from exc
    layout = resolve_layout(
        {"blueprint_string": PILOT.read_text(), "provenance": "development_pilot"},
        recipes=recipes,
    )
    graph = layout.graph
    ports = {p.id: p for p in graph.ports}
    lanes = {ln.id: ln for ln in graph.lanes}

    def role_of(endpoint):
        if endpoint in ports:
            return ports[endpoint].role, endpoint
        if endpoint in lanes:
            lane = lanes[endpoint]
            return ports[lane.incoming].role, endpoint
        return None, endpoint

    boundary = [ep for finding in layout.findings if finding.code == "transport_boundary_candidate"
                for ep in finding.endpoint_ids]
    feed_endpoint = export_endpoint = None
    for endpoint in boundary:
        role, ident = role_of(endpoint)
        if role == "incoming" and feed_endpoint is None:
            feed_endpoint = ident
        elif role == "outgoing" and export_endpoint is None:
            export_endpoint = ident
    if feed_endpoint is None or export_endpoint is None:
        raise SystemExit("the pilot graph offered no incoming/outgoing boundary candidate")

    assignments = {
        "schema_version": graph.schema_version,
        "blueprint_hash": graph.blueprint_hash,
        "graph_hash": graph.graph_hash,
        "feeds": [{
            "id": "pilot_feed", "budget_id": "iron",
            "endpoint": to_dict(feed_endpoint),
            "capacity": {"kind": "unlimited", "value": None},
        }],
        "furnaces": [],
        "controls": [],
    }
    draft = {
        "document_kind": "factoribot.routing.assignment_draft",
        "note": ILLUSTRATIVE + " Shaped exactly like the viewer's assignment export.",
        "selection_rule": "first transport_boundary_candidate endpoint resolving to an incoming port",
        "assignments": assignments,
    }

    template = {
        "note": ILLUSTRATIVE,
        "budgets": [{"id": "iron", "material": item("iron-plate"),
                     "capacity": {"kind": "finite", "value": 60.0}}],
        "exports": [{
            "id": "pilot_export", "material": item("iron-plate"),
            "endpoint": to_dict(export_endpoint),
            "requirement": "minimum", "rate": 0.0,
            "sink": {"kind": "external", "service": ILLUSTRATIVE,
                     "capacity": {"kind": "unlimited", "value": None}},
        }],
        "surplus": [],
        "objective": {"kind": "maximize_export", "export_id": "pilot_export"},
        "protected": {"entities": [], "endpoints": [], "areas": [],
                      "preserve_wiring": True, "preserve_unknown": True, "preserve_boundaries": True},
        "assumptions": {
            "game_version": "2.0.77",
            # The pilot's three ee-super-substation poles carry mod `unknown`: task 03's
            # adapter refuses to write "EditorExtensions" because the base-only extract
            # has no such prototype. The contract rejects a graph entity whose mod is
            # undeclared, so a mod literally named `unknown` is declared here -- an honest
            # audit line ("an unidentified mod provides these power prototypes").
            # `irrelevant` stays EMPTY on purpose: nothing here asserts those poles are
            # irrelevant to item delivery, so the analysis reports them as unresolved and
            # withholds every bound instead of assuming them away.
            "mods": [{"name": "unknown", "version": "unknown", "provides": ["unknown"],
                      "alters_item_mechanics": False},
                     {"name": "base", "version": "2.0.77", "provides": [], "alters_item_mechanics": False}],
            "quality": "normal",
            # Read from the blueprint's own recipe fields via the graph's activities.
            "available_recipes": sorted({a.recipe for a in graph.activities}),
            "research": [],
            "control_policy": "relax_open",
            "power": "assumed_available",
            "modules": "none",
            "beacons": "none",
            "irrelevant": [],
        },
        "detail": {"kind": "summary", "entity_ids": [], "cursor": None, "limit": 100},
    }

    (HERE / "pilot_assignments.json").write_text(json.dumps(draft, indent=1, sort_keys=True) + "\n")
    (HERE / "pilot_request_template.json").write_text(json.dumps(template, indent=1, sort_keys=True) + "\n")
    provenance = {
        "note": ILLUSTRATIVE,
        "blueprint_file": "daemon/tests/fixtures/wip_science.txt",
        "schema_version": SCHEMA_VERSION,
        "mechanics_profile": MECHANICS_PROFILE,
        "blueprint_hash": graph.blueprint_hash,
        "prototype_hash": graph.prototype_hash,
        "graph_hash": graph.graph_hash,
        "counts": layout.counts(),
        "feed_endpoint": feed_endpoint.key,
        "export_endpoint": export_endpoint.key,
        "activity_recipes": len(template["assumptions"]["available_recipes"]),
    }
    (HERE / "pilot_provenance.json").write_text(json.dumps(provenance, indent=1, sort_keys=True) + "\n")
    print(json.dumps(provenance, indent=1))


if __name__ == "__main__":
    build()
