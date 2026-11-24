"use client";

import clsx from "clsx";
import { AlertTriangle, CircleSlash, Info, Loader2, ShieldCheck, ShieldQuestion, ShieldX } from "lucide-react";
import { useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import { ApiError } from "@/lib/api";
import type { Severity } from "@/lib/types";

export function Panel({ title, subtitle, actions, children, className, id, dense }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; id?: string; dense?: boolean;
}) {
  const auto = useId();
  const titleId = `${id ?? auto}-title`;
  return (
    <section id={id} className={clsx("rounded-xl border border-ink-700/80 bg-ink-900/80 shadow-[0_1px_0_0_rgba(255,255,255,0.03)_inset] min-w-0", className)}
      aria-labelledby={title ? titleId : undefined}>
      {(title || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-ink-700/70 px-4 py-3">
          <div className="min-w-0">
            {title && <h2 id={titleId} className="text-[13px] font-semibold tracking-wide text-fg">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-fg-3">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={dense ? "p-0" : "p-4"}>{children}</div>
    </section>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "good" | "bad" | "warn" }) {
  return (
    <div className="min-w-0 rounded-lg border border-ink-700/70 bg-ink-850 px-3 py-2.5">
      <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-fg-3">{label}</div>
      <div className={clsx("num mt-1 truncate text-lg font-semibold",
        tone === "good" && "text-good", tone === "bad" && "text-bad", tone === "warn" && "text-warn")}>{value}</div>
      {sub && <div className="mt-0.5 truncate text-[11px] text-fg-3">{sub}</div>}
    </div>
  );
}

const SEV: Record<string, { cls: string; label: string }> = {
  concern: { cls: "border-bad/40 bg-bad/10 text-bad", label: "Concern" },
  watch: { cls: "border-warn/40 bg-warn/10 text-warn", label: "Watch" },
  positive: { cls: "border-good/40 bg-good/10 text-good", label: "Positive" },
  neutral: { cls: "border-ink-500 bg-ink-800 text-fg-2", label: "Neutral" },
  unavailable: { cls: "border-na/30 bg-na/5 text-na", label: "Unavailable" },
};

export function SeverityBadge({ s }: { s: Severity | string }) {
  const v = SEV[s] ?? SEV.neutral;
  return <span className={clsx("inline-flex items-center rounded border px-1.5 py-px text-[10px] font-semibold uppercase tracking-wider", v.cls)}>{v.label}</span>;
}

const EPI: Record<string, string> = {
  historical_fact: "Verified fact", corroborated_fact: "Corroborated fact", company_statement: "Company statement",
  third_party_report: "Third-party report", estimate: "Estimate", model_assumption: "Model assumption",
  analytical_inference: "Inference", speculative_scenario: "Speculative", unverified_claim: "Unverified",
};

export function EpistemicBadge({ s }: { s: string }) {
  const tone = s === "historical_fact" || s === "corroborated_fact" ? "text-accent border-accent/30 bg-accent/5"
    : s === "company_statement" ? "text-s1 border-s1/30 bg-s1/5"
    : s === "unverified_claim" ? "text-warn border-warn/30 bg-warn/5" : "text-violet border-violet/30 bg-violet/5";
  return <span className={clsx("inline-flex items-center rounded border px-1.5 py-px text-[10px] font-medium", tone)}>{EPI[s] ?? s}</span>;
}

export function VerificationBadge({ s }: { s: string }) {
  if (s === "verified") return <span className="inline-flex items-center gap-1 text-[11px] text-good"><ShieldCheck size={12} aria-hidden />Verified against source</span>;
  if (s === "failed") return <span className="inline-flex items-center gap-1 text-[11px] text-bad"><ShieldX size={12} aria-hidden />Quote not found in source</span>;
  if (s === "not_applicable") return <span className="inline-flex items-center gap-1 text-[11px] text-fg-3"><Info size={12} aria-hidden />Calculation</span>;
  return <span className="inline-flex items-center gap-1 text-[11px] text-warn"><ShieldQuestion size={12} aria-hidden />Unverified / {s.replace(/_/g, " ")}</span>;
}

export function SyntheticBadge({ show = true }: { show?: boolean }) {
  if (!show) return null;
  return <span className="inline-flex items-center rounded border border-warn/50 bg-warn/10 px-1.5 py-px text-[10px] font-bold uppercase tracking-wider text-warn"
    title="Fictional company and synthetic data in SEC format — not real SEC data">Demo · synthetic</span>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("skeleton", className)} aria-hidden />;
}

export function LoadingPanel({ rows = 4, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div className="space-y-2" role="status" aria-label={label}>
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-5" />)}
    </div>
  );
}

const CODE_TEXT: Record<string, string> = {
  blocked: "Blocked by network policy", denied: "Refused by data provider", not_found: "Not found",
  rate_limited: "Rate limited", offline: "Offline mode", not_configured: "Not configured", unsupported: "Not supported",
  no_price: "Price required", error: "Retrieval error",
};

export function Unavailable({ error, title, compact }: { error: unknown; title?: string; compact?: boolean }) {
  const plain = !(error instanceof Error) && error && typeof error === "object" ? (error as { status?: string; message?: string; hint?: string }) : null;
  const e = error instanceof ApiError ? error
    : plain ? { message: plain.message ?? "Unavailable", code: plain.status ?? "error", hint: plain.hint ?? "" } : null;
  const msg = e?.message ?? (error instanceof Error ? error.message : String(error ?? "Unavailable"));
  return (
    <div role="alert" className={clsx("flex gap-3 rounded-lg border border-ink-600 bg-ink-850", compact ? "p-3" : "p-4")}>
      <CircleSlash className="mt-0.5 shrink-0 text-na" size={18} aria-hidden />
      <div className="min-w-0 text-sm">
        <div className="font-semibold text-fg">{title ?? (e ? CODE_TEXT[e.code] ?? "Unavailable" : "Unavailable")}</div>
        <div className="mt-0.5 text-fg-2">{msg}</div>
        {e?.hint && <div className="mt-1 text-xs text-fg-3">{e.hint}</div>}
        <div className="mt-1 text-[11px] text-fg-3">No value is shown rather than an invented one.</div>
      </div>
    </div>
  );
}

export function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  return (
    <div className={clsx("flex gap-2 rounded-lg border px-3 py-2 text-xs",
      tone === "warn" ? "border-warn/40 bg-warn/5 text-warn" : "border-ink-600 bg-ink-850 text-fg-2")}>
      {tone === "warn" ? <AlertTriangle size={14} className="mt-px shrink-0" aria-hidden /> : <Info size={14} className="mt-px shrink-0" aria-hidden />}
      <div>{children}</div>
    </div>
  );
}

export function Button({ variant = "secondary", loading, className, children, ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "danger"; loading?: boolean }) {
  return (
    <button {...p} disabled={p.disabled || loading}
      className={clsx("inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-accent text-accent-ink hover:bg-accent-2",
        variant === "secondary" && "border border-ink-600 bg-ink-800 text-fg hover:bg-ink-700",
        variant === "ghost" && "text-fg-2 hover:bg-ink-800 hover:text-fg",
        variant === "danger" && "border border-bad/40 bg-bad/10 text-bad hover:bg-bad/20", className)}>
      {loading && <Loader2 size={14} className="animate-spin" aria-hidden />}{children}
    </button>
  );
}

export function Input(p: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={clsx("w-full rounded-md border border-ink-600 bg-ink-850 px-2.5 py-1.5 text-sm text-fg placeholder:text-fg-3 focus:border-accent focus:outline-none", p.className)} />;
}

export function Select(p: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...p} className={clsx("rounded-md border border-ink-600 bg-ink-850 px-2.5 py-1.5 text-sm text-fg focus:border-accent focus:outline-none", p.className)} />;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-fg-3">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-fg-3">{hint}</span>}
    </label>
  );
}

export function KV({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(110px,40%)_1fr] gap-x-3 gap-y-1.5 text-sm">
      {items.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-fg-3">{k}</dt><dd className="min-w-0 break-words text-fg">{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}
