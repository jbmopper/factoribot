"""The solve spec: the contract between the LLM and the deterministic solver.

The LLM's job is to translate natural language ("purple science, assembly
machine 2, no modules") into one of these. The solver never guesses; anything
ambiguous is reported back so the model can fill it in.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy

# Categories an "assembler" choice applies to.
ASSEMBLING_CATEGORIES = frozenset(
    {"crafting", "basic-crafting", "advanced-crafting", "crafting-with-fluid"}
)


class OptionValidationError(Exception):
    """A category-scoped option cannot affect any recipe in this request."""

    def __init__(self, option: str, category: str, active_categories: set[str]):
        self.option = option
        self.category = category
        self.active_categories = sorted(active_categories)
        super().__init__(
            f"{option}: category '{category}' does not apply to an active recipe "
            f"(active categories: {self.active_categories})."
        )


def validate_category_options(spec: "SolveSpec", active_categories: set[str]) -> None:
    """Reject options that would otherwise be silently ignored.

    This is deliberately based on the active recipe set, rather than every
    category in the data.  A category key is meaningful only if it affects this
    calculation.  ``assembler`` remains the assembling-category alias and
    ``default`` remains the module/beacon fallback alias; machine defaults are
    selected by the database when no machine option applies.
    """
    for option in ("machines", "modules", "beacons"):
        values = getattr(spec, option)
        for category in values:
            applies = category in active_categories
            applies |= (
                category == "assembler"
                and bool(active_categories & ASSEMBLING_CATEGORIES)
            )
            applies |= (
                category == "default"
                and option != "machines"
                and bool(active_categories)
            )
            if not applies:
                raise OptionValidationError(option, category, active_categories)


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
    # items to force-treat as raw (free source; stop expansion here).
    raw: set[str] = field(default_factory=set)
    # extra recipes to force into the active set even if they add a second
    # producer for an item (e.g. oil cracking). The solver balances them.
    use_recipes: list[str] = field(default_factory=list)
    # items allowed to be surplus (free sink) instead of forcing a balance,
    # e.g. dump excess heavy-oil rather than cracking it all.
    byproducts: set[str] = field(default_factory=set)
    # crafting category (or "assembler") -> beacon setup affecting those machines:
    #   {"count": N, "modules": [module names per beacon], "beacon": optional name}
    beacons: dict[str, dict] = field(default_factory=dict)

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

    def beacons_for(self, category: str) -> dict | None:
        if category in self.beacons:
            return self.beacons[category]
        if category in ASSEMBLING_CATEGORIES and "assembler" in self.beacons:
            return self.beacons["assembler"]
        return self.beacons.get("default")

    def to_dict(self) -> dict:
        """Return a JSON-ready request that can be replayed by ``solve``."""
        return {
            "targets": [{"name": t.name, "rate": t.rate} for t in self.targets],
            "machines": deepcopy(self.machines),
            "modules": deepcopy(self.modules),
            "recipes": deepcopy(self.recipes),
            "raw": sorted(self.raw),
            "use_recipes": list(self.use_recipes),
            "byproducts": sorted(self.byproducts),
            "beacons": deepcopy(self.beacons),
        }

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
            use_recipes=list(d.get("use_recipes", [])),
            byproducts=set(d.get("byproducts", [])),
            beacons={k: dict(v) for k, v in d.get("beacons", {}).items()},
        )
