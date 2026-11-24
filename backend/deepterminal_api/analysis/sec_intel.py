"""SEC filing intelligence: timeline, risk-factor changes, material events, restatements,
accounting changes and management statements versus later outcomes."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date

from deepterminal.data import sec_edgar as se

from ..config import get_settings
from ..services import filings as fs
from ..services.evidence import FindingDraft, computed_evidence, excerpt_evidence, fact_evidence
from ..services.gateway import DataUnavailable
from .base import Ctx, pct, clip

MODULE = "sec_analysis"
FORWARD = re.compile(r"\b(we (expect|anticipate|believe|plan|intend|will)|outlook|guidance)\b", re.I)
RANGE = re.compile(r"(?:revenue|sales)?[^.%]{0,60}?(-?\d+(?:\.\d+)?)\s*%\s*(?:to|-|–)\s*(-?\d+(?:\.\d+)?)\s*%", re.I)
POINT = re.compile(r"(?:revenue|sales)[^.%]{0,60}?(?:growth|grow|increase)[^.%]{0,30}?(?:approximately|about|of)\s*(-?\d+(?:\.\d+)?)\s*%", re.I)
ACCOUNTING = re.compile(r"[^.]*\b(adopted (ASU|ASC)|change in accounting (principle|estimate)|restat(ed|ement)|"
                        r"material weakness)\b[^.]*\.", re.I)


def _sentences(t: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", t.replace("\n", " ")) if 20 < len(s.strip()) < 600]


def compute(ctx: Ctx) -> dict:
    db, c = ctx.db, ctx.company
    limit = get_settings().max_filing_documents_per_job
    all_f = ctx.filings(("10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A", "4", "DEF 14A", "S-1", "SC 13G", "SC 13D",
                         "SC 13G/A", "SC 13D/A", "10-KT"))
    counts = Counter((f.filed.year, f.form) for f in all_f)
    timeline = [{"accession": f.accession, "form": f.form, "filed": f.filed.isoformat(),
                 "report_date": f.report_date.isoformat() if f.report_date else None, "url": f.url,
                 "items": f.items, "synthetic": f.synthetic} for f in all_f[:400]]
    ten_ks = fs.ten_k_filings(db, c, ctx.as_of)
    errors = []
    for f in ten_ks[: min(limit, 6)]:
        try:
            fs.fetch_filing_text(db, c, f)
        except DataUnavailable as e:
            errors.append(e.to_dict())
    risk_change = None
    if len(ten_ks) >= 2:
        try:
            risk_change = fs.compare_sections(db, c, ten_ks[1], ten_ks[0], "item_1a")
        except DataUnavailable as e:
            errors.append(e.to_dict())
    events = [e for e in fs.events(db, c, ctx.as_of) if any(i["significance"] != "info" for i in e["items"])]

    # management statements vs subsequent actuals
    revenue = ctx.series("revenue")
    statements = []
    for f in ten_ks[:6]:
        sec = fs.section(db, f, "item_7")
        if not sec:
            continue
        fy = f.report_date.year if f.report_date else f.filed.year - 1
        for s in _sentences(sec.text):
            if not FORWARD.search(s):
                continue
            m, p = RANGE.search(s), POINT.search(s)
            target = None
            if m and re.search(r"revenue|sales", s, re.I):
                target = (float(m.group(1)) / 100, float(m.group(2)) / 100)
            elif p:
                v = float(p.group(1)) / 100
                target = (v - 0.01, v + 0.01)
            outcome = None
            nxt = next((e for e in revenue if e.year == fy + 1), None)
            cur = next((e for e in revenue if e.year == fy), None)
            if target and nxt and cur:
                actual = revenue[nxt].value / revenue[cur].value - 1
                outcome = {"actual_growth": actual, "status": "met" if target[0] - 1e-9 <= actual <= target[1] + 1e-9
                           else ("exceeded" if actual > target[1] else "missed"),
                           "actual_accession": revenue[nxt].accession}
            statements.append({"fy": fy, "accession": f.accession, "filing_id": f.id, "statement": s,
                               "target_range": target, "outcome": outcome})
    accounting = []
    for f in ten_ks[:6]:
        full = fs.section(db, f, "full")
        if not full:
            continue
        for s in {m.group(0).strip() for m in ACCOUNTING.finditer(full.text)}:
            if 20 < len(s) < 600:
                accounting.append({"fy": f.report_date.year if f.report_date else None, "accession": f.accession,
                                   "filing_id": f.id, "text": s})
    revisions = [{"field": r.field, "period_end": r.period_end.isoformat(), "original": r.original / 1e6,
                  "revised": r.revised / 1e6, "change": r.revised / r.original - 1 if r.original else None,
                  "revised_accession": r.revised_accession, "revised_filed": r.revised_filed.isoformat(),
                  "kind": r.kind, "split_ratio": r.split_ratio}
                 for r in se.detect_revisions(ctx.facts, as_of=ctx.as_of)]
    nonreliance = [e for e in fs.events(db, c, ctx.as_of) if any(i["code"] == "4.02" for i in e["items"])]
    return {"timeline": timeline, "counts": [{"year": y, "form": fm, "n": n} for (y, fm), n in sorted(counts.items())],
            "risk_change": risk_change, "material_events": events, "management_statements": statements,
            "accounting_changes": accounting[:30], "restatements": {"xbrl_revisions": revisions,
                                                                   "non_reliance_8k": nonreliance},
            "errors": errors[:5]}


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    db, c = ctx.db, ctx.company
    out: list[FindingDraft] = []
    rc = data.get("risk_change")
    if rc:
        filing = next(f for f in ctx.filings(("10-K", "10-K/A")) if f.accession == rc["to"]["accession"])
        evs = [excerpt_evidence(db, c, filing, "item_1a", a["text"], "company_statement",
                                f"New risk factor in 10-K filed {rc['to']['filed']}") for a in rc["diff"]["added"][:6]]
        sev = "watch" if rc["counts"]["added"] else "neutral"
        out.append(FindingDraft(MODULE, f"Risk factors: {rc['counts']['added']} added, {rc['counts']['removed']} removed, "
                                        f"{rc['counts']['modified']} modified since the prior 10-K",
                                "New disclosures: " + "; ".join(clip(a["text"], 140) for a in rc["diff"]["added"][:4])
                                if rc["diff"]["added"] else "No new risk-factor paragraphs detected.",
                                sev, "company_statement", "high" if evs else "medium",
                                evs or [computed_evidence("Risk factor comparison", None, "paragraph diff", [])],
                                "Paragraph matching is heuristic (similarity thresholds 0.6/0.97)."))
    for e in data["material_events"][:8]:
        items = [i for i in e["items"] if i["significance"] != "info"]
        f = next((x for x in ctx.filings(("8-K", "8-K/A")) if x.accession == e["accession"]), None)
        if not f:
            continue
        from ..services.evidence import filing_source, EvidenceDraft
        ev = EvidenceDraft("filing_event", f"8-K filed {e['filed']}: items {', '.join(i['code'] for i in e['items'])}",
                           "historical_fact", filing_source(c, f.accession, f.form, f.filed, f.url, None, f.report_date),
                           locator=f"{f.accession} items {','.join(f.items)}", verification_status="verified",
                           limitations="Item codes from the SEC filing index; read the filing for details.")
        sev = "concern" if any(i["significance"] == "concern" for i in items) else "watch"
        out.append(FindingDraft(MODULE, f"8-K {e['filed']}: " + "; ".join(i["description"] for i in items),
                                "Material event disclosed on Form 8-K.", sev, "historical_fact", "high", [ev]))
    revs = [r for r in data["restatements"]["xbrl_revisions"] if r.get("kind", "revision") == "revision"]
    for r in revs[:6]:
        if r["field"] not in ("revenue", "net_income", "operating_income", "operating_cash_flow"):
            continue
        end = date.fromisoformat(r["period_end"])
        orig = se.annual_series(ctx.facts, r["field"], ctx.as_of, "original").get(end)
        late = ctx.series(r["field"]).get(end)
        evs = [fact_evidence(c, x, r["field"], ctx.meta) for x in (orig, late) if x]
        out.append(FindingDraft(MODULE, f"{r['field'].replace('_', ' ').title()} for FY{end.year} revised "
                                        f"{pct(r['change'])} in a later filing",
                                f"Originally {r['original']:,.0f}m, later {r['revised']:,.0f}m "
                                f"(filed {r['revised_filed']}). Revisions can reflect restatements, reclassifications "
                                "or discontinued operations; read the later filing.",
                                "watch", "historical_fact", "high", evs))
    met = [s for s in data["management_statements"] if s["outcome"]]
    if met:
        evs = []
        for s in met[:6]:
            f = next(x for x in ctx.filings(("10-K", "10-K/A")) if x.accession == s["accession"])
            evs.append(excerpt_evidence(db, c, f, "item_7", s["statement"], "company_statement",
                                        f"FY{s['fy']} outlook statement"))
        missed = [s for s in met if s["outcome"]["status"] == "missed"]
        out.append(FindingDraft(MODULE, f"Management revenue outlook: {len(met) - len(missed)} of {len(met)} "
                                        "quantified statements met or exceeded",
                                "; ".join(f"FY{s['fy'] + 1}: target {pct(s['target_range'][0])}–{pct(s['target_range'][1])}, "
                                          f"actual {pct(s['outcome']['actual_growth'])} ({s['outcome']['status']})"
                                          for s in met[:6]),
                                "concern" if len(missed) > len(met) / 2 else ("watch" if missed else "positive"),
                                "analytical_inference", "medium", evs,
                                "Only statements with explicit revenue-growth percentages are scored; "
                                "organic vs reported growth differences are not adjusted."))
    if data["accounting_changes"]:
        a = data["accounting_changes"][:4]
        evs = []
        for x in a:
            f = next(y for y in ctx.filings(("10-K", "10-K/A")) if y.accession == x["accession"])
            evs.append(excerpt_evidence(db, c, f, "full", x["text"], "company_statement", "Accounting change disclosure"))
        out.append(FindingDraft(MODULE, f"{len(data['accounting_changes'])} accounting-policy/restatement mentions in recent 10-Ks",
                                " | ".join(clip(x["text"], 160) for x in a), "watch" if any(
                                    re.search(r"restat|material weakness", x["text"], re.I) for x in a) else "neutral",
                                "company_statement", "medium", evs))
    return out
