"""DCF engine checked against hand calculations and closed-form identities."""

import math

import pytest

from deepterminal.finance.timevalue import cagr, gordon_value, linear_path, present_value
from deepterminal.valuation.dcf import DCFInputs, ExplicitReinvestment, SalesToCapital, run_dcf


def two_year(**kw):
    base = dict(base_revenue=100.0, revenue_growth=(0.10, 0.10), ebit_margin=(0.20, 0.20),
                tax_rate=0.25, discount_rate=0.10, terminal_growth=0.02, terminal_roic=0.10,
                reinvestment=SalesToCapital(2.0))
    base.update(kw)
    return DCFInputs(**base)


def test_two_year_dcf_matches_hand_calculation():
    # Year 1: revenue 110, EBIT 22, NOPAT 16.5, reinvestment 10/2 = 5, FCFF 11.5
    # Year 2: revenue 121, EBIT 24.2, NOPAT 18.15, reinvestment 11/2 = 5.5, FCFF 12.65
    # Terminal: NOPAT3 = 121*1.02*0.2*0.75 = 18.513; FCFF3 = 18.513*(1-0.02/0.10) = 14.8104
    #           TV = 14.8104/0.08 = 185.13; PV = 185.13/1.21
    pv1 = 11.5 / 1.1
    pv2 = 12.65 / 1.21
    pv_tv = 185.13 / 1.21
    r = run_dcf(two_year())
    assert [round(y.fcff, 10) for y in r.years] == [11.5, 12.65]
    assert r.terminal_fcff == pytest.approx(14.8104)
    assert r.terminal_value == pytest.approx(185.13)
    assert r.enterprise_value == pytest.approx(pv1 + pv2 + pv_tv)
    assert r.terminal_share == pytest.approx(pv_tv / (pv1 + pv2 + pv_tv))


def test_terminal_roic_equal_to_wacc_collapses_to_nopat_over_wacc():
    for g in (0.0, 0.01, 0.03):
        r = run_dcf(two_year(terminal_growth=g, terminal_roic=0.10))
        nopat_next = 121 * (1 + g) * 0.20 * 0.75
        assert r.terminal_value == pytest.approx(nopat_next / 0.10)


def test_zero_growth_business_is_a_perpetuity():
    inp = DCFInputs(base_revenue=500, revenue_growth=(0.0,) * 5, ebit_margin=(0.1,) * 5,
                    tax_rate=0.2, discount_rate=0.08, terminal_growth=0.0, terminal_roic=0.15,
                    reinvestment=SalesToCapital(3.0))
    nopat = 500 * 0.1 * 0.8
    assert run_dcf(inp).enterprise_value == pytest.approx(nopat / 0.08)


def test_mid_year_convention_shifts_all_flows_half_a_year():
    end = run_dcf(two_year()).enterprise_value
    mid = run_dcf(two_year(mid_year=True)).enterprise_value
    assert mid == pytest.approx(end * 1.10 ** 0.5)


def test_explicit_reinvestment_mode():
    inp = two_year(reinvestment=ExplicitReinvestment(0.02, 0.10))
    r = run_dcf(inp)
    # Year 1 reinvestment = 2% * 110 + 10% * 10 = 3.2
    assert r.years[0].reinvestment == pytest.approx(3.2)
    assert r.years[0].fcff == pytest.approx(16.5 - 3.2)


def test_losses_get_no_tax_shield():
    r = run_dcf(two_year(ebit_margin=(-0.05, 0.20)))
    assert r.years[0].nopat == pytest.approx(-5.5)


@pytest.mark.parametrize("kw", [dict(discount_rate=0.02), dict(ebit_margin=(0.2,)),
                                dict(terminal_roic=0.0), dict(base_revenue=0.0)])
def test_invalid_inputs_rejected(kw):
    with pytest.raises(ValueError):
        run_dcf(two_year(**kw))


def test_warnings():
    r = run_dcf(two_year(terminal_growth=0.05, terminal_roic=0.08, discount_rate=0.09))
    assert any("exceeds a typical" in w for w in r.warnings)
    assert any("destroys value" in w for w in r.warnings)
    assert any("terminal value is" in w for w in r.warnings)


def test_timevalue_primitives():
    assert present_value([110, 121], 0.10) == pytest.approx(200)
    assert gordon_value(5, 0.10, 0.05) == pytest.approx(100)
    assert cagr(100, 121, 2) == pytest.approx(0.10)
    assert linear_path(0.2, 0.0, 3) == pytest.approx([0.2, 0.1, 0.0])
    with pytest.raises(ValueError):
        gordon_value(5, 0.05, 0.05)
    assert math.isclose(linear_path(1, 2, 1)[0], 2)
