"use client";

import { useDemo } from "@/lib/demo";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, ExternalLink, FileText, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";
import { api, post } from "@/lib/api";
import { date, price } from "@/lib/format";
import type { CompanyDetail } from "@/lib/types";
import { Button, Skeleton, SyntheticBadge, Unavailable } from "./ui";

export function useCompanyId(): number {
  const p = useParams<{ id: string }>();
  return Number(p.id);
}

export function useCompany() {
  const id = useCompanyId();
  return useQuery({ queryKey: ["company", id], queryFn: () => api<CompanyDetail>(`/companies/${id}`) });
}

export function PageHeader({ title, description, children }: { title: string; description?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-fg">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-fg-3">{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export function CompanyHeader() {
  const q = useCompany();
  const qc = useQueryClient();
  const isDemo = useDemo();
  const save = useMutation({
    mutationFn: () => post("/saved", { company_id: q.data!.id, kind: "watchlist", title: `${q.data!.ticker} — ${q.data!.name}` }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["saved"] }),
  });
  if (q.isLoading) return <div className="space-y-2 border-b border-ink-800 px-6 py-5"><Skeleton className="h-6 w-72" /><Skeleton className="h-4 w-96" /></div>;
  if (q.error || !q.data) return <div className="p-6"><Unavailable error={q.error} /></div>;
  const c = q.data;
  return (
    <div className="border-b border-ink-800 bg-gradient-to-b from-ink-900 to-ink-950 px-4 py-4 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="num rounded-md border border-accent/40 bg-accent/10 px-2 py-0.5 text-sm font-bold text-accent">{c.ticker ?? "—"}</span>
            <h1 className="truncate text-lg font-semibold tracking-tight sm:text-xl">{c.name}</h1>
            <SyntheticBadge show={c.synthetic} />
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-fg-3">
            <span>CIK <span className="num text-fg-2">{String(c.cik).padStart(10, "0")}</span></span>
            <span>{c.sic_description ?? "SIC n/a"}{c.sic ? ` (${c.sic})` : ""}</span>
            <span>Inc. {c.state_of_incorporation ?? "—"}</span>
            <span>FYE {c.fiscal_year_end ?? "—"}</span>
            <span>Profile retrieved {date(c.profile_retrieved_at)}</span>
            {!c.synthetic && <a href={c.edgar_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">EDGAR <ExternalLink size={11} aria-hidden /></a>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="mr-2 text-right">
            <div className="num text-lg font-semibold">{c.price ? price(c.price.value) : "—"}</div>
            <div className="max-w-[22rem] truncate text-[11px] text-fg-3" title={c.price?.source}>{c.price ? `as of ${date(c.price.as_of)} · ${c.price.source}` : "no price entered"}</div>
          </div>
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={isDemo} title={isDemo ? "Watchlists need the full local backend" : undefined} aria-label="Add to watchlist">
            <BookmarkPlus size={14} aria-hidden />{save.isSuccess ? "Saved" : "Watch"}
          </Button>
          <Link href={`/company/${c.id}/research`}><Button variant="primary"><TrendingUp size={14} aria-hidden />Investigate</Button></Link>
          <Link href={`/reports?company=${c.id}`}><Button><FileText size={14} aria-hidden />Report</Button></Link>
        </div>
      </div>
      {c.financial_institution && <p className="mt-2 text-xs text-warn">Financial institution (SIC {c.sic}): enterprise-value DCF is not appropriate; the valuation lab will refuse it.</p>}
    </div>
  );
}

export function Page({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full max-w-[1500px] space-y-4 px-4 py-5 sm:px-6">{children}</div>;
}
