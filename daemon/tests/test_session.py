import pytest

from factoribot.agent import run_agent
from factoribot.gamedata import load_database
from factoribot.llm.base import LLMResponse, Message
from factoribot.llm.fake import FakeClient
from factoribot.server import Sessions


@pytest.fixture(scope="module")
def db():
    try:
        return load_database()
    except FileNotFoundError:
        pytest.skip("data-raw-dump.json not present; run `factorio --dump-data`")


def test_sessions_trim_keeps_recent_user_turns_at_boundary():
    msgs: list[Message] = []
    for n in range(5):
        msgs.append(Message(role="user", content=f"q{n}"))
        msgs.append(Message(role="assistant", content=f"a{n}"))
    s = Sessions(max_user_turns=3)
    s.set("p1", msgs)
    kept = s.get("p1")
    # 3 most recent exchanges, starting on a user message
    assert kept[0].role == "user"
    assert kept[0].content == "q2"
    assert sum(1 for m in kept if m.role == "user") == 3


def test_sessions_reset():
    s = Sessions()
    s.set("p1", [Message(role="user", content="hi")])
    assert s.get("p1")
    s.reset("p1")
    assert s.get("p1") == []


def test_run_agent_threads_history_and_records_answer(db):
    history = [
        Message(role="user", content="first question"),
        Message(role="assistant", content="first answer"),
    ]
    client = FakeClient([LLMResponse(text="second answer")])
    res = run_agent(client, db, "second question", history=history)

    # The model saw the prior history plus the new user turn.
    seen = client.seen[0]
    assert [m.content for m in seen] == [
        "first question",
        "first answer",
        "second question",
    ]
    # The returned transcript includes the new answer, so the session carries it.
    assert res.messages[-1].role == "assistant"
    assert res.messages[-1].content == "second answer"
    # History is not mutated in place.
    assert len(history) == 2
