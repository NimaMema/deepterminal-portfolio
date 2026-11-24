# Valuation methods: formulas, assumptions, limitations, verification

All functions are deterministic and live in `deepterminal/valuation` and `deepterminal/finance`.
Monetary inputs are in one currency and unit, so per-share values are equity divided by diluted
shares.

## 1. FCFF DCF — `dcf.run_dcf`

```
Revenue_t   = Revenue_{t-1} · (1 + g_t)
EBIT_t      = Revenue_t · m_t                 (margin after stock-based compensation)
NOPAT_t     = EBIT_t · (1 − τ_t)              (no tax shield on losses)
Reinvest_t  = ΔRevenue_t / (sales-to-capital) | net-capex% · Revenue_t + NWC% · ΔRevenue_t
FCFF_t      = NOPAT_t − Reinvest_t
TV_N        = NOPAT_{N+1} · (1 − g / ROIC_terminal) / (WACC − g)
EV          = Σ FCFF_t · DF(t) + TV_N · DF(N)      DF(t) = (1+WACC)^−t, or ^−(t−0.5) mid-year
```

| Aspect | Detail |
|---|---|
| Horizon | Explicit N years, set by the length of the growth path. Terminal value is a growing perpetuity |
| Key assumptions | Growth path, margin path, tax, reinvestment efficiency, WACC, terminal growth, terminal ROIC |
| Why value-driver TV | Growth is not free. Reinvestment g/ROIC is implied, so high g with low ROIC destroys value |
| Warnings emitted | g > 4%; TV > 75% of EV; terminal ROIC < WACC with g > 0; terminal NOPAT ≤ 0 |
| Limitations | Single currency; constant discount rate; no explicit debt schedule (APV not implemented); far-future cash flows dominate for young companies |
| Verification | Hand-computed two-year example; zero-growth perpetuity identity; mid-year ×(1+r)^½ identity; ROIC = WACC ⇒ TV = NOPAT_{N+1}/WACC |

## 2. Equity bridge & dilution — `bridge`

```
Equity = EV + (cash − operating cash) + non-operating assets − debt − leases* − pension deficit (after tax)
            − preferred − minority − convertibles (if debt) − expected contingent liabilities
Diluted shares = basic + RSUs + Σ options · max(0, 1 − K/P) + conversion shares (if equity)
```

\* Leases are subtracted only when EBIT is pre-lease-cost. Otherwise `DoubleCountError` is
raised. The same `CapitalStructure` produces the market EV for the reverse DCF, so intrinsic and
market-implied values are always comparable.

Verification: hand example, market round trip, convertible exclusivity, guards.

## 3. Reverse DCF — `reverse_dcf`

Solve `EV_model(x) = EV_market` for **one** lever x, holding the rest at the base case.

| Lever | Parameterisation |
|---|---|
| `growth` | Year-1 growth x fading linearly to terminal growth by year N |
| `constant_growth` | Growth x every year |
| `margin` | Margin moves linearly from year-1 level to x by year N; terminal margin x |
| `terminal_margin` | Terminal margin only |
| `sales_to_capital` | Reinvestment efficiency |
| `discount_rate` | Implied IRR on the forecast |
| `terminal_growth` | Perpetual growth |
| duration | Smallest N years of growth h justifying the price (integer search) |

The solver scans 120–240 grid points and bisects every sign change, returning `unique`,
`multiple` or `none_in_bounds` together with the monotonicity diagnostic and the full
held-constant set. The **iso-value surface** solves growth for a grid of margins, giving the
family of combinations consistent with the price.

Verification: round-trip recovery for four levers; every surface point reproduces market EV;
value-destroying growth lowers value; multiple roots are all found; duration minimality.

## 4. Multiples — `multiples`

| Multiple | Formula | Not meaningful when |
|---|---|---|
| P/E | Market cap / net income | Earnings ≤ 0 |
| Forward P/E | Price / forward EPS (licensed) | Forward EPS ≤ 0 |
| PEG | P/E / (EPS growth × 100) | P/E not meaningful or growth ≤ 0 |
| EV/EBITDA | EV / (EBIT + D&A) | EBITDA ≤ 0 |
| EV/Revenue | EV / revenue | — (blind to profitability; use only as a cross-check) |
| P/B | Market cap / book equity | Book ≤ 0 |
| FCF yield | (CFO − capex − SBC) / market cap | Market cap ≤ 0 (negative yields are reported) |

**Comparables.** The peer interquartile range (inclusive quartiles) is applied to the subject's
metric. Excluded peers are listed with their reason. The engine warns if fewer than three peers
remain or if Q3/Q1 > 2.

**Historical context.** Percentile, z-score and range of the current multiple versus its own
history. *Mean reversion is not assumed.*

## 5. Financial-institution models — `equity_models`
- Justified P/B = (ROE − g)/(r_e − g)
- Residual income: BV₀ + Σ (ROE_t − r_e)·BV_{t−1}/(1+r_e)^t + terminal RI/(r_e − g)
  discounted, with clean-surplus book growth.
- Gordon DDM.

Verification: the RI model equals the DDM under clean surplus (ROE 12%, payout 50%, r 10% ⇒ 1.5×
book), and justified P/B matches its closed form.

## 6. SOTP & asset-based — `sotp`
- SOTP: Σ segment EV − capitalised head-office cost (cost·(1−τ)/(r−g)). Each segment records its
  own method.
- Adjusted NAV: Σ book × recovery − liabilities. Each recovery rate needs a rationale.

## 7. Normalisation — `normalization`
- Through-cycle margin by median, mean or aggregate. The engine warns when the current margin is
  more than 30% above normal, or when fewer than 7 years are available.
- Non-recurring removal flags "non-recurring" charges seen in 3 or more years.
- Greenwald maintenance capex: growth capex = avg(PP&E/Revenue) × ΔRevenue⁺.
- FCF after SBC = CFO − capex − SBC. Outstanding grants sit in diluted shares; future grants are
  in the expense. Never both for the same grant.

## 8. Scenarios & sensitivity — `scenarios`
- Exactly bear, base and bull; the engine warns when values are not ordered.
- Probability weighting only with a calibration basis and probabilities summing to 1.
- Sensitivity grid of discount rate × terminal growth, with invalid cells (r ≤ g) left blank.
- Tornado of standard shocks: growth ±3 pp, margin ±3 pp, WACC ±1 pp, terminal g ±0.5 pp,
  terminal ROIC ±25%.

## 9. Cost of capital — `finance/wacc`
CAPM r_e = r_f + β·ERP + explicit premium; Hamada un/re-levering; WACC from market-value
weights. No hidden defaults: every input is passed explicitly and should be a sourced
`assumption`.

## 10. Misvaluation verdict — `expectations.assess_misvaluation`
The decision rule and 13 steps are described in the [specification §12](SPECIFICATION.md#12-misvaluation-investigation-engine--market-expectations-vs-fundamental-value).
Default margin of safety: ±20%. Default maximum scenario spread: 150% of base. Default maximum
price age: 7 days. All three are parameters, reported in the output.
