"""Health, configuration, data-source status, settings."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..analysis import MODULES
from ..config import get_settings
from ..db import get_db
from ..models import AppSetting, DataFetch
from ..research.providers import provider_status, tokens_used_today
from ..services.gateway import DataUnavailable, get_gateway

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("select 1"))
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


def showcase() -> dict:
    s = get_settings()
    path = Path(s.demo_showcase_path) if s.demo_showcase_path else Path(__file__).resolve().parents[2] / "demo" / "showcase.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


@router.get("/demo/showcase")
def demo_showcase():
    """Judges' guide: recorded AI examples (with attribution), sample questions, tour."""
    return showcase()


@router.get("/status")
def status(db: Session = Depends(get_db)):
    s = get_settings()
    return {"data_mode": s.data_mode, "synthetic": s.data_mode == "demo", "offline": s.offline,
            "sec_user_agent_configured": bool(s.sec_user_agent), "providers": provider_status(),
            "paid_apis_enabled": s.allow_paid_apis, "public_demo": s.public_demo,
            "snapshot_date": showcase().get("snapshot_date") if s.public_demo else None,
            # Public demo: true once the start-up warm-up has computed every screen once.
            "warm": os.path.exists(os.environ.get("DEEPTERMINAL_WARM_FLAG", "/tmp/deepterminal-warm-done"))
            if s.public_demo else None,
            "llm_tokens_today": tokens_used_today(), "llm_daily_budget": s.llm_daily_token_budget,
            "llm_limits": {"max_tool_calls": s.llm_max_tool_calls, "max_input_tokens_per_job": s.llm_max_input_tokens_per_job,
                           "max_output_tokens": s.llm_max_output_tokens},
            "modules": [{"key": m.key, "title": m.title, "capability": m.capability} for m in MODULES.values()]}


SOURCES = [
    {"id": "sec_edgar", "adapter": "sec", "name": "SEC EDGAR (filings, XBRL, submissions)",
     "hosts": ["www.sec.gov", "data.sec.gov"], "licence": "US government public data; fair-access policy",
     "cost": "free", "limits": "≤10 requests/second; User-Agent with contact e-mail required"},
    {"id": "edgar_fts", "adapter": "edgar_fts", "name": "EDGAR full-text search (who names this company)",
     "hosts": ["efts.sec.gov"], "licence": "US government public data", "cost": "free",
     "limits": "filings since 2001; results have no snippets, so quoted passages are fetched separately"},
    {"id": "stooq", "adapter": "stooq", "name": "Stooq end-of-day prices", "hosts": ["stooq.com"],
     "licence": "free for non-commercial use; attribution", "cost": "free (no key)",
     "limits": "end-of-day only; informal daily limit. Since Oct 2026 it can answer automated clients with a "
               "browser bot check, which DEEPTERMINAL respects (no data then)"},
    {"id": "alphavantage", "adapter": "alphavantage", "name": "Alpha Vantage end-of-day prices (free tier)",
     "hosts": ["www.alphavantage.co"], "licence": "Alpha Vantage terms; attribution",
     "cost": "free (free key, no payment)", "limits": "25 requests/day; last 100 daily closes; premium endpoints never used",
     "env": "DEEPTERMINAL_ALPHAVANTAGE_API_KEY"},
    {"id": "fred", "adapter": "fred", "name": "FRED economic data (keyless CSV)", "hosts": ["fred.stlouisfed.org"],
     "licence": "public data; cite FRED and original source", "cost": "free (no key)",
     "limits": "daily or monthly series; some series carry third-party copyright"},
    {"id": "federal_register", "adapter": "federal_register", "name": "Federal Register API",
     "hosts": ["www.federalregister.gov"], "licence": "US government public data", "cost": "free (no key)",
     "limits": "federal rules and notices only; not court dockets"},
    {"id": "ofac", "adapter": "ofac", "name": "OFAC sanctions list (SDN)",
     "hosts": ["sanctionslistservice.ofac.treas.gov"], "licence": "US government public data", "cost": "free",
     "limits": "name matching only: possible false positives and negatives"},
    {"id": "wayback", "adapter": "wayback", "name": "Internet Archive Wayback (historical websites)",
     "hosts": ["archive.org"], "licence": "archive.org terms", "cost": "free",
     "limits": "snapshot availability; page content is not analysed"},
    {"id": "ollama", "adapter": None, "name": "Ollama (local open-weight AI models)", "hosts": ["localhost:11434"],
     "licence": "model licence (e.g. Apache-2.0 for Qwen2.5)", "cost": "free (runs on your machine)",
     "limits": "quality and speed depend on the model and your hardware"},
    {"id": "anthropic", "adapter": None, "name": "Anthropic Claude API", "hosts": ["api.anthropic.com"],
     "licence": "API terms", "cost": "PAID — disabled unless DEEPTERMINAL_ALLOW_PAID_APIS=true", "env": "ANTHROPIC_API_KEY"},
    {"id": "openai", "adapter": None, "name": "OpenAI API", "hosts": ["api.openai.com"], "licence": "API terms",
     "cost": "PAID — disabled unless DEEPTERMINAL_ALLOW_PAID_APIS=true", "env": "OPENAI_API_KEY"},
    {"id": "news", "adapter": None, "name": "Licensed news, estimates, reviews, trade data", "hosts": [],
     "licence": "licence required", "cost": "paid — not used"},
]


