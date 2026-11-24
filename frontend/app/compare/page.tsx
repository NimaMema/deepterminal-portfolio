"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { BarTrend } from "@/components/charts";
import { Page, PageHeader } from "@/components/company";
import { LoadingPanel, Notice, Panel, Unavailable } from "@/components/ui";
import { api } from "@/lib/api";
import { money, pct } from "@/lib/format";
import type { Company } from "@/lib/types";

interface M { company_id: number; ticker: string; name: string; fy: number; revenue: number; revenue_growth: number | null; revenue_cagr_3y: number | null; gross_margin: number | null;
  operating_margin: number | null; fcf_margin: number | null; rnd_pct: number | null; sbc_pct: number | null; roe: number | null; net_debt: number }

const ROWS: [keyof M, string, (v: number | null) => string][] = [["fy", "Fiscal year", (v) => String(v)], ["revenue", "Revenue", (v) => money(v)], ["revenue_growth", "Growth 1y", pct], ["revenue_cagr_3y", "CAGR 3y", pct],
  ["gross_margin", "Gross margin", pct], ["operating_margin", "Operating margin", pct], ["fcf_margin", "FCF margin", pct], ["rnd_pct", "R&D % revenue", pct], ["sbc_pct", "SBC % revenue", pct], ["roe", "ROE", pct], ["net_debt", "Net debt", (v) => money(v)]];

export default function Compare() {
  const companies = useQuery({ queryKey: ["companies"], queryFn: () => api<Company[]>("/companies") });
  const [sel, setSel] = useState<number[]>([]);
  // Selection lives in the URL (?ids=1,2,3) so comparisons can be linked and bookmarked.
  const ready = useRef(false);
  useEffect(() => {
    const ids = new URLSearchParams(window.location.search).get("ids");
    if (ids) setSel(ids.split(",").map(Number).filter((n) => Number.isInteger(n) && n > 0).slice(0, 6));
    ready.current = true;
  }, []);
  useEffect(() => {
    if (!ready.current) return;
    const url = sel.length ? `?ids=${sel.join(",")}` : window.location.pathname;
    window.history.replaceState(null, "", url);
  }, [sel]);
  const cmp = useQuery({ queryKey: ["compare", sel], enabled: sel.length > 0, queryFn: () => api<{ companies: M[]; errors: { ticker: string; message: string }[] }>(`/compare?ids=${sel.join(",")}`) });
  return (
    <Page>
      <PageHeader title="Compare companies" description="Pick up to six loaded companies. Figures are each company's latest fiscal year from its own SEC filings." />
      <Panel title="Companies">
        {companies.isLoading && <LoadingPanel rows={2} />}
        {companies.data?.length === 0 && <Notice>Open companies from the terminal first.</Notice>}
        <div className="flex flex-wrap gap-2">{companies.data?.map((c) => {
          const on = sel.includes(c.id);
          return <button key={c.id} aria-pressed={on} onClick={() => setSel(on ? sel.filter((x) => x !== c.id) : sel.length < 6 ? [...sel, c.id] : sel)}
            className={`rounded-md border px-2.5 py-1 text-sm ${on ? "border-accent bg-accent/10 text-accent" : "border-ink-600 text-fg-2 hover:bg-ink-800"}`}><span className="num font-semibold">{c.ticker}</span></button>;
        })}</div>
      </Panel>
      {cmp.error && <Unavailable error={cmp.error} />}
      {cmp.data && cmp.data.companies.length > 0 && (
        <>
          <Panel title="Side by side" dense>
            <div className="overflow-x-auto"><table className="w-full text-[13px]"><thead><tr className="border-b border-ink-700"><th scope="col" className="px-4 py-2 text-left text-[11px] uppercase text-fg-3">Metric</th>
              {cmp.data.companies.map((c) => <th key={c.company_id} scope="col" className="px-3 py-2 text-right"><Link href={`/company/${c.company_id}`} className="num text-accent hover:underline">{c.ticker}</Link></th>)}</tr></thead>
              <tbody>{ROWS.map(([k, l, f]) => <tr key={k} className="border-b border-ink-800"><th scope="row" className="px-4 py-1.5 text-left font-normal text-fg-2">{l}</th>
                {cmp.data!.companies.map((c) => <td key={c.company_id} className="num px-3 py-1.5 text-right">{f(c[k] as number | null)}</td>)}</tr>)}</tbody></table></div>
          </Panel>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Operating margin"><BarTrend data={cmp.data.companies.map((c) => ({ t: c.ticker, v: c.operating_margin ?? 0 }))} x="t" y="v" label="Operating margin" fmt={(v) => pct(v)} highlightNegative /></Panel>
            <Panel title="Revenue growth (1y)"><BarTrend data={cmp.data.companies.map((c) => ({ t: c.ticker, v: c.revenue_growth ?? 0 }))} x="t" y="v" label="Revenue growth" fmt={(v) => pct(v)} highlightNegative /></Panel>
          </div>
        </>
      )}
    </Page>
  );
}
