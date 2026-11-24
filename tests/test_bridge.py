import pytest

from deepterminal.valuation.bridge import (CapitalStructure, DoubleCountError, OptionTranche,
                                           equity_from_enterprise, market_enterprise_value)


def cap(**kw):
    base = dict(basic_shares=100, rsus=5, options=(OptionTranche(10, 40.0),),
                cash_and_investments=200, operating_cash_requirement=50, total_debt=300,
                minority_interest=20, pension_deficit_after_tax=10)
    base.update(kw)
    return CapitalStructure(**base)


def test_bridge_hand_example():
    # TSM at 50: 10 * (1 - 40/50) = 2 shares → 100 + 5 + 2 = 107
    # Equity = 1000 + (200-50) - 300 - 20 - 10 = 820
    r = equity_from_enterprise(1000, cap(), dilution_price=50)
    assert r.diluted_shares == pytest.approx(107)
    assert r.equity_value == pytest.approx(820)
    assert r.value_per_share == pytest.approx(820 / 107)


def test_out_of_the_money_options_do_not_dilute():
    assert cap().diluted_shares(30) == pytest.approx(105)


def test_market_round_trip():
    c = cap()
    m = market_enterprise_value(64.0, c)
    back = equity_from_enterprise(m.enterprise_value, c, 64.0)
    assert back.value_per_share == pytest.approx(64.0)


def test_convertible_equity_treatment_adds_shares_not_debt():
    c = cap(convertible_face_value=100, convertible_treatment="equity", convertible_conversion_shares=4)
    d = cap(convertible_face_value=100, convertible_treatment="debt")
    assert c.diluted_shares(50) == pytest.approx(111)
    assert equity_from_enterprise(1000, c, 50).equity_value == pytest.approx(820)
    assert equity_from_enterprise(1000, d, 50).equity_value == pytest.approx(720)


def test_double_count_guards():
    with pytest.raises(DoubleCountError):
        equity_from_enterprise(1000, cap(debt_includes_leases=True, lease_liabilities=50,
                                         ebit_after_lease_cost=False), 50)
    with pytest.raises(DoubleCountError):
        equity_from_enterprise(1000, cap(lease_liabilities=50, ebit_after_lease_cost=True), 50)
    ok = equity_from_enterprise(1000, cap(lease_liabilities=50, ebit_after_lease_cost=False), 50)
    assert ok.equity_value == pytest.approx(770)


def test_negative_equity_floors_per_share_at_zero():
    r = equity_from_enterprise(100, cap(), 50)
    assert r.equity_value < 0 and r.value_per_share == 0
    assert any("no residual value" in n for n in r.notes)
