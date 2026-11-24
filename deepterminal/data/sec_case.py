"""Build a valuation :class:`Case` from real SEC filings plus a user-supplied price.

Provenance rules:

* every reported figure comes from SEC XBRL facts with its accession number,
  period, filing date and retrieval time (``FinancialPeriod.provenance`` and
  ``Case.figure_provenance``);
* the share price is supplied by the user with an as-of date and source
  (live market data is licensed — see docs/DATA_SOURCES.md);
* forecast assumptions are **model assumptions**. Unless overridden in a
  settings file they are derived mechanically from the company's own history
  with the rule written into each rationale. They are a neutral starting
  point, not a forecast, and the report says so;
* nothing is filled in when data is missing: the builder raises or records a
  limitation instead.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..evidence import DataQuality, EpistemicStatus, FigureProvenance, Source, SourcedValue
from ..finance.timevalue import cagr, linear_path
from ..financials.statements import FinancialPeriod
from ..validation import ValidationReport, validate_companyfacts
from ..valuation.bridge import CapitalStructure, OptionTranche
from ..valuation.dcf import DCFInputs, ExplicitReinvestment
from ..valuation.scenarios import Scenario
from ..valuation.selection import CompanyProfile
from . import sec_edgar as se
from .case_file import Case


class InsufficientData(ValueError):
    pass


@dataclass(frozen=True)
class PriceQuote:
    """A share price the user observed, with where and when."""

    value: float
    as_of: date
    source: str
    url: str | None = None
    currency: str = "USD"

    def validate(self, analysis_date: date) -> None:
        if self.value <= 0:
            raise ValueError("price must be positive")
        if not self.source.strip():
            raise ValueError("price source is required (e.g. 'Nasdaq official close')")
        if self.as_of > analysis_date:
            raise ValueError(f"price as-of {self.as_of} is after the analysis date {analysis_date}")


@dataclass
class ValuationSettings:
    """Forecast assumptions. ``discount_rate`` has no default: it is company-specific."""

    discount_rate: float
    discount_rate_rationale: str = "user-supplied"
    terminal_growth: float = 0.025
    terminal_roic: float | None = None            # default: equal to discount rate
    forecast_years: int = 7
    basis: str = "ttm"                           # "ttm" | "annual"
    base_growth: float | None = None              # default: historical revenue CAGR (≤3y), clamped
    base_margin: float | None = None              # default: latest operating margin
    tax_rate: float | None = None                 # default: median effective tax rate (≤3y)
    net_capex_pct_revenue: float | None = None    # default: median (capex − D&A)/revenue, ≥ 0
    nwc_pct_revenue_change: float | None = None   # default: median ΔNWC/ΔRevenue, clamped
    forward_eps: float | None = None              # user's own next-year EPS estimate (consensus is licensed data)
    bear: dict = field(default_factory=lambda: {"growth": -0.04, "margin": -0.03,
                                                "discount_rate": 0.01, "terminal_growth": -0.005})
    bull: dict = field(default_factory=lambda: {"growth": 0.03, "margin": 0.02, "discount_rate": -0.005})
    operating_cash_pct_revenue: float = 0.0
    include_noncurrent_securities: bool = True
    evidence_quality: str = "medium"
    rationales: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ValuationSettings":
        known = {f.name for f in fields(cls)}
        unknown = set(d) - known - {"_comment"}
        if unknown:
            raise ValueError(f"unknown settings keys: {sorted(unknown)}")
        return cls(**{k: v for k, v in d.items() if k in known})

    @classmethod
    def from_json(cls, path: str | Path, **overrides) -> "ValuationSettings":
        d = json.loads(Path(path).read_text())
        d.update({k: v for k, v in overrides.items() if v is not None})
        return cls.from_dict(d)


def _clamp(x: float, lo: float, hi: float) -> tuple[float, bool]:
    y = max(lo, min(hi, x))
    return y, y != x


def _effective_tax(facts: dict, as_of: date | None) -> tuple[float | None, list[FigureProvenance], str]:
    tax = se.annual_series(facts, "income_tax", as_of, "latest")
    pre = se.annual_series(facts, "pretax_income", as_of, "latest")
    ends = sorted(set(tax) & set(pre))[-3:]
    rates = [(e, tax[e].value / pre[e].value) for e in ends if pre[e].value > 0]
    if not rates:
        return None, [], ""
    cik = int(facts.get("cik", 0))
    provs = [se._prov("income_tax", tax[e], 1e6, cik, None) for e, _ in rates] + \
            [se._prov("pretax_income", pre[e], 1e6, cik, None) for e, _ in rates]
    detail = ", ".join(f"FY{e.year} {r:.1%}" for e, r in rates)
    return statistics.median(r for _, r in rates), provs, detail


def _history_reinvestment(history: list[FinancialPeriod], facts: dict, as_of: date | None) -> tuple[float | None, float | None, str, str]:
    net_capex = [(p.capex - p.depreciation) / p.revenue for p in history[-3:] if p.revenue > 0 and p.depreciation]
    ap = se.annual_series(facts, "accounts_payable", as_of, "latest")
    nwc_ratios = []
    for a, b in zip(history, history[1:]):
        if b.period_end in ap and a.period_end in ap and b.revenue != a.revenue:
            nwc_a = a.accounts_receivable + a.inventory - ap[a.period_end].value / 1e6
            nwc_b = b.accounts_receivable + b.inventory - ap[b.period_end].value / 1e6
            nwc_ratios.append((nwc_b - nwc_a) / (b.revenue - a.revenue))
    capex_pct = max(statistics.median(net_capex), 0.0) if net_capex else None
    nwc_pct = statistics.median(nwc_ratios[-3:]) if nwc_ratios else None
    return (capex_pct, nwc_pct,
            ", ".join(f"{x:.1%}" for x in net_capex),
            ", ".join(f"{x:.1%}" for x in nwc_ratios[-3:]))


STALE_BALANCE_DAYS = 400          # balance-sheet items older than this (vs the balance-sheet date) are not used


def build_capital_structure(facts: dict, bs_date: date, as_of: date | None, settings: ValuationSettings,
                            tax_rate: float, revenue: float, diluted_fallback: float,
                            retrieved: datetime | None) -> tuple[CapitalStructure, list[FigureProvenance], list[str]]:
    notes: list[str] = []
    provs: list[FigureProvenance] = []

    def at(name: str) -> FigureProvenance | None:
        p = se.latest_instant(facts, name, as_of, retrieved_at=retrieved, on_or_before=bs_date)
        if p and (bs_date - p.period_end).days > STALE_BALANCE_DAYS:
            # A company that stops tagging an item has usually stopped reporting it separately;
            # a value from years earlier would distort today's bridge.
            notes.append(f"{name} last tagged at {p.period_end}, more than a year before {bs_date}: not used")
            return None
        if p and p.period_end != bs_date:
            notes.append(f"{name} taken at {p.period_end} (not tagged at {bs_date})")
        if p:
            provs.append(p)
        return p

    cash = at("cash")
    if cash is None:
        raise InsufficientData("cash not reported in XBRL facts")
    ms_c = at("marketable_securities_current")
    ms_n = at("marketable_securities_noncurrent") if settings.include_noncurrent_securities else None
    cash_total = cash.value + (ms_c.value if ms_c else 0) + (ms_n.value if ms_n else 0)

    ltd = se.latest_instant(facts, "total_debt", as_of, retrieved_at=retrieved, on_or_before=bs_date)
    if ltd and ltd.concept.endswith(":LongTermDebt") and ltd.period_end == bs_date:
        provs.append(ltd)
        debt = ltd.value
        notes.append("debt = LongTermDebt (includes current maturities)")
    else:
        nc, cur = at("debt_noncurrent"), at("debt_current")
        debt = (nc.value if nc else 0) + (cur.value if cur else 0)
        notes.append("debt = LongTermDebtNoncurrent + LongTermDebtCurrent")
        if not nc and not cur:
            notes.append("no long-term debt tagged; debt treated as zero — verify in the filing")
    stb = at("short_term_borrowings")
    if stb:
        debt += stb.value
    lease = at("operating_lease_liabilities")
    if lease:
        notes.append(f"operating lease liabilities {lease.value:,.0f} not subtracted: US GAAP EBIT is already "
                     "after operating lease cost (subtracting would double-count)")
    mi = at("minority_interest")
    pref = at("preferred_equity")
    pens = at("pension_funded_status")
    pension_deficit = max(-pens.value, 0.0) * (1 - tax_rate) if pens else 0.0

    shares = se.shares_outstanding(facts, as_of, retrieved_at=retrieved)
    if shares and shares.value > 0.7 * diluted_fallback:
        provs.append(shares)
        basic = shares.value
        if shares.derivation:
            notes.append(f"basic shares: {shares.derivation}")
    else:
        basic = diluted_fallback
        notes.append("basic shares = latest diluted weighted-average shares (cover-page count missing or "
                     "covers only part of a multi-class structure); RSUs/options not added to avoid double counting")
    options: tuple[OptionTranche, ...] = ()
    rsus = 0.0
    if basic != diluted_fallback:
        opt, strike, rsu = at("options_outstanding"), at("options_strike"), at("rsus_unvested")
        if opt and strike:
            # options_outstanding was scaled by 1e6 as shares; strike must be per share (unscaled)
            options = (OptionTranche(opt.value, strike.value * 1e6),)
        if rsu:
            rsus = rsu.value
    cap = CapitalStructure(
        basic_shares=basic, cash_and_investments=cash_total,
        operating_cash_requirement=settings.operating_cash_pct_revenue * revenue,
        total_debt=debt, debt_includes_leases=False, lease_liabilities=0.0, ebit_after_lease_cost=True,
        pension_deficit_after_tax=pension_deficit, preferred_equity=pref.value if pref else 0.0,
        minority_interest=mi.value if mi else 0.0, rsus=rsus, options=options)
    return cap, provs, notes


def is_synthetic_facts(facts: dict[str, Any]) -> bool:
    """Synthetic fixtures carry a "_comment" marker; genuine SEC responses never do."""
    return "SYNTHETIC" in str(facts.get("_comment", "")).upper()


def _source_for(p: FigureProvenance, ident_name: str, synthetic: bool = False) -> Source:
    return Source(se.accession_ref(p.accession), f"{ident_name} {p.form} (accession {p.accession})",
                  "SYNTHETIC fixture in SEC format" if synthetic else "U.S. Securities and Exchange Commission — EDGAR",
                  None if synthetic else p.source_url, p.filed, p.retrieved_at, p.period_end, p.accession,
                  "synthetic fixture (not a real filing)" if synthetic else
                  "US government public data; SEC fair-access policy", synthetic=synthetic)


def _walk(p: FigureProvenance):
    yield p
    for i in p.inputs:
        yield from _walk(i)


def build_sec_case(facts: dict[str, Any], identity: se.CompanyIdentity, price: PriceQuote | None,
                   settings: ValuationSettings, analysis_date: date | None = None,
                   retrieved_at: datetime | None = None, max_years: int = 6) -> Case:
    analysis_date = analysis_date or date.today()
    if price is not None:
        price.validate(analysis_date)
    se.check_supported(facts)
    if se.is_financial_sic(identity.sic):
        raise se.UnsupportedFiler(
            f"SIC {identity.sic} ({identity.sic_description}) is a financial institution: FCFF DCF is "
            "inappropriate (debt is operating). Use residual-income / P/B methods (not yet wired to SEC data).")
    as_of = analysis_date
    synthetic = is_synthetic_facts(facts)
    history = se.build_periods(facts, as_of=as_of, retrieved_at=retrieved_at)[-max_years:]
    if len(history) < 2:
        raise InsufficientData(f"only {len(history)} complete fiscal years in XBRL facts; need ≥2")
    ttm = se.build_ttm_period(facts, as_of=as_of, retrieved_at=retrieved_at)
    use_ttm = settings.basis == "ttm" and ttm is not None and ttm.period_end > history[-1].period_end
    basis = ttm if use_ttm else history[-1]
    notes: list[str] = []
    if settings.basis == "ttm" and not use_ttm:
        notes.append("TTM basis requested but not available beyond the last fiscal year; using annual basis")
    validation = validate_companyfacts(facts, as_of, analysis_date)

    # ── data-derived assumptions (each with its rule) ──
    rationales: dict[str, str] = {}
    sources_for: dict[str, list[FigureProvenance]] = {}
    tax, tax_provs, tax_detail = _effective_tax(facts, as_of)
    if settings.tax_rate is not None:
        tax_rate = settings.tax_rate
        rationales["tax_rate"] = settings.rationales.get("tax_rate", "user-supplied")
    elif tax is not None and tax < 0:
        tax_rate = 0.21
        rationales["tax_rate"] = (f"US federal statutory rate: the median effective rate ({tax_detail}) is negative, "
                                  "reflecting tax benefits that are not a sustainable long-run rate")
        sources_for["tax_rate"] = tax_provs
    elif tax is not None:
        tax_rate, clamped = _clamp(tax, 0.0, 0.35)
        rationales["tax_rate"] = (f"median effective tax rate of last {len(tax_provs) // 2} fiscal years "
                                  f"({tax_detail}){', clamped to 0–35%' if clamped else ''}")
        sources_for["tax_rate"] = tax_provs
    else:
        tax_rate = 0.21
        rationales["tax_rate"] = "US federal statutory rate (no positive pre-tax income to measure an effective rate)"

    years = min(3, len(history) - 1)
    if settings.base_growth is not None:
        g0 = settings.base_growth
        rationales["base_growth"] = settings.rationales.get("base_growth", "user-supplied")
    else:
        raw = cagr(history[-1 - years].revenue, history[-1].revenue, years)
        g0, clamped = _clamp(raw, -0.10, 0.40)
        rationales["base_growth"] = (f"{years}-year historical revenue CAGR FY{history[-1 - years].fiscal_year}–"
                                     f"FY{history[-1].fiscal_year} = {raw:.1%}{', clamped to [−10%, 40%]' if clamped else ''}; "
                                     f"fades linearly to terminal growth over {settings.forecast_years} years")
        sources_for["base_growth"] = [history[-1 - years].provenance["revenue"], history[-1].provenance["revenue"]]
    m0 = settings.base_margin if settings.base_margin is not None else basis.operating_income / basis.revenue
    rationales["base_margin"] = (settings.rationales.get("base_margin", "user-supplied") if settings.base_margin is not None
                                 else f"latest operating margin ({'TTM' if use_ttm else f'FY{basis.fiscal_year}'}) "
                                      f"{m0:.1%}, held flat")
    if settings.base_margin is None:
        sources_for["base_margin"] = [basis.provenance["operating_income"], basis.provenance["revenue"]]
    capex_pct, nwc_pct, capex_detail, nwc_detail = _history_reinvestment(history, facts, as_of)
    if settings.net_capex_pct_revenue is not None:
        capex_pct = settings.net_capex_pct_revenue
        rationales["net_capex_pct_revenue"] = settings.rationales.get("net_capex_pct_revenue", "user-supplied")
    elif capex_pct is None:
        raise InsufficientData("depreciation not reported; cannot derive net capex — supply net_capex_pct_revenue")
    else:
        rationales["net_capex_pct_revenue"] = f"median (capex − D&A)/revenue of last 3 fiscal years ({capex_detail}), floored at 0"
    if settings.nwc_pct_revenue_change is not None:
        nwc_pct = settings.nwc_pct_revenue_change
        rationales["nwc_pct_revenue_change"] = settings.rationales.get("nwc_pct_revenue_change", "user-supplied")
    elif nwc_pct is None:
        nwc_pct = 0.0
        rationales["nwc_pct_revenue_change"] = "0: receivables/inventory/payables history insufficient (limitation)"
    else:
        nwc_pct, clamped = _clamp(nwc_pct, -0.5, 0.5)
        rationales["nwc_pct_revenue_change"] = (f"median ΔNWC/ΔRevenue (receivables + inventory − payables) "
                                                f"of recent years ({nwc_detail}){', clamped' if clamped else ''}")
    r = settings.discount_rate
    t_roic = settings.terminal_roic if settings.terminal_roic is not None else r
    rationales["discount_rate"] = settings.discount_rate_rationale
    rationales["terminal_growth"] = settings.rationales.get(
        "terminal_growth", "below long-run nominal economic growth; generic model assumption")
    rationales["terminal_roic"] = settings.rationales.get(
        "terminal_roic", "user-supplied" if settings.terminal_roic is not None
        else "equal to the discount rate: no excess returns on new investment in perpetuity (conservative default)")

    n = settings.forecast_years

    def scen(name: str, d: dict, narrative: str) -> Scenario:
        g = g0 + d.get("growth", 0.0)
        m = m0 + d.get("margin", 0.0)
        dr = r + d.get("discount_rate", 0.0)
        tg = settings.terminal_growth + d.get("terminal_growth", 0.0)
        roic = min(t_roic, dr) if name == "bear" else t_roic
        inp = DCFInputs(basis.revenue, tuple(linear_path(g, tg, n)), (m,) * n, tax_rate, dr, tg, roic,
                        ExplicitReinvestment(capex_pct, nwc_pct), terminal_ebit_margin=m)
        return Scenario(name, narrative, inp,
                        key_dependencies=("revenue growth path", "operating margin", "discount rate"),
                        source_refs=(basis.source_ref,))
    deltas = lambda d: ", ".join(f"{k} {v:+.1%}" for k, v in d.items())
    scenarios = [
        scen("bear", settings.bear, f"Mechanical stress from the base case ({deltas(settings.bear)}); "
                                    "terminal ROIC capped at the discount rate. Not a forecast."),
        scen("base", {}, f"Mechanical baseline: growth starts at {g0:.1%} and fades to {settings.terminal_growth:.1%}; "
                         f"operating margin held at {m0:.1%}. A neutral starting point, not a forecast."),
        scen("bull", settings.bull, f"Mechanical upside from the base case ({deltas(settings.bull)}). Not a forecast."),
    ]

    # ── sources & evidence ──
    sources: dict[str, Source] = {}
    for p in history + ([ttm] if ttm else []):
        for prov in p.provenance.values():
            for leaf in _walk(prov):
                sources.setdefault(se.accession_ref(leaf.accession), _source_for(leaf, identity.name, synthetic))
    cap, cap_provs, cap_notes = build_capital_structure(
        facts, basis.period_end, as_of, settings, tax_rate, basis.revenue, basis.diluted_shares, retrieved_at)
    for prov in cap_provs + tax_provs:
        sources.setdefault(se.accession_ref(prov.accession), _source_for(prov, identity.name, synthetic))
    price_src = None
    if price is not None:
        price_src = Source("PRICE", price.source, "user-supplied (not independently verified)", price.url,
                           price.as_of, None, None, None, "as stated by user")
        sources["PRICE"] = price_src
    companyfacts_src = Source("SEC-COMPANYFACTS", f"XBRL companyfacts CIK {identity.cik:010d}",
                              "U.S. Securities and Exchange Commission — data.sec.gov",
                              None if synthetic else se.COMPANYFACTS_URL.format(cik=identity.cik), None, retrieved_at,
                              licence="synthetic fixture (not real data)" if synthetic else "US government public data",
                              synthetic=synthetic)
    sources["SEC-COMPANYFACTS"] = companyfacts_src

    def assumption_sv(key: str, value: float, unit: str = "%") -> SourcedValue:
        provs = sources_for.get(key, [])
        srcs = tuple(sources[se.accession_ref(p.accession)] for p in provs if se.accession_ref(p.accession) in sources)
        status = EpistemicStatus.ANALYTICAL_INFERENCE if srcs else EpistemicStatus.MODEL_ASSUMPTION
        return SourcedValue(key, value, status, unit=unit, sources=srcs, rationale=rationales[key])
    assumptions = [assumption_sv("discount_rate", r), assumption_sv("terminal_growth", settings.terminal_growth),
                   assumption_sv("terminal_roic", t_roic), assumption_sv("tax_rate", tax_rate),
                   assumption_sv("base_growth", g0), assumption_sv("base_margin", m0),
                   assumption_sv("net_capex_pct_revenue", capex_pct),
                   assumption_sv("nwc_pct_revenue_change", nwc_pct)]

    profile = CompanyProfile(
        sector=identity.sic_description or "", profitable=basis.operating_income > 0,
        positive_fcf=(basis.operating_cash_flow - basis.capex) > 0, cyclical=False,
        high_growth=g0 > 0.20, years_of_history=len(history), peers_available=0, multiple_history_years=0)
    notes += cap_notes
    notes.append("cyclicality not assessed automatically: for cyclical businesses supply a through-cycle "
                 "base_margin in the settings file")
    quality = DataQuality(settings.evidence_quality)
    return Case(
        case_id=f"SEC-{identity.ticker}-{analysis_date.isoformat()}", company_name=identity.name,
        ticker=identity.ticker, currency="USD", units="millions (except per-share values)",
        analysis_date=analysis_date, synthetic=synthetic,
        disclaimer=("SYNTHETIC FIXTURE in SEC EDGAR format. Every number is invented for testing; it describes "
                    "no real company.") if synthetic else "", sources=sources,
        share_price=SourcedValue("share price", price.value, EpistemicStatus.HISTORICAL_FACT, unit="USD/share",
                                 as_of=price.as_of, sources=(price_src,), quality=DataQuality.MEDIUM)
        if price is not None else None,
        capital=cap, capital_source_refs=tuple(sorted({se.accession_ref(p.accession) for p in cap_provs})),
        history=history, profile=profile, scenarios=scenarios, assumptions=assumptions,
        peers_ev_ebitda=[], peers_operating=[], multiple_history={}, tam_final_year=None, consensus=None,
        evidence_quality=quality, findings=[],
        normalisation_note=("No normalisation applied; margins taken as reported "
                            f"({'TTM' if use_ttm else 'latest fiscal year'})."),
        constraints_note="", ttm=ttm if use_ttm else None, figure_provenance=cap_provs + tax_provs,
        data_validation=validation, identity=identity, notes=notes)
