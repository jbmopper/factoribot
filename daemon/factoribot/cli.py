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
from pathlib import Path

from . import report
from .gamedata import load_database
from .solver import AmbiguousRecipe, SolverError, solve
from .spec import SolveSpec


def _cmd_tool(args: argparse.Namespace) -> int:
    from .mcp_server import load_toolbox

    source = args.spec
    try:
        if source == "-":
            request = json.load(sys.stdin)
        else:
            with open(source) as f:
                request = json.load(f)
        result = load_toolbox(args.data).call(args.name, request)
    except (OSError, ValueError) as e:
        result = {"error": "bad_request", "message": str(e)}
    print(json.dumps(result, indent=2, allow_nan=False))
    return 2 if "error" in result else 0


def _cmd_tools(args: argparse.Namespace) -> int:
    from .tools import TOOL_SCHEMAS

    print(json.dumps(TOOL_SCHEMAS, indent=2))
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    import asyncio
    from .mcp_server import serve_mcp

    try:
        asyncio.run(serve_mcp(args.data))
    except ImportError:
        print("Install factoribot[mcp] to run the MCP server.", file=sys.stderr)
        return 2
    except (OSError, ValueError) as e:
        print(f"Cannot load Factorio data: {e}", file=sys.stderr)
        return 2
    return 0


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


def _cmd_analyze(args: argparse.Namespace) -> int:
    """Decode and analyze a blueprint string. Deterministic; no LLM/API."""
    from .blueprint import (
        BlueprintError,
        decode_blueprint_string,
        iter_blueprints,
        summarize_blueprint,
    )
    from .bpanalyze import analyze_blueprint

    db = load_database(args.data)
    src = sys.stdin.read() if args.bp == "-" else open(args.bp).read()
    try:
        bps = iter_blueprints(decode_blueprint_string(src))
    except BlueprintError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if not bps:
        print("error: no blueprint with entities found.", file=sys.stderr)
        return 2
    if len(bps) > 1:
        print(f"(blueprint book: analyzing the first of {len(bps)} blueprints)\n")
    summ = summarize_blueprint(bps[0], db)
    print(report.render_blueprint(analyze_blueprint(summ, db, product=args.product), db))
    return 0


# ---------------------------------------------------------------------------
# Blueprint routing audit (task 07 public integration)
#
# These are the *host* actions of the routing surface: they may write local
# artifacts and open a local file in a browser. The MCP tools of the same name
# stay pure and never do either.
# ---------------------------------------------------------------------------

def _routes_read(path: str) -> str:
    return sys.stdin.read() if path == "-" else open(path).read()


def _routes_json(path: str):
    return json.loads(_routes_read(path))


_DEFAULT_ROUTE_RECIPES = object()


def _routes_layout(args: argparse.Namespace, *, recipes=_DEFAULT_ROUTE_RECIPES,
                   furnace_candidates=None):
    """Build the layout named by --bp, reusing the loaded recipe database."""
    from .routing import RecipeSource
    from .routing_public import resolve_layout

    if recipes is _DEFAULT_ROUTE_RECIPES:
        recipes = None
        try:
            recipes = RecipeSource(load_database(args.data))
        except (OSError, ValueError) as e:  # no dump: machines get no activities, and say so
            print(f"note: no prototype dump ({e}); machines get no recipe activities.", file=sys.stderr)
    request = {
        "blueprint_string": _routes_read(args.bp),
        "book_path": args.book_path,
        "furnace_candidates": (args.furnace_candidate or []
                               if furnace_candidates is None else furnace_candidates),
        "provenance": args.provenance,
    }
    return resolve_layout(request, recipes=recipes)


def _routes_write(path: str | None, text: str, label: str) -> None:
    if not path:
        return
    with open(path, "w") as handle:
        handle.write(text)
    print(f"wrote {label}: {path} ({len(text.encode('utf-8'))} bytes)", file=sys.stderr)


def _routes_open(path: str | None, wanted: bool) -> None:
    if not (path and wanted):
        return
    import webbrowser

    webbrowser.open(Path(path).resolve().as_uri())


