"""Research job orchestration: background execution, live progress, bounded AI synthesis.

Jobs run in a small thread pool. Every step writes a JobEvent (streamed to the UI
over SSE) and updates progress. Modules are deterministic; the optional LLM step
only synthesises from evidence already gathered, and its citations are validated.
"""

from __future__ import annotations

import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select, update

from ..analysis import MODULES
from ..analysis.base import Ctx
from ..config import get_settings
from ..db import session_scope
from ..models import Company, Evidence, Finding, JobEvent, ResearchJob
from ..services.evidence import FindingDraft, save_finding, unavailable
from ..services.gateway import DataUnavailable
from . import guard
from .providers import BudgetExceeded, check_daily_budget, get_provider, record_usage

log = logging.getLogger("deepterminal.jobs")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="research")


def now() -> datetime:
    return datetime.now(timezone.utc)


def create_job(db, company: Company | None, kind: str, modules: list[str], params: dict) -> ResearchJob:
    bad = [m for m in modules if m not in MODULES]
    if bad:
        raise ValueError(f"unknown modules: {bad}")
    job = ResearchJob(company_id=company.id if company else None, kind=kind, modules=modules, params=params)
    db.add(job)
    db.commit()
    return job


def submit(job_id: str, sync: bool = False) -> None:
    if sync:
        run_job(job_id)
    else:
        _pool.submit(run_job, job_id)


def recover_stale_jobs() -> int:
    with session_scope() as db:
        r = db.execute(update(ResearchJob).where(ResearchJob.status.in_(("queued", "running")))
                       .values(status="failed", error="Server restarted while the job was running.",
                               finished_at=now()))
        return r.rowcount or 0


class JobLogger:
    def __init__(self, job_id: str):
        self.job_id = job_id

    def __call__(self, message: str, module: str | None = None, level: str = "info", progress: float | None = None,
                 data: dict | None = None) -> None:
        with session_scope() as db:
            db.add(JobEvent(job_id=self.job_id, message=message[:2000], module=module, level=level, data=data or {}))
            vals: dict[str, Any] = {"current_step": message[:250]}
            if progress is not None:
                vals["progress"] = progress
            db.execute(update(ResearchJob).where(ResearchJob.id == self.job_id).values(**vals))

    def cancelled(self) -> bool:
        with session_scope() as db:
            return db.scalar(select(ResearchJob.status).where(ResearchJob.id == self.job_id)) == "cancelled"


def run_job(job_id: str) -> None:
    jl = JobLogger(job_id)
    with session_scope() as db:
        job = db.get(ResearchJob, job_id)
        job.status, job.started_at = "running", now()
        kind = job.kind
    try:
        if kind == "investigation" or kind == "module":
            result = run_investigation(job_id, jl)
        elif kind == "thesis":
            from .thesis import run_thesis
            result = run_thesis(job_id, jl)
        elif kind == "report":
            from ..services.reports import build_report_job
            result = build_report_job(job_id, jl)
        else:
            raise ValueError(f"unknown job kind {kind}")
        with session_scope() as db:
            job = db.get(ResearchJob, job_id)
            if job.status != "cancelled":
                job.status = "succeeded"
            job.result = result
            job.progress = 1.0
            job.finished_at = now()
        jl("Completed", progress=1.0)
    except Exception as e:  # noqa: BLE001 - recorded on the job
        log.exception("job %s failed", job_id)
        with session_scope() as db:
            job = db.get(ResearchJob, job_id)
            job.status, job.error, job.finished_at = "failed", f"{type(e).__name__}: {e}", now()
        jl(f"Failed: {type(e).__name__}: {e}", level="error", data={"trace": traceback.format_exc()[-2000:]})


