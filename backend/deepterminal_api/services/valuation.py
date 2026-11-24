"""Valuation Laboratory service: wraps the tested deterministic engine for the API.

Nothing here computes finance itself — it builds a Case from SEC data (``build_sec_case``),
runs ``deepterminal.pipeline.run_case`` (or scenario-only valuation when no price is
available) and serialises every intermediate so the UI can show its working.
"""

from __future__ import annotations

import time

from dataclasses import asdict, fields
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepterminal.data import sec_edgar as se
from deepterminal.data.sec_case import PriceQuote, ValuationSettings, build_sec_case
from deepterminal.pipeline import CaseAnalysis, run_case
from deepterminal.reporting.provenance import provenance_rows
from deepterminal.valuation import multiples as mx
from deepterminal.valuation.bridge import equity_from_enterprise
from deepterminal.valuation.dcf import DCFResult, run_dcf
from deepterminal.valuation.scenarios import run_scenarios, sensitivity_grid, standard_shocks, tornado
from deepterminal.valuation.sotp import AssetLine, Segment, adjusted_net_asset_value, sum_of_the_parts

from ..config import get_settings
from ..models import Company, PriceQuote as PriceRow, ValuationRun
from . import companies as cs
from .gateway import DataUnavailable

SETTING_FIELDS = {f.name for f in fields(ValuationSettings)}


def latest_price(db: Session, company: Company, as_of: date | None = None) -> PriceRow | None:
    q = select(PriceRow).where(PriceRow.company_id == company.id).order_by(PriceRow.as_of.desc(), PriceRow.id.desc())
    if as_of:
        q = q.where(PriceRow.as_of <= as_of)
    return db.scalars(q).first()


def identity(company: Company) -> se.CompanyIdentity:
    return se.CompanyIdentity(company.cik, company.ticker or "", company.name, sic=company.sic,
                              sic_description=company.sic_description)


def _dcf_dict(d: DCFResult) -> dict:
    i = d.inputs
    return {"enterprise_value": d.enterprise_value, "pv_explicit": d.pv_explicit, "terminal_value": d.terminal_value,
            "pv_terminal": d.pv_terminal, "terminal_share": d.terminal_share, "terminal_fcff": d.terminal_fcff,
            "warnings": list(d.warnings),
            "inputs": {"base_revenue": i.base_revenue, "revenue_growth": list(i.revenue_growth),
                       "ebit_margin": list(i.ebit_margin), "tax_rate": i.tax_rate, "discount_rate": i.discount_rate,
                       "terminal_growth": i.terminal_growth, "terminal_roic": i.terminal_roic,
                       "terminal_ebit_margin": i.terminal_ebit_margin, "mid_year": i.mid_year,
                       "reinvestment": asdict(i.reinvestment) | {"type": type(i.reinvestment).__name__}},
            "years": [asdict(y) for y in d.years]}


def serialize(a: CaseAnalysis) -> dict[str, Any]:
    c = a.case
    s = a.scenarios
    return {
        "company": c.company_name, "ticker": c.ticker, "synthetic": c.synthetic, "analysis_date": c.analysis_date.isoformat(),
        "basis": c.latest_label,
        "price": {"value": c.share_price.value, "as_of": c.share_price.as_of.isoformat(),
                  "source": c.share_price.sources[0].title if c.share_price.sources else None},
        "market": {"enterprise_value": a.market.enterprise_value, "market_cap": a.market.equity_value,
                   "diluted_shares": a.market.diluted_shares, "ledger": a.market.ledger},
        "capital_structure": {**asdict(c.capital), "options": [asdict(o) for o in c.capital.options],
                              "excess_cash": c.capital.excess_cash},
        "methods": [{"method": m.method.value, "role": m.role, "reason": m.reason} for m in a.methods],
        "assumptions": [v.to_dict() for v in c.assumptions],
        "scenarios": [{"name": o.scenario.name, "narrative": o.scenario.narrative,
                       "dependencies": list(o.scenario.key_dependencies), "per_share": o.per_share,
                       "equity_value": o.bridge.equity_value, "diluted_shares": o.bridge.diluted_shares,
                       "bridge": o.bridge.ledger, "dcf": _dcf_dict(o.dcf)} for o in s.outcomes],
        "weighted_value": s.weighted_value, "scenario_warnings": list(s.warnings),
        "reverse_dcf": [{"lever": r.lever, "label": r.lever_label, "unit": r.unit, "status": r.status,
                         "statement": r.statement(), "solutions": [{"value": p.value, "final_revenue": p.final_revenue,
                                                                   "revenue_cagr": p.revenue_cagr, "final_margin": p.final_margin,
                                                                   "cumulative_fcff": p.cumulative_fcff,
                                                                   "cumulative_reinvestment": p.cumulative_reinvestment,
                                                                   "implied_market_share": p.implied_market_share,
                                                                   "fcff_path": [y.fcff for y in p.model.years],
                                                                   "revenue_path": [y.revenue for y in p.model.years]}
                                                                  for p in r.solutions],
                         "held_constant": r.held_constant, "notes": list(r.notes), "bounds": r.bounds,
                         "target_enterprise_value": r.target_enterprise_value} for r in a.reverse],
        "iso_value": [{"margin": p.x, "growth": list(p.y_solutions)} for p in a.surface],
        "growth_duration": asdict(a.duration),
        "sensitivity": {"rows": a.sensitivity.rows, "cols": a.sensitivity.cols, "values": a.sensitivity.values,
                        "row_label": a.sensitivity.row_label, "col_label": a.sensitivity.col_label},
        "tornado": [asdict(b) | {"swing": b.swing} for b in a.tornado],
        "multiples": {k: asdict(v) for k, v in a.multiples.items()},
        "comparables": asdict(a.comparables) if a.comparables else None,
        "expectations_gap": [asdict(g) for g in a.gap],
        "assessment": {"verdict": a.assessment.verdict.value, "reasons": list(a.assessment.reasons),
                       "price_position": a.assessment.price_position, "margin_of_safety": a.assessment.margin_of_safety,
                       "upside_to_base": a.assessment.upside_to_base, "downside_to_bear": a.assessment.downside_to_bear,
                       "steps": [asdict(st) for st in a.assessment.steps], "caveat": a.assessment.caveat},
        "validation": [asdict(ch) for ch in c.data_validation.checks] if c.data_validation else [],
        "notes": list(c.notes), "citation_findings": [f.__dict__ for f in a.citations.findings],
        "provenance_count": len(provenance_rows(c)),
    }


