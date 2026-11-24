---
title: DEEPTERMINAL
emoji: 📈
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: other
short_description: Evidence-first equity research on real SEC EDGAR data
---

# DEEPTERMINAL: public demo

An evidence-first equity research terminal. Every figure carries its SEC source, and anything that
cannot be verified is reported as unavailable, never invented.

## What this demo serves

- **Data.** A read-only snapshot of real SEC EDGAR data for NVIDIA, Apple, Microsoft, AMD and Intel.
  It covers submissions, XBRL company facts and filing documents (US government public data).
- **Live calculations.** Valuation, reverse DCF, research chat (extractive) and the rule-based
  Thesis Challenger run live on this server.
- **Recorded AI examples.** These were generated locally with the open-weight
  `qwen2.5:7b-instruct` model (Apache-2.0) through Ollama, on a CPU with no paid API. Each is
  labelled with its model, hardware, generation time and date.

## Safeguards

- **No outbound network access.** Nothing leaves the container, so it makes no paid API calls.
- **Limited writes.** Only stateless calculations, chat and Thesis Challenger runs are accepted,
  each rate-limited per visitor. Visitors' own runs are not shown to other visitors.

## Valuation assumptions

- **Discount rate.** The 9% discount rate in the recorded investigations is illustrative.
- **Prices.** Prices are SEC Form 4 insider trade prices: real, dated transactions, not official
  closing prices.

Nothing here is investment advice.

## Running it yourself

The full application, including live SEC retrieval for any registrant and local AI generation,
runs free on your own machine. See the project repository.
