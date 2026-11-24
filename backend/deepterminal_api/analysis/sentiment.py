"""Market sentiment & hype: insider/ownership activity, narrative intensity vs results, multiple expansion."""

from __future__ import annotations

import re

from datetime import date

from deepterminal.data import sec_edgar as se

from ..services import filings as fs
from ..services.evidence import FindingDraft, computed_evidence, save_evidence, unavailable
from ..services.gateway import DataUnavailable
from .base import Ctx, pct

MODULE = "market_sentiment"
# Label → pattern. "AI" is matched case-sensitively as a word so it does not hit "said" or "maintain".
NARRATIVE_TERMS = {
    "AI / artificial intelligence": re.compile(r"\bartificial intelligence\b|(?-i:\bAI\b)", re.I),
    "generative AI": re.compile(r"\bgenerative (?:ai|artificial intelligence)\b", re.I),
    "machine learning": re.compile(r"\bmachine learning\b", re.I),
    "blockchain": re.compile(r"\bblockchain\b", re.I),
    "metaverse": re.compile(r"\bmetaverse\b", re.I),
    "transformation": re.compile(r"\btransformation", re.I),
    "platform": re.compile(r"\bplatforms?\b", re.I),
    "disruption": re.compile(r"\bdisrupt\w*", re.I),
}
AI_TERM = "AI / artificial intelligence"
PROVIDERS = [
    {"source": "News volume & sentiment", "status": "not_configured", "reason": "No licensed news API configured."},
    {"source": "Analyst estimate revisions", "status": "not_configured",
     "reason": "Consensus estimates are licensed data (e.g. LSEG I/B/E/S, FactSet) — not purchased."},
    {"source": "Reddit / social discussion", "status": "not_configured",
     "reason": "Reddit Data API requires an approved application; not configured."},
    {"source": "Search interest", "status": "unavailable", "reason": "No permitted API reachable."},
    {"source": "Short interest & borrow cost", "status": "unavailable",
     "reason": "FINRA short-interest adapter not implemented yet; borrow cost is licensed data."},
    {"source": "Options activity", "status": "not_configured", "reason": "OPRA-derived data is licensed."},
    {"source": "Institutional ownership (13F)", "status": "partial",
     "reason": "13F filings are filed by holders, not the issuer; aggregation across all filers is not yet wired."},
]


def compute(ctx: Ctx) -> dict:
    db, c = ctx.db, ctx.company
    try:
        trend = fs.term_trend(db, c, NARRATIVE_TERMS)
    except DataUnavailable as e:
        trend = []
    rev = ctx.series("revenue")
    for t in trend:
        end = next((e for e in rev if e.year == t["fy"]), None)
        prev = next((e for e in rev if e.year == t["fy"] - 1), None)
        t["revenue_growth"] = rev[end].value / rev[prev].value - 1 if end and prev else None
    insiders = fs.insider_transactions(db, c, as_of=ctx.as_of)
    ownership = ctx.filings(("SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A"))
    # valuation multiple history from user-entered price quotes (point-in-time fundamentals)
    from sqlalchemy import select
    from ..models import PriceQuote
    quotes = list(db.scalars(select(PriceQuote).where(PriceQuote.company_id == c.id).order_by(PriceQuote.as_of)))
    mult = []
    for q in quotes:
        periods = se.build_periods(ctx.facts, as_of=q.as_of)
        ttm = se.build_ttm_period(ctx.facts, as_of=q.as_of)
        basis = ttm if ttm and periods and ttm.period_end > periods[-1].period_end else (periods[-1] if periods else None)
        if not basis or not basis.diluted_shares:
            continue
        mcap = q.value * basis.diluted_shares
        ev = mcap + basis.total_debt - basis.cash
        mult.append({"as_of": q.as_of.isoformat(), "price": q.value, "source": q.source, "market_cap": mcap,
                     "ev_revenue": ev / basis.revenue if basis.revenue else None,
                     "pe": mcap / basis.net_income if basis.net_income > 0 else None,
                     "basis_period_end": basis.period_end.isoformat(), "revenue": basis.revenue})
    return {"narrative": trend, "terms": list(NARRATIVE_TERMS), "insiders": {k: insiders[k] for k in
                                                                        ("open_market_buy_value", "open_market_sell_value")}
            | {"count": len(insiders["transactions"])},
            "ownership_filings": [{"form": f.form, "filed": f.filed.isoformat(), "url": f.url} for f in ownership[:20]],
            "multiples_history": mult, "providers": PROVIDERS,
            "decomposition_note": "Price change ≈ fundamental growth × multiple change × other effects; this is an "
                                  "approximation, not an accounting identity."}


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    out = []
    n = [t for t in data["narrative"] if t["counts"]]
    if len(n) >= 2:
        a, b = n[0], n[-1]
        ai_a, ai_b = a["per_10k_words"][AI_TERM], b["per_10k_words"][AI_TERM]
        evidence = computed_evidence(f"'AI / artificial intelligence' mentions per 10k words: FY{a['fy']} {ai_a:.1f} → "
                                     f"FY{b['fy']} {ai_b:.1f}", ai_b, "term count / word count × 10,000 in 10-K text", [],
                                     data={"filings": [t["accession"] for t in n]})
        growth = [t["revenue_growth"] for t in n[-3:] if t.get("revenue_growth") is not None]
        sev = "watch" if ai_b > max(ai_a * 3, 5) and growth and sum(growth) / len(growth) < .1 else "neutral"
        out.append(FindingDraft(MODULE, f"Narrative intensity: 'AI / artificial intelligence' {ai_a:.1f} → {ai_b:.1f} mentions "
                                        f"per 10,000 words in 10-Ks (FY{a['fy']}–FY{b['fy']})",
                                "Compare with revenue growth over the same years: " +
                                ", ".join(f"FY{t['fy']} {pct(t['revenue_growth'])}" for t in n[-4:]),
                                sev, "analytical_inference", "medium", [evidence],
                                "Word frequency measures emphasis, not substance."))
    ins = data["insiders"]
    if ins["count"]:
        out.append(FindingDraft(MODULE, f"Insider open-market sells ${ins['open_market_sell_value'] / 1e6:,.1f}m vs buys "
                                        f"${ins['open_market_buy_value'] / 1e6:,.1f}m",
                                "See Management Intelligence for transaction-level evidence.", "neutral",
                                "historical_fact", "medium",
                                [computed_evidence("Insider totals", ins["open_market_sell_value"], "Σ Form 4 P/S values", [])]))
    m = data["multiples_history"]
    if len(m) >= 2 and m[0]["ev_revenue"] and m[-1]["ev_revenue"]:
        chg = m[-1]["ev_revenue"] / m[0]["ev_revenue"] - 1
        rg = m[-1]["revenue"] / m[0]["revenue"] - 1
        out.append(FindingDraft(MODULE, f"EV/Revenue {m[0]['ev_revenue']:.1f}x → {m[-1]['ev_revenue']:.1f}x "
                                        f"({m[0]['as_of']} → {m[-1]['as_of']}) while revenue changed {pct(rg)}",
                                "Multiple expansion beyond operating growth indicates rising expectations.",
                                "watch" if chg > rg + .5 else "neutral", "analytical_inference", "medium",
                                [computed_evidence("Multiple history", chg, "EV/Revenue at each user-supplied price", [])],
                                "Prices are user-supplied; fundamentals point-in-time at each price date."))
    for p in data["providers"]:
        out.append(unavailable(MODULE, p["source"], p["reason"]))
    return out
