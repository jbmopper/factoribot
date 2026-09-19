"""Deterministic SYNTHETIC contract examples, not a routing solver or game oracle."""
from __future__ import annotations

import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import zlib

from factoribot.blueprint_contract import (
    SCHEMA_VERSION, MECHANICS_PROFILE, JsonDocument, content_hash, parse_graph,
    parse_request, parse_assignments, to_dict, EntityId, EndpointId, Material,
    declared_assumptions,
)
from factoribot.findings import finding_id, comparison_hash, constraint_hash, parse_result

HERE = Path(__file__).resolve().parent


def eid(n):
    # Nested book indices intentionally differ from flattened list offsets.
    return {"book_path": [2, 7], "entity_number": n}


def ep(n, name, kind="port"):
    return {"entity": eid(n), "kind": kind, "name": name}


def mat(name):
    return {"kind": "item", "name": name, "quality": "normal"}


def cap(value):
    return {"kind": "unlimited" if value is None else "finite", "value": value}


def doc(value):
    return to_dict(JsonDocument.from_value(value))


def seal(value, key):
    value.pop(key, None)
    value[key] = content_hash(value)
    return value


def any_item():
    return {"kind": "any_item", "materials": []}


class Layout:
    def __init__(self, name):
        self.name = name
        self.raw = []
        self.g = dict(schema_version=SCHEMA_VERSION, mechanics_profile=MECHANICS_PROFILE,
                      provenance="synthetic", selected_paths=[[2, 7]], entities=[], ports=[],
                      lanes=[], inventories=[], capacity_groups=[], arcs=[], activities=[], evidence=[], topology_gaps=[])

    def entity(self, n, name, x, y, candidates=(), support="supported", subsystem="production", mod="base"):
        raw = dict(entity_number=n, name=name, position=dict(x=x, y=y), direction=4,
                   tags={"fixture": "SYNTHETIC; illustrative, not game observation", "opaque": ["preserved", n]})
        self.raw.append(raw)
        # subsystem/mod are adapter claims written by the fixture author, not label inference.
        self.g["entities"].append(dict(id=eid(n), prototype=name, position=raw["position"],
            footprint={"minimum": dict(x=x-.5, y=y-.5), "maximum": dict(x=x+.5, y=y+.5)},
            direction=4, orientation=None, quality="normal", support=support, subsystem=subsystem, mod=mod,
            furnace_candidates=list(candidates), raw=doc(raw), evidence_ids=["fixture_geometry"]))

    def port(self, n, name, x, y, role):
        self.g["ports"].append(dict(id=ep(n, name), position=dict(x=x, y=y), direction=4,
            role=role, eligibility=any_item(), boundary_candidate=True, evidence_ids=["fixture_geometry"]))
        return ep(n, name)

    def inventory(self, n, name, x, y):
        self.g["inventories"].append(dict(id=ep(n, name, "inventory"), position=dict(x=x,y=y),
            eligibility=any_item(), storage_capacity=cap(100), evidence_ids=["fixture_geometry"]))
        return ep(n, name, "inventory")

    def group(self, name, value, kind="lane"):
        self.g["capacity_groups"].append(dict(id=name, kind=kind,
            unit="seconds/s" if kind == "machine_time" else "items/s", capacity=cap(value), evidence_ids=["fixture_geometry"]))
        return name

    def arc(self, name, source, target, group):
        self.g["arcs"].append(dict(id=name, source=source, target=target, eligibility=any_item(),
            semantics="exact", conditions=[], resources=[dict(group_id=group, coefficient=1)], evidence_ids=["fixture_geometry"]))

    def belt(self, n, x, y, group=None):
        self.entity(n, "transport-belt", x, y, subsystem="transport")
        incoming = self.port(n, "left_in", x-.5, y-.2, "incoming")
        outgoing = self.port(n, "left_out", x+.5, y-.2, "outgoing")
        self.g["lanes"].append(dict(id=ep(n,"left","lane"), side="left", incoming=incoming,
            outgoing=outgoing, polyline=[dict(x=x-.5,y=y-.2),dict(x=x+.5,y=y-.2)],
            eligibility=any_item(), evidence_ids=["fixture_geometry"]))
        self.arc(f"belt_{n}", incoming, outgoing, group or self.group(f"lane_{n}", 15))
        return incoming, outgoing

    def activity(self, name, n, recipe, source, ingredient, amount, target, product, capacity, group):
        self.g["activities"].append(dict(id=name, entity=eid(n), recipe=recipe,
            inputs=[dict(endpoint=source,material=mat(ingredient),amount_per_craft=amount)],
            outputs=[dict(endpoint=target,material=mat(product),amount_per_craft=1)],
            craft_capacity=cap(capacity), resources=[dict(group_id=group,coefficient=1/capacity)],
            evidence_ids=["fixture_geometry"]))

    def finish(self, path=()):
        blueprint = {"blueprint_book":{"item":"blueprint-book", "active_index":2,"blueprints":[
            {"index":2,"blueprint_book":{"item":"blueprint-book","active_index":7,"blueprints":[
                {"index":7,"blueprint":{"item":"blueprint", "version":562949958402048,
                 "label":f"SYNTHETIC {self.name}", "entities":self.raw,
                 "description":"Illustrative assignments. No owner feed assignments inferred."}}]}}]}}
        prototypes = {"fixture":"synthetic", "profile":MECHANICS_PROFILE,
                      "note":"Hand-defined geometry, activities and capacities; NOT a Factorio prototype extract.",
                      "entities": sorted({r["name"] for r in self.raw})}
        self.g.update(blueprint=doc(blueprint),prototypes=doc(prototypes),
                      blueprint_hash=content_hash(blueprint),prototype_hash=content_hash(prototypes))
        self.g["evidence"] = [dict(id="fixture_geometry",kind="structural",
            sources=[dict(source="blueprint",uri=f"synthetic:{self.name}",pointer="/blueprint_book/blueprints/0/blueprint_book/blueprints/0/blueprint/entities"),
                     dict(source="prototype",uri=f"synthetic:{self.name}",pointer="/entities")],
            entity_ids=[eid(1)],endpoint_ids=[],arc_path=list(path),
            description="SYNTHETIC hand-defined geometry and conservation example, not observed game behavior.")]
        return parse_graph(seal(self.g,"graph_hash"))


