"""Integration tests on GENUINE recorded SEC EDGAR responses (offline replay).

Skipped, with the reason shown, until recordings exist in tests/recorded/sec
(see tests/recorded/README.md). No synthetic data is ever used here.
"""

import gzip
import json
import re
from datetime import date
from pathlib import Path

import pytest

from deepterminal.data import sec_edgar as se
from deepterminal.data.sec_case import PriceQuote, ValuationSettings, build_sec_case
from deepterminal.pipeline import run_case
from deepterminal.reporting.report import render_report
from deepterminal.validation import validate_companyfacts

REC = Path(__file__).resolve().parents[1] / "recorded" / "sec"
FACTS = sorted(REC.glob("companyfacts_*.json.gz"))
PRICES_FILE = REC.parent / "prices.json"
PRICES = json.loads(PRICES_FILE.read_text()) if PRICES_FILE.exists() else {}

pytestmark = pytest.mark.skipif(
    not FACTS, reason="no genuine SEC recordings in tests/recorded/sec — run "
                      "`deepterminal record AAPL KO CAT` with network access (see tests/recorded/README.md)")


def _cik(p: Path) -> int:
    return int(re.search(r"(\d{10})", p.name).group(1))


@pytest.fixture(scope="module")
def client():
    return se.SECClient(cache_dir=REC, offline=True)


@pytest.mark.parametrize("path", FACTS, ids=lambda p: p.name)
def test_recording_is_genuine_and_intact(path, client):
    meta = json.loads(Path(str(path) + ".meta.json").read_text())
    assert meta["url"] == se.COMPANYFACTS_URL.format(cik=_cik(path))
    assert meta["retrieved_at"] and meta["status"] == 200
    res = client.companyfacts_result(_cik(path))          # verifies SHA-256 on read
    data = res.json()
    assert int(data["cik"]) == _cik(path) and "_comment" not in data   # synthetic fixtures carry _comment


@pytest.mark.parametrize("path", FACTS, ids=lambda p: p.name)
def test_real_financials_parse_validate_and_carry_provenance(path, client):
    res = client.companyfacts_result(_cik(path))
    facts = res.json()
    se.check_supported(facts)
    periods = se.build_periods(facts, retrieved_at=res.retrieved_at)
    assert len(periods) >= 3
    for p in periods:
        assert p.revenue > 0 and abs(p.operating_income) < p.revenue
        prov = p.provenance["revenue"]
        assert re.fullmatch(r"\d{10}-\d{2}-\d{6}", prov.accession)
        assert prov.filed > p.period_end and prov.retrieved_at == res.retrieved_at
    rep = validate_companyfacts(facts, None, res.retrieved_at.date())
    assert rep.passed, rep.summary() + " " + "; ".join(c.detail for c in rep.failures)
    quarters = se.build_quarterly_periods(facts, retrieved_at=res.retrieved_at)
    assert quarters, "no 10-Q quarters parsed"
    # point-in-time: nothing filed after the cut-off is visible
    cut = periods[-1].filed
    assert all(p.filed <= cut for p in se.build_periods(facts, as_of=cut))


@pytest.mark.skipif(not PRICES, reason="no genuine observed prices in tests/recorded/prices.json")
@pytest.mark.parametrize("ticker", sorted(PRICES))
def test_full_pipeline_on_real_company(ticker, client):
    spec = PRICES[ticker]
    ident = se.resolve_company(ticker, client)
    ident = se.enrich_identity(ident, client.submissions_result(ident.cik).json())
    res = client.companyfacts_result(ident.cik)
    case = build_sec_case(res.json(), ident, PriceQuote(spec["value"], date.fromisoformat(spec["as_of"]),
                                                        spec["source"], spec.get("url")),
                          ValuationSettings.from_dict(spec["settings"]),
                          date.fromisoformat(spec["analysis_date"]), res.retrieved_at)
    a = run_case(case)
    if a.reverse[0].solutions:
        assert a.reverse[0].solutions[0].model.enterprise_value == pytest.approx(a.market.enterprise_value, rel=1e-6)
    bear, base, bull = (a.scenarios.by_name(n).per_share for n in ("bear", "base", "bull"))
    assert bear <= base <= bull
    md = render_report(a)
    assert "Figure provenance" in md and ident.name in md


def _facts(cik: int, client):
    p = REC / f"companyfacts_{cik:010d}.json.gz"
    if not p.exists():
        pytest.skip(f"no recording for CIK {cik}")
    return client.companyfacts_result(cik).json()


def test_stock_splits_are_not_reported_as_restatements(client):
    # NVIDIA: 4-for-1 (2021) and 10-for-1 (2024) splits rescale historical share counts.
    revs = se.detect_revisions(_facts(1045810, client))
    splits = {r.split_ratio for r in revs if r.kind == "stock_split"}
    assert {4, 10} <= splits
    assert not any(r.field == "diluted_shares" and r.kind == "revision" for r in revs)


def test_tie_out_explains_restated_quarter(client):
    # Coca-Cola: Q1 2019 revenue first filed as 8,020m and later restated to 8,694m; the nine-month
    # figure ties only with the restated quarter, which is a documented revision, not a parsing error.
    rep = validate_companyfacts(_facts(21344, client), None, date(2026, 10, 29))
    tie = next(c for c in rep.checks if c.name == "quarterly tie-out")
    assert tie.status == "WARN" and "explained by restatement" in tie.detail and "8,020,000,000→8,694,000,000" in tie.detail


def test_share_counts_put_on_one_basis_across_splits(client):
    # NVIDIA split 4:1 (2021) and 10:1 (2024); FY2017 was only ever reported pre-split (649m diluted shares).
    facts = _facts(1045810, client)
    assert se.split_events(facts) == [(date(2021, 8, 20), 4), (date(2024, 8, 28), 10)]
    s = se.annual_series(facts, "diluted_shares", None, "latest")
    fy17 = s[date(2017, 1, 29)]
    assert fy17.split_factor == 40 and 25e9 < fy17.value < 27e9
    assert max(f.value for f in s.values() if f.end.year >= 2017) / min(f.value for f in s.values() if f.end.year >= 2017) < 1.1
    # Point in time (before the 2024 split): only the 2021 split applies.
    then = se.annual_series(facts, "diluted_shares", date(2022, 3, 1), "latest")
    assert then[date(2021, 1, 31)].split_factor == 4 and 2.4e9 < then[date(2021, 1, 31)].value < 2.6e9


@pytest.mark.parametrize("ticker", sorted(PRICES))
def test_observed_prices_match_archived_source(ticker):
    spec = PRICES[ticker]
    recording = spec["recording"]
    snapshot = json.loads(gzip.decompress((REC.parents[2] / recording["path"]).read_bytes()))
    original = json.loads(snapshot[recording["endpoint"]][1])[0]
    assert {k: spec[k] for k in ("value", "as_of", "source", "url")} == {
        k: original[k] for k in ("value", "as_of", "source", "url")}
    assert "not an official close" in spec["source"]
