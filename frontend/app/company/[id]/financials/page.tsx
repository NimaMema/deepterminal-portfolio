"use client";

import * as Popover from "@radix-ui/react-popover";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { Page, PageHeader, useCompanyId } from "@/components/company";
import { Button, Input, LoadingPanel, Notice, Panel, Select, Unavailable } from "@/components/ui";
import { api } from "@/lib/api";
import { date, num } from "@/lib/format";

interface Cell { value: number; concept?: string; accession?: string; form?: string; filed?: string; start?: string | null; end?: string; url?: string; retrieved_at?: string; derived?: string; inputs?: string[] }
interface Row { key: string; label: string; cells: (Cell | null)[] }
interface Statements { columns: { end: string; label: string }[]; statements: Record<string, Row[]>; revisions: { field: string; period_end: string; original: number; revised: number; revised_filed: string; revised_accession: string; kind?: string; split_ratio?: number | null }[]; retrieved_at: string; source_url: string; synthetic: boolean }

const TITLES: Record<string, string> = { income: "Income statement", balance: "Balance sheet", cashflow: "Cash flow statement" };

function CellView({ c, label }: { c: Cell | null; label: string }) {
  if (!c) return <span className="text-fg-3">—</span>;
  return (
    <Popover.Root>
      <Popover.Trigger className="num rounded px-1 hover:bg-ink-700 focus-visible:bg-ink-700" aria-label={`${label}: ${num(c.value, 0)}. Show source`}>
        {num(c.value, c.value !== 0 && Math.abs(c.value) < 10 ? 2 : 0)}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content sideOffset={6} className="z-50 w-80 rounded-lg border border-ink-600 bg-ink-900 p-3 text-xs shadow-2xl">
          <div className="font-semibold text-fg">{label}</div>
          {c.derived ? (
            <p className="mt-1 text-fg-2">Derived: {c.derived}.{c.inputs?.length ? ` Inputs from filings ${c.inputs.join(", ")}.` : ""}</p>
          ) : (
            <dl className="mt-2 grid grid-cols-[90px_1fr] gap-y-1 text-fg-2">
              <dt className="text-fg-3">XBRL concept</dt><dd className="num break-all">{c.concept}</dd>
              <dt className="text-fg-3">Period</dt><dd>{c.start ? `${date(c.start)} – ` : "at "}{date(c.end)}</dd>
              <dt className="text-fg-3">Filing</dt><dd className="num">{c.form} {c.accession}</dd>
              <dt className="text-fg-3">Filed</dt><dd>{date(c.filed)}</dd>
              <dt className="text-fg-3">Retrieved</dt><dd>{c.retrieved_at?.slice(0, 16).replace("T", " ")} UTC</dd>
            </dl>
          )}
          {c.url && <a href={c.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-accent hover:underline">Open filing <ExternalLink size={11} /></a>}
          <Popover.Arrow className="fill-ink-600" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export default function Financials() {
  const id = useCompanyId();
  const [period, setPeriod] = useState("annual");
  const [revision, setRevision] = useState("latest");
  const [asOf, setAsOf] = useState("");
  const q = useQuery({ queryKey: ["statements", id, period, revision, asOf],
    queryFn: () => api<Statements>(`/companies/${id}/statements?period=${period}&revision=${revision}${asOf ? `&as_of=${asOf}` : ""}`) });
  const exportCsv = () => {
    if (!q.data) return;
    const lines = [["statement", "line", ...q.data.columns.map((c) => c.label)].join(",")];
    for (const [s, rows] of Object.entries(q.data.statements))
      for (const r of rows) lines.push([s, `"${r.label}"`, ...r.cells.map((c) => (c ? c.value : ""))].join(","));
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
    const a = document.createElement("a"); a.href = url; a.download = `statements-${id}-${period}.csv`; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <Page>
      <PageHeader title="Financial statements" description="USD millions. Every number is an XBRL fact from a specific SEC filing — select it to see the concept, period, accession, filing and retrieval dates.">
        <Select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Period"><option value="annual">Annual (10-K)</option><option value="quarterly">Quarterly (10-Q, discrete)</option></Select>
        {period === "annual" && <Select value={revision} onChange={(e) => setRevision(e.target.value)} aria-label="Revision"><option value="latest">As latest reported</option><option value="original">As originally reported</option></Select>}
        <Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} aria-label="Point-in-time as of date" className="w-40" />
        <Button onClick={exportCsv} disabled={!q.data}>Export CSV</Button>
      </PageHeader>
      {asOf && <Notice>Point-in-time view: only facts filed on or before {date(asOf)} are shown (no look-ahead).</Notice>}
      {q.isLoading && <Panel><LoadingPanel rows={12} /></Panel>}
      {q.error && <Unavailable error={q.error} />}
      {q.data && Object.entries(q.data.statements).map(([s, rows]) => (
        <Panel key={s} title={TITLES[s]} subtitle={`Source: SEC XBRL companyfacts · retrieved ${date(q.data.retrieved_at)}`} dense>
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead><tr className="border-b border-ink-700"><th scope="col" className="sticky left-0 bg-ink-900 px-4 py-2 text-left text-[11px] font-semibold uppercase tracking-wider text-fg-3">Line item</th>
                {q.data.columns.map((c) => <th key={c.end} scope="col" className="num px-3 py-2 text-right text-[11px] font-semibold text-fg-3">{c.label}</th>)}</tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.key} className={`border-b border-ink-800 hover:bg-ink-850 ${r.key === "fcf" ? "bg-ink-850/60" : ""}`}>
                  <th scope="row" className="sticky left-0 whitespace-nowrap bg-ink-900 px-4 py-1.5 text-left font-normal text-fg-2">{r.label}</th>
                  {r.cells.map((c, i) => <td key={i} className="px-3 py-1.5 text-right"><CellView c={c} label={`${r.label} · ${q.data.columns[i].label}`} /></td>)}
                </tr>))}</tbody>
            </table>
          </div>
        </Panel>
      ))}
      {q.data && q.data.revisions.length > 0 && (
        <Panel title="Restatements and revisions" subtitle="Values that changed between the original and a later filing, newest first. Stock splits and scale re-tagging are labelled; other changes can reflect restatements, reclassifications or discontinued operations">
          <ul className="space-y-1 text-sm">{[...q.data.revisions].sort((a, b) => b.period_end.localeCompare(a.period_end)).slice(0, 30).map((r, i) => (
            <li key={i} className="num text-fg-2">{r.field} · period ending {date(r.period_end)}: {num(r.original, 1)} → {num(r.revised, 1)} (filed {date(r.revised_filed)}, {r.revised_accession})
              {r.kind === "stock_split" && <span className="ml-2 rounded border border-ink-600 px-1 text-[11px] text-fg-3">stock split {r.split_ratio && r.split_ratio >= 1 ? `${r.split_ratio}-for-1` : `1-for-${Math.round(1 / (r.split_ratio ?? 1))}`}, not a restatement</span>}
              {r.kind === "scale_correction" && <span className="ml-2 rounded border border-ink-600 px-1 text-[11px] text-fg-3">re-tagged at a different scale</span>}
            </li>))}</ul>
        </Panel>
      )}
    </Page>
  );
}
