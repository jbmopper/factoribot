import json
import math
from pathlib import Path

import pytest

from factoribot.gamedata import load_database
from factoribot.solver import AmbiguousRecipe, solve
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
