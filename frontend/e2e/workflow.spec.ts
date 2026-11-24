import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function openCompany(page: Page, ticker: string) {
  await page.goto("/");
  await page.getByLabel("Search by ticker, company name or CIK").fill(ticker);
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await expect(page).toHaveURL(/\/company\/\d+$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("(Demo)");
  return page.url().match(/company\/(\d+)/)![1];
}

test("search opens a company profile with provenance-linked statements", async ({ page }) => {
  const id = await openCompany(page, "DQD");
  await expect(page.getByText("Revenue · TTM")).toBeVisible();
  await page.goto(`/company/${id}/financials`);
  const cell = page.getByRole("button", { name: /^Revenue · FY2025:/ });
  await cell.click();
  await expect(page.getByText("XBRL concept")).toBeVisible();
  await expect(page.getByText(/us-gaap:Revenues/)).toBeVisible();
});

test("command palette searches and navigates (keyboard)", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Control+k");
  await page.getByPlaceholder("Ticker, company name or CIK…").fill("harbor");
  await expect(page.getByRole("option", { name: /DHB/ })).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/company\/\d+$/);
});

test("valuation lab: price with source, DCF scenarios, verdict, reverse DCF", async ({ page }) => {
  const id = await openCompany(page, "DQD");
  await page.goto(`/company/${id}/valuation`);
  await page.getByLabel("Price (USD)").fill("140");
  await page.getByLabel("As of").fill("2026-10-27");
  await page.getByLabel("Source", { exact: true }).fill("demo closing price (synthetic)");
  await page.getByRole("button", { name: "Save price" }).click();
  await expect(page.getByText("in use")).toBeVisible();
  await page.getByLabel(/Discount rate \(WACC\)/).fill("0.095");
  await page.getByRole("button", { name: "Run valuation" }).click();
  await expect(page.getByText(/under specified assumptions|Too uncertain/)).toBeVisible();
  await expect(page.getByText("Base value / share")).toBeVisible();
  await page.getByRole("tab", { name: "sensitivity" }).click();
  await expect(page.getByRole("table", { name: /Sensitivity/ })).toBeVisible();
  await page.goto(`/company/${id}/reverse-dcf`);
  await expect(page.getByText("Market EV to explain")).toBeVisible();
  await expect(page.getByText("Iso-value curve")).toBeVisible();
  await expect(page.getByText(/Misvaluation investigation/)).toBeVisible();
});

test("investigation runs in the background with live progress and evidence drawer", async ({ page }) => {
  const id = await openCompany(page, "DHB");
  await page.goto(`/company/${id}/research`);
  await page.getByLabel(/Discount rate for valuation/).fill("0.07");
  await page.getByRole("button", { name: "Start investigation" }).click();
  await expect(page.getByRole("progressbar", { name: "Job progress" })).toBeVisible();
  await expect(page.getByText("succeeded", { exact: true }).first()).toBeVisible({ timeout: 90_000 });
  const cite = page.getByRole("button", { name: /^Open evidence E\d+/ }).first();
  await cite.click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByText(/Evidence E\d+/)).toBeVisible();
  await expect(drawer.getByText("Original source")).toBeVisible();
  await expect(drawer.getByText(/Synthetic demo source|Verified against source|Calculation/).first()).toBeVisible();
});

test("thesis challenger reports counter-evidence and what it checked", async ({ page }) => {
  const id = await openCompany(page, "DQD");
  await page.goto(`/company/${id}/thesis`);
  await page.getByLabel("Investment thesis").fill("AI demand will keep growth above 40% and its moat gives lasting pricing power.");
  await page.getByRole("button", { name: "Challenge thesis" }).click();
  await expect(page.getByText(/Counter-evidence \(\d+\)/)).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("Alternative explanations")).toBeVisible();
  await expect(page.getByText(/Searched — nothing contradicting found/)).toBeVisible();
});

test("research chat answers with citations (extractive without an LLM key)", async ({ page }) => {
  const id = await openCompany(page, "DQD");
  await page.goto(`/company/${id}/chat`);
  await page.getByLabel("Ask a question").fill("What are the risks related to the foundry in Taiwan?");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(/cited source\(s\)/).last()).toBeVisible();
  await expect(page.getByRole("button", { name: /^Open evidence E\d+/ }).first()).toBeVisible();
});

test("report generation and PDF export", async ({ page, request }) => {
  const id = await openCompany(page, "DQD");
  await page.goto(`/reports?company=${id}`);
  await page.getByRole("button", { name: "Generate report" }).click();
  const view = page.getByRole("link", { name: /research report/ }).first();
  await expect(view).toBeVisible();
  const pdfHref = await page.locator('a[href$="/pdf"]').first().getAttribute("href");
  const res = await request.get(pdfHref!);
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toContain("application/pdf");
  expect((await res.body()).subarray(0, 4).toString()).toBe("%PDF");
  await view.click();
  await expect(page.frameLocator('iframe[title="Research report"]').getByText("Source bibliography")).toBeVisible();
});

test("supply-chain graph shows evidence for a relationship", async ({ page }) => {
  const id = await openCompany(page, "DQD");
  await page.goto(`/company/${id}/supply-chain`);
  await page.getByText("Formosa Precision Foundry Co., Ltd.").first().click();
  await expect(page.getByText(/wafer fabrication/).first()).toBeVisible();
});

test("unavailable data is explained, not invented", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Search by ticker, company name or CIK").fill("ZZZZQ");
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "No SEC registrant" })).toBeVisible();
});

test("zero-cost mode: paid AI providers are off and free sources are listed", async ({ page }) => {
  await page.goto("/settings");
  await expect(page.getByRole("status").filter({ hasText: "Zero-cost mode." })).toBeVisible();
  const engine = page.getByRole("region", { name: "AI engine" });
  for (const paid of ["anthropic", "openai"]) {
    const row = engine.getByRole("listitem").filter({ hasText: new RegExp(`^${paid}`, "i") });
    await expect(row).toContainText("paid");
    await expect(row).toContainText("off");
  }
  await expect(page.getByRole("cell", { name: "Stooq end-of-day prices" })).toBeVisible();
  await expect(page.getByText("AI: rule-based (Ollama not running)")).toBeVisible();
});

for (const path of ["/", "/settings"]) {
  test(`accessibility: no serious axe violations on ${path}`, async ({ page }) => {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const serious = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
  });
}

test("accessibility: company pages", async ({ page }) => {
  const id = await openCompany(page, "DQD");
  for (const sub of ["", "/financials", "/forensics", "/valuation"]) {
    await page.goto(`/company/${id}${sub}`);
    await page.waitForLoadState("networkidle");
    const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).exclude(".react-flow").analyze();
    const serious = r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${sub}: ${v.id} (${v.nodes.length})`)).toEqual([]);
  }
});
