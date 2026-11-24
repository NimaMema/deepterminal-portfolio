from datetime import date

import pytest

from deepterminal.evidence import (EpistemicStatus, LookAheadError, Source, SourcedValue, assumption,
                                   citation_audit, enforce_point_in_time)
from deepterminal.financials.statements import FinancialPeriod, analyse

SRC = Source("s1", "10-K", "SEC", published_at=date(2024, 2, 1))


def test_look_ahead_guard():
    v = SourcedValue("rev", 1, EpistemicStatus.HISTORICAL_FACT, sources=(SRC,))
    enforce_point_in_time([v], date(2024, 2, 1))
    with pytest.raises(LookAheadError):
        enforce_point_in_time([v], date(2024, 1, 31))


def test_citation_audit_rules():
    vals = [SourcedValue("fact", 1, EpistemicStatus.HISTORICAL_FACT),
            SourcedValue("corr", 1, EpistemicStatus.CORROBORATED_FACT, sources=(SRC,)),
            SourcedValue("claim", 1, EpistemicStatus.UNVERIFIED_CLAIM, rationale="x"),
            SourcedValue("old", 1, EpistemicStatus.HISTORICAL_FACT, sources=(SRC,), as_of=date(2020, 1, 1)),
            assumption("wacc", 0.09, "CAPM build-up"),
            SourcedValue("syn", 1, EpistemicStatus.ESTIMATE, sources=(Source("x", "t", "p", synthetic=True),))]
    problems = {(f.name, f.problem.split(":")[0]) for f in citation_audit(vals, date(2024, 6, 1)).findings}
    assert ("fact", "historical_fact has no source") in problems
    assert ("corr", "corroborated_fact needs two or more independent sources") in problems
    assert ("claim", "unverified claim") in problems
    assert ("old", "stale") in problems
    assert ("syn", "synthetic fixture data") in problems
    assert not any(n == "wacc" for n, _ in problems)
    with pytest.raises(ValueError):
        assumption("g", 0.03, "  ")


def _p(y, rev, ar, ni=10, ocf=12, shares=100):
    return FinancialPeriod(y, date(y, 12, 31), rev, rev * 0.15, ni, ocf, 5, depreciation=3,
                           stock_based_comp=2, accounts_receivable=ar, total_assets=200,
                           total_debt=50, cash=20, shareholders_equity=100, interest_expense=2,
                           diluted_shares=shares, gross_profit=rev * 0.4)


def test_statement_metrics_and_flags():
    a = analyse([_p(2023, 100, 10), _p(2024, 110, 15, ni=30, ocf=4, shares=105)])
    m = a.latest()
    assert m.revenue_growth == pytest.approx(0.10)
    assert m.fcf == pytest.approx(-1) and m.fcf_after_sbc == pytest.approx(-3)
    assert m.dso == pytest.approx(15 * 365 / 110)
    assert m.accruals_ratio == pytest.approx(26 / 200)
    assert m.net_debt == 30 and m.interest_coverage == pytest.approx(16.5 / 2)
    codes = {f.code for f in a.flags}
    assert {"RECEIVABLES_OUTPACE_REVENUE", "HIGH_ACCRUALS", "PROFIT_WITHOUT_CASH", "DILUTION"} <= codes
