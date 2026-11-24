# DEEPTERMINAL research report — Synthetic Widget Corp (fictional) (DEMO-SWC)

*Case `SYNTHETIC-SWC-2026-10` · analysis date 2026-10-28 · share price 94.00 USD as of 2026-10-27 · monetary figures in USD millions (except per-share values)*

> ⚠️ **SYNTHETIC DATA.** SYNTHETIC FIXTURE. Every number in this file is invented for testing and demonstration. It describes no real company and must not be used for any investment decision.

> This report is analysis, not investment advice. It makes no buy/sell recommendation.


## 1. Executive summary

**Is this a good business?** Partially assessed. Financial-statement evidence only: latest operating margin 18.0%, FCF after SBC 1,170, 1 statement flag(s) for review. Product, competitive, management and supply-chain quality are not yet assessed, so no overall quality conclusion is drawn.

**What is a defensible range of economic value?** 39.75–112.83 per share across bear/base/bull scenarios (base 72.77), conditional on the stated assumptions in §18. No probability weighting is applied because no calibrated probabilities were supplied.

**What expectations are embedded in the current price?** Conditional solution: Year-1 revenue growth (fading to terminal) = 20.47%, holding: EBIT margin path = 18.0%, 18.0%, 18.5%, 18.5%, 19.0%, 19.0%, 19.0%; terminal margin = 19.0%; discount rate = 8.50%; terminal growth = 3.00%; terminal ROIC = 15.0%; reinvestment = sales-to-capital 2.0; forecast horizon = 7 years. This is one point in a family of assumption sets consistent with the price, not a unique market forecast. Alternatively, holding growth at the base path, the price requires a steady-state operating margin of 24.9%.

**What might the market be overlooking?** Not assessed: no sourced research findings were supplied. The Thesis Challenger and research agents are required before anything can be claimed here.

**What evidence could invalidate the thesis?** The base case depends on: capacity expansion completes on schedule; pricing holds with stable input costs. The largest valuation sensitivity is **discount rate** (60.70–90.22 per share).

**Qualified conclusion:** Potentially overvalued under specified assumptions. price 94.00 is more than 20% above base value 72.77; why the market might already understand the gap has not been researched; treat the verdict as provisional.

## 2. Company identity and legitimacy

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Intermediate: corporate legitimacy module). No conclusion is drawn.

## 3. Business model

Sector (from case file): industrial components (fictional). **Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Intermediate: business-model research agent). No conclusion is drawn.

## 4. Financial strength

| FY | Revenue | Growth | Op. margin | FCF | FCF after SBC | Net debt | Interest cover | ROE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 8,000 | n/a | 15.0% | 850 | 730 | 1,600 | 10.9x | 21.0% |
| 2022 | 8,800 | 10.0% | 16.0% | 940 | 805 | 1,400 | 13.4x | 21.7% |
| 2023 | 9,900 | 12.5% | 17.0% | 1,080 | 930 | 1,150 | 16.8x | 22.7% |
| 2024 | 10,600 | 7.1% | 16.5% | 1,140 | 975 | 900 | 18.4x | 21.3% |
| 2025 | 11,500 | 8.5% | 18.0% | 1,350 | 1,170 | 600 | 23.0x | 22.2% |

Source: case-file financial history (see §24). Metrics computed by `deepterminal.financials.statements.analyse`.

## 5. Accounting quality

Automated statement checks (analytical inferences that direct further review, not findings of misconduct):

- FY2024 `RECEIVABLES_OUTPACE_REVENUE` (review): receivables grew 21% vs revenue 7%: check revenue recognition, channel stuffing or collection problems

Revenue-recognition policy, reserves, auditor changes and related-party review: **Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Intermediate: forensic accounting agent). No conclusion is drawn.

## 6. Management and governance

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Intermediate: management analysis). No conclusion is drawn.

## 7. Products and customer satisfaction

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Intermediate: customer review trends). No conclusion is drawn.

## 8. Competitors and industry structure

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Intermediate: competitor intelligence). No conclusion is drawn.

## 9. Supply-chain analysis

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Intermediate: supply-chain research). No conclusion is drawn.

## 10. Revenue and demand sustainability

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Intermediate: demand intelligence). No conclusion is drawn.

## 11. Historical SEC filing changes

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Intermediate: historical filing comparisons). No conclusion is drawn.

## 12. Market sentiment and hype

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Advanced: narrative-versus-fundamentals). No conclusion is drawn.

## 13. Institutional and insider activity

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Intermediate: insider & institutional data (licensed source required)). No conclusion is drawn.

## 14. Historical company analogues

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Advanced: historical analogue selection). No conclusion is drawn.

## 15. Macroeconomic and regulatory exposure

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Intermediate: macro & policy exposure). No conclusion is drawn.

## 16. Valuation methodology

