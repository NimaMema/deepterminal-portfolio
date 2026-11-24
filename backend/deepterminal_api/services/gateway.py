"""Data gateway: one interface over live SEC EDGAR and the labelled synthetic demo set.

Every retrieval is recorded in ``data_fetches`` (adapter, URL, status, hash),
and every failure is converted to :class:`DataUnavailable` with a status the UI
can explain (``blocked`` by network policy, ``denied`` by the server,
``not_found``, ``rate_limited``, ``not_configured``, ``error``).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from deepterminal.data import http as dh
from deepterminal.data import sec_edgar as se

from ..config import Settings, get_settings
from ..db import session_scope
from ..models import DataFetch

log = logging.getLogger("deepterminal.gateway")

ARCHIVES = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{name}"


class DataUnavailable(Exception):
    def __init__(self, status: str, message: str, hint: str = "", url: str = ""):
        super().__init__(message)
        self.status, self.message, self.hint, self.url = status, message, hint, url

    def to_dict(self) -> dict[str, str]:
        return {"status": self.status, "message": self.message, "hint": self.hint, "url": self.url}


@dataclass(frozen=True)
class Meta:
    url: str
    retrieved_at: datetime
    sha256: str
    from_cache: bool
    synthetic: bool


def _record(adapter: str, url: str, status: str, sha: str | None = None, detail: str | None = None) -> None:
    try:
        with session_scope() as db:
            db.add(DataFetch(adapter=adapter, url=url, status=status, sha256=sha, detail=(detail or "")[:2000]))
    except Exception:  # logging must never break a request
        log.exception("could not record data fetch")


DEMO_SNAPSHOT_ONLY = "Not in this public demo's snapshot: the demo serves a fixed set of recorded SEC data."
DEMO_FULL_BACKEND = "Run DEEPTERMINAL locally (free) to research any SEC registrant with live data."


def _translate(e: Exception, url: str) -> DataUnavailable:
    if isinstance(e, dh.NetworkPolicyBlocked):
        return DataUnavailable("blocked", "The network policy of this environment blocks this host.",
                               "Allow www.sec.gov and data.sec.gov in the environment's network settings.", url)
    if isinstance(e, dh.AccessDenied):
        return DataUnavailable("denied", "SEC refused the request (HTTP 403).",
                               "Check DEEPTERMINAL_SEC_USER_AGENT includes a contact e-mail.", url)
    if isinstance(e, dh.RateLimited):
        return DataUnavailable("rate_limited", "SEC rate limit reached; retried with backoff.", "Try again shortly.", url)
    if isinstance(e, dh.NotFound):
        return DataUnavailable("not_found", "Not found at SEC EDGAR.", "", url)
    if isinstance(e, dh.OfflineCacheMiss):
        if get_settings().public_demo:
            return DataUnavailable("offline", DEMO_SNAPSHOT_ONLY, DEMO_FULL_BACKEND, url)
        return DataUnavailable("offline", "Offline mode: response not in cache.", "Disable offline mode or record data.", url)
    if isinstance(e, RuntimeError):
        return DataUnavailable("not_configured", str(e), "Set DEEPTERMINAL_SEC_USER_AGENT.", url)
    return DataUnavailable("error", f"Retrieval failed: {e}", "", url)


class LiveGateway:
    mode = "live"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: se.SECClient | None = None

    @property
    def client(self) -> se.SECClient:
        if self._client is None:
            try:
                self._client = se.SECClient(user_agent=self.settings.sec_user_agent, cache_dir=self.settings.cache_dir,
                                            offline=self.settings.offline)
            except RuntimeError as e:
                raise _translate(e, se.TICKERS_URL) from e
        return self._client

    def _wrap(self, url: str, fn) -> tuple[Any, Meta]:
        try:
            r: dh.FetchResult = fn()
        except Exception as e:  # noqa: BLE001 - translated
            err = _translate(e, url)
            _record("sec", url, err.status, detail=err.message)
            raise err from e
        _record("sec", url, "cache" if r.from_cache else "ok", r.sha256)
        return r, Meta(r.url, r.retrieved_at, r.sha256, r.from_cache, False)

    def tickers(self) -> tuple[dict, Meta]:
        r, m = self._wrap(se.TICKERS_URL, lambda: self.client.company_tickers_result())
        return r.json(), m

    def submissions(self, cik: int) -> tuple[dict, Meta]:
        r, m = self._wrap(se.SUBMISSIONS_URL.format(cik=cik), lambda: self.client.submissions_result(cik))
        return r.json(), m

    def companyfacts(self, cik: int) -> tuple[dict, Meta]:
        r, m = self._wrap(se.COMPANYFACTS_URL.format(cik=cik), lambda: self.client.companyfacts_result(cik))
        return r.json(), m

    def filing_index(self, cik: int, accession: str) -> list[dict]:
        url = ARCHIVES.format(cik=cik, accn=accession.replace("-", ""), name="index.json")
        key = f"docs/{cik}/{accession}/index.json"
        r, _ = self._wrap(url, lambda: self.client.fetcher.get(url, key, max_age=timedelta(days=365)))
        return r.json().get("directory", {}).get("item", [])

    def document(self, cik: int, accession: str, name: str) -> tuple[str, Meta]:
        url = ARCHIVES.format(cik=cik, accn=accession.replace("-", ""), name=name)
        key = f"docs/{cik}/{accession}/{name}.gz"
        r, m = self._wrap(url, lambda: self.client.fetcher.get(url, key, max_age=timedelta(days=3650)))
        return r.body.decode("utf-8", errors="replace"), m


class DemoGateway:
    """Serves the synthetic demo set through the same interface (no network)."""

    mode = "demo"

    def __init__(self):
        from ..demo.generator import dataset, tickers_json
        self._data = dataset()
        self._tickers = tickers_json()
        self._t = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)

    def _meta(self, url: str, payload: str) -> Meta:
        return Meta(url, self._t, hashlib.sha256(payload.encode()).hexdigest(), True, True)

    def _get(self, cik: int):
        if cik not in self._data:
            raise DataUnavailable("not_found", f"CIK {cik} is not in the demo dataset.", "Demo mode serves only the "
                                  "five synthetic demo companies.")
        return self._data[cik]

    def tickers(self):
        return self._tickers, self._meta(se.TICKERS_URL, "demo")

    def submissions(self, cik: int):
        return self._get(cik)[2], self._meta(se.SUBMISSIONS_URL.format(cik=cik), str(cik))

    def companyfacts(self, cik: int):
        return self._get(cik)[1], self._meta(se.COMPANYFACTS_URL.format(cik=cik), str(cik))

    def _filing(self, cik: int, accession: str):
        for f in self._get(cik)[3]:
            if f.accession == accession:
                return f
        raise DataUnavailable("not_found", f"Filing {accession} not in demo dataset.")

    def filing_index(self, cik: int, accession: str) -> list[dict]:
        return [{"name": n, "type": "text/html"} for n in self._filing(cik, accession).documents]

    def document(self, cik: int, accession: str, name: str):
        f = self._filing(cik, accession)
        if name not in f.documents:
            raise DataUnavailable("not_found", f"{name} not in filing {accession}.")
        text = f.documents[name]
        return text, self._meta(ARCHIVES.format(cik=cik, accn=accession.replace("-", ""), name=name), text)


_gateway = None


def get_gateway(settings: Settings | None = None):
    global _gateway
    s = settings or get_settings()
    if _gateway is None or _gateway.mode != s.data_mode:
        _gateway = DemoGateway() if s.data_mode == "demo" else LiveGateway(s)
    return _gateway


def reset_gateway() -> None:
    global _gateway
    _gateway = None
