"""Choose valuation methods that fit the company, with reasons for each choice.

Methods are never applied indiscriminately: each is selected, used as a
cross-check, or excluded, and the reason is recorded for the report.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Method(str, Enum):
    DCF = "dcf"
    REVERSE_DCF = "reverse_dcf"
    PE = "pe"
    FORWARD_PE = "forward_pe"
    PEG = "peg"
    EV_EBITDA = "ev_ebitda"
    EV_REVENUE = "ev_revenue"
    PRICE_TO_BOOK = "price_to_book"
    FCF_YIELD = "fcf_yield"
    SOTP = "sum_of_the_parts"
    ASSET_BASED = "asset_based"
    HISTORICAL_MULTIPLES = "historical_multiples"
    COMPARABLES = "comparables"
    SCENARIOS = "scenarios"
    RESIDUAL_INCOME = "residual_income"
    DDM = "dividend_discount"
    NORMALISED_DCF = "normalised_dcf"


@dataclass(frozen=True)
class CompanyProfile:
    sector: str = ""
    is_financial_institution: bool = False   # banks, insurers
    profitable: bool = True                  # positive operating income (normalised)
    positive_fcf: bool = True
    cyclical: bool = False
    segments: int = 1
    asset_heavy: bool = False                # e.g. REITs, holding companies, liquidation cases
    high_growth: bool = False                # revenue growth > ~20%
    pays_dividends: bool = False
    years_of_history: int = 5
    peers_available: int = 0
    multiple_history_years: int = 0


@dataclass(frozen=True)
class MethodChoice:
    method: Method
    role: str            # "primary" | "cross-check" | "excluded"
    reason: str


def select_methods(p: CompanyProfile) -> list[MethodChoice]:
    out: list[MethodChoice] = []

    def add(m: Method, role: str, reason: str) -> None:
        out.append(MethodChoice(m, role, reason))

    if p.is_financial_institution:
        add(Method.RESIDUAL_INCOME, "primary", "financial institution: debt is operating, value equity directly")
        add(Method.PRICE_TO_BOOK, "cross-check", "book value is the core economic base for lenders/insurers")
        if p.pays_dividends:
            add(Method.DDM, "cross-check", "regulated capital returns make dividends a reasonable proxy")
        for m in (Method.DCF, Method.EV_EBITDA, Method.EV_REVENUE):
            add(m, "excluded", "enterprise-value methods treat operating debt as financing")
        add(Method.REVERSE_DCF, "excluded", "FCFF reverse DCF inappropriate; use implied ROE instead")
    else:
        if p.cyclical:
            add(Method.NORMALISED_DCF, "primary", "cyclical: forecast from through-cycle margins, not the latest year")
        elif p.profitable and p.positive_fcf:
            add(Method.DCF, "primary", "profitable, cash-generative business supports a DCF")
        else:
            add(Method.DCF, "primary", "unprofitable: DCF with explicit path to profitability and wide scenarios; "
                                       "distant cash flows dominate and are highly uncertain")
        add(Method.REVERSE_DCF, "primary", "states the operating outcomes the price requires")
        add(Method.SCENARIOS, "primary", "bear/base/bull range instead of a single point")
        if p.profitable:
            add(Method.EV_EBITDA, "cross-check", "capital-structure-neutral earnings multiple")
            add(Method.PE, "cross-check", "common market yardstick")
            add(Method.FORWARD_PE, "cross-check", "uses expected rather than trailing earnings (needs licensed estimates)")
            if p.high_growth:
                add(Method.PEG, "cross-check", "relates P/E to growth for growth companies")
        else:
            for m in (Method.PE, Method.FORWARD_PE, Method.PEG):
                add(m, "excluded", "earnings not positive: earnings multiples not meaningful")
            add(Method.EV_REVENUE, "cross-check", "revenue multiple usable when earnings are negative, "
                                                  "but blind to profitability")
        if p.positive_fcf:
            add(Method.FCF_YIELD, "cross-check", "cash return on today's price")
        if p.segments > 1:
            add(Method.SOTP, "cross-check", f"{p.segments} segments with potentially different economics")
        if p.asset_heavy:
            add(Method.ASSET_BASED, "cross-check", "asset values are a meaningful floor or anchor")
            add(Method.PRICE_TO_BOOK, "cross-check", "asset-heavy balance sheet")
    if p.peers_available >= 3:
        add(Method.COMPARABLES, "cross-check", f"{p.peers_available} peers available")
    else:
        add(Method.COMPARABLES, "excluded", "fewer than three comparable peers")
    if p.multiple_history_years >= 5:
        add(Method.HISTORICAL_MULTIPLES, "cross-check", "multi-year multiple history available")
    if p.years_of_history < 3:
        out.append(MethodChoice(Method.DCF, "caveat", "under three years of history: forecasts are weakly anchored"))
    return out
