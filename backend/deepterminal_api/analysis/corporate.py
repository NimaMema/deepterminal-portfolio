"""Corporate legitimacy: registration, identity history, structure, filing regularity, insolvency signals."""

from __future__ import annotations

import re
from datetime import date

from ..services import filings as fs
from ..services.evidence import EvidenceDraft, FindingDraft, SourceDraft, excerpt_evidence, filing_source, unavailable
from ..services.gateway import DataUnavailable
from .base import Ctx, clip

MODULE = "corporate_legitimacy"

NOT_CONNECTED = [
    {"check": "State corporate registry records", "adapter": "state registries / OpenCorporates",
     "status": "not_configured", "reason": "No free, bulk, legally reusable registry API covers all states; not used."},
    {"check": "SEC enforcement / litigation releases", "adapter": "sec.gov litigation releases",
     "status": "unavailable", "reason": "SEC litigation releases have no search API; adapter not implemented."},
]


def sanctions_screen(names: list[str]) -> dict:
    """Exact match of normalised names against the OFAC SDN list (free, US Treasury)."""
    from ..services.free_sources import free_sources, normalise_name
    try:
        sdn, res = free_sources().ofac_sdn()
    except DataUnavailable as e:
        return {"status": e.status, "message": e.message, "hint": e.hint}
    index: dict[str, list[dict]] = {}
    for r in sdn:
        index.setdefault(normalise_name(r["name"]), []).append(r)
    matches = [{"screened": n, **m} for n in names for m in index.get(normalise_name(n), []) if normalise_name(n)]
    return {"status": "ok", "screened": len(names), "list_size": len(sdn), "matches": matches,
            "retrieved_at": res.retrieved_at.isoformat(), "url": res.url,
            "method": "Exact match after removing punctuation and legal suffixes; aliases (alt.csv) not screened."}


def website_from_10k(ctx: Ctx) -> str | None:
    """The company's own domain, as named most often in its latest 10-K (the SEC profile field is often empty)."""
    from collections import Counter
    for f in ctx.filings(("10-K",))[:1]:
        try:
            fs.fetch_filing_text(ctx.db, ctx.company, f)
        except DataUnavailable:
            return None
        full = fs.section(ctx.db, f, "full")
        if full:
            hosts = Counter(m.lower() for m in re.findall(r"\bwww\.[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|io|co)\b",
                                                         full.text, re.I) if "sec.gov" not in m.lower())
            if hosts:
                return hosts.most_common(1)[0][0]
    return None


def website_history(site: str | None) -> dict:
    """First and latest Internet Archive snapshots of the company website (free availability API)."""
    from ..services.free_sources import free_sources
    if not site:
        return {"status": "not_applicable", "message": "No website on the SEC profile."}
    site = re.sub(r"^https?://", "", site).strip("/")
    try:
        first, res = free_sources().wayback_snapshot(site, 1996)
    except DataUnavailable as e:
        return {"status": e.status, "message": e.message, "hint": e.hint}
    # Only the earliest snapshot is reported: the availability API's "closest to today" answer can be years
    # old (it returned 2020 for nvidia.com in 2026), so a "latest" date would mislead.
    return {"status": "ok", "site": site, "first": first, "latest": None, "retrieved_at": res.retrieved_at.isoformat()}




