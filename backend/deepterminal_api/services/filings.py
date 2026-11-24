"""SEC filing documents: retrieval, text extraction, sectioning, search, comparisons.

All filing content is UNTRUSTED input: it is parsed with defusedxml /
BeautifulSoup, stored as plain text, never executed, and passed to language
models only inside delimited data blocks (see research/guard.py).
"""

from __future__ import annotations

import difflib
import hashlib
import math
import re
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from typing import Any

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)   # EDGAR serves XHTML
from defusedxml import ElementTree as SafeET
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import Company, Filing, FilingSection
from .gateway import DataUnavailable, get_gateway

EIGHT_K_ITEMS = {
    "1.01": "Entry into a material definitive agreement", "1.02": "Termination of a material definitive agreement",
    "1.03": "Bankruptcy or receivership", "1.05": "Material cybersecurity incident",
    "2.01": "Completion of acquisition or disposition of assets", "2.02": "Results of operations and financial condition",
    "2.03": "Creation of a direct financial obligation", "2.04": "Triggering events accelerating an obligation",
    "2.05": "Costs associated with exit or disposal activities", "2.06": "Material impairments",
    "3.01": "Notice of delisting or failure to satisfy listing rule", "3.02": "Unregistered sales of equity securities",
    "3.03": "Material modification to rights of security holders",
    "4.01": "Changes in registrant's certifying accountant",
    "4.02": "Non-reliance on previously issued financial statements (restatement)",
    "5.01": "Changes in control of registrant", "5.02": "Departure/appointment of directors or officers; compensation",
    "5.03": "Amendments to articles or bylaws; change in fiscal year", "5.07": "Submission of matters to a vote of security holders",
    "7.01": "Regulation FD disclosure", "8.01": "Other events", "9.01": "Financial statements and exhibits",
}
SIGNIFICANT_8K = {"1.03": "concern", "1.05": "concern", "2.04": "concern", "2.06": "watch", "3.01": "concern",
                  "4.01": "watch", "4.02": "concern", "5.01": "watch", "5.02": "watch", "2.05": "watch"}
TEN_K_KEYS = {"1": "Business", "1a": "Risk Factors", "1b": "Unresolved Staff Comments", "1c": "Cybersecurity",
              "2": "Properties", "3": "Legal Proceedings", "4": "Mine Safety Disclosures", "5": "Market for Equity",
              "7": "Management's Discussion and Analysis", "7a": "Market Risk", "8": "Financial Statements",
              "9": "Changes in and Disagreements with Accountants", "9a": "Controls and Procedures"}
KEEP_SECTIONS = {"1", "1a", "1c", "3", "7", "7a", "9", "9a"}


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "head"]):
        t.decompose()
    for br in soup.find_all(["br"]):
        br.replace_with("\n")
    raw = soup.get_text("\n")
    lines = [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in raw.splitlines()]
    lines = [ln for ln in lines if ln]
    toc = re.compile(r"^table of contents$", re.I)
    out = []
    for i, ln in enumerate(lines):
        # Page furniture: a running "Table of Contents" link and the page number printed beside it.
        if toc.match(ln) or (re.fullmatch(r"\d{1,3}", ln) and (
                (i + 1 < len(lines) and toc.match(lines[i + 1])) or (i > 0 and toc.match(lines[i - 1])))):
            continue
        out.append(ln)
    return "\n".join(out)


HEADING = re.compile(r"^\s*item\s*(\d{1,2}[a-c]?)\s*[\.\:\-—–]?\s*(.{0,160})$", re.I)


def split_items(text_: str) -> dict[str, tuple[str, str]]:
    """10-K item key → (title, text). Picks, per item, the longest occurrence (skips the TOC)."""
    lines = text_.split("\n")
    pos, heads = 0, []
    for ln in lines:
        m = HEADING.match(ln)
        if m and len(ln) < 220:
            heads.append((pos, m.group(1).lower(), ln.strip()))
        pos += len(ln) + 1
    best: dict[str, tuple[str, str]] = {}
    for i, (p, key, title) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text_)
        body = text_[p:end].strip()
        if key not in best or len(body) > len(best[key][1]):
            best[key] = (title, body)
    return best


