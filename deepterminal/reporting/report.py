"""Render the 24-section investment research report (spec §13) as Markdown.

Sections backed by an implemented engine are filled from deterministic
outputs. Sections whose research module is not yet implemented say so
explicitly — the report never fills a gap with generated opinion.
"""

from __future__ import annotations

from ..pipeline import CaseAnalysis
from .provenance import provenance_rows

NOT_ASSESSED = ("**Not assessed.** The research module for this section is not implemented in "
                "this version (see docs/ROADMAP.md, milestone {m}). No conclusion is drawn.")

SECTIONS = (
    "Executive summary", "Company identity and legitimacy", "Business model", "Financial strength",
    "Accounting quality", "Management and governance", "Products and customer satisfaction",
    "Competitors and industry structure", "Supply-chain analysis", "Revenue and demand sustainability",
    "Historical SEC filing changes", "Market sentiment and hype", "Institutional and insider activity",
    "Historical company analogues", "Macroeconomic and regulatory exposure", "Valuation methodology",
    "Reverse DCF and market expectations", "Bear/base/bull scenarios", "Major uncertainties",
    "Potential catalysts", "Counterarguments", "Evidence coverage and limitations",
    "Final analytical conclusion", "Source bibliography",
)


def _pct(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def _num(x: float | None, d: int = 0) -> str:
    return "n/a" if x is None else f"{x:,.{d}f}"


def render_report(a: CaseAnalysis) -> str:
    c = a.case
    s = a.scenarios
    asmt = a.assessment
    out: list[str] = []
    w = out.append
    w(f"# DEEPTERMINAL research report — {c.company_name} ({c.ticker})\n")
    w(f"*Case `{c.case_id}` · analysis date {c.analysis_date} · share price {c.share_price.value:,.2f} "
      f"{c.currency} as of {c.share_price.as_of} · monetary figures in {c.currency} {c.units}*\n")
    if c.synthetic:
        w(f"> ⚠️ **SYNTHETIC DATA.** {c.disclaimer}\n")
    w("> This report is analysis, not investment advice. It makes no buy/sell recommendation.\n")

    sec = iter(enumerate(SECTIONS, start=1))

    def h() -> None:
        n, title = next(sec)
        w(f"\n## {n}. {title}\n")

    # 1 Executive summary
    h()
    flags = a.statements.flags
    w("**Is this a good business?** Partially assessed. Financial-statement evidence only: "
      f"latest operating margin {_pct(a.statements.latest().operating_margin)}, "
      f"FCF after SBC {_num(a.statements.latest().fcf_after_sbc)}, "
      f"{len(flags)} statement flag(s) for review. Product, competitive, management and supply-chain "
      "quality are not yet assessed, so no overall quality conclusion is drawn.\n")
    lo, hi = s.value_range
    w(f"**What is a defensible range of economic value?** {_num(lo, 2)}–{_num(hi, 2)} per share across "
      f"bear/base/bull scenarios (base {_num(s.by_name('base').per_share, 2)}), conditional on the "
      "stated assumptions in §18. " + ("No probability weighting is applied because no calibrated "
                                        "probabilities were supplied." if s.weighted_value is None
                                        else f"Probability-weighted value {_num(s.weighted_value, 2)} "
                                             f"(calibration: {s.calibration_basis})."))
    w("")
    g, m = a.reverse[0], a.reverse[1]
    w("**What expectations are embedded in the current price?** " + g.statement() + " " +
      (f"Alternatively, holding growth at the base path, the price requires a steady-state "
       f"operating margin of {_pct(m.solutions[0].value)}." if m.solutions else m.statement()))
    w("")
    w("**What might the market be overlooking?** " + (
        "; ".join(f.text for f in c.findings if f.step == "overlooked") or
        "Not assessed: no sourced research findings were supplied. The Thesis Challenger and "
        "research agents are required before anything can be claimed here."))
    w("")
    inval = [o.scenario.key_dependencies for o in s.outcomes if o.scenario.name == "base"][0]
    w("**What evidence could invalidate the thesis?** The base case depends on: " +
      ("; ".join(inval) or "dependencies not stated") +
      f". The largest valuation sensitivity is **{a.tornado[0].assumption}** "
      f"({_num(a.tornado[0].low_value, 2)}–{_num(a.tornado[0].high_value, 2)} per share).\n")
    w(f"**Qualified conclusion:** {asmt.verdict.value}. " + "; ".join(asmt.reasons) + ".")

    # 2-3
    h(); w(NOT_ASSESSED.format(m="Intermediate: corporate legitimacy module"))
    h(); w(f"Sector (from case file): {c.profile.sector or 'not stated'}. "
           + NOT_ASSESSED.format(m="Intermediate: business-model research agent"))

    # 4 Financial strength
    h()
    w("| FY | Revenue | Growth | Op. margin | FCF | FCF after SBC | Net debt | Interest cover | ROE |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for p, mt in zip(c.history, a.statements.metrics):
        w(f"| {mt.fiscal_year} | {_num(p.revenue)} | {_pct(mt.revenue_growth)} | {_pct(mt.operating_margin)} "
          f"| {_num(mt.fcf)} | {_num(mt.fcf_after_sbc)} | {_num(mt.net_debt)} | "
          f"{_num(mt.interest_coverage, 1)}x | {_pct(mt.roe)} |")
    if c.ttm is not None:
        t = c.ttm
        w(f"| TTM to {t.period_end} | {_num(t.revenue)} | | {_pct(t.operating_income / t.revenue)} | "
          f"{_num(t.operating_cash_flow - t.capex)} | {_num(t.operating_cash_flow - t.capex - t.stock_based_comp)} "
          f"| {_num(t.total_debt - t.cash)} | | |")
    if c.identity is not None:
        w(f"\nSource: SEC EDGAR XBRL companyfacts for CIK {c.identity.cik:010d}; each figure's concept, period, "
          "accession, filing date and retrieval time are listed in §22. Metrics computed by "
          "`deepterminal.financials.statements.analyse`.")
    else:
        w("\nSource: case-file financial history (see §24). Metrics computed by "
          "`deepterminal.financials.statements.analyse`.")

    # 5 Accounting quality
    h()
    w("Automated statement checks (analytical inferences that direct further review, not findings "
      "of misconduct):\n")
    if flags:
        for f in flags:
            w(f"- FY{f.fiscal_year} `{f.code}` ({f.severity}): {f.message}")
    else:
        w("- No automated flags triggered.")
    w("\nRevenue-recognition policy, reserves, auditor changes and related-party review: "
      + NOT_ASSESSED.format(m="Intermediate: forensic accounting agent"))

    for _, milestone in zip(range(6), ("Intermediate: management analysis",
                                        "Intermediate: customer review trends",
                                        "Intermediate: competitor intelligence",
                                        "Intermediate: supply-chain research",
                                        "Intermediate: demand intelligence",
                                        "Intermediate: historical filing comparisons")):
        h(); w(NOT_ASSESSED.format(m=milestone))
    h(); w(NOT_ASSESSED.format(m="Advanced: narrative-versus-fundamentals"))
    h(); w(NOT_ASSESSED.format(m="Intermediate: insider & institutional data (licensed source required)"))
    h(); w(NOT_ASSESSED.format(m="Advanced: historical analogue selection"))
    h(); w(NOT_ASSESSED.format(m="Intermediate: macro & policy exposure"))

    # 16 Valuation methodology
    h()
    w("| Method | Role | Reason |\n|---|---|---|")
    for mc in a.methods:
        w(f"| {mc.method.value} | {mc.role} | {mc.reason} |")
    w("\n**Market-implied enterprise value bridge** (price × diluted shares, then claims):\n")
    w(f"- Diluted shares (treasury stock method at market price): {_num(a.market.diluted_shares, 1)}")
    w(f"- Market capitalisation: {_num(a.market.equity_value)}")
    for k, v in a.market.ledger:
        w(f"- EV→equity adjustment, {k}: {_num(v)}")
    w(f"- Market enterprise value: {_num(a.market.enterprise_value)}\n")
    w("**Multiples (trailing, at market price):**\n")
    for name, mul in a.multiples.items():
        val = (_pct(mul.value) if "yield" in name else f"{mul.value:.2f}x") if mul.meaningful else \
            f"not meaningful ({mul.reason})"
        w(f"- {name}: {val}")
    for name, ctx in a.multiple_context.items():
        w(f"- {name} history: current {ctx.current:.2f}x vs median {ctx.median:.2f}x "
          f"(percentile {ctx.percentile:.0%}, z {ctx.z_score:+.2f}, n={ctx.observations}). "
          "Context only; mean reversion is not assumed.")
    if a.comparables:
        cv = a.comparables
        w(f"\n**Comparable companies (EV/EBITDA):** peer IQR {cv.low_multiple:.2f}x–{cv.high_multiple:.2f}x "
          f"(median {cv.median_multiple:.2f}x) on EBITDA {_num(cv.subject_metric)} → implied EV "
          f"{_num(cv.implied_low)}–{_num(cv.implied_high)}. Excluded: "
          + (", ".join(f"{n} ({r})" for n, r in cv.excluded) or "none") + ".")
        for wn in cv.warnings:
            w(f"  - ⚠️ {wn}")

    # 17 Reverse DCF
    h()
    w(f"Market EV to explain: **{_num(a.reverse[0].target_enterprise_value)}**. Each line solves one "
      "lever with all others held at the base case:\n")
    for r in a.reverse:
        w(f"- {r.statement()}")
        for note in r.notes:
            w(f"  - note: {note}")
        for p in r.solutions:
            w(f"  - implied year-{len(p.model.years)} revenue {_num(p.final_revenue)}, revenue CAGR "
              f"{_pct(p.revenue_cagr)}, cumulative FCFF {_num(p.cumulative_fcff)}"
              + (f", implied share of stated addressable market {_pct(p.implied_market_share)}"
                 if p.implied_market_share is not None else ""))
    w("\n**Iso-value family (margin ↔ growth combinations consistent with the price):**\n")
    w("| Steady-state margin | Implied year-1 growth (fading) |\n|---:|---:|")
    for sp in a.surface:
        w(f"| {_pct(sp.x)} | {', '.join(_pct(y) for y in sp.y_solutions) or 'no solution in bounds'} |")
    d = a.duration
    w(f"\n**Growth duration:** at {_pct(d.growth_rate)} growth, the price is justified after "
      + (f"**{d.years_required} year(s)**" if d.years_required else f"no horizon up to {d.max_years_tested} years")
      + " of that growth (margins held at the final base-case level).\n")
    w("**Expectations gap:**\n")
    for gi in a.gap:
        w(f"- {gi.metric}: market-implied {_pct(gi.market_implied)}; company median {_pct(gi.company_median)} "
          f"/ best {_pct(gi.company_max)}; peer median {_pct(gi.peer_median)} / best {_pct(gi.peer_max)}"
          + (f"; consensus {_pct(gi.analyst_consensus)}" if gi.analyst_consensus is not None else
             "; consensus not available (licensed estimates not connected)"))
        for o in gi.observations:
            w(f"  - {o}")

    # 18 Scenarios
    h()
    w("| | Bear | Base | Bull |\n|---|---:|---:|---:|")
    rows = [
        ("Year-1 → final growth", lambda o: f"{_pct(o.dcf.inputs.revenue_growth[0])} → {_pct(o.dcf.inputs.revenue_growth[-1])}"),
        ("Final-year revenue", lambda o: _num(o.dcf.final_revenue)),
        ("Final-year EBIT margin", lambda o: _pct(o.dcf.years[-1].ebit_margin)),
        ("Cumulative FCFF (explicit)", lambda o: _num(sum(y.fcff for y in o.dcf.years))),
        ("Cumulative reinvestment", lambda o: _num(sum(y.reinvestment for y in o.dcf.years))),
        ("Discount rate", lambda o: _pct(o.dcf.inputs.discount_rate, 2)),
        ("Terminal growth / ROIC", lambda o: f"{_pct(o.dcf.inputs.terminal_growth)} / {_pct(o.dcf.inputs.terminal_roic)}"),
        ("Enterprise value", lambda o: _num(o.dcf.enterprise_value)),
        ("Terminal value share of EV", lambda o: _pct(o.dcf.terminal_share, 0)),
        ("Equity value", lambda o: _num(o.bridge.equity_value)),
        ("**Value per share**", lambda o: f"**{_num(o.per_share, 2)}**"),
        ("vs. price", lambda o: _pct(o.per_share / s.share_price - 1)),
    ]
    for label, fn in rows:
        w(f"| {label} | " + " | ".join(fn(o) for o in s.outcomes) + " |")
    w("")
    for o in s.outcomes:
        w(f"- **{o.scenario.name}** — {o.scenario.narrative} Dependencies: "
          f"{'; '.join(o.scenario.key_dependencies) or 'not stated'}. Sources: "
          f"{', '.join(o.scenario.source_refs) or 'none'}.")
        for wn in o.dcf.warnings:
            w(f"  - ⚠️ {wn}")
    for wn in s.warnings:
        w(f"- ⚠️ {wn}")
    w("\n**Sensitivity — base-case value per share (rows: discount rate; columns: terminal growth):**\n")
    sg = a.sensitivity
    w("| | " + " | ".join(_pct(g, 1) for g in sg.cols) + " |")
    w("|---" * (len(sg.cols) + 1) + "|")
    for r, row in zip(sg.rows, sg.values):
        w(f"| {_pct(r, 1)} | " + " | ".join(_num(v, 2) if v is not None else "—" for v in row) + " |")

    # 19 Major uncertainties
    h()
    w("Assumptions ranked by valuation swing (tornado):\n")
    for b in a.tornado:
        w(f"- {b.assumption}: {_num(b.low_value, 2)} ({b.low_input}) to {_num(b.high_value, 2)} "
          f"({b.high_input}); swing {_num(b.swing, 2)}")
    # 20-21
    h()
    cats = [f for f in c.findings if f.step == "catalyst"]
    w("\n".join(f"- {f.text} [{', '.join(f.source_refs)}]" for f in cats) or
      NOT_ASSESSED.format(m="Advanced: catalyst calendar & research agents"))
    h()
    cons = [f for f in c.findings if f.step in ("counterargument", "market_may_know")]
    w("\n".join(f"- {f.text} [{', '.join(f.source_refs)}]" for f in cons) or
      NOT_ASSESSED.format(m="Advanced: Thesis Challenger"))

    # 22 Evidence coverage
    h()
    w(f"Evidence quality (case-level): **{c.evidence_quality.value}**. Citation audit: "
      f"{a.citations.checked} values checked, {len(a.citations.findings)} finding(s).\n")
    for f in a.citations.findings:
        w(f"- {f.name}: {f.problem}")
    if c.data_validation is not None:
        w(f"\n**Data validation** ({c.data_validation.summary()}):\n")
        for ch in c.data_validation.checks:
            w(f"- {ch.status} — {ch.name}: {ch.detail}")
    if c.notes:
        w("\n**Data handling notes:**\n")
        for note in c.notes:
            w(f"- {note}")
    rows = provenance_rows(c)
    if rows:
        w(f"\n**Figure provenance** ({len(rows)} figures; full table in the CSV export):\n")
        w("| Figure | Period | Value | Concept | Form · accession | Filed | Retrieved | Derivation |")
        w("|---|---|---:|---|---|---|---|---|")
        for r in rows:
            w(f"| {r['figure']} | {r['period']} | {r['value']} {r['unit']} | `{r['concept']}` | "
              f"[{r['form']} {r['accession']}]({r['source_url']}) | {r['filed']} | {r['retrieved_at'][:19]} | "
              f"{r['derivation'] or '—'} |")
    w("\n**13-step misvaluation investigation status:**\n")
    for st in asmt.steps:
        w(f"{st.number}. {'✅' if st.performed else '⬜'} {st.title} — {st.detail}")

    # 23 Final
    h()
    w(f"**{asmt.verdict.value}.** Price {_num(asmt.price, 2)} (as of {asmt.price_as_of}) sits "
      f"{asmt.price_position} (bear {_num(asmt.bear_value, 2)} / base {_num(asmt.base_value, 2)} / "
      f"bull {_num(asmt.bull_value, 2)}); margin-of-safety band ±{asmt.margin_of_safety:.0%}. "
      f"Downside to bear case {_pct(asmt.downside_to_bear)}.\n")
    w("Reasons: " + "; ".join(asmt.reasons) + ".\n")
    w(f"*{asmt.caveat}* Business quality, intrinsic value and market expectations are separate "
      "conclusions; this verdict concerns valuation only.")

    # 24 Bibliography
    h()
    for src in c.sources.values():
        bits = [f"`{src.source_id}`", src.title, src.publisher]
        if src.published_at:
            bits.append(f"published {src.published_at}")
        if src.retrieved_at:
            bits.append(f"retrieved {src.retrieved_at.isoformat()}")
        if src.url:
            bits.append(src.url)
        if src.accession:
            bits.append(f"accession {src.accession}")
        if src.synthetic:
            bits.append("**SYNTHETIC**")
        w("- " + " · ".join(bits))
    return "\n".join(out) + "\n"
