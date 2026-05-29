import pytest

from factoribot.agent import run_agent
from factoribot.gamedata import load_database
from factoribot.llm.base import LLMResponse, ToolCall
from factoribot.llm.fake import FakeClient


@pytest.fixture(scope="module")
def db():
    try:
        return load_database()
    except FileNotFoundError:
        pytest.skip("data-raw-dump.json not present; run `factorio --dump-data`")


def test_agent_resolves_ambiguity_then_answers(db):
    base_spec = {
        "targets": [{"name": "production-science-pack", "rate": 1.0}],
        "machines": {"assembler": "assembling-machine-2"},
    }
    script = [
        # 1) first attempt omits the oil choice -> tool reports ambiguity
        LLMResponse(tool_calls=[ToolCall("a", "solve_production", dict(base_spec))]),
        # 2) model resolves it by pinning the recipe
        LLMResponse(tool_calls=[ToolCall(
            "b", "solve_production",
            {**base_spec, "recipes": {"petroleum-gas": "basic-oil-processing"}},
        )]),
        # 3) final natural-language answer
        LLMResponse(text="For 1/s purple science with AM2 and no modules you need ~10 assemblers."),
    ]
    events: list[tuple[str, dict]] = []
    res = run_agent(
        FakeClient(script), db, "purple science, AM2, no modules",
        on_event=lambda k, d: events.append((k, d)),
    )

    assert res.steps == 3
    assert "purple science" in res.text.lower()

    results = [d["output"] for (k, d) in events if k == "tool_result"]
    assert results[0]["error"] == "ambiguous_recipe"
    assert results[0]["item"] == "petroleum-gas"
    assert results[1]["ok"] is True
    assert results[1]["summary"]["machines"]["assembling-machine-2"] > 0
