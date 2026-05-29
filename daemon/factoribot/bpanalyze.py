"""Blueprint capacity analysis: fixed machine counts -> throughput + bottleneck.

This bridges the geometry-free blueprint model (``blueprint.py``) and the
recipe-set solver. A blueprint fixes how many machines run each recipe, which
fixes each *stage's* maximum craft rate. We:

1. pick the blueprint's primary product (the net output with the most capacity),
2. find the recipe sub-chain that feeds it (items it doesn't make are treated as
   externally supplied -- belted in),
3. ask the solver for the per-unit craft rates of that chain, and
4. set the achievable output to the stage with the least headroom -- the
   bottleneck -- then scale every stage, external input, and surplus to it.

Limitations (v1): productivity from modules/beacons is not folded into throughput
(speed only; we warn when productivity modules are present), and a single primary
product chain is analyzed. Belt routing / beacon coverage (geometry) is out of
scope -- this is the ratio view, not a wiring diagram.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .blueprint import BlueprintSummary
from .model import Database
from .solver import SolverError, _effect_multipliers, solve
from .spec import SolveSpec, Target


@dataclass
class StageLoad:
    recipe: str
    machine: str
    machines_present: int
    capacity_per_s: float  # max crafts/s summed over machines on this recipe
    actual_per_s: float = 0.0  # crafts/s at the achievable output (0 if unknown)
    power_w: float = 0.0

    @property
    def utilization(self) -> float:
        return self.actual_per_s / self.capacity_per_s if self.capacity_per_s else 0.0


@dataclass
class BlueprintAnalysis:
    product: str | None
    output_per_s: float
    bottleneck: str | None  # recipe name of the binding stage
    stages: list[StageLoad] = field(default_factory=list)
    external_inputs: dict[str, float] = field(default_factory=dict)  # item -> /s in
    surplus: dict[str, float] = field(default_factory=dict)  # item -> /s leftover
    offchain: list[StageLoad] = field(default_factory=list)  # present, not on chain
    unmodeled_machines: dict[str, int] = field(default_factory=dict)  # no-recipe (furnaces)
    total_power_w: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Stage:
    """Internal per-recipe capacity record (summed across module variants)."""

    machine: str
    count: int
    capacity: float  # crafts/s
    energy_w: float  # one machine's draw
    cons_mult: float


def _stages_by_recipe(
    summary: BlueprintSummary, db: Database, warnings: list[str]
) -> dict[str, _Stage]:
    """Aggregate capacity per recipe across the blueprint's machine groups."""
    out: dict[str, _Stage] = {}
    missing: set[str] = set()
    prod_present = False
    for g in summary.groups:
        machine = db.machines.get(g.machine)
        recipe = db.recipes.get(g.recipe) if g.recipe else None
        if machine is None or recipe is None or not recipe.energy:
            missing.add(g.recipe or g.machine)
            continue
        mods = [m for m, c in g.modules.items() for _ in range(c)]
        try:
            speed_mult, prod_mult, cons_mult = _effect_multipliers(
                machine, recipe, mods, None, db
            )
        except SolverError as e:
            warnings.append(f"{g.recipe}: {e}")
            continue
        if prod_mult > 1.0:
            prod_present = True
        cap = g.count * machine.speed * speed_mult / recipe.energy
        if g.recipe in out:
            s = out[g.recipe]
            s.count += g.count
            s.capacity += cap
        else:
            out[g.recipe] = _Stage(g.machine, g.count, cap, machine.energy_w, cons_mult)
    if prod_present:
        warnings.append(
            "Productivity modules present: throughput is computed speed-only "
            "(productivity is not yet folded into blueprint analysis)."
        )
    if missing:
        warnings.append(f"Ignored entries not found as recipes in data: {sorted(missing)}.")
    return out


def _pick_product(stages: dict[str, _Stage], db: Database) -> str | None:
    """The net output (produced but not consumed by the present recipes) with the
    most capacity behind it."""
    produced: set[str] = set()
    consumed: set[str] = set()
    out_items: dict[str, set[str]] = {}
    for rn in stages:
        r = db.recipes[rn]
        outs = {s.name for s in r.results if s.amount > 0}
        out_items[rn] = outs
        produced |= outs
        consumed |= {s.name for s in r.ingredients}
    nets = produced - consumed
    if not nets:
        return None

    def behind(item: str) -> float:
        return sum(stages[rn].capacity for rn in stages if item in out_items[rn])

    return sorted(nets, key=lambda it: (-behind(it), it))[0]


