"""Competitor intelligence: peer set (user-chosen + same-SIC candidates) and side-by-side economics."""

from __future__ import annotations

from sqlalchemy import select

from deepterminal.data import sec_edgar as se

from ..models import Company, Peer
from ..services import companies as cs
from ..services.evidence import FindingDraft, computed_evidence, fact_evidence, save_evidence, unavailable
from ..services.gateway import DataUnavailable
from .base import Ctx, pct

MODULE = "competitors"
METRIC_LABELS = {"revenue_growth": "Revenue growth", "operating_margin": "Operating margin", "gross_margin": "Gross margin",
                 "fcf_margin": "FCF margin", "rnd_pct": "R&D intensity", "sbc_pct": "SBC intensity", "roe": "Return on equity",
                 "revenue_cagr_3y": "3-year revenue CAGR"}


def metrics_for(company: Company, as_of=None) -> dict:
    facts, meta = cs.companyfacts(company)
    se.check_supported(facts)
    s = lambda n: se.annual_series(facts, n, as_of, "latest")
    rev, oi, ni = s("revenue"), s("operating_income"), s("net_income")
    ends = sorted(set(rev) & set(ni))
    if len(ends) < 2:
        raise DataUnavailable("not_found", "insufficient annual data")
    e, p = ends[-1], ends[-2]
    e3 = ends[-4] if len(ends) >= 4 else None
    def v(n, d=e):
        f = s(n).get(d)
        return f.value / 1e6 if f else None
    r = v("revenue")
    out = {"company_id": company.id, "ticker": company.ticker, "name": company.name, "fy": e.year,
           "synthetic": company.synthetic, "revenue": r, "revenue_growth": r / v("revenue", p) - 1 if v("revenue", p) else None,
           "revenue_cagr_3y": (r / v("revenue", e3)) ** (1 / 3) - 1 if e3 and v("revenue", e3) else None,
           "gross_margin": v("gross_profit") / r if v("gross_profit") is not None else None,
           "operating_margin": v("operating_income") / r if v("operating_income") is not None else None,
           "net_margin": v("net_income") / r if v("net_income") is not None else None,
           "fcf_margin": (v("operating_cash_flow") - v("capex")) / r if None not in (v("operating_cash_flow"), v("capex")) else None,
           "rnd_pct": v("rnd") / r if v("rnd") else None,
           "sbc_pct": v("stock_based_comp") / r if v("stock_based_comp") is not None else None,
           "roe": v("net_income") / v("shareholders_equity") if v("shareholders_equity") else None,
           "net_debt": (v("total_debt") or 0) - (v("cash") or 0),
           "capex_pct": v("capex") / r if v("capex") is not None else None,
           "accession": rev[e].accession, "retrieved_at": meta.retrieved_at.isoformat()}
    return out


def peer_set(db, company: Company) -> list[tuple[Company, str, str]]:
    rows = db.execute(select(Peer, Company).join(Company, Company.id == Peer.peer_id)
                      .where(Peer.company_id == company.id)).all()
    out = [(c, p.relation, p.rationale or "added by user") for p, c in rows]
    have = {c.id for c, _, _ in out}
    if company.sic:
        same = db.scalars(select(Company).where(Company.sic == company.sic, Company.id != company.id,
                                                Company.synthetic == company.synthetic)).all()
        out += [(c, "candidate", f"same SIC code {company.sic}") for c in same if c.id not in have]
    return out


def compute(ctx: Ctx) -> dict:
    subject = metrics_for(ctx.company, ctx.as_of)
    peers, errors = [], []
    for c, rel, why in peer_set(ctx.db, ctx.company):
        try:
            peers.append({**metrics_for(c, ctx.as_of), "relation": rel, "rationale": why})
        except (DataUnavailable, se.UnsupportedFiler) as e:
            errors.append({"ticker": c.ticker, "message": str(e)})
    ranks = {}
    for k in ("revenue_growth", "operating_margin", "gross_margin", "fcf_margin", "rnd_pct", "roe"):
        vals = [x[k] for x in [subject] + peers if x.get(k) is not None]
        if subject.get(k) is not None and len(vals) > 1:
            ranks[k] = {"rank": sorted(vals, reverse=True).index(subject[k]) + 1, "of": len(vals)}
    return {"subject": subject, "peers": peers, "ranks": ranks, "errors": errors,
            "qualitative": {"status": "not_configured",
                            "reason": "Product specifications, benchmarks, pricing, market share and brand strength "
                                      "require third-party data or research evidence; add sourced notes in the "
                                      "evidence system. Not inferred from financials."}}


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    out = []
    if not data["peers"]:
        out.append(unavailable(MODULE, "No peers defined", "Add competitors on the Competitor Comparison screen "
                               "(direct or indirect) so their SEC financials can be compared."))
        return out
    s = data["subject"]
    ids = []
    for co in [ctx.company] + [ctx.db.get(Company, p["company_id"]) for p in data["peers"]]:
        facts, meta = cs.companyfacts(co)
        rev = se.annual_series(facts, "revenue", ctx.as_of, "latest")
        if rev:
            e = max(rev)
            ids.append(save_evidence(ctx.db, co, fact_evidence(co, rev[e], f"{co.ticker} revenue", meta), ctx.job_id, "rules"))
    for k, r in data["ranks"].items():
        vals = sorted(p[k] for p in data["peers"] if p.get(k) is not None)
        n = len(vals)
        med = None if not n else (vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2)
        label = METRIC_LABELS.get(k, k.replace("_", " "))
        # Higher is better for these; R&D and SBC intensity are reported without a judgement.
        directional = k not in ("rnd_pct", "sbc_pct")
        sev = ("positive" if r["rank"] == 1 else ("watch" if r["rank"] == r["of"] else "neutral")) if directional else "neutral"
        out.append(FindingDraft(MODULE, f"{label}: rank {r['rank']} of {r['of']} "
                                        f"({pct(s[k])} vs peer median {pct(med)})",
                                "Peer set: " + ", ".join(f"{p['ticker']} ({p['relation']})" for p in data["peers"]),
                                sev, "analytical_inference", "medium",
                                [computed_evidence(f"{label} comparison", s[k], f"{label} from latest fiscal-year XBRL", ids)],
                                "Fiscal years and accounting policies may differ across peers; candidates by SIC code "
                                "are not necessarily true competitors."))
    out.append(unavailable(MODULE, "Product, pricing and market-share comparison", data["qualitative"]["reason"]))
    return out
