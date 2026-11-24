"use client";

import { LineTrend } from "@/components/charts";
import { Page, PageHeader, useCompanyId } from "@/components/company";
import { ModuleFindings } from "@/components/evidence";
import { LoadingPanel, Notice, Panel, SeverityBadge, Unavailable } from "@/components/ui";
import { useModule } from "@/lib/api";
import { money, num, pct } from "@/lib/format";

interface Score { score: number | null; zone: string | null; interpretation: string; components: Record<string, number | null>; missing: string[]; caveats: string[]; fy: number }
interface Row { fy: number; revenue: number; net_income: number; cfo: number; fcf: number; cfo_to_ni: number | null; dso: number | null; dio: number | null; gross_margin: number | null; sbc_pct: number | null; current_ratio: number | null; debt_to_equity: number | null; interest_cover: number | null; share_change: number | null; accruals: number | null }
interface Forensic { rows: Row[]; scores: Record<string, Score>; score_history: { fy: number; beneish: number | null; piotroski: number | null }[]; anomalies: { fy: number; code: string; severity: string; detail: string }[]; disclaimer: string }

const ZONE: Record<string, string> = { elevated: "concern", distress: "concern", grey: "watch", weak: "watch", moderate: "neutral", strong: "positive", safe: "positive", "not elevated": "positive" };

export default function Forensics() {
  const id = useCompanyId();
  const m = useModule<Forensic>(id, "forensic_accounting");
  const d = m.data?.data;
  const metrics: [keyof Row, string, (v: number | null) => string][] = [
    ["cfo_to_ni", "CFO / net income", (v) => (v === null ? "—" : `${num(v, 2)}x`)], ["accruals", "Accruals ratio (Sloan)", (v) => pct(v)],
    ["dso", "Days sales outstanding", (v) => num(v, 0)], ["dio", "Days inventory", (v) => num(v, 0)], ["gross_margin", "Gross margin", (v) => pct(v)],
    ["sbc_pct", "SBC % revenue", (v) => pct(v)], ["share_change", "Diluted share change", (v) => pct(v)], ["current_ratio", "Current ratio", (v) => (v === null ? "—" : `${num(v, 2)}`)],
    ["debt_to_equity", "Debt / equity", (v) => (v === null ? "—" : `${num(v, 2)}`)], ["interest_cover", "Interest cover", (v) => (v === null ? "—" : `${num(v, 1)}x`)],
    ["fcf", "Free cash flow", (v) => money(v)],
  ];
  return (
    <Page>
      <PageHeader title="Forensic accounting" description="Earnings quality, working capital, dilution, liquidity and academic screening scores, computed from reported XBRL values with nothing imputed." />
      {d && <Notice tone="warn">{d.disclaimer}</Notice>}
      {m.isLoading && <LoadingPanel rows={8} />}
      {m.error && <Unavailable error={m.error} />}
      {d && (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            {Object.entries(d.scores).map(([name, s]) => (
              <Panel key={name} title={name} subtitle={`FY${s.fy}`}>
                <div className="flex items-baseline gap-3"><span className="num text-3xl font-semibold">{s.score === null ? "n/a" : num(s.score, 2)}</span>{s.zone && <SeverityBadge s={ZONE[s.zone] ?? "neutral"} />}</div>
                <p className="mt-1 text-sm text-fg-2">{s.interpretation}</p>
                <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">{Object.entries(s.components).map(([k, v]) => (
                  <div key={k} className="contents"><dt className="text-fg-3">{k.replace(/_/g, " ")}</dt><dd className={`num text-right ${v === null ? "text-fg-3" : ""}`}>{v === null ? "missing" : num(v, 3)}</dd></div>))}</dl>
                {s.caveats.map((c) => <p key={c} className="mt-2 text-[11px] text-fg-3">{c}</p>)}
              </Panel>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Beneish M-Score history" subtitle="Dashed line: −1.78 screening threshold">
              <LineTrend data={d.score_history.map((h) => ({ fy: `FY${h.fy}`, m: h.beneish }))} x="fy" series={[{ key: "m", label: "M-Score" }]} fmt={(v) => num(v, 2)} refY={{ y: -1.78, label: "−1.78" }} />
            </Panel>
            <Panel title="Earnings quality" subtitle="Cash conversion and accruals">
              <LineTrend data={d.rows.map((r) => ({ fy: `FY${r.fy}`, accruals: r.accruals, cfo: r.cfo_to_ni }))} x="fy" series={[{ key: "accruals", label: "Accruals ratio" }]} />
            </Panel>
          </div>
          <Panel title="Forensic metrics by year" dense>
            <div className="overflow-x-auto"><table className="w-full text-[13px]"><thead><tr className="border-b border-ink-700"><th scope="col" className="px-4 py-2 text-left text-[11px] uppercase text-fg-3">Metric</th>
              {d.rows.map((r) => <th key={r.fy} scope="col" className="num px-3 py-2 text-right text-[11px] text-fg-3">FY{r.fy}</th>)}</tr></thead>
              <tbody>{metrics.map(([k, label, f]) => <tr key={k} className="border-b border-ink-800"><th scope="row" className="px-4 py-1.5 text-left font-normal text-fg-2">{label}</th>
                {d.rows.map((r) => <td key={r.fy} className="num px-3 py-1.5 text-right">{f(r[k] as number | null)}</td>)}</tr>)}</tbody></table></div>
          </Panel>
          <Panel title="Anomalies" subtitle="Rule-based screens — each links to a reason, not a verdict">
            {d.anomalies.length === 0 && <p className="text-sm text-fg-3">No anomalies triggered.</p>}
            <ul className="grid gap-2 md:grid-cols-2">{d.anomalies.map((a, i) => (
              <li key={i} className="flex items-start gap-2 rounded-lg border border-ink-700 bg-ink-850 p-3 text-sm"><SeverityBadge s={a.severity} />
                <div><div className="num text-xs text-fg-3">FY{a.fy} · {a.code}</div><div className="text-fg-2">{a.detail}</div></div></li>))}</ul>
          </Panel>
        </>
      )}
      <ModuleFindings companyId={id} module="forensic_accounting" />
    </Page>
  );
}
