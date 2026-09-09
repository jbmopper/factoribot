"""Behavioral checks with small, hand-solvable factories; no dump required."""
import copy
import json
from pathlib import Path

import pytest

pytest.importorskip("scipy")
pytest.importorskip("jsonschema")

from factoribot.model import Database, Machine, Module, Recipe, Stack
from factoribot.planner import plan_production
from factoribot.plan_spec import PlanError
from factoribot.solver import InvalidOption, evaluate, solve
from factoribot.spec import SolveSpec
from factoribot.tools import Toolbox
from factoribot.blueprint import BlueprintSummary, MachineGroup
from factoribot.bpanalyze import analyze_blueprint


def database(*rows):
    recipes = {}
    producers = {}
    items = {}
    for name, ingredients, results, seconds in rows:
        recipes[name] = Recipe(name, "crafting", seconds,
                               [Stack(n, q) for n, q in ingredients.items()],
                               [Stack(n, q) for n, q in results.items()], True)
        for n in ingredients | results:
            items[n] = {}
        for n in results:
            producers.setdefault(n, []).append(name)
    return Database(recipes, {"assembler": Machine("assembler", 1, frozenset({"crafting"}), 100,
                    module_slots=2, allowed_effects=frozenset({"speed", "productivity", "consumption"}))},
                    {}, producers, items, set())


@pytest.fixture
def simple():
    return database(("gear", {"iron": 2}, {"gear": 1}, 1),
                    ("belt", {"gear": 1, "iron": 1}, {"belt": 2}, 2))


def test_net_exports_keep_internal_gears_separate(simple):
    result = plan_production({"inputs": {"iron": 14}, "outputs": {"gear": {"ratio": 1}, "belt": {"ratio": 1}},
                              "objective": {"kind": "maximize_ratio"}}, simple)
    assert result['outputs_per_s'] == pytest.approx({'gear': 4, 'belt': 4})
    assert result['gross_production_per_s']['gear'] == pytest.approx(6)
    assert result['internal_consumption_per_s']['gear'] == pytest.approx(2)
    assert result['inputs']['iron']['used_per_s'] == pytest.approx(14)
    assert result['verification']['max_balance_residual'] < 1e-9


def test_six_outputs_and_followup():
    # Independent recipe arithmetic: one equal bundle costs 16 iron, 5.5 copper.
    db = database(
        ('iron-gear-wheel', {'iron-plate': 2}, {'iron-gear-wheel': 1}, .5),
        ('copper-cable', {'copper-plate': 1}, {'copper-cable': 2}, .5),
        ('electronic-circuit', {'iron-plate': 1, 'copper-cable': 3}, {'electronic-circuit': 1}, .5),
        ('inserter', {'iron-plate': 1, 'iron-gear-wheel': 1, 'electronic-circuit': 1}, {'inserter': 1}, .5),
        ('transport-belt', {'iron-plate': 1, 'iron-gear-wheel': 1}, {'transport-belt': 2}, .5),
        ('automation-science-pack', {'copper-plate': 1, 'iron-gear-wheel': 1}, {'automation-science-pack': 1}, 5),
        ('logistic-science-pack', {'inserter': 1, 'transport-belt': 1}, {'logistic-science-pack': 1}, 6),
    )
    path = Path(__file__).parents[1] / 'examples' / 'balanced_six_outputs.json'
    request = json.loads(path.read_text())
    request['machines'] = {'assembler': 'assembler'}
    original = copy.deepcopy(request)
    result = plan_production(request, db)
    assert request == original
    assert len(result['outputs_per_s']) == 6
    assert list(result['outputs_per_s'].values()) == pytest.approx([60 / 11] * 6)
    assert result['inputs']['iron-plate']['used_per_s'] == pytest.approx(960 / 11)
    assert result['inputs']['copper-plate']['used_per_s'] == pytest.approx(30)
    assert result['active_limits']['inputs'] == ['copper-plate']
    # Double circuit exports, keeping all other demands and input budgets.
    request['outputs']['electronic-circuit']['ratio'] = 2
    next_result = plan_production(request, db)
    for item, value in next_result['outputs_per_s'].items():
        assert value == pytest.approx((2 if item == 'electronic-circuit' else 1) * 30 / 7)


def test_exact_min_max_with_weighted_objective(simple):
    result = plan_production({
        'inputs': {'iron': 20}, 'outputs': {'gear': {'min': 2, 'max': 3}, 'belt': {'rate': 4}},
        'objective': {'kind': 'maximize_outputs', 'weights': {'gear': 1}},
    }, simple)
    assert result['outputs_per_s'] == pytest.approx({'gear': 3, 'belt': 4})
    assert result['inputs']['iron']['unused_per_s'] == pytest.approx(8)


