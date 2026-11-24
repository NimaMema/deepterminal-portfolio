"use client";

import { BackendOnly, useDemo } from "@/lib/demo";
import { useMutation, useQuery } from "@tanstack/react-query";
import * as Tabs from "@radix-ui/react-tabs";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Heatmap, RangeStrip, Tornado } from "@/components/charts";
import { Page, PageHeader, useCompany, useCompanyId } from "@/components/company";
import { AssumptionForm, PriceManager } from "@/components/valform";
import { Button, EpistemicBadge, Input, KV, Notice, Panel, Stat, Unavailable } from "@/components/ui";
import { api, post } from "@/lib/api";
import { date, money, num, pct, price } from "@/lib/format";
import { toPayload, usePrices, useValSettings, useValuation, type ValResult } from "@/lib/valuation";

function ScenarioTable({ r }: { r: ValResult }) {
  const [open, setOpen] = useState<string>("base");
  const sc = r.scenarios.find((s) => s.name === open)!;
  return (
    <div>
      <div className="overflow-x-auto"><table className="w-full text-[13px]"><thead><tr className="border-b border-ink-700 text-[11px] uppercase text-fg-3">
        <th className="px-3 py-2 text-left" scope="col"></th>{r.scenarios.map((s) => <th key={s.name} scope="col" className="px-3 py-2 text-right capitalize">{s.name}</th>)}</tr></thead>
        <tbody>{([
          ["Year-1 → final growth", (s: ValResult["scenarios"][0]) => `${pct(s.dcf.inputs.revenue_growth[0])} → ${pct(s.dcf.inputs.revenue_growth.at(-1))}`],
          ["Operating margin", (s) => pct(s.dcf.inputs.ebit_margin.at(-1))], ["Discount rate", (s) => pct(s.dcf.inputs.discount_rate, 2)],
          ["Terminal growth / ROIC", (s) => `${pct(s.dcf.inputs.terminal_growth)} / ${pct(s.dcf.inputs.terminal_roic)}`],
          ["Final-year revenue", (s) => money(s.dcf.years.at(-1)?.revenue)], ["Cumulative FCFF", (s) => money(s.dcf.years.reduce((a, y) => a + y.fcff, 0))],
          ["Enterprise value", (s) => money(s.dcf.enterprise_value)], ["Terminal share of EV", (s) => pct(s.dcf.terminal_share, 0)],
          ["Equity value", (s) => money(s.equity_value)], ["Value per share", (s) => <b className="text-fg">{price(s.per_share)}</b>],
          ...(r.price ? [["vs. price", (s: ValResult["scenarios"][0]) => pct(s.per_share / r.price!.value - 1)] as const] : []),
        ] as [string, (s: ValResult["scenarios"][0]) => React.ReactNode][]).map(([l, f]) => (
          <tr key={l} className="border-b border-ink-800"><th scope="row" className="px-3 py-1.5 text-left font-normal text-fg-2">{l}</th>{r.scenarios.map((s) => <td key={s.name} className="num px-3 py-1.5 text-right">{f(s)}</td>)}</tr>))}</tbody></table></div>
      <div className="mt-4 flex gap-1" role="tablist" aria-label="Scenario detail">{r.scenarios.map((s) => (
        <button key={s.name} role="tab" aria-selected={open === s.name} onClick={() => setOpen(s.name)} className={`rounded-md px-2.5 py-1 text-xs capitalize ${open === s.name ? "bg-accent/15 text-accent" : "text-fg-3 hover:bg-ink-800"}`}>{s.name} DCF detail</button>))}</div>
      <p className="mt-2 text-sm text-fg-2">{sc.narrative}</p>
      <div className="mt-2 overflow-x-auto"><table className="w-full text-xs"><thead><tr className="text-fg-3"><th className="text-left">Year</th>{["Revenue", "Growth", "EBIT", "Margin", "NOPAT", "Reinvest.", "FCFF", "DF", "PV"].map((h) => <th key={h} className="px-2 text-right">{h}</th>)}</tr></thead>
        <tbody>{sc.dcf.years.map((y) => <tr key={y.year} className="num border-t border-ink-800"><td>Y{y.year}</td><td className="px-2 text-right">{num(y.revenue)}</td><td className="px-2 text-right">{pct(y.growth)}</td>
          <td className="px-2 text-right">{num(y.ebit)}</td><td className="px-2 text-right">{pct(y.ebit_margin)}</td><td className="px-2 text-right">{num(y.nopat)}</td><td className="px-2 text-right">{num(y.reinvestment)}</td>
          <td className="px-2 text-right">{num(y.fcff)}</td><td className="px-2 text-right">{num(y.discount_factor, 3)}</td><td className="px-2 text-right">{num(y.present_value)}</td></tr>)}
          <tr className="num border-t border-ink-600"><td colSpan={7} className="pt-1 text-fg-3">Terminal value {num(sc.dcf.terminal_value)} → PV {num(sc.dcf.pv_terminal)}</td><td colSpan={3} className="pt-1 text-right">EV {num(sc.dcf.enterprise_value)}</td></tr></tbody></table></div>
      {sc.dcf.warnings.map((w) => <p key={w} className="mt-1 text-xs text-warn">⚠ {w}</p>)}
      <p className="mt-2 text-xs text-fg-3">EV → equity: {sc.bridge.map(([k, v]) => `${k} ${v >= 0 ? "+" : "−"}${num(Math.abs(v))}`).join(", ")} → equity {num(sc.equity_value)} ÷ {num(sc.diluted_shares, 1)}m shares.</p>
    </div>
  );
}

