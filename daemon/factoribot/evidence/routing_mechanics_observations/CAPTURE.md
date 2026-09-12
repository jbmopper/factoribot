# Controlled capture procedure for routing mechanics

How to turn a `pending` or `documented-only` record in `records/` into an
`observed` one. Nothing in this file has been executed: task 02 had no Factorio
installation or disposable save available, so every record is still unobserved.

## 1. Safety rules

- **Never use the player's live save.** Every capture happens in a disposable
  sandbox created for the purpose. Record its name in the record's
  `environment.save`; if you cannot name it, the record is not `observed`.
- Do not modify, migrate or overwrite any existing save file. Create a new one.
- The captures below build small setups from scratch. Do not import the pilot
  blueprint into a live factory to measure it.
- Delete or archive the sandbox when done; keep only the setup blueprint strings
  and the recorded numbers, both of which live in the record.

## 2. Sandbox setup

1. Note the exact game build (the version string in the main menu) and the exact
   enabled mod list with versions (Mods menu). Both go in `environment`. If
   either is unavailable, the capture cannot be `observed`.
2. New game, sandbox/editor start, default settings, peaceful. Name it something
   identifiable, e.g. `routing-02-capture`.
3. Enable the technologies each capture needs and **write the levels down**.
   Inserter capacity research changes hand size; an unrecorded level makes an
   inserter measurement meaningless. Unlisted levels are unknown, not zero.
4. Use editor infinity chests for sources and sinks so supply is never the
   limiting factor unless the capture is about supply.
5. Keep power out of the question: place enough generation, or use the editor's
   power source, and confirm no low-power alert during the run.

## 3. Measuring a rate

1. Build the setup, then let it run until the belts are saturated end to end and
   the reading is steady. A rate read during fill-up is not a throughput.
2. Empty the sink chest, note the game tick, run for a fixed interval
   (60 s = 3600 ticks is a good default), and read the sink's item count.
3. Rate = items / interval. Repeat the run at least twice; if the two runs
   differ by more than the belt's item quantum, say so in `notes` rather than
   averaging the disagreement away.
4. Record the setup as a blueprint string in `setup_blueprint`, so the capture is
   reproducible by someone who was not there.
5. Fill in `measurement` with the numbers and the interval, set
   `evidence_status` to `observed`, clear `blocking_gate`, then regenerate the
   index:

   ```sh
   .venv/bin/python daemon/factoribot/evidence/routing_prototypes/generate.py --from-slice
   .venv/bin/python -m pytest daemon/tests/test_transport_prototypes.py -q
   ```

   The schema check refuses an `observed` record that is missing any of the
   setup, interval, method, measurement, build, mod list or save name.

## 4. The captures

Each subsection matches one record id. Run every capture for the tier the pilot
uses (fast) at minimum; the other two tiers make the rule general.

### 4.1 `belt.straight.lane_capacity`

A straight belt of at least 20 tiles, fed from an infinity chest through
inserters or a loader on both lanes, ending in a sink chest. Confirm both lanes
are visually compressed, then measure. Expect 15 / 30 / 45 items/s for the three
tiers, and half of that per lane. Repeat with only one lane fed to read the
per-lane figure directly.

### 4.2 `belt.turn.lane_behavior`

Two identical saturated runs of equal tile length, one straight and one with a
single 90-degree turn, each into its own sink. Compare rates. Then feed the two
lanes with two visually distinct items and check whether either lane's rate
changes through the turn. Record both the totals and the per-lane numbers.

### 4.3 `belt.side_load.lane_assignment`

A main belt fed on one lane only, side-loaded from a perpendicular belt carrying
a second item. Separate the two items at the far end (filter inserters into
separate chests) and count each. Repeat with the side-load entering from the
other side, and repeat with the main belt fully saturated to see what the
side-load does when there is no room.

### 4.4 `belt.transfer.belt_to_belt`

A saturated run crossing a tier boundary, fast into express and express into
fast, each direction measured separately per lane. This establishes both the
handover limit and whether lane identity survives the boundary.

### 4.5 `underground.pairing.range`

For each tier: place an entrance, then place the exit at increasing separation,
one tile at a time, until it no longer forms a pair. Record the largest
separation that pairs, counted two ways -- tiles of gap between the two
entities, and centre-to-centre distance -- and say explicitly which one equals
the prototype's `max_distance` (5 / 7 / 9). This is the number that resolves
`underground_span_tiles` in the extract.

### 4.6 `underground.pairing.conflict`

Build a valid pair, then place a second same-tier entrance between them facing
the same way, and record which entrance the exit now serves. Repeat with the
intervening entity being a different tier, and with a plain belt in between.

### 4.7 `underground.lane_mapping`

Feed only the left lane of an entrance with a distinct item and observe which
lane carries it at the exit. Repeat for the right lane.

### 4.8 `splitter.lane_split`

Saturate one input side of a splitter and count both outputs separately; then
saturate both inputs; then feed a single lane. Record the totals and the split.
Also record which tile of the 2x1 footprint is which input and output, since the
prototype does not state it.

### 4.9 `splitter.priority_and_filter`

Repeat 4.8 for each input priority setting, each output priority setting, and
with a filter set, with the input both saturated and under-supplied. The
under-supplied case is the one that distinguishes a priority from a fixed split.

### 4.10 `inserter.endpoints.pickup_drop_tiles`

For each of the four cardinal directions: an inserter between a source chest and
a belt. Record the tile it takes from, the tile it drops on, and which belt lane
receives the item. Repeat with the belt parallel to the inserter and
perpendicular to it, and with a chest as the destination. This confirms (or
refutes) the rotation of `pickup_position [0, -1]` and `insert_position
[0, 1.2]` into world tiles that task 03 implements.

### 4.11 `inserter.rate.cycle_and_stack`

For inserter, fast-inserter and bulk-inserter: chest-to-chest, chest-to-belt,
belt-to-chest and belt-to-belt, at each inserter-capacity research level you
record. Measure items per interval, not cycles by eye. This is the evidence task
09 needs before an inserter ever gets a finite capacity.

### 4.12 `machine.activity.assembling_machine_2`

One AM2, no modules, no beacons, a fixed recipe, unlimited ingredients, output
removed continuously. Measure products per interval and compare with
`crafting_speed / energy_required`. Repeat for a recipe with a different
ingredient count.

### 4.13 `machine.activity.electric_furnace`

One electric furnace fed a single ore type, output removed continuously.
Measure plates per interval per smelting recipe. Also record what the furnace
does when two different ores are inserted, since a blueprint furnace has no
recipe field and its candidate set is what task 10 must resolve.

### 4.14 `power.supply_assumption`

Build the same small setup twice, one connected to sufficient generation and one
deliberately under-powered, and measure both. This does not implement power
analysis; it records what "assumed available" is worth compared with an actual
network.

### 4.15 `circuit.control_state`

An inserter and a belt wired to a constant combinator, with the enable condition
satisfied in one run and unsatisfied in the next. Measure both. Then record the
third case explicitly: a wire present whose condition state is unknown, which
must stay an unresolved condition rather than being treated as enabled or
deleted.

## 5. After a capture

Update only the record you measured. Do not backfill the others by analogy: a
belt observation is not an underground observation. Regenerate the index, run
the focused tests, and note in the handoff which gates are now closed and which
remain open.
