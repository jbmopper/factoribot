"""Terminal entry point for the factoribot brain.

Examples
--------
Solve from a spec file::

    python -m factoribot.cli solve --spec examples/purple_am2_nomods.json

Inspect the loaded data (sanity check the dump)::

    python -m factoribot.cli info
"""
from __future__ import annotations

import argparse
import json
import sys

from . import report
from .gamedata import load_database
from .solver import AmbiguousRecipe, SolverError, solve
from .spec import SolveSpec


def _cmd_solve(args: argparse.Namespace) -> int:
    db = load_database(args.data)
    if args.spec == "-":
        spec_dict = json.load(sys.stdin)
    else:
        with open(args.spec) as f:
            spec_dict = json.load(f)
    spec = SolveSpec.from_dict(spec_dict)
    try:
        result = solve(spec, db)
    except AmbiguousRecipe as e:
        print(f"Ambiguous: {e}\nCandidates: {e.candidates}", file=sys.stderr)
        return 2
    except SolverError as e:
        print(f"Solver error: {e}", file=sys.stderr)
        return 2
    print(report.render(result, spec))
    return 0


def _cmd_info(args: argparse.Namespace) -> int:
    db = load_database(args.data)
    print(f"recipes: {len(db.recipes)}")
    print(f"crafting machines: {len(db.machines)}")
    print(f"modules: {len(db.modules)}")
    print(f"fluids: {len(db.fluids)}")
    if args.recipe:
        r = db.recipes.get(args.recipe)
        if not r:
            print(f"(no recipe '{args.recipe}')")
            return 1
        print(json.dumps(
            {
                "name": r.name,
                "category": r.category,
                "energy": r.energy,
                "ingredients": [s.__dict__ for s in r.ingredients],
                "results": [s.__dict__ for s in r.results],
                "allow_productivity": r.allow_productivity,
            },
            indent=2,
        ))
    if args.producers:
        print(f"producers of {args.producers}: {db.producers.get(args.producers, [])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="factoribot")
    p.add_argument("--data", default=None, help="path to data-raw-dump.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("solve", help="solve a production spec")
    sp.add_argument("--spec", required=True, help="spec JSON file, or - for stdin")
    sp.set_defaults(func=_cmd_solve)

    si = sub.add_parser("info", help="inspect the loaded data")
    si.add_argument("--recipe", default=None)
    si.add_argument("--producers", default=None)
    si.set_defaults(func=_cmd_info)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
