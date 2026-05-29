"""Normalized data model for the solver.

These are thin, solver-friendly views over Factorio's ``data.raw`` prototypes.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stack:
    """An ingredient or product entry."""
    name: str
    amount: float
    type: str = "item"  # "item" or "fluid"


@dataclass
class Recipe:
    name: str
    category: str
    energy: float  # seconds at crafting_speed 1.0 (energy_required)
    ingredients: list[Stack]
    results: list[Stack]
    allow_productivity: bool = False

    def yield_of(self, item: str) -> float:
        return sum(s.amount for s in self.results if s.name == item)

    @property
    def main_product(self) -> str | None:
        return self.results[0].name if self.results else None


@dataclass
class Machine:
    name: str
    speed: float
    categories: frozenset[str]
    energy_w: float
    module_slots: int = 0
    allowed_effects: frozenset[str] = field(default_factory=frozenset)
    source_type: str = "electric"


@dataclass
class Module:
    name: str
    category: str
    effect: dict[str, float]


@dataclass
class Database:
    recipes: dict[str, Recipe]
    machines: dict[str, Machine]
    modules: dict[str, Module]
    producers: dict[str, list[str]]  # item -> recipe names that output it
    items: dict[str, dict]           # raw item prototype (for stack sizes, names)
    fluids: set[str]

    def machines_for_category(self, category: str) -> list[Machine]:
        return [m for m in self.machines.values() if category in m.categories]

    def default_machine(self, category: str) -> Machine | None:
        cands = self.machines_for_category(category)
        if not cands:
            return None
        # Prefer the most capable: more module slots, then faster, then name.
        return max(cands, key=lambda m: (m.module_slots, m.speed, m.name))
