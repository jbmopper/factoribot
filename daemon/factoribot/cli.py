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
    print(report.render(result, spec, db))
    return 0


def _make_tracer(verbose: bool):
    """A run_agent on_event callback that traces tool calls to stderr."""
    if not verbose:
        return None

    def on_event(kind: str, data: dict) -> None:
        if kind == "tool_call":
            print(f"  -> {data['name']}({json.dumps(data['arguments'])})", file=sys.stderr)
        elif kind == "tool_result":
            out = data["output"]
            brief = out.get("error") or ("ok" if out.get("ok") else list(out)[:3])
            print(f"  <- {data['name']}: {brief}", file=sys.stderr)

    return on_event


def _cmd_ask(args: argparse.Namespace) -> int:
    from .agent import run_agent
    from .llm import make_client

    db = load_database(args.data)
    client = make_client(args.provider, args.model, key_file=args.key_file)
    result = run_agent(client, db, args.query, on_event=_make_tracer(args.verbose))
    print(result.text)
    return 0


def _cmd_chat(args: argparse.Namespace) -> int:
    """Interactive, multi-turn REPL. Same agent + memory model as the daemon."""
    from .agent import run_agent
    from .llm import make_client
    from .server import Sessions

    # Importing readline upgrades the bare input() to a real line editor: arrow
    # keys, in-session history (up/down), and word-delete. Without it, arrow keys
    # leak escape codes like "^[[D". Optional so non-readline platforms still run.
    try:
        import readline  # noqa: F401
    except ImportError:
        pass

    db = load_database(args.data)
    client = make_client(args.provider, args.model, key_file=args.key_file)
    model = getattr(client, "model", None) or "default"
    tracer = _make_tracer(args.verbose)

    sessions = Sessions()
    key = "cli"

    print(f"factoribot chat  (provider={args.provider}, model={model})")
    print("Ask a factory-design question. Commands: /new  /exit  (or Ctrl-D).")
    while True:
        try:
            line = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        low = line.lower()
        if low in ("/exit", "/quit", ":q"):
            break
        if low in ("/new", "/reset"):
            sessions.reset(key)
            print("(new conversation)")
            continue
        if low in ("/help", "/?", "?"):
            print("commands: /new (clear memory), /exit (quit)")
            continue
        try:
            result = run_agent(
                client, db, line, history=sessions.get(key), on_event=tracer
            )
            sessions.set(key, result.messages)
            print(f"\nbot> {result.text}")
        except Exception as e:  # keep the REPL alive on transient errors
            print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
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

    sc = sub.add_parser("chat", help="interactive multi-turn chat in the terminal")
    sc.add_argument("--provider", default="openai", help="openai | anthropic | gemini | ollama")
    sc.add_argument("--model", default=None, help="provider model id (optional)")
    sc.add_argument("--key-file", default=None, help="path to API key file")
    sc.add_argument("-v", "--verbose", action="store_true", help="trace tool calls")
    sc.set_defaults(func=_cmd_chat)

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