def _settings(overrides: dict[str, Any]) -> ValuationSettings:
    clean = {k: v for k, v in (overrides or {}).items() if k in SETTING_FIELDS and v is not None and v != ""}
    if "discount_rate" not in clean:
        raise DataUnavailable("not_configured", "A discount rate is required.",
                              "DEEPTERMINAL does not invent a company's cost of capital; enter your WACC estimate.")
    return ValuationSettings.from_dict(clean)


_LAST_PRICE_ATTEMPT: dict[int, float] = {}


def ps_due(company_id: int, every_seconds: int = 6 * 3600) -> bool:
    """Automatic free-price lookups run at most every six hours per company."""
    t = _LAST_PRICE_ATTEMPT.get(company_id)
    return t is None or time.monotonic() - t > every_seconds


def value_company(db: Session, company: Company, overrides: dict[str, Any], price: dict | None = None,
                  as_of: date | None = None) -> dict[str, Any]:
    facts, meta = cs.companyfacts(company)
    settings = _settings(overrides)
    quote = None
    price_fetch: dict | None = None
    if price and price.get("value"):
        quote = PriceQuote(float(price["value"]), date.fromisoformat(str(price["as_of"])), str(price.get("source") or ""),
                           price.get("url"))
    else:
        row = latest_price(db, company, as_of)
        if get_settings().public_demo and not company.synthetic:
            price_fetch = {"status": "not_configured",
                           "message": "Public demo: no live price fetch. The price shown is the recorded SEC Form 4 "
                                      "insider trade price from the snapshot (a real dated trade, not an official close)."}
        elif (not company.synthetic and not as_of and (row is None or (date.today() - row.as_of).days > 4)
                and ps_due(company.id)):
            # No recent price: try the free end-of-day source once. A failure is reported, never papered over.
            from . import prices as ps
            _LAST_PRICE_ATTEMPT[company.id] = time.monotonic()
            try:
                fetched = ps.fetch_prices(db, company, fiscal_year_ends=True)
                price_fetch = {"status": "ok", "message": f"Latest close fetched from {fetched['provider']} ({fetched['latest']['as_of']}).",
                               "attribution": fetched["attribution"]}
                row = latest_price(db, company, as_of)
            except DataUnavailable as e:
                price_fetch = {"status": e.status, "message": e.message, "hint": e.hint}
        if row:
            quote = PriceQuote(row.value, row.as_of, row.source, row.url)
    analysis_date = as_of or (max(date.today(), quote.as_of) if quote else date.today())
    if company.synthetic and not as_of:
        analysis_date = max(date(2026, 10, 28), quote.as_of if quote else date(2026, 10, 28))
    try:
        case = build_sec_case(facts, identity(company), quote, settings, analysis_date=analysis_date,
                              retrieved_at=meta.retrieved_at)
    except (ValueError, se.UnsupportedFiler) as e:
        raise DataUnavailable("unsupported", str(e)) from e
    if quote is not None:
        out = serialize(run_case(case))
        out["price_fetch"] = price_fetch
        if settings.forward_eps:
            fpe = asdict(mx.forward_pe(quote.value, settings.forward_eps))
            fpe["reason"] = fpe["reason"] or "uses your forward EPS estimate (model assumption)"
        else:
            fpe = {"name": "Forward P/E", "value": None, "meaningful": False,
                   "reason": "needs a forward EPS estimate: consensus estimates are licensed data and not connected; "
                             "enter your own estimate to compute it"}
        out["multiples"]["Forward P/E"] = fpe
        out["settings"] = asdict(settings)
        return out
    # intrinsic only — no price, no market expectations
    sc = run_scenarios(case.scenarios, case.capital, share_price=1e-9)
    base = case.base_inputs
    grid = sensitivity_grid(base, case.capital, 1e-9, [round(base.discount_rate + d, 4) for d in (-.02, -.01, 0, .01, .02)],
                            [round(base.terminal_growth + d, 4) for d in (-.01, -.005, 0, .005, .01)])
    torn = tornado(base, case.capital, 1e-9, standard_shocks(base))
    return {"company": case.company_name, "ticker": case.ticker, "synthetic": case.synthetic,
            "analysis_date": case.analysis_date.isoformat(), "basis": case.latest_label, "price": None,
            "market": None, "assumptions": [v.to_dict() for v in case.assumptions],
            "scenarios": [{"name": o.scenario.name, "narrative": o.scenario.narrative,
                           "dependencies": list(o.scenario.key_dependencies), "per_share": o.per_share,
                           "equity_value": o.bridge.equity_value, "diluted_shares": o.bridge.diluted_shares,
                           "bridge": o.bridge.ledger, "dcf": _dcf_dict(o.dcf)} for o in sc.outcomes],
            "sensitivity": {"rows": grid.rows, "cols": grid.cols, "values": grid.values, "row_label": grid.row_label,
                            "col_label": grid.col_label},
            "tornado": [asdict(b) | {"swing": b.swing} for b in torn],
            "reverse_dcf": [], "expectations_gap": [], "multiples": {},
            "assessment": None, "validation": [asdict(ch) for ch in case.data_validation.checks],
            "notes": list(case.notes) + ["No timestamped share price: market-implied expectations, multiples and the "
                                         "misvaluation verdict are unavailable. Options dilution excluded."],
            "settings": asdict(settings), "price_fetch": price_fetch,
            "unavailable": {"status": "no_price",
                            "message": "No share price: enter one with its date and source to compute market expectations."
                            + (f" Automatic free price: {price_fetch['message']}" if price_fetch else "")}}