function Calculators() {
  const [segs, setSegs] = useState([{ name: "Segment A", enterprise_value: "", method: "EV/EBITDA 9x" }, { name: "Segment B", enterprise_value: "", method: "DCF" }]);
  const [corp, setCorp] = useState({ annual_corporate_cost: "0", tax_rate: "0.21", discount_rate: "0.09", growth: "0.02" });
  const sotp = useMutation({ mutationFn: () => post<{ gross_value: number; capitalised_corporate_costs: number; enterprise_value: number }>("/valuation/sotp", {
    segments: segs.map((s) => ({ ...s, enterprise_value: Number(s.enterprise_value) })), annual_corporate_cost: Number(corp.annual_corporate_cost),
    tax_rate: Number(corp.tax_rate), discount_rate: Number(corp.discount_rate), growth: Number(corp.growth) }) });
  const [assets, setAssets] = useState([{ name: "Cash", book_value: "", recovery_rate: "1", rationale: "cash at face value" }, { name: "Inventory", book_value: "", recovery_rate: "0.6", rationale: "forced-sale haircut" }]);
  const [liab, setLiab] = useState("");
  const nav = useMutation({ mutationFn: () => post<{ adjusted_assets: number; liabilities: number; net_asset_value: number }>("/valuation/nav", {
    assets: assets.map((a) => ({ ...a, book_value: Number(a.book_value), recovery_rate: Number(a.recovery_rate) })), liabilities: Number(liab) }) });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title="Sum-of-the-parts" subtitle="Segment EVs minus capitalised head-office cost">
        {segs.map((s, i) => <div key={i} className="mb-2 grid grid-cols-3 gap-2">
          <Input aria-label="Segment name" value={s.name} onChange={(e) => setSegs(segs.map((x, j) => j === i ? { ...x, name: e.target.value } : x))} />
          <Input aria-label="Segment EV" placeholder="EV (USD m)" value={s.enterprise_value} onChange={(e) => setSegs(segs.map((x, j) => j === i ? { ...x, enterprise_value: e.target.value } : x))} />
          <Input aria-label="Method" value={s.method} onChange={(e) => setSegs(segs.map((x, j) => j === i ? { ...x, method: e.target.value } : x))} /></div>)}
        <div className="grid grid-cols-4 gap-2">{(Object.keys(corp) as (keyof typeof corp)[]).map((k) => <Input key={k} aria-label={k} title={k} value={corp[k]} onChange={(e) => setCorp({ ...corp, [k]: e.target.value })} />)}</div>
        <p className="mt-1 text-[11px] text-fg-3">annual corporate cost · tax rate · discount rate · growth</p>
        <div className="mt-2 flex gap-2"><Button onClick={() => setSegs([...segs, { name: `Segment ${segs.length + 1}`, enterprise_value: "", method: "" }])}>Add segment</Button><Button variant="primary" onClick={() => sotp.mutate()} loading={sotp.isPending}>Calculate</Button></div>
        {sotp.error && <Unavailable error={sotp.error} compact />}
        {sotp.data && <KV items={[["Gross segment value", money(sotp.data.gross_value)], ["Capitalised corporate costs", money(sotp.data.capitalised_corporate_costs)], ["Enterprise value", money(sotp.data.enterprise_value)]]} />}
      </Panel>
      <Panel title="Asset-based (adjusted NAV)" subtitle="Book value × recovery rate − liabilities; each rate needs a rationale">
        {assets.map((a, i) => <div key={i} className="mb-2 grid grid-cols-4 gap-2">{(["name", "book_value", "recovery_rate", "rationale"] as const).map((k) => (
          <Input key={k} aria-label={k} placeholder={k} value={a[k]} onChange={(e) => setAssets(assets.map((x, j) => j === i ? { ...x, [k]: e.target.value } : x))} />))}</div>)}
        <Input aria-label="Total liabilities" placeholder="Total liabilities (USD m)" value={liab} onChange={(e) => setLiab(e.target.value)} />
        <div className="mt-2 flex gap-2"><Button onClick={() => setAssets([...assets, { name: "", book_value: "", recovery_rate: "1", rationale: "" }])}>Add asset</Button><Button variant="primary" onClick={() => nav.mutate()} loading={nav.isPending}>Calculate</Button></div>
        {nav.error && <Unavailable error={nav.error} compact />}
        {nav.data && <KV items={[["Adjusted assets", money(nav.data.adjusted_assets)], ["Liabilities", money(nav.data.liabilities)], ["Net asset value", money(nav.data.net_asset_value)]]} />}
      </Panel>
    </div>
  );
}