BASE_MOD_DECLARATION = dict(name="base", version="2.0.77", provides=[], alters_item_mechanics=False)


def request(graph, feeds, budgets, exports, recipes=(), furnaces=(), mods=(), irrelevant=()):
    assignments = dict(schema_version=SCHEMA_VERSION,blueprint_hash=graph.blueprint_hash,graph_hash=graph.graph_hash,
        feeds=feeds,furnaces=list(furnaces),controls=[])
    value = dict(schema_version=SCHEMA_VERSION,mechanics_profile=MECHANICS_PROFILE,
        blueprint_hash=graph.blueprint_hash,prototype_hash=graph.prototype_hash,graph_hash=graph.graph_hash,
        budgets=budgets,exports=exports,surplus=[],objective=dict(kind="maximize_export",export_id="product"),
        assignments=assignments,protected=dict(entities=[],endpoints=[exports[0]["endpoint"]],areas=[],
        preserve_wiring=True,preserve_unknown=True,preserve_boundaries=True),
        assumptions=dict(game_version="2.0.77",mods=[BASE_MOD_DECLARATION, *mods],quality="normal",
          available_recipes=list(recipes),research=[dict(name="inserter-capacity-bonus",level=0)],
          control_policy="explicit",power="assumed_available",modules="none",beacons="none",irrelevant=list(irrelevant)),
        detail=dict(kind="full",entity_ids=[],cursor=None,limit=10000))
    return parse_request(seal(value,"request_hash"),graph)


def budget(name, item, rate):
    return dict(id=name,material=mat(item),capacity=cap(rate))


def feed(name, budget_name, endpoint, rate=None):
    return dict(id=name,budget_id=budget_name,endpoint=endpoint,capacity=cap(rate))


def export(endpoint, item, rate=1, name="product", mode="minimum", ceiling=None):
    return dict(id=name,material=mat(item),endpoint=endpoint,requirement=mode,rate=rate,
                sink=dict(kind="external",service="Illustrative continuous external removal; not inventory storage",capacity=cap(ceiling)))


def finding(graph, code, kind, message, bound=None, item=None, entities=(1,), path_endpoint=None):
    es = tuple(EntityId((2,7),n) for n in entities)
    endpoints = () if path_endpoint is None else (EndpointId(EntityId(tuple(path_endpoint["entity"]["book_path"]), path_endpoint["entity"]["entity_number"]), path_endpoint["kind"],path_endpoint["name"]),)
    material = None if item is None else Material("item",item,"normal")
    return dict(id=finding_id(code,es,endpoints,material,("fixture_geometry",)),code=code,severity="warning",
        evidence_kind=kind,message=message,entity_ids=to_dict(es),endpoint_ids=to_dict(endpoints),material=to_dict(material),
        required_rate=None if item is None else 1,capacity_upper_bound=bound,evidence_ids=["fixture_geometry"],
        assumptions=["Synthetic fixture with explicitly illustrative assignments"])


