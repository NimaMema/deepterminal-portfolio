export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function money(v: unknown, digits = 0, unit = "m"): string {
  if (!isNum(v)) return "—";
  const abs = Math.abs(v);
  if (unit === "m" && abs >= 1000) return `${v < 0 ? "−" : ""}$${(abs / 1000).toLocaleString("en-US", { maximumFractionDigits: 1 })}bn`;
  return `${v < 0 ? "−" : ""}$${abs.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits })}${unit}`;
}

export function num(v: unknown, digits = 0): string {
  if (!isNum(v)) return "—";
  return v.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits }).replace("-", "−");
}

export function pct(v: unknown, digits = 1): string {
  if (!isNum(v)) return "—";
  return `${(v * 100).toFixed(digits).replace("-", "−")}%`;
}

export function signedPct(v: unknown, digits = 1): string {
  if (!isNum(v)) return "—";
  return `${v >= 0 ? "+" : "−"}${Math.abs(v * 100).toFixed(digits)}%`;
}

export function price(v: unknown): string {
  return isNum(v) ? `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—";
}

export function date(v?: string | null): string {
  if (!v) return "—";
  const d = new Date(v.length === 10 ? `${v}T00:00:00Z` : v);
  return d.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric", timeZone: "UTC" });
}

export function ago(v?: string | null): string {
  if (!v) return "—";
  const s = (Date.now() - new Date(v).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

const FORMS: Record<string, string> = {
  "10-K": "Annual report", "10-K/A": "Annual report (amended)", "10-Q": "Quarterly report", "10-Q/A": "Quarterly report (amended)",
  "8-K": "Current report", "DEF 14A": "Proxy statement", "4": "Insider transaction", "3": "Initial insider holdings",
  "SC 13D": "Beneficial ownership (activist)", "SC 13G": "Beneficial ownership (passive)",
  "SCHEDULE 13D": "Beneficial ownership (activist)", "SCHEDULE 13G": "Beneficial ownership (passive)",
  "SCHEDULE 13D/A": "Beneficial ownership (activist, amended)", "SCHEDULE 13G/A": "Beneficial ownership (passive, amended)", "S-1": "Registration statement",
  "20-F": "Annual report (foreign issuer)", "6-K": "Foreign issuer report",
};
export const formLabel = (form: string) => FORMS[form] ?? `Form ${form}`;
