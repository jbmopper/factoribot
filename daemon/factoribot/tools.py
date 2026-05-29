"""Tools the LLM can call.

These ground the model in the *actual* loaded game data and run the
deterministic solver. The model handles the fuzzy/natural-language parts
(aliases like "purple science", choosing machines/modules); the tools handle
ground truth and exact math.

Tool schemas are provider-neutral ({name, description, parameters}); the LLM
adapters translate them to each provider's function-calling format.
"""
from __future__ import annotations

import difflib
import math
from collections import defaultdict

from . import report
from .model import Database, Recipe
from .solver import AmbiguousRecipe, SolverError, UnknownName, solve
from .spec import SolveSpec

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "search_items",
        "description": (
            "Find exact internal item/fluid/recipe names from a fuzzy query. "
            "Use this to resolve nicknames (e.g. 'purple science', 'red belt') "
            "into real names like 'production-science-pack' before solving."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_recipe",
        "description": (
            "Inspect a recipe or an item. For an item, returns all recipes that "
            "produce it (use this to resolve a solve_production 'ambiguous_recipe' "
            "error by picking one)."
        ),
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "list_machines",
        "description": "List crafting machines, optionally filtered to a crafting category.",
        "parameters": {
            "type": "object",
            "properties": {"category": {"type": "string"}},
        },
    },
    {
        "name": "list_modules",
        "description": "List available modules and their effects.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "solve_production",
        "description": (
            "Compute exact machine counts, raw inputs/s, and power for a target. "
            "Machine choice is PER recipe category: set machines={'assembler': "
            "'assembling-machine-2'} for assembling recipes; smelting/chemistry/"
            "oil default automatically unless overridden. modules maps a category "
            "(or 'assembler') to a list of module names; omit/empty for none. "
            "Resolve any 'ambiguous_recipe' error by adding recipes={item: recipe}."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "targets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "rate": {"type": "number", "description": "items per second"},
                        },
                        "required": ["name", "rate"],
                    },
                },
                "machines": {
                    "type": "object",
                    "description": "category (or 'assembler') -> machine name",
                    "additionalProperties": {"type": "string"},
                },
                "modules": {
                    "type": "object",
                    "description": "category (or 'assembler') -> list of module names",
                    "additionalProperties": {"type": "array", "items": {"type": "string"}},
                },
                "recipes": {
                    "type": "object",
                    "description": "item -> recipe name (disambiguation)",
                    "additionalProperties": {"type": "string"},
                },
                "raw": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "items to treat as raw (stop expansion)",
                },
            },
            "required": ["targets"],
        },
    },
]


def _recipe_dict(r: Recipe) -> dict:
    return {
        "name": r.name,
        "category": r.category,
        "energy": r.energy,
        "ingredients": [{"name": s.name, "amount": s.amount, "type": s.type} for s in r.ingredients],
        "results": [{"name": s.name, "amount": s.amount, "type": s.type} for s in r.results],
        "allow_productivity": r.allow_productivity,
    }


def _summary(result) -> dict:
    machine_totals: dict[str, int] = defaultdict(int)
    for u in result.uses:
        machine_totals[u.machine] += math.ceil(u.machines - 1e-9)
    return {
        "machines": dict(machine_totals),
        "lines": [
            {
                "item": u.item,
                "recipe": u.recipe,
                "machine": u.machine,
                "machines_exact": round(u.machines, 3),
                "machines_whole": math.ceil(u.machines - 1e-9),
            }
            for u in result.uses
        ],
        "raw_per_s": {k: round(v, 3) for k, v in result.raw.items()},
        "byproducts_per_s": {k: round(v, 3) for k, v in result.byproducts.items()},
        "total_power_w": round(result.total_power_w, 1),
        "warnings": result.warnings,
    }


class Toolbox:
    """Dispatches tool calls against a Database."""

    def __init__(self, db: Database):
        self.db = db
        self._pool = sorted(set(db.items) | set(db.recipes) | set(db.fluids))

    def call(self, name: str, args: dict) -> dict:
        fn = getattr(self, f"_t_{name}", None)
        if fn is None:
            return {"error": "unknown_tool", "message": f"No tool named '{name}'."}
        try:
            return fn(args or {})
        except Exception as e:  # tools must never crash the loop
            return {"error": "tool_exception", "message": f"{type(e).__name__}: {e}"}

    def _t_search_items(self, args: dict) -> dict:
        query = str(args.get("query", ""))
        limit = int(args.get("limit", 10))
        ql = query.lower()
        qd = ql.replace(" ", "-")
        subs = [n for n in self._pool if ql in n.lower() or qd in n.lower()]
        close = difflib.get_close_matches(qd, self._pool, n=limit, cutoff=0.5)
        out: list[str] = []
        for n in subs + close:
            if n not in out:
                out.append(n)
        return {"matches": out[:limit]}

    def _t_get_recipe(self, args: dict) -> dict:
        name = str(args.get("name", ""))
        if name in self.db.recipes:
            return {
                "recipe": _recipe_dict(self.db.recipes[name]),
                "producers_of_same_name_item": self.db.producers.get(name, []),
            }
        producers = self.db.producers.get(name, [])
        if not producers:
            return {"item": name, "producers": [], "note": "no producers -> treated as raw"}
        return {
            "item": name,
            "producers": producers,
            "recipes": {p: _recipe_dict(self.db.recipes[p]) for p in producers},
        }

    def _t_list_machines(self, args: dict) -> dict:
        cat = args.get("category")
        out = []
        for m in self.db.machines.values():
            if cat and cat not in m.categories:
                continue
            out.append({
                "name": m.name,
                "categories": sorted(m.categories),
                "speed": m.speed,
                "module_slots": m.module_slots,
                "energy_w": m.energy_w,
            })
        return {"machines": sorted(out, key=lambda d: d["name"])}

    def _t_list_modules(self, args: dict) -> dict:
        return {
            "modules": [
                {"name": m.name, "category": m.category, "effect": m.effect}
                for m in sorted(self.db.modules.values(), key=lambda m: m.name)
            ]
        }

    def _t_solve_production(self, args: dict) -> dict:
        spec = SolveSpec.from_dict(args)
        try:
            result = solve(spec, self.db)
        except AmbiguousRecipe as e:
            return {
                "error": "ambiguous_recipe",
                "item": e.item,
                "candidates": e.candidates,
                "hint": "Pick one and resend with recipes={'%s': <recipe>}." % e.item,
            }
        except UnknownName as e:
            return {"error": "unknown_name", "message": str(e)}
        except SolverError as e:
            return {"error": "solver_error", "message": str(e)}
        return {"ok": True, "summary": _summary(result), "report": report.render(result, spec)}
