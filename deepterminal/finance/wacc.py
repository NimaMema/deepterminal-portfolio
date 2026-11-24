"""Cost of capital. Every input is explicit; there are no hidden defaults."""

from __future__ import annotations

from dataclasses import dataclass


def capm_cost_of_equity(risk_free: float, beta: float, equity_risk_premium: float,
                        additional_premium: float = 0.0) -> float:
    """r_e = r_f + beta * ERP + explicit additional premium (country, size...)."""
    return risk_free + beta * equity_risk_premium + additional_premium


def unlever_beta(levered_beta: float, debt_to_equity: float, tax_rate: float) -> float:
    """Hamada: beta_u = beta_l / (1 + (1 - t) * D/E)."""
    return levered_beta / (1.0 + (1.0 - tax_rate) * debt_to_equity)


def relever_beta(unlevered_beta: float, debt_to_equity: float, tax_rate: float) -> float:
    return unlevered_beta * (1.0 + (1.0 - tax_rate) * debt_to_equity)


@dataclass(frozen=True)
class WACCResult:
    cost_of_equity: float
    after_tax_cost_of_debt: float
    weight_equity: float
    weight_debt: float
    wacc: float


def wacc(equity_value: float, debt_value: float, cost_of_equity: float,
         pre_tax_cost_of_debt: float, tax_rate: float) -> WACCResult:
    """Weights should be market values (equity at market cap, debt at fair value)."""
    total = equity_value + debt_value
    if total <= 0:
        raise ValueError("capital must be positive")
    we, wd = equity_value / total, debt_value / total
    kd = pre_tax_cost_of_debt * (1.0 - tax_rate)
    return WACCResult(cost_of_equity, kd, we, wd, we * cost_of_equity + wd * kd)
