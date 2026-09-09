"""Continuous linear optimization of net exports under explicit resource budgets.

For every item: recipe production + imports = consumption + exports + surplus.
Only declared inputs are importable; only declared byproducts may be discarded.
This complements the Fraction-based exact solver. HiGHS uses floating point;
successful solutions are checked against every balance and bound before reporting.
"""
from __future__ import annotations

import math
from collections import defaultdict

from .model import Database
from .plan_spec import PlanError, validate_plan
from .solver import _active_recipes, _effect_multipliers, _resolve_machine, output_items_per_s
from .spec import OptionValidationError, SolveSpec, validate_category_options

TOLERANCE = 1e-7
LIMITATIONS = [
    "Continuous steady-state rates; rounded machines are a build estimate, not integer optimization.",
    "Recipe scope comes from the exported prototypes, not the save's researched technologies or planet access.",
    "No belt/inserter routing, fluid temperature, quality, startup inventory, or spatial constraints.",
    "Power is active crafting-machine consumption only; fuel supply, idle drain, beacons and infrastructure are excluded.",
    "Productivity uses the existing normalized recipe model; catalyst-specific productivity exemptions are not represented.",
]


def plan_production(request: dict, db: Database) -> dict:
    validate_plan(request)
    try:
        import numpy as np
        from scipy.optimize import linprog
    except ImportError as e:
        raise PlanError("missing_dependency", "Install factoribot[planning] or factoribot[mcp].") from e

    inputs = request["inputs"]
    outputs = request["outputs"]
    objective = request["objective"]
    kind = objective["kind"]
    surplus_items = sorted(request.get("byproducts", []))
    known = set(db.items) | db.fluids
    known.update(s.name for r in db.recipes.values() for s in r.ingredients + r.results)
    unknown = (set(inputs) | set(outputs) | set(surplus_items) | set(request.get("recipes", {}))) - known
    if unknown:
        raise PlanError("unknown_name", "Unknown items or fluids; resolve names before planning.", items=sorted(unknown))
    for item, rn in request.get("recipes", {}).items():
        if rn not in db.recipes or db.recipes[rn].yield_of(item) <= 0:
            raise PlanError("bad_request", f"Recipe '{rn}' does not produce '{item}'.")

    spec = SolveSpec.from_dict({
        **{k: request[k] for k in ("machines", "modules", "beacons", "recipes", "use_recipes") if k in request},
        "targets": [{"name": item, "rate": 1} for item in sorted(outputs)],
        "raw": list(inputs),
    })
    # byproducts are sinks, not instructions to stop dependency expansion.
    active = sorted(request["available_recipes"] if "available_recipes" in request else _active_recipes(spec, db))
    unknown_recipes = set(active) - set(db.recipes)
    if unknown_recipes:
        raise PlanError("unknown_name", "Unknown recipes.", recipes=sorted(unknown_recipes))
    unused_pins = set(request.get("recipes", {}).values()) - set(active)
    if unused_pins:
        raise PlanError("bad_request", "Pinned recipes were not selected during expansion; use available_recipes for an explicit candidate set.", recipes=sorted(unused_pins))
    limits = request.get("machine_limits", {})
    if set(limits) - set(active):
        raise PlanError("bad_request", "machine_limits must name recipes in the active set.", recipes=sorted(set(limits) - set(active)))

    categories = {db.recipes[rn].category for rn in active}
    try:
        validate_category_options(spec, categories)
    except OptionValidationError as e:
        raise PlanError("bad_request", str(e), option=e.option, category=e.category) from e

    # One rate variable per recipe, external input, net output and allowed sink.
    keys = ([('recipe', n) for n in active] + [('input', n) for n in sorted(inputs)]
            + [('output', n) for n in sorted(outputs)] + [('surplus', n) for n in surplus_items])
    if kind == "maximize_ratio":
        keys.append(('scale', 'bundle'))
    index = {key: i for i, key in enumerate(keys)}
    n = len(keys)
    bounds = [(0.0, None) for _ in keys]
    coeff = defaultdict(lambda: np.zeros(n))
    machines_per_craft = np.zeros(n)
    power_per_craft = np.zeros(n)
    recipe_info = {}
    produced = set()
    consumed = set()
    for rn in active:
        r = db.recipes[rn]
        machine = _resolve_machine(db, spec, r.category)
        sm, pm, cm = _effect_multipliers(machine, r, spec.modules_for(r.category), spec.beacons_for(r.category), db)
        if r.energy <= 0 or machine.speed <= 0:
            raise PlanError("unsupported_feature", f"Nonpositive recipe duration or machine speed for '{rn}'.")
        col = index['recipe', rn]
        machines_per_craft[col] = r.energy / (machine.speed * sm)
        power_per_craft[col] = machines_per_craft[col] * machine.energy_w * cm
        recipe_info[rn] = machine
        for s in r.ingredients:
            coeff[s.name][col] -= s.amount
            if s.amount > 0:
                consumed.add(s.name)
        for s in r.results:
            coeff[s.name][col] += s.amount * pm
            if s.amount > 0:
                produced.add(s.name)
        if rn in limits:
            bounds[col] = (0, limits[rn] / machines_per_craft[col])
    for item, capacity in inputs.items():
        col = index['input', item]
        coeff[item][col] = 1
        bounds[col] = (0, capacity)
    for item, cfg in outputs.items():
        col = index['output', item]
        coeff[item][col] = -1
        bounds[col] = (cfg['rate'], cfg['rate']) if 'rate' in cfg else (cfg.get('min', 0), cfg.get('max'))
    for item in surplus_items:
        coeff[item][index['surplus', item]] = -1

    items = sorted(coeff)
    equalities = [coeff[item] for item in items]
    rhs = [0.0] * len(equalities)
    for item, cfg in outputs.items():
        if 'ratio' in cfg:
            row = np.zeros(n)
            row[index['output', item]] = 1
            row[index['scale', 'bundle']] = -cfg['ratio']
            equalities.append(row)
            rhs.append(0.0)
    a_eq = np.array(equalities)
    b_eq = np.array(rhs)
    a_ub = np.array([power_per_craft]) if 'max_power_w' in request else None
    b_ub = np.array([request['max_power_w']]) if a_ub is not None else None

    c = np.zeros(n)
    if kind == 'maximize_ratio':
        c[index['scale', 'bundle']] = -1
    elif kind in ('maximize_outputs', 'minimize_inputs'):
        domain = 'output' if kind == 'maximize_outputs' else 'input'
        sign = -1 if domain == 'output' else 1
        for item, weight in objective['weights'].items():
            c[index[domain, item]] = sign * weight
    elif kind == 'minimize_machines':
        c = machines_per_craft.copy()
    elif kind == 'minimize_power':
        c = power_per_craft.copy()
    # A feasibility request gets a useful, minimal fractional-machine solution.
    else:
        c = machines_per_craft.copy()

    def run(cost, eq=a_eq, eq_rhs=b_eq):
        return linprog(cost, A_eq=eq, b_eq=eq_rhs, A_ub=a_ub, b_ub=b_ub,
                       bounds=bounds, method='highs', options={"time_limit": 20.0,
                       "primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9})

    unavailable = sorted((consumed | set(outputs)) - produced - set(inputs))
    solution = run(c)
    if not solution.success:
        code = {1: 'solver_limit', 2: 'infeasible', 3: 'unbounded'}.get(solution.status, 'numerical_error')
        raise PlanError(code, {
            'infeasible': 'No plan satisfies the declared inputs, output bounds, recipe scope and surplus rules.',
            'unbounded': 'The objective has no finite optimum. Add finite input, output, machine or power limits.',
            'solver_limit': 'The optimizer reached its time or iteration limit; no optimum is reported.',
            'numerical_error': 'The optimizer could not establish a reliable solution.',
        }[code], unavailable_source_items=unavailable, active_recipes=active)

    # Preserve the primary optimum exactly as a constraint, then remove gratuitous
    # recipe cycles, imports, exports and waste. This is not a weighted compromise.
    secondary = np.zeros(n)
    for key, col in index.items():
        secondary[col] = machines_per_craft[col] if key[0] == 'recipe' else (0 if key[0] == 'scale' else 1)
    tied = run(secondary, np.vstack([a_eq, c]), np.append(b_eq, solution.fun))
    warnings = []
    if tied.success:
        x = tied.x
    else:
        x = solution.x
        warnings.append('Primary optimum found, but secondary cleanup did not converge; an equivalent simpler plan may exist.')

    # Independent numerical checks; don't present an optimizer status as proof.
    if not np.all(np.isfinite(x)):
        raise PlanError('numerical_error', 'Non-finite solution.')
    if any(v < -TOLERANCE for v in x):
        raise PlanError('numerical_error', 'Negative production or flow in solution.')
    x = np.maximum(x, 0)
    residuals = a_eq @ x - b_eq
    eq_scale = np.maximum(1, np.abs(a_eq) @ np.abs(x) + np.abs(b_eq))
    if np.any(np.abs(residuals) > TOLERANCE * eq_scale):
        raise PlanError('numerical_error', 'Solution failed material balance or output ratio verification.')
    for col, (lo, hi) in enumerate(bounds):
        if x[col] < lo - TOLERANCE * max(1, abs(lo)) or (hi is not None and x[col] > hi + TOLERANCE * max(1, abs(hi))):
            raise PlanError('numerical_error', 'Solution failed input/output/machine bound verification.')
    if a_ub is not None and np.any(a_ub @ x > b_ub + TOLERANCE * np.maximum(1, np.abs(b_ub))):
        raise PlanError('numerical_error', 'Solution failed power limit verification.')
    if abs(c @ x - solution.fun) > TOLERANCE * max(1, abs(solution.fun)):
        raise PlanError('numerical_error', 'Secondary solve changed the primary objective.')

    def value(domain, item):
        return float(x[index[domain, item]])

    def tight(a, b):
        return abs(a - b) <= TOLERANCE * max(1, abs(b))

    lines = []
    gross_production = defaultdict(float)
    gross_consumption = defaultdict(float)
    for rn in active:
        rate = value('recipe', rn)
        if rate <= 0:
            continue
        r = db.recipes[rn]
        machine = recipe_info[rn]
        col = index['recipe', rn]
        count = rate * machines_per_craft[col]
        _, pm, _ = _effect_multipliers(machine, r, spec.modules_for(r.category), spec.beacons_for(r.category), db)
        for s in r.results:
            gross_production[s.name] += s.amount * pm * rate
        for s in r.ingredients:
            gross_consumption[s.name] += s.amount * rate
        lines.append({
            'recipe': rn, 'machine': machine.name, 'crafts_per_s': rate,
            'output_items_per_s': output_items_per_s(r, rate, pm),
            'machines_exact': float(count), 'machines_whole': math.ceil(count - 1e-9),
            'power_w': float(rate * power_per_craft[col]),
        })
    net_outputs = {item: value('output', item) for item in sorted(outputs)}
    input_use = {
        item: {'available_per_s': inputs[item], 'used_per_s': value('input', item),
               'unused_per_s': None if inputs[item] is None else max(0, inputs[item] - value('input', item))}
        for item in sorted(inputs)
    }
    if kind.startswith('maximize') and -float(c @ x) <= TOLERANCE:
        warnings.append('The maximum objective is zero. Check unavailable sources, zero budgets and allowed surplus; no positive requested production is established.')
    if spec.beacons:
        warnings.append('Beacon effects assume the configured count per machine; actual coverage and beacon power are not modeled.')
    if set(inputs) & set(outputs):
        warnings.append('Some declared outputs can be supplied directly from matching inputs; exports include that pass-through.')

    return {
        'ok': True, 'status': 'optimal', 'request': request,
        'resolved_choices': {
            category: {
                'machine': _resolve_machine(db, spec, category).name,
                'modules': list(spec.modules_for(category)),
                'beacon': spec.beacons_for(category),
            }
            for category in sorted(categories)
        },
        'objective': {**objective, 'value': float(-c @ x if kind.startswith('maximize') else c @ x),
                      'units': {'maximize_ratio': 'bundles/s', 'maximize_outputs': 'weighted exports/s',
                                'minimize_inputs': 'weighted imports/s', 'minimize_machines': 'fractional machines',
                                'minimize_power': 'W', 'feasible': 'fractional machines (feasibility tie-break)'}[kind]},
        'outputs_per_s': net_outputs, 'inputs': input_use,
        'surplus_per_s': {item: value('surplus', item) for item in surplus_items},
        'gross_production_per_s': dict(sorted(gross_production.items())),
        'internal_consumption_per_s': dict(sorted(gross_consumption.items())),
        'lines': lines, 'total_machines_exact': float(machines_per_craft @ x),
        'total_machines_whole': sum(line['machines_whole'] for line in lines),
        'total_power_w': float(power_per_craft @ x),
        'active_limits': {
            'inputs': [item for item in sorted(inputs) if inputs[item] is not None and tight(value('input', item), inputs[item])],
            'machine_limits': [rn for rn in sorted(limits) if tight(value('recipe', rn) * machines_per_craft[index['recipe', rn]], limits[rn])],
            'output_maxima': [item for item, cfg in outputs.items() if 'max' in cfg and tight(value('output', item), cfg['max'])],
            'power': 'max_power_w' in request and tight(float(power_per_craft @ x), request['max_power_w']),
        },
        'recipe_scope': {'mode': 'explicit' if 'available_recipes' in request else 'expanded', 'recipes': active},
        'unavailable_source_items': unavailable,
        'verification': {'method': 'HiGHS LP with independently checked balances and bounds',
                         'relative_tolerance': TOLERANCE, 'max_balance_residual': float(np.max(np.abs(residuals)))},
        'warnings': warnings, 'limitations': LIMITATIONS,
    }