| Method | Role | Reason |
|---|---|---|
| dcf | primary | profitable, cash-generative business supports a DCF |
| reverse_dcf | primary | states the operating outcomes the price requires |
| scenarios | primary | bear/base/bull range instead of a single point |
| ev_ebitda | cross-check | capital-structure-neutral earnings multiple |
| pe | cross-check | common market yardstick |
| forward_pe | cross-check | uses expected rather than trailing earnings (needs licensed estimates) |
| fcf_yield | cross-check | cash return on today's price |
| comparables | cross-check | 5 peers available |
| historical_multiples | cross-check | multi-year multiple history available |

**Market-implied enterprise value bridge** (price × diluted shares, then claims):

- Diluted shares (treasury stock method at market price): 411.9
- Market capitalisation: 38,718
- EV→equity adjustment, excess cash: 1,100
- EV→equity adjustment, debt: -2,100
- EV→equity adjustment, pension deficit (after tax): -60
- EV→equity adjustment, minority interest: -150
- Market enterprise value: 39,928

**Multiples (trailing, at market price):**

- P/E: 25.31x
- PEG: 1.75x
- EV/EBITDA: 15.84x
- EV/Revenue: 3.47x
- P/B: 5.61x
- FCF yield (after SBC): 3.0%
- EV/EBITDA history: current 15.84x vs median 13.00x (percentile 100%, z +2.04, n=8). Context only; mean reversion is not assumed.

**Comparable companies (EV/EBITDA):** peer IQR 10.62x–12.88x (median 11.75x) on EBITDA 2,520 → implied EV 26,775–32,445. Excluded: Synthetic Peer E (multiple missing or not meaningful).

## 17. Reverse DCF and market expectations

Market EV to explain: **39,928**. Each line solves one lever with all others held at the base case:

- Conditional solution: Year-1 revenue growth (fading to terminal) = 20.47%, holding: EBIT margin path = 18.0%, 18.0%, 18.5%, 18.5%, 19.0%, 19.0%, 19.0%; terminal margin = 19.0%; discount rate = 8.50%; terminal growth = 3.00%; terminal ROIC = 15.0%; reinvestment = sales-to-capital 2.0; forecast horizon = 7 years. This is one point in a family of assumption sets consistent with the price, not a unique market forecast.
  - implied year-7 revenue 24,770, revenue CAGR 11.6%, cumulative FCFF 13,639, implied share of stated addressable market 41.3%
- Conditional solution: Steady-state operating (EBIT) margin = 24.94%, holding: revenue growth path = 9.0%, 8.5%, 8.0%, 7.0%, 6.0%, 5.0%, 4.0%; discount rate = 8.50%; terminal growth = 3.00%; terminal ROIC = 15.0%; reinvestment = sales-to-capital 2.0; forecast horizon = 7 years. This is one point in a family of assumption sets consistent with the price, not a unique market forecast.
  - implied year-7 revenue 18,192, revenue CAGR 6.8%, cumulative FCFF 14,894, implied share of stated addressable market 30.3%
- Conditional solution: Implied expected return (IRR on the forecast) = 7.33%, holding: revenue growth path = 9.0%, 8.5%, 8.0%, 7.0%, 6.0%, 5.0%, 4.0%; EBIT margin path = 18.0%, 18.0%, 18.5%, 18.5%, 19.0%, 19.0%, 19.0%; terminal margin = 19.0%; terminal growth = 3.00%; terminal ROIC = 15.0%; reinvestment = sales-to-capital 2.0; forecast horizon = 7 years. This is one point in a family of assumption sets consistent with the price, not a unique market forecast.
  - implied year-7 revenue 18,192, revenue CAGR 6.8%, cumulative FCFF 12,265, implied share of stated addressable market 30.3%

**Iso-value family (margin ↔ growth combinations consistent with the price):**

| Steady-state margin | Implied year-1 growth (fading) |
|---:|---:|
| 11.0% | 45.1% |
| 13.0% | 36.8% |
| 15.0% | 30.3% |
| 17.0% | 25.0% |
| 19.0% | 20.5% |
| 21.0% | 16.7% |
| 23.0% | 13.4% |
| 25.0% | 10.4% |
| 27.0% | 7.7% |

**Growth duration:** at 9.0% growth, the price is justified after **12 year(s)** of that growth (margins held at the final base-case level).

**Expectations gap:**

- revenue CAGR: market-implied 11.6%; company median 9.2% / best 12.5%; peer median 7.0% / best 10.0%; consensus not available (licensed estimates not connected)
  - implied revenue CAGR exceeds every listed peer (peer max 10.0%)
- operating margin: market-implied 24.9%; company median 16.5% / best 18.0%; peer median 16.0% / best 19.0%; consensus not available (licensed estimates not connected)
  - implied operating margin 24.9% exceeds the company's best recorded 18.0%
  - implied operating margin exceeds every listed peer (peer max 19.0%)

