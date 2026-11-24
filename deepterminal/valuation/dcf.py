"""Free-cash-flow-to-the-firm DCF.

Model (all figures in one currency, nominal):

    Revenue_t   = Revenue_{t-1} * (1 + g_t)
    EBIT_t      = Revenue_t * margin_t          (margin after stock-based comp)
    NOPAT_t     = EBIT_t * (1 - tax_t)
    Reinvest_t  = (Revenue_t - Revenue_{t-1}) / sales_to_capital_t
                  or net_capex% * Revenue_t + nwc% * (Revenue_t - Revenue_{t-1})
    FCFF_t      = NOPAT_t - Reinvest_t

Terminal value (value-driver form, consistent growth and reinvestment):

    NOPAT_{N+1} = Revenue_N * (1 + g) * terminal_margin * (1 - terminal_tax)
    FCFF_{N+1}  = NOPAT_{N+1} * (1 - g / terminal_ROIC)
    TV_N        = FCFF_{N+1} / (WACC - g)

Using the reinvestment rate g / ROIC (rather than "last FCF × (1+g)") stops
the model from assuming growth is free. When terminal ROIC equals WACC the
terminal value collapses to NOPAT_{N+1} / WACC: growth beyond year N+1 adds
no value — an identity checked in the test suite.

Timing: end-of-year by default. With ``mid_year=True`` each flow is
discounted at t - 0.5 and the terminal value at N - 0.5, which is the
consistent treatment for a perpetuity whose flows also arrive mid-year.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Sequence

from ..finance.timevalue import discount_factor, gordon_value, period_time


@dataclass(frozen=True)
class SalesToCapital:
    """Net reinvestment = change in revenue / ratio (Damodaran-style)."""

    ratio: float | tuple[float, ...]


@dataclass(frozen=True)
class ExplicitReinvestment:
    """Net reinvestment = net capex% × revenue + NWC% × change in revenue.

    ``net_capex_pct_revenue`` is capex minus D&A. Use maintenance/growth
    capex analysis (see normalization.py) to choose it; do not also add
    maintenance capex elsewhere.
    """

    net_capex_pct_revenue: float | tuple[float, ...]
    nwc_pct_revenue_change: float | tuple[float, ...]


Reinvestment = SalesToCapital | ExplicitReinvestment


@dataclass(frozen=True)
class DCFInputs:
    base_revenue: float
    revenue_growth: tuple[float, ...]
    ebit_margin: tuple[float, ...]
    tax_rate: float | tuple[float, ...]
    discount_rate: float
    terminal_growth: float
    terminal_roic: float
    reinvestment: Reinvestment
    terminal_ebit_margin: float | None = None   # default: final explicit-year margin
    terminal_tax_rate: float | None = None      # default: final explicit-year tax
    mid_year: bool = False

    @property
    def years(self) -> int:
        return len(self.revenue_growth)

    def with_changes(self, **changes) -> "DCFInputs":
        return replace(self, **changes)

    def validate(self) -> None:
        n = self.years
        if n < 1:
            raise ValueError("at least one explicit forecast year is required")
        if len(self.ebit_margin) != n:
            raise ValueError("ebit_margin must have one value per forecast year")
        for name, val in (("tax_rate", self.tax_rate),):
            if isinstance(val, tuple) and len(val) != n:
                raise ValueError(f"{name} must be scalar or one value per year")
        if self.base_revenue <= 0:
            raise ValueError("base_revenue must be positive")
        if self.discount_rate <= self.terminal_growth:
            raise ValueError("discount_rate must exceed terminal_growth")
        if self.terminal_roic <= 0:
            raise ValueError("terminal_roic must be positive")


@dataclass(frozen=True)
class DCFYear:
    year: int
    revenue: float
    growth: float
    ebit: float
    ebit_margin: float
    tax_rate: float
    nopat: float
    reinvestment: float
    fcff: float
    discount_factor: float
    present_value: float


@dataclass(frozen=True)
class DCFResult:
    inputs: DCFInputs
    years: tuple[DCFYear, ...]
    pv_explicit: float
    terminal_fcff: float
    terminal_value: float
    pv_terminal: float
    enterprise_value: float
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def terminal_share(self) -> float:
        return self.pv_terminal / self.enterprise_value if self.enterprise_value else float("nan")

    @property
    def final_revenue(self) -> float:
        return self.years[-1].revenue


def _at(value: float | Sequence[float], i: int) -> float:
    return value[i] if isinstance(value, (tuple, list)) else value


def run_dcf(inp: DCFInputs) -> DCFResult:
    inp.validate()
    rows: list[DCFYear] = []
    prev_rev = inp.base_revenue
    pv_sum = 0.0
    r = inp.discount_rate
    for i in range(inp.years):
        g = inp.revenue_growth[i]
        rev = prev_rev * (1.0 + g)
        margin = inp.ebit_margin[i]
        tax = _at(inp.tax_rate, i)
        ebit = rev * margin
        nopat = ebit * (1.0 - tax) if ebit > 0 else ebit   # no tax shield modelled on losses
        delta = rev - prev_rev
        if isinstance(inp.reinvestment, SalesToCapital):
            s2c = _at(inp.reinvestment.ratio, i)
            if s2c <= 0:
                raise ValueError("sales_to_capital must be positive")
            reinv = delta / s2c
        else:
            reinv = (_at(inp.reinvestment.net_capex_pct_revenue, i) * rev
                     + _at(inp.reinvestment.nwc_pct_revenue_change, i) * delta)
        fcff = nopat - reinv
        df = discount_factor(r, period_time(i + 1, inp.mid_year))
        pv = fcff * df
        pv_sum += pv
        rows.append(DCFYear(i + 1, rev, g, ebit, margin, tax, nopat, reinv, fcff, df, pv))
        prev_rev = rev

    g_t = inp.terminal_growth
    t_margin = inp.terminal_ebit_margin if inp.terminal_ebit_margin is not None else rows[-1].ebit_margin
    t_tax = inp.terminal_tax_rate if inp.terminal_tax_rate is not None else rows[-1].tax_rate
    t_nopat = prev_rev * (1.0 + g_t) * t_margin * (1.0 - t_tax)
    t_fcff = t_nopat * (1.0 - g_t / inp.terminal_roic)
    tv = gordon_value(t_fcff, r, g_t)
    pv_tv = tv * discount_factor(r, period_time(inp.years, inp.mid_year))
    ev = pv_sum + pv_tv

    warnings: list[str] = []
    if g_t > 0.04:
        warnings.append(f"terminal growth {g_t:.1%} exceeds a typical long-run nominal "
                        "economic growth ceiling (~4%)")
    if ev and pv_tv / ev > 0.75:
        warnings.append(f"terminal value is {pv_tv / ev:.0%} of enterprise value; "
                        "conclusions are dominated by terminal assumptions")
    if g_t > 0 and inp.terminal_roic < r:
        warnings.append("terminal ROIC below discount rate: terminal growth destroys value")
    if t_nopat <= 0:
        warnings.append("terminal NOPAT is not positive; a going-concern DCF may be inappropriate")
    return DCFResult(inp, tuple(rows), pv_sum, t_fcff, tv, pv_tv, ev, tuple(warnings))
