"""SYNTHETIC delivery-bound cases with hand-derived expectations (task 05).

Every graph here is built through the public contract constructors; nothing is
a game observation. Each case function returns ``(graph, request, expected)``
where ``expected`` carries the hand derivation written in the comment above it.
The LP's own output is never used as an expectation.

Run ``.venv/bin/python daemon/tests/fixtures/routing_plan/cases.py`` from the
repository root to print every case's expectation and model size.
"""
from __future__ import annotations

from factoribot.blueprint_contract import (
    SCHEMA_VERSION, MECHANICS_PROFILE, BASE_MOD, JsonDocument, content_hash, parse_graph, parse_request, to_dict,
)

PATH = [3, 1]  # nested book entry indices, deliberately not list offsets
BASE_DECLARATION = dict(name=BASE_MOD[0], version=BASE_MOD[1], provides=[], alters_item_mechanics=False)


def eid(n):
    return {"book_path": PATH, "entity_number": n}


def ep(n, name, kind="port"):
    return {"entity": eid(n), "kind": kind, "name": name}


def mat(name):
    return {"kind": "item", "name": name, "quality": "normal"}


def cap(value):
    if value == "unknown":
        return {"kind": "unknown", "value": None}
    return {"kind": "unlimited" if value is None else "finite", "value": value}


def any_item():
    return {"kind": "any_item", "materials": []}


def only(*names):
    return {"kind": "only", "materials": [mat(n) for n in names]}


def seal(value, key):
    value.pop(key, None)
    value[key] = content_hash(value)
    return value