def test_multiple_recipes_can_mix_under_machine_limits():
    db = database(('slow', {'ore': 1}, {'plate': 1}, 2),
                  ('fast', {'ore': 2}, {'plate': 1}, 1))
    result = plan_production({
        'inputs': {'ore': 10}, 'outputs': {'plate': {'rate': 6}},
        'available_recipes': ['slow', 'fast'], 'machine_limits': {'slow': 4},
        'objective': {'kind': 'minimize_inputs', 'weights': {'ore': 1}},
    }, db)
    assert {line['recipe']: line['crafts_per_s'] for line in result['lines']} == pytest.approx({'slow': 2, 'fast': 4})
    assert result['inputs']['ore']['used_per_s'] == pytest.approx(10)


@pytest.mark.parametrize('kind', ['minimize_machines', 'minimize_power'])
def test_efficiency_objectives_choose_faster_recipe(kind):
    db = database(('slow', {'ore': 1}, {'plate': 1}, 2), ('fast', {'ore': 2}, {'plate': 1}, 1))
    result = plan_production({'inputs': {'ore': None}, 'outputs': {'plate': {'min': 6}},
                             'available_recipes': ['slow', 'fast'], 'objective': {'kind': kind}}, db)
    assert [line['recipe'] for line in result['lines']] == ['fast']
    assert result['total_machines_exact'] == pytest.approx(6)
    assert result['total_power_w'] == pytest.approx(600)


def test_missing_inputs_are_never_free(simple):
    request = {'inputs': {}, 'outputs': {'belt': {'rate': 1}}, 'objective': {'kind': 'feasible'}}
    with pytest.raises(PlanError) as e:
        plan_production(request, simple)
    assert e.value.code == 'infeasible'
    assert e.value.details['unavailable_source_items'] == ['iron']
    request['inputs']['iron'] = None
    result = plan_production(request, simple)
    assert result['inputs']['iron']['used_per_s'] == pytest.approx(1.5)
    assert result['inputs']['iron']['unused_per_s'] is None


def test_infeasible_bounded_outputs(simple):
    out = Toolbox(simple).call('plan_production', {
        'inputs': {'iron': 1}, 'outputs': {'gear': {'rate': 2}}, 'objective': {'kind': 'feasible'},
    })
    assert out['error'] == 'infeasible'


def test_unbounded_and_zero_capacity(simple):
    request = {'inputs': {'iron': None}, 'outputs': {'gear': {'ratio': 1}}, 'objective': {'kind': 'maximize_ratio'}}
    with pytest.raises(PlanError) as e:
        plan_production(request, simple)
    assert e.value.code == 'unbounded'
    request['inputs']['iron'] = 0
    out = plan_production(request, simple)
    assert out['outputs_per_s']['gear'] == 0
    assert out['warnings']


def test_explicit_surplus_and_consuming_byproducts():
    db = database(('oil', {'crude': 1}, {'light': 1, 'heavy': 1}, 1),
                  ('crack', {'heavy': 1}, {'light': 1}, 1))
    request = {'inputs': {'crude': 10}, 'outputs': {'light': {'rate': 5}},
               'available_recipes': ['oil'], 'objective': {'kind': 'minimize_inputs', 'weights': {'crude': 1}}}
    with pytest.raises(PlanError):
        plan_production(request, db)
    request['byproducts'] = ['heavy']
    out = plan_production(request, db)
    assert out['surplus_per_s']['heavy'] == pytest.approx(5)
    request['available_recipes'].append('crack')
    out = plan_production(request, db)
    assert out['inputs']['crude']['used_per_s'] == pytest.approx(2.5)
    assert out['surplus_per_s']['heavy'] == pytest.approx(0)


def test_power_and_machine_limits(simple):
    request = {'inputs': {'iron': 100}, 'outputs': {'gear': {'ratio': 1}},
               'objective': {'kind': 'maximize_ratio'}, 'max_power_w': 500}
    assert plan_production(request, simple)['outputs_per_s']['gear'] == pytest.approx(5)
    request['machine_limits'] = {'gear': 2}
    out = plan_production(request, simple)
    assert out['outputs_per_s']['gear'] == pytest.approx(2)
    assert out['active_limits']['machine_limits'] == ['gear']


def test_module_effects_change_resource_balance(simple):
    simple.modules['prod'] = Module('prod', 'productivity', {'productivity': .5})
    out = plan_production({'inputs': {'iron': 10}, 'outputs': {'gear': {'ratio': 1}},
                           'modules': {'assembler': ['prod']}, 'objective': {'kind': 'maximize_ratio'}}, simple)
    assert out['outputs_per_s']['gear'] == pytest.approx(7.5)


