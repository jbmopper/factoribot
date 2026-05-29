"""The solve spec: the contract between the LLM and the deterministic solver.

The LLM's job is to translate natural language ("purple science, assembly
machine 2, no modules") into one of these. The solver never guesses; anything
ambiguous is reported back so the model can fill it in.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Categories an "assembler" choice applies to.
ASSEMBLING_CATEGORIES = frozenset(
    {"crafting", "basic-crafting", "advanced-crafting", "crafting-with-fluid"}
)


@dataclass
class Target:
    name: str
    rate: float  # items per second


@dataclass
class SolveSpec:
    targets: list[Target]
    # crafting category -> machine name. Special key "assembler" applies to all
    # assembling categories.
    machines: dict[str, str] = field(default_factory=dict)
    # crafting category -> list of module item names (empty = no modules).
    modules: dict[str, list[str]] = field(default_factory=dict)
    # item -> recipe name, to disambiguate items with multiple producers.
    recipes: dict[str, str] = field(default_factory=dict)
    # items to force-treat as raw (stop expansion here).
    raw: set[str] = field(default_factory=set)

    def machine_for(self, category: str) -> str | None:
        if category in self.machines:
            return self.machines[category]
        if category in ASSEMBLING_CATEGORIES and "assembler" in self.machines:
            return self.machines["assembler"]
        return None

    def modules_for(self, category: str) -> list[str]:
        if category in self.modules:
            return self.modules[category]
        if category in ASSEMBLING_CATEGORIES and "assembler" in self.modules:
            return self.modules["assembler"]
        return self.modules.get("default", [])

    @classmethod
    def from_dict(cls, d: dict) -> "SolveSpec":
        targets = [
            Target(name=t["name"], rate=float(t.get("rate", 1.0)))
            for t in d.get("targets", [])
        ]
        return cls(
            targets=targets,
            machines=dict(d.get("machines", {})),
            modules={k: list(v) for k, v in d.get("modules", {}).items()},
            recipes=dict(d.get("recipes", {})),
            raw=set(d.get("raw", [])),
        )
