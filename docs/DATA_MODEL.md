# Data model & evidence schema

The relational schema lives in [`schema/deepterminal.sql`](../schema/deepterminal.sql) and is
loaded and constraint-checked by `tests/test_schema.py`. This page explains the design.

## The evidence chain

```
source ──< evidence_sources >── evidence_item ──< claim_evidence >── claim
   │  published_at, retrieved_at,     │  value, unit, epistemic_status,      relation:
   │  period_end, accession,          │  quality, as_of, rationale,          supports |
   │  content_hash, licence,          │  supersedes_id                       contradicts |
   │  synthetic                       │                                       context
```

- **`sources`** is the origin. Three times are kept apart: when it was *published* (knowable),
  what *period* it describes, and when we *retrieved* it. `content_hash` plus `archive_uri` let
  any citation be re-verified against the exact bytes we read.
- **`evidence_items`** is a value with an epistemic status (one of eight, enforced by `CHECK`).
  Facts, statements and estimates need a source. Assumptions and inferences need a rationale.
  Corrections never update in place: a new row points to the old one through `supersedes_id`.
- **`claims`** are sentences that appear in reports or assessments. `claim_evidence` records
  support *and* contradiction, which is what the Thesis Challenger and §10 counterevidence rely on.

In code the same chain is `Source` → `SourcedValue` (`deepterminal/evidence.py`). It provides:

| Function | Purpose |
|---|---|
| `enforce_point_in_time(values, decision_date)` | Raises `LookAheadError` for evidence not yet public |
| `citation_audit(values, reference)` | Reports missing sources or rationales, corroboration with fewer than two sources, unverified claims, synthetic data and stale data |
| `assumption(name, value, rationale)` | Creates an assumption; a rationale is mandatory |

## Figure provenance (implemented)

Each reported figure used in an analysis carries a `FigureProvenance`
(`deepterminal/evidence.py`) with these fields:

| Field | Meaning |
|---|---|
| XBRL concept | e.g. `us-gaap:Revenues` |
| Period | Start and end dates |
| Filing | Form and accession number |
| Filing date | When the figure became public |
| Filing URL | EDGAR index page |
| Retrieval time | UTC; taken from the cache metadata |
| Derivation | For computed figures (`FY − 9M YTD`, `sum of four quarters`), every input is listed recursively |

Exported in report §22, the dashboard's *Data provenance & validation* panel and `provenance.csv`.
Maps to `financial_facts` plus `sources` in the schema.

## Point-in-time financials

`financial_facts` stores every XBRL fact *per filing*. The same period appears once for each
filing that reports it (original, comparative, restatement), each row with its `filed_at`. The
query for "what was knowable on D" is:

```sql
SELECT DISTINCT ON (concept, period_end) *
FROM financial_facts
WHERE company_id = :c AND filed_at <= :D
ORDER BY concept, period_end, filed_at DESC;   -- latest knowable revision
```

`sec_edgar.annual_series(..., as_of=D, revision="original"|"latest")` implements the same logic
on the raw companyfacts JSON, and `detect_revisions` lists restated periods.

## Valuation run tables

| Table | Holds | Integrity rule |
|---|---|---|
| `valuation_runs` | analysis date, price evidence, engine version, **case-file hash** | Reproducible: same hash + version ⇒ same output |
| `method_selections` | primary / cross-check / excluded / caveat + reason | Methods never applied without a recorded reason |
| `valuation_assumptions` | every scenario input with evidence or rationale | `rationale NOT NULL` |
| `bridge_items` | signed EV→equity adjustments | PK `(run_id, item)` ⇒ one entry per claim type (no double counting) |
| `scenario_results` | bear/base/bull EV, equity, per share, yearly table | `CHECK (probability IS NULL OR calibration_basis IS NOT NULL)` |
| `reverse_dcf_results` | lever, status (unique/multiple/none), solutions, **held-constant set**, bounds | |
| `misvaluation_assessments` | verdict, margin of safety, reasons, 13 steps | Verdict enum is the four qualified labels |
| `assessment_categories` / `assessment_evidence` | 13 categories with findings, trend, unknowns, risks, confidence; supporting **and** counter-evidence | status `assessed / partial / not_assessed` |

## Research-module tables

| Module | Tables | Notable design choices |
|---|---|---|
| Management | `people`, `management_claims`, `insider_transactions` | Promises are tracked with their outcome and the evidence for it |
| Filings diff | `filings`, `filing_changes` | Section-level added / removed / modified |
| Competition | `competitors`, `products`, `product_comparisons`, `market_share_observations` | Comparisons are per **criterion × customer segment** and require a methodology; there is no universal score column |
| Supply chain | `supply_chain_nodes`, `supply_chain_edges`, `supply_chain_events` | Revenue effect and margin effect are recorded separately, plus a dominant-effect analysis |
| Demand | `demand_indicators` | Platform, region, segment, sample size, verified-only flag and a mandatory coverage note |
| Sentiment | `sentiment_observations` | Channel, metric and method on each row |
| Analogues | `analogues` | `decision_date`, success/failure class, selection criteria, survivorship note |
| Catalysts | `catalysts` | Date confidence: confirmed, estimated or unknown |
| Agents | `agent_runs`, `audit_log` | Prompt hash, tools, and counts of claims produced and rejected |

## Case-file format (MVP input)

Until the database-backed pipeline lands, an analysis runs from a JSON case file. A complete
example is in [`fixtures/synthetic_widget_corp.json`](../fixtures/synthetic_widget_corp.json),
which is **synthetic**.

| Key | Contents |
|---|---|
| `meta` | case_id, company_name, ticker, currency, units, `analysis_date`, `synthetic`, disclaimer |
| `sources[]` | `Source` fields (`published_at` mandatory for temporal checks) |
| `market.share_price` | value, **as_of**, status, source_refs, quality |
| `capital_structure` | `CapitalStructure` fields + source_refs |
| `history[]` | `FinancialPeriod` fields + `filed` + `source_ref` |
| `profile` | `CompanyProfile` (drives method selection) |
| `assumptions` | Each with value, status, rationale and/or source_refs |
| `scenarios.{bear,base,bull}` | narrative, growth & margin paths, tax, discount rate, terminal growth & ROIC, `sales_to_capital` **or** `net_capex_pct_revenue` + `nwc_pct_revenue_change`, dependencies, source_refs, optional `probability` |
| `probability_calibration_basis` | Required if any probability is given |
| `tam_final_year` | Optional sourced addressable market (implied market share) |
| `peers[]` | name, ev_ebitda, revenue_growth, operating_margin, source_ref |
| `multiple_history` | Historical series per multiple name |
| `consensus` | Optional licensed estimates (`revenue_cagr`, `operating_margin`) |
| `evidence_quality` | high / medium / low |
| `research_findings[]` | step (overlooked / counterargument / catalyst / market_may_know), text, source_refs |
