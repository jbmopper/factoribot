"""Numerical soundness of the LP certificates (Fix A).

Every expectation here is derived by hand in the comment above it. The solver's
own answer is never the expectation; where the solver's answer *was* the defect,
the test states the true optimum and an independent feasible point that exceeds
the value the old code certified.

The defect these regressions pin: a weak-duality bound needs
``r.x >= sum_j inf{r_j t : l_j <= t <= u_j}``, which is ``-infinity`` as soon as
one reduced cost is negative on a column with no ceiling -- *at any magnitude*,
because that column's value is unbounded. The old certificate discarded such a
reduced cost whenever ``|r_j| <= 1e-9``, exactly the band in which HiGHS is
allowed to call a dual-infeasible point "optimal".
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import pytest

from factoribot.blueprint_plan import analyze_delivery
from factoribot.routing_lp import (
    LPModel, LPSolution, dual_bound, implied_upper_bounds, solve_lp, _repair_step,
)

HERE = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("routing_plan_cases", HERE / "fixtures" / "routing_plan" / "cases.py")
cases = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cases)


def _solution(model, *, ineq=None, eq=None):
    """A hand-written LPSolution, so a certificate can be judged on chosen multipliers."""
    return LPSolution(status=0, message="hand-written", x=None, fun=None,
                      ineq_marginals=ineq, eq_marginals=eq, seconds=0.0, rows=model.matrices()[5])


# ---------------------------------------------------------------------------
# 1. The reported defect, at the LP layer.
# ---------------------------------------------------------------------------

def test_tiny_negative_cost_on_an_unbounded_column_is_not_certified():
    """min -5e-10 x over x >= 0 has optimum -infinity (take x -> infinity).

    HiGHS calls x = 0 optimal because the reduced cost -5e-10 is inside its 1e-9
    dual feasibility tolerance. The certificate must not repeat that: with no
    ceiling on x, inf{-5e-10 t : t >= 0} is -infinity, so these multipliers bound
    nothing. Before this fix: value 0.0, valid True, i.e. "the maximum is 0".
    """
    model = LPModel()
    model.variable(("x",))  # 0 <= x, no upper bound
    cost = [-5e-10]

    solved = solve_lp(model, cost, time_limit=10)
    assert solved.status == 0 and solved.fun == 0.0  # the optimizer's word, not a proof

    certificate = dual_bound(model, cost, solved, tolerance=1e-9)
    assert certificate.valid is False
    assert certificate.value == -math.inf
    assert certificate.uncertified_variables == (("x",),)
    assert certificate.worst_reduced_cost == pytest.approx(-5e-10, rel=1e-9)
    # x = 2e9 is feasible with objective -1: the withheld "bound" of 0 was false.
    assert -5e-10 * 2e9 == pytest.approx(-1.0)


def test_the_same_column_with_a_real_ceiling_is_still_certified():
    """Counterexample to "reject every small negative reduced cost".

    Same column and cost, plus the row x <= 4. The true optimum is -2e-9 at x = 4,
    and the certificate must still produce a finite bound rather than withhold.
    """
    model = LPModel()
    column = model.variable(("x",))
    model.add(model.row(("cap",), "ub", 4.0), column, 1.0)
    cost = [-5e-10]

    solved = solve_lp(model, cost, time_limit=10)
    certificate = dual_bound(model, cost, solved, tolerance=1e-12)
    assert certificate.valid is True
    assert certificate.value <= -2e-9 * (1 - 1e-9)  # a valid lower bound on the true -2e-9
    assert certificate.value >= -2e-9 * (1 + 1e-6)  # and not a vacuous one


# ---------------------------------------------------------------------------
# 2. The reported defect, through the contract graph.
# ---------------------------------------------------------------------------

def tiny_yield_layout(yield_per_craft=5e-10):
    """One machine: 1 iron -> ``yield_per_craft`` gear, unlimited everywhere.

    Craft capacity unlimited, machine time unlimited, iron budget and feed
    unlimited, gear sink unlimited. Gear export is therefore UNBOUNDED at every
    stage: c crafts per second consume c iron (unlimited) and deliver
    ``yield_per_craft * c`` gear, and c has no ceiling. Any finite certified
    bound is false; before this fix all three stages certified 0 items/s.
    """
    layout = cases.Layout("tiny_yield")
    ingredients, output = layout.machine(1, 0, 0)
    layout.activity("gears", 1, "synthetic-gear", [(ingredients, "iron-plate", 1)],
                    [(output, "iron-gear-wheel", yield_per_craft)], None,
                    layout.group("m1_time", None, "machine_time"))
    graph = layout.finish()
    request = cases.request(graph, [cases.feed("iron_feed", "iron", ingredients)],
                            [cases.budget("iron", "iron-plate", None)],
                            [cases.export(output, "iron-gear-wheel", 0, "product", ceiling=None)],
                            recipes=("synthetic-gear",))
    return graph, request


def test_unbounded_tiny_yield_layout_advertises_no_bound():
    """No stage may claim a finite ceiling on an unbounded export."""
    graph, request = tiny_yield_layout()
    report = analyze_delivery(graph, request)

    assert report.result.status == "solver_limit"
    assert list(report.result.bounds) == []  # before: three "optimal" scenarios of 0 items/s
    assert {solution.state for solution in report.stages.values()} == {"uncertified"}
    assert any("solver_limit" in finding.code for finding in report.result.findings)
    # Nothing anywhere may still carry the false ceiling as a finding.
    assert not any(finding.capacity_upper_bound is not None for finding in report.result.findings)
    assert not any(finding.evidence_kind == "upper_bound" for finding in report.result.findings)


def test_the_unbounded_layout_really_is_unbounded():
    """Independent of the LP: exhibit a feasible point 10^12 times the certified 0.

    1000 gear/s needs 1000 / 5e-10 = 2e12 crafts/s, hence 2e12 iron/s, all of
    which the layout permits (no craft, machine-time, budget, feed or sink
    ceiling). Conservation holds exactly at both endpoints, so the model's
    feasible set contains a point whose objective export is 1000 items/s.
    """
    from factoribot.blueprint_plan import resolve_model_inputs
    from factoribot.routing_lp import build_lp

    graph, request = tiny_yield_layout()
    inputs = resolve_model_inputs(graph, request)
    for stage in ("aggregate", "budget", "routing"):
        model = build_lp(inputs, stage)
        point = [0.0] * model.n_variables
        crafts = 1000.0 / 5e-10
        point[model.var_index[("craft", "gears")]] = crafts
        point[model.var_index[("import", "iron_feed")]] = crafts
        point[model.var_index[("export", "product")]] = 5e-10 * crafts
        a_ub, b_ub, a_eq, b_eq, bounds, _ = model.matrices()
        assert all(low <= value <= high for value, (low, high) in zip(point, bounds))
        if a_eq is not None:
            assert max(abs(a_eq @ point - b_eq)) <= 1e-9
        if a_ub is not None:
            assert max(a_ub @ point - b_ub) <= 1e-9
        assert point[model.var_index[("export", "product")]] == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# 3. A normal bounded model stays exactly as sharp as before.
# ---------------------------------------------------------------------------

def test_bounded_model_keeps_a_bit_exact_certificate():
    """min -2a - b over a, b >= 0, a + b <= 4, a <= 3.

    The optimum is a = 3, b = 1 with value -7: a is worth twice b, so fill a to
    its own ceiling first and spend the remaining unit of the shared row on b.
    Dual: y(a+b<=4) = -1, y(a<=3) = -1, giving r_a = -2 + 1 + 1 = 0, r_b = 0 and
    the bound -1*4 + -1*3 = -7. The rigorous evaluation must return exactly -7.0,
    not a widened -7.000000000000001: the products and the sum are exact here and
    the certificate proves that rather than assuming an error.
    """
    model = LPModel()
    a = model.variable(("a",))
    b = model.variable(("b",))
    shared = model.row(("shared",), "ub", 4.0)
    own = model.row(("own",), "ub", 3.0)
    model.add(shared, a, 1.0)
    model.add(shared, b, 1.0)
    model.add(own, a, 1.0)
    cost = [-2.0, -1.0]

    solved = solve_lp(model, cost, time_limit=10)
    assert solved.status == 0 and solved.fun == pytest.approx(-7.0)
    certificate = dual_bound(model, cost, solved, tolerance=1e-9)
    assert certificate.valid is True
    assert certificate.value == -7.0
    assert {term.label for term in certificate.cut} == {("shared",), ("own",)}
    # Deterministic: the same multipliers give the same bits every time.
    assert dual_bound(model, cost, solved, tolerance=1e-9).value == -7.0


# ---------------------------------------------------------------------------
# 4. The conservative bound: a ceiling proven from the rows, not declared.
# ---------------------------------------------------------------------------

def test_implied_ceilings_are_derived_from_the_rows():
    """x, y, z >= 0 with 2x <= 10, y - 3x = 0 and z - y = 0: x <= 5, y <= 15, z <= 15.

    Only the first is a one-row consequence; y needs x's ceiling and z needs y's,
    so this also pins the iteration. Derived ceilings are rounded outwards, so
    they may exceed the exact value slightly but must never fall below it (a
    ceiling that is too small would silently strengthen a bound into a false one).
    Bounds propagate in the upper direction only: a tighter x <= 3.5 that would
    need the *lower* bound y >= 3 is deliberately not derived.
    """
    model = LPModel()
    x = model.variable(("x",))
    y = model.variable(("y",))
    z = model.variable(("z",))
    # Deliberately in reverse dependency order, so one pass cannot reach the end.
    relay = model.row(("relay",), "eq", 0.0)
    model.add(relay, z, 1.0)
    model.add(relay, y, -1.0)
    chain = model.row(("chain",), "eq", 0.0)
    model.add(chain, y, 1.0)
    model.add(chain, x, -3.0)
    model.add(model.row(("cap",), "ub", 10.0), x, 2.0)

    ceilings = implied_upper_bounds(model)
    assert 5.0 <= ceilings[x] <= 5.0 * (1 + 1e-6)
    assert 15.0 <= ceilings[y] <= 15.0 * (1 + 1e-6)
    assert 15.0 <= ceilings[z] <= 15.0 * (1 + 1e-5)
    # A single pass cannot reach the end of the chain; the iteration is what does.
    single = implied_upper_bounds(model, rounds=1)
    assert single[x] <= 5.0 * (1 + 1e-6) and math.isinf(single[z])


def test_a_negative_reduced_cost_is_charged_to_an_implied_ceiling():
    """Trivial multipliers y = 0 on: min -x over x >= 0 with x <= 10 as a row.

    With y = 0 the reduced cost is r = c = -1 on a column whose *declared* upper
    bound is infinite, so the old rule would either certify nothing or (if -1 had
    been small) certify a false 0. The row proves x <= 10 at every feasible point,
    so the honest conservative bound is -10 (slightly below, because the derived
    ceiling is rounded outwards). The true optimum is exactly -10, so this is a
    valid and useful bound obtained without trusting the solver at all.
    """
    model = LPModel()
    column = model.variable(("x",))
    model.add(model.row(("cap",), "ub", 10.0), column, 1.0)
    cost = [-1.0]

    certificate = dual_bound(model, cost, _solution(model, ineq=[0.0]), tolerance=1e-9)
    assert certificate.valid is True
    assert certificate.value <= -10.0            # a valid lower bound on the true optimum -10
    assert certificate.value >= -10.0 * (1 + 1e-6)  # and not vacuous
    assert any(term.label[0] == "implied" for term in certificate.cut)


def test_without_a_row_the_same_multipliers_certify_nothing():
    """Counterexample to the previous test: drop the row and the model is unbounded.

    min -x over x >= 0 alone has optimum -infinity. Nothing about the column
    changed except that no constraint proves a ceiling, so the certificate must
    flip from -10 to withheld.
    """
    model = LPModel()
    model.variable(("x",))
    certificate = dual_bound(model, [-1.0], _solution(model), tolerance=1e-9)
    assert certificate.valid is False
    assert certificate.uncertified_variables == (("x",),)


# ---------------------------------------------------------------------------
# 5. The repair step, and what it must refuse to repair.
# ---------------------------------------------------------------------------

def test_repair_step_refuses_a_column_whose_own_cost_points_the_wrong_way():
    """y(t) = t*y makes r(t) = (1-t)c + t*r; at t = 0 the reduced cost is c itself.

    So a violation can only be walked off when c_j > 0 for that column. With
    c_j = -5e-10 (the defect's column) no positive step exists, and with c_j = 0
    (a column the objective does not price at all) none exists either: scaling
    cannot invent a bound, only give back one the trivial multipliers already had.
    """
    assert _repair_step([-5e-10], [(0, -5e-10, 0.0, 1)]) == 0.0
    assert _repair_step([0.0], [(0, -1e-15, 0.0, 1)]) == 0.0
    step = _repair_step([1.0], [(0, -1e-15, 0.0, 1)])
    assert 0.0 < step < 1.0 and step > 1 - 1e-11  # the repaired bound loses ~1e-12 relative


def test_infeasibility_certificate_survives_the_stricter_rule():
    """pass_through with iron 10 and an exact gear export of 6 is infeasible.

    2 iron per gear, so 6 gears need 12 iron/s while the budget is 10/s. The
    minimum total export shortfall is exactly 1 gear/s (10 iron -> 5 gears), and
    the analysis must still certify a positive shortfall rather than fall back to
    "no claim": the slack column that carries the shortfall is unbounded above,
    and its reduced cost picks up a ~1e-15 dual infeasibility from the solver.
    """
    graph, request, _ = cases.pass_through(iron_budget=10, gear_exact=6)
    report = analyze_delivery(graph, request)

    assert report.result.status == "insufficient"
    routing = report.stages["routing"]
    assert routing.state == "infeasible"
    assert routing.shortfall == pytest.approx(1.0, abs=1e-9)
    assert "shortfall of at least" in routing.certificate


def test_non_finite_multipliers_are_rejected():
    """Optimizer success is not enough: NaN multipliers prove nothing."""
    model = LPModel()
    column = model.variable(("x",), 0.0, 5.0)
    model.add(model.row(("cap",), "ub", 4.0), column, 1.0)
    certificate = dual_bound(model, [-1.0], _solution(model, ineq=[float("nan")]), tolerance=1e-9)
    assert certificate.valid is False
    assert "non-finite" in certificate.reason


def test_an_infinite_right_hand_side_cannot_carry_a_multiplier():
    """y_i * b_i with b_i = +infinity and y_i < 0 is -infinity, not a bound."""
    model = LPModel()
    column = model.variable(("x",), 0.0, 5.0)
    model.add(model.row(("cap",), "ub", math.inf), column, 1.0)
    certificate = dual_bound(model, [-1.0], _solution(model, ineq=[-1.0]), tolerance=1e-9)
    assert certificate.valid is False
    assert "infinite right-hand side" in certificate.reason
