"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { Chat } from "@/components/chat";
import { Page, PageHeader, useCompanyId } from "@/components/company";

function CompanyChatInner() {
  const id = useCompanyId();
  const sp = useSearchParams();
  return <Chat companyId={id} initialSession={sp.get("session")} initialText={sp.get("q")} />;
}

export default function CompanyChat() {
  return (
    <Page><PageHeader title="Research chat" description="Every answer cites evidence; open a citation to see the source passage in context." />
      <Suspense><CompanyChatInner /></Suspense></Page>
  );
}
