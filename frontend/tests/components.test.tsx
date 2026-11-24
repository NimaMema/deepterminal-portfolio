import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { CitedText, EvidenceProvider, FindingsList } from "@/components/evidence";
import { SeverityBadge, Unavailable } from "@/components/ui";
import { ApiError } from "@/lib/api";
import type { Finding } from "@/lib/types";

const wrap = (ui: ReactNode) => render(<QueryClientProvider client={new QueryClient()}><EvidenceProvider>{ui}</EvidenceProvider></QueryClientProvider>);

const f = (id: number, severity: Finding["severity"], title: string): Finding => ({
  id, job_id: "j", module: "forensic_accounting", title, summary: `Summary ${id} [E${id}]`, epistemic_status: "analytical_inference",
  severity, confidence: "medium", evidence_ids: severity === "unavailable" ? [] : [id], limitations: null, data: {}, generated_by: "rules", created_at: "2026-10-28T00:00:00Z" });

describe("evidence UI", () => {
  it("turns [E#] markers into citation buttons", () => {
    wrap(<CitedText text="Margins fell [E12] and debt rose [E7]." />);
    expect(screen.getByRole("button", { name: "Open evidence E12" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open evidence E7" })).toBeInTheDocument();
  });

  it("filters findings by severity", async () => {
    wrap(<FindingsList findings={[f(1, "concern", "High accruals"), f(2, "positive", "Strong F-Score"), f(3, "unavailable", "No reviews")]} />);
    expect(screen.getByText("High accruals")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^positive/ }));
    expect(screen.queryByText("High accruals")).not.toBeInTheDocument();
    expect(screen.getByText("Strong F-Score")).toBeInTheDocument();
  });

  it("explains unavailable data with the server's hint", () => {
    wrap(<Unavailable error={new ApiError(503, { status: "blocked", message: "Network policy blocks sec.gov", hint: "Allow data.sec.gov" })} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Blocked by network policy");
    expect(screen.getByRole("alert")).toHaveTextContent("Allow data.sec.gov");
    expect(screen.getByRole("alert")).toHaveTextContent("No value is shown rather than an invented one");
  });

  it("labels severity in text, not colour alone", () => {
    render(<SeverityBadge s="concern" />);
    expect(screen.getByText("Concern")).toBeInTheDocument();
  });
});

describe("CitedText formatting of model output", () => {
  it("renders bold and headings as text, citations as buttons, and never injects HTML", () => {
    const { container } = wrap(<CitedText text={"### Risks\n- **Tariffs**: cost impact [E7]\n<img src=x onerror=alert(1)>"} />);
    expect(screen.getByText("Risks").closest("strong")).not.toBeNull();
    expect(screen.getByText("Tariffs").tagName).toBe("STRONG");
    expect(screen.getByRole("button", { name: "Open evidence E7" })).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
