"use client";

import { Page, PageHeader, useCompany, useCompanyId } from "@/components/company";
import { ModuleFindings } from "@/components/evidence";
import { KV, LoadingPanel, Notice, Panel, Unavailable } from "@/components/ui";
import { useModule } from "@/lib/api";
import { date } from "@/lib/format";

interface Corp {
  identity: Record<string, string | string[] | number | null>; former_names: { name: string; from?: string; to?: string }[];
  addresses: Record<string, Record<string, string>>; filing_regularity: { annual_report_years: number[]; missing_years: number[]; first_10k: number | null };
  subsidiaries: { subsidiaries: { name: string; jurisdiction: string }[]; accession?: string; filed?: string; url?: string; unavailable?: { message: string } };
  auditor_changes: { accession: string; filed: string }[]; insolvency_events: { accession: string; filed: string; items: { code: string; description: string }[] }[];
  going_concern: { filed: string; text: string }[]; legal_proceedings: { filed: string; text: string } | null;
  beneficial_ownership_filings: { form: string; filed: string; url: string }[];
  not_connected: { check: string; adapter: string; status: string; reason: string }[]; parent_company: { status: string; reason: string };
  sanctions?: { status: string; message?: string; hint?: string; screened?: number; list_size?: number; matches?: { screened: string; name: string; program: string }[]; retrieved_at?: string; method?: string };
  website_history?: { status: string; message?: string; hint?: string; site?: string; first?: { timestamp: string; url: string } | null; latest?: { timestamp: string; url: string } | null };
}

