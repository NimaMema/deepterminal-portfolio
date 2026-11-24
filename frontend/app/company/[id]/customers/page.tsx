"use client";

import { LineTrend } from "@/components/charts";
import { Page, PageHeader, useCompanyId } from "@/components/company";
import { ModuleFindings } from "@/components/evidence";
import { LoadingPanel, Notice, Panel, Unavailable } from "@/components/ui";
import { useModule } from "@/lib/api";
import { date, pct } from "@/lib/format";

interface Demand {
  concentration: { share: number; text: string; accession: string; fy: number; filed: string }[];
  trend: { fy: number; revenue: number; revenue_growth: number | null; deferred_growth: number | null; rpo_growth: number | null; receivables_growth: number | null; dso: number | null; gross_margin: number | null }[];
  quality_tests: { test: string; result: string; detail: string }[]; unavailable_tests: string[];
  providers: { source: string; status: string; reason: string }[]; caution: string;
}

export default function Customers() {
  const id = useCompanyId();
  const m = useModule<Demand>(id, "customer_demand");
  const d = m.data?.data;
  return (
    <Page>
      <PageHeader title="Customer & demand intelligence" description="Is reported revenue growth backed by sustainable demand? Tests use deferred revenue, backlog (RPO), receivables and disclosed customer concentration." />
      {m.isLoading && <LoadingPanel rows={8} />}
      {m.error && <Unavailable error={m.error} />}
      {d && (
        <>
          <Notice>{d.caution}</Notice>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Revenue vs demand indicators" subtitle="Year-over-year growth">
              <LineTrend data={d.trend.filter((t) => t.revenue_growth !== null).map((t) => ({ fy: `FY${t.fy}`, rev: t.revenue_growth, def: t.deferred_growth, rpo: t.rpo_growth, ar: t.receivables_growth }))} x="fy"
                series={[{ key: "rev", label: "Revenue" }, { key: "def", label: "Deferred revenue" }, { key: "rpo", label: "Backlog (RPO)" }, { key: "ar", label: "Receivables", dashed: true }]} />
            </Panel>
            <Panel title="Demand-quality tests" subtitle="Latest fiscal year">
              {d.quality_tests.length === 0 && <p className="text-sm text-fg-3">Not enough disclosed data for these tests.</p>}
              <ul className="space-y-2">{d.quality_tests.map((t) => (
                <li key={t.test} className="rounded-lg border border-ink-700 bg-ink-850 p-3 text-sm"><div className="font-medium">{t.test}</div>
                  <div className={t.result === "supports demand" ? "text-good" : t.result === "consistent" ? "text-fg-2" : "text-warn"}>{t.result}</div>
                  <div className="text-xs text-fg-3">{t.detail}</div></li>))}</ul>
              <div className="mt-3 text-xs text-fg-3">Not computable from filings: {d.unavailable_tests.join("; ")}.</div>
            </Panel>
          </div>
          <Panel title="Customer concentration" subtitle="Disclosed in annual reports">
            {d.concentration.length === 0 && <p className="text-sm text-fg-3">No customer concentration disclosure found in recent 10-K text.</p>}
            <ul className="space-y-2">{d.concentration.map((c, i) => (
              <li key={i} className="flex gap-3 rounded-lg border border-ink-700 bg-ink-850 p-3 text-sm"><span className={`num text-lg font-semibold ${c.share >= 0.2 ? "text-bad" : c.share >= 0.1 ? "text-warn" : ""}`}>{pct(c.share, 0)}</span>
                <div><div className="text-fg-2">{c.text}</div><div className="text-[11px] text-fg-3">FY{c.fy} 10-K · filed {date(c.filed)} · {c.accession}</div></div></li>))}</ul>
          </Panel>
          <Panel title="Customer satisfaction & usage data" subtitle="Requires licensed or permitted providers">
            <ul className="grid gap-2 md:grid-cols-2">{d.providers.map((p) => (
              <li key={p.source} className="rounded-lg border border-ink-700 bg-ink-850 p-3 text-xs"><div className="font-medium text-fg">{p.source}</div>
                <div className="uppercase tracking-wider text-fg-3">{p.status.replace(/_/g, " ")}</div><div className="mt-1 text-fg-2">{p.reason}</div></li>))}</ul>
          </Panel>
        </>
      )}
      <ModuleFindings companyId={id} module="customer_demand" />
      <ModuleFindings companyId={id} module="product_research" title="Product research findings" />
    </Page>
  );
}
