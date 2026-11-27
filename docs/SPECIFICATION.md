# DEEPTERMINAL — Master Specification (v2)

This document describes the research and valuation design. See [project status](STATUS.md)
for current feature coverage and verification.

Companion documents:
[Architecture](ARCHITECTURE.md) · [Data model & evidence schema](DATA_MODEL.md) ·
[Research agents](AGENTS.md) · [Valuation methods](VALUATION_METHODS.md) ·
[Roadmap & acceptance criteria](ROADMAP.md) · [Data sources & licensing](DATA_SOURCES.md)

---

## 0. Mission and the central question

DEEPTERMINAL is a working financial research application, not a generator of opinions. It must
answer:

> **What is the company's realistic future economic value, what is the market currently paying
> for it, and what important information might the market be overlooking?**

Every major analysis keeps three conclusions separate:

| | Question | Primary evidence | Engine |
|---|---|---|---|
| **A. Company quality** | Is this fundamentally a strong business? | Competitive advantage, financial durability, product quality, customer satisfaction, management, capital allocation, industry position, supply-chain resilience, sustainable profitability, growth runway | Research modules §A–§H, assessment §10 |
| **B. Stock valuation** | Is the price attractive relative to a *defensible range* of intrinsic values? | Market cap, EV, intrinsic value range, multiples, financial risks, dilution, margin of safety, downside | Valuation engine §2, scenarios §11 |
| **C. Market expectations** | What operating performance must occur to justify the price? | Implied growth, margins, FCF, market share, competitive position, reinvestment, terminal assumptions; gap versus analyst forecasts | Reverse DCF §3, expectations gap §12 |

**Invariants.**
- A wonderful business is not automatically an attractive investment.
- A weak business is not necessarily overvalued.
- The system must be able to reach findings that **disagree with the user's initial hypothesis**.
  Its purpose is to investigate and explain the evidence, not to confirm beliefs.

---

## Part I — Original modules (preserved)

### A. Corporate legitimacy
Verify that the entity is real, registered and operating as it claims. Checks cover SEC
registration and CIK, legal entity identifiers (LEI), state or country incorporation records,
auditor identity and PCAOB inspection status, exchange listing status, physical-presence
evidence, domain and website history, and sanctions and enforcement lists (OFAC, SEC litigation
releases). Shell-company, reverse-merger and going-concern indicators are also checked.
Output: `companies.legitimacy_status` with linked evidence.

### B. Management investigation
Cover executive and director histories, prior companies and their outcomes, litigation and
regulatory actions, related-party relationships, compensation structure and incentives (DEF 14A),
insider transactions (Form 4, including 10b5-1 plans), turnover and succession. A track record of
promises versus outcomes is kept in `management_claims`. *Extended in §9: capital allocation,
acquisition record, historical execution.*

### C. SEC filings intelligence
Ingest 10-K, 10-Q, 8-K, DEF 14A, S-1, Forms 3/4/5, 13D/G, 13F and comment letters. XBRL facts are
stored point-in-time with filing date and accession number (`financial_facts`), and restatements
are kept as superseding rows. Section-level diffs between successive filings (`filing_changes`)
cover risk factors, MD&A, accounting policies, segment definitions and legal proceedings.
**Implemented:** an EDGAR connector (fair-access User-Agent, throttling, retries, verified
cache), ticker/CIK lookup, and 10-K and 10-Q parsing (discrete quarters, YTD-derived quarters,
TTM). Every figure has point-in-time filtering, revision detection and per-figure provenance
(`deepterminal/data/`). See [PHASE1_VERIFICATION.md](PHASE1_VERIFICATION.md).

### D. Forensic accounting
Covers accruals quality, receivables and inventory growth versus revenue, cash conversion,
capitalisation policies, reserve releases, non-GAAP reconciliation, auditor changes and opinions,
related-party transactions, Beneish and Altman-style screens (used as screens, never as verdicts),
and segment re-casting. *Extended in §9: revenue recognition and unusual accounting assumptions.*
**Implemented (MVP subset):** receivables, inventory, accruals, profit-without-cash, SBC,
dilution and coverage flags (`deepterminal/financials/statements.py`).

