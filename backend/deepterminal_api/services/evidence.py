"""Evidence & findings persistence. The only path by which research results reach the database.

Rules enforced here:
* every Evidence row has a Source (publication + retrieval time) or is an explicit computation
  whose inputs are other evidence rows;
* excerpts quoted from filings are mechanically verified against the stored text
  (``verification_status = verified`` only if the quote is found);
* findings must cite at least one evidence row unless their severity is ``unavailable``
  (an explained data gap).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepterminal.data import sec_edgar as se

from ..models import Company, Evidence, Filing, FilingSection, Finding, Source
from .gateway import Meta


@dataclass
class SourceDraft:
    id: str
    kind: str
    title: str
    publisher: str
    url: str | None = None
    published_at: date | None = None
    retrieved_at: datetime | None = None
    period_end: date | None = None
    accession: str | None = None
    licence: str | None = None
    synthetic: bool = False


@dataclass
class EvidenceDraft:
    kind: str
    title: str
    epistemic_status: str
    source: SourceDraft | None = None
    excerpt: str | None = None
    locator: str | None = None
    value: float | None = None
    unit: str | None = None
    period_end: date | None = None
    verification_status: str = "unverified"
    limitations: str | None = None
    data: dict = field(default_factory=dict)


@dataclass
class FindingDraft:
    module: str
    title: str
    summary: str
    severity: str = "neutral"            # positive | neutral | watch | concern | unavailable
    epistemic_status: str = "analytical_inference"
    confidence: str = "medium"
    evidence: list[EvidenceDraft | int] = field(default_factory=list)
    limitations: str | None = None
    data: dict = field(default_factory=dict)


SEC_PUBLISHER = "U.S. Securities and Exchange Commission — EDGAR"
SYNTHETIC_LICENCE = "synthetic demo data (not a real filing; no source to open)"


def filing_source(company: Company, accession: str, form: str, filed: date, url: str | None,
                  retrieved_at: datetime | None, period_end: date | None = None) -> SourceDraft:
    return SourceDraft(f"SEC:{accession}", "sec_filing", f"{company.name} {form} (accession {accession})",
                       "SYNTHETIC demo dataset in SEC format" if company.synthetic else SEC_PUBLISHER,
                       None if company.synthetic else url or se.filing_url(company.cik, accession),
                       filed, retrieved_at, period_end, accession,
                       SYNTHETIC_LICENCE if company.synthetic else "US government public data", company.synthetic)


def fact_evidence(company: Company, fact: se.Fact, label: str, meta: Meta, scale: float = 1e6,
                  unit: str = "USD m") -> EvidenceDraft:
    src = filing_source(company, fact.accession, fact.form, fact.filed, None, meta.retrieved_at, fact.end)
    period = f"{fact.start}–{fact.end}" if fact.start else f"at {fact.end}"
    return EvidenceDraft("financial_fact", f"{label} {period}: {fact.value / scale:,.2f} {unit}", "historical_fact",
                         src, locator=f"us-gaap:{fact.concept} {period}", value=fact.value / scale, unit=unit,
                         period_end=fact.end, verification_status="verified",
                         limitations="Machine-readable XBRL value as filed; verified against the companyfacts record.",
                         data={"concept": fact.concept, "form": fact.form, "filed": fact.filed.isoformat()})


def excerpt_evidence(db: Session, company: Company, filing: Filing, key: str, excerpt: str,
                     epistemic: str = "company_statement", title: str | None = None) -> EvidenceDraft:
    sec = db.scalar(select(FilingSection).where(FilingSection.filing_id == filing.id, FilingSection.key == key))
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    found = bool(sec) and norm(excerpt) in norm(sec.text)
    offset = norm(sec.text).find(norm(excerpt)) if found else -1
    return EvidenceDraft("excerpt", title or f"{filing.form} {filing.filed} — {key.replace('_', ' ').title()}",
                         epistemic, filing_source(company, filing.accession, filing.form, filing.filed, filing.url,
                                                  filing.text_retrieved_at, filing.report_date),
                         excerpt=excerpt[:2000], locator=f"{filing.accession}#{key}@{offset}",
                         verification_status="verified" if found else "failed",
                         limitations="Company statement quoted from its filing; a statement is not independent confirmation."
                         if epistemic == "company_statement" else None,
                         data={"filing_id": filing.id, "section": key, "offset": offset})


def computed_evidence(title: str, value: float | None, formula: str, inputs: list[int], unit: str | None = None,
                      limitations: str | None = None, data: dict | None = None) -> EvidenceDraft:
    return EvidenceDraft("computed", title, "analytical_inference",
                         SourceDraft("COMPUTATION:deepterminal", "computation", "DEEPTERMINAL deterministic calculation",
                                     "DEEPTERMINAL (open-source calculation, tested)"),
                         value=value, unit=unit, locator=formula, verification_status="not_applicable",
                         limitations=limitations, data={"formula": formula, "inputs": inputs, **(data or {})})


def _upsert_source(db: Session, s: SourceDraft) -> str:
    row = db.get(Source, s.id)
    if row is None:
        db.add(Source(id=s.id, kind=s.kind, title=s.title, publisher=s.publisher, url=s.url,
                      published_at=s.published_at, retrieved_at=s.retrieved_at, period_end=s.period_end,
                      accession=s.accession, licence=s.licence, synthetic=s.synthetic))
        db.flush()
    elif s.retrieved_at and (row.retrieved_at is None or s.retrieved_at > row.retrieved_at):
        row.retrieved_at = s.retrieved_at
    return s.id


def save_evidence(db: Session, company: Company | None, e: EvidenceDraft, job_id: str | None, created_by: str) -> int:
    sid = _upsert_source(db, e.source) if e.source else None
    row = Evidence(company_id=company.id if company else None, source_id=sid, job_id=job_id, kind=e.kind,
                   title=e.title[:2000], excerpt=e.excerpt, locator=e.locator, value=e.value, unit=e.unit,
                   period_end=e.period_end, epistemic_status=e.epistemic_status,
                   verification_status=e.verification_status, limitations=e.limitations, data=e.data,
                   created_by=created_by)
    db.add(row)
    db.flush()
    return row.id


def save_finding(db: Session, company: Company, f: FindingDraft, job_id: str | None, generated_by: str = "rules") -> Finding:
    ids = []
    for e in f.evidence:
        ids.append(e if isinstance(e, int) else save_evidence(db, company, e, job_id, generated_by))
    if not ids and f.severity != "unavailable":
        raise ValueError(f"finding {f.title!r} cites no evidence")
    row = Finding(job_id=job_id, company_id=company.id, module=f.module, title=f.title, summary=f.summary,
                  epistemic_status=f.epistemic_status, severity=f.severity, confidence=f.confidence,
                  evidence_ids=ids, limitations=f.limitations, data=f.data, generated_by=generated_by)
    db.add(row)
    db.flush()
    return row


def unavailable(module: str, title: str, reason: str, hint: str = "") -> FindingDraft:
    return FindingDraft(module, title, reason + (f" {hint}" if hint else ""), severity="unavailable",
                        epistemic_status="unverified_claim", confidence="low",
                        limitations="Data unavailable — no conclusion drawn.")


def evidence_dict(e: Evidence) -> dict[str, Any]:
    s = e.source
    return {"id": e.id, "kind": e.kind, "title": e.title, "excerpt": e.excerpt, "locator": e.locator,
            "value": e.value, "unit": e.unit, "period_end": e.period_end.isoformat() if e.period_end else None,
            "epistemic_status": e.epistemic_status, "verification_status": e.verification_status,
            "limitations": e.limitations, "data": e.data, "created_by": e.created_by,
            "created_at": e.created_at.isoformat(),
            "source": None if s is None else {
                "id": s.id, "kind": s.kind, "title": s.title, "publisher": s.publisher, "url": s.url,
                "published_at": s.published_at.isoformat() if s.published_at else None,
                "retrieved_at": s.retrieved_at.isoformat() if s.retrieved_at else None,
                "period_end": s.period_end.isoformat() if s.period_end else None,
                "accession": s.accession, "licence": s.licence, "synthetic": s.synthetic}}


def finding_dict(f: Finding) -> dict[str, Any]:
    return {"id": f.id, "job_id": f.job_id, "module": f.module, "title": f.title, "summary": f.summary,
            "epistemic_status": f.epistemic_status, "severity": f.severity, "confidence": f.confidence,
            "evidence_ids": f.evidence_ids, "limitations": f.limitations, "data": f.data,
            "generated_by": f.generated_by, "created_at": f.created_at.isoformat()}
