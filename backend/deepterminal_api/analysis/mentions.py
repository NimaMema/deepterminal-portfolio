"""Mentions by other filers (EDGAR full-text search — free).

Who names this company in their own annual reports, and how: as a supplier they depend on,
a customer, a competitor or a partner. Each mention is quoted from the other company's filing
(fetched from EDGAR and verified), so supply-chain and competitive links come from both sides,
not only from the company's own disclosures.
"""

from __future__ import annotations

import re
from datetime import date

from ..services import filings as fs
from ..services.evidence import EvidenceDraft, FindingDraft, SourceDraft, unavailable
from ..services.free_sources import free_sources, normalise_name
from ..services.gateway import ARCHIVES, DataUnavailable, get_gateway
from .base import Ctx, clip

MODULE = "external_mentions"
MAX_DOCS = 8

RELATIONS = [
    # (label, pattern with {n} = the name) — first match wins; heuristic, always shown with the quote.
    ("names it as an investor", r"(private placement|invest\w*|shares of[^.]{0,60}(issued|sold) to|stockholder|"
                                r"shareholder)[^.]{0,120}\b{n}|\b{n}\b[^.]{0,60}(invest\w*|acquired[^.]{0,20}shares|stake)"),
    ("names it as a competitor", r"compet\w*|rival"),
    ("depends on it as a supplier",
     r"(purchas\w*|buy|bought|procur\w*|sourc\w*|obtain\w*|acquir\w*)[^.]{0,100}\b{n}\b"
     r"|(dependent|depend\w*|rel(y|ies|ied)) (on|upon)\s+{n}"
     r"|\b{n}\b[^.]{0,40}\bas (a|an|our|the) (\w+ )?(supplier|vendor|source)"
     r"|(supplier|vendor)s?\b[^.]{0,40}(such as|includ\w*|like)[^.]{0,80}\b{n}"
     r"|\b{n}\b[^.]{0,30}\b(supplies|manufactures|fabricates)\b"),
    ("names it as a customer", r"(sales to|revenue from|customers?,? (such as|includ\w*))[^.]{0,120}\b{n}"),
    ("names it as a partner", r"partner\w*|collaborat\w*|alliance|joint venture"),
]


def search_phrase(name: str) -> str:
    """Phrase used for full-text search: the distinctive part of the registered name.
    Single common-looking words keep their legal suffix ("Apple Inc") to avoid matching ordinary words."""
    core = normalise_name(name)
    words = core.split()
    if len(words) == 1 and not name.split()[0].isupper():
        suffix = re.search(r"\b(Inc|Corp|Corporation|Co|Ltd|plc|LLC)\b", name, re.I)
        return f"{core.title()} {suffix.group(1)}" if suffix else core.title()
    return core if len(words) > 1 else words[0]


def relation(sentence: str, phrase: str) -> str:
    n = re.escape(phrase)
    sentence = re.sub(r"(\d)\.(\d)", r"\1,\2", sentence)      # "5.5k GPUs": a decimal is not a sentence end
    for label, rx in RELATIONS:
        if re.search(rx.replace("{n}", n), sentence, re.I):
            return label
    return "mentions it"


def compute(ctx: Ctx) -> dict:
    c = ctx.company
    if c.synthetic:
        raise DataUnavailable("not_configured", "Demo companies are fictional; other filers cannot mention them.",
                              "Use live mode for real companies.")
    phrase = ctx.cache.get("params", {}).get("phrase") or search_phrase(c.name)
    hits, res = free_sources().edgar_mentions(phrase, forms="10-K")
    others = [h for h in hits if c.cik not in h["ciks"]]
    seen, docs = set(), []
    for h in others:                       # one document per other filer, main 10-K text first
        key = h["ciks"][0] if h["ciks"] else h["accession"]
        if key in seen:
            continue
        seen.add(key)
        docs.append(h)
        if len(docs) >= MAX_DOCS:
            break
    mentions, errors = [], []
    gw = get_gateway()
    pat = re.compile(r"\b" + re.escape(phrase) + r"\b", re.I)
    for h in docs:
        try:
            html, meta = gw.document(h["ciks"][0], h["accession"], h["document"])
        except DataUnavailable as e:
            errors.append(e.to_dict())
            continue
        text = " ".join(fs.html_to_text(html).split())
        sentences = [s for s in re.split(r"(?<=[.;])\s+", text) if pat.search(s) and 40 <= len(s) <= 700][:3]
        for s in sentences:
            mentions.append({"filer": re.sub(r"\s+\(CIK.*$", "", h["names"][0]) if h["names"] else str(h["ciks"][0]),
                             "cik": h["ciks"][0], "sic": (h["sics"] or [None])[0], "form": h["form"],
                             "filed": h["filed"], "accession": h["accession"], "document": h["document"],
                             "url": ARCHIVES.format(cik=h["ciks"][0], accn=h["accession"].replace("-", ""),
                                                        name=h["document"]),
                             "retrieved_at": meta.retrieved_at.isoformat(), "text": s, "relation": relation(s, phrase)})
    by_rel: dict[str, int] = {}
    for m in mentions:
        by_rel[m["relation"]] = by_rel.get(m["relation"], 0) + 1
    return {"phrase": phrase, "total_hits": len(hits), "other_filers": len({h["ciks"][0] for h in others if h["ciks"]}),
            "documents_read": len(docs), "mentions": mentions, "by_relation": by_rel, "errors": errors[:3],
            "method": "EDGAR full-text search for the company's name in other companies' 10-Ks filed in the last "
                      "18 months; up to eight filers are read and the sentences naming the company are quoted. "
                      "The relation label is keyword-based and shown with its quote.",
            "search_url": res.url}


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    out: list[FindingDraft] = []
    if not data["mentions"]:
        return [unavailable(MODULE, "No quotable mentions by other filers found",
                            f"Searched '{data['phrase']}' in other companies' 10-Ks ({data['total_hits']} hits).")]
    rank = {"depends on it as a supplier": 0, "names it as a customer": 1, "names it as a competitor": 2,
            "names it as an investor": 3, "names it as a partner": 4, "mentions it": 5}
    by_filer: dict[int, list[dict]] = {}
    for m in data["mentions"]:
        by_filer.setdefault(m["cik"], []).append(m)
    for ms in list(by_filer.values())[:10]:          # one finding per filer: its most informative relation
        ms.sort(key=lambda m: rank.get(m["relation"], 9))
        top = ms[0]
        evs = []
        for m in ms[:3]:
            src = SourceDraft(f"SEC:{m['accession']}", "sec_filing", f"{m['filer']} {m['form']} (accession {m['accession']})",
                              "U.S. Securities and Exchange Commission — EDGAR", m["url"], date.fromisoformat(m["filed"]),
                              None, None, m["accession"], "US government public data")
            evs.append(EvidenceDraft("excerpt", f"{m['filer']} {m['form']} filed {m['filed']}", "third_party_report", src,
                                     excerpt=m["text"][:2000], locator=f"{m['accession']}/{m['document']}",
                                     verification_status="verified",
                                     limitations="Quoted from another company's filing; the relation label is keyword-based."))
        sev = "watch" if top["relation"] == "names it as a competitor" else "neutral"
        others = sorted({m["relation"] for m in ms[1:]} - {top["relation"]})
        out.append(FindingDraft(MODULE, f"{top['filer']} {top['relation']}", clip(top["text"], 400)
                                + (f" (Also: {', '.join(others)}.)" if others else ""), sev,
                                "third_party_report", "medium", evs,
                                "Sentences from another filer's 10-K; read the filing for context."))
    return out
