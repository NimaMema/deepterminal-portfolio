"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { CheckCircle2, CircleDashed, Loader2, OctagonX, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, post } from "@/lib/api";
import type { Job } from "@/lib/types";
import { Button } from "./ui";

interface Ev { id: number; ts: string; level: string; module: string | null; message: string }

/** Live job progress: server-sent events with automatic fallback to polling. */
export function useJobLive(jobId: string | null) {
  const qc = useQueryClient();
  const [events, setEvents] = useState<Ev[]>([]);
  const [sse, setSse] = useState(true);
  const job = useQuery({ queryKey: ["job", jobId], enabled: !!jobId, queryFn: () => api<Job>(`/jobs/${jobId}`),
    refetchInterval: (q) => (!sse && q.state.data && ["queued", "running"].includes(q.state.data.status) ? 1000 : false) });
  useEffect(() => { setEvents([]); setSse(true); }, [jobId]);
  useEffect(() => { if (job.data?.events) setEvents((prev) => (job.data!.events!.length > prev.length ? job.data!.events! : prev)); }, [job.data]);
  useEffect(() => {
    if (!jobId || typeof EventSource === "undefined") { setSse(false); return; }
    const es = new EventSource(`/api/jobs/${jobId}/stream`);
    es.addEventListener("log", (e) => { const d = JSON.parse((e as MessageEvent).data) as Ev; setEvents((p) => (p.some((x) => x.id === d.id) ? p : [...p, d])); });
    es.addEventListener("status", (e) => {
      const st = JSON.parse((e as MessageEvent).data);
      qc.setQueryData<Job>(["job", jobId], (old) => (old ? { ...old, ...st } : old));
      if (st && ["succeeded", "failed", "cancelled"].includes(st.status)) { es.close(); job.refetch(); qc.invalidateQueries({ queryKey: ["findings"] }); qc.invalidateQueries({ queryKey: ["graph"] }); }
    });
    es.onerror = () => { es.close(); setSse(false); };
    return () => es.close();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);
  return { job: job.data, events, transport: sse ? "live stream" : "polling" };
}

export function JobProgress({ jobId, modules }: { jobId: string; modules?: { key: string; title: string }[] }) {
  const { job, events, transport } = useJobLive(jobId);
  const logRef = useRef<HTMLOListElement>(null);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight }); }, [events.length]);
  if (!job) return <div className="skeleton h-24" />;
  const running = ["queued", "running"].includes(job.status);
  const modState = (key: string) => {
    const evs = events.filter((e) => e.module === key);
    if (!evs.length) return "pending";
    const last = evs[evs.length - 1];
    if (last.level === "error") return "error";
    if (last.level === "warning") return "unavailable";
    return last.message.startsWith("Running") ? "running" : "done";
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className={clsx("inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-semibold uppercase tracking-wider",
          job.status === "succeeded" ? "bg-good/10 text-good" : job.status === "failed" ? "bg-bad/10 text-bad" : job.status === "cancelled" ? "bg-ink-700 text-fg-3" : "bg-accent/10 text-accent")}>
          {running && <Loader2 size={12} className="animate-spin" aria-hidden />}{job.status}</span>
        <span className="text-sm text-fg-2" aria-live="polite">{job.current_step}</span>
        <span className="ml-auto text-[11px] text-fg-3">{transport}</span>
        {running && <Button variant="danger" onClick={() => post(`/jobs/${jobId}/cancel`, {})}>Cancel</Button>}
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-ink-700" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(job.progress * 100)} aria-label="Job progress">
        <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${Math.max(2, job.progress * 100)}%` }} />
      </div>
      {job.error && <p className="text-sm text-bad">{job.error}</p>}
      {modules && (
        <ul className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">{modules.map((m) => {
          const st = modState(m.key);
          return (
            <li key={m.key} className="flex items-center gap-2 rounded-md border border-ink-700 bg-ink-850 px-2.5 py-1.5 text-xs">
              {st === "done" ? <CheckCircle2 size={14} className="text-good" aria-hidden /> : st === "running" ? <Loader2 size={14} className="animate-spin text-accent" aria-hidden />
                : st === "error" ? <OctagonX size={14} className="text-bad" aria-hidden /> : st === "unavailable" ? <TriangleAlert size={14} className="text-warn" aria-hidden />
                : <CircleDashed size={14} className="text-fg-3" aria-hidden />}
              <span className={st === "pending" ? "text-fg-3" : "text-fg-2"}>{m.title}</span><span className="sr-only">{st}</span>
            </li>);
        })}</ul>
      )}
      <ol ref={logRef} className="scroll-thin max-h-56 space-y-0.5 overflow-y-auto rounded-lg border border-ink-700 bg-ink-950 p-2 font-mono text-[11.5px]" aria-label="Job log">
        {events.map((e) => (
          <li key={e.id} className={e.level === "error" ? "text-bad" : e.level === "warning" ? "text-warn" : "text-fg-2"}>
            <span className="text-fg-3">{e.ts.slice(11, 19)}</span> {e.module ? <span className="text-accent">[{e.module}]</span> : null} {e.message}</li>))}
      </ol>
    </div>
  );
}
