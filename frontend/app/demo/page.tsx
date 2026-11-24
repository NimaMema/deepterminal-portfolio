"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Bot, Calculator, Clock3, FileSearch, FileText, Gauge, Lock, MessagesSquare, Network, Scale, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { Page, PageHeader } from "@/components/company";
import { LoadingPanel, Notice, Panel } from "@/components/ui";
import { api } from "@/lib/api";
import { date } from "@/lib/format";

interface Example {
  kind: "synthesis" | "thesis" | "chat"; title: string; company_id: number; ticker: string; href: string;
  prompt: string; model: string; engine: string; hardware: string; runtime_seconds: number | null; recorded_at: string;
  citations: number | null; removed_sentences: number | null; notes: string;
}
interface Showcase {
  snapshot_date?: string;
  companies?: { id: number; ticker: string; name: string; price: { value: number; as_of: string } | null; findings: number }[];
  examples?: Example[];
  sample_questions?: { company_id: number; ticker: string; question: string }[];
  valuation?: { discount_rate: number; note: string };
}

const TOUR = [
  { icon: FileSearch, title: "Company profile & financials", path: "", text: "SEC submissions profile, ten-plus years of XBRL statements, split-adjusted, every cell traceable to its filing." },
  { icon: Clock3, title: "Filing time machine", path: "/time-machine", text: "What was knowable on any past date, later restatements and risk-factor changes between 10-Ks." },
  { icon: Network, title: "Supply chain", path: "/supply-chain", text: "Suppliers, customers and concentration extracted from 10-K text, and other filers who name the company." },
  { icon: Calculator, title: "Valuation laboratory", path: "/valuation", text: "Edit any assumption; DCF, bear/base/bull scenarios, sensitivity and tornado are recomputed live." },
  { icon: Gauge, title: "Reverse DCF", path: "/reverse-dcf", text: "What growth, margin or return the market price implies, solved lever by lever." },
  { icon: Scale, title: "Thesis challenger", path: "/thesis", text: "Type a thesis; it is split into claims and tested against the recorded evidence (rule-based in the demo)." },
  { icon: MessagesSquare, title: "Research chat", path: "/chat", text: "Recorded local-model answers with citations; new questions are answered extractively from the evidence." },
  { icon: FileText, title: "Research report", path: "", report: true, text: "21-section report with a numbered bibliography, exportable as PDF." },
];

const LIVE = [
  "Every dashboard, chart, filing viewer and evidence source viewer",
  "Valuation laboratory: DCF, scenarios, sensitivity, multiples, SOTP/NAV, supply-shock scenarios",
  "Reverse DCF with the iso-value curve",
  "Thesis Challenger (rule-based) and research chat (extractive), rate-limited",
  "Report viewer and PDF export",
];
const BACKEND_ONLY = [
  "Researching companies outside the snapshot (live SEC EDGAR retrieval)",
  "New investigations and new local-AI (Ollama) generations, which take minutes on a CPU",
  "Fetching new prices, macro data, sanctions and archive look-ups",
  "Saving valuation runs, watchlists, notes and peers; generating new reports",
  "Settings changes and optional paid AI providers (off by default)",
];

function mins(s: number | null) { return s == null ? "—" : s < 90 ? `${Math.round(s)} s` : `${(s / 60).toFixed(1)} min`; }

