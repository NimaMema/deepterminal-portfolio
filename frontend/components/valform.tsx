"use client";

import { BackendOnly, useDemo } from "@/lib/demo";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { api, del, post } from "@/lib/api";
import { date, price } from "@/lib/format";
import { usePrices, type ValSettings } from "@/lib/valuation";
import { Button, Field, Input, Notice, Select, Unavailable } from "./ui";

export function PriceManager({ companyId, synthetic }: { companyId: number; synthetic?: boolean }) {
  const qc = useQueryClient();
  const prices = usePrices(companyId);
  const isDemo = useDemo();
  const fetchClose = useMutation({
    mutationFn: () => post<{ latest: { as_of: string; close: number }; stored: number; attribution: string; from_cache: boolean | null; provider: string; errors?: string[] }>(`/companies/${companyId}/prices/fetch`, {}),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["prices", companyId] }); qc.invalidateQueries({ queryKey: ["company", companyId] }); } });
  const [p, setP] = useState({ value: "", as_of: new Date().toISOString().slice(0, 10), source: "", url: "" });
  const add = useMutation({ mutationFn: () => post(`/companies/${companyId}/prices`, { value: Number(p.value), as_of: p.as_of, source: p.source, url: p.url || null }),
    onSuccess: () => { setP({ ...p, value: "", source: "", url: "" }); qc.invalidateQueries({ queryKey: ["prices", companyId] }); qc.invalidateQueries({ queryKey: ["company", companyId] }); } });
  const remove = useMutation({ mutationFn: (id: number) => del(`/companies/${companyId}/prices/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["prices", companyId] }) });
  if (isDemo) return (
    <div className="space-y-2">
      <Notice>Public demo: prices are the recorded SEC Form 4 insider trade prices in the snapshot (real dated trades,
        not official closes). <BackendOnly what="Fetching or entering prices: full local backend" /></Notice>
      <ul className="space-y-1 text-xs">{prices.data?.map((q, i) => (
        <li key={q.id} className={`flex items-center gap-2 rounded px-2 py-1 ${i === 0 ? "bg-accent/5" : ""}`}><span className="num font-semibold">{price(q.value)}</span>
          <span className="text-fg-3">{date(q.as_of)} · {q.source}</span>{i === 0 && <span className="text-accent">in use</span>}</li>))}</ul>
    </div>
  );
  return (
    <div className="space-y-3">
      {synthetic ? (
        <Notice>Demo companies are fictional, so there is no market price. Enter a labelled demo price to explore the tools.</Notice>
      ) : (
        <div className="space-y-1.5">
          <Button onClick={() => fetchClose.mutate()} loading={fetchClose.isPending} className="w-full">Fetch latest price (free sources)</Button>
          {fetchClose.data && <p className="text-[11px] text-fg-3">{fetchClose.data.provider === "sec_form4" ? "Insider trade price" : "Close"} {price(fetchClose.data.latest.close)} on {date(fetchClose.data.latest.as_of)}
            {fetchClose.data.stored > 1 ? ` · ${fetchClose.data.stored - 1} fiscal-year-end closes saved for multiple history` : ""}. {fetchClose.data.attribution}{fetchClose.data.errors?.length ? ` Tried first: ${fetchClose.data.errors.join(" ")}` : ""}</p>}
          {fetchClose.error && <Unavailable error={fetchClose.error} compact />}
          <p className="text-[11px] text-fg-3">Or enter a price you observed, with its date and source (labelled “user-supplied”).</p>
        </div>
      )}
      <form className="grid grid-cols-2 gap-2" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Price (USD)"><Input required inputMode="decimal" value={p.value} onChange={(e) => setP({ ...p, value: e.target.value })} /></Field>
        <Field label="As of"><Input required type="date" value={p.as_of} onChange={(e) => setP({ ...p, as_of: e.target.value })} /></Field>
        <div className="col-span-2"><Field label="Source"><Input required minLength={3} placeholder="e.g. Nasdaq official close" value={p.source} onChange={(e) => setP({ ...p, source: e.target.value })} /></Field></div>
        <div className="col-span-2"><Field label="Source URL (optional)"><Input value={p.url} onChange={(e) => setP({ ...p, url: e.target.value })} /></Field></div>
        <Button type="submit" variant="primary" loading={add.isPending} className="col-span-2">Save price</Button>
      </form>
      {add.error && <Unavailable error={add.error} compact />}
      <ul className="space-y-1 text-xs">{prices.data?.map((q, i) => (
        <li key={q.id} className={`flex items-center gap-2 rounded px-2 py-1 ${i === 0 ? "bg-accent/5" : ""}`}><span className="num font-semibold">{price(q.value)}</span>
          <span className="text-fg-3">{date(q.as_of)} · {q.source}</span>{i === 0 && <span className="text-accent">in use</span>}
          <button className="ml-auto text-fg-3 hover:text-bad" onClick={() => remove.mutate(q.id)} aria-label="Delete price"><Trash2 size={12} /></button></li>))}</ul>
    </div>
  );
}

const FIELDS: [keyof ValSettings, string, string][] = [
  ["terminal_growth", "Terminal growth", "decimal, e.g. 0.025"], ["terminal_roic", "Terminal ROIC", "blank = discount rate"],
  ["base_growth", "Year-1 growth", "blank = 3y historical CAGR"], ["base_margin", "Operating margin", "blank = latest margin"],
  ["tax_rate", "Tax rate", "blank = median effective"], ["net_capex_pct_revenue", "Net capex % rev.", "blank = historical"],
  ["nwc_pct_revenue_change", "NWC % Δrevenue", "blank = historical"], ["forecast_years", "Horizon (years)", "explicit forecast"],
  ["forward_eps", "Forward EPS (your estimate)", "blank = no forward P/E"],
];

interface MacroSeries { id: string; label: string; value?: number; date?: string; status: string; message?: string; hint?: string; url?: string }

/** The 10-year Treasury yield from FRED (free) as a reference for the user's own build-up — never applied automatically. */
function RiskFreeReference() {
  const q = useQuery({ queryKey: ["macro"], queryFn: () => api<{ series: MacroSeries[] }>("/macro"), staleTime: 3_600_000 });
  const t = q.data?.series.find((x) => x.id === "DGS10");
  if (!t) return null;
  return t.status === "ok" ? (
    <p className="text-[11px] text-fg-3">Reference: 10-year Treasury <span className="num text-fg-2">{t.value?.toFixed(2)}%</span> on {date(t.date ?? null)}
      {" "}(<a className="text-accent underline underline-offset-2" href={t.url} target="_blank" rel="noopener noreferrer">FRED DGS10</a>). Not applied automatically.</p>
  ) : <p className="text-[11px] text-fg-3">FRED reference rate unavailable: {t.message}</p>;
}

export function AssumptionForm({ s, update, onRun, running }: { s: ValSettings; update: (p: Partial<ValSettings>) => void; onRun: () => void; running: boolean }) {
  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); onRun(); }}>
      <Field label="Discount rate (WACC) — required" hint="DEEPTERMINAL never invents a cost of capital.">
        <Input required inputMode="decimal" placeholder="e.g. 0.09" value={s.discount_rate} onChange={(e) => update({ discount_rate: e.target.value })} />
      </Field>
      <RiskFreeReference />
      <Field label="How was it chosen?"><Input placeholder="e.g. CAPM: rf 4.2% + β1.1 × ERP 4.5%" value={s.discount_rate_rationale} onChange={(e) => update({ discount_rate_rationale: e.target.value })} /></Field>
      <div className="grid grid-cols-2 gap-2">
        {FIELDS.map(([k, label, hint]) => <Field key={k} label={label} hint={hint}><Input inputMode="decimal" value={s[k]} onChange={(e) => update({ [k]: e.target.value } as Partial<ValSettings>)} /></Field>)}
        <Field label="Basis"><Select value={s.basis} onChange={(e) => update({ basis: e.target.value })} className="w-full"><option value="ttm">Trailing 12 months</option><option value="annual">Last fiscal year</option></Select></Field>
      </div>
      <Button type="submit" variant="primary" loading={running} className="w-full" disabled={!s.discount_rate}>Run valuation</Button>
    </form>
  );
}
