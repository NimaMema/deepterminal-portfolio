"""Historical analogue engine.

Compares the company's current operating profile with other companies *as they
looked at historical decision dates*, using only facts filed by those dates
(point-in-time), then reports what happened next. Selection rules:

* the universe is every company in the local database of the same data mode
  (live or demo) — documented, not hand-picked;
* the candidate set must contain both later successes and later failures when the
  universe has them; the balance is reported;
* outcomes come from filings after the decision date and are labelled as such;
* survivorship: delisted or bankrupt companies appear only if loaded by CIK.
"""

from __future__ import annotations

import math
from datetime import date

from sqlalchemy import select

from deepterminal.data import sec_edgar as se

from ..models import Company
from ..services import companies as cs
from ..services.evidence import FindingDraft, computed_evidence, unavailable
from .base import Ctx, pct

MODULE = "historical_analogues"
FEATURES = ("growth_1y", "cagr_3y", "op_margin", "gross_margin", "capex_pct", "rnd_pct", "log_revenue")


def profile_at(facts: dict, end: date, as_of: date | None) -> dict | None:
    s = lambda n: se.annual_series(facts, n, as_of, "latest")
    rev = s("revenue")
    ends = sorted(e for e in rev if e <= end)
    if len(ends) < 4:
        return None
    e, p, e3 = ends[-1], ends[-2], ends[-4]
    r = rev[e].value
    def v(n):
        f = s(n).get(e)
        return f.value if f else None
    ratio = lambda n: None if v(n) is None else v(n) / r     # missing stays missing: nothing is imputed
    return {"growth_1y": r / rev[p].value - 1, "cagr_3y": (r / rev[e3].value) ** (1 / 3) - 1,
            "op_margin": ratio("operating_income"), "gross_margin": ratio("gross_profit"),
            "capex_pct": ratio("capex"), "rnd_pct": ratio("rnd"), "log_revenue": math.log10(r / 1e6),
            "end": e.isoformat(), "revenue": r / 1e6}


def first_public(facts: dict, end: date) -> date | None:
    """When the fiscal year's revenue first became public, across every revenue concept the filer has used.
    Companies change tags (NVIDIA moved to us-gaap:Revenues in 2022); following one tag would date
    FY2020 to 2022 and leak later information into the 'point-in-time' profile."""
    dates = [f.filed for concept in se.CONCEPTS["revenue"][0] for f in se.iter_facts(facts, concept, "USD")
             if f.end == end and f.start and 350 <= f.days <= 380 and f.form in se.ANNUAL_FORMS]
    return min(dates) if dates else None


def outcome_after(facts: dict, end: date) -> dict | None:
    rev = se.annual_series(facts, "revenue", None, "latest")
    oi = se.annual_series(facts, "operating_income", None, "latest")
    later = sorted(e for e in rev if e > end)
    if len(later) < 3 or end not in rev:
        return None
    e3 = later[2]
    cagr = (rev[e3].value / rev[end].value) ** (1 / 3) - 1 if rev[e3].value > 0 else -1
    dm = (oi[e3].value / rev[e3].value if e3 in oi else 0) - (oi[end].value / rev[end].value if end in oi else 0)
    cls = "success" if cagr > .08 and dm > -.05 else ("failure" if cagr < 0 or (cagr < .08 and dm < -.05) else "mixed")
    return {"revenue_cagr_next_3y": cagr, "margin_change_next_3y": dm, "class": cls, "through": e3.isoformat()}