def _store_section(db: Session, filing: Filing, key: str, title: str, body: str) -> None:
    sec = db.scalar(select(FilingSection).where(FilingSection.filing_id == filing.id, FilingSection.key == key))
    h = hashlib.sha256(body.encode()).hexdigest()
    if sec is None:
        db.add(FilingSection(filing_id=filing.id, key=key, title=title[:250], text=body, sha256=h))
    elif sec.sha256 != h:
        sec.text, sec.sha256, sec.title = body, h, title[:250]


def fetch_filing_text(db: Session, company: Company, filing: Filing, force: bool = False) -> dict[str, Any]:
    if filing.text_status == "fetched" and not force:
        return {"status": "cached"}
    gw = get_gateway()
    doc = filing.primary_document
    if not doc:
        raise DataUnavailable("not_found", "Filing has no primary document listed.")
    try:
        html, meta = gw.document(company.cik, filing.accession, doc.split("/")[-1] if filing.form == "4" else doc)
    except DataUnavailable:
        filing.text_status = "failed"
        db.commit()
        raise
    txt = form4_text(html) if filing.form in ("3", "4", "5") else html_to_text(html)
    _store_section(db, filing, "full", f"{filing.form} filed {filing.filed}", txt)
    if filing.form.startswith("10-K") or filing.form.startswith("10-Q"):
        for key, (title, body) in split_items(txt).items():
            if key in KEEP_SECTIONS and len(body) > 40:
                _store_section(db, filing, f"item_{key}", title, body)
    filing.text_status = "fetched"
    filing.text_retrieved_at = meta.retrieved_at
    db.commit()
    return {"status": "fetched", "chars": len(txt)}


def ensure_text(db: Session, company: Company, forms: tuple[str, ...], limit: int, since: date | None = None) -> list[Filing]:
    q = select(Filing).where(Filing.company_id == company.id, Filing.form.in_(forms)).order_by(Filing.filed.desc())
    if since:
        q = q.where(Filing.filed >= since)
    fs = db.scalars(q.limit(limit)).all()
    for f in fs:
        try:
            fetch_filing_text(db, company, f)
        except DataUnavailable:
            pass
    return fs


def section(db: Session, filing: Filing, key: str) -> FilingSection | None:
    return db.scalar(select(FilingSection).where(FilingSection.filing_id == filing.id, FilingSection.key == key))


def search(db: Session, company_id: int | None, q: str, forms: list[str] | None = None, limit: int = 25) -> list[dict]:
    sql = """
      SELECT s.id AS section_id, s.key, s.title, f.accession, f.form, f.filed, f.company_id, f.url, f.synthetic,
             ts_rank(s.tsv, websearch_to_tsquery('english', :q)) AS rank,
             ts_headline('english', s.text, websearch_to_tsquery('english', :q),
                         'MaxWords=40, MinWords=15, MaxFragments=2, StartSel=<<, StopSel=>>') AS snippet
      FROM filing_sections s JOIN filings f ON f.id = s.filing_id
      WHERE s.tsv @@ websearch_to_tsquery('english', :q) AND s.key <> 'full'
    """
    params: dict[str, Any] = {"q": q, "limit": limit}
    if company_id:
        sql += " AND f.company_id = :cid"
        params["cid"] = company_id
    if forms:
        sql += " AND f.form = ANY(:forms)"
        params["forms"] = forms
    sql += " ORDER BY rank DESC, f.filed DESC LIMIT :limit"
    rows = db.execute(text(sql), params).mappings().all()
    if not rows:   # fall back to full documents when no item sections match (8-K, proxies)
        sql2 = sql.replace("AND s.key <> 'full'", "AND s.key = 'full'")
        rows = db.execute(text(sql2), params).mappings().all()
    return [dict(r, filed=r["filed"].isoformat()) for r in rows]


