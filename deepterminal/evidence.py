"""Evidence model: every number DEEPTERMINAL uses carries its provenance.

The research-quality rules (spec §15) are enforced here rather than left to
convention:

* every value is classified by epistemic status (fact, company statement,
  estimate, model assumption, ...);
* every value records when it became public and when we retrieved it;
* historical analyses can be run "as of" a decision date, and any evidence
  published after that date is rejected (look-ahead guard);
* stale data is detectable;
* values that drive a valuation without a source or a stated rationale are
  surfaced by :func:`citation_audit` instead of silently accepted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Iterable


class EpistemicStatus(str, Enum):
    """What kind of claim a value is. Never collapse these categories."""

    HISTORICAL_FACT = "historical_fact"            # e.g. audited 10-K figure
    COMPANY_STATEMENT = "company_statement"        # management claim / guidance
    CORROBORATED_FACT = "corroborated_fact"        # confirmed by an independent source
    ESTIMATE = "estimate"                          # third-party or analyst estimate
    MODEL_ASSUMPTION = "model_assumption"          # chosen by the analyst/model
    ANALYTICAL_INFERENCE = "analytical_inference"  # derived conclusion
    SPECULATIVE_SCENARIO = "speculative_scenario"  # what-if, not a forecast
    UNVERIFIED_CLAIM = "unverified_claim"          # reported but not checked


class DataQuality(str, Enum):
    HIGH = "high"        # primary source, audited, recent
    MEDIUM = "medium"    # reputable secondary source or partially verified
    LOW = "low"          # sparse, stale, unverified or synthetic


class LookAheadError(ValueError):
    """Raised when evidence published after the decision date is used."""


@dataclass(frozen=True)
class Source:
    """A citable origin of evidence.

    ``published_at`` is when the information became public (e.g. SEC filing
    date), which is distinct from ``period_end`` (the period it describes)
    and ``retrieved_at`` (when DEEPTERMINAL fetched it).
    """

    source_id: str
    title: str
    publisher: str
    url: str | None = None
    published_at: date | None = None
    retrieved_at: datetime | None = None
    period_end: date | None = None
    accession: str | None = None   # SEC accession number where applicable
    licence: str | None = None     # usage terms, see docs/DATA_SOURCES.md
    synthetic: bool = False        # True for labelled test fixtures

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "publisher": self.publisher,
            "url": self.url,
            "published_at": _iso(self.published_at),
            "retrieved_at": _iso(self.retrieved_at),
            "period_end": _iso(self.period_end),
            "accession": self.accession,
            "licence": self.licence,
            "synthetic": self.synthetic,
        }


@dataclass(frozen=True)
class SourcedValue:
    """A value together with its provenance and epistemic status."""

    name: str
    value: Any
    status: EpistemicStatus
    unit: str = ""
    as_of: date | None = None
    sources: tuple[Source, ...] = ()
    rationale: str = ""            # required for assumptions without sources
    quality: DataQuality = DataQuality.MEDIUM

    @property
    def published_at(self) -> date | None:
        """Latest publication date among the sources (when the value was knowable)."""
        dates = [s.published_at for s in self.sources if s.published_at]
        return max(dates) if dates else None

    @property
    def is_synthetic(self) -> bool:
        return any(s.synthetic for s in self.sources)

    def knowable_on(self, decision_date: date) -> bool:
        pub = self.published_at
        return pub is None or pub <= decision_date

    def is_stale(self, reference: date, max_age_days: int) -> bool:
        anchor = self.as_of or self.published_at
        return anchor is not None and (reference - anchor).days > max_age_days

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "status": self.status.value,
            "as_of": _iso(self.as_of),
            "quality": self.quality.value,
            "rationale": self.rationale,
            "sources": [s.to_dict() for s in self.sources],
        }


@dataclass(frozen=True)
class FigureProvenance:
    """Where one reported financial figure came from.

    ``derivation`` is empty for figures taken directly from a filing, or
    describes the arithmetic (e.g. "FY − 9M YTD") with every input listed in
    ``inputs`` so derived figures stay fully traceable.
    """

    field: str
    value: float
    unit: str
    concept: str
    period_start: date | None
    period_end: date
    form: str
    accession: str
    filed: date
    source_url: str
    retrieved_at: datetime | None
    derivation: str = ""
    inputs: tuple["FigureProvenance", ...] = ()

    def describe(self) -> str:
        period = f"{self.period_start}–{self.period_end}" if self.period_start else f"at {self.period_end}"
        base = (f"{self.concept} {period}, {self.form} accession {self.accession} filed {self.filed}"
                if not self.derivation else f"derived ({self.derivation}) from "
                + "; ".join(i.describe() for i in self.inputs))
        return base

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field, "value": self.value, "unit": self.unit, "concept": self.concept,
            "period_start": _iso(self.period_start), "period_end": _iso(self.period_end),
            "form": self.form, "accession": self.accession, "filed": _iso(self.filed),
            "source_url": self.source_url, "retrieved_at": _iso(self.retrieved_at),
            "derivation": self.derivation, "inputs": [i.to_dict() for i in self.inputs],
        }


def assumption(name: str, value: Any, rationale: str, unit: str = "") -> SourcedValue:
    """Shorthand for an explicit model assumption; a rationale is mandatory."""
    if not rationale.strip():
        raise ValueError(f"assumption {name!r} needs a rationale")
    return SourcedValue(name, value, EpistemicStatus.MODEL_ASSUMPTION, unit=unit,
                        rationale=rationale)


def enforce_point_in_time(values: Iterable[SourcedValue], decision_date: date) -> None:
    """Reject any evidence that was not public on ``decision_date``."""
    late = [v for v in values if not v.knowable_on(decision_date)]
    if late:
        names = ", ".join(f"{v.name} (published {v.published_at})" for v in late)
        raise LookAheadError(f"evidence not available on {decision_date}: {names}")


@dataclass
class CitationFinding:
    name: str
    problem: str


@dataclass
class CitationAudit:
    checked: int = 0
    findings: list[CitationFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.findings


def citation_audit(values: Iterable[SourcedValue], reference: date | None = None,
                   max_age_days: int = 548) -> CitationAudit:
    """Check every value has support appropriate to its epistemic status.

    * facts, statements and estimates need at least one source;
    * assumptions, inferences and scenarios need a rationale (or a source);
    * unverified claims are always reported, since they must not drive a
      conclusion silently;
    * synthetic sources are always reported so fixtures are never mistaken
      for real evidence;
    * values older than ``max_age_days`` relative to ``reference`` are stale.
    """
    audit = CitationAudit()
    needs_source = {EpistemicStatus.HISTORICAL_FACT, EpistemicStatus.COMPANY_STATEMENT,
                    EpistemicStatus.CORROBORATED_FACT, EpistemicStatus.ESTIMATE}
    for v in values:
        audit.checked += 1
        if v.status in needs_source and not v.sources:
            audit.findings.append(CitationFinding(v.name, f"{v.status.value} has no source"))
        elif v.status not in needs_source and not (v.sources or v.rationale.strip()):
            audit.findings.append(CitationFinding(v.name, f"{v.status.value} has no rationale"))
        if v.status is EpistemicStatus.CORROBORATED_FACT and len(v.sources) < 2:
            audit.findings.append(CitationFinding(
                v.name, "corroborated_fact needs two or more independent sources"))
        if v.status is EpistemicStatus.UNVERIFIED_CLAIM:
            audit.findings.append(CitationFinding(v.name, "unverified claim"))
        if v.is_synthetic:
            audit.findings.append(CitationFinding(v.name, "synthetic fixture data"))
        if reference and v.is_stale(reference, max_age_days):
            audit.findings.append(CitationFinding(
                v.name, f"stale: older than {max_age_days} days at {reference}"))
    return audit


def _iso(d: date | datetime | None) -> str | None:
    return d.isoformat() if d else None
