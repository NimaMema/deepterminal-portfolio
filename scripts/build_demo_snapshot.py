"""Build the public-demo snapshot from a live DEEPTERMINAL database.

    python scripts/build_demo_snapshot.py --source postgresql://postgres@localhost:5432/deepterminal_live

Writes deploy/snapshot/{deepterminal.dump, cache.tar.gz, showcase.json}:

* the database, copied into a scratch database and cleaned (failed or unfinished jobs, personal
  items and settings, visitor-irrelevant chats removed);
* the recorded SEC EDGAR and free-source HTTP cache the API replays offline;
* the judges' guide data: recorded local-AI examples with their attribution, read from the jobs and
  messages themselves (model, generation time, citations, removed sentences).

Refuses to write anything that contains the SEC contact e-mail (DEEPTERMINAL_SEC_USER_AGENT).
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = "deepterminal_snapshot_build"
ENGINE = "Ollama 0.6.8"
HARDWARE = "4 CPU cores, no GPU"
ENGINE_FIX_AT = datetime.fromisoformat("2026-10-30T14:50:00+00:00")
DISCOUNT_NOTE = ("Chosen by the DEEPTERMINAL author to demonstrate the engine; it is not an estimate of any company's "
                 "cost of capital. In the Valuation laboratory you can set your own. Other inputs use the engine's "
                 "documented defaults derived from each company's filings, each shown with its rationale.")
QUESTIONS = {
    "NVDA": ["Who manufactures NVIDIA's wafers and what are the risks?", "What does NVIDIA say about export controls on sales to China?",
             "How concentrated are NVIDIA's customers?"],
    "AAPL": ["Where does Apple assemble its products?", "What does Apple say about tariffs?"],
    "MSFT": ["How much is Microsoft spending on AI infrastructure?", "What are Microsoft's main competitive risks?"],
    "AMD": ["Who manufactures AMD's chips?"],
    "INTC": ["What does Intel say about its foundry business?"],
}


def pg(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def run(*cmd: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kw)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=os.environ.get("DEEPTERMINAL_DATABASE_URL", "postgresql://postgres@localhost:5432/deepterminal_live"))
    ap.add_argument("--cache", default=str(ROOT / "backend" / ".cache"))
    ap.add_argument("--out", default=str(ROOT / "deploy" / "snapshot"))
    ap.add_argument("--snapshot-date", default=datetime.now().date().isoformat())
    ap.add_argument("--fixed-at", default="2026-10-30T02:45:00+00:00",
                    help="examples recorded before this time predate the latest grounding fixes and are labelled so")
    a = ap.parse_args()
    src = pg(a.source)
    base = src.rsplit("/", 1)[0]
    scratch = f"{base}/{SCRATCH}"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", os.environ.get("DEEPTERMINAL_SEC_USER_AGENT", ""))
    secret = m.group(0).lower() if m else None

    # 1. Copy into a scratch database and clean it there; the live database is never modified.
    with psycopg.connect(f"{base}/postgres", autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {SCRATCH}")
        c.execute(f"CREATE DATABASE {SCRATCH}")
    dump = subprocess.run(["pg_dump", "-Fc", src], check=True, capture_output=True).stdout
    run("pg_restore", "--no-owner", "--no-privileges", "-d", scratch, input=dump)
    with psycopg.connect(scratch) as c:
        failed = [r[0] for r in c.execute("SELECT id FROM research_jobs WHERE status <> 'succeeded'")]
        for t in ("job_events", "findings"):
            c.execute(f"DELETE FROM {t} WHERE job_id = ANY(%s)", (failed,))
        c.execute("DELETE FROM research_jobs WHERE id = ANY(%s)", (failed,))
        c.execute("DELETE FROM saved_items")
        c.execute("DELETE FROM app_settings")
        # Chats: keep one extractive example per question and local-model answers that cite evidence.
        c.execute("""DELETE FROM chat_sessions s WHERE EXISTS (
                       SELECT 1 FROM chat_messages m WHERE m.session_id = s.id AND m.role = 'assistant'
                       AND m.generated_by LIKE 'ollama:%%' AND COALESCE((m.usage->>'coverage')::float, 0) = 0)""")
        c.execute("""DELETE FROM chat_sessions s WHERE s.id IN (
                       SELECT session_id FROM (SELECT session_id, row_number() OVER (PARTITION BY content ORDER BY id DESC) n
                                               FROM chat_messages WHERE role = 'user') q WHERE n > 1)
                     AND NOT EXISTS (SELECT 1 FROM chat_messages m WHERE m.session_id = s.id AND m.generated_by LIKE 'ollama:%%')""")
        c.execute("DELETE FROM chat_messages WHERE session_id NOT IN (SELECT id FROM chat_sessions)")
        showcase = build_showcase(c, a.snapshot_date, datetime.fromisoformat(a.fixed_at))
        c.commit()

    # 2. Dump, cache and guide data, each checked for the contact e-mail before it is kept.
    data = subprocess.run(["pg_dump", "-Fc", "-Z9", "--no-owner", "--no-privileges", scratch],
                          check=True, capture_output=True).stdout
    plain = subprocess.run(["pg_dump", "--data-only", scratch], check=True, capture_output=True).stdout
    if secret and secret.encode() in plain.lower():
        sys.exit("refusing: the contact e-mail appears in the database snapshot")
    (out / "deepterminal.dump").write_bytes(data)

    cache = Path(a.cache)
    members = [p for d in ("sec", "free") for p in sorted((cache / d).rglob("*")) if p.is_file()
               and "stooq" not in p.parts]
    for p in members:
        raw = p.read_bytes()
        body = gzip.decompress(raw) if p.suffix == ".gz" else raw
        if secret and secret.encode() in body.lower():
            sys.exit(f"refusing: the contact e-mail appears in {p}")
    with tarfile.open(out / "cache.tar.gz", "w:gz") as tf:
        for p in members:
            tf.add(p, arcname=str(p.relative_to(cache)))
    text = json.dumps(showcase, indent=2)
    if secret and secret in text.lower():
        sys.exit("refusing: the contact e-mail appears in the showcase")
    (out / "showcase.json").write_text(text + "\n")
    with psycopg.connect(f"{base}/postgres", autocommit=True) as c:
        c.execute(f"DROP DATABASE IF EXISTS {SCRATCH}")
    print(f"snapshot: {len(data) / 1e6:.1f} MB database, {(out / 'cache.tar.gz').stat().st_size / 1e6:.1f} MB cache "
          f"({len(members)} files), {len(showcase['examples'])} AI examples")


def build_showcase(c, snapshot_date: str, fixed_at: datetime) -> dict:
    companies = []
    for cid, ticker, name in c.execute("""SELECT co.id, co.ticker, co.name FROM companies co WHERE EXISTS (
            SELECT 1 FROM research_jobs j WHERE j.company_id = co.id AND j.kind = 'investigation') ORDER BY co.id""").fetchall():
        price = c.execute("SELECT value, as_of FROM price_quotes WHERE company_id = %s ORDER BY as_of DESC LIMIT 1", (cid,)).fetchone()
        job = c.execute("""SELECT id FROM research_jobs WHERE company_id = %s AND kind = 'investigation'
                           ORDER BY finished_at DESC LIMIT 1""", (cid,)).fetchone()
        n = c.execute("SELECT count(*) FROM findings WHERE job_id = %s", (job[0],)).fetchone()[0]
        companies.append({"id": cid, "ticker": ticker, "name": name, "findings": n,
                          "price": {"value": float(price[0]), "as_of": price[1].isoformat()} if price else None})
    tick = {x["id"]: x["ticker"] for x in companies}
    examples = []

    def note(at: datetime) -> str:
        parts = []
        if at < fixed_at:
            parts.append("Recorded before the latest grounding fixes (valuation findings pinned in the evidence, "
                         "engine-computed valuation citations), so its valuation discussion is less complete than newer examples.")
        if at < ENGINE_FIX_AT:
            parts.append("Any per-share values it quotes predate a 2026-10-30 engine correction (balance-sheet, option "
                         "and RSU figures last tagged years earlier are no longer used); the Valuation laboratory shows "
                         "current figures.")
        return " ".join(parts)

    def gen_seconds(job_id: str, marker: str) -> float | None:
        evs = c.execute("SELECT ts, message FROM job_events WHERE job_id = %s ORDER BY id", (job_id,)).fetchall()
        for i, (ts, msg) in enumerate(evs):
            if marker in msg and i + 1 < len(evs):
                return (evs[i + 1][0] - ts).total_seconds()
        return None

    def llm_seconds(job_id: str, end: datetime) -> float | None:      # the challenger's LLM pass runs to the end
        row = c.execute("SELECT min(ts) FROM job_events WHERE job_id = %s AND module = 'thesis_llm'", (job_id,)).fetchone()
        return (end - row[0]).total_seconds() if row and row[0] else None

    # Investigation syntheses (newest per company)
    for cid in tick:
        row = c.execute("""SELECT f.id, f.job_id, j.finished_at, NULL FROM findings f JOIN research_jobs j ON j.id = f.job_id
                           WHERE f.company_id = %s AND f.module = 'synthesis' AND f.title = 'AI research synthesis'
                           ORDER BY j.finished_at DESC LIMIT 1""", (cid,)).fetchone()
        if not row:
            continue
        fid, job_id, at, _ = row
        cites = c.execute("SELECT jsonb_array_length(evidence_ids) FROM findings WHERE id = %s", (fid,)).fetchone()[0]
        removed = None
        for (msg,) in c.execute("SELECT message FROM job_events WHERE job_id = %s AND module = 'synthesis'", (job_id,)):
            mm = re.search(r"(\d+) unsupported-figure sentences removed", msg)
            if mm:
                removed = int(mm.group(1))
        model = c.execute("SELECT message FROM job_events WHERE job_id = %s AND message LIKE 'Synthesising with %%'",
                          (job_id,)).fetchone()
        examples.append({"kind": "synthesis", "title": f"{tick[cid]} investigation synthesis", "company_id": cid,
                         "ticker": tick[cid], "href": f"/company/{cid}/research?job={job_id}",
                         "prompt": "Write a research synthesis of this investigation using only its findings and evidence; "
                                   "cite every claim.",
                         "model": model[0].split("with ", 1)[1].rstrip("…").split(":", 1)[1] if model else "local model",
                         "engine": ENGINE, "hardware": HARDWARE, "runtime_seconds": gen_seconds(job_id, "Synthesising with"),
                         "recorded_at": at.isoformat(), "citations": cites, "removed_sentences": removed, "notes": note(at)})
    # Thesis challenges with a local-model pass
    for job_id, cid, params, result, at in c.execute(
            """SELECT id, company_id, params, result, finished_at FROM research_jobs WHERE kind = 'thesis'
               ORDER BY finished_at DESC""").fetchall():
        llm = (result or {}).get("llm") or {}
        if not llm.get("text") or cid not in tick:
            continue
        examples.append({"kind": "thesis", "title": f"{tick[cid]} thesis challenge", "company_id": cid, "ticker": tick[cid],
                         "href": f"/company/{cid}/thesis?job={job_id}", "prompt": params.get("thesis", ""),
                         "model": (llm.get("model") or "ollama:qwen2.5:7b-instruct").split(":", 1)[1], "engine": ENGINE,
                         "hardware": HARDWARE, "runtime_seconds": llm_seconds(job_id, at),
                         "recorded_at": at.isoformat(), "citations": len(llm.get("valid_citations") or []),
                         "removed_sentences": llm.get("removed_sentences"), "notes": note(at)})
    # Chat answers by the local model that cite evidence
    for sid, cid, q, ans_at, q_at, usage, mid in c.execute(
            """SELECT s.id, s.company_id, u.content, a.created_at, u.created_at, a.usage, a.id
               FROM chat_messages a JOIN chat_sessions s ON s.id = a.session_id
               JOIN LATERAL (SELECT content, created_at FROM chat_messages u WHERE u.session_id = a.session_id
                             AND u.role = 'user' AND u.id < a.id ORDER BY u.id DESC LIMIT 1) u ON true
               WHERE a.role = 'assistant' AND a.generated_by LIKE 'ollama:%%' ORDER BY a.created_at DESC""").fetchall():
        if cid not in tick:
            continue
        cites = c.execute("SELECT citations FROM chat_messages WHERE id = %s", (mid,)).fetchone()[0]
        examples.append({"kind": "chat", "title": f"{tick[cid]} research chat", "company_id": cid, "ticker": tick[cid],
                         "href": f"/company/{cid}/chat?session={sid}", "prompt": q, "model": "qwen2.5:7b-instruct",
                         "engine": ENGINE, "hardware": HARDWARE, "runtime_seconds": (ans_at - q_at).total_seconds(),
                         "recorded_at": ans_at.isoformat(), "citations": len(cites or []),
                         "removed_sentences": (usage or {}).get("removed"), "notes": note(ans_at)})
    examples.sort(key=lambda e: (e["notes"] != "", {"synthesis": 0, "thesis": 1, "chat": 2}[e["kind"]], e["company_id"]))
    return {"snapshot_date": snapshot_date, "companies": companies, "examples": examples,
            "sample_questions": [{"company_id": cid, "ticker": t, "question": q}
                                 for cid, t in tick.items() for q in QUESTIONS.get(t, [])],
            "valuation": {"discount_rate": 0.09, "note": DISCOUNT_NOTE}}


if __name__ == "__main__":
    main()
