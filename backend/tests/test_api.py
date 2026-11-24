"""End-to-end API tests: search → profile → statements → filings → modules → valuation → jobs → chat → reports."""

import importlib.util

import pytest


def test_health_and_status(client):
    assert client.get("/api/health").json()["status"] == "ok"
    s = client.get("/api/status").json()
    assert s["data_mode"] == "demo" and s["synthetic"] is True
    assert next(p for p in s["providers"] if p["provider"] == "rules")["active"] is True   # no LLM key in tests
    assert len(s["modules"]) == 14
    assert s["paid_apis_enabled"] is False                                   # zero-cost default
    assert all(not p["configured"] for p in s["providers"] if p["paid"])


def test_search_and_resolve(client):
    r = client.get("/api/search", params={"q": "harbor"}).json()["results"]
    assert r[0]["ticker"] == "DHB" and r[0]["synthetic"]
    assert client.get("/api/search", params={"q": "9900003"}).json()["results"][0]["ticker"] == "DIM"
    e = client.get("/api/companies/resolve/NOPE")
    assert e.status_code == 404 and e.json()["status"] == "not_found" and e.json()["hint"]


def test_profile_metrics_and_statement_provenance(client, dqd):
    p = client.get(f"/api/companies/{dqd['id']}").json()
    assert p["synthetic"] and p["metrics"]["ttm"]["end"] == "2026-06-30"
    st = client.get(f"/api/companies/{dqd['id']}/statements").json()
    rev = next(r for r in st["statements"]["income"] if r["key"] == "revenue")
    cell = rev["cells"][-1]
    assert cell["concept"] == "us-gaap:Revenues" and cell["accession"] and cell["filed"] and cell["retrieved_at"]
    assert any(r["field"] == "revenue" for r in st["revisions"])          # demo restatement detected
    orig = client.get(f"/api/companies/{dqd['id']}/statements", params={"revision": "original"}).json()
    assert orig["statements"]["income"][0]["cells"] != st["statements"]["income"][0]["cells"]
    q = client.get(f"/api/companies/{dqd['id']}/statements", params={"period": "quarterly"}).json()
    assert q["columns"][-1]["end"] == "2026-06-30"


def test_filings_document_search_and_diff(client, dqd):
    fs = client.get(f"/api/companies/{dqd['id']}/filings", params={"form": "10-K"}).json()
    assert len(fs) == 11
    doc = client.get(f"/api/companies/{dqd['id']}/filings/{fs[0]['accession']}").json()
    keys = {s["key"] for s in doc["sections"]}
    assert {"full", "item_1", "item_1a", "item_3", "item_7"} <= keys
    client.post(f"/api/companies/{dqd['id']}/filings/index", json={"forms": ["10-K"], "limit": 4})
    hits = client.get(f"/api/companies/{dqd['id']}/search", params={"q": "foundry Taiwan"}).json()["results"]
    assert hits and "<<" in hits[0]["snippet"]
    d = client.get(f"/api/companies/{dqd['id']}/risk-diff").json()
    assert d["counts"]["added"] >= 1


def test_time_machine_is_point_in_time(client, dqd):
    tm = client.get(f"/api/companies/{dqd['id']}/time-machine", params={"as_of": "2024-06-01"}).json()
    assert all(f["filed"] <= "2024-06-01" for f in tm["filings_known"])
    assert all(n["filed"] > "2024-06-01" for n in tm["next_filings"])
    assert any(r["field"] == "revenue" for r in tm["later_revisions"])


@pytest.mark.parametrize("module", ["sec_analysis", "corporate_legitimacy", "management_governance", "forensic_accounting",
                                    "supply_chain", "product_research", "customer_demand", "competitors",
                                    "legal_regulatory", "market_sentiment", "historical_analogues"])
def test_module_dashboards(client, dqd, module):
    for t in ("DHB", "DIM", "DCS", "DNR"):
        client.get(f"/api/companies/resolve/{t}")
    r = client.get(f"/api/companies/{dqd['id']}/modules/{module}")
    assert r.status_code == 200 and r.json()["synthetic"] is True
    if module == "supply_chain":
        alts = {a["entity"]: a for a in r.json()["data"]["alternatives"]}
        f = alts["Formosa Precision Foundry Co., Ltd."]
        assert f["single_source"] and f["status"] == "mitigation disclosed"
        assert all(a["status"] != "mitigation disclosed" for n, a in alts.items() if n != f["entity"])
        assert not any(a["candidates"] for a in alts.values())   # no other semiconductor company is loaded