def best_fragment(snippet: str, limit: int = 320) -> str:
    """From a ts_headline snippet, the line with the most highlighted terms, markers removed."""
    parts = [p for p in re.split(r"\n| \.\.\. ", snippet) if p.strip()]
    if not parts:
        return ""
    best = max(parts, key=lambda p: (p.count("<<"), len(p)))
    return best.replace("<<", "").replace(">>", "").strip()[:limit]


def passages(db: Session, company_id: int, keywords: list[str], k: int = 4, sections: int = 12) -> list[dict]:
    """Best-matching sentences inside the best-matching sections.

    Section-level full-text rank alone is too coarse for real 10-Ks (Item 1A runs to tens of thousands
    of words), so sentences are re-scored: each keyword counts once, weighted by how rare it is among the
    candidate sentences, with a bonus for adjacent keyword pairs from the question ("export controls")."""
    if not keywords:
        return []
    hits = search(db, company_id, " or ".join(keywords), None, limit=sections)
    stems = [w[:6] for w in keywords]
    cands = []
    for h in hits:
        sec = db.get(FilingSection, h["section_id"])
        for sent in re.split(r"(?<=[.;])\s+", " ".join(sec.text.split())):
            if 40 <= len(sent) <= 700:
                low = sent.lower()
                present = {st for st in stems if st in low}
                if present:
                    cands.append((sent, low, present, h))
    if not cands:
        return []
    df = {st: sum(1 for c in cands if st in c[2]) for st in stems}
    pairs = [f"{a} {b}" for a, b in zip(keywords, keywords[1:])]
    def score(c):
        sent, low, present, h = c
        idf = sum(math.log(1 + len(cands) / df[st]) for st in present)
        return idf + 2.0 * sum(1 for p in pairs if p[:-2] in low), h["filed"]
    out, seen = [], set()
    for sent, low, present, h in sorted(cands, key=score, reverse=True):
        norm = re.sub(r"\W+", " ", low)
        if norm in seen:
            continue
        seen.add(norm)
        out.append({"text": sent, "key": h["key"], "title": h["title"], "accession": h["accession"],
                    "form": h["form"], "filed": h["filed"], "matched": sorted(present)})
        if len(out) >= k:
            break
    return out


# ───────────────────────────── risk factors ─────────────────────────────

def risk_paragraphs(body: str) -> list[str]:
    paras = [p.strip() for p in body.split("\n")[1:] if len(p.strip()) > 30]
    merged: list[str] = []
    for p in paras:   # merge "Heading." + body lines produced by inline bold headings
        if merged and len(merged[-1]) < 120 and merged[-1].endswith("."):
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z]{4,}", s.lower()))


def diff_paragraphs(old: list[str], new: list[str]) -> dict[str, list[dict]]:
    out = {"added": [], "removed": [], "modified": [], "unchanged": []}
    used: set[int] = set()
    old_words = [_words(o) for o in old]
    for b in new:
        wb = _words(b)
        cands = sorted(range(len(old)), key=lambda i: -len(wb & old_words[i]) / (len(wb | old_words[i]) or 1))[:5]
        best, best_r = None, 0.0
        for i in cands:
            if i in used:
                continue
            r = difflib.SequenceMatcher(None, old[i], b, autojunk=False).ratio()
            if r > best_r:
                best, best_r = i, r
        if best is not None and best_r >= 0.97:
            used.add(best)
            out["unchanged"].append({"text": b})
        elif best is not None and best_r >= 0.6:
            used.add(best)
            out["modified"].append({"text": b, "previous": old[best], "similarity": round(best_r, 3)})
        else:
            out["added"].append({"text": b})
    out["removed"] = [{"text": old[i]} for i in range(len(old)) if i not in used]
    return out


def ten_k_filings(db: Session, company: Company, as_of: date | None = None) -> list[Filing]:
    q = select(Filing).where(Filing.company_id == company.id, Filing.form.in_(("10-K", "10-K/A"))).order_by(Filing.filed.desc())
    if as_of:
        q = q.where(Filing.filed <= as_of)
    return list(db.scalars(q))