def _routes_detail(args: argparse.Namespace, graph):
    from .routing_public import parse_detail

    entity_ids = [{"book_path": list(args.book_path or []), "entity_number": n}
                  for n in (args.entity or [])]
    return parse_detail({
        "kind": "entities" if entity_ids else ("full" if args.section != "summary" else "summary"),
        "entity_ids": entity_ids,
        "cursor": args.cursor,
        "limit": args.limit,
    }, graph)


def _cmd_routes_inspect(args: argparse.Namespace) -> int:
    """Import a blueprint, build the routing graph, report it, write artifacts."""
    from .blueprint_contract import to_dict
    from .routing_public import PublicError, layout_summary

    try:
        layout = _routes_layout(args)
        summary = layout_summary(layout, _routes_detail(args, layout.graph), args.section)
    except PublicError as e:
        print(json.dumps(e.as_dict(), indent=2), file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, allow_nan=False))
    _routes_write(args.graph_out, json.dumps(to_dict(layout.graph), allow_nan=False), "graph")
    _routes_write(args.json_out, json.dumps(summary, indent=2, allow_nan=False), "summary")
    if args.view:
        from .blueprint_view import render_view

        assignments = _routes_json(args.assignments) if args.assignments else None
        _routes_write(args.view, render_view(to_dict(layout.graph), None, assignments,
                                             title=f"Routing layout {layout.graph_hash[7:19]}"), "viewer page")
        _routes_open(args.view, args.open)
    return 0


def _cmd_routes_request(args: argparse.Namespace) -> int:
    """Seal a saved request from a template plus the viewer's assignment export."""
    from .blueprint_contract import canonical_json
    from .routing_public import (
        DRAFT_REQUEST_KEYS,
        HOST_POLICY_TEMPLATE_KEYS,
        PublicError,
        request_unresolved,
        seal_request,
    )

    try:
        layout = _routes_layout(args)
        assignments = _routes_json(args.assignments) if args.assignments else None
        document = seal_request(_routes_json(args.template), layout, assignments)
        unresolved = request_unresolved(document, layout)
    except PublicError as e:
        print(json.dumps(e.as_dict(), indent=2), file=sys.stderr)
        return 2
    print(json.dumps({
        "ok": True,
        "request_hash": document["request_hash"],
        "graph_hash": document["graph_hash"],
        "blueprint_hash": document["blueprint_hash"],
        "page_declaration_fields": [key for key in DRAFT_REQUEST_KEYS
                                    if isinstance(assignments, dict)
                                    and isinstance(assignments.get("proposed_request"), dict)
                                    and key in assignments["proposed_request"]],
        "host_policy_fields": list(HOST_POLICY_TEMPLATE_KEYS),
        "precedence": ("Viewer draft owns budgets, exports, surplus and objective; "
                       "the host template owns assumptions, protected interfaces and detail. "
                       "Differing duplicate page declarations are rejected as draft_conflict."),
        "unresolved_reasons": list(unresolved),
        "bounds_advertisable": not unresolved,
        "note": ("No bound can be advertised for this request until every reason above is resolved."
                 if unresolved else
                 "unresolved_reasons is empty: a certified bound may be advertised if a stage certifies one."),
    }, indent=2))
    _routes_write(args.out, canonical_json(document), "sealed request")
    return 0


