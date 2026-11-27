# Data sources & licensing requirements

> **Not legal advice.** Terms change; verify each provider's current terms before integrating,
> and record the licence on every `sources` row (`licence` column). The rule for DEEPTERMINAL:
> **if access is not clearly permitted, don't collect it.**

## Tier 1 — Free, primary, MVP-critical

| Data | Source | Access | Licensing / constraints | Module |
|---|---|---|---|---|
| XBRL financial facts | SEC EDGAR `data.sec.gov/api/xbrl/companyfacts` | JSON API, no key | US government data. SEC fair-access policy: descriptive User-Agent with contact, ≤10 requests/s. **Implemented** (`DEEPTERMINAL_SEC_USER_AGENT`, 8 req/s throttle, cache). Sandboxed environments must allow `www.sec.gov` and `data.sec.gov` | Statements, valuation |
| Ticker ↔ CIK map, filings index | `www.sec.gov/files/company_tickers.json`, `data.sec.gov/submissions` | JSON, no key | As above. **Implemented** | Lookup, SIC, filings list |
| Filings (10-K/Q, 8-K, DEF 14A, S-1) | EDGAR full-text and archives | HTTPS | As above | Filings, management, forensic |
| Insider transactions | EDGAR Forms 3/4/5 | XML | As above | Management, sentiment |
| Institutional holdings | EDGAR 13F, 13D/G | XML | As above; 13F is quarterly with a 45-day lag, so it is stale by design | Institutional activity |
| Macro series | FRED (St. Louis Fed) | API key | FRED terms; some series are third-party copyrighted, so check each series' notes | Macro, discount rates |
| Treasury yields | US Treasury | CSV/XML | Public | Risk-free rate |
| Patents | USPTO (PatentsView / bulk data) | API / bulk | Public | Competitive, technology |
| Short interest | FINRA equity short interest | Files | Twice-monthly publication; check redistribution terms | Market mechanics |
| News metadata | GDELT | API / BigQuery | Open; tone scores are model outputs, so they are estimates | Narrative |

## Tier 2 — Licensed, required for full functionality

| Data | Typical providers | Why licensed | Notes |
|---|---|---|---|
| **Share prices (as-of timestamped)** | Exchange-licensed vendors (e.g. Nasdaq Data Link, Polygon, Intrinio, IEX-style feeds) | Exchange redistribution rules | Free web quote sites generally prohibit automated collection. The MVP takes a user-supplied price with source and as-of date |
| Consensus estimates, revisions | LSEG I/B/E/S, FactSet, S&P Capital IQ, Zacks | Proprietary | Needed for forward P/E and the analyst column of the expectations gap. Engine handles `consensus=None` |
| Options activity, implied volatility | OPRA-derived vendors | Exchange data | Aggregates only |
| Borrow cost / securities lending | Vendor data (e.g. S&P, Ortex) | Proprietary | |
| ETF holdings / fund flows | Issuers (holdings often free), flow vendors | Mixed | Use only where reliable |
| App downloads / active users | Sensor Tower, data.ai and similar | Proprietary | Estimates: epistemic status `estimate`, with methodology notes |
| Web traffic | Similarweb and similar | Proprietary | Panel-based estimates |
| Job postings | Revelio, LinkUp, Lightcast and similar | Proprietary | Do **not** scrape LinkedIn or job boards against their terms |
| Product reviews at scale | Licensed aggregators; first-party APIs where offered | Platform ToS | Amazon and many retailers prohibit scraping. Prefer verified-purchase data. Aggregate, never profile individuals |
| Trade / customs (supplier mapping) | ImportGenius, Panjiva and similar | Proprietary | |
| Commodity & freight indices | Exchanges, Drewry, Freightos and similar | Mixed | |
| Satellite / geolocation | Specialist vendors | Proprietary | Highest measurement-error risk; document it |
| Historical point-in-time fundamentals (for analogues) | Compustat PIT, Sharadar and similar | Proprietary | EDGAR covers roughly 2009+ XBRL; earlier analogues need licensed PIT data to avoid look-ahead |

## Tier 3 — Restricted / conditional

| Data | Constraint |
|---|---|
| Reddit | Data API terms; commercial use requires agreement. Aggregate counts and sentiment only |
| X/Twitter | Paid API tiers with restrictive terms |
| Google Trends | Values are relative indices (0–100) and resampled; official API access has been limited, and scraping may breach ToS. Treat as an `estimate` with heavy caveats |
| Court records | PACER (per-page fees); CourtListener / RECAP (free subset) |
| Earnings-call transcripts | Usually licensed; company IR pages sometimes host them |

## Optional hosted model providers
Anthropic and OpenAI are optional providers. Hosted providers require explicit opt-in and an API key.
Apply these requirements when enabling a hosted provider.
- API key held in a secret manager.
- Data sent to the API must be permitted by the source licences. Some vendor licences forbid
  sending their data to third-party processors, so check before routing licensed content through
  agents.
- Retention: log prompt hashes rather than full licensed content where the licence requires it.

## Methodological requirements by source type
- **Every alternative-data indicator** records platform, region, segment, sample size,
  verified-only flag and a coverage note (`demand_indicators.coverage_note NOT NULL`).
- Review volume, search interest and downloads are **never** used as a revenue proxy without a
  validated, documented relationship for that company.
- Vendor *estimates* get epistemic status `estimate`, never `historical_fact`.
- Synthetic fixtures are flagged `synthetic=true` and always surfaced by the citation audit.
