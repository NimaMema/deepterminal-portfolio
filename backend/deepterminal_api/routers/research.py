"""Research jobs (investigations, thesis challenges, reports), live progress, chat, reports."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import public_demo as demo
from ..analysis import MODULES
from ..db import get_db, session_scope
from ..models import ChatMessage, ChatSession, Finding, JobEvent, Report, ResearchJob
from ..research import chat as chat_svc
from ..research.orchestrator import create_job, submit
from ..services import reports as rp
from ..services.evidence import finding_dict
from ..services.gateway import DataUnavailable
from .companies import company_or_404

router = APIRouter(tags=["research"])


class JobIn(BaseModel):
    company_id: int
    kind: str = Field("investigation", pattern="^(investigation|thesis|report)$")
    modules: list[str] | None = None
    discount_rate: float | None = Field(None, gt=0, lt=0.5)
    thesis: str | None = Field(None, max_length=2000)
    stance: str = Field("bullish", pattern="^(bullish|bearish|neutral)$")
    as_of: str | None = None
    investigation_id: str | None = None


def job_dict(j: ResearchJob) -> dict:
    return {"id": j.id, "company_id": j.company_id, "kind": j.kind, "modules": j.modules, "params": j.params,
            "status": j.status, "progress": j.progress, "current_step": j.current_step, "error": j.error,
            "result": j.result, "created_at": j.created_at.isoformat(),
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None}


@router.get("/modules")
def modules():
    return [{"key": m.key, "title": m.title, "capability": m.capability} for m in MODULES.values()]


@router.post("/jobs")
def start_job(body: JobIn, db: Session = Depends(get_db)):
    c = company_or_404(db, body.company_id)
    params = {k: v for k, v in body.model_dump().items() if k not in ("company_id", "kind", "modules") and v is not None}
    if body.kind == "thesis" and not (body.thesis or "").strip():
        raise DataUnavailable("unsupported", "A thesis statement is required.")
    demo.check_job(db, body.kind)
    mods = body.modules or (list(MODULES) if body.kind == "investigation" else [])
    job = create_job(db, c, body.kind, mods, params)
    submit(job.id)
    return job_dict(job)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    j = db.get(ResearchJob, job_id)
    if j is None:
        raise DataUnavailable("not_found", "job not found")
    out = job_dict(j)
    out["events"] = [{"id": e.id, "ts": e.ts.isoformat(), "level": e.level, "module": e.module, "message": e.message}
                     for e in db.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.id))]
    return out


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str, db: Session = Depends(get_db)):
    j = db.get(ResearchJob, job_id)
    if j and j.status in ("queued", "running"):
        j.status = "cancelled"
        db.commit()
    return job_dict(j)


@router.get("/jobs/{job_id}/stream")
async def stream(job_id: str, request: Request):
    """Server-sent events: job events and status until the job finishes."""
    async def gen():
        last = 0
        while True:
            if await request.is_disconnected():
                return
            with session_scope() as db:
                evs = db.scalars(select(JobEvent).where(JobEvent.job_id == job_id, JobEvent.id > last)
                                 .order_by(JobEvent.id)).all()
                j = db.get(ResearchJob, job_id)
                payload = [{"id": e.id, "ts": e.ts.isoformat(), "level": e.level, "module": e.module,
                            "message": e.message} for e in evs]
                status = {"status": j.status, "progress": j.progress, "current_step": j.current_step} if j else None
            for p in payload:
                last = p["id"]
                yield f"event: log\ndata: {json.dumps(p)}\n\n"
            yield f"event: status\ndata: {json.dumps(status)}\n\n"
            if not status or status["status"] in ("succeeded", "failed", "cancelled"):
                return
            await asyncio.sleep(0.7)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/companies/{company_id}/jobs")
def company_jobs(company_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(ResearchJob).where(ResearchJob.company_id == company_id)
                      .order_by(ResearchJob.created_at.desc()).limit(50))
    hidden = demo.visitor_job_ids(db, company_id)
    return [job_dict(j) for j in rows if j.id not in hidden]


@router.get("/jobs/{job_id}/findings")
def job_findings(job_id: str, db: Session = Depends(get_db)):
    return [finding_dict(f) for f in db.scalars(select(Finding).where(Finding.job_id == job_id).order_by(Finding.id))]


# ── chat ──
class SessionIn(BaseModel):
    company_id: int | None = None
    title: str = Field("Research chat", max_length=200)


class MessageIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=4000)


@router.post("/chat/sessions")
def new_session(body: SessionIn, db: Session = Depends(get_db)):
    s = ChatSession(company_id=body.company_id, title=body.title)
    db.add(s)
    db.commit()
    return {"id": s.id, "company_id": s.company_id, "title": s.title, "created_at": s.created_at.isoformat()}


@router.get("/chat/sessions")
def sessions(company_id: int | None = None, db: Session = Depends(get_db)):
    q = select(ChatSession).order_by(ChatSession.created_at.desc())
    if company_id:
        q = q.where(ChatSession.company_id == company_id)
    if demo.active():
        q = q.where(ChatSession.created_at <= demo.BOOT)
    return [{"id": s.id, "company_id": s.company_id, "title": s.title, "created_at": s.created_at.isoformat()}
            for s in db.scalars(q.limit(50))]


@router.get("/chat/sessions/{session_id}")
def get_session(session_id: str, db: Session = Depends(get_db)):
    s = db.get(ChatSession, session_id)
    if s is None:
        raise DataUnavailable("not_found", "session not found")
    msgs = db.scalars(select(ChatMessage).where(ChatMessage.session_id == s.id).order_by(ChatMessage.id)).all()
    return {"id": s.id, "company_id": s.company_id, "title": s.title,
            "messages": [chat_svc.message_dict(db, m) for m in msgs]}


@router.post("/chat/sessions/{session_id}/messages")
def post_message(session_id: str, body: MessageIn, db: Session = Depends(get_db)):
    s = db.get(ChatSession, session_id)
    if s is None:
        raise DataUnavailable("not_found", "session not found")
    m = chat_svc.ask(db, s, body.content)
    return chat_svc.message_dict(db, m)


# ── reports ──
class ReportIn(BaseModel):
    company_id: int
    investigation_id: str | None = None


@router.post("/reports")
def create_report(body: ReportIn, db: Session = Depends(get_db)):
    c = company_or_404(db, body.company_id)
    r = rp.build_report(db, c, body.investigation_id)
    return {"id": r.id, "title": r.title, "sections": r.sections, "created_at": r.created_at.isoformat()}


@router.get("/companies/{company_id}/reports")
def list_reports(company_id: int, db: Session = Depends(get_db)):
    return [{"id": r.id, "title": r.title, "job_id": r.job_id, "sections": r.sections,
             "created_at": r.created_at.isoformat()}
            for r in db.scalars(select(Report).where(Report.company_id == company_id).order_by(Report.created_at.desc()))]


@router.get("/reports")
def all_reports(db: Session = Depends(get_db)):
    return [{"id": r.id, "company_id": r.company_id, "title": r.title, "created_at": r.created_at.isoformat()}
            for r in db.scalars(select(Report).order_by(Report.created_at.desc()).limit(100))]


@router.get("/reports/{report_id}/html", response_class=HTMLResponse)
def report_html(report_id: str, db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if r is None:
        raise DataUnavailable("not_found", "report not found")
    return HTMLResponse(r.html, headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:"})


_PDF_CACHE: dict[str, bytes] = {}


@router.get("/reports/{report_id}/pdf")
def report_pdf(report_id: str, db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if r is None:
        raise DataUnavailable("not_found", "report not found")
    try:
        pdf = _PDF_CACHE.get(r.id) or rp.render_pdf(r.html)
        if demo.active():                  # demo reports never change; render each once
            _PDF_CACHE[r.id] = pdf
    except ImportError as e:
        raise DataUnavailable("not_configured", "PDF export is not installed on this server.",
                              'Install the "pdf" extra (pip install "./backend[pdf]") and run '
                              "`python -m playwright install chromium`.") from e
    except Exception as e:
        raise DataUnavailable("error", f"PDF rendering failed: {e}",
                              "Install Chromium (playwright) or set DEEPTERMINAL_CHROMIUM_EXECUTABLE.") from e
    safe = "".join(ch if ch.isalnum() else "-" for ch in r.title)[:60]
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.pdf"'})
