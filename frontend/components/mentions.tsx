"use client";

import { ExternalLink } from "lucide-react";
import { useModule } from "@/lib/api";
import { date } from "@/lib/format";
import { LoadingPanel, Panel, Unavailable } from "./ui";

interface Mentions {
  phrase: string; total_hits: number; other_filers: number; documents_read: number; method: string; search_url: string;
  by_relation: Record<string, number>;
  mentions: { filer: string; form: string; filed: string; url: string; text: string; relation: string }[];
}

/** Other companies' annual reports that name this company (EDGAR full-text search — free). */
export function MentionsPanel({ companyId }: { companyId: number }) {
  const q = useModule<Mentions>(companyId, "external_mentions");
  const d = q.data?.data;
  return (
    <Panel title="Who names this company" subtitle="Other filers' 10-Ks that mention it, quoted — from EDGAR full-text search (free)">
      {q.isLoading && <LoadingPanel rows={4} />}
      {q.error && <Unavailable error={q.error} />}
      {d && (
        <div className="space-y-3">
          <p className="text-xs text-fg-3">“{d.phrase}” in {d.total_hits} filings by {d.other_filers} other companies (last 18 months); {d.documents_read} read.{" "}
            {Object.entries(d.by_relation).map(([k, v]) => `${v} ${k}`).join(" · ")}</p>
          <ul className="space-y-2">{d.mentions.map((m, i) => (
            <li key={i} className="rounded-lg border border-ink-700 bg-ink-850 p-3 text-[13px]">
              <div className="flex flex-wrap items-baseline gap-x-2 text-xs"><span className="font-semibold text-fg">{m.filer}</span>
                <span className="text-accent">{m.relation}</span><span className="text-fg-3">{m.form} filed {date(m.filed)}</span>
                <a href={m.url} target="_blank" rel="noopener noreferrer" className="ml-auto inline-flex items-center gap-1 text-accent hover:underline">filing <ExternalLink size={11} aria-hidden /></a></div>
              <blockquote className="mt-1 border-l-2 border-ink-600 pl-2 text-fg-2">{m.text}</blockquote></li>))}</ul>
          <p className="text-[11px] text-fg-3">{d.method}</p>
        </div>
      )}
    </Panel>
  );
}
