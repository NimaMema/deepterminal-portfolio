"use client";

import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { api } from "@/lib/api";

/** True when the backend runs as the hosted public demo (fixed snapshot, read-only). */
export function useDemo(): boolean {
  const q = useQuery({ queryKey: ["status"], queryFn: () => api<{ public_demo?: boolean }>("/status"), staleTime: 30_000 });
  return !!q.data?.public_demo;
}

/** Label for a control that needs the full local backend in the public demo. */
export function BackendOnly({ what }: { what?: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border border-ink-600 px-1.5 py-0.5 text-[10.5px] text-fg-3"
      title="Not available in the public demo. Run DEEPTERMINAL locally (free) for this feature.">
      <Lock size={10} aria-hidden />{what ?? "Full local backend"}
    </span>
  );
}
