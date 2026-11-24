"""Polite, cached, retrying HTTP fetcher with explicit failure classes.

Failure classes matter because they need different responses:

* :class:`NetworkPolicyBlocked` — a proxy or firewall refused the connection
  (e.g. a cloud sandbox whose egress policy does not allow the host). Not
  retried: retrying cannot help and routing around it is not acceptable.
* :class:`AccessDenied` — the server itself answered 403 (for SEC this usually
  means a missing/undeclared User-Agent or a fair-access block).
* :class:`RateLimited` — 429, or 503 with Retry-After, after retries are exhausted.
* :class:`NotFound` — 404 (e.g. unknown CIK).
* :class:`FetchError` — anything else after retries (timeouts, resets, 5xx).

Every successful network response is cached as the exact bytes received plus
a ``.meta.json`` sidecar recording URL, retrieval time (UTC), HTTP status,
content type and SHA-256, so any figure can be traced to the response it came
from and re-verified later.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import re
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from ..costpolicy import PaidRequestBlocked, UnapprovedHostBlocked, check_url


class FetchError(RuntimeError):
    def __init__(self, message: str, url: str = "", hint: str = ""):
        super().__init__(message + (f"\n  hint: {hint}" if hint else ""))
        self.url = url
        self.hint = hint


class NetworkPolicyBlocked(FetchError):
    pass


class AccessDenied(FetchError):
    pass


class RateLimited(FetchError):
    pass


class NotFound(FetchError):
    pass


class OfflineCacheMiss(FetchError):
    pass


class CostPolicyBlocked(FetchError):
    """Refused before any network traffic: the host is paid or not on the free-source list."""


@dataclass(frozen=True)
class FetchResult:
    url: str
    body: bytes
    retrieved_at: datetime
    sha256: str
    from_cache: bool
    cache_path: Path | None
    status: int = 200
    content_type: str = ""

    def json(self):
        return json.loads(self.body)


def redact(url: str) -> str:
    """URL with secret query parameters (API keys, tokens) masked, for logs and cache metadata."""
    return re.sub(r"([?&](?:apikey|api_key|key|token|access_token)=)[^&]+", r"\1REDACTED", url, flags=re.I)


def _decode(body: bytes, encoding: str | None) -> bytes:
    if encoding == "gzip" or body[:2] == b"\x1f\x8b":
        return gzip.decompress(body)
    if encoding == "deflate":
        return zlib.decompress(body)
    return body


def _is_proxy_refusal(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "tunnel connection failed" in text or "proxy" in text and "403" in text


class CachedFetcher:
    """HTTP GET with rate limiting, retries with exponential backoff, and a disk cache.

    ``offline=True`` never touches the network (cache only) — used by tests and
    for reproducible re-runs of recorded responses.
    """

    def __init__(self, cache_dir: str | Path, user_agent: str, min_interval: float = 0.125,
                 max_retries: int = 4, backoff_base: float = 1.0, timeout: float = 30.0,
                 offline: bool = False, opener: Callable | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.cache_dir = Path(cache_dir)
        self.user_agent = user_agent
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.timeout = timeout
        self.offline = offline
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep
        self._last_request = 0.0

    # ── cache ──────────────────────────────────────────────────────────
    def _paths(self, key: str) -> tuple[Path, Path]:
        return self.cache_dir / key, self.cache_dir / (key + ".meta.json")

    def read_cache(self, key: str, max_age: timedelta | None) -> FetchResult | None:
        body_path, meta_path = self._paths(key)
        if not (body_path.exists() and meta_path.exists()):
            return None
        meta = json.loads(meta_path.read_text())
        retrieved = datetime.fromisoformat(meta["retrieved_at"])
        if max_age is not None and not self.offline and datetime.now(timezone.utc) - retrieved > max_age:
            return None
        raw = body_path.read_bytes()
        body = gzip.decompress(raw) if body_path.suffix == ".gz" else raw
        digest = hashlib.sha256(body).hexdigest()
        if digest != meta["sha256"]:
            raise FetchError(f"cache integrity check failed for {body_path}", meta.get("url", ""),
                             "delete the cached file and fetch again")
        return FetchResult(meta["url"], body, retrieved, digest, True, body_path,
                           meta.get("status", 200), meta.get("content_type", ""))

    def write_cache(self, key: str, res: FetchResult) -> Path:
        body_path, meta_path = self._paths(key)
        body_path.parent.mkdir(parents=True, exist_ok=True)
        data = gzip.compress(res.body, mtime=0) if body_path.suffix == ".gz" else res.body
        body_path.write_bytes(data)
        meta_path.write_text(json.dumps({
            "url": redact(res.url), "retrieved_at": res.retrieved_at.isoformat(), "status": res.status,
            "content_type": res.content_type, "sha256": res.sha256, "bytes": len(res.body),
            "note": "sha256 is of the decoded response body exactly as served",
        }, indent=2))
        return body_path

    # ── network ────────────────────────────────────────────────────────
    def get(self, url: str, cache_key: str, max_age: timedelta | None = None,
            refresh: bool = False, accept: str = "application/json") -> FetchResult:
        if not refresh or self.offline:
            cached = self.read_cache(cache_key, max_age)
            if cached:
                return cached
        if self.offline:
            raise OfflineCacheMiss(f"offline mode and no cached response for {url}", url,
                                   "run once with network access (or record responses) first")
        res = self._fetch(url, accept)
        path = self.write_cache(cache_key, res)
        return FetchResult(res.url, res.body, res.retrieved_at, res.sha256, False, path,
                           res.status, res.content_type)

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            self._sleep(wait)
        self._last_request = time.monotonic()

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), 120.0)
            except ValueError:
                pass
        return self.backoff_base * (2 ** attempt) + random.uniform(0, 0.25 * self.backoff_base)

    def _fetch(self, url: str, accept: str = "application/json") -> FetchResult:
        try:
            check_url(url)              # zero-cost policy: free/local hosts only unless paid APIs are enabled
        except (PaidRequestBlocked, UnapprovedHostBlocked) as e:
            raise CostPolicyBlocked(str(e), url, "see docs/FREE_ARCHITECTURE.md") from e
        headers = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate",
                   "Accept": accept}
        last_exc: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            req = urllib.request.Request(url, headers=headers)
            try:
                with self._open(req, timeout=self.timeout) as resp:
                    body = _decode(resp.read(), resp.headers.get("Content-Encoding"))
                    return FetchResult(url, body, datetime.now(timezone.utc),
                                       hashlib.sha256(body).hexdigest(), False, None,
                                       getattr(resp, "status", 200),
                                       resp.headers.get("Content-Type", ""))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise NotFound(f"404 Not Found: {url}", url) from e
                if e.code == 403:
                    raise AccessDenied(
                        f"403 Forbidden from server: {url}", url,
                        "SEC requires a User-Agent naming you and a contact e-mail, and limits "
                        "clients to 10 requests/second; check DEEPTERMINAL_SEC_USER_AGENT") from e
                if e.code in (429, 500, 502, 503, 504):
                    last_exc = e
                    if attempt < self.max_retries:
                        self._sleep(self._backoff(attempt, e.headers.get("Retry-After") if e.headers else None))
                        continue
                    cls = RateLimited if e.code in (429, 503) else FetchError
                    raise cls(f"HTTP {e.code} after {attempt + 1} attempts: {url}", url,
                              "slow down or retry later") from e
                raise FetchError(f"HTTP {e.code}: {url}", url) from e
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                reason = getattr(e, "reason", e)
                if _is_proxy_refusal(reason) or _is_proxy_refusal(e):
                    raise NetworkPolicyBlocked(
                        f"connection to {url} refused by a network proxy/firewall ({reason})", url,
                        "this environment's egress policy does not allow the host; allow it in the "
                        "environment's network settings or run from a machine with access. "
                        "Do not route around the restriction.") from e
                last_exc = e
                if attempt < self.max_retries:
                    self._sleep(self._backoff(attempt, None))
                    continue
        raise FetchError(f"network error after {self.max_retries + 1} attempts: {url} ({last_exc})", url)
