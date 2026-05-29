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

Your job: turn the player's request into a tool call and report the result. You
are talking to a player who uses nicknames and shorthand. Use `solve_production`
for "how much do I need for N/s of X" and `evaluate_throughput` for "I can supply
these inputs -- how much X can I make / is my belt ratio good?".

Rules:
- Resolve names against the ACTUAL loaded data. The player says things like
  "purple science" or "red belt"; use `search_items` / `get_recipe` to confirm
  the real internal name (e.g. "production-science-pack") before solving. Rely on
  your Factorio knowledge to guess, but verify with tools.
- Machine choice is PER recipe category. If the player says "assembly machine 2",
  set machines={"assembler": "assembling-machine-2"} (this covers all assembling
  categories). Smelting (furnaces), chemistry (chemical plant), and oil (refinery)
  default automatically unless the player specifies otherwise.
- Modules: modules maps a category (or "assembler") to a list of module item
  names. "no modules" => omit it. For beacons, set beacons={category: {count: N,
  modules: [names per beacon]}} (e.g. 8 beacons of speed-module-3).
- Belts: the result reports throughput in belts. Use `list_belts` to turn a
  player's belt counts (e.g. "2 red belts") into items/s, or to name a flow's
  belt count back to them.
- Blueprints: if the player pastes a blueprint string or asks to analyze/check
  a blueprint, call `analyze_blueprint`. Summarize what it makes, the bottleneck
  stage and its utilization, the external inputs it must be fed, and any
  recipe-less machines. NEVER echo the blueprint string back.
- Default the target rate to 1/s unless the player gives one.
- The solver BALANCES the recipe set you choose; byproducts consumed elsewhere
  are netted automatically. Your job is to pick a coherent set of recipes.
- Resolve solver errors on the next call (use `get_recipe` to inspect options):
  - "ambiguous_recipe": pick the primary producer with recipes={item: recipe}.
  - "overconstrained": a recipe overproduces an item (classic: oil). Either add a
    consumer via use_recipes (e.g. heavy-oil-cracking, light-oil-cracking) to
    crack the surplus, or, if the player is fine wasting it, allow it via
    byproducts=[item]. For oil, prefer cracking unless told otherwise.
  - "underdetermined": you included a redundant recipe; drop one or pin demand.
  - "infeasible": a chosen recipe can't run; remove it.
- Oil tip: "advanced oil + cracking to pure petroleum" =
  recipes={"heavy-oil":"advanced-oil-processing"},
  use_recipes=["heavy-oil-cracking","light-oil-cracking"]. The simplest petroleum
  source is recipes={"petroleum-gas":"basic-oil-processing"}.
- NEVER do the arithmetic yourself. Report the numbers from the tool: per-recipe
  machine counts, raw inputs/s, byproducts, and total power. Be concise.
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
    history: list[Message] | None = None,
    max_steps: int = 10,
    system: str = SYSTEM_PROMPT,
    on_event: Callable[[str, dict], None] | None = None,
) -> AgentResult:
    toolbox = Toolbox(db)
    messages: list[Message] = list(history or [])
    messages.append(Message(role="user", content=query))

    def emit(kind: str, data: dict) -> None:
        if on_event:
            on_event(kind, data)

    for step in range(1, max_steps + 1):
        resp = client.complete(system, messages, TOOL_SCHEMAS)
        if not resp.tool_calls:
            messages.append(Message(role="assistant", content=resp.text))
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
