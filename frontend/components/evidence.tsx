"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileText, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { date, num } from "@/lib/format";
import type { Evidence, Finding } from "@/lib/types";
import { EpistemicBadge, LoadingPanel, SeverityBadge, Unavailable, VerificationBadge } from "./ui";

const Ctx = createContext<(id: number) => void>(() => {});
export const useEvidence = () => useContext(Ctx);

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [id, setId] = useState<number | null>(null);
  const open = useCallback((i: number) => setId(i), []);
  return (
    <Ctx.Provider value={open}>
      {children}
      <Dialog.Root open={id !== null} onOpenChange={(o) => !o && setId(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px]" />
          <Dialog.Content className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col border-l border-ink-600 bg-ink-900 shadow-2xl focus:outline-none"
            aria-describedby={undefined}>
            {id !== null && <EvidenceView id={id} onOpen={setId} />}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </Ctx.Provider>
  );
}

function Highlighted({ text, excerpt }: { text: string; excerpt: string | null }) {
  const ref = useRef<HTMLElement>(null);
  const parts = useMemo(() => {
    if (!excerpt) return null;
    const norm = (s: string) => s.replace(/\s+/g, " ");
    const t = norm(text), x = norm(excerpt).trim();
    const i = t.toLowerCase().indexOf(x.toLowerCase());
    return i < 0 ? null : [t.slice(Math.max(0, i - 2500), i), t.slice(i, i + x.length), t.slice(i + x.length, i + x.length + 2500)];
  }, [text, excerpt]);
  useEffect(() => { ref.current?.scrollIntoView({ block: "center" }); }, [parts]);
  if (!parts) return <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-fg-2">{text.slice(0, 6000)}</p>;
  return (
    <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-fg-2">
      {parts[0]}<mark ref={ref}>{parts[1]}</mark>{parts[2]}
    </p>
  );
}

function EvidenceView({ id, onOpen }: { id: number; onOpen: (i: number) => void }) {
  const q = useQuery({ queryKey: ["evidence", id], queryFn: () => api<Evidence>(`/evidence/${id}`) });
  const e = q.data;
  const inputs = (e?.data?.inputs as number[] | undefined) ?? [];
  return (
    <>
      <header className="flex items-start justify-between gap-4 border-b border-ink-700 px-5 py-4">
        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent">Evidence E{id}</div>
          <Dialog.Title className="mt-1 text-[15px] font-semibold text-fg">{e?.title ?? "Loading…"}</Dialog.Title>
        </div>
        <Dialog.Close className="rounded p-1 text-fg-3 hover:bg-ink-800 hover:text-fg" aria-label="Close evidence"><X size={18} /></Dialog.Close>
      </header>
      <div className="scroll-thin flex-1 space-y-5 overflow-y-auto px-5 py-4">
        {q.isLoading && <LoadingPanel rows={6} />}
        {q.error && <Unavailable error={q.error} />}
        {e && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <EpistemicBadge s={e.epistemic_status} /><VerificationBadge s={e.verification_status} />
              {e.source?.synthetic && <span className="rounded border border-warn/50 bg-warn/10 px-1.5 text-[10px] font-bold uppercase text-warn">Synthetic demo source</span>}
            </div>
            {e.value !== null && (
              <div className="rounded-lg border border-ink-700 bg-ink-850 p-3">
                <div className="text-[11px] uppercase tracking-wider text-fg-3">Value</div>
                <div className="num mt-1 text-xl font-semibold">{num(e.value, 2)} <span className="text-sm text-fg-3">{e.unit}</span></div>
              </div>
            )}
            {e.source && (
              <div className="rounded-lg border border-ink-700 bg-ink-850 p-3 text-sm">
                <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-fg-3"><FileText size={13} aria-hidden />Original source</div>
                <div className="font-medium text-fg">{e.source.title}</div>
                <div className="text-fg-3">{e.source.publisher}</div>
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <dt className="text-fg-3">Published</dt><dd>{date(e.source.published_at)}</dd>
                  <dt className="text-fg-3">Retrieved</dt><dd>{e.source.retrieved_at ? new Date(e.source.retrieved_at).toISOString().replace("T", " ").slice(0, 16) + " UTC" : "—"}</dd>
                  <dt className="text-fg-3">Period</dt><dd>{date(e.source.period_end)}</dd>
                  <dt className="text-fg-3">Document ref.</dt><dd className="num break-all">{e.source.accession ?? e.locator ?? "—"}</dd>
                  <dt className="text-fg-3">Licence</dt><dd>{e.source.licence ?? "—"}</dd>
                </dl>
                {e.source.url && (
                  <a href={e.source.url} target="_blank" rel="noopener noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs text-accent hover:underline">
                    Open at source <ExternalLink size={12} aria-hidden />
                  </a>
                )}
              </div>
            )}
            {e.locator && <div className="text-xs"><span className="text-fg-3">Locator · </span><span className="num break-all text-fg-2">{e.locator}</span></div>}
            {e.limitations && <div className="rounded-lg border border-warn/30 bg-warn/5 p-3 text-xs text-warn"><b>Limitations.</b> {e.limitations}</div>}
            {inputs.length > 0 && (
              <div className="text-xs">
                <div className="mb-1 text-fg-3">Computed from evidence:</div>
                <div className="flex flex-wrap gap-1">{inputs.slice(0, 40).map((i) => <Cite key={i} id={i} onClick={() => onOpen(i)} />)}</div>
              </div>
            )}
            {e.excerpt && !e.context && (
              <blockquote className="border-l-2 border-accent pl-3 text-[13px] leading-relaxed text-fg-2">{e.excerpt}</blockquote>
            )}
            {e.context && (
              <div>
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-fg-3">In context · {e.context.section_title}
                  <span className="ml-2 font-normal normal-case tracking-normal">sha256 {e.context.sha256.slice(0, 12)}…</span></div>
                <div className="rounded-lg border border-ink-700 bg-ink-950 p-3 text-fg-3"><p className="mb-2 text-[11px]">Retrieved document text (untrusted data, shown as-is):</p>
                  <Highlighted text={e.context.text} excerpt={e.excerpt} /></div>
              </div>
            )}
            <div className="text-[11px] text-fg-3">Recorded by {e.created_by} · {date(e.created_at)}</div>
          </>
        )}
      </div>
    </>
  );
}