@router.get("/sources")
def sources(db: Session = Depends(get_db)):
    s = get_settings()
    last = {r.adapter: r for r in db.scalars(select(DataFetch).order_by(DataFetch.id.desc()).limit(500))}
    providers = {p["provider"]: p for p in provider_status()}
    out = []
    for src in SOURCES:
        if src["id"] == "sec_edgar" and s.data_mode == "demo":
            st = {"configured": True, "status": "demo", "detail": "Demo mode: serving labelled synthetic data."}
        elif src["id"] == "sec_edgar" and not s.sec_user_agent:
            st = {"configured": False, "status": "not_configured", "detail": "Set DEEPTERMINAL_SEC_USER_AGENT."}
        elif src["id"] == "ollama":
            p = providers["ollama"]
            st = {"configured": p["configured"], "status": "ready" if p["configured"] else "not_running",
                  "detail": p["detail"]}
        elif src["id"] in ("anthropic", "openai"):
            p = providers[src["id"]]
            st = {"configured": p["configured"], "status": "enabled" if p["configured"] else "disabled",
                  "detail": p["detail"]}
        elif src["id"] == "alphavantage" and not s.alphavantage_api_key:
            st = {"configured": False, "status": "not_configured",
                  "detail": "Optional: set DEEPTERMINAL_ALPHAVANTAGE_API_KEY to a free key (no payment) as a price fallback."}
        elif not src["hosts"]:
            st = {"configured": False, "status": "not_used", "detail": "Requires a paid licence; not used."}
        else:
            r = last.get(src["adapter"])
            st = {"configured": True, "status": r.status if r else "untested",
                  "detail": (r.detail or r.url) if r else "No request made yet."}
        out.append({**src, **st})
    return {"sources": out, "network_note": get_settings().network_note,
            "cost_policy": {"paid_apis_enabled": s.allow_paid_apis, "llm_provider": s.llm_provider,
                            "summary": "Zero-cost mode: only free public sources and local AI are contacted."
                            if not s.allow_paid_apis else
                            "Paid APIs are ENABLED by DEEPTERMINAL_ALLOW_PAID_APIS; requests may incur charges."}}


@router.post("/sources/sec_edgar/probe")
def probe_sec():
    try:
        data, meta = get_gateway().tickers()
        return {"status": "ok", "retrieved_at": meta.retrieved_at.isoformat(), "from_cache": meta.from_cache,
                "synthetic": meta.synthetic, "companies": len(data)}
    except DataUnavailable as e:
        return {"status": e.status, **e.to_dict()}


class SettingIn(BaseModel):
    value: dict


ALLOWED_SETTINGS = {"default_valuation", "ui", "watchlist"}


@router.get("/settings")
def get_app_settings(db: Session = Depends(get_db)):
    return {r.key: r.value for r in db.scalars(select(AppSetting))}


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingIn, db: Session = Depends(get_db)):
    if key not in ALLOWED_SETTINGS:
        raise DataUnavailable("not_found", f"unknown setting {key}")
    row = db.get(AppSetting, key) or AppSetting(key=key, value={})
    row.value = body.value
    db.add(row)
    db.commit()
    return {key: row.value}


@router.get("/fetch-log")
def fetch_log(db: Session = Depends(get_db), limit: int = 50):
    rows = db.scalars(select(DataFetch).order_by(DataFetch.id.desc()).limit(min(limit, 200)))
    return [{"adapter": r.adapter, "url": r.url, "status": r.status, "sha256": r.sha256,
             "retrieved_at": r.retrieved_at.isoformat(), "detail": r.detail} for r in rows]


MACRO_SERIES = [
    ("DGS10", "10-year Treasury yield", "percent", "risk-free reference for the discount rate"),
    ("DGS3MO", "3-month Treasury bill yield", "percent", "short rate"),
    ("T10YIE", "10-year breakeven inflation", "percent", "market inflation expectation"),
    ("BAA10Y", "Moody's Baa corporate spread over 10-year Treasury", "percent", "credit conditions"),
    ("FEDFUNDS", "Effective federal funds rate", "percent", "policy rate"),
    ("UNRATE", "Unemployment rate", "percent", "labour market"),
]


@router.get("/macro")
def macro():
    """Latest observation of key FRED series (keyless CSV; free). Each series reports its own availability."""
    from ..services.free_sources import free_sources
    out = []
    failed: DataUnavailable | None = None
    for sid, label, unit, use in MACRO_SERIES:
        try:
            if failed and failed.status not in ("not_found", "offline"):
                raise failed              # FRED unreachable: report it for every series, do not wait again
            rows, res = free_sources().fred_series(sid)
            obs = [(d, v) for d, v in rows if v is not None]
            d, v = obs[-1]
            prev = next((x for x in reversed(obs) if (d - x[0]).days >= 365), None)
            out.append({"id": sid, "label": label, "unit": unit, "use": use, "value": v, "date": d.isoformat(),
                        "year_ago": prev[1] if prev else None, "retrieved_at": res.retrieved_at.isoformat(),
                        "url": f"https://fred.stlouisfed.org/series/{sid}", "status": "ok"})
        except DataUnavailable as e:
            failed = e
            out.append({"id": sid, "label": label, "unit": unit, "use": use, "status": e.status,
                        "message": e.message, "hint": e.hint})
    return {"series": out, "source": "Federal Reserve Bank of St. Louis, FRED (fred.stlouisfed.org)",
            "note": "Context only. DEEPTERMINAL never sets your discount rate; the 10-year yield is shown as a "
                    "reference you may use in your own build-up."}
