import json
import socket
import threading
import time

import pytest

from factoribot import server
from factoribot.agent import AgentResult
from factoribot.gamedata import load_database
from factoribot.llm.base import Message


@pytest.fixture
def daemon(monkeypatch):
    """A real UDP daemon with the LLM faked out (no network/key needed)."""
    try:
        load_database()
    except FileNotFoundError:
        pytest.skip("data-raw-dump.json not present; run `factorio --dump-data`")

    seen_history_lens: list[int] = []

    def fake_make_client(*a, **k):
        return object()

    def fake_run_agent(client, db, query, *, history=None, **k):
        seen_history_lens.append(len(history or []))
        msgs = list(history or [])
        msgs.append(Message(role="user", content=query))
        msgs.append(Message(role="assistant", content=f"echo:{query}"))
        return AgentResult(text=f"echo:{query}", messages=msgs, steps=1)

    monkeypatch.setattr(server, "make_client", fake_make_client)
    monkeypatch.setattr(server, "run_agent", fake_run_agent)

    port = 25097
    t = threading.Thread(target=server.serve, kwargs={"port": port}, daemon=True)
    t.start()
    time.sleep(0.4)  # let it bind
    return port, seen_history_lens


def _roundtrip(port: int, obj: dict, timeout: float = 2.0) -> dict:
    c = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    c.settimeout(timeout)
    try:
        c.sendto(json.dumps(obj).encode("utf-8"), ("127.0.0.1", port))
        data, _ = c.recvfrom(65535)
    finally:
        c.close()
    return json.loads(data.decode("utf-8"))


def test_session_memory_and_reset(daemon):
    port, history_lens = daemon

    r1 = _roundtrip(port, {"id": 1, "query": "a", "player": "7"})
    assert r1["text"] == "echo:a"
    assert history_lens[-1] == 0  # first turn, no history

    r2 = _roundtrip(port, {"id": 2, "query": "b", "player": "7"})
    assert r2["text"] == "echo:b"
    assert history_lens[-1] >= 2  # carried the first exchange

    # A different player has an independent (empty) session.
    _roundtrip(port, {"id": 3, "query": "x", "player": "9"})
    assert history_lens[-1] == 0

    # Reset clears player 7's history.
    rr = _roundtrip(port, {"id": 4, "reset": True, "player": "7"})
    assert "new conversation" in rr["text"].lower()

    r3 = _roundtrip(port, {"id": 5, "query": "c", "player": "7"})
    assert history_lens[-1] == 0  # memory was wiped
