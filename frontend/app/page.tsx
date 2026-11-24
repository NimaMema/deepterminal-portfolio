"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Bot, Database, FileText, Search, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import type { Company } from "@/lib/types";
import { Button, Input, LoadingPanel, Panel, SyntheticBadge, Unavailable } from "@/components/ui";

interface Saved { id: number; company_id: number; kind: string; title: string; company: { name: string; ticker: string; synthetic: boolean } | null; updated_at: string }
interface Hit { cik: number; ticker: string; name: string; synthetic: boolean }
interface Sources { sources: { id: string; name: string; status: string; detail: string; configured: boolean }[]; network_note: string | null }

export default function Terminal() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const hits = useQuery({ queryKey: ["search", q], enabled: q.trim().length > 0, queryFn: () => api<{ results: Hit[] }>(`/search?q=${encodeURIComponent(q)}`) });
  const loaded = useQuery({ queryKey: ["companies"], queryFn: () => api<Company[]>("/companies") });
  const saved = useQuery({ queryKey: ["saved", "watchlist"], queryFn: () => api<Saved[]>("/saved?kind=watchlist") });
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api<Sources>("/sources") });
  const open = async (key: string) => {
    setBusy(true); setErr(null);
    try { const c = await api<{ id: number }>(`/companies/resolve/${encodeURIComponent(key)}`); router.push(`/company/${c.id}`); }
    catch (e) { setErr(e); } finally { setBusy(false); }
  };
  return (
    <div className="grid-bg min-h-full">
      <div className="mx-auto max-w-[1400px] space-y-6 px-4 py-8 sm:px-6">
        <section className="rounded-2xl border border-ink-700 bg-gradient-to-br from-ink-900 via-ink-900 to-[#0b1d1c] p-6 sm:p-8">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-accent">Evidence-first equity research</div>
          <h1 className="mt-2 max-w-3xl text-2xl font-semibold tracking-tight sm:text-3xl">Is it a good business, what is it worth, and what is the market already assuming?</h1>
          <p className="mt-2 max-w-3xl text-sm text-fg-3">Every figure links to its SEC filing. Every claim shows its evidence. Missing data is reported as missing — never invented.</p>
          <form className="mt-5 flex max-w-2xl gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim()) open(hits.data?.results[0]?.ticker ?? q.trim()); }}>
            <div className="relative flex-1">
              <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-fg-3" aria-hidden />
              <Input aria-label="Search by ticker, company name or CIK" value={q} onChange={(e) => setQ(e.target.value)}
                placeholder="Ticker, company name or CIK — e.g. DQD, Harbor, 9900003" className="h-11 pl-9 text-[15px]" />
            </div>
            <Button variant="primary" type="submit" loading={busy} className="h-11 px-5">Open</Button>
          </form>
          {q && hits.data && (
            <ul className="mt-2 max-w-2xl divide-y divide-ink-800 overflow-hidden rounded-lg border border-ink-700 bg-ink-900" aria-label="Search results">
              {hits.data.results.slice(0, 6).map((h) => (
                <li key={`${h.cik}${h.ticker}`}>
                  <button onClick={() => open(h.ticker || String(h.cik))} className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-ink-800">
                    <span className="num w-16 font-semibold text-accent">{h.ticker}</span><span className="truncate">{h.name}</span>
                    {h.synthetic && <SyntheticBadge />}<span className="num ml-auto text-[11px] text-fg-3">CIK {h.cik}</span>
                  </button>
                </li>
              ))}
              {hits.data.results.length === 0 && <li className="px-3 py-2 text-sm text-fg-3">No SEC registrant matches “{q}”.</li>}
            </ul>
          )}
          {hits.error && <div className="mt-3 max-w-2xl"><Unavailable error={hits.error} compact /></div>}
          {err != null && <div className="mt-3 max-w-2xl"><Unavailable error={err} compact /></div>}
        </section>

        <div className="grid gap-4 lg:grid-cols-3">
          <Panel title="Watchlist" subtitle="Saved companies" className="lg:col-span-1"
            actions={<Link href="/saved" className="text-xs text-accent hover:underline">All saved</Link>}>
            {saved.isLoading && <LoadingPanel rows={3} />}
            {saved.data && saved.data.length === 0 && <p className="text-sm text-fg-3">Nothing saved yet. Open a company and press “Watch”.</p>}
            <ul className="space-y-1">{saved.data?.map((s) => (
              <li key={s.id}><Link href={`/company/${s.company_id}`} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-ink-800">
                <span className="num w-14 font-semibold text-accent">{s.company?.ticker}</span><span className="truncate text-fg-2">{s.company?.name}</span>
                <ArrowRight size={13} className="ml-auto text-fg-3" aria-hidden /></Link></li>))}</ul>
          </Panel>
          <Panel title="Recently researched" subtitle="Companies loaded into this workspace" className="lg:col-span-2">
            {loaded.isLoading && <LoadingPanel rows={4} />}
            {loaded.error && <Unavailable error={loaded.error} />}
            {loaded.data && loaded.data.length === 0 && <p className="text-sm text-fg-3">Search above to load your first company from SEC EDGAR.</p>}
            <div className="grid gap-2 sm:grid-cols-2">
              {loaded.data?.slice(0, 8).map((c) => (
                <Link key={c.id} href={`/company/${c.id}`} className="group rounded-lg border border-ink-700 bg-ink-850 p-3 hover:border-accent/50">
                  <div className="flex items-center gap-2"><span className="num font-semibold text-accent">{c.ticker}</span><SyntheticBadge show={c.synthetic} /></div>
                  <div className="mt-0.5 truncate text-sm text-fg">{c.name}</div>
                  <div className="mt-1 truncate text-[11px] text-fg-3">{c.sic_description} · profile {ago(c.profile_retrieved_at)}</div>
                </Link>
              ))}
            </div>
          </Panel>
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[
            { icon: TrendingUp, t: "Investigate", d: "13 research modules produce evidence-linked findings with live progress.", href: loaded.data?.[0] ? `/company/${loaded.data[0].id}/research` : "/" },
            { icon: Sparkles, t: "Thesis Challenger", d: "Actively searches for evidence that your thesis is wrong.", href: loaded.data?.[0] ? `/company/${loaded.data[0].id}/thesis` : "/" },
            { icon: Bot, t: "Research chat", d: "Ask questions; answers cite filing passages you can open.", href: "/chat" },
            { icon: FileText, t: "Reports", d: "21-section research reports with bibliography and PDF export.", href: "/reports" },
          ].map((c) => (
            <Link key={c.t} href={c.href} className="rounded-xl border border-ink-700 bg-ink-900 p-4 hover:border-accent/50">
              <c.icon size={18} className="text-accent" aria-hidden /><div className="mt-2 text-sm font-semibold">{c.t}</div>
              <div className="mt-1 text-xs text-fg-3">{c.d}</div>
            </Link>
          ))}
        </div>

        <Panel title="Data sources" subtitle="Live adapter status — nothing is purchased or bypassed"
          actions={<Link href="/settings" className="text-xs text-accent hover:underline">Configure</Link>}>
          {sources.isLoading && <LoadingPanel rows={3} />}
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {sources.data?.sources.map((s) => (
              <div key={s.id} className="rounded-lg border border-ink-700 bg-ink-850 p-3 text-xs">
                <div className="flex items-center gap-1.5 font-medium text-fg">{s.status === "ok" || s.status === "configured" || s.status === "cache" ? <ShieldCheck size={13} className="text-good" aria-hidden /> : <Database size={13} className="text-fg-3" aria-hidden />}{s.name}</div>
                <div className={`mt-1 font-semibold uppercase tracking-wider ${["ok", "cache", "configured"].includes(s.status) ? "text-good" : s.status === "demo" ? "text-warn" : "text-fg-3"}`}>{s.status.replace(/_/g, " ")}</div>
                <div className="mt-0.5 line-clamp-2 text-fg-3">{s.detail}</div>
              </div>
            ))}
          </div>
          {sources.data?.network_note && <p className="mt-3 text-[11px] text-fg-3">{sources.data.network_note}</p>}
        </Panel>
      </div>
    </div>
  );
}
