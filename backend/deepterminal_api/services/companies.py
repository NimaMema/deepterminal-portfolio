"""Company search, profiles and financial statements (with per-figure provenance)."""

from __future__ import annotations

import threading
from datetime import date, datetime
from typing import Any

from sqlalchemy import text, func, or_, select
from sqlalchemy.orm import Session

from deepterminal.data import sec_edgar as se

from ..config import get_settings
from ..models import Company, Filing, TickerIndex
from .gateway import DataUnavailable, Meta, get_gateway

_facts_cache: dict[int, tuple[dict, Meta]] = {}
_lock = threading.Lock()


def sync_ticker_index(db: Session) -> int:
    gw = get_gateway()
    data, meta = gw.tickers()
    rows = se.parse_tickers(data)
    db.query(TickerIndex).delete()
    seen = set()
    for cik, ticker, name in rows:
        if (cik, ticker) in seen:
            continue
        seen.add((cik, ticker))
        db.add(TickerIndex(cik=cik, ticker=ticker, name=name, synthetic=meta.synthetic))
    db.commit()
    return len(seen)


_index_lock = threading.Lock()
TICKER_INDEX_LOCK_ID = 7_402_011       # Postgres advisory lock: one loader across processes


def ensure_ticker_index(db: Session) -> None:
    """Load the ticker index once. Concurrent first requests (several API calls on an empty database)
    would otherwise each insert the same rows and fail on the primary key."""
    if db.scalar(select(func.count()).select_from(TickerIndex)):
        return
    with _index_lock:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": TICKER_INDEX_LOCK_ID})
        if not db.scalar(select(func.count()).select_from(TickerIndex)):
            sync_ticker_index(db)
        else:
            db.commit()                 # release the advisory lock


def search(db: Session, q: str, limit: int = 12) -> list[dict]:
    ensure_ticker_index(db)
    q = q.strip()
    if not q:
        return []
    qu = q.upper().replace(".", "-")
    conds = [TickerIndex.ticker == qu, TickerIndex.ticker.like(f"{qu}%"), TickerIndex.name.ilike(f"%{q}%")]
    if q.isdigit():
        conds.append(TickerIndex.cik == int(q))
    stmt = select(TickerIndex).where(or_(*conds))
    if get_settings().public_demo:          # only the companies in the demo snapshot
        stmt = stmt.where(TickerIndex.cik.in_(select(Company.cik)))
    rows = db.scalars(stmt.limit(200)).all()

    def rank(r: TickerIndex) -> tuple:
        return (r.ticker != qu, not r.ticker.startswith(qu), not r.name.lower().startswith(q.lower()), len(r.name))
    return [{"cik": r.cik, "ticker": r.ticker, "name": r.name, "synthetic": r.synthetic}
            for r in sorted(rows, key=rank)[:limit]]


def resolve(db: Session, query: str) -> Company:
    """Ticker or CIK → Company row (profile refreshed from SEC submissions)."""
    ensure_ticker_index(db)
    q = query.strip().upper().replace(".", "-")
    row = None
    if q.isdigit():
        row = db.scalar(select(TickerIndex).where(TickerIndex.cik == int(q)))
        cik = int(q)
    else:
        row = db.scalar(select(TickerIndex).where(TickerIndex.ticker == q))
        if row is None:
            raise DataUnavailable("not_found", f"No SEC registrant with ticker {query!r}.",
                                  "Search by company name or CIK instead.")
        cik = row.cik
    company = db.scalar(select(Company).where(Company.cik == cik))
    if company is None or company.profile_retrieved_at is None:
        company = refresh_profile(db, cik, fallback=row)
    return company