class Layout:
    """Minimal synthetic graph builder over the contract wire format."""

    def __init__(self, name):
        self.name = name
        self.raw = []
        self.g = dict(schema_version=SCHEMA_VERSION, mechanics_profile=MECHANICS_PROFILE, provenance="synthetic",
                      selected_paths=[PATH], entities=[], ports=[], lanes=[], inventories=[], capacity_groups=[],
                      arcs=[], activities=[], evidence=[], topology_gaps=[])
        self._auto = 0

    def entity(self, n, name, x, y, candidates=(), support="supported", subsystem="production"):
        raw = dict(entity_number=n, name=name, position=dict(x=x, y=y), direction=4,
                   tags={"fixture": "SYNTHETIC routing_plan case; not a game observation"})
        self.raw.append(raw)
        self.g["entities"].append(dict(id=eid(n), prototype=name, position=raw["position"],
            footprint={"minimum": dict(x=x - .5, y=y - .5), "maximum": dict(x=x + .5, y=y + .5)},
            direction=4, orientation=None, quality="normal", support=support, subsystem=subsystem, mod="base",
            furnace_candidates=list(candidates), raw=to_dict(JsonDocument.from_value(raw)), evidence_ids=["case_geometry"]))
        return n

    def port(self, n, name, x, y, role, eligibility=None):
        self.g["ports"].append(dict(id=ep(n, name), position=dict(x=x, y=y), direction=4, role=role,
            eligibility=eligibility or any_item(), boundary_candidate=True, evidence_ids=["case_geometry"]))
        return ep(n, name)

    def inventory(self, n, name, x, y, eligibility=None):
        self.g["inventories"].append(dict(id=ep(n, name, "inventory"), position=dict(x=x, y=y),
            eligibility=eligibility or any_item(), storage_capacity=cap(100), evidence_ids=["case_geometry"]))
        return ep(n, name, "inventory")

    def group(self, name, value, kind="lane"):
        self.g["capacity_groups"].append(dict(id=name, kind=kind, unit="seconds/s" if kind == "machine_time" else "items/s",
            capacity=cap(value), evidence_ids=["case_geometry"]))
        return name

    def transfer(self):
        """A fresh explicitly unlimited boundary resource (machine port to belt, etc.)."""
        self._auto += 1
        return self.group(f"transfer_{self._auto}", None, "boundary")

    def arc(self, name, source, target, groups, semantics="exact", conditions=(), eligibility=None):
        if isinstance(groups, str):
            groups = [(groups, 1)]
        self.g["arcs"].append(dict(id=name, source=source, target=target, eligibility=eligibility or any_item(),
            semantics=semantics, conditions=list(conditions),
            resources=[dict(group_id=g, coefficient=c) for g, c in groups], evidence_ids=["case_geometry"]))
        return name

    def belt(self, n, x, y, group=None, capacity=15, eligibility=None):
        self.entity(n, "transport-belt", x, y, subsystem="transport")
        incoming = self.port(n, "left_in", x - .5, y - .2, "incoming", eligibility)
        outgoing = self.port(n, "left_out", x + .5, y - .2, "outgoing", eligibility)
        self.g["lanes"].append(dict(id=ep(n, "left", "lane"), side="left", incoming=incoming, outgoing=outgoing,
            polyline=[dict(x=x - .5, y=y - .2), dict(x=x + .5, y=y - .2)], eligibility=eligibility or any_item(),
            evidence_ids=["case_geometry"]))
        self.arc(f"belt_{n}", incoming, outgoing, group or self.group(f"lane_{n}", capacity))
        return incoming, outgoing

    def machine(self, n, x, y, name="assembling-machine-2", candidates=()):
        self.entity(n, name, x, y, candidates=candidates)
        return self.inventory(n, "ingredients", x, y), self.port(n, "output", x + .5, y, "outgoing")

    def activity(self, name, n, recipe, inputs, outputs, capacity, group, seconds_per_craft=None):
        """inputs/outputs: [(endpoint, item, amount_per_craft)]. capacity None = unlimited."""
        coefficient = seconds_per_craft if seconds_per_craft is not None else (1 / capacity if capacity else 1.0)
        self.g["activities"].append(dict(id=name, entity=eid(n), recipe=recipe,
            inputs=[dict(endpoint=e, material=mat(i), amount_per_craft=a) for e, i, a in inputs],
            outputs=[dict(endpoint=e, material=mat(i), amount_per_craft=a) for e, i, a in outputs],
            craft_capacity=cap(capacity), resources=[dict(group_id=group, coefficient=coefficient)],
            evidence_ids=["case_geometry"]))
        return name

    def gap(self, name, entities, endpoints, may_connect=True, reason="Unsupported entity may connect these endpoints."):
        self.g["topology_gaps"].append(dict(id=name, entity_ids=[eid(n) for n in entities], possible_endpoints=endpoints,
            may_connect=may_connect, reason=reason, evidence_ids=["case_geometry"]))

    def finish(self):
        blueprint = {"blueprint_book": {"item": "blueprint-book", "active_index": 0, "blueprints": [
            {"index": 3, "blueprint_book": {"item": "blueprint-book", "active_index": 0, "blueprints": [
                {"index": 1, "blueprint": {"item": "blueprint", "version": 562949958402048,
                                           "label": f"SYNTHETIC routing_plan {self.name}", "entities": self.raw}}]}}]}}
        prototypes = {"fixture": "synthetic", "profile": MECHANICS_PROFILE,
                      "note": "Hand-defined activities and capacities; NOT a Factorio prototype extract.",
                      "entities": sorted({r["name"] for r in self.raw})}
        self.g.update(blueprint=to_dict(JsonDocument.from_value(blueprint)), prototypes=to_dict(JsonDocument.from_value(prototypes)),
                      blueprint_hash=content_hash(blueprint), prototype_hash=content_hash(prototypes))
        self.g["evidence"] = [dict(id="case_geometry", kind="structural",
            sources=[dict(source="blueprint", uri=f"synthetic:routing_plan/{self.name}",
                          pointer="/blueprint_book/blueprints/0/blueprint_book/blueprints/0/blueprint/entities"),
                     dict(source="prototype", uri=f"synthetic:routing_plan/{self.name}", pointer="/entities")],
            entity_ids=[eid(self.raw[0]["entity_number"])], endpoint_ids=[], arc_path=[],
            description="SYNTHETIC hand-defined geometry and conservation case, not observed game behaviour.")]
        return parse_graph(seal(self.g, "graph_hash"))