def _cmd_routes_infer(args: argparse.Namespace) -> int:
    """Infer uniquely evidenced furnace recipes and write replay artifacts."""
    from .blueprint_contract import canonical_json
    from .furnace_inference import (
        FurnaceInferenceError,
        INFERENCE_DOCUMENT_KIND,
        InferenceLimits,
        compatible_furnace_recipes,
    )
    from .routing import RecipeSource
    from .routing_public import (
        PublicError,
        prepare_furnace_inference,
        request_unresolved,
        seal_request,
    )

    try:
        template = _routes_json(args.template)
        assignments = _routes_json(args.assignments)
        assumptions = template.get("assumptions") if isinstance(template, dict) else None
        available = assumptions.get("available_recipes") if isinstance(assumptions, dict) else None
        if not isinstance(available, list):
            raise PublicError("bad_request", "template assumptions.available_recipes must be a list")
        recipes = RecipeSource(load_database(args.data))
        final_candidates = compatible_furnace_recipes(recipes, available)

        source_candidates = tuple(args.furnace_candidate or ())
        if (isinstance(assignments, dict)
                and assignments.get("document_kind") == INFERENCE_DOCUMENT_KIND):
            prior = assignments.get("inference")
            if not isinstance(prior, dict) or not isinstance(prior.get("candidate_recipes"), list):
                raise PublicError("stale_inference", "previous inference artifact lacks candidate identity")
            recorded = tuple(prior["candidate_recipes"])
            if source_candidates and source_candidates != recorded:
                raise PublicError(
                    "stale_identity",
                    "--furnace-candidate does not reproduce the previous inference graph",
                    supplied=list(source_candidates), recorded=list(recorded),
                )
            source_candidates = recorded

        source_layout = _routes_layout(
            args, recipes=recipes, furnace_candidates=source_candidates
        )
        if (not final_candidates
                and any(entity.prototype == "electric-furnace"
                        for entity in source_layout.graph.entities)):
            raise PublicError(
                "bad_request",
                "no available item-only smelting recipe can account for the blueprint's furnaces",
            )
        final_layout = _routes_layout(
            args, recipes=recipes, furnace_candidates=final_candidates
        )
        artifact = prepare_furnace_inference(
            template,
            source_layout,
            final_layout,
            assignments,
            limits=InferenceLimits(
                max_iterations=args.max_iterations,
                max_states=args.max_states,
                max_steps_per_trace=args.max_steps_per_trace,
            ),
        )
        request = seal_request(template, final_layout, artifact)
        unresolved = request_unresolved(request, final_layout)
    except (PublicError, FurnaceInferenceError) as exc:
        error = exc if isinstance(exc, PublicError) else PublicError(exc.code, str(exc), **exc.detail)
        print(json.dumps(error.as_dict(), indent=2), file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        error = PublicError("bad_request", str(exc))
        print(json.dumps(error.as_dict(), indent=2), file=sys.stderr)
        return 2

    report = artifact["inference"]
    counts = {}
    for furnace in report["furnaces"]:
        counts[furnace["status"]] = counts.get(furnace["status"], 0) + 1
    group_summary = [{
        "id": group["id"],
        "status": group["status"],
        "candidates": group["candidates"],
        "entity_count": len(group["entities"]),
        "entity_examples": group["entities"][:10],
        "override_path": group["override_path"],
        "action": group["action"],
    } for group in report["ambiguity_groups"]]
    print(json.dumps({
        "ok": True,
        "inference_version": report["inference_version"],
        "input_hash": report["input_hash"],
        "report_hash": report["report_hash"],
        "artifact_hash": artifact["artifact_hash"],
        "source_graph_hash": artifact["source_graph_hash"],
        "final_graph_hash": artifact["final_graph_hash"],
        "graph_rebuilt": artifact["source_graph_hash"] != artifact["final_graph_hash"],
        "candidate_recipes": report["candidate_recipes"],
        "furnace_status_counts": dict(sorted(counts.items())),
        "ambiguity_groups": group_summary,
        "request_hash": request["request_hash"],
        "unresolved_reason_count": len(unresolved),
        "unresolved_reasons": list(unresolved[:25]),
        "unresolved_reasons_truncated": len(unresolved) > 25,
        "bounds_advertisable": not unresolved,
        "meaning": "Recipe identity inference only; no item rate or runtime selection is predicted.",
    }, indent=2, allow_nan=False))
    _routes_write(args.out, canonical_json(artifact), "furnace inference artifact")
    _routes_write(args.request_out, canonical_json(request), "sealed request")
    return 0


def _cmd_routes_analyze(args: argparse.Namespace) -> int:
    """Analyze a saved request against a blueprint and write report artifacts."""
    from .blueprint_contract import canonical_json, to_dict
    from .routing_public import PublicError, analysis_summary, analyze_layout

    try:
        layout = _routes_layout(args)
        document = _routes_json(args.request)
        report = analyze_layout(layout, document)
        summary = analysis_summary(layout, report, section=args.section,
                                   page_args={"cursor": args.cursor, "limit": args.limit})
    except PublicError as e:
        print(json.dumps(e.as_dict(), indent=2), file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2, allow_nan=False))
    result_document = to_dict(report.result)
    _routes_write(args.result_out, canonical_json(result_document), "result")
    _routes_write(args.json_out, json.dumps(summary, indent=2, allow_nan=False), "summary")
    if args.view:
        from .blueprint_view import render_view

        assignments = document.get("assignments") if isinstance(document, dict) else None
        _routes_write(args.view, render_view(to_dict(layout.graph), result_document, assignments,
                                             title=f"Routing audit {report.result.result_hash[7:19]}"), "viewer page")
        _routes_open(args.view, args.open)
    return 2 if report.result.status == "invalid_request" else 0


