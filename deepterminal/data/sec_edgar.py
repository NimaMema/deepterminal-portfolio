"""SEC EDGAR connector: company lookup, submissions, XBRL companyfacts, point-in-time parsing.

Endpoints (public; SEC fair-access policy applies):

* ``https://www.sec.gov/files/company_tickers.json`` — ticker ↔ CIK map
* ``https://data.sec.gov/submissions/CIK##########.json`` — filings list, SIC code
* ``https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`` — all XBRL facts

Fair access (https://www.sec.gov/os/accessing-edgar-data): declare a User-Agent
with your name/organisation and a contact e-mail, and stay at or below 10
requests per second. :class:`SECClient` enforces both (it refuses to make
network calls without a contact address and throttles to 8 req/s).

Temporal discipline:

* every fact carries its ``filed`` date and accession number; all builders
  accept ``as_of`` and ignore facts filed later (no look-ahead);
* the same period is reported in several filings (comparatives,
  restatements): ``revision="original"`` keeps the first-filed value,
  ``"latest"`` the most recent knowable one; :func:`detect_revisions` lists
  periods whose value changed;
* each figure placed in a :class:`FinancialPeriod` gets a
  :class:`~deepterminal.evidence.FigureProvenance` (concept, period, form,
  accession, filing date, filing URL, retrieval time).

10-Q support: discrete quarters are taken from 3-month facts when tagged and
otherwise derived from year-to-date differences (e.g. cash flow, Q4 = FY − 9M);
derived figures record both inputs. Trailing-twelve-month (TTM) figures sum
four contiguous quarters.
"""

from __future__ import annotations

import difflib
import os
import re
from dataclasses import replace, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from ..evidence import FigureProvenance
from ..financials.statements import FinancialPeriod
from .http import CachedFetcher, FetchResult, NotFound

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{name}"
USER_AGENT_ENV = "DEEPTERMINAL_SEC_USER_AGENT"
OFFLINE_USER_AGENT = "DEEPTERMINAL offline (no network requests)"

Revision = Literal["original", "latest"]