def refresh_profile(db: Session, cik: int, fallback: TickerIndex | None = None) -> Company:
    gw = get_gateway()
    company = db.scalar(select(Company).where(Company.cik == cik)) or Company(cik=cik, name=fallback.name if fallback else str(cik))
    sub, meta = gw.submissions(cik)
    company.name = sub.get("name") or company.name
    company.ticker = (sub.get("tickers") or [fallback.ticker if fallback else None])[0]
    company.sic = sub.get("sic")
    company.sic_description = sub.get("sicDescription")
    company.state_of_incorporation = sub.get("stateOfIncorporationDescription") or sub.get("stateOfIncorporation")
    company.fiscal_year_end = sub.get("fiscalYearEnd")
    company.entity_type = sub.get("entityType")
    company.category = sub.get("category")
    company.ein = sub.get("ein")
    company.website = sub.get("website") or None
    company.exchanges = sub.get("exchanges") or []
    company.former_names = sub.get("formerNames") or []
    company.addresses = sub.get("addresses") or {}
    filings = sub.get("filings", {})
    starts = [f.get("filingFrom") for f in filings.get("files", []) if f.get("filingFrom")]
    starts += [min(filings.get("recent", {}).get("filingDate") or [None]) or None]
    starts = [d for d in starts if d]
    company.first_filing_date = date.fromisoformat(min(starts)) if starts else None
    company.synthetic = meta.synthetic
    company.profile_retrieved_at = meta.retrieved_at
    db.add(company)
    db.flush()
    sync_filings(db, company, sub)
    db.commit()
    return company


def sync_filings(db: Session, company: Company, sub: dict) -> int:
    rec = sub.get("filings", {}).get("recent", {})
    existing = {a for (a,) in db.execute(select(Filing.accession).where(Filing.company_id == company.id))}
    n = 0
    for i, accn in enumerate(rec.get("accessionNumber", [])):
        if accn in existing:
            continue
        def g(k, default=""):
            v = rec.get(k, [])
            return v[i] if i < len(v) else default
        rd = g("reportDate")
        doc = g("primaryDocument")
        db.add(Filing(company_id=company.id, accession=accn, form=g("form"), filed=date.fromisoformat(g("filingDate")),
                      report_date=date.fromisoformat(rd) if rd else None, primary_document=doc or None,
                      url=se.ARCHIVES_URL.format(cik=company.cik, accn=accn.replace("-", ""), name=doc) if doc
                      else se.filing_url(company.cik, accn),
                      items=[x for x in (g("items") or "").split(",") if x], size=g("size", None) or None,
                      synthetic=company.synthetic))
        n += 1
    return n


def companyfacts(company: Company, refresh: bool = False) -> tuple[dict, Meta]:
    with _lock:
        if not refresh and company.cik in _facts_cache:
            return _facts_cache[company.cik]
    facts, meta = get_gateway().companyfacts(company.cik)
    with _lock:
        _facts_cache[company.cik] = (facts, meta)
    return facts, meta


def clear_caches() -> None:
    with _lock:
        _facts_cache.clear()


def profile_dict(c: Company) -> dict[str, Any]:
    return {"id": c.id, "cik": c.cik, "ticker": c.ticker, "name": c.name, "sic": c.sic,
            "sic_description": c.sic_description, "state_of_incorporation": c.state_of_incorporation,
            "fiscal_year_end": c.fiscal_year_end, "entity_type": c.entity_type, "category": c.category,
            "ein": c.ein, "website": c.website, "exchanges": c.exchanges, "former_names": c.former_names,
            "addresses": c.addresses, "synthetic": c.synthetic,
            "first_filing_date": c.first_filing_date.isoformat() if c.first_filing_date else None, "financial_institution": se.is_financial_sic(c.sic),
            "profile_retrieved_at": c.profile_retrieved_at.isoformat() if c.profile_retrieved_at else None,
            "edgar_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={c.cik:010d}"}


# ───────────────────────────── statements ─────────────────────────────

