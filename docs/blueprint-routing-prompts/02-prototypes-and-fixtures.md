# 02 — Supply versioned transport prototypes and fixture evidence

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 00's
contract and sample schemas exist. Read `gamedata.py`, `model.py`, the dump-loading
path, current fixtures, and the mod's existing capabilities.

Own a new `transport_prototypes.py`, additive `gamedata.py`/`model.py` changes,
prototype normalization tests, `daemon/tests/fixtures/routing_prototypes/`,
`daemon/tests/fixtures/routing_mechanics_observations/`, and their README/manifest
tooling. This directory owns static mechanics evidence; 14 owns quantitative
live telemetry captures in a separate directory.
Do not edit `blueprint.py`, transport algorithms, or public tool registration.

Inventory raw fields for the agreed first entity set: footprint geometry,
directions, belt speeds, underground reach, splitter shape, inserter pickup/drop
positions and rate-relevant parameters. Distinguish raw fields from derived engine
semantics. Missing fields need an unsupported/unknown representation, not a guessed
default. Retain enough data for later power/beacon adapters without implementing
those mechanics now.

Implement the agreed provenance manifest: exact build and enabled mod versions
when known, source dump SHA, extract SHA, schema version, and source references.
The blueprint format version alone does not identify the prototype environment.
Unknown provenance stays unknown. Reuse the MCP loader's existing SHA rather than
introducing a contradictory identity convention.

Create small pinned extracts sufficient for offline CI. Define an observation
record with setup blueprint, supplied items, research/control state, measurement
interval, expected behavior, observation method, and evidence status. Document a
repeatable controlled-game capture procedure for straight/curved belts, side-loads,
underground conflicts, splitters, and inserter endpoints. Acquire available
evidence only through an identified disposable setup; never invent observations.

Acceptance: normalization tests run without the local full dump; invalid or
mismatched manifests fail; unsupported prototype fields remain explicit; every
first-release mechanics rule has a record marked observed, documented-only, or
pending. Record exact pilot blueprint/hash/entity counts and unavailable feed
information. A missing game observation is an unmet mechanics gate, not a passing
test. Provide the adapter API and fixture locations to 03/04/05.