### E. Supply-chain research
Identifies suppliers, customers, manufacturing locations and logistics routes from filings,
customs and trade data where licensed, and supplier disclosures. *Extended in §5 to supply-chain
economics.*

### F. Customer intelligence
Covers reviews, complaints, retention signals and customer concentration disclosures. *Extended
in §6 to Customer & Demand Intelligence.*

### G. AI research agents
A research system with optional language models with planning, tool use and synthesis. See
[AGENTS.md](AGENTS.md). Extended with the Valuation Analyst, Expectations Analyst, Competitive
Intelligence, Demand, Supply-Chain Economics, Narrative, Analogue and **Thesis Challenger**
agents.

### H. Source verification
Every claim links to evidence and every piece of evidence links to an archived source with a
content hash. Citations are verified mechanically: the quoted text must exist at the locator, and
the number must match the source. Claims that fail are rejected rather than softened. Each claim
carries an epistemic status (§15). **Implemented (MVP):** `deepterminal/evidence.py`, which
provides the epistemic statuses, look-ahead guard, staleness checks and citation audit.

### I. Security
- Secrets come only from the environment or a secret manager; nothing is committed.
- Documents fetched by agents are treated as **untrusted input**: prompt-injection defences,
  tool allow-lists and no execution of fetched content.
- Rate-limited, polite crawling within each source's terms (see DATA_SOURCES.md).
- The database role has least privilege. Audit logs are append-only (`audit_log`).
- Dependencies are pinned and scanned. The calculation core has zero third-party dependencies.
- Personal data is minimised: reviewers and social users are never profiled individually, and
  aggregation happens before storage.

---

## Part II — Expansion requirements

### 1. Central investment question
See §0. Every comprehensive report answers A, B and C separately (§13).

### 2. Advanced valuation engine
The engine must be comprehensive, transparent and mathematically tested.

| # | Method | Status | Module |
|---|---|---|---|
| 1 | Discounted cash flow (FCFF) | ✅ MVP | `valuation/dcf.py` |
| 2 | Reverse DCF | ✅ MVP | `valuation/reverse_dcf.py` |
| 3 | Price-to-earnings | ✅ | `valuation/multiples.py` |
| 4 | Forward P/E | ✅ function; needs licensed estimates | `multiples.forward_pe` |
| 5 | PEG | ✅ | `multiples.peg` |
| 6 | EV/EBITDA | ✅ | `multiples.ev_to_ebitda` |
| 7 | EV/Revenue | ✅ | `multiples.ev_to_revenue` |
| 8 | Price-to-book (incl. justified P/B) | ✅ | `multiples`, `equity_models` |
| 9 | Free-cash-flow yield (after SBC) | ✅ | `multiples.fcf_yield` |
| 10 | Sum-of-the-parts | ✅ | `valuation/sotp.py` |
| 11 | Asset-based (adjusted NAV) | ✅ | `valuation/sotp.py` |
| 12 | Historical multiple analysis | ✅ | `multiples.historical_multiple_context` |
| 13 | Comparable-company valuation | ✅ | `multiples.comparable_valuation` |
| 14 | Scenario analysis | ✅ MVP | `valuation/scenarios.py` |
| + | Residual income / DDM (financials) | ✅ | `valuation/equity_models.py` |

**Method selection** is done by `valuation/selection.py`, never indiscriminately. Each method is
recorded as primary, cross-check, excluded or caveat, with a reason:

- mature cash generator → DCF primary;
- bank or insurer → residual income and P/B; EV methods excluded;
- cyclical business → normalised DCF from through-cycle margins;
- unprofitable high-growth company → DCF with an explicit path to profitability and wide
  scenarios; earnings multiples excluded;
- conglomerate → SOTP cross-check.

**Transparency per method.** Each method exposes its input data, source references, formula,
forecast horizon, assumptions, sensitivity, output, limitations and data quality
(VALUATION_METHODS.md, report §16–§18).

**Required financial adjustments**, and where each is handled:

