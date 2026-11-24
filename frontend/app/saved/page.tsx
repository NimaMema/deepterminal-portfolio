"use client";

import { BackendOnly, useDemo } from "@/lib/demo";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Page, PageHeader } from "@/components/company";
import { Button, Input, LoadingPanel, Notice, Panel, Select, SyntheticBadge } from "@/components/ui";
import { api, del, post } from "@/lib/api";
import { date } from "@/lib/format";
import type { Company } from "@/lib/types";

interface Item { id: number; company_id: number | null; company: { name: string; ticker: string; synthetic: boolean } | null; kind: string; ref_id: string | null; title: string; notes: string; tags: string[]; updated_at: string }

function NoteEditor({ item }: { item: Item }) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState(item.notes);
  const save = useMutation({ mutationFn: () => api(`/saved/${item.id}`, { method: "PATCH", json: { notes } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["saved"] }) });
  return (
    <div className="mt-2">
      <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} aria-label={`Notes for ${item.title}`} placeholder="Notes…"
        className="w-full rounded-md border border-ink-600 bg-ink-850 p-2 text-sm text-fg focus:border-accent focus:outline-none" />
      {notes !== item.notes && <Button onClick={() => save.mutate()} loading={save.isPending} className="mt-1">Save notes</Button>}
    </div>
  );
}

export default function Saved() {
  const qc = useQueryClient();
  const isDemo = useDemo();
  const [kind, setKind] = useState("");
  const items = useQuery({ queryKey: ["saved", kind], queryFn: () => api<Item[]>(`/saved${kind ? `?kind=${kind}` : ""}`) });
  const companies = useQuery({ queryKey: ["companies"], queryFn: () => api<Company[]>("/companies") });
  const [note, setNote] = useState({ company_id: "", title: "" });
  const add = useMutation({ mutationFn: () => post("/saved", { company_id: note.company_id ? Number(note.company_id) : null, kind: "note", title: note.title }),
    onSuccess: () => { setNote({ company_id: "", title: "" }); qc.invalidateQueries({ queryKey: ["saved"] }); } });
  const remove = useMutation({ mutationFn: (id: number) => del(`/saved/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["saved"] }) });
  return (
    <Page>
      <PageHeader title="Saved research" description="Watchlist, notes and saved items persist in the database.">
        <Select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Filter"><option value="">All</option>{["watchlist", "note", "investigation", "report", "valuation", "thesis"].map((k) => <option key={k} value={k}>{k}</option>)}</Select>
      </PageHeader>
      {isDemo && <Notice><BackendOnly /> Watchlists and notes are personal, so they need the full local backend. The public demo is shared and read-only.</Notice>}
      {!isDemo && <Panel title="New note">
        <form className="grid gap-2 md:grid-cols-[220px_1fr_auto]" onSubmit={(e) => { e.preventDefault(); if (note.title.trim()) add.mutate(); }}>
          <Select value={note.company_id} onChange={(e) => setNote({ ...note, company_id: e.target.value })} aria-label="Company"><option value="">No company</option>{companies.data?.map((c) => <option key={c.id} value={c.id}>{c.ticker}</option>)}</Select>
          <Input value={note.title} onChange={(e) => setNote({ ...note, title: e.target.value })} placeholder="Title" aria-label="Note title" />
          <Button type="submit" variant="primary" loading={add.isPending}>Add</Button>
        </form>
      </Panel>}
      <Panel title={`Items (${items.data?.length ?? 0})`}>
        {items.isLoading && <LoadingPanel rows={4} />}
        {items.data?.length === 0 && <p className="text-sm text-fg-3">Nothing saved yet.</p>}
        <ul className="grid gap-3 md:grid-cols-2">{items.data?.map((i) => (
          <li key={i.id} className="rounded-lg border border-ink-700 bg-ink-850 p-3">
            <div className="flex items-start gap-2"><span className="rounded bg-ink-700 px-1.5 text-[10px] uppercase tracking-wider text-fg-2">{i.kind}</span>
              <div className="min-w-0 flex-1">{i.company_id ? <Link href={`/company/${i.company_id}`} className="font-medium hover:underline">{i.title}</Link> : <span className="font-medium">{i.title}</span>}
                <div className="text-[11px] text-fg-3">{i.company?.ticker} · updated {date(i.updated_at)} <SyntheticBadge show={!!i.company?.synthetic} /></div></div>
              <button onClick={() => remove.mutate(i.id)} aria-label={`Delete ${i.title}`} className="text-fg-3 hover:text-bad"><Trash2 size={14} /></button></div>
            <NoteEditor item={i} />
          </li>))}</ul>
      </Panel>
    </Page>
  );
}
