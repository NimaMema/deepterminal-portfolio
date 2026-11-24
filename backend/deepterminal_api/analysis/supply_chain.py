"""Supply-chain intelligence from filings: entities, geography, single-source and trade exposure, inventory.

Relationships are extracted from the company's own disclosures; every graph edge
carries the quoted passage it came from and is labelled ``extracted mention``
(company statement), not an independently confirmed relationship.
"""

from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import delete, select

from ..models import Company, EntityLink
from ..services import filings as fs
from ..services.evidence import FindingDraft, computed_evidence, excerpt_evidence, save_evidence, unavailable
from ..services.gateway import DataUnavailable
from .base import Ctx, pct, clip

MODULE = "supply_chain"
SUFFIX = r"(?:Inc\.?|Incorporated|Corporation|Corp\.?|Co\.,? Ltd\.?|Company|Ltd\.?|Limited|LLC|L\.L\.C\.|GmbH|S\.A\.|" \
         r"N\.V\.|B\.V\.|plc|PLC|AG|SE|Holdings|Pte\.? Ltd\.?|K\.K\.)"
ENTITY = re.compile(r"\b((?:[A-Z][A-Za-z0-9&'\-]+\s+){0,5}[A-Z][A-Za-z0-9&'\-]+,?\s+" + SUFFIX + r")")
SUPPLY_WORDS = re.compile(r"supplier|suppl(y|ies|ied)|purchase|foundr|manufactur|vendor|source[sd]?\b|"
                          r"assembl|contract manufactur|component|raw material|substrate|wafer", re.I)
COUNTRIES = ["United States", "China", "Taiwan", "Japan", "South Korea", "Korea", "Germany", "Mexico", "Vietnam",
             "Malaysia", "India", "Brazil", "Netherlands", "Israel", "Singapore", "Thailand", "Philippines", "Canada",
             "United Kingdom", "France", "Italy", "Ireland", "Indonesia", "Russia", "Ukraine"]
ALTERNATIVE = re.compile(r"(second|alternative|additional|backup|another) (source|supplier|foundr\w*|manufacturer|vendor)s?|"
                         r"dual[- ]sourc|multi[- ]sourc|multiple (sources|suppliers)|qualif\w* (an? )?(second|alternative|additional|new) "
                         r"(source|supplier|foundr\w*|manufacturer)", re.I)
SIGNALS = {
    "single_source": r"sole[- ]source|single[- ]source|single supplier|sole supplier|limited number of (third-party )?(suppliers|foundries|manufacturers)",
    "export_controls": r"export control|entity list|export restriction",
    "tariffs": r"\btariff",
    "geopolitical": r"geopolitic|military conflict|war\b|political instability",
    "natural_hazard": r"earthquake|natural disaster|typhoon|flood|pandemic",
    "capacity": r"capacity (constraint|shortage)|supply (constrain|shortage)|demand to exceed supply|supply remains constrained",
    "commodity": r"commodit|steel price|aluminum|energy cost|raw material cost",
    "logistics": r"freight|shipping|logistics|port congestion",
}


# A sentence establishes a supply relationship only when the company itself is the buyer or the
# outsourcer ("we purchase … from X", "we utilize foundries, such as X", "our contract manufacturers
# include X"). Lists of competitors and executive biographies name many companies near words like
# "suppliers" or "manufacturer" without any relationship.
RELATION = re.compile(
    r"\b(?:we|our|us)\b[^.;]{0,80}?\b(?:utiliz\w*|use|uses|purchas\w*|buy|bought|source[sd]?|obtain\w*|procur\w*|"
    r"rel(?:y|ies|ied) (?:on|upon)|depend\w* (?:on|upon)|engag\w*|contract\w* with|outsourc\w*|partner\w* with)\b|"
    r"\bour (?:suppliers|foundr\w*|contract manufacturers|subcontractors|vendors|manufacturing partners)\b|"
    r"\b(?:manufactur\w*|produc\w*|fabricat\w*|assembl\w*|suppli\w*) (?:for|to) us\b", re.I)
