"""Annual financial statement model and basic / forensic analysis (MVP).

Each derived metric is deterministic. Warning flags are *analytical
inferences* that point to where an analyst should look; they are not
findings of misconduct.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class FinancialPeriod:
    fiscal_year: int
    period_end: date
    revenue: float
    operating_income: float
    net_income: float
    operating_cash_flow: float
    capex: float                       # positive number = cash spent
    depreciation: float = 0.0
    stock_based_comp: float = 0.0
    accounts_receivable: float = 0.0
    inventory: float = 0.0
    total_assets: float = 0.0
    total_debt: float = 0.0
    cash: float = 0.0
    shareholders_equity: float = 0.0
    interest_expense: float = 0.0
    diluted_shares: float = 0.0
    gross_profit: float | None = None
    cost_of_revenue: float | None = None
    filed: date | None = None          # when the figures became public
    source_ref: str = ""
    period_start: date | None = None
    period_type: str = "FY"            # "FY" | "Q" | "TTM"
    # field name -> FigureProvenance (concept, accession, period, filed, retrieved_at, URL)
    provenance: dict = field(default_factory=dict, compare=False, hash=False, repr=False)


@dataclass(frozen=True)
class PeriodMetrics:
    fiscal_year: int
    revenue_growth: float | None
    gross_margin: float | None
    operating_margin: float
    net_margin: float
    fcf: float
    fcf_after_sbc: float
    fcf_conversion: float | None       # FCF / net income
    sbc_pct_revenue: float
    capex_pct_revenue: float
    dso: float | None
    dio: float | None
    accruals_ratio: float | None       # (NI - CFO) / average total assets
    net_debt: float
    interest_coverage: float | None
    share_count_change: float | None
    roe: float | None


@dataclass(frozen=True)
class Flag:
    fiscal_year: int
    code: str
    message: str
    severity: str = "review"           # "review" | "elevated"


@dataclass(frozen=True)
class StatementAnalysis:
    metrics: tuple[PeriodMetrics, ...]
    flags: tuple[Flag, ...] = field(default_factory=tuple)

    def latest(self) -> PeriodMetrics:
        return self.metrics[-1]


def _safe(num: float, den: float) -> float | None:
    return num / den if den else None


def analyse(periods: list[FinancialPeriod]) -> StatementAnalysis:
    if not periods:
        raise ValueError("no periods")
    ps = sorted(periods, key=lambda p: p.fiscal_year)
    out: list[PeriodMetrics] = []
    flags: list[Flag] = []
    prev: FinancialPeriod | None = None
    for p in ps:
        g = _safe(p.revenue - prev.revenue, prev.revenue) if prev else None
        gp = p.gross_profit if p.gross_profit is not None else (
            p.revenue - p.cost_of_revenue if p.cost_of_revenue is not None else None)
        fcf = p.operating_cash_flow - p.capex
        avg_assets = (p.total_assets + prev.total_assets) / 2 if prev and prev.total_assets else p.total_assets
        dso = _safe(p.accounts_receivable * 365, p.revenue)
        cogs = p.cost_of_revenue if p.cost_of_revenue is not None else (
            p.revenue - p.gross_profit if p.gross_profit is not None else None)
        dio = _safe(p.inventory * 365, cogs) if cogs else None
        m = PeriodMetrics(
            p.fiscal_year, g, _safe(gp, p.revenue) if gp is not None else None,
            p.operating_income / p.revenue, p.net_income / p.revenue, fcf,
            fcf - p.stock_based_comp,
            _safe(fcf, p.net_income) if p.net_income > 0 else None,
            p.stock_based_comp / p.revenue, p.capex / p.revenue, dso, dio,
            _safe(p.net_income - p.operating_cash_flow, avg_assets) if avg_assets else None,
            p.total_debt - p.cash,
            _safe(p.operating_income, p.interest_expense) if p.interest_expense else None,
            _safe(p.diluted_shares - prev.diluted_shares, prev.diluted_shares)
            if prev and prev.diluted_shares else None,
            _safe(p.net_income, p.shareholders_equity) if p.shareholders_equity > 0 else None,
        )
        out.append(m)

        if prev:
            ar_g = _safe(p.accounts_receivable - prev.accounts_receivable, prev.accounts_receivable)
            if ar_g is not None and g is not None and ar_g - g > 0.10:
                flags.append(Flag(p.fiscal_year, "RECEIVABLES_OUTPACE_REVENUE",
                                  f"receivables grew {ar_g:.0%} vs revenue {g:.0%}: check revenue "
                                  "recognition, channel stuffing or collection problems"))
            inv_g = _safe(p.inventory - prev.inventory, prev.inventory)
            if inv_g is not None and g is not None and inv_g - g > 0.15:
                flags.append(Flag(p.fiscal_year, "INVENTORY_OUTPACES_REVENUE",
                                  f"inventory grew {inv_g:.0%} vs revenue {g:.0%}: possible demand "
                                  "slowdown or obsolescence risk"))
            if m.share_count_change is not None and m.share_count_change > 0.03:
                flags.append(Flag(p.fiscal_year, "DILUTION",
                                  f"diluted shares rose {m.share_count_change:.1%}"))
        if m.accruals_ratio is not None and m.accruals_ratio > 0.10:
            flags.append(Flag(p.fiscal_year, "HIGH_ACCRUALS",
                              f"accruals ratio {m.accruals_ratio:.1%}: earnings well ahead of cash",
                              "elevated"))
        if p.net_income > 0 and fcf < 0:
            flags.append(Flag(p.fiscal_year, "PROFIT_WITHOUT_CASH",
                              "positive net income but negative free cash flow"))
        if m.sbc_pct_revenue > 0.10:
            flags.append(Flag(p.fiscal_year, "HEAVY_SBC",
                              f"stock-based compensation is {m.sbc_pct_revenue:.1%} of revenue"))
        if m.interest_coverage is not None and m.interest_coverage < 3:
            flags.append(Flag(p.fiscal_year, "LOW_INTEREST_COVERAGE",
                              f"EBIT covers interest {m.interest_coverage:.1f}x", "elevated"))
        prev = p
    return StatementAnalysis(tuple(out), tuple(flags))
