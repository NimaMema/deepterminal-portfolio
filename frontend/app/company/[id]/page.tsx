"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { BarTrend, LineTrend } from "@/components/charts";
import { Page, useCompany, useCompanyId } from "@/components/company";
import { FindingCard } from "@/components/evidence";
import { LoadingPanel, Notice, Panel, Stat, Unavailable } from "@/components/ui";
import { api } from "@/lib/api";
import { date, formLabel, money, num, pct } from "@/lib/format";
import type { Finding, Job } from "@/lib/types";

const MATERIAL_FORMS = "10-K,10-K/A,10-Q,10-Q/A,8-K,8-K/A,DEF 14A,20-F,40-F,6-K,S-1,S-3,S-4,SC 13D,SC 13G,SC 13D/A,SC 13G/A,SCHEDULE 13D,SCHEDULE 13G,SCHEDULE 13D/A,SCHEDULE 13G/A";

export default function Overview() {
  const id = useCompanyId();
  const c = useCompany();
  const findings = useQuery({ queryKey: ["findings", id], queryFn: () => api<Finding[]>(`/companies/${id}/findings`) });
  const filings = useQuery({ queryKey: ["filings", id, "recent"], queryFn: () => api<{ accession: string; form: string; filed: string; report_date: string | null; items: { code: string; description: string }[] }[]>(`/companies/${id}/filings?limit=8&form=${encodeURIComponent(MATERIAL_FORMS)}`) });
  const jobs = useQuery({ queryKey: ["jobs", id], queryFn: () => api<Job[]>(`/companies/${id}/jobs`) });
  const m = c.data?.metrics;
  const hist = m?.history ?? [];
  // Chart every reported year; complete-period history can skip years with a missing field.
  const trend = m?.trend?.length ? m.trend : hist;
  const last = hist[hist.length - 1];
  const ttm = m?.ttm as Record<string, number> | null | undefined;
  const material = (findings.data ?? []).filter((f) => f.severity === "concern" || f.severity === "watch").slice(0, 6);
  const positive = (findings.data ?? []).filter((f) => f.severity === "positive").slice(0, 3);
  return (
    <Page>
      {c.data?.metrics_unavailable && <Unavailable error={c.data.metrics_unavailable} title="Financial data unavailable" />}
      {c.isLoading && <LoadingPanel rows={6} />}
      {m && (
        <>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
            <Stat label={ttm ? "Revenue · TTM" : `Revenue · FY${last?.fy}`} value={money(ttm?.revenue ?? last?.revenue)} sub={ttm ? `to ${date(String(ttm.end))}` : undefined} />
            <Stat label="Revenue growth" value={pct(last?.revenue_growth)} sub={`FY${last?.fy} vs prior`} tone={(last?.revenue_growth ?? 0) < 0 ? "bad" : undefined} />
            <Stat label="Operating margin" value={pct(ttm?.operating_margin ?? last?.operating_margin)} sub={ttm ? "TTM" : `FY${last?.fy}`} />
            <Stat label="Free cash flow" value={money(ttm?.fcf ?? last?.fcf)} sub="OCF − capex" tone={(ttm?.fcf ?? last?.fcf ?? 0) < 0 ? "bad" : undefined} />
            <Stat label="Net debt" value={money(last?.net_debt)} sub={`FY${last?.fy}`} />
            <Stat label="Shares outstanding" value={`${num(m.shares_outstanding ?? last?.diluted_shares, 1)}m`} sub={m.shares_outstanding_as_of ? `cover page ${date(m.shares_outstanding_as_of)}` : "diluted weighted"} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Revenue" subtitle="Annual, USD — from 10-K XBRL facts">
              <BarTrend data={trend.map((h) => ({ fy: `FY${h.fy}`, revenue: h.revenue }))} x="fy" y="revenue" label="Revenue" fmt={(v) => money(v)} />
            </Panel>
            <Panel title="Margins" subtitle="Operating and net margin">
              <LineTrend data={trend.map((h) => ({ fy: `FY${h.fy}`, op: h.operating_margin, net: h.net_margin }))} x="fy"
                series={[{ key: "op", label: "Operating margin" }, { key: "net", label: "Net margin" }]} />
            </Panel>
          </div>
        </>
      )}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Material findings" subtitle="Concern and watch items from the latest investigations" className="lg:col-span-2"
          actions={<Link href={`/company/${id}/research`} className="text-xs text-accent hover:underline">All findings</Link>}>
          {findings.isLoading && <LoadingPanel rows={4} />}
          {findings.data && findings.data.length === 0 && (
            <Notice>No investigation has been run for this company yet. <Link href={`/company/${id}/research`} className="text-accent underline">Launch one</Link> to populate every module with evidence-backed findings.</Notice>
          )}
          <div className="space-y-2">{material.map((f) => <FindingCard key={f.id} f={f} />)}</div>
          {positive.length > 0 && <div className="mt-3 space-y-2">{positive.map((f) => <FindingCard key={f.id} f={f} compact />)}</div>}
        </Panel>
        <div className="space-y-4">
          <Panel title="Recent filings" actions={<Link href={`/company/${id}/filings`} className="text-xs text-accent hover:underline">Explorer</Link>}>
            {filings.isLoading && <LoadingPanel rows={4} />}
            <ul className="space-y-1.5 text-sm">
              {filings.data?.map((f) => (
                <li key={f.accession} className="flex items-baseline gap-2">
                  <span className="num w-20 shrink-0 truncate text-xs font-semibold text-accent">{f.form}</span>
                  <span className="truncate text-fg-2" title={f.accession}>{f.items.length ? f.items.map((i) => i.description).join("; ")
                    : `${formLabel(f.form)}${f.report_date ? ` · period ${date(f.report_date)}` : ""}`}</span>
                  <span className="num ml-auto shrink-0 text-[11px] text-fg-3">{date(f.filed)}</span>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Statement flags" subtitle="Automated screens (not findings of wrongdoing)">
            {m?.flags.length === 0 && <p className="text-sm text-fg-3">No automated flags triggered.</p>}
            <ul className="space-y-1.5 text-xs">{m?.flags.slice(-6).map((f, i) => (
              <li key={i}><span className="num text-warn">FY{f.fiscal_year} {f.code}</span><div className="text-fg-3">{f.message}</div></li>))}</ul>
          </Panel>
          <Panel title="Research jobs">
            {jobs.data?.length === 0 && <p className="text-sm text-fg-3">None yet.</p>}
            <ul className="space-y-1 text-xs">{jobs.data?.slice(0, 5).map((j) => (
              <li key={j.id} className="flex justify-between gap-2"><span className="capitalize text-fg-2">{j.kind}</span>
                <span className={j.status === "succeeded" ? "text-good" : j.status === "failed" ? "text-bad" : "text-warn"}>{j.status}</span>
                <span className="text-fg-3">{date(j.created_at)}</span></li>))}</ul>
          </Panel>
        </div>
      </div>
    </Page>
  );
}
