#!/usr/bin/env node
"use strict";

// Test only the deterministic JSONL parser; running a trial still requires a
// separate Factorio installation and disposable game-data directory.

const path = require("path");

async function main() {
  const upstream = process.argv[2];
  const fixture = process.argv[3];
  if (!upstream || !fixture) {
    throw new Error("usage: probe_factorio_analytics.js UPSTREAM_DIST FIXTURE");
  }
  const { Factory } = require(path.join(upstream, "src", "Factory.js"));
  const { Trial } = require(path.join(upstream, "src", "Trial.js"));
  const trial = new Trial();
  trial.id = "task-16-parser-probe";
  trial.length = 120;
  trial.tickInterval = 60;
  const rows = await Factory.parseItemDataFile(fixture, trial);
  console.log(JSON.stringify({
    status: "returned",
    row_count: rows.length,
    metadata: trial.itemMetadata,
    rows: rows.map((row) => ({
      label: row.label,
      tick: row.tick,
      cons: row.cons,
      prod: row.prod,
    })),
    expectation: "Over 120 ticks (2 seconds), 6 plates consumed and 3 gears produced imply averages of 3 and 1.5 item/s.",
  }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