def result(graph, req, status, findings, values=(), witness=None):
    fingerprint = comparison_hash(req)
    bounds = []
    for stage,value in values:
        bounds.append(dict(stage=stage,direction="upper",comparison_hash=fingerprint,
            constraint_hash=constraint_hash(fingerprint,stage),objective_export_id="product",unit="items/s",
            value=None if value == "infeasible" else cap(value),
            solver_state="infeasible" if value == "infeasible" else "optimal",
            certificate=("SYNTHETIC hand proof: no arc reaches the demanded endpoint, so its net export cannot reach 1/s."
                         if value == "infeasible" else "SYNTHETIC hand proof: explicit machine, budget or outlet ceiling; illustrative allocation attains the stated relaxed bound."),
            evidence_ids=["fixture_geometry"],assumptions=["Declared illustrative feeds, recipes, external removal and power"],
            relaxations={"aggregate":["delivery_unconstrained","budgets_unlimited"],"budget":["delivery_unconstrained"],"routing":[]}[stage]))
    value = dict(schema_version=SCHEMA_VERSION,analyzer_version="synthetic-contract-fixture-1",blueprint_hash=graph.blueprint_hash,
        prototype_hash=graph.prototype_hash,graph_hash=graph.graph_hash,request_hash=req.request_hash,
        interpreted_request=to_dict(req),status=status,findings=sorted(findings,key=lambda f:f["id"]),bounds=bounds,witness=witness,
        assumptions=["SYNTHETIC; illustrative input and external removal assignments", *declared_assumptions(req)],
        limitations=["Not a game observation or computed routing solution; no achievable-throughput claim"],detail=to_dict(req.detail))
    return parse_result(seal(value,"result_hash"),graph)


def witness(flows=(),activities=(),imports=(),exports=()):
    return dict(flows=[dict(arc_id=a,material=mat(m),rate=r) for a,m,r in flows],
        activities=[dict(activity_id=a,crafts_per_s=r) for a,r in activities],
        imports=[dict(id=i,rate=r) for i,r in imports],exports=[dict(id=i,rate=r) for i,r in exports],
        surplus=[],validation="synthetic_hand_checked",tolerance=1e-8)


def write_case(name, graph, req, res, expectation, compact=False):
    assignment = parse_assignments(to_dict(req.assignments),graph)
    payload = dict(provenance="synthetic",description="SYNTHETIC schema/interaction fixture; all assignments illustrative.",
                   hand_expectation=expectation, graph=to_dict(graph),request=to_dict(req),assignments=to_dict(assignment),result=to_dict(res))
    (HERE / f"{name}.json").write_text(json.dumps(payload,indent=None if compact else 2,sort_keys=True,ensure_ascii=False)+"\n")


def shared_budget():
    layout = Layout("shared_budget")
    shared = layout.group("one_physical_belt",15)
    p1,q1 = layout.belt(1,0,0,shared)
    p2,q2 = layout.belt(2,0,2,shared)
    graph = layout.finish(("belt_1",))
    req = request(graph,[feed("feed_a","iron",p1),feed("feed_b","iron",p2)],
        [budget("iron","iron-plate",10)],
        [export(q1,"iron-plate",0,ceiling=20),export(q2,"iron-plate",5,"reserved","exact")])
    res = result(graph,req,"feasible_relaxed",[finding(graph,"shared_budget","upper_bound",
        "Both feeds together receive at most 10 iron plates/s; after reserving 5/s, product has at most 5/s.",5,"iron-plate",(1,2))],
        [("aggregate",20),("budget",5),("routing",5)],
        witness(flows=[("belt_1","iron-plate",5),("belt_2","iron-plate",5)],imports=[("feed_a",5),("feed_b",5)],exports=[("product",5),("reserved",5)]))
    write_case("shared_budget",graph,req,res,"5 + 5 <= one global budget of 10; both arcs also share one physical capacity of 15. Incorrect per-port budgets permit 15 total.")


