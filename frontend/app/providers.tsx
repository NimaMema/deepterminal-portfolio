"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { EvidenceProvider } from "@/components/evidence";

export function Providers({ children }: { children: ReactNode }) {
  const [qc] = useState(() => new QueryClient({
    defaultOptions: { queries: { retry: (n, e) => n < 1 && !(e as { status?: number })?.status, refetchOnWindowFocus: false, staleTime: 15_000 } },
  }));
  return <QueryClientProvider client={qc}><EvidenceProvider>{children}</EvidenceProvider></QueryClientProvider>;
}
