# Presentation notes (GitHub & LinkedIn)

## One-line pitch
An evidence-first equity research engine that separates **how good a business is**, **what it is
worth**, and **what the stock price already assumes**, with transparent maths and verifiable
sources.

## LinkedIn post (draft)

> Most stock analysis blurs three different questions:
> 1️⃣ Is this a good business?
> 2️⃣ What is it worth?
> 3️⃣ What does today's price already assume?
>
> I'm building **DEEPTERMINAL** to keep them apart.
>
> The core is a reverse DCF that asks "what has to happen for this price to make sense?" It
> solves for implied growth, margins, reinvestment or return one lever at a time, and always
> shows the assumptions it held fixed. When no realistic answer exists, it says so instead of
> inventing one.
>
> Design rules I hold myself to:
> • every number is computed by tested, deterministic code, and AI is used only for research and
>   writing
> • every input carries its source, its type (fact vs estimate vs assumption) and the date it
>   became public, with a guard against look-ahead bias
> • no single "AI score", no buy/sell calls, no made-up scenario probabilities
> • if a module hasn't been built, the report says "Not assessed"
>
> v0.1 ships the valuation and market-expectations engine, an SEC EDGAR point-in-time parser, a
> 24-section research report and an interactive dashboard, verified by 59 tests against hand
> calculations and closed-form identities.
>
> Next: live EDGAR runs, competitor and demand intelligence, and a Claude-powered "Thesis
> Challenger" whose only job is to find evidence against my own conclusions.
>
> (Screenshot uses a fully synthetic company. Not investment advice.)

## Screenshot checklist
- Dashboard light and dark (`docs/images/`), with the synthetic banner visible
- Iso-value curve panel (most distinctive visual)
- Report §17 Reverse DCF excerpt

## Talking points for interviews
- Why the value-driver terminal value (reinvestment = g/ROIC) matters more than WACC tweaks.
- Why "the implied growth rate" is ill-posed: one equation, many unknowns, so the engine shows a
  family of solutions.
- Temporal discipline: publication date vs period end vs retrieval date, and point-in-time XBRL
  with restatement detection.
- The deterministic / LLM boundary and the citation verifier.