def budget(name, item, rate):
    return dict(id=name, material=mat(item), capacity=cap(rate))


def feed(name, budget_name, endpoint, rate=None):
    return dict(id=name, budget_id=budget_name, endpoint=endpoint, capacity=cap(rate))


def export(endpoint, item, rate=0, name="product", mode="minimum", ceiling=None):
    return dict(id=name, material=mat(item), endpoint=endpoint, requirement=mode, rate=rate,
                sink=dict(kind="external", service="Illustrative continuous external removal; not inventory storage", capacity=cap(ceiling)))


def surplus(endpoint, item, name, ceiling=None):
    return dict(id=name, material=mat(item), endpoint=endpoint,
                sink=dict(kind="external", service="Illustrative continuous external disposal", capacity=cap(ceiling)))


def request_document(graph, feeds, budgets, exports, surplus_outlets=(), recipes=(), furnaces=(), controls=(),
                     objective="product", policy="explicit", power="assumed_available"):
    assignments = dict(schema_version=SCHEMA_VERSION, blueprint_hash=graph.blueprint_hash, graph_hash=graph.graph_hash,
                       feeds=feeds, furnaces=list(furnaces), controls=[dict(condition=c, enabled=e) for c, e in controls])
    return seal(dict(schema_version=SCHEMA_VERSION, mechanics_profile=MECHANICS_PROFILE, blueprint_hash=graph.blueprint_hash,
        prototype_hash=graph.prototype_hash, graph_hash=graph.graph_hash, budgets=budgets, exports=exports,
        surplus=list(surplus_outlets),
        objective=dict(kind="feasible", export_id=None) if objective is None else dict(kind="maximize_export", export_id=objective),
        assignments=assignments,
        protected=dict(entities=[], endpoints=[exports[0]["endpoint"]], areas=[], preserve_wiring=True, preserve_unknown=True, preserve_boundaries=True),
        assumptions=dict(game_version="2.0.76", mods=[BASE_DECLARATION], quality="normal", available_recipes=list(recipes),
                         research=[dict(name="inserter-capacity-bonus", level=0)], control_policy=policy, power=power,
                         modules="none", beacons="none", irrelevant=[]),
        detail=dict(kind="full", entity_ids=[], cursor=None, limit=10000)), "request_hash")


def request(graph, *args, **kwargs):
    return parse_request(request_document(graph, *args, **kwargs), graph)


# ---------------------------------------------------------------------------
# Cases. Expected numbers are derived by hand in the comments, never solved.
# ---------------------------------------------------------------------------

def competing_items(lane_capacity=15):
    """Two items share one lane feeding a 1:1 combiner.

    m1: 1 iron -> 1 a (10 crafts/s), m2: 1 copper -> 1 b (10 crafts/s), both onto
    belt 3 (lane 15/s), belt 3 feeds m4: 1 a + 1 b -> 1 c (10 crafts/s).
    Budgets iron 20, copper 20.
      aggregate: c <= min(10, 10, 10) = 10 (each machine 10 crafts/s, inputs free).
      budget:    iron/copper 20 each >= 10, still 10.
      routing:   a + b <= 15 on the shared lane and a = b = c, so c <= 7.5.
    A per-item copy of the lane (a <= 15 and b <= 15 separately) would give 10.
    """
    L = Layout("competing_items")
    inv1, out1 = L.machine(1, 0, 0)
    inv2, out2 = L.machine(2, 0, 2)
    p3, q3 = L.belt(3, 2, 1, capacity=lane_capacity)
    inv4, out4 = L.machine(4, 4, 1)
    L.arc("m1_to_belt", out1, p3, L.transfer())
    L.arc("m2_to_belt", out2, p3, L.transfer())
    L.arc("belt_to_m4", q3, inv4, L.transfer())
    L.activity("make_a", 1, "synthetic-a", [(inv1, "iron-plate", 1)], [(out1, "item-a", 1)], 10, L.group("m1_time", 1, "machine_time"))
    L.activity("make_b", 2, "synthetic-b", [(inv2, "copper-plate", 1)], [(out2, "item-b", 1)], 10, L.group("m2_time", 1, "machine_time"))
    L.activity("make_c", 4, "synthetic-c", [(inv4, "item-a", 1), (inv4, "item-b", 1)], [(out4, "item-c", 1)], 10, L.group("m4_time", 1, "machine_time"))
    graph = L.finish()
    req = request(graph, [feed("iron_feed", "iron", inv1), feed("copper_feed", "copper", inv2)],
                  [budget("iron", "iron-plate", 20), budget("copper", "copper-plate", 20)],
                  [export(out4, "item-c")], recipes=("synthetic-a", "synthetic-b", "synthetic-c"))
    return graph, req, dict(aggregate=10, budget=10, routing=lane_capacity / 2, status="feasible_relaxed",
                            wrong_per_item_copies=10)


