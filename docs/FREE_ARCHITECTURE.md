# Zero-cost architecture

DEEPTERMINAL has **no required operating costs**. It runs on free software on your own machine,
uses only free public data, and uses a local open-weight model for AI. Nothing asks for payment
details, and nothing is billed per request.

## What runs where

| Component | What it is | Cost |
|---|---|---|
| Web UI | Next.js, run locally (`npm run dev` / `next start`) | free (MIT) |
| API | FastAPI + Uvicorn, run locally | free (MIT/BSD) |
| Database | PostgreSQL on your machine or in docker-compose | free (PostgreSQL licence) |
| Calculations | DCF, reverse DCF, multiples, scenarios, forensics, screening: pure Python, local | free |
| AI | **Ollama** with an open-weight model (default `qwen2.5:7b-instruct`, Apache-2.0) | free, runs locally |
| PDF export | Chromium via Playwright, local | free |
| Hosting | none; everything is local. docker-compose is optional | free |

## Data sources (all free)

| Source | Used for | Key | Unavoidable limitations of the free source |
|---|---|---|---|
| SEC EDGAR (submissions, XBRL, filings) | Financial statements, filings, risk factors, 8-Ks, proxies, Form 4, Exhibit 21 | none (User-Agent with contact e-mail) | ≤10 requests/second; XBRL from about 2009; US registrants only; IFRS and foreign filers not modelled |
| EDGAR full-text search | Who names a company in their 10-K (supplier, customer, competitor, investor, partner) | none | Filings since 2001; results have no snippets, so up to eight documents are fetched and quoted; the relation label is keyword-based |
| Stooq | End-of-day share prices; fiscal-year-end closes for multiple history | none | End-of-day only; non-commercial use with attribution. **As of 2026-10-30 Stooq answers automated clients from cloud networks with a JavaScript bot check (or resets the connection).** DEEPTERMINAL detects this, reports it and does not try to pass the check, so Stooq may not work at all from servers |
| SEC Form 4 insider trades | Price fallback when no end-of-day source works: volume-weighted price of insiders' open-market purchases and sales (codes P and S) on the latest trade date | none | A real, dated market transaction price, but **not an official close**; only as recent as the latest insider trade (often weeks old, so the verdict's 7-day freshness rule then marks it too uncertain); labelled as such everywhere |
| Alpha Vantage (free tier) | End-of-day share prices: fallback after Stooq | free key, no payment (`DEEPTERMINAL_ALPHAVANTAGE_API_KEY`) | 25 requests/day; last 100 daily closes only; only the free `TIME_SERIES_DAILY` compact endpoint is called; the key is redacted from logs and cache metadata |
| FRED (keyless CSV) | Treasury yields, breakeven inflation, credit spreads, policy rate, unemployment | none | Daily or monthly frequency; some series are revised; some carry third-party copyright notices (cite FRED and the source) |
| Federal Register API | Federal rules and notices that name the company | none | Federal publications only; no court dockets. Many full-text matches are exchange rule filings listing a ticker; only documents naming the company in the title or abstract become findings, and the rest are counted |
| OFAC SDN list | Sanctions name screening of the company and its listed subsidiaries | none | Exact normalised name match only; aliases (alt.csv) not screened; a match is not an identification, and no match is not clearance |
| Internet Archive (Wayback availability) | Earliest snapshot of the company website (the domain comes from the SEC profile or, if empty, the domain the 10-K names most) | none | Availability only, not content. The API's "closest to today" answer can be years old, so no "latest snapshot" is reported |

### Not available for free (shown as unavailable, never invented)

The following data has no free, legally reusable source, so DEEPTERMINAL leaves it out:

- consensus estimates and analyst revisions;
- licensed news sentiment;
- product reviews and app usage;
- short interest and borrow cost;
- options flow;
- customs and bill-of-lading data;
- state corporate-registry bulk data;
- full 13F aggregation;
- court dockets (PACER charges per page).

Each appears in the UI as **unavailable**, with the reason. Forward P/E uses your own forward-EPS
estimate.

## The cost guard

All outbound HTTP from the application goes through `deepterminal/costpolicy.py`:

- **Allowed.** Hosts in `FREE_SOURCES`, and the local machine (Ollama, the API itself).
- **Paid** (`api.anthropic.com`, `api.openai.com`). Refused with `PaidRequestBlocked` unless
  `DEEPTERMINAL_ALLOW_PAID_APIS=true`.
- **Everything else.** Refused with `UnapprovedHostBlocked`. A new integration cannot send
  requests until its host is classified as free.

The check runs in two places, before any network traffic:

