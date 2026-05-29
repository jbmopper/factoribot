"""UDP daemon for the in-game mod.

The Factorio mod (launched with ``--enable-lua-udp=<gameport>``) sends a JSON
request ``{id, query, player}`` to this server's port. We run the agent and
reply ``{id, text}`` to the packet's source address (the game's UDP port), which
the mod drains via ``helpers.recv_udp()``.

Each request is handled on its own thread so a slow LLM call doesn't block the
socket. All traffic is localhost-only (matching Factorio's UDP sockets).
"""
from __future__ import annotations

import json
import socket
import threading

from .agent import run_agent
from .gamedata import load_database
from .llm import make_client
from .llm.base import Message

# UDP datagram safety margin (Factorio's recv buffer is 256KB; a single
# datagram should stay well under the ~64KB IPv4 limit).
_MAX_REPLY_BYTES = 60000


class Sessions:
    """Per-player conversation memory so follow-ups ('what about AM3?') chain.

    The stored state is the LLM message history; the structured spec lives inside
    the last tool call, so the model just emits a delta. History is bounded to
    the most recent ``max_user_turns`` exchanges, always trimmed at a user-message
    boundary to keep the assistant/tool-result pairing valid for the API.
    """

    def __init__(self, max_user_turns: int = 12):
        self._d: dict[str, list[Message]] = {}
        self._lock = threading.Lock()
        self.max_user_turns = max_user_turns

    def get(self, key: str) -> list[Message]:
        with self._lock:
            return list(self._d.get(key, []))

    def set(self, key: str, messages: list[Message]) -> None:
        trimmed = self._trim(messages)
        with self._lock:
            self._d[key] = trimmed

    def reset(self, key: str) -> None:
        with self._lock:
            self._d.pop(key, None)

    def _trim(self, messages: list[Message]) -> list[Message]:
        user_idxs = [i for i, m in enumerate(messages) if m.role == "user"]
        if len(user_idxs) > self.max_user_turns:
            start = user_idxs[len(user_idxs) - self.max_user_turns]
            return list(messages[start:])
        return list(messages)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 25001,
    provider: str = "openai",
    model: str | None = None,
    key_file: str | None = None,
    data: str | None = None,
    verbose: bool = False,
) -> None:
    db = load_database(data)
    client = make_client(provider, model, key_file=key_file)
    sessions = Sessions()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(
        f"factoribot daemon listening on {host}:{port} "
        f"(provider={provider}, model={model or 'default'})",
        flush=True,
    )

    def handle(raw: bytes, addr: tuple[str, int]) -> None:
        try:
            req = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        rid = req.get("id")
        query = str(req.get("query", "")).strip()
        player = str(req.get("player", "?"))
        if req.get("reset"):
            sessions.reset(player)
            if verbose:
                print(f"<- [{rid}] reset session for player {player}", flush=True)
            if not query:
                _send({"id": rid, "text": "(started a new conversation)"}, addr)
                return
        if verbose:
            print(f"<- [{rid}] {query!r} from {addr} (player {player})", flush=True)
        if not query:
            return
        try:
            result = run_agent(client, db, query, history=sessions.get(player))
            sessions.set(player, result.messages)
            text = result.text
        except Exception as e:  # never let a request kill the daemon
            text = f"error: {type(e).__name__}: {e}"
        _send({"id": rid, "text": text}, addr)

    def _send(obj: dict, addr: tuple[str, int]) -> None:
        rid = obj.get("id")
        text = obj.get("text", "")
        reply = json.dumps(obj).encode("utf-8")
        if len(reply) > _MAX_REPLY_BYTES:
            text = text[: _MAX_REPLY_BYTES - 1000] + "\n…(truncated)"
            reply = json.dumps({"id": rid, "text": text}).encode("utf-8")
        sock.sendto(reply, addr)
        if verbose:
            print(f"-> [{rid}] {len(reply)} bytes to {addr}", flush=True)

    try:
        while True:
            raw, addr = sock.recvfrom(65535)
            threading.Thread(target=handle, args=(raw, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nshutting down.", flush=True)
    finally:
        sock.close()
