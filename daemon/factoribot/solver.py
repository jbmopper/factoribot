"""The production solver: exact balance of a chosen recipe set.

Given a ``SolveSpec`` and a ``Database``, we (1) expand the dependency graph to
decide which recipes are *active*, then (2) solve the linear flow-balance system
``M · r = d`` for the per-recipe craft rates ``r`` -- where ``M[item][recipe]``
is the net amount of ``item`` produced per craft and ``d`` is the external demand
(the targets). From the rates we derive machine counts, power, raw inputs, and
byproducts.

Division of labour: the *LLM* picks the recipe set (which oil process, whether to
crack, etc.) and expresses it in the spec; the solver does only exact arithmetic.
When the chosen set can't be balanced it says so precisely, so the model can fix
the set on the next turn:

- ``AmbiguousRecipe``  -- an item has multiple producers and none is active/pinned.
- ``Overconstrained``  -- a (usually multi-output) item can't be balanced; add a
  consumer via ``use_recipes`` (e.g. cracking) or allow surplus via ``byproducts``.
- ``Underdetermined``  -- the set has a free ratio; remove a recipe or pin demand.
- ``Infeasible``       -- the set forces a negative craft rate (contradictory).

Cycles (e.g. coal liquefaction consuming the heavy oil it makes) are fine: the
balance is a linear system, not a topological walk.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from fractions import Fraction

from .model import Database, Machine, Recipe
from .spec import SolveSpec, Target

# Factorio clamps total speed and consumption multipliers to a floor of 20%.
_MIN_MULT = 0.2
# Cap denominators when lifting JSON floats to exact rationals (kills binary
# float noise like 0.1 while keeping real recipe values exact).
_DENOM = 1_000_000


def _F(x) -> Fraction:
    return Fraction(x).limit_denominator(_DENOM)


class SolverError(Exception):
    pass


class AmbiguousRecipe(SolverError):
    def __init__(self, item: str, candidates: list[str]):
        self.item = item
        self.candidates = candidates
        super().__init__(
            f"Item '{item}' has multiple producers; choose one via recipes[] "
            f"(and/or add others via use_recipes[]): {candidates}"
        )


class UnknownName(SolverError):
    pass


class Overconstrained(SolverError):
    def __init__(self, items: list[str]):
        self.items = items
        super().__init__(
            f"Cannot balance {items} with the chosen recipes (over-constrained): "
            f"a recipe makes more of these than is consumed. Add a consuming "
            f"recipe via use_recipes[] (e.g. oil cracking) or allow surplus via "
            f"byproducts[]."
        )


class Underdetermined(SolverError):
    def __init__(self, free_recipes: list[str]):
        self.free_recipes = free_recipes
        super().__init__(
            f"Recipe set is under-determined ({len(free_recipes)} free rate(s)): "
            f"{free_recipes}. Remove a redundant recipe, add its product as a "
            f"target, or mark an input as raw[]."
        )


class Infeasible(SolverError):
    def __init__(self, recipe: str, rate: float):
        self.recipe = recipe
        self.rate = rate
        super().__init__(
            f"Recipe '{recipe}' resolves to a negative rate ({rate:.4g}); the "
            f"recipe set is contradictory. Remove it or adjust "
            f"use_recipes[]/byproducts[]."
        )


@dataclass
class RecipeUse:
    item: str  # the recipe's main product (display label)
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


def _beacon_deltas(
    cfg: dict | None, db: Database, machine: Machine, recipe: Recipe
) -> tuple[float, float, float]:
    """(speed, consumption, productivity) bonuses transmitted by beacons.

    Models the 2.0 mechanic: with ``N`` beacons, each beacon's module effect is
    scaled by ``distribution_effectivity * profile[N]`` (the profile is the
    diminishing-returns curve, ~1/sqrt(N) for vanilla).
    """
    if not cfg:
        return 0.0, 0.0, 0.0
    count = int(cfg.get("count", 0))
    if count <= 0:
        return 0.0, 0.0, 0.0
    bname = cfg.get("beacon")
    beacon = db.beacons.get(bname) if bname else db.default_beacon()
    if beacon is None:
        raise UnknownName(f"Unknown beacon '{bname}'." if bname else "No beacon in data.")
    mods = list(cfg.get("modules", []))
    if len(mods) > beacon.module_slots:
        raise SolverError(
            f"{beacon.name} has {beacon.module_slots} module slots but "
            f"{len(mods)} modules were requested."
        )
    s = c = p = 0.0
    for mn in mods:
        mod = db.modules.get(mn)
        if mod is None:
            raise UnknownName(f"Unknown module '{mn}'.")
        e = mod.effect
        s += e.get("speed", 0.0)
        c += e.get("consumption", 0.0)
        p += e.get("productivity", 0.0)
    prof = beacon.profile[min(count, len(beacon.profile)) - 1] if beacon.profile else 1.0
    scale = count * beacon.distribution_effectivity * prof
    sd = scale * s if "speed" in beacon.allowed_effects and "speed" in machine.allowed_effects else 0.0
    cd = scale * c if "consumption" in beacon.allowed_effects and "consumption" in machine.allowed_effects else 0.0
    pd = (
        scale * p
        if "productivity" in beacon.allowed_effects
        and "productivity" in machine.allowed_effects
        and recipe.allow_productivity
        else 0.0
    )
    return sd, cd, pd


def _effect_multipliers(
    machine: Machine,
    recipe: Recipe,
    module_names: list[str],
    beacon_cfg: dict | None,
    db: Database,
) -> tuple[float, float, float]:
    """Return (speed_mult, prod_mult, consumption_mult) for modules + beacons."""
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
    bs, bc, bp = _beacon_deltas(beacon_cfg, db, machine, recipe)
    speed += bs
    cons += bc
    prod += bp
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


def _pick_producer(db: Database, spec: SolveSpec, item: str) -> str | None:
    """Choose the recipe to *introduce* for an item, or None if it is raw.

    Only called when no already-active recipe produces the item.
    """
    if item in spec.recipes:
        rn = spec.recipes[item]
        if rn not in db.recipes:
            raise UnknownName(f"Unknown recipe '{rn}' pinned for '{item}'.")
        return rn
    producers = db.producers.get(item, [])
    if not producers:
        return None  # raw (ore, water, fluid source, etc.)
    # Prefer a recipe named exactly after the item (the canonical one).
    canonical = [p for p in producers if p == item]
    candidates = canonical or producers
    if len(candidates) > 1:
        raise AmbiguousRecipe(item, sorted(producers))
    return candidates[0]


def _active_recipes(spec: SolveSpec, db: Database) -> list[str]:
    """Expand from the targets (+ use_recipes) to the set of active recipes."""
    active: list[str] = []
    active_set: set[str] = set()
    queue: deque[str] = deque()

    def add_recipe(rn: str) -> None:
        if rn in active_set:
            return
        if rn not in db.recipes:
            raise UnknownName(f"Unknown recipe '{rn}' in use_recipes[].")
        active_set.add(rn)
        active.append(rn)
        for ing in db.recipes[rn].ingredients:
            queue.append(ing.name)

    for rn in spec.use_recipes:
        add_recipe(rn)
    for t in spec.targets:
        queue.append(t.name)

    def produced_by_active(item: str) -> bool:
        return any(
            any(s.name == item and s.amount > 0 for s in db.recipes[rn].results)
            for rn in active
        )

    seen: set[str] = set()
    while queue:
        item = queue.popleft()
        if item in seen:
            continue
        seen.add(item)
        if item in spec.raw or item in spec.byproducts:
            continue
        if produced_by_active(item):
            continue
        rn = _pick_producer(db, spec, item)
        if rn is not None:
            add_recipe(rn)
    return active


def _rref_solve(
    rows: list[list[Fraction]], rhs: list[Fraction], ncols: int
) -> tuple[list[Fraction] | None, list[int], bool]:
    """Gauss-Jordan over the rationals.

    Returns ``(solution, free_columns, consistent)``. ``solution`` is the
    unique solution with free variables set to 0 (None if inconsistent).
    """
    m = len(rows)
    aug = [list(rows[i]) + [rhs[i]] for i in range(m)]
    pivot_cols: list[int] = []
    r = 0
    for c in range(ncols):
        piv = next((i for i in range(r, m) if aug[i][c] != 0), None)
        if piv is None:
            continue
        aug[r], aug[piv] = aug[piv], aug[r]
        pv = aug[r][c]
        aug[r] = [x / pv for x in aug[r]]
        for i in range(m):
            if i != r and aug[i][c] != 0:
                f = aug[i][c]
                aug[i] = [a - f * b for a, b in zip(aug[i], aug[r])]
        pivot_cols.append(c)
        r += 1
        if r == m:
            break

    consistent = not any(
        all(aug[i][c] == 0 for c in range(ncols)) and aug[i][ncols] != 0
        for i in range(m)
    )
    free_cols = [c for c in range(ncols) if c not in pivot_cols]
    if not consistent:
        return None, free_cols, False

    sol = [Fraction(0)] * ncols
    for i in range(m):
        pc = next((c for c in range(ncols) if aug[i][c] != 0), None)
        if pc is not None and pc in pivot_cols:
            sol[pc] = aug[i][ncols]
    return sol, free_cols, True


def solve(spec: SolveSpec, db: Database) -> Result:
    result = Result()
    demand: dict[str, Fraction] = defaultdict(lambda: Fraction(0))
    for t in spec.targets:
        demand[t.name] += _F(t.rate)
    targets = set(demand)

    active = _active_recipes(spec, db)

    # Resolve machine + module effects per active recipe (independent of rates).
    info: dict[str, tuple[Machine, float, float, float]] = {}
    for rn in active:
        recipe = db.recipes[rn]
        machine = _resolve_machine(db, spec, recipe.category)
        sm, pm, cm = _effect_multipliers(
            machine,
            recipe,
            spec.modules_for(recipe.category),
            spec.beacons_for(recipe.category),
            db,
        )
        info[rn] = (machine, sm, pm, cm)

    # Net stoichiometry (outputs scaled by productivity), plus gross produce/consume
    # sets used to classify each item.
    coeff: dict[str, dict[str, Fraction]] = defaultdict(dict)
    gross_out: dict[str, set[str]] = defaultdict(set)
    gross_in: dict[str, set[str]] = defaultdict(set)
    for rn in active:
        recipe = db.recipes[rn]
        pm = _F(info[rn][2])
        per: dict[str, Fraction] = defaultdict(lambda: Fraction(0))
        for ing in recipe.ingredients:
            per[ing.name] -= _F(ing.amount)
            gross_in[ing.name].add(rn)
        for res in recipe.results:
            if res.amount > 0:
                per[res.name] += _F(res.amount) * pm
                gross_out[res.name].add(rn)
        for item, v in per.items():
            coeff[item][rn] = v

    # Classify items -> which get a balance equation.
    #   raw / no producer            -> free source (solved from net flow)
    #   byproducts[] / produced-only -> free sink   (surplus reported)
    #   target or intermediate       -> balance equation
    eq_items: list[str] = []
    for item in coeff:
        if item in spec.raw or item in spec.byproducts:
            continue
        if not gross_out.get(item):
            continue  # only consumed -> raw
        if item in targets or gross_in.get(item):
            eq_items.append(item)
    # A target produced by nothing active is a raw resource to mine; handled below.

    cols = active
    A = [[coeff.get(it, {}).get(rn, Fraction(0)) for rn in cols] for it in eq_items]
    b = [demand.get(it, Fraction(0)) for it in eq_items]
    sol, free_cols, consistent = _rref_solve(A, b, len(cols))

    if not consistent:
        culprits = [
            it
            for it in eq_items
            if any(len(db.recipes[rn].results) > 1 for rn in gross_out.get(it, ()))
        ]
        raise Overconstrained(culprits or eq_items)
    if free_cols:
        raise Underdetermined([cols[c] for c in free_cols])

    rates: dict[str, Fraction] = {cols[i]: sol[i] for i in range(len(cols))}
    for rn, rate in rates.items():
        if rate < 0:
            raise Infeasible(rn, float(rate))

    # Per-recipe machine counts and power.
    for rn in active:
        rate = rates[rn]
        if rate == 0:
            continue
        recipe = db.recipes[rn]
        machine, sm, pm, cm = info[rn]
        eff_speed = machine.speed * sm
        machines = float(rate) * (recipe.energy / eff_speed)
        power = machines * machine.energy_w * cm
        result.uses.append(
            RecipeUse(
                item=recipe.main_product or rn,
                recipe=rn,
                category=recipe.category,
                machine=machine.name,
                crafts_per_s=float(rate),
                machines=machines,
                power_w=power,
            )
        )
        result.total_power_w += power

    # Net flows -> raw inputs and byproducts.
    items = set(coeff) | targets
    for item in items:
        flow = sum(
            (coeff.get(item, {}).get(rn, Fraction(0)) * rates.get(rn, Fraction(0))
             for rn in active),
            Fraction(0),
        )
        d = demand.get(item, Fraction(0))
        if item in targets and not gross_out.get(item):
            if d > 0:
                result.raw[item] = result.raw.get(item, 0.0) + float(d)
            continue
        surplus = flow - d
        if surplus < 0:
            result.raw[item] = result.raw.get(item, 0.0) - float(surplus)
        elif surplus > 0 and item not in targets:
            result.byproducts[item] = result.byproducts.get(item, 0.0) + float(surplus)

    if spec.beacons:
        result.warnings.append(
            "Beacon effects use the 2.0 profile, but beacon power draw is not "
            "included and counts are per affected machine (real sharing depends "
            "on layout)."
        )
    return result


@dataclass
class InputUse:
    item: str
    supplied: float  # /s available
    used: float      # /s actually consumed at the achievable output
    idle: float      # /s of supplied capacity left unused


@dataclass
class EvalResult:
    product: str
    output_per_s: float
    bottleneck: str | None
    inputs: list[InputUse] = field(default_factory=list)
    result: Result = field(default_factory=Result)  # full production, scaled to output


def _scaled(result: Result, f: float) -> Result:
    out = Result(
        raw={k: v * f for k, v in result.raw.items()},
        byproducts={k: v * f for k, v in result.byproducts.items()},
        total_power_w=result.total_power_w * f,
        warnings=list(result.warnings),
    )
    out.uses = [
        RecipeUse(
            item=u.item,
            recipe=u.recipe,
            category=u.category,
            machine=u.machine,
            crafts_per_s=u.crafts_per_s * f,
            machines=u.machines * f,
            power_w=u.power_w * f,
        )
        for u in result.uses
    ]
    return out


def evaluate(spec: SolveSpec, db: Database, inputs: dict[str, float]) -> EvalResult:
    """Input-driven: given supply rates for some inputs, find the max output.

    The single target in ``spec`` names the product (its rate is ignored). The
    given inputs are treated as raw sources; the achievable output is set by the
    binding input ``min_i(supply_i / consumption_per_output_i)``.
    """
    if len(spec.targets) != 1:
        raise SolverError("evaluate needs exactly one target product.")
    product = spec.targets[0].name

    unit_spec = replace(
        spec,
        targets=[Target(product, 1.0)],
        raw=set(spec.raw) | set(inputs),
    )
    unit = solve(unit_spec, db)
    per_unit = unit.raw  # input consumption per 1/s of product

    ratios: list[tuple[float, str]] = []
    for item, supply in inputs.items():
        k = per_unit.get(item, 0.0)
        if k > 0:
            ratios.append((supply / k, item))
    if not ratios:
        raise SolverError(
            f"None of the given inputs {sorted(inputs)} are consumed when making "
            f"'{product}'. Check names (and mark them raw if they're intermediates)."
        )
    output, bottleneck = min(ratios, key=lambda r: r[0])

    scaled = _scaled(unit, output)
    input_uses: list[InputUse] = []
    for item, supply in sorted(inputs.items()):
        used = per_unit.get(item, 0.0) * output
        input_uses.append(InputUse(item, supply, used, supply - used))
    return EvalResult(product, output, bottleneck, input_uses, scaled)
