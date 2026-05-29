"""A scripted client for testing the agent loop with no network/key.

Provide a list of LLMResponse objects; each ``complete`` call returns the next
one. A response with tool_calls drives a tool round-trip; a text-only response
ends the loop.
"""
from __future__ import annotations

from collections.abc import Iterable

from .base import LLMResponse, Message


class FakeClient:
    def __init__(self, script: Iterable[LLMResponse]):
        self._script = list(script)
        self.i = 0
        self.seen: list[list[Message]] = []

    def complete(self, system: str, messages: list[Message], tools: list[dict]) -> LLMResponse:
        self.seen.append(list(messages))
        if self.i >= len(self._script):
            return LLMResponse(text="(fake client ran out of scripted responses)")
        resp = self._script[self.i]
        self.i += 1
        return resp
