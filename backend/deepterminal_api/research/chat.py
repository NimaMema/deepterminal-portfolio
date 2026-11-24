"""AI Research Chat with citations.

With an LLM configured: an agent with read-only research tools answers, citing evidence
ids that the tools actually returned (validated). Without an LLM: an extractive answer
that lists the most relevant evidence — clearly labelled, no generated prose.
"""

from __future__ import annotations

import re

from sqlalchemy import or_, select

from ..analysis.base import Ctx
from ..config import get_settings
from ..models import ChatMessage, ChatSession, Company, Evidence, Finding, ValuationRun
from ..services.evidence import evidence_dict, excerpt_evidence, save_evidence
from ..services import filings as fs
from . import guard
from .providers import check_daily_budget, get_provider, record_usage
from .tools import ToolBox

STOP = set("what how why when which who does did is are was the a an of for to in on and or with company its it "
           "their about tell me show give explain say says said our we any there".split())


def _keywords(q: str, company: Company | None = None) -> list[str]:
    own = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", (company.name if company else "") + " " + ((company.ticker or "") if company else ""))}
    return [w for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", q.lower()) if w not in STOP and w not in own][:6]


def extractive_answer(db, company: Company, question: str) -> tuple[str, list[int]]:
    kws = _keywords(question, company)
    cited: list[int] = []
    lines = []
    if kws:
        from ..models import Filing
        for psg in fs.passages(db, company.id, kws, k=4):
            f = db.scalar(select(Filing).where(Filing.accession == psg["accession"]))
            eid = save_evidence(db, company, excerpt_evidence(db, company, f, psg["key"], psg["text"]), None, "chat:rules")
            cited.append(eid)
            lines.append(f"- {psg['form']} filed {psg['filed']} ({psg['title'][:60]}): “{psg['text']}” [E{eid}]")
        conds = [Finding.title.ilike(f"%{k}%") for k in kws] + [Finding.summary.ilike(f"%{k}%") for k in kws]
        titles: set[str] = set()
        for f in db.scalars(select(Finding).where(Finding.company_id == company.id, or_(*conds),
                                                  Finding.severity != "unavailable").order_by(Finding.id.desc()).limit(40)):
            if f.title in titles:
                continue                 # the same finding from an earlier investigation run
            titles.add(f.title)
            if len(titles) > 5:
                break
            cite = " ".join(f"[E{i}]" for i in f.evidence_ids[:2])
            cited.extend(f.evidence_ids[:2])
            lines.append(f"- Finding ({f.module}, {f.severity}): {f.title} {cite}")
    if not lines:
        return ("No language model is configured, and no indexed filing passages or findings matched your question. "
                "Run an investigation (or open the SEC Filing Explorer to index filings) and ask again.", [])
    return ("No language model is configured, so this is an extractive answer: the most relevant evidence "
            "DEEPTERMINAL holds, without generated interpretation.\n\n" + "\n".join(lines), cited)


def ask(db, session: ChatSession, question: str) -> ChatMessage:
    company = db.get(Company, session.company_id) if session.company_id else None
    db.add(ChatMessage(session_id=session.id, role="user", content=question[:4000]))
    db.flush()
    provider = get_provider()
    if company is None:
        msg = ChatMessage(session_id=session.id, role="assistant", generated_by="rules", citations=[],
                          content="Open a company first; research chat answers questions about a specific company's evidence.")
        db.add(msg)
        db.commit()
        return msg
    if provider is None:
        text, cited = extractive_answer(db, company, question)
        msg = ChatMessage(session_id=session.id, role="assistant", content=text, citations=sorted(set(cited)),
                          generated_by="rules")
        db.add(msg)
        db.commit()
        return msg
    check_daily_budget(provider)
    s = get_settings()
    history = db.scalars(select(ChatMessage).where(ChatMessage.session_id == session.id)
                         .order_by(ChatMessage.id.desc()).limit(7)).all()[::-1]
    convo = "\n".join(f"{m.role.upper()}: {m.content[:1500]}" for m in history[:-1])
    ctx = Ctx(db, company)
    # Valuation questions use the discount rate from the user's latest saved valuation run, if any.
    run = db.scalar(select(ValuationRun).where(ValuationRun.company_id == company.id).order_by(ValuationRun.id.desc()))
    if run and (run.settings or {}).get("discount_rate"):
        ctx.cache["params"] = {"discount_rate": run.settings["discount_rate"]}
    tb = ToolBox(ctx, f"chat:{provider.name}")
    prompt = ((f"Previous conversation:\n{convo}\n\n" if convo else "") +
              f"Question about {company.name} ({company.ticker})"
              + (" — a SYNTHETIC demo company" if company.synthetic else "") +
              f": {question}\n\nUse the tools to gather evidence for every part of the question (for example "
              "module_findings with module='supply_chain' for supply-chain risks, 'valuation' for value), then answer "
              "concisely. Cite the evidence_id values the tools returned, one per bracket like [E12]; never invent ids "
              "or numbers.")
    res = provider.run(guard.SYSTEM_RULES, prompt, tb.specs(), (s.ollama_max_tool_calls if provider.name == "ollama" else s.llm_max_tool_calls), s.llm_max_input_tokens_per_job // 4,
                       (s.ollama_max_output_tokens if provider.name == "ollama" else s.llm_max_output_tokens))
    record_usage(provider, res.usage, None)
    text, valid, invalid, removed = guard.ground(res.text, tb.allowed, "\n".join(tb.corpus))
    if invalid:
        text += f"\n\n_{len(invalid)} citation(s) to unknown sources were removed._"
    if tb.injection_flags:
        text += "\n\n_Warning: some retrieved passages contained instruction-like text; they were treated as data._"
    msg = ChatMessage(session_id=session.id, role="assistant", content=text, citations=valid,
                      generated_by=f"{provider.name}:{provider.model}",
                      usage={"input": res.usage.input_tokens, "output": res.usage.output_tokens,
                             "tool_calls": res.usage.tool_calls, "coverage": guard.citation_coverage(text),
                             "stopped": res.stopped})
    db.add(msg)
    db.commit()
    return msg


def message_dict(db, m: ChatMessage) -> dict:
    ev = db.scalars(select(Evidence).where(Evidence.id.in_(m.citations or []))).all()
    return {"id": m.id, "role": m.role, "content": m.content, "generated_by": m.generated_by, "usage": m.usage,
            "created_at": m.created_at.isoformat(), "citations": [evidence_dict(e) for e in ev]}