export default function Corporate() {
  const id = useCompanyId();
  const c = useCompany();
  const m = useModule<Corp>(id, "corporate_legitimacy");
  const d = m.data?.data;
  return (
    <Page>
      <PageHeader title="Corporate intelligence" description="Who the registrant is, how its identity changed, how it is structured, and whether its filing record shows warning signs." />
      {m.isLoading && <LoadingPanel rows={8} />}
      {m.error && <Unavailable error={m.error} />}
      {d && (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <Panel title="Registration & identity" subtitle={`SEC submissions record · retrieved ${date(String(d.identity.profile_retrieved_at ?? ""))}`}>
              <KV items={[["Legal name", d.identity.name as string], ["CIK", String(d.identity.cik).padStart(10, "0")], ["Ticker", d.identity.ticker as string],
                ["Entity type", d.identity.entity_type as string], ["Incorporated", d.identity.state_of_incorporation as string], ["EIN", d.identity.ein as string],
                ["Filer category", d.identity.category as string], ["Exchanges", (d.identity.exchanges as string[] | null)?.join(", ")],
                ["Industry (SIC)", `${d.identity.sic_description ?? ""} (${d.identity.sic ?? "—"})`], ["Website", d.identity.website as string]]} />
            </Panel>
            <Panel title="Locations" subtitle="Business and mailing addresses on file">
              {Object.entries(d.addresses).map(([k, a]) => (
                <div key={k} className="mb-3 text-sm"><div className="text-[11px] uppercase tracking-wider text-fg-3">{k}</div>
                  <div className="text-fg-2">{[a.street1, a.street2, a.city, a.stateOrCountry, a.zipCode].filter(Boolean).join(", ")}</div></div>))}
              <div className="mt-2 text-[11px] uppercase tracking-wider text-fg-3">Name history</div>
              {d.former_names.length === 0 ? <p className="text-sm text-fg-3">No former names on record.</p> :
                <ul className="text-sm text-fg-2">{d.former_names.map((n) => <li key={n.name}>{n.name} <span className="text-fg-3">({n.from?.slice(0, 10)} – {n.to?.slice(0, 10)})</span></li>)}</ul>}
            </Panel>
            <Panel title="Filing record" subtitle="Annual reports by filing year">
              <div className="flex flex-wrap gap-1">{d.filing_regularity.annual_report_years.map((y) => <span key={y} className="num rounded bg-good/10 px-1.5 py-0.5 text-xs text-good">{y}</span>)}
                {d.filing_regularity.missing_years.map((y) => <span key={y} className="num rounded bg-bad/15 px-1.5 py-0.5 text-xs text-bad" title="No annual report filed">{y}</span>)}</div>
              <div className="mt-3 space-y-1 text-sm">
                <div>Auditor changes (8-K 4.01): <b className={d.auditor_changes.length ? "text-warn" : "text-fg"}>{d.auditor_changes.length}</b></div>
                <div>Insolvency/delisting events: <b className={d.insolvency_events.length ? "text-bad" : "text-fg"}>{d.insolvency_events.length}</b></div>
                <div>Going-concern language: <b className={d.going_concern.length ? "text-bad" : "text-fg"}>{d.going_concern.length ? "present" : "none found"}</b></div>
                <div>Schedule 13D/G ownership filings: <b>{d.beneficial_ownership_filings.length}</b></div>
              </div>
            </Panel>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Subsidiaries (Exhibit 21)" subtitle={d.subsidiaries.filed ? `10-K filed ${date(d.subsidiaries.filed)} · ${d.subsidiaries.accession}` : undefined}>
              {d.subsidiaries.unavailable && <Unavailable error={d.subsidiaries.unavailable} compact />}
              <ul className="grid gap-1 text-sm sm:grid-cols-2">{d.subsidiaries.subsidiaries.map((s) => <li key={s.name} className="rounded border border-ink-700 bg-ink-850 px-2 py-1"><div className="text-fg">{s.name}</div><div className="text-[11px] text-fg-3">{s.jurisdiction}</div></li>)}</ul>
              <p className="mt-3 text-xs text-fg-3">Parent company: {d.parent_company.reason}</p>
            </Panel>
            <Panel title="Litigation (Item 3, latest 10-K)" subtitle={d.legal_proceedings ? `filed ${date(d.legal_proceedings.filed)}` : undefined}>
              {d.legal_proceedings ? <p className="whitespace-pre-line text-sm leading-relaxed text-fg-2">{d.legal_proceedings.text.slice(0, 1800)}</p> : <p className="text-sm text-fg-3">Item 3 not located.</p>}
              {d.going_concern.map((g, i) => <Notice key={i} tone="warn">Going concern ({date(g.filed)}): {g.text}</Notice>)}
            </Panel>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Sanctions screening (OFAC SDN · free)" subtitle={d.sanctions?.retrieved_at ? `list retrieved ${date(d.sanctions.retrieved_at)}` : undefined}>
              {d.sanctions?.status === "ok" ? (
                <div className="space-y-1 text-sm">
                  <p className={d.sanctions.matches?.length ? "text-bad" : "text-good"}>{d.sanctions.matches?.length
                    ? `${d.sanctions.matches.length} exact name match(es): ${d.sanctions.matches.map((m) => `${m.name} (${m.program})`).join("; ")}`
                    : `No exact match for ${d.sanctions.screened} name(s) among ${d.sanctions.list_size?.toLocaleString()} SDN entries.`}</p>
                  <p className="text-[11px] text-fg-3">{d.sanctions.method} A name match is not an identification, and no match is not clearance.</p>
                </div>
              ) : <p className="text-sm text-fg-3">{d.sanctions?.message ?? "Not checked."} {d.sanctions?.hint}</p>}
            </Panel>
            <Panel title="Website history (Internet Archive · free)">
              {d.website_history?.status === "ok" ? (
                <p className="text-sm text-fg-2">{d.website_history.site}: earliest snapshot {d.website_history.first?.timestamp.slice(0, 4) ?? "none"}
                  {d.website_history.latest ? `, latest ${d.website_history.latest.timestamp.slice(0, 8)}` : ""}.{" "}
                  {d.website_history.first && <a className="text-accent underline underline-offset-2" href={d.website_history.first.url} target="_blank" rel="noopener noreferrer">earliest snapshot</a>}</p>
              ) : <p className="text-sm text-fg-3">{d.website_history?.message ?? "Not checked."} {d.website_history?.hint}</p>}
            </Panel>
          </div>
          <Panel title="Checks not yet possible" subtitle="Shown explicitly instead of silently skipped">
            <ul className="grid gap-2 md:grid-cols-2">{d.not_connected.map((n) => (
              <li key={n.check} className="rounded-lg border border-ink-700 bg-ink-850 p-3 text-xs"><div className="font-medium text-fg">{n.check}</div>
                <div className="text-fg-3">{n.adapter} · <span className="uppercase">{n.status.replace(/_/g, " ")}</span></div><div className="mt-1 text-fg-2">{n.reason}</div></li>))}</ul>
          </Panel>
        </>
      )}
      {c.data && <ModuleFindings companyId={id} module="corporate_legitimacy" />}
    </Page>
  );
}
