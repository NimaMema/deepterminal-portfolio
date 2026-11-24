"""Market Expectations vs. Fundamental Value (spec §12) and the Expectations Gap.

Implements the 13-step misvaluation investigation. Steps that need research
evidence (overlooked information, counterarguments, catalysts, why the market
may already understand the discrepancy) are filled from supplied
:class:`ResearchFinding` objects; if none are supplied the step is recorded
as *not performed* rather than invented, and the verdict says so.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from ..evidence import DataQuality, SourcedValue
from .reverse_dcf import ReverseDCFResult
from .scenarios import ScenarioSetResult


class Verdict(str, Enum):
    POTENTIALLY_UNDERVALUED = "Potentially undervalued under specified assumptions"
    APPROXIMATELY_FAIR = "Approximately fairly valued under specified assumptions"
    POTENTIALLY_OVERVALUED = "Potentially overvalued under specified assumptions"
    TOO_UNCERTAIN = "Too uncertain to assess reliably"


@dataclass(frozen=True)
class OperatingHistory:
    """Company's own record, used to judge whether implied expectations are unusual."""

    revenue_growth: tuple[float, ...]
    operating_margin: tuple[float, ...]


@dataclass(frozen=True)
class PeerOperating:
    name: str
    revenue_growth: float
    operating_margin: float
    source_ref: str = ""


@dataclass(frozen=True)
class GapItem:
    metric: str
    market_implied: float
    company_median: float | None
    company_max: float | None
    peer_median: float | None
    peer_max: float | None
    analyst_consensus: float | None
    observations: tuple[str, ...]


def expectations_gap(implied_revenue_cagr: float | None, implied_margin: float | None,
                     history: OperatingHistory, peers: list[PeerOperating],
                     consensus: dict[str, float] | None = None) -> list[GapItem]:
    """Compare market-implied operating outcomes with history, peers and consensus.

    Observations are analytical inferences; they describe how demanding an
    expectation is, not whether it will be met.
    """
    items = []
    consensus = consensus or {}
    specs = [("revenue CAGR", implied_revenue_cagr, history.revenue_growth,
              [p.revenue_growth for p in peers], consensus.get("revenue_cagr")),
             ("operating margin", implied_margin, history.operating_margin,
              [p.operating_margin for p in peers], consensus.get("operating_margin"))]
    for metric, implied, own, peer_vals, cons in specs:
        if implied is None:
            continue
        obs = []
        c_med = statistics.median(own) if own else None
        c_max = max(own) if own else None
        p_med = statistics.median(peer_vals) if peer_vals else None
        p_max = max(peer_vals) if peer_vals else None
        if c_max is not None and implied > c_max:
            obs.append(f"implied {metric} {implied:.1%} exceeds the company's best recorded {c_max:.1%}")
        elif c_med is not None and implied < c_med:
            obs.append(f"implied {metric} {implied:.1%} is below the company's historical median {c_med:.1%}")
        if p_max is not None and implied > p_max:
            obs.append(f"implied {metric} exceeds every listed peer (peer max {p_max:.1%})")
        if cons is not None:
            obs.append(f"market-implied {metric} is {implied - cons:+.1%} pts versus analyst consensus {cons:.1%}")
        if not own:
            obs.append("no company history supplied for comparison")
        items.append(GapItem(metric, implied, c_med, c_max, p_med, p_max, cons, tuple(obs)))
    return items


@dataclass(frozen=True)
class ResearchFinding:
    step: str            # "overlooked" | "counterargument" | "catalyst" | "market_may_know"
    text: str
    source_refs: tuple[str, ...]
    status: str = "analytical_inference"


@dataclass(frozen=True)
class InvestigationStep:
    number: int
    title: str
    performed: bool
    detail: str


@dataclass(frozen=True)
class MisvaluationAssessment:
    verdict: Verdict
    price: float
    price_as_of: date | None
    base_value: float
    bear_value: float
    bull_value: float
    margin_of_safety: float
    price_position: str
    upside_to_base: float
    downside_to_bear: float
    steps: tuple[InvestigationStep, ...]
    reasons: tuple[str, ...]
    assumptions: tuple[str, ...]
    caveat: str = ("A valuation discrepancy does not establish that the market is wrong; "
                   "the market may hold information or risk views not captured here.")
    findings: tuple[ResearchFinding, ...] = field(default_factory=tuple)


STEP_TITLES = (
    "Obtain a timestamped share price",
    "Calculate market capitalisation and enterprise value",
    "Normalise relevant financial data",
    "Estimate a range of fundamental values",
    "Calculate market-implied expectations",
    "Compare expectations with historical performance",
    "Compare with peer-company performance",
    "Evaluate competitive and operational constraints",
    "Identify potentially overlooked information",
    "Examine counterarguments",
    "Identify potential catalysts",
    "Explain why the market may already understand the discrepancy",
    "Assess model uncertainty and evidence quality",
)


