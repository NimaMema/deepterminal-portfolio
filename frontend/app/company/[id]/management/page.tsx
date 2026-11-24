"use client";

import type { ColumnDef } from "@tanstack/react-table";
import { BarTrend } from "@/components/charts";
import { Page, PageHeader, useCompanyId } from "@/components/company";
import { ModuleFindings } from "@/components/evidence";
import { DataTable } from "@/components/table";
import { LoadingPanel, Notice, Panel, Stat, Unavailable } from "@/components/ui";
import { useModule } from "@/lib/api";
import { date, money, num } from "@/lib/format";

interface Tx { owner: string; role: string; date: string; code: string; code_description: string; shares: number; price: number; value: number; accession: string; filed: string; url: string }
interface Mgmt {
  executives: { name: string; latest_total: number | null; position: string | null; history: { year: string; salary: number | null; total: number | null; filed: string }[] }[];
  governance_statements: { text: string }[]; insiders: { transactions: Tx[]; open_market_buy_value: number; open_market_sell_value: number; note: string; errors: { message: string }[] };
  officer_changes: { accession: string; filed: string }[];
  capital_allocation: { fy: number; fcf: number | null; dividends: number | null; buybacks: number | null; acquisitions: number | null; sbc: number | null; rnd: number | null; shares: number | null }[];
  not_connected: { check: string; reason: string }[];
}

const txCols: ColumnDef<Tx, unknown>[] = [
  { accessorKey: "date", header: "Date", cell: (c) => <span className="num">{date(c.getValue() as string)}</span> },
  { accessorKey: "owner", header: "Insider" }, { accessorKey: "role", header: "Role", cell: (c) => <span className="text-fg-3">{c.getValue() as string}</span> },
  { accessorKey: "code_description", header: "Transaction", cell: (c) => <span className={c.row.original.code === "S" ? "text-bad" : c.row.original.code === "P" ? "text-good" : ""}>{c.getValue() as string}</span> },
  { accessorKey: "shares", header: "Shares", meta: { right: true }, cell: (c) => num(c.getValue() as number) },
  { accessorKey: "price", header: "Price", meta: { right: true }, cell: (c) => `$${num(c.getValue() as number, 2)}` },
  { accessorKey: "value", header: "Value", meta: { right: true }, cell: (c) => money((c.getValue() as number) / 1e6, 1) },
  { accessorKey: "accession", header: "Form 4", cell: (c) => <a className="num text-xs text-accent hover:underline" href={c.row.original.url} target="_blank" rel="noopener noreferrer">{c.getValue() as string}</a> },
];

export default function Management() {
  const id = useCompanyId();
  const m = useModule<Mgmt>(id, "management_governance");
  const d = m.data?.data;
  return (
    <Page>
      <PageHeader title="Management intelligence" description="Executives and pay from proxy statements, insider trading from Form 4, leadership changes from 8-K, and capital allocation from cash-flow statements. Biographical claims are company statements, not verified facts." />
      {m.isLoading && <LoadingPanel rows={8} />}
      {m.error && <Unavailable error={m.error} />}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Stat label="Insider open-market buys" value={money(d.insiders.open_market_buy_value / 1e6, 1)} tone="good" />
            <Stat label="Insider open-market sells" value={money(d.insiders.open_market_sell_value / 1e6, 1)} tone={d.insiders.open_market_sell_value > 0 ? "bad" : undefined} />
            <Stat label="Officer/director changes" value={d.officer_changes.length} sub="8-K Item 5.02" />
            <Stat label="Named executives" value={d.executives.length} sub="latest proxy" />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Executive compensation" subtitle="Summary Compensation Table (parsed from DEF 14A — verify against source)">
              {d.executives.length === 0 && <p className="text-sm text-fg-3">No compensation table could be parsed from recent proxies.</p>}
              <ul className="space-y-2">{d.executives.map((e) => (
                <li key={e.name} className="rounded-lg border border-ink-700 bg-ink-850 p-3"><div className="flex justify-between gap-2"><span className="font-medium">{e.name}</span><span className="num">{money((e.latest_total ?? 0) / 1e6, 1)}</span></div>
                  <div className="text-xs text-fg-3">{e.position ?? "position not parsed"}</div>
                  <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-fg-3">{e.history.map((h, i) => <span key={i} className="num">{h.year}: {money((h.total ?? 0) / 1e6, 1)}</span>)}</div></li>))}</ul>
              {d.governance_statements.map((g, i) => <p key={i} className="mt-2 text-xs text-fg-2">Governance: {g.text}</p>)}
            </Panel>
            <Panel title="Capital allocation" subtitle="Where free cash flow went (USD m)">
              <BarTrend data={d.capital_allocation.map((a) => ({ fy: `FY${a.fy}`, returned: (a.dividends ?? 0) + (a.buybacks ?? 0) }))} x="fy" y="returned" label="Dividends + buybacks" fmt={(v) => money(v)} height={170} />
              <table className="mt-2 w-full text-xs"><thead><tr className="text-fg-3"><th className="text-left">FY</th><th className="text-right">FCF</th><th className="text-right">Div.</th><th className="text-right">Buyback</th><th className="text-right">M&amp;A</th><th className="text-right">SBC</th></tr></thead>
                <tbody>{d.capital_allocation.map((a) => <tr key={a.fy} className="num border-t border-ink-800"><td>{a.fy}</td><td className="text-right">{money(a.fcf)}</td><td className="text-right">{money(a.dividends)}</td><td className="text-right">{money(a.buybacks)}</td><td className="text-right">{money(a.acquisitions)}</td><td className="text-right">{money(a.sbc)}</td></tr>)}</tbody></table>
            </Panel>
          </div>
          <Panel title="Insider transactions" subtitle={d.insiders.note} dense>
            {d.insiders.errors.length > 0 && <div className="p-3"><Notice tone="warn">{d.insiders.errors.length} Form 4 filing(s) could not be retrieved: {d.insiders.errors[0].message}</Notice></div>}
            <DataTable data={d.insiders.transactions} columns={txCols} empty="No Form 4 transactions retrieved." caption="Insider transactions" />
          </Panel>
          {d.not_connected.map((n) => <Notice key={n.check}>{n.check}: {n.reason}</Notice>)}
        </>
      )}
      <ModuleFindings companyId={id} module="management_governance" />
    </Page>
  );
}
