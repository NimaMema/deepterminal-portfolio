"""Time-value-of-money primitives."""

from __future__ import annotations

from typing import Sequence


def discount_factor(rate: float, t: float) -> float:
    """1 / (1 + rate)^t."""
    if rate <= -1:
        raise ValueError("discount rate must exceed -100%")
    return (1.0 + rate) ** -t


def period_time(year: int, mid_year: bool) -> float:
    """Timing of a cash flow for year ``year`` (1-based)."""
    return year - 0.5 if mid_year else float(year)


def present_value(cash_flows: Sequence[float], rate: float, mid_year: bool = False) -> float:
    """PV of cash flows received in years 1..n."""
    return sum(cf * discount_factor(rate, period_time(i, mid_year))
               for i, cf in enumerate(cash_flows, start=1))


def gordon_value(next_cash_flow: float, rate: float, growth: float) -> float:
    """Value one period before ``next_cash_flow`` of a growing perpetuity."""
    if rate <= growth:
        raise ValueError(f"discount rate {rate:.4f} must exceed perpetual growth {growth:.4f}")
    return next_cash_flow / (rate - growth)


def cagr(start: float, end: float, years: float) -> float:
    if start <= 0 or end <= 0 or years <= 0:
        raise ValueError("CAGR requires positive start, end and years")
    return (end / start) ** (1.0 / years) - 1.0


def linear_path(start: float, end: float, n: int) -> list[float]:
    """n values moving linearly from ``start`` (year 1) to ``end`` (year n)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if n == 1:
        return [end]
    step = (end - start) / (n - 1)
    return [start + step * i for i in range(n)]
