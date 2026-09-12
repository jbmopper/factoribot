"""Regression tests for Fix C: prototype provenance matching in the viewer.

`findings.validate_result` requires a result's `blueprint_hash`, `prototype_hash`
and `graph_hash` to all agree with the graph it describes (see
`validate_result` in `daemon/factoribot/findings.py`). Before this fix,
`blueprint_view.build_view_model` computed `result.graph_match` from only the
blueprint and graph hashes, so a result whose `prototype_hash` disagreed with
(or was missing from) the graph it was rendered against was displayed as
current/matching. These tests reproduce that gap directly against the
`shared_budget` fixture and pin the fix: `prototype_hash` is preserved on the
rendered result and folded into `graph_match`.

These tests deliberately call `build_view_model` on plain, hand-mutated wire
dicts rather than through `parse_result`/`validate_result` (which would reject
the mismatched data outright): the viewer must render defensively without
crashing when it is handed a result whose provenance does not match the graph
it is displayed next to, and it must never present that as current.
"""
import json
import pathlib

import pytest

from factoribot.blueprint_contract import ContractError, content_hash, parse_graph
from factoribot.findings import parse_result
from factoribot.blueprint_view import build_view_model

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "routing_contracts"


def load_bundle():
    return json.loads((FIXTURES / "shared_budget.json").read_text(encoding="utf-8"))


def reseal_result_hash(result: dict) -> dict:
    """Recompute `result_hash` the way the contract/fixture generator does:
    pop the field, hash the canonical JSON of what remains, and set it back."""
    result = dict(result)
    result.pop("result_hash", None)
    result["result_hash"] = content_hash(result)
    return result


def flipped_hash(original: str) -> str:
    """A differently formatted valid `sha256:` + 64 lowercase hex digest hash."""
    prefix, digest = original.split(":", 1)
    flipped = ("0" if digest[0] != "0" else "1") + digest[1:]
    assert flipped != digest
    new = prefix + ":" + flipped
    assert len(new) == len(original)
    return new


# --------------------------------------------------------------- reproduction

def test_reproduction_prototype_only_mismatch_was_shown_as_matching():
    """Pinned reproduction from the task: mutate only prototype_hash, reseal
    result_hash, and confirm the authoritative check rejects it while the
    fixed viewer no longer reports it as matching (this is the exact defect:
    graph_match used to stay True here)."""
    bundle = load_bundle()
    graph_dict = bundle["graph"]
    graph = parse_graph(graph_dict)

    mutated = dict(bundle["result"])
    assert mutated["prototype_hash"] == graph.prototype_hash
    mutated["prototype_hash"] = flipped_hash(mutated["prototype_hash"])
    mutated = reseal_result_hash(mutated)

    # The authoritative path still refuses this: hashes must all agree.
    with pytest.raises(ContractError):
        parse_result(mutated, graph)

    model = build_view_model(graph_dict, mutated, bundle["assignments"])
    assert model["result"]["graph_match"] is False
    assert model["result"]["prototype_hash"] == mutated["prototype_hash"]


# --------------------------------------------------------------------- cases

def test_valid_matching_data_reports_a_match_and_preserves_the_hash():
    bundle = load_bundle()
    graph_dict = bundle["graph"]
    graph = parse_graph(graph_dict)
    # sanity: the fixture is internally consistent before we touch anything
    parse_result(bundle["result"], graph)

    model = build_view_model(graph_dict, bundle["result"], bundle["assignments"])
    result_model = model["result"]
    assert result_model["graph_match"] is True
    assert result_model["prototype_hash"] == graph.prototype_hash
    assert result_model["prototype_hash"] == bundle["result"]["prototype_hash"]
    assert result_model["blueprint_hash"] == graph.blueprint_hash
    assert result_model["graph_hash"] == graph.graph_hash


def test_prototype_only_mismatch_is_not_a_match():
    bundle = load_bundle()
    graph_dict = bundle["graph"]
    graph = parse_graph(graph_dict)

    mutated = dict(bundle["result"])
    mutated["prototype_hash"] = flipped_hash(mutated["prototype_hash"])
    mutated = reseal_result_hash(mutated)
    # blueprint_hash and graph_hash are untouched and still agree with the graph
    assert mutated["blueprint_hash"] == graph.blueprint_hash
    assert mutated["graph_hash"] == graph.graph_hash

    with pytest.raises(ContractError):
        parse_result(mutated, graph)

    model = build_view_model(graph_dict, mutated, bundle["assignments"])
    result_model = model["result"]
    assert result_model["graph_match"] is False, (
        "a prototype-only mismatch must not be displayed as a matching/current result"
    )
    # the mismatched hash is still shown, not silently dropped or overwritten
    assert result_model["prototype_hash"] == mutated["prototype_hash"]
    assert result_model["prototype_hash"] != graph.prototype_hash


def test_missing_prototype_hash_is_not_a_match():
    bundle = load_bundle()
    graph_dict = bundle["graph"]
    graph = parse_graph(graph_dict)

    mutated = dict(bundle["result"])
    del mutated["prototype_hash"]
    mutated = reseal_result_hash(mutated)

    with pytest.raises(ContractError):
        parse_result(mutated, graph)

    model = build_view_model(graph_dict, mutated, bundle["assignments"])
    result_model = model["result"]
    assert result_model["graph_match"] is False, (
        "a result with no prototype_hash at all must not be displayed as current"
    )
    # _generic(None) renders as the literal text "null", not dropped/blank
    assert result_model["prototype_hash"] == "null"


def test_blueprint_hash_mismatch_is_not_a_match():
    bundle = load_bundle()
    graph_dict = bundle["graph"]
    graph = parse_graph(graph_dict)

    mutated = dict(bundle["result"])
    mutated["blueprint_hash"] = flipped_hash(mutated["blueprint_hash"])
    mutated = reseal_result_hash(mutated)

    with pytest.raises(ContractError):
        parse_result(mutated, graph)

    model = build_view_model(graph_dict, mutated, bundle["assignments"])
    assert model["result"]["graph_match"] is False
    # prototype and graph hashes still agree; the mismatch alone must fail the match
    assert model["result"]["prototype_hash"] == graph.prototype_hash
    assert model["result"]["graph_hash"] == graph.graph_hash


def test_graph_hash_mismatch_is_not_a_match():
    bundle = load_bundle()
    graph_dict = bundle["graph"]
    graph = parse_graph(graph_dict)

    mutated = dict(bundle["result"])
    mutated["graph_hash"] = flipped_hash(mutated["graph_hash"])
    mutated = reseal_result_hash(mutated)

    with pytest.raises(ContractError):
        parse_result(mutated, graph)

    model = build_view_model(graph_dict, mutated, bundle["assignments"])
    assert model["result"]["graph_match"] is False
    assert model["result"]["prototype_hash"] == graph.prototype_hash
    assert model["result"]["blueprint_hash"] == graph.blueprint_hash


def test_all_three_hashes_mismatched_is_still_not_a_match():
    bundle = load_bundle()
    graph_dict = bundle["graph"]
    graph = parse_graph(graph_dict)

    mutated = dict(bundle["result"])
    mutated["blueprint_hash"] = flipped_hash(mutated["blueprint_hash"])
    mutated["prototype_hash"] = flipped_hash(mutated["prototype_hash"])
    mutated["graph_hash"] = flipped_hash(mutated["graph_hash"])
    mutated = reseal_result_hash(mutated)

    with pytest.raises(ContractError):
        parse_result(mutated, graph)

    model = build_view_model(graph_dict, mutated, bundle["assignments"])
    assert model["result"]["graph_match"] is False
