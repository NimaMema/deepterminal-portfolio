import pytest

from deepterminal.valuation.bridge import CapitalStructure
from deepterminal.valuation.dcf import DCFInputs, SalesToCapital
from deepterminal.valuation.scenarios import (Scenario, run_scenarios, sensitivity_grid,
                                              standard_shocks, tornado)

CAP = CapitalStructure(basic_shares=10)


def inp(m):
    return DCFInputs(100, (0.05,) * 3, (m,) * 3, 0.25, 0.09, 0.02, 0.12, SalesToCapital(2.0))


def scen(probs=(None, None, None)):
    return [Scenario("bull", "b", inp(0.25), probability=probs[2]),
            Scenario("bear", "x", inp(0.10), probability=probs[0]),
            Scenario("base", "m", inp(0.18), probability=probs[1])]


def test_scenarios_sorted_and_ranged_without_fabricated_weights():
    r = run_scenarios(scen(), CAP, 20.0)
    assert [o.scenario.name for o in r.outcomes] == ["bear", "base", "bull"]
    assert r.weighted_value is None
    lo, hi = r.value_range
    assert lo == r.by_name("bear").per_share and hi == r.by_name("bull").per_share


def test_probabilities_need_basis_and_must_sum_to_one():
    with pytest.raises(ValueError, match="calibration"):
        run_scenarios(scen((0.25, 0.5, 0.25)), CAP, 20.0)
    with pytest.raises(ValueError, match="sum"):
        run_scenarios(scen((0.3, 0.5, 0.3)), CAP, 20.0, calibration_basis="x")
    r = run_scenarios(scen((0.25, 0.5, 0.25)), CAP, 20.0, calibration_basis="historical base rates")
    vals = [o.per_share for o in r.outcomes]
    assert r.weighted_value == pytest.approx(0.25 * vals[0] + 0.5 * vals[1] + 0.25 * vals[2])


def test_requires_bear_base_bull():
    with pytest.raises(ValueError):
        run_scenarios(scen()[:2], CAP, 20.0)


def test_sensitivity_grid_marks_invalid_region_and_is_monotonic():
    g = sensitivity_grid(inp(0.18), CAP, 20.0, [0.02, 0.08, 0.10], [0.01, 0.02, 0.03])
    assert g.values[0][1] is None and g.values[0][2] is None
    assert g.values[1][0] > g.values[2][0]          # higher discount rate → lower value


def test_tornado_sorted_by_swing():
    bars = tornado(inp(0.18), CAP, 20.0, standard_shocks(inp(0.18)))
    swings = [b.swing for b in bars]
    assert swings == sorted(swings, reverse=True)


def test_negative_equity_is_flagged_not_shown_as_a_value():
    r = run_scenarios(scen(), CapitalStructure(basic_shares=10, total_debt=10_000), 20.0)
    assert all(o.per_share == 0 for o in r.outcomes)
    assert any("floor, not an estimate" in w for w in r.warnings)