## 18. Bear/base/bull scenarios

| | Bear | Base | Bull |
|---|---:|---:|---:|
| Year-1 → final growth | 4.0% → 2.5% | 9.0% → 4.0% | 13.0% → 5.0% |
| Final-year revenue | 14,143 | 18,192 | 21,763 |
| Final-year EBIT margin | 15.0% | 19.0% | 22.0% |
| Cumulative FCFF (explicit) | 9,375 | 12,265 | 15,168 |
| Cumulative reinvestment | 1,468 | 3,346 | 4,462 |
| Discount rate | 9.00% | 8.50% | 8.00% |
| Terminal growth / ROIC | 2.5% / 11.0% | 3.0% / 15.0% | 3.0% / 18.0% |
| Enterprise value | 17,584 | 31,183 | 47,683 |
| Terminal value share of EV | 62% | 72% | 77% |
| Equity value | 16,374 | 29,973 | 46,473 |
| **Value per share** | **39.75** | **72.77** | **112.83** |
| vs. price | -57.7% | -22.6% | 20.0% |

- **bear** — Demand normalises to low single-digit growth, a new low-cost entrant compresses margins to 15%, and higher financing costs lift WACC to 9%. Dependencies: entrant pricing behaviour; order backlog conversion; credit spreads. Sources: SYN-10K-FY2025, SYN-RATES.
- **base** — Growth fades from 9% toward the terminal rate; margins edge up to 19% on operating leverage; reinvestment at the historical sales-to-capital ratio. Dependencies: capacity expansion completes on schedule; pricing holds with stable input costs. Sources: SYN-10K-FY2025, SYN-RATES.
- **bull** — Share gains from a superior product line sustain double-digit growth for four years; operating leverage takes margins to 22%. Dependencies: product benchmarks hold versus competitors; no supply constraint on key components. Sources: SYN-10K-FY2025, SYN-TAM.
  - ⚠️ terminal value is 77% of enterprise value; conclusions are dominated by terminal assumptions

**Sensitivity — base-case value per share (rows: discount rate; columns: terminal growth):**

| | 2.0% | 2.5% | 3.0% | 3.5% | 4.0% |
|---|---|---|---|---|---|
| 6.5% | 101.45 | 108.56 | 117.66 | 129.75 | 146.62 |
| 7.5% | 81.50 | 85.43 | 90.22 | 96.16 | 103.77 |
| 8.5% | 67.72 | 70.05 | 72.77 | 76.01 | 79.95 |
| 9.5% | 57.65 | 59.08 | 60.70 | 62.58 | 64.77 |
| 10.5% | 49.98 | 50.87 | 51.86 | 52.98 | 54.26 |

## 19. Major uncertainties

Assumptions ranked by valuation swing (tornado):

- discount rate: 60.70 (+1% pts) to 90.22 (-1% pts); swing 29.52
- operating margin (incl. terminal): 59.76 (-3% pts) to 85.78 (+3% pts); swing 26.02
- revenue growth (every year): 62.89 (-3% pts) to 84.32 (+3% pts); swing 21.43
- terminal ROIC: 68.21 (-25%) to 75.50 (+25%); swing 7.29
- terminal growth: 70.05 (-0.5% pts) to 76.01 (+0.5% pts); swing 5.96

## 20. Potential catalysts

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Advanced: catalyst calendar & research agents). No conclusion is drawn.

## 21. Counterarguments

**Not assessed.** The research module for this section is not implemented in this version (see docs/ROADMAP.md, milestone Advanced: Thesis Challenger). No conclusion is drawn.

## 22. Evidence coverage and limitations

Evidence quality (case-level): **medium**. Citation audit: 13 values checked, 13 finding(s).

- share price: synthetic fixture data
- discount_rate: synthetic fixture data
- FY2021 financial statements: synthetic fixture data
- FY2021 financial statements: stale: older than 548 days at 2026-10-28
- FY2022 financial statements: synthetic fixture data
- FY2022 financial statements: stale: older than 548 days at 2026-10-28
- FY2023 financial statements: synthetic fixture data
- FY2023 financial statements: stale: older than 548 days at 2026-10-28
- FY2024 financial statements: synthetic fixture data
- FY2024 financial statements: stale: older than 548 days at 2026-10-28
- FY2025 financial statements: synthetic fixture data
- capital structure: synthetic fixture data
- addressable market (final forecast year): synthetic fixture data

**13-step misvaluation investigation status:**

