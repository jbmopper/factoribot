import json
import math
from collections import defaultdict
from pathlib import Path

import pytest

from factoribot.gamedata import load_database
from factoribot.planner import plan_production
from factoribot.solver import solve
from factoribot.spec import SolveSpec


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "planner_crosschecks"
CASES = sorted(
    p for p in FIXTURES.glob("*.json")
    if not p.name.endswith(".example.json")
)


@pytest.fixture(scope="module")
def db():
    try:
        return load_database()
    except FileNotFoundError:
        pytest.skip("data-raw-dump.json not present; run `factorio --dump-data`")


def _case_id(path: Path) -> str:
    return path.stem


def _assert_close(case_name: str, label: str, actual: float, expected: float, tol: dict):
    assert math.isclose(
        actual,
        expected,
        rel_tol=float(tol.get("rel", 1e-6)),
        abs_tol=float(tol.get("abs", 1e-9)),
    ), f"{case_name}: {label}: expected {expected}, got {actual}"


def _whole_machine_totals(result):
    totals = defaultdict(int)
    for use in result.uses:
        totals[use.machine] += math.ceil(use.machines - 1e-9)
    return dict(totals)


def _assert_float_map(case_name: str, label: str, actual: dict, expected: dict, tol: dict):
    for name, value in expected.items():
        assert name in actual, f"{case_name}: missing {label} entry {name!r}"
        _assert_close(case_name, f"{label}.{name}", actual[name], value, tol)


@pytest.mark.parametrize("path", CASES, ids=_case_id)
def test_solver_matches_external_planner_snapshot(db, path):
    data = json.loads(path.read_text())
    case_name = data.get("name", path.stem)
    tol = data.get("tolerance", {})
    strict = bool(data.get("strict", False))
    result = solve(SolveSpec.from_dict(data["spec"]), db)

    expected = data["expected"]
    actual_by_recipe = {use.recipe: use for use in result.uses}
    expected_recipes = expected.get("recipes", {})

    for recipe, recipe_expected in expected_recipes.items():
        assert recipe in actual_by_recipe, f"{case_name}: missing recipe {recipe!r}"
        use = actual_by_recipe[recipe]
        if "crafts_per_s" in recipe_expected:
            _assert_close(
                case_name,
                f"recipes.{recipe}.crafts_per_s",
                use.crafts_per_s,
                recipe_expected["crafts_per_s"],
                tol,
            )
        if "machines_exact" in recipe_expected:
            _assert_close(
                case_name,
                f"recipes.{recipe}.machines_exact",
                use.machines,
                recipe_expected["machines_exact"],
                tol,
            )
        if "machines_whole" in recipe_expected:
            assert (
                math.ceil(use.machines - 1e-9) == recipe_expected["machines_whole"]
            ), f"{case_name}: recipes.{recipe}.machines_whole"
        if "machine" in recipe_expected:
            assert use.machine == recipe_expected["machine"], (
                f"{case_name}: recipes.{recipe}.machine: "
                f"expected {recipe_expected['machine']!r}, got {use.machine!r}"
            )

    _assert_float_map(case_name, "raw_per_s", result.raw, expected.get("raw_per_s", {}), tol)
    _assert_float_map(
        case_name,
        "byproducts_per_s",
        result.byproducts,
        expected.get("byproducts_per_s", {}),
        tol,
    )

    if "machine_totals_whole" in expected:
        assert _whole_machine_totals(result) == expected["machine_totals_whole"]

    if "total_power_w" in expected:
        _assert_close(case_name, "total_power_w", result.total_power_w, expected["total_power_w"], tol)

    if strict:
        assert set(actual_by_recipe) == set(expected_recipes), f"{case_name}: recipe set differs"
        assert set(result.raw) == set(expected.get("raw_per_s", {})), f"{case_name}: raw inputs differ"
        assert set(result.byproducts) == set(expected.get("byproducts_per_s", {})), (
            f"{case_name}: byproducts differ"
        )


def test_purple_science_budget_is_8_over_7_and_scope_variants_are_distinct(db):
    """Independent pinned-recipe arithmetic, not an optimizer-derived oracle.

    One science pack is three per craft.  Per science item, the pinned recipes
    require 52.5 iron plates (125/3 from steel, 25/3 from circuits, and 5/2
    from sticks), 115/6 copper plates, 20/3 plastic, and 35/3 stone.  Thus the
    60 iron-plate/s budget binds at 60 / (105/2) = 8/7 science/s.
    """
    request = {
        "inputs": {"stone": 30, "copper-plate": 30, "plastic-bar": 30, "iron-plate": 60},
        "outputs": {"production-science-pack": {"ratio": 1}},
        "machines": {"assembler": "assembling-machine-2"},
        "modules": {},
        "objective": {"kind": "maximize_ratio"},
    }
    expected_per_science = {"iron-plate": 52.5, "copper-plate": 115 / 6,
                             "plastic-bar": 20 / 3, "stone": 35 / 3}
    assert min(request["inputs"][item] / need for item, need in expected_per_science.items()) == pytest.approx(8 / 7)
    result = plan_production(request, db)
    assert result["outputs_per_s"]["production-science-pack"] == pytest.approx(8 / 7)
    assert result["inputs"]["iron-plate"]["used_per_s"] == pytest.approx(60)

    # An intermediate export is additional net demand, not silently consumed.
    intermediate = {
        **request,
        "outputs": {"production-science-pack": {"ratio": 1}, "steel-plate": {"rate": 1}},
    }
    with_export = plan_production(intermediate, db)
    assert with_export["outputs_per_s"]["steel-plate"] == pytest.approx(1)
    assert "steel-plate" in with_export["gross_production_per_s"]
    assert "steel-plate" in with_export["internal_consumption_per_s"]

    # Declared external steel intentionally stops the internal steel recipe.
    external_steel = {
        **request,
        "inputs": {**request["inputs"], "steel-plate": None},
    }
    external = plan_production(external_steel, db)
    assert "steel-plate" not in external["recipe_scope"]["recipes"]
    assert external["inputs"]["steel-plate"]["used_per_s"] > 0
