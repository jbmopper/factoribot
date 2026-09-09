# Planner cross-check fixtures

These fixtures compare Factoribot's deterministic solver against numbers copied
from an external planning tool such as Factory Planner or Helmod.

Each `*.json` file describes one planner snapshot:

```json
{
  "name": "purple science, AM2, no modules",
  "source": {
    "tool": "factory_planner",
    "version": "1.2.3",
    "factorio_version": "2.0.x",
    "notes": "Vanilla, no modules, basic oil"
  },
  "tolerance": { "rel": 0.001, "abs": 0.000001 },
  "strict": true,
  "spec": {
    "targets": [{ "name": "production-science-pack", "rate": 1.0 }]
  },
  "expected": {
    "recipes": {
      "production-science-pack": {
        "crafts_per_s": 0.3333333333333333,
        "machines_exact": 9.333333333333332,
        "machines_whole": 10,
        "machine": "assembling-machine-2"
      }
    },
    "raw_per_s": { "iron-ore": 52.5 },
    "byproducts_per_s": {},
    "machine_totals_whole": { "assembling-machine-2": 72 },
    "total_power_w": 47644444.44444444
  }
}
```

`strict: true` also checks that Factoribot did not produce extra recipe rows,
raw inputs, or byproducts beyond the expected maps. Leave it false for partial
planner snapshots.

Use planner-visible exact machine counts where possible. Rounded UI values are
fine too; set a looser `tolerance` for those cases.
