"""Financial valuation & market expectations modules (wrap the tested engine)."""

from __future__ import annotations

from ..services import valuation as vs
from ..services.evidence import FindingDraft, computed_evidence, save_evidence, unavailable
from ..services.gateway import DataUnavailable
from .base import Ctx, pct

VAL, EXP = "financial_valuation", "market_expectations"


def compute(ctx: Ctx) -> dict:
    params = ctx.cache.get("params", {})
    if not params.get("discount_rate"):
        return {"unavailable": {"status": "not_configured", "message": "No discount rate supplied for this "
                                                                     "investigation; DEEPTERMINAL does not invent one."}}
    try:
        return vs.value_company(ctx.db, ctx.company, params, None, ctx.as_of)
    except DataUnavailable as e:
        return {"unavailable": e.to_dict()}


def _input_ids(ctx: Ctx) -> list[int]:
    return [save_evidence(ctx.db, ctx.company, e, ctx.job_id, "rules")
            for e in ctx.evs([(n, ctx.fiscal_ends[-1]) for n in ("revenue", "operating_income", "cash", "total_debt")])]


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    if "scenarios" not in data:
        u = data.get("unavailable", {})
        return [unavailable(VAL, "Intrinsic valuation not run", u.get("message", ""), u.get("hint", ""))]
    ids = _input_ids(ctx)
    sc = {s["name"]: s for s in data["scenarios"]}
    a = [x for x in data["assumptions"]]
    rationale = "; ".join(f"{x['name']}: {x['rationale']}" for x in a[:6])
    out = [FindingDraft(VAL, f"DCF value range {sc['bear']['per_share']:,.2f} – {sc['bull']['per_share']:,.2f} per share "
                             f"(base {sc['base']['per_share']:,.2f})",
                        "Bear/base/bull FCFF DCF under the stated assumptions. " + rationale,
                        "neutral", "model_assumption", "medium",
                        [computed_evidence("Scenario DCF", sc["base"]["per_share"], "deepterminal.valuation.dcf.run_dcf + bridge",
                                           ids, "USD/share", "Model output; sensitive to discount rate and terminal "
                                           "assumptions (see tornado).")],
                        f"Terminal value is {pct(sc['base']['dcf']['terminal_share'], 0)} of base EV.")]
    if data.get("assessment"):
        asm = data["assessment"]
        sev = {"Potentially undervalued under specified assumptions": "positive",
               "Potentially overvalued under specified assumptions": "watch",
               "Too uncertain to assess reliably": "unavailable"}.get(asm["verdict"], "neutral")
        out.append(FindingDraft(VAL, asm["verdict"], " ".join(asm["reasons"]) + " " + asm["caveat"],
                                sev if sev != "unavailable" else "neutral", "analytical_inference", "low",
                                [computed_evidence("Misvaluation assessment", asm["upside_to_base"],
                                                   "price vs base value with margin of safety", ids)]))
    return out


def findings_expectations(ctx: Ctx, data: dict) -> list[FindingDraft]:
    if not data.get("reverse_dcf"):
        return [unavailable(EXP, "Market-implied expectations not computed",
                            "Requires a timestamped share price (enter one on the Valuation Laboratory) and a discount rate.")]
    ids = _input_ids(ctx)
    out = []
    for r in data["reverse_dcf"]:
        if r["status"] == "none_in_bounds":
            out.append(FindingDraft(EXP, f"No {r['label'].lower()} within bounds reproduces the price",
                                    r["statement"], "watch", "analytical_inference", "medium",
                                    [computed_evidence("Reverse DCF", None, r["statement"], ids)]))
            continue
        s = r["solutions"][0]
        out.append(FindingDraft(EXP, f"Price implies {r['label'].lower()} of {pct(s['value']) if r['unit'] == '%' else round(s['value'], 2)}",
                                r["statement"], "neutral", "analytical_inference", "medium",
                                [computed_evidence("Reverse DCF", s["value"], "solve EV_model(x) = EV_market", ids)],
                                "One of a family of assumption sets consistent with the price."))
    for g in data.get("expectations_gap", []):
        if g["observations"]:
            out.append(FindingDraft(EXP, f"Expectations gap — {g['metric']}: implied {pct(g['market_implied'])}",
                                    "; ".join(g["observations"]),
                                    "watch" if any("exceeds" in o for o in g["observations"]) else "neutral",
                                    "analytical_inference", "medium",
                                    [computed_evidence("Expectations gap", g["market_implied"], "implied vs history", ids)]))
    return out
