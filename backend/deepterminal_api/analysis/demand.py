"""Customer & demand intelligence: revenue quality from filings; review/usage data only via configured providers."""

from __future__ import annotations

import re

from ..services import filings as fs
from ..services.evidence import FindingDraft, computed_evidence, excerpt_evidence, save_evidence, unavailable
from ..services.gateway import DataUnavailable
from .base import Ctx, pct, clip

MODULE = "customer_demand"
# Single-customer concentration only. Geographic splits ("customers headquartered outside the United
# States accounted for 48%") are aggregates, not one customer, and are excluded.
SINGLE = re.compile(r"\b(?:one|a single|single|another|largest|two|three|four)\s+(?:direct\s+|indirect\s+|end\s+|major\s+)?"
                    r"(?:customers?|distributors?|retailers?|resellers?)\b|\bcustomer [A-Z]\b|"
                    r"\bsales to (?:a|an|one|our largest)\b", re.I)
NOT_SINGLE = re.compile(r"headquartered|outside (?:of )?the United States|located in|geograph|\bregion|\bcountr", re.I)
PCT = re.compile(r"(\d{1,2}(?:\.\d)?)\s?%\s+of\s+(?:our\s+)?(?:total\s+|net\s+|consolidated\s+)?"
                 r"(?:revenue|revenues|net sales|sales)\b", re.I)
FISCAL_YEAR = re.compile(r"\bfiscal(?: year)?\s+(\d{4})\b", re.I)


def customer_concentration(text: str, default_fy: int | None) -> list[dict]:
    """Largest single-customer revenue share stated per sentence, with the fiscal year the sentence names."""
    out = []
    for sent in re.split(r"(?<=\.)\s+", " ".join(text.split())):
        if len(sent) > 900 or not SINGLE.search(sent) or NOT_SINGLE.search(sent):
            continue
        shares = [float(m.group(1)) / 100 for m in PCT.finditer(sent)]
        if not shares or re.search(r"\bfiscal years\b", sent, re.I):
            continue          # several years in one sentence: the share-to-year mapping is ambiguous
        years = {int(y) for y in FISCAL_YEAR.findall(sent)}
        if len(years) > 1:
            continue
        out.append({"share": max(shares), "text": sent.strip(), "fy": years.pop() if years else default_fy})
    return out


PROVIDERS = [
    {"source": "Product reviews & ratings", "status": "not_configured",
     "reason": "No licensed review data provider configured; scraping retailer sites violates their terms."},
    {"source": "App downloads & active users", "status": "not_configured",
     "reason": "Requires a licensed app-intelligence provider (e.g. Sensor Tower) — not purchased."},
    {"source": "Search interest", "status": "unavailable",
     "reason": "No permitted API reachable from this environment."},
    {"source": "Warranty claims & returns", "status": "partial",
     "reason": "Only where disclosed in filings (warranty reserve XBRL tags not yet mapped)."},
]


def compute(ctx: Ctx) -> dict:
    db, c = ctx.db, ctx.company
    conc = []
    for f in ctx.filings(("10-K", "10-K/A"))[:3]:
        try:
            fs.fetch_filing_text(db, c, f)
        except DataUnavailable:
            continue
        full = fs.section(db, f, "full")
        if full:
            for x in customer_concentration(full.text, f.report_date.year if f.report_date else None):
                if not any(y["fy"] == x["fy"] and y["share"] == x["share"] for y in conc):
                    conc.append({**x, "accession": f.accession, "filed": f.filed.isoformat()})
    rows = []
    ends = ctx.fiscal_ends[-8:]
    for i, e in enumerate(ends):
        y = ctx.year(e)
        p = ctx.year(ends[i - 1]) if i else {}
        rev = y.get("revenue")
        def g(k):
            return None if not p.get(k) or y.get(k) is None else y[k] / p[k] - 1
        rows.append({"fy": e.year, "revenue": rev, "revenue_growth": g("revenue"),
                     "deferred_revenue": y.get("deferred_revenue"), "deferred_growth": g("deferred_revenue"),
                     "rpo": y.get("rpo"), "rpo_growth": g("rpo"), "receivables_growth": g("accounts_receivable"),
                     "dso": y["accounts_receivable"] * 365 / rev if y.get("accounts_receivable") is not None and rev else None,
                     "gross_margin": y["gross_profit"] / rev if y.get("gross_profit") is not None and rev else None,
                     "rnd_pct": y["rnd"] / rev if y.get("rnd") and rev else None})
    quality = []
    last = rows[-1] if rows else None
    if last and last["revenue_growth"] is not None:
        if last["deferred_growth"] is not None:
            quality.append({"test": "Deferred revenue vs revenue growth",
                            "result": "supports demand" if last["deferred_growth"] >= last["revenue_growth"] else "lagging",
                            "detail": f"deferred {pct(last['deferred_growth'])} vs revenue {pct(last['revenue_growth'])}"})
        if last["rpo_growth"] is not None:
            quality.append({"test": "Remaining performance obligations vs revenue",
                            "result": "supports demand" if last["rpo_growth"] >= last["revenue_growth"] else "lagging",
                            "detail": f"RPO {pct(last['rpo_growth'])} vs revenue {pct(last['revenue_growth'])}"})
        if last["receivables_growth"] is not None:
            quality.append({"test": "Receivables vs revenue growth",
                            "result": "possible pull-forward / collection risk"
                            if last["receivables_growth"] - last["revenue_growth"] > 0.10 else "consistent",
                            "detail": f"receivables {pct(last['receivables_growth'])} vs revenue {pct(last['revenue_growth'])}"})
    unavailable_tests = ["Price vs volume decomposition (units not disclosed in XBRL)",
                         "Organic vs acquisition-driven growth (requires acquisition revenue disclosure parsing)",
                         "Channel inventory (requires distributor data)"]
    return {"concentration": conc[:10], "trend": rows, "quality_tests": quality,
            "unavailable_tests": unavailable_tests, "providers": PROVIDERS,
            "caution": "Review volume, search interest and downloads are never treated as revenue."}


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    db, c = ctx.db, ctx.company
    out = []
    ten_ks = {f.accession: f for f in ctx.filings(("10-K", "10-K/A"))}
    if data["concentration"]:
        latest = max(x["fy"] or 0 for x in data["concentration"])
        top = max((x for x in data["concentration"] if (x["fy"] or 0) == latest), key=lambda x: x["share"])
        out.append(FindingDraft(MODULE, f"Customer concentration: a single customer at {pct(top['share'], 0)} of revenue "
                                        f"(FY{top['fy']})", clip(top["text"], 400),
                                "concern" if top["share"] >= .2 else ("watch" if top["share"] >= .1 else "neutral"),
                                "company_statement", "high",
                                [excerpt_evidence(db, c, ten_ks[top["accession"]], "full", top["text"])]))
    ends = ctx.fiscal_ends[-2:]
    ids = [save_evidence(db, c, e, ctx.job_id, "rules") for e in ctx.evs(
        [(n, d) for d in ends for n in ("revenue", "deferred_revenue", "rpo", "accounts_receivable")])]
    for q in data["quality_tests"]:
        sev = "positive" if q["result"] == "supports demand" else ("watch" if q["result"] != "consistent" else "neutral")
        out.append(FindingDraft(MODULE, f"{q['test']}: {q['result']}", q["detail"], sev, "analytical_inference",
                                "medium", [computed_evidence(q["test"], None, q["detail"], ids)],
                                "Single-year comparison; seasonality and acquisitions are not adjusted."))
    for p in data["providers"]:
        out.append(unavailable(MODULE, p["source"], p["reason"]))
    return out