def test_valuation_requires_discount_rate_and_price(client, dqd):
    r = client.post(f"/api/companies/{dqd['id']}/valuation", json={"settings": {}})
    assert r.status_code == 422 and "discount rate" in r.json()["message"]
    no_price = client.post(f"/api/companies/{dqd['id']}/valuation", json={"settings": {"discount_rate": 0.095}}).json()
    assert no_price["price"] is None and no_price["unavailable"]["status"] == "no_price" and no_price["reverse_dcf"] == []
    bad = client.post(f"/api/companies/{dqd['id']}/prices", json={"value": 140, "as_of": "2026-10-27", "source": ""})
    assert bad.status_code == 422
    assert client.post(f"/api/companies/{dqd['id']}/prices", json={"value": 140, "as_of": "2026-10-27",
                                                                    "source": "demo price (synthetic)"}).status_code == 200
    v = client.post(f"/api/companies/{dqd['id']}/valuation", json={"settings": {"discount_rate": 0.095}, "save": True}).json()
    assert v["price"]["value"] == 140 and "under specified assumptions" in v["assessment"]["verdict"] or \
        v["assessment"]["verdict"].startswith("Too uncertain")
    s = {x["name"]: x["per_share"] for x in v["scenarios"]}
    assert s["bear"] <= s["base"] <= s["bull"]
    sol = next(r for r in v["reverse_dcf"] if r["status"] != "none_in_bounds")
    assert abs(sol["target_enterprise_value"] - v["market"]["enterprise_value"]) < 1e-6
    assert v["run_id"]
    assert v["multiples"]["Forward P/E"]["value"] is None and "licensed" in v["multiples"]["Forward P/E"]["reason"]
    f = client.post(f"/api/companies/{dqd['id']}/valuation", json={"settings": {"discount_rate": 0.095, "forward_eps": 3.5}}).json()
    assert f["multiples"]["Forward P/E"]["value"] == 40 and "your forward EPS" in f["multiples"]["Forward P/E"]["reason"]
    shock = client.post(f"/api/companies/{dqd['id']}/valuation/shock", json={"settings": {"discount_rate": 0.095},
                                                                              "revenue_shock": .2, "margin_shock": .03, "years": 2}).json()
    assert shock["shocked_ev"] < shock["base_ev"]


def test_calculators(client):
    r = client.post("/api/valuation/sotp", json={"segments": [{"name": "A", "enterprise_value": 600, "method": "x"},
                                                              {"name": "B", "enterprise_value": 400, "method": "y"}],
                                                 "annual_corporate_cost": 10, "tax_rate": .25, "discount_rate": .09, "growth": .015}).json()
    assert abs(r["enterprise_value"] - 900) < 1e-9
    assert client.post("/api/valuation/nav", json={"assets": [{"name": "x", "book_value": 1, "recovery_rate": 1, "rationale": ""}],
                                                   "liabilities": 0}).status_code == 422


def test_investigation_job_findings_and_evidence(client, dqd):
    job = client.post("/api/jobs", json={"company_id": dqd["id"], "kind": "investigation", "discount_rate": 0.095}).json()
    j = client.get(f"/api/jobs/{job['id']}").json()
    assert j["status"] == "succeeded", j["error"]
    assert set(j["result"]["modules"]) == {m["key"] for m in client.get("/api/modules").json()}
    assert any("No LLM provider configured" in e["message"] for e in j["events"])
    fs = client.get(f"/api/jobs/{job['id']}/findings").json()
    assert len(fs) > 40
    assert all(f["evidence_ids"] or f["severity"] == "unavailable" for f in fs)
    ev = client.get(f"/api/evidence/{next(f for f in fs if f['module'] == 'supply_chain' and f['evidence_ids'])['evidence_ids'][0]}").json()
    assert ev["source"]["accession"] and ev["source"]["synthetic"] and ev["verification_status"] == "verified"
    assert ev["context"]["text"] and ev["excerpt"].split()[0] in ev["context"]["text"]
    alt = next(f for f in fs if f["title"].startswith("Alternative sourcing for Formosa"))
    assert "second foundry" in alt["summary"] and len(alt["evidence_ids"]) == 2
    g = client.get(f"/api/companies/{dqd['id']}/graph").json()
    assert g["source"] == "investigation" and any(e["evidence_id"] for e in g["edges"])


def test_thesis_challenger(client, dqd):
    job = client.post("/api/jobs", json={"company_id": dqd["id"], "kind": "thesis", "stance": "bullish",
                                         "thesis": "Growth will stay above 40% thanks to an unassailable moat and pricing power."}).json()
    r = client.get(f"/api/jobs/{job['id']}").json()
    assert r["status"] == "succeeded", r["error"]
    res = r["result"]
    assert {"growth", "competitive advantage"} <= {c["claim"] for c in res["claims"]}
    assert res["counter_evidence"] and res["alternative_explanations"] and res["llm"]["status"] == "skipped"
    assert all(f["severity"] in ("concern", "watch") for f in res["counter_evidence"])
    assert client.post("/api/jobs", json={"company_id": dqd["id"], "kind": "thesis", "thesis": " "}).status_code == 422


