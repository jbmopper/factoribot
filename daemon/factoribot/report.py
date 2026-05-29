"""Human-readable rendering of a solver Result."""
from __future__ import annotations

import math
from collections import defaultdict

from .solver import Result
from .spec import SolveSpec


def _fmt(x: float) -> str:
    if x == 0:
        return "0"
    if abs(x) >= 100:
        return f"{x:,.0f}"
    if abs(x) >= 1:
        return f"{x:.2f}"
    return f"{x:.3g}"


def _power(w: float) -> str:
    for unit, scale in (("GW", 1e9), ("MW", 1e6), ("kW", 1e3)):
        if abs(w) >= scale:
            return f"{w / scale:.2f} {unit}"
    return f"{w:.0f} W"


def render(result: Result, spec: SolveSpec) -> str:
    lines: list[str] = []
    tgt = ", ".join(f"{_fmt(t.rate)}/s {t.name}" for t in spec.targets)
    lines.append(f"Target: {tgt}")
    lines.append("")

    uses = sorted(result.uses, key=lambda u: (-u.machines, u.item))
    name_w = max((len(u.item) for u in uses), default=4)
    rec_w = max((len(u.recipe) for u in uses), default=6)
    mac_w = max((len(u.machine) for u in uses), default=7)

    header = f"  {'item':<{name_w}}  {'recipe':<{rec_w}}  {'/s':>8}  {'machine':<{mac_w}}  {'count':>10}"
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))
    machine_totals: dict[str, float] = defaultdict(float)
    for u in uses:
        whole = math.ceil(u.machines - 1e-9)
        machine_totals[u.machine] += whole
        count = f"{whole:>4} ({u.machines:.2f})"
        lines.append(
            f"  {u.item:<{name_w}}  {u.recipe:<{rec_w}}  {_fmt(u.crafts_per_s):>8}  "
            f"{u.machine:<{mac_w}}  {count:>10}"
        )

    lines.append("")
    lines.append("Raw inputs /s:")
    if result.raw:
        for name, rate in sorted(result.raw.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {name:<28} {_fmt(rate):>10}")
    else:
        lines.append("  (none)")

    if result.byproducts:
        lines.append("")
        lines.append("Byproducts /s:")
        for name, rate in sorted(result.byproducts.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {name:<28} {_fmt(rate):>10}")

    lines.append("")
    lines.append("Machines (whole, built):")
    for name, count in sorted(machine_totals.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {name:<28} {int(count):>6}")

    lines.append("")
    lines.append(f"Total electric power (active): {_power(result.total_power_w)}")

    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in result.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)
