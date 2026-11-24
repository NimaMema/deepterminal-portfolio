"""Orchestrate a full valuation & market-expectations analysis for one case."""

from __future__ import annotations

from dataclasses import dataclass

from .data.case_file import Case
from .evidence import CitationAudit, citation_audit, enforce_point_in_time
from .finance.timevalue import cagr
from .financials.statements import StatementAnalysis, analyse
from .valuation import multiples as mx
from .valuation import reverse_dcf as rd
from .valuation.bridge import BridgeResult, equity_from_enterprise, market_enterprise_value
from .valuation.dcf import DCFResult, run_dcf
from .valuation.expectations import (GapItem, MisvaluationAssessment, OperatingHistory,
                                     assess_misvaluation, expectations_gap)
from .valuation.scenarios import (ScenarioSetResult, SensitivityGrid, TornadoBar, run_scenarios,
                                  sensitivity_grid, standard_shocks, tornado)
from .valuation.selection import MethodChoice, select_methods


@dataclass
class CaseAnalysis:
    case: Case
    statements: StatementAnalysis
    methods: list[MethodChoice]
    market: BridgeResult
    base_dcf: DCFResult
    base_bridge: BridgeResult
    scenarios: ScenarioSetResult
    reverse: list[rd.ReverseDCFResult]
    surface: list[rd.SurfacePoint]
    duration: rd.DurationResult
    sensitivity: SensitivityGrid
    tornado: list[TornadoBar]
    multiples: dict[str, mx.Multiple]
    comparables: mx.ComparableValuation | None
    multiple_context: dict[str, mx.HistoricalMultipleContext]
    gap: list[GapItem]
    assessment: MisvaluationAssessment
    citations: CitationAudit


def run_case(case: Case) -> CaseAnalysis:
    # Temporal discipline: nothing published after the analysis date may be used.
    enforce_point_in_time(case.all_evidence(), case.analysis_date)
    late = [p for p in case.history if p.filed and p.filed > case.analysis_date]
    if late:
        raise ValueError(f"financial periods filed after analysis date: {[p.fiscal_year for p in late]}")

    price = float(case.share_price.value)
    cap = case.capital
    stmts = analyse(case.history)
    latest = case.latest_period
    market = market_enterprise_value(price, cap)
    base_in = case.base_inputs
    base_dcf = run_dcf(base_in)
    base_bridge = equity_from_enterprise(base_dcf.enterprise_value, cap, price)
    scen = run_scenarios(case.scenarios, cap, price,
                         calibration_basis=case.probability_calibration_basis)

    tam = float(case.tam_final_year.value) if case.tam_final_year else None
    reverse = [rd.solve_implied(base_in, rd.growth_with_fade(), price, cap, tam),
               rd.solve_implied(base_in, rd.target_operating_margin(), price, cap, tam),
               rd.solve_implied(base_in, rd.discount_rate(), price, cap, tam)]
    margins = [round(base_in.ebit_margin[-1] + d, 4) for d in (-0.08, -0.06, -0.04, -0.02, 0.0,
                                                                 0.02, 0.04, 0.06, 0.08)]
    surface = rd.implied_surface(base_in, rd.target_operating_margin(), margins,
                                 rd.growth_with_fade(), price, cap)
    duration = rd.implied_growth_duration(base_in, base_in.revenue_growth[0], price, cap)

    r0 = base_in.discount_rate
    g0 = base_in.terminal_growth
    sens = sensitivity_grid(base_in, cap, price,
                            [round(r0 + d, 4) for d in (-0.02, -0.01, 0.0, 0.01, 0.02)],
                            [round(g0 + d, 4) for d in (-0.01, -0.005, 0.0, 0.005, 0.01)])
    torn = tornado(base_in, cap, price, standard_shocks(base_in))

    ebitda = latest.operating_income + latest.depreciation
    pe = mx.price_to_earnings(market.equity_value, latest.net_income)
    eps_growth = None
    first, last_fy = case.history[0], case.history[-1]
    if (len(case.history) >= 2 and first.net_income > 0 and last_fy.net_income > 0
            and first.diluted_shares > 0 and last_fy.diluted_shares > 0):
        eps_growth = cagr(first.net_income / first.diluted_shares,
                          last_fy.net_income / last_fy.diluted_shares, len(case.history) - 1)
    mults = {
        "P/E": pe,
        "PEG": mx.peg(pe, eps_growth) if eps_growth is not None else mx.Multiple("PEG", None, False, "no EPS history"),
        "EV/EBITDA": mx.ev_to_ebitda(market.enterprise_value, ebitda),
        "EV/Revenue": mx.ev_to_revenue(market.enterprise_value, latest.revenue),
        "P/B": mx.price_to_book(market.equity_value, latest.shareholders_equity),
        "FCF yield (after SBC)": mx.fcf_yield(
            latest.operating_cash_flow - latest.capex - latest.stock_based_comp, market.equity_value),
    }
    comps = None
    if len([p for p in case.peers_ev_ebitda if p.multiple]) >= 1 and ebitda > 0:
        comps = mx.comparable_valuation("EBITDA", ebitda, case.peers_ev_ebitda)
    ctx = {}
    for name, hist in case.multiple_history.items():
        cur = mults.get(name)
        if cur and cur.meaningful and len(hist) >= 2:
            ctx[name] = mx.historical_multiple_context(cur.value, hist)

    growth_sol = reverse[0].solutions[0] if reverse[0].solutions else None
    margin_sol = reverse[1].solutions[0] if reverse[1].solutions else None
    hist_growth = tuple(m.revenue_growth for m in stmts.metrics if m.revenue_growth is not None)
    hist_margin = tuple(m.operating_margin for m in stmts.metrics)
    gap = expectations_gap(growth_sol.revenue_cagr if growth_sol else None,
                           margin_sol.value if margin_sol else None,
                           OperatingHistory(hist_growth, hist_margin),
                           case.peers_operating, case.consensus)

    assessment = assess_misvaluation(
        case.share_price, scen, reverse, gap, case.evidence_quality, case.analysis_date,
        normalisation_note=case.normalisation_note, constraints_note=case.constraints_note,
        findings=case.findings)
    audit = citation_audit(case.all_evidence(), reference=case.analysis_date)
    return CaseAnalysis(case, stmts, select_methods(case.profile), market, base_dcf, base_bridge,
                        scen, reverse, surface, duration, sens, torn, mults, comps, ctx, gap,
                        assessment, audit)
