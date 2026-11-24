"""Shared context for analysis modules.

Each module exposes:
    compute(ctx) -> dict           data for its dashboard (works without a research job)
    findings(ctx, data) -> list    FindingDraft objects with evidence (used by research jobs)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepterminal.data import sec_edgar as se

from ..models import Company, Filing, PriceQuote
from ..services import companies as cs
from ..services.evidence import EvidenceDraft, fact_evidence
from ..services.gateway import Meta


@dataclass
class Ctx:
    db: Session
    company: Company
    as_of: date | None = None
    job_id: str | None = None
    progress: Any = None            # callable(message) for live job events
    cache: dict = field(default_factory=dict)

    def log(self, msg: str) -> None:
        if self.progress:
            self.progress(msg)

    @cached_property
    def facts_meta(self) -> tuple[dict, Meta]:
        return cs.companyfacts(self.company)

    @property
    def facts(self) -> dict:
        return self.facts_meta[0]

    @property
    def meta(self) -> Meta:
        return self.facts_meta[1]

    def series(self, name: str) -> dict[date, se.Fact]:
        key = ("annual", name)
        if key not in self.cache:
            self.cache[key] = se.annual_series(self.facts, name, self.as_of, "latest")
        return self.cache[key]

    @cached_property
    def fiscal_ends(self) -> list[date]:
        return sorted(set(self.series("revenue")) & set(self.series("net_income")))

    def year(self, end: date) -> dict[str, float | None]:
        """All known fields for one fiscal year, in millions (shares in millions)."""
        out: dict[str, float | None] = {}
        for name in se.CONCEPTS:
            f = self.series(name).get(end)
            out[name] = f.value / 1e6 if f else None
        return out

    def ev(self, name: str, end: date, label: str | None = None) -> EvidenceDraft | None:
        f = self.series(name).get(end)
        if f is None:
            return None
        unit = "m shares" if se.CONCEPTS[name][1] == "shares" else "USD m"
        return fact_evidence(self.company, f, label or name.replace("_", " "), self.meta, unit=unit)

    def evs(self, pairs: list[tuple[str, date]]) -> list[EvidenceDraft]:
        return [e for e in (self.ev(n, d) for n, d in pairs) if e is not None]

    def filings(self, forms: tuple[str, ...]) -> list[Filing]:
        q = select(Filing).where(Filing.company_id == self.company.id, Filing.form.in_(forms)).order_by(Filing.filed.desc())
        if self.as_of:
            q = q.where(Filing.filed <= self.as_of)
        return list(self.db.scalars(q))

    @cached_property
    def price(self) -> PriceQuote | None:
        q = select(PriceQuote).where(PriceQuote.company_id == self.company.id).order_by(PriceQuote.as_of.desc())
        if self.as_of:
            q = q.where(PriceQuote.as_of <= self.as_of)
        return self.db.scalars(q).first()


def pct(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def money(x: float | None, d: int = 0) -> str:
    return "n/a" if x is None else f"${x:,.{d}f}m"


def clip(text: str, n: int) -> str:
    """Shorten to at most n characters at a word boundary, marking the cut with an ellipsis."""
    text = " ".join(text.split())
    if len(text) <= n:
        return text
    cut = text[:n - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"
