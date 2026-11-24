"""Product research: what filings and financials say about products; benchmarks require outside evidence."""

from __future__ import annotations

import re

from ..services import filings as fs
from ..services.evidence import FindingDraft, computed_evidence, excerpt_evidence, save_evidence, unavailable
from ..services.gateway import DataUnavailable
from .base import Ctx, pct

MODULE = "product_research"
PRODUCT = re.compile(r"[^.]*\b(our (products?|platform|solutions?|offerings?)|we (sell|offer|design|develop))\b[^.]*\.", re.I)


def compute(ctx: Ctx) -> dict:
    db, c = ctx.db, ctx.company
    statements = []
    for f in ctx.filings(("10-K",))[:1]:
        try:
            fs.fetch_filing_text(db, c, f)
        except DataUnavailable:
            continue
        sec = fs.section(db, f, "item_1")
        if sec:
            statements = [{"text": m.group(0).strip(), "accession": f.accession}
                          for m in PRODUCT.finditer(sec.text)][:12]
    trend = []
    for e in ctx.fiscal_ends[-8:]:
        y = ctx.year(e)
        r = y.get("revenue")
        trend.append({"fy": e.year, "gross_margin": y["gross_profit"] / r if y.get("gross_profit") is not None and r else None,
                      "rnd_pct": y["rnd"] / r if y.get("rnd") and r else None, "revenue": r})
    return {"statements": statements, "trend": trend,
            "dimensions": [{"dimension": d, "status": "needs_evidence",
                            "reason": "Requires independent benchmarks, reviews or pricing data with a stated "
                                      "comparison method and customer segment."}
                           for d in ("Technical benchmarks", "Reliability", "Customer satisfaction", "Ownership cost",
                                     "Capabilities", "Price", "Availability", "Support quality")],
            "principle": "Product superiority is never reduced to one score; each dimension needs its own sourced "
                         "evidence and a defined customer segment."}


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    out = []
    t = [x for x in data["trend"] if x["gross_margin"] is not None]
    if len(t) >= 3:
        ids = [save_evidence(ctx.db, ctx.company, e, ctx.job_id, "rules")
               for e in ctx.evs([(n, d) for d in ctx.fiscal_ends[-3:] for n in ("revenue", "gross_profit", "rnd")])]
        chg = t[-1]["gross_margin"] - t[-3]["gross_margin"]
        out.append(FindingDraft(MODULE, f"Gross margin {pct(t[-3]['gross_margin'])} → {pct(t[-1]['gross_margin'])} "
                                        f"(FY{t[-3]['fy']}–FY{t[-1]['fy']})",
                                "Sustained gross-margin expansion is consistent with pricing power or mix shift; "
                                "compression with competitive pressure or input costs. Financials alone cannot tell "
                                "which.", "positive" if chg > .02 else ("watch" if chg < -.02 else "neutral"),
                                "analytical_inference", "medium",
                                [computed_evidence("Gross margin trend", chg, "gross profit / revenue", ids)]))
    if data["statements"]:
        f = next(x for x in ctx.filings(("10-K",)) if x.accession == data["statements"][0]["accession"])
        s = data["statements"][0]["text"]
        out.append(FindingDraft(MODULE, "Company's own product description", s[:400], "neutral", "company_statement",
                                "medium", [excerpt_evidence(ctx.db, ctx.company, f, "item_1", s)],
                                "Self-description; not evidence of product quality."))
    out.append(unavailable(MODULE, "Independent product benchmarks and reviews",
                           "No benchmark or review provider is connected; DEEPTERMINAL does not infer product "
                           "superiority from financial data."))
    return out
