#!/usr/bin/env python3
"""Exercise Factoribot's public layout inspection on the same logical cases."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
from pathlib import Path

from corpus import get_cases


FACTORIO_2_BLUEPRINT_VERSION = 562949954469888


def as_factorio_2(document: dict) -> dict:
    """Translate cardinal direction values from the legacy 8-way encoding."""
    value = copy.deepcopy(document)
    bp = value["blueprint"]
    bp["version"] = FACTORIO_2_BLUEPRINT_VERSION
    for entity in bp["entities"]:
        if "direction" in entity:
            entity["direction"] *= 2
    return value


def invoke(executable: Path, args: dict, section: str = "summary") -> dict:
    args = dict(args)
    args["section"] = section
    args["detail"] = {"kind": "full", "limit": 200}
    process = subprocess.run(
        [str(executable), "tool", "inspect_blueprint_layout", "--args", "-"],
        input=json.dumps(args, sort_keys=True),
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        return {
            "process_returncode": process.returncode,
            "process_stderr": process.stderr,
            "process_stdout": process.stdout,
        }
    return json.loads(process.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--factoribot", type=Path, required=True)
    args = parser.parse_args()

    report = {
        "note": (
            "Structural inspection only. Factoribot advertises no operating rate: "
            "all arcs are relaxed/conditional and the mechanics gate is unmet."
        ),
        "cases": {},
    }
    for name, case in get_cases().items():
        request = {
            "blueprint_string": json.dumps(as_factorio_2(case["blueprint"]), sort_keys=True),
            "provenance": "synthetic",
        }
        summary = invoke(args.factoribot, request)
        findings = invoke(args.factoribot, request, "findings")
        report["cases"][name] = {
            "ok": summary.get("ok"),
            "identity": summary.get("identity"),
            "counts": summary.get("counts"),
            "prototypes": summary.get("prototypes"),
            "support": summary.get("support"),
            "arc_semantics": summary.get("arc_semantics"),
            "conditions": summary.get("conditions"),
            "capacity_kinds": summary.get("capacity_kinds"),
            "graph_findings": summary.get("graph_findings"),
            "bound_prerequisites": summary.get("bound_prerequisites"),
            "finding_rows": findings.get("findings"),
            "error": summary.get("error"),
        }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
