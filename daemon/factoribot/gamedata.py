"""Load and normalize Factorio's ``data-raw-dump.json`` into a Database.

Generate the dump with::

    factorio --dump-data

It lands in ``<write-data-path>/script-output/data-raw-dump.json`` and reflects
whatever mods are currently enabled.
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path

from .model import Database, Machine, Module, Recipe, Stack
from .units import parse_energy

# Recipe categories that aren't real production (editor tools, recipe params).
EXCLUDED_CATEGORIES = {"parameters", "ee-testing-tool"}
# Barreling recipes create spurious "producers" for every fluid; drop them.
_BARREL_RE = re.compile(r"^(empty|fill)-.*-barrel$")

# Prototype categories that can craft recipes.
CRAFTING_MACHINE_TYPES = ("assembling-machine", "furnace", "rocket-silo")


def _is_barreling(name: str) -> bool:
    return bool(_BARREL_RE.match(name))


def _expected_amount(entry: dict) -> float:
    """Expected output of a result entry, accounting for probability/ranges."""
    if "amount" in entry:
        amount = float(entry["amount"])
    elif "amount_min" in entry and "amount_max" in entry:
        amount = (float(entry["amount_min"]) + float(entry["amount_max"])) / 2.0
    else:
        amount = 0.0
    return amount * float(entry.get("probability", 1.0))


def _stacks_in(entries) -> list[Stack]:
    out = []
    for e in entries or []:
        out.append(Stack(name=e["name"], amount=float(e.get("amount", 0)), type=e.get("type", "item")))
    return out


def _stacks_out(entries) -> list[Stack]:
    out = []
    for e in entries or []:
        out.append(Stack(name=e["name"], amount=_expected_amount(e), type=e.get("type", "item")))
    return out


def build_database(raw: dict) -> Database:
    recipes: dict[str, Recipe] = {}
    producers: dict[str, list[str]] = defaultdict(list)

    for name, r in raw.get("recipe", {}).items():
        category = r.get("category", "crafting")
        if category in EXCLUDED_CATEGORIES or _is_barreling(name):
            continue
        results = _stacks_out(r.get("results"))
        recipe = Recipe(
            name=name,
            category=category,
            energy=float(r.get("energy_required", 0.5)),
            ingredients=_stacks_in(r.get("ingredients")),
            results=results,
            allow_productivity=bool(r.get("allow_productivity", False)),
        )
        recipes[name] = recipe
        for s in results:
            if s.amount > 0:
                producers[s.name].append(name)

    machines: dict[str, Machine] = {}
    for mtype in CRAFTING_MACHINE_TYPES:
        for name, m in raw.get(mtype, {}).items():
            cats = m.get("crafting_categories") or []
            if not cats:
                continue
            src = m.get("energy_source") or {}
            machines[name] = Machine(
                name=name,
                speed=float(m.get("crafting_speed", 1.0)),
                categories=frozenset(cats),
                energy_w=parse_energy(m.get("energy_usage")),
                module_slots=int(m.get("module_slots", 0)),
                allowed_effects=frozenset(m.get("allowed_effects") or []),
                source_type=src.get("type", "electric"),
            )

    modules: dict[str, Module] = {}
    for name, mod in raw.get("module", {}).items():
        modules[name] = Module(
            name=name,
            category=mod.get("category", ""),
            effect=dict(mod.get("effect") or {}),
        )

    items: dict[str, dict] = {}
    for itype, protos in raw.items():
        # Item-like prototypes share the item namespace; collect names for lookups.
        if not isinstance(protos, dict):
            continue
        for name, proto in protos.items():
            if isinstance(proto, dict) and proto.get("type") in (
                "item", "tool", "ammo", "capsule", "module", "gun",
                "item-with-entity-data", "rail-planner", "armor",
            ):
                items.setdefault(name, proto)

    fluids = set(raw.get("fluid", {}).keys())

    return Database(
        recipes=recipes,
        machines=machines,
        modules=modules,
        producers={k: v for k, v in producers.items()},
        items=items,
        fluids=fluids,
    )


def find_dump(explicit: str | None = None) -> str:
    """Locate ``data-raw-dump.json``.

    Order: explicit arg, ``$FACTORIBOT_DATA``, then walk up from CWD and from
    this package looking for ``data/data-raw-dump.json``.
    """
    if explicit:
        return explicit
    env = os.environ.get("FACTORIBOT_DATA")
    if env:
        return env
    seen = []
    for start in (Path.cwd(), Path(__file__).resolve()):
        for base in [start, *start.parents]:
            cand = base / "data" / "data-raw-dump.json"
            seen.append(cand)
            if cand.exists():
                return str(cand)
    raise FileNotFoundError(
        "Could not find data/data-raw-dump.json. Run `factorio --dump-data` and "
        "copy it into ./data/, or pass --data / set FACTORIBOT_DATA."
    )


def load_database(path: str | None = None) -> Database:
    with open(find_dump(path)) as f:
        raw = json.load(f)
    return build_database(raw)
