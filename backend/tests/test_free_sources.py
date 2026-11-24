"""Free-source adapters: parsing, attribution and failure states.

These run offline with a stub opener and small payloads in each source's documented format
(test fixtures, not market data). Live verification is recorded in docs/STATUS.md.
"""

import json
from datetime import date

import pytest

from deepterminal.data import http as dh
from deepterminal_api.config import get_settings
from deepterminal_api.services.free_sources import FreeSources, normalise_name
from deepterminal_api.services.gateway import DataUnavailable


class Resp:
    def __init__(self, body: bytes, ctype: str):
        self._b, self.headers, self.status = body, {"Content-Type": ctype}, 200

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def sources(tmp_path, payloads: dict[str, tuple[bytes, str]], seen: list | None = None):
    def opener(req, timeout=None):
        url = req.full_url
        if seen is not None:
            seen.append(url)
        for frag, (body, ctype) in payloads.items():
            if frag in url:
                return Resp(body, ctype)
        raise dh.NetworkPolicyBlocked("blocked by proxy", url)
    f = dh.CachedFetcher(tmp_path, "test-agent", opener=opener, sleep=lambda s: None, min_interval=0)
    return FreeSources(get_settings(), fetcher=f)


def test_stooq_daily_closes_and_symbol(tmp_path):
    csv = b"Date,Open,High,Low,Close,Volume\n2026-10-26,10,11,9,10.5,100\n2026-10-27,10.5,12,10,11.25,120\n"
    seen = []
    fs = sources(tmp_path, {"stooq.com/q/d/l/": (csv, "text/csv")}, seen)
    rows, res = fs.stooq_daily("BRK.B")
    assert rows == [(date(2026, 10, 26), 10.5), (date(2026, 10, 27), 11.25)]
    assert "s=brk-b.us" in seen[0] and res.sha256
    fs.stooq_daily("BRK.B")
    assert len(seen) == 1                                    # cached: one request per symbol per 12 hours


def test_stooq_without_table_is_unavailable_not_invented(tmp_path):
    fs = sources(tmp_path, {"stooq.com": (b"Exceeded the daily hits limit", "text/plain")})
    with pytest.raises(DataUnavailable) as e:
        fs.stooq_daily("NVDA")
    assert e.value.status == "not_found" and "daily download limit" in e.value.hint


def test_fred_csv_handles_missing_observations(tmp_path):
    csv = b"observation_date,DGS10\n2026-10-23,4.10\n2026-10-26,.\n2026-10-27,4.05\n"
    fs = sources(tmp_path, {"fredgraph.csv?id=DGS10": (csv, "text/csv")})
    rows, _ = fs.fred_series("DGS10")
    assert rows == [(date(2026, 10, 23), 4.10), (date(2026, 10, 26), None), (date(2026, 10, 27), 4.05)]
    with pytest.raises(DataUnavailable):
        fs.fred_series("bad id; drop")


def test_blocked_host_reports_which_free_host_to_allow(tmp_path):
    fs = sources(tmp_path, {})
    with pytest.raises(DataUnavailable) as e:
        fs.fred_series("DGS10")
    assert e.value.status == "blocked" and "fred.stlouisfed.org" in e.value.hint and "free" in e.value.hint


