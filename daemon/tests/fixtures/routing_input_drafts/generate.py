#!/usr/bin/env python3
"""Regenerate the sealed identities in the task-15 full-input draft fixture."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "daemon"))

from factoribot.routing_public import resolve_layout  # noqa: E402


def main() -> None:
    layout = resolve_layout({
        "blueprint_string": (HERE / "two_lane_fast_belt.txt").read_text().strip(),
        "provenance": "synthetic",
    })
    path = HERE / "full_belt_same_item_draft.json"
    document = json.loads(path.read_text())
    document["blueprint_hash"] = layout.graph.blueprint_hash
    document["graph_hash"] = layout.graph.graph_hash
    document["assignments"]["blueprint_hash"] = layout.graph.blueprint_hash
    document["assignments"]["graph_hash"] = layout.graph.graph_hash
    path.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n")
    print(json.dumps({"blueprint_hash": layout.graph.blueprint_hash,
                      "graph_hash": layout.graph.graph_hash}, indent=2))


if __name__ == "__main__":
    main()
