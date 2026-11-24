"""Free public data sources (no payment, no account unless noted).

Every request goes through deepterminal's CachedFetcher, so it is cached with its
retrieval time and SHA-256, logged to ``data_fetches``, and checked against the
zero-cost policy (deepterminal/costpolicy.py) before any network traffic.

=====================  ======================================  ==============================
Source                 What it gives                           Free-tier limitation
=====================  ======================================  ==============================
Stooq                  end-of-day prices (CSV, no key)         EOD only; informal daily limit;
                                                               non-commercial use; attribute
FRED (keyless CSV)     macro series (rates, CPI, spreads)      daily/monthly; revisions
EDGAR full-text search other filers that name a company        2001+; no snippets (we fetch
                                                               the document to quote it)
Federal Register API   rules/notices naming a company          federal only; not court cases
OFAC SDN list          sanctions name screening                name match only (false
                                                               positives/negatives possible)
Wayback availability   archived snapshots of a website         existence, not content analysis
=====================  ======================================  ==============================
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode

from deepterminal.data import http as dh

from ..config import Settings, get_settings
from .gateway import DEMO_FULL_BACKEND, DEMO_SNAPSHOT_ONLY, DataUnavailable, _record

DOWN_SECONDS = 1800        # after a refusal, skip that source for 30 minutes

HOST_HINT = {
    "stooq.com": "stooq.com",
    "fred.stlouisfed.org": "fred.stlouisfed.org",
    "www.federalregister.gov": "www.federalregister.gov",
    "sanctionslistservice.ofac.treas.gov": "www.treasury.gov and sanctionslistservice.ofac.treas.gov",
    "archive.org": "archive.org",
    "efts.sec.gov": "efts.sec.gov",
}


def _translate(e: Exception, url: str, label: str) -> DataUnavailable:
    e = type(e)(dh.redact(str(e))) if not isinstance(e, dh.FetchError) else e
    detail = dh.redact(str(e))
    host = re.sub(r"^https?://([^/]+).*$", r"\1", url)
    if isinstance(e, dh.CostPolicyBlocked):
        return DataUnavailable("not_configured", f"{label}: blocked by the zero-cost policy.", detail, url)
    if isinstance(e, dh.NetworkPolicyBlocked):
        return DataUnavailable("blocked", f"{label}: this environment's network policy blocks {host}.",
                               f"Allow {HOST_HINT.get(host, host)} in the environment's network settings "
                               "(the source itself is free).", url)
    if isinstance(e, dh.RateLimited):
        return DataUnavailable("rate_limited", f"{label}: the free tier's rate limit was reached.",
                               "Results are cached; try again later.", url)
    if isinstance(e, dh.NotFound):
        return DataUnavailable("not_found", f"{label}: not found.", "", url)
    if isinstance(e, dh.OfflineCacheMiss):
        if get_settings().public_demo:
            return DataUnavailable("offline", f"{label}: {DEMO_SNAPSHOT_ONLY}", DEMO_FULL_BACKEND, url)
        return DataUnavailable("offline", f"{label}: offline mode and nothing cached.", "", url)
    if "Connection reset" in detail or "Errno 104" in detail:
        return DataUnavailable("denied", f"{label}: {host} closed the connection from this network.",
                               "The source refuses requests from some cloud or datacenter addresses. It usually works "
                               "from a home or office connection; DEEPTERMINAL does not try to get around it.", url)
    if isinstance(e, dh.AccessDenied):
        return DataUnavailable("denied", f"{label}: the server refused the request (HTTP 403).", "", url)
    return DataUnavailable("error", f"{label}: retrieval failed ({detail}).", "", url)


class FreeSources:
    def __init__(self, settings: Settings | None = None, fetcher: dh.CachedFetcher | None = None):
        s = settings or get_settings()
        self.settings = s
        self._down: dict[str, tuple[float, DataUnavailable]] = {}
        self.fetcher = fetcher or dh.CachedFetcher(
            Path(s.cache_dir).parent / "free", s.sec_user_agent or "DEEPTERMINAL research tool (open source)",
            min_interval=0.5, max_retries=1, timeout=10.0, offline=s.offline)   # free sources must not stall a page

    def _get(self, adapter: str, label: str, url: str, key: str, max_age: timedelta, accept: str) -> dh.FetchResult:
        down = self._down.get(adapter)
        if down and time.monotonic() < down[0]:
            cached = self.fetcher.read_cache(key, max_age)
            if cached:
                return cached
            raise down[1]                     # remembered refusal: do not hammer a source that said no
        try:
            res = self.fetcher.get(url, key, max_age=max_age, accept=accept)
        except dh.FetchError as e:
            err = _translate(e, dh.redact(url), label)
            _record(adapter, dh.redact(url), err.status, detail=dh.redact(err.message))
            if err.status in ("blocked", "denied", "rate_limited"):
                self._down[adapter] = (time.monotonic() + DOWN_SECONDS, err)
            raise err from e
        _record(adapter, dh.redact(url), "cache" if res.from_cache else "ok", res.sha256)
        return res

    # ── prices: Stooq ──────────────────────────────────────────────────
    @staticmethod
    def stooq_symbol(ticker: str) -> str:
        return ticker.lower().replace(".", "-") + ".us"

    def stooq_daily(self, ticker: str) -> tuple[list[tuple[date, float]], dh.FetchResult]:
        """Daily closes, oldest first. Stooq's CSV needs no key; a free key can be set if Stooq asks for one."""
        sym = self.stooq_symbol(ticker)
        params = {"s": sym, "i": "d"}
        if self.settings.stooq_apikey:
            params["apikey"] = self.settings.stooq_apikey
        url = "https://stooq.com/q/d/l/?" + urlencode(params)
        res = self._get("stooq", "Stooq prices", url, f"stooq/{sym}.csv", timedelta(hours=12), "text/csv")
        text = res.body.decode("utf-8", "replace")
        if text.lstrip().lower().startswith(("<!doctype html", "<html")):
            for p in self.fetcher._paths(f"stooq/{sym}.csv"):      # never keep a challenge page as "data"
                p.unlink(missing_ok=True)
            err = DataUnavailable("denied", "Stooq answered with a browser bot check instead of data.",
                                  "Stooq does not allow automated downloads from this network. DEEPTERMINAL respects "
                                  "that and does not try to pass the check. Use the free Alpha Vantage key or enter "
                                  "a price you observed.", url)
            self._down["stooq"] = (time.monotonic() + DOWN_SECONDS, err)
            raise err
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows or "Close" not in rows[0]:
            raise DataUnavailable("not_found", f"Stooq returned no price table for {sym}.",
                                  "Unknown symbol, the daily download limit was reached, or Stooq now asks for "
                                  "a free key (set DEEPTERMINAL_STOOQ_APIKEY). Response: " + text[:120].strip(), url)
        out = []
        for r in rows:
            try:
                out.append((date.fromisoformat(r["Date"]), float(r["Close"])))
            except (KeyError, ValueError):
                continue
        return out, res

    # ── prices: Alpha Vantage free tier (optional free key) ────────────
    def alphavantage_daily(self, ticker: str) -> tuple[list[tuple[date, float]], dh.FetchResult]:
        """Last ~100 daily closes from the free TIME_SERIES_DAILY endpoint (compact output only)."""
        key = self.settings.alphavantage_api_key
        if not key:
            raise DataUnavailable("not_configured", "Alpha Vantage is not configured.",
                                  "Optional: set DEEPTERMINAL_ALPHAVANTAGE_API_KEY to a free key (no payment).")
        url = "https://www.alphavantage.co/query?" + urlencode(
            {"function": "TIME_SERIES_DAILY", "symbol": ticker.upper(), "outputsize": "compact", "apikey": key})
        res = self._get("alphavantage", "Alpha Vantage prices", url, f"alphavantage/{ticker.upper()}.json",
                        timedelta(hours=12), "application/json")
        data = json.loads(res.body)
        series = data.get("Time Series (Daily)")
        if not series:
            msg = data.get("Note") or data.get("Information") or data.get("Error Message") or "no price series"
            raise DataUnavailable("rate_limited" if ("Note" in data or "Information" in data) else "not_found",
                                  f"Alpha Vantage returned no prices for {ticker}: {str(msg)[:160]}", "", url.split("apikey=")[0])
        rows = sorted((date.fromisoformat(d), float(v["4. close"])) for d, v in series.items())
        return rows, res

    # ── macro: FRED keyless CSV ────────────────────────────────────────
    def fred_series(self, series_id: str) -> tuple[list[tuple[date, float | None]], dh.FetchResult]:
        if not re.fullmatch(r"[A-Z0-9_]{1,30}", series_id):
            raise DataUnavailable("not_found", f"invalid FRED series id {series_id!r}")
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        res = self._get("fred", "FRED", url, f"fred/{series_id}.csv", timedelta(hours=12), "text/csv")
        rows = list(csv.reader(io.StringIO(res.body.decode("utf-8", "replace"))))
        if len(rows) < 2:
            raise DataUnavailable("not_found", f"FRED returned no data for {series_id}.", "", url)
        out = []
        for r in rows[1:]:
            if len(r) < 2:
                continue
            try:
                d = date.fromisoformat(r[0])
            except ValueError:
                continue
            out.append((d, None if r[1] in (".", "") else float(r[1])))   # "." marks a missing observation
        return out, res

    # ── EDGAR full-text search: who names this company ──────────────────
    def edgar_mentions(self, phrase: str, forms: str = "10-K", since: date | None = None) -> tuple[list[dict], dh.FetchResult]:
        since = since or date.today() - timedelta(days=550)
        q = {"q": f'"{phrase}"', "forms": forms, "dateRange": "custom", "startdt": since.isoformat(),
             "enddt": date.today().isoformat()}
        url = "https://efts.sec.gov/LATEST/search-index?" + urlencode(q)
        key = "efts/" + re.sub(r"[^a-z0-9]+", "_", f"{phrase}_{forms}_{since}".lower()) + ".json"
        res = self._get("edgar_fts", "EDGAR full-text search", url, key, timedelta(days=3), "application/json")
        hits = json.loads(res.body).get("hits", {}).get("hits", [])
        out = []
        for h in hits:
            src = h.get("_source", {})
            adsh, _, doc = h.get("_id", "").partition(":")
            out.append({"accession": adsh, "document": doc, "ciks": [int(c) for c in src.get("ciks", [])],
                        "names": src.get("display_names", []), "form": src.get("form"),
                        "file_type": src.get("file_type"), "filed": src.get("file_date"),
                        "period": src.get("period_ending"), "sics": src.get("sics", [])})
        return out, res

    # ── Federal Register ───────────────────────────────────────────────
    def federal_register(self, term: str, per_page: int = 20) -> tuple[list[dict], dh.FetchResult]:
        q = {"conditions[term]": f'"{term}"', "per_page": per_page, "order": "newest"}
        url = "https://www.federalregister.gov/api/v1/documents.json?" + urlencode(q)
        key = "fedreg/" + re.sub(r"[^a-z0-9]+", "_", term.lower()) + ".json"
        res = self._get("federal_register", "Federal Register", url, key, timedelta(days=1), "application/json")
        docs = json.loads(res.body).get("results", [])
        return [{"title": d.get("title"), "type": d.get("type"), "date": d.get("publication_date"),
                 "agencies": [a.get("name") for a in d.get("agencies", []) if a.get("name")],
                 "url": d.get("html_url"), "abstract": d.get("abstract")} for d in docs], res

    # ── OFAC SDN ────────────────────────────────────────────────────────
    def ofac_sdn(self) -> tuple[list[dict], dh.FetchResult]:
        url = "https://sanctionslistservice.ofac.treas.gov/api/publicationpreview/exports/sdn.csv"
        res = self._get("ofac", "OFAC SDN list", url, "ofac/sdn.csv", timedelta(days=1), "text/csv")
        out = []
        for r in csv.reader(io.StringIO(res.body.decode("latin-1"))):
            if len(r) >= 4 and r[0].strip().isdigit():
                out.append({"id": r[0].strip(), "name": r[1].strip(), "type": r[2].strip(), "program": r[3].strip()})
        return out, res

    # ── Wayback availability ───────────────────────────────────────────
    def wayback_snapshot(self, site: str, year: int) -> tuple[dict | None, dh.FetchResult]:
        url = f"https://archive.org/wayback/available?url={quote(site)}&timestamp={year}0101"
        key = "wayback/" + re.sub(r"[^a-z0-9]+", "_", f"{site}_{year}".lower()) + ".json"
        res = self._get("wayback", "Internet Archive", url, key, timedelta(days=30), "application/json")
        snap = json.loads(res.body).get("archived_snapshots", {}).get("closest")
        return (snap if snap and snap.get("available") else None), res


@lru_cache
def free_sources() -> FreeSources:
    return FreeSources()


def normalise_name(name: str) -> str:
    """Company name for matching: upper case, punctuation and legal suffixes removed."""
    n = re.sub(r"[^A-Z0-9 ]+", " ", name.upper())
    n = re.sub(r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|LLC|PLC|SA|AG|NV|HOLDINGS?|GROUP|THE)\b", " ", n)
    return " ".join(n.split())
