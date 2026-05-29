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
from .blueprint import (
    BlueprintError,
    decode_blueprint_string,
    iter_blueprints,
    summarize_blueprint,
)
from .bpanalyze import analyze_blueprint
from .model import Database, Recipe
from .solver import (
    AmbiguousRecipe,
    Infeasible,
    Overconstrained,
    SolverError,
    Underdetermined,
    UnknownName,
    evaluate,
    solve,
)
from .spec import SolveSpec, Target

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
        "name": "list_belts",
        "description": (
            "List transport belts and their throughput in items/s (both lanes). "
            "Use to convert a player's belt counts (e.g. '2 red belts') into a "
            "rate, or to report a flow in belts."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "solve_production",
        "description": (
            "Compute exact machine counts, raw inputs/s, byproducts, and power "
            "for one or more targets. Machine choice is PER recipe category: set "
            "machines={'assembler': 'assembling-machine-2'} for assembling "
            "recipes; smelting/chemistry/oil default automatically unless "
            "overridden. modules maps a category (or 'assembler') to a list of "
            "module names; omit/empty for none. The solver BALANCES the chosen "
            "recipe set, so byproducts that are consumed elsewhere are netted "
            "automatically. Resolve errors on the next call: 'ambiguous_recipe' "
            "-> add recipes={item: recipe}; 'overconstrained' -> add a consumer "
            "via use_recipes (e.g. ['heavy-oil-cracking','light-oil-cracking']) "
            "or allow surplus via byproducts; 'underdetermined' -> drop a recipe "
            "or mark an input raw; 'infeasible' -> remove the offending recipe."
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
                    "description": "items to treat as raw / free source (stop expansion)",
                },
                "use_recipes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "extra recipes to force into the set even if they add a "
                        "second producer for an item (e.g. oil cracking); the "
                        "solver balances them"
                    ),
                },
                "byproducts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "items allowed to be surplus / free sink instead of balanced",
                },
                "beacons": {
                    "type": "object",
                    "description": (
                        "category (or 'assembler') -> {count: N, modules: [names "
                        "per beacon], beacon: optional name}. Models N beacons "
                        "affecting each machine in that category."
                    ),
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer"},
                            "modules": {"type": "array", "items": {"type": "string"}},
                            "beacon": {"type": "string"},
                        },
                        "required": ["count", "modules"],
                    },
                },
            },
            "required": ["targets"],
        },
    },
    {
        "name": "evaluate_throughput",
        "description": (
            "Input-driven sizing: given how much of some inputs you can supply "
            "(items/s), compute the MAX output of a product, which input is the "
            "bottleneck, and how much of each input is idle. Use this for "
            "questions like 'two red belts of iron and one of copper -- how much "
            "X can I make, and is the ratio good?'. Convert belts to items/s "
            "first with list_belts. Same recipe/machine/module options as "
            "solve_production. Mark intermediate inputs (e.g. iron-plate) raw if "
            "needed -- inputs are treated as supplied."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "item to maximize"},
                "inputs": {
                    "type": "object",
                    "description": "input item -> available rate (items/s)",
                    "additionalProperties": {"type": "number"},
                },
                "machines": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "modules": {
                    "type": "object",
                    "additionalProperties": {"type": "array", "items": {"type": "string"}},
                },
                "recipes": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
                "raw": {"type": "array", "items": {"type": "string"}},
                "use_recipes": {"type": "array", "items": {"type": "string"}},
                "byproducts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["product", "inputs"],
        },
    },
    {
        "name": "analyze_blueprint",
        "description": (
            "Analyze a Factorio blueprint STRING. Decodes it and reports what it "
            "produces, the achievable throughput, the limiting stage (bottleneck) "
            "with per-stage machine utilization, the external inputs it must be fed "
            "(stages it doesn't build itself), and any recipe-less machines like "
            "furnaces. Use when the player pastes a blueprint string or asks to "
            "analyze/check/balance a blueprint. Do NOT echo the blueprint string "
            "back. Geometry (belt routing/beacon coverage) is not modeled and "
            "throughput is speed-only (productivity modules are noted)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "blueprint_string": {
                    "type": "string",
                    "description": "the exported blueprint string (usually starts with '0')",
                },
                "product": {
                    "type": "string",
                    "description": (
                        "optional: which output item to analyze throughput for; "
                        "defaults to the blueprint's largest net output"
                    ),
                },
            },
            "required": ["blueprint_string"],
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


def _err(e: SolverError) -> dict:
    """Map a solver exception to a structured, LLM-actionable error."""
    if isinstance(e, AmbiguousRecipe):
        return {
            "error": "ambiguous_recipe",
            "item": e.item,
            "candidates": e.candidates,
            "hint": (
                "Pick the primary producer with recipes={'%s': <recipe>}. To also "
                "consume byproducts (e.g. oil), add the extra recipes via "
                "use_recipes=[...]." % e.item
            ),
        }
    if isinstance(e, Overconstrained):
        return {
            "error": "overconstrained",
            "items": e.items,
            "hint": (
                "A recipe overproduces these. Add a consumer via use_recipes "
                "(e.g. ['heavy-oil-cracking','light-oil-cracking']) or allow "
                "surplus via byproducts=[...]."
            ),
        }
    if isinstance(e, Underdetermined):
        return {
            "error": "underdetermined",
            "free_recipes": e.free_recipes,
            "hint": "Remove a redundant recipe, add its product as a target, or mark an input raw=[...].",
        }
    if isinstance(e, Infeasible):
        return {
            "error": "infeasible",
            "recipe": e.recipe,
            "hint": "This recipe would run at a negative rate; remove it from use_recipes/recipes.",
        }
    if isinstance(e, UnknownName):
        return {"error": "unknown_name", "message": str(e)}
    return {"error": "solver_error", "message": str(e)}