# field: (candidate us-gaap concepts in priority order, unit, is_duration)
CONCEPTS: dict[str, tuple[tuple[str, ...], str, bool]] = {
    "revenue": (("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                 "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
                 "SalesRevenueGoodsNet"), "USD", True),
    "operating_income": (("OperatingIncomeLoss",), "USD", True),
    "net_income": (("NetIncomeLoss", "ProfitLoss"), "USD", True),
    "operating_cash_flow": (("NetCashProvidedByUsedInOperatingActivities",
                             "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"), "USD", True),
    "capex": (("PaymentsToAcquirePropertyPlantAndEquipment",
               "PaymentsToAcquireProductiveAssets"), "USD", True),
    "depreciation": (("DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
                      "DepreciationAndAmortization", "Depreciation"), "USD", True),
    "stock_based_comp": (("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"), "USD", True),
    "gross_profit": (("GrossProfit",), "USD", True),
    "cost_of_revenue": (("CostOfRevenue", "CostOfGoodsAndServicesSold"), "USD", True),
    "interest_expense": (("InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"), "USD", True),
    "income_tax": (("IncomeTaxExpenseBenefit",), "USD", True),
    "pretax_income": (("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                       "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
                      "USD", True),
    "diluted_shares": (("WeightedAverageNumberOfDilutedSharesOutstanding",), "shares", True),
    "accounts_receivable": (("AccountsReceivableNetCurrent",), "USD", False),
    "inventory": (("InventoryNet",), "USD", False),
    "accounts_payable": (("AccountsPayableCurrent",), "USD", False),
    "total_assets": (("Assets",), "USD", False),
    "liabilities_and_equity": (("LiabilitiesAndStockholdersEquity",), "USD", False),
    "total_debt": (("LongTermDebt", "LongTermDebtNoncurrent"), "USD", False),
    "debt_noncurrent": (("LongTermDebtNoncurrent",), "USD", False),
    "debt_current": (("LongTermDebtCurrent", "DebtCurrent"), "USD", False),
    "short_term_borrowings": (("CommercialPaper", "ShortTermBorrowings"), "USD", False),
    "cash": (("CashAndCashEquivalentsAtCarryingValue",
              "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"), "USD", False),
    "marketable_securities_current": (("MarketableSecuritiesCurrent", "ShortTermInvestments",
                                       "AvailableForSaleSecuritiesDebtSecuritiesCurrent"), "USD", False),
    "marketable_securities_noncurrent": (("MarketableSecuritiesNoncurrent",
                                          "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent"), "USD", False),
    "operating_lease_liabilities": (("OperatingLeaseLiability",), "USD", False),
    "minority_interest": (("MinorityInterest",), "USD", False),
    "preferred_equity": (("PreferredStockValue",), "USD", False),
    "pension_funded_status": (("DefinedBenefitPlanFundedStatusOfPlan",), "USD", False),
    "shareholders_equity": (("StockholdersEquity",
                             "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"), "USD", False),
    "options_outstanding": (("ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingNumber",),
                            "shares", False),
    "options_strike": (("ShareBasedCompensationArrangementByShareBasedPaymentAwardOptionsOutstandingWeightedAverageExercisePrice",),
                       "USD/shares", False),
    "assets_current": (("AssetsCurrent",), "USD", False),
    "liabilities_current": (("LiabilitiesCurrent",), "USD", False),
    "total_liabilities": (("Liabilities",), "USD", False),
    "retained_earnings": (("RetainedEarningsAccumulatedDeficit",), "USD", False),
    "ppe_net": (("PropertyPlantAndEquipmentNet",), "USD", False),
    "sga": (("SellingGeneralAndAdministrativeExpense",), "USD", True),
    "rnd": (("ResearchAndDevelopmentExpense",
             "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"), "USD", True),
    "deferred_revenue": (("ContractWithCustomerLiabilityCurrent", "ContractWithCustomerLiability",
                          "DeferredRevenueCurrent"), "USD", False),
    "rpo": (("RevenueRemainingPerformanceObligation",), "USD", False),
    "goodwill": (("Goodwill",), "USD", False),
    "dividends_paid": (("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"), "USD", True),
    "buybacks": (("PaymentsForRepurchaseOfCommonStock",), "USD", True),
    "acquisitions": (("PaymentsToAcquireBusinessesNetOfCashAcquired",), "USD", True),
    "rsus_unvested": (("ShareBasedCompensationArrangementByShareBasedPaymentAwardEquityInstrumentsOtherThanOptionsNonvestedNumber",),
                      "shares", False),
}
REQUIRED = ("revenue", "operating_income", "net_income", "operating_cash_flow", "capex")
PERIOD_FIELDS = ("revenue", "operating_income", "net_income", "operating_cash_flow", "capex",
                 "depreciation", "stock_based_comp", "accounts_receivable", "inventory", "total_assets",
                 "total_debt", "cash", "shareholders_equity", "interest_expense", "diluted_shares",
                 "gross_profit", "cost_of_revenue")
ANNUAL_FORMS = ("10-K", "10-K/A", "10-KT", "10-KT/A")
QUARTERLY_FORMS = ("10-Q", "10-Q/A")


class UnsupportedFiler(ValueError):
    """Raised when facts are not in a supported form (e.g. no USD us-gaap facts)."""


@dataclass(frozen=True)
class Fact:
    concept: str
    end: date
    start: date | None
    value: float
    filed: date
    form: str
    accession: str
    fiscal_year: int | None
    fiscal_period: str | None = None
    split_factor: float = 1.0      # ≠ 1 when a share count was restated to the post-split basis (value is adjusted)

    @property
    def days(self) -> int | None:
        return (self.end - self.start).days + 1 if self.start else None


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def filing_url(cik: int, accession: str) -> str:
    """Human-readable filing index page on EDGAR."""
    if not accession:
        return ""
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{accession}-index.htm")


def iter_facts(companyfacts: dict[str, Any], concept: str, unit: str,
               taxonomy: str = "us-gaap") -> list[Fact]:
    node = companyfacts.get("facts", {}).get(taxonomy, {}).get(concept)
    if not node:
        return []
    out = []
    for f in node.get("units", {}).get(unit, []):
        out.append(Fact(concept, _d(f["end"]), _d(f.get("start")), float(f["val"]),
                        _d(f["filed"]), f.get("form", ""), f.get("accn", ""), f.get("fy"), f.get("fp")))
    return out


def _form_ok(f: Fact, forms: tuple[str, ...]) -> bool:
    return f.form in forms


def _is_annual(f: Fact, duration: bool) -> bool:
    if not (_form_ok(f, ANNUAL_FORMS) or f.form.startswith("20-F")):
        return False
    if not duration:
        return f.start is None
    return f.start is not None and 350 <= (f.end - f.start).days <= 380


def _choose(facts: list[Fact], revision: Revision) -> dict[tuple, Fact]:
    """One fact per (start, end): earliest filed ('original') or latest filed ('latest')."""
    chosen: dict[tuple, Fact] = {}
    for f in sorted(facts, key=lambda x: (x.filed, x.accession), reverse=(revision == "original")):
        chosen[(f.start, f.end)] = f   # last write wins
    return chosen


def _merged(companyfacts: dict[str, Any], field_name: str, keep, as_of: date | None,
            revision: Revision, adjust_splits: bool = True) -> dict[tuple, Fact]:
    """Merge candidate concepts per period, earlier concepts taking priority.

    Share counts are put on one basis: a period last reported before a stock split is multiplied by the
    splits that took effect after it was filed (and, point-in-time, on or before ``as_of``)."""
    concepts, unit, _ = CONCEPTS[field_name]
    splits = split_events(companyfacts) if adjust_splits and unit == "shares" else []
    out: dict[tuple, Fact] = {}
    for concept in concepts:
        facts = [f for f in iter_facts(companyfacts, concept, unit)
                 if keep(f) and (as_of is None or f.filed <= as_of)]
        for key, f in _choose(facts, revision).items():
            k = 1.0
            for eff, ratio in splits:
                if f.filed < eff and (as_of is None or eff <= as_of):
                    k *= ratio
            out.setdefault(key, replace(f, value=f.value * k, split_factor=k) if k != 1.0 else f)
    return out


SHARE_COUNT_CONCEPTS = ("WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic")


def split_events(companyfacts: dict[str, Any]) -> list[tuple[date, float]]:
    """Stock splits inferred from the filings themselves: the first filing in which a period's share count
    reappears multiplied by a standard split ratio. Returns (effective filing date, ratio), oldest first."""
    found: list[tuple[date, float]] = []
    for concept in SHARE_COUNT_CONCEPTS:
        by_period: dict[tuple, list[Fact]] = {}
        for f in iter_facts(companyfacts, concept, "shares"):
            if f.value > 0:
                by_period.setdefault((f.start, f.end), []).append(f)
        for fs in by_period.values():
            fs.sort(key=lambda f: f.filed)
            for a, b in zip(fs, fs[1:]):
                ratio = _split_ratio(a.value, b.value)
                if ratio and b.filed > a.filed:
                    found.append((b.filed, ratio))
    events: list[tuple[date, float]] = []
    for eff, ratio in sorted(found):
        if any(r == ratio and abs((eff - e).days) <= 400 for e, r in events):
            continue                    # same split seen again in later comparatives
        events.append((eff, ratio))
    return events


def annual_series(companyfacts: dict[str, Any], field_name: str, as_of: date | None = None,
                  revision: Revision = "original", adjust_splits: bool = True) -> dict[date, Fact]:
    """Annual values keyed by period end (10-K; duration ≈ one year or balance-sheet instant)."""
    _, _, duration = CONCEPTS[field_name]
    merged = _merged(companyfacts, field_name, lambda f: _is_annual(f, duration), as_of, revision, adjust_splits)
    return {end: f for (_, end), f in sorted(merged.items(), key=lambda kv: kv[0][1])}


def instant_series(companyfacts: dict[str, Any], field_name: str, as_of: date | None = None,
                   revision: Revision = "latest") -> dict[date, Fact]:
    """Balance-sheet values at every 10-K/10-Q period end."""
    merged = _merged(companyfacts, field_name,
                     lambda f: f.start is None and _form_ok(f, ANNUAL_FORMS + QUARTERLY_FORMS),
                     as_of, revision)
    return {end: f for (_, end), f in sorted(merged.items(), key=lambda kv: kv[0][1])}


@dataclass(frozen=True)
class QuarterValue:
    start: date
    end: date
    value: float
    derivation: str            # "" if reported directly
    facts: tuple[Fact, ...]    # the reported fact, or minuend and subtrahend


def quarterly_series(companyfacts: dict[str, Any], field_name: str, as_of: date | None = None,
                     revision: Revision = "latest") -> dict[date, QuarterValue]:
    """Discrete fiscal quarters keyed by quarter end.

    Uses 3-month facts where tagged; otherwise derives quarter = YTD(n) − YTD(n−1)
    (or FY − 9M for Q4) from facts sharing the same fiscal-year start.
    """
    _, _, duration = CONCEPTS[field_name]
    if not duration:
        raise ValueError(f"{field_name} is a balance-sheet item; use instant_series")
    merged = _merged(companyfacts, field_name,
                     lambda f: f.start is not None and _form_ok(f, ANNUAL_FORMS + QUARTERLY_FORMS),
                     as_of, revision)
    facts = list(merged.values())
    out: dict[date, QuarterValue] = {}
    for f in facts:
        if 80 <= f.days <= 100:
            out[f.end] = QuarterValue(f.start, f.end, f.value, "", (f,))
    by_start: dict[date, list[Fact]] = {}
    for f in facts:
        if f.days > 100:
            by_start.setdefault(f.start, []).append(f)
    for start, group in by_start.items():
        # include the first discrete quarter of the year as the base YTD (Q1 = 3-month fact)
        q1 = [f for f in facts if f.start == start and 80 <= f.days <= 100]
        chain = sorted(group + q1, key=lambda x: x.end)
        for prev, cur in zip(chain, chain[1:]):
            gap = (cur.end - prev.end).days
            if cur.end in out or not 80 <= gap <= 100:
                continue
            label = "FY − 9M YTD" if cur.days >= 350 else f"{round(cur.days / 91)}Q YTD − {round(prev.days / 91)}Q YTD"
            out[cur.end] = QuarterValue(prev.end + timedelta(days=1), cur.end, cur.value - prev.value,
                                        label, (cur, prev))
    return dict(sorted(out.items()))


@dataclass(frozen=True)
class RevisionRecord:
    field: str
    period_end: date
    original: float
    revised: float
    original_accession: str
    revised_accession: str
    revised_filed: date
    kind: str = "revision"          # "revision" | "stock_split" | "scale_correction" (value re-tagged ×1,000 / ×1,000,000)
    split_ratio: float | None = None


SPLIT_RATIOS = (2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 30, 40, 50, 100)


def _split_ratio(original: float, revised: float, tol: float = 0.01) -> float | None:
    """Ratio if a share count changed by a standard split (or reverse split) factor, else None."""
    if not original or not revised:
        return None
    r = revised / original
    for k in SPLIT_RATIOS:
        for target in (k, 1 / k):
            if abs(r - target) / target <= tol:
                return target
    return None


def detect_revisions(companyfacts: dict[str, Any], as_of: date | None = None,
                     tolerance: float = 0.005) -> list[RevisionRecord]:
    out = []
    for name in CONCEPTS:
        orig = annual_series(companyfacts, name, as_of, "original", adjust_splits=False)
        late = annual_series(companyfacts, name, as_of, "latest", adjust_splits=False)
        for end, o in orig.items():
            l = late.get(end)
            if l and o.concept == l.concept and o.value and abs(l.value - o.value) / abs(o.value) > tolerance:
                r = l.value / o.value
                if any(abs(r - k) / k <= 1e-6 for k in (1e3, 1e6, 1e-3, 1e-6)):
                    kind, ratio = "scale_correction", r          # e.g. early XBRL tagged in thousands
                else:
                    ratio = _split_ratio(o.value, l.value) if CONCEPTS[name][1] == "shares" else None
                    kind = "stock_split" if ratio else "revision"
                out.append(RevisionRecord(name, end, o.value, l.value, o.accession, l.accession, l.filed, kind, ratio))
    return sorted(out, key=lambda r: (r.period_end, r.field))


def _prov(name: str, f: Fact, scale: float, cik: int, retrieved: datetime | None) -> FigureProvenance:
    _, unit, _ = CONCEPTS[name]
    note = (f"split-adjusted ×{f.split_factor:g} to the current share basis (filed value "
            f"{f.value / f.split_factor:,.0f})") if f.split_factor != 1.0 else ""
    return FigureProvenance(name, f.value / scale, unit, f"us-gaap:{f.concept}", f.start, f.end, f.form,
                            f.accession, f.filed, filing_url(cik, f.accession), retrieved, note)


def _prov_q(name: str, q: QuarterValue, scale: float, cik: int, retrieved: datetime | None) -> FigureProvenance:
    if not q.derivation:
        return _prov(name, q.facts[0], scale, cik, retrieved)
    inputs = tuple(_prov(name, f, scale, cik, retrieved) for f in q.facts)
    _, unit, _ = CONCEPTS[name]
    latest = max(q.facts, key=lambda f: f.filed)
    return FigureProvenance(name, q.value / scale, unit, inputs[0].concept, q.start, q.end, latest.form,
                            latest.accession, latest.filed, filing_url(cik, latest.accession), retrieved,
                            q.derivation, inputs)


def _cik(companyfacts: dict[str, Any]) -> int:
    try:
        return int(companyfacts.get("cik", 0))
    except (TypeError, ValueError):
        return 0


def check_supported(companyfacts: dict[str, Any]) -> None:
    usgaap = companyfacts.get("facts", {}).get("us-gaap", {})
    if not usgaap:
        if companyfacts.get("facts", {}).get("ifrs-full"):
            raise UnsupportedFiler("company reports under IFRS (ifrs-full taxonomy); only us-gaap is supported")
        raise UnsupportedFiler("no us-gaap XBRL facts found")
    rev_units: set[str] = set()
    for c in CONCEPTS["revenue"][0]:
        rev_units |= set(usgaap.get(c, {}).get("units", {}))
    if rev_units and "USD" not in rev_units:
        raise UnsupportedFiler(f"revenue reported in {sorted(rev_units)}; only USD is supported")


def _period_from(values: dict[str, tuple[float, FigureProvenance]], end: date, start: date | None,
                 period_type: str, ref: str) -> FinancialPeriod:
    def v(name: str, default: float = 0.0) -> float:
        return values[name][0] if name in values else default
    filed = max(p.filed for _, p in values.values())
    prov = {k: p for k, (_, p) in values.items()}
    return FinancialPeriod(
        fiscal_year=end.year, period_end=end, revenue=v("revenue"),
        operating_income=v("operating_income"), net_income=v("net_income"),
        operating_cash_flow=v("operating_cash_flow"), capex=v("capex"), depreciation=v("depreciation"),
        stock_based_comp=v("stock_based_comp"), accounts_receivable=v("accounts_receivable"),
        inventory=v("inventory"), total_assets=v("total_assets"), total_debt=v("total_debt"),
        cash=v("cash"), shareholders_equity=v("shareholders_equity"),
        interest_expense=v("interest_expense"), diluted_shares=v("diluted_shares"),
        gross_profit=values["gross_profit"][0] if "gross_profit" in values else None,
        cost_of_revenue=values["cost_of_revenue"][0] if "cost_of_revenue" in values else None,
        filed=filed, source_ref=ref, period_start=start, period_type=period_type, provenance=prov)


def accession_ref(accession: str) -> str:
    return f"SEC accession {accession}"


def build_periods(companyfacts: dict[str, Any], as_of: date | None = None,
                  revision: Revision = "latest", scale: float = 1e6,
                  retrieved_at: datetime | None = None) -> list[FinancialPeriod]:
    """Annual FinancialPeriods (in ``scale`` units, default millions) knowable on ``as_of``.

    Periods missing any required field are skipped, never filled in.
    """
    cik = _cik(companyfacts)
    series = {name: annual_series(companyfacts, name, as_of, revision) for name in PERIOD_FIELDS}
    if not all(series[r] for r in REQUIRED):
        return []
    ends = sorted(set.intersection(*(set(series[r]) for r in REQUIRED)))
    periods = []
    for end in ends:
        values = {}
        for name in PERIOD_FIELDS:
            f = series[name].get(end)
            if f:
                values[name] = (f.value / scale, _prov(name, f, scale, cik, retrieved_at))
        start = series["revenue"][end].start
        periods.append(_period_from(values, end, start, "FY",
                                    accession_ref(series["revenue"][end].accession)))
    return periods


def build_quarterly_periods(companyfacts: dict[str, Any], as_of: date | None = None,
                            revision: Revision = "latest", scale: float = 1e6,
                            retrieved_at: datetime | None = None) -> list[FinancialPeriod]:
    """Discrete-quarter FinancialPeriods (10-Q + derived Q4), balance sheet at quarter end."""
    cik = _cik(companyfacts)
    flows = [n for n in PERIOD_FIELDS if CONCEPTS[n][2]]
    stocks = [n for n in PERIOD_FIELDS if not CONCEPTS[n][2]]
    q = {n: quarterly_series(companyfacts, n, as_of, revision) for n in flows}
    inst = {n: instant_series(companyfacts, n, as_of, revision) for n in stocks}
    if not all(q[r] for r in REQUIRED):
        return []
    ends = sorted(set.intersection(*(set(q[r]) for r in REQUIRED)))
    out = []
    for end in ends:
        values = {}
        for n in flows:
            if end in q[n]:
                values[n] = (q[n][end].value / scale, _prov_q(n, q[n][end], scale, cik, retrieved_at))
        for n in stocks:
            f = inst[n].get(end)
            if f:
                values[n] = (f.value / scale, _prov(n, f, scale, cik, retrieved_at))
        rq = q["revenue"][end]
        out.append(_period_from(values, end, rq.start, "Q", accession_ref(max(rq.facts, key=lambda f: f.filed).accession)))
    return out


def _contiguous(quarters: list[FinancialPeriod]) -> bool:
    for a, b in zip(quarters, quarters[1:]):
        if b.period_start is None or abs((b.period_start - a.period_end).days - 1) > 7:
            return False
    span = (quarters[-1].period_end - quarters[0].period_start).days + 1
    return 350 <= span <= 380


def build_ttm_period(companyfacts: dict[str, Any], as_of: date | None = None,
                     revision: Revision = "latest", scale: float = 1e6,
                     retrieved_at: datetime | None = None) -> FinancialPeriod | None:
    """Trailing twelve months ending at the latest quarter knowable on ``as_of``.

    Flows = sum of the last four contiguous discrete quarters; balance-sheet
    items at the latest quarter end; diluted shares = latest quarter's value.
    Returns None if four contiguous quarters are not available.
    """
    quarters = build_quarterly_periods(companyfacts, as_of, revision, scale, retrieved_at)
    if len(quarters) < 4:
        return None
    last4 = quarters[-4:]
    if not _contiguous(last4):
        return None
    latest = last4[-1]
    values: dict[str, tuple[float, FigureProvenance]] = {}
    for n in PERIOD_FIELDS:
        if not CONCEPTS[n][2] or n == "diluted_shares":
            if n in latest.provenance:
                values[n] = (latest.provenance[n].value, latest.provenance[n])
            continue
        provs = [p.provenance.get(n) for p in last4]
        if any(p is None for p in provs):
            continue
        total = sum(p.value for p in provs)
        values[n] = (total, FigureProvenance(
            n, total, provs[0].unit, provs[0].concept, last4[0].period_start, latest.period_end,
            latest.provenance[n].form, latest.provenance[n].accession, latest.provenance[n].filed,
            latest.provenance[n].source_url, retrieved_at, "sum of four quarters", tuple(provs)))
    if not all(r in values for r in REQUIRED):
        return None
    return _period_from(values, latest.period_end, last4[0].period_start, "TTM", latest.source_ref)


def latest_instant(companyfacts: dict[str, Any], field_name: str, as_of: date | None = None,
                   scale: float = 1e6, retrieved_at: datetime | None = None,
                   on_or_before: date | None = None) -> FigureProvenance | None:
    series = instant_series(companyfacts, field_name, as_of, "latest")
    ends = [e for e in series if on_or_before is None or e <= on_or_before]
    if not ends:
        return None
    return _prov(field_name, series[max(ends)], scale, _cik(companyfacts), retrieved_at)


def shares_outstanding(companyfacts: dict[str, Any], as_of: date | None = None, scale: float = 1e6,
                       retrieved_at: datetime | None = None) -> FigureProvenance | None:
    """Latest cover-page shares outstanding (dei:EntityCommonStockSharesOutstanding).

    companyfacts omits dimensional facts, so multi-class issuers may report
    only one class here; callers should compare with diluted weighted shares.
    """
    facts = [f for f in iter_facts(companyfacts, "EntityCommonStockSharesOutstanding", "shares", "dei")
             if as_of is None or f.filed <= as_of]
    if not facts:
        return None
    latest_filed = max(f.filed for f in facts)
    same = [f for f in facts if f.filed == latest_filed]
    f = max(same, key=lambda x: x.end)
    total = sum(x.value for x in same if x.end == f.end and x.accession == f.accession)
    derivation = "sum of share classes on cover page" if len([x for x in same if x.end == f.end]) > 1 else ""
    return FigureProvenance("shares_outstanding", total / scale, "shares", "dei:EntityCommonStockSharesOutstanding",
                            None, f.end, f.form, f.accession, f.filed, filing_url(_cik(companyfacts), f.accession),
                            retrieved_at, derivation)


# ───────────────────────────── network client ─────────────────────────────

def _valid_user_agent(ua: str | None) -> bool:
    return bool(ua) and re.search(r"[^@\s]+@[^@\s]+\.[^@\s]+", ua) is not None


class SECClient:
    """Fair-access EDGAR client with on-disk cache, retries and offline mode.

    ``DEEPTERMINAL_SEC_USER_AGENT`` (or ``user_agent``) must include a contact
    e-mail, e.g. "Jane Doe Research jane@example.com". In ``offline=True``
    mode the client only reads previously cached or recorded responses.
    """

    def __init__(self, user_agent: str | None = None, cache_dir: str | Path = ".cache/sec",
                 offline: bool = False, max_age: timedelta = timedelta(days=1),
                 fetcher: CachedFetcher | None = None, min_interval: float = 0.125):
        self.offline = offline
        self.max_age = max_age
        ua = user_agent or os.environ.get(USER_AGENT_ENV)
        if not offline and not _valid_user_agent(ua):
            raise RuntimeError(
                f"SEC fair-access policy requires a User-Agent with a contact e-mail; set {USER_AGENT_ENV}, "
                'e.g. export DEEPTERMINAL_SEC_USER_AGENT="Your Name your.email@example.com"')
        self.user_agent = ua or OFFLINE_USER_AGENT
        self.cache = Path(cache_dir)
        self.fetcher = fetcher or CachedFetcher(self.cache, self.user_agent, min_interval=min_interval,
                                                offline=offline)

    def _get(self, url: str, key: str, refresh: bool, max_age: timedelta | None = None) -> FetchResult:
        return self.fetcher.get(url, key, max_age=max_age or self.max_age, refresh=refresh)

    def company_tickers_result(self, refresh: bool = False) -> FetchResult:
        return self._get(TICKERS_URL, "company_tickers.json", refresh, timedelta(days=7))

    def submissions_result(self, cik: int, refresh: bool = False) -> FetchResult:
        return self._get(SUBMISSIONS_URL.format(cik=cik), f"submissions_{cik:010d}.json.gz", refresh)

    def companyfacts_result(self, cik: int, refresh: bool = False) -> FetchResult:
        return self._get(COMPANYFACTS_URL.format(cik=cik), f"companyfacts_{cik:010d}.json.gz", refresh)

    def companyfacts(self, cik: int, refresh: bool = False) -> tuple[dict[str, Any], datetime]:
        """Return (companyfacts JSON, retrieval timestamp)."""
        r = self.companyfacts_result(cik, refresh)
        return r.json(), r.retrieved_at


# ───────────────────────────── company lookup ─────────────────────────────

@dataclass(frozen=True)
class CompanyIdentity:
    cik: int
    ticker: str
    name: str
    source_url: str = TICKERS_URL
    retrieved_at: datetime | None = None
    sic: str | None = None
    sic_description: str | None = None
    fiscal_year_end: str | None = None
    exchanges: tuple[str, ...] = field(default_factory=tuple)


def _normalise_ticker(t: str) -> str:
    return t.strip().upper().replace(".", "-").replace("/", "-")


def parse_tickers(data: dict[str, Any]) -> list[tuple[int, str, str]]:
    """company_tickers.json → [(cik, ticker, title)]."""
    return [(int(v["cik_str"]), str(v["ticker"]).upper(), v["title"]) for v in data.values()]


def resolve_company(query: str, client: SECClient, refresh: bool = False) -> CompanyIdentity:
    """Resolve a ticker (e.g. "AAPL", "BRK.B") or CIK (e.g. "320193", "0000320193")."""
    q = query.strip()
    tick = client.company_tickers_result(refresh)
    rows = parse_tickers(tick.json())
    if q.isdigit():
        cik = int(q)
        match = [r for r in rows if r[0] == cik]
        if match:
            return CompanyIdentity(cik, match[0][1], match[0][2], TICKERS_URL, tick.retrieved_at)
        sub = client.submissions_result(cik, refresh).json()   # raises NotFound for bad CIK
        tickers = sub.get("tickers") or [""]
        return CompanyIdentity(cik, tickers[0], sub.get("name", ""), SUBMISSIONS_URL.format(cik=cik),
                               tick.retrieved_at)
    t = _normalise_ticker(q)
    for cik, ticker, title in rows:
        if ticker == t:
            return CompanyIdentity(cik, ticker, title, TICKERS_URL, tick.retrieved_at)
    close = difflib.get_close_matches(t, [r[1] for r in rows], n=5, cutoff=0.6)
    raise NotFound(f"ticker {query!r} not found in SEC company_tickers.json",
                   TICKERS_URL, f"did you mean: {', '.join(close)}" if close else
                   "the SEC list covers current registrants only; try the CIK")


def enrich_identity(ident: CompanyIdentity, submissions: dict[str, Any]) -> CompanyIdentity:
    return CompanyIdentity(ident.cik, ident.ticker, submissions.get("name") or ident.name, ident.source_url,
                           ident.retrieved_at, submissions.get("sic"), submissions.get("sicDescription"),
                           submissions.get("fiscalYearEnd"), tuple(submissions.get("exchanges") or ()))


@dataclass(frozen=True)
class FilingRecord:
    accession: str
    form: str
    filed: date
    report_date: date | None
    primary_document: str
    url: str


def recent_filings(submissions: dict[str, Any], forms: tuple[str, ...] = ("10-K", "10-Q"),
                   as_of: date | None = None) -> list[FilingRecord]:
    rec = submissions.get("filings", {}).get("recent", {})
    cik = int(submissions.get("cik", 0))
    out = []
    for i, form in enumerate(rec.get("form", [])):
        if form not in forms:
            continue
        filed = date.fromisoformat(rec["filingDate"][i])
        if as_of and filed > as_of:
            continue
        accn = rec["accessionNumber"][i]
        rd = rec.get("reportDate", [""] * (i + 1))[i]
        doc = rec.get("primaryDocument", [""] * (i + 1))[i]
        out.append(FilingRecord(accn, form, filed, date.fromisoformat(rd) if rd else None, doc,
                                f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{doc}"
                                if doc else filing_url(cik, accn)))
    return sorted(out, key=lambda r: r.filed, reverse=True)


# Financial-institution SIC ranges where FCFF DCF is inappropriate.
FINANCIAL_SIC = [(6000, 6399), (6700, 6799)]


def is_financial_sic(sic: str | None) -> bool:
    try:
        s = int(sic or "")
    except ValueError:
        return False
    return any(lo <= s <= hi for lo, hi in FINANCIAL_SIC)