def _cmd_routes_finding(args: argparse.Namespace) -> int:
    """Show one finding from a saved result and every entity location it names."""
    from .findings import parse_result
    from .routing_public import PublicError, entity_row, finding_row

    try:
        layout = _routes_layout(args)
    except PublicError as e:
        print(json.dumps(e.as_dict(), indent=2), file=sys.stderr)
        return 2
    findings = list(layout.findings)
    source = "graph"
    if args.result:
        try:
            result = parse_result(_routes_json(args.result), layout.graph)
        except Exception as e:  # noqa: BLE001 - a stale or invalid result must be explained
            print(json.dumps({"error": "bad_result", "message": f"{type(e).__name__}: {e}"}, indent=2),
                  file=sys.stderr)
            return 2
        findings, source = list(result.findings), "result"
    selected = [f for f in findings if args.finding in (f.id, f.code)]
    if not selected:
        print(json.dumps({"error": "unknown_finding", "message": f"no {source} finding matches {args.finding!r}",
                          "available_codes": sorted({f.code for f in findings})}, indent=2), file=sys.stderr)
        return 2
    entities = {e.id: e for e in layout.graph.entities}
    out = []
    for finding in selected[:args.limit]:
        row = finding_row(finding)
        row["source"] = source
        row["entities"] = [entity_row(entities[i], include_raw=True) for i in finding.entity_ids if i in entities]
        row["endpoint_entities"] = [entity_row(entities[e.entity], include_raw=True)
                                    for e in finding.endpoint_ids if e.entity in entities
                                    and e.entity not in set(finding.entity_ids)]
        out.append(row)
    print(json.dumps({"ok": True, "matched": len(selected), "shown": len(out), "findings": out},
                     indent=2, allow_nan=False))
    return 0


def _cmd_routes_throughput(args: argparse.Namespace) -> int:
    """Build the restricted operating prediction/measurement comparison report."""
    from .blueprint_contract import canonical_json
    from .gamedata import read_dump
    from .sustained_throughput import build_operating_report

    try:
        scenario = _routes_json(args.scenario)
        captures = [_routes_json(path) for path in args.capture]
        request = _routes_json(args.request) if args.request else None
        result = _routes_json(args.result) if args.result else None
        _path, dump_sha, _raw = read_dump(args.data)
        document = build_operating_report(
            scenario,
            captures,
            routing_request=request,
            routing_result=result,
            database=load_database(args.data),
            recipe_data_sha256=dump_sha,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": "invalid_throughput_evidence", "message": str(exc)},
                         indent=2), file=sys.stderr)
        return 2
    comparison = document["comparison"]
    print(json.dumps({
        "ok": True,
        "report_hash": document["report_hash"],
        "scenario_hash": scenario["scenario_hash"],
        "prediction_kind": document["prediction"]["rate_kind"],
        "predicted_exports": document["prediction"]["items"]["net_export"],
        "measurement_kind": "actual_measured_interval_rate",
        "validated_runs": len(document["measurements"]),
        "all_windows_match": comparison["all_windows_match"],
        "sustained_rate_established": False,
        "meaning": document["result_meanings"],
    }, indent=2, allow_nan=False))
    _routes_write(args.out, canonical_json(document), "throughput report")
    return 0 if comparison["all_windows_match"] else 1


