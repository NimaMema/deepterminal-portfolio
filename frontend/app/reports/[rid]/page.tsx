"use client";

import { Download } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Page, PageHeader } from "@/components/company";
import { Button } from "@/components/ui";

export default function ReportView() {
  const { rid } = useParams<{ rid: string }>();
  const [h, setH] = useState(1600);
  return (
    <Page>
      <PageHeader title="Research report" description="Rendered from stored evidence. Citation numbers refer to the bibliography at the end.">
        <a href={`/api/reports/${rid}/pdf`}><Button variant="primary"><Download size={14} aria-hidden />Download PDF</Button></a>
      </PageHeader>
      <iframe title="Research report" src={`/api/reports/${rid}/html`} sandbox="allow-same-origin" className="w-full rounded-xl border border-ink-700 bg-white" style={{ height: h }}
        onLoad={(e) => { try { const d = (e.target as HTMLIFrameElement).contentDocument; if (d) setH(d.documentElement.scrollHeight + 40); } catch { /* cross-origin */ } }} />
    </Page>
  );
}