export default function ValuationLab() {
  const id = useCompanyId();
  const company = useCompany();
  const [s, update] = useValSettings(id);
  const run = useValuation(id);
  const [label, setLabel] = useState("");
  const isDemo = useDemo();
  const runs = useQuery({ queryKey: ["valruns", id], queryFn: () => api<{ id: number; label: string; created_at: string; base: number | null; verdict: string | null }[]>(`/companies/${id}/valuation/runs`) });
  const r = run.data;
  const base = r?.scenarios.find((x) => x.name === "base");
  const prices = usePrices(id);
  // Public demo: show a result straight away (illustrative, labelled discount rate).
  useEffect(() => { if (isDemo && s.discount_rate && prices.data?.length && !run.data && !run.isPending) run.mutate({ settings: toPayload(s) }); },
    [isDemo, s.discount_rate, prices.data?.length]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Page>
      <PageHeader title="Valuation laboratory" description="Transparent DCF with bear/base/bull scenarios, multiples, sensitivity and margin of safety. Every assumption is visible, editable and carries its rationale; nothing is a hidden default.">
        <Link href={`/company/${id}/reverse-dcf`}><Button>Reverse DCF →</Button></Link>
      </PageHeader>
      <div className="grid gap-4 xl:grid-cols-[330px_1fr]">
        <div className="space-y-4">
          <Panel title="Assumptions"><AssumptionForm s={s} update={update} running={run.isPending} onRun={() => run.mutate({ settings: toPayload(s) })} /></Panel>
          <Panel title="Share price"><PriceManager companyId={id} synthetic={company.data?.synthetic} /></Panel>
        </div>
        <div className="min-w-0 space-y-4">
          {!r && !run.isPending && !run.error && <Notice>Enter your discount rate and run the valuation. Other assumptions default to transparent rules based on the company&apos;s own filings (shown with each result).</Notice>}
          {run.error && <Unavailable error={run.error} />}
          {run.isPending && <Panel><div className="space-y-2" role="status" aria-label="Valuing"><div className="skeleton h-24" /><div className="skeleton h-48" /></div></Panel>}
          {r && base && (
            <Tabs.Root defaultValue="summary">
              <Tabs.List className="mb-3 flex flex-wrap gap-1 border-b border-ink-700 pb-2" aria-label="Valuation views">
                {["summary", "scenarios", "sensitivity", "multiples", "methods", "calculators"].map((t) => (
                  <Tabs.Trigger key={t} value={t} className="rounded-md px-3 py-1.5 text-sm capitalize text-fg-3 data-[state=active]:bg-ink-700 data-[state=active]:text-fg">{t}</Tabs.Trigger>))}
              </Tabs.List>
              <Tabs.Content value="summary" className="space-y-4">
                {r.assessment && (
                  <Panel title="Market expectations vs fundamental value" subtitle={`Basis ${r.basis} · analysis date ${date(r.analysis_date)}`}>
                    <div className="text-lg font-semibold">{r.assessment.verdict}</div>
                    <ul className="mt-1 list-disc pl-5 text-sm text-fg-2">{r.assessment.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
                    <p className="mt-2 text-xs text-fg-3">{r.assessment.caveat}</p>
                  </Panel>
                )}
                {r.scenario_warnings?.map((w) => <Notice key={w} tone="warn">{w}</Notice>)}
                {r.unavailable && <Unavailable error={{ ...r.unavailable, hint: r.price_fetch?.hint ?? r.unavailable.hint }} title="Market comparison unavailable" />}
                {r.price_fetch?.status === "ok" && <p className="text-[11px] text-fg-3">{r.price_fetch.message} {r.price_fetch.attribution}</p>}
                {isDemo && r.price && <p className="text-[11px] text-fg-3">Public demo: valued as of the recorded price&apos;s date ({date(r.price.as_of)}), so the price and the filings it is compared with are contemporaneous. The {pct(Number(s.discount_rate), 0)} discount rate is illustrative; change it and any other assumption on the left.</p>}
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                  <Stat label="Base value / share" value={price(base.per_share)} />
                  <Stat label="Range (bear–bull)" value={`${price(r.scenarios[0].per_share)} – ${price(r.scenarios[2].per_share)}`} />
                  <Stat label="Price" value={r.price ? price(r.price.value) : "—"} sub={r.price ? `${date(r.price.as_of)} · ${r.price.source}` : "none entered"} />
                  <Stat label="Upside to base" value={r.assessment ? pct(r.assessment.upside_to_base) : "—"} tone={r.assessment && r.assessment.upside_to_base < 0 ? "bad" : "good"} />
                </div>
                <Panel title="Intrinsic value range"><RangeStrip bear={r.scenarios[0].per_share} base={base.per_share} bull={r.scenarios[2].per_share} current={r.price?.value} /></Panel>
                <Panel title="Assumptions used" subtitle="Status and rationale for each input">
                  <ul className="space-y-2">{r.assumptions.map((a) => (
                    <li key={a.name} className="grid gap-1 rounded-lg border border-ink-700 bg-ink-850 p-2.5 text-sm md:grid-cols-[180px_90px_1fr]">
                      <span className="font-medium">{a.name.replace(/_/g, " ")}</span><span className="num">{a.unit === "%" ? pct(a.value, 2) : num(a.value, 3)}</span>
                      <span className="text-fg-2"><EpistemicBadge s={a.status} /> {a.rationale}</span></li>))}</ul>
                </Panel>
                <Panel title="Data checks & notes">
                  <ul className="space-y-1 text-xs">{r.validation.map((v) => <li key={v.name}><b className={v.status === "PASS" ? "text-good" : v.status === "WARN" ? "text-warn" : "text-bad"}>{v.status}</b> {v.name}: <span className="text-fg-3">{v.detail}</span></li>)}</ul>
                  <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-fg-3">{r.notes.map((n) => <li key={n}>{n}</li>)}</ul>
                </Panel>
                {isDemo ? <p className="text-xs text-fg-3"><BackendOnly what="Saving runs: full local backend" /> Every calculation above runs live on the demo server; only saving is disabled.</p> :
                <div className="flex flex-wrap items-center gap-2"><Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label this run" aria-label="Run label" className="max-w-xs" />
                  <Button onClick={() => run.mutate({ settings: toPayload(s), save: true, label: label || undefined }, { onSuccess: () => runs.refetch() })}>Save run</Button>
                  {r.run_id && <span className="text-xs text-good">Saved as run #{r.run_id}</span>}</div>}
              </Tabs.Content>
              <Tabs.Content value="scenarios"><Panel title="Bear / base / bull"><ScenarioTable r={r} /></Panel></Tabs.Content>
              <Tabs.Content value="sensitivity" className="space-y-4">
                <Panel title="Value per share: discount rate × terminal growth"><Heatmap {...r.sensitivity} reference={r.price?.value} rowLabel="Discount rate" colLabel="Terminal growth" /></Panel>
                <Panel title="Critical assumptions" subtitle="Each moved alone; bars start at the base value"><Tornado bars={r.tornado} base={base.per_share} /></Panel>
              </Tabs.Content>
              <Tabs.Content value="multiples">
                <Panel title="Multiples at the entered price" subtitle={r.price ? `Market cap ${money(r.market?.market_cap)} · EV ${money(r.market?.enterprise_value)}` : "Enter a price to compute multiples"}>
                  {Object.keys(r.multiples).length === 0 && <p className="text-sm text-fg-3">Requires a price.</p>}
                  <div className="grid grid-cols-2 gap-2 md:grid-cols-3">{Object.values(r.multiples).map((m) => (
                    <Stat key={m.name} label={m.name} value={m.meaningful && m.value !== null ? (m.name.includes("yield") ? pct(m.value) : `${num(m.value, 1)}x`) : "n/m"} sub={m.meaningful ? undefined : m.reason} />))}</div>
                  {r.market && <p className="mt-3 text-xs text-fg-3">Market EV bridge: market cap {money(r.market.market_cap)} {r.market.ledger.map(([k, v]) => `${v >= 0 ? "−" : "+"} ${k} ${money(Math.abs(v))}`).join(" ")} = EV {money(r.market.enterprise_value)}.</p>}
                </Panel>
              </Tabs.Content>
              <Tabs.Content value="methods">
                <Panel title="Method selection" subtitle="Why each valuation method is used, used as a cross-check, or excluded">
                  <ul className="space-y-1.5 text-sm">{r.methods?.map((m) => <li key={m.method + m.role} className="grid grid-cols-[150px_100px_1fr] gap-2"><span className="font-medium">{m.method.replace(/_/g, " ")}</span>
                    <span className={m.role === "excluded" ? "text-fg-3" : m.role === "primary" ? "text-accent" : "text-fg-2"}>{m.role}</span><span className="text-fg-2">{m.reason}</span></li>)}</ul>
                </Panel>
              </Tabs.Content>
              <Tabs.Content value="calculators"><Calculators /></Tabs.Content>
            </Tabs.Root>
          )}
          {!r && <Calculators />}
          <Panel title="Saved runs">
            {runs.data?.length === 0 && <p className="text-sm text-fg-3">No saved runs.</p>}
            <ul className="space-y-1 text-sm">{runs.data?.map((x) => <li key={x.id} className="flex gap-3"><span className="num text-fg-3">#{x.id}</span><span>{x.label ?? "unlabelled"}</span><span className="num">{price(x.base)}</span><span className="text-xs text-fg-3">{x.verdict ?? "no price"}</span><span className="ml-auto text-xs text-fg-3">{date(x.created_at)}</span></li>)}</ul>
          </Panel>
        </div>
      </div>
    </Page>
  );
}
