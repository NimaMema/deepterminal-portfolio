"""Earnings normalisation and reinvestment decomposition.

These adjustments feed the DCF's margin and reinvestment assumptions. Each
returns its working so the user can audit it, and none is applied twice:
the DCF consumes a *margin* and a *reinvestment* assumption, so normalised
EBIT should inform the margin, and maintenance/growth capex should inform
the reinvestment, never both on top of each other.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field


@dataclass(frozen=True)
class NonRecurringItem:
    year: int
    description: str
    amount: float        # positive = gain included in EBIT, negative = charge


@dataclass(frozen=True)
class AdjustedEBIT:
    reported: float
    adjustments: tuple[NonRecurringItem, ...]
    adjusted: float
    warnings: tuple[str, ...] = field(default_factory=tuple)


def remove_nonrecurring(reported_ebit: float, year: int, items: list[NonRecurringItem],
                        history: list[NonRecurringItem] | None = None,
                        recurrence_threshold: int = 3) -> AdjustedEBIT:
    """Strip one-off gains/charges from ``year``'s EBIT.

    "Non-recurring" charges that appear in ``recurrence_threshold`` or more
    distinct years of ``history`` are flagged: recurring restructuring is an
    operating cost, and excluding it inflates normalised margins.
    """
    this_year = [i for i in items if i.year == year]
    adjusted = reported_ebit - sum(i.amount for i in this_year)
    warns = []
    hist = history or []
    charge_years = {i.year for i in hist if i.amount < 0}
    if this_year and len(charge_years) >= recurrence_threshold:
        warns.append(f"'non-recurring' charges occurred in {len(charge_years)} years; "
                     "treat them as recurring operating costs")
    return AdjustedEBIT(reported_ebit, tuple(this_year), adjusted, tuple(warns))


@dataclass(frozen=True)
class NormalisedMargin:
    margins: tuple[float, ...]
    method: str
    normalised_margin: float
    current_margin: float
    current_vs_normal: float     # current / normalised - 1
    warnings: tuple[str, ...] = field(default_factory=tuple)


def normalised_margin(revenues: list[float], ebits: list[float], method: str = "median") -> NormalisedMargin:
    """Through-the-cycle margin. Supply a full cycle (trough and peak years).

    Methods: ``median`` or ``mean`` of annual margins, or ``aggregate``
    (Σ EBIT / Σ revenue, which weights large years more).
    """
    if len(revenues) != len(ebits) or len(revenues) < 3:
        raise ValueError("need at least three matching years")
    margins = tuple(e / r for e, r in zip(ebits, revenues))
    if method == "median":
        norm = statistics.median(margins)
    elif method == "mean":
        norm = statistics.fmean(margins)
    elif method == "aggregate":
        norm = sum(ebits) / sum(revenues)
    else:
        raise ValueError(f"unknown method {method}")
    cur = margins[-1]
    warns = []
    if norm > 0 and cur / norm - 1 > 0.30:
        warns.append(f"current margin {cur:.1%} is {cur / norm - 1:.0%} above the through-cycle "
                     f"{method} {norm:.1%}: earnings may be cyclically inflated")
    if len(margins) < 7:
        warns.append(f"only {len(margins)} years; may not span a full cycle")
    return NormalisedMargin(margins, method, norm, cur,
                            cur / norm - 1 if norm else float("nan"), tuple(warns))


@dataclass(frozen=True)
class CapexSplit:
    total_capex: float
    growth_capex: float
    maintenance_capex: float
    capital_intensity: float     # average PP&E / revenue
    depreciation: float | None
    method: str


def maintenance_capex_greenwald(capex: float, revenue_change: float, ppe: list[float],
                                revenues: list[float], depreciation: float | None = None) -> CapexSplit:
    """Greenwald: growth capex = (avg PP&E / revenue) × Δrevenue.

    Maintenance capex = total − growth capex (floored at zero). When revenue
    falls, growth capex is set to zero rather than negative.
    """
    if len(ppe) != len(revenues) or not ppe:
        raise ValueError("ppe and revenues must be matching non-empty lists")
    intensity = statistics.fmean(p / r for p, r in zip(ppe, revenues))
    growth = max(revenue_change, 0.0) * intensity
    growth = min(growth, capex)
    return CapexSplit(capex, growth, capex - growth, intensity, depreciation, "greenwald")


def sbc_adjusted_fcf(operating_cash_flow: float, capex: float, stock_based_comp: float) -> float:
    """FCF treating stock-based compensation as the real expense it is.

    SBC is added back in operating cash flow; subtracting it again here
    avoids overstating owner cash flow. Do not *also* count the resulting
    dilution in the share count for the same grants (that would double-count).
    """
    return operating_cash_flow - capex - stock_based_comp
