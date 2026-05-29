"""Provider-neutral message/tool types and the LLMClient protocol."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Message:
    role: Literal["user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)  # assistant turns
    tool_call_id: str | None = None  # tool-result turns
    name: str | None = None  # tool name (for tool-result turns)


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


@runtime_checkable
class LLMClient(Protocol):
    """Minimal interface every provider adapter implements.

    ``tools`` is the provider-neutral schema list from ``tools.TOOL_SCHEMAS``;
    the adapter converts it to the provider's function-calling format.
    """

    def complete(
        self, system: str, messages: list[Message], tools: list[dict]
    ) -> LLMResponse: ...
