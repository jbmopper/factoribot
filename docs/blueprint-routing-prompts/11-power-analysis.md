# 11 — Distinguish power coverage, wiring, and available generation

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 08. Own
`power_analysis.py`, power fixtures/tests, and an extension note. Coordinate
additive prototype properties and viewer/tool integration with their owners.

Freeze a small supported pole/machine set from the pilot. Determine footprint
coverage using versioned geometry, preserve explicit copper-wire connections,
and compute connected networks. Infer omitted wires only when a documented
placement rule and the available data justify it; preserve uncertainty otherwise.

Report separately whether a machine is in supply coverage, whether its covering
poles form a network, whether external power is declared, and the supported load
estimate. A blueprint without a generator can be externally powered. A blueprint
with a generator does not establish its live fuel, steam, temperature, or output.
Do not turn unresolved power into a certified zero-production result.

Acceptance: independently recorded cases cover edge-of-coverage machines,
non-square footprints, explicit disconnected networks, long wires within/outside
supported reach, declared external power, and unsupported modded poles. Cover
active crafting consumption and any explicitly supported idle loads separately;
avoid double-counting a machine covered by multiple poles. Verify translation
and supported rotation invariance and retain original wire records on round-trip.

Keep this analysis advisory unless sufficient supply modeling justifies a power
constraint in the production model. Reuse existing machine effects and label
excluded infrastructure. Run focused tests and `make test`, and exercise the
coordinated public result additions. Do not implement fluid/steam simulation,
automatic rewiring, or generation dispatch in this assignment.