| Adjustment | Handling |
|---|---|
| Share dilution, options, RSUs | Treasury stock method at as-of price (`bridge.CapitalStructure.diluted_shares`) |
| Stock-based compensation | Treated as an expense in margins and FCF; outstanding grants in shares; future grants **not** double-counted |
| Net debt, excess cash | `total_debt`, `cash − operating_cash_requirement` |
| Preferred, minority interests | Bridge claims |
| Convertibles | Debt **or** if-converted shares, enforced exclusive |
| Leases | Subtracted only if EBIT is pre-lease-cost; guarded (`DoubleCountError`) |
| Pensions | After-tax deficit as a claim |
| Contingent liabilities | Expected value as a claim, sourced |
| Cyclically inflated profits | `normalised_margin` with warning |
| Non-recurring items | `remove_nonrecurring`, flags "recurring non-recurring" charges |
| Maintenance vs growth capex | Greenwald split |
| Sustainable margins, reinvestment, working capital | DCF margin path, sales-to-capital or explicit capex + NWC |
| Currency exposure | Single-currency model; FX scenarios via assumptions (roadmap: segment currency mix) |
| Discount rate | CAPM/WACC with explicit inputs (`finance/wacc.py`) |
| Terminal growth | Value-driver terminal value: reinvestment = g / ROIC |
| Margin of safety | Explicit parameter in the verdict rule |

Formulas are tested against independently calculated examples (`tests/`).

### 3. Reverse DCF — market expectations engine
The engine solves for the operating assumptions implied by the current price, one lever at a
time, and reports what was held constant. It never claims a unique implied growth rate when
several assumptions are unknown. The **iso-value surface** shows the whole family of margin and
growth pairs consistent with the price.

Solvable levers: revenue growth (fading or constant), steady-state or terminal operating margin,
sales-to-capital (reinvestment), discount rate (implied IRR), terminal growth, and growth duration
(integer search). Derived outputs per solution are implied FCF path, final revenue, revenue CAGR,
cumulative reinvestment and implied share of a sourced addressable market. Root-finding scans the
interval and reports *zero, one or several* solutions.

**Market Expectations dashboard** — the eight required panels are implemented in
`reporting/dashboard.py`:
1. current market value
2. base-case intrinsic value range
3. market-implied operating assumptions
4. historical operating performance
5. industry comparisons
6. sensitivity analysis
7. critical assumptions
8. downside if expectations are missed

Every price and forecast shows its as-of date.

### 4. Product & competitor intelligence
For each material competitor (materiality rationale stored), the engine investigates product
quality and specifications, reliability, price-to-performance, switching costs, market share and
its history, launch timing, R&D, patents and IP, differentiation, distribution, manufacturing
cost, customer acquisition and retention, brand, pricing power, geographic expansion,
technological disruption, financial health, substitutes and new entrants.

**Product superiority** is evaluated *per criterion and per customer segment*: technical
benchmarks, reliability, satisfaction, ownership cost, capabilities, price, availability and
support. There is **never one universal score** (`product_comparisons` has no score column by
design). Comparison criteria and methodology are mandatory fields.

Dashboard: **Competitive Battlefield** (side-by-side comparison).

### 5. Supply-chain economics & operational risk
The model maps raw materials → components → manufacturing → logistics and distribution → end
customers (`supply_chain_nodes/edges`). It overlays energy, labour, regulation, geopolitics,
capital, infrastructure and natural hazards.

Investigations cover supplier concentration, single sources, utilisation, capacity, backlog,
cancellations, inventory turnover and obsolescence, lead times, supplier health, commodity and
energy prices, labour shortages and strikes, freight and route disruptions, tariffs, export
controls, sanctions, climate exposure, defect rates and recalls, supplier bargaining power,
yields, capacity expansion, alternative suppliers and customer concentration.

**Critical distinction.** A shortage can cut volumes yet raise profitability through pricing
power. Each `supply_chain_events` row records revenue and margin effects separately, plus a
*dominant-effect analysis*. No shortage is assumed negative. Effects are traced to revenue, gross
margin, working capital, inventory, capex, pricing power, delivery, satisfaction and competitive
position, and quantified with scenarios where the evidence allows.

Dashboard: **Supply-Chain Economics**.