def disconnected(bridge=False):
    layout = Layout("unsupported_bridge" if bridge else "disconnected_circuit")
    layout.entity(1,"assembling-machine-2",0,0)
    source = layout.inventory(1,"ingredients",0,0)
    output = layout.port(1,"output",.5,0,"outgoing")
    p,q = layout.belt(2,1,0)
    layout.arc("producer_to_belt",output,p,layout.group("transfer",None,"boundary"))
    layout.entity(3,"assembling-machine-2",4,0)
    target = layout.inventory(3,"ingredients",4,0)
    final = layout.port(3,"output",4.5,0,"outgoing")
    layout.activity("circuits",1,"synthetic-circuit",source,"iron-plate",1,output,"electronic-circuit",10,layout.group("producer_time",1,"machine_time"))
    layout.activity("science",3,"synthetic-science",target,"electronic-circuit",1,final,"production-science-pack",5,layout.group("consumer_time",1,"machine_time"))
    if bridge:
        layout.entity(4,"synthetic-unknown-bridge",2.5,0,support="unsupported",subsystem="unknown")
        layout.g["topology_gaps"].append(dict(id="possible_bridge",entity_ids=[eid(4)],possible_endpoints=[q,target],may_connect=True,
            reason="Unsupported entity may connect the circuit lane to the consumer; dropping it cannot prove disconnection.",evidence_ids=["fixture_geometry"]))
    graph = layout.finish(("producer_to_belt","belt_2"))
    req = request(graph,[feed("iron_feed","iron",source)],[budget("iron","iron-plate",10)],
        [export(final,"production-science-pack")],recipes=("synthetic-circuit","synthetic-science"))
    res = result(graph,req,"partial" if bridge else "insufficient",[finding(graph,
        "unsupported_possible_bridge" if bridge else "disconnected_circuit_producer",
        "conditional" if bridge else "structural",
        "Possible unknown bridge prevents a disconnection proof." if bridge else "Circuit output reaches belt 2 but has no route to machine 3.",entities=(1,2,3))],
        [] if bridge else [("aggregate",5),("budget",5),("routing","infeasible")])
    write_case(layout.name,graph,req,res,"No bound is justified until the possible bridge is modeled." if bridge else "Consumer requires 1 circuit/craft but receives zero, so the 1 science/s minimum is infeasible.")


def blocked_export():
    layout = Layout("blocked_export")
    layout.entity(1,"assembling-machine-2",0,0)
    source = layout.inventory(1,"ingredients",0,0)
    produced = layout.port(1,"output",.5,0,"outgoing")
    p,q = layout.belt(2,3,0)
    layout.activity("make_circuit",1,"synthetic-circuit",source,"iron-plate",1,produced,"electronic-circuit",10,layout.group("machine_time",1,"machine_time"))
    graph = layout.finish(("belt_2",))
    req = request(graph,[feed("iron_feed","iron",source)],[budget("iron","iron-plate",10)],
        [export(q,"electronic-circuit")],recipes=("synthetic-circuit",))
    res = result(graph,req,"insufficient",[finding(graph,"blocked_export","structural",
        "The machine output has no connection to the explicitly declared export lane.",entities=(1,2),path_endpoint=q)],
        [("aggregate",10),("budget",10),("routing","infeasible")])
    write_case(layout.name,graph,req,res,"Production is not net export: the isolated outlet has zero incoming material despite 10 crafts/s machine capacity.")


def furnace():
    layout = Layout("furnace_override")
    layout.entity(1,"electric-furnace",0,0,candidates=("iron-plate","stone-brick"))
    source = layout.inventory(1,"ingredients",0,0)
    output = layout.port(1,"output",.5,0,"outgoing")
    p,q = layout.belt(2,1,0)
    layout.arc("furnace_to_belt",output,p,layout.group("transfer",None,"boundary"))
    machine = layout.group("furnace_time",1,"machine_time")
    layout.activity("iron",1,"iron-plate",source,"iron-ore",1,output,"iron-plate",10,machine)
    layout.activity("brick",1,"stone-brick",source,"stone",2,output,"stone-brick",10,machine)
    graph = layout.finish(("furnace_to_belt","belt_2"))
    req = request(graph,[feed("stone_feed","stone",source)],[budget("stone","stone",10)],
        [export(q,"stone-brick",0)],recipes=("iron-plate","stone-brick"),furnaces=[dict(entity=eid(1),recipe="stone-brick")])
    res = result(graph,req,"feasible_relaxed",[finding(graph,"furnace_override","conditional",
        "Illustrative explicit stone-brick assignment resolves the candidate ambiguity; it is not inferred from the owner.")],
        [("aggregate",10),("budget",5),("routing",5)],witness(flows=[("furnace_to_belt","stone-brick",5),("belt_2","stone-brick",5)],
        activities=[("brick",5)],imports=[("stone_feed",10)],exports=[("product",5)]))
    write_case(layout.name,graph,req,res,"Explicit stone-brick override: 10 stone/s / 2 stone per craft = 5 bricks/s. Fixture craft speed is illustrative, not the real furnace speed.")


