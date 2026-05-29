"""Human-readable rendering of a solver Result."""
from __future__ import annotations

import math
from collections import defaultdict

from .model import Database
from .solver import EvalResult, Result
from .spec import SolveSpec, Target


def _fmt(x: float) -> str:
    if x == 0:
        return "0"
    if abs(x) >= 100:
        return f"{x:,.0f}"
    if abs(x) >= 1:
        return f"{x:.2f}"
    return f"{x:.3g}"


def _belt_label(name: str) -> str:
    s = name.replace("-transport-belt", "").replace("transport-belt", "")
    return s or "belt"


def belt_counts(rate: float, db: Database, item: str) -> dict[str, float]:
    """Belt counts per tier for a solid item flow ({} for fluids / no belts)."""
    if item in db.fluids:
        return {}
    return {name: rate / per for name, per in db.belt_tiers() if per > 0}


def _belt_note(rate: float, db: Database, item: str) -> str:
    """Inline annotation using the fastest belt tier."""
    tiers = db.belt_tiers()
    if item in db.fluids or not tiers or tiers[-1][1] <= 0:
        return ""
    name, per = tiers[-1]
    return f"   ({rate / per:.2f} {_belt_label(name)})"


def _power(w: float) -> str:
    for unit, scale in (("GW", 1e9), ("MW", 1e6), ("kW", 1e3)):
        if abs(w) >= scale:
            return f"{w / scale:.2f} {unit}"
    return f"{w:.0f} W"


def render(result: Result, spec: SolveSpec, db: Database) -> str:
    lines: list[str] = []
    tgt = ", ".join(
        f"{_fmt(t.rate)}/s {t.name}{_belt_note(t.rate, db, t.name)}"
        for t in spec.targets
    )
    lines.append(f"Target: {tgt}")
    fastest = db.belt_tiers()[-1] if db.belts else None
    if fastest:
        lines.append(f"(belt counts shown for {fastest[0]} = {_fmt(fastest[1])}/s)")
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
            lines.append(f"  {name:<28} {_fmt(rate):>10}{_belt_note(rate, db, name)}")
    else:
        lines.append("  (none)")

    if result.byproducts:
        lines.append("")
        lines.append("Byproducts /s:")
        for name, rate in sorted(result.byproducts.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {name:<28} {_fmt(rate):>10}{_belt_note(rate, db, name)}")

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


def render_eval(ev: EvalResult, db: Database) -> str:
    lines: list[str] = []
    lines.append(
        f"Throughput of {ev.product} (input-limited): "
        f"{_fmt(ev.output_per_s)}/s{_belt_note(ev.output_per_s, db, ev.product)}"
    )
    lines.append(f"Bottleneck: {ev.bottleneck}")
    lines.append("")
    lines.append("Inputs:")
    name_w = max((len(i.item) for i in ev.inputs), default=4)
    for i in sorted(ev.inputs, key=lambda i: -i.used):
        util = (i.used / i.supplied * 100) if i.supplied else 0.0
        flag = "  <- limiting" if i.item == ev.bottleneck else ""
        lines.append(
            f"  {i.item:<{name_w}}  supplied {_fmt(i.supplied):>8}  "
            f"used {_fmt(i.used):>8}  idle {_fmt(i.idle):>8}  ({util:.0f}%){flag}"
        )
    lines.append("")
    sub = SolveSpec(targets=[Target(ev.product, ev.output_per_s)])
    lines.append(render(ev.result, sub, db))
    return "\n".join(lines)
