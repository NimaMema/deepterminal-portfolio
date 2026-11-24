"""Hosted public demo: read-only, offline, rule-based, rate-limited, and visitors' runs kept private."""

import gzip
import json
import os
import tempfile
from pathlib import Path

import pytest

from deepterminal import costpolicy

RECORDED = Path(tempfile.mkdtemp()) / "responses.json.gz"
with gzip.open(RECORDED, "wt") as _f:      # a response recorded with the snapshot, preloaded at start-up
    json.dump({"/api/macro?": ["application/json", '{"recorded": true}']}, _f)

DEMO_ENV = {"DEEPTERMINAL_PUBLIC_DEMO": "true", "DEEPTERMINAL_DEMO_CHAT_PER_HOUR": "4",
            "DEEPTERMINAL_PROXY_HOPS": "1", "DEEPTERMINAL_LLM_PROVIDER": "auto",
            "DEEPTERMINAL_DEMO_RESPONSES_PATH": str(RECORDED)}


@pytest.fixture(scope="module")
def demo(client, dqd):
    from fastapi.testclient import TestClient
    from deepterminal_api.config import get_settings
    from deepterminal_api.main import create_app
    saved = {k: os.environ.get(k) for k in [*DEMO_ENV, "DEEPTERMINAL_NETWORK_DISABLED", "DEEPTERMINAL_ALLOW_PAID_APIS"]}
    os.environ.update(DEMO_ENV)
    os.environ["DEEPTERMINAL_ALLOW_PAID_APIS"] = "true"          # must be overridden by the demo lock
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as c:
            yield c
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        os.environ["DEEPTERMINAL_NETWORK_DISABLED"] = "false"
        os.environ.pop("DEEPTERMINAL_ALLOW_PAID_APIS", None)
        get_settings.cache_clear()


def ip(n: int) -> dict:
    # proxy_hops=1: the last X-Forwarded-For entry is the client; anything before it is client-supplied.
    return {"x-forwarded-for": f"6.6.6.6, 10.0.0.{n}"}


def test_demo_settings_are_locked(demo):
    from deepterminal_api.config import get_settings
    s = get_settings()
    assert s.public_demo and s.offline and s.llm_provider == "rules" and not s.allow_paid_apis
    assert s.price_provider == "none" and s.api_token is None
    st = demo.get("/api/status").json()
    assert st["public_demo"] is True and st["paid_apis_enabled"] is False


def test_demo_disables_all_network_access(demo):
    assert os.environ["DEEPTERMINAL_NETWORK_DISABLED"] == "true"
    for url in ("https://data.sec.gov/submissions/CIK0001045810.json", "https://fred.stlouisfed.org/graph/fredgraph.csv",
                "https://api.anthropic.com/v1/messages"):
        with pytest.raises(costpolicy.UnapprovedHostBlocked):
            costpolicy.check_url(url)
    costpolicy.check_url("http://127.0.0.1:8000/api/health")


@pytest.mark.parametrize("method,path,body", [
    ("PUT", "/api/settings/ui", {"value": {}}),
    ("POST", "/api/reports", {"company_id": 1}),
    ("POST", "/api/saved", {"kind": "note", "title": "x"}),
    ("POST", "/api/companies/1/prices", {"value": 1, "as_of": "2026-01-02", "source": "test"}),
    ("POST", "/api/companies/1/prices/fetch", {}),
    ("POST", "/api/companies/1/refresh", {}),
    ("POST", "/api/companies/1/filings/index", {}),
    ("POST", "/api/companies/1/peers", {"peer": "DHB"}),
    ("DELETE", "/api/companies/1/peers/2", None),
    ("POST", "/api/sources/sec_edgar/probe", {}),
    ("POST", "/api/jobs/abc/cancel", {}),
])
def test_demo_refuses_writes(demo, method, path, body):
    r = demo.request(method, path, json=body, headers=ip(1))
    assert r.status_code == 403 and r.json()["status"] == "demo_readonly"


def test_demo_valuation_computes_but_does_not_save(demo, dqd):
    body = {"settings": {"discount_rate": 0.09}, "price": {"value": 20, "as_of": "2025-03-31", "source": "demo price"}}
    r = demo.post(f"/api/companies/{dqd['id']}/valuation", json=body, headers=ip(2))
    assert r.status_code == 200 and r.json()["scenarios"]
    r = demo.post(f"/api/companies/{dqd['id']}/valuation", json={**body, "save": True}, headers=ip(2))
    assert r.status_code == 403 and r.json()["status"] == "demo_readonly"


def test_demo_jobs_only_rule_based_thesis(demo, dqd):
    r = demo.post("/api/jobs", json={"company_id": dqd["id"], "kind": "investigation"}, headers=ip(3))
    assert r.status_code == 403 and r.json()["status"] == "demo_readonly"
    r = demo.post("/api/jobs", json={"company_id": dqd["id"], "kind": "thesis", "thesis": "Margins will keep expanding."},
                  headers=ip(3))
    assert r.status_code == 200
    job = r.json()["id"]
    # A visitor's run is reachable by id but not listed to other visitors.
    assert demo.get(f"/api/jobs/{job}").status_code == 200
    assert job not in {j["id"] for j in demo.get(f"/api/companies/{dqd['id']}/jobs").json()}
    assert all(f["job_id"] != job for f in demo.get(f"/api/companies/{dqd['id']}/findings").json())


def test_demo_chat_is_private_and_rate_limited(demo, dqd):
    s = demo.post("/api/chat/sessions", json={"company_id": dqd["id"], "title": "visitor"}, headers=ip(4)).json()
    m = demo.post(f"/api/chat/sessions/{s['id']}/messages", json={"content": "What are the main risks?"}, headers=ip(4))
    assert m.status_code == 200 and m.json()["generated_by"] == "rules"
    assert s["id"] not in {x["id"] for x in demo.get(f"/api/chat/sessions?company_id={dqd['id']}").json()}
    codes = [demo.post(f"/api/chat/sessions/{s['id']}/messages", json={"content": "Revenue?"},
                       headers={"x-forwarded-for": f"{n}.1.1.1, 10.0.0.4"}).status_code for n in range(5)]
    assert codes.count(429) >= 2           # 4 per hour per client; a spoofed first hop does not reset it
    other = demo.post(f"/api/chat/sessions/{s['id']}/messages", json={"content": "Revenue?"}, headers=ip(5))
    assert other.status_code == 200


def test_demo_search_is_limited_to_snapshot_companies(demo):
    tickers = {r["ticker"] for r in demo.get("/api/search?q=D").json()["results"]}
    loaded = {c["ticker"] for c in demo.get("/api/companies").json()}
    assert tickers and tickers <= loaded


def test_demo_rejects_large_requests(demo):
    r = demo.post("/api/chat/sessions", content=b"x" * 70_000, headers={"content-type": "application/json", **ip(6)})
    assert r.status_code == 413


def test_demo_showcase_endpoint(demo):
    assert demo.get("/api/demo/showcase").status_code == 200


def test_demo_serves_recorded_responses_and_caches_the_rest(demo, dqd):
    r = demo.get("/api/macro")
    assert r.json() == {"recorded": True} and r.headers.get("x-demo-cache") == "hit"
    first = demo.get(f"/api/companies/{dqd['id']}/statements")
    again = demo.get(f"/api/companies/{dqd['id']}/statements")
    assert first.status_code == 200 and again.headers.get("x-demo-cache") == "hit" and again.json() == first.json()
