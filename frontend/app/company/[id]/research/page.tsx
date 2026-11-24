"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Page, PageHeader, useCompanyId } from "@/components/company";
import { FindingsList } from "@/components/evidence";
import { JobProgress } from "@/components/jobs";
import { Button, Field, Input, LoadingPanel, Notice, Panel, Unavailable } from "@/components/ui";
import { BackendOnly, useDemo } from "@/lib/demo";
import { api, post } from "@/lib/api";
import { date } from "@/lib/format";
import type { Finding, Job } from "@/lib/types";

interface Mod { key: string; title: string; capability: string }

export default function Research() {
  return <Suspense><ResearchInner /></Suspense>;
}

function ResearchInner() {
  const id = useCompanyId();
  const qc = useQueryClient();
  const isDemo = useDemo();
  const mods = useQuery({ queryKey: ["modules"], queryFn: () => api<Mod[]>("/modules") });
  const jobs = useQuery({ queryKey: ["jobs", id], queryFn: () => api<Job[]>(`/companies/${id}/jobs`) });
  const [sel, setSel] = useState<string[]>([]);
  const [dr, setDr] = useState("");
  const [active, setActive] = useState<string | null>(useSearchParams().get("job"));
  useEffect(() => { if (mods.data && !sel.length) setSel(mods.data.map((m) => m.key)); }, [mods.data, sel.length]);
  useEffect(() => { if (!active && jobs.data?.length) setActive(jobs.data.find((j) => j.kind === "investigation")?.id ?? null); }, [jobs.data, active]);
  const start = useMutation({ mutationFn: () => post<Job>("/jobs", { company_id: id, kind: "investigation", modules: sel, discount_rate: dr ? Number(dr) : null }),
    onSuccess: (j) => { setActive(j.id); qc.invalidateQueries({ queryKey: ["jobs", id] }); } });
  const job = jobs.data?.find((j) => j.id === active);
  const findings = useQuery({ queryKey: ["findings", "job", active], enabled: !!active, queryFn: () => api<Finding[]>(`/jobs/${active}/findings`), refetchInterval: job && ["queued", "running"].includes(job.status) ? 2000 : false });
  const byModule = (findings.data ?? []).reduce<Record<string, Finding[]>>((acc, f) => { (acc[f.module] ??= []).push(f); return acc; }, {});
  return (
    <Page>
      <PageHeader title="Comprehensive investigation" description="Runs the research modules in the background: retrieves filings and financial records, analyses them, and stores evidence-backed findings that populate every dashboard and the report." />
      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <Panel title="Launch">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); start.mutate(); }}>
            <Field label="Discount rate for valuation" hint="Optional. Without it, valuation modules report 'not run' rather than inventing a WACC.">
              <Input value={dr} onChange={(e) => setDr(e.target.value)} placeholder="e.g. 0.09" inputMode="decimal" /></Field>
            <fieldset><legend className="mb-1 text-[11px] font-medium uppercase tracking-wider text-fg-3">Modules</legend>
              {mods.isLoading && <LoadingPanel rows={6} />}
              <div className="space-y-1">{mods.data?.map((m) => (
                <label key={m.key} className="flex items-center gap-2 text-sm text-fg-2"><input type="checkbox" className="accent-[var(--color-accent)]" checked={sel.includes(m.key)}
                  onChange={(e) => setSel(e.target.checked ? [...sel, m.key] : sel.filter((x) => x !== m.key))} />{m.title}</label>))}</div>
            </fieldset>
            <Button type="submit" variant="primary" className="w-full" loading={start.isPending} disabled={!sel.length || isDemo}>Start investigation</Button>
            {isDemo && <p className="text-xs text-fg-3"><BackendOnly /> New investigations retrieve live SEC data. The public demo shows the recorded investigations in History.</p>}
            {start.error && <Unavailable error={start.error} compact />}
          </form>
          <div className="mt-4"><div className="mb-1 text-[11px] uppercase tracking-wider text-fg-3">History</div>
            <ul className="space-y-1 text-xs">{jobs.data?.map((j) => (
              <li key={j.id}><button onClick={() => setActive(j.id)} className={`flex w-full justify-between rounded px-2 py-1 hover:bg-ink-800 ${active === j.id ? "bg-ink-800" : ""}`}>
                <span className="capitalize">{j.kind}</span><span className={j.status === "succeeded" ? "text-good" : j.status === "failed" ? "text-bad" : "text-warn"}>{j.status}</span><span className="text-fg-3">{date(j.created_at)}</span></button></li>))}</ul></div>
        </Panel>
        <div className="min-w-0 space-y-4">
          {!active && <Notice>No investigation yet. Choose modules and start one.</Notice>}
          {active && <Panel title="Progress" subtitle={`Job ${active}`}><JobProgress jobId={active} modules={job?.kind === "investigation" ? mods.data?.filter((m) => job.modules.includes(m.key)) : undefined} /></Panel>}
          {active && findings.data && (
            <Panel title="Findings" subtitle={`${findings.data.length} findings · grouped by module`}>
              {Object.entries(byModule).map(([m, fs]) => (
                <details key={m} open className="mb-3 rounded-lg border border-ink-700 bg-ink-900 p-3">
                  <summary className="cursor-pointer text-sm font-semibold capitalize">{m.replace(/_/g, " ")} <span className="num text-xs text-fg-3">({fs.length})</span></summary>
                  <div className="mt-3"><FindingsList findings={fs} /></div>
                </details>))}
            </Panel>
          )}
        </div>
      </div>
    </Page>
  );
}
