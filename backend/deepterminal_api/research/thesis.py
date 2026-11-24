"""Thesis Challenger: actively searches for evidence that the user's thesis could be wrong.

Process
1. Decompose the thesis into claims (keyword rules; LLM decomposition when configured).
2. Map each claim to checks in the analysis modules and run them.
3. Collect evidence that cuts AGAINST the stated stance (concern/watch findings for a bullish thesis,
   positive findings for a bearish one) and record checks that found nothing ("searched, not found").
4. Generate alternative explanations for the thesis's key observations.
5. Optional LLM pass: an agent with read-only tools searches filings for contradicting passages; its
   citations are validated against retrieved evidence.

It never outputs a verdict on the thesis — only the strongest counter-evidence and what was checked.
"""

from __future__ import annotations

import re

from sqlalchemy import select

from ..analysis import MODULES
from ..analysis.base import Ctx
from ..config import get_settings
from ..db import session_scope
from ..models import Company, Finding, ResearchJob
from ..services.evidence import FindingDraft, finding_dict, save_finding
from ..services.gateway import DataUnavailable
from . import guard
from .providers import check_daily_budget, get_provider, record_usage
from .tools import ToolBox

CLAIM_RULES = [
    ("growth", r"grow|growth|expand|demand|adoption|tam|market share", ["customer_demand", "market_expectations",
                                                                         "historical_analogues"]),
    ("margins & pricing power", r"margin|pricing power|profitab|operating leverage", ["product_research", "competitors",
                                                                                       "forensic_accounting"]),
    ("competitive advantage", r"moat|competitive|advantage|leader|dominan|superior|best", ["competitors", "product_research",
                                                                                          "sec_analysis"]),
    ("management quality", r"management|ceo|founder|capital allocation|execution", ["management_governance", "sec_analysis"]),
    ("valuation", r"undervalued|cheap|overvalued|expensive|valuation|price|upside|downside", ["financial_valuation",
                                                                                              "market_expectations"]),
    ("supply chain", r"supply|manufactur|capacity|supplier|chips?|production", ["supply_chain"]),
    ("financial strength", r"balance sheet|cash|debt|liquidity|solvent|cash flow", ["forensic_accounting",
                                                                                     "corporate_legitimacy"]),
    ("legal & regulatory", r"regulat|legal|lawsuit|export|antitrust|tariff", ["legal_regulatory"]),
]
ALWAYS = ["forensic_accounting", "sec_analysis", "legal_regulatory"]
ALTERNATIVES = {
    "growth": ["Growth may reflect price increases or a temporary shortage rather than durable unit demand.",
               "Customers may be pulling orders forward or building inventory.",
               "A few large customers may account for the growth (concentration risk)."],
    "margins & pricing power": ["Margins may be at a cyclical peak.", "Mix shift rather than pricing power may explain margins."],
    "competitive advantage": ["Competitors or customers' in-house alternatives may close the gap.",
                              "Advantage may rely on a single supplier or technology generation."],
    "valuation": ["The market may price risks not captured in the model (discount rate, terminal assumptions).",
                  "Small changes in long-run assumptions can explain the gap (see tornado)."],
    "management quality": ["Past execution may have benefited from favourable industry conditions."],
    "supply chain": ["Supply constraints can inflate prices temporarily and then reverse."],
}


def decompose(thesis: str) -> list[dict]:
    claims = []
    for name, rx, mods in CLAIM_RULES:
        if re.search(rx, thesis, re.I):
            claims.append({"claim": name, "modules": mods})
    if not claims:
        claims.append({"claim": "general thesis", "modules": ["financial_valuation", "competitors", "customer_demand"]})
    return claims


