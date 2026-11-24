"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useState } from "react";
import { LineTrend } from "@/components/charts";
import { Page, PageHeader, useCompany, useCompanyId } from "@/components/company";
import { Cite, ModuleFindings } from "@/components/evidence";
import { MentionsPanel } from "@/components/mentions";
import type { GraphEdge } from "@/components/supplygraph";
import { Button, Field, Input, LoadingPanel, Notice, Panel, Stat, Unavailable } from "@/components/ui";
import { api, post, useModule } from "@/lib/api";
import { date, money, num, pct, signedPct } from "@/lib/format";

const SupplyGraph = dynamic(() => import("@/components/supplygraph").then((m) => m.SupplyGraph), { ssr: false, loading: () => <LoadingPanel rows={8} /> });

interface SC { signals: { signal: string; mentions: number; examples: { text: string; accession: string; filed: string }[] }[]; countries: { country: string; mentions: number }[];
  inventory: { fy: number; inventory: number; dio: number; revenue: number }[]; method: string; not_connected: { source: string; status: string; reason: string }[]; errors: { message: string }[];
  alternatives?: { entity: string; relation: string; single_source: boolean; country: string | null; status: string;
    disclosed_mitigation: { text: string; filed: string }[]; candidates: { entity: string; named_by: string }[] }[] }
interface Shock { base_ev: number; shocked_ev: number; ev_change: number; base_per_share: number; shocked_per_share: number; explanation: string;
  rows: { year: number; revenue_base: number; revenue_shocked: number; fcff_base: number; fcff_shocked: number; margin_base: number; margin_shocked: number }[] }

