"""Contract boundaries and hand-derived counterexamples, independent of an LP."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path

import pytest

from factoribot.blueprint_contract import (
    SCHEMA_VERSION, ContractError, EntityId, EndpointId, Material, JsonDocument, Capacity,
    IrrelevanceDeclaration, ModDeclaration, ModVersion, canonical_json, content_hash,
    parse_graph, parse_request, parse_assignments, to_dict, unresolved_reasons,
    declared_assumptions,
)
from factoribot.findings import parse_result, comparison_hash, finding_id

FIXTURES = Path(__file__).parent / "fixtures" / "routing_contracts"
CASES = ("disconnected_circuit", "shared_budget", "unsupported_bridge", "blocked_export", "furnace_override", "declared_power")
EE_MOD = {"name": "EditorExtensions", "version": "unknown", "provides": ["power"], "alters_item_mechanics": False}


def load(name="shared_budget"):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def seal(value, key):
    value.pop(key, None)
    value[key] = content_hash(value)
    return value


def reseal_result(result):
    if result["interpreted_request"] is not None:
        seal(result["interpreted_request"], "request_hash")
        result["request_hash"] = result["interpreted_request"]["request_hash"]
    return seal(result, "result_hash")


@pytest.mark.parametrize("name", CASES + ("large_layout",))
def test_complete_examples_round_trip_and_assignment_import(name):
    sample = load(name)
    graph = parse_graph(sample["graph"])
    request = parse_request(sample["request"], graph)
    result = parse_result(sample["result"], graph)
    assignments = parse_assignments(sample["assignments"], graph)
    assert request.assignments == assignments
    assert result.interpreted_request == request
    assert parse_graph(json.loads(json.dumps(to_dict(graph)))) == graph
    assert parse_result(json.loads(json.dumps(to_dict(result))), graph) == result
    assert sample["provenance"] == graph.provenance == "synthetic"


def test_hash_has_independent_expected_bytes_and_numeric_equivalence():
    expected = '{"a":[1,0,0.0000001],"z":"é"}'
    value = {"z": "é", "a": [1.0, -0.0, 1e-7]}
    assert canonical_json(value) == expected
    assert content_hash(value) == "sha256:" + hashlib.sha256(expected.encode()).hexdigest()
    assert content_hash(value) == content_hash({"a": [1, 0, .0000001], "z": "é"})
    assert content_hash([1, 2]) != content_hash([2, 1])
    assert content_hash("é") != content_hash("e\u0301")


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}', '{"x": 1}', '{"x":1.0}'])
def test_noncanonical_or_ambiguous_json_rejected(text):
    with pytest.raises(ContractError):
        JsonDocument(text)


def test_immutable_source_and_graph_do_not_alias_callers():
    sample = load()
    graph = parse_graph(sample["graph"])
    sample["graph"]["entities"][0]["position"]["x"] = 100
    assert graph.entities[0].position.x == 0
    with pytest.raises(FrozenInstanceError):
        graph.entities[0].position.x = 100
    decoded = graph.blueprint.value()
    decoded.clear()
    assert graph.blueprint.value()


@pytest.mark.parametrize("path,number", [((-1,), 1), ((True,),1), ((1.0,),1), ((),0), ((),-1), ((),True), ((),1.0)])
def test_malformed_entity_ids_rejected(path, number):
    with pytest.raises(ContractError):
        EntityId(path, number)


@pytest.mark.parametrize("name", ["Left", "left/right", "", "left.out", "1left"])
def test_malformed_endpoint_names_rejected(name):
    with pytest.raises(ContractError):
        EndpointId(EntityId((2,7),1), "port", name)


def test_nested_identity_not_flattened_and_leaf_numbers_may_repeat():
    assert EntityId((2,7),1).key == "bp/2/7/e/1"
    assert EntityId((),1).key == "bp/root/e/1"
    assert EntityId((2,7),1) != EntityId((7,2),1)
    sample = load()
    graph = sample["graph"]
    source = json.loads(graph["blueprint"]["canonical"])
    leaf = deepcopy(source["blueprint_book"]["blueprints"][0]["blueprint_book"]["blueprints"][0])
    leaf["index"] = 9
    source["blueprint_book"]["blueprints"][0]["blueprint_book"]["blueprints"].append(leaf)
    graph["blueprint"] = to_dict(JsonDocument.from_value(source))
    graph["blueprint_hash"] = content_hash(source)
    # Unselected sibling containing the same entity numbers must be retained.
    assert parse_graph(seal(graph,"graph_hash")).selected_paths == ((2,7),)
    source["blueprint_book"]["blueprints"][0]["blueprint_book"]["blueprints"][1]["index"] = 7
    graph["blueprint"] = to_dict(JsonDocument.from_value(source))
    graph["blueprint_hash"] = content_hash(source)
    with pytest.raises(ContractError, match="duplicate book"):
        parse_graph(seal(graph,"graph_hash"))


@pytest.mark.parametrize("collection", ["entities", "ports", "lanes", "capacity_groups", "arcs", "evidence"])
def test_duplicate_graph_identifiers_rejected_even_with_fresh_hash(collection):
    graph = load()["graph"]
    graph[collection].append(deepcopy(graph[collection][0]))
    with pytest.raises(ContractError, match="duplicate"):
        parse_graph(seal(graph, "graph_hash"))


@pytest.mark.parametrize("field", ["blueprint_hash", "prototype_hash", "graph_hash"])
def test_inconsistent_graph_hashes_rejected(field):
    graph = load()["graph"]
    graph[field] = "sha256:" + "0" * 64
    with pytest.raises(ContractError, match="hash"):
        parse_graph(graph)


def test_stale_assignments_requests_results_rejected():
    sample = load()
    graph = parse_graph(sample["graph"])
    sample["assignments"]["graph_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ContractError, match="stale"):
        parse_assignments(sample["assignments"], graph)
    sample["request"]["budgets"][0]["capacity"]["value"] = 20
    with pytest.raises(ContractError, match="request hash"):
        parse_request(sample["request"], graph)
    sample["result"]["limitations"].append("changed")
    with pytest.raises(ContractError, match="result hash"):
        parse_result(sample["result"], graph)


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(unused_machine_options={"smelting":"assembling-machine-2"}),
    lambda r: r["objective"].update(kind="maximize_ratio"),
    lambda r: r["assumptions"].update(quality="legendary"),
    lambda r: r["assumptions"].update(game_version="2.0.76"),
    lambda r: r["assumptions"].update(modules="productivity-module"),
    lambda r: r["assumptions"]["mods"].append({"name":"space-age","version":"2.0.77"}),
    lambda r: r["assumptions"]["mods"].append({"name":"space-age","version":"","provides":[],"alters_item_mechanics":False}),
    lambda r: r["assumptions"]["mods"].append({"name":"base","version":"2.0.77","provides":[],"alters_item_mechanics":False}),
    lambda r: r["assumptions"]["mods"][0].update(version="2.0.76"),
    lambda r: r["assumptions"].update(mods=[]),
    lambda r: r["exports"][0]["sink"].update(kind="buffer"),
    lambda r: r["exports"][0]["sink"].update(service=""),
    lambda r: r["budgets"][0].update(capacity={"kind":"unknown","value":None}),
    lambda r: r["assignments"]["feeds"][0].update(budget_id="unlisted"),
    lambda r: r["assignments"]["feeds"][0]["endpoint"].update(name="left_out"),
    lambda r: r["exports"][0]["endpoint"].update(name="left_in"),
    lambda r: r["budgets"].append(deepcopy(r["budgets"][0]) | {"id":"second_copy"}),
    lambda r: r["exports"].append(deepcopy(r["exports"][0]) | {"id":"second_copy"}),
    lambda r: r["exports"][0].update(rate=True),
    lambda r: r["exports"][0].update(rate=-1),
])
def test_invalid_request_options_sinks_and_budget_duplication(mutate):
    sample = load()
    mutate(sample["request"])
    with pytest.raises(ContractError):
        parse_request(seal(sample["request"],"request_hash"), parse_graph(sample["graph"]))


def test_finite_inventory_does_not_authorize_export():
    sample = load("furnace_override")
    graph = parse_graph(sample["graph"])
    assert graph.inventories[0].storage_capacity.value == 100
    sample["request"]["exports"][0]["sink"] = {"kind":"buffer","service":"100 slots", "capacity":{"kind":"unlimited","value":None}}
    with pytest.raises(ContractError):
        parse_request(seal(sample["request"],"request_hash"),graph)


def test_fluid_identity_preserved_but_not_supported_numerically():
    assert Material("item","water","normal") != Material("fluid","water",None)
    sample = load()
    sample["request"]["budgets"][0]["material"] = to_dict(Material("fluid","water",None))
    with pytest.raises(ContractError):
        parse_request(seal(sample["request"],"request_hash"),parse_graph(sample["graph"]))
    with pytest.raises(ContractError):
        Material("fluid","water","normal")


def test_unknown_and_unlimited_are_distinct():
    assert Capacity("unknown",None) != Capacity("unlimited",None)
    for kind,value in (("finite",None),("unknown",10),("unlimited",0),("finite",float("inf")),("finite",True)):
        with pytest.raises(ContractError):
            Capacity(kind,value)


def test_shared_budget_hand_counterexample_and_resource_accounting():
    sample = load()
    graph = parse_graph(sample["graph"])
    req = parse_request(sample["request"],graph)
    witness = parse_result(sample["result"],graph).witness
    # Independent arithmetic: reserve 5 of a total 10, leaving only 5 for objective.
    assert sum(i.rate for i in witness.imports) == 10 == req.budgets[0].capacity.value
    assert {f.budget_id for f in req.assignments.feeds} == {"iron"}
    assert len(graph.capacity_groups) == 1
    assert {u.group_id for a in graph.arcs for u in a.resources} == {"one_physical_belt"}
    assert sum(f.rate for f in witness.flows) == 10 <= graph.capacity_groups[0].capacity.value
    assert 10 + 5 > req.budgets[0].capacity.value  # plausible duplicated-budget bug


@pytest.mark.parametrize("name", ["disconnected_circuit", "blocked_export"])
def test_missing_delivery_not_confused_with_machine_capacity(name):
    sample = load(name)
    graph = parse_graph(sample["graph"])
    result = parse_result(sample["result"],graph)
    assert graph.activities[0].craft_capacity.value == 10
    assert result.status == "insufficient"
    assert result.bounds[-1].solver_state == "infeasible"
    # Inspection, not a routing algorithm: the missing physical link is explicit.
    if name == "disconnected_circuit":
        assert not any(a.target.entity.entity_number == 3 for a in graph.arcs)
    else:
        assert not any(a.source.entity.entity_number == 1 for a in graph.arcs)


def test_unknown_possible_bridge_cannot_advertise_a_bound_or_infeasibility():
    sample = load("unsupported_bridge")
    graph = parse_graph(sample["graph"])
    result = sample["result"]
    assert graph.topology_gaps[0].may_connect
    assert parse_result(result,graph).status == "partial"
    borrowed = deepcopy(load("disconnected_circuit")["result"]["bounds"][-1])
    req = parse_request(sample["request"],graph)
    borrowed["comparison_hash"] = comparison_hash(req)
    borrowed["constraint_hash"] = content_hash({"comparison_hash":borrowed["comparison_hash"],"stage":"routing"})
    result.update(status="insufficient",bounds=[borrowed])
    with pytest.raises(ContractError,match="unresolved"):
        parse_result(reseal_result(result),graph)


def test_ambiguous_furnace_requires_override_for_claim_and_round_trips():
    sample = load("furnace_override")
    graph = parse_graph(sample["graph"])
    req = parse_request(sample["request"],graph)
    assert req.assignments.furnaces[0].recipe == "stone-brick"
    assert unresolved_reasons(req,graph) == ()
    result = parse_result(sample["result"],graph)
    assert result.witness.activities[0].crafts_per_s == 10 / 2
    # Deleting the override preserves ambiguity, it must not select a default.
    sample["request"]["assignments"]["furnaces"] = []
    unresolved = parse_request(seal(sample["request"],"request_hash"),graph)
    assert "ambiguous furnace" in unresolved_reasons(unresolved,graph)[0]
    sample["result"]["interpreted_request"] = to_dict(unresolved)
    with pytest.raises(ContractError,match="unresolved"):
        parse_result(reseal_result(sample["result"]),graph)
    assignments = to_dict(req.assignments)
    assignments["furnaces"][0]["recipe"] = "steel-plate"
    with pytest.raises(ContractError,match="override"):
        parse_assignments(assignments,graph)


def test_comparison_ignores_display_scope_but_never_budget_changes():
    sample = load()
    graph = parse_graph(sample["graph"])
    baseline = parse_request(sample["request"],graph)
    request = deepcopy(sample["request"])
    request["detail"].update(kind="summary",limit=1)
    scoped = parse_request(seal(request,"request_hash"),graph)
    assert baseline.request_hash != scoped.request_hash
    assert comparison_hash(baseline) == comparison_hash(scoped)
    request["budgets"][0]["capacity"]["value"] = 20
    changed = parse_request(seal(request,"request_hash"),graph)
    assert comparison_hash(changed) != comparison_hash(baseline)
    sample["result"]["interpreted_request"] = to_dict(changed)
    with pytest.raises(ContractError,match="incomparable"):
        parse_result(reseal_result(sample["result"]),graph)


def test_severity_and_message_do_not_change_finding_identity():
    sample = load()
    graph = parse_graph(sample["graph"])
    finding = parse_result(sample["result"],graph).findings[0]
    assert replace(finding,severity="info",message="translated message").id == finding.id
    assert finding_id(finding.code,tuple(reversed(finding.entity_ids)),finding.endpoint_ids,finding.material,finding.evidence_ids) == finding.id


def test_evidence_path_must_resolve_and_be_contiguous():
    graph = load("disconnected_circuit")["graph"]
    graph["evidence"][0]["arc_path"].reverse()
    with pytest.raises(ContractError,match="contiguous"):
        parse_graph(seal(graph,"graph_hash"))
    graph["evidence"][0]["arc_path"] = ["missing_arc"]
    with pytest.raises(ContractError,match="arc missing"):
        parse_graph(seal(graph,"graph_hash"))
    graph["evidence"][0]["arc_path"] = []
    graph["evidence"][0]["sources"][0]["pointer"] = "/missing"
    with pytest.raises(ContractError,match="pointer"):
        parse_graph(seal(graph,"graph_hash"))


def test_solver_limit_cannot_advertise_uncertified_optimum():
    sample = load()
    graph = parse_graph(sample["graph"])
    sample["result"]["status"] = "solver_limit"
    with pytest.raises(ContractError,match="certified"):
        parse_result(reseal_result(sample["result"]),graph)
    for bound in sample["result"]["bounds"]:
        bound["solver_state"] = "certified_limit"
    assert parse_result(reseal_result(sample["result"]),graph).status == "solver_limit"


def test_nested_bound_values_and_invalid_status_constraints():
    sample = load()
    graph = parse_graph(sample["graph"])
    sample["result"]["bounds"][-1]["value"]["value"] = 6
    with pytest.raises(ContractError,match="nested"):
        parse_result(reseal_result(sample["result"]),graph)
    result = load()["result"]
    result.update(status="invalid_request",interpreted_request=None,request_hash=None,bounds=[],witness=None)
    result["findings"][0]["severity"] = "error"
    result["findings"][0].update(evidence_kind="structural", capacity_upper_bound=None,
                                 required_rate=None, message="Request validation failed.")
    assert parse_result(reseal_result(result),graph).interpreted_request is None
    result["request_hash"] = graph.blueprint_hash
    with pytest.raises(ContractError,match="request hash"):
        parse_result(seal(result,"result_hash"),graph)


def test_pilot_is_reproducible_and_not_claimed_as_original_factory():
    manifest = json.loads((FIXTURES / "pilot_manifest.json").read_text())
    raw = (FIXTURES.parent / "wip_science.txt").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["file_sha256"]
    assert manifest["confirmed_original_factory"] is False
    assert manifest["entity_count"] == 2771
    assert "actual port/lane feeds" in manifest["unresolved"]


def test_machine_alternatives_cannot_duplicate_physical_time_capacity():
    graph = load("furnace_override")["graph"]
    machine_group = deepcopy(next(g for g in graph["capacity_groups"] if g["kind"] == "machine_time"))
    machine_group["id"] = "second_machine_copy"
    graph["capacity_groups"].append(machine_group)
    graph["activities"][1]["resources"][0]["group_id"] = machine_group["id"]
    with pytest.raises(ContractError,match="alternatives must share"):
        parse_graph(seal(graph,"graph_hash"))


def test_source_duplicates_and_lossless_record_mismatch_rejected():
    graph = load()["graph"]
    source = json.loads(graph["blueprint"]["canonical"])
    records = source["blueprint_book"]["blueprints"][0]["blueprint_book"]["blueprints"][0]["blueprint"]["entities"]
    records.append(deepcopy(records[0]))
    graph["blueprint"] = to_dict(JsonDocument.from_value(source))
    graph["blueprint_hash"] = content_hash(source)
    with pytest.raises(ContractError,match="duplicate source"):
        parse_graph(seal(graph,"graph_hash"))
    graph = load()["graph"]
    raw = json.loads(graph["entities"][0]["raw"]["canonical"])
    raw["tags"]["opaque"] = ["changed"]
    graph["entities"][0]["raw"] = to_dict(JsonDocument.from_value(raw))
    with pytest.raises(ContractError,match="raw differs"):
        parse_graph(seal(graph,"graph_hash"))


def test_unknown_capacity_and_conditional_links_need_disclosed_relaxations():
    sample = load()
    sample["graph"]["capacity_groups"][0]["capacity"] = {"kind":"unknown","value":None}
    sample["graph"]["arcs"][0].update(semantics="conditional",conditions=["switch_enabled"])
    graph = parse_graph(seal(sample["graph"],"graph_hash"))
    request = sample["request"]
    request["graph_hash"] = request["assignments"]["graph_hash"] = graph.graph_hash
    with pytest.raises(ContractError,match="control state missing"):
        parse_request(seal(request,"request_hash"),graph)
    request["assumptions"]["control_policy"] = "relax_open"
    req = parse_request(seal(request,"request_hash"),graph)
    result = sample["result"]
    result.update(graph_hash=graph.graph_hash, interpreted_request=to_dict(req))
    for bound in result["bounds"]:
        bound["comparison_hash"] = comparison_hash(req)
        bound["constraint_hash"] = content_hash({"comparison_hash":comparison_hash(req),"stage":bound["stage"]})
    with pytest.raises(ContractError,match="unknown capacities"):
        parse_result(reseal_result(result),graph)
    result["bounds"][-1]["relaxations"] = ["unknown_capacity_unlimited"]
    with pytest.raises(ContractError,match="conditional connections"):
        parse_result(reseal_result(result),graph)
    result["bounds"][-1]["relaxations"].append("conditional_connections_open")
    assert parse_result(reseal_result(result),graph).status == "feasible_relaxed"


def test_scoped_detail_does_not_hide_unknown_bridge():
    sample = load("unsupported_bridge")
    graph = parse_graph(sample["graph"])
    sample["request"]["detail"].update(kind="entities",entity_ids=[to_dict(EntityId((2,7),1))],limit=1)
    request = parse_request(seal(sample["request"],"request_hash"),graph)
    assert unresolved_reasons(request,graph)


def test_unmarked_unsupported_entity_still_withholds_claims():
    sample = load("unsupported_bridge")
    sample["graph"]["topology_gaps"] = []
    graph = parse_graph(seal(sample["graph"],"graph_hash"))
    sample["request"]["graph_hash"] = sample["request"]["assignments"]["graph_hash"] = graph.graph_hash
    request = parse_request(seal(sample["request"],"request_hash"),graph)
    assert "unsupported entity" in unresolved_reasons(request,graph)[0]


# --- 1.1.0: unsupported-subsystem scoping and declared mods ---------------------------------


def rebind(sample, graph):
    """Point a fixture request/result at a re-sealed graph without changing anything else."""
    sample["request"]["graph_hash"] = sample["request"]["assignments"]["graph_hash"] = graph.graph_hash
    sample["result"]["graph_hash"] = graph.graph_hash
    return sample


def reseal_request_result(sample, graph):
    req = parse_request(seal(sample["request"], "request_hash"), graph)
    result = sample["result"]
    result["interpreted_request"] = to_dict(req)
    for bound in result["bounds"]:
        bound["comparison_hash"] = comparison_hash(req)
        bound["constraint_hash"] = content_hash({"comparison_hash": comparison_hash(req), "stage": bound["stage"]})
    return req, reseal_result(result)


def test_schema_version_is_1_1_1_and_fixtures_pin_it():
    assert SCHEMA_VERSION == "1.1.1"
    for name in CASES + ("large_layout",):
        sample = load(name)
        assert sample["graph"]["schema_version"] == sample["request"]["schema_version"] == sample["result"]["schema_version"] == "1.1.1"
    assert ModVersion is ModDeclaration


def test_declared_power_only_substation_permits_bounds_and_is_recorded():
    sample = load("declared_power")
    graph = parse_graph(sample["graph"])
    substation = next(e for e in graph.entities if e.prototype == "ee-super-substation")
    assert (substation.support, substation.subsystem, substation.mod) == ("unsupported", "power", "EditorExtensions")
    req = parse_request(sample["request"], graph)
    assert req.assumptions.power == "assumed_available"
    assert unresolved_reasons(req, graph) == ()
    result = parse_result(sample["result"], graph)
    assert result.status == "feasible_relaxed" and [b.value.value for b in result.bounds] == [10, 10, 10]
    # Independent arithmetic: 10 iron/s at 1 per craft, 10 crafts/s machine, 15/s lane -> 10/s.
    assert min(10 / 1, 10, 15) == 10 == result.witness.exports[0].rate
    assert set(declared_assumptions(req)) == {"mod:EditorExtensions:unknown", "irrelevant:modded_power:power:power_assumed_available"}
    assert set(declared_assumptions(req)) <= set(result.assumptions)


def test_same_substation_without_declaration_withholds_bounds():
    sample = load("declared_power")
    graph = parse_graph(sample["graph"])
    sample["request"]["assumptions"]["irrelevant"] = []
    req, result = reseal_request_result(sample, graph)
    assert unresolved_reasons(req, graph) == ("unsupported entity: bp/2/7/e/3",)
    with pytest.raises(ContractError, match="unresolved"):
        parse_result(result, graph)


def test_result_must_record_accepted_declarations():
    sample = load("declared_power")
    graph = parse_graph(sample["graph"])
    sample["result"]["assumptions"] = ["SYNTHETIC; declarations dropped"]
    with pytest.raises(ContractError, match="recorded in result assumptions"):
        parse_result(reseal_result(sample["result"]), graph)


@pytest.mark.parametrize("subsystem", ["transport", "inserter", "logistics", "production", "other", "unknown"])
def test_item_capable_subsystems_can_never_be_declared_irrelevant(subsystem):
    with pytest.raises(ContractError, match="cannot be declared irrelevant"):
        IrrelevanceDeclaration("x", subsystem, (), "power_assumed_available", "not allowed")
    sample = load("declared_power")
    sample["graph"]["entities"][2]["subsystem"] = subsystem
    if subsystem in ("transport", "inserter", "production", "logistics"):
        # A modded item-capable entity must also be inside the mod's declared scope.
        sample["request"]["assumptions"]["mods"][1]["provides"] = [subsystem]
    graph = parse_graph(seal(sample["graph"], "graph_hash"))
    rebind(sample, graph)
    with pytest.raises(ContractError):
        parse_request(seal(sample["request"], "request_hash"), graph)


@pytest.mark.parametrize("subsystem,basis", [("power", "circuit_control_declared"), ("rail", "power_assumed_available"), ("fluid", "rail_no_item_interface")])
def test_irrelevance_basis_must_match_subsystem(subsystem, basis):
    with pytest.raises(ContractError, match="basis"):
        IrrelevanceDeclaration("x", subsystem, (), basis, "mismatch")


def test_power_irrelevance_requires_power_assumed_available():
    sample = load("declared_power")
    graph = parse_graph(sample["graph"])
    sample["request"]["assumptions"]["power"] = "unknown"
    with pytest.raises(ContractError, match="power assumed available"):
        parse_request(seal(sample["request"], "request_hash"), graph)


def test_irrelevance_entity_scope_must_resolve_to_that_subsystem():
    sample = load("declared_power")
    graph = parse_graph(sample["graph"])
    request = deepcopy(sample["request"])
    request["assumptions"]["irrelevant"][0]["entity_ids"] = [to_dict(EntityId((2, 7), 2))]  # the belt
    with pytest.raises(ContractError, match="subsystem mismatch"):
        parse_request(seal(request, "request_hash"), graph)
    request = deepcopy(sample["request"])
    request["assumptions"]["irrelevant"][0]["entity_ids"] = [to_dict(EntityId((2, 7), 9))]
    with pytest.raises(ContractError, match="unknown irrelevance entity"):
        parse_request(seal(request, "request_hash"), graph)
    request = deepcopy(sample["request"])
    request["assumptions"]["irrelevant"][0]["justification"] = "  "
    with pytest.raises(ContractError, match="justification"):
        parse_request(seal(request, "request_hash"), graph)
    # Subsystem-wide (empty entity list) declaration covers the substation too.
    request = deepcopy(sample["request"])
    request["assumptions"]["irrelevant"][0]["entity_ids"] = []
    req = parse_request(seal(request, "request_hash"), graph)
    assert unresolved_reasons(req, graph) == ()


def test_possible_bridge_still_forces_partial_despite_declarations():
    sample = load("unsupported_bridge")
    graph = parse_graph(sample["graph"])
    assert graph.topology_gaps[0].may_connect
    # Mark a second, power-only entity irrelevant; the bridge itself cannot be declared away.
    sample["request"]["assumptions"]["irrelevant"] = [dict(id="all_power", subsystem="power", entity_ids=[],
        basis="power_assumed_available", justification="Power poles cannot carry items.")]
    req = parse_request(seal(sample["request"], "request_hash"), graph)
    reasons = unresolved_reasons(req, graph)
    assert reasons == ("unsupported topology: possible_bridge",)
    bridge = sample["graph"]["entities"][3]
    assert bridge["subsystem"] == "unknown"
    with pytest.raises(ContractError):
        IrrelevanceDeclaration("bridge", "unknown", (EntityId((2, 7), 4),), "power_assumed_available", "unsound")


def test_gap_asserting_disconnection_needs_structural_or_observed_evidence():
    sample = load("unsupported_bridge")
    sample["graph"]["topology_gaps"][0]["may_connect"] = False
    graph = parse_graph(seal(sample["graph"], "graph_hash"))
    rebind(sample, graph)
    req = parse_request(seal(sample["request"], "request_hash"), graph)
    assert unresolved_reasons(req, graph) == ()  # fixture evidence is structural
    sample["graph"]["evidence"][0]["kind"] = "estimated"
    graph = parse_graph(seal(sample["graph"], "graph_hash"))
    rebind(sample, graph)
    req = parse_request(seal(sample["request"], "request_hash"), graph)
    assert unresolved_reasons(req, graph) == ("unsupported topology: possible_bridge (disconnection needs structural or observed evidence)",)


def test_undeclared_non_base_prototype_is_rejected():
    sample = load("declared_power")
    graph = parse_graph(sample["graph"])
    request = deepcopy(sample["request"])
    request["assumptions"]["mods"] = [request["assumptions"]["mods"][0]]
    with pytest.raises(ContractError, match="undeclared mod prototype: ee-super-substation from EditorExtensions"):
        parse_request(seal(request, "request_hash"), graph)
    request = deepcopy(sample["request"])
    request["assumptions"]["mods"][1]["provides"] = ["circuit"]
    with pytest.raises(ContractError, match="outside declared mod scope"):
        parse_request(seal(request, "request_hash"), graph)


def test_mod_altering_item_mechanics_forces_partial():
    sample = load("declared_power")
    graph = parse_graph(sample["graph"])
    sample["request"]["assumptions"]["mods"][1]["alters_item_mechanics"] = True
    req, result = reseal_request_result(sample, graph)
    assert unresolved_reasons(req, graph) == ("mod alters item mechanics: EditorExtensions",)
    with pytest.raises(ContractError, match="unresolved"):
        parse_result(result, graph)


def test_supported_entity_must_come_from_base():
    graph = load()["graph"]
    graph["entities"][0]["mod"] = "SomeBeltMod"
    with pytest.raises(ContractError, match="base prototypes only"):
        parse_graph(seal(graph, "graph_hash"))
    for bad in ("", " base", "Editor Extensions"):
        graph = load()["graph"]
        graph["entities"][0]["mod"] = bad
        with pytest.raises(ContractError):
            parse_graph(seal(graph, "graph_hash"))


def test_entity_subsystem_is_required_and_enumerated():
    graph = load()["graph"]
    graph["entities"][0]["subsystem"] = "belts"
    with pytest.raises(ContractError, match="unsupported option"):
        parse_graph(seal(graph, "graph_hash"))
    del graph["entities"][0]["subsystem"]
    with pytest.raises(ContractError, match="missing"):
        parse_graph(seal(graph, "graph_hash"))


def test_mod_version_unknown_is_explicit_and_visible():
    assert ModDeclaration("EditorExtensions", "unknown", ("power",), False).version == "unknown"
    for name, version in (("EditorExtensions", ""), ("EditorExtensions", " 2.3.0"), ("", "1.0"), ("Editor Extensions", "1.0")):
        with pytest.raises(ContractError):
            ModDeclaration(name, version, ("power",), False)
    with pytest.raises(ContractError, match="duplicate mod subsystem"):
        ModDeclaration("x", "1", ("power", "power"), False)
    sample = load("declared_power")
    graph = parse_graph(sample["graph"])
    sample["request"]["assumptions"]["mods"].append({"name": "OtherMod", "version": "unknown", "provides": ["circuit"], "alters_item_mechanics": False})
    req = parse_request(seal(sample["request"], "request_hash"), graph)
    assert "mod:OtherMod:unknown" in declared_assumptions(req)
    sample["request"]["assumptions"]["mods"].append(dict(EE_MOD))
    with pytest.raises(ContractError, match="duplicate mod"):
        parse_request(seal(sample["request"], "request_hash"), graph)


def test_declaring_mods_does_not_enable_fluid_or_quality():
    sample = load("declared_power")
    graph = parse_graph(sample["graph"])
    request = deepcopy(sample["request"])
    request["assumptions"]["mods"].append({"name": "FluidMod", "version": "1.0.0", "provides": ["fluid", "production"], "alters_item_mechanics": False})
    request["budgets"][0]["material"] = to_dict(Material("fluid", "water", None))
    with pytest.raises(ContractError, match="fluid|not eligible"):
        parse_request(seal(request, "request_hash"), graph)
    request = deepcopy(sample["request"])
    request["assumptions"]["mods"].append({"name": "QualityMod", "version": "1.0.0", "provides": ["production"], "alters_item_mechanics": False})
    request["assumptions"]["quality"] = "legendary"
    with pytest.raises(ContractError, match="unsupported option"):
        parse_request(seal(request, "request_hash"), graph)
    request = deepcopy(sample["request"])
    request["assumptions"]["game_version"] = "2.0.76"
    with pytest.raises(ContractError, match="unsupported option"):
        parse_request(seal(request, "request_hash"), graph)


# --- 1.1.1: scenarios and infeasibility certificates under a feasible objective --------------


def routing_infeasible_bound(export_id):
    """The fixture's certified routing infeasibility, re-aimed at `export_id`."""
    bound = deepcopy(load("disconnected_circuit")["result"]["bounds"][-1])
    assert (bound["stage"], bound["solver_state"], bound["value"]) == ("routing", "infeasible", None)
    bound["objective_export_id"] = export_id
    return bound