def _cmd_chat(args: argparse.Namespace) -> int:
    """Interactive, multi-turn REPL. Same agent + memory model as the daemon."""
    from .agent import run_agent
    from .blueprint import (
        decode_blueprint_string,
        find_blueprint_string,
        iter_blueprints,
        summarize_blueprint,
    )
    from .bpanalyze import analyze_blueprint
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
            print("commands: /new (clear memory), /exit (quit). Paste a blueprint "
                  "string to analyze it.")
            continue
        # A pasted blueprint string is analyzed deterministically -- no point
        # sending 20+ KB through the LLM (and it can't echo it back reliably).
        bp = find_blueprint_string(line)
        if bp:
            try:
                bps = iter_blueprints(decode_blueprint_string(bp))
                summ = summarize_blueprint(bps[0], db)
                a = analyze_blueprint(summ, db)
                print("\n" + report.render_blueprint(a, db))
            except Exception as e:
                print(f"error analyzing blueprint: {type(e).__name__}: {e}", file=sys.stderr)
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


def _add_routes(sub) -> None:
    """`factoribot routes ...` -- the blueprint routing audit, offline and no LLM."""
    from .routing_public import ANALYSIS_SECTIONS, DEFAULT_PAGE_LIMIT, LAYOUT_SECTIONS

    parser = sub.add_parser(
        "routes",
        help="blueprint routing audit: structural graph, strict delivery analysis, viewer artifacts",
        description=(
            "Import a blueprint, build its routing graph, analyze a saved strict request, and write "
            "local report/viewer artifacts. The optional infer pass derives only uniquely evidenced "
            "furnace recipes from explicit feeds; feeds, exports, disposal, research, control state "
            "and power still come from the request you supply. Every "
            "advertised value is an upper bound under stated relaxations, never an achievable rate."
        ),
    )
    routes = parser.add_subparsers(dest="routes_cmd", required=True)

    def common(p, *, blueprint=True, furnace_candidate_help=None):
        if blueprint:
            p.add_argument("--bp", required=True, help="file with the blueprint string, or - for stdin")
            p.add_argument("--book-path", type=_book_path_arg, default=(),
                           help="book entry index values selecting one leaf, e.g. 2/7 (NOT array offsets)")
            p.add_argument("--furnace-candidate", action="append", default=[],
                           help=(furnace_candidate_help or
                                 "candidate recipe for recipe-less furnaces; repeatable, never inferred"))
            p.add_argument("--provenance", default="game_export",
                           choices=["game_export", "development_pilot", "synthetic"])

    ins = routes.add_parser("inspect", help="build and report the routing graph; optionally write a viewer page")
    common(ins)
    ins.add_argument("--section", default="summary", choices=list(LAYOUT_SECTIONS))
    ins.add_argument("--entity", action="append", type=int, default=[],
                     help="scope to this entity_number (repeatable); includes its original blueprint record")
    ins.add_argument("--limit", type=int, default=DEFAULT_PAGE_LIMIT)
    ins.add_argument("--cursor", default=None, help="page cursor from a previous call")
    ins.add_argument("--json", dest="json_out", default=None, help="write the summary JSON here")
    ins.add_argument("--graph", dest="graph_out", default=None, help="write the full contract graph document here")
    ins.add_argument("--view", default=None, help="write a standalone viewer page here")
    ins.add_argument("--assignments", default=None, help="assignment document to preload into the page")
    ins.add_argument("--open", action="store_true", help="open the written page in a browser")
    ins.set_defaults(func=_cmd_routes_inspect)

    req = routes.add_parser("request", help="seal a saved request from a template plus an assignment export")
    common(req)
    req.add_argument("--template", required=True,
                     help="host policy JSON: assumptions, protected and detail; bare assignments also need budgets, exports, surplus and objective")
    req.add_argument("--assignments", default=None,
                     help="the viewer's bare AssignmentSet or assignment draft; draft declarations must not conflict with template values")
    req.add_argument("--out", default=None, help="write the sealed request document here")
    req.set_defaults(func=_cmd_routes_request)

    inf = routes.add_parser(
        "infer",
        help="derive furnace assignments from explicit feed/path evidence, then seal a request",
    )
    common(
        inf,
        furnace_candidate_help=(
            "candidate list used to reproduce the source assignment graph; repeatable. "
            "The final list is derived from loaded recipe data and available_recipes"
        ),
    )
    inf.add_argument("--template", required=True,
                     help="the same host policy/request template accepted by routes request")
    inf.add_argument("--assignments", required=True,
                     help="source viewer draft, assignment set, or prior inference artifact")
    inf.add_argument("--out", required=True,
                     help="write the provenance-bearing furnace inference artifact here")
    inf.add_argument("--request-out", default=None,
                     help="also write the equivalent sealed routing request")
    inf.add_argument("--max-iterations", type=int, default=4096)
    inf.add_argument("--max-states", type=int, default=200000)
    inf.add_argument("--max-steps-per-trace", type=int, default=4096)
    inf.set_defaults(func=_cmd_routes_infer)

    ana = routes.add_parser("analyze", help="analyze a saved request; write result and viewer artifacts")
    common(ana)
    ana.add_argument("--request", required=True, help="a sealed request document (from `routes request`)")
    ana.add_argument("--section", default="summary", choices=list(ANALYSIS_SECTIONS))
    ana.add_argument("--limit", type=int, default=DEFAULT_PAGE_LIMIT)
    ana.add_argument("--cursor", default=None)
    ana.add_argument("--json", dest="json_out", default=None, help="write the summary JSON here")
    ana.add_argument("--result", dest="result_out", default=None, help="write the sealed result document here")
    ana.add_argument("--view", default=None, help="write a standalone viewer page here (graph + result)")
    ana.add_argument("--open", action="store_true")
    ana.set_defaults(func=_cmd_routes_analyze)

    throughput = routes.add_parser(
        "throughput",
        help="compare the restricted analytic operating rate with bound game captures",
    )
    throughput.add_argument("--scenario", required=True,
                            help="sealed factoribot routing throughput scenario")
    throughput.add_argument("--capture", action="append", required=True,
                            help="v3 game-observation capture; repeat for every required run")
    throughput.add_argument("--request", default=None,
                            help="matching sealed routing request for identity verification")
    throughput.add_argument("--result", default=None,
                            help="matching capacity-bound result kept separate in the report")
    throughput.add_argument("--out", required=True, help="write the sealed throughput report")
    throughput.set_defaults(func=_cmd_routes_throughput)

    fnd = routes.add_parser("finding", help="show a finding and the original location of every entity it names")
    common(fnd)
    fnd.add_argument("--finding", required=True, help="a finding ID or a finding code")
    fnd.add_argument("--result", default=None,
                     help="a saved result document; without it the graph's own findings are searched")
    fnd.add_argument("--limit", type=int, default=5)
    fnd.set_defaults(func=_cmd_routes_finding)