def compare_sections(db: Session, company: Company, a: Filing, b: Filing, key: str = "item_1a") -> dict[str, Any]:
    for f in (a, b):
        fetch_filing_text(db, company, f)
    sa, sb = section(db, a, key), section(db, b, key)
    if not sa or not sb:
        raise DataUnavailable("not_found", f"Section {key} could not be located in one of the filings.",
                              "Section detection relies on 'Item 1A.'-style headings.")
    d = diff_paragraphs(risk_paragraphs(sa.text), risk_paragraphs(sb.text))
    return {"key": key, "from": {"accession": a.accession, "filed": a.filed.isoformat(), "url": a.url},
            "to": {"accession": b.accession, "filed": b.filed.isoformat(), "url": b.url},
            "counts": {k: len(v) for k, v in d.items()}, "diff": d, "synthetic": company.synthetic}


# ───────────────────────────── 8-K, Form 4, proxies, Exhibit 21 ─────────────────────────────

def events(db: Session, company: Company, as_of: date | None = None) -> list[dict]:
    q = select(Filing).where(Filing.company_id == company.id, Filing.form.in_(("8-K", "8-K/A"))).order_by(Filing.filed.desc())
    if as_of:
        q = q.where(Filing.filed <= as_of)
    out = []
    for f in db.scalars(q):
        items = [{"code": i, "description": EIGHT_K_ITEMS.get(i, "Other item"),
                  "significance": SIGNIFICANT_8K.get(i, "info")} for i in f.items]
        out.append({"accession": f.accession, "filed": f.filed.isoformat(), "form": f.form, "url": f.url,
                    "items": items, "synthetic": f.synthetic})
    return out


def form4_text(xml: str) -> str:
    tx = parse_form4(xml)
    lines = [f"Form 4 — {tx['owner']} ({tx['role']}) — issuer {tx['issuer']}"]
    for t in tx["transactions"]:
        lines.append(f"{t['date']}: code {t['code']} {t['shares']:,.0f} shares at {t['price']} ({t['acquired_disposed']})")
    return "\n".join(lines)


def _xml_text(el, path: str) -> str:
    node = el.find(path)
    return (node.text or "").strip() if node is not None and node.text else ""


