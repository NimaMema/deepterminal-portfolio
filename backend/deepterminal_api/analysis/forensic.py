"""Forensic accounting: earnings quality, working capital, dilution, liquidity, scores, anomalies."""

from __future__ import annotations

from deepterminal.forensics import altman_z, beneish, piotroski, sloan_accruals

from ..services.evidence import FindingDraft, computed_evidence, save_evidence
from .base import Ctx, pct

MODULE = "forensic_accounting"


def compute(ctx: Ctx) -> dict:
    ends = ctx.fiscal_ends[-8:]
    years = [ctx.year(e) for e in ends]
    rows = []
    for i, (e, y) in enumerate(zip(ends, years)):
        p = years[i - 1] if i else None
        rev = y.get("revenue")
        def r(a, b):
            return None if a is None or b in (None, 0) else a / b
        row = {"fy": e.year, "end": e.isoformat(), "revenue": rev, "net_income": y.get("net_income"),
               "cfo": y.get("operating_cash_flow"), "fcf": None if y.get("operating_cash_flow") is None or y.get("capex") is None
               else y["operating_cash_flow"] - y["capex"],
               "cfo_to_ni": r(y.get("operating_cash_flow"), y.get("net_income")) if (y.get("net_income") or 0) > 0 else None,
               "dso": r((y.get("accounts_receivable") or 0) * 365, rev) if y.get("accounts_receivable") is not None else None,
               "dio": r((y.get("inventory") or 0) * 365, y.get("cost_of_revenue")) if y.get("inventory") is not None else None,
               "gross_margin": r(y.get("gross_profit"), rev), "sbc_pct": r(y.get("stock_based_comp"), rev),
               "current_ratio": r(y.get("assets_current"), y.get("liabilities_current")),
               "debt_to_equity": r(y.get("total_debt"), y.get("shareholders_equity")),
               "interest_cover": r(y.get("operating_income"), y.get("interest_expense")),
               "shares": y.get("diluted_shares"),
               "share_change": r((y.get("diluted_shares") or 0) - (p.get("diluted_shares") or 0), p.get("diluted_shares"))
               if p and p.get("diluted_shares") else None,
               "accruals": sloan_accruals(y, p) if p else None,
               "receivables_growth": r((y.get("accounts_receivable") or 0) - (p.get("accounts_receivable") or 0),
                                       p.get("accounts_receivable")) if p and p.get("accounts_receivable") else None,
               "revenue_growth": r((rev or 0) - (p.get("revenue") or 0), p.get("revenue")) if p and p.get("revenue") else None}
        rows.append(row)
    scores = {}
    if len(years) >= 2:
        c, p = years[-1], years[-2]
        pp = years[-3] if len(years) >= 3 else None
        mve = None
        if ctx.price and c.get("diluted_shares"):
            mve = ctx.price.value * c["diluted_shares"]
        for res in (piotroski(c, p, pp), beneish(c, p), altman_z(c, mve)):
            scores[res.name] = {"score": res.score, "zone": res.zone, "interpretation": res.interpretation,
                                "components": res.components, "missing": res.missing, "caveats": res.caveats,
                                "fy": ends[-1].year}
        history = []
        for i in range(1, len(years)):
            b = beneish(years[i], years[i - 1])
            pt = piotroski(years[i], years[i - 1], years[i - 2] if i >= 2 else None)
            history.append({"fy": ends[i].year, "beneish": b.score, "piotroski": pt.score})
    else:
        history = []
    anomalies = []
    for row in rows:
        if row["receivables_growth"] is not None and row["revenue_growth"] is not None \
                and row["receivables_growth"] - row["revenue_growth"] > 0.10:
            anomalies.append({"fy": row["fy"], "code": "RECEIVABLES_OUTPACE_REVENUE", "severity": "watch",
                              "detail": f"receivables +{pct(row['receivables_growth'])} vs revenue +{pct(row['revenue_growth'])}"})
        if row["accruals"] is not None and row["accruals"] > 0.10:
            anomalies.append({"fy": row["fy"], "code": "HIGH_ACCRUALS", "severity": "concern",
                              "detail": f"accruals ratio {pct(row['accruals'])}"})
        if row["share_change"] is not None and row["share_change"] > 0.03:
            anomalies.append({"fy": row["fy"], "code": "DILUTION", "severity": "watch",
                              "detail": f"diluted shares +{pct(row['share_change'])}"})
        if row["sbc_pct"] is not None and row["sbc_pct"] > 0.10:
            anomalies.append({"fy": row["fy"], "code": "HEAVY_SBC", "severity": "watch",
                              "detail": f"SBC {pct(row['sbc_pct'])} of revenue"})
        if row["interest_cover"] is not None and row["interest_cover"] < 3:
            anomalies.append({"fy": row["fy"], "code": "LOW_INTEREST_COVER", "severity": "concern",
                              "detail": f"EBIT/interest {row['interest_cover']:.1f}x"})
        if row["current_ratio"] is not None and row["current_ratio"] < 1:
            anomalies.append({"fy": row["fy"], "code": "LOW_LIQUIDITY", "severity": "watch",
                              "detail": f"current ratio {row['current_ratio']:.2f}"})
        if (row["net_income"] or 0) > 0 and row["fcf"] is not None and row["fcf"] < 0:
            anomalies.append({"fy": row["fy"], "code": "PROFIT_WITHOUT_CASH", "severity": "concern",
                              "detail": "positive net income but negative free cash flow"})
    return {"rows": rows, "scores": scores, "score_history": history, "anomalies": anomalies,
            "disclaimer": "Anomalies and scores are screening signals that direct further review. They are not "
                          "evidence of wrongdoing."}


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    out: list[FindingDraft] = []
    ends = ctx.fiscal_ends[-2:]
    if len(ends) < 2:
        return out
    c_end, p_end = ends[-1], ends[-2]
    base_inputs = ["revenue", "gross_profit", "accounts_receivable", "assets_current", "ppe_net", "total_assets",
                   "depreciation", "sga", "liabilities_current", "total_debt", "net_income", "operating_cash_flow"]
    input_ev = ctx.evs([(n, d) for n in base_inputs for d in (c_end, p_end)])
    ids = [save_evidence(ctx.db, ctx.company, e, ctx.job_id, "rules") for e in input_ev]
    for name, s in data["scores"].items():
        if s["score"] is None:
            out.append(FindingDraft(MODULE, f"{name}: not computable", s["interpretation"], "unavailable",
                                    "analytical_inference", "low", [], "Missing XBRL inputs; nothing imputed."))
            continue
        sev = {"elevated": "concern", "distress": "concern", "grey": "watch", "weak": "watch", "strong": "positive",
               "safe": "positive"}.get(s["zone"], "neutral")
        comp = computed_evidence(f"{name} FY{s['fy']} = {s['score']:.2f}", s["score"],
                                 f"{name} per published formula; components {s['components']}", ids,
                                 limitations="; ".join(s["caveats"]))
        out.append(FindingDraft(MODULE, f"{name} FY{s['fy']}: {s['interpretation']}",
                                f"{s['interpretation']}. " + " ".join(s["caveats"]), sev, "analytical_inference",
                                "medium", [comp], "; ".join(s["caveats"]), {"components": s["components"]}))
    by_code: dict[str, list] = {}
    for a in data["anomalies"]:
        by_code.setdefault(a["code"], []).append(a)
    for code, items in by_code.items():
        latest = max(items, key=lambda a: a["fy"])
        # A signal that has not recurred in the last three fiscal years is history, not a current concern.
        stale = latest["fy"] < c_end.year - 2
        comp = computed_evidence(f"{code} in {len(items)} year(s), latest FY{latest['fy']}: {latest['detail']}",
                                 None, "see forensic table formulas", ids)
        out.append(FindingDraft(MODULE, f"{code.replace('_', ' ').title()} (FY{', FY'.join(str(i['fy']) for i in items[-3:])})"
                                + (" — historical, not recurring" if stale else ""),
                                f"{latest['detail']}. Screening signal for follow-up; not proof of misstatement."
                                + (f" Not seen in FY{latest['fy'] + 1}–FY{c_end.year}." if stale else ""),
                                "neutral" if stale else latest["severity"], "analytical_inference", "medium", [comp],
                                "Ratios computed from reported XBRL values; industry norms differ."))
    return out