1. ✅ Obtain a timestamped share price — 94.00 as of 2026-10-27
2. ✅ Calculate market capitalisation and enterprise value — market equity 38,718; market EV 39,928
3. ✅ Normalise relevant financial data — No material non-recurring items in the synthetic history; margins have risen steadily rather than cyclically, so no cyclical normalisation applied.
4. ✅ Estimate a range of fundamental values — bear 39.75 / base 72.77 / bull 112.83 per share
5. ✅ Calculate market-implied expectations — Conditional solution: Year-1 revenue growth (fading to terminal) = 20.47%, holding: EBIT margin path = 18.0%, 18.0%, 18.5%, 18.5%, 19.0%, 19.0%, 19.0%; terminal margin = 19.0%; discount rate = 8.50%; terminal growth = 3.00%; terminal ROIC = 15.0%; reinvestment = sales-to-capital 2.0; forecast horizon = 7 years. This is one point in a family of assumption sets consistent with the price, not a unique market forecast.; Conditional solution: Steady-state operating (EBIT) margin = 24.94%, holding: revenue growth path = 9.0%, 8.5%, 8.0%, 7.0%, 6.0%, 5.0%, 4.0%; discount rate = 8.50%; terminal growth = 3.00%; terminal ROIC = 15.0%; reinvestment = sales-to-capital 2.0; forecast horizon = 7 years. This is one point in a family of assumption sets consistent with the price, not a unique market forecast.; Conditional solution: Implied expected return (IRR on the forecast) = 7.33%, holding: revenue growth path = 9.0%, 8.5%, 8.0%, 7.0%, 6.0%, 5.0%, 4.0%; EBIT margin path = 18.0%, 18.0%, 18.5%, 18.5%, 19.0%, 19.0%, 19.0%; terminal margin = 19.0%; terminal growth = 3.00%; terminal ROIC = 15.0%; reinvestment = sales-to-capital 2.0; forecast horizon = 7 years. This is one point in a family of assumption sets consistent with the price, not a unique market forecast.
6. ✅ Compare expectations with historical performance — implied revenue CAGR exceeds every listed peer (peer max 10.0%); implied operating margin 24.9% exceeds the company's best recorded 18.0%; implied operating margin exceeds every listed peer (peer max 19.0%)
7. ✅ Compare with peer-company performance — revenue CAGR: peer median 7.0%; operating margin: peer median 16.0%
8. ⬜ Evaluate competitive and operational constraints — not performed: competitive/supply-chain modules not run
9. ⬜ Identify potentially overlooked information — not performed: no sourced research findings supplied
10. ⬜ Examine counterarguments — not performed: no sourced research findings supplied
11. ⬜ Identify potential catalysts — not performed: no sourced research findings supplied
12. ⬜ Explain why the market may already understand the discrepancy — not performed: no sourced research findings supplied
13. ✅ Assess model uncertainty and evidence quality — evidence quality medium; scenario spread 100%

## 23. Final analytical conclusion

**Potentially overvalued under specified assumptions.** Price 94.00 (as of 2026-10-27) sits between base and bull values (bear 39.75 / base 72.77 / bull 112.83); margin-of-safety band ±20%. Downside to bear case -57.7%.

Reasons: price 94.00 is more than 20% above base value 72.77; why the market might already understand the gap has not been researched; treat the verdict as provisional.

*A valuation discrepancy does not establish that the market is wrong; the market may hold information or risk views not captured here.* Business quality, intrinsic value and market expectations are separate conclusions; this verdict concerns valuation only.

## 24. Source bibliography

- `SYN-10K-FY2021` · Synthetic annual report FY2021 · DEEPTERMINAL fixtures · published 2022-02-20 · **SYNTHETIC**
- `SYN-10K-FY2022` · Synthetic annual report FY2022 · DEEPTERMINAL fixtures · published 2023-02-19 · **SYNTHETIC**
- `SYN-10K-FY2023` · Synthetic annual report FY2023 · DEEPTERMINAL fixtures · published 2024-02-18 · **SYNTHETIC**
- `SYN-10K-FY2024` · Synthetic annual report FY2024 · DEEPTERMINAL fixtures · published 2025-02-16 · **SYNTHETIC**
- `SYN-10K-FY2025` · Synthetic annual report FY2025 · DEEPTERMINAL fixtures · published 2026-02-15 · **SYNTHETIC**
- `SYN-10Q-Q3-2026` · Synthetic quarterly report Q3 2026 (balance sheet) · DEEPTERMINAL fixtures · published 2026-10-22 · **SYNTHETIC**
- `SYN-PRICE` · Synthetic closing price · DEEPTERMINAL fixtures · published 2026-10-27 · **SYNTHETIC**
- `SYN-RATES` · Synthetic risk-free rate and equity risk premium · DEEPTERMINAL fixtures · published 2026-10-01 · **SYNTHETIC**
- `SYN-TAM` · Synthetic industry market-size estimate · DEEPTERMINAL fixtures · published 2026-06-30 · **SYNTHETIC**
- `SYN-PEERS` · Synthetic peer financial summary · DEEPTERMINAL fixtures · published 2026-10-27 · **SYNTHETIC**
