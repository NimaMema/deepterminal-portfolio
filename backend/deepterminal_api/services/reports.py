"""Research report generation (HTML) and PDF export (headless Chromium).

The report contains only stored findings, deterministic valuation output and their
evidence. Sections with no findings say so explicitly. No buy/sell recommendation.
"""

from __future__ import annotations

import glob
import os
from datetime import datetime, timezone
from typing import Any

from jinja2 import Environment, select_autoescape
from sqlalchemy import select

from ..config import get_settings
from ..db import session_scope
from ..models import Company, Evidence, Finding, Report, ResearchJob, ValuationRun
from .evidence import evidence_dict, finding_dict

SECTIONS = [
    ("executive_summary", "Executive summary", ["synthesis"]),
    ("business_quality", "Business quality", ["product_research", "competitors"]),
    ("financial_strength", "Financial strength", ["forensic_accounting"]),
    ("corporate_legitimacy", "Corporate legitimacy", ["corporate_legitimacy"]),
    ("management", "Management", ["management_governance"]),
    ("accounting_quality", "Accounting quality", ["forensic_accounting", "sec_analysis"]),
    ("products", "Products", ["product_research"]),
    ("customers", "Customers", ["customer_demand"]),
    ("competition", "Competition", ["competitors"]),
    ("supply_chain", "Supply chain", ["supply_chain"]),
    ("market_position", "Market position", ["competitors", "market_sentiment"]),
    ("growth_sustainability", "Growth sustainability", ["customer_demand", "historical_analogues"]),
    ("historical_filings", "Historical filings", ["sec_analysis"]),
    ("market_expectations", "Market expectations", ["market_expectations"]),
    ("valuation_models", "Valuation models", ["financial_valuation"]),
    ("scenarios", "Bear / base / bull scenarios", []),
    ("major_risks", "Major risks", []),
    ("catalysts", "Potential catalysts", []),
    ("counterarguments", "Counterarguments", ["thesis_challenger"]),
    ("limitations", "Evidence limitations", []),
    ("bibliography", "Source bibliography", []),
]

TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{{ title }}</title>
<style>
@page { size: A4; margin: 18mm 16mm 20mm; }
:root { --ink:#0f172a; --muted:#475569; --line:#e2e8f0; --accent:#0e7490; --warn:#b45309; --bad:#b91c1c; --good:#15803d; }
* { box-sizing: border-box; }
body { font-family: "Inter", "Helvetica Neue", Arial, sans-serif; color: var(--ink); font-size: 10.5pt; line-height: 1.5; margin: 0; }
.cover { padding: 28mm 0 10mm; border-bottom: 3px solid var(--ink); margin-bottom: 8mm; }
.brand { letter-spacing: .32em; font-weight: 700; font-size: 9pt; color: var(--accent); }
h1 { font-size: 24pt; margin: 6mm 0 2mm; } h2 { font-size: 13.5pt; margin: 8mm 0 2mm; padding-bottom: 1mm; border-bottom: 1px solid var(--line); page-break-after: avoid; }
.meta { color: var(--muted); font-size: 9pt; }
.banner { background:#fff7ed; border:1px solid #fdba74; color:#9a3412; padding:3mm 4mm; border-radius:2mm; margin:4mm 0; font-size:9.5pt; }
.f { margin: 2.5mm 0; padding-left: 3mm; border-left: 3px solid var(--line); page-break-inside: avoid; }
.f.concern { border-color: var(--bad); } .f.watch { border-color: var(--warn); } .f.positive { border-color: var(--good); } .f.unavailable { border-color:#94a3b8; color: var(--muted); }
.f .t { font-weight: 600; } .tag { font-size: 7.5pt; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-left: 2mm; }
.cite { color: var(--accent); font-size: 8pt; } .lim { color: var(--muted); font-size: 8.5pt; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 2mm 0; font-variant-numeric: tabular-nums; }
th, td { border-bottom: 1px solid var(--line); padding: 1.2mm 2mm; text-align: right; } th:first-child, td:first-child { text-align: left; }
th { color: var(--muted); font-weight: 600; }
.empty { color: var(--muted); font-style: italic; }
.bib li { font-size: 8.5pt; margin-bottom: 1mm; word-break: break-word; }
.disclaimer { margin-top: 8mm; font-size: 8.5pt; color: var(--muted); border-top: 1px solid var(--line); padding-top: 3mm; }
</style></head><body>
<div class="cover"><div class="brand">DEEPTERMINAL · RESEARCH REPORT</div>
<h1>{{ company.name }}{% if company.ticker %} ({{ company.ticker }}){% endif %}</h1>
<div class="meta">CIK {{ "%010d"|format(company.cik) }} · {{ company.sic_description or "" }} · generated {{ generated }} · investigation {{ job_id or "none" }}</div>
{% if company.synthetic %}<div class="banner"><b>SYNTHETIC DEMO DATA.</b> This company and every figure in this report are fictional, generated for demonstration in SEC format. Not real SEC data.</div>{% endif %}
<div class="banner" style="background:#f0f9ff;border-color:#7dd3fc;color:#075985">Analysis, not investment advice. Business quality, intrinsic value and market expectations are separate conclusions. Every factual statement cites evidence [n]; see the bibliography.</div>
</div>
{% for s in sections %}
<h2>{{ loop.index }}. {{ s.title }}</h2>
{% if s.html %}{{ s.html|safe }}{% endif %}
{% for f in s.findings %}<div class="f {{ f.severity }}"><span class="t">{{ f.title }}</span><span class="tag">{{ f.severity }} · {{ f.epistemic_status.replace('_',' ') }}</span>
<div>{{ f.summary }}{% for i in f.evidence_ids[:6] %} <span class="cite">[{{ refmap.get(i, '?') }}]</span>{% endfor %}</div>
{% if f.limitations %}<div class="lim">Limitation: {{ f.limitations }}</div>{% endif %}</div>{% endfor %}
{% if not s.findings and not s.html %}<p class="empty">No findings in this section from the latest investigation{% if s.why %} — {{ s.why }}{% endif %}.</p>{% endif %}
{% endfor %}
<div class="disclaimer">DEEPTERMINAL reports contain deterministic calculations and evidence-linked findings. Model outputs depend on stated assumptions. A valuation discrepancy does not establish that the market is wrong.</div>
</body></html>"""


def _scenario_html(val: dict | None) -> str:
    if not val or not val.get("scenarios"):
        return "<p class='empty'>No valuation run is available (a discount rate is required; a price enables market expectations).</p>"
    rows = "".join(f"<tr><td>{s['name'].title()}</td><td>{s['dcf']['inputs']['revenue_growth'][0]*100:.1f}%</td>"
                   f"<td>{s['dcf']['inputs']['ebit_margin'][-1]*100:.1f}%</td><td>{s['dcf']['inputs']['discount_rate']*100:.2f}%</td>"
                   f"<td>{s['dcf']['enterprise_value']:,.0f}</td><td>{s['dcf']['terminal_share']*100:.0f}%</td>"
                   f"<td><b>{s['per_share']:,.2f}</b></td></tr>" for s in val["scenarios"])
    price = val.get("price")
    p = f"<p>Price {price['value']:,.2f} as of {price['as_of']} (source: {price['source']}). Basis: {val.get('basis')}.</p>" if price else ""
    assume = "".join(f"<li><b>{a['name']}</b> = {a['value']:.4g} — {a['rationale']}</li>" for a in val.get("assumptions", []))
    return (p + "<table><tr><th>Scenario</th><th>Year-1 growth</th><th>Final margin</th><th>Discount rate</th>"
            "<th>EV (USD m)</th><th>Terminal share</th><th>Value / share</th></tr>" + rows + "</table>"
            f"<p class='lim'>Assumptions:</p><ul class='lim'>{assume}</ul>")


def build_report(db, company: Company, job_id: str | None = None, valuation: dict | None = None,
                 thesis: dict | None = None) -> Report:
    if job_id is None:
        job = db.scalars(select(ResearchJob).where(ResearchJob.company_id == company.id,
                                                   ResearchJob.kind == "investigation", ResearchJob.status == "succeeded")
                         .order_by(ResearchJob.finished_at.desc())).first()
        job_id = job.id if job else None
    q = select(Finding).where(Finding.company_id == company.id)
    jobs = [job_id] if job_id else []
    th = db.scalars(select(ResearchJob).where(ResearchJob.company_id == company.id, ResearchJob.kind == "thesis",
                                              ResearchJob.status == "succeeded").order_by(ResearchJob.finished_at.desc())).first()
    if th:
        jobs.append(th.id)
        thesis = thesis or th.result
    findings = db.scalars(q.where(Finding.job_id.in_(jobs)).order_by(Finding.id)).all() if jobs else []
    if valuation is None:
        vr = db.scalars(select(ValuationRun).where(ValuationRun.company_id == company.id)
                        .order_by(ValuationRun.created_at.desc())).first()
        valuation = vr.result if vr else None
    by_mod: dict[str, list] = {}
    for f in findings:
        by_mod.setdefault(f.module, []).append(finding_dict(f))
    ev_ids = sorted({i for f in findings for i in f.evidence_ids})
    evidence = db.scalars(select(Evidence).where(Evidence.id.in_(ev_ids))).all() if ev_ids else []
    refmap = {e.id: n for n, e in enumerate(evidence, start=1)}
    order = {"concern": 0, "watch": 1, "positive": 2, "neutral": 3, "unavailable": 4}
    sections = []
    for key, title, mods in SECTIONS:
        fs_ = [f for m in mods for f in by_mod.get(m, [])]
        html, why = "", ""
        if key == "executive_summary":
            if not fs_:
                top = sorted([f for f in findings if f.severity in ("concern", "watch", "positive")],
                             key=lambda f: order[f.severity])[:8]
                fs_ = [finding_dict(f) for f in top]
                html = ("<p class='lim'>No AI synthesis is available (no LLM provider configured). The most material "
                        "deterministic findings are listed instead.</p>")
        elif key == "scenarios":
            html = _scenario_html(valuation)
        elif key == "major_risks":
            fs_ = [finding_dict(f) for f in findings if f.severity == "concern"][:15]
        elif key == "catalysts":
            fs_ = [finding_dict(f) for f in findings if f.module == "sec_analysis" and f.title.startswith("8-K")][:8]
            html = "<p class='lim'>Catalyst calendars and earnings dates require a licensed data provider; listed here are recent material SEC events.</p>"
        elif key == "counterarguments" and thesis:
            ce = thesis.get("counter_evidence", [])[:12]
            html = (f"<p>Thesis tested ({thesis.get('stance')}): “{thesis.get('thesis')}”. {len(ce)} counter-points; "
                    f"{len(thesis.get('not_found', []))} checks found nothing.</p>" +
                    "".join(f"<p class='lim'>Alternative explanation ({a['claim']}): {a['alternative']}</p>"
                            for a in thesis.get("alternative_explanations", [])[:6]))
            fs_ = ce + fs_
        elif key == "limitations":
            fs_ = [finding_dict(f) for f in findings if f.severity == "unavailable"]
        elif key == "bibliography":
            items = "".join(
                f"<li>[{refmap[e.id]}] {e.title}"
                + (f" — {e.source.publisher}, {e.source.title}" if e.source else "")
                + (f", published {e.source.published_at}" if e.source and e.source.published_at else "")
                + (f", retrieved {e.source.retrieved_at:%Y-%m-%d}" if e.source and e.source.retrieved_at else "")
                + f". Status: {e.epistemic_status.replace('_', ' ')}, {e.verification_status}."
                + (f" <a href='{e.source.url}'>{e.source.url}</a>" if e.source and e.source.url else "") + "</li>"
                for e in evidence)
            html = f"<ol class='bib'>{items}</ol>" if items else ""
        if not fs_ and not html:
            why = "run an investigation including the relevant modules" if not job_id else "no evidence in available data"
        fs_.sort(key=lambda f: order.get(f["severity"], 5))
        sections.append({"key": key, "title": title, "findings": fs_, "html": html, "why": why})
    env = Environment(autoescape=select_autoescape(["html"]))
    html = env.from_string(TEMPLATE).render(
        title=f"DEEPTERMINAL — {company.name}", company=company, sections=sections, refmap=refmap, job_id=job_id,
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    rep = Report(company_id=company.id, job_id=job_id, title=f"{company.name} — research report",
                 sections=[{"key": s["key"], "title": s["title"], "count": len(s["findings"])} for s in sections], html=html)
    db.add(rep)
    db.commit()
    return rep


def build_report_job(job_id: str, jl) -> dict:
    with session_scope() as db:
        job = db.get(ResearchJob, job_id)
        company = db.get(Company, job.company_id)
        jl("Compiling report sections…", progress=.3)
        rep = build_report(db, company, job.params.get("investigation_id"))
        jl(f"Report {rep.id} ready", progress=.95)
        return {"report_id": rep.id}


def chromium_path() -> str | None:
    s = get_settings().chromium_executable
    if s and os.path.exists(s):
        return s
    found = sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome"))
    return found[-1] if found else None


def render_pdf(html: str) -> bytes:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = chromium_path()
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.abort() if not route.request.url.startswith("data:")
                       and route.request.url != "about:blank" else route.continue_())
            page.set_content(html, wait_until="load")
            pdf = page.pdf(format="A4", print_background=True, display_header_footer=True,
                           header_template="<div></div>",
                           footer_template="<div style='font-size:7pt;color:#64748b;width:100%;text-align:center'>"
                                           "DEEPTERMINAL · page <span class='pageNumber'></span> of "
                                           "<span class='totalPages'></span></div>",
                           margin={"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"})
        finally:
            browser.close()
    return pdf
