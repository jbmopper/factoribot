from pathlib import Path

import pytest

from factoribot.blueprint import decode_blueprint_string, iter_blueprints, summarize_blueprint
from factoribot.bpanalyze import analyze_blueprint
from factoribot.gamedata import load_database

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def db():
    try:
        return load_database()
    except FileNotFoundError:
        pytest.skip("data-raw-dump.json not present; run `factorio --dump-data`")


@pytest.fixture(scope="module")
def wip(db):
    s = (FIXTURES / "wip_science.txt").read_text()
    return summarize_blueprint(iter_blueprints(decode_blueprint_string(s))[0], db)


def test_picks_science_and_advanced_circuit_bottleneck(db, wip):
    a = analyze_blueprint(wip, db)
    assert a.product == "production-science-pack"
    assert a.bottleneck == "advanced-circuit"
    # 1 AM2 (speed 0.75) on advanced-circuit (6s) = 0.125 crafts/s, fully saturated.
    by_recipe = {s.recipe: s for s in a.stages}
    assert by_recipe["advanced-circuit"].utilization == pytest.approx(1.0, rel=1e-6)
    # The 120 science + 32 furnace machines are starved -> tiny utilization.
    assert by_recipe["production-science-pack"].utilization < 0.05
    assert by_recipe["electric-furnace"].utilization < 0.05


def test_external_inputs_and_unmodeled(db, wip):
    a = analyze_blueprint(wip, db)
    # Internally produced items are NOT external feeds.
    assert "advanced-circuit" not in a.external_inputs
    assert "electric-furnace" not in a.external_inputs
    # Stages with zero machines placed are belted in. Electric-furnace recipe is
    # 10 steel + 10 stone-brick + 5 advanced-circuit; steel/stone come from outside.
    assert a.external_inputs["steel-plate"] == pytest.approx(0.25, rel=1e-3)
    assert a.external_inputs["stone-brick"] == pytest.approx(0.25, rel=1e-3)
    # Recipe-less furnaces are reported, not balanced.
    assert a.unmodeled_machines == {"electric-furnace": 76}


def test_output_scales_with_bottleneck(db, wip):
    a = analyze_blueprint(wip, db)
    # production-science-pack yields 3/craft; bottleneck caps crafts at 0.025/s.
    assert a.output_per_s == pytest.approx(0.075, rel=1e-3)
    assert a.total_power_w > 0


def test_explicit_product_override(db, wip):
    a = analyze_blueprint(wip, db, product="advanced-circuit")
    assert a.product == "advanced-circuit"
    # Asked directly for advanced-circuit: its own stage is the only/binding one.
    assert a.bottleneck == "advanced-circuit"
    assert a.output_per_s == pytest.approx(0.125, rel=1e-3)


def test_empty_blueprint(db):
    from factoribot.blueprint import BlueprintSummary

    empty = BlueprintSummary(None, [], {}, {}, {}, {}, {}, 0)
    a = analyze_blueprint(empty, db)
    assert a.product is None and a.output_per_s == 0.0
    assert any("No analyzable" in w for w in a.warnings)


def test_analyze_blueprint_tool(db):
    from factoribot.tools import Toolbox

    s = (FIXTURES / "wip_science.txt").read_text()
    out = Toolbox(db).call("analyze_blueprint", {"blueprint_string": s})
    assert out["ok"] is True
    assert out["summary"]["product"] == "production-science-pack"
    assert out["summary"]["bottleneck"] == "advanced-circuit"
    assert out["summary"]["unmodeled_machines"] == {"electric-furnace": 76}
    assert "Bottleneck: advanced-circuit" in out["report"]
    assert "External inputs" in out["report"]


def test_analyze_blueprint_tool_rejects_garbage(db):
    from factoribot.tools import Toolbox

    out = Toolbox(db).call("analyze_blueprint", {"blueprint_string": "not-a-blueprint"})
    assert out.get("error") == "bad_blueprint"


def test_render_blueprint_text(db, wip):
    from factoribot import report

    txt = report.render_blueprint(analyze_blueprint(wip, db), db)
    assert "production-science-pack" in txt
    assert "<- bottleneck" in txt
    assert "Not modeled" in txt
