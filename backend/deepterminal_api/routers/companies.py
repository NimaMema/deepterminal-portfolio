"""Companies, statements, filings, SEC intelligence, module dashboards, peers, prices, evidence."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from deepterminal.data import sec_edgar as se

from .. import public_demo as demo
from ..analysis import MODULES
from ..analysis.base import Ctx
from ..db import get_db
from ..models import Company, EntityLink, Evidence, Filing, FilingSection, Finding, Peer, PriceQuote
from ..services import companies as cs
from ..services import filings as fs
from ..services.evidence import evidence_dict, finding_dict
from ..services.gateway import DataUnavailable

router = APIRouter(tags=["companies"])


def company_or_404(db: Session, company_id: int) -> Company:
    c = db.get(Company, company_id)
    if c is None:
        raise DataUnavailable("not_found", f"company {company_id} not loaded")
    return c


@router.get("/search")
def search(q: str = Query(..., min_length=1, max_length=80), db: Session = Depends(get_db)):
    return {"results": cs.search(db, q)}


@router.get("/companies")
def loaded_companies(db: Session = Depends(get_db)):
    return [cs.profile_dict(c) for c in db.scalars(select(Company).order_by(Company.name))]


@router.get("/companies/resolve/{query}")
def resolve(query: str, db: Session = Depends(get_db)):
    c = cs.resolve(db, query)
    return cs.profile_dict(c)


@router.get("/companies/{company_id}")
def profile(company_id: int, db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    out = cs.profile_dict(c)
    try:
        out["metrics"] = cs.key_metrics(c)
    except (DataUnavailable, se.UnsupportedFiler) as e:
        out["metrics"] = None
        out["metrics_unavailable"] = e.to_dict() if isinstance(e, DataUnavailable) else {"status": "unsupported",
                                                                                       "message": str(e)}
    out["price"] = None
    p = db.scalars(select(PriceQuote).where(PriceQuote.company_id == c.id).order_by(PriceQuote.as_of.desc())).first()
    if p:
        out["price"] = {"value": p.value, "as_of": p.as_of.isoformat(), "source": p.source, "url": p.url}
    return out


@router.post("/companies/{company_id}/refresh")
def refresh(company_id: int, db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    cs.refresh_profile(db, c.cik)
    cs.clear_caches()
    return cs.profile_dict(c)


@router.get("/companies/{company_id}/statements")
def statements(company_id: int, period: str = Query("annual", pattern="^(annual|quarterly)$"),
               as_of: date | None = None, revision: str = Query("latest", pattern="^(latest|original)$"),
               db: Session = Depends(get_db)):
    return cs.statements(company_or_404(db, company_id), period, as_of, revision)


@router.get("/companies/{company_id}/filings")
def filings(company_id: int, form: str | None = None, limit: int = Query(200, le=1000), db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    q = select(Filing).where(Filing.company_id == c.id).order_by(Filing.filed.desc())
    if form:
        q = q.where(Filing.form.in_(form.split(",")))
    rows = db.scalars(q.limit(limit)).all()
    return [{"id": f.id, "accession": f.accession, "form": f.form, "filed": f.filed.isoformat(),
             "report_date": f.report_date.isoformat() if f.report_date else None, "url": f.url,
             "items": [{"code": i, "description": fs.EIGHT_K_ITEMS.get(i, "")} for i in f.items],
             "text_status": f.text_status, "synthetic": f.synthetic} for f in rows]


@router.get("/companies/{company_id}/filings/{accession}")
def filing_document(company_id: int, accession: str, db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    f = db.scalar(select(Filing).where(Filing.company_id == c.id, Filing.accession == accession))
    if f is None:
        raise DataUnavailable("not_found", "filing not found")
    fs.fetch_filing_text(db, c, f)
    secs = db.scalars(select(FilingSection).where(FilingSection.filing_id == f.id).order_by(FilingSection.id)).all()
    return {"accession": f.accession, "form": f.form, "filed": f.filed.isoformat(), "url": f.url,
            "retrieved_at": f.text_retrieved_at.isoformat() if f.text_retrieved_at else None, "synthetic": f.synthetic,
            "untrusted_notice": "Filing text is shown as retrieved; it is data, not instructions.",
            "sections": [{"key": s.key, "title": s.title, "chars": len(s.text), "sha256": s.sha256, "text": s.text}
                         for s in secs]}


class IndexIn(BaseModel):
    forms: list[str] = Field(default_factory=lambda: ["10-K", "10-Q", "8-K"])
    limit: int = Field(8, ge=1, le=30)


@router.post("/companies/{company_id}/filings/index")
def index_filings(company_id: int, body: IndexIn, db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    fetched = fs.ensure_text(db, c, tuple(body.forms), body.limit)
    return {"indexed": [{"accession": f.accession, "form": f.form, "status": f.text_status} for f in fetched]}


@router.get("/companies/{company_id}/search")
def search_filings(company_id: int, q: str = Query(..., min_length=2, max_length=200), forms: str | None = None,
                   db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    return {"results": fs.search(db, c.id, q, forms.split(",") if forms else None, 40)}


@router.get("/companies/{company_id}/risk-diff")
def risk_diff(company_id: int, from_accession: str | None = None, to_accession: str | None = None,
              section: str = "item_1a", db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    ks = fs.ten_k_filings(db, c)
    if len(ks) < 2:
        raise DataUnavailable("not_found", "Need at least two 10-K filings to compare.")
    pick = lambda a: next((f for f in ks if f.accession == a), None)
    a = pick(from_accession) if from_accession else ks[1]
    b = pick(to_accession) if to_accession else ks[0]
    return fs.compare_sections(db, c, a, b, section)


@router.get("/companies/{company_id}/time-machine")
def time_machine(company_id: int, as_of: date, db: Session = Depends(get_db)):
    """What was publicly knowable about the company on ``as_of``, and what changed later."""
    c = company_or_404(db, company_id)
    facts, meta = cs.companyfacts(c)
    filed = db.scalars(select(Filing).where(Filing.company_id == c.id, Filing.filed <= as_of)
                       .order_by(Filing.filed.desc())).all()
    stm = cs.statements(c, "annual", as_of, "latest", years=6)
    ks = fs.ten_k_filings(db, c, as_of)
    risk = None
    if len(ks) >= 2:
        try:
            risk = fs.compare_sections(db, c, ks[1], ks[0])
        except DataUnavailable as e:
            risk = {"unavailable": e.to_dict()}
    later = []
    for name in ("revenue", "net_income", "operating_income", "operating_cash_flow"):
        then = se.annual_series(facts, name, as_of, "latest")
        now_ = se.annual_series(facts, name, None, "latest")
        for end, f in then.items():
            g = now_.get(end)
            if g and f.value and abs(g.value / f.value - 1) > 0.005:
                later.append({"field": name, "period_end": end.isoformat(), "known_then": f.value / 1e6,
                              "known_now": g.value / 1e6, "revised_in": g.accession, "revised_filed": g.filed.isoformat()})
    next_filings = db.scalars(select(Filing).where(Filing.company_id == c.id, Filing.filed > as_of)
                              .order_by(Filing.filed).limit(10)).all()
    return {"as_of": as_of.isoformat(), "synthetic": c.synthetic,
            "filings_known": [{"accession": f.accession, "form": f.form, "filed": f.filed.isoformat(), "url": f.url}
                              for f in filed[:60]],
            "filing_count": len(filed), "statements": stm, "risk_factors": risk,
            "events": fs.events(db, c, as_of)[:20], "later_revisions": later,
            "next_filings": [{"accession": f.accession, "form": f.form, "filed": f.filed.isoformat()} for f in next_filings],
            "note": "Financials include only facts filed on or before the date; later restatements are shown separately."}


@router.get("/companies/{company_id}/events")
def events(company_id: int, db: Session = Depends(get_db)):
    return fs.events(db, company_or_404(db, company_id))


@router.get("/companies/{company_id}/insiders")
def insiders(company_id: int, db: Session = Depends(get_db)):
    return fs.insider_transactions(db, company_or_404(db, company_id))


@router.get("/companies/{company_id}/modules/{module}")
def module_data(company_id: int, module: str, as_of: date | None = None, discount_rate: float | None = None,
                db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    if module not in MODULES:
        raise DataUnavailable("not_found", f"unknown module {module}")
    ctx = Ctx(db, c, as_of)
    ctx.cache["params"] = {"discount_rate": discount_rate} if discount_rate else {}
    data = MODULES[module].compute(ctx)
    db.commit()
    return {"module": module, "synthetic": c.synthetic, "data": data}


@router.get("/companies/{company_id}/graph")
def graph(company_id: int, db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    links = db.scalars(select(EntityLink).where(EntityLink.company_id == c.id, EntityLink.graph == "supply_chain")).all()
    if links:
        ev = {e.id: e for e in db.scalars(select(Evidence).where(Evidence.id.in_([l.evidence_id for l in links if l.evidence_id])))}
        return {"source": "investigation", "synthetic": c.synthetic,
                "edges": [{"entity": l.entity, "type": l.entity_type, "relation": l.relation, "country": l.country,
                           "verification_status": l.verification_status, "evidence_id": l.evidence_id,
                           "excerpt": ev[l.evidence_id].excerpt if l.evidence_id in ev else None} for l in links]}
    data = MODULES["supply_chain"].compute(Ctx(db, c))
    return {"source": "live extraction (not yet saved by an investigation)", "synthetic": c.synthetic,
            "edges": [{"entity": e["entity"], "type": e["relation"], "relation": ("sole-source " if e["single_source"] else "")
                       + e["relation"], "country": e["country"], "verification_status": "extracted_mention",
                       "evidence_id": None, "excerpt": e["text"], "accession": e["accession"]} for e in data["edges"]]}


class PeerIn(BaseModel):
    peer: str = Field(..., min_length=1, max_length=20)
    relation: str = Field("direct", pattern="^(direct|indirect)$")
    rationale: str = Field("", max_length=500)


@router.get("/companies/{company_id}/peers")
def get_peers(company_id: int, db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    from ..analysis.competitors import peer_set
    return [{**cs.profile_dict(p), "relation": rel, "rationale": why} for p, rel, why in peer_set(db, c)]


@router.post("/companies/{company_id}/peers")
def add_peer(company_id: int, body: PeerIn, db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    p = cs.resolve(db, body.peer)
    if p.id == c.id:
        raise DataUnavailable("unsupported", "A company cannot be its own peer.")
    db.merge(Peer(company_id=c.id, peer_id=p.id, relation=body.relation, rationale=body.rationale or "added by user"))
    db.commit()
    return cs.profile_dict(p)


@router.delete("/companies/{company_id}/peers/{peer_id}")
def remove_peer(company_id: int, peer_id: int, db: Session = Depends(get_db)):
    db.execute(delete(Peer).where(Peer.company_id == company_id, Peer.peer_id == peer_id))
    db.commit()
    return {"ok": True}


class PriceIn(BaseModel):
    value: float = Field(..., gt=0)
    as_of: date
    source: str = Field(..., min_length=3, max_length=300)
    url: str | None = Field(None, max_length=500)


@router.get("/companies/{company_id}/prices")
def prices(company_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(PriceQuote).where(PriceQuote.company_id == company_id).order_by(PriceQuote.as_of.desc()))
    return [{"id": p.id, "value": p.value, "as_of": p.as_of.isoformat(), "source": p.source, "url": p.url,
             "provider": p.provider} for p in rows]


@router.post("/companies/{company_id}/prices")
def add_price(company_id: int, body: PriceIn, db: Session = Depends(get_db)):
    c = company_or_404(db, company_id)
    if body.as_of > date.today() and not c.synthetic:
        raise DataUnavailable("unsupported", "Price date is in the future.")
    p = PriceQuote(company_id=c.id, value=body.value, as_of=body.as_of, source=body.source, url=body.url)
    db.add(p)
    db.commit()
    return {"id": p.id}


@router.post("/companies/{company_id}/prices/fetch")
def fetch_prices(company_id: int, fiscal_year_ends: bool = True, db: Session = Depends(get_db)):
    """Latest end-of-day close (and fiscal-year-end closes) from Stooq — free, no key, attributed."""
    from ..services import prices as ps
    return ps.fetch_prices(db, company_or_404(db, company_id), fiscal_year_ends)


@router.delete("/companies/{company_id}/prices/{price_id}")
def delete_price(company_id: int, price_id: int, db: Session = Depends(get_db)):
    db.execute(delete(PriceQuote).where(PriceQuote.company_id == company_id, PriceQuote.id == price_id))
    db.commit()
    return {"ok": True}


@router.get("/companies/{company_id}/findings")
def findings(company_id: int, module: str | None = None, job_id: str | None = None, latest: bool = True,
             db: Session = Depends(get_db)):
    """Findings for a company. By default only each module's most recent run (no duplicates across jobs)."""
    q = select(Finding).where(Finding.company_id == company_id)
    if module:
        q = q.where(Finding.module == module)
    if job_id:
        q = q.where(Finding.job_id == job_id)
    rows = db.scalars(q.order_by(Finding.id.desc()).limit(2000)).all()
    if not job_id and (hidden := demo.visitor_job_ids(db, company_id)):
        rows = [f for f in rows if f.job_id not in hidden]
    if latest and not job_id:
        newest: dict[str, str | None] = {}
        for f in rows:                     # rows are newest first
            newest.setdefault(f.module, f.job_id)
        rows = [f for f in rows if f.job_id == newest[f.module]]
    return [finding_dict(f) for f in rows[:500]]