def parse_form4(xml: str) -> dict[str, Any]:
    body = xml[xml.find("<ownershipDocument"):] if "<ownershipDocument" in xml else xml
    root = SafeET.fromstring(body)
    owner = _xml_text(root, "reportingOwner/reportingOwnerId/rptOwnerName")
    rel = root.find("reportingOwner/reportingOwnerRelationship")
    role = _xml_text(rel, "officerTitle") if rel is not None else ""
    if rel is not None and _xml_text(rel, "isDirector") in ("1", "true") and "Director" not in role:
        role = (role + ", Director").strip(", ")
    txs = []
    for t in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        def v(p):
            return _xml_text(t, p)
        try:
            shares = float(v("transactionAmounts/transactionShares/value") or 0)
        except ValueError:
            shares = 0.0
        try:
            price = float(v("transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            price = 0.0
        txs.append({"date": v("transactionDate/value"), "code": v("transactionCoding/transactionCode"),
                    "shares": shares, "price": price,
                    "acquired_disposed": v("transactionAmounts/transactionAcquiredDisposedCode/value"),
                    "owned_after": v("postTransactionAmounts/sharesOwnedFollowingTransaction/value")})
    return {"owner": owner, "role": role, "issuer": _xml_text(root, "issuer/issuerName"), "transactions": txs}


FORM4_CODES = {"P": "Open-market purchase", "S": "Open-market sale", "A": "Grant/award", "M": "Option exercise",
               "F": "Tax withholding", "G": "Gift", "D": "Disposition to issuer", "C": "Conversion"}


def insider_transactions(db: Session, company: Company, limit: int = 40, as_of: date | None = None) -> dict[str, Any]:
    gw = get_gateway()
    q = select(Filing).where(Filing.company_id == company.id, Filing.form == "4").order_by(Filing.filed.desc())
    if as_of:
        q = q.where(Filing.filed <= as_of)
    out, errors = [], []
    for f in db.scalars(q.limit(limit)):
        try:
            names = [i["name"] for i in gw.filing_index(company.cik, f.accession) if i["name"].lower().endswith(".xml")]
            if not names:
                continue
            xml, meta = gw.document(company.cik, f.accession, names[0])
            p = parse_form4(xml)
        except DataUnavailable as e:
            errors.append(e.to_dict())
            continue
        except Exception as e:  # malformed XML from source
            errors.append({"status": "parse_error", "message": str(e)[:200], "url": f.url})
            continue
        for t in p["transactions"]:
            out.append({**t, "owner": p["owner"], "role": p["role"], "accession": f.accession,
                        "filed": f.filed.isoformat(), "url": f.url, "code_description": FORM4_CODES.get(t["code"], t["code"]),
                        "value": t["shares"] * t["price"], "synthetic": f.synthetic})
    buys = sum(t["value"] for t in out if t["code"] == "P")
    sells = sum(t["value"] for t in out if t["code"] == "S")
    return {"transactions": out, "open_market_buy_value": buys, "open_market_sell_value": sells,
            "errors": errors[:5], "note": "Only open-market purchases (P) and sales (S) are informative about insider "
                                          "views; grants, exercises and tax withholding are mostly mechanical."}


def _num(s: str) -> float | None:
    s = re.sub(r"[,$\s]", "", s or "")
    if s in ("", "-", "—"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        v = float(s.strip("()"))
    except ValueError:
        return None
    return -v if neg else v


TITLE_ONLY = re.compile(r"^(?:(?:former|executive|senior|vice|chief|president|officer|chair\w*|ceo|cfo|coo|cto|evp|svp|"
                        r"general|counsel|secretary|treasurer|director|and|&|of|the|operations|financial|technology|"
                        r"worldwide|field|global|sales|marketing|legal|human|resources|people|interim|co-founder|founder)"
                        r"[\s,.&/-]*)+$", re.I)
YEAR_CELL = re.compile(r"^(?:fiscal\s+)?(20\d\d)$", re.I)


def _cells(tr) -> list[str]:
    """Row cells with spacer and lone currency cells removed (proxy tables put "$" in its own cell)."""
    out = []
    for c in tr.find_all(["td", "th"]):
        t = " ".join(c.get_text(" ", strip=True).split())
        t = re.sub(r"\s*\((?:\d{1,2}|[a-z])\)|\*+$", "", t).strip()     # footnote markers: (1), (a), *
        if t and t not in ("$", "(", ")", "%"):
            out.append(t)
    return out


def compensation_table(html: str) -> list[dict]:
    """Rows of the Summary Compensation Table: name, year, salary and total (the row's last figure).

    Identified by its columns (salary, stock awards, total) rather than by position. Each executive's name
    appears only on their first yearly row, so it is carried forward. Rows that fail basic checks (a year,
    total ≥ salary, a plausible amount) are dropped rather than guessed."""
    soup = BeautifulSoup(html, "lxml")
    best: list[dict] = []
    for table in soup.find_all("table"):
        head = " ".join(table.get_text(" ", strip=True).split())[:1500].lower()   # spacer cells come first
        if not ("salary" in head and "total" in head and ("stock" in head or "award" in head)):
            continue
        rows, name, position = [], None, None
        for tr in table.find_all("tr"):
            cells = _cells(tr)
            yi = next((i for i, c in enumerate(cells) if YEAR_CELL.match(c)), None)
            if yi is None:
                continue
            if yi > 0:
                label = " ".join(cells[:yi])[:160]
                # Some tables put the title on the executive's second yearly row: keep it as their position.
                if name and TITLE_ONLY.match(label):
                    position = label
                else:
                    name, position = label, None
            nums = [v for v in (_num(c) for c in cells[yi + 1:]) if v is not None]
            if not name or len(nums) < 2:
                continue
            salary, total = nums[0], nums[-1]
            if total < salary or total < 10_000 or total > 5e9:
                continue
            rows.append({"name": name, "year": int(YEAR_CELL.match(cells[yi]).group(1)), "salary": salary,
                         "total": total, "position": position})
        if len(rows) > len(best):
            best = rows
    return best


def exhibit_documents(gw, cik: int, accession: str, exhibit_type: str) -> list[str]:
    """Documents of an exhibit type (e.g. EX-21 matches EX-21.1), read from the filing's index page, which
    states each document's type. File names are chosen by filers (NVIDIA: subsidiariesofregistrantfy.htm)."""
    try:
        html, _ = gw.document(cik, accession, f"{accession}-index.html")
    except DataUnavailable:
        return []
    out = []
    for tr in BeautifulSoup(html, "lxml").select("table.tableFile tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
        if len(cells) >= 4 and re.match(re.escape(exhibit_type) + r"(\.\d+)?$", cells[3], re.I):
            out.append(cells[2].split()[0])
    return out


def subsidiaries(db: Session, company: Company) -> dict[str, Any]:
    gw = get_gateway()
    for f in ten_k_filings(db, company)[:2]:
        try:
            items = gw.filing_index(company.cik, f.accession)
        except DataUnavailable as e:
            return {"subsidiaries": [], "unavailable": e.to_dict()}
        ex = exhibit_documents(gw, company.cik, f.accession, "EX-21") or \
            [i["name"] for i in items if re.search(r"ex(hibit)?[-_]?21|subsidiar", i["name"], re.I)]
        if not ex:
            continue
        html, meta = gw.document(company.cik, f.accession, ex[0])
        soup = BeautifulSoup(html, "lxml")
        subs = []
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            cells = [c for c in cells if c]
            header = re.search(r"^(name|subsidiar)|jurisdiction|incorporat(ed|ion) in$|organization$", " | ".join(cells), re.I) \
                and not re.search(r"\b(inc|ltd|llc|corp|gmbh|b\.v|pte|s\.a)\b", cells[0], re.I)
            if len(cells) >= 2 and not header:
                subs.append({"name": cells[0], "jurisdiction": cells[-1]})
        if not subs:   # plain-text exhibit
            for ln in html_to_text(html).split("\n"):
                if "(" in ln and ln.endswith(")") and len(ln) < 200:
                    n, _, j = ln.rpartition("(")
                    subs.append({"name": n.strip(), "jurisdiction": j.rstrip(")")})
        return {"subsidiaries": subs, "accession": f.accession, "document": ex[0], "filed": f.filed.isoformat(),
                "url": f.url, "retrieved_at": meta.retrieved_at.isoformat(), "synthetic": f.synthetic}
    return {"subsidiaries": [], "unavailable": {"status": "not_found",
                                                 "message": "No Exhibit 21 found in the two most recent 10-K filings."}}


# ───────────────────────────── term trends ─────────────────────────────

def term_trend(db: Session, company: Company, terms: dict[str, re.Pattern], form: str = "10-K") -> list[dict]:
    """Mentions per filing of narrative terms (e.g. 'artificial intelligence') — a hype/narrative proxy."""
    out = []
    for f in reversed(ten_k_filings(db, company)[:8]):
        try:
            fetch_filing_text(db, company, f)
        except DataUnavailable:
            continue
        full = section(db, f, "full")
        if not full:
            continue
        words = max(len(full.text.split()), 1)
        counts = {label: len(rx.findall(full.text)) for label, rx in terms.items()}
        out.append({"filed": f.filed.isoformat(), "fy": f.report_date.year if f.report_date else f.filed.year - 1,
                    "accession": f.accession, "words": words, "counts": counts,
                    "per_10k_words": {t: n / words * 10000 for t, n in counts.items()}})
    return out


def verify_excerpt(db: Session, filing_id: int, key: str, excerpt: str) -> bool:
    """Mechanical citation check: the quoted text must exist in the stored section."""
    sec = db.scalar(select(FilingSection).where(FilingSection.filing_id == filing_id, FilingSection.key == key))
    norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    return bool(sec) and norm(excerpt) in norm(sec.text)
