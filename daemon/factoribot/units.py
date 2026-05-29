"""Parsing for Factorio's stringly-typed numbers (e.g. energy "150kW")."""
from __future__ import annotations

import re

_SI = {"": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "T": 1e12}
_ENERGY_RE = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*([kKMGT]?)\s*([WJ])\s*$")


def parse_energy(value) -> float:
    """Parse an energy/power string like "150kW" or "1.5MW" into watts.

    Factorio expresses ``energy_usage`` in watts (W). Joule (J) values are
    returned as-is numerically; callers that need per-tick energy can adjust.
    Numbers and ``None`` pass through sensibly.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    m = _ENERGY_RE.match(str(value))
    if not m:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    return float(m.group(1)) * _SI[m.group(2)]