def shared_inserter(inserter_capacity=5, gate_capacity=None):
    """Two alternative pickups through one inserter group into one machine.

    Feeds iron at belt 1 and belt 3 (one 20/s budget, lanes 15/s each). Arcs p1
    (belt 1 -> m2) and p2 (belt 3 -> m2) both use inserter group `ins` (5/s).
    m2: 1 iron -> 1 gear, 10 crafts/s; export gear at m2 output.
      aggregate: 10 (machine).  budget: min(10, 20) = 10.
      routing:   p1 + p2 <= 5 (one shared ceiling) so 5.
    Copying the ceiling per arc would give 10; charging the inserter twice per
    traversal (e.g. once per endpoint) would give 2.5.
    With gate_capacity=3, p1 additionally crosses lane group `gate` (3/s) and p2
    is removed: the arc consumes both resources, so routing = min(5, 3) = 3.
    """
    L = Layout("shared_inserter")
    p1, q1 = L.belt(1, 0, 0)
    p3, q3 = L.belt(3, 0, 2)
    inv2, out2 = L.machine(2, 2, 1)
    ins = L.group("ins", inserter_capacity, "inserter")
    if gate_capacity is None:
        L.arc("p1", q1, inv2, ins)
        L.arc("p2", q3, inv2, ins)
        routing = min(inserter_capacity if inserter_capacity != "unknown" else 10, 10)
    else:
        L.arc("p1", q1, inv2, [(ins, 1), (L.group("gate", gate_capacity), 1)])
        routing = min(inserter_capacity, gate_capacity)
    L.activity("gears", 2, "synthetic-gear", [(inv2, "iron-plate", 1)], [(out2, "iron-gear-wheel", 1)], 10, L.group("m2_time", 1, "machine_time"))
    graph = L.finish()
    req = request(graph, [feed("feed_a", "iron", p1), feed("feed_b", "iron", p3)], [budget("iron", "iron-plate", 20)],
                  [export(out2, "iron-gear-wheel")], recipes=("synthetic-gear",))
    return graph, req, dict(aggregate=10, budget=10, routing=routing, status="feasible_relaxed", wrong_double_charge=2.5, wrong_per_arc_copy=10)


def blocked_byproduct(scrap_sink=None, gear_minimum=0, objective="product"):
    """A byproduct with no outlet pins its producer to zero.

    m1: 1 iron -> 1 gear + 1 scrap (10 crafts/s) onto belt 2 (15/s); gear exported
    at belt 2's exit; iron budget 10. Scrap has no export or surplus outlet, so
    conservation forces crafts = 0 at every stage: bound 0 (feasible for a
    minimum of 0, insufficient for a minimum of 1).
    With a scrap surplus outlet of scrap_sink=3/s at the machine output, crafts
    <= 3 and the gear bound is 3 at every stage (machine 10, iron 10 are looser).
    """
    L = Layout("blocked_byproduct")
    inv1, out1 = L.machine(1, 0, 0)
    p2, q2 = L.belt(2, 2, 0)
    L.arc("m1_to_belt", out1, p2, L.transfer())
    L.activity("gears", 1, "synthetic-gear-scrap", [(inv1, "iron-plate", 1)], [(out1, "iron-gear-wheel", 1), (out1, "scrap", 1)], 10,
               L.group("m1_time", 1, "machine_time"))
    graph = L.finish()
    outlets = [] if scrap_sink is None else [surplus(out1, "scrap", "scrap_out", scrap_sink)]
    req = request(graph, [feed("iron_feed", "iron", inv1)], [budget("iron", "iron-plate", 10)],
                  [export(q2, "iron-gear-wheel", gear_minimum)], surplus_outlets=outlets, recipes=("synthetic-gear-scrap",),
                  objective=objective)
    value = 0 if scrap_sink is None else scrap_sink
    # objective=None (feasible): same status; a certified routing infeasibility is insufficient under either objective (1.1.1).
    status = "insufficient" if gear_minimum > value else "feasible_relaxed"
    return graph, req, dict(aggregate=value, budget=value, routing=value, status=status)