def feasible_objective_case(bounds):
    """`disconnected_circuit` re-aimed at a `feasible` objective and carrying `bounds`."""
    sample = load("disconnected_circuit")
    graph = parse_graph(sample["graph"])
    sample["request"]["objective"] = {"kind": "feasible", "export_id": None}
    sample["result"]["bounds"] = bounds
    return graph, reseal_request_result(sample, graph)


def test_feasible_objective_result_can_certify_insufficiency():
    graph, (req, raw) = feasible_objective_case([routing_infeasible_bound(None)])
    assert (req.objective.kind, req.objective.export_id) == ("feasible", None)
    result = parse_result(raw, graph)
    # Same request as the maximizing fixture: the consumer still gets zero circuits,
    # so the declared 1 science/s minimum export cannot be met by any allocation.
    assert result.status == "insufficient" and req.exports[0].rate == 1
    bound, = result.bounds
    assert (bound.objective_export_id, bound.stage, bound.solver_state, bound.value) == (None, "routing", "infeasible", None)
    assert bound.certificate.strip() and bound.evidence_ids
    assert parse_result(json.loads(json.dumps(to_dict(result))), graph) == result


def test_feasible_objective_scenario_cannot_name_an_export():
    graph, (_, raw) = feasible_objective_case([routing_infeasible_bound("product")])
    with pytest.raises(ContractError, match="bound objective differs from request"):
        parse_result(raw, graph)


def test_feasible_objective_scenario_cannot_claim_a_value():
    optimal = deepcopy(load("disconnected_circuit")["result"]["bounds"][0])
    assert (optimal["stage"], optimal["solver_state"], optimal["value"]["value"]) == ("aggregate", "optimal", 5)
    optimal["objective_export_id"] = None
    graph, (_, raw) = feasible_objective_case([optimal, routing_infeasible_bound(None)])
    # A feasibility request maximizes nothing, so 5/s is not the optimum of anything.
    with pytest.raises(ContractError, match="only certify infeasibility"):
        parse_result(raw, graph)


def test_maximizing_scenario_must_still_name_its_export():
    sample = load("disconnected_circuit")
    graph = parse_graph(sample["graph"])
    assert sample["request"]["objective"] == {"kind": "maximize_export", "export_id": "product"}
    sample["result"]["bounds"] = [routing_infeasible_bound(None)]
    with pytest.raises(ContractError, match="bound objective differs from request"):
        parse_result(reseal_request_result(sample, graph)[1], graph)