def compute(ctx: Ctx) -> dict:
    c = ctx.company
    ten_ks = ctx.filings(("10-K", "10-K/A", "10-KT"))
    years = sorted({f.filed.year for f in ten_ks if f.form.startswith("10-K")})
    gaps = [y for y in range(years[0], years[-1] + 1) if y not in years] if years else []
    try:
        subs = fs.subsidiaries(ctx.db, c)
    except DataUnavailable as e:
        subs = {"subsidiaries": [], "unavailable": e.to_dict()}
    ev8k = fs.events(ctx.db, c, ctx.as_of)
    auditor_changes = [e for e in ev8k if any(i["code"] == "4.01" for i in e["items"])]
    insolvency = [e for e in ev8k if any(i["code"] in ("1.03", "2.04", "3.01") for i in e["items"])]
    going_concern = []
    legal = None
    for f in ten_ks[:3]:
        try:
            fs.fetch_filing_text(ctx.db, c, f)
        except DataUnavailable:
            continue
        full = fs.section(ctx.db, f, "full")
        if full:
            for m in re.finditer(r"[^.]*substantial doubt[^.]*going concern[^.]*\.", full.text, re.I):
                going_concern.append({"accession": f.accession, "filing_id": f.id, "filed": f.filed.isoformat(),
                                      "text": m.group(0).strip()})
        if legal is None:
            sec = fs.section(ctx.db, f, "item_3")
            if sec:
                legal = {"accession": f.accession, "filing_id": f.id, "filed": f.filed.isoformat(),
                         "text": sec.text[:4000]}
    ownership = [{"form": f.form, "filed": f.filed.isoformat(), "accession": f.accession, "url": f.url}
                 for f in ctx.filings(("SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A", "SCHEDULE 13D", "SCHEDULE 13G"))][:30]
    return {
        "identity": {"name": c.name, "cik": c.cik, "ticker": c.ticker, "ein": c.ein, "entity_type": c.entity_type,
                     "state_of_incorporation": c.state_of_incorporation, "sic": c.sic,
                     "sic_description": c.sic_description, "category": c.category, "exchanges": c.exchanges,
                     "fiscal_year_end": c.fiscal_year_end, "website": c.website,
                     "profile_retrieved_at": c.profile_retrieved_at.isoformat() if c.profile_retrieved_at else None},
        "former_names": c.former_names, "addresses": c.addresses,
        "filing_regularity": {"annual_report_years": years, "missing_years": gaps,
                              "first_10k": years[0] if years else None},
        "subsidiaries": subs, "auditor_changes": auditor_changes, "insolvency_events": insolvency,
        "going_concern": going_concern, "legal_proceedings": legal, "beneficial_ownership_filings": ownership,
        "sanctions": ({"status": "not_applicable", "message": "Demo companies are fictional."} if c.synthetic
                      else sanctions_screen([c.name] + [x["name"] for x in (subs.get("subsidiaries") or [])][:50])),
        "website_history": ({"status": "not_applicable", "message": "Demo companies are fictional."} if c.synthetic
                            else website_history(c.website or website_from_10k(ctx))),
        "not_connected": NOT_CONNECTED,
        "parent_company": {"status": "not_determined",
                           "reason": "Parent relationships are not available as structured SEC data; check Exhibit 21 "
                                     "of a potential parent or Schedule 13D filings."},
    }


def _sub_source(ctx: Ctx) -> SourceDraft:
    c = ctx.company
    return SourceDraft(f"SEC-SUBMISSIONS:{c.cik}", "sec_xbrl", f"EDGAR submissions record for CIK {c.cik:010d}",
                       "SYNTHETIC demo dataset in SEC format" if c.synthetic else "U.S. SEC — data.sec.gov",
                       f"https://data.sec.gov/submissions/CIK{c.cik:010d}.json", None, c.profile_retrieved_at,
                       synthetic=c.synthetic)


