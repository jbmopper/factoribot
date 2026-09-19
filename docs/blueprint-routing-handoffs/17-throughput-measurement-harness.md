# Task 17 — Controlled throughput measurement harness

## Handoff

1. **Starting point and contract.** Started from `ab25b2a` (actual `HEAD` at
   start) with pre-existing documentation edits and untracked roadmap/prompts.
   During this task, unrelated edits also appeared in
   `daemon/factoribot/blueprint_view.py` and its viewer JavaScript; they were
   not inspected or changed. The capture contract introduced here is local,
   versioned `factoribot-routing-measurement-capture-1`; it does not change the
   shared observation schema or a public interface. Model: not recorded.

2. **Owned changes.**

   - `experiments/routing-measurements/harness.py`: standard-library offline
     parser, rate calculator, conservation checker, stability classifier, and
     repeat-run validator. It never launches Factorio or writes a save.
   - `experiments/routing-measurements/scenarios/*.json`: four versioned plans:
     straight fast belt, one lane; straight fast belt, two lanes; fixed-research
     fast-inserter chest-to-chest; and blocked output.
   - `experiments/routing-measurements/samples/synthetic-steady-capture.json`:
     explicitly synthetic recorder test data, not an observation.
   - `experiments/routing-measurements/RUNBOOK.md`: exact disposable-save
     procedure and operator commands.
   - `daemon/tests/test_routing_measurement_harness.py`: six offline tests.

   No mechanics record, evidence manifest, solver, viewer, CLI registration,
   save, or global mod configuration was changed.

3. **Commands and results.**

   ```sh
   .venv/bin/python experiments/routing-measurements/harness.py validate-scenarios
   ```

   Result: four valid scenario IDs.

   ```sh
   .venv/bin/python experiments/routing-measurements/harness.py validate-capture \
     experiments/routing-measurements/samples/synthetic-steady-capture.json
   ```

   Result: two 3,600-tick windows, each 900 collected iron plates = 15.0
   items/s; `record_kind` remains `synthetic-recorder-test`.

   ```sh
   .venv/bin/python -m pytest daemon/tests/test_routing_measurement_harness.py -q
   git diff --check
   ```

   Result: `6 passed`; no whitespace errors.

   `make test` was started three times; each reached about 33% of the suite
   before the host's 30-second execution window ended, without a completion or
   pass/fail result. It must be rerun in an environment that permits a complete
   process before integration. A short-lived redirected retry wrote
   `/private/tmp/factoribot-task17-make-test.log`; that scratch file was removed.

4. **Concrete counterexample.** A naive recorder accepting a delete sink could
   report no final inventory while having no countable output. The new parser
   rejects `removal.count_before_removal: false`. Separately, its conservation
   test accepts `source=10`, `collected=4`, inventory changing from 2 to 8:
   10 = 4 + (8 - 2), so retained inventory is not silently treated as loss.
   It labels rate-disagreeing contiguous windows
   `nonconverged-or-oscillating` and does not average them.

5. **Unmet game gate.** Local inspection found numerous existing saves and mod
   archives under the user's Factorio application-support directory, but no
   executable at the project launcher's standard candidates. Existing saves and
   global mod configuration were not touched. Therefore all four actual game
   measurements remain unexecuted: the missing prerequisite is a compatible
   Factorio executable plus an operator creating a new editor/sandbox save named
   `routing-measurement-17-<date>`. The operator must record exact executable,
   game build, enabled mods, research, power/control state, exported setup
   blueprint, countable source/collector figures, inventories, warmup, and
   contiguous ticks, then validate both runs using the RUNBOOK commands. A
   synthetically valid record does not become game evidence, and valid raw game
   records still require later review before any evidence promotion.

6. **Next step.** Task 20 can consume the local capture interface after the
   operator produces and reviews two raw captures per scenario. Task 17 itself
   needs that game prerequisite and one completed full `make test` run; it must
   not be marked as having observed mechanics until then.
