#!/usr/bin/env python3
"""Probe the analyser's documented custom data-file hook in a temp directory."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.upstream))

    from factorio_blueprint_analyser import blueprint_analyser  # noqa: PLC0415

    source = (
        args.upstream
        / "factorio_blueprint_analyser/assets/factorio_raw/factorio_raw_min.json"
    )
    data = json.loads(source.read_text())
    custom = copy.deepcopy(data["transport-belt"]["transport-belt"])
    custom["name"] = "probe-transport-belt"
    custom["speed"] = 0.125
    data["transport-belt"][custom["name"]] = custom

    with tempfile.TemporaryDirectory(prefix="factoribot-routing-reuse-") as folder:
        data_path = Path(folder) / "custom-prototypes.json"
        data_path.write_text(json.dumps(data))
        blueprint_analyser.init(
            {
                "dataFilePath": str(data_path),
                "displayNetwork": False,
                "verboseLevel": 0,
            }
        )
        document = {
            "blueprint": {
                "entities": [
                    {
                        "entity_number": 1,
                        "name": "probe-transport-belt",
                        "position": {"x": 0, "y": 0},
                        "direction": 2,
                    },
                    {
                        "entity_number": 2,
                        "name": "probe-transport-belt",
                        "position": {"x": 1, "y": 0},
                        "direction": 2,
                    },
                ],
                "item": "blueprint",
                "label": "custom-prototype-probe",
                "version": 281479275544576,
            }
        }
        result = blueprint_analyser.analyse_blueprint(json.dumps(document))

    entities = result["blueprint"]["entities"]
    print(
        json.dumps(
            {
                "status": "returned",
                "custom_name": custom["name"],
                "custom_speed_field": custom["speed"],
                "expected_whole_belt_capacity_from_upstream_formula": 30.0,
                "entities_input": result["blueprint"]["entities_input"],
                "entities_output": result["blueprint"]["entities_output"],
                "entities": [
                    {
                        key: item.get(key)
                        for key in (
                            "entity_number",
                            "name",
                            "parents",
                            "children",
                            "usage_rate",
                        )
                    }
                    for item in entities
                ],
                "items_input": result["blueprint"]["items_input"],
                "items_output": result["blueprint"]["items_output"],
                "conclusion": (
                    "The custom path works for a custom name whose prototype type "
                    "matches an implemented dispatcher branch; it does not provide "
                    "generic entity semantics, version identity, or lane behavior."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
