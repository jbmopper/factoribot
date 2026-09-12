"""Minimal SYNTHETIC routing requests for the transport-graph acceptance cases.

Everything here is an *explicit declaration*: budgets, feeds, exports and their
removal services, mods, recipes and control policy. Nothing is inferred from the
graph, and none of these numbers is a measurement -- they exist so the graph can
be pushed through `blueprint_plan.analyze_delivery` and its arithmetic checked
against hand-derived expectations.
"""
from __future__ import annotations

from factoribot.blueprint_contract import (
    SCHEMA_VERSION, MECHANICS_PROFILE, EndpointId, content_hash, parse_request, to_dict,
)

BASE_MOD = {"name": "base", "version": "2.0.76", "provides": [], "alters_item_mechanics": False}


def item(name):
    return {"kind": "item", "name": name, "quality": "normal"}


def finite(value):
    return {"kind": "finite", "value": value}


def unlimited():
    return {"kind": "unlimited", "value": None}


def seal(body, key):
    body.pop(key, None)
    body[key] = content_hash(body)
    return body


def sink(service="SYNTHETIC declared external removal", capacity=None):
    return {"kind": "external", "service": service,
            "capacity": unlimited() if capacity is None else finite(capacity)}


def budget(bid, name, rate):
    return {"id": bid, "material": item(name), "capacity": finite(rate)}


def feed(fid, budget_id, endpoint: EndpointId, rate=None):
    return {"id": fid, "budget_id": budget_id, "endpoint": to_dict(endpoint),
            "capacity": unlimited() if rate is None else finite(rate)}


def export(xid, name, endpoint: EndpointId, rate=0.0, requirement="minimum", capacity=None):
    return {"id": xid, "material": item(name), "endpoint": to_dict(endpoint),
            "requirement": requirement, "rate": rate, "sink": sink(capacity=capacity)}


def surplus(sid, name, endpoint: EndpointId, capacity=None):
    return {"id": sid, "material": item(name), "endpoint": to_dict(endpoint),
            "sink": sink(capacity=capacity)}


def mods_for(graph, extra=()):
    """Declare exactly the mods the graph's entities claim, with their subsystems.

    The pinned extract carries no mod manifest, so unsupported prototypes claim
    mod `unknown`; declaring a mod literally named `unknown` is the honest audit
    line the task 03 handoff describes, not a guess at Editor Extensions.
    """
    provides = {}
    for entity in graph.entities:
        if entity.mod != "base":
            provides.setdefault(entity.mod, set()).add(entity.subsystem)
    declared = [BASE_MOD] + [
        {"name": name, "version": "unknown", "provides": sorted(subsystems),
         "alters_item_mechanics": False}
        for name, subsystems in sorted(provides.items())
    ]
    return declared + list(extra)


def irrelevance(graph, subsystem, basis, ident=None):
    return {
        "id": ident or f"declared_{subsystem}", "subsystem": subsystem, "entity_ids": [],
        "basis": basis,
        "justification": (
            f"SYNTHETIC: the request asserts that no {subsystem} entity exchanges items with this "
            "layout other than through declared feeds and outlets."
        ),
    }


def make_request(
    graph, *, budgets=(), feeds=(), exports=(), surplus_outlets=(), objective=None,
    control_policy="relax_open", controls=(), power="assumed_available", irrelevant=(),
    furnaces=(), extra_recipes=(),
):
    recipes = sorted({a.recipe for a in graph.activities} | set(extra_recipes))
    assignments = {
        "schema_version": SCHEMA_VERSION,
        "blueprint_hash": graph.blueprint_hash, "graph_hash": graph.graph_hash,
        "feeds": list(feeds), "furnaces": list(furnaces), "controls": list(controls),
    }
    body = {
        "schema_version": SCHEMA_VERSION, "mechanics_profile": MECHANICS_PROFILE,
        "blueprint_hash": graph.blueprint_hash, "prototype_hash": graph.prototype_hash,
        "graph_hash": graph.graph_hash,
        "budgets": list(budgets), "exports": list(exports), "surplus": list(surplus_outlets),
        "objective": objective or {"kind": "feasible", "export_id": None},
        "assignments": assignments,
        "protected": {"entities": [], "endpoints": [], "areas": [],
                      "preserve_wiring": True, "preserve_unknown": True, "preserve_boundaries": True},
        "assumptions": {
            "game_version": "2.0.76", "mods": mods_for(graph), "quality": "normal",
            "available_recipes": recipes, "research": [],
            "control_policy": control_policy, "power": power,
            "modules": "none", "beacons": "none", "irrelevant": list(irrelevant),
        },
        "detail": {"kind": "summary", "entity_ids": [], "cursor": None, "limit": 100},
    }
    return parse_request(seal(body, "request_hash"), graph)


def all_conditions(graph, enabled=True):
    """An `explicit` control assignment for every condition the graph names."""
    names = sorted({c for arc in graph.arcs for c in arc.conditions})
    if isinstance(enabled, dict):
        return [{"condition": n, "enabled": bool(enabled.get(n, False))} for n in names]
    return [{"condition": n, "enabled": bool(enabled)} for n in names]