def compute(ctx: Ctx, k: int = 6) -> dict:
    facts = ctx.facts
    ends = sorted(ctx.series("revenue"))
    if not ends:
        return {"error": "no data"}
    target = profile_at(facts, ends[-1], ctx.as_of)
    if target is None:
        return {"target": None, "candidates": [], "error": "fewer than four years of history"}
    universe = ctx.db.scalars(select(Company).where(Company.synthetic == ctx.company.synthetic)).all()
    cands = []
    for co in universe:
        try:
            f, _ = cs.companyfacts(co)
        except Exception:
            continue
        for end in sorted(se.annual_series(f, "revenue", None, "latest")):
            if co.id == ctx.company.id and end >= ends[-1]:
                continue
            decision = first_public(f, end)
            if decision is None:
                continue
            prof = profile_at(f, end, decision)        # only facts filed by the decision date
            out = outcome_after(f, end)
            if prof and out:
                cands.append({"company_id": co.id, "ticker": co.ticker, "name": co.name, "decision_date": decision.isoformat(),
                              "profile": prof, "outcome": out, "self": co.id == ctx.company.id})
    if not cands:
        return {"target": target, "candidates": [], "selected": [], "balance": {},
                "error": "No candidates with three years of subsequent history in the local universe."}
    def sd(f):
        xs = [c["profile"][f] for c in cands if c["profile"][f] is not None]
        if len(xs) < 2:
            return 1.0
        m = sum(xs) / len(xs)
        return (sum((x - m) ** 2 for x in xs) / len(xs)) ** .5 or 1.0
    sds = {f: sd(f) for f in FEATURES}
    for c in cands:
        # Features missing on either side are left out (and listed), not treated as zero.
        used = [f for f in FEATURES if c["profile"][f] is not None and target[f] is not None]
        c["features_used"] = used
        c["distance"] = (math.sqrt(sum(((c["profile"][f] - target[f]) / sds[f]) ** 2 for f in used) / len(used))
                         if len(used) >= 4 else None)
    cands = [c for c in cands if c["distance"] is not None]      # too few comparable features to rank
    if not cands:
        return {"target": target, "candidates": [], "selected": [], "balance": {},
                "error": "No candidates share enough reported features with the target to compare."}
    cands.sort(key=lambda c: c["distance"])
    selected = cands[:k]
    for cls in ("success", "failure"):     # anti-cherry-picking: include the nearest of each outcome class
        if not any(c["outcome"]["class"] == cls for c in selected):
            nearest = next((c for c in cands if c["outcome"]["class"] == cls), None)
            if nearest:
                selected.append(nearest)
    bal = {cls: sum(1 for c in selected if c["outcome"]["class"] == cls) for cls in ("success", "mixed", "failure")}
    return {"target": target, "features": FEATURES, "selected": selected, "candidates_considered": len(cands),
            "universe_size": len(universe), "balance": bal,
            "self_only": all(c["self"] for c in selected),
            "outcome_definition": "success: next-3y revenue CAGR > 8% and operating margin change > −5pp; failure: "
                                  "revenue declining, or CAGR < 8% with margin down more than 5pp; otherwise mixed",
            "base_rate": {cls: sum(1 for c in cands if c["outcome"]["class"] == cls) / len(cands)
                          for cls in ("success", "mixed", "failure")},
            "selection_criteria": "Standardised Euclidean distance over growth (1y, 3y), operating and gross margin, "
                                  "capex and R&D intensity, and log revenue; nearest six plus the nearest success and "
                                  "failure if absent. Profiles use only facts filed by each decision date.",
            "limitations": ["Universe limited to companies loaded into this instance (survivorship bias likely).",
                            "XBRL data starts around 2009; earlier bubbles (e.g. 2000) are not covered.",
                            "Macro regime (rates, inflation) not controlled: FRED is not reachable here.",
                            "Resemblance does not imply the same outcome."]}


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    if not data.get("selected"):
        return [unavailable(MODULE, "Historical analogues", data.get("error", "no candidates"),
                            "Load more companies (search and open them) to widen the universe.")]
    sel = data["selected"]
    b = data["balance"]
    ev = computed_evidence(f"{len(sel)} analogues from {data['candidates_considered']} point-in-time candidates",
                           None, data["selection_criteria"], [], data={"selected": [
                               {"ticker": c["ticker"], "decision_date": c["decision_date"], "distance": c["distance"],
                                "outcome": c["outcome"]} for c in sel]})
    scope = "Company's own history only (no other companies loaded): " if data.get("self_only") else "Nearest historical analogues: "
    return [FindingDraft(MODULE, scope + f"{b.get('success', 0)} later succeeded, "
                                 f"{b.get('mixed', 0)} mixed, {b.get('failure', 0)} failed",
                         "; ".join(f"{c['ticker']} at {c['decision_date']} → next-3y revenue CAGR "
                                   f"{pct(c['outcome']['revenue_cagr_next_3y'])} ({c['outcome']['class']})" for c in sel[:6]),
                         "neutral", "analytical_inference", "low", [ev], " ".join(data["limitations"]))]
