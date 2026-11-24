# Release scope and continuation plan

Updated 2026-11-19. v0.3.0 is a private, single-user research terminal with a reproducible offline
demo. It does not require paid APIs. See `STATUS.md` for evidence and limits.

## Completed release capabilities

- Deterministic valuation and reverse DCF, provenance, financial validation and report/dashboard exports.
- Genuine SEC recordings, offline integration tests, and full-pipeline replay for AAPL, MSFT and NVDA.
- FastAPI/PostgreSQL persistence, migrations, jobs and evidence store.
- Next.js terminal, valuation laboratory, company comparisons and source-linked research screens.
- Filing comparisons, management, demand, supply-chain, sentiment and analogue modules.
- Rules/local-Ollama research, thesis challenger and guarded narrative synthesis.
- Docker image, five-company frozen demo, PDF and browser smoke suite.

## Release acceptance

| Gate | Evidence |
|---|---|
| Maths matches independent calculations and identities | Core unit tests, DCF/reverse-DCF round trips |
| Temporal/provenance discipline | SEC recordings with SHA-256 sidecars; look-ahead and restatement tests |
| Genuine price path | Archived Form 4 trades, original source URLs, snapshot equality tests |
| Application workflow | PostgreSQL API suite and 14 desktop/mobile Playwright E2E tests |
| Offline demo | Image build and 37 signed-out smoke checks |
| Zero-cost operation | Cost guard, unavailable states and rules fallback tests |
| AI safeguards | Citation validation, unsupported-number and uncited-claim regressions |

Use the release commit's GitHub Actions checks as the pass/fail authority. The historical test
prices and assumed discount rates are explicitly labelled and do not establish present value.

## Next milestones (outside this release)

1. **Measured AI quality.** Freeze questions, expected evidence and missing-data cases; compare local
   model answers for faithfulness, interpretation errors, abstention and latency. Retain the
   deterministic findings as authority. A valid citation alone is insufficient.
2. **Broader real-data coverage.** Complete cross-industry live acceptance on AAPL, KO and CAT;
   segment facts, larger analogue universe and more filing formats. Existing recordings cover
   those companies but the price-based replay set is AAPL/MSFT/NVDA.
3. **Current-price reliability.** Check permitted free end-of-day availability on the user's machine;
   preserve manual dated/source-attributed entry and stale-price uncertainty when unavailable.
4. **Historical intelligence.** Curated episodes and documented selection, including failures;
   multi-source contradiction evaluation and richer supply-chain scenarios.
5. **Productisation.** Accounts/tenant isolation, refresh jobs and alerts only when needed.

Public hosting is optional and remains disabled until explicitly configured. Keep scope changes
separate from stabilising this release; no paid data or provider is required.