STATEMENTS: dict[str, list[tuple[str, str]]] = {
    "income": [("revenue", "Revenue"), ("cost_of_revenue", "Cost of revenue"), ("gross_profit", "Gross profit"),
               ("rnd", "Research & development"), ("sga", "Selling, general & administrative"),
               ("operating_income", "Operating income"), ("interest_expense", "Interest expense"),
               ("pretax_income", "Pre-tax income"), ("income_tax", "Income tax"), ("net_income", "Net income"),
               ("diluted_shares", "Diluted shares (m)")],
    "balance": [("cash", "Cash & equivalents"), ("marketable_securities_current", "Marketable securities (current)"),
                ("accounts_receivable", "Accounts receivable"), ("inventory", "Inventory"),
                ("assets_current", "Total current assets"), ("ppe_net", "Property, plant & equipment"),
                ("goodwill", "Goodwill"), ("total_assets", "Total assets"), ("accounts_payable", "Accounts payable"),
                ("deferred_revenue", "Deferred revenue"), ("liabilities_current", "Total current liabilities"),
                ("total_debt", "Long-term debt"), ("total_liabilities", "Total liabilities"),
                ("retained_earnings", "Retained earnings"), ("shareholders_equity", "Shareholders' equity")],
    "cashflow": [("operating_cash_flow", "Operating cash flow"), ("capex", "Capital expenditures"),
                 ("depreciation", "Depreciation & amortization"), ("stock_based_comp", "Stock-based compensation"),
                 ("dividends_paid", "Dividends paid"), ("buybacks", "Share repurchases"),
                 ("acquisitions", "Acquisitions")],
}


def _cell(f: se.Fact | None, cik: int, scale: float, meta: Meta) -> dict | None:
    if f is None:
        return None
    return {"value": f.value / scale, "concept": f"us-gaap:{f.concept}", "accession": f.accession, "form": f.form,
            "filed": f.filed.isoformat(), "start": f.start.isoformat() if f.start else None,
            "end": f.end.isoformat(), "url": se.filing_url(cik, f.accession),
            "retrieved_at": meta.retrieved_at.isoformat(),
            **({"derived": f"split-adjusted ×{f.split_factor:g} (filed value {f.value / f.split_factor / scale:,.1f})"}
               if f.split_factor != 1.0 else {})}


def statements(company: Company, period: str = "annual", as_of: date | None = None,
               revision: str = "latest", years: int = 10) -> dict[str, Any]:
    facts, meta = companyfacts(company)
    se.check_supported(facts)
    cik = company.cik
    out: dict[str, Any] = {"period": period, "as_of": as_of.isoformat() if as_of else None, "revision": revision,
                           "currency": "USD", "unit": "millions", "synthetic": meta.synthetic,
                           "retrieved_at": meta.retrieved_at.isoformat(),
                           "source_url": se.COMPANYFACTS_URL.format(cik=cik), "statements": {}}
    if period == "annual":
        series = {n: se.annual_series(facts, n, as_of, revision) for s in STATEMENTS.values() for n, _ in s}
        ends = sorted({e for n in ("revenue", "net_income") for e in series[n]})[-years:]
        cols = [{"end": e.isoformat(), "label": f"FY{e.year}"} for e in ends]
        def get(n, e):
            return series[n].get(e)
    else:
        flows = {n for s in STATEMENTS.values() for n, _ in s if se.CONCEPTS[n][2]}
        qs = {n: se.quarterly_series(facts, n, as_of, "latest") for n in flows}
        inst = {n: se.instant_series(facts, n, as_of, "latest")
                for s in STATEMENTS.values() for n, _ in s if not se.CONCEPTS[n][2]}
        ends = sorted(qs["revenue"])[-12:]
        cols = [{"end": e.isoformat(), "label": f"Q-end {e.isoformat()}"} for e in ends]
        def get(n, e):
            if n in qs:
                q = qs[n].get(e)
                if q is None:
                    return None
                f = q.facts[0]
                fake = se.Fact(f.concept, q.end, q.start, q.value, max(x.filed for x in q.facts), f.form,
                               max(q.facts, key=lambda x: x.filed).accession, None)
                return fake
            return inst[n].get(e)
    out["columns"] = cols
    for sname, rows in STATEMENTS.items():
        srows = []
        for key, label in rows:
            cells = [_cell(get(key, e), cik, 1e6, meta) for e in ends]
            if any(cells):
                srows.append({"key": key, "label": label, "cells": cells})
        out["statements"][sname] = srows
    # derived free cash flow row (formula shown, inputs referenced)
    ocf = next((r for r in out["statements"]["cashflow"] if r["key"] == "operating_cash_flow"), None)
    capex = next((r for r in out["statements"]["cashflow"] if r["key"] == "capex"), None)
    if ocf and capex:
        cells = []
        for a, b in zip(ocf["cells"], capex["cells"]):
            cells.append({"value": a["value"] - b["value"], "derived": "operating cash flow − capital expenditures",
                          "inputs": [a["accession"], b["accession"]]} if a and b else None)
        out["statements"]["cashflow"].append({"key": "fcf", "label": "Free cash flow (derived)", "cells": cells})
    revs = se.detect_revisions(facts, as_of=as_of)
    out["revisions"] = [{"field": r.field, "period_end": r.period_end.isoformat(), "original": r.original / 1e6,
                         "revised": r.revised / 1e6, "original_accession": r.original_accession,
                         "revised_accession": r.revised_accession, "revised_filed": r.revised_filed.isoformat(),
                         "kind": r.kind, "split_ratio": r.split_ratio}
                        for r in revs]
    return out


