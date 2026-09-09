"""Render the routing contract fixtures with the viewer, for manual inspection.

    .venv/bin/python daemon/tests/fixtures/routing_view/render_examples.py OUTDIR

Writes one standalone HTML page per fixture plus `hostile_labels.html`, whose
free text carries script-closing and markup payloads. Nothing here is game data:
every fixture is the synthetic contract example set. The pages are demonstration
artifacts, not checked-in output; a local static server is enough to open them
(`python -m http.server` in OUTDIR), and no page contacts the network.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "daemon"))

from factoribot.blueprint_contract import content_hash, parse_assignments, parse_graph, to_dict  # noqa: E402
from factoribot.blueprint_view import render_view  # noqa: E402
from factoribot.findings import parse_result  # noqa: E402

FIXTURES = ROOT / "daemon" / "tests" / "fixtures" / "routing_contracts"

HOSTILE = [
    "</script><img src=x onerror=\"window.__pwned=1\"><!--",
    "</SCRIPT ><svg/onload=alert(1)>",
    "{\"closing\": \"</script>\"} & <b>markup</b>",
    "line separator paragraph",
]


def render(bundle, title):
    graph = parse_graph(bundle["graph"])
    result = parse_result(bundle["result"], graph) if bundle.get("result") else None
    assignments = parse_assignments(bundle["assignments"], graph) if bundle.get("assignments") else None
    return render_view(to_dict(graph),
                       to_dict(result) if result else None,
                       to_dict(assignments) if assignments else None,
                       title=title)


def hostile(bundle):
    """Message and certificate text do not enter finding identity; rehash only the result."""
    graph = parse_graph(bundle["graph"])
    raw = json.loads(json.dumps(bundle["result"]))
    raw["findings"][0]["message"] = HOSTILE[0]
    raw["bounds"][0]["certificate"] = HOSTILE[1]
    raw["limitations"] = [HOSTILE[2]]
    raw["assumptions"] = [HOSTILE[3]]
    raw["result_hash"] = content_hash({k: v for k, v in raw.items() if k != "result_hash"})
    result = parse_result(raw, graph)
    return render_view(to_dict(graph), to_dict(result),
                       title="Routing audit - hostile labels " + HOSTILE[0])


def main(argv):
    out = pathlib.Path(argv[1] if len(argv) > 1 else "routing_view_pages")
    out.mkdir(parents=True, exist_ok=True)
    for path in sorted(FIXTURES.glob("*.json")):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(bundle, dict) or "graph" not in bundle:
            continue
        page = out / (path.stem + ".html")
        page.write_text(render(bundle, "Routing audit - " + path.stem), encoding="utf-8")
        print(f"{page}  {page.stat().st_size / 1024:.0f} KiB")
    bundle = json.loads((FIXTURES / "shared_budget.json").read_text(encoding="utf-8"))
    page = out / "hostile_labels.html"
    page.write_text(hostile(bundle), encoding="utf-8")
    print(f"{page}  {page.stat().st_size / 1024:.0f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
