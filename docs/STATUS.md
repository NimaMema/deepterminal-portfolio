# DEEPTERMINAL implementation status

Updated 2026-11-19 for the private v0.3.0 release. This file describes the implemented release
scope; `ROADMAP.md` separates later work. Automated verification establishes exercised behavior,
not universal financial accuracy or model answer quality.

## Release scope

| Area | Implemented and exercised | Limits |
|---|---|---|
| Platform | Next.js terminal, FastAPI, PostgreSQL migrations, jobs, cache, Docker Compose | Single user; no accounts or tenant isolation |
| SEC data | Ticker/CIK lookup, annual/quarterly/TTM facts, provenance, revisions, filing search and time machine | US-GAAP, USD, non-financial filers; XBRL history starts around 2009 |
| Research | 14 modules; investigation, thesis challenger, cited chat | Filings provide most evidence; undisclosed data stays unavailable |
| Valuation | DCF, reverse DCF, equity bridge, multiples, scenarios, sensitivity, SOTP and NAV | Assumptions need review; no free real-time quote feed |
| Evidence | Stored passages, document locators, dates, epistemic status, source drawer | A citation is a reference, not proof that an AI interpretation follows |
| Reports | Web reports with 21 sections and bibliography, PDF export; standalone CLI has 24 sections | Model prose remains experimental |
| UI | 20 screens, desktop/mobile navigation, accessibility checks on tested routes | Tests cover specified workflows, not every possible input |
| Free sources | SEC, FRED, Federal Register, OFAC, Internet Archive; Stooq and SEC Form 4 price fallback | Source access varies; Stooq previously refused this cloud network |
| AI | Local Ollama or rule-based fallback; explicit cost guard; citation and numeric checks | Cited interpretations can still be wrong; CPU inference can take minutes |
| Offline demo | Five real companies, archived findings/data, restricted writes, no backend outbound traffic | Frozen October 30 snapshot; recorded model examples predate later guards |

## Verification evidence

The baseline at `c566a05` passed GitHub tests run 27 on 2026-10-30:
101 calculation tests plus one skip, 90 API tests, 9 frontend unit tests, typecheck, lint, build,
and 14 Playwright end-to-end tests. Demo-image run 9 at `e10bfbe` built the container and passed
37/37 signed-out browser smoke checks, including PDF, mobile and valuation round trips.

The release removes the observed-price skip by replaying three genuine archived SEC Form 4
observations with their exact source URLs and dates. Tests verify these against the unchanged
response archive. These are historical insider trades, **not current prices or official closes**.
The 9% discount rate is explicitly an illustrative test assumption. The calculation suite now
contains 107 tests. Four additional guard regressions cover uncited interpretations, abstention,
citations following punctuation, and unknown citations/short uncited claims.

Release CI runs the core on Python 3.11–3.13, API on fresh PostgreSQL, frontend checks/build,
Playwright E2E and the Docker demo smoke suite. GitHub Actions results for the release commit are
the authority for whether those checks pass; the counts above do not claim a new local-model run.

## AI quality and remaining limits

The October 30 CPU model runs exposed invented numbers and interpretive mistakes (receivables
versus deferred revenue, and misreading a stale-price uncertainty verdict). Numeric grounding,
valid-citation enforcement and deterministic findings reduce exposure, but **semantic correctness
has not been established**. The private release uses rule-based fallback by default when no local
model is available; the hosted snapshot uses rules only. No claims of publication-ready AI
performance, trading suitability, or a completed research experiment are made.

News, consensus estimates, social feeds, reviews, short interest, options and customs data have
no configured permitted provider. Cross-market historical episodes, multi-user accounts,
scheduled refresh and alerts remain future work. Do not substitute model guesses for these gaps.

## Privacy, cost and publication

The repository stays private. Paid providers are disabled by default and require explicit opt-in.
The demo deployment remains gated by `DEMO_DEPLOY=true` and owner-provided configuration.
Merging to main does not authorize public hosting. A public Hugging Face deployment uploads the
assembled application source and snapshot; see `DEPLOY_DEMO.md` before enabling it.
No external post or public deployment is part of this private release.