def save_run(db: Session, company: Company, label: str | None, settings: dict, price: dict | None, result: dict) -> int:
    row = ValuationRun(company_id=company.id, label=label, settings=settings, price=price or {}, result=result)
    db.add(row)
    db.commit()
    return row.id


def shock_scenario(db: Session, company: Company, overrides: dict, revenue_shock: float, margin_shock: float,
                   years: int, price_offset: float = 0.0) -> dict[str, Any]:
    """Supply-chain disruption: lose ``revenue_shock`` of volume and ``margin_shock`` of margin for ``years``,
    partially offset by price increases (``price_offset`` share of lost revenue recovered at full margin)."""
    facts, meta = cs.companyfacts(company)
    settings = _settings(overrides)
    case = build_sec_case(facts, identity(company), None, settings,
                          analysis_date=date(2026, 10, 28) if company.synthetic else date.today(),
                          retrieved_at=meta.retrieved_at)
    base = case.base_inputs
    n = base.years
    growth = list(base.revenue_growth)
    margins = list(base.ebit_margin)
    net_rev = -revenue_shock * (1 - price_offset)
    for i in range(min(years, n)):
        margins[i] = margins[i] - margin_shock + (revenue_shock * price_offset * 0.5)
    if years > 0:
        growth[0] = (1 + growth[0]) * (1 + net_rev) - 1
        if years < n:
            growth[years] = (1 + growth[years]) / (1 + net_rev) - 1   # volume recovers after the disruption
    shocked = base.with_changes(revenue_growth=tuple(growth), ebit_margin=tuple(margins))
    b, s = run_dcf(base), run_dcf(shocked)
    bv = equity_from_enterprise(b.enterprise_value, case.capital, 0)
    sv = equity_from_enterprise(s.enterprise_value, case.capital, 0)
    rows = [{"year": yb.year, "revenue_base": yb.revenue, "revenue_shocked": ys.revenue, "fcff_base": yb.fcff,
             "fcff_shocked": ys.fcff, "margin_base": yb.ebit_margin, "margin_shocked": ys.ebit_margin}
            for yb, ys in zip(b.years, s.years)]
    return {"params": {"revenue_shock": revenue_shock, "margin_shock": margin_shock, "years": years,
                       "price_offset": price_offset},
            "base_ev": b.enterprise_value, "shocked_ev": s.enterprise_value, "ev_change": s.enterprise_value / b.enterprise_value - 1,
            "base_per_share": bv.value_per_share, "shocked_per_share": sv.value_per_share, "rows": rows,
            "explanation": "Shortages can cut volume (revenue_shock) yet raise prices (price_offset recovers part of the "
                           "lost revenue at higher margin). Which effect dominates depends on pricing power; set the "
                           "offset from evidence, not by default.", "synthetic": company.synthetic}


def sotp(payload: dict) -> dict:
    r = sum_of_the_parts([Segment(**s) for s in payload["segments"]], payload.get("annual_corporate_cost", 0.0),
                         payload.get("tax_rate", 0.0), payload.get("discount_rate"), payload.get("growth", 0.0))
    return asdict(r)


def nav(payload: dict) -> dict:
    r = adjusted_net_asset_value([AssetLine(**a) for a in payload["assets"]], payload["liabilities"])
    return asdict(r)