def _book_path_arg(value: str):
    from .routing_public import PublicError, parse_book_path

    try:
        return parse_book_path(value)
    except PublicError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="factoribot")
    p.add_argument("--data", default=None, help="path to data-raw-dump.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    sm = sub.add_parser("mcp", help="serve read-only tools over MCP stdio; host supplies the LLM")
    sm.set_defaults(func=_cmd_mcp)

    spl = sub.add_parser("plan", help="optimize multiple inputs/outputs from a JSON spec; no LLM")
    spl.add_argument("--spec", required=True, help="plan JSON file, or - for stdin")
    spl.set_defaults(func=_cmd_tool, name="plan_production")

    st = sub.add_parser("tool", help="call a deterministic tool with JSON arguments; no LLM")
    st.add_argument("name", help="tool name; see tools for schemas")
    st.add_argument("--args", dest="spec", default="-", help="JSON argument file, or - for stdin")
    st.set_defaults(func=_cmd_tool)

    sts = sub.add_parser("tools", help="print deterministic tool schemas as JSON")
    sts.set_defaults(func=_cmd_tools)

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

    sb = sub.add_parser("analyze", help="analyze a blueprint string (offline, no LLM)")
    sb.add_argument("--bp", required=True, help="file with the blueprint string, or - for stdin")
    sb.add_argument("--product", default=None, help="optional output item to analyze")
    sb.set_defaults(func=_cmd_analyze)

    _add_routes(sub)

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
