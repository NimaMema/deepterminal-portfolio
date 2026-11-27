# Phase 1 — SEC data integration and verification

*Historical verification report, 2026-10-29.* This phase verified the SEC pipeline with synthetic
fixtures. See [project status](STATUS.md) for later verification with genuine filings.

## 1. Repository inspection — what was actually implemented before this phase

| Area | Status at start of Phase 1 | Evidence |
|---|---|---|
| Evidence model (epistemic status, look-ahead guard, citation audit) | Implemented | `evidence.py`, tests |
| DCF, bridge, reverse DCF, multiples, comparables, RI/DDM, SOTP, NAV, normalisation, scenarios, method selection, misvaluation verdict | Implemented, tested on hand calculations | `valuation/`, 41 tests |
| Statement analysis & forensic flags | Implemented | `financials/statements.py` |
| SEC EDGAR | **Partial.** Annual companyfacts parser plus a minimal client. No ticker lookup, no 10-Q, no retries, no provenance per figure, never run against live SEC | `data/sec_edgar.py` (v0.1) |
| Real-company valuation | **Not implemented.** Only a hand-built JSON case file (synthetic fixture) could be valued | — |
| Report / dashboard / CLI / schema | Implemented for case files | `reporting/`, `cli.py`, `schema/` |
| Research modules & agents | Designed only | docs |

## 2. Live SEC access

The Phase 1 test network blocked outbound connections to EDGAR, so live fetches were deferred.
The client reports this as `NetworkPolicyBlocked`. Live verification requires a network that
can reach the SEC hosts and a contact address in the User-Agent.

