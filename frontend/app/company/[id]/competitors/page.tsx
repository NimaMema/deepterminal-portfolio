"use client";

import { BackendOnly, useDemo } from "@/lib/demo";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Page, PageHeader, useCompanyId } from "@/components/company";
import { ModuleFindings } from "@/components/evidence";
import { MentionsPanel } from "@/components/mentions";
import { DataTable } from "@/components/table";
import { Button, Input, LoadingPanel, Notice, Panel, Select, SyntheticBadge, Unavailable } from "@/components/ui";
import { del, post, useModule } from "@/lib/api";
import { money, pct } from "@/lib/format";

interface M { company_id: number; ticker: string; name: string; fy: number; synthetic: boolean; revenue: number; revenue_growth: number | null; revenue_cagr_3y: number | null;
  gross_margin: number | null; operating_margin: number | null; net_margin: number | null; fcf_margin: number | null; rnd_pct: number | null; sbc_pct: number | null; roe: number | null; net_debt: number; relation?: string; rationale?: string }
const RANK_LABELS: Record<string, string> = { revenue_growth: "Revenue growth", operating_margin: "Operating margin", gross_margin: "Gross margin",
  fcf_margin: "FCF margin", rnd_pct: "R&D intensity", sbc_pct: "SBC intensity", roe: "Return on equity", revenue_cagr_3y: "3-year CAGR" };

interface Comp { subject: M; peers: M[]; ranks: Record<string, { rank: number; of: number }>; errors: { ticker: string; message: string }[]; qualitative: { reason: string } }

const pctCol = (k: keyof M, h: string): ColumnDef<M, unknown> => ({ accessorKey: k, header: h, meta: { right: true }, cell: (c) => pct(c.getValue() as number | null),
  sortingFn: (a, b) => ((a.original[k] as number) ?? -9) - ((b.original[k] as number) ?? -9) });

export default function Competitors() {
  const id = useCompanyId();
  const qc = useQueryClient();
  const isDemo = useDemo();
  const m = useModule<Comp>(id, "competitors");
  const [peer, setPeer] = useState("");
  const [rel, setRel] = useState("direct");
  const [why, setWhy] = useState("");
  const add = useMutation({ mutationFn: () => post(`/companies/${id}/peers`, { peer, relation: rel, rationale: why }),
    onSuccess: () => { setPeer(""); setWhy(""); qc.invalidateQueries({ queryKey: ["module", id, "competitors"] }); } });
  const remove = useMutation({ mutationFn: (pid: number) => del(`/companies/${id}/peers/${pid}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["module", id, "competitors"] }) });
  const d = m.data?.data;
  const rows = d ? [{ ...d.subject, relation: "subject" }, ...d.peers] : [];
  const cols: ColumnDef<M, unknown>[] = [
    { accessorKey: "ticker", header: "Company", cell: (c) => (
      <div><Link href={`/company/${c.row.original.company_id}`} className={`num font-semibold ${c.row.original.relation === "subject" ? "text-accent" : "text-fg"} hover:underline`}>{c.row.original.ticker}</Link>
        <SyntheticBadge show={c.row.original.synthetic && c.row.original.relation === "subject"} />
        <div className="max-w-[220px] truncate text-[11px] text-fg-3">{c.row.original.relation} · {c.row.original.rationale ?? c.row.original.name}</div></div>) },
    { accessorKey: "revenue", header: "Revenue", meta: { right: true }, cell: (c) => money(c.getValue() as number) },
    pctCol("revenue_growth", "Growth 1y"), pctCol("revenue_cagr_3y", "CAGR 3y"), pctCol("gross_margin", "Gross m."), pctCol("operating_margin", "Op. m."),
    pctCol("fcf_margin", "FCF m."), pctCol("rnd_pct", "R&D %"), pctCol("sbc_pct", "SBC %"), pctCol("roe", "ROE"),
    { accessorKey: "net_debt", header: "Net debt", meta: { right: true }, cell: (c) => money(c.getValue() as number) },
    { id: "x", header: "", cell: (c) => c.row.original.relation && !["subject", "candidate"].includes(c.row.original.relation) ? (
      <button onClick={() => remove.mutate(c.row.original.company_id)} aria-label={`Remove ${c.row.original.ticker}`} className="text-fg-3 hover:text-bad"><Trash2 size={14} /></button>) : null },
  ];
  return (
    <Page>
      <PageHeader title="Competitor comparison" description="Side-by-side economics from each company's own SEC filings. Choose direct and indirect competitors with a rationale; same-industry (SIC) companies in the workspace are suggested as candidates." />
      <Panel title="Add a competitor">
        <form className="grid gap-2 md:grid-cols-[160px_140px_1fr_auto]" onSubmit={(e) => { e.preventDefault(); if (peer.trim()) add.mutate(); }}>
          <Input value={peer} onChange={(e) => setPeer(e.target.value)} placeholder="Ticker or CIK" aria-label="Competitor ticker or CIK" />
          <Select value={rel} onChange={(e) => setRel(e.target.value)} aria-label="Relation"><option value="direct">Direct</option><option value="indirect">Indirect</option></Select>
          <Input value={why} onChange={(e) => setWhy(e.target.value)} placeholder="Why is this a competitor? (rationale is stored)" aria-label="Rationale" />
          <Button type="submit" variant="primary" loading={add.isPending} disabled={isDemo}>Add</Button>
          {isDemo && <BackendOnly />}
        </form>
        {add.error && <div className="mt-2"><Unavailable error={add.error} compact /></div>}
      </Panel>
      {m.isLoading && <LoadingPanel rows={6} />}
      {m.error && <Unavailable error={m.error} />}
      {d && (
        <>
          <Panel title="Comparison" subtitle="Latest fiscal year for each company · sortable" dense>
            <DataTable data={rows} columns={cols} caption="Competitor comparison" />
            {d.errors.length > 0 && <div className="p-3"><Notice tone="warn">Could not load: {d.errors.map((e) => `${e.ticker} (${e.message})`).join(", ")}</Notice></div>}
          </Panel>
          {Object.keys(d.ranks).length > 0 && (
            <div className="grid grid-cols-2 gap-2 md:grid-cols-6">{Object.entries(d.ranks).map(([k, r]) => (
              <div key={k} className="rounded-lg border border-ink-700 bg-ink-850 p-3"><div className="text-[11px] uppercase tracking-wider text-fg-3">{RANK_LABELS[k] ?? k.replace(/_/g, " ")}</div>
                <div className="num mt-1 text-lg font-semibold">#{r.rank}<span className="text-sm text-fg-3"> of {r.of}</span></div></div>))}</div>
          )}
          <Notice>{d.qualitative.reason}</Notice>
        </>
      )}
      <MentionsPanel companyId={id} />
      <ModuleFindings companyId={id} module="competitors" />
    </Page>
  );
}
