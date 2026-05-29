"""OpenAI Chat Completions adapter (function calling)."""
from __future__ import annotations

import json

from .base import LLMResponse, Message, ToolCall
from .keys import load_key

DEFAULT_MODEL = "gpt-4o"


class OpenAIClient:
    def __init__(self, model: str | None = None, key_file: str | None = None):
        from openai import OpenAI  # lazy: only needed when this provider is used

        self.model = model or DEFAULT_MODEL
        self._client = OpenAI(
            api_key=load_key("OPENAI_API_KEY", "openai_api_key", key_file)
        )

    @staticmethod
    def _messages(system: str, messages: list[Message]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            if m.role == "assistant":
                msg: dict = {"role": "assistant", "content": m.content or None}
                if m.tool_calls:
                    msg["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in m.tool_calls
                    ]
                out.append(msg)
            elif m.role == "tool":
                out.append(
                    {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
                )
            else:
                out.append({"role": "user", "content": m.content})
        return out

    @staticmethod
    def _tools(tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]

    def complete(self, system: str, messages: list[Message], tools: list[dict]) -> LLMResponse:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=self._messages(system, messages),
            tools=self._tools(tools),
            tool_choice="auto",
            temperature=0,
        )
        msg = resp.choices[0].message
        calls: list[ToolCall] = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return LLMResponse(text=msg.content or "", tool_calls=calls)