def run_investigation(job_id: str, jl: JobLogger) -> dict:
    with session_scope() as db:
        job = db.get(ResearchJob, job_id)
        modules, params, company_id = list(job.modules), dict(job.params), job.company_id
    as_of = date.fromisoformat(params["as_of"]) if params.get("as_of") else None
    summary: dict[str, Any] = {"modules": {}}
    n = len(modules) + 1
    with session_scope() as db:
        company = db.get(Company, company_id)
        ctx = Ctx(db, company, as_of, job_id, progress=lambda m: jl(m))
        ctx.cache["params"] = params
        jl(f"Investigation of {company.name} started ({len(modules)} modules)", progress=0.01,
           data={"synthetic": company.synthetic})
        for i, key in enumerate(modules):
            if jl.cancelled():
                jl("Cancelled by user", level="warning")
                return summary
            spec = MODULES[key]
            jl(f"Running {spec.title}…", module=key, progress=i / n)
            try:
                data = spec.compute(ctx)
                if key == "financial_valuation":
                    ctx.cache["financial_valuation_data"] = data
                drafts = spec.findings(ctx, data)
                rows = [save_finding(db, company, d, job_id, "rules") for d in drafts]
                db.commit()
                sev = {s: sum(1 for r in rows if r.severity == s) for s in ("concern", "watch", "positive", "unavailable")}
                summary["modules"][key] = {"status": "done", "findings": len(rows), "severity": sev}
                jl(f"{spec.title}: {len(rows)} findings ({sev['concern']} concern, {sev['watch']} watch, "
                   f"{sev['unavailable']} unavailable)", module=key, progress=(i + 1) / n)
            except DataUnavailable as e:
                db.rollback()
                save_finding(db, company, FindingDraft(key, f"{spec.title}: data unavailable", e.message + " " + e.hint,
                                                       "unavailable", "unverified_claim", "low"), job_id)
                db.commit()
                summary["modules"][key] = {"status": "unavailable", "reason": e.to_dict()}
                jl(f"{spec.title}: data unavailable — {e.message}", module=key, level="warning")
            except Exception as e:  # keep going with other modules
                db.rollback()
                log.exception("module %s failed", key)
                summary["modules"][key] = {"status": "error", "error": f"{type(e).__name__}: {e}"}
                jl(f"{spec.title} failed: {type(e).__name__}: {e}", module=key, level="error")
                save_finding(db, company, unavailable(key, f"{spec.title}: not assessed (module error)",
                                                      f"The analysis stopped with {type(e).__name__}; nothing from this "
                                                      "module is reported for this run."), job_id, "rules")
                db.commit()
        summary["synthesis"] = synthesize(db, company, job_id, jl)
        db.commit()
    return summary


SEVERITY_ORDER = {"concern": 0, "watch": 1, "positive": 2, "neutral": 3}
PINNED_MODULES = ("financial_valuation", "market_expectations")


def evidence_pack(db, company_id: int, job_id: str, max_findings: int = 150, max_evidence: int = 80) -> tuple[str, set[int]]:
    """Findings (most material first) and the evidence they cite, as untrusted documents.

    Smaller limits suit local models on modest hardware: prompt processing time grows with length,
    and everything left out is still in the findings list and the report."""
    findings = db.scalars(select(Finding).where(Finding.job_id == job_id).order_by(Finding.id)).all()
    # Valuation and market-expectation findings are always included (they are usually "neutral", so a
    # severity-ranked cap would drop them and the model would wrongly report that no valuation was run).
    usable = sorted((f for f in findings if f.severity != "unavailable"),
                    key=lambda f: (f.module not in PINNED_MODULES, SEVERITY_ORDER.get(f.severity, 9)))
    unavailable_titles = [f.title for f in findings if f.severity == "unavailable"]
    ids: set[int] = set()
    order: list[int] = []
    lines = []
    for f in usable[:max_findings]:
        cited = f.evidence_ids[:4]
        ids.update(f.evidence_ids)
        order.extend(i for i in cited if i not in order)
        lines.append(f"- [{f.module}] ({f.severity}, {f.epistemic_status}) {f.title} — {f.summary[:300]} "
                     + " ".join(f"[E{i}]" for i in cited))
    if unavailable_titles:
        lines.append("- NOT ASSESSED (data unavailable): " + "; ".join(t[:80] for t in unavailable_titles[:30]))
    by_id = {e.id: e for e in db.scalars(select(Evidence).where(Evidence.id.in_(order[:max_evidence]))).all()}
    docs = [guard.wrap(f"E{e.id}", e.title, (e.excerpt or e.locator or "") + (f" value={e.value} {e.unit}" if e.value is not None else ""), 600)
            for e in (by_id[i] for i in order[:max_evidence] if i in by_id)]
    return "FINDINGS:\n" + "\n".join(lines) + "\n\nEVIDENCE:\n" + "\n".join(docs), ids


