# DEEPTERMINAL

**Equity research with source-linked evidence, transparent valuation and local AI.**

[![Tests](https://github.com/NimaMema/deepterminal-portfolio/actions/workflows/tests.yml/badge.svg)](https://github.com/NimaMema/deepterminal-portfolio/actions/workflows/tests.yml)
[![Docker demo](https://github.com/NimaMema/deepterminal-portfolio/actions/workflows/demo-image.yml/badge.svg)](https://github.com/NimaMema/deepterminal-portfolio/actions/workflows/demo-image.yml)
[Release notes](docs/RELEASE_NOTES.md) · [Quick start](#quick-start) · [Architecture](#architecture) · [Verification](#testing) · [Scope and limitations](docs/STATUS.md)

DEEPTERMINAL brings SEC filings, financial statements, company research and valuation into one
research terminal. It separates three questions: **is this a good business, what is it plausibly
worth, and what does the observed share price already assume?**

The calculation engine handles the financial maths. The optional local AI layer helps explore
evidence and draft research, with citation and numeric checks. Assumptions, source dates and
missing data remain visible.

## Quick start

1. **Install and open Docker.** Use Docker Desktop for [Windows](https://docs.docker.com/desktop/setup/install/windows-install/) or [macOS](https://docs.docker.com/desktop/setup/install/mac-install/). On Linux, use [Docker Engine with the Compose plugin](https://docs.docker.com/compose/install/linux/).
   - Windows on Intel or AMD: choose **x86_64 / AMD64**. Windows on ARM: choose **Arm64**.
   - Mac with an M-series chip: choose **Apple silicon**. For an Intel Mac, choose **Intel chip**.
2. **[Download the ZIP](https://github.com/NimaMema/deepterminal-portfolio/archive/refs/heads/main.zip)** and extract it. On GitHub you can also choose **Code → Download ZIP**.
3. **Open a terminal in the extracted folder** containing `docker-compose.yml`. On Windows, open the folder in File Explorer, type `powershell` in the address bar, and press Enter. On macOS, open Terminal, type `cd ` (with a space), drag the extracted folder into the window, and press Return. On Linux, open a terminal from the extracted folder or use `cd` with its path.
4. **Start the demo** by running this command. The first launch downloads and builds the containers, which can take several minutes.

   ```sh
   docker compose up --build --wait db api web
   ```

5. **Open [localhost:3000](http://localhost:3000)** and search for **DQD** to explore Demo Quantum Devices. The demo uses fictional companies and needs no Git, Python, Node.js, API keys, or local AI model on your computer.

### Try a valuation

Load sample share prices from the same terminal.

```sh
docker compose exec api python /app/scripts/seed_demo.py --no-jobs
```

Open **DQD → Valuation laboratory**, enter `0.09` as an example discount rate (9%), and click **Run valuation**.

To stop DeepTerminal while keeping your data, run `docker compose down` in the project folder. To start it again, run the command in step 4.

### Troubleshooting

| What you see | What to do |
|---|---|
| `docker` is not recognized or the command is missing | Install Docker, reopen your terminal, and run `docker compose version`. |
| Docker cannot connect to the engine | Open Docker Desktop and wait for it to finish starting. On Linux, start the Docker service. |
| Compose cannot find a configuration file | Open your terminal inside the extracted folder containing `docker-compose.yml`. |
| Port 3000 or 8000 is already in use | Close the app using that port and rerun the startup command. |
| A container fails to start | Run `docker compose logs --tail=80 api web db` to see the startup error. |

To run with live SEC data, use the [development setup](#local-development). For optional local AI in Docker, run `docker compose up -d ollama`, then `docker compose exec ollama ollama pull qwen2.5:7b-instruct` (about 4.7 GB).

![NVIDIA research overview using recorded SEC data](docs/screenshots/live-01-nvda-overview.png)

*Real NVIDIA data retrieved in October 2026; this is a recorded research example, not a current quote.*

## Project at a glance

| Area | What it does |
|---|---|
| Research | 14 modules covering filings, forensic accounting, management, supply chain, competitors and more |
| Valuation | DCF, reverse DCF, comparables, scenarios and sensitivity analysis |
| Evidence | Source passages and XBRL provenance, with an evidence drawer and filing time machine |
| Output | Company comparisons, research reports and PDF export |
| Stack | Next.js, TypeScript, FastAPI, PostgreSQL, Python and optional local Ollama |
| Validation | v0.3.0: 107 core, 94 API, 9 frontend, 14 browser and 37 demo smoke checks passed; typecheck, lint, builds and container PDF verified |

**No paid API is required.** The app runs on your own hardware with free public data and local
computation. Paid providers are disabled by default. Free sources have access and freshness
limits; see [the free-data architecture](docs/FREE_ARCHITECTURE.md).

**Data modes:** the built-in local demo uses fictional companies clearly marked “Demo”.
Screenshots prefixed `live-` show recorded real-company data. The five-company offline snapshot
contains NVIDIA, Apple, Microsoft, AMD and Intel. No public demo is currently hosted.
Local-model prose remains experimental; a valid citation alone does not establish correctness.

| | Question | Where it is answered |
|---|---|---|
| **Quality** | Is this fundamentally a strong business? | Statements, forensic accounting, management, supply chain, customers, competitors |
| **Value** | What is a defensible *range* of intrinsic value? | Valuation laboratory: DCF, multiples, SOTP, NAV, bear/base/bull, sensitivity |
| **Expectations** | What must happen for today's price to make sense? | Reverse DCF: implied growth, margin, IRR, duration, iso-value curve, expectations gap |

## Contents

- [Tour](#tour)
- [Live SEC data](#live-sec-data)
- [Principles](#principles)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Local development](#local-development)
- [Demo scenarios](#demo-scenarios)
- [Configuration](#configuration)
- [Testing](#testing)
- [API](#api)
- [Data sources and status](#data-sources-and-status)
- [Security](#security)
- [Known limitations](#known-limitations)
- [Documentation](#documentation)

## Tour

| | |
|---|---|
| ![Terminal](docs/screenshots/01-terminal.png) **Terminal.** Search by ticker, name or CIK; watchlist; recent research; ⌘K palette | ![Financial statements](docs/screenshots/03-financial-statements.png) **Financial statements.** Annual, quarterly and TTM; every cell opens its XBRL fact, filing and retrieval time |
| ![Time machine](docs/screenshots/04-filing-time-machine.png) **SEC filing time machine.** What was knowable on any past date, what was filed later, which figures were revised | ![Forensic accounting](docs/screenshots/05-forensic-accounting.png) **Forensic accounting.** Piotroski, Beneish, Altman, accruals and anomaly screens, shown with their components and caveats |
| ![Supply chain](docs/screenshots/06-supply-chain.png) **Supply-chain graph.** Each supplier edge is backed by the sentence that disclosed it; disruption scenarios feed the valuation engine | ![Valuation lab](docs/screenshots/07-valuation-lab.png) **Valuation laboratory.** Editable assumptions with rationale; scenarios; sensitivity; multiples; SOTP and NAV calculators |
| ![Reverse DCF](docs/screenshots/08-reverse-dcf.png) **Reverse DCF.** Solves one lever at a time, prints what was held constant, and draws every margin/growth pair the price implies | ![Investigation](docs/screenshots/09-investigation.png) **Investigation.** 14 research modules run as a background job with live progress and structured, cited findings |
| ![Thesis challenger](docs/screenshots/10-thesis-challenger.png) **Thesis challenger.** Breaks a thesis into claims and returns the strongest counter-evidence, alternative explanations and what it searched without finding | ![Research chat](docs/screenshots/11-research-chat.png) **Research chat.** Answers cite evidence ids that resolve to source passages (extractive mode shown; with Ollama running, a local model answers through the same cited tools) |
| ![Evidence drawer](docs/screenshots/16-evidence-drawer.png) **Evidence viewer.** Source, dates, locator, verification status, limitations, and the passage highlighted in the retrieved document | ![Report](docs/screenshots/14-report.png) **Research reports.** 21 sections plus a bibliography, rendered from stored evidence and exported to PDF |
| ![Compare](docs/screenshots/13-compare.png) **Compare companies.** Side-by-side economics from each company's own filings | ![Data sources](docs/screenshots/15-data-sources.png) **Settings and data sources.** Live status, licence and cost of every source, plus AI budget limits |

The other screens include company overview, SEC filing explorer, corporate and management
intelligence, customers and demand, competitors, sentiment and hype, historical analogues, and
saved research. The UI works on mobile ([screenshot](docs/screenshots/17-mobile.png)).

## Live SEC data

The same screens on **real SEC EDGAR data** for NVIDIA (retrieved 2026-10-29). Every figure, supplier
and quote links to the filing it came from.

| | |
|---|---|
| ![NVIDIA overview](docs/screenshots/live-01-nvda-overview.png) **Overview.** Annual revenue and margins FY2015–FY2026 from XBRL; recent material filings | ![NVIDIA financials](docs/screenshots/live-02-nvda-financials.png) **Statements.** Share counts restated to one basis across the 2021 and 2024 splits, with the adjustment shown in each cell's provenance |
| ![NVIDIA supply chain](docs/screenshots/live-03-nvda-supply-chain.png) **Supply chain.** Only relationships NVIDIA itself states ("we utilize foundries, such as TSMC… and Samsung") | ![NVIDIA chat](docs/screenshots/live-04-nvda-research-chat.png) **Research chat.** Extractive answer ranked at sentence level, each quote verified against the stored 10-K |
| ![NVIDIA competitors](docs/screenshots/live-05-nvda-competitors.png) **Competitors.** User-chosen peers (AMD, Intel) with the rationale from NVIDIA's 10-K | ![NVIDIA analogues](docs/screenshots/live-06-nvda-analogues.png) **Historical analogues.** Point-in-time profiles of loaded companies (Apple 2010–12, AMD, Microsoft) and what happened next |
| ![NVIDIA valuation](docs/screenshots/live-07-nvda-valuation.png) **Valuation on a real price.** $222.80 from SEC Form 4 open-market trades (free), with an illustrative discount rate referenced to FRED's 10-year yield | ![NVIDIA reverse DCF](docs/screenshots/live-08-nvda-reverse-dcf.png) **Reverse DCF on a real price.** What $5.6tn of market value implies: about 36% first-year growth, or a 59% steady-state margin |
| ![Local AI chat](docs/screenshots/live-09-nvda-local-ai-chat.png) **Local AI, zero cost.** `qwen2.5:7b` through Ollama on CPU answers with engine and 10-K citations; any figure not in the evidence is removed | |

**What real filings taught the parser.** These are things synthetic data never shows, each now a
regression test on genuine recorded responses:

- **Supplier lists.** Competitor lists that mention "suppliers" are not supplier relationships.
- **Customer concentration.** "Customers outside the US: 48%" is not a single customer.
- **Stock splits.** NVIDIA's 4:1 and 10:1 splits are not restatements; share histories must be put
  on one basis.
- **Decision dates.** Revenue tags change (NVIDIA, 2022), so a point-in-time decision date must
  follow the first public figure across tags, or the backtest leaks the future.
- **Exhibit names.** Exhibit file names are arbitrary (`subsidiariesofregistrantfy.htm`); the filing
  index's declared document type is reliable.
- **Restatements.** Coca-Cola's Q1 2019 revenue was restated after the nine-month figure was
  filed. The quarterly tie-out explains that gap instead of failing.

## Principles

- **Deterministic maths, AI for research.**
  - Valuation and forensic calculations are pure Python, tested against hand calculations and
    closed-form identities.
  - Language models choose tools, read evidence and draft prose. They never supply numbers.
- **Cite or omit.**
  - `save_finding` refuses a finding without evidence.
  - LLM output may only cite evidence ids that were actually retrieved for that job; others are
    removed and counted.
- **Unavailable is an answer.**
  - Missing data is reported as missing, with the reason and what would fix it: blocked host,
    missing key, licensed data, or adapter not built.
  - Nothing is imputed or invented, including prices and a company's cost of capital.
- **Epistemic labels everywhere.** Verified fact, company statement, third-party report,
  estimate, model assumption, analytical inference and unverified are kept distinct in the data
  and the UI.
- **Qualified verdicts only.**
  - Verdicts read like *"Potentially overvalued under specified assumptions"*, and drop to *"Too
    uncertain to assess reliably"* when evidence is weak.
  - Scenario probabilities are not weighted without a calibration basis.
  - There are no buy or sell calls.
- **Retrieved text is untrusted.** Documents are wrapped as data, scanned for injected
  instructions, and never allowed to change tool permissions.

## Architecture

```mermaid
flowchart TD
  UI["Next.js research terminal"] --> API["FastAPI and background jobs"]
  DATA["SEC filings and free sources"] --> API
  API --> CORE["Python valuation engine"]
  API --> AI["Optional local Ollama"]
  API --> DB["PostgreSQL evidence store"]
  CORE --> REPORT["Reports and PDF"]
  DB --> REPORT
```

- **One evidence store.** Every module writes `Finding` rows that reference `Evidence` rows, each
  pointing at a `Source`. The UI's citation chips, the chat and the report all read the same
  store.
- **Jobs.** Investigations, thesis challenges and reports run as background jobs. Progress events
  stream over SSE, and the UI falls back to polling.
- **Point-in-time.** Statements, the time machine and the analogue engine use only facts filed
  by the analysis date. Restatements are detected and surfaced.

More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/DATA_MODEL.md](docs/DATA_MODEL.md) and [docs/AGENTS.md](docs/AGENTS.md).

## Local development

Requirements: Python 3.11+, Node 22, PostgreSQL 16.

```bash
createdb deepterminal
```

```bash
pip install -e . -e "./backend[dev,pdf]" && python -m playwright install chromium
```

```bash
(cd frontend && npm ci)
```

```bash
cp .env.example .env
```

```bash
scripts/dev.sh
```

`scripts/dev.sh` runs migrations, then starts the API on :8000 and the web UI on :3000. Then:

```bash
python scripts/seed_demo.py
```

Stop both servers with:

```bash
scripts/dev.sh stop
```

### Live SEC data

```bash
export DEEPTERMINAL_DATA_MODE=live
export DEEPTERMINAL_SEC_USER_AGENT="Your Name you@example.com"
scripts/dev.sh
```

- **User-Agent.** The SEC's fair-access policy requires a contact e-mail in the User-Agent.
- **Hosts.** Live mode needs outbound access to `www.sec.gov`, `data.sec.gov` and
  `efts.sec.gov`.
- **Using it.** Search any ticker; DEEPTERMINAL fetches submissions, XBRL facts and filings,
  caches them, and records every fetch.

### CLI (calculation core only)

The original command-line engine still works on its own:

```bash
deepterminal value AAPL --price <observed> --price-as-of YYYY-MM-DD --price-source "<where>" --discount-rate 0.085
```

```bash
deepterminal analyze fixtures/synthetic_widget_corp.json --report out/report.md --dashboard out/dashboard.html
```

## Demo scenarios

Each fictional company exercises a different workflow. Use [the sample-price command](#try-a-valuation) to explore valuation and reverse DCF.

| Company | What to look at |
|---|---|
| **DQD** Demo Quantum Devices | Sole-source foundry in Taiwan (supply-chain graph), export controls, FY2023 revenue restatement (time machine), customer concentration, AI narrative intensity vs revenue, potentially overvalued at the demo price |
| **DHB** Demo Harbor Beverages | Mature, steady business; approximately fairly valued; net debt |
| **DIM** Demo Ironworks Machinery | Cyclical margins; historical analogues; approximately fairly valued |
| **DCS** Demo Cloudline Software | Auditor change (8-K 4.01), heavy SBC, deferred revenue and RPO demand tests; potentially undervalued |
| **DNR** Demo Northfield Retail | Going-concern language, losses, negative base value; the verdict is "Too uncertain to assess reliably" |

Suggested walkthrough:

1. Open **DQD**, press **Investigate** and watch the live progress.
2. Open any **E-number** citation to see the source passage.
3. In the **Valuation lab**, enter a WACC and run it.
4. In **Reverse DCF**, see what the price implies.
5. In the **Thesis challenger**, paste *"DQD has durable pricing power and no customer concentration
   risk"*.
6. Generate a **Report** and download the PDF.

## Configuration

All settings are environment variables; see [`.env.example`](.env.example).

| Variable | Purpose |
|---|---|
| `DEEPTERMINAL_DATA_MODE` | `demo` (synthetic) or `live` (SEC EDGAR) |
| `DEEPTERMINAL_SEC_USER_AGENT` | Required for live mode: `"Name email"` |
| `DEEPTERMINAL_LLM_PROVIDER` | `auto` (default: local Ollama if running, else rule-based), `ollama`, `rules`, or the opt-in paid providers `anthropic`/`openai` |
| `DEEPTERMINAL_OLLAMA_URL`, `DEEPTERMINAL_OLLAMA_MODEL` | Local AI server and model (default `qwen2.5:7b-instruct`, Apache-2.0) |
| `DEEPTERMINAL_PRICE_PROVIDER` | `stooq` (free end-of-day prices) or `none` |
| `DEEPTERMINAL_ALLOW_PAID_APIS` | `false` by default. Paid AI APIs stay blocked at the network level unless this is `true` *and* a paid provider is selected |
| `DEEPTERMINAL_LLM_MAX_OUTPUT_TOKENS`, `…_MAX_TOOL_CALLS`, `…_MAX_INPUT_TOKENS_PER_JOB` | Limits for every model; `…_DAILY_TOKEN_BUDGET` caps paid-API tokens only |
| `DEEPTERMINAL_API_TOKEN` | If set, the API requires a bearer token. The web server adds it to proxied requests so it never reaches the browser |
| `DEEPTERMINAL_RATE_LIMIT_PER_MINUTE` | Per-IP API rate limit |

## Testing

| Suite | Command | Current result |
|---|---|---|
| Calculation core | `pytest -q` | 107 passed, including genuine SEC recordings, archived price replay and provenance checks |
| API on PostgreSQL | `pytest -q backend/tests` | 94 passed (v0.3.0 release CI) |
| Web unit tests | `cd frontend && npm test` | 9 passed |
| Typecheck and lint | `npm run typecheck && npm run lint` | clean, zero warnings |
| Browser E2E | `cd frontend && npx playwright test`, with the stack running in demo mode | 14 passed (desktop and mobile, axe accessibility, zero-cost settings) |

- **API tests.** These use a separate `deepterminal_test` database and refuse any database not named `*_test`. They run migrations from
  scratch and execute jobs synchronously.
- **E2E workflow.** Search, statements provenance, palette, price entry, valuation, reverse DCF,
  background investigation with the evidence drawer, thesis challenger, cited chat, report and
  PDF, supply-chain evidence, unavailable states, accessibility, and mobile layout.
- **How the maths is verified.** The core is checked against independently derived results, not
  snapshots of its own output:
  - hand-computed DCF;
  - perpetuity, mid-year and terminal-ROIC identities;
  - reverse-DCF round trips;
  - every iso-value point reproducing market EV;
  - residual income equalling DDM under clean surplus;
  - dilution and the EV bridge;
  - Piotroski, Beneish and Altman components;
  - point-in-time SEC parsing with a restatement.
- **CI** ([`.github/workflows/tests.yml`](.github/workflows/tests.yml)) runs all of the above on every push.

## API

Interactive OpenAPI documentation is at **`/api/docs`** (raw schema at `/api/openapi.json`).
The main groups:

| Group | Endpoints |
|---|---|
| Companies and filings | `GET /api/search`, `/companies/{id}`, `/statements`, `/filings`, `/filings/{accession}`, `/search` (full text), `/risk-diff`, `/time-machine`, `/events`, `/insiders`, `/graph`, `/compare` |
| Evidence | `GET /api/companies/{id}/findings`, `/evidence/{id}` (with source context) |
| Valuation | `POST /api/companies/{id}/valuation`, `/valuation/shock`, `/valuation/sotp`, `/valuation/nav`; prices and peers CRUD |
| Research | `POST /api/jobs` (investigation, thesis, report), `GET /jobs/{id}/stream` (SSE), chat sessions and messages |
| Reports | `POST /api/reports`, `GET /reports/{id}/html`, `/reports/{id}/pdf` |
| Workspace and system | `/api/saved`, `/api/status`, `/api/sources`, `/api/fetch-log`, `/api/health` |

## Data sources and status

| Source | Status |
|---|---|
| SEC EDGAR (submissions, XBRL, filings, full text) | Verified live (NVIDIA, Apple, Microsoft, AMD, Intel). Genuine recorded responses for AAPL, KO, CAT, MSFT and NVDA replay offline in tests |
| EDGAR full-text search (who names the company) | Verified live (NVIDIA: 100 hits from 83 other filers, quoted) |
| Share prices (free chain) | Stooq end-of-day, then Alpha Vantage free tier (free key), then **SEC Form 4**: the volume-weighted price of insiders' latest open-market trades, labelled "not an official close". Verified live: Stooq refused this network with a bot check (respected), so Form 4 supplied real prices for NVIDIA, Apple and Microsoft, which flowed through the valuation and reverse DCF |
| FRED, Federal Register, OFAC SDN, Internet Archive (free) | Verified live (e.g. 10-year Treasury 5.05% on 2026-10-28; 19,484 SDN entries screened; nvidia.com archived since 1996) |
| AI: Ollama (local, free) | Verified live with `qwen2.5:7b-instruct` on CPU: tool use, cited answers, investigation synthesis. A grounding guard removes any generated sentence whose figures are not in the evidence; a real run invented a value range, and it is now removed |
| Paid AI APIs (Anthropic, OpenAI) | Off by default and blocked by the cost guard; optional opt-in |
| News, estimates, reviews, social, short interest, options, trade data, registries | No free, legally reusable source. Each screen shows these as *unavailable* with the reason |

The live status of every source appears under **Settings and data sources**. The per-component
checklist is in [docs/STATUS.md](docs/STATUS.md).

## Security

- **Secrets.** Secrets live only in server environment variables. The UI shows whether a key is
  set, never its value.
- **API access.**
  - Optional bearer-token protection; the token is added server-side by the web proxy.
  - Per-IP rate limiting.
  - Security headers.
  - A strict CSP on rendered reports.
  - PDF rendering blocks all network requests.
- **Untrusted input.**
  - Retrieved documents are treated as untrusted. They are wrapped as data, scanned for injected
    instructions, and parsed with `defusedxml` for XML.
  - Tool schemas are strict, and LLM citations are validated against retrieved evidence.
- **Zero-cost guard.** Every outbound request is checked against the free-source list before any
  traffic. Paid hosts need `DEEPTERMINAL_ALLOW_PAID_APIS=true`, and unknown hosts are refused.
  Model limits apply per call and per job; any paid usage is capped per day and recorded in
  `llm_usage`.
- **SEC fair access.** The SEC client identifies itself, throttles to 8 req/s and caches
  aggressively.

## Known limitations

- **Generated prose.** Local-model output is experimental. Substantive sentences without a valid
  evidence citation are suppressed, as are unsupported figures. A valid citation does not prove
  that an interpretation is correct; inspect the cited passage and deterministic findings.


- **Prices.** There is no free real-time feed. Stooq (end-of-day) can refuse automated clients.
  The SEC Form 4 fallback is a real trade price but can be weeks old, so the verdict then reports
  "too uncertain" unless you value as of the price date or enter a current price.
- **Local model quality and speed.** A 7B model on a 4-core CPU takes minutes per answer, and its
  prose is uneven. DEEPTERMINAL keeps it honest with tools, citation validation, the
  figure-grounding guard and the deterministic engine; a GPU or a larger model improves both.
- **Free-data gaps.** See [docs/FREE_ARCHITECTURE.md](docs/FREE_ARCHITECTURE.md) for every
  free-source limitation.
- **Filing-based modules only.** Corporate, management, customer, competitor and sentiment
  modules analyse filings. External sources such as registries, reviews, news, estimates and
  trade data appear as unavailable until a permitted provider is configured.
- **Analogue universe.** The analogue engine compares only against companies loaded in the
  database.
- **SEC path scope.** US-GAAP, USD, non-financial filers. Banks, insurers and IFRS filers are
  refused rather than mis-modelled.
- **Single-user.** The app has no user accounts.

**Not investment advice.** DEEPTERMINAL produces research and calculations, not
recommendations.

## Documentation

| Document | Contents |
|---|---|
| [STATUS.md](docs/STATUS.md) | Implemented, verified and blocked status per requirement, plus the continuation plan |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md) | Repository layout, adding a module, testing guide, troubleshooting |
| [SPECIFICATION.md](docs/SPECIFICATION.md) | Master specification |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) · [DATA_MODEL.md](docs/DATA_MODEL.md) · [AGENTS.md](docs/AGENTS.md) | Design |
| [VALUATION_METHODS.md](docs/VALUATION_METHODS.md) | Formulas, limitations, verification |
| [DATA_SOURCES.md](docs/DATA_SOURCES.md) | Sources, licensing, access |
| [PHASE1_VERIFICATION.md](docs/PHASE1_VERIFICATION.md) | Real-data pipeline verification |
| [RELEASE_NOTES.md](docs/RELEASE_NOTES.md) | v0.3.0 release notes |
