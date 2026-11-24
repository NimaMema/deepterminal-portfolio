/** Typed fetch helper. Errors carry the backend's unavailability status and hint. */
export class ApiError extends Error {
  status: number;
  code: string;
  hint: string;
  url: string;
  constructor(status: number, body: Record<string, string>) {
    super(body.message || body.detail || `Request failed (${status})`);
    this.status = status;
    this.code = body.status || "error";
    this.hint = body.hint || "";
    this.url = body.url || "";
  }
}

export async function api<T = unknown>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  const res = await fetch(`/api${path}`, {
    ...rest,
    headers: { ...(json !== undefined ? { "content-type": "application/json" } : {}), ...(rest.headers ?? {}) },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
    cache: "no-store",
  });
  if (!res.ok) {
    let body: Record<string, string> = {};
    try { body = await res.json(); } catch { /* non-JSON error */ }
    throw new ApiError(res.status, body);
  }
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export const post = <T,>(path: string, json: unknown) => api<T>(path, { method: "POST", json });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

import { useQuery } from "@tanstack/react-query";

/** Dashboard data for an analysis module (computed live by the backend). */
export function useModule<T = Record<string, unknown>>(companyId: number, module: string, params: Record<string, string | number | undefined> = {}) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)])).toString();
  return useQuery({
    queryKey: ["module", companyId, module, qs],
    queryFn: () => api<{ module: string; synthetic: boolean; data: T }>(`/companies/${companyId}/modules/${module}${qs ? `?${qs}` : ""}`),
    staleTime: 60_000,
  });
}
