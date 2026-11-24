"""Management & governance: executives, compensation, insider activity, turnover, capital allocation."""

from __future__ import annotations

import re
from datetime import date

from ..services import filings as fs
from ..services.evidence import EvidenceDraft, FindingDraft, computed_evidence, excerpt_evidence, filing_source, save_evidence
from ..services.gateway import DataUnavailable, get_gateway
from .base import Ctx, money, pct

MODULE = "management_governance"


def compute(ctx: Ctx) -> dict:
    db, c = ctx.db, ctx.company
    proxies = ctx.filings(("DEF 14A",))
    comp_history, bios, governance = [], [], []
    gw = get_gateway()
    for f in proxies[:3]:
        try:
            fs.fetch_filing_text(db, c, f)
            html, _ = gw.document(c.cik, f.accession, f.primary_document)
        except DataUnavailable:
            continue
        rows = fs.compensation_table(html)
        for r in rows:
            comp_history.append({**r, "accession": f.accession, "filed": f.filed.isoformat(), "filing_id": f.id})
        full = fs.section(db, f, "full")
        if full and f is proxies[0]:
            for m in re.finditer(r"[^.\n]*\b(independent)\b[^.\n]*\.", full.text, re.I):
                governance.append({"text": m.group(0).strip(), "accession": f.accession, "filing_id": f.id})
    insiders = fs.insider_transactions(db, c, as_of=ctx.as_of)
    departures = [e for e in fs.events(db, c, ctx.as_of) if any(i["code"] == "5.02" for i in e["items"])]
    ends = ctx.fiscal_ends[-6:]
    alloc = []
    for e in ends:
        y = ctx.year(e)
        fcf = None if y.get("operating_cash_flow") is None or y.get("capex") is None else y["operating_cash_flow"] - y["capex"]
        alloc.append({"fy": e.year, "fcf": fcf, "dividends": y.get("dividends_paid"), "buybacks": y.get("buybacks"),
                      "acquisitions": y.get("acquisitions"), "sbc": y.get("stock_based_comp"),
                      "capex": y.get("capex"), "rnd": y.get("rnd"), "shares": y.get("diluted_shares")})
    # Each proxy repeats the prior two years: keep one row per executive and year, from the latest proxy.
    latest: dict[tuple, dict] = {}
    for r in sorted(comp_history, key=lambda r: r["filed"]):
        latest[(r["name"], r["year"])] = r
    comp_history = sorted(latest.values(), key=lambda r: (r["name"], -r["year"]))
    by_exec: dict[str, list] = {}
    for r in comp_history:
        by_exec.setdefault(r["name"], []).append(r)
    return {"executives": [{"name": n, "latest_total": max(rs, key=lambda r: r["year"])["total"],
                            "latest_year": max(r["year"] for r in rs),
                            "position": next((r["position"] for r in rs if r.get("position")), None), "history": rs}
                           for n, rs in by_exec.items()],
            "compensation_rows": comp_history, "governance_statements": governance[:6], "insiders": insiders,
            "officer_changes": departures, "capital_allocation": alloc,
            "not_connected": [{"check": "Education and career claims", "status": "not_verified",
                               "reason": "Biographical claims come from the company's proxy; independent verification "
                                         "(registries, university records) is not connected."}]}


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    c, db = ctx.company, ctx.db
    out: list[FindingDraft] = []
    ins = data["insiders"]
    if ins["transactions"]:
        evs = []
        for t in ins["transactions"][:8]:
            evs.append(EvidenceDraft("insider_transaction",
                                     f"Form 4: {t['owner']} ({t['role']}) {t['code_description']} {t['shares']:,.0f} sh @ {t['price']} on {t['date']}",
                                     "historical_fact", filing_source(c, t["accession"], "4", date.fromisoformat(t["filed"]),
                                                                      t["url"], None), value=t["value"], unit="USD",
                                     verification_status="verified", locator=f"{t['accession']} nonDerivativeTransaction"))
        net = ins["open_market_buy_value"] - ins["open_market_sell_value"]
        out.append(FindingDraft(MODULE, f"Insider open-market activity: buys ${ins['open_market_buy_value'] / 1e6:,.1f}m, "
                                        f"sells ${ins['open_market_sell_value'] / 1e6:,.1f}m (recent Form 4s)",
                                "Net selling by insiders is common (diversification, taxes, 10b5-1 plans) and is a weak "
                                "signal on its own; clustered buying is historically more informative.",
                                "watch" if net < 0 and abs(net) > 5e7 else "neutral", "historical_fact", "high", evs,
                                "Limited to the most recent Form 4 filings; 10b5-1 plan status not parsed."))
    if data["executives"]:
        evs = []
        for r in data["compensation_rows"][:6]:
            f = next(x for x in ctx.filings(("DEF 14A",)) if x.accession == r["accession"])
            evs.append(EvidenceDraft("table_row", f"Summary Compensation Table: {r['name']} total ${r['total']:,.0f}",
                                     "company_statement", filing_source(c, f.accession, f.form, f.filed, f.url,
                                                                        f.text_retrieved_at), value=r["total"], unit="USD",
                                     verification_status="unverified",
                                     limitations="Extracted from an HTML table by a parser; verify against the proxy."))
        top = max(data["executives"], key=lambda e: e["latest_total"] or 0)
        out.append(FindingDraft(MODULE, f"Highest-paid executive: {top['name']} (${(top['latest_total'] or 0) / 1e6:,.1f}m total)",
                                f"{len(data['executives'])} named executive officers in the latest proxy statements.",
                                "neutral", "company_statement", "medium", evs))
    if data["officer_changes"]:
        evs = [EvidenceDraft("filing_event", f"8-K Item 5.02 filed {e['filed']}", "historical_fact",
                             filing_source(c, e["accession"], "8-K", date.fromisoformat(e["filed"]), e["url"], None),
                             verification_status="verified") for e in data["officer_changes"][:5]]
        out.append(FindingDraft(MODULE, f"{len(data['officer_changes'])} director/officer change filing(s) (8-K Item 5.02)",
                                "Turnover in finance or accounting roles deserves attention alongside other signals.",
                                "watch" if len(data["officer_changes"]) >= 2 else "neutral", "historical_fact", "high", evs))
    alloc = [a for a in data["capital_allocation"] if a["fcf"] is not None]
    if alloc:
        tot = lambda k: sum((a[k] or 0) for a in alloc)
        f_ids = [save_evidence(db, c, e, ctx.job_id, "rules") for e in ctx.evs(
            [(n, d) for d in ctx.fiscal_ends[-len(alloc):] for n in ("operating_cash_flow", "capex", "dividends_paid",
                                                                       "buybacks", "stock_based_comp")])]
        returned = tot("dividends") + tot("buybacks")
        comp = computed_evidence(f"{len(alloc)}-year FCF {money(tot('fcf'))}; dividends+buybacks {money(returned)}; "
                                 f"SBC {money(tot('sbc'))}", returned, "Σ(dividends + buybacks) vs Σ(OCF − capex)", f_ids)
        ratio = returned / tot("fcf") if tot("fcf") > 0 else None
        out.append(FindingDraft(MODULE, f"Capital allocation: returned {pct(ratio)} of {len(alloc)}-year free cash flow",
                                f"Dividends {money(tot('dividends'))}, buybacks {money(tot('buybacks'))}, acquisitions "
                                f"{money(tot('acquisitions'))}, SBC {money(tot('sbc'))} against FCF {money(tot('fcf'))}.",
                                "watch" if ratio is not None and ratio > 1.2 else "neutral", "analytical_inference",
                                "medium", [comp], "Buybacks partly offset SBC dilution; check net share count change."))
    for g in data["governance_statements"][:1]:
        f = next(x for x in ctx.filings(("DEF 14A",)) if x.accession == g["accession"])
        out.append(FindingDraft(MODULE, "Board independence statement", g["text"], "neutral", "company_statement",
                                "medium", [excerpt_evidence(db, c, f, "full", g["text"])]))
    return out
