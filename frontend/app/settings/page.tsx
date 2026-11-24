"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Page, PageHeader } from "@/components/company";
import { Button, KV, LoadingPanel, Notice, Panel } from "@/components/ui";
import { api, post } from "@/lib/api";
import { num } from "@/lib/format";

interface Status { data_mode: string; synthetic: boolean; offline: boolean; sec_user_agent_configured: boolean; llm_tokens_today: number; llm_daily_budget: number;
  llm_limits: Record<string, number>; providers: { provider: string; model: string; configured: boolean; active: boolean; key_env: string | null; paid: boolean; detail: string }[]; paid_apis_enabled: boolean; modules: { key: string; title: string; capability: string }[] }
interface Sources { sources: { id: string; name: string; hosts: string[]; licence: string; cost: string; limits?: string; status: string; detail: string; configured: boolean; env?: string }[];
  network_note: string | null; cost_policy: { paid_apis_enabled: boolean; llm_provider: string; summary: string } }

export default function Settings() {
  const status = useQuery({ queryKey: ["status"], queryFn: () => api<Status>("/status") });
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api<Sources>("/sources") });
  const log = useQuery({ queryKey: ["fetch-log"], queryFn: () => api<{ adapter: string; url: string; status: string; retrieved_at: string; detail: string | null }[]>("/fetch-log?limit=25") });
  const probe = useMutation({ mutationFn: () => post<{ status: string; message?: string; hint?: string; companies?: number }>("/sources/sec_edgar/probe", {}), onSuccess: () => { sources.refetch(); log.refetch(); } });
  const s = status.data;
  return (
    <Page>
      <PageHeader title="Settings & data sources" description="Secrets are configured through environment variables on the server and are never displayed or stored in the browser." />
      {status.isLoading && <LoadingPanel rows={6} />}
      {sources.data && (
        <div role="status" className={`rounded-xl border p-3 text-sm ${sources.data.cost_policy.paid_apis_enabled ? "border-bad/50 bg-bad/10 text-bad" : "border-good/40 bg-good/5 text-good"}`}>
          <b>{sources.data.cost_policy.paid_apis_enabled ? "Paid APIs enabled." : "Zero-cost mode."}</b> {sources.data.cost_policy.summary}
          {!sources.data.cost_policy.paid_apis_enabled && <span className="text-fg-3"> Paid providers stay off unless you set <code className="num">DEEPTERMINAL_ALLOW_PAID_APIS=true</code> and select one explicitly.</span>}
        </div>
      )}
      {s && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Data mode">
            <KV items={[["Mode", s.synthetic ? "DEMO — synthetic companies in SEC format" : "LIVE — SEC EDGAR"], ["Offline replay", s.offline ? "on" : "off"],
              ["SEC User-Agent", s.sec_user_agent_configured ? "configured" : "not set (required for live mode)"]]} />
            <Notice>Switch modes with <code className="num">DEEPTERMINAL_DATA_MODE=live|demo</code> and set <code className="num">DEEPTERMINAL_SEC_USER_AGENT=&quot;Your Name you@example.com&quot;</code>, then restart the API.</Notice>
            <div className="mt-3 flex items-center gap-2"><Button onClick={() => probe.mutate()} loading={probe.isPending}>Test SEC connection</Button>
              {probe.data && <span className={`text-xs ${probe.data.status === "ok" ? "text-good" : "text-warn"}`}>{probe.data.status}{probe.data.companies ? ` · ${num(probe.data.companies)} registrants` : ""} {probe.data.message}</span>}</div>
          </Panel>
          <Panel title="AI engine" subtitle="Local open-weight models through Ollama by default; paid APIs are opt-in only">
            <ul className="space-y-2">{s.providers.map((p) => (
              <li key={p.provider} className="rounded-lg border border-ink-700 bg-ink-850 p-2.5 text-sm">
                <div className="flex items-center gap-3"><span className="w-20 font-medium capitalize">{p.provider}</span><span className="num text-xs text-fg-3">{p.model}</span>
                  <span className={`rounded px-1.5 text-[10px] font-bold uppercase ${p.paid ? "bg-bad/10 text-bad" : "bg-good/10 text-good"}`}>{p.paid ? "paid" : "free"}</span>
                  <span className={`ml-auto text-xs ${p.active ? "text-accent" : p.configured ? "text-good" : "text-fg-3"}`}>{p.active ? "active" : p.configured ? "ready" : "off"}</span></div>
                <p className="mt-1 text-[11px] text-fg-3">{p.detail}</p></li>))}</ul>
            <div className="mt-3"><KV items={[["Paid-API tokens today", `${num(s.llm_tokens_today)} / ${num(s.llm_daily_budget)}`], ["Max tool calls per agent run", num(s.llm_limits.max_tool_calls)],
              ["Max input tokens per job", num(s.llm_limits.max_input_tokens_per_job)], ["Max output tokens per call", num(s.llm_limits.max_output_tokens)]]} /></div>
          </Panel>
        </div>
      )}
      <Panel title="Data sources" subtitle={sources.data?.network_note ?? undefined}>
        {sources.isLoading && <LoadingPanel rows={5} />}
        <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="text-left text-[11px] uppercase text-fg-3"><th className="py-2">Source</th><th>Status</th><th>Hosts</th><th>Licence / cost</th><th>Free-tier limits</th><th>Detail</th></tr></thead>
          <tbody>{sources.data?.sources.map((x) => (
            <tr key={x.id} className="border-t border-ink-800 align-top"><td className="py-2 pr-3 font-medium">{x.name}</td>
              <td className={`pr-3 text-xs font-semibold uppercase ${["ok", "cache", "configured", "ready"].includes(x.status) ? "text-good" : x.status === "demo" ? "text-warn" : "text-fg-3"}`}>{x.status.replace(/_/g, " ")}</td>
              <td className="num pr-3 text-xs text-fg-3">{x.hosts.join(", ") || "—"}</td><td className="pr-3 text-xs text-fg-2">{x.licence} · <span className={x.cost.startsWith("PAID") ? "text-bad" : ""}>{x.cost}</span></td>
              <td className="pr-3 text-xs text-fg-3">{x.limits ?? "—"}</td><td className="text-xs text-fg-3">{x.detail}</td></tr>))}</tbody></table></div>
      </Panel>
      <Panel title="Retrieval log" subtitle="Every external request, with outcome">
        <ul className="space-y-1 font-mono text-[11.5px]">{log.data?.map((l, i) => (
          <li key={i} className="truncate"><span className="text-fg-3">{l.retrieved_at.slice(0, 19)}</span> <span className={l.status === "ok" || l.status === "cache" ? "text-good" : "text-warn"}>{l.status}</span> <span className="text-fg-2">{l.url}</span></li>))}</ul>
        {log.data?.length === 0 && <p className="text-sm text-fg-3">No external requests yet (demo mode serves local synthetic data).</p>}
      </Panel>
      {s && <Panel title="Research capabilities"><ul className="grid gap-1 text-sm sm:grid-cols-2 lg:grid-cols-3">{s.modules.map((m) => <li key={m.key} className="text-fg-2">• {m.title}</li>)}</ul></Panel>}
    </Page>
  );
}