def test_federal_register_ofac_wayback_and_edgar_fts_parsing(tmp_path):
    fr = {"results": [{"title": "Notice of determination", "type": "Notice", "publication_date": "2026-05-01",
                       "agencies": [{"name": "Commerce Department"}], "html_url": "https://www.federalregister.gov/d/x",
                       "abstract": "Example."}]}
    sdn = b'36,"AEROCARIBBEAN AIRLINES","-0-","CUBA"\n173,"ANGLO-CARIBBEAN CO., LTD.","-0-","CUBA"\n'
    wb = {"archived_snapshots": {"closest": {"available": True, "url": "http://web.archive.org/web/1998/example.com",
                                             "timestamp": "19981201000000", "status": "200"}}}
    efts = {"hits": {"hits": [{"_id": "0000000001-26-000001:doc.htm", "_source": {
        "ciks": ["0000000001"], "display_names": ["EXAMPLE CO  (EX)  (CIK 0000000001)"], "form": "10-K",
        "file_type": "10-K", "file_date": "2026-02-01", "period_ending": "2025-12-31", "sics": ["3674"]}}]}}
    fs = sources(tmp_path, {
        "federalregister.gov": (json.dumps(fr).encode(), "application/json"),
        "sdn.csv": (sdn, "text/csv"),
        "archive.org/wayback": (json.dumps(wb).encode(), "application/json"),
        "efts.sec.gov": (json.dumps(efts).encode(), "application/json"),
    })
    docs, _ = fs.federal_register("Example Co")
    assert docs[0]["agencies"] == ["Commerce Department"] and docs[0]["date"] == "2026-05-01"
    rows, _ = fs.ofac_sdn()
    assert [r["name"] for r in rows] == ["AEROCARIBBEAN AIRLINES", "ANGLO-CARIBBEAN CO., LTD."]
    snap, _ = fs.wayback_snapshot("example.com", 1996)
    assert snap["timestamp"].startswith("1998")
    hits, _ = fs.edgar_mentions("Example")
    assert hits[0]["ciks"] == [1] and hits[0]["accession"] == "0000000001-26-000001" and hits[0]["document"] == "doc.htm"


def test_name_normalisation_for_screening():
    assert normalise_name("Anglo-Caribbean Co., Ltd.") == normalise_name("ANGLO CARIBBEAN CO LTD") == "ANGLO CARIBBEAN"
    assert normalise_name("NVIDIA Corporation") == "NVIDIA"


def test_price_fetch_refuses_fictional_companies(client, dqd):
    r = client.post(f"/api/companies/{dqd['id']}/prices/fetch")
    assert r.status_code == 422 and "fictional" in r.json()["message"]


def test_sources_listing_shows_costs(client):
    s = client.get("/api/sources").json()
    assert s["cost_policy"]["paid_apis_enabled"] is False and "Zero-cost" in s["cost_policy"]["summary"]
    costs = {x["id"]: x["cost"] for x in s["sources"]}
    assert costs["stooq"].startswith("free") and costs["fred"].startswith("free") and costs["ollama"].startswith("free")
    assert costs["anthropic"].startswith("PAID") and costs["openai"].startswith("PAID")


