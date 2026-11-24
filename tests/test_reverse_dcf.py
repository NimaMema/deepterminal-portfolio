import pytest

from deepterminal.finance.solvers import find_roots
from deepterminal.finance.timevalue import linear_path
from deepterminal.valuation import reverse_dcf as rd
from deepterminal.valuation.bridge import CapitalStructure, equity_from_enterprise, market_enterprise_value
from deepterminal.valuation.dcf import DCFInputs, SalesToCapital, run_dcf

CAP = CapitalStructure(basic_shares=100, cash_and_investments=100, total_debt=300)


def base(**kw):
    d = dict(base_revenue=1000, revenue_growth=tuple(linear_path(0.12, 0.03, 6)),
             ebit_margin=(0.15,) * 6, tax_rate=0.25, discount_rate=0.09, terminal_growth=0.03,
             terminal_roic=0.14, reinvestment=SalesToCapital(2.0))
    d.update(kw)
    return DCFInputs(**d)


def price_of(inp):
    return equity_from_enterprise(run_dcf(inp).enterprise_value, CAP, 1.0).value_per_share


@pytest.mark.parametrize("lever,true_value,shift", [
    (rd.growth_with_fade(), 0.18, lambda b: rd.growth_with_fade().apply(b, 0.18)),
    (rd.target_operating_margin(), 0.21, lambda b: rd.target_operating_margin().apply(b, 0.21)),
    (rd.discount_rate(), 0.075, lambda b: b.with_changes(discount_rate=0.075)),
    (rd.sales_to_capital(), 3.1, lambda b: b.with_changes(reinvestment=SalesToCapital(3.1))),
])
def test_round_trip_recovers_the_generating_assumption(lever, true_value, shift):
    b = base()
    price = price_of(shift(b))
    r = rd.solve_implied(b, lever, price, CAP)
    assert r.status == "unique"
    assert r.solutions[0].value == pytest.approx(true_value, abs=1e-6)
    assert "not a unique market forecast" in r.statement()
    assert "discount rate" in r.held_constant or lever.key == "discount_rate"


def test_value_destroying_growth_lowers_value():
    # Incremental ROIC = margin*(1-t)*s2c = 0.06*0.75*0.5 = 2.25% < 9% WACC
    b = base(ebit_margin=(0.06,) * 6, reinvestment=SalesToCapital(0.5), terminal_roic=0.05)
    lever = rd.growth_with_fade()
    evs = [run_dcf(lever.apply(b, g)).enterprise_value for g in (0.0, 0.1, 0.2, 0.3)]
    assert evs == sorted(evs, reverse=True)


def test_no_solution_is_reported_not_invented():
    r = rd.solve_implied(base(), rd.sales_to_capital(), 10_000.0, CAP)
    assert r.status == "none_in_bounds" and not r.solutions
    assert "No value of" in r.statement()


def test_multiple_roots_are_all_reported():
    scan = find_roots(lambda x: (x - 0.1) * (x - 0.3), 0.0, 0.5)
    assert scan.roots == pytest.approx([0.1, 0.3])
    assert not scan.monotonic


def test_surface_points_each_reproduce_the_market_value():
    b = base()
    price = 25.0
    target = market_enterprise_value(price, CAP).enterprise_value
    m_lever, g_lever = rd.target_operating_margin(), rd.growth_with_fade()
    surface = rd.implied_surface(b, m_lever, [0.12, 0.15, 0.18], g_lever, price, CAP)
    growths = []
    for sp in surface:
        assert len(sp.y_solutions) == 1
        inp = g_lever.apply(m_lever.apply(b, sp.x), sp.y_solutions[0])
        assert run_dcf(inp).enterprise_value == pytest.approx(target, rel=1e-6)
        growths.append(sp.y_solutions[0])
    assert growths == sorted(growths, reverse=True)   # higher margin needs less growth


def test_growth_duration_is_minimal():
    b = base()
    d = rd.implied_growth_duration(b, 0.12, 30.0, CAP, max_years=40)
    assert d.years_required is not None
    n = d.years_required
    assert d.enterprise_values[n - 1] >= d.target_enterprise_value
    if n > 1:
        assert d.enterprise_values[n - 2] < d.target_enterprise_value


def test_implied_market_share_note():
    r = rd.solve_implied(base(), rd.growth_with_fade(), 60.0, CAP,
                         total_addressable_market_final_year=1500)
    assert r.solutions[0].implied_market_share > 1
    assert any("addressable market" in n for n in r.notes)