def run_thesis(job_id: str, jl) -> dict:
    with session_scope() as db:
        job = db.get(ResearchJob, job_id)
        params = dict(job.params)
        company = db.get(Company, job.company_id)
        thesis, stance = params["thesis"], params.get("stance", "bullish")
        claims = decompose(thesis)
        mods = list(dict.fromkeys([m for c in claims for m in c["modules"]] + ALWAYS))
        jl(f"Thesis decomposed into {len(claims)} claim(s): {', '.join(c['claim'] for c in claims)}", progress=.05,
           data={"claims": claims})
        ctx = Ctx(db, company, None, job_id, progress=lambda m: jl(m))
        ctx.cache["params"] = params
        against, supporting, not_found, unavailable = [], [], [], []
        contrary = {"concern", "watch"} if stance == "bullish" else {"positive"}
        for i, key in enumerate(mods):
            spec = MODULES[key]
            jl(f"Searching for counter-evidence: {spec.title}", module=key, progress=.1 + .7 * i / len(mods))
            try:
                data = spec.compute(ctx)
                if key == "financial_valuation":
                    ctx.cache["financial_valuation_data"] = data
                rows = [save_finding(db, company, d, job_id, "rules") for d in spec.findings(ctx, data)]
                db.commit()
            except DataUnavailable as e:
                db.rollback()
                unavailable.append({"module": key, "reason": e.message})
                continue
            hits = [r for r in rows if r.severity in contrary]
            for r in rows:
                if r.severity == "unavailable":
                    unavailable.append({"module": key, "reason": r.title})
                elif r.severity in contrary:
                    against.append(finding_dict(r))
                elif r.severity in ({"positive"} if stance == "bullish" else {"concern", "watch"}):
                    supporting.append(finding_dict(r))
            if rows and all(r.severity == "unavailable" for r in rows):
                continue            # nothing could be checked: listed under "could not check", not "not found"
            if not hits:
                not_found.append({"module": key, "check": spec.title,
                                  "result": "searched; no contradicting evidence found in available data"})
        alternatives = [{"claim": c["claim"], "alternative": a} for c in claims for a in ALTERNATIVES.get(c["claim"], [])]
        llm = _llm_challenge(db, company, job_id, thesis, stance, jl)
        sev_rank = {"concern": 0, "watch": 1, "positive": 2, "neutral": 3}
        against.sort(key=lambda f: sev_rank.get(f["severity"], 9))
        result = {"thesis": thesis, "stance": stance, "claims": claims, "counter_evidence": against[:40],
                  "supporting_evidence": supporting[:20], "not_found": not_found, "unavailable": unavailable[:20],
                  "alternative_explanations": alternatives, "llm": llm,
                  "principle": "The Challenger reports the strongest evidence against the thesis and what it checked. "
                               "It does not decide whether the thesis is right."}
        save_finding(db, company, FindingDraft("thesis_challenger", f"Thesis challenged: {len(against)} counter-points, "
                                                                     f"{len(not_found)} checks found nothing",
                                               thesis, "neutral", "analytical_inference", "medium",
                                               [i for f in against[:5] for i in f["evidence_ids"][:1]] or [],
                                               data={"stance": stance}) if against else
                     FindingDraft("thesis_challenger", "Thesis challenged: no counter-evidence in available data",
                                  thesis, "unavailable", "analytical_inference", "low"), job_id)
        db.commit()
        jl(f"Challenger finished: {len(against)} counter-points", progress=.98)
        return result


def _llm_challenge(db, company, job_id, thesis, stance, jl) -> dict:
    provider = get_provider()
    if provider is None:
        return {"status": "skipped", "reason": "No LLM provider configured; rule-based challenge only."}
    try:
        check_daily_budget(provider)
    except Exception as e:
        return {"status": "skipped", "reason": str(e)}
    s = get_settings()
    ctx = Ctx(db, company, None, job_id)
    tb = ToolBox(ctx, f"{provider.name}:{provider.model}", on_event=lambda m: jl(m, module="thesis_llm"))
    prompt = (f"Investment thesis ({stance}) about {company.name}: \"{thesis}\"\n\nYour job is to find the strongest "
              "evidence that this thesis could be WRONG: contradictory evidence, financial weaknesses, competitive "
              "threats, unrealistic valuation assumptions, management inconsistencies, supply-chain vulnerabilities, "
              "weak demand, alternative explanations. Use the tools to search filings and module findings. Then list "
              "each counter-argument as a bullet with its evidence ids [E#]. Also list what you searched for but did "
              "not find. Do not conclude whether the thesis is right.")
    jl(f"AI challenger ({provider.name}) searching filings…", module="thesis_llm")
    res = provider.run(guard.SYSTEM_RULES, prompt, tb.specs(), (s.ollama_max_tool_calls if provider.name == "ollama" else s.llm_max_tool_calls), s.llm_max_input_tokens_per_job,
                       s.ollama_max_output_tokens if provider.name == "ollama" else s.llm_max_output_tokens,
                       on_event=lambda m: jl(m, module="thesis_llm"))
    record_usage(provider, res.usage, job_id)
    db.commit()
    text, valid, invalid, removed = guard.ground(res.text, tb.allowed, "\n".join(tb.corpus))
    if valid:
        save_finding(db, company, FindingDraft("thesis_challenger", "AI counter-argument search", text, "watch",
                                               "analytical_inference", "medium", valid,
                                               f"{provider.name}:{provider.model}; {len(invalid)} invalid citations removed."),
                     job_id, f"{provider.name}:{provider.model}")
    return {"status": res.stopped, "text": text, "valid_citations": valid, "invalid_citations": invalid,
            "removed_sentences": len(removed), "model": f"{provider.name}:{provider.model}",
            "injection_flags": tb.injection_flags, "tool_calls": res.usage.tool_calls,
            "usage": {"input": res.usage.input_tokens, "output": res.usage.output_tokens}}
