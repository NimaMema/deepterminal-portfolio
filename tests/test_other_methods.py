import pytest

from deepterminal.valuation import multiples as mx
from deepterminal.valuation.equity_models import (gordon_ddm, justified_price_to_book,
                                                  residual_income_value)
from deepterminal.valuation.normalization import (NonRecurringItem, maintenance_capex_greenwald,
                                                  normalised_margin, remove_nonrecurring,
                                                  sbc_adjusted_fcf)
from deepterminal.valuation.selection import CompanyProfile, Method, select_methods
from deepterminal.valuation.sotp import AssetLine, Segment, adjusted_net_asset_value, sum_of_the_parts


def test_multiples_and_guards():
    assert mx.price_to_earnings(1000, 40).value == pytest.approx(25)
    neg = mx.price_to_earnings(1000, -5)
    assert not neg.meaningful and "earnings" in neg.reason
    assert mx.peg(mx.price_to_earnings(1000, 40), 0.20).value == pytest.approx(1.25)
    assert not mx.peg(neg, 0.2).meaningful
    assert mx.fcf_yield(-10, 1000).value == pytest.approx(-0.01)
    assert mx.ev_to_ebitda(1200, 100).value == pytest.approx(12)


def test_comparables_interquartile_range():
    peers = [mx.Peer("a", 8), mx.Peer("b", 10), mx.Peer("c", 12), mx.Peer("d", 14), mx.Peer("e", None)]
    cv = mx.comparable_valuation("EBITDA", 100, peers)
    # inclusive quartiles of [8,10,12,14]: 9.5, 11, 12.5
    assert (cv.low_multiple, cv.median_multiple, cv.high_multiple) == pytest.approx((9.5, 11, 12.5))
    assert (cv.implied_low, cv.implied_high) == pytest.approx((950, 1250))
    assert cv.excluded == (("e", "multiple missing or not meaningful"),)


def test_historical_multiple_context():
    ctx = mx.historical_multiple_context(15, [10, 12, 14, 16])
    assert ctx.percentile == pytest.approx(0.75)
    assert ctx.mean == pytest.approx(13)


def test_justified_pb_and_ddm():
    assert justified_price_to_book(0.12, 0.10, 0.04) == pytest.approx(0.08 / 0.06)
    assert gordon_ddm(6, 0.10, 0.06) == pytest.approx(150)


def test_residual_income_equals_ddm_under_clean_surplus():
    # ROE 12%, payout 50% → g = 6%; DDM: D1 = 6, value = 6 / (0.10 - 0.06) = 150
    ri = residual_income_value(100, (0.12,) * 5, (0.5,) * 5, 0.10, 0.06)
    assert ri.equity_value == pytest.approx(gordon_ddm(6, 0.10, 0.06))
    assert ri.ending_book_values[0] == pytest.approx(106)


def test_sotp_and_nav():
    r = sum_of_the_parts([Segment("A", 600, "EV/EBITDA 8x"), Segment("B", 400, "DCF")],
                         annual_corporate_cost=10, tax_rate=0.25, discount_rate=0.09, growth=0.015)
    assert r.capitalised_corporate_costs == pytest.approx(7.5 / 0.075)
    assert r.enterprise_value == pytest.approx(900)
    nav = adjusted_net_asset_value([AssetLine("cash", 100, 1.0, "cash"),
                                    AssetLine("inventory", 200, 0.5, "distressed sale haircut")], 120)
    assert nav.net_asset_value == pytest.approx(80)
    with pytest.raises(ValueError):
        adjusted_net_asset_value([AssetLine("x", 1, 1, " ")], 0)


def test_normalisation():
    nm = normalised_margin([100, 100, 100, 100], [5, 10, 15, 25], "median")
    assert nm.normalised_margin == pytest.approx(0.125)
    assert any("cyclically inflated" in w for w in nm.warnings)
    agg = normalised_margin([100, 300, 100], [10, 60, 10], "aggregate")
    assert agg.normalised_margin == pytest.approx(80 / 500)
    split = maintenance_capex_greenwald(100, 50, [50, 60], [100, 120])
    assert split.growth_capex == pytest.approx(25) and split.maintenance_capex == pytest.approx(75)
    assert maintenance_capex_greenwald(100, -50, [50], [100]).growth_capex == 0
    hist = [NonRecurringItem(y, "restructuring", -5) for y in (2021, 2022, 2023)]
    adj = remove_nonrecurring(100, 2023, [NonRecurringItem(2023, "restructuring", -5)], hist)
    assert adj.adjusted == pytest.approx(105) and adj.warnings
    assert sbc_adjusted_fcf(100, 30, 15) == 55


def _methods(p):
    return {(m.method, m.role) for m in select_methods(p)}


def test_method_selection():
    bank = _methods(CompanyProfile(is_financial_institution=True, pays_dividends=True))
    assert (Method.RESIDUAL_INCOME, "primary") in bank and (Method.DCF, "excluded") in bank
    loss = _methods(CompanyProfile(profitable=False, positive_fcf=False, high_growth=True))
    assert (Method.PE, "excluded") in loss and (Method.EV_REVENUE, "cross-check") in loss
    cyc = _methods(CompanyProfile(cyclical=True))
    assert (Method.NORMALISED_DCF, "primary") in cyc
    conglom = _methods(CompanyProfile(segments=4, peers_available=5))
    assert (Method.SOTP, "cross-check") in conglom and (Method.COMPARABLES, "cross-check") in conglom