export default function SupplyChain() {
  const id = useCompanyId();
  const c = useCompany();
  const m = useModule<SC>(id, "supply_chain");
  const graph = useQuery({ queryKey: ["graph", id], queryFn: () => api<{ source: string; edges: GraphEdge[] }>(`/companies/${id}/graph`) });
  const [sel, setSel] = useState<GraphEdge | null>(null);
  const [p, setP] = useState({ discount_rate: "0.09", revenue_shock: "0.15", margin_shock: "0.03", years: "2", price_offset: "0.3" });
  const shock = useMutation({ mutationFn: () => post<Shock>(`/companies/${id}/valuation/shock`, {
    settings: { discount_rate: Number(p.discount_rate) }, revenue_shock: Number(p.revenue_shock), margin_shock: Number(p.margin_shock),
    years: Number(p.years), price_offset: Number(p.price_offset) }) });
  const d = m.data?.data;
  return (
    <Page>
      <PageHeader title="Supply-chain intelligence" description="Suppliers, manufacturers and geographic dependencies extracted from the company's own filings — each relationship links to the sentence it came from — and a disruption model that runs through the valuation engine." />
      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <Panel title="Supplier relationship graph" subtitle={graph.data ? `${graph.data.edges.length} relationships · ${graph.data.source}` : undefined}>
          {graph.isLoading && <LoadingPanel rows={8} />}
          {graph.error && <Unavailable error={graph.error} />}
          {graph.data && graph.data.edges.length === 0 && <Notice>No supplier relationships were found in retrieved filings.</Notice>}
          {graph.data && graph.data.edges.length > 0 && <SupplyGraph center={c.data?.ticker ?? "Company"} edges={graph.data.edges} onSelect={setSel} />}
          <p className="mt-2 text-[11px] text-fg-3">Red animated edges: disclosed sole/single source. Edges are “extracted mentions” — company statements, not independently confirmed relationships.</p>
        </Panel>
        <Panel title={sel ? sel.entity : "Relationship evidence"} subtitle={sel ? `${sel.relation}${sel.country ? ` · ${sel.country}` : ""}` : "Select a node"}>
          {!sel && <p className="text-sm text-fg-3">Select a supplier node to see the passage that establishes the relationship.</p>}
          {sel && (
            <div className="space-y-2 text-sm">
              <blockquote className="border-l-2 border-accent pl-3 text-fg-2">{sel.excerpt}</blockquote>
              <div className="text-xs text-fg-3">Status: {sel.verification_status.replace(/_/g, " ")}</div>
              {sel.evidence_id ? <div className="text-xs">Evidence <Cite id={sel.evidence_id} /></div> : <p className="text-xs text-fg-3">Run an investigation to save this relationship as citable evidence.</p>}
            </div>
          )}
        </Panel>
      </div>
      {m.isLoading && <LoadingPanel rows={6} />}
      {m.error && <Unavailable error={m.error} />}
      {d && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Panel title="Risk signals in disclosures" className="lg:col-span-2">
            {d.signals.length === 0 && <p className="text-sm text-fg-3">No supply-chain risk language detected.</p>}
            <ul className="space-y-2">{d.signals.map((s) => (
              <li key={s.signal} className="rounded-lg border border-ink-700 bg-ink-850 p-3"><div className="flex justify-between text-sm"><span className="font-medium capitalize">{s.signal.replace(/_/g, " ")}</span><span className="num text-fg-3">{s.mentions} passages</span></div>
                <p className="mt-1 text-[13px] text-fg-2">{s.examples[0]?.text}</p><div className="text-[11px] text-fg-3">10-K filed {date(s.examples[0]?.filed)}</div></li>))}</ul>
          </Panel>
          <div className="space-y-4">
            <Panel title="Geography of supply mentions"><ul className="space-y-1 text-sm">{d.countries.map((k) => (
              <li key={k.country} className="flex items-center gap-2"><span className="w-28 truncate">{k.country}</span><span className="h-2 rounded bg-s1" style={{ width: `${Math.min(100, k.mentions * 12)}%` }} aria-hidden /><span className="num ml-auto text-fg-3">{k.mentions}</span></li>))}</ul></Panel>
            <Panel title="Inventory days"><LineTrend data={d.inventory.map((i) => ({ fy: `FY${i.fy}`, dio: i.dio }))} x="fy" series={[{ key: "dio", label: "Days inventory outstanding" }]} fmt={(v) => num(v, 0)} height={150} /></Panel>
          </div>
        </div>
      )}
      {d?.alternatives && d.alternatives.length > 0 && (
        <Panel title="Alternative sourcing" subtitle="Whether the company discloses a second-source effort for each supplier, and counterparties in the same role named by other loaded companies (leads, not verified substitutes)">
          <div className="overflow-x-auto"><table className="w-full text-[13px]">
            <thead><tr className="border-b border-ink-700 text-left text-[11px] uppercase text-fg-3">
              <th scope="col" className="py-2 pr-3">Supplier</th><th scope="col" className="py-2 pr-3">Role</th><th scope="col" className="py-2 pr-3">Status</th>
              <th scope="col" className="py-2 pr-3">Company disclosure</th><th scope="col" className="py-2">Same-role counterparties elsewhere</th></tr></thead>
            <tbody>{d.alternatives.map((a) => (
              <tr key={a.entity} className="border-b border-ink-800 align-top">
                <td className="py-2 pr-3 font-medium">{a.entity}{a.country ? <span className="block text-[11px] font-normal text-fg-3">{a.country}</span> : null}</td>
                <td className="py-2 pr-3 text-fg-2">{a.single_source ? "sole-source " : ""}{a.relation}</td>
                <td className={`py-2 pr-3 ${a.status === "no alternative disclosed" ? "text-bad" : a.status === "mitigation disclosed" ? "text-warn" : "text-fg-3"}`}>{a.status}</td>
                <td className="py-2 pr-3 text-fg-2">{a.disclosed_mitigation.length ? a.disclosed_mitigation.map((m) => m.text).join(" ") : "—"}</td>
                <td className="py-2 text-fg-2">{a.candidates.length ? a.candidates.map((x) => `${x.entity} (${x.named_by})`).join("; ") : "none among loaded companies in the same industry"}</td>
              </tr>))}</tbody>
          </table></div>
        </Panel>
      )}
      <Panel title="Disruption scenario" subtitle="Volume loss can be offset by pricing power — set both from evidence, then see the effect on revenue, free cash flow and value">
        <form className="grid grid-cols-2 gap-3 md:grid-cols-6" onSubmit={(e) => { e.preventDefault(); shock.mutate(); }}>
          <Field label="Discount rate" hint="your WACC"><Input value={p.discount_rate} onChange={(e) => setP({ ...p, discount_rate: e.target.value })} inputMode="decimal" /></Field>
          <Field label="Volume lost" hint="share of revenue"><Input value={p.revenue_shock} onChange={(e) => setP({ ...p, revenue_shock: e.target.value })} inputMode="decimal" /></Field>
          <Field label="Margin hit" hint="pp, e.g. 0.03"><Input value={p.margin_shock} onChange={(e) => setP({ ...p, margin_shock: e.target.value })} inputMode="decimal" /></Field>
          <Field label="Duration (years)"><Input value={p.years} onChange={(e) => setP({ ...p, years: e.target.value })} inputMode="numeric" /></Field>
          <Field label="Price recovery" hint="share of lost revenue"><Input value={p.price_offset} onChange={(e) => setP({ ...p, price_offset: e.target.value })} inputMode="decimal" /></Field>
          <div className="flex items-end"><Button type="submit" variant="primary" loading={shock.isPending} className="w-full">Run scenario</Button></div>
        </form>
        {shock.error && <div className="mt-3"><Unavailable error={shock.error} compact /></div>}
        {shock.data && (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <Stat label="Base EV" value={money(shock.data.base_ev)} /><Stat label="Disrupted EV" value={money(shock.data.shocked_ev)} />
              <Stat label="EV change" value={signedPct(shock.data.ev_change)} tone={shock.data.ev_change < 0 ? "bad" : "good"} />
              <Stat label="Value / share" value={`${num(shock.data.base_per_share, 2)} → ${num(shock.data.shocked_per_share, 2)}`} />
            </div>
            <LineTrend data={shock.data.rows.map((r) => ({ y: `Y${r.year}`, base: r.fcff_base, shock: r.fcff_shocked }))} x="y"
              series={[{ key: "base", label: "FCFF base" }, { key: "shock", label: "FCFF disrupted", dashed: true }]} fmt={(v) => money(v)} />
            <p className="text-xs text-fg-3">{shock.data.explanation} Margin path: {shock.data.rows.slice(0, 3).map((r) => `${pct(r.margin_base)}→${pct(r.margin_shocked)}`).join(", ")}.</p>
          </div>
        )}
      </Panel>
      {d && <Panel title="Not connected"><ul className="space-y-1 text-sm text-fg-2">{d.not_connected.map((n) => <li key={n.source}><b>{n.source}</b>: {n.reason}</li>)}</ul></Panel>}
      <MentionsPanel companyId={id} />
      <ModuleFindings companyId={id} module="supply_chain" />
    </Page>
  );
}
