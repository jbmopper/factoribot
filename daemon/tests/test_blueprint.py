from pathlib import Path

import pytest

from factoribot.blueprint import (
    BlueprintError,
    MachineGroup,
    _parse_modules,
    decode_blueprint_string,
    iter_blueprints,
    summarize_blueprint,
)
from factoribot.gamedata import load_database

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# A tiny 1.x-shaped blueprint: one assembling-machine-2 with two prod-3 modules
# and no recipe set. Exercises the version-byte + base64 + zlib + JSON path and
# the dict-style ("items") module request, with no game data needed.
SMALL_BP = (
    "0eNp9j80OgjAQhN9lzq0RFNC+ijGGnw1uQhdCi5GQvrstXjx5m9mfb2c3NMNC08ziYTZwO4q"
    "DuW1w3Es9pJpfJ4IBe7JQkNomVztHthlYem3r9slCOkdQYOnoDZOFuwKJZ8/05e1mfchiG5r"
    "jwH+SwjS6uDxKShCB+nQoFNYoskOR7sQ0LvWmeeyW1vMr0rWNeiB9gslDSrBnNj8vKrxodjs2"
    "v2Tn6nytyio7lkUZwgd0Blhx"
)


def test_decode_compressed_string():
    decoded = decode_blueprint_string(SMALL_BP)
    bps = iter_blueprints(decoded)
    assert len(bps) == 1
    ents = bps[0]["entities"]
    assert ents[0]["name"] == "assembling-machine-2"
    assert "recipe" not in ents[0]  # recipe genuinely unset
    assert _parse_modules(ents[0]) == {"productivity-module-3": 2}


def test_decode_handles_pasted_code_fence():
    decoded = decode_blueprint_string(f"```\n{SMALL_BP}\n```")
    assert iter_blueprints(decoded)[0]["entities"][0]["name"] == "assembling-machine-2"


def test_decode_raw_json():
    decoded = decode_blueprint_string('{"blueprint": {"entities": []}}')
    assert iter_blueprints(decoded) == [{"entities": []}]


def test_decode_garbage_raises():
    with pytest.raises(BlueprintError):
        decode_blueprint_string("not a blueprint")
    with pytest.raises(BlueprintError):
        decode_blueprint_string("")


def test_iter_blueprints_flattens_book():
    book = {
        "blueprint_book": {
            "blueprints": [
                {"index": 0, "blueprint": {"entities": [{"name": "a"}]}},
                {"index": 1, "blueprint": {"entities": [{"name": "b"}]}},
            ]
        }
    }
    bps = iter_blueprints(book)
    assert [b["entities"][0]["name"] for b in bps] == ["a", "b"]


def test_parse_modules_2_0_shape():
    entity = {
        "items": [
            {
                "id": {"name": "speed-module-3", "quality": "normal"},
                "items": {"in_inventory": [{"count": 2}, {"count": 1}]},
            }
        ]
    }
    assert _parse_modules(entity) == {"speed-module-3": 3}


@pytest.fixture(scope="module")
def db():
    try:
        return load_database()
    except FileNotFoundError:
        pytest.skip("data-raw-dump.json not present; run `factorio --dump-data`")


def test_summarize_wip_science(db):
    s = (FIXTURES / "wip_science.txt").read_text()
    summ = summarize_blueprint(iter_blueprints(decode_blueprint_string(s))[0], db)

    assert summ.total_entities == 2771
    by_recipe = {(g.machine, g.recipe): g.count for g in summ.groups}
    assert by_recipe[("assembling-machine-2", "production-science-pack")] == 120
    assert by_recipe[("assembling-machine-2", "electric-furnace")] == 32
    assert by_recipe[("assembling-machine-2", "advanced-circuit")] == 1
    # Furnaces auto-pick their recipe, so a blueprint never stores one.
    assert summ.no_recipe == {"electric-furnace": 76}
    assert summ.belts.get("fast-transport-belt") == 1738
    # Groups come back largest-first.
    assert [g.count for g in summ.groups] == sorted(
        (g.count for g in summ.groups), reverse=True
    )


def test_summarize_ignores_empty_entities(db):
    summ = summarize_blueprint({"entities": []}, db)
    assert summ.groups == [] and summ.total_entities == 0
    assert isinstance(summ, type(summ))  # smoke


def test_machinegroup_defaults():
    g = MachineGroup(machine="assembling-machine-2", recipe="iron-gear-wheel", count=4)
    assert g.modules == {}
