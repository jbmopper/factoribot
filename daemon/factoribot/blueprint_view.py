"""Self-contained local viewer for routing contract graphs, results and assignments.

`render_view` turns contract data (a graph, an optional analysis result and an
optional assignment set, in the wire form produced by
`blueprint_contract.to_dict`) into one standalone HTML document. The page uses
plain JavaScript with a single canvas: no framework, build step, network access
or CDN, and no DOM element per graph arc.

The page displays; it never analyses. Every number it shows is copied verbatim
from the supplied data and formatted here in Python, so no numerical finding is
derived in JavaScript. The page writes no files and runs no solver: it produces
an assignment JSON document for the host to act on.

Blueprint labels, descriptions, certificates and messages are untrusted imported
content. They are embedded as JSON with `<`, `>`, `&`, U+2028 and U+2029 escaped,
and the page renders every one of them through `textContent`, never as markup.

Fields are read defensively: unknown record keys are displayed generically rather
than dropped or treated as an error, so a later contract revision remains
inspectable. No schema version string is hardcoded.
"""
from __future__ import annotations

from dataclasses import is_dataclass
from importlib.resources import files
import html
import json
import math
import re
from typing import Any

from .blueprint_contract import canonical_json, to_dict

VIEW_VERSION = "factoribot-blueprint-view-1"
ASSET_PACKAGE = "blueprint_view_assets"
DOCUMENT_KIND = "factoribot.routing.assignment_draft"

_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
_RAW_DISPLAY_LIMIT = 2000

_DIRECTIONS = {0: "north", 4: "east", 8: "south", 12: "west"}

_KNOWN = {
    "graph": {
        "schema_version", "mechanics_profile", "provenance", "blueprint",
        "prototypes", "blueprint_hash", "prototype_hash", "graph_hash",
        "selected_paths", "entities", "ports", "lanes", "inventories",
        "capacity_groups", "arcs", "activities", "evidence", "topology_gaps",
    },
    "entity": {
        "id", "prototype", "position", "footprint", "direction", "orientation",
        "quality", "support", "subsystem", "mod", "furnace_candidates", "raw",
        "evidence_ids",
    },
    "port": {"id", "position", "direction", "role", "eligibility",
             "boundary_candidate", "evidence_ids"},
    "lane": {"id", "side", "incoming", "outgoing", "polyline", "eligibility",
             "evidence_ids"},
    "inventory": {"id", "position", "eligibility", "storage_capacity",
                  "evidence_ids"},
    "group": {"id", "kind", "unit", "capacity", "evidence_ids"},
    "arc": {"id", "source", "target", "eligibility", "semantics", "conditions",
            "resources", "evidence_ids"},
    "activity": {"id", "entity", "recipe", "inputs", "outputs", "craft_capacity",
                 "resources", "evidence_ids"},
    "evidence": {"id", "kind", "sources", "entity_ids", "endpoint_ids",
                 "arc_path", "description"},
    "gap": {"id", "entity_ids", "possible_endpoints", "may_connect", "reason",
            "evidence_ids"},
    "result": {"schema_version", "analyzer_version", "blueprint_hash",
               "prototype_hash", "graph_hash", "request_hash", "result_hash",
               "interpreted_request", "status", "findings", "bounds", "witness",
               "assumptions", "limitations", "detail"},
    "finding": {"id", "code", "severity", "evidence_kind", "message",
                "entity_ids", "endpoint_ids", "material", "required_rate",
                "capacity_upper_bound", "evidence_ids", "assumptions"},
    "bound": {"stage", "direction", "comparison_hash", "constraint_hash",
              "objective_export_id", "unit", "value", "solver_state",
              "certificate", "evidence_ids", "assumptions", "relaxations"},
    "request": {"schema_version", "mechanics_profile", "blueprint_hash",
                "prototype_hash", "graph_hash", "request_hash", "budgets",
                "exports", "surplus", "objective", "assignments", "protected",
                "assumptions", "detail"},
    "assumptions": {"game_version", "mods", "quality", "available_recipes",
                    "research", "control_policy", "power", "modules", "beacons",
                    "irrelevant"},
}

_STATUS_TEXT = {
    "partial": "Partial - missing assignments, evidence or topology; no global conclusion.",
    "insufficient": "Insufficient - a sound optimistic relaxation cannot satisfy every requested net export.",
    "feasible_relaxed": "Feasible (relaxed) - a continuous allocation exists in the relaxed model; no achieved-rate claim.",
    "solver_limit": "Solver limit - only independently certified upper bounds survive.",
    "invalid_request": "Invalid request - strict parsing or context checks failed; no numerical claim.",
}

_STAGE_TEXT = {
    "aggregate": "aggregate (delivery and budgets relaxed)",
    "budget": "budget (delivery relaxed)",
    "routing": "routing (supported transport included)",
}

_EVIDENCE_TEXT = {
    "structural": "structural - derived from static layout, not runtime behaviour",
    "upper_bound": "upper bound - a ceiling under the stated relaxations",
    "estimated": "estimated - approximate, not a certified bound",
    "conditional": "conditional - holds only under the named conditions",
    "observed": "observed - recorded from a running game",
}