### 6. Customer satisfaction & real demand
Indicators include ratings over time, verified-purchase reviews, review volume, return, refund and
warranty rates, repeat purchase, retention, NPS, downloads, active users, complaints, support
issues, delivery delays, price sensitivity, LTV and CAC (`demand_indicators`, each with platform,
region, segment, sample size and coverage note).

Historical comparisons:
- current vs prior periods
- company vs competitors
- launch period vs later periods
- sentiment vs reported sales
- acquisition vs retention
- revenue growth vs verifiable usage

**Demand quality** examines price versus volume, organic versus acquired growth, backlog
conversion, channel inventory, concentration, one-time orders, promotions, recurring revenue,
pull-forward, replacement cycles, churn, deferred revenue and receivables growth.

Review volume, search interest and downloads are **never equated with revenue**, and data is
adjusted for platform, region, segment and sample size.

Dashboard: **Demand Reality Monitor**.

### 7. Historical cycles & analogue engine
The engine compares the company with historical businesses and environments: fast-growing tech,
bubbles, post-bubble recoveries, margin peaks, new competition, supply-constrained industries,
disruptive adoption, extreme multiples, companies that grew into their valuations, and companies
that failed despite rapid growth.

Each comparison covers growth trajectory, margins, multiples, profitability, capital intensity,
industry structure, rates, competition, concentration, reinvestment and macro conditions.

**Anti-cherry-picking rules** apply:
- successful and unsuccessful analogues are required (`outcome_class`);
- selection criteria are documented;
- analogues are compared on information available at their decision date (`decision_date`);
- survivorship is noted;
- resemblance does not prove outcome.

Dashboard: **Historical Analogue Explorer**.

### 8. Hype, sentiment & investor expectations
The engine tracks news volume and sentiment, search interest, Reddit and other *permitted* social
sources, retail attention, engagement, analyst revisions, estimate changes, options activity,
short interest, borrow cost, institutional ownership, insider transactions, ETF exposure, fund
flows (where reliable), multiple expansion, earnings and revenue growth, promotional claims and
commercial results.

**Reality vs narrative** compares:
- announced opportunities vs realised revenue
- guidance vs outcomes
- claims vs independent benchmarks
- enthusiasm vs retention
- growth vs cash
- valuation growth vs operating growth

Each change is distinguished between fundamentals, expectations, market structure, and capital
changes or dividends. A price decomposition is **not** an exact accounting identity.

Manipulation risk is analysed only from documented evidence, and **never asserted from unusual
trading or social activity alone**.

Dashboard: **Narrative vs Fundamentals**.

### 9. Additional research dimensions
- **Management quality**: capital allocation, acquisitions, compensation incentives, insider
  transactions, succession, historical execution.
- **Accounting quality**: revenue recognition, receivables, reserves, auditor changes,
  related-party transactions, unusual assumptions.
- **Industry structure**: concentration, entry barriers, supplier and customer power, rivalry,
  cyclicality.
- **Macroeconomics**: rates, inflation, employment, currency, credit, consumer spending, growth.
- **Government policy**: subsidies, tariffs, tax, antitrust, permits, procurement, export
  restrictions, environmental regulation.
- **Technology**: innovation rate, obsolescence, patent expiry, cybersecurity, open-source
  competition, substitution.
- **Market mechanics**: liquidity, index inclusion, short interest, issuance, convertibles,
  options positioning.
- **Catalysts**: earnings, launches, regulatory decisions, clinical results, contracts,
  refinancing, industry developments (`catalysts`).
- **Hidden liabilities**: litigation, pensions, leases, remediation, warranties, contingencies
  (all flow to the bridge when quantified).
- **Alternative evidence**, where lawful and methodologically reliable: job postings, hiring,
  web and app activity, availability, store traffic, shipping, satellite. Coverage and
  measurement limitations are documented.

### 10. Multidimensional assessment
There is **no single AI-generated investment score**. Thirteen categories are assessed
separately:
1. financial strength
2. business quality
3. product strength
4. competitive positioning
5. supply-chain resilience
6. management & governance
7. growth sustainability
8. intrinsic valuation
9. market-implied expectations
10. market sentiment
11. permanent capital-loss risks
12. future catalysts
13. evidence confidence

