#!/usr/bin/env python3
"""Run factorio_blueprint_analyser against the task-16 synthetic corpus."""

from __future__ import annotations

import argparse
import collections
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path

from corpus import get_cases


def summarize(result: dict) -> dict:
    bp = result["blueprint"]
    entities = []
    for item in bp.get("entities", []):
        entities.append(
            {
                key: item[key]
                for key in (
                    "entity_number",
                    "name",
                    "input",
                    "output",
                    "usage_rate",
                    "transpoted_items",
                    "parents",
                    "children",
                    "output_priority",
                )
                if key in item
            }
        )
    return {
        "items_input": bp.get("items_input"),
        "items_output": bp.get("items_output"),
        "entities_input": bp.get("entities_input"),
        "entities_output": bp.get("entities_output"),
        "entities_bottleneck": bp.get("entities_bottleneck"),
        "entities": entities,
    }


def summarize_pilot(result: dict, warnings: list[str]) -> dict:
    """Keep the large pilot result reviewable without discarding key failures."""
    summary = summarize(result)
    entities = summary.pop("entities")
    nonzero = [
        item
        for item in entities
        if item.get("transpoted_items") or item.get("usage_rate")
    ]
    summary.update(
        {
            "analysed_entity_rows": len(entities),
            "entity_names": dict(sorted(collections.Counter(
                item["name"] for item in entities
            ).items())),
            "warning_counts": dict(sorted(collections.Counter(warnings).items())),
            "nonzero_entity_rows": len(nonzero),
            "nonzero_examples": nonzero[:12],
        }
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--pilot", type=Path)
    args = parser.parse_args()

    sys.path.insert(0, str(args.upstream))
    from factorio_blueprint_analyser import blueprint_analyser  # noqa: PLC0415

    blueprint_analyser.init(
        {"verboseLevel": 2, "displayNetwork": False, "inserterCapacityBonus": 0}
    )

    report = {"cases": {}, "pilot": None}
    for name, case in get_cases().items():
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                result = blueprint_analyser.analyse_blueprint(
                    json.dumps(case["blueprint"], sort_keys=True)
                )
            observed = summarize(result)
            status = "returned"
            error = None
        except Exception as exc:  # preserve upstream failures verbatim
            observed = None
            status = "exception"
            error = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        report["cases"][name] = {
            "expectation": case["expectation"],
            "status": status,
            "stderr": stderr.getvalue().splitlines(),
            "error": error,
            "observed": observed,
        }

    if args.pilot is not None:
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                result = blueprint_analyser.analyse_blueprint_from_path(str(args.pilot))
            warning_lines = stderr.getvalue().splitlines()
            report["pilot"] = {
                "status": "returned",
                "stderr_line_count": len(warning_lines),
                "error": None,
                "observed": summarize_pilot(result, warning_lines),
            }
        except Exception as exc:
            report["pilot"] = {
                "status": "exception",
                "stderr": stderr.getvalue().splitlines(),
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                },
                "observed": None,
            }

    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
