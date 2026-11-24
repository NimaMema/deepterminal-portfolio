# Specification reconciliation register

The original DEEPTERMINAL master specification has never been committed. The repository's only
pre-existing content was a one-line README, and `main` contains only the initial commit.
`docs/SPECIFICATION.md` is **preserved as-is**. Its Part I modules were reconstructed from the
module names given in the expansion prompt.

This register lists what must be checked against the original once it is available.

**Legend.**
- **R**: reconstructed; content inferred from a module name only.
- **A**: assumption made where the expansion prompt was silent.
- **C**: possible conflict between the expansion and typical original-spec content.

| ID | Spec location | Type | What was assumed | Needs from the original |
|---|---|---|---|---|
| SR-01 | Part I §A Corporate legitimacy | R | Checks: SEC/CIK, LEI, incorporation, auditor/PCAOB, listing, sanctions, shell/going-concern indicators | Exact checks, data sources, pass/fail criteria |
| SR-02 | Part I §B Management investigation | R | Biographies, litigation, related parties, DEF 14A compensation, Form 4, promise-vs-outcome tracking | Scope (e.g. personal social media? background checks?) and privacy limits |
| SR-03 | Part I §C SEC filings | R | Form list (10-K/Q, 8-K, DEF 14A, S-1, 3/4/5, 13D/G, 13F, comment letters) and section diffs | Required forms, history depth, diff granularity |
| SR-04 | Part I §D Forensic accounting | R | Accruals, receivables and inventory vs revenue, Beneish/Altman as screens only | Specific models or thresholds the original mandated |
| SR-05 | Part I §E Supply-chain research | R | Suppliers and customers from filings plus licensed trade data | Required sources; whether paid trade data was in scope |
| SR-06 | Part I §F Customer intelligence | R | Reviews, complaints, retention, concentration | Platforms named; scraping policy |
| SR-07 | Part I §G AI agents | R/A | Claude agents with a deterministic core; roster in AGENTS.md | Original agent list, autonomy level, human-in-the-loop rules |
| SR-08 | Part I §H Source verification | R | Archived source plus hash, quote-at-locator verification, rejection on failure | Original verification standard (e.g. two-source rule scope) |
| SR-09 | Part I §I Security | R | Secrets handling, untrusted-content isolation, least-privilege DB, audit log | Threat model, auth and multi-user requirements, compliance targets |
| SR-10 | Part I §J GitHub documentation | R | README, docs set, CI, labelled fixtures | Required docs (e.g. ADRs, CONTRIBUTING, licence choice: **no licence file has been added**) |
| SR-11 | Part I §K LinkedIn presentation | R | Post draft, screenshots, talking points | Tone, audience, deliverable format |
| SR-12 | Phased roadmap | R/C | Phases 0–4 with expansion milestones merged in | Original phase names, ordering and dates; whether real-data integration was originally earlier |
| SR-13 | Technology stack | A | Python stdlib core; Postgres target; FastAPI and React planned | Any mandated stack (language, DB, front-end, hosting) |
| SR-14 | Market data | A | User-supplied price; licensed feed later | Whether a specific (paid) provider was chosen; budget |
| SR-15 | Valuation defaults | A | Mechanical defaults for real companies (see PHASE1_VERIFICATION.md §3); no default discount rate | Whether the original specified a WACC methodology or data source |
| SR-16 | Verdict thresholds | A | Margin of safety ±20%, max scenario spread 150%, max price age 7 days | Any thresholds in the original |
| SR-17 | Report format | C | The 24-section format (expansion §13) replaces any earlier report structure | Original sections not in the 24 must be mapped, not dropped |
| SR-18 | Scoring | C | Expansion forbids a single AI score | If the original had a composite score, decide whether it becomes one of the 13 assessment categories |
| SR-19 | Jurisdiction | A | US SEC registrants only (US-GAAP, USD) | Whether non-US companies (IFRS, 20-F) were in scope |
| SR-20 | Users & deployment | A | Single-user CLI with static HTML outputs | Multi-user, hosted app, authentication requirements |

**Process.** When the original specification is found, add it as
`docs/ORIGINAL_SPECIFICATION.md` unchanged. Then resolve each row above: confirm it, amend
SPECIFICATION.md, or record the decision. The expansion's requirements stay authoritative where
they *add* requirements; nothing from the original is dropped.