def test_alphavantage_free_tier_parsing_and_key_redaction(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPTERMINAL_ALPHAVANTAGE_API_KEY", "SECRETKEY123")
    get_settings.cache_clear()
    try:
        body = {"Meta Data": {}, "Time Series (Daily)": {"2026-10-28": {"4. close": "101.5"}, "2026-10-27": {"4. close": "99.0"}}}
        seen = []
        fs = sources(tmp_path, {"alphavantage.co": (json.dumps(body).encode(), "application/json")}, seen)
        rows, res = fs.alphavantage_daily("ibm")
        assert rows == [(date(2026, 10, 27), 99.0), (date(2026, 10, 28), 101.5)]
        assert "outputsize=compact" in seen[0] and "function=TIME_SERIES_DAILY" in seen[0]     # free endpoint only
        meta = next(tmp_path.rglob("*.meta.json")).read_text()
        assert "SECRETKEY123" not in meta and "REDACTED" in meta
        limited = sources(tmp_path / "b", {"alphavantage.co": (json.dumps({"Note": "rate limit"}).encode(), "application/json")})
        with pytest.raises(DataUnavailable) as e:
            limited.alphavantage_daily("ibm")
        assert e.value.status == "rate_limited" and "SECRETKEY123" not in e.value.url
    finally:
        get_settings.cache_clear()


def test_stooq_connection_reset_is_explained(tmp_path):
    def opener(req, timeout=None):
        raise ConnectionResetError(104, "Connection reset by peer")
    f = dh.CachedFetcher(tmp_path, "t", opener=opener, sleep=lambda s: None, min_interval=0, max_retries=0)
    with pytest.raises(DataUnavailable) as e:
        FreeSources(get_settings(), fetcher=f).stooq_daily("NVDA")
    assert e.value.status == "denied" and "does not try to get around it" in e.value.hint


def test_stooq_bot_check_page_is_refused_and_not_cached(tmp_path):
    page = b'<!DOCTYPE html><html><body><noscript>This site requires JavaScript to verify your browser.</noscript></body></html>'
    fs = sources(tmp_path, {"stooq.com": (page, "text/html")})
    with pytest.raises(DataUnavailable) as e:
        fs.stooq_daily("NVDA")
    assert e.value.status == "denied" and "does not try to pass the check" in e.value.hint
    assert not list(tmp_path.rglob("nvda.us.csv*"))


def test_price_chain_falls_back_to_free_key_provider_and_reports_failures(monkeypatch):
    from types import SimpleNamespace
    from deepterminal_api.services import prices as ps

    class Sources:
        def stooq_symbol(self, t):
            return t.lower() + ".us"

        def stooq_daily(self, t):
            raise DataUnavailable("denied", "Stooq answered with a browser bot check instead of data.")

        def alphavantage_daily(self, t):
            return [(date(2026, 10, 28), 186.5)], SimpleNamespace(retrieved_at=date(2026, 10, 29), from_cache=False)

    stored = []

    class DB:
        def scalar(self, q):
            return None

        def add(self, p):
            stored.append(p)

        def commit(self):
            pass

    company = SimpleNamespace(id=1, synthetic=False, ticker="NVDA")
    monkeypatch.setattr(ps, "free_sources", lambda: Sources())
    monkeypatch.setattr(ps.cs, "companyfacts", lambda c: ({}, None))
    monkeypatch.setattr(ps.se, "annual_series", lambda *a, **k: {})
    monkeypatch.setenv("DEEPTERMINAL_ALPHAVANTAGE_API_KEY", "free-key")
    get_settings.cache_clear()
    try:
        out = ps.fetch_prices(DB(), company)
        assert out["provider"] == "alphavantage" and out["latest"] == {"as_of": "2026-10-28", "close": 186.5}
        assert stored[0].provider == "alphavantage" and stored[0].source.startswith("Alpha Vantage end-of-day close")
        monkeypatch.delenv("DEEPTERMINAL_ALPHAVANTAGE_API_KEY")
        get_settings.cache_clear()
        monkeypatch.setattr(ps, "form4_price", lambda db, c: None)   # no recent insider trades either
        with pytest.raises(DataUnavailable) as e:            # no key: Stooq's refusal is reported, nothing invented
            ps.fetch_prices(DB(), company)
        assert "bot check" in e.value.message and "Alpha Vantage" in e.value.hint
    finally:
        get_settings.cache_clear()



def test_form4_price_is_volume_weighted_latest_open_market_trades(monkeypatch):
    from types import SimpleNamespace
    from deepterminal_api.services import filings as fsvc
    from deepterminal_api.services import prices as ps
    trades = [  # transaction values in Form 4's own fields; grants (A) and exercises (M) must be ignored
        {"code": "S", "date": "2026-09-21", "shares": 12483.0, "price": 222.1932, "owner": "TETER TIMOTHY S.", "url": "u1"},
        {"code": "S", "date": "2026-09-21", "shares": 4499.0, "price": 223.7479, "owner": "TETER TIMOTHY S.", "url": "u1"},
        {"code": "S", "date": "2026-09-18", "shares": 10000.0, "price": 220.4199, "owner": "STEVENS MARK A", "url": "u2"},
        {"code": "M", "date": "2026-09-25", "shares": 5000.0, "price": 10.0, "owner": "X", "url": "u3"},
    ]
    monkeypatch.setattr(fsvc, "insider_transactions", lambda db, c, limit=25: {"transactions": trades})
    d, px, url, label = ps.form4_price(None, SimpleNamespace(id=1))
    assert d == date(2026, 9, 21) and url == "u1"
    assert abs(px - (12483 * 222.1932 + 4499 * 223.7479) / (12483 + 4499)) < 1e-9
    assert "not an official close" in label


def test_refusing_source_is_not_contacted_again_within_backoff(tmp_path):
    seen = []
    page = b"<!DOCTYPE html><html>bot check</html>"
    fs = sources(tmp_path, {"stooq.com": (page, "text/html")}, seen)
    for _ in range(3):
        with pytest.raises(DataUnavailable) as e:
            fs.stooq_daily("NVDA")
        assert e.value.status == "denied"
    assert len(seen) == 1                      # one request; the refusal is remembered for 30 minutes
