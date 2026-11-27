# Public demo deployment

This guide describes how the maintainer can publish the demo app and its data snapshot in a
Hugging Face Space. See the [quick start](../README.md#quick-start) to run DeepTerminal locally.

## Hosting

- **Host:** Hugging Face Docker Space, free "CPU basic" tier (2 vCPU, 16 GB).
- **Cost and access:** no payment details are needed, and judges need no account.
- **Sleep:** the Space sleeps after 48 h without visitors and wakes on the next visit, which takes about a minute.

## How the demo works

### Read-only, offline backend (`DEEPTERMINAL_PUBLIC_DEMO=true`)

- **Offline by force.** The backend replays its cache only and disables every outbound host
  (`DEEPTERMINAL_NETWORK_DISABLED`). AI is rule-based, paid APIs are off and there is no price provider.
- **Few writes allowed.** Every write is refused with a 403, except:
  - stateless valuation (SOTP, NAV and shock);
  - chat, at most 30 per hour per visitor;
  - the rule-based Thesis Challenger, at most 3 per hour per visitor and one running at a time.
- **Abuse limits:**
  - a global cap of 600 per hour;
  - a request size limit of 64 KB;
  - a per-minute rate limit.
- **Visitor identity.** Visitors are identified from `X-Forwarded-For`, counting hops from the right (`DEEPTERMINAL_PROXY_HOPS`).
- **Privacy.** A visitor's chats and runs are hidden from everyone else.
- **Speed.**
  - The snapshot is fixed, so responses are recorded once (`snapshot/responses.json.gz`) and preloaded.
  - Every screen is fast from the first visit, even right after the Space wakes.
  - `warm.py` fills in anything missing.
  - `/api/status` reports `"warm": true` when ready.

### Judges' guide and labelling

- **Guide page.** `/demo` has a tour, the recorded local-AI examples and sample questions.
  - Each example is labelled with model, hardware, generation time, date, citations and any later fixes it predates.
  - It also lists what works live, what needs the full local backend, and the valuation assumptions.
- **Illustrative discount rate.** The valuation lab and reverse DCF start from an illustrative 9% discount rate, labelled as such.
- **Valuation date.** They value as of the recorded SEC Form 4 price date. These are real, dated trades, not official closing prices.

### Snapshot (`deploy/snapshot/`, built by `scripts/build_demo_snapshot.py`)

- **Coverage:** NVIDIA, Apple, Microsoft, AMD and Intel.
- **Data:** SEC EDGAR filings, XBRL and full-text search; FRED; OFAC; the Internet Archive. All retrieved 2026-10-30.
- **Research:** a full rule-based investigation for each company, with 70–96 findings.
- **Recorded AI examples (NVIDIA):** an investigation synthesis, a thesis challenge and a chat answer. All were generated locally by `qwen2.5:7b-instruct` through Ollama.
- **Contact e-mail.** The builder refuses to write anything that contains the SEC contact e-mail.

## Verification

- **Backend:** core 101 passed, 1 skipped; API 90 passed. This includes the public-demo protections, preloading and the engine fixes below.
- **Frontend:** `tsc` and ESLint are clean. E2E: 14 of 14 passed locally.
- **Demo image (CI, `demo-image.yml`):** the exact image that will be deployed builds and runs as uid 1000 on port 7860.
  - It is healthy within about 10 s, with all 118 recorded responses preloaded.
  - **37 of 37** smoke checks pass in a fresh, signed-out browser. They cover the protections, all main screens, citations to sec.gov, chat, report HTML and PDF, phone layout, and valuation and reverse-DCF results equal to the pre-computed values.
  - Run 9 (commit `e10bfbe`) is green; the main `tests` workflow is green on the same commit.
- **Dependencies:**
  - `npm audit --omit=dev`: 0 vulnerabilities.
  - `pip-audit`: none.
  - Vitest, which is dev-only and not shipped, needs a major upgrade to clear its advisories.

### Engine fixes found while preparing the demo (2026-10-30)

- **Stale balance-sheet items.** The equity bridge used balance-sheet, option and RSU figures that a company had last tagged years earlier, for example 2014 securities and 2011 options. Items more than 400 days older than the balance-sheet date are now excluded, and the exclusion is noted.
  - Effect at a 9% discount rate: NVDA base value $243.76 → $252.22; AAPL $114.87 → $118.28.
- **Negative effective tax rates.** These came from tax benefits and were clamped to a 0% long-run tax rate. They now fall back to the 21% statutory rate, with a stated rationale.
- **Negative equity.** When claims exceed the DCF value, the scenario shows a $0.00 floor. It is now flagged as a floor, not an estimate, which is the case for Intel on current margins and reinvestment.

## Owner steps to deploy

These are free and need no payment details. Do not paste the token into chat.

1. Create an account at https://huggingface.co/join and verify your e-mail.
2. Create a token at https://huggingface.co/settings/tokens: **New token**, type **Write**, then copy it.
3. In GitHub, open the repository, then go to **Settings → Secrets and variables → Actions**:
   - **Secrets → New repository secret:** `HF_TOKEN` = the token.
   - **Variables → New repository variable:** `HF_SPACE` = `<your-hf-username>/deepterminal`.
   - **Variables → New repository variable:** `DEMO_DEPLOY` = `true`. This is the authorisation switch; delete it to stop deploying.
4. Open **Actions → Deploy public demo**, select the latest run and choose **Re-run all jobs**.
5. The workflow then:
   - uploads the Space;
   - waits for it to build and warm up;
   - tests `https://<your-hf-username>-deepterminal.hf.space` in a fresh, signed-out browser;
   - keeps screenshots as artifacts.

## After the first deployment

- **Check `DEEPTERMINAL_PROXY_HOPS=2`.** It assumes Hugging Face's proxy plus the Next proxy. If all visitors share one rate-limit bucket, adjust it. The global caps protect the demo either way.
