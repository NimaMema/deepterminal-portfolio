"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Chat } from "@/components/chat";
import { PageHeader, Page } from "@/components/company";
import { Select } from "@/components/ui";
import { api } from "@/lib/api";
import type { Company } from "@/lib/types";

export default function ChatPage() {
  const companies = useQuery({ queryKey: ["companies"], queryFn: () => api<Company[]>("/companies") });
  const [cid, setCid] = useState<number | null>(null);
  useEffect(() => { if (!cid && companies.data?.length) setCid(companies.data[0].id); }, [companies.data, cid]);
  return (
    <Page>
      <PageHeader title="AI research chat" description="Questions are answered from DEEPTERMINAL's evidence store and retrieved filings. With an LLM configured, an agent uses read-only research tools; without one, you get an extractive answer listing the matching evidence.">
        <Select value={cid ?? ""} onChange={(e) => setCid(Number(e.target.value))} aria-label="Company">
          {companies.data?.map((c) => <option key={c.id} value={c.id}>{c.ticker} — {c.name}</option>)}</Select>
      </PageHeader>
      <Chat companyId={cid} />
    </Page>
  );
}