Each category holds key findings, supporting evidence, **counterevidence**, historical trend,
unknowns, risks and confidence limitations, plus a status of *assessed*, *partial* or *not
assessed* (`assessment_categories`, `assessment_evidence`). Users can drill into the original
evidence.

### 11. Bear, base & bull valuation
There are three DCF scenarios, each with:
- narrative and dependencies
- revenue, margins, FCF and reinvestment
- discount and terminal assumptions
- equity and per-share value
- sources

Ranges and sensitivities (rate × terminal growth grid, tornado) are shown.

**Probabilities are optional.** They are accepted only with a stated calibration basis and must
sum to 1. Otherwise **no weighted average is produced** (enforced in code and in the schema).

### 12. Misvaluation investigation engine — "Market Expectations vs. Fundamental Value"
The 13-step process is implemented in `valuation/expectations.py`. Steps that need research
evidence (9 overlooked information, 10 counterarguments, 11 catalysts, 12 why the market may
already know) are marked **not performed** unless sourced findings are supplied.

Possible verdicts:
- *Potentially undervalued under specified assumptions*
- *Approximately fairly valued under specified assumptions*
- *Potentially overvalued under specified assumptions*
- *Too uncertain to assess reliably*

The verdict rule is explicit:
- **Too uncertain** if evidence quality is low, the price is stale or undated, the scenario
  spread is above 150% of base, or the base value is not positive.
- **Undervalued** if the price is below base × (1 − margin of safety).
- **Overvalued** if the price is above base × (1 + margin of safety).
- **Approximately fair** otherwise.

Labels are always accompanied by assumptions, calculations and the caveat that a discrepancy
does not prove the market wrong.

### 13. Investment research report format
The report has 24 sections in the specified order (`reporting/report.py`). The executive summary
answers five questions separately:
1. Is this a good business?
2. What is a defensible value range?
3. What does the price embed?
4. What might the market be overlooking?
5. What evidence could invalidate the thesis?

It contains **no buy/sell recommendation**. Sections whose module is not implemented say *Not
assessed* explicitly.

### 14. Application views

| View | Status |
|---|---|
| Valuation Laboratory (interactive DCF, multiples, peers, scenarios) | Partial: CLI + report; interactive web UI in roadmap |
| Reverse DCF Dashboard | ✅ static HTML with tooltips (panels 1–3, 6–8) |
| Expectations Gap | ✅ panels 4–5 + report §17 |
| Competitive Battlefield | Roadmap — Intermediate |
| Demand Reality Monitor | Roadmap — Intermediate |
| Supply-Chain Economics | Roadmap — Intermediate/Advanced |
| Historical Analogue Explorer | Roadmap — Advanced |
| Narrative vs Fundamentals | Roadmap — Advanced |
| Thesis Challenger | Roadmap — Advanced (agent design in AGENTS.md) |

### 15. AI research-quality requirements
- **Epistemic statuses**: historical fact, company statement, corroborated fact (≥2 independent
  sources), estimate, model assumption, analytical inference, speculative scenario, unverified
  claim (`EpistemicStatus`).
- **Temporal discipline**: when information became public (`published_at`) is kept separate from
  the period it covers and the retrieval time. A look-ahead guard rejects later evidence
  (`enforce_point_in_time`). Staleness is checked, filing and restatement history is preserved,
  and as-of dates appear on every price.
- **Division of labour**: deterministic functions do all calculations. Language models can
  help plan research, interpret documents, synthesise evidence, find contradictions, explain scenarios,
  and draft reports. Missing financial data is reported as a limitation.

### 16. Implementation priorities
These are in [ROADMAP.md](ROADMAP.md): Early MVP (done in v0.1), then Intermediate, then
Advanced. A functional MVP is never delayed for advanced features. Each feature is tested with
real source data or clearly labelled fixtures.

### 17. Success criteria
A user enters a ticker and can investigate:
- what the company does, whether it is legitimate and well governed
- product competitiveness and customer satisfaction
- demand sustainability and supply-chain threats
- accounting warning signs and management's delivery record
- competitor momentum
- whether the price embeds demanding expectations
- relevant historical parallels
- potentially overlooked information

The system can reach conclusions that contradict the starting hypothesis, and it explains its
evidence transparently.
