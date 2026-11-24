# DEEPTERMINAL v0.3.0 — research terminal

> Private release. No public deployment or change to repository visibility.

## Release completion (2026-11-19)

- Align calculation-core and API/web versions at 0.3.0.
- Replay genuine archived prices for three companies, preserving dates and original SEC URLs;
  verify them against the frozen snapshot and remove the real-price pipeline skip.
- Suppress uncited substantive AI prose and unknown-source claims, including short claims;
  preserve explicit abstention and citations after sentence punctuation. Cited interpretations
  still need human review.
- Target optional deployment at main, retaining the explicit publication gate.
- Reconcile status and roadmap with actual implementation and remaining limits.

## Highlights

- **Full-stack application.** A Next.js 15 research terminal on a FastAPI and PostgreSQL backend,
  with 20 screens from search to PDF report.
- **Evidence system.**
  - Every finding is backed by stored evidence: source, publication and retrieval dates,
    locator, verification status, epistemic status and limitations.
  - A source viewer shows the quoted passage highlighted in the retrieved document.
- **14 research modules.** These run as background jobs with live progress:
  - SEC filing analysis;
  - corporate legitimacy;
  - management and governance;
  - forensic accounting;
  - supply chain;
  - product;
  - customer and demand;
  - competitors;
  - legal and regulatory;
  - sentiment;
  - historical analogues;
  - valuation;
  - market expectations.
- **SEC filing time machine.** Point-in-time view of what was knowable on any date, with later
  revisions and risk-factor diffs.
- **Valuation laboratory and reverse DCF.** The tested calculation core is integrated into the UI:
  - editable assumptions with rationale;
  - bear/base/bull scenarios, sensitivity and tornado;
  - multiples, including forward P/E from the user's own estimate;
  - SOTP and NAV;
  - supply-shock scenarios;
  - seven-lever reverse DCF with an iso-value curve.
- **Thesis Challenger.** Breaks a thesis into claims and reports counter-evidence, alternative
  explanations, what was searched without finding anything, and what could not be checked.
- **Research chat.** Every answer cites evidence. Without an LLM key it answers extractively, with
  repeated passages collapsed.
- **AI provider abstraction.** Local Ollama (default), rules, or opt-in paid providers:
  - hard budgets per call, per job and per day;
  - prompt-injection guard;
  - citation validation.
- **Reports.** 21 sections plus a bibliography, rendered from stored evidence, with PDF export.
- **Demo mode.** Five fictional companies in exact SEC formats, labelled as synthetic everywhere.

## Zero-cost architecture

- **No required operating costs.** Free public data, local computation, and local AI through
  Ollama with open-weight models (default `qwen2.5:7b-instruct`, Apache-2.0).
- **Cost guard.** Every outbound request is checked against a free-source list before any
  traffic. Paid AI APIs are refused unless `DEEPTERMINAL_ALLOW_PAID_APIS=true` and the provider is
  selected explicitly, and there is no automatic fallback to them. Unknown hosts are always
  refused.
- **New free sources:**
  - Stooq end-of-day prices (latest close and fiscal-year-end closes);
  - FRED macro series (10-year Treasury reference in the valuation lab);
  - EDGAR full-text search, in a new *Mentions by other filers* module;
  - Federal Register search in the legal module;
  - OFAC SDN sanctions screening and Internet Archive website history in the corporate module.
- **Settings screen.** It shows the zero-cost state, free or paid labels for each AI provider, and
  each source's cost and free-tier limits.
- **docker-compose.** Adds a local Ollama service.

## Verified live (zero-cost)

- **Free sources:** FRED, the Federal Register, the OFAC SDN list, the Internet Archive and EDGAR
  full-text search.
- **Real prices:** from SEC Form 4, through the valuation and reverse DCF for NVIDIA, Apple and
  Microsoft.
- **Local model:** `qwen2.5:7b` through Ollama for the investigation synthesis, Thesis Challenger
  and research chat, with the figure-grounding guard.

## Real-data hardening

Running on live SEC EDGAR exposed parser defects that the synthetic data could not. All are fixed and
covered by tests on genuine recorded filings:

- supplier extraction from competitor lists and biographies;
- geographic revenue shares read as single-customer concentration;
- stock splits and ×1000 re-tagging reported as restatements, and share histories on mixed bases;
- look-ahead from a revenue-tag change in analogue decision dates;
- proxy compensation tables;
- Exhibit 21 discovery;
- "AI" term counting;
- sentence-level chat retrieval;
- a race on the first ticker-index load.

## Engineering

- Alembic migrations, typed settings and an optional API bearer token, injected server-side by
  the web proxy.
- Rate limiting, structured logs, and an external fetch log.
- Docker images and docker-compose; `scripts/dev.sh`; `scripts/seed_demo.py`.
- CI covers core (py3.11–3.13), API on PostgreSQL, web typecheck, lint, unit tests and build, and
  Playwright E2E.

## Verification at release

| Suite | Result |
|---|---|
| Core | 107 tests, including genuine SEC financial/price replay and archive-provenance checks |
| API | 90 baseline tests plus 4 citation-guard regressions |
| Web unit | 9 passed |
| Browser E2E | 14 passed (desktop and mobile, axe, zero-cost settings) |

## Known limitations

- **Prices.** There is no free real-time feed. Stooq refuses automated clients from cloud networks
  (bot check, respected). The SEC Form 4 fallback is a real trade price but can be weeks old;
  Alpha Vantage's free tier needs your free key.
- **Local AI is slow on CPU.** `qwen2.5:7b` on 4 cores takes minutes per answer. Its interpretation
  can be wrong in ways no figure check catches; the deterministic findings remain the authority.
- **Free-data gaps.** There are no consensus estimates, licensed news, reviews, short interest,
  options or trade data (no free, legally reusable source). These are shown as unavailable.

See [STATUS.md](STATUS.md) for the per-requirement checklist.
