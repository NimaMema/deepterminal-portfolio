# Development guide

## Repository layout

```
deepterminal/                 calculation core (stdlib only): valuation, reverse DCF, multiples,
                              scenarios, forensics, EDGAR point-in-time parser, validation, CLI
backend/
  deepterminal_api/
    main.py                   app factory: lifespan, CORS, security middleware, error mapping
    config.py                 settings from DEEPTERMINAL_* environment variables
    models.py, db.py          SQLAlchemy 2 models (20 tables) and session
    services/
      gateway.py              LiveGateway (SEC EDGAR) | DemoGateway (synthetic); every fetch logged
      companies.py            search, resolve, profile, statements with per-cell provenance
      filings.py              text extraction, item splitting, FTS search, risk diff, 8-K/Form 4/DEF 14A
      evidence.py             Source/Evidence/Finding drafts and persistence (cite-or-omit)
      valuation.py            core-engine bridge: valuation, shock, SOTP, NAV, saved runs
      reports.py              21-section report (Jinja) and Chromium PDF
      free_sources.py         Stooq, FRED, EDGAR full-text search, Federal Register, OFAC, Wayback
      prices.py               free end-of-day prices stored as attributed observations
    analysis/                 14 research modules: compute(ctx) → data, findings(ctx, data) → findings
    research/
      orchestrator.py         background jobs, JobEvents, investigation and synthesis
      thesis.py               Thesis Challenger
      chat.py                 research chat (LLM or extractive)
      tools.py                tools exposed to LLMs; tracks citable evidence ids
      guard.py                untrusted-content wrapping, injection detection, citation validation
      providers/              Ollama (local, default), rule-based, and opt-in paid providers
    routers/                  companies, valuation, research, workspace, system
    demo/generator.py         synthetic SEC-format dataset (five fictional companies)
  alembic/                    migrations
  tests/                      API tests on PostgreSQL, guard and provider tests
frontend/
  app/                        Next.js App Router pages (20 screens)
  components/                 shell, evidence drawer, charts, tables, graph, jobs, forms
  lib/                        API client, types, formatting, valuation hooks
  middleware.ts               adds the API token to proxied /api requests
  e2e/                        Playwright workflows (desktop and mobile, axe)
  tests/                      Vitest unit and component tests
  scripts/screenshots.cjs     regenerates docs/screenshots from a seeded demo stack
scripts/
  dev.sh                      start/stop API and web
  seed_demo.py                demo companies, labelled prices, investigations
tests/                        core tests (hand calculations, identities, SEC parsing)
```

## Running locally

See the [README quick start](../README.md#quick-start). After changing models:

```bash
cd backend && alembic revision --autogenerate -m "describe change"
```

```bash
cd backend && alembic upgrade head
```

## Adding a research module

1. Create `backend/deepterminal_api/analysis/<name>.py` with the following:
   - `compute(ctx) -> dict`: data for the dashboard. It must work without a job.
   - `findings(ctx, data) -> list[FindingDraft]`. Each finding carries evidence from
     `fact_evidence`, `excerpt_evidence` (verified only when the quote is found in the stored
     document) or `computed_evidence` (listing its input evidence ids).
   - Report sources that cannot be reached with `unavailable(module, source, reason)`. Never
     substitute a value.
2. Register it in `analysis/__init__.py` (`MODULES`).
3. Expose it to the UI through `GET /api/companies/{id}/modules/{key}`. `useModule` in
   `frontend/lib/api.ts` reads it.
4. Add an API test in `backend/tests/test_api.py`.

## Rules the code enforces

- **Zero cost.** All outbound HTTP must go through `deepterminal.data.http.CachedFetcher` (data) or
  `guarded_http_client()` (SDKs), which call `deepterminal.costpolicy.check_url`. To add a data
  source, add its hosts to `FREE_SOURCES` with its licence and limits. Hosts that can bill belong
  in `PAID_HOSTS` and stay off by default.

- `save_finding` raises if a finding has no evidence, unless its severity is `unavailable`.
- LLM text may cite only evidence ids returned by tools in that job (`guard.validate_citations`).
- Valuation requires an explicit discount rate. Multiples and expectations require a price with a
  date and source.
- Synthetic data is flagged at every level: company, source, evidence, report and UI banner.

## Testing guide

| What | How |
|---|---|
| Core maths | `pytest -q` from the repo root |
| API | `pytest -q backend/tests`. Needs PostgreSQL and a `deepterminal_test` database (or `DEEPTERMINAL_TEST_DATABASE_URL`). The suite drops and re-migrates the schema, so it refuses any database whose name does not end in `_test`, whatever `DEEPTERMINAL_DATABASE_URL` says |
| Real-data recordings | `DEEPTERMINAL_SEC_USER_AGENT="Name email" deepterminal record AAPL KO CAT MSFT NVDA --dest tests/recorded/sec`. These are genuine, unmodified responses; tests replay them offline |
| Web unit | `cd frontend && npm test` |
| Types and lint | `npm run typecheck && npm run lint` |
| E2E | Start the stack in demo mode (`scripts/dev.sh`), then `cd frontend && npx playwright test` |
| Screenshots | `python scripts/seed_demo.py`, then `node frontend/scripts/screenshots.cjs docs/screenshots <report-id>` |

The E2E tests create their own state through the UI (prices, jobs, reports), so they work
against a freshly migrated database.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| UI shows "blocked" for SEC data | Outbound access to `*.sec.gov` is denied. Allow the hosts, or use `DEEPTERMINAL_DATA_MODE=demo` |
| PDF export returns `not_configured` | Install the pdf extra and `python -m playwright install chromium`, or set `DEEPTERMINAL_CHROMIUM_EXECUTABLE` |
| `Cannot find module './NN.js'` in `next dev` | `next build` was run while dev was serving. Stop dev, `rm -rf frontend/.next`, restart |
| Chat answers are extractive | No LLM key configured. Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` |
| 401 from the API | `DEEPTERMINAL_API_TOKEN` is set. Set the same value for the web process |
