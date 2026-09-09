# 06 — Make the routing audit inspectable

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` once 00 provides
validated spatial/result examples. Use those samples while spatial/transport work proceeds.
Read the contract; do not derive numerical findings in JavaScript.

Own new `blueprint_view.py`, viewer assets under
`daemon/factoribot/blueprint_view_assets/`, viewer-specific tests, and demonstration
artifacts. Coordinate asset packaging changes with 07. Keep public CLI/MCP
registration and shared contracts out of this task.

Create a portable local map/report with pan/zoom, entity selection, lane/item route
overlays, a findings list, evidence highlighting, unsupported-entity visibility,
and explicit assumptions/bound labels. Use simple geometry and labels initially;
game sprite acquisition is not required. Keep large fixtures interactive without
injecting one heavyweight DOM element per graph edge.

Implement a complete manual assignment workflow: select an entity/port/lane,
declare a feed or export, reference its shared global budget, assign a compatible
furnace recipe, and export a request JSON file for the host to reanalyze. Imported
analysis results must be tied to their blueprint/request hashes. Clearly show when
edited assignments make the displayed analysis stale. Do not silently solve or
write source files from a read-only analysis call.

Acceptance: in an actual browser, open sample analyses, select a finding and verify
its exact entities/path are highlighted; select two ports sharing one budget;
export/reimport assignments without losing identity; detect stale/mismatched
results; test zoom/selection using 00's large synthetic layout. Conditional findings must remain
distinguishable without color alone. Never label a machine currently starved from
static evidence. Render hostile labels as inert text, including safely embedding
JSON containing closing-script sequences.

The renderer should accept data and return artifact contents; the host decides
where to write/open them. Capture representative screenshots and interaction
results. Component acceptance uses 00's fixtures; task 07 owns final end-to-end
acceptance using real spatial/graph/analysis outputs from 03–05 and the pilot.
Do not build automatic cleanup, a hosted site, accounts, telemetry, or
speculative dashboards. Reuse the same renderer for before/after reports later.
