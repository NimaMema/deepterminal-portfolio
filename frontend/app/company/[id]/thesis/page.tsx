"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Page, PageHeader, useCompanyId } from "@/components/company";
import { CitedText, FindingCard } from "@/components/evidence";
import { JobProgress, useJobLive } from "@/components/jobs";
import { Button, Field, Input, Notice, Panel, Select, Unavailable } from "@/components/ui";
import { api, post } from "@/lib/api";
import { date } from "@/lib/format";
import type { Finding, Job } from "@/lib/types";

interface ThesisResult { thesis: string; stance: string; claims: { claim: string; modules: string[] }[]; counter_evidence: Finding[]; supporting_evidence: Finding[];
  not_found: { module: string; check: string; result: string }[]; unavailable: { module: string; reason: string }[];
  alternative_explanations: { claim: string; alternative: string }[]; llm: { status: string; reason?: string; text?: string; invalid_citations?: number[]; injection_flags?: unknown[] }; principle: string }

export default function Thesis() {
  return <Suspense><ThesisInner /></Suspense>;
}

function ThesisInner() {
  const id = useCompanyId();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [stance, setStance] = useState("bullish");
  const [dr, setDr] = useState("");
  const [jobId, setJobId] = useState<string | null>(useSearchParams().get("job"));
  const jobs = useQuery({ queryKey: ["jobs", id], queryFn: () => api<Job[]>(`/companies/${id}/jobs`) });
  useEffect(() => { if (!jobId) { const j = jobs.data?.find((x) => x.kind === "thesis"); if (j) setJobId(j.id); } }, [jobs.data, jobId]);
  const start = useMutation({ mutationFn: () => post<Job>("/jobs", { company_id: id, kind: "thesis", thesis: text, stance, discount_rate: dr ? Number(dr) : null }),
    onSuccess: (j) => { setJobId(j.id); qc.invalidateQueries({ queryKey: ["jobs", id] }); } });
  const { job } = useJobLive(jobId);
  // The live stream can report "succeeded" before the job's result payload has been refetched.
  const res = job?.status === "succeeded" && (job.result as { claims?: unknown })?.claims ? (job.result as unknown as ThesisResult) : null;
  return (
    <Page>
      <PageHeader title="Thesis challenger" description="State your thesis. The challenger decomposes it into claims, runs the relevant investigations, and reports the strongest evidence that it could be wrong — plus what it searched for and did not find. It never declares the thesis right or wrong." />
      <Panel title="Your thesis">
        <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (text.trim()) start.mutate(); }}>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} required aria-label="Investment thesis"
            placeholder="e.g. Demand for its data-center chips will sustain 40% growth, and its technology lead gives it lasting pricing power."
            className="w-full rounded-md border border-ink-600 bg-ink-850 p-3 text-sm text-fg placeholder:text-fg-3 focus:border-accent focus:outline-none" />
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Stance"><Select value={stance} onChange={(e) => setStance(e.target.value)}><option value="bullish">Bullish</option><option value="bearish">Bearish</option></Select></Field>
            <Field label="Discount rate (optional)"><Input value={dr} onChange={(e) => setDr(e.target.value)} placeholder="0.09" className="w-28" /></Field>
            <Button type="submit" variant="primary" loading={start.isPending}>Challenge thesis</Button>
          </div>
          {start.error && <Unavailable error={start.error} compact />}
        </form>
      </Panel>
      {jobId && <Panel title="Investigation progress"><JobProgress jobId={jobId} /></Panel>}
      {res && (
        <>
          <Notice>{res.principle}</Notice>
          <Panel title={`“${res.thesis}”`} subtitle={`${res.stance} · ${res.claims.length} claims tested · ${date(job?.finished_at)}`}>
            <div className="flex flex-wrap gap-2">{res.claims.map((c) => <span key={c.claim} className="rounded-md border border-ink-600 bg-ink-850 px-2 py-1 text-xs">{c.claim} <span className="text-fg-3">→ {c.modules.join(", ").replace(/_/g, " ")}</span></span>)}</div>
          </Panel>
          <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <Panel title={`Counter-evidence (${res.counter_evidence.length})`} subtitle="Strongest first">
              {res.counter_evidence.length === 0 && <p className="text-sm text-fg-3">No contradicting evidence found in available data.</p>}
              <div className="space-y-2">{res.counter_evidence.map((f) => <FindingCard key={f.id} f={f} />)}</div>
            </Panel>
            <div className="space-y-4">
              <Panel title="Alternative explanations"><ul className="space-y-2 text-sm">{res.alternative_explanations.map((a, i) => <li key={i} className="rounded border border-ink-700 bg-ink-850 p-2"><span className="text-[11px] uppercase text-fg-3">{a.claim}</span><div className="text-fg-2">{a.alternative}</div></li>)}</ul></Panel>
              <Panel title="Searched — nothing contradicting found"><ul className="space-y-1 text-sm text-fg-2">{res.not_found.map((n) => <li key={n.module}>✓ {n.check}</li>)}</ul></Panel>
              <Panel title="Could not check"><ul className="space-y-1 text-xs text-fg-3">{res.unavailable.map((u, i) => <li key={i}>{u.module.replace(/_/g, " ")}: {u.reason}</li>)}</ul></Panel>
              <Panel title={`Evidence supporting the thesis (${res.supporting_evidence.length})`}><div className="space-y-2">{res.supporting_evidence.slice(0, 6).map((f) => <FindingCard key={f.id} f={f} compact />)}</div></Panel>
            </div>
          </div>
          <Panel title="AI challenger" subtitle={res.llm.status}>
            {res.llm.text ? <p className="whitespace-pre-line text-sm leading-relaxed text-fg-2"><CitedText text={res.llm.text} /></p>
              : <p className="text-sm text-fg-3">{res.llm.reason ?? "Not run."} Configure ANTHROPIC_API_KEY or OPENAI_API_KEY to add an agent that searches filings for contradicting passages.</p>}
          </Panel>
        </>
      )}
    </Page>
  );
}