def test_unused_category_options_fail_identically_across_calculators(simple):
    """A typo must not disappear and fall back to the default assembler."""
    legacy = SolveSpec.from_dict({
        'targets': [{'name': 'gear', 'rate': 1}], 'machines': {'not-a-category': 'assembler'},
    })
    with pytest.raises(InvalidOption) as error:
        solve(legacy, simple)
    assert error.value.option == 'machines'
    with pytest.raises(InvalidOption):
        evaluate(legacy, simple, {'iron': 10})

    request = {
        'inputs': {'iron': 10}, 'outputs': {'gear': {'rate': 1}},
        'machines': {'not-a-category': 'assembler'}, 'objective': {'kind': 'feasible'},
    }
    with pytest.raises(PlanError) as error:
        plan_production(request, simple)
    assert error.value.code == 'bad_request'
    assert Toolbox(simple).call('solve_production', legacy.to_dict())['error'] == 'bad_request'
    assert Toolbox(simple).call('evaluate_throughput', {
        'product': 'gear', 'inputs': {'iron': 10}, 'machines': {'not-a-category': 'assembler'},
    })['error'] == 'bad_request'


def test_category_aliases_resolved_choices_and_multi_result_rates(simple):
    db = database(('split', {'ore': 1}, {'plate': 2, 'slag': 3}, 1))
    spec = SolveSpec.from_dict({
        'targets': [{'name': 'plate', 'rate': 4}],
        'machines': {'assembler': 'assembler'},
        'modules': {'default': []},
        'byproducts': ['slag'],
    })
    result = solve(spec, db)
    line = result.uses[0]
    assert line.crafts_per_s == pytest.approx(2)
    assert line.output_items_per_s == pytest.approx({'plate': 4, 'slag': 6})
    assert result.resolved_choices['crafting']['machine'] == 'assembler'
    assert result.request == spec.to_dict()
    category_spec = SolveSpec.from_dict({
        'targets': [{'name': 'plate', 'rate': 2}],
        'machines': {'crafting': 'assembler'}, 'byproducts': ['slag'],
    })
    assert solve(category_spec, db).resolved_choices['crafting']['machine'] == 'assembler'

    planned = plan_production({
        'inputs': {'ore': 2}, 'outputs': {'plate': {'ratio': 1}},
        'machines': {'assembler': 'assembler'}, 'modules': {'default': []},
        'byproducts': ['slag'], 'objective': {'kind': 'maximize_ratio'},
    }, db)
    assert planned['lines'][0]['crafts_per_s'] == pytest.approx(2)
    assert planned['lines'][0]['output_items_per_s'] == pytest.approx({'plate': 4, 'slag': 6})
    assert planned['resolved_choices']['crafting']['machine'] == 'assembler'

    analysis = analyze_blueprint(BlueprintSummary(
        None, [MachineGroup('assembler', 'split', 1)], {}, {}, {}, {}, {}, 1,
    ), db, product='plate')
    stage = analysis.stages[0]
    assert stage.capacity_per_s == pytest.approx(1)  # legacy crafts/s alias
    assert stage.capacity_output_items_per_s == pytest.approx({'plate': 2, 'slag': 3})
    assert stage.actual_output_items_per_s == pytest.approx({'plate': 2, 'slag': 3})


def test_explicit_empty_recipe_scope_allows_only_passthrough(simple):
    out = plan_production({'inputs': {'gear': 10}, 'outputs': {'gear': {'rate': 2}},
                           'available_recipes': [], 'objective': {'kind': 'feasible'}}, simple)
    assert out['lines'] == []
    assert out['inputs']['gear']['used_per_s'] == 2
    assert out['warnings']


@pytest.mark.parametrize('change', [
    {'inputs': {'iron': -1}}, {'inputs': {'iron': float('nan')}},
    {'inputs': {'iron': float('inf')}}, {'inputs': {'iron': True}},
    {'inputs': {'iron': '10'}}, {'inputs': {'made-up': 10}},
    {'outputs': {'gear': {'min': 3, 'max': 1}}},
    {'outputs': {'gear': {'rate': 1, 'min': 1}}},
    {'outputs': {'gear': {'ratio': 0}}}, {'integer_machines': True},
    {'objective': {'kind': 'maximize_ratio'}},
    {'objective': {'kind': 'maximize_outputs', 'weights': {'typo': 1}}},
    {'objective': {'kind': 'minimize_inputs', 'weights': {}}},
    {'recipes': {'gear': 'belt'}}, {'machines': {'typo': 'assembler'}},
    {'machine_limits': {'typo': 1}}, {'byproducts': ['gear']},
    {'available_recipes': ['gear'], 'use_recipes': ['belt']},
    {'available_recipes': ['not-a-recipe']},
])
def test_bad_contracts_do_not_silently_change_question(simple, change):
    request = {'inputs': {'iron': 10}, 'outputs': {'gear': {'rate': 1}}, 'objective': {'kind': 'feasible'}}
    request.update(change)
    with pytest.raises(PlanError):
        plan_production(request, simple)


def test_beacon_power_model_gap_is_explicit(simple):
    out = Toolbox(simple).call('plan_production', {
        'inputs': {'iron': 10}, 'outputs': {'gear': {'rate': 1}}, 'objective': {'kind': 'minimize_power'},
        'beacons': {'assembler': {'count': 1, 'modules': []}},
    })
    assert out['error'] == 'unsupported_feature'