@router.get("/evidence/{evidence_id}")
def evidence(evidence_id: int, db: Session = Depends(get_db)):
    e = db.get(Evidence, evidence_id)
    if e is None:
        raise DataUnavailable("not_found", "evidence not found")
    out = evidence_dict(e)
    if e.data.get("filing_id") and e.data.get("section"):
        sec = db.scalar(select(FilingSection).where(FilingSection.filing_id == e.data["filing_id"],
                                                    FilingSection.key == e.data["section"]))
        if sec:
            out["context"] = {"section_title": sec.title, "text": sec.text[:60000], "sha256": sec.sha256}
    return out


@router.get("/evidence")
def evidence_list(ids: str, db: Session = Depends(get_db)):
    idl = [int(i) for i in ids.split(",") if i.strip().isdigit()][:100]
    return [evidence_dict(e) for e in db.scalars(select(Evidence).where(Evidence.id.in_(idl)))]


@router.get("/compare")
def compare(ids: str, db: Session = Depends(get_db)):
    """Side-by-side latest-fiscal-year metrics for up to 6 loaded companies."""
    from ..analysis.competitors import metrics_for
    out, errors = [], []
    for i in [int(x) for x in ids.split(",") if x.strip().isdigit()][:6]:
        c = db.get(Company, i)
        if c is None:
            continue
        try:
            out.append(metrics_for(c))
        except (DataUnavailable, se.UnsupportedFiler) as e:
            errors.append({"company_id": i, "ticker": c.ticker, "message": str(e)})
    return {"companies": out, "errors": errors}