**SEC fair-access requirements** (https://www.sec.gov/os/accessing-edgar-data) and how the
connector meets them:

| Requirement | Implementation |
|---|---|
| Declare a User-Agent identifying you, with contact e-mail | `DEEPTERMINAL_SEC_USER_AGENT` is required for network mode and validated to contain an e-mail address |
| No more than 10 requests per second | Client throttles to 8 req/s (`min_interval=0.125`) |
| Efficient use, no unnecessary re-downloads | On-disk cache (1-day freshness for filings data, 7 days for the ticker list); `--offline` replays the cache |
| Backoff when throttled | 429 and 503 retried with exponential backoff, honouring `Retry-After`; then `RateLimited` |

## 3. What was built in Phase 1

| # | Requirement | Implementation | Tests |
|---|---|---|---|
| 3 | Reliable EDGAR connector | `data/http.py` `CachedFetcher`: retries with backoff and jitter, `Retry-After`, gzip and deflate, raw-bytes cache plus `.meta.json` (URL, UTC retrieval time, status, SHA-256), integrity check on read, offline mode. Typed errors: `NetworkPolicyBlocked`, `AccessDenied`, `RateLimited`, `NotFound`, `OfflineCacheMiss`, `FetchError` | `test_http_client.py` (9) |
| 4 | Real statements → valuation engine | `data/sec_case.py` `build_sec_case` turns companyfacts plus price plus settings into a `Case`, which runs through the existing `run_case` unchanged | `test_sec_pipeline.py` |
| 5 | Lookup by ticker and CIK | `resolve_company` (`company_tickers.json`; `BRK.B`→`BRK-B`; "did you mean"), `enrich_identity` (SIC, FYE, exchanges from submissions), `recent_filings` | `test_lookup` |
| 6 | Historical 10-K and 10-Q | Annual series; discrete quarters from 3-month facts or derived YTD differences (Q4 = FY − 9M); TTM from four contiguous quarters; point-in-time `as_of`; original-vs-latest revisions; multi-concept merge (e.g. `Revenues` → `RevenueFromContractWithCustomer…`) | `test_quarters_ttm_and_point_in_time`, `test_revisions_detected` |
| 7 | Source, period and retrieval date on every figure | `FigureProvenance` on each `FinancialPeriod` field and each capital-structure input: concept, period start and end, form, accession, filing date, filing URL, retrieval time, plus the derivation with its inputs. Shown in report §22, the dashboard panel and `provenance.csv` | `test_every_figure_has_source_period_and_retrieval` |
| 8 | Real data in the dashboard | Header shows the basis (e.g. *TTM to 2026-06-30*); new *Data provenance & validation* panel; multiples use TTM | `test_build_case_and_run` |
| 9 | User-supplied price | `PriceQuote(value, as_of, source, url)`, required and validated (positive, source stated, not after the analysis date). `--price/--price-as-of/--price-source` or `--price-file`. Labelled *user-supplied (not independently verified)* | `test_case_guards`, CLI tests |
| 11 | Verification | `validation.py`: balance-sheet identity, **independent** 9-month vs three-quarter tie-out, revenue-concept consistency, sign sanity, restatements, freshness, TTM availability. FCFF DCF refused for financial-institution SIC codes; IFRS and non-USD filers refused | `test_sec_pipeline.py` |
| 12 | Recorded genuine responses | `deepterminal record` copies cached responses (bytes plus metadata). `tests/integration/test_recorded_sec.py` verifies SHA-256, provenance, validation and the full pipeline. It **skips with a stated reason** until recordings exist | 3 (skipped) |
| 13 | Preserve existing behaviour | All 59 original tests still pass unchanged | — |
| 14 | No fabricated data | Prices never defaulted; discount rate required; synthetic SEC-format data auto-detected and labelled SYNTHETIC in report, dashboard and citation audit; `NO_PRICE` status in batch runs | `test_cli_refuses_missing_price_or_discount_rate`, `test_cli_verify_reports_missing_prices_and_errors` |

### How forecast assumptions are set for real companies
Forecast inputs are **model assumptions**, not data. Unless a settings file overrides them, they
are derived mechanically from the company's own filings, and each rule is written into the
assumption's rationale in the report:

| Assumption | Mechanical default |
|---|---|
| Discount rate | **No default.** Must be supplied |
| Year-1 growth | 3-year revenue CAGR, clamped to [−10%, 40%], fading linearly to terminal growth |
| Operating margin | Latest (TTM or FY) margin, held flat |
| Tax rate | Median effective rate of the last 3 years, clamped to 0–35% (21% statutory if not measurable) |
| Net capex | Median (capex − D&A)/revenue, floored at 0 |
| Working capital | Median ΔNWC/ΔRevenue (receivables + inventory − payables) |
| Terminal growth | 2.5% |
| Terminal ROIC | Equal to the discount rate (no excess returns in perpetuity) |
| Bear/bull | Symmetric mechanical deltas, labelled "not a forecast" |

Capital structure comes from XBRL at the basis date:
- cash plus current and non-current marketable securities;
- `LongTermDebt`, or non-current plus current debt, plus commercial paper;
- minority interest, preferred stock, and the after-tax pension deficit;
- cover-page shares outstanding, with options and RSUs where tagged.

Operating lease liabilities are reported but **not** subtracted, because US GAAP EBIT is already
after lease cost.

## 4. Real companies tested

| Company | Industry | Status |
|---|---|---|
| Apple (AAPL) | Technology hardware (FYE September) | **Not run.** SEC hosts blocked by environment policy; no observed price supplied |
| Coca-Cola (KO) | Consumer staples | **Not run.** Same |
| Caterpillar (CAT) | Cyclical industrial | **Not run.** Same |

The selection (in `examples/verification_manifest.json`) spans three industries and includes a
cyclical case. All three are non-financial US-GAAP USD filers, which is what the FCFF engine
supports. The manifest's prices are intentionally empty. `deepterminal verify` reports
`NO_PRICE` rather than inventing one; it was run and produced exactly that.

## 5. Test results

```
80 passed, 3 skipped
```

| File | Tests | Data |
|---|---|---|
| test_dcf, test_bridge, test_reverse_dcf, test_other_methods, test_scenarios | 41 | Hand calculations and closed-form identities |
| test_pipeline, test_evidence_and_statements, test_schema, test_sec_edgar | 18 | Synthetic fixtures (labelled) |
| test_http_client | 9 | Injected transport (no network) |
| test_sec_pipeline | 12 | Synthetic data in exact SEC companyfacts format (`tests/sec_synth.py`), offline cache |
| integration/test_recorded_sec | 3 | **Skipped:** no genuine recordings available |

**Not verified:** behaviour on genuine SEC responses. Real filings contain tagging variety
(custom extension concepts, multiple debt tags, non-calendar fiscal years, 52/53-week years,
segment-only revenue tags, missing D&A) that synthetic data cannot fully represent. Expect
parser adjustments on the first real run. The validation report and the integration tests are
designed to surface those problems rather than hide them.

## 6. How to complete the real-company run

On a machine or environment that can reach `www.sec.gov` and `data.sec.gov`:

```bash
pip install -e ".[dev]"
export DEEPTERMINAL_SEC_USER_AGENT="Your Name your.email@example.com"
deepterminal lookup AAPL KO CAT
deepterminal fetch AAPL KO CAT                       # caches data; prints periods with provenance
deepterminal record AAPL KO CAT                      # genuine responses → tests/recorded/sec
# fill prices (value, as_of, source) and your discount rates in examples/verification_manifest.json, then:
deepterminal verify examples/verification_manifest.json
pytest -q                                            # integration tests now run on the recordings
```

Acceptance for closing A17 (ROADMAP):
- integration tests pass on all three recordings;
- validation shows 0 FAIL;
- reverse-DCF round trips reproduce market EV;
- the provenance CSV for each company is spot-checked against the filing pages for at least
  revenue, operating income, OCF, capex, cash, debt and shares.

## 7. Phase 1 limitations

- **Data and parsing**
  - Only US-GAAP, USD filers are supported. Financial institutions are refused because the
    residual-income model is not yet wired to SEC data.
  - Multi-class share structures: the companyfacts cover-page share count can omit classes. The
    builder falls back to diluted weighted shares when the count looks partial, and records why.
  - Custom (company-extension) XBRL concepts are ignored. Some companies' revenue, debt or D&A
    may therefore be missing; the case builder then raises instead of guessing.
- **Model**
  - Cyclicality is not detected automatically. Supply a through-cycle `base_margin` for cyclical
    companies (e.g. CAT).
  - No peer data source is connected, so comparables and the peer columns of the expectations
    gap are empty for real companies.
- **Market data**
  - The price is user-supplied and not independently verified. Live or licensed market data is
    not connected, and nothing has been purchased.
