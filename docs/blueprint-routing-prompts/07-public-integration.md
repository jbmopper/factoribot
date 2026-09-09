# 07 — Integrate the first usable routing audit

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 01–06 are
available in this checkout. Read 00's contract and every prerequisite handoff.
Check the actual files and tests rather than accepting a completion claim.

Own integration changes in `tools.py`, `mcp_server.py`, `cli.py`, capability
metadata, `daemon/pyproject.toml` asset packaging, MCP/CLI integration tests,
README, and the Factoribot skill/references. Coordinate fixes in other owned
modules with their implementers; do not compensate for model defects in output
formatting or adapters.

Expose `inspect_blueprint_layout` and `analyze_blueprint_routes` with the agreed
strict request/result schemas. Preserve `analyze_blueprint` and existing planning
behavior. Return compact summaries and deterministic scoped/paginated details;
define how a caller supplies the same blueprint/request identity for subsequent
detail requests. Large graphs should not flood MCP output.

Add CLI paths to analyze a selected blueprint/book entry with a saved request and
write/open local report artifacts. Complete the viewer's assignment-export to
reanalyze to result-import workflow. Artifact writes belong in explicit host/CLI
actions; MCP calculations remain pure and accurately annotated read-only.
Include available supported mechanics, provenance, errors, solver limits, and
partial results in capability/tool documentation. Advertise only validated scope.

Acceptance: use real stdio MCP to list tools and call successful, invalid,
conditional, insufficient, oversized, and unsupported cases. Verify structured
results agree with direct Python calls, no diagnostics corrupt protocol stdout,
and pure calls do not create files or call a model. A saved complete request must
replay with matching hashes and assumptions. Existing tool callers keep working.

Run the pinned pilot end to end: import, select ports, save assignments, analyze,
inspect a finding, and show its original entity location. Verify packaged assets
work from an installed package, not just the source tree. Run `make test` and
record skips, game-evidence gaps, latency/memory method, and entity/edge/model
counts. Give 08 reproducible commands and artifacts. Reload a running MCP process
before claiming that process has the new tools; otherwise state which fresh test
server was verified. Do not start cleanup or live telemetry in this task.
