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


def _cmd_ask(args: argparse.Namespace) -> int:
    from .agent import run_agent
    from .llm import make_client

    db = load_database(args.data)
    client = make_client(args.provider, args.model, key_file=args.key_file)

    def on_event(kind: str, data: dict) -> None:
        if not args.verbose:
            return
        if kind == "tool_call":
            print(f"  -> {data['name']}({json.dumps(data['arguments'])})", file=sys.stderr)
        elif kind == "tool_result":
            out = data["output"]
            brief = out.get("error") or ("ok" if out.get("ok") else list(out)[:3])
            print(f"  <- {data['name']}: {brief}", file=sys.stderr)

    result = run_agent(client, db, args.query, on_event=on_event)
    print(result.text)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    serve(
        host=args.host,
        port=args.port,
        provider=args.provider,
        model=args.model,
        key_file=args.key_file,
        data=args.data,
        verbose=args.verbose,
    )
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

    sa = sub.add_parser("ask", help="natural-language query via the LLM agent")
    sa.add_argument("query", help='e.g. "purple science, assembly machine 2, no modules"')
    sa.add_argument("--provider", default="openai", help="openai | anthropic | gemini | ollama")
    sa.add_argument("--model", default=None, help="provider model id (optional)")
    sa.add_argument("--key-file", default=None, help="path to API key file")
    sa.add_argument("-v", "--verbose", action="store_true", help="trace tool calls")
    sa.set_defaults(func=_cmd_ask)

    sv = sub.add_parser("serve", help="run the UDP daemon for the in-game mod")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=25001)
    sv.add_argument("--provider", default="openai", help="openai | anthropic | gemini | ollama")
    sv.add_argument("--model", default=None)
    sv.add_argument("--key-file", default=None)
    sv.add_argument("-v", "--verbose", action="store_true")
    sv.set_defaults(func=_cmd_serve)

    si = sub.add_parser("info", help="inspect the loaded data")
    si.add_argument("--recipe", default=None)
    si.add_argument("--producers", default=None)
    si.set_defaults(func=_cmd_info)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