def declared_power():
    """Pilot-like: an unsupported modded substation declared power-only; bounds permitted."""
    layout = Layout("declared_power")
    layout.entity(1,"assembling-machine-2",0,0)
    source = layout.inventory(1,"ingredients",0,0)
    produced = layout.port(1,"output",.5,0,"outgoing")
    p,q = layout.belt(2,1,0)
    layout.arc("producer_to_belt",produced,p,layout.group("transfer",None,"boundary"))
    layout.activity("make_circuit",1,"synthetic-circuit",source,"iron-plate",1,produced,"electronic-circuit",10,layout.group("machine_time",1,"machine_time"))
    layout.entity(3,"ee-super-substation",0,3,support="unsupported",subsystem="power",mod="EditorExtensions")
    graph = layout.finish(("producer_to_belt","belt_2"))
    mods = [dict(name="EditorExtensions",version="unknown",provides=["power"],alters_item_mechanics=False)]
    irrelevant = [dict(id="modded_power",subsystem="power",entity_ids=[eid(3)],basis="power_assumed_available",
        justification="Substation is power-only; with power assumed available it cannot carry, insert or transform items.")]
    req = request(graph,[feed("iron_feed","iron",source)],[budget("iron","iron-plate",10)],
        [export(q,"electronic-circuit",0,ceiling=20)],recipes=("synthetic-circuit",),mods=mods,irrelevant=irrelevant)
    res = result(graph,req,"feasible_relaxed",[finding(graph,"unsupported_subsystem_declared_irrelevant","conditional",
        "Unsupported modded substation (mod EditorExtensions, version unknown) is declared power-only and irrelevant under power assumed available; no power coverage claim is made.",entities=(3,))],
        [("aggregate",10),("budget",10),("routing",10)],
        witness(flows=[("producer_to_belt","electronic-circuit",10),("belt_2","electronic-circuit",10)],
            activities=[("make_circuit",10)],imports=[("iron_feed",10)],exports=[("product",10)]))
    write_case(layout.name,graph,req,res,"10 iron/s budget at 1/craft and 10 crafts/s give at most 10 circuits/s on a 15/s lane. The unsupported modded substation cannot touch items, so under power assumed available it does not change the bound; without the declaration the same graph is partial with no bound.")


def large():
    layout = Layout("large_layout")
    for n in range(1,3201):
        layout.belt(n,((n-1)%80)*2,((n-1)//80)*2)
    graph = layout.finish(("belt_1",))
    req = request(graph,[feed("iron_feed","iron",ep(1,"left_in"))],[budget("iron","iron-plate",5)],
        [export(ep(1,"left_out"),"iron-plate",0,ceiling=15)])
    res = result(graph,req,"feasible_relaxed",[finding(graph,"synthetic_selection_target","structural",
        "Select this finding to highlight entity 1 and its left-lane path; all 3200 belts are synthetic.",path_endpoint=ep(1,"left","lane"))],
        [("aggregate",15),("budget",5),("routing",5)],
        witness(flows=[("belt_1","iron-plate",5)],imports=[("iron_feed",5)],exports=[("product",5)]))
    write_case(layout.name,graph,req,res,"3200 independent lanes in an 80 x 40 grid; only lane 1 has illustrative supply/export.",compact=True)


def pilot_manifest():
    path = HERE.parent / "wip_science.txt"
    raw = path.read_bytes()
    blueprint = json.loads(zlib.decompress(base64.b64decode(raw.decode().strip()[1:])))
    entities = blueprint["blueprint"]["entities"]
    manifest = dict(provenance="development_pilot",confirmed_original_factory=False,
        source="daemon/tests/fixtures/wip_science.txt",file_sha256=hashlib.sha256(raw).hexdigest(),
        blueprint_hash=content_hash(blueprint),blueprint_format_version=blueprint["blueprint"]["version"],
        entity_count=len(entities),prototypes=dict(sorted(Counter(e["name"] for e in entities).items())),
        unresolved=["actual port/lane feeds", "actual export locations", "enabled mod versions", "research", "control states", "power", "versioned prototype extract"],
        illustrative_budget_target={"stone":30,"copper-plate":30,"plastic-bar":30,"iron-plate":60},
        target="net production-science-pack; AM2; no modules; internally produced steel and bricks")
    (HERE/"pilot_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")


if __name__ == "__main__":
    shared_budget()
    disconnected()
    disconnected(bridge=True)
    blocked_export()
    furnace()
    declared_power()
    large()
    pilot_manifest()
    print("Generated and validated six synthetic cases, 3200-entity layout and development pilot manifest.")
