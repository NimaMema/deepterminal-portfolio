"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Page, PageHeader, useCompanyId } from "@/components/company";
import { RiskDiff, type DiffResult } from "@/components/riskdiff";
import { Input, LoadingPanel, Notice, Panel, Unavailable } from "@/components/ui";
import { api } from "@/lib/api";
import { date, num } from "@/lib/format";

interface TM {
  as_of: string; filing_count: number; filings_known: { accession: string; form: string; filed: string; url: string }[];
  statements: { columns: { label: string }[]; statements: Record<string, { key: string; label: string; cells: ({ value: number } | null)[] }[]> };
  risk_factors: DiffResult | { unavailable: { message: string } } | null;
  events: { accession: string; filed: string; items: { code: string; description: string; significance: string }[] }[];
  later_revisions: { field: string; period_end: string; known_then: number; known_now: number; revised_in: string; revised_filed: string }[];
  next_filings: { accession: string; form: string; filed: string }[];
}

export default function TimeMachine() {
  const id = useCompanyId();
  const [asOf, setAsOf] = useState("2024-06-30");
  const q = useQuery({ queryKey: ["tm", id, asOf], enabled: !!asOf, queryFn: () => api<TM>(`/companies/${id}/time-machine?as_of=${asOf}`) });
  const years = q.data?.statements.columns.length ?? 0;
  return (
    <Page>
      <PageHeader title="SEC filing time machine" description="See exactly what was publicly knowable on a past date — filings, financials, risk disclosures — and what changed afterwards. Nothing filed later leaks into the view.">
        <label className="flex items-center gap-2 text-xs text-fg-3">As of<Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} className="w-44" aria-label="As-of date" /></label>
      </PageHeader>
      <input type="range" min={2016} max={2026} step={0.25} aria-label="Scrub date"
        value={Number(asOf.slice(0, 4)) + (Number(asOf.slice(5, 7)) - 1) / 12}
        onChange={(e) => { const v = Number(e.target.value); const y = Math.floor(v); const m = Math.round((v - y) * 12) + 1; setAsOf(`${y}-${String(m).padStart(2, "0")}-28`); }}
        className="w-full accent-[var(--color-accent)]" />
      {q.isLoading && <LoadingPanel rows={8} />}
      {q.error && <Unavailable error={q.error} />}
      {q.data && (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <Panel title={`Known on ${date(q.data.as_of)}`} subtitle={`${q.data.filing_count} filings public`}>
              <ul className="scroll-thin max-h-72 space-y-1 overflow-y-auto text-sm">{q.data.filings_known.map((f) => (
                <li key={f.accession} className="flex gap-2"><span className="num w-16 shrink-0 whitespace-nowrap font-semibold text-accent">{f.form}</span><span className="text-fg-3">{date(f.filed)}</span></li>))}</ul>
            </Panel>
            <Panel title="Filed afterwards" subtitle="Not knowable on the selected date">
              <ul className="space-y-1 text-sm">{q.data.next_filings.map((f) => (
                <li key={f.accession} className="flex gap-2 opacity-70"><span className="num w-16 shrink-0 whitespace-nowrap font-semibold">{f.form}</span><span className="text-fg-3">{date(f.filed)}</span></li>))}</ul>
            </Panel>
            <Panel title="Later revisions" subtitle="Figures known then vs now">
              {q.data.later_revisions.length === 0 && <p className="text-sm text-fg-3">No later restatement of key figures.</p>}
              <ul className="space-y-1.5 text-xs">{q.data.later_revisions.map((r, i) => (
                <li key={i} className="num"><span className="text-warn">{r.field}</span> {date(r.period_end)}: {num(r.known_then, 1)} → {num(r.known_now, 1)}<div className="text-fg-3">revised in {r.revised_in} ({date(r.revised_filed)})</div></li>))}</ul>
            </Panel>
          </div>
          <Panel title="Financials as knowable then" subtitle="USD millions, point-in-time" dense>
            <div className="overflow-x-auto"><table className="w-full text-[13px]"><thead><tr className="border-b border-ink-700"><th className="px-4 py-2 text-left text-[11px] uppercase text-fg-3">Line</th>
              {q.data.statements.columns.map((c) => <th key={c.label} className="num px-3 py-2 text-right text-[11px] text-fg-3">{c.label}</th>)}</tr></thead>
              <tbody>{["income", "cashflow"].flatMap((s) => q.data.statements.statements[s] ?? []).filter((r) => ["revenue", "operating_income", "net_income", "operating_cash_flow", "fcf"].includes(r.key)).map((r) => (
                <tr key={r.key} className="border-b border-ink-800"><th className="px-4 py-1.5 text-left font-normal text-fg-2">{r.label}</th>
                  {r.cells.slice(-years).map((c, i) => <td key={i} className="num px-3 py-1.5 text-right">{c ? num(c.value, 0) : "—"}</td>)}</tr>))}</tbody></table></div>
          </Panel>
          <Panel title="Risk factors: what changed in the latest 10-K before this date">
            {!q.data.risk_factors && <p className="text-sm text-fg-3">Fewer than two annual reports existed on this date.</p>}
            {q.data.risk_factors && "unavailable" in q.data.risk_factors && <Unavailable error={q.data.risk_factors.unavailable} compact />}
            {q.data.risk_factors && "diff" in q.data.risk_factors && <RiskDiff d={q.data.risk_factors} />}
          </Panel>
          <Panel title="Material events (8-K) up to this date">
            {q.data.events.length === 0 && <Notice>No 8-K filings on record before this date.</Notice>}
            <ul className="space-y-1 text-sm">{q.data.events.map((e) => (
              <li key={e.accession}><span className="num text-fg-3">{date(e.filed)}</span> · {e.items.map((i) => <span key={i.code} className={i.significance === "concern" ? "text-bad" : i.significance === "watch" ? "text-warn" : "text-fg-2"}>{i.code} {i.description}; </span>)}</li>))}</ul>
          </Panel>
        </>
      )}
    </Page>
  );
}
