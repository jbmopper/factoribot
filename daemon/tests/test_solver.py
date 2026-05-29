import json
import math
from pathlib import Path

import pytest

from factoribot import report
from factoribot.gamedata import load_database
from factoribot.solver import (
    AmbiguousRecipe,
    Infeasible,
    Overconstrained,
    Underdetermined,
    evaluate,
    solve,
)
from factoribot.spec import SolveSpec

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_spec(name: str) -> SolveSpec:
    with open(EXAMPLES / name) as f:
        return SolveSpec.from_dict(json.load(f))


@pytest.fixture(scope="module")
def db():
    try:
        return load_database()
    except FileNotFoundError:
        pytest.skip("data-raw-dump.json not present; run `factorio --dump-data`")


def test_purple_am2_nomods(db):
    res = solve(load_spec("purple_am2_nomods.json"), db)
    by_item = {u.item: u for u in res.uses}

    sci = by_item["production-science-pack"]
    assert sci.machine == "assembling-machine-2"
    assert math.isclose(sci.machines, 21 / (3 * 0.75), rel_tol=1e-9)

    # Machine choice is per recipe category: smelting -> furnace, chemistry -> plant.
    assert by_item["iron-plate"].machine == "electric-furnace"
    assert by_item["plastic-bar"].machine == "chemical-plant"
    assert by_item["petroleum-gas"].machine == "oil-refinery"

    # crude-oil: petroleum demand 66.667/s -> 1.4815 refinery crafts -> 148.148/s crude.
    assert math.isclose(res.raw["crude-oil"], 148.148, rel_tol=1e-3)
    assert math.isclose(res.raw["iron-ore"], 52.5, rel_tol=1e-3)
    assert not res.warnings


def test_ambiguous_without_override(db):
    spec = SolveSpec.from_dict({
        "targets": [{"name": "production-science-pack", "rate": 1.0}],
        "machines": {"assembler": "assembling-machine-2"},
    })
    with pytest.raises(AmbiguousRecipe) as ei:
        solve(spec, db)
    assert ei.value.item == "petroleum-gas"


def _by_recipe(res):
    return {u.recipe: u for u in res.uses}


def test_oil_cracking_nets_byproducts(db):
    """advanced oil + cracking -> pure petroleum, heavy/light netted to zero."""
    spec = SolveSpec.from_dict({
        "targets": [{"name": "petroleum-gas", "rate": 100.0}],
        "recipes": {"heavy-oil": "advanced-oil-processing"},
        "use_recipes": ["heavy-oil-cracking", "light-oil-cracking"],
    })
    res = solve(spec, db)
    used = _by_recipe(res)
    assert set(used) == {
        "advanced-oil-processing",
        "heavy-oil-cracking",
        "light-oil-cracking",
    }
    a = 100 / 97.5  # advanced-oil crafts/s for 100/s petroleum with full cracking
    assert math.isclose(res.raw["crude-oil"], 100 * a, rel_tol=1e-6)
    assert math.isclose(res.raw["water"], 132.5 * a, rel_tol=1e-6)
    assert "heavy-oil" not in res.byproducts
    assert "light-oil" not in res.byproducts
    assert "petroleum-gas" not in res.raw
    assert not res.warnings


def test_advanced_oil_reports_surplus_byproducts(db):
    spec = SolveSpec.from_dict({
        "targets": [{"name": "petroleum-gas", "rate": 100.0}],
        "recipes": {"petroleum-gas": "advanced-oil-processing"},
    })
    res = solve(spec, db)
    a = 100 / 55
    assert math.isclose(res.byproducts["heavy-oil"], 25 * a, rel_tol=1e-6)
    assert math.isclose(res.byproducts["light-oil"], 45 * a, rel_tol=1e-6)
    assert math.isclose(res.raw["crude-oil"], 100 * a, rel_tol=1e-6)


def test_overconstrained_without_cracking(db):
    spec = SolveSpec.from_dict({
        "targets": [
            {"name": "petroleum-gas", "rate": 10.0},
            {"name": "light-oil", "rate": 10.0},
            {"name": "heavy-oil", "rate": 10.0},
        ],
        "recipes": {
            "petroleum-gas": "advanced-oil-processing",
            "light-oil": "advanced-oil-processing",
            "heavy-oil": "advanced-oil-processing",
        },
    })
    with pytest.raises(Overconstrained):
        solve(spec, db)