def key_metrics(company: Company, as_of: date | None = None) -> dict[str, Any]:
    """Headline metrics for the overview (latest FY and TTM) with provenance."""
    facts, meta = companyfacts(company)
    se.check_supported(facts)
    annual = se.build_periods(facts, as_of=as_of, retrieved_at=meta.retrieved_at)
    ttm = se.build_ttm_period(facts, as_of=as_of, retrieved_at=meta.retrieved_at)
    from deepterminal.financials.statements import analyse
    an = analyse(annual) if annual else None
    hist = []
    if an:
        for p, m in zip(annual, an.metrics):
            hist.append({"fy": p.fiscal_year, "end": p.period_end.isoformat(), "revenue": p.revenue,
                         "operating_income": p.operating_income, "net_income": p.net_income,
                         "fcf": m.fcf, "fcf_after_sbc": m.fcf_after_sbc, "operating_margin": m.operating_margin,
                         "net_margin": m.net_margin, "revenue_growth": m.revenue_growth,
                         "gross_margin": m.gross_margin, "roe": m.roe, "sbc_pct_revenue": m.sbc_pct_revenue,
                         "dso": m.dso, "dio": m.dio, "net_debt": m.net_debt, "diluted_shares": p.diluted_shares,
                         "filed": p.filed.isoformat() if p.filed else None, "source_ref": p.source_ref})
    t = None
    if ttm:
        t = {"start": ttm.period_start.isoformat(), "end": ttm.period_end.isoformat(), "revenue": ttm.revenue,
             "operating_income": ttm.operating_income, "net_income": ttm.net_income,
             "operating_margin": ttm.operating_income / ttm.revenue if ttm.revenue else None,
             "fcf": ttm.operating_cash_flow - ttm.capex, "cash": ttm.cash, "total_debt": ttm.total_debt,
             "diluted_shares": ttm.diluted_shares, "filed": ttm.filed.isoformat() if ttm.filed else None}
    # Chart series: every fiscal year with reported revenue. Years missing another field (e.g. capex filed
    # under a company-specific tag) stay visible with that field empty, instead of disappearing.
    rev = se.annual_series(facts, "revenue", as_of, "latest")
    oi = se.annual_series(facts, "operating_income", as_of, "latest")
    ni = se.annual_series(facts, "net_income", as_of, "latest")
    trend = []
    for e in sorted(rev)[-12:]:
        r = rev[e].value
        trend.append({"fy": e.year, "end": e.isoformat(), "revenue": r / 1e6,
                      "operating_margin": oi[e].value / r if e in oi and r else None,
                      "net_margin": ni[e].value / r if e in ni and r else None,
                      "accession": rev[e].accession})
    shares = se.shares_outstanding(facts, as_of)
    return {"history": hist, "trend": trend, "ttm": t, "flags": [f.__dict__ for f in an.flags] if an else [],
            "shares_outstanding": shares.value if shares else None,
            "shares_outstanding_as_of": shares.period_end.isoformat() if shares else None,
            "synthetic": meta.synthetic, "retrieved_at": meta.retrieved_at.isoformat()}
