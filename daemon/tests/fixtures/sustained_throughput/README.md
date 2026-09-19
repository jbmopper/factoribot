# Sustained-throughput design cases

`cases.json` is the task 20 pre-implementation corpus for task 21 review. Every
case is synthetic or an independently derived arithmetic reference. None is a
Factorio observation, and no expected value may be copied into a mechanics
evidence record.

The manifest links to task 16's small corpus and task 17's scenario IDs where a
matching artifact exists. A missing task 17 scenario is a deliberate measurement
gap, not permission to synthesize one. `steady_balance` uses exact rational
strings and is checked item by item:

```
accepted_import + gross_production
  = activity_consumption + net_export + stored_delta
```

The eventual implementation should turn these into black-box prediction tests
only after task 21 accepts or narrows the semantics in the task 20 handoff.
