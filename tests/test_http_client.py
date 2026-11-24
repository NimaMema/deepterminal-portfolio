"""CachedFetcher transport behaviour, using an injected opener (no network)."""

import gzip
import io
import json
import urllib.error
from datetime import timedelta

import pytest

from deepterminal.data.http import (AccessDenied, CachedFetcher, FetchError, NetworkPolicyBlocked, NotFound,
                                    OfflineCacheMiss, RateLimited)


class Resp:
    def __init__(self, body: bytes, encoding: str | None = None):
        self._b = body
        self.status = 200
        self.headers = {"Content-Encoding": encoding, "Content-Type": "application/json"} if encoding else \
            {"Content-Type": "application/json"}

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, retry_after=None):
    hdrs = {"Retry-After": retry_after} if retry_after else {}
    return urllib.error.HTTPError("https://x", code, "err", hdrs, io.BytesIO(b""))


def opener_from(seq, calls):
    def _open(req, timeout):
        calls.append(req)
        item = seq.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item
    return _open


def fetcher(tmp_path, seq, calls, sleeps, **kw):
    return CachedFetcher(tmp_path, "Test Agent test@example.com", min_interval=0, backoff_base=0.01,
                         opener=opener_from(seq, calls), sleep=sleeps.append, **kw)


def test_retries_then_succeeds_and_respects_retry_after(tmp_path):
    calls, sleeps = [], []
    f = fetcher(tmp_path, [http_error(503, "2"), http_error(500), Resp(b'{"ok": 1}')], calls, sleeps)
    r = f.get("https://data.sec.gov/x", "x.json")
    assert r.json() == {"ok": 1} and len(calls) == 3
    assert 2.0 in sleeps
    assert calls[0].get_header("User-agent") == "Test Agent test@example.com"


def test_rate_limit_exhaustion(tmp_path):
    f = fetcher(tmp_path, [http_error(429)] * 3, [], [], max_retries=2)
    with pytest.raises(RateLimited):
        f.get("https://data.sec.gov/x", "x.json")


@pytest.mark.parametrize("err,cls", [(http_error(404), NotFound), (http_error(403), AccessDenied),
                                     (http_error(400), FetchError)])
def test_http_errors_are_classified_without_retry(tmp_path, err, cls):
    calls = []
    f = fetcher(tmp_path, [err, Resp(b"{}")], calls, [])
    with pytest.raises(cls):
        f.get("https://data.sec.gov/x", "x.json")
    assert len(calls) == 1


def test_proxy_policy_block_is_not_retried(tmp_path):
    calls = []
    err = urllib.error.URLError(OSError("Tunnel connection failed: 403 Forbidden"))
    f = fetcher(tmp_path, [err, Resp(b"{}")], calls, [])
    with pytest.raises(NetworkPolicyBlocked) as ei:
        f.get("https://data.sec.gov/x", "x.json")
    assert len(calls) == 1 and "Do not route around" in str(ei.value)


def test_transient_network_errors_retry(tmp_path):
    calls = []
    f = fetcher(tmp_path, [urllib.error.URLError("timed out"), Resp(b"[]")], calls, [])
    assert f.get("https://data.sec.gov/x", "x.json").json() == []


def test_gzip_cache_roundtrip_integrity_and_offline(tmp_path):
    body = json.dumps({"a": list(range(50))}).encode()
    f = fetcher(tmp_path, [Resp(gzip.compress(body), "gzip")], [], [])
    r1 = f.get("https://data.sec.gov/y", "y.json.gz")
    assert r1.body == body and not r1.from_cache
    meta = json.loads((tmp_path / "y.json.gz.meta.json").read_text())
    assert meta["url"] == "https://data.sec.gov/y" and meta["sha256"] == r1.sha256 and meta["retrieved_at"]
    off = CachedFetcher(tmp_path, "x", offline=True)
    r2 = off.get("https://data.sec.gov/y", "y.json.gz")
    assert r2.from_cache and r2.body == body and r2.retrieved_at == r1.retrieved_at
    with pytest.raises(OfflineCacheMiss):
        off.get("https://data.sec.gov/z", "z.json")
    (tmp_path / "y.json.gz").write_bytes(gzip.compress(b'{"tampered": true}'))
    with pytest.raises(FetchError, match="integrity"):
        off.get("https://data.sec.gov/y", "y.json.gz")


def test_stale_cache_is_refetched(tmp_path):
    calls = []
    f = fetcher(tmp_path, [Resp(b"1"), Resp(b"2")], calls, [])
    f.get("https://data.sec.gov/q", "q.json")
    assert f.get("https://data.sec.gov/q", "q.json", max_age=timedelta(days=1)).body == b"1"
    assert f.get("https://data.sec.gov/q", "q.json", max_age=timedelta(seconds=-1)).body == b"2"
    assert len(calls) == 2