NOT_RELATION = re.compile(r"\bcompet\w*|\brival|\bemployed\b|\bserved (?:as|from|on)\b|\bjoined\b|"
                          r"\bheld (?:a|various|the)\b|prior to joining|\bcareer\b|\bwas (?:a|the) (?:founder|director)", re.I)
MANUFACTURING = re.compile(r"foundr|manufactur|fabricat|assembl|packag|\btest", re.I)


def extract_relationships(sent: str, own_words: set[str] = frozenset()) -> list[tuple[str, str, str | None]]:
    """(entity, role, country) for each counterparty the sentence says the company buys from or outsources to."""
    if not RELATION.search(sent) or NOT_RELATION.search(sent):
        return []
    role = "manufacturer" if MANUFACTURING.search(sent) else "supplier"
    out = []
    for m in ENTITY.finditer(sent):
        name = m.group(1).strip().rstrip(",")
        words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", name)}
        if words & own_words and len(words & own_words) >= len(words) - 1:
            continue     # the company itself or its subsidiaries
        # Country only when the text places this entity there ("…, located in Taiwan").
        near = re.match(r"[^.;]{0,60}?\b(?:located|based|headquartered|operat\w*)? ?in (?:the )?(" +
                        "|".join(re.escape(k) for k in COUNTRIES) + r")\b", sent[m.end():])
        out.append((name, role, near.group(1) if near else None))
    return out


def compute(ctx: Ctx) -> dict:
    db, c = ctx.db, ctx.company
    own = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", c.name)}
    nodes: dict[str, dict] = {}
    edges, signals = [], []
    country_counts: Counter = Counter()
    errors, mitigations = [], []
    for f in ctx.filings(("10-K", "10-K/A"))[:2]:
        try:
            fs.fetch_filing_text(db, c, f)
        except DataUnavailable as e:
            errors.append(e.to_dict())
            continue
        for key in ("item_1", "item_1a", "item_7"):
            sec = fs.section(db, f, key)
            if not sec:
                continue
            for whole in re.split(r"(?<=\.)\s+", sec.text.replace("\n", " ")):   # full sentences keep caveats
                if 40 <= len(whole) <= 900 and ALTERNATIVE.search(whole) and SUPPLY_WORDS.search(whole) \
                        and not any(m["text"] == whole.strip() for m in mitigations):
                    mitigations.append({"text": whole.strip(), "accession": f.accession, "section": key,
                                        "filed": f.filed.isoformat()})
            for sent in re.split(r"(?<=[.;])\s+", sec.text.replace("\n", " ")):
                if len(sent) > 900 or len(sent) < 40:
                    continue
                for sig, rx in SIGNALS.items():
                    if re.search(rx, sent, re.I):
                        signals.append({"signal": sig, "text": sent.strip(), "accession": f.accession, "section": key,
                                        "filed": f.filed.isoformat()})
                masked = ENTITY.sub(" ", sent)        # "Taiwan Semiconductor…" is a name, not a location
                ctry = [k for k in COUNTRIES if re.search(r"\b" + re.escape(k) + r"\b", masked)]
                if SUPPLY_WORDS.search(sent):
                    country_counts.update(ctry)
                for name, role, country in extract_relationships(sent, own):
                    nodes.setdefault(name, {"name": name, "type": role, "countries": set(), "mentions": 0})
                    nodes[name]["mentions"] += 1
                    if country:
                        nodes[name]["countries"].add(country)
                    edges.append({"entity": name, "relation": role, "country": country,
                                  "text": sent.strip(), "accession": f.accession, "filing_id": f.id,
                                  "section": key, "filed": f.filed.isoformat(),
                                  "single_source": bool(re.search(SIGNALS["single_source"], sent, re.I))})
    # de-duplicate edges per entity (keep first/most recent)
    seen, uniq = set(), []
    for e in edges:
        if e["entity"] not in seen:
            seen.add(e["entity"])
            uniq.append(e)
    sig_counts = Counter(s["signal"] for s in signals)
    alternatives = _alternatives(db, c, uniq, mitigations)
    inv = []
    for e in ctx.fiscal_ends[-6:]:
        y = ctx.year(e)
        if y.get("inventory") is not None and y.get("cost_of_revenue"):
            inv.append({"fy": e.year, "inventory": y["inventory"], "dio": y["inventory"] * 365 / y["cost_of_revenue"],
                        "revenue": y.get("revenue")})
    return {"nodes": [{**n, "countries": sorted(n["countries"])} for n in nodes.values()], "edges": uniq,
            "countries": [{"country": k, "mentions": v} for k, v in country_counts.most_common()],
            "signals": [{"signal": k, "mentions": v, "examples": [s for s in signals if s["signal"] == k][:3]}
                        for k, v in sig_counts.most_common()],
            "inventory": inv, "errors": errors[:3], "alternatives": alternatives, "mitigations": mitigations[:6],
            "method": "Entities are extracted from sentences that mention supply, purchasing or manufacturing and "
                      "end in a corporate suffix; they are company statements, not confirmed relationships.",
            "not_connected": [{"source": "Customs / bill-of-lading data", "status": "not_configured",
                               "reason": "Licensed trade data (e.g. Panjiva, ImportGenius) not purchased."},
                              {"source": "Supplier financial health", "status": "partial",
                               "reason": "Only suppliers that are SEC registrants can be analysed; add them as peers."}]}


