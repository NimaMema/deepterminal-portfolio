"""Legal & regulatory intelligence from company filings (enforcement databases not connected)."""

from __future__ import annotations

import re
from datetime import date

from ..services import filings as fs
from ..services.evidence import EvidenceDraft, FindingDraft, SourceDraft, computed_evidence, excerpt_evidence, unavailable
from ..services.gateway import DataUnavailable
from .base import Ctx, clip

MODULE = "legal_regulatory"
TOPICS = {
    "export controls": r"export control|entity list|export restriction",
    "tariffs & trade": r"\btariff",
    "antitrust": r"antitrust|competition authorit|anti-competitive",
    "data privacy": r"privacy|GDPR|data protection",
    "environmental": r"environmental regulation|emissions|climate",
    "securities litigation": r"class action|securities litigation|shareholder lawsuit",
    "government investigations": r"subpoena|investigation by|Department of Justice|SEC staff",
    "sanctions": r"\bsanction",
    "tax disputes": r"tax (audit|dispute|assessment)",
    "product liability": r"product liability|recall",
}


def compute(ctx: Ctx) -> dict:
    db, c = ctx.db, ctx.company
    hits = []
    for f in ctx.filings(("10-K", "10-K/A"))[:2]:
        try:
            fs.fetch_filing_text(db, c, f)
        except DataUnavailable:
            continue
        for key in ("item_1a", "item_3"):
            sec = fs.section(db, f, key)
            if not sec:
                continue
            for para in sec.text.split("\n"):
                for topic, rx in TOPICS.items():
                    if re.search(rx, para, re.I) and len(para) > 40:
                        hits.append({"topic": topic, "section": key, "accession": f.accession, "filing_id": f.id,
                                     "filed": f.filed.isoformat(), "text": para[:800]})
    fedreg, fedreg_error = [], None
    if not c.synthetic:
        from .mentions import search_phrase
        from ..services.free_sources import free_sources
        try:
            fedreg, _ = free_sources().federal_register(search_phrase(c.name))
        except DataUnavailable as e:
            fedreg_error = e.to_dict()
    topics: dict[str, list] = {}
    for h in hits:
        topics.setdefault(h["topic"], []).append(h)
    return {"topics": [{"topic": t, "mentions": len(v), "examples": v[:3]} for t, v in sorted(topics.items(),
                                                                                          key=lambda kv: -len(kv[1]))],
            "federal_register": fedreg[:20], "federal_register_error": fedreg_error,
            "not_connected": [
                {"source": "SEC enforcement actions", "status": "unavailable",
                 "reason": "SEC litigation releases have no search API; adapter not implemented."},
                {"source": "Federal court dockets", "status": "not_configured",
                 "reason": "PACER charges per page (not used); CourtListener's free API is not integrated yet."}]
            + ([{"source": "Federal Register", "status": fedreg_error["status"], "reason": fedreg_error["message"]}]
               if fedreg_error else [])
            + ([{"source": "Federal Register", "status": "not_applicable",
                 "reason": "Demo companies are fictional."}] if c.synthetic else [])}


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    out = []
    for t in data["topics"][:6]:
        ex = t["examples"][0]
        f = next(x for x in ctx.filings(("10-K", "10-K/A")) if x.accession == ex["accession"])
        out.append(FindingDraft(MODULE, f"Regulatory exposure disclosed: {t['topic']} ({t['mentions']} passage(s))",
                                clip(ex["text"], 400), "watch", "company_statement", "medium",
                                [excerpt_evidence(ctx.db, ctx.company, f, ex["section"], ex["text"])],
                                "Keyword-based detection in risk factors and legal proceedings."))
    from .mentions import search_phrase
    name = search_phrase(ctx.company.name).lower()
    docs = data.get("federal_register", [])
    # Documents about the company name it in the title or abstract. Exchange rule filings
    # ("Self-Regulatory Organizations; …") often list a ticker among many and are counted, not reported.
    about = [d for d in docs if name in ((d.get("title") or "") + " " + (d.get("abstract") or "")).lower()
             and not (d.get("title") or "").startswith("Self-Regulatory Organizations")]
    incidental = len(docs) - len(about)
    if docs and incidental:
        out.append(FindingDraft(MODULE, f"Federal Register: {incidental} document(s) mention the company only incidentally",
                                "Full-text matches outside the title and abstract (often exchange rule filings listing "
                                "products on many securities). Not treated as regulatory exposure.", "neutral",
                                "analytical_inference", "low",
                                [computed_evidence("Federal Register full-text matches", len(docs),
                                                   "federalregister.gov documents search, newest first", [])]))
    for d in about[:5]:
        src = SourceDraft(f"FR:{d['url']}", "government_record", d["title"] or "Federal Register document",
                          "Federal Register (federalregister.gov)", d["url"],
                          date.fromisoformat(d["date"]) if d.get("date") else None, licence="US government public data")
        ev = EvidenceDraft("registry_record", f"{d['type']}: {d['title']}", "historical_fact", src,
                           excerpt=(d.get("abstract") or "")[:1000] or None, verification_status="verified",
                           limitations="Full-text match on the company name; the document may concern it only in passing.")
        out.append(FindingDraft(MODULE, f"Federal Register {d['type'].lower()} naming the company ({d['date']}): "
                                        f"{clip(d['title'] or '', 120)}",
                                f"{', '.join(d['agencies']) or 'Agency not stated'}. {clip(d.get('abstract') or '', 300)}",
                                "neutral", "historical_fact", "medium", [ev],
                                "Name match in a federal publication; read the document for its relevance."))
    for nc in data["not_connected"]:
        out.append(unavailable(MODULE, f"{nc['source']}: not searched", nc["reason"]))
    return out