def synthesize(db, company: Company, job_id: str, jl: JobLogger) -> dict:
    provider = get_provider()
    if provider is None:
        jl("No LLM provider configured: skipping narrative synthesis (findings above are deterministic).",
           module="synthesis", level="warning")
        return {"status": "skipped", "reason": "no LLM provider configured"}
    try:
        check_daily_budget(provider)
    except BudgetExceeded as e:
        jl(str(e), module="synthesis", level="warning")
        return {"status": "skipped", "reason": str(e)}
    s = get_settings()
    local = provider.name == "ollama"
    pack, allowed = evidence_pack(db, company.id, job_id,
                                  s.ollama_synthesis_findings if local else 150, s.ollama_synthesis_evidence if local else 80)
    prompt = (f"Company: {company.name} (ticker {company.ticker}). "
              + ("THIS IS A SYNTHETIC DEMO COMPANY. " if company.synthetic else "")
              + "Using ONLY the findings and evidence below, write an investment research synthesis with four "
                "short sections: (1) Is this a good business? (2) What do DEEPTERMINAL's valuation findings say? "
                "Report only values the findings state; if no valuation was run, say so — never estimate a value, "
                "price or range yourself. (3) What does the market price imply, per the findings (or that it is "
                "unknown)? (4) What might the market be overlooking, and what would invalidate the thesis? "
                "Every number you write must appear in the findings or evidence. Cite evidence ids like [E12] "
                "on every factual sentence, one id per bracket. Mark inferences as inferences. "
                "No buy/sell recommendation.\n\n" + pack)
    jl(f"Synthesising with {provider.name}:{provider.model}…", module="synthesis")
    res = provider.run(guard.SYSTEM_RULES, prompt, [], 0, s.llm_max_input_tokens_per_job,
                       s.ollama_max_output_tokens if local else s.llm_max_output_tokens)
    record_usage(provider, res.usage, job_id)
    if res.stopped in ("error", "refusal"):
        jl(f"Synthesis not produced: {res.text}", module="synthesis", level="warning")
        return {"status": res.stopped, "message": res.text}
    text, valid, invalid, removed = guard.ground(res.text, allowed, prompt)
    cov = guard.citation_coverage(text)
    save_finding(db, company, FindingDraft("synthesis", "AI research synthesis", text, "neutral",
                                           "analytical_inference", "medium", valid or [],
                                           f"Generated by {provider.name}:{provider.model} from DEEPTERMINAL findings; "
                                           f"{len(invalid)} invalid citation(s) and {len(removed)} unsupported sentence(s) "
                                           f"removed; citation coverage {cov:.0%}.",
                                           {"invalid_citations": invalid, "coverage": cov, "removed": removed}) if valid else
                 FindingDraft("synthesis", "AI research synthesis (uncited)", text, "unavailable", "unverified_claim",
                              "low", [], "Model output contained no valid citations; treat as unverified."),
                 job_id, f"{provider.name}:{provider.model}")
    jl(f"Synthesis complete (citation coverage {cov:.0%}, {len(invalid)} invalid citations and "
       f"{len(removed)} unsupported sentences removed)", module="synthesis")
    return {"status": "done", "coverage": cov, "invalid_citations": invalid, "removed_sentences": removed,
            "usage": {"input": res.usage.input_tokens, "output": res.usage.output_tokens}}
