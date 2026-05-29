"""The production solver: exact machine/throughput math over the recipe graph.

Given a SolveSpec and a Database, expand the dependency graph and compute, for
every recipe used, the crafts/s and machine count, plus raw inputs/s, power,
and byproducts.

Scope (MVP): acyclic chains with one recipe chosen per item. Genuine choices
(items with multiple producers) must be resolved in the spec; otherwise we raise
``AmbiguousRecipe`` so the caller (the LLM) can pick. Cycles raise ``CyclicGraph``.
Multi-output recipes are handled by crediting side-products as byproducts.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .model import Database, Machine, Recipe
from .spec import SolveSpec

# Factorio clamps total speed and consumption multipliers to a floor of 20%.
_MIN_MULT = 0.2


class SolverError(Exception):
    pass


class AmbiguousRecipe(SolverError):
    def __init__(self, item: str, candidates: list[str]):
        self.item = item
        self.candidates = candidates
        super().__init__(
            f"Item '{item}' has multiple producers; choose one via recipes[]: "
            f"{candidates}"
        )


class CyclicGraph(SolverError):
    def __init__(self, item: str):
        self.item = item
        super().__init__(
            f"Dependency cycle through '{item}'. Break it by marking an "
            f"intermediate as raw[] or pinning recipes[]."
        )


class UnknownName(SolverError):
    pass


@dataclass
class RecipeUse:
    item: str
    recipe: str
    category: str
    machine: str
    crafts_per_s: float
    machines: float  # fractional (throughput-exact)
    power_w: float


@dataclass
class Result:
    uses: list[RecipeUse] = field(default_factory=list)
    raw: dict[str, float] = field(default_factory=dict)          # item -> /s
    byproducts: dict[str, float] = field(default_factory=dict)   # item -> /s surplus
    total_power_w: float = 0.0
    warnings: list[str] = field(default_factory=list)


def _module_multipliers(
    machine: Machine, recipe: Recipe, module_names: list[str], db: Database
) -> tuple[float, float, float]:
    """Return (speed_mult, prod_mult, consumption_mult) for a machine loadout."""
    if module_names and len(module_names) > machine.module_slots:
        raise SolverError(
            f"{machine.name} has {machine.module_slots} module slots but "
            f"{len(module_names)} modules were requested."
        )
    speed = cons = prod = 0.0
    for mn in module_names:
        mod = db.modules.get(mn)
        if mod is None:
            raise UnknownName(f"Unknown module '{mn}'.")
        e = mod.effect
        if "speed" in e and "speed" in machine.allowed_effects:
            speed += e["speed"]
        if "consumption" in e and "consumption" in machine.allowed_effects:
            cons += e["consumption"]
        if (
            "productivity" in e
            and "productivity" in machine.allowed_effects
            and recipe.allow_productivity
        ):
            prod += e["productivity"]
    return (
        max(_MIN_MULT, 1.0 + speed),
        1.0 + max(0.0, prod),
        max(_MIN_MULT, 1.0 + cons),
    )


def _resolve_machine(db: Database, spec: SolveSpec, category: str) -> Machine:
    name = spec.machine_for(category)
    if name is not None:
        machine = db.machines.get(name)
        if machine is None:
            raise UnknownName(f"Unknown machine '{name}'.")
        if category not in machine.categories:
            raise SolverError(
                f"{name} cannot craft category '{category}'. "
                f"It supports: {sorted(machine.categories)}."
            )
        return machine
    machine = db.default_machine(category)
    if machine is None:
        raise SolverError(f"No machine available for category '{category}'.")
    return machine


def _choose_recipe(db: Database, spec: SolveSpec, item: str) -> str | None:
    if item in spec.raw:
        return None
    if item in spec.recipes:
        rn = spec.recipes[item]
        if rn not in db.recipes:
            raise UnknownName(f"Unknown recipe '{rn}' pinned for '{item}'.")
        return rn
    producers = db.producers.get(item, [])
    if not producers:
        return None  # raw (ore, fluid source, etc.)
    # Prefer a recipe named exactly after the item (the canonical one).
    canonical = [p for p in producers if p == item]
    candidates = canonical or producers
    if len(candidates) > 1:
        raise AmbiguousRecipe(item, sorted(producers))
    return candidates[0]


def solve(spec: SolveSpec, db: Database) -> Result:
    result = Result()
    required: dict[str, float] = defaultdict(float)
    for t in spec.targets:
        required[t.name] += t.rate

    chosen: dict[str, str | None] = {}

    def choose(item: str) -> str | None:
        if item not in chosen:
            chosen[item] = _choose_recipe(db, spec, item)
        return chosen[item]

    # Post-order DFS -> reversed gives topological (consumer-before-ingredient).
    order: list[str] = []
    state: dict[str, int] = {}  # 0 = visiting, 1 = done

    def visit(item: str) -> None:
        st = state.get(item)
        if st == 1:
            return
        if st == 0:
            raise CyclicGraph(item)
        state[item] = 0
        rn = choose(item)
        if rn is not None:
            for ing in db.recipes[rn].ingredients:
                visit(ing.name)
        state[item] = 1
        order.append(item)

    for t in spec.targets:
        visit(t.name)

    for item in reversed(order):
        rn = chosen.get(item)
        need = required[item]
        if rn is None:
            if need > 0:
                result.raw[item] = result.raw.get(item, 0.0) + need
            continue
        recipe = db.recipes[rn]
        machine = _resolve_machine(db, spec, recipe.category)
        speed_mult, prod_mult, cons_mult = _module_multipliers(
            machine, recipe, spec.modules_for(recipe.category), db
        )
        base_yield = recipe.yield_of(item)
        if base_yield <= 0:
            result.warnings.append(f"Recipe '{rn}' does not produce '{item}'.")
            continue
        eff_yield = base_yield * prod_mult
        crafts = need / eff_yield
        eff_speed = machine.speed * speed_mult
        machines = crafts * (recipe.energy / eff_speed)
        power = machines * machine.energy_w * cons_mult

        result.uses.append(
            RecipeUse(
                item=item,
                recipe=rn,
                category=recipe.category,
                machine=machine.name,
                crafts_per_s=crafts,
                machines=machines,
                power_w=power,
            )
        )
        result.total_power_w += power

        for ing in recipe.ingredients:
            required[ing.name] += crafts * ing.amount
        for res in recipe.results:
            if res.name != item and res.amount > 0:
                result.byproducts[res.name] = (
                    result.byproducts.get(res.name, 0.0) + crafts * res.amount
                )

    for name in list(result.byproducts):
        if name in required and required[name] > 0:
            result.warnings.append(
                f"'{name}' is also a byproduct; surplus is not netted against "
                f"demand in this MVP solver."
            )
    return result
