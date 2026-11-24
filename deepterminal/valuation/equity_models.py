"""Equity-side models for financial institutions and dividend payers.

For banks and insurers, debt is operating raw material rather than
financing, so FCFF/EV approaches are inappropriate. These models value
equity directly at the cost of equity.
"""

from __future__ import annotations

from dataclasses import dataclass


def gordon_ddm(next_dividend: float, cost_of_equity: float, growth: float) -> float:
    if cost_of_equity <= growth:
        raise ValueError("cost of equity must exceed growth")
    return next_dividend / (cost_of_equity - growth)


def justified_price_to_book(roe: float, cost_of_equity: float, growth: float) -> float:
    """Steady-state P/B = (ROE - g) / (r_e - g)."""
    if cost_of_equity <= growth:
        raise ValueError("cost of equity must exceed growth")
    return (roe - growth) / (cost_of_equity - growth)


@dataclass(frozen=True)
class ResidualIncomeResult:
    book_value_start: float
    residual_incomes: tuple[float, ...]
    pv_residual_income: float
    terminal_value: float
    pv_terminal: float
    equity_value: float
    ending_book_values: tuple[float, ...]


def residual_income_value(book_value: float, roe: tuple[float, ...], payout: tuple[float, ...],
                          cost_of_equity: float, terminal_growth: float) -> ResidualIncomeResult:
    """Equity = BV_0 + Σ (ROE_t - r) BV_{t-1} / (1+r)^t + terminal residual income.

    Clean-surplus accounting: BV_t = BV_{t-1} + NI_t - dividends_t. Terminal
    residual income grows at ``terminal_growth`` from year N+1 assuming
    final-year ROE persists and book grows at ``terminal_growth``.
    Consistency with the DDM under clean surplus is checked in tests.
    """
    if len(roe) != len(payout) or not roe:
        raise ValueError("roe and payout need one value per year")
    if cost_of_equity <= terminal_growth:
        raise ValueError("cost of equity must exceed terminal growth")
    bv = book_value
    ris, bvs = [], []
    pv = 0.0
    for t, (r_t, p_t) in enumerate(zip(roe, payout), start=1):
        ni = r_t * bv
        ri = ni - cost_of_equity * bv
        pv += ri / (1 + cost_of_equity) ** t
        ris.append(ri)
        bv = bv + ni * (1 - p_t)
        bvs.append(bv)
    n = len(roe)
    ri_next = (roe[-1] - cost_of_equity) * bv
    tv = ri_next / (cost_of_equity - terminal_growth)
    pv_tv = tv / (1 + cost_of_equity) ** n
    return ResidualIncomeResult(book_value, tuple(ris), pv, tv, pv_tv, book_value + pv + pv_tv,
                                tuple(bvs))
