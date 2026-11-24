"use client";

import { BackendOnly, useDemo } from "@/lib/demo";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FileSearch, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Page, PageHeader, useCompanyId } from "@/components/company";
import { Button, Input, LoadingPanel, Notice, Panel, Select, Unavailable } from "@/components/ui";
import { api, post } from "@/lib/api";
import { date } from "@/lib/format";

interface FilingRow { id: number; accession: string; form: string; filed: string; report_date: string | null; url: string; items: { code: string; description: string }[]; text_status: string; synthetic: boolean }
interface Doc { accession: string; form: string; filed: string; url: string; retrieved_at: string | null; synthetic: boolean; untrusted_notice: string; sections: { key: string; title: string; chars: number; sha256: string; text: string }[] }
interface Hit { section_id: number; key: string; title: string; accession: string; form: string; filed: string; url: string; snippet: string; rank: number }

function Snippet({ s }: { s: string }) {
  const parts = s.split(/(<<|>>)/);
  let on = false;
  return <>{parts.map((p, i) => { if (p === "<<") { on = true; return null; } if (p === ">>") { on = false; return null; } return on ? <mark key={i}>{p}</mark> : <span key={i}>{p}</span>; })}</>;
}

export default function FilingsExplorer() {
  const id = useCompanyId();
  const qc = useQueryClient();
  const isDemo = useDemo();
  const [form, setForm] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [sectionKey, setSectionKey] = useState<string>("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const filings = useQuery({ queryKey: ["filings", id, form], queryFn: () => api<FilingRow[]>(`/companies/${id}/filings?limit=400${form ? `&form=${encodeURIComponent(form)}` : ""}`) });
  const doc = useQuery({ queryKey: ["doc", id, sel], enabled: !!sel, queryFn: () => api<Doc>(`/companies/${id}/filings/${sel}`) });
  const hits = useQuery({ queryKey: ["fts", id, query], enabled: query.length > 1, queryFn: () => api<{ results: Hit[] }>(`/companies/${id}/search?q=${encodeURIComponent(query)}`) });
  const index = useMutation({ mutationFn: () => post<{ indexed: unknown[] }>(`/companies/${id}/filings/index`, { forms: ["10-K", "10-Q", "8-K", "DEF 14A"], limit: 12 }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["filings", id] }); qc.invalidateQueries({ queryKey: ["fts", id] }); } });
  const forms = useMemo(() => Array.from(new Set((filings.data ?? []).map((f) => f.form))).sort(), [filings.data]);
  const section = doc.data?.sections.find((s) => s.key === (sectionKey || doc.data?.sections.find((x) => x.key !== "full")?.key || "full")) ?? doc.data?.sections[0];
  return (
    <Page>
      <PageHeader title="SEC filing explorer" description="Every filing on EDGAR for this registrant. Retrieve documents to read them, search across their text, and cite passages as evidence.">
        {isDemo ? <BackendOnly what="Indexing more filings: full local backend" /> : <Button onClick={() => index.mutate()} loading={index.isPending}><FileSearch size={14} aria-hidden />Index recent filings for search</Button>}
      </PageHeader>
      {index.error && <Unavailable error={index.error} compact />}
      {index.data && <Notice>Indexed {index.data.indexed.length} filings for full-text search.</Notice>}
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }}>
        <div className="relative flex-1"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-3" aria-hidden />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder='Full-text search, e.g. "sole source" OR tariff' aria-label="Search filing text" className="pl-9" /></div>
        <Button type="submit" variant="primary">Search</Button>
      </form>
      {query && (
        <Panel title={`Search results for “${query}”`} subtitle="Postgres full-text search over retrieved filing sections">
          {hits.isLoading && <LoadingPanel rows={3} />}
          {hits.error && <Unavailable error={hits.error} compact />}
          {hits.data?.results.length === 0 && <p className="text-sm text-fg-3">No matches in indexed text. Index more filings above, then search again.</p>}
          <ul className="space-y-2">{hits.data?.results.map((h) => (
            <li key={h.section_id}><button onClick={() => { setSel(h.accession); setSectionKey(h.key); }} className="w-full rounded-lg border border-ink-700 bg-ink-850 p-3 text-left hover:border-accent/50">
              <div className="flex flex-wrap items-center gap-2 text-xs"><span className="num font-semibold text-accent">{h.form}</span><span className="text-fg-3">{date(h.filed)} · {h.title}</span></div>
              <p className="mt-1 whitespace-pre-line text-[13px] text-fg-2"><Snippet s={h.snippet} /></p></button></li>))}</ul>
        </Panel>
      )}
      <div className="grid gap-4 xl:grid-cols-[minmax(320px,420px)_1fr]">
        <Panel title="Filings" subtitle={filings.data ? `${filings.data.length} filings` : undefined} dense
          actions={<Select value={form} onChange={(e) => setForm(e.target.value)} aria-label="Filter by form"><option value="">All forms</option>{forms.map((f) => <option key={f}>{f}</option>)}</Select>}>
          {filings.isLoading && <div className="p-4"><LoadingPanel rows={10} /></div>}
          {filings.error && <div className="p-4"><Unavailable error={filings.error} /></div>}
          <ul className="scroll-thin max-h-[70vh] divide-y divide-ink-800 overflow-y-auto">{filings.data?.map((f) => (
            <li key={f.accession}><button onClick={() => { setSel(f.accession); setSectionKey(""); }} aria-current={sel === f.accession}
              className={`flex w-full items-start gap-3 px-4 py-2 text-left text-sm hover:bg-ink-850 ${sel === f.accession ? "bg-accent/5" : ""}`}>
              <span className="num w-16 shrink-0 font-semibold text-accent">{f.form}</span>
              <span className="min-w-0 flex-1"><span className="block truncate text-fg-2">{f.items.length ? f.items.map((i) => `${i.code} ${i.description}`).join(" · ") : f.report_date ? `Period ${date(f.report_date)}` : f.accession}</span>
                <span className="num block text-[11px] text-fg-3">{f.accession}{f.text_status === "fetched" ? " · indexed" : ""}</span></span>
              <span className="num shrink-0 text-[11px] text-fg-3">{date(f.filed)}</span></button></li>))}</ul>
        </Panel>
        <Panel title={doc.data ? `${doc.data.form} filed ${date(doc.data.filed)}` : "Document viewer"} subtitle={doc.data?.accession}
          actions={doc.data && <a href={doc.data.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs text-accent hover:underline">EDGAR <ExternalLink size={11} /></a>}>
          {!sel && <p className="text-sm text-fg-3">Select a filing to retrieve and read it.</p>}
          {doc.isLoading && <LoadingPanel rows={10} label="Retrieving document" />}
          {doc.error && <Unavailable error={doc.error} />}
          {doc.data && (
            <div>
              <div className="mb-3 flex flex-wrap gap-1" role="tablist" aria-label="Sections">
                {doc.data.sections.map((s) => (
                  <button key={s.key} role="tab" aria-selected={section?.key === s.key} onClick={() => setSectionKey(s.key)}
                    className={`rounded-md px-2 py-1 text-xs ${section?.key === s.key ? "bg-accent/15 text-accent" : "text-fg-3 hover:bg-ink-800"}`}>
                    {s.key === "full" ? "Full document" : s.title.slice(0, 40)}</button>))}
              </div>
              <Notice>{doc.data.untrusted_notice} Retrieved {doc.data.retrieved_at?.slice(0, 16).replace("T", " ")} UTC · sha256 {section?.sha256.slice(0, 16)}…</Notice>
              <article className="scroll-thin mt-3 max-h-[64vh] overflow-y-auto whitespace-pre-wrap rounded-lg border border-ink-700 bg-ink-950 p-4 text-[13px] leading-relaxed text-fg-2">
                {section?.text}
              </article>
            </div>
          )}
        </Panel>
      </div>
    </Page>
  );
}