def pass_through(iron_budget=10, gear_exact=2, objective="iron_out"):
    """Direct input pass-through competing with an internal consumer.

    Feed iron at belt 1 (15/s lane); belt exit exports iron (objective, sink 20)
    and also feeds m2: 2 iron -> 1 gear (10 crafts/s) with an exact gear export.
      aggregate: iron unlimited, so iron export <= sink ceiling 20.
      budget:    iron_budget - 2 * gear_exact (10 - 4 = 6).
      routing:   the lane (15) is not binding, so also 6.
    """
    L = Layout("pass_through")
    p1, q1 = L.belt(1, 0, 0)
    inv2, out2 = L.machine(2, 2, 0)
    L.arc("belt_to_m2", q1, inv2, L.transfer())
    L.activity("gears", 2, "synthetic-gear2", [(inv2, "iron-plate", 2)], [(out2, "iron-gear-wheel", 1)], 10, L.group("m2_time", 1, "machine_time"))
    graph = L.finish()
    req = request(graph, [feed("iron_feed", "iron", p1)], [budget("iron", "iron-plate", iron_budget)],
                  [export(q1, "iron-plate", 0, "iron_out", ceiling=20), export(out2, "iron-gear-wheel", gear_exact, "gear_out", "exact")],
                  recipes=("synthetic-gear2",), objective=objective)
    value = iron_budget - 2 * gear_exact
    if value < 0:
        return graph, req, dict(aggregate=20, budget="infeasible", routing="infeasible", status="insufficient")
    return graph, req, dict(aggregate=20, budget=value, routing=value, status="feasible_relaxed")


def mixed_variants():
    """Two machine variants of one recipe with different speed and yield.

    m1: 1 iron -> 1 gear at 2 crafts/s (0.5 s/craft of 1 s/s machine time);
    m2: 1 iron -> 1.2 gear at 4 crafts/s (0.25 s/craft), a pinned productivity
    coefficient. Both outputs go onto belt 3 (5/s lane) whose exit exports gear.
    Feeds: iron into each machine, one 5/s budget.
      aggregate: 2*1 + 4*1.2 = 6.8 gear/s.
      budget:    max xA + 1.2 xB s.t. xA + xB <= 5, xA <= 2, xB <= 4 -> xB = 4, xA = 1: 5.8.
      routing:   lane 5/s: 5.
    """
    L = Layout("mixed_variants")
    inv1, out1 = L.machine(1, 0, 0)
    inv2, out2 = L.machine(2, 0, 2, name="assembling-machine-2")
    p3, q3 = L.belt(3, 2, 1, capacity=5)
    L.arc("m1_to_belt", out1, p3, L.transfer())
    L.arc("m2_to_belt", out2, p3, L.transfer())
    L.activity("gears_slow", 1, "synthetic-gear", [(inv1, "iron-plate", 1)], [(out1, "iron-gear-wheel", 1)], 2, L.group("m1_time", 1, "machine_time"), 0.5)
    L.activity("gears_fast", 2, "synthetic-gear", [(inv2, "iron-plate", 1)], [(out2, "iron-gear-wheel", 1.2)], 4, L.group("m2_time", 1, "machine_time"), 0.25)
    graph = L.finish()
    req = request(graph, [feed("feed_a", "iron", inv1), feed("feed_b", "iron", inv2)], [budget("iron", "iron-plate", 5)],
                  [export(q3, "iron-gear-wheel")], recipes=("synthetic-gear",))
    return graph, req, dict(aggregate=6.8, budget=5.8, routing=5, status="feasible_relaxed")


