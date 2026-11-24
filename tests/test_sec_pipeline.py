"""SEC → case → valuation → report/dashboard, on SYNTHETIC EDGAR-format data (offline)."""

import json
from datetime import date, datetime, timezone

import pytest

import sec_synth as S
from deepterminal.cli import main
from deepterminal.data import sec_edgar as se
from deepterminal.data.http import CachedFetcher, FetchResult, NotFound
from deepterminal.data.sec_case import (InsufficientData, PriceQuote, ValuationSettings, build_sec_case)
from deepterminal.pipeline import run_case
from deepterminal.reporting.dashboard import render_dashboard
from deepterminal.reporting.provenance import provenance_csv, provenance_rows
from deepterminal.reporting.report import render_report

RETRIEVED = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
ANALYSIS = date(2026, 10, 28)
PRICE = PriceQuote(30.0, date(2026, 10, 27), "synthetic test price (fictional company)")
IDENT = se.CompanyIdentity(0, "SYNQ", "SYNTHETIC QUARTERLY CO (fictional)", sic="3571")


@pytest.fixture
def facts():
    return S.build()


@pytest.fixture
def cache(tmp_path):
    """Offline cache in SECClient layout holding SYNTHETIC responses."""
    import hashlib
    f = CachedFetcher(tmp_path, "test")
    for key, url, obj in (("company_tickers.json", se.TICKERS_URL, S.TICKERS),
                          ("submissions_0000000000.json.gz", se.SUBMISSIONS_URL.format(cik=0), S.SUBMISSIONS),
                          ("companyfacts_0000000000.json.gz", se.COMPANYFACTS_URL.format(cik=0), S.build())):
        body = json.dumps(obj).encode()
        f.write_cache(key, FetchResult(url, body, RETRIEVED, hashlib.sha256(body).hexdigest(), False, None))
    return tmp_path


def test_quarters_ttm_and_point_in_time(facts):
    q = se.quarterly_series(facts, "revenue")
    assert q[date(2025, 12, 31)].value == pytest.approx(380e6)          # FY − 9M
    assert q[date(2025, 12, 31)].derivation == "FY − 9M YTD"
    ocf = se.quarterly_series(facts, "operating_cash_flow")
    assert ocf[date(2026, 6, 30)].value == pytest.approx(375e6 * 0.18)  # 6M YTD − Q1
    ttm = se.build_ttm_period(facts)
    assert (ttm.period_start, ttm.period_end) == (date(2025, 7, 1), date(2026, 6, 30))
    assert ttm.revenue == pytest.approx(350 + 380 + 360 + 375)
    # Before the Q2-2026 10-Q was filed, TTM ends at Q1 2026
    early = se.build_ttm_period(facts, as_of=date(2026, 7, 1))
    assert early.period_end == date(2026, 3, 31)
    assert early.revenue == pytest.approx(340 + 350 + 380 + 360)
    # And before the FY2023 restatement, the original figure is used
    pit = se.build_periods(facts, as_of=date(2024, 6, 1))
    assert pit[-1].fiscal_year == 2023 and pit[-1].revenue == pytest.approx(1150)


def test_every_figure_has_source_period_and_retrieval(facts):
    periods = se.build_periods(facts, retrieved_at=RETRIEVED) + [se.build_ttm_period(facts, retrieved_at=RETRIEVED)]
    for p in periods:
        for name in ("revenue", "operating_income", "net_income", "operating_cash_flow", "capex", "cash"):
            prov = p.provenance[name]
            assert prov.accession and prov.filed and prov.period_end and prov.retrieved_at == RETRIEVED
            assert prov.source_url.startswith("https://www.sec.gov/Archives/edgar/data/")
            assert prov.value == pytest.approx(getattr(p, name))
    d = se.build_ttm_period(facts, retrieved_at=RETRIEVED).provenance["operating_cash_flow"]
    assert d.derivation == "sum of four quarters" and len(d.inputs) == 4
    assert any(i.derivation for i in d.inputs)       # derived quarters keep their inputs


def test_revisions_detected(facts):
    revs = {(r.field, r.period_end): r for r in se.detect_revisions(facts)}
    r = revs[("revenue", date(2023, 12, 31))]
    assert (r.original, r.revised) == (1150e6, 1210e6)


