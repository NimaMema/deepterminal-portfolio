"""Research tools exposed to LLM agents (read-only, bounded, evidence-producing).

Every tool that surfaces information records it as Evidence and returns the
evidence id, so the model can only cite things the system actually retrieved.
"""

from __future__ import annotations

import json
import re

from typing import Any

from sqlalchemy import select

from ..analysis import MODULES
from ..analysis.base import Ctx
from ..models import Evidence, Filing, Finding
from ..services import filings as fs
from ..services import valuation as vs
from ..services.evidence import computed_evidence, excerpt_evidence, evidence_dict, save_evidence
from ..services.gateway import DataUnavailable
from .guard import detect_injection, wrap
from .providers.base import ToolSpec


STOPWORDS = set("what how why when which who does did the and for with about from that this are was its their our".split())


class ToolBox:
    def __init__(self, ctx: Ctx, created_by: str, on_event=None):
        self.ctx = ctx
        self.created_by = created_by
        self.allowed: set[int] = set()
        self.injection_flags: list[dict] = []
        self.on_event = on_event
        self.corpus: list[str] = []          # every tool result, for checking figures in the answer

    def _remember(self, ids: list[int]) -> None:
        self.allowed.update(ids)

    # ── tools ──
    def company_profile(self, _: dict) -> dict:
        c = self.ctx.company
        return {"name": c.name, "ticker": c.ticker, "cik": c.cik, "sic": c.sic_description, "synthetic": c.synthetic,
                "state_of_incorporation": c.state_of_incorporation, "fiscal_year_end": c.fiscal_year_end}

    def financial_history(self, args: dict) -> dict:
        names = ["revenue", "operating_income", "net_income", "operating_cash_flow", "capex", "gross_profit",
                 "total_debt", "cash", "diluted_shares"]
        out = []
        for end in self.ctx.fiscal_ends[-int(args.get("years", 5)):]:
            row = {"fiscal_year_end": end.isoformat()}
            for n in names:
                e = self.ctx.ev(n, end)
                if e:
                    eid = save_evidence(self.ctx.db, self.ctx.company, e, self.ctx.job_id, self.created_by)
                    self._remember([eid])
                    row[n] = {"value_usd_m": round(e.value, 2), "evidence_id": f"E{eid}"}
            out.append(row)
        return {"annual": out, "note": "values in USD millions (shares in millions) from SEC XBRL"}

    def search_filings(self, args: dict) -> dict:
        q = str(args.get("query", ""))[:200]
        words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", q.lower()) if w not in STOPWORDS][:6]
        out = []
        for p in fs.passages(self.ctx.db, self.ctx.company.id, words, k=6):     # best sentences, not whole sections
            if args.get("forms") and p["form"] not in args["forms"]:
                continue
            f = self.ctx.db.scalar(select(Filing).where(Filing.accession == p["accession"]))
            ev = excerpt_evidence(self.ctx.db, self.ctx.company, f, p["key"], p["text"], "company_statement",
                                  f"{p['form']} {p['filed']} {p['title'][:60]}")
            eid = save_evidence(self.ctx.db, self.ctx.company, ev, self.ctx.job_id, self.created_by)
            self._remember([eid])
            flags = detect_injection(p["text"])
            if flags:
                self.injection_flags.append({"evidence_id": eid, "patterns": flags})
            out.append({"evidence_id": f"E{eid}", "form": p["form"], "filed": p["filed"],
                        "section": p["title"][:80], "verified_quote": ev.verification_status == "verified",
                        "content": wrap(f"E{eid}", p["title"], p["text"], 1500)})
        if not out:
            return {"results": [], "note": "No matches in indexed filings. Indexed filings: 10-K/10-Q/8-K text that "
                                           "has been retrieved; run the SEC module to index more."}
        return {"results": out}

    def module_findings(self, args: dict) -> dict:
        q = select(Finding).where(Finding.company_id == self.ctx.company.id)
        if args.get("module"):
            q = q.where(Finding.module == args["module"])
        rows = self.ctx.db.scalars(q.order_by(Finding.id.desc()).limit(25)).all()
        if not rows and args.get("module") in MODULES:
            spec = MODULES[args["module"]]
            if self.on_event:
                self.on_event(f"running module {spec.key} for agent")
            data = spec.compute(self.ctx)
            from ..services.evidence import save_finding
            rows = [save_finding(self.ctx.db, self.ctx.company, f, self.ctx.job_id, "rules")
                    for f in spec.findings(self.ctx, data)]
        out = []
        for f in rows:
            self._remember(f.evidence_ids)
            out.append({"module": f.module, "title": f.title, "summary": f.summary[:600], "severity": f.severity,
                        "epistemic_status": f.epistemic_status,
                        "evidence_ids": [f"E{i}" for i in f.evidence_ids], "limitations": f.limitations})
        return {"findings": out, "modules": list(MODULES)}

    def get_evidence(self, args: dict) -> dict:
        ids = [int(str(i).lstrip("E")) for i in args.get("ids", [])][:10]
        rows = self.ctx.db.scalars(select(Evidence).where(Evidence.id.in_(ids),
                                                          Evidence.company_id == self.ctx.company.id)).all()
        self._remember([r.id for r in rows])
        return {"evidence": [{"id": f"E{r.id}", "title": r.title, "epistemic_status": r.epistemic_status,
                              "verification_status": r.verification_status,
                              "content": wrap(f"E{r.id}", r.title, r.excerpt or "", 2000) if r.excerpt else None,
                              "value": r.value, "unit": r.unit, "source": evidence_dict(r)["source"]} for r in rows]}

    def valuation(self, args: dict) -> dict:
        # The model may not choose valuation inputs: the discount rate is the user's, and every other
        # assumption follows the engine's documented rules. Anything the model passes is ignored.
        dr = (self.ctx.cache.get("params") or {}).get("discount_rate")
        if not dr:
            return {"unavailable": {"status": "not_configured",
                                    "message": "No discount rate was set by the user for this job, so no valuation "
                                               "was run. Do not estimate one."}}
        params = {"discount_rate": dr}
        try:
            r = vs.value_company(self.ctx.db, self.ctx.company, params, None, self.ctx.as_of)
        except DataUnavailable as e:
            return {"unavailable": e.to_dict()}
        sc = {x["name"]: x["per_share"] for x in r["scenarios"]}
        title = (f"DCF per share: bear {sc.get('bear', 0):,.2f} / base {sc.get('base', 0):,.2f} / bull {sc.get('bull', 0):,.2f}"
                 f" at discount rate {dr:.2%}"
                 + (f"; price {r['price']['value']:,.2f} on {r['price']['as_of']} ({r['price'].get('source') or ''})"
                    if r.get("price") else "; no price"))
        eid = save_evidence(self.ctx.db, self.ctx.company,
                            computed_evidence(title, sc.get("base"), "deterministic FCFF DCF, user discount rate, "
                                              "documented default assumptions", [],
                                              limitations="Engine output under stated assumptions, not a fact."),
                            self.ctx.job_id, self.created_by)
        self._remember([eid])
        return {"evidence_id": f"E{eid}", "basis": r["basis"], "price": r["price"],
                "scenarios": [{"name": s["name"], "per_share": round(s["per_share"], 2), "narrative": s["narrative"]}
                              for s in r["scenarios"]],
                "reverse_dcf": [x["statement"] for x in r["reverse_dcf"]],
                "verdict": r["assessment"]["verdict"] if r.get("assessment") else None,
                "assumptions": [{"name": a["name"], "value": a["value"], "rationale": a["rationale"]} for a in r["assumptions"]],
                "note": "Model outputs under stated assumptions — not facts."}

    def specs(self) -> list[ToolSpec]:
        def recorded(spec: ToolSpec) -> ToolSpec:
            def fn(args, _f=spec.fn):
                out = _f(args)
                self.corpus.append(json.dumps(out, default=str))
                return out
            return ToolSpec(spec.name, spec.description, spec.parameters, fn)
        return [recorded(t) for t in self._specs()]

    def _specs(self) -> list[ToolSpec]:
        obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req),
                                     "additionalProperties": False}
        return [
            ToolSpec("company_profile", "Basic SEC registrant profile of the company under research.", obj({}), self.company_profile),
            ToolSpec("financial_history", "Annual XBRL financials (USD m) with evidence ids.",
                     obj({"years": {"type": "integer", "minimum": 1, "maximum": 10}}, ["years"]), self.financial_history),
            ToolSpec("search_filings", "Full-text search of the company's retrieved SEC filings. Returns quoted passages "
                     "as untrusted documents with evidence ids.",
                     obj({"query": {"type": "string"}, "forms": {"type": ["array", "null"], "items": {"type": "string"}}},
                         ["query", "forms"]), self.search_filings),
            ToolSpec("module_findings", "Findings from DEEPTERMINAL analysis modules (" + ", ".join(MODULES) + ").",
                     obj({"module": {"type": ["string", "null"], "enum": list(MODULES) + [None]}}, ["module"]),
                     self.module_findings),
            ToolSpec("get_evidence", "Retrieve evidence records by id (e.g. ['E12']).",
                     obj({"ids": {"type": "array", "items": {"type": "string"}}}, ["ids"]), self.get_evidence),
            ToolSpec("valuation", "Results of the deterministic DCF/reverse-DCF engine with the user's discount rate and "
                     "the engine's documented assumptions. Takes no inputs: you cannot change assumptions.",
                     obj({}), self.valuation),
        ]