def series_tight():
    """Three constraints tight in series: relaxing one alone does not help.

    Feed iron (10/s budget) at belt 1 (5/s lane) -> m2 (machine time 1 s/s at
    0.2 s/craft = 5 crafts/s, craft capacity unlimited) -> belt 3 (5/s) -> export.
      routing = 5, tight at lane_1, m2_time and lane_3.
      counterfactual lane_1 = 10: still 5.  lane_1 = lane_3 = 10, m2_time = 2: 10 (budget).
    """
    L = Layout("series_tight")
    p1, q1 = L.belt(1, 0, 0, capacity=5)
    inv2, out2 = L.machine(2, 2, 0)
    p3, q3 = L.belt(3, 4, 0, capacity=5)
    L.arc("belt_to_m2", q1, inv2, L.transfer())
    L.arc("m2_to_belt", out2, p3, L.transfer())
    L.activity("gears", 2, "synthetic-gear", [(inv2, "iron-plate", 1)], [(out2, "iron-gear-wheel", 1)], None, L.group("m2_time", 1, "machine_time"), 0.2)
    graph = L.finish()
    req = request(graph, [feed("iron_feed", "iron", p1)], [budget("iron", "iron-plate", 10)], [export(q3, "iron-gear-wheel")], recipes=("synthetic-gear",))
    return graph, req, dict(aggregate=5, budget=5, routing=5, status="feasible_relaxed", one_relaxed=5, all_relaxed=10)


def cycle():
    """A belt loop that could carry gratuitous circulating flow.

    Feed iron (10/s) at belt 1 (15/s); belt 1 -> belt 2 (15/s) -> back to belt 1.
    Export iron at belt 1 exit. Bound 10 at every stage (budget). Any positive
    flow on `loop_back`/`belt_2` is a cycle that the secondary objective removes.
    """
    L = Layout("cycle")
    p1, q1 = L.belt(1, 0, 0)
    p2, q2 = L.belt(2, 2, 0)
    L.arc("forward", q1, p2, L.transfer())
    L.arc("loop_back", q2, p1, L.transfer())
    graph = L.finish()
    req = request(graph, [feed("iron_feed", "iron", p1)], [budget("iron", "iron-plate", 10)], [export(q1, "iron-plate")])
    return graph, req, dict(aggregate="unlimited", budget=10, routing=10, status="feasible_relaxed")


def conditional_gate(policy="explicit", enabled=True):
    """A conditional connection between two belts.

    Feed iron (10/s) at belt 1 (15/s); conditional arc `gate` (condition
    gate_enabled) to belt 2 (15/s); export iron (minimum 1) at belt 2's exit.
      explicit enabled / relax_open: 10 (budget); explicit disabled: no route,
      so the 1/s minimum is insufficient (aggregate/budget still 10).
    """
    L = Layout("conditional_gate")
    p1, q1 = L.belt(1, 0, 0)
    p2, q2 = L.belt(2, 2, 0)
    L.arc("gate", q1, p2, L.transfer(), semantics="conditional", conditions=("gate_enabled",))
    graph = L.finish()
    controls = [("gate_enabled", enabled)] if policy == "explicit" else []
    req = request(graph, [feed("iron_feed", "iron", p1)], [budget("iron", "iron-plate", 10)], [export(q2, "iron-plate", 1)],
                  controls=controls, policy=policy)
    open_ = policy == "relax_open" or enabled
    return graph, req, dict(aggregate="unlimited", budget=10, routing=10 if open_ else "infeasible",
                            status="feasible_relaxed" if open_ else "insufficient")