# --------------------------------------------------------------------------
# defensive readers
# --------------------------------------------------------------------------

def _plain(value: Any) -> Any:
    """Contract records or already-plain wire data as JSON-compatible data."""
    if is_dataclass(value) and not isinstance(value, type):
        return to_dict(value)
    if isinstance(value, (dict, list, tuple)):
        return to_dict(value)
    return value


def _obj(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _seq(value: Any) -> list:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _num(value: Any) -> str:
    """Contract decimal spelling for a number; never a recomputation."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _generic(value)
    try:
        return canonical_json(value)
    except Exception:
        return repr(value)


def _generic(value: Any) -> str:
    """Display text for a value of unexpected shape (later schema revisions)."""
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return _num(value)
    try:
        return json.dumps(_plain(value), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return repr(value)


def _float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _extra(record: Any, known: str) -> dict:
    record = _obj(record)
    names = _KNOWN.get(known, set())
    return {key: _generic(record[key]) for key in sorted(record) if key not in names}


def _short(digest_text: Any) -> str:
    text = _str(digest_text)
    if text.startswith("sha256:") and len(text) > 19:
        return text[:19] + "…"
    return text or "—"


# --------------------------------------------------------------------------
# identity keys (display and index only; exports reuse the original objects)
# --------------------------------------------------------------------------

def entity_key(ident: Any) -> str:
    ident = _obj(ident)
    path = _seq(ident.get("book_path"))
    parts = [str(p) for p in path if isinstance(p, int) and not isinstance(p, bool)]
    number = ident.get("entity_number")
    clean = len(parts) == len(path) and isinstance(number, int) and not isinstance(number, bool)
    key = "bp/" + ("/".join(parts) or "root") + "/e/" + (str(number) if clean else "?")
    return key if clean else key + "#" + _generic(ident)


def endpoint_key(ident: Any) -> str:
    ident = _obj(ident)
    kind, name = ident.get("kind"), ident.get("name")
    clean = isinstance(kind, str) and isinstance(name, str)
    key = entity_key(ident.get("entity")) + "/" + (kind if isinstance(kind, str) else "?") \
        + "/" + (name if isinstance(name, str) else "?")
    return key if clean else key + "#" + _generic(ident)


def _material_text(material: Any) -> str:
    if material is None:
        return "—"
    material = _obj(material)
    if not material:
        return _generic(material)
    name = _str(material.get("name"), _generic(material.get("name")))
    kind = _str(material.get("kind"))
    quality = material.get("quality")
    text = name
    if kind and kind != "item":
        text += " (" + kind + ")"
    if isinstance(quality, str) and quality != "normal":
        text += " [" + quality + "]"
    return text


def _mod_text(mod: Any) -> str:
    mod = _obj(mod)
    text = _generic(mod.get("name")) + " " + _generic(mod.get("version"))
    provides = [_generic(p) for p in _seq(mod.get("provides"))]
    if provides:
        text += " provides " + "/".join(provides)
    if "alters_item_mechanics" in mod:
        text += (" - alters item mechanics" if mod.get("alters_item_mechanics")
                 else " - declared not to alter item mechanics")
    return text


def _eligibility_text(eligibility: Any) -> str:
    eligibility = _obj(eligibility)
    kind = _str(eligibility.get("kind"))
    materials = [_material_text(m) for m in _seq(eligibility.get("materials"))]
    if kind == "any_item":
        return "any item"
    if kind == "only":
        return "only: " + (", ".join(materials) if materials else "nothing permitted")
    return _generic(eligibility)


def _capacity_text(capacity: Any, unit: str = "") -> str:
    capacity = _obj(capacity)
    kind = _str(capacity.get("kind"))
    suffix = (" " + unit) if unit else ""
    if kind == "finite":
        return _num(capacity.get("value")) + suffix
    if kind == "unlimited":
        return "unlimited"
    if kind == "unknown":
        return "unknown"
    return _generic(capacity) if capacity else "—"


def _rate_text(value: Any, unit: str = "items/s") -> str | None:
    if value is None:
        return None
    return _num(value) + ((" " + unit) if unit else "")


def _direction_text(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return _DIRECTIONS.get(value, str(value) + "/16 clockwise")
    return _generic(value)


# --------------------------------------------------------------------------
# view model
# --------------------------------------------------------------------------

def _entities_model(graph: dict) -> tuple[list, dict]:
    entities, index = [], {}
    for record in _seq(graph.get("entities")):
        record = _obj(record)
        ident = _obj(record.get("id"))
        key = entity_key(ident)
        position = _obj(record.get("position"))
        box = _obj(record.get("footprint"))
        minimum, maximum = _obj(box.get("minimum")), _obj(box.get("maximum"))
        x, y = _float(position.get("x")), _float(position.get("y"))
        raw = _obj(record.get("raw")).get("canonical")
        raw_text = _str(raw, _generic(record.get("raw")))
        truncated = len(raw_text) > _RAW_DISPLAY_LIMIT
        item = {
            "key": key,
            "id": ident,
            "prototype": _str(record.get("prototype"), _generic(record.get("prototype"))),
            "position": [x, y],
            "position_text": _num(position.get("x")) + ", " + _num(position.get("y")),
            "box": [
                _float(minimum.get("x"), x - 0.5), _float(minimum.get("y"), y - 0.5),
                _float(maximum.get("x"), x + 0.5), _float(maximum.get("y"), y + 0.5),
            ],
            "direction_text": _direction_text(record.get("direction")),
            "orientation_text": _generic(record.get("orientation")),
            "quality": _str(record.get("quality"), _generic(record.get("quality"))),
            "support": _str(record.get("support"), _generic(record.get("support"))),
            "subsystem": (_generic(record.get("subsystem")) if "subsystem" in record else None),
            "mod": (_generic(record.get("mod")) if "mod" in record else None),
            "furnace_candidates": [_generic(c) for c in _seq(record.get("furnace_candidates"))],
            "evidence_ids": [_generic(e) for e in _seq(record.get("evidence_ids"))],
            "raw_text": raw_text[:_RAW_DISPLAY_LIMIT] + ("… (truncated for display)" if truncated else ""),
            "extra": _extra(record, "entity"),
            "ports": [], "lanes": [], "inventories": [], "arcs": [], "activities": [],
        }
        index[key] = item
        entities.append(item)
    return entities, index


def _endpoints_model(graph: dict, entities: dict) -> tuple[list, list, list, dict]:
    ports, lanes, inventories, index = [], [], [], {}

    def attach(owner_key: str, bucket: str, key: str) -> None:
        owner = entities.get(owner_key)
        if owner is not None:
            owner[bucket].append(key)

    for record in _seq(graph.get("ports")):
        record = _obj(record)
        ident = _obj(record.get("id"))
        key = endpoint_key(ident)
        position = _obj(record.get("position"))
        item = {
            "key": key, "id": ident, "kind": "port",
            "entity_key": entity_key(ident.get("entity")),
            "name": _generic(ident.get("name")),
            "anchor": [_float(position.get("x")), _float(position.get("y"))],
            "position_text": _num(position.get("x")) + ", " + _num(position.get("y")),
            "role": _str(record.get("role"), _generic(record.get("role"))),
            "direction_text": _direction_text(record.get("direction")),
            "eligibility_text": _eligibility_text(record.get("eligibility")),
            "boundary_candidate": bool(record.get("boundary_candidate")),
            "evidence_ids": [_generic(e) for e in _seq(record.get("evidence_ids"))],
            "extra": _extra(record, "port"),
        }
        index[key] = item
        ports.append(item)
        attach(item["entity_key"], "ports", key)

    for record in _seq(graph.get("lanes")):
        record = _obj(record)
        ident = _obj(record.get("id"))
        key = endpoint_key(ident)
        polyline = [[_float(_obj(p).get("x")), _float(_obj(p).get("y"))]
                    for p in _seq(record.get("polyline"))]
        anchor = polyline[len(polyline) // 2] if polyline else [0.0, 0.0]
        item = {
            "key": key, "id": ident, "kind": "lane",
            "entity_key": entity_key(ident.get("entity")),
            "name": _generic(ident.get("name")),
            "side": _str(record.get("side"), _generic(record.get("side"))),
            "incoming_key": endpoint_key(record.get("incoming")),
            "outgoing_key": endpoint_key(record.get("outgoing")),
            "polyline": polyline,
            "anchor": anchor,
            "eligibility_text": _eligibility_text(record.get("eligibility")),
            "evidence_ids": [_generic(e) for e in _seq(record.get("evidence_ids"))],
            "extra": _extra(record, "lane"),
        }
        index[key] = item
        lanes.append(item)
        attach(item["entity_key"], "lanes", key)

    for record in _seq(graph.get("inventories")):
        record = _obj(record)
        ident = _obj(record.get("id"))
        key = endpoint_key(ident)
        position = _obj(record.get("position"))
        item = {
            "key": key, "id": ident, "kind": "inventory",
            "entity_key": entity_key(ident.get("entity")),
            "name": _generic(ident.get("name")),
            "anchor": [_float(position.get("x")), _float(position.get("y"))],
            "position_text": _num(position.get("x")) + ", " + _num(position.get("y")),
            "eligibility_text": _eligibility_text(record.get("eligibility")),
            "storage_text": _capacity_text(record.get("storage_capacity"), "items"),
            "evidence_ids": [_generic(e) for e in _seq(record.get("evidence_ids"))],
            "extra": _extra(record, "inventory"),
        }
        index[key] = item
        inventories.append(item)
        attach(item["entity_key"], "inventories", key)
    return ports, lanes, inventories, index


def _resolve_anchor(key: str, endpoints: dict, role: str) -> list:
    """Lane references resolve to their outgoing (source) / incoming (target) port."""
    endpoint = endpoints.get(key)
    if endpoint is None:
        return [0.0, 0.0]
    if endpoint.get("kind") == "lane":
        target = endpoint.get("outgoing_key") if role == "source" else endpoint.get("incoming_key")
        port = endpoints.get(target)
        if port is not None:
            return list(port.get("anchor", [0.0, 0.0]))
    return list(endpoint.get("anchor", [0.0, 0.0]))


def _arcs_model(graph: dict, endpoints: dict, entities: dict) -> tuple[list, dict]:
    arcs, index = [], {}
    for record in _seq(graph.get("arcs")):
        record = _obj(record)
        arc_id = _generic(record.get("id"))
        source_key, target_key = endpoint_key(record.get("source")), endpoint_key(record.get("target"))
        start, end = _resolve_anchor(source_key, endpoints, "source"), _resolve_anchor(target_key, endpoints, "target")
        item = {
            "id": arc_id,
            "source_key": source_key, "target_key": target_key,
            "geometry": [start[0], start[1], end[0], end[1]],
            "semantics": _str(record.get("semantics"), _generic(record.get("semantics"))),
            "conditions": [_generic(c) for c in _seq(record.get("conditions"))],
            "eligibility_text": _eligibility_text(record.get("eligibility")),
            "resources": [
                {"group_id": _generic(_obj(r).get("group_id")),
                 "coefficient_text": _num(_obj(r).get("coefficient"))}
                for r in _seq(record.get("resources"))
            ],
            "evidence_ids": [_generic(e) for e in _seq(record.get("evidence_ids"))],
            "extra": _extra(record, "arc"),
        }
        index[arc_id] = item
        arcs.append(item)
        for key in (source_key, target_key):
            endpoint = endpoints.get(key)
            owner = entities.get(endpoint["entity_key"]) if endpoint else None
            if owner is not None and arc_id not in owner["arcs"]:
                owner["arcs"].append(arc_id)
    return arcs, index


def _activities_model(graph: dict, entities: dict) -> list:
    activities = []
    for record in _seq(graph.get("activities")):
        record = _obj(record)
        owner_key = entity_key(record.get("entity"))

        def parts(name: str) -> list:
            return [{
                "endpoint_key": endpoint_key(_obj(p).get("endpoint")),
                "material_text": _material_text(_obj(p).get("material")),
                "amount_text": _num(_obj(p).get("amount_per_craft")),
            } for p in _seq(record.get(name))]

        item = {
            "id": _generic(record.get("id")),
            "entity_key": owner_key,
            "recipe": _generic(record.get("recipe")),
            "inputs": parts("inputs"),
            "outputs": parts("outputs"),
            "craft_capacity_text": _capacity_text(record.get("craft_capacity"), "crafts/s"),
            "resources": [
                {"group_id": _generic(_obj(r).get("group_id")),
                 "coefficient_text": _num(_obj(r).get("coefficient"))}
                for r in _seq(record.get("resources"))
            ],
            "evidence_ids": [_generic(e) for e in _seq(record.get("evidence_ids"))],
            "extra": _extra(record, "activity"),
        }
        activities.append(item)
        owner = entities.get(owner_key)
        if owner is not None:
            owner["activities"].append(item["id"])
    return activities


def _evidence_model(graph: dict) -> tuple[list, dict]:
    evidence, index = [], {}
    for record in _seq(graph.get("evidence")):
        record = _obj(record)
        item = {
            "id": _generic(record.get("id")),
            "kind": _str(record.get("kind"), _generic(record.get("kind"))),
            "kind_text": _EVIDENCE_TEXT.get(_str(record.get("kind")), _generic(record.get("kind"))),
            "description": _generic(record.get("description")),
            "sources": [
                {"source": _generic(_obj(s).get("source")), "uri": _generic(_obj(s).get("uri")),
                 "pointer": _generic(_obj(s).get("pointer"))}
                for s in _seq(record.get("sources"))
            ],
            "entity_keys": [entity_key(e) for e in _seq(record.get("entity_ids"))],
            "endpoint_keys": [endpoint_key(e) for e in _seq(record.get("endpoint_ids"))],
            "arc_path": [_generic(a) for a in _seq(record.get("arc_path"))],
            "extra": _extra(record, "evidence"),
        }
        index[item["id"]] = item
        evidence.append(item)
    return evidence, index


def _focus_box(entity_keys, endpoint_keys, arc_ids, entities, endpoints, arcs):
    xs, ys = [], []
    for key in entity_keys:
        item = entities.get(key)
        if item:
            xs += [item["box"][0], item["box"][2]]
            ys += [item["box"][1], item["box"][3]]
    for key in endpoint_keys:
        item = endpoints.get(key)
        if item:
            points = item.get("polyline") or [item.get("anchor", [0.0, 0.0])]
            xs += [p[0] for p in points]
            ys += [p[1] for p in points]
    for arc_id in arc_ids:
        item = arcs.get(arc_id)
        if item:
            xs += [item["geometry"][0], item["geometry"][2]]
            ys += [item["geometry"][1], item["geometry"][3]]
    if not xs or not ys:
        return None
    return [min(xs), min(ys), max(xs), max(ys)]


def _findings_model(result: dict, evidence: dict, entities: dict, endpoints: dict, arcs: dict) -> list:
    findings = []
    for record in _seq(result.get("findings")):
        record = _obj(record)
        entity_keys = [entity_key(e) for e in _seq(record.get("entity_ids"))]
        endpoint_keys = [endpoint_key(e) for e in _seq(record.get("endpoint_ids"))]
        evidence_ids = [_generic(e) for e in _seq(record.get("evidence_ids"))]
        arc_ids, extra_entities, extra_endpoints = [], [], []
        for eid in evidence_ids:
            item = evidence.get(eid)
            if item is None:
                continue
            arc_ids += [a for a in item["arc_path"] if a not in arc_ids]
            extra_entities += [k for k in item["entity_keys"] if k not in entity_keys + extra_entities]
            extra_endpoints += [k for k in item["endpoint_keys"] if k not in endpoint_keys + extra_endpoints]
        highlight_entities = entity_keys + extra_entities
        highlight_endpoints = endpoint_keys + extra_endpoints
        severity = _str(record.get("severity"), _generic(record.get("severity")))
        kind = _str(record.get("evidence_kind"), _generic(record.get("evidence_kind")))
        material = record.get("material")
        findings.append({
            "id": _generic(record.get("id")),
            "code": _generic(record.get("code")),
            "severity": severity,
            "evidence_kind": kind,
            "evidence_kind_text": _EVIDENCE_TEXT.get(kind, kind),
            "message": _generic(record.get("message")),
            "entity_keys": entity_keys,
            "endpoint_keys": endpoint_keys,
            "evidence_ids": evidence_ids,
            "material_text": _material_text(material) if material is not None else None,
            "required_rate_text": _rate_text(record.get("required_rate")),
            "capacity_upper_bound_text": _rate_text(record.get("capacity_upper_bound")),
            "assumptions": [_generic(a) for a in _seq(record.get("assumptions"))],
            "runtime_note": ("Recorded live observation."
                             if kind == "observed" else
                             "Static evidence: no claim about what this machine is doing right now."),
            "highlight": {
                "entities": highlight_entities,
                "endpoints": highlight_endpoints,
                "arcs": arc_ids,
            },
            "focus": _focus_box(highlight_entities, highlight_endpoints, arc_ids, entities, endpoints, arcs),
            "extra": _extra(record, "finding"),
        })
    return findings


def _bounds_model(result: dict) -> list:
    bounds = []
    for record in _seq(result.get("bounds")):
        record = _obj(record)
        stage = _str(record.get("stage"), _generic(record.get("stage")))
        unit = _str(record.get("unit"))
        value = record.get("value")
        bounds.append({
            "stage": stage,
            "stage_text": _STAGE_TEXT.get(stage, stage),
            "direction": _str(record.get("direction"), _generic(record.get("direction"))),
            "value_text": ("no value (infeasible)" if value is None else _capacity_text(value, unit)),
            "unit": unit,
            "solver_state": _str(record.get("solver_state"), _generic(record.get("solver_state"))),
            "objective_export_id": _generic(record.get("objective_export_id")),
            "certificate": _generic(record.get("certificate")),
            "relaxations": [_generic(r) for r in _seq(record.get("relaxations"))],
            "assumptions": [_generic(a) for a in _seq(record.get("assumptions"))],
            "evidence_ids": [_generic(e) for e in _seq(record.get("evidence_ids"))],
            "comparison_hash": _generic(record.get("comparison_hash")),
            "constraint_hash": _generic(record.get("constraint_hash")),
            "extra": _extra(record, "bound"),
        })
    return bounds


def _request_model(request: Any) -> dict | None:
    request = _obj(request)
    if not request:
        return None
    assumptions = _obj(request.get("assumptions"))
    objective = _obj(request.get("objective"))
    protected = _obj(request.get("protected"))
    kind = _generic(objective.get("kind"))
    export_id = objective.get("export_id")
    return {
        "objective_text": kind + ((": " + _generic(export_id)) if export_id is not None else ""),
        "objective": {"kind": _generic(objective.get("kind")),
                      "export_id": (None if export_id is None else _generic(export_id))},
        "budgets": [{
            "id": _generic(_obj(b).get("id")),
            "material": _obj(_obj(b).get("material")),
            "material_text": _material_text(_obj(b).get("material")),
            "capacity": _obj(_obj(b).get("capacity")),
            "capacity_text": _capacity_text(_obj(b).get("capacity"), "items/s"),
        } for b in _seq(request.get("budgets"))],
        "exports": [{
            "id": _generic(_obj(x).get("id")),
            "material_text": _material_text(_obj(x).get("material")),
            "endpoint_key": endpoint_key(_obj(x).get("endpoint")),
            "requirement": _generic(_obj(x).get("requirement")),
            "rate_text": _num(_obj(x).get("rate")) + " items/s",
            "sink_service": _generic(_obj(_obj(x).get("sink")).get("service")),
            "sink_capacity_text": _capacity_text(_obj(_obj(x).get("sink")).get("capacity"), "items/s"),
            "record": _obj(x),
        } for x in _seq(request.get("exports"))],
        "surplus": [{
            "id": _generic(_obj(x).get("id")),
            "material_text": _material_text(_obj(x).get("material")),
            "endpoint_key": endpoint_key(_obj(x).get("endpoint")),
            "sink_service": _generic(_obj(_obj(x).get("sink")).get("service")),
            "sink_capacity_text": _capacity_text(_obj(_obj(x).get("sink")).get("capacity"), "items/s"),
            "record": _obj(x),
        } for x in _seq(request.get("surplus"))],
        "assumptions": {
            "rows": [
                ["game version", _generic(assumptions.get("game_version"))],
                ["declared mods", "; ".join(_mod_text(m) for m in _seq(assumptions.get("mods"))) or "—"],
                ["quality", _generic(assumptions.get("quality"))],
                ["control policy", _generic(assumptions.get("control_policy"))],
                ["power", _generic(assumptions.get("power"))],
                ["modules", _generic(assumptions.get("modules"))],
                ["beacons", _generic(assumptions.get("beacons"))],
                ["available recipes", ", ".join(_generic(r) for r in _seq(assumptions.get("available_recipes"))) or "none listed"],
                ["research levels", ", ".join(_generic(_obj(r).get("name")) + "=" + _generic(_obj(r).get("level"))
                                              for r in _seq(assumptions.get("research"))) or "none listed (unlisted levels are unknown, not zero)"],
            ],
            "irrelevant": [{
                "id": _generic(_obj(d).get("id")),
                "subsystem": _generic(_obj(d).get("subsystem")),
                "basis": _generic(_obj(d).get("basis")),
                "justification": _generic(_obj(d).get("justification")),
                "entity_keys": [entity_key(e) for e in _seq(_obj(d).get("entity_ids"))],
            } for d in _seq(assumptions.get("irrelevant"))],
            "extra": _extra(assumptions, "assumptions"),
        },
        "protected": {
            "entities": [entity_key(e) for e in _seq(protected.get("entities"))],
            "endpoints": [endpoint_key(e) for e in _seq(protected.get("endpoints"))],
            "areas": len(_seq(protected.get("areas"))),
            "flags": [k + "=" + _generic(protected.get(k))
                      for k in ("preserve_wiring", "preserve_unknown", "preserve_boundaries")
                      if k in protected],
        },
        "hashes": {
            "blueprint": _generic(request.get("blueprint_hash")),
            "prototype": _generic(request.get("prototype_hash")),
            "graph": _generic(request.get("graph_hash")),
            "request": _generic(request.get("request_hash")),
        },
        "extra": _extra(request, "request"),
    }


def _assignment_state(document: Any, graph: dict) -> dict:
    document = _obj(document)
    feeds = []
    for record in _seq(document.get("feeds")):
        record = _obj(record)
        feeds.append({
            "id": _generic(record.get("id")),
            "budget_id": _generic(record.get("budget_id")),
            "endpoint": _obj(record.get("endpoint")),
            "endpoint_key": endpoint_key(record.get("endpoint")),
            "capacity": _obj(record.get("capacity")),
            "capacity_text": _capacity_text(record.get("capacity"), "items/s"),
        })
    furnaces = []
    for record in _seq(document.get("furnaces")):
        record = _obj(record)
        furnaces.append({
            "entity": _obj(record.get("entity")),
            "entity_key": entity_key(record.get("entity")),
            "recipe": _generic(record.get("recipe")),
        })
    controls = [{"condition": _generic(_obj(c).get("condition")),
                 "enabled": bool(_obj(c).get("enabled"))}
                for c in _seq(document.get("controls"))]
    return {
        "schema_version": document.get("schema_version", graph.get("schema_version")),
        "blueprint_hash": _generic(document.get("blueprint_hash", graph.get("blueprint_hash"))),
        "graph_hash": _generic(document.get("graph_hash", graph.get("graph_hash"))),
        "feeds": feeds, "furnaces": furnaces, "controls": controls,
        "document": document,
        "canonical": _canonical_or_none(document),
    }


def _canonical_or_none(document: Any) -> str | None:
    try:
        return canonical_json(document)
    except Exception:
        return None


def build_view_model(graph: Any, result: Any = None, assignments: Any = None,
                     *, title: str | None = None) -> dict:
    """Display model: every rendered number is formatted here, never in the page."""
    graph = _obj(_plain(graph))
    result = _obj(_plain(result)) if result is not None else {}
    supplied = _plain(assignments) if assignments is not None else None

    entity_list, entity_index = _entities_model(graph)
    ports, lanes, inventories, endpoint_index = _endpoints_model(graph, entity_index)
    arc_list, arc_index = _arcs_model(graph, endpoint_index, entity_index)
    activities = _activities_model(graph, entity_index)
    evidence_list, evidence_index = _evidence_model(graph)

    request = _request_model(result.get("interpreted_request"))
    analyzed = _obj(result.get("interpreted_request")).get("assignments")
    seed = supplied if supplied is not None else analyzed
    conditions: list[str] = []
    for arc in arc_list:
        for condition in arc["conditions"]:
            if condition not in conditions:
                conditions.append(condition)

    xs = [c for e in entity_list for c in (e["box"][0], e["box"][2])]
    ys = [c for e in entity_list for c in (e["box"][1], e["box"][3])]
    bounds_box = [min(xs), min(ys), max(xs), max(ys)] if xs and ys else [-1.0, -1.0, 1.0, 1.0]

    status = _str(result.get("status"))
    model = {
        "view_version": VIEW_VERSION,
        "document_kind": DOCUMENT_KIND,
        "title": title or "Routing audit map",
        "graph": {
            "schema_version": _generic(graph.get("schema_version")),
            "mechanics_profile": _generic(graph.get("mechanics_profile")),
            "provenance": _generic(graph.get("provenance")),
            "blueprint_hash": _generic(graph.get("blueprint_hash")),
            "prototype_hash": _generic(graph.get("prototype_hash")),
            "graph_hash": _generic(graph.get("graph_hash")),
            "blueprint_hash_short": _short(graph.get("blueprint_hash")),
            "graph_hash_short": _short(graph.get("graph_hash")),
            "selected_paths": ["[" + ", ".join(_generic(i) for i in _seq(p)) + "]"
                               for p in _seq(graph.get("selected_paths"))],
            "bounds_box": bounds_box,
            "entities": entity_list,
            "ports": ports, "lanes": lanes, "inventories": inventories,
            "arcs": arc_list,
            "capacity_groups": [{
                "id": _generic(_obj(g).get("id")),
                "kind": _generic(_obj(g).get("kind")),
                "unit": _generic(_obj(g).get("unit")),
                "capacity_text": _capacity_text(_obj(g).get("capacity"), _str(_obj(g).get("unit"))),
                "evidence_ids": [_generic(e) for e in _seq(_obj(g).get("evidence_ids"))],
                "extra": _extra(g, "group"),
            } for g in _seq(graph.get("capacity_groups"))],
            "activities": activities,
            "evidence": evidence_list,
            "topology_gaps": [{
                "id": _generic(_obj(g).get("id")),
                "reason": _generic(_obj(g).get("reason")),
                "may_connect": bool(_obj(g).get("may_connect")),
                "entity_keys": [entity_key(e) for e in _seq(_obj(g).get("entity_ids"))],
                "endpoint_keys": [endpoint_key(e) for e in _seq(_obj(g).get("possible_endpoints"))],
                "evidence_ids": [_generic(e) for e in _seq(_obj(g).get("evidence_ids"))],
                "extra": _extra(g, "gap"),
            } for g in _seq(graph.get("topology_gaps"))],
            "conditions": conditions,
            "counts": {
                "entities": len(entity_list), "ports": len(ports), "lanes": len(lanes),
                "inventories": len(inventories), "arcs": len(arc_list),
                "activities": len(activities),
                "capacity_groups": len(_seq(graph.get("capacity_groups"))),
                "evidence": len(evidence_list),
                "topology_gaps": len(_seq(graph.get("topology_gaps"))),
                "unsupported_entities": sum(1 for e in entity_list if e["support"] != "supported"),
            },
            "extra": _extra(graph, "graph"),
        },
        "result": None,
        "assignments": _assignment_state(seed, graph),
        "analyzed_assignments": (_assignment_state(analyzed, graph) if analyzed is not None else None),
        "assignments_source": ("supplied to the renderer" if supplied is not None
                               else ("the analysed request" if analyzed is not None else "empty (none supplied)")),
        "notes": [
            "This page displays contract data. It performs no analysis, no solving and writes no files.",
            "Imported labels, descriptions, certificates and messages are shown as inert text.",
            "Upper bounds hold only under their stated relaxations; they are never achievable rates.",
        ],
    }
    if result:
        model["result"] = {
            "status": status,
            "status_text": _STATUS_TEXT.get(status, _generic(result.get("status"))),
            "analyzer_version": _generic(result.get("analyzer_version")),
            "schema_version": _generic(result.get("schema_version")),
            "blueprint_hash": _generic(result.get("blueprint_hash")),
            "graph_hash": _generic(result.get("graph_hash")),
            "request_hash": _generic(result.get("request_hash")),
            "result_hash": _generic(result.get("result_hash")),
            "findings": _findings_model(result, evidence_index, entity_index, endpoint_index, arc_index),
            "bounds": _bounds_model(result),
            "assumptions": [_generic(a) for a in _seq(result.get("assumptions"))],
            "limitations": [_generic(a) for a in _seq(result.get("limitations"))],
            "witness_present": result.get("witness") is not None,
            "witness_validation": _generic(_obj(result.get("witness")).get("validation")) if result.get("witness") else None,
            "detail_kind": _generic(_obj(result.get("detail")).get("kind")),
            "request": request,
            "graph_match": (result.get("graph_hash") == graph.get("graph_hash")
                            and result.get("blueprint_hash") == graph.get("blueprint_hash")),
            "extra": _extra(result, "result"),
        }
    return model


# --------------------------------------------------------------------------
# HTML assembly
# --------------------------------------------------------------------------

def embed_json(value: Any) -> str:
    """JSON text safe inside a `<script type="application/json">` element."""
    text = json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), sort_keys=True)
    for character, escape in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                              (" ", "\\u2028"), (" ", "\\u2029")):
        text = text.replace(character, escape)
    return text


def _asset(name: str) -> str:
    return files(__package__).joinpath(ASSET_PACKAGE, name).read_text(encoding="utf-8")


def render_model(model: dict) -> str:
    css, script = _asset("view.css"), _asset("view.js")
    for text, closer in ((css, "</style"), (script, "</script")):
        if closer in text.lower():
            raise ValueError("viewer asset contains a closing tag sequence")
    values = {
        "TITLE": html.escape(str(model.get("title", "Routing audit map")), quote=True),
        "CSS": css,
        "JS": script,
        "DATA": embed_json(model),
        "VIEW_VERSION": html.escape(VIEW_VERSION, quote=True),
    }
    template = _asset("view.html")
    return _PLACEHOLDER.sub(lambda match: values.get(match.group(1), match.group(0)), template)


def render_view(graph: Any, result: Any = None, assignments: Any = None,
                *, title: str | None = None) -> str:
    """Return a standalone HTML document for this graph/result/assignment set."""
    return render_model(build_view_model(graph, result, assignments, title=title))


def render_bundle(bundle: Any, *, title: str | None = None) -> str:
    """Render a fixture-style bundle carrying `graph`, `result` and `assignments`."""
    bundle = _obj(_plain(bundle))
    return render_view(bundle.get("graph"), bundle.get("result"),
                       bundle.get("assignments"), title=title)


# --------------------------------------------------------------------------
# assignment documents produced by the page
# --------------------------------------------------------------------------

def assignment_set_from_document(document: Any) -> dict:
    """The `AssignmentSet` inside a page export, whether bare or in a draft envelope."""
    document = _obj(_plain(document))
    inner = document.get("assignments")
    if isinstance(inner, dict) and "feeds" in inner and "feeds" not in document:
        return inner
    if isinstance(inner, dict) and document.get("document_kind") == DOCUMENT_KIND:
        return inner
    return document


def check_assignment_document(document: Any, graph: Any) -> dict:
    """Report stale hashes and unresolved identities without raising.

    Mirrors the page's import check. `parse_assignments` remains the authority;
    this reports every problem instead of the first one.
    """
    graph = _obj(_plain(graph))
    assignments = assignment_set_from_document(document)
    stale: list[str] = []
    unknown: list[str] = []
    if not isinstance(assignments, dict) or "feeds" not in assignments:
        return {"assignments": None, "stale": [], "unknown": ["document is not an assignment set"], "ok": False}
    for field, label in (("blueprint_hash", "blueprint"), ("graph_hash", "graph")):
        expected, found = graph.get(field), assignments.get(field)
        if found != expected:
            stale.append("stale " + label + " hash: document has " + _short(found)
                         + ", this graph has " + _short(expected))
    entities = {entity_key(_obj(e).get("id")): _obj(e) for e in _seq(graph.get("entities"))}
    endpoints = {}
    for name in ("ports", "lanes", "inventories"):
        for record in _seq(graph.get(name)):
            endpoints[endpoint_key(_obj(record).get("id"))] = (name, _obj(record))
    conditions = {c for arc in _seq(graph.get("arcs")) for c in _seq(_obj(arc).get("conditions"))}
    for feed in _seq(assignments.get("feeds")):
        key = endpoint_key(_obj(feed).get("endpoint"))
        if key not in endpoints:
            unknown.append("unknown feed endpoint: " + key)
            continue
        name, record = endpoints[key]
        if name == "ports" and record.get("role") == "outgoing":
            unknown.append("feed targets an outgoing port: " + key)
    for furnace in _seq(assignments.get("furnaces")):
        key = entity_key(_obj(furnace).get("entity"))
        recipe = _obj(furnace).get("recipe")
        if key not in entities:
            unknown.append("unknown furnace entity: " + key)
        elif recipe not in _seq(entities[key].get("furnace_candidates")):
            unknown.append("recipe " + _generic(recipe) + " is not a recorded candidate of " + key)
    for control in _seq(assignments.get("controls")):
        condition = _obj(control).get("condition")
        if condition not in conditions:
            unknown.append("unknown control condition: " + _generic(condition))
    return {"assignments": assignments, "stale": stale, "unknown": unknown,
            "ok": not stale and not unknown}