def test_chat_extractive_with_valid_citations(client, dqd):
    s = client.post("/api/chat/sessions", json={"company_id": dqd["id"]}).json()
    m = client.post(f"/api/chat/sessions/{s['id']}/messages", json={"content": "What are the risks around the foundry in Taiwan?"}).json()
    assert m["generated_by"] == "rules" and "No language model is configured" in m["content"]
    assert m["citations"] and all(c["source"] for c in m["citations"])
    import re
    cited = {int(x) for x in re.findall(r"\[E(\d+)\]", m["content"])}
    assert cited <= {c["id"] for c in m["citations"]}
    quotes = re.findall(r"“(.+?)”", m["content"])
    assert len(quotes) == len({" ".join(q.lower().split()) for q in quotes}), "repeated passages should be collapsed"


def test_report_html_and_pdf(client, dqd):
    rep = client.post("/api/reports", json={"company_id": dqd["id"]}).json()
    assert len(rep["sections"]) == 21
    html = client.get(f"/api/reports/{rep['id']}/html")
    assert "SYNTHETIC DEMO DATA" in html.text and "Source bibliography" in html.text
    assert "default-src 'none'" in html.headers["content-security-policy"]
    pdf = client.get(f"/api/reports/{rep['id']}/pdf")
    if importlib.util.find_spec("playwright") is None:      # optional extra; CI installs it
        assert pdf.status_code == 422 and pdf.json()["status"] == "not_configured"
        return
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_saved_items_and_peers(client, dqd):
    w = client.post("/api/saved", json={"company_id": dqd["id"], "kind": "watchlist", "title": "DQD"}).json()
    again = client.post("/api/saved", json={"company_id": dqd["id"], "kind": "watchlist", "title": "DQD"}).json()
    assert w["id"] == again["id"]                                         # watchlist is idempotent
    n = client.patch(f"/api/saved/{w['id']}", json={"notes": "check export controls"}).json()
    assert n["notes"] == "check export controls"
    peer = client.post(f"/api/companies/{dqd['id']}/peers", json={"peer": "DCS", "relation": "indirect", "rationale": "test"})
    assert peer.status_code == 200
    comp = client.get(f"/api/companies/{dqd['id']}/modules/competitors").json()["data"]
    assert [p["ticker"] for p in comp["peers"]] == ["DCS"] and comp["ranks"]
    assert client.post(f"/api/companies/{dqd['id']}/peers", json={"peer": "DQD"}).status_code == 422


def test_security_controls(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/search", params={"q": "x" * 200}).status_code == 422       # input validation
    assert client.put("/api/settings/not_allowed", json={"value": {}}).status_code == 404


def test_module_error_is_reported_not_silent(client, dqd, monkeypatch):
    from deepterminal_api import analysis
    spec = analysis.MODULES["product_research"]
    def boom(ctx, data):
        raise TypeError("simulated parser failure")
    monkeypatch.setitem(analysis.MODULES, "product_research", spec.__class__(spec.key, spec.title, spec.capability, spec.compute, boom))
    job = client.post("/api/jobs", json={"company_id": dqd["id"], "kind": "investigation", "modules": ["product_research"]}).json()
    j = client.get(f"/api/jobs/{job['id']}").json()
    assert j["result"]["modules"]["product_research"]["status"] == "error"
    fs = client.get(f"/api/jobs/{job['id']}/findings").json()
    assert any(f["severity"] == "unavailable" and "module error" in f["title"] for f in fs)


def test_ticker_index_load_is_safe_under_concurrency(client):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy import text
    from deepterminal_api.db import engine
    with engine().begin() as c:
        c.execute(text("DELETE FROM ticker_index"))
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda _: client.get("/api/search?q=DQD").status_code, range(8)))
    assert codes == [200] * 8


def test_evidence_pack_always_includes_valuation_findings(client, dqd):
    from deepterminal_api.db import session_factory
    from deepterminal_api.research.orchestrator import evidence_pack
    client.post(f"/api/companies/{dqd['id']}/prices", json={"value": 140, "as_of": "2026-10-27", "source": "demo price (synthetic)"})
    job = client.post("/api/jobs", json={"company_id": dqd["id"], "kind": "investigation", "discount_rate": 0.09}).json()
    with session_factory()() as db:
        pack, _ = evidence_pack(db, dqd["id"], job["id"], max_findings=5, max_evidence=5)
    assert "[financial_valuation]" in pack and "[market_expectations]" in pack


def test_model_cannot_choose_valuation_inputs(client, dqd):
    from deepterminal_api.analysis.base import Ctx
    from deepterminal_api.db import session_factory
    from deepterminal_api.models import Company
    from deepterminal_api.research.tools import ToolBox
    with session_factory()() as db:
        ctx = Ctx(db, db.get(Company, dqd["id"]))
        tb = ToolBox(ctx, "test")
        spec = next(t for t in tb.specs() if t.name == "valuation")
        assert spec.parameters["properties"] == {}
        assert spec.fn({"discount_rate": 0.01, "base_growth": 0.9})["unavailable"]["status"] == "not_configured"
        ctx.cache["params"] = {"discount_rate": 0.09}
        out = spec.fn({"discount_rate": 0.01})                       # ignored: the user's rate is used
        rate = next(a for a in out["assumptions"] if a["name"] == "discount_rate")
        assert rate["value"] == 0.09
