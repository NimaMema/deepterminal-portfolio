"""Load a research *case file* (JSON) into typed objects.

A case file is the auditable input to an analysis: market price with its
as-of date, capital structure, financial history, scenario assumptions and
the sources and rationales behind each of them. See
fixtures/synthetic_widget_corp.json for a complete, clearly labelled
synthetic example and docs/DATA_MODEL.md for the schema.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..evidence import DataQuality, EpistemicStatus, Source, SourcedValue
from ..financials.statements import FinancialPeriod
from ..valuation.bridge import CapitalStructure, OptionTranche
from ..valuation.dcf import DCFInputs, ExplicitReinvestment, SalesToCapital
from ..valuation.expectations import PeerOperating, ResearchFinding
from ..valuation.multiples import Peer
from ..valuation.scenarios import Scenario
from ..valuation.selection import CompanyProfile


@dataclass
class Case:
    case_id: str
    company_name: str
    ticker: str
    currency: str
    units: str
    analysis_date: date
    synthetic: bool
    disclaimer: str
    sources: dict[str, Source]
    share_price: SourcedValue
    capital: CapitalStructure
    capital_source_refs: tuple[str, ...]
    history: list[FinancialPeriod]
    profile: CompanyProfile
    scenarios: list[Scenario]
    assumptions: list[SourcedValue]
    peers_ev_ebitda: list[Peer]
    peers_operating: list[PeerOperating]
    multiple_history: dict[str, list[float]]
    tam_final_year: SourcedValue | None
    consensus: dict[str, float] | None
    evidence_quality: DataQuality
    findings: list[ResearchFinding] = field(default_factory=list)
    normalisation_note: str = ""
    constraints_note: str = ""
    probability_calibration_basis: str | None = None
    # Real-data extensions (populated by data/sec_case.py)
    ttm: FinancialPeriod | None = None
    figure_provenance: list = field(default_factory=list)   # FigureProvenance for non-period figures
    data_validation: Any = None                              # validation.ValidationReport
    identity: Any = None                                     # sec_edgar.CompanyIdentity
    notes: list = field(default_factory=list)

    @property
    def latest_period(self) -> FinancialPeriod:
        """Most recent full-year-equivalent period: TTM when available, else last fiscal year."""
        if self.ttm is not None and self.ttm.period_end > self.history[-1].period_end:
            return self.ttm
        return self.history[-1]

    @property
    def latest_label(self) -> str:
        p = self.latest_period
        return f"TTM to {p.period_end}" if p.period_type == "TTM" else f"FY{p.fiscal_year}"

    @property
    def base_inputs(self) -> DCFInputs:
        return next(s.inputs for s in self.scenarios if s.name == "base")

    def all_evidence(self) -> list[SourcedValue]:
        """Every value that feeds the analysis, for citation auditing."""
        out = ([self.share_price] if self.share_price is not None else []) + list(self.assumptions)
        for p in self.history + ([self.ttm] if self.ttm else []):
            src = self.sources.get(p.source_ref)
            label = f"FY{p.fiscal_year}" if p.period_type == "FY" else f"{p.period_type} to {p.period_end}"
            out.append(SourcedValue(f"{label} financial statements", p.revenue,
                                    EpistemicStatus.HISTORICAL_FACT, as_of=p.period_end,
                                    sources=(src,) if src else ()))
        refs = tuple(self.sources[r] for r in self.capital_source_refs if r in self.sources)
        out.append(SourcedValue("capital structure", self.capital.basic_shares,
                                EpistemicStatus.HISTORICAL_FACT, sources=refs))
        if self.tam_final_year:
            out.append(self.tam_final_year)
        return out


def _date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _source(d: dict[str, Any]) -> Source:
    return Source(
        source_id=d["source_id"], title=d["title"], publisher=d["publisher"], url=d.get("url"),
        published_at=_date(d.get("published_at")),
        retrieved_at=datetime.fromisoformat(d["retrieved_at"]) if d.get("retrieved_at") else None,
        period_end=_date(d.get("period_end")), accession=d.get("accession"),
        licence=d.get("licence"), synthetic=bool(d.get("synthetic", False)))


def _tuple(v: Any) -> Any:
    return tuple(v) if isinstance(v, list) else v


def _dcf_inputs(d: dict[str, Any], base_revenue: float) -> DCFInputs:
    if "sales_to_capital" in d:
        reinv = SalesToCapital(_tuple(d["sales_to_capital"]))
    else:
        reinv = ExplicitReinvestment(_tuple(d["net_capex_pct_revenue"]),
                                     _tuple(d["nwc_pct_revenue_change"]))
    return DCFInputs(
        base_revenue=base_revenue, revenue_growth=tuple(d["revenue_growth"]),
        ebit_margin=tuple(d["ebit_margin"]), tax_rate=_tuple(d["tax_rate"]),
        discount_rate=d["discount_rate"], terminal_growth=d["terminal_growth"],
        terminal_roic=d["terminal_roic"], reinvestment=reinv,
        terminal_ebit_margin=d.get("terminal_ebit_margin"),
        mid_year=bool(d.get("mid_year", False)))


def _sourced(name: str, d: dict[str, Any], sources: dict[str, Source], default_status: str) -> SourcedValue:
    refs = tuple(sources[r] for r in d.get("source_refs", []) if r in sources)
    return SourcedValue(name, d["value"], EpistemicStatus(d.get("status", default_status)),
                        unit=d.get("unit", ""), as_of=_date(d.get("as_of")), sources=refs,
                        rationale=d.get("rationale", ""),
                        quality=DataQuality(d.get("quality", "medium")))


def load_case(path: str | Path) -> Case:
    raw = json.loads(Path(path).read_text())
    return parse_case(raw)


def parse_case(raw: dict[str, Any]) -> Case:
    meta = raw["meta"]
    sources = {s["source_id"]: _source(s) for s in raw.get("sources", [])}
    history = [FinancialPeriod(
        **{k: (_date(v) if k in ("period_end", "filed") else v)
           for k, v in h.items()}) for h in raw["history"]]
    history.sort(key=lambda p: p.fiscal_year)
    base_revenue = history[-1].revenue

    cs = dict(raw["capital_structure"])
    cap_refs = tuple(cs.pop("source_refs", []))
    cs["options"] = tuple(OptionTranche(**o) for o in cs.get("options", []))
    capital = CapitalStructure(**cs)

    scenarios = []
    for name, sd in raw["scenarios"].items():
        scenarios.append(Scenario(
            name=name, narrative=sd["narrative"], inputs=_dcf_inputs(sd, base_revenue),
            key_dependencies=tuple(sd.get("key_dependencies", [])),
            source_refs=tuple(sd.get("source_refs", [])), probability=sd.get("probability")))

    assumptions = [_sourced(k, v, sources, "model_assumption")
                   for k, v in raw.get("assumptions", {}).items()]
    peers = raw.get("peers", [])
    tam = raw.get("tam_final_year")
    return Case(
        case_id=meta["case_id"], company_name=meta["company_name"], ticker=meta["ticker"],
        currency=meta.get("currency", "USD"), units=meta.get("units", "millions"),
        analysis_date=date.fromisoformat(meta["analysis_date"]),
        synthetic=bool(meta.get("synthetic", False)), disclaimer=meta.get("disclaimer", ""),
        sources=sources,
        share_price=_sourced("share price", raw["market"]["share_price"], sources, "historical_fact"),
        capital=capital, capital_source_refs=cap_refs, history=history,
        profile=CompanyProfile(**raw.get("profile", {})), scenarios=scenarios,
        assumptions=assumptions,
        peers_ev_ebitda=[Peer(p["name"], p.get("ev_ebitda"), p.get("source_ref", "")) for p in peers],
        peers_operating=[PeerOperating(p["name"], p["revenue_growth"], p["operating_margin"],
                                       p.get("source_ref", ""))
                         for p in peers if "revenue_growth" in p and "operating_margin" in p],
        multiple_history={k: list(v) for k, v in raw.get("multiple_history", {}).items()},
        tam_final_year=_sourced("addressable market (final forecast year)", tam, sources, "estimate")
        if tam else None,
        consensus=raw.get("consensus"),
        evidence_quality=DataQuality(raw.get("evidence_quality", "medium")),
        findings=[ResearchFinding(f["step"], f["text"], tuple(f.get("source_refs", [])),
                                  f.get("status", "analytical_inference"))
                  for f in raw.get("research_findings", [])],
        normalisation_note=raw.get("normalisation_note", ""),
        constraints_note=raw.get("constraints_note", ""),
        probability_calibration_basis=raw.get("probability_calibration_basis"))
