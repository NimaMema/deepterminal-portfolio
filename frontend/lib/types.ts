export type Severity = "positive" | "neutral" | "watch" | "concern" | "unavailable";

export interface Company {
  id: number; cik: number; ticker: string | null; name: string; sic: string | null; sic_description: string | null;
  state_of_incorporation: string | null; fiscal_year_end: string | null; entity_type: string | null; category: string | null;
  ein: string | null; website: string | null; exchanges: string[]; former_names: { name: string; from?: string; to?: string }[];
  addresses: Record<string, Record<string, string>>; synthetic: boolean; financial_institution: boolean;
  profile_retrieved_at: string | null; edgar_url: string;
}

export interface MetricsYear {
  fy: number; end: string; revenue: number; operating_income: number; net_income: number; fcf: number; fcf_after_sbc: number;
  operating_margin: number; net_margin: number; revenue_growth: number | null; gross_margin: number | null; roe: number | null;
  sbc_pct_revenue: number; dso: number | null; dio: number | null; net_debt: number; diluted_shares: number; filed: string | null;
  source_ref: string;
}

export interface CompanyDetail extends Company {
  metrics: { history: MetricsYear[]; trend?: { fy: number; end: string; revenue: number; operating_margin: number | null; net_margin: number | null }[]; ttm: Record<string, number | string> | null; flags: { fiscal_year: number; code: string; message: string; severity: string }[];
             shares_outstanding: number | null; shares_outstanding_as_of: string | null; synthetic: boolean; retrieved_at: string } | null;
  metrics_unavailable?: { status: string; message: string; hint?: string };
  price: { value: number; as_of: string; source: string; url?: string } | null;
}

export interface Source {
  id: string; kind: string; title: string; publisher: string; url: string | null; published_at: string | null;
  retrieved_at: string | null; period_end: string | null; accession: string | null; licence: string | null; synthetic: boolean;
}

export interface Evidence {
  id: number; kind: string; title: string; excerpt: string | null; locator: string | null; value: number | null; unit: string | null;
  period_end: string | null; epistemic_status: string; verification_status: string; limitations: string | null;
  data: Record<string, unknown>; created_by: string; created_at: string; source: Source | null;
  context?: { section_title: string; text: string; sha256: string };
}

export interface Finding {
  id: number; job_id: string | null; module: string; title: string; summary: string; epistemic_status: string;
  severity: Severity; confidence: string; evidence_ids: number[]; limitations: string | null; data: Record<string, unknown>;
  generated_by: string; created_at: string;
}

export interface Job {
  id: string; company_id: number; kind: string; modules: string[]; params: Record<string, unknown>; status: string;
  progress: number; current_step: string | null; error: string | null; result: Record<string, unknown>;
  created_at: string; started_at: string | null; finished_at: string | null;
  events?: { id: number; ts: string; level: string; module: string | null; message: string }[];
}

export interface Unavailable { status: string; message: string; hint?: string }