export function Cite({ id, onClick }: { id: number; onClick?: () => void }) {
  const open = useEvidence();
  return (
    <button type="button" onClick={onClick ?? (() => open(id))}
      className="num inline-flex items-center rounded border border-accent/30 bg-accent/5 px-1 text-[10.5px] leading-[1.35rem] text-accent hover:bg-accent/15"
      aria-label={`Open evidence E${id}`}>E{id}</button>
  );
}

/** Render text with [E123] markers turned into clickable citations, plus minimal formatting of model
 *  output: **bold** and "### heading" lines. Text is rendered as React text nodes, never as HTML. */
export function CitedText({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <>{lines.map((line, li) => {
      const heading = /^#{1,4}\s+/.test(line);
      const body = line.replace(/^#{1,4}\s+/, "");
      const parts = body.split(/(\[E\d+\]|\*\*[^*\n]+\*\*)/g);
      const nodes = parts.map((p, i) => {
        const m = p.match(/^\[E(\d+)\]$/);
        if (m) return <Cite key={i} id={Number(m[1])} />;
        const b = p.match(/^\*\*([^*]+)\*\*$/);
        return b ? <strong key={i} className="font-semibold text-fg">{b[1]}</strong> : <span key={i}>{p}</span>;
      });
      return <span key={li}>{heading ? <strong className="font-semibold text-fg">{nodes}</strong> : nodes}{li < lines.length - 1 ? "\n" : ""}</span>;
    })}</>
  );
}

export function FindingCard({ f, compact }: { f: Finding; compact?: boolean }) {
  return (
    <article className="rounded-lg border border-ink-700 bg-ink-850 p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <SeverityBadge s={f.severity} /><EpistemicBadge s={f.epistemic_status} />
        <span className="text-[10px] uppercase tracking-wider text-fg-3">{f.module.replace(/_/g, " ")} · {f.confidence} confidence</span>
      </div>
      <h3 className="mt-1.5 text-[13.5px] font-semibold leading-snug text-fg">{f.title}</h3>
      {!compact && <p className="mt-1 whitespace-pre-line text-[13px] leading-relaxed text-fg-2"><CitedText text={f.summary.slice(0, 1600)} /></p>}
      {f.evidence_ids.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-1"><span className="text-[11px] text-fg-3">Evidence</span>
          {f.evidence_ids.slice(0, 12).map((i) => <Cite key={i} id={i} />)}
          {f.evidence_ids.length > 12 && <span className="text-[11px] text-fg-3">+{f.evidence_ids.length - 12}</span>}
        </div>
      )}
      {f.limitations && !compact && <p className="mt-1.5 text-[11.5px] text-fg-3">Limitation: {f.limitations}</p>}
      {f.generated_by !== "rules" && <p className="mt-1 text-[11px] text-violet">Generated by {f.generated_by}</p>}
    </article>
  );
}

export function FindingsList({ findings, empty }: { findings: Finding[]; empty?: string }) {
  const [sev, setSev] = useState<string>("all");
  const order: Record<string, number> = { concern: 0, watch: 1, positive: 2, neutral: 3, unavailable: 4 };
  const shown = findings.filter((f) => sev === "all" || f.severity === sev).sort((a, b) => order[a.severity] - order[b.severity]);
  if (!findings.length) return <p className="text-sm text-fg-3">{empty ?? "No findings yet. Run an investigation to generate evidence-backed findings."}</p>;
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1" role="group" aria-label="Filter findings by severity">
        {["all", "concern", "watch", "positive", "neutral", "unavailable"].map((s) => {
          const n = s === "all" ? findings.length : findings.filter((f) => f.severity === s).length;
          return (
            <button key={s} onClick={() => setSev(s)} aria-pressed={sev === s}
              className={`rounded-md px-2 py-1 text-xs capitalize ${sev === s ? "bg-ink-600 text-fg" : "text-fg-3 hover:bg-ink-800"}`}>
              {s} <span className="num text-fg-3">{n}</span>
            </button>
          );
        })}
      </div>
      <div className="space-y-2">{shown.map((f) => <FindingCard key={f.id} f={f} />)}</div>
    </div>
  );
}

export function ModuleFindings({ companyId, module, title = "Investigation findings" }: { companyId: number; module: string; title?: string }) {
  const q = useQuery({ queryKey: ["findings", companyId, module], queryFn: () => api<Finding[]>(`/companies/${companyId}/findings?module=${module}`) });
  return (
    <section className="rounded-xl border border-ink-700/80 bg-ink-900/80 p-4" aria-label={title}>
      <h2 className="mb-3 text-[13px] font-semibold">{title}</h2>
      {q.isLoading ? <LoadingPanel rows={3} /> : <FindingsList findings={q.data ?? []}
        empty="No findings yet for this module. Run an investigation from the Investigation screen to generate evidence-backed findings." />}
    </section>
  );
}
