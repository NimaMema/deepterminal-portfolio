"use client";

import { useState } from "react";
import { LineTrend } from "@/components/charts";
import { Page, PageHeader, useCompanyId } from "@/components/company";
import { ModuleFindings } from "@/components/evidence";
import { LoadingPanel, Notice, Panel, Select, Stat, Unavailable } from "@/components/ui";
import { useModule } from "@/lib/api";
import { date, money, num, price } from "@/lib/format";

interface Sent {
  narrative: { fy: number; filed: string; counts: Record<string, number>; per_10k_words: Record<string, number>; revenue_growth: number | null }[];
  terms: string[]; insiders: { open_market_buy_value: number; open_market_sell_value: number; count: number };
  ownership_filings: { form: string; filed: string; url: string }[];
  multiples_history: { as_of: string; price: number; source: string; ev_revenue: number | null; pe: number | null; basis_period_end: string }[];
  providers: { source: string; status: string; reason: string }[]; decomposition_note: string;
}

export default function Sentiment() {
  const id = useCompanyId();
  const [term, setTerm] = useState("AI / artificial intelligence");
  const m = useModule<Sent>(id, "market_sentiment");
  const d = m.data?.data;
  return (
    <Page>
      <PageHeader title="Market sentiment & hype" description="Narrative versus fundamentals: how often the company's own filings emphasise a theme, compared with what its revenue actually did; plus insider activity and valuation multiples at the prices you record." />
      {m.isLoading && <LoadingPanel rows={8} />}
      {m.error && <Unavailable error={m.error} />}
      {d && (
        <>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Stat label="Insider sells (Form 4)" value={money(d.insiders.open_market_sell_value / 1e6, 1)} />
            <Stat label="Insider buys (Form 4)" value={money(d.insiders.open_market_buy_value / 1e6, 1)} />
            <Stat label="13D/13G filings" value={d.ownership_filings.length} />
            <Stat label="Price observations" value={d.multiples_history.length} sub="entered in Valuation lab" />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Narrative intensity vs revenue growth" subtitle="Mentions per 10,000 words in each 10-K (left) — revenue growth that year (right panel)"
              actions={<Select value={term} onChange={(e) => setTerm(e.target.value)} aria-label="Narrative term">{d.terms.map((t) => <option key={t}>{t}</option>)}</Select>}>
              <LineTrend data={d.narrative.map((n) => ({ fy: `FY${n.fy}`, v: n.per_10k_words[term] }))} x="fy" series={[{ key: "v", label: `“${term}” per 10k words` }]} fmt={(v) => num(v, 1)} />
            </Panel>
            <Panel title="Revenue growth (same years)" subtitle="From XBRL — the operating reality to compare against">
              <LineTrend data={d.narrative.map((n) => ({ fy: `FY${n.fy}`, g: n.revenue_growth }))} x="fy" series={[{ key: "g", label: "Revenue growth" }]} />
            </Panel>
          </div>
          <Panel title="Valuation multiple history" subtitle={d.decomposition_note}>
            {d.multiples_history.length === 0 ? <Notice>Record prices (with date and source) in the Valuation laboratory to track multiple expansion against point-in-time fundamentals.</Notice> : (
              <table className="w-full text-sm"><thead><tr className="text-[11px] uppercase text-fg-3"><th className="text-left">Date</th><th className="text-right">Price</th><th className="text-right">EV/Revenue</th><th className="text-right">P/E</th><th className="text-left pl-4">Fundamentals as of</th><th className="text-left">Source</th></tr></thead>
                <tbody>{d.multiples_history.map((r) => <tr key={r.as_of} className="num border-t border-ink-800"><td>{date(r.as_of)}</td><td className="text-right">{price(r.price)}</td><td className="text-right">{r.ev_revenue ? `${num(r.ev_revenue, 1)}x` : "—"}</td><td className="text-right">{r.pe ? `${num(r.pe, 1)}x` : "n/m"}</td><td className="pl-4">{date(r.basis_period_end)}</td><td className="font-sans text-xs text-fg-3">{r.source}</td></tr>)}</tbody></table>)}
          </Panel>
          <Panel title="External sentiment sources" subtitle="Each requires a permitted, configured provider">
            <ul className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">{d.providers.map((p) => (
              <li key={p.source} className="rounded-lg border border-ink-700 bg-ink-850 p-3 text-xs"><div className="font-medium text-fg">{p.source}</div>
                <div className="uppercase tracking-wider text-fg-3">{p.status.replace(/_/g, " ")}</div><div className="mt-1 text-fg-2">{p.reason}</div></li>))}</ul>
            <p className="mt-3 text-xs text-fg-3">Unusual trading or social activity is never treated as evidence of manipulation on its own.</p>
          </Panel>
        </>
      )}
      <ModuleFindings companyId={id} module="market_sentiment" />
    </Page>
  );
}
