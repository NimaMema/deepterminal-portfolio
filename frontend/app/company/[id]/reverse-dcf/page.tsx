"use client";

import { useEffect } from "react";
import { LineTrend, Tornado } from "@/components/charts";
import { Page, PageHeader, useCompany, useCompanyId } from "@/components/company";
import { AssumptionForm, PriceManager } from "@/components/valform";
import { LoadingPanel, Notice, Panel, Stat, Unavailable } from "@/components/ui";
import { money, num, pct, price } from "@/lib/format";
import { toPayload, useValSettings, useValuation } from "@/lib/valuation";

export default function ReverseDCF() {
  const id = useCompanyId();
  const c = useCompany();
  const [s, update] = useValSettings(id);
  const run = useValuation(id);
  const r = run.data;
  const hist = c.data?.metrics?.history ?? [];
  // Auto-run once when a discount rate and a price are available; later runs are explicit.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (s.discount_rate && c.data?.price && !run.data && !run.isPending) run.mutate({ settings: toPayload(s) }); }, [s.discount_rate, c.data?.price]);
  const growth = r?.reverse_dcf.find((x) => x.lever === "initial_growth_fading");
  const base = r?.scenarios.find((x) => x.name === "base");
  return (
    <Page>
      <PageHeader title="Reverse DCF — market expectations" description="Instead of asking what the company is worth, ask what must happen for today's price to make sense. Each answer solves one assumption with all others held fixed — it is one point in a family of possibilities, not a unique forecast." />
      <div className="grid gap-4 xl:grid-cols-[330px_1fr]">
        <div className="space-y-4">
          <Panel title="Assumptions held fixed"><AssumptionForm s={s} update={update} running={run.isPending} onRun={() => run.mutate({ settings: toPayload(s) })} /></Panel>
          <Panel title="Share price"><PriceManager companyId={id} synthetic={c.data?.synthetic} /></Panel>
        </div>
        <div className="min-w-0 space-y-4">
          {run.isPending && <LoadingPanel rows={8} label="Solving implied expectations" />}
          {run.error && <Unavailable error={run.error} />}
          {!r && !run.isPending && <Notice>Enter a discount rate and a dated price, then run. The engine solves for growth, margin and implied return separately and reports every assumption it held constant.</Notice>}
          {r && r.reverse_dcf.length === 0 && <Unavailable error={r.unavailable ? { ...r.unavailable, hint: r.price_fetch?.hint ?? r.unavailable.hint } : { status: "no_price", message: "A timestamped price is required." }} title="Market expectations need a price" />}
          {r && r.reverse_dcf.length > 0 && (
            <>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                <Stat label="Market cap" value={money(r.market?.market_cap)} sub={`${price(r.price?.value)} × ${num(r.market?.diluted_shares, 1)}m sh`} />
                <Stat label="Market EV to explain" value={money(r.market?.enterprise_value)} />
                <Stat label="Implied year-1 growth" value={growth?.solutions[0] ? pct(growth.solutions[0].value) : "none"} sub="fading to terminal" />
                <Stat label="Years of growth needed" value={r.growth_duration?.years_required ?? `>${r.growth_duration?.max_years_tested}`} sub={r.growth_duration ? `at ${pct(r.growth_duration.growth_rate)}` : undefined} />
              </div>
              <div className="grid gap-4 lg:grid-cols-3">
                {r.reverse_dcf.map((x) => (
                  <Panel key={x.lever} title={x.label} subtitle={x.status === "unique" ? "unique solution" : x.status === "multiple" ? "multiple solutions" : "no solution in bounds"}>
                    <div className="num text-2xl font-semibold">{x.solutions.length ? x.solutions.map((p) => (x.unit === "%" ? pct(p.value) : num(p.value, 2))).join(" / ") : "—"}</div>
                    {x.solutions[0] && <p className="mt-1 text-xs text-fg-3">Implies year-{x.solutions[0].revenue_path.length} revenue {money(x.solutions[0].final_revenue)} (CAGR {pct(x.solutions[0].revenue_cagr)}), cumulative FCFF {money(x.solutions[0].cumulative_fcff)}.</p>}
                    {x.notes.map((n) => <p key={n} className="mt-1 text-xs text-warn">{n}</p>)}
                    <details className="mt-2 text-xs text-fg-3"><summary className="cursor-pointer">Held constant</summary><ul className="mt-1 space-y-0.5">{Object.entries(x.held_constant).map(([k, v]) => <li key={k}><span className="text-fg-2">{k}</span>: {v}</li>)}</ul></details>
                  </Panel>))}
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <Panel title="Iso-value curve" subtitle="Every margin/growth pair that justifies today's price — the honest answer when both are unknown">
                  <LineTrend data={(r.iso_value ?? []).filter((p) => p.growth.length).map((p) => ({ m: pct(p.margin, 0), g: p.growth[0] }))} x="m" series={[{ key: "g", label: "Required year-1 growth" }]} />
                  <p className="mt-1 text-[11px] text-fg-3">x-axis: steady-state operating margin. Higher margins need less growth.</p>
                </Panel>
                <Panel title="Implied revenue vs history" subtitle="Reported revenue then the growth path the price implies">
                  <LineTrend data={[...hist.map((h) => ({ t: `FY${h.fy}`, actual: h.revenue, implied: null as number | null })),
                    ...(growth?.solutions[0]?.revenue_path ?? []).map((v, i) => ({ t: `Y+${i + 1}`, actual: null as number | null, implied: v }))]}
                    x="t" series={[{ key: "actual", label: "Reported" }, { key: "implied", label: "Market-implied", dashed: true }]} fmt={(v) => money(v)} />
                </Panel>
              </div>
              <Panel title="Expectations gap" subtitle="Market-implied versus the company's record and peers">
                <table className="w-full text-sm"><thead><tr className="text-[11px] uppercase text-fg-3"><th className="text-left">Metric</th><th className="text-right">Implied</th><th className="text-right">Co. median</th><th className="text-right">Co. best</th><th className="text-right">Peer median</th><th className="text-right">Peer best</th></tr></thead>
                  <tbody>{r.expectations_gap.map((g) => <tr key={g.metric} className="num border-t border-ink-800"><td className="font-sans">{g.metric}</td><td className="text-right font-semibold">{pct(g.market_implied)}</td><td className="text-right">{pct(g.company_median)}</td><td className="text-right">{pct(g.company_max)}</td><td className="text-right">{pct(g.peer_median)}</td><td className="text-right">{pct(g.peer_max)}</td></tr>)}</tbody></table>
                <ul className="mt-2 list-disc pl-5 text-sm text-fg-2">{r.expectations_gap.flatMap((g) => g.observations).map((o) => <li key={o}>{o}</li>)}</ul>
              </Panel>
              {base && <Panel title="What could change expectations" subtitle="Assumptions ranked by how much value moves when each changes"><Tornado bars={r.tornado} base={base.per_share} /></Panel>}
              {r.assessment && (
                <Panel title="Misvaluation investigation (13 steps)" subtitle={r.assessment.verdict}>
                  <ol className="space-y-1.5 text-sm">{r.assessment.steps.map((st) => (
                    <li key={st.number} className="grid grid-cols-[24px_1fr] gap-2"><span className={st.performed ? "text-good" : "text-fg-3"}>{st.performed ? "✓" : "○"}</span>
                      <div><span className="font-medium">{st.number}. {st.title}</span><div className="text-xs text-fg-3">{st.detail}</div></div></li>))}</ol>
                  <p className="mt-2 text-xs text-fg-3">{r.assessment.caveat}</p>
                </Panel>
              )}
            </>
          )}
        </div>
      </div>
    </Page>
  );
}
