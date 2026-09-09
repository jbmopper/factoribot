# 14 — Compare static predictions with controlled game measurements

Implement under `docs/blueprint-routing-prompts/WORKING-RULES.md` after 08, with
an identified disposable Factorio test environment. Read the existing mod and
`docs/game-bridge-design.md`; chat transport is not a telemetry implementation.

Own a measurement design, new `mod/telemetry.lua`, the minimal opt-in registration
in `mod/control.lua`, `daemon/factoribot/blueprint_observations.py`, quantitative
captures under `daemon/tests/fixtures/routing_live_measurements/`, and measurement
tests. Reuse 02's manifest conventions without taking ownership of its static
mechanics observations. Coordinate any mod metadata/settings changes. Preserve chat
behavior. Do not build general remote control or modify the player's live save.

Create an opt-in capture over explicit entity scope and start/end ticks. Record
actual game/mod versions, research and relevant controls, initial/final inventories
including in-transit material where needed, produced/consumed/imported/exported
counters with their exact meaning, machine status, and scope/entity mapping.
Define reset, save reload, missing entity, wraparound, and interrupted-run behavior.
Use simulation ticks for rates, not wall-clock speed.

Define reproducible warmup and repeated-run procedures with declared supplies and
export sinks. Distinguish sustained throughput from drawing down buffers. Compare
observations only against a static result with matching blueprint/entity mapping,
request, prototype provenance, and assumptions. A violated upper bound requires
investigation of model/evidence mismatch; low observed output alone does not prove
which tight static constraint caused it.

Acceptance: a controlled circuit chain and shared-belt bottleneck have replayable
captures; a deliberately prefilled buffer demonstrates why inventory deltas
matter; changed research, disabled inserter, and interrupted capture are reported
correctly. Validate the export schema and rate arithmetic offline with independent
expected values. Retain raw observations and comparison results separately.

Run mod syntax/load checks available in the test environment, Python tests,
`make test`, and at least one actual controlled capture before claiming telemetry
works. If the game environment is unavailable, deliver the offline implementation
and exact capture steps with that gate explicitly unverified. No fake captures,
unrequested network listeners, or automatic live blueprint placement.