def findings(ctx: Ctx, data: dict) -> list[FindingDraft]:
    c, db = ctx.company, ctx.db
    out: list[FindingDraft] = []
    idn = data["identity"]
    reg = EvidenceDraft("registry_record", f"SEC registrant {idn['name']} (CIK {idn['cik']}), {idn['entity_type']}, "
                                           f"incorporated in {idn['state_of_incorporation']}",
                        "historical_fact", _sub_source(ctx), locator="submissions: name, entityType, stateOfIncorporation",
                        verification_status="verified",
                        limitations="SEC registration confirms the entity files with the SEC; it is not an audit of "
                                    "operations or a state-registry check.")
    fr = data["filing_regularity"]
    since = c.first_filing_date.year if c.first_filing_date else fr["first_10k"]
    out.append(FindingDraft(MODULE, f"SEC filer since {since} (earliest EDGAR filing); "
                                    f"{len(fr['annual_report_years'])} annual reports in the recent filing index",
                            ("Annual reports missing for: " + ", ".join(map(str, fr["missing_years"])))
                            if fr["missing_years"] else "No gaps in annual report filings detected.",
                            "watch" if fr["missing_years"] else "positive", "historical_fact", "high", [reg]))
    if data["former_names"]:
        ev = EvidenceDraft("registry_record", "Former names: " + "; ".join(
            f"{n['name']} ({n.get('from', '')[:10]}–{n.get('to', '')[:10]})" for n in data["former_names"]),
            "historical_fact", _sub_source(ctx), locator="submissions: formerNames", verification_status="verified")
        out.append(FindingDraft(MODULE, f"{len(data['former_names'])} former name(s) on record",
                                "Name changes are common (rebrands, mergers) but should be reconciled with the "
                                "company's stated history.", "neutral", "historical_fact", "high", [ev]))
    subs = data["subsidiaries"]
    if subs.get("subsidiaries"):
        juris = sorted({s["jurisdiction"] for s in subs["subsidiaries"]})
        f = next((x for x in ctx.filings(("10-K",)) if x.accession == subs["accession"]), None)
        ev = EvidenceDraft("exhibit", f"Exhibit 21 lists {len(subs['subsidiaries'])} subsidiaries in "
                                      f"{len(juris)} jurisdictions", "company_statement",
                           filing_source(c, subs["accession"], "10-K", date.fromisoformat(subs["filed"]), subs["url"],
                                         None), locator=f"{subs['accession']}/{subs['document']}",
                           verification_status="verified", data={"subsidiaries": subs["subsidiaries"]})
        out.append(FindingDraft(MODULE, f"Corporate structure: {len(subs['subsidiaries'])} significant subsidiaries "
                                        f"({', '.join(juris[:6])})", "From Exhibit 21 of the latest 10-K.",
                                "neutral", "company_statement", "high", [ev]))
    for e in data["auditor_changes"]:
        out.append(FindingDraft(MODULE, f"Auditor change disclosed (8-K Item 4.01, {e['filed']})",
                                "Read the 8-K for whether disagreements with the former auditor were reported.",
                                "watch", "historical_fact", "high",
                                [EvidenceDraft("filing_event", f"8-K Item 4.01 filed {e['filed']}", "historical_fact",
                                               filing_source(c, e["accession"], "8-K", date.fromisoformat(e["filed"]),
                                                             e["url"], None), verification_status="verified")]))
    for g in data["going_concern"][:2]:
        f = next(x for x in ctx.filings(("10-K", "10-K/A")) if x.accession == g["accession"])
        out.append(FindingDraft(MODULE, "Going-concern language in annual report",
                                clip(g["text"], 400), "concern", "company_statement", "high",
                                [excerpt_evidence(db, c, f, "full", g["text"])]))
    if data["legal_proceedings"]:
        lp = data["legal_proceedings"]
        f = next(x for x in ctx.filings(("10-K", "10-K/A")) if x.accession == lp["accession"])
        body = lp["text"].split("\n", 1)[-1].strip()[:600]
        material = not re.search(r"not (currently )?(a )?party to any material", body, re.I)
        out.append(FindingDraft(MODULE, "Legal proceedings disclosed" if material else "No material legal proceedings disclosed",
                                body, "watch" if material else "neutral", "company_statement", "medium",
                                [excerpt_evidence(db, c, f, "item_3", body)],
                                "Company-disclosed litigation only; court dockets are not searched."))
    sx = data.get("sanctions", {})
    if sx.get("status") == "ok":
        src = SourceDraft("OFAC:SDN", "government_record", "OFAC Specially Designated Nationals list (SDN)",
                          "U.S. Department of the Treasury — OFAC", sx["url"], None, None, licence="US government public data")
        ev = EvidenceDraft("registry_record", f"SDN screening of {sx['screened']} name(s) against {sx['list_size']} entries",
                           "historical_fact", src, verification_status="verified", limitations=sx["method"],
                           data={"matches": sx["matches"]})
        if sx["matches"]:
            out.append(FindingDraft(MODULE, f"Possible sanctions-list name match: {sx['matches'][0]['name']} "
                                            f"({sx['matches'][0]['program']})",
                                    "An exact normalised name match on the OFAC SDN list. A name match is not an "
                                    "identification; confirm identifiers (address, IDs) before drawing conclusions.",
                                    "concern", "historical_fact", "medium", [ev], sx["method"]))
        else:
            out.append(FindingDraft(MODULE, f"No exact OFAC SDN name match ({sx['screened']} names screened)",
                                    "The company and its listed subsidiaries do not appear on the SDN list by exact "
                                    "normalised name.", "positive", "historical_fact", "medium", [ev],
                                    sx["method"] + " Absence of a match is not clearance."))
    elif sx:
        out.append(unavailable(MODULE, "Sanctions screening: not checked", sx.get("message", ""), sx.get("hint", "")))
    wh = data.get("website_history", {})
    if wh.get("status") == "ok" and wh.get("first"):
        first = wh["first"]
        src = SourceDraft(f"WAYBACK:{wh['site']}", "web_archive", f"Internet Archive snapshots of {wh['site']}",
                          "Internet Archive (archive.org)", first.get("url"), None, None, licence="archive.org terms")
        ev = EvidenceDraft("web_archive", f"Earliest snapshot {first.get('timestamp', '')[:8]}", "historical_fact", src,
                           locator=first.get("url"), verification_status="verified",
                           limitations="Snapshot availability only; archived content is not analysed.")
        out.append(FindingDraft(MODULE, f"Website {wh['site']} archived since {first.get('timestamp', '')[:4]}",
                                "A long, continuous web presence is weak supporting evidence of an operating business.",
                                "neutral", "historical_fact", "medium", [ev]))
    elif wh and wh.get("status") not in ("ok", "not_applicable"):
        out.append(unavailable(MODULE, "Historical websites: not checked", wh.get("message", ""), wh.get("hint", "")))
    for nc in data["not_connected"]:
        out.append(unavailable(MODULE, f"{nc['check']}: not checked", nc["reason"],
                               f"Adapter: {nc['adapter']}."))
    return out
