"""Zero-cost policy: which hosts DEEPTERMINAL may contact.

DEEPTERMINAL must run with no operating costs. Every outbound request made by the
application goes through :func:`check_url`, which allows:

* free public sources listed in :data:`FREE_SOURCES` (no account or payment needed);
* the local machine (Ollama, the API itself);

and refuses everything else. Hosts that can incur charges (:data:`PAID_HOSTS`, e.g.
commercial LLM APIs) are reachable only when the user sets
``DEEPTERMINAL_ALLOW_PAID_APIS=true`` *and* explicitly selects that provider; there is
no automatic fallback to them. Unknown hosts are refused too, so a new integration
cannot start sending requests without being classified here first.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Source:
    name: str
    hosts: tuple[str, ...]
    licence: str
    limits: str
    key: str = "none"              # "none" | "free key (no payment)"


FREE_SOURCES: tuple[Source, ...] = (
    Source("SEC EDGAR", ("www.sec.gov", "data.sec.gov", "efts.sec.gov"),
           "US government public data", "fair access: ≤10 requests/second with a User-Agent naming a contact e-mail"),
    Source("Stooq daily prices", ("stooq.com",),
           "free for non-commercial use; attribute stooq.com",
           "end-of-day only; informal per-IP daily download limit; no intraday data"),
    Source("Alpha Vantage (free tier)", ("www.alphavantage.co",),
           "free API key; follow Alpha Vantage terms and attribute",
           "25 requests/day; last 100 daily closes on the free tier; premium endpoints are never called",
           key="free key (no payment)"),
    Source("FRED (keyless CSV)", ("fred.stlouisfed.org",),
           "public data; cite Federal Reserve Bank of St. Louis and the original source",
           "series-level CSV; some series carry third-party copyright notices"),
    Source("FRED API", ("api.stlouisfed.org",),
           "public data; free API key", "120 requests/minute", key="free key (no payment)"),
    Source("Federal Register API", ("www.federalregister.gov",), "US government public data", "no key; be polite"),
    Source("OFAC sanctions list", ("www.treasury.gov", "sanctionslistservice.ofac.treas.gov"),
           "US government public data", "full list download; refresh daily at most"),
    Source("Internet Archive Wayback availability", ("archive.org", "web.archive.org"),
           "archive.org terms of use", "availability API only; be polite"),
)

LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "ollama", "host.docker.internal")

# Hosts that bill per request or per token. Reachable only with explicit opt-in.
PAID_HOSTS = ("api.anthropic.com", "api.openai.com")


class PaidRequestBlocked(RuntimeError):
    """A request to a host that can incur charges, without explicit opt-in."""


class UnapprovedHostBlocked(RuntimeError):
    """A request to a host that is not classified as free (refused by default)."""


def paid_apis_allowed() -> bool:
    return os.environ.get("DEEPTERMINAL_ALLOW_PAID_APIS", "false").strip().lower() in ("1", "true", "yes")


def network_disabled() -> bool:
    """True in the hosted public demo: no outbound request of any kind, free or paid."""
    return os.environ.get("DEEPTERMINAL_NETWORK_DISABLED", "false").strip().lower() in ("1", "true", "yes")


def classify(url: str) -> str:
    """'free' | 'local' | 'paid' | 'unknown'."""
    host = (urlparse(url).hostname or "").lower()
    if host in LOCAL_HOSTS or host.endswith(".local"):
        return "local"
    if any(host == h or host.endswith("." + h) for h in PAID_HOSTS):
        return "paid"
    if any(host == h for s in FREE_SOURCES for h in s.hosts):
        return "free"
    return "unknown"


def check_url(url: str) -> None:
    """Raise unless the request is free, local, or an explicitly enabled paid request."""
    kind = classify(url)
    if network_disabled() and kind != "local":
        raise UnapprovedHostBlocked(f"blocked request to {urlparse(url).hostname}: network access is disabled "
                                    "(public demo serves a fixed snapshot)")
    if kind in ("free", "local"):
        return
    if kind == "paid":
        if paid_apis_allowed():
            return
        raise PaidRequestBlocked(f"blocked request to {urlparse(url).hostname}: paid APIs are disabled "
                                 "(set DEEPTERMINAL_ALLOW_PAID_APIS=true to opt in)")
    raise UnapprovedHostBlocked(f"blocked request to {urlparse(url).hostname}: host is not on the free-source "
                                "list in deepterminal/costpolicy.py")


def source_for(url: str) -> Source | None:
    host = (urlparse(url).hostname or "").lower()
    return next((s for s in FREE_SOURCES if host in s.hosts), None)
