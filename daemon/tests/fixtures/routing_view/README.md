# Viewer demonstration artifacts (task 06)

Everything here was produced by `factoribot.blueprint_view` from the **synthetic**
contract fixtures in `../routing_contracts/`. None of it is game data, a
measurement, or a solver result. Captured against contract schema **1.1.1**
(the fixtures were regenerated from 1.1.0 to 1.1.1 while this task ran; the
viewer reads the version from the data and never hardcodes it, so the artifacts
were simply re-captured).

## Regenerating the pages

```sh
.venv/bin/python daemon/tests/fixtures/routing_view/render_examples.py OUTDIR
```

Writes one standalone HTML page per fixture plus `hostile_labels.html`, whose
finding message, bound certificate, limitations and assumptions carry
script-closing and markup payloads. The rendered pages are not checked in: the
large layout alone is about 7.5 MiB. Open them from a local static server
(`python -m http.server` inside OUTDIR); the pages themselves make no network
request and load no CDN.

## Files

| File | What it shows |
| --- | --- |
| `render_examples.py` | Regenerates every demonstration page, including the hostile-label one |
| `edited_assignments.json` | `AssignmentSet` exported by the page after assigning a furnace recipe and declaring a second feed on the same global budget; `parse_assignments` accepts it against `furnace_override.json` |
| `edited_draft.json` | The same edit exported as the draft envelope (assignment set plus proposed budgets, exports, surplus and objective) for the host to reanalyze |
| `screenshots/large_layout_overview.png` | The 3200-entity synthetic grid drawn on one canvas |
| `screenshots/large_layout_finding_highlight.png` | The large layout's finding selected: entity 1, its left lane and arc `belt_1` are highlighted, nothing else |
| `screenshots/shared_budget_two_ports_one_budget.png` | Both ports that draw on the single global `iron` budget selected at once |

The screenshots are the map canvas only; the surrounding panels are described in
the task handoff. `edited_*.json` were exported from a browser against the
fixture state at capture time. If task 00 regenerates the fixtures again, the
recorded hashes go stale, which is exactly what the page's stale banner reports;
re-run the export to refresh them.
