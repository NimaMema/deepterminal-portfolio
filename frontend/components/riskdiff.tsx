"use client";

import { useState } from "react";

export interface DiffResult {
  key: string; from: { accession: string; filed: string; url: string }; to: { accession: string; filed: string; url: string };
  counts: Record<string, number>;
  diff: { added: { text: string }[]; removed: { text: string }[]; modified: { text: string; previous: string; similarity: number }[]; unchanged: { text: string }[] };
}

export function RiskDiff({ d }: { d: DiffResult }) {
  const [tab, setTab] = useState<"added" | "removed" | "modified">("added");
  const items = d.diff[tab];
  return (
    <div>
      <p className="mb-2 text-xs text-fg-3">Comparing 10-K filed {d.from.filed} ({d.from.accession}) → {d.to.filed} ({d.to.accession}). Paragraph matching: ≥97% similar = unchanged, 60–97% = modified.</p>
      <div className="mb-3 flex gap-1" role="tablist" aria-label="Change type">
        {(["added", "removed", "modified"] as const).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
            className={`rounded-md px-2.5 py-1 text-xs capitalize ${tab === t ? (t === "added" ? "bg-good/15 text-good" : t === "removed" ? "bg-bad/15 text-bad" : "bg-warn/15 text-warn") : "text-fg-3 hover:bg-ink-800"}`}>
            {t} <span className="num">{d.counts[t]}</span></button>))}
        <span className="ml-auto self-center text-xs text-fg-3">{d.counts.unchanged} unchanged</span>
      </div>
      {items.length === 0 && <p className="text-sm text-fg-3">None.</p>}
      <ul className="space-y-2">{items.map((it, i) => (
        <li key={i} className={`rounded-md border-l-2 bg-ink-850 p-3 text-[13px] leading-relaxed ${tab === "added" ? "border-good" : tab === "removed" ? "border-bad" : "border-warn"}`}>
          {it.text}
          {"previous" in it && <details className="mt-1 text-xs text-fg-3"><summary className="cursor-pointer">Previous wording ({Math.round((it as { similarity: number }).similarity * 100)}% similar)</summary><p className="mt-1">{(it as { previous: string }).previous}</p></details>}
        </li>))}</ul>
    </div>
  );
}