def assess_misvaluation(price: SourcedValue, scenarios: ScenarioSetResult,
                        reverse: list[ReverseDCFResult], gap: list[GapItem],
                        evidence_quality: DataQuality, analysis_date: date,
                        normalisation_note: str = "",
                        constraints_note: str = "",
                        findings: list[ResearchFinding] | None = None,
                        margin_of_safety: float = 0.20,
                        max_relative_spread: float = 1.5,
                        max_price_age_days: int = 7) -> MisvaluationAssessment:
    """Qualified verdict from scenario values, reverse DCF and evidence quality.

    Decision rule (explicit, configurable):

    * TOO_UNCERTAIN if evidence quality is LOW, the price has no as-of date
      or is stale, or (bull − bear) / base exceeds ``max_relative_spread``;
    * POTENTIALLY_UNDERVALUED if price < base × (1 − margin_of_safety);
    * POTENTIALLY_OVERVALUED if price > base × (1 + margin_of_safety);
    * otherwise APPROXIMATELY_FAIR.
    """
    findings = findings or []
    p = float(price.value)
    bear = scenarios.by_name("bear").per_share
    base = scenarios.by_name("base").per_share
    bull = scenarios.by_name("bull").per_share
    reasons: list[str] = []

    price_ok = price.as_of is not None and (analysis_date - price.as_of).days <= max_price_age_days
    spread = (bull - bear) / base if base > 0 else float("inf")

    if evidence_quality is DataQuality.LOW:
        reasons.append("evidence quality is LOW")
    if not price_ok:
        reasons.append("share price lacks an as-of date or is older than "
                       f"{max_price_age_days} days at {analysis_date}")
    if base > 0 and spread > max_relative_spread:
        reasons.append(f"scenario spread (bull − bear)/base = {spread:.0%} exceeds "
                       f"{max_relative_spread:.0%}")
    if base <= 0:
        reasons.append("base-case equity value is not positive")

    if reasons:
        verdict = Verdict.TOO_UNCERTAIN
    elif p < base * (1 - margin_of_safety):
        verdict = Verdict.POTENTIALLY_UNDERVALUED
        reasons.append(f"price {p:,.2f} is more than {margin_of_safety:.0%} below base value {base:,.2f}")
    elif p > base * (1 + margin_of_safety):
        verdict = Verdict.POTENTIALLY_OVERVALUED
        reasons.append(f"price {p:,.2f} is more than {margin_of_safety:.0%} above base value {base:,.2f}")
    else:
        verdict = Verdict.APPROXIMATELY_FAIR
        reasons.append(f"price {p:,.2f} is within ±{margin_of_safety:.0%} of base value {base:,.2f}")

    if p < bear:
        position = "below the bear-case value"
    elif p > bull:
        position = "above the bull-case value"
    elif p <= base:
        position = "between bear and base values"
    else:
        position = "between base and bull values"

    by_step = {k: [f for f in findings if f.step == k]
               for k in ("overlooked", "counterargument", "catalyst", "market_may_know")}

    def research_step(n: int, key: str) -> InvestigationStep:
        fs = by_step[key]
        if not fs:
            return InvestigationStep(n, STEP_TITLES[n - 1], False,
                                     "not performed: no sourced research findings supplied")
        return InvestigationStep(n, STEP_TITLES[n - 1], True,
                                 " | ".join(f"{f.text} [{', '.join(f.source_refs)}]" for f in fs))

    rev_detail = "; ".join(r.statement() for r in reverse) or "not performed"
    gap_obs = [o for g in gap for o in g.observations]
    steps = (
        InvestigationStep(1, STEP_TITLES[0], price.as_of is not None,
                          f"{p:,.2f} as of {price.as_of}" if price.as_of else "no as-of date"),
        InvestigationStep(2, STEP_TITLES[1], bool(reverse),
                          (f"market equity {reverse[0].target_equity_value:,.0f}; "
                           f"market EV {reverse[0].target_enterprise_value:,.0f}") if reverse else "not performed"),
        InvestigationStep(3, STEP_TITLES[2], bool(normalisation_note), normalisation_note or "not performed"),
        InvestigationStep(4, STEP_TITLES[3], True,
                          f"bear {bear:,.2f} / base {base:,.2f} / bull {bull:,.2f} per share"),
        InvestigationStep(5, STEP_TITLES[4], bool(reverse), rev_detail),
        InvestigationStep(6, STEP_TITLES[5], any(g.company_median is not None for g in gap),
                          "; ".join(gap_obs) or "not performed"),
        InvestigationStep(7, STEP_TITLES[6], any(g.peer_median is not None for g in gap),
                          "; ".join(f"{g.metric}: peer median {g.peer_median:.1%}" for g in gap
                                    if g.peer_median is not None) or "not performed: no peer data"),
        InvestigationStep(8, STEP_TITLES[7], bool(constraints_note), constraints_note or
                          "not performed: competitive/supply-chain modules not run"),
        research_step(9, "overlooked"),
        research_step(10, "counterargument"),
        research_step(11, "catalyst"),
        research_step(12, "market_may_know"),
        InvestigationStep(13, STEP_TITLES[12], True,
                          f"evidence quality {evidence_quality.value}; scenario spread "
                          + (f"{spread:.0%}" if base > 0 else "undefined (base value not positive)")),
    )
    if verdict is not Verdict.TOO_UNCERTAIN and not by_step["market_may_know"]:
        reasons.append("why the market might already understand the gap has not been researched; "
                       "treat the verdict as provisional")
    assumptions = tuple(f"{o.scenario.name}: {o.scenario.narrative}" for o in scenarios.outcomes)
    return MisvaluationAssessment(
        verdict, p, price.as_of, base, bear, bull, margin_of_safety, position,
        base / p - 1, bear / p - 1, steps, tuple(reasons), assumptions, findings=tuple(findings))
