"""Serial-chain operating rates conserve items and respect downstream blocking.

These run from synthetic recipe coefficients and the checked-in scenario, so
they need neither the pinned 2.0.77 dump nor a game capture. The arithmetic is
hand-derived in each test.
"""
from __future__ import annotations

from fractions import Fraction
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from factoribot.sustained_throughput import (
    ThroughputError,
    predict_operating_rate,
    seal_document,
)


ROOT = Path(__file__).resolve().parents[2]
SCENARIO = ROOT / "experiments/routing-measurements/scenarios/furnace-chain-base-2.0.77-v2.json"


def stack(name: str, amount) -> SimpleNamespace:
    return SimpleNamespace(type="item", name=name, amount=amount)


def database(recipes: dict, speed=2) -> SimpleNamespace:
    return SimpleNamespace(recipes=recipes, machines={"electric-furnace": SimpleNamespace(speed=speed)})


def scenario(*, recipes=None, export=None, supply=None) -> dict:
    """The checked-in serial scenario, optionally re-pointed and re-sealed."""
    document = json.loads(SCENARIO.read_text())
    if recipes is not None:
        for machine, name in zip(document["model"]["machines"], recipes):
            machine["recipe"] = name
    if export is not None:
        document["model"]["external_removal"]["item"] = export
    if supply is not None:
        document["model"]["external_supply"]["capacity_items_per_s"] = supply
    return seal_document(document, "scenario_hash")


def predict(document: dict, db) -> dict:
    return predict_operating_rate(
        document, database=db, recipe_data_sha256=document["recipe_data"]["sha256"])


def ledger_conserves(prediction: dict) -> bool:
    """Every item's accepted + produced must equal consumed + exported + stored."""
    items = prediction["items"]

    def rates(field):
        return {name: Fraction(value) for name, value in items[field].items()}

    names = set().union(*(rates(field) for field in (
        "accepted_import", "gross_production", "activity_consumption",
        "net_export", "stored_delta")))
    return all(
        rates("accepted_import").get(name, Fraction()) + rates("gross_production").get(name, Fraction())
        == (rates("activity_consumption").get(name, Fraction())
            + rates("net_export").get(name, Fraction())
            + rates("stored_delta").get(name, Fraction()))
        for name in names
    )


BASE_RECIPES = {
    # An electric furnace runs at speed 2, so its craft capacity is 2/energy.
    "iron-plate": SimpleNamespace(
        ingredients=[stack("iron-ore", 1)], results=[stack("iron-plate", 1)], energy=3.2),
    "steel-plate": SimpleNamespace(
        ingredients=[stack("iron-plate", 5)], results=[stack("steel-plate", 1)], energy=16),
}


def test_the_balanced_base_chain_is_unchanged():
    """2/3.2 = 5/8 plate crafts/s; 2/16 = 1/8 steel crafts/s needs exactly 5/8 plates."""
    prediction = predict(scenario(), database(BASE_RECIPES))

    assert [row["crafts_per_s"] for row in prediction["machines"]] == ["5/8", "1/8"]
    assert prediction["items"]["accepted_import"] == {"iron-ore": "5/8"}
    assert prediction["items"]["net_export"] == {"steel-plate": "1/8"}
    assert ledger_conserves(prediction)


def test_a_slower_downstream_machine_throttles_the_one_feeding_it():
    """Furnace 2 caps at 2/6.4 = 5/16 crafts/s, so furnace 1 blocks at 5/16 too.

    Reading each machine independently would report 5/8 and 5/16, leaving
    5/16 iron-plate/s produced, unconsumed and unexported.
    """
    recipes = dict(BASE_RECIPES)
    recipes["slow-widget"] = SimpleNamespace(
        ingredients=[stack("iron-plate", 1)], results=[stack("widget", 1)], energy=6.4)
    document = scenario(recipes=("iron-plate", "slow-widget"), export="widget")

    prediction = predict(document, database(recipes))

    assert [row["crafts_per_s"] for row in prediction["machines"]] == ["5/16", "5/16"]
    assert prediction["items"]["gross_production"] == {"iron-plate": "5/16", "widget": "5/16"}
    assert prediction["items"]["activity_consumption"] == {"iron-ore": "5/16", "iron-plate": "5/16"}
    assert prediction["items"]["net_export"] == {"widget": "5/16"}
    assert prediction["items"]["stored_delta"] == {}
    assert ledger_conserves(prediction)


def test_a_supply_limited_chain_scales_the_whole_chain_down():
    """1/4 ore/s is below furnace 1's 5/8 capacity: 1/4 plates feed 1/20 steel/s."""
    prediction = predict(scenario(supply="1/4"), database(BASE_RECIPES))

    assert [row["crafts_per_s"] for row in prediction["machines"]] == ["1/4", "1/20"]
    assert prediction["items"]["accepted_import"] == {"iron-ore": "1/4"}
    assert prediction["items"]["unused_supply"] == {"iron-ore": "0"}
    assert prediction["items"]["net_export"] == {"steel-plate": "1/20"}
    assert ledger_conserves(prediction)


def test_the_reported_capacity_still_names_each_machine_s_own_ceiling():
    """Throttling changes the rate, not the recorded capacity it was measured against."""
    prediction = predict(scenario(supply="1/4"), database(BASE_RECIPES))

    assert [row["craft_capacity_per_s"] for row in prediction["machines"]] == ["5/8", "1/8"]


@pytest.mark.parametrize("energy,amount", [(0, 1), (3.2, 0)])
def test_a_degenerate_recipe_is_rejected_instead_of_dividing_by_zero(energy, amount):
    recipes = dict(BASE_RECIPES)
    recipes["iron-plate"] = SimpleNamespace(
        ingredients=[stack("iron-ore", amount)], results=[stack("iron-plate", 1)], energy=energy)

    with pytest.raises(ThroughputError, match="nonpositive amount or energy"):
        predict(scenario(), database(recipes))