- **The shared fetcher** (`CachedFetcher._fetch`), which every data source uses.
- **The paid SDKs' HTTP clients.** Anthropic and OpenAI get a guarded `httpx` client
  (`guarded_http_client`), so even a constructed SDK client cannot reach its API without opt-in.

### AI provider selection

AI provider selection (`research/providers/__init__.py`):

| `DEEPTERMINAL_LLM_PROVIDER` | Behaviour |
|---|---|
| `auto` (default) | Ollama if it is running with the configured model; otherwise rule-based. **Never a paid provider.** |
| `ollama` | Ollama, or rule-based if it is not running. No paid fallback. |
| `rules` | Deterministic tools only, with no generated prose. |
| `anthropic` / `openai` | Used only if `DEEPTERMINAL_ALLOW_PAID_APIS=true` **and** the key is set. |

### Budgets and visibility

- **Budgets.** The daily token budget counts only paid-provider tokens; local tokens are free.
  Per-call, per-job and tool-call limits still apply to every model.
- **Visibility.** The Settings screen shows a zero-cost banner (or a red warning if paid APIs are
  enabled), each provider with a free or paid label, and every data source with its cost and
  free-tier limits. Every external request is recorded in `data_fetches` (Settings → Retrieval
  log).

## Keeping a local model honest

Smaller local models are more likely to invent plausible numbers. These rules apply to every model,
local or paid:

1. **The model never chooses valuation inputs.** The `valuation` tool takes no arguments. It uses the
   user's discount rate (the job's, or the latest saved valuation run's in chat) and the engine's
   documented defaults. With no user discount rate it returns "no valuation was run".
2. **Figures must come from the evidence.** `guard.ground()` removes any generated sentence whose
   figures do not appear in the material the model was given, comparing across units. On
   2026-10-30, a real `qwen2.5:7b` synthesis invented a "$300 to $450 per share" range; it is now
   removed.
3. **Citations are checked.** Grouped citations (`[E1, E2]`) are split, and ids the model did not
   receive are removed.
4. **The synthesis always sees the valuation findings.** Valuation and market-expectation findings
   are pinned in the evidence pack, so the model cannot wrongly claim no valuation was run.
5. **Local profile for speed.** The local profile sends the 40 most material findings and 30
   evidence documents, with a 900-token answer and a 16k context window. On a 4-core CPU a
   synthesis takes about 6 minutes; a GPU makes this seconds.

## Running locally with local AI

1. Install Ollama (free) from ollama.com, or use the `ollama` service in docker-compose.
2. Pull a model with tool calling. This is about 4.7 GB, done once:

   ```bash
   ollama pull qwen2.5:7b-instruct
   ```

3. Start DEEPTERMINAL. Settings → AI engine shows "ollama · ready", and the top bar shows
   `AI: local · qwen2.5:7b-instruct`.

Smaller or larger models work through `DEEPTERMINAL_OLLAMA_MODEL`. Check each model's licence:
Qwen2.5 0.5B/1.5B/7B/14B/32B are Apache-2.0, but Qwen2.5-3B and 72B use other licences.

Without a model, the app stays fully usable:

- **Investigations and the Thesis Challenger** run their deterministic tools.
- **Chat** answers extractively, with ranked, verified quotes.

## Verification

| What | Result |
|---|---|
| Paid hosts refused without opt-in; unknown hosts refused | Unit tests (`backend/tests/test_zero_cost.py`) |
| Default provider is never paid, even with keys present | Unit test with fake keys set |
| **Real local model** (Ollama 0.6.8, `qwen2.5:7b-instruct`, 4 CPU cores, no GPU) | Live 2026-10-30: tool calls executed, citations correct, growth computed correctly (2m15s for a two-tool question) |
| Local-AI path through the API | Tests against an Ollama-protocol scripted server, plus live runs (§ STATUS) |
| FRED keyless CSV | **Live:** DGS10 5.05% (2026-10-28), DGS3MO, T10YIE, BAA10Y, FEDFUNDS, UNRATE |
| Federal Register API | **Live:** NVIDIA search returned exchange rule filings, which are ranked as incidental |
| OFAC SDN list | **Live:** 19,484 entries; NVIDIA and its subsidiaries have no exact match |
| Internet Archive availability | **Live:** www.nvidia.com earliest snapshot 1996-11-12 |
| EDGAR full-text search | **Live:** 100 hits from 83 other filers for NVIDIA |
| Stooq | **Live: refused.** Connection resets and a JavaScript bot-check page; detected and reported, not circumvented |
| Alpha Vantage free tier | Parser, key redaction and rate-limit handling tested offline. Host not reachable from the sandbox; needs a free key |
