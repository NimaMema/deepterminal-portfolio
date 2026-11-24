"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, post } from "./api";
import { useDemo } from "./demo";

export interface ValSettings { discount_rate: string; discount_rate_rationale: string; terminal_growth: string; terminal_roic: string; forecast_years: string;
  basis: string; base_growth: string; base_margin: string; tax_rate: string; net_capex_pct_revenue: string; nwc_pct_revenue_change: string; forward_eps: string }
export const DEFAULTS: ValSettings = { discount_rate: "", discount_rate_rationale: "", terminal_growth: "0.025", terminal_roic: "", forecast_years: "7",
  basis: "ttm", base_growth: "", base_margin: "", tax_rate: "", net_capex_pct_revenue: "", nwc_pct_revenue_change: "", forward_eps: "" };

export interface ValResult {
  scenario_warnings?: string[];
  company: string; ticker: string; synthetic: boolean; analysis_date: string; basis: string;
  price: { value: number; as_of: string; source: string } | null;
  market: { enterprise_value: number; market_cap: number; diluted_shares: number; ledger: [string, number][] } | null;
  capital_structure?: Record<string, unknown>;
  methods?: { method: string; role: string; reason: string }[];
  assumptions: { name: string; value: number; unit: string; status: string; rationale: string; sources: { title: string; url: string | null }[] }[];
  scenarios: { name: string; narrative: string; dependencies: string[]; per_share: number; equity_value: number; diluted_shares: number; bridge: [string, number][];
    dcf: { enterprise_value: number; pv_explicit: number; terminal_value: number; pv_terminal: number; terminal_share: number; warnings: string[];
      inputs: { base_revenue: number; revenue_growth: number[]; ebit_margin: number[]; tax_rate: number; discount_rate: number; terminal_growth: number; terminal_roic: number };
      years: { year: number; revenue: number; growth: number; ebit: number; ebit_margin: number; nopat: number; reinvestment: number; fcff: number; discount_factor: number; present_value: number }[] } }[];
  sensitivity: { rows: number[]; cols: number[]; values: (number | null)[][]; row_label: string; col_label: string };
  tornado: { assumption: string; low_input: string; high_input: string; low_value: number; high_value: number; swing: number }[];
  reverse_dcf: { lever: string; label: string; unit: string; status: string; statement: string; held_constant: Record<string, string>; notes: string[]; target_enterprise_value: number;
    solutions: { value: number; final_revenue: number; revenue_cagr: number | null; final_margin: number; cumulative_fcff: number; implied_market_share: number | null; fcff_path: number[]; revenue_path: number[] }[] }[];
  iso_value?: { margin: number; growth: number[] }[]; growth_duration?: { growth_rate: number; years_required: number | null; max_years_tested: number };
  multiples: Record<string, { name: string; value: number | null; meaningful: boolean; reason: string }>;
  expectations_gap: { metric: string; market_implied: number; company_median: number | null; company_max: number | null; peer_median: number | null; peer_max: number | null; observations: string[] }[];
  assessment: { verdict: string; reasons: string[]; price_position: string; margin_of_safety: number; upside_to_base: number; downside_to_bear: number; caveat: string;
    steps: { number: number; title: string; performed: boolean; detail: string }[] } | null;
  validation: { name: string; status: string; detail: string }[]; notes: string[]; settings: Record<string, unknown>;
  unavailable?: { status: string; message: string; hint?: string }; run_id?: number;
  price_fetch?: { status: string; message: string; hint?: string; attribution?: string } | null;
}

export const DEMO_DISCOUNT_RATIONALE = "Illustrative 9% for the public demo, not an estimate of this company's cost of capital";

export function useValSettings(companyId: number) {
  const key = `dt:val:${companyId}`;
  const isDemo = useDemo();
  const [s, setS] = useState<ValSettings>(DEFAULTS);
  useEffect(() => {
    let stored: Partial<ValSettings> | null = null;
    try { const v = localStorage.getItem(key); if (v) stored = JSON.parse(v); } catch { /* ignore */ }
    // The public demo starts from a labelled illustrative discount rate so results show at once.
    const demo = isDemo && !stored?.discount_rate ? { discount_rate: "0.09", discount_rate_rationale: DEMO_DISCOUNT_RATIONALE } : {};
    setS({ ...DEFAULTS, ...(stored ?? {}), ...demo });
  }, [key, isDemo]);
  const update = (patch: Partial<ValSettings>) => setS((prev) => { const n = { ...prev, ...patch }; try { localStorage.setItem(key, JSON.stringify(n)); } catch { /* ignore */ } return n; });
  return [s, update] as const;
}

export function toPayload(s: ValSettings) {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(s)) {
    if (v === "") continue;
    out[k] = ["basis", "discount_rate_rationale"].includes(k) ? v : k === "forecast_years" ? parseInt(v, 10) : Number(v);
  }
  if (!out.discount_rate_rationale) delete out.discount_rate_rationale;
  return out;
}

export function useValuation(companyId: number) {
  // Public demo: value as of the recorded price's date, so the price and the filings it is
  // compared with are contemporaneous (the recorded prices are weeks old by design).
  const isDemo = useDemo();
  const prices = usePrices(companyId);
  const asOf = isDemo ? prices.data?.[0]?.as_of : undefined;
  return useMutation({ mutationFn: (body: { settings: Record<string, unknown>; save?: boolean; label?: string }) =>
    post<ValResult>(`/companies/${companyId}/valuation`, asOf ? { ...body, as_of: asOf } : body) });
}

export function usePrices(companyId: number) {
  return useQuery({ queryKey: ["prices", companyId], queryFn: () => api<{ id: number; value: number; as_of: string; source: string; url: string | null }[]>(`/companies/${companyId}/prices`) });
}