def test_build_case_and_run(facts):
    case = build_sec_case(facts, IDENT, PRICE, ValuationSettings(discount_rate=0.09),
                          analysis_date=ANALYSIS, retrieved_at=RETRIEVED)
    assert case.synthetic and case.ttm is not None        # fixture detected and labelled and case.latest_label == "TTM to 2026-06-30"
    base = case.base_inputs
    assert base.base_revenue == pytest.approx(1465)
    assert base.ebit_margin[0] == pytest.approx(0.20)
    assert base.revenue_growth[0] == pytest.approx((1400 / 1100) ** (1 / 3) - 1)
    assert base.tax_rate == pytest.approx(0.20)
    # capital structure: cash + marketable, debt, minority; lease not subtracted
    cap = case.capital
    assert cap.cash_and_investments == pytest.approx(250) and cap.total_debt == pytest.approx(300)
    assert cap.minority_interest == pytest.approx(10) and cap.basic_shares == pytest.approx(99)
    assert any("lease" in n for n in case.notes)
    rationales = {a.name: a.rationale for a in case.assumptions}
    assert "CAGR" in rationales["base_growth"] and "effective tax" in rationales["tax_rate"]
    a = run_case(case)
    assert a.case.data_validation.passed
    sol = a.reverse[0].solutions[0]
    assert sol.model.enterprise_value == pytest.approx(a.market.enterprise_value, rel=1e-7)
    md = render_report(a)
    assert "Figure provenance" in md and "Data validation" in md and "SYNTHETIC DATA" in md
    assert any(f.problem == "synthetic fixture data" for f in a.citations.findings)
    assert "SEC EDGAR XBRL companyfacts" in md and "TTM to 2026-06-30" in md
    html = render_dashboard(a)
    assert "Data provenance &amp; validation" in html and "TTM to 2026-06-30" in html
    assert "<script src" not in html and "<link" not in html     # still no external resources
    csv = provenance_csv(case)
    assert csv.splitlines()[0].startswith("figure,period,value") and len(provenance_rows(case)) > 50


def test_case_guards(facts):
    with pytest.raises(ValueError, match="after the analysis date"):
        build_sec_case(facts, IDENT, PriceQuote(30, date(2026, 11, 1), "x"), ValuationSettings(0.09), ANALYSIS)
    with pytest.raises(ValueError, match="source"):
        build_sec_case(facts, IDENT, PriceQuote(30, ANALYSIS, " "), ValuationSettings(0.09), ANALYSIS)
    bank = se.CompanyIdentity(0, "BNK", "Bank", sic="6022", sic_description="State commercial banks")
    with pytest.raises(se.UnsupportedFiler, match="financial institution"):
        build_sec_case(facts, bank, PRICE, ValuationSettings(0.09), ANALYSIS)
    with pytest.raises(InsufficientData):
        build_sec_case(facts, IDENT, PriceQuote(30, date(2022, 2, 28), "x"), ValuationSettings(0.09), date(2022, 3, 1))
    with pytest.raises(ValueError, match="unknown settings"):
        ValuationSettings.from_dict({"discount_rate": 0.09, "dicount": 1})
    ifrs = {"facts": {"ifrs-full": {"Revenue": {}}}}
    with pytest.raises(se.UnsupportedFiler, match="IFRS"):
        se.check_supported(ifrs)


def test_settings_overrides_are_used_and_labelled(facts):
    s = ValuationSettings(discount_rate=0.09, base_growth=0.05, base_margin=0.18, basis="annual",
                          rationales={"base_growth": "management guidance, 10-K p.30"})
    case = build_sec_case(facts, IDENT, PRICE, s, ANALYSIS, RETRIEVED)
    assert case.ttm is None and case.base_inputs.base_revenue == pytest.approx(1400)
    assert case.base_inputs.revenue_growth[0] == 0.05 and case.base_inputs.ebit_margin[0] == 0.18
    assert {a.name: a.rationale for a in case.assumptions}["base_growth"] == "management guidance, 10-K p.30"


def test_lookup(cache):
    client = se.SECClient(cache_dir=cache, offline=True)
    assert se.resolve_company("synq", client).cik == 0
    assert se.resolve_company("0000000000", client).ticker == "SYNQ"
    assert se.resolve_company("BRK.B", client).cik == 1          # dot/dash normalisation
    with pytest.raises(NotFound, match="did you mean"):
        se.resolve_company("SYNX", client)
    sub = client.submissions_result(0).json()
    ident = se.enrich_identity(se.resolve_company("SYNQ", client), sub)
    assert ident.sic == "3571" and ident.fiscal_year_end == "1231"
    filings = se.recent_filings(sub, as_of=date(2026, 3, 1))
    assert [f.form for f in filings] == ["10-K"]


