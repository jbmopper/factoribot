"""Decode Factorio blueprint strings and extract a solver-friendly model.

A blueprint string is a version byte (``'0'``) followed by base64 of zlib-
compressed JSON; Factorio 2.0 also imports raw JSON directly. The decoded blob
is either ``{"blueprint": {...}}`` or ``{"blueprint_book": {"blueprints": [...]}}``.

We decode, flatten books, and group the crafting machines by (machine, recipe,
modules) so the analyzer can reason about capacity per recipe *stage*. Geometry
(belt routing, beacon coverage by position) is intentionally ignored here -- this
is the aggregate/ratio view, not a wiring diagram.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import zlib
from collections import defaultdict
from dataclasses import dataclass, field

from .model import Database

# A blueprint export string is a version digit followed by a long base64 run.
_BP_RE = re.compile(r"[0-9][A-Za-z0-9+/=]{60,}")


class BlueprintError(ValueError):
    """The input could not be decoded as a blueprint string."""


def decode_blueprint_string(s: str) -> dict:
    """Decode a blueprint export string (or raw JSON) into its dict form."""
    s = (s or "").strip()
    # Tolerate a pasted markdown fence around the string.
    if s.startswith("```"):
        s = s.strip("`").strip()
    if not s:
        raise BlueprintError("empty blueprint string")
    if s[0] == "{":  # 2.0 accepts uncompressed JSON
        try:
            return json.loads(s)
        except json.JSONDecodeError as e:
            raise BlueprintError(f"looks like JSON but won't parse: {e}") from e
    body = s[1:]  # skip the version byte
    try:
        return json.loads(zlib.decompress(base64.b64decode(body)).decode("utf-8"))
    except (binascii.Error, zlib.error, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise BlueprintError(
            "not a valid blueprint string "
            "(expected a version byte followed by base64 of zlib-compressed JSON)"
        ) from e


def find_blueprint_string(text: str) -> str | None:
    """Pull a blueprint string out of free text (e.g. a pasted chat message).

    Returns the first long base64-ish run that actually decodes, so we can route
    a pasted blueprint to the analyzer without sending it through the LLM.
    """
    for m in _BP_RE.finditer(text or ""):
        cand = m.group(0)
        try:
            decode_blueprint_string(cand)
            return cand
        except BlueprintError:
            continue
    return None


def iter_blueprints(decoded: dict) -> list[dict]:
    """Flatten a decoded blob into the list of individual blueprint dicts.

    A blueprint book may nest books; entries look like ``{"index", "blueprint"}``
    or ``{"index", "blueprint_book"}``. Upgrade-planners/deconstruction-planners
    carry no entities and are skipped.
    """
    if not isinstance(decoded, dict):
        return []
    if "blueprint" in decoded:
        return [decoded["blueprint"]]
    book = decoded.get("blueprint_book")
    if book:
        out: list[dict] = []
        for entry in book.get("blueprints", []):
            out.extend(iter_blueprints(entry))
        return out
    if "entities" in decoded:  # already a bare blueprint
        return [decoded]
    return []


def _parse_modules(entity: dict) -> dict[str, int]:
    """Module name -> count for an entity, tolerating 1.x and 2.0 shapes.

    1.x: ``items = {"productivity-module-3": 2}``.
    2.0: ``items = [{"id": {"name", "quality"}, "items": {"in_inventory": [...]}}]``.
    We only sum counts by module name; quality and slot positions are ignored.
    """
    items = entity.get("items")
    if not items:
        return {}
    out: dict[str, int] = defaultdict(int)
    if isinstance(items, dict):  # 1.x
        for name, count in items.items():
            try:
                out[name] += int(count)
            except (TypeError, ValueError):
                out[name] += 1
    elif isinstance(items, list):  # 2.0
        for it in items:
            if not isinstance(it, dict):
                continue
            ident = it.get("id")
            name = ident.get("name") if isinstance(ident, dict) else ident
            if not name:
                continue
            inv = ((it.get("items") or {}).get("in_inventory")) or []
            n = sum(int(slot.get("count", 1)) for slot in inv) if inv else 1
            out[name] += n
    return dict(out)


@dataclass
class MachineGroup:
    """A run of identical crafting machines: same prototype, recipe, and modules."""

    machine: str  # entity prototype name, e.g. "assembling-machine-2"
    recipe: str | None  # recipe set on the machine, or None (e.g. furnaces)
    count: int
    modules: dict[str, int] = field(default_factory=dict)  # per-machine modules


@dataclass
class BlueprintSummary:
    """The aggregate, geometry-free view of one blueprint."""

    label: str | None
    groups: list[MachineGroup]  # crafting machines with a recipe set, grouped
    no_recipe: dict[str, int]  # crafting machine name -> count, recipe unset
    beacons: dict[str, int]  # beacon name -> count
    beacon_modules: dict[str, int]  # module name -> total count across beacons
    belts: dict[str, int]  # transport-belt name -> count
    other: dict[str, int]  # everything else (inserters, poles, modded, ...)
    total_entities: int


def summarize_blueprint(bp: dict, db: Database) -> BlueprintSummary:
    """Group a blueprint's entities into the analyzer's vocabulary using `db`."""
    ents = bp.get("entities") or []
    grouped: dict[tuple, int] = defaultdict(int)
    group_mods: dict[tuple, dict[str, int]] = {}
    no_recipe: dict[str, int] = defaultdict(int)
    beacons: dict[str, int] = defaultdict(int)
    beacon_modules: dict[str, int] = defaultdict(int)
    belts: dict[str, int] = defaultdict(int)
    other: dict[str, int] = defaultdict(int)

    for e in ents:
        name = e.get("name") if isinstance(e, dict) else None
        if not name:
            continue
        if name in db.machines:
            recipe = e.get("recipe")
            mods = _parse_modules(e)
            if recipe:
                key = (name, recipe, tuple(sorted(mods.items())))
                grouped[key] += 1
                group_mods[key] = mods
            else:
                no_recipe[name] += 1
        elif name in db.beacons:
            beacons[name] += 1
            for m, c in _parse_modules(e).items():
                beacon_modules[m] += c
        elif name in db.belts:
            belts[name] += 1
        else:
            other[name] += 1

    groups = [
        MachineGroup(machine=k[0], recipe=k[1], count=n, modules=dict(group_mods[k]))
        for k, n in sorted(grouped.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return BlueprintSummary(
        label=bp.get("label"),
        groups=groups,
        no_recipe=dict(no_recipe),
        beacons=dict(beacons),
        beacon_modules=dict(beacon_modules),
        belts=dict(belts),
        other=dict(other),
        total_entities=len(ents),
    )
