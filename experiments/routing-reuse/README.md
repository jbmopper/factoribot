# Routing reuse evaluation harness

This directory belongs to task 16. It contains deterministic, synthetic,
known-answer layouts used to evaluate `factorio_blueprint_analyser` 1.3.6. The
expectations are mathematical reference cases; they are **not** Factorio game
observations.

Run the harness against an isolated upstream checkout:

```sh
python run_static_analyser.py \
  --upstream /path/to/factorio_blueprint_analyser \
  --pilot ../../daemon/tests/fixtures/wip_science.txt > results.json
```

The runner does not upload blueprints, alter an upstream checkout, or launch a
browser. `results.json` is retained as the exact observed result set used by the
task handoff.

Compare Factoribot's current conservative structural model through its public
CLI tool adapter:

```sh
python run_factoribot_inspect.py \
  --factoribot ../../.venv/bin/factoribot > factoribot-inspect-results.json
```

The remaining probes cover the static analyser's custom prototype hook and the
game-trial package's deterministic JSONL parser independently of a game install:

```sh
python probe_custom_prototypes.py --upstream /path/to/factorio_blueprint_analyser
node probe_factorio_analytics.js /path/to/factorio-analytics/dist \
  factorio-analytics-sample.jsonl
```