def unsupported_bridge():
    """competing_items plus an unknown entity that may bridge belt 3 to m4 directly: partial."""
    L = Layout("unsupported_bridge")
    inv1, out1 = L.machine(1, 0, 0)
    p3, q3 = L.belt(3, 2, 1)
    inv4, out4 = L.machine(4, 4, 1)
    L.arc("m1_to_belt", out1, p3, L.transfer())
    L.activity("make_a", 1, "synthetic-a", [(inv1, "iron-plate", 1)], [(out1, "item-a", 1)], 10, L.group("m1_time", 1, "machine_time"))
    L.activity("make_c", 4, "synthetic-c", [(inv4, "item-a", 1)], [(out4, "item-c", 1)], 10, L.group("m4_time", 1, "machine_time"))
    L.entity(5, "synthetic-unknown-bridge", 3, 1, support="unsupported", subsystem="unknown")
    L.gap("possible_bridge", [5], [q3, inv4])
    graph = L.finish()
    req = request(graph, [feed("iron_feed", "iron", inv1)], [budget("iron", "iron-plate", 20)], [export(out4, "item-c", 1)],
                  recipes=("synthetic-a", "synthetic-c"))
    return graph, req, dict(status="partial")


def furnace_choice(override="stone-brick", stone=10):
    """An electric furnace with two candidate recipes sharing one machine time.

    Furnace 1: iron-plate (1 ore -> 1 plate) or stone-brick (2 stone -> 1 brick),
    each 10 crafts/s on a 1 s/s machine group. Only a stone feed (stone/s budget)
    is declared; bricks are exported from belt 2 (15/s).
      no override: ambiguous -> partial.
      stone-brick: aggregate 10 (machine), budget stone/2 = 5, routing 5.
      iron-plate:  no ore feed, so 0 bricks and 0 plates: bound 0 (zero objective).
    """
    L = Layout("furnace_choice")
    L.entity(1, "electric-furnace", 0, 0, candidates=("iron-plate", "stone-brick"))
    inv1 = L.inventory(1, "ingredients", 0, 0)
    out1 = L.port(1, "output", .5, 0, "outgoing")
    p2, q2 = L.belt(2, 2, 0)
    L.arc("furnace_to_belt", out1, p2, L.transfer())
    time_ = L.group("furnace_time", 1, "machine_time")
    L.activity("plates", 1, "iron-plate", [(inv1, "iron-ore", 1)], [(out1, "iron-plate", 1)], 10, time_)
    L.activity("bricks", 1, "stone-brick", [(inv1, "stone", 2)], [(out1, "stone-brick", 1)], 10, time_)
    graph = L.finish()
    furnaces = [] if override is None else [dict(entity=eid(1), recipe=override)]
    req = request(graph, [feed("stone_feed", "stone", inv1)], [budget("stone", "stone", stone)], [export(q2, "stone-brick")],
                  recipes=("iron-plate", "stone-brick"), furnaces=furnaces)
    if override is None:
        return graph, req, dict(status="partial")
    if override == "iron-plate":
        return graph, req, dict(aggregate=0, budget=0, routing=0, status="feasible_relaxed")
    return graph, req, dict(aggregate=10, budget=stone / 2, routing=stone / 2, status="feasible_relaxed")


CASES = {
    "competing_items": competing_items,
    "shared_inserter": shared_inserter,
    "blocked_byproduct": blocked_byproduct,
    "pass_through": pass_through,
    "mixed_variants": mixed_variants,
    "series_tight": series_tight,
    "cycle": cycle,
    "conditional_gate": conditional_gate,
    "unsupported_bridge": unsupported_bridge,
    "furnace_choice": furnace_choice,
}


if __name__ == "__main__":
    from factoribot.blueprint_plan import analyze_delivery

    for name, build in CASES.items():
        graph, req, expected = build()
        report = analyze_delivery(graph, req)
        sizes = {s: v.sizes for s, v in report.stages.items()}
        values = {s: v.value for s, v in report.stages.items()}
        print(f"{name}: status={report.result.status} expected={expected} values={values} sizes={sizes}")
