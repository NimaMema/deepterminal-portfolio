"""Valuation multiples, comparable-company valuation and historical-multiple context.

Every multiple returns a :class:`Multiple` with ``meaningful=False`` and a
reason instead of a misleading number (negative earnings, negative EBITDA,
negative book value...). Comparable-company valuation reports which peers
were excluded and why, and gives a range rather than a point.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Multiple:
    name: str
    value: float | None
    meaningful: bool
    reason: str = ""


def _ratio(name: str, num: float, den: float, den_label: str) -> Multiple:
    if den is None or num is None:
        return Multiple(name, None, False, "missing input")
    if den <= 0:
        return Multiple(name, None, False, f"{den_label} is not positive")
    if num <= 0:
        return Multiple(name, None, False, "numerator is not positive")
    return Multiple(name, num / den, True)


def price_to_earnings(market_cap: float, net_income: float) -> Multiple:
    return _ratio("P/E", market_cap, net_income, "earnings")


def forward_pe(share_price: float, forward_eps: float) -> Multiple:
    return _ratio("Forward P/E", share_price, forward_eps, "forward EPS")


def peg(pe: Multiple, eps_growth: float) -> Multiple:
    """P/E divided by growth in percentage points (e.g. 25x / 20 = 1.25)."""
    if not pe.meaningful:
        return Multiple("PEG", None, False, f"P/E not meaningful: {pe.reason}")
    if eps_growth <= 0:
        return Multiple("PEG", None, False, "growth is not positive")
    return Multiple("PEG", pe.value / (eps_growth * 100.0), True)


def ev_to_ebitda(ev: float, ebitda: float) -> Multiple:
    return _ratio("EV/EBITDA", ev, ebitda, "EBITDA")


def ev_to_revenue(ev: float, revenue: float) -> Multiple:
    return _ratio("EV/Revenue", ev, revenue, "revenue")


def price_to_book(market_cap: float, book_equity: float) -> Multiple:
    return _ratio("P/B", market_cap, book_equity, "book equity")


def fcf_yield(free_cash_flow: float, market_cap: float) -> Multiple:
    """Equity FCF yield. Negative FCF is reported (it is meaningful as a yield)."""
    if market_cap <= 0:
        return Multiple("FCF yield", None, False, "market cap is not positive")
    return Multiple("FCF yield", free_cash_flow / market_cap, True)


@dataclass(frozen=True)
class Peer:
    name: str
    multiple: float | None           # e.g. peer EV/EBITDA
    note: str = ""


@dataclass(frozen=True)
class ComparableValuation:
    metric_name: str
    subject_metric: float
    included: tuple[Peer, ...]
    excluded: tuple[tuple[str, str], ...]
    low_multiple: float
    median_multiple: float
    high_multiple: float
    implied_low: float
    implied_median: float
    implied_high: float
    warnings: tuple[str, ...] = field(default_factory=tuple)


def comparable_valuation(metric_name: str, subject_metric: float, peers: list[Peer],
                         min_peers: int = 3) -> ComparableValuation:
    """Apply the peer interquartile range of a multiple to the subject's metric.

    The implied values are in the multiple's numerator units (e.g. EV for
    EV/EBITDA); convert to equity with the bridge.
    """
    if subject_metric <= 0:
        raise ValueError(f"subject {metric_name} must be positive for a multiple-based value")
    inc = tuple(p for p in peers if p.multiple is not None and p.multiple > 0)
    exc = tuple((p.name, "multiple missing or not meaningful") for p in peers if p not in inc)
    if not inc:
        raise ValueError("no meaningful peer multiples")
    vals = sorted(p.multiple for p in inc)
    if len(vals) >= 4:
        q1, med, q3 = statistics.quantiles(vals, n=4, method="inclusive")
    else:
        q1, med, q3 = vals[0], statistics.median(vals), vals[-1]
    warns = []
    if len(inc) < min_peers:
        warns.append(f"only {len(inc)} meaningful peers; range is not robust")
    if q3 > 0 and q1 > 0 and q3 / q1 > 2.0:
        warns.append("peer multiples are widely dispersed; peers may not be comparable")
    return ComparableValuation(metric_name, subject_metric, inc, exc, q1, med, q3,
                               q1 * subject_metric, med * subject_metric, q3 * subject_metric,
                               tuple(warns))


@dataclass(frozen=True)
class HistoricalMultipleContext:
    current: float
    mean: float
    median: float
    stdev: float
    minimum: float
    maximum: float
    percentile: float          # share of history at or below current
    z_score: float
    observations: int


def historical_multiple_context(current: float, history: list[float]) -> HistoricalMultipleContext:
    """Where today's multiple sits in its own history.

    A high percentile is context, not a verdict: regimes (rates, business mix)
    change, so mean reversion is not assumed.
    """
    if len(history) < 2:
        raise ValueError("need at least two historical observations")
    sd = statistics.stdev(history)
    pct = sum(1 for h in history if h <= current) / len(history)
    mean = statistics.fmean(history)
    return HistoricalMultipleContext(current, mean, statistics.median(history), sd,
                                     min(history), max(history), pct,
                                     (current - mean) / sd if sd else 0.0, len(history))
