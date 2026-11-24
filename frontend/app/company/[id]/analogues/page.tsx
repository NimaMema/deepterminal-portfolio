"use client";

import { Page, PageHeader, useCompanyId } from "@/components/company";
import { ModuleFindings } from "@/components/evidence";
import { LoadingPanel, Notice, Panel, Unavailable } from "@/components/ui";
import { useModule } from "@/lib/api";
import { date, num, pct } from "@/lib/format";

interface Prof { growth_1y: number; cagr_3y: number; op_margin: number; gross_margin: number; capex_pct: number; rnd_pct: number; log_revenue: number; end: string; revenue: number }
interface Cand { company_id: number; ticker: string; name: string; decision_date: string; profile: Prof; outcome: { revenue_cagr_next_3y: number; margin_change_next_3y: number; class: string; through: string }; distance: number; self: boolean }
interface An { target: Prof | null; selected?: Cand[]; candidates_considered?: number; universe_size?: number; balance?: Record<string, number>; base_rate?: Record<string, number>; selection_criteria?: string; limitations?: string[]; error?: string }

const F: [keyof Prof, string][] = [["growth_1y", "Growth 1y"], ["cagr_3y", "CAGR 3y"], ["op_margin", "Op. margin"], ["gross_margin", "Gross margin"], ["capex_pct", "Capex %"], ["rnd_pct", "R&D %"]];

export default function Analogues() {
  const id = useCompanyId();
  const m = useModule<An>(id, "historical_analogues");
  const d = m.data?.data;
  return (
    <Page>
      <PageHeader title="Historical analogue explorer" description="Companies that looked like this one at past decision dates — using only facts filed by then — and what happened over the next three years. Both successes and failures are always shown." />
      {m.isLoading && <LoadingPanel rows={8} />}
      {m.error && <Unavailable error={m.error} />}
      {d?.error && <Notice tone="warn">{d.error} Open more companies to widen the comparison universe.</Notice>}
      {d?.target && d.selected && (
        <>
          <Panel title="Selection" subtitle={`${d.candidates_considered} point-in-time candidates from ${d.universe_size} companies in this workspace`}>
            <p className="text-sm text-fg-2">{d.selection_criteria}</p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">{Object.entries(d.balance ?? {}).map(([k, v]) => (
              <span key={k} className={`rounded px-2 py-1 ${k === "success" ? "bg-good/10 text-good" : k === "failure" ? "bg-bad/10 text-bad" : "bg-ink-700 text-fg-2"}`}>{k}: {v} selected · base rate {pct(d.base_rate?.[k], 0)}</span>))}</div>
          </Panel>
          <Panel title="Analogues vs today" dense>
            <div className="overflow-x-auto"><table className="w-full text-[13px]"><thead><tr className="border-b border-ink-700 text-[11px] uppercase text-fg-3">
              <th scope="col" className="px-3 py-2 text-left">Company · decision date</th>{F.map(([, l]) => <th key={l} scope="col" className="px-3 py-2 text-right">{l}</th>)}
              <th scope="col" className="px-3 py-2 text-right">Distance</th><th scope="col" className="px-3 py-2 text-right">Next 3y revenue CAGR</th><th scope="col" className="px-3 py-2 text-right">Margin Δ</th><th scope="col" className="px-3 py-2 text-left">Outcome</th></tr></thead>
              <tbody>
                <tr className="border-b border-ink-700 bg-accent/5"><td className="px-3 py-2 font-semibold text-accent">This company · {date(d.target.end)}</td>{F.map(([k]) => <td key={k} className="num px-3 py-2 text-right">{pct(d.target![k] as number)}</td>)}<td colSpan={4} className="px-3 py-2 text-xs text-fg-3">outcome unknown</td></tr>
                {d.selected.map((c, i) => (
                  <tr key={i} className="border-b border-ink-800"><td className="px-3 py-2"><span className="num font-semibold">{c.ticker}</span> <span className="text-fg-3">· {date(c.decision_date)}{c.self ? " (own history)" : ""}</span></td>
                    {F.map(([k]) => <td key={k} className="num px-3 py-2 text-right text-fg-2">{pct(c.profile[k] as number)}</td>)}
                    <td className="num px-3 py-2 text-right">{num(c.distance, 2)}</td><td className="num px-3 py-2 text-right">{pct(c.outcome.revenue_cagr_next_3y)}</td>
                    <td className="num px-3 py-2 text-right">{pct(c.outcome.margin_change_next_3y)}</td>
                    <td className={`px-3 py-2 text-xs font-semibold uppercase ${c.outcome.class === "success" ? "text-good" : c.outcome.class === "failure" ? "text-bad" : "text-fg-2"}`}>{c.outcome.class}</td></tr>))}
              </tbody></table></div>
          </Panel>
          <Panel title="Limitations"><ul className="list-disc space-y-1 pl-5 text-sm text-fg-2">{d.limitations?.map((l) => <li key={l}>{l}</li>)}</ul></Panel>
        </>
      )}
      <ModuleFindings companyId={id} module="historical_analogues" />
    </Page>
  );
}