def _bp_summary(a) -> dict:
    return {
        "product": a.product,
        "output_per_s": round(a.output_per_s, 4),
        "bottleneck": a.bottleneck,
        "stages": [
            {
                "recipe": s.recipe,
                "machine": s.machine,
                "machines": s.machines_present,
                "capacity_per_s": round(s.capacity_per_s, 4),
                "utilization": round(s.utilization, 4),
            }
            for s in a.stages
        ],
        "external_inputs_per_s": {k: round(v, 4) for k, v in a.external_inputs.items()},
        "surplus_per_s": {k: round(v, 4) for k, v in a.surplus.items()},
        "unmodeled_machines": a.unmodeled_machines,
        "total_power_w": round(a.total_power_w, 1),
        "warnings": a.warnings,
    }


def _eval_summary(ev, db: Database) -> dict:
    return {
        "product": ev.product,
        "output_per_s": round(ev.output_per_s, 3),
        "bottleneck": ev.bottleneck,
        "inputs": [
            {
                "item": i.item,
                "supplied": round(i.supplied, 3),
                "used": round(i.used, 3),
                "idle": round(i.idle, 3),
                "utilization": round(i.used / i.supplied, 4) if i.supplied else None,
            }
            for i in ev.inputs
        ],
        "production": _summary(
            ev.result, SolveSpec(targets=[Target(ev.product, ev.output_per_s)]), db
        ),
    }


def _summary(result, spec: SolveSpec, db: Database) -> dict:
    machine_totals: dict[str, int] = defaultdict(int)
    for u in result.uses:
        machine_totals[u.machine] += math.ceil(u.machines - 1e-9)

    flows: dict[str, float] = {}
    for t in spec.targets:
        flows[t.name] = flows.get(t.name, 0.0) + t.rate
    for k, v in result.raw.items():
        flows[k] = flows.get(k, 0.0) + v
    for k, v in result.byproducts.items():
        flows[k] = flows.get(k, 0.0) + v
    belts: dict[str, dict[str, float]] = {}
    for item, rate in flows.items():
        bc = report.belt_counts(rate, db, item)
        if bc:
            belts[item] = {name: round(c, 3) for name, c in bc.items()}

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
        "outputs_per_s": {t.name: t.rate for t in spec.targets},
        "raw_per_s": {k: round(v, 3) for k, v in result.raw.items()},
        "byproducts_per_s": {k: round(v, 3) for k, v in result.byproducts.items()},
        "belts": belts,
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

    def _t_list_belts(self, args: dict) -> dict:
        return {
            "belts": [
                {"name": name, "items_per_s": round(per, 3)}
                for name, per in self.db.belt_tiers()
            ]
        }

    def _t_solve_production(self, args: dict) -> dict:
        spec = SolveSpec.from_dict(args)
        try:
            result = solve(spec, self.db)
        except SolverError as e:
            return _err(e)
        return {
            "ok": True,
            "summary": _summary(result, spec, self.db),
            "report": report.render(result, spec, self.db),
        }

    def _t_evaluate_throughput(self, args: dict) -> dict:
        product = args.get("product")
        if not product:
            return {"error": "bad_request", "message": "product is required."}
        try:
            inputs = {str(k): float(v) for k, v in (args.get("inputs") or {}).items()}
        except (TypeError, ValueError):
            return {"error": "bad_request", "message": "inputs must be item -> number."}
        spec_dict = {
            k: v for k, v in args.items() if k not in ("product", "inputs")
        }
        spec_dict["targets"] = [{"name": product, "rate": 1.0}]
        spec = SolveSpec.from_dict(spec_dict)
        try:
            ev = evaluate(spec, self.db, inputs)
        except SolverError as e:
            return _err(e)
        return {
            "ok": True,
            "summary": _eval_summary(ev, self.db),
            "report": report.render_eval(ev, self.db),
        }

    def _t_analyze_blueprint(self, args: dict) -> dict:
        s = str(args.get("blueprint_string") or "")
        if not s.strip():
            return {"error": "bad_request", "message": "blueprint_string is required."}
        try:
            decoded = decode_blueprint_string(s)
        except BlueprintError as e:
            return {"error": "bad_blueprint", "message": str(e)}
        bps = iter_blueprints(decoded)
        if not bps:
            return {
                "error": "bad_blueprint",
                "message": "no blueprint with entities found (an empty book or a planner?).",
            }
        summ = summarize_blueprint(bps[0], self.db)
        a = analyze_blueprint(summ, self.db, product=args.get("product"))
        result = {
            "ok": True,
            "summary": _bp_summary(a),
            "report": report.render_blueprint(a, self.db),
        }
        if len(bps) > 1:
            result["note"] = f"analyzed the first of {len(bps)} blueprints in the book"
        return result
