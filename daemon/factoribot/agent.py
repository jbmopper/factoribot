"""The agent loop: natural language -> tool calls -> answer.

The LLM is the parser. It resolves nicknames, picks machines/modules, and emits
``solve_production`` calls; the deterministic tools do lookups and exact math.
Ambiguities come back as tool errors the model resolves on the next turn.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from .llm.base import LLMClient, Message
from .model import Database
from .tools import TOOL_SCHEMAS, Toolbox

SYSTEM_PROMPT = """\
You are factoribot, an in-game Factorio factory-design assistant.

Your job: turn the player's request into a `solve_production` call and report the
result. You are talking to a player who uses nicknames and shorthand.

Rules:
- Resolve names against the ACTUAL loaded data. The player says things like
  "purple science" or "red belt"; use `search_items` / `get_recipe` to confirm
  the real internal name (e.g. "production-science-pack") before solving. Rely on
  your Factorio knowledge to guess, but verify with tools.
- Machine choice is PER recipe category. If the player says "assembly machine 2",
  set machines={"assembler": "assembling-machine-2"} (this covers all assembling
  categories). Smelting (furnaces), chemistry (chemical plant), and oil (refinery)
  default automatically unless the player specifies otherwise.
- Modules: machines/modules maps a category (or "assembler") to a list of module
  item names. "no modules" => omit it.
- Default the target rate to 1/s unless the player gives one.
- If `solve_production` returns "ambiguous_recipe", call `get_recipe` on that item
  to see the options, pick the sensible one (ask the player only if it really
  matters, e.g. oil setup), and resend with recipes={item: recipe}.
- NEVER do the arithmetic yourself. Report the numbers from the tool: per-recipe
  machine counts, raw inputs/s, and total power. Be concise.
"""


@dataclass
class AgentResult:
    text: str
    messages: list[Message] = field(default_factory=list)
    steps: int = 0


def run_agent(
    client: LLMClient,
    db: Database,
    query: str,
    *,
    max_steps: int = 10,
    system: str = SYSTEM_PROMPT,
    on_event: Callable[[str, dict], None] | None = None,
) -> AgentResult:
    toolbox = Toolbox(db)
    messages: list[Message] = [Message(role="user", content=query)]

    def emit(kind: str, data: dict) -> None:
        if on_event:
            on_event(kind, data)

    for step in range(1, max_steps + 1):
        resp = client.complete(system, messages, TOOL_SCHEMAS)
        if not resp.tool_calls:
            emit("final", {"text": resp.text})
            return AgentResult(text=resp.text, messages=messages, steps=step)

        messages.append(
            Message(role="assistant", content=resp.text, tool_calls=resp.tool_calls)
        )
        for tc in resp.tool_calls:
            emit("tool_call", {"name": tc.name, "arguments": tc.arguments})
            output = toolbox.call(tc.name, tc.arguments)
            emit("tool_result", {"name": tc.name, "output": output})
            messages.append(
                Message(
                    role="tool",
                    content=json.dumps(output),
                    tool_call_id=tc.id,
                    name=tc.name,
                )
            )

    return AgentResult(
        text="(stopped: reached max steps without a final answer)",
        messages=messages,
        steps=max_steps,
    )
