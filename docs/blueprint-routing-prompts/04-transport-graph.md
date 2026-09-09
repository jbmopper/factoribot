# 04 — Build supported lane connections and structural findings

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 00, 02,
and 03. Read the mechanics evidence matrix and contract before coding.

Own new `transport.py`, `routing.py` for connectivity/reachability, and transport
tests/fixtures. Types and finding serialization come from 00. Task 05 owns the LP;
do not create a second flow optimizer here.

Build lane-specific ports/arcs for the frozen belt set, supported turns and
side-loading, underground pairing/lane mapping, splitters, and concrete inserter
pickup/drop endpoints. Model inventory compartments and direct insertion where
supported; being on a machine footprint is not itself proof of a valid endpoint.
Distinguish arc topology, item filters, shared physical capacity groups, and
conditional controls. Keep unvalidated engine rules explicit.

Propagate possible items from declared feeds and fixed recipe outputs. Unknown
feed identity must not produce a false incompatible-filter or unreachable-input
finding. Do not infer supplies from every dangling belt. Structural findings must
distinguish internal breaks, declared interfaces, and incomplete external context.
Use stable IDs and evidence paths tied to original entity/port IDs.

Acceptance: independently specified cases cover both lanes, a half-belt feed,
turns, side-loading, filtered/priority splitters, conflicting underground endpoints,
disabled/conditional inserters, disconnected producer, direct insertion, blocked
output, and unsupported possible bridge. Validate supported engine mechanics
against 02's evidence; mark unobserved ones accordingly. Translation and supported
rotation preserve meaning. Multiple splitter arcs cannot each claim the full shared
capacity. An unknown possible bridge cannot become a proven disconnection.

Keep initial capacity relaxations transparent; detailed inserter timing is 09.
Do not collapse arbitrary connected components into free material pools. Return
the graph and constraint/evidence references required by 05, with resource counts
and graph-build elapsed time. Report unsupported mechanics on the pilot even if an
unrelated subgraph can be analyzed successfully.