def test_underdetermined_two_producers(db):
    spec = SolveSpec.from_dict({
        "targets": [{"name": "petroleum-gas", "rate": 100.0}],
        "use_recipes": ["basic-oil-processing", "advanced-oil-processing"],
        "byproducts": ["heavy-oil", "light-oil"],
    })
    with pytest.raises(Underdetermined):
        solve(spec, db)


def test_infeasible_negative_rate(db):
    # heavy=10 forces advanced high (22 petro), but petro target is only 5,
    # so basic-oil would need a negative rate.
    spec = SolveSpec.from_dict({
        "targets": [
            {"name": "heavy-oil", "rate": 10.0},
            {"name": "petroleum-gas", "rate": 5.0},
        ],
        "recipes": {"heavy-oil": "advanced-oil-processing"},
        "use_recipes": ["basic-oil-processing"],
        "byproducts": ["light-oil"],
    })
    with pytest.raises(Infeasible):
        solve(spec, db)


def test_multiple_targets_share_intermediate(db):
    spec = SolveSpec.from_dict({
        "targets": [
            {"name": "electronic-circuit", "rate": 1.0},
            {"name": "copper-cable", "rate": 2.0},
        ],
        "machines": {"assembler": "assembling-machine-2"},
    })
    res = solve(spec, db)
    used = _by_recipe(res)
    # copper-cable: 3/s into circuits + 2/s exported = 5/s -> 2.5 crafts/s (yield 2)
    assert math.isclose(used["copper-cable"].crafts_per_s, 2.5, rel_tol=1e-9)
    assert math.isclose(used["electronic-circuit"].crafts_per_s, 1.0, rel_tol=1e-9)


def test_belt_counts_solid_vs_fluid(db):
    bc = report.belt_counts(90.0, db, "iron-plate")
    assert math.isclose(bc["express-transport-belt"], 2.0, rel_tol=1e-9)
    assert math.isclose(bc["transport-belt"], 6.0, rel_tol=1e-9)
    # fluids don't go on belts
    assert report.belt_counts(100.0, db, "petroleum-gas") == {}


def test_beacons_speed_up_machines(db):
    base = {
        "targets": [{"name": "electronic-circuit", "rate": 10.0}],
        "machines": {"assembler": "assembling-machine-3"},
    }
    r0 = solve(SolveSpec.from_dict(base), db)
    m0 = next(u.machines for u in r0.uses if u.recipe == "electronic-circuit")

    spec = dict(base)
    spec["beacons"] = {
        "assembler": {"count": 8, "modules": ["speed-module-3", "speed-module-3"]}
    }
    r1 = solve(SolveSpec.from_dict(spec), db)
    m1 = next(u.machines for u in r1.uses if u.recipe == "electronic-circuit")

    beacon = db.default_beacon()
    prof = beacon.profile[7]  # 8 beacons -> index 7
    speed_bonus = 8 * beacon.distribution_effectivity * prof * (2 * 0.5)  # 2x speed-3
    assert math.isclose(m0 / m1, 1.0 + speed_bonus, rel_tol=1e-6)
    assert r1.warnings  # beacon caveat surfaced


def test_evaluate_throughput_bottleneck(db):
    # circuits need 1 iron-plate + 1.5 copper-plate each. With 60 iron + 30 copper,
    # copper limits to 30/1.5 = 20/s; iron is only 33% used.
    spec = SolveSpec.from_dict({
        "targets": [{"name": "electronic-circuit", "rate": 1.0}],
        "machines": {"assembler": "assembling-machine-2"},
        "raw": ["iron-plate", "copper-plate"],
    })
    ev = evaluate(spec, db, {"iron-plate": 60.0, "copper-plate": 30.0})
    assert ev.bottleneck == "copper-plate"
    assert math.isclose(ev.output_per_s, 20.0, rel_tol=1e-9)
    idle = {i.item: i.idle for i in ev.inputs}
    assert math.isclose(idle["iron-plate"], 40.0, rel_tol=1e-9)
    assert math.isclose(idle["copper-plate"], 0.0, abs_tol=1e-9)