def _chain_for(product: str, stages: dict[str, _Stage], db: Database) -> set[str]:
    """The present recipes that (transitively) produce `product`."""
    producers: dict[str, list[str]] = defaultdict(list)
    for rn in stages:
        for s in db.recipes[rn].results:
            if s.amount > 0:
                producers[s.name].append(rn)
    relevant: set[str] = set()
    frontier = [product]
    seen: set[str] = set()
    while frontier:
        item = frontier.pop()
        if item in seen:
            continue
        seen.add(item)
        for rn in producers.get(item, []):
            if rn not in relevant:
                relevant.add(rn)
                frontier.extend(s.name for s in db.recipes[rn].ingredients)
    return relevant


def analyze_blueprint(
    summary: BlueprintSummary, db: Database, product: str | None = None
) -> BlueprintAnalysis:
    warnings: list[str] = []
    stages = _stages_by_recipe(summary, db, warnings)
    unmodeled = dict(summary.no_recipe)

    if not stages:
        warnings.append("No analyzable crafting recipes in this blueprint.")
        return BlueprintAnalysis(None, 0.0, None, unmodeled_machines=unmodeled, warnings=warnings)

    if product is None:
        product = _pick_product(stages, db)
    if product is None:
        # Everything is an internal intermediate (no clear end product). Report
        # capacities without a throughput figure.
        loads = [
            StageLoad(rn, s.machine, s.count, s.capacity) for rn, s in stages.items()
        ]
        warnings.append("No net output product found; reporting stage capacities only.")
        return BlueprintAnalysis(
            None, 0.0, None, offchain=loads, unmodeled_machines=unmodeled, warnings=warnings
        )

    relevant = _chain_for(product, stages, db)
    rel_out = {s.name for rn in relevant for s in db.recipes[rn].results if s.amount > 0}
    rel_in = {s.name for rn in relevant for s in db.recipes[rn].ingredients}
    externals = rel_in - rel_out

    spec = SolveSpec(
        targets=[Target(product, 1.0)], use_recipes=sorted(relevant), raw=set(externals)
    )
    try:
        unit = solve(spec, db)
    except SolverError as e:
        warnings.append(f"Couldn't compute throughput for '{product}': {e}")
        loads = [StageLoad(rn, s.machine, s.count, s.capacity) for rn, s in stages.items()]
        return BlueprintAnalysis(
            product, 0.0, None, offchain=loads, unmodeled_machines=unmodeled, warnings=warnings
        )

    cpu = {u.recipe: u.crafts_per_s for u in unit.uses}  # crafts/s per 1/s of product
    ratios = [(stages[rn].capacity / cpu[rn], rn) for rn in relevant if cpu.get(rn, 0) > 0]
    output, bottleneck = min(ratios, key=lambda r: r[0])

    stage_loads: list[StageLoad] = []
    total_power = 0.0
    for rn in sorted(relevant, key=lambda r: -stages[r].capacity):
        s = stages[rn]
        actual = cpu.get(rn, 0.0) * output
        # machines actually running = count * utilization; power scales with it.
        util = actual / s.capacity if s.capacity else 0.0
        power = s.count * util * s.energy_w * s.cons_mult
        total_power += power
        stage_loads.append(
            StageLoad(rn, s.machine, s.count, s.capacity, actual_per_s=actual, power_w=power)
        )

    offchain = [
        StageLoad(rn, s.machine, s.count, s.capacity)
        for rn, s in stages.items()
        if rn not in relevant
    ]
    return BlueprintAnalysis(
        product=product,
        output_per_s=output,
        bottleneck=bottleneck,
        stages=stage_loads,
        external_inputs={k: v * output for k, v in unit.raw.items()},
        surplus={k: v * output for k, v in unit.byproducts.items()},
        offchain=offchain,
        unmodeled_machines=unmodeled,
        total_power_w=total_power,
        warnings=warnings,
    )