export default function DemoGuide() {
  const q = useQuery({ queryKey: ["showcase"], queryFn: () => api<Showcase>("/demo/showcase") });
  const d = q.data;
  const lead = d?.companies?.[0];
  return (
    <Page>
      <PageHeader title="Judges' guide" description="DEEPTERMINAL is an evidence-first equity research terminal: every figure carries its SEC source, and anything it cannot verify is reported as unavailable, never invented. This public demo serves a recorded snapshot of real SEC EDGAR data." />
      {q.isLoading && <LoadingPanel rows={6} />}
      {d && (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {d.companies?.map((c) => (
              <Link key={c.id} href={`/company/${c.id}`} className="group rounded-xl border border-ink-700 bg-ink-900 p-4 transition-colors hover:border-accent/60">
                <div className="flex items-center justify-between"><span className="num rounded border border-accent/40 bg-accent/10 px-2 py-0.5 text-sm font-bold text-accent">{c.ticker}</span>
                  <ArrowRight size={14} className="text-fg-3 group-hover:text-accent" aria-hidden /></div>
                <div className="mt-2 truncate text-sm font-medium">{c.name}</div>
                <div className="mt-1 text-xs text-fg-3">{c.findings} evidence-backed findings{c.price ? ` · Form 4 price $${c.price.value.toFixed(2)} (${date(c.price.as_of)})` : ""}</div>
              </Link>))}
          </div>

          <Panel title="Three-minute tour" subtitle={lead ? `Using ${lead.ticker}; every page works for each company above` : undefined}>
            <ol className="grid gap-3 md:grid-cols-2">
              {TOUR.map((t, i) => {
                const href = !lead ? "#" : t.report ? `/reports?company=${lead.id}` : `/company/${lead.id}${t.path}`;
                return (
                  <li key={t.title}>
                    <Link href={href} className="flex h-full gap-3 rounded-lg border border-ink-700 bg-ink-850 p-3 hover:border-accent/60">
                      <span className="num grid size-7 shrink-0 place-items-center rounded-full bg-accent/15 text-xs font-bold text-accent">{i + 1}</span>
                      <span><span className="flex items-center gap-1.5 text-sm font-semibold"><t.icon size={14} aria-hidden className="text-accent" />{t.title}</span>
                        <span className="mt-0.5 block text-xs text-fg-2">{t.text}</span></span>
                    </Link>
                  </li>);
              })}
            </ol>
          </Panel>

          <Panel title="Recorded AI research examples" subtitle="Precomputed so you do not wait for local inference; shown exactly as generated, after DEEPTERMINAL's grounding checks">
            <Notice>Generated locally by an open-weight model through Ollama, with no paid API. Each answer could only cite evidence it was given,
              and sentences stating figures not found in that evidence were removed automatically. The deterministic findings remain the authority.</Notice>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              {d.examples?.map((e) => (
                <Link key={e.href} href={e.href} className="block rounded-lg border border-ink-700 bg-ink-850 p-3 hover:border-accent/60">
                  <div className="flex items-center gap-2 text-[11px] uppercase tracking-wider text-fg-3"><Bot size={12} aria-hidden className="text-accent" />{e.kind === "synthesis" ? "Investigation synthesis" : e.kind === "thesis" ? "Thesis challenge" : "Research chat"} · {e.ticker}</div>
                  <div className="mt-1 text-sm font-semibold">{e.title}</div>
                  <p className="mt-1 line-clamp-3 text-xs text-fg-2">“{e.prompt}”</p>
                  <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] text-fg-3">
                    <dt>Model</dt><dd className="num text-fg-2">{e.model}</dd>
                    <dt>Engine · hardware</dt><dd className="text-fg-2">{e.engine} · {e.hardware}</dd>
                    <dt>Generation time</dt><dd className="num text-fg-2">{mins(e.runtime_seconds)}</dd>
                    <dt>Recorded</dt><dd className="num text-fg-2">{date(e.recorded_at)}</dd>
                    {e.citations != null && <><dt>Cited sources</dt><dd className="num text-fg-2">{e.citations}</dd></>}
                    {e.removed_sentences != null && <><dt>Unsupported sentences removed</dt><dd className="num text-fg-2">{e.removed_sentences}</dd></>}
                  </dl>
                  {e.notes && <p className="mt-2 text-[11px] text-warn">{e.notes}</p>}
                </Link>))}
            </div>
          </Panel>

          <Panel title="Sample research questions" subtitle="Open the chat with the question filled in; answers in the demo are extractive and cite their sources">
            <ul className="flex flex-wrap gap-2">
              {d.sample_questions?.map((s) => (
                <li key={s.question + s.ticker}><Link href={`/company/${s.company_id}/chat?q=${encodeURIComponent(s.question)}`}
                  className="inline-block rounded-full border border-ink-600 px-3 py-1 text-xs text-fg-2 hover:border-accent/60 hover:text-fg"><b className="num text-accent">{s.ticker}</b> {s.question}</Link></li>))}
            </ul>
          </Panel>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Works live in this demo">
              <ul className="space-y-1.5 text-sm text-fg-2">{LIVE.map((x) => <li key={x} className="flex gap-2"><ShieldCheck size={14} className="mt-0.5 shrink-0 text-good" aria-hidden />{x}</li>)}</ul>
            </Panel>
            <Panel title="Needs the full local backend" subtitle="Free to run locally: PostgreSQL, FastAPI, Next.js and Ollama">
              <ul className="space-y-1.5 text-sm text-fg-2">{BACKEND_ONLY.map((x) => <li key={x} className="flex gap-2"><Lock size={14} className="mt-0.5 shrink-0 text-fg-3" aria-hidden />{x}</li>)}</ul>
            </Panel>
          </div>

          <Panel title="Valuation assumptions and data">
            <ul className="list-disc space-y-1.5 pl-5 text-sm text-fg-2">
              {d.valuation && <li><b>Discount rate {(d.valuation.discount_rate * 100).toFixed(0)}% is illustrative.</b> {d.valuation.note}</li>}
              <li><b>Prices are SEC Form 4 insider trade prices</b>: the volume-weighted price of open-market insider trades on the latest trade date in the snapshot. They are real, dated transactions, not official closing prices, and can be weeks old, so a valuation dated today reports “too uncertain”. Set the valuation date to the price date to see the full verdict.</li>
              <li><b>Financial data</b>: SEC EDGAR submissions, XBRL company facts and filing documents (US government public data), recorded {d.snapshot_date}. Treasury yields: FRED. Sanctions: OFAC SDN list. Website history: Internet Archive.</li>
              <li>No buy or sell recommendation is made. This is a research tool, not investment advice.</li>
            </ul>
          </Panel>
        </div>
      )}
    </Page>
  );
}
