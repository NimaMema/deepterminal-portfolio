"use client";

import { BackendOnly, useDemo } from "@/lib/demo";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Page, PageHeader } from "@/components/company";
import { Button, LoadingPanel, Notice, Panel, Select, Unavailable } from "@/components/ui";
import { api, post } from "@/lib/api";
import { date } from "@/lib/format";
import type { Company } from "@/lib/types";

function Reports() {
  const sp = useSearchParams();
  const qc = useQueryClient();
  const isDemo = useDemo();
  const companies = useQuery({ queryKey: ["companies"], queryFn: () => api<Company[]>("/companies") });
  const [cid, setCid] = useState<number | null>(sp.get("company") ? Number(sp.get("company")) : null);
  useEffect(() => { if (!cid && companies.data?.length) setCid(companies.data[0].id); }, [companies.data, cid]);
  const reports = useQuery({ queryKey: ["reports", cid], enabled: !!cid, queryFn: () => api<{ id: string; title: string; created_at: string; sections: { title: string; count: number }[]; job_id: string | null }[]>(`/companies/${cid}/reports`) });
  const gen = useMutation({ mutationFn: () => post<{ id: string }>("/reports", { company_id: cid }), onSuccess: () => qc.invalidateQueries({ queryKey: ["reports", cid] }) });
  return (
    <Page>
      <PageHeader title="Research reports" description="Professional 21-section reports compiled from stored findings, valuation output and their evidence, with a numbered bibliography. No buy/sell recommendation.">
        <Select value={cid ?? ""} onChange={(e) => setCid(Number(e.target.value))} aria-label="Company">{companies.data?.map((c) => <option key={c.id} value={c.id}>{c.ticker} — {c.name}</option>)}</Select>
        <Button variant="primary" onClick={() => gen.mutate()} loading={gen.isPending} disabled={!cid || isDemo}><FileText size={14} aria-hidden />Generate report</Button>
        {isDemo && <BackendOnly />}
      </PageHeader>
      {gen.error && <Unavailable error={gen.error} />}
      <Notice>Reports use the latest successful investigation (and thesis challenge, if any) plus your latest saved valuation run. Sections with no findings say so explicitly.</Notice>
      <Panel title="Reports">
        {reports.isLoading && <LoadingPanel rows={3} />}
        {reports.data?.length === 0 && <p className="text-sm text-fg-3">No reports yet for this company.</p>}
        <ul className="divide-y divide-ink-800">{reports.data?.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center gap-3 py-3">
            <FileText size={16} className="text-accent" aria-hidden />
            <div className="min-w-0 flex-1"><Link href={`/reports/${r.id}`} className="font-medium hover:underline">{r.title}</Link>
              <div className="text-xs text-fg-3">{date(r.created_at)} · {r.sections.reduce((a, s) => a + s.count, 0)} findings across {r.sections.filter((s) => s.count).length} sections · investigation {r.job_id ?? "none"}</div></div>
            <Link href={`/reports/${r.id}`}><Button>View</Button></Link>
            <a href={`/api/reports/${r.id}/pdf`}><Button><Download size={14} aria-hidden />PDF</Button></a>
          </li>))}</ul>
      </Panel>
    </Page>
  );
}

export default function ReportsPage() { return <Suspense fallback={<div className="p-6"><LoadingPanel /></div>}><Reports /></Suspense>; }