def test_client_requires_contact_email(monkeypatch, tmp_path):
    monkeypatch.setenv("DEEPTERMINAL_SEC_USER_AGENT", "no-contact-here")
    with pytest.raises(RuntimeError, match="contact e-mail"):
        se.SECClient(cache_dir=tmp_path)
    monkeypatch.setenv("DEEPTERMINAL_SEC_USER_AGENT", "Jane Research jane@example.com")
    assert se.SECClient(cache_dir=tmp_path).user_agent.endswith("jane@example.com")


def test_cli_value_offline_end_to_end(cache, tmp_path, capsys):
    out = tmp_path / "out"
    rc = main(["value", "SYNQ", "--price", "30", "--price-as-of", "2026-10-27", "--price-source", "synthetic test",
               "--discount-rate", "0.09", "--as-of", "2026-10-28", "--offline", "--cache-dir", str(cache),
               "--out", str(out)])
    assert rc == 0
    files = {p.name for p in (out / "SYNQ").iterdir()}
    assert files == {"report.md", "dashboard.html", "result.json", "provenance.csv"}
    res = json.loads((out / "SYNQ" / "result.json").read_text())
    assert res["basis"] == "TTM to 2026-06-30" and res["price"]["as_of"] == "2026-10-27"
    assert {v["name"] for v in res["assumptions"]} >= {"discount_rate", "base_growth", "tax_rate"}


def test_cli_refuses_missing_price_or_discount_rate(cache, capsys):
    with pytest.raises(SystemExit, match="price-source"):
        main(["value", "SYNQ", "--price", "30", "--discount-rate", "0.09", "--offline", "--cache-dir", str(cache)])
    with pytest.raises(SystemExit, match="discount-rate"):
        main(["value", "SYNQ", "--price", "30", "--price-as-of", "2026-10-27", "--price-source", "x",
              "--offline", "--cache-dir", str(cache)])


def test_cli_verify_reports_missing_prices_and_errors(cache, tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"companies": [
        {"company": "SYNQ", "price": {"value": 30, "as_of": "2026-10-27", "source": "synthetic"},
         "settings": {"discount_rate": 0.09}, "analysis_date": "2026-10-28"},
        {"company": "SYNQ", "price": {"value": None, "as_of": None, "source": None}, "settings": {"discount_rate": 0.09}},
        {"company": "NOPE", "price": {"value": 1, "as_of": "2026-10-27", "source": "x"}, "settings": {"discount_rate": 0.09}},
    ]}))
    rc = main(["verify", str(manifest), "--offline", "--cache-dir", str(cache), "--out", str(tmp_path / "v")])
    summary = (tmp_path / "v" / "verification_summary.md").read_text()
    assert rc == 3
    assert "| SYNQ | OK |" in summary and "NO_PRICE" in summary and "| NOPE | NotFound |" in summary


def test_cli_reports_policy_block_cleanly(monkeypatch, tmp_path, capsys):
    import urllib.error
    import deepterminal.data.http as h

    def blocked(req, timeout):
        raise urllib.error.URLError(OSError("Tunnel connection failed: 403 Forbidden"))
    monkeypatch.setattr(h.urllib.request, "urlopen", blocked)
    monkeypatch.setenv("DEEPTERMINAL_SEC_USER_AGENT", "Jane Research jane@example.com")
    rc = main(["lookup", "AAPL", "--cache-dir", str(tmp_path)])
    err = capsys.readouterr().err
    assert rc == 2 and "NetworkPolicyBlocked" in err


def _usd(facts, concept):
    return facts["facts"]["us-gaap"][concept]["units"]["USD"]


def test_negative_effective_tax_uses_statutory_rate(facts):
    for row in _usd(facts, "IncomeTaxExpenseBenefit"):       # tax benefits every year (e.g. allowance releases)
        row["val"] = -abs(row["val"])
    case = build_sec_case(facts, IDENT, PRICE, ValuationSettings(discount_rate=0.09),
                          analysis_date=ANALYSIS, retrieved_at=RETRIEVED)
    assert case.base_inputs.tax_rate == pytest.approx(0.21)
    assert "negative" in {a.name: a.rationale for a in case.assumptions}["tax_rate"]


def test_balance_sheet_items_tagged_years_ago_are_not_used(facts):
    minority = next(c for c in facts["facts"]["us-gaap"] if c.startswith("MinorityInterest"))
    for row in _usd(facts, minority):                         # stopped tagging the item in 2021
        row["end"] = "2021-12-31"
    case = build_sec_case(facts, IDENT, PRICE, ValuationSettings(discount_rate=0.09),
                          analysis_date=ANALYSIS, retrieved_at=RETRIEVED)
    assert case.capital.minority_interest == 0
    assert any("2021-12-31" in n and "not used" in n for n in case.notes)