GENERIC_NAME_WORDS = {"corporation", "company", "limited", "holdings", "group", "international", "services",
                      "incorporated", "industries", "technologies", "global", "precision"}


def _alternatives(db, c: Company, edges: list[dict], mitigations: list[dict]) -> list[dict]:
    """For each disclosed supplier: does the company disclose an alternative-source effort, and which other
    loaded registrants name counterparties in the same role? Candidates are leads, not verified substitutes."""
    # Only registrants in the same SIC major group: a can maker is not an alternative to a wafer foundry.
    others = db.execute(select(EntityLink.entity, EntityLink.entity_type, Company.ticker)
                        .join(Company, Company.id == EntityLink.company_id)
                        .where(EntityLink.graph == "supply_chain", EntityLink.company_id != c.id,
                               Company.synthetic == c.synthetic,
                               Company.sic.startswith((c.sic or "--")[:2]))).all()
    own = {e["entity"] for e in edges}
    out = []
    for e in edges:
        words = {w.lower() for w in re.findall(r"[A-Za-z]{5,}", e["entity"])} - GENERIC_NAME_WORDS
        related = [m for m in mitigations if words & {w.lower() for w in re.findall(r"[A-Za-z]{5,}", m["text"])}]
        candidates = sorted({(name, t) for name, role, t in others if role == e["relation"] and name not in own})
        out.append({"entity": e["entity"], "relation": e["relation"], "single_source": e["single_source"],
                    "country": e["country"], "disclosed_mitigation": related[:3],
                    "candidates": [{"entity": n, "named_by": t} for n, t in candidates[:8]],
                    "status": "mitigation disclosed" if related else
                              ("no alternative disclosed" if e["single_source"] else "not assessed")})
    return out


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    db, c = ctx.db, ctx.company
    out = []
    ten_ks = {f.accession: f for f in ctx.filings(("10-K", "10-K/A"))}
    if ctx.job_id:
        db.execute(delete(EntityLink).where(EntityLink.company_id == c.id, EntityLink.graph == "supply_chain"))
    for e in data["edges"][:25]:
        ev = excerpt_evidence(db, c, ten_ks[e["accession"]], e["section"], e["text"], "company_statement",
                              f"Supply-chain mention: {e['entity']}")
        eid = save_evidence(db, c, ev, ctx.job_id, "rules")
        db.add(EntityLink(company_id=c.id, graph="supply_chain", entity=e["entity"], entity_type=e["relation"],
                          relation=("sole-source " if e["single_source"] else "") + e["relation"], country=e["country"],
                          evidence_id=eid, verification_status="extracted_mention", job_id=ctx.job_id))
        out.append(FindingDraft(MODULE, f"{e['relation'].title()}: {e['entity']}" + (f" ({e['country']})" if e["country"] else ""),
                                clip(e["text"], 400), "watch" if e["single_source"] else "neutral", "company_statement",
                                "medium", [eid], "Extracted from the company's filing; relationship not independently confirmed."))
    for s in data["signals"]:
        ex = s["examples"][0]
        sev = "concern" if s["signal"] in ("single_source", "export_controls") else "watch"
        out.append(FindingDraft(MODULE, f"Supply-chain risk signal: {s['signal'].replace('_', ' ')} ({s['mentions']} passage(s))",
                                clip(ex["text"], 400), sev, "company_statement", "medium",
                                [excerpt_evidence(db, c, ten_ks[ex["accession"]], ex["section"], ex["text"])],
                                "Keyword-based; a disclosed risk is not a realised event."))
    if data["countries"]:
        top = data["countries"][:4]
        out.append(FindingDraft(MODULE, "Geographic concentration in supply-related disclosures: " +
                                ", ".join(f"{x['country']} ({x['mentions']})" for x in top),
                                "Counts of country mentions in sentences about suppliers or manufacturing.", "neutral",
                                "analytical_inference", "low",
                                [computed_evidence("Country mention counts", None, "sentence co-occurrence count", [])],
                                "Mention frequency is a weak proxy for dependency."))
    inv = data["inventory"]
    if len(inv) >= 2:
        a, b = inv[-2], inv[-1]
        ids = [save_evidence(db, c, e, ctx.job_id, "rules") for e in ctx.evs(
            [("inventory", d) for d in ctx.fiscal_ends[-2:]] + [("cost_of_revenue", d) for d in ctx.fiscal_ends[-2:]])]
        out.append(FindingDraft(MODULE, f"Days inventory outstanding {a['dio']:.0f} → {b['dio']:.0f} (FY{a['fy']}→FY{b['fy']})",
                                "Rising DIO can signal slowing demand or deliberate stock-building for supply security; "
                                "falling DIO can signal shortages.", "watch" if b["dio"] > a["dio"] * 1.2 else "neutral",
                                "analytical_inference", "medium",
                                [computed_evidence(f"DIO FY{b['fy']} = {b['dio']:.1f}", b["dio"], "inventory × 365 / cost of revenue", ids)]))
    for a in data.get("alternatives", []):
        if not a["single_source"]:
            continue
        edge = next(e for e in data["edges"] if e["entity"] == a["entity"])
        ev = [excerpt_evidence(db, c, ten_ks[edge["accession"]], edge["section"], edge["text"], "company_statement",
                               f"Sole-source disclosure: {a['entity']}")]
        if a["disclosed_mitigation"]:
            m = a["disclosed_mitigation"][0]
            ev.append(excerpt_evidence(db, c, ten_ks[m["accession"]], m["section"], m["text"], "company_statement",
                                       "Alternative-source disclosure"))
            out.append(FindingDraft(MODULE, f"Alternative sourcing for {a['entity']}: effort disclosed", clip(m["text"], 400),
                                    "watch", "company_statement", "medium", ev,
                                    "A disclosed qualification effort is a plan, not an available substitute."))
        else:
            out.append(FindingDraft(MODULE, f"No alternative source disclosed for sole-source {a['relation']} {a['entity']}",
                                    "The latest 10-Ks describe this supplier as a sole or single source and do not "
                                    "describe a second-source effort.", "concern", "analytical_inference", "medium", ev,
                                    "Absence of disclosure is not proof that no alternative exists."))
    for nc in data["not_connected"]:
        out.append(unavailable(MODULE, f"{nc['source']}", nc["reason"]))
    return out
