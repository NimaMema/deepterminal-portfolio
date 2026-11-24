# DEEPTERMINAL LinkedIn and portfolio kit

Updated 2026-11-24 against v0.3.0. This is a draft for the owner to review and post.

## Ready-to-paste LinkedIn post

I’ve been working on DEEPTERMINAL, a financial research platform built with Python, TypeScript, Next.js, FastAPI and PostgreSQL.

It brings company filings, financial statements and valuation tools into one place. You can explore a company’s financials, change valuation assumptions, see what growth a share price implies, and trace figures back to their sources.

A big part of the work was handling real SEC data: stock splits, restatements and financial tags that change between filings. The project also includes company comparisons, supply-chain research and PDF reports.

The first private release is finished, with automated tests covering the calculation engine, API and browser workflows. I’m continuing to improve the data coverage and research tools.

I’d appreciate feedback from anyone working in software development or fintech.

#SoftwareEngineering #FinTech #Python

## If the repository becomes public

Replace “The first private release is finished” with “v0.3.0 is released”
Add this line before the feedback request:

GitHub: https://github.com/NimaMema/deepterminal-portfolio

Do not advertise the repository as publicly accessible while it is private. No hosted demo is
currently available. Posting screenshots does not make the code publicly accessible.

## Screenshots to attach

Use actual app screenshots, in this order. These are existing captures, not newly generated UI.

| Order | File | Caption |
|---|---|---|
| 1 | [NVIDIA overview](screenshots/live-01-nvda-overview.png) | DEEPTERMINAL company overview using recorded NVIDIA SEC data |
| 2 | [Valuation lab](screenshots/live-07-nvda-valuation.png) | DCF scenarios and sensitivity under explicit assumptions |
| 3 | [Reverse DCF](screenshots/live-08-nvda-reverse-dcf.png) | What an observed price implies when other assumptions are held constant |
| 4 | [Evidence drawer](screenshots/16-evidence-drawer.png) | Inspecting the source passage behind a finding; synthetic demo shown |

Real-company captures use October 2026 data. Prices shown are historical observations, including
SEC Form 4 transactions rather than official closing prices. Valuation inputs are illustrative.
The evidence-drawer capture uses fictional demo data. Keep these labels if cropping images.
Avoid presenting recorded examples as current analysis or as the result of a new model evaluation.

## LinkedIn Featured entry

**Title:** DEEPTERMINAL | Equity Research & Valuation Platform

**Description:** A full-stack research terminal combining SEC filings, source-linked financial
analysis, DCF/reverse DCF, company research and PDF reports. Built with Next.js, TypeScript,
FastAPI, PostgreSQL and Python, with automated test coverage.

Use the repository URL only after public access is enabled. Until then, use the screenshots or
a screen recording rather than a link other people cannot open.

## Short demo recording (60–90 seconds)

| Time | Show | Explain |
|---|---|---|
| 0–15s | Company overview | The three questions: quality, value and market expectations. State whether using recorded real data or the synthetic demo. |
| 15–30s | Statement cell and evidence drawer | Trace a figure back to its source and retrieval date. |
| 30–50s | Valuation lab and reverse DCF | Show editable assumptions, scenarios and implied expectations. |
| 50–65s | Thesis challenger | Show counter-evidence and missing-data labels. |
| 65–90s | Report and PDF | Show the export, stack and current limitations. |

Use preloaded results for a recorded snapshot. Do not imply a fresh live investigation if one
was not run. Keep personal browser tabs, contact email and credentials out of the recording.

## Verified technical talking points

- Deterministic Python financial calculations; local AI assists research and prose.
- SEC XBRL/filing pipeline with point-in-time handling, revisions and figure provenance.
- Next.js/TypeScript frontend; FastAPI/PostgreSQL backend, migrations and background jobs.
- v0.3.0 release CI: 107 core tests, 94 API tests, 9 frontend tests, 14 browser E2E tests,
  37 demo smoke checks, typecheck/lint/build, and a PDF check inside the non-root API container.
- Paid APIs disabled by default; no paid API required for the documented local setup.
- Single-user release. Local-model interpretations need source review; broader datasets and
  measured model quality remain ongoing work.

Do not claim a live public deployment, real-time market data, guaranteed AI correctness,
validated investment returns, a published paper, or an open-source licence that has not been
selected. Repository visibility and public posting remain separate owner decisions.
