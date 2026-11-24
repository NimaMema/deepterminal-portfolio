"""Forensic scores against hand-calculated examples."""

import pytest

from deepterminal.forensics import altman_z, beneish, piotroski, sloan_accruals

P = dict(revenue=1000, gross_profit=400, accounts_receivable=100, assets_current=500, ppe_net=300,
         total_assets=1000, depreciation=50, sga=150, liabilities_current=200, total_debt=200,
         net_income=80, operating_cash_flow=100, diluted_shares=100, retained_earnings=300,
         operating_income=120, total_liabilities=500, shareholders_equity=500)
C = dict(revenue=1200, gross_profit=456, accounts_receivable=150, assets_current=560, ppe_net=320,
         total_assets=1100, depreciation=55, sga=168, liabilities_current=230, total_debt=180,
         net_income=110, operating_cash_flow=90, diluted_shares=101, retained_earnings=380,
         operating_income=150, total_liabilities=520, shareholders_equity=580)


def test_beneish_hand_calculation():
    r = beneish(C, P)
    dsri = (150 / 1200) / (100 / 1000)                      # 1.25
    gmi = 0.40 / 0.38
    aqi = (1 - 880 / 1100) / (1 - 800 / 1000)               # 0.2/0.2 = 1
    sgi = 1.2
    depi = (50 / 350) / (55 / 375)
    sgai = (168 / 1200) / (150 / 1000)
    tata = (110 - 90) / 1100
    lvgi = (410 / 1100) / (400 / 1000)
    m = (-4.84 + .92 * dsri + .528 * gmi + .404 * aqi + .892 * sgi + .115 * depi - .172 * sgai
         + 4.679 * tata - .327 * lvgi)
    assert r.components["dsri"] == pytest.approx(1.25)
    assert r.components["aqi"] == pytest.approx(1.0)
    assert r.score == pytest.approx(m)
    assert r.zone == ("elevated" if m > -1.78 else "not elevated")
    assert any("not evidence" in c for c in r.caveats)


def test_beneish_refuses_to_impute():
    c = dict(C)
    del c["sga"]
    r = beneish(c, P)
    assert r.score is None and r.missing == ["sgai"]


def test_piotroski_signals():
    r = piotroski(C, P)
    comps = r.components
    assert comps["roa_positive"] == 1 and comps["cfo_positive"] == 1
    assert comps["cfo_exceeds_net_income"] == 0              # 90 < 110
    assert comps["no_dilution"] == 0                         # 101 > 100
    assert comps["leverage_falling"] == 1                    # 180/1100 < 200/1000
    assert comps["current_ratio_rising"] == 0                # 560/230=2.43 < 2.5
    assert comps["gross_margin_rising"] == 0                 # 0.38 < 0.40
    assert r.score == sum(comps.values())


def test_altman_variants():
    z2 = altman_z(C)
    x1, x2, x3, x4 = 330 / 1100, 380 / 1100, 150 / 1100, 580 / 520
    assert z2.name == "Altman Z''" and z2.score == pytest.approx(6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4)
    z = altman_z(C, market_value_equity=2600)
    assert z.score == pytest.approx(1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * 5 + 1.0 * 1200 / 1100)
    assert z.zone == "safe"


def test_sloan():
    assert sloan_accruals(C, P) == pytest.approx(20 / 1050)
