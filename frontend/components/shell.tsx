"use client";

import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Command } from "cmdk";
import * as Dialog from "@radix-ui/react-dialog";
import {
  Activity, Archive, BarChart3, BookMarked, Bot, Boxes, Building2, Calculator, Clock3, FileSearch, FileText, Gauge,
  GitCompare, History, LayoutDashboard, Menu, MessagesSquare, Network, Scale, Search, Settings, ShieldAlert, Swords,
  Sparkles, TrendingUp, Users, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";

export const COMPANY_NAV = [
  { href: "", label: "Overview", icon: LayoutDashboard },
  { href: "/financials", label: "Financial statements", icon: BarChart3 },
  { href: "/filings", label: "SEC filing explorer", icon: FileSearch },
  { href: "/time-machine", label: "Filing time machine", icon: Clock3 },
  { href: "/corporate", label: "Corporate intelligence", icon: Building2 },
  { href: "/management", label: "Management", icon: Users },
  { href: "/forensics", label: "Forensic accounting", icon: ShieldAlert },
  { href: "/supply-chain", label: "Supply chain", icon: Network },
  { href: "/customers", label: "Customers & demand", icon: Boxes },
  { href: "/competitors", label: "Competitors", icon: Swords },
  { href: "/sentiment", label: "Sentiment & hype", icon: Activity },
  { href: "/analogues", label: "Historical analogues", icon: History },
  { href: "/valuation", label: "Valuation laboratory", icon: Calculator },
  { href: "/reverse-dcf", label: "Reverse DCF", icon: Gauge },
  { href: "/research", label: "Investigation", icon: TrendingUp },
  { href: "/thesis", label: "Thesis challenger", icon: Scale },
  { href: "/chat", label: "Research chat", icon: MessagesSquare },
];

const GLOBAL_NAV = [
  { href: "/", label: "Terminal", icon: LayoutDashboard },
  { href: "/compare", label: "Compare companies", icon: GitCompare },
  { href: "/chat", label: "AI research chat", icon: Bot },
  { href: "/reports", label: "Research reports", icon: FileText },
  { href: "/saved", label: "Saved research", icon: BookMarked },
  { href: "/settings", label: "Settings & data sources", icon: Settings },
];

interface Status { data_mode: string; synthetic: boolean; public_demo?: boolean; snapshot_date?: string | null; providers: { provider: string; model: string; active: boolean; configured: boolean }[] }
interface SearchHit { cik: number; ticker: string; name: string; synthetic: boolean }

function useCompanyIdFromPath(): string | null {
  const p = usePathname();
  const m = p?.match(/^\/company\/(\d+)/);
  return m ? m[1] : null;
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const companyId = useCompanyIdFromPath();
  const [palette, setPalette] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [lastCompany, setLastCompany] = useState<{ id: string; label: string } | null>(null);
  const status = useQuery({ queryKey: ["status"], queryFn: () => api<Status>("/status"), staleTime: 30_000 });
  const company = useQuery({
    queryKey: ["company-lite", companyId], enabled: !!companyId,
    queryFn: () => api<{ id: number; ticker: string; name: string; synthetic: boolean }>(`/companies/${companyId}`),
  });
  const cid = companyId ?? lastCompany?.id ?? null;

  useEffect(() => {
    try { const v = localStorage.getItem("dt:last-company"); if (v) setLastCompany(JSON.parse(v)); } catch { /* storage unavailable */ }
  }, []);
  useEffect(() => {
    if (company.data) {
      const v = { id: String(company.data.id), label: company.data.ticker || company.data.name };
      setLastCompany(v);
      try { localStorage.setItem("dt:last-company", JSON.stringify(v)); } catch { /* ignore */ }
    }
  }, [company.data]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((v) => !v); }
      if (e.key === "/" && !(e.target as HTMLElement)?.closest("input,textarea,select")) { e.preventDefault(); setPalette(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => setMobileNav(false), [pathname]);

  const active = status.data?.providers.find((p) => p.active);
  const nav = (
    <nav aria-label="Primary" className="scroll-thin flex h-full flex-col gap-5 overflow-y-auto px-3 py-4">
      <div>
        <div className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-fg-3">Workspace</div>
        <ul className="space-y-0.5">
          {status.data?.public_demo && <NavItem href="/demo" label="Judges' guide" icon={Sparkles} active={pathname === "/demo"} />}
          {GLOBAL_NAV.map((n) => <NavItem key={n.href} {...n} active={pathname === n.href} />)}
        </ul>
      </div>
      {cid && (
        <div>
          <div className="flex items-center justify-between px-2 pb-1">
            <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-fg-3">Company</span>
            <span className="num truncate text-[11px] text-accent">{company.data?.ticker ?? lastCompany?.label}</span>
          </div>
          <ul className="space-y-0.5">
            {COMPANY_NAV.map((n) => {
              const href = `/company/${cid}${n.href}`;
              return <NavItem key={n.href} href={href} label={n.label} icon={n.icon}
                active={pathname === href} />;
            })}
          </ul>
        </div>
      )}
      {!cid && <p className="px-2 text-xs text-fg-3">Open a company to see its research modules.</p>}
    </nav>
  );

  return (
    <div className="flex min-h-dvh bg-ink-950 text-fg">
      <a href="#main" className="sr-only z-50 rounded bg-accent px-3 py-2 text-accent-ink focus:not-sr-only focus:fixed focus:left-3 focus:top-3">Skip to content</a>
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 border-r border-ink-800 bg-ink-900/70 lg:block">
        <Brand />
        {nav}
      </aside>
      <Dialog.Root open={mobileNav} onOpenChange={setMobileNav}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60 lg:hidden" />
          <Dialog.Content className="fixed inset-y-0 left-0 z-50 w-72 border-r border-ink-700 bg-ink-900 lg:hidden" aria-describedby={undefined}>
            <Dialog.Title className="sr-only">Navigation</Dialog.Title>
            <div className="flex items-center justify-between pr-3"><Brand /><Dialog.Close aria-label="Close navigation" className="p-1 text-fg-3"><X size={18} /></Dialog.Close></div>
            {nav}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-ink-800 bg-ink-950/85 px-4 backdrop-blur">
          <button className="rounded p-1.5 text-fg-2 hover:bg-ink-800 lg:hidden" onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu size={18} /></button>
          <button onClick={() => setPalette(true)}
            className="flex min-w-0 flex-1 items-center gap-2 rounded-lg border border-ink-700 bg-ink-900 px-3 py-1.5 text-left text-sm text-fg-3 hover:border-ink-600 sm:max-w-md"
            aria-label="Search companies and commands">
            <Search size={15} aria-hidden /><span className="truncate">Search ticker, company or CIK…</span>
            <kbd className="ml-auto hidden rounded border border-ink-600 px-1.5 text-[10px] text-fg-3 sm:inline">⌘K</kbd>
          </button>
          <div className="ml-auto flex items-center gap-2 text-[11px]">
            {status.data && (
              <Link href="/settings" className={clsx("hidden items-center gap-1.5 rounded-md border px-2 py-1 sm:flex",
                status.data.synthetic ? "border-warn/50 bg-warn/10 text-warn" : "border-good/40 bg-good/10 text-good")}>
                <span className="size-1.5 rounded-full bg-current" aria-hidden />
                {status.data.synthetic ? "DEMO DATA · synthetic" : status.data.public_demo ? "SEC EDGAR · recorded snapshot" : "LIVE · SEC EDGAR"}
              </Link>
            )}
            {status.data && (
              <Link href="/settings" className="hidden items-center gap-1.5 rounded-md border border-ink-700 px-2 py-1 text-fg-2 md:flex">
                <Bot size={12} aria-hidden />AI: {status.data.public_demo ? "recorded local-model examples · rule-based live" : active && active.provider !== "rules" ? `${active.provider === "ollama" ? "local" : active.provider} · ${active.model}` : "rule-based (Ollama not running)"}
              </Link>
            )}
          </div>
        </header>
        {status.data?.public_demo && (
          <div className="border-b border-accent/30 bg-accent/[0.06] px-4 py-1.5 text-[11.5px] text-fg-2" role="note">
            <b className="text-accent">Public demo.</b> Real SEC EDGAR data recorded{status.data.snapshot_date ? ` on ${status.data.snapshot_date}` : ""}, served read-only. Valuation, reverse DCF,
            chat and the Thesis Challenger run live on this server; controls marked “full local backend” need a local install.{" "}
            <Link href="/demo" className="underline underline-offset-2 hover:text-accent">Judges&apos; guide</Link>
          </div>
        )}
        {status.data?.synthetic && (
          <div className="border-b border-warn/30 bg-warn/[0.06] px-4 py-1.5 text-[11.5px] text-warn" role="note">
            Demo mode: companies marked “(Demo)” are fictional and their filings and figures are synthetic, generated in SEC formats.
            Switch to live SEC data in Settings once network access to sec.gov is allowed.
          </div>
        )}
        <main id="main" className="min-w-0 flex-1">{children}</main>
      </div>
      <CommandPalette open={palette} onOpenChange={setPalette} companyId={cid} />
    </div>
  );
}

function Brand() {
  return (
    <Link href="/" className="flex h-14 items-center gap-2.5 border-b border-ink-800 px-5">
      <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden><rect x="2" y="2" width="20" height="20" rx="5" fill="#0f2e2b" stroke="#2dd4bf" strokeWidth="1.5" />
        <path d="M7 15l3-4 3 2 4-6" fill="none" stroke="#2dd4bf" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
      <span className="text-[13px] font-bold tracking-[0.22em]">DEEP<span className="text-accent">TERMINAL</span></span>
    </Link>
  );
}

function NavItem({ href, label, icon: Icon, active }: { href: string; label: string; icon: typeof Search; active: boolean }) {
  return (
    <li>
      <Link href={href} aria-current={active ? "page" : undefined}
        className={clsx("flex items-center gap-2.5 rounded-md px-2 py-1.5 text-[13px] transition-colors",
          active ? "bg-accent/10 text-accent" : "text-fg-2 hover:bg-ink-800 hover:text-fg")}>
        <Icon size={15} aria-hidden className="shrink-0" /><span className="truncate">{label}</span>
      </Link>
    </li>
  );
}

function CommandPalette({ open, onOpenChange, companyId }: { open: boolean; onOpenChange: (o: boolean) => void; companyId: string | null }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const hits = useQuery({ queryKey: ["search", q], enabled: q.trim().length > 0,
    queryFn: () => api<{ results: SearchHit[] }>(`/search?q=${encodeURIComponent(q.trim())}`), staleTime: 60_000 });
  const go = (href: string) => { onOpenChange(false); setQ(""); router.push(href); };
  const openCompany = async (key: string) => {
    setBusy(key); setErr(null);
    try { const c = await api<{ id: number }>(`/companies/resolve/${encodeURIComponent(key)}`); go(`/company/${c.id}`); }
    catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  };
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-[12vh] z-50 w-[min(640px,calc(100vw-24px))] -translate-x-1/2 overflow-hidden rounded-xl border border-ink-600 bg-ink-900 shadow-2xl" aria-describedby={undefined}>
          <Dialog.Title className="sr-only">Search and commands</Dialog.Title>
          <Command shouldFilter={false} label="Search companies and commands">
            <div className="flex items-center gap-2 border-b border-ink-700 px-4">
              <Search size={16} className="text-fg-3" aria-hidden />
              <Command.Input value={q} onValueChange={setQ} placeholder="Ticker, company name or CIK…" autoFocus
                className="h-12 flex-1 bg-transparent text-[15px] text-fg placeholder:text-fg-3 focus:outline-none" />
            </div>
            <Command.List className="scroll-thin max-h-[60vh] overflow-y-auto p-2">
              {err && <div className="m-2 rounded border border-bad/40 bg-bad/10 p-2 text-xs text-bad">{err}</div>}
              {q.trim() && hits.isLoading && <Command.Loading><div className="p-3 text-sm text-fg-3">Searching SEC registrants…</div></Command.Loading>}
              {hits.error && <div className="p-3 text-sm text-bad">{(hits.error as Error).message}</div>}
              {q.trim() && hits.data && hits.data.results.length === 0 && <Command.Empty className="p-3 text-sm text-fg-3">No matching SEC registrant.</Command.Empty>}
              {hits.data && hits.data.results.length > 0 && (
                <Command.Group heading="Companies" className="text-[11px] text-fg-3 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1">
                  {hits.data.results.map((h) => (
                    <Command.Item key={`${h.cik}-${h.ticker}`} value={`${h.ticker}-${h.cik}`} onSelect={() => openCompany(h.ticker || String(h.cik))}
                      className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm text-fg data-[selected=true]:bg-ink-700">
                      <span className="num w-16 shrink-0 font-semibold text-accent">{h.ticker}</span>
                      <span className="truncate">{h.name}</span>
                      <span className="num ml-auto shrink-0 text-[11px] text-fg-3">{busy === (h.ticker || String(h.cik)) ? "opening…" : `CIK ${h.cik}`}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
              <Command.Group heading="Navigate" className="text-[11px] text-fg-3 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1">
                {[...GLOBAL_NAV.map((n) => ({ ...n, full: n.href })),
                  ...(companyId ? COMPANY_NAV.map((n) => ({ ...n, full: `/company/${companyId}${n.href}` })) : [])]
                  .filter((n) => !q || n.label.toLowerCase().includes(q.toLowerCase()))
                  .map((n) => (
                    <Command.Item key={n.full} value={n.full} onSelect={() => go(n.full)}
                      className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm text-fg-2 data-[selected=true]:bg-ink-700 data-[selected=true]:text-fg">
                      <n.icon size={15} aria-hidden />{n.label}
                    </Command.Item>
                  ))}
              </Command.Group>
            </Command.List>
          </Command>
          <div className="flex items-center gap-3 border-t border-ink-700 px-4 py-2 text-[11px] text-fg-3">
            <span><kbd>↑↓</kbd> navigate</span><span><kbd>↵</kbd> open</span><span><kbd>esc</kbd> close</span>
            <Archive size={12} className="ml-auto" aria-hidden /> SEC registrant index
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
