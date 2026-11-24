// Smoke test of the deployed public demo, in a fresh, signed-out browser (no cookies, no
// credentials), at desktop and phone sizes.   node smoke.mjs https://<space>.hf.space
// Checks every main screen, live calculations against expected values, citations, the
// read-only and no-paid-API protections, and saves a screenshot of each screen to ./out.
import { chromium, devices } from "playwright";
import { mkdirSync, readFileSync, existsSync } from "node:fs";

const BASE = (process.argv[2] || "").replace(/\/$/, "");
if (!/^https?:\/\//.test(BASE)) { console.error("usage: node smoke.mjs <url>"); process.exit(2); }
mkdirSync("out", { recursive: true });
const expected = existsSync("expected.json") ? JSON.parse(readFileSync("expected.json", "utf8")) : null;
const results = [];
const ok = (name, pass, detail = "") => { results.push({ name, pass, detail }); console.log(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`); };
const near = (a, b, tol = 0.005) => Math.abs(a - b) <= Math.max(1e-9, Math.abs(b) * tol);

const browser = await chromium.launch();
try {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const api = async (path, init) => {
    const r = await ctx.request.fetch(`${BASE}/api${path}`, init);
    let body = null; try { body = await r.json(); } catch { /* not JSON */ }
    return { status: r.status(), body, headers: r.headers() };
  };

  // Protections
  const st = await api("/status");
  ok("status: public demo, paid APIs off, rule-based AI", st.status === 200 && st.body.public_demo === true && st.body.paid_apis_enabled === false
     && st.body.providers.every((p) => !p.active || p.provider === "rules"), JSON.stringify({ demo: st.body?.public_demo, paid: st.body?.paid_apis_enabled }));
  const w = await api("/settings/ui", { method: "PUT", data: { value: { x: 1 } } });
  ok("writes refused (settings)", w.status === 403 && w.body?.status === "demo_readonly", String(w.status));
  const inv = await api("/jobs", { method: "POST", data: { company_id: 1, kind: "investigation" } });
  ok("new investigations refused", inv.status === 403, String(inv.status));
  const pf = await api("/companies/1/prices/fetch", { method: "POST", data: {} });
  ok("live price fetch refused", pf.status === 403, String(pf.status));
  const other = await api("/companies/resolve/TSLA");
  ok("companies outside the snapshot are reported unavailable", other.status >= 400 && /snapshot/i.test(JSON.stringify(other.body)), String(other.status));

  // Data
  const companies = (await api("/companies")).body || [];
  ok("snapshot companies", companies.length >= 3, companies.map((c) => c.ticker).join(", "));
  const nv = companies.find((c) => c.ticker === "NVDA") || companies[0];
  const show = (await api("/demo/showcase")).body || {};
  ok("judges' guide data with attributed AI examples", (show.examples || []).length >= 1 && show.examples.every((e) => e.model && e.engine && e.recorded_at),
     `${(show.examples || []).length} examples`);

  // Calculations: the deployed engine must reproduce the values computed before deployment.
  if (expected) {
    for (const e of expected.valuations) {
      const r = await api(`/companies/${e.company_id}/valuation`, { method: "POST", data: e.request });
      const base = r.body?.scenarios?.find((s) => s.name === "base")?.per_share;
      ok(`valuation ${e.ticker}: base per share ${base?.toFixed?.(2)} = expected ${e.base_per_share.toFixed(2)}`, r.status === 200 && near(base, e.base_per_share));
      const rd = r.body?.reverse_dcf?.find((x) => x.lever === "initial_growth_fading")?.solutions?.[0]?.value;
      if (e.implied_growth != null) ok(`reverse DCF ${e.ticker}: implied growth ${rd} = expected ${e.implied_growth}`, rd != null && near(rd, e.implied_growth, 0.01));
    }
  }

  // Screens (desktop)
  const screens = [
    ["home", "/", /DEEP/],
    ["guide", "/demo", /Judges' guide/],
    ["overview", `/company/${nv.id}`, new RegExp(nv.ticker)],
    ["financials", `/company/${nv.id}/financials`, /Revenue/i],
    ["filings", `/company/${nv.id}/filings`, /10-K/],
    ["time-machine", `/company/${nv.id}/time-machine`, /time machine/i],
    ["supply-chain", `/company/${nv.id}/supply-chain`, /Supply chain/i],
    ["competitors", `/company/${nv.id}/competitors`, /Competitors/i],
    ["valuation", `/company/${nv.id}/valuation`, /Base value/i],
    ["reverse-dcf", `/company/${nv.id}/reverse-dcf`, /Reverse DCF/i],
    ["investigation", `/company/${nv.id}/research`, /investigation/i],
    ["thesis", `/company/${nv.id}/thesis`, /Thesis/i],
    ["reports", `/reports?company=${nv.id}`, /Research reports/i],
  ];
  for (const [name, path, re] of screens) {
    const r = await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 90_000 });
    const text = await page.locator("main").innerText({ timeout: 30_000 }).catch(() => "");
    const bad = /Application error|Internal Server Error|Something went wrong/i.test(text);
    ok(`screen ${name}`, r?.status() === 200 && re.test(text) && !bad, `${r?.status()} ${bad ? "error text" : ""}`);
    await page.screenshot({ path: `out/${name}.png`, fullPage: false });
  }
  const banner = await page.getByRole("note").first().innerText().catch(() => "");
  ok("public-demo banner shown", /Public demo/i.test(banner));

  // Evidence: open a cited source from the overview / investigation findings
  const ev = await api(`/companies/${nv.id}/findings`);
  const ids = [...new Set((ev.body || []).flatMap((f) => f.evidence_ids || []))].slice(0, 100);
  const evs = ids.length ? (await api(`/evidence?ids=${ids.join(",")}`)).body || [] : [];
  const sec = evs.filter((e) => /^https:\/\/(www|data)\.sec\.gov\//.test(e.source?.url || ""));
  ok("findings cite stored evidence; filing evidence links to sec.gov", evs.length > 0 && sec.length > 0 && evs.every((e) => e.source?.kind),
     `${evs.length} evidence records, ${sec.length} with SEC URLs`);

  // Chat (extractive, cited)
  await page.goto(`${BASE}/company/${nv.id}/chat?q=${encodeURIComponent("Who manufactures NVIDIA's wafers?")}`, { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByText(/cited source/).last().waitFor({ timeout: 60_000 }).catch(() => {});
  const chatText = await page.locator("main").innerText();
  ok("chat answers with citations", /[1-9]\d* cited source/.test(chatText));
  await page.screenshot({ path: "out/chat.png" });

  // Report + PDF
  const reps = (await api(`/companies/${nv.id}/reports`)).body || [];
  if (reps.length) {
    const html = await ctx.request.get(`${BASE}/api/reports/${reps[0].id}/html`);
    ok("report HTML", html.status() === 200 && /Bibliography|References/i.test(await html.text()));
    const pdf = await ctx.request.get(`${BASE}/api/reports/${reps[0].id}/pdf`, { timeout: 120_000 });
    ok("report PDF export", pdf.status() === 200 && (pdf.headers()["content-type"] || "").includes("pdf"), String(pdf.status()));
  } else ok("report present", false);

  ok("no uncaught page errors", errors.length === 0, errors.slice(0, 3).join(" | "));

  // Phone
  const phone = await browser.newContext({ ...devices["iPhone 13"] });
  const pp = await phone.newPage();
  for (const [name, path] of [["phone-guide", "/demo"], ["phone-overview", `/company/${nv.id}`], ["phone-valuation", `/company/${nv.id}/valuation`]]) {
    const r = await pp.goto(BASE + path, { waitUntil: "networkidle", timeout: 90_000 });
    const overflow = await pp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    ok(`${name}: loads, no horizontal scroll`, r?.status() === 200 && overflow <= 1, `overflow ${overflow}px`);
    await pp.screenshot({ path: `out/${name}.png` });
  }
} finally {
  await browser.close();
}
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} checks passed against ${BASE}`);
process.exit(failed.length ? 1 : 0);
