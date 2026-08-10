---
ticker: META
style: GARP
framework_preference: lynch_garp_v1, joys_of_compounding, psychology_of_money
entry_date: 2026-04-20
last_reviewed: '2026-08-08'
current_allocation: 1.39%
cost_basis: 8852.820000000003
time_horizon: 3 to 5+ years
triggers:
  trigger_type: fwd_pe
  fwd_pe_add_below: 18              # add if ads/engagement solid but market panics
  fwd_pe_trim_above: 28             # trim if multiple rich AND RL spend re-accelerates
  fwd_pe_historical_median:
  price_add_below:                  # valuation + KPIs drive actions, not price levels alone
  # price_trim_above: 841.00  # superseded 2026-08-09, non-primary/stale -- see Review Log
  discount_from_52w_high_add:
  revenue_growth_floor_pct: 8       # want at least high single-digit top line
  operating_margin_floor_pct:       # focus on FCF margin and Reality Labs losses
  style_size_ceiling_pct: 4.0       # below MSFT given higher idiosyncratic risk
---
# META — Investment Thesis

## Core Thesis (AI‑Supercharged Ad Engine)

I am owning META as the most ruthlessly efficient digital advertising engine in the world, now **supercharged by AI** and cost discipline. Upside is driven by continuous improvement in AI‑driven ad targeting (e.g., Advantage+), growing engagement on Instagram Reels, and a structurally leaner cost base post “Year of Efficiency.”

Meta has largely neutralized the Apple iOS privacy hit and is using its open‑source Llama models to commoditize the foundation‑model layer while protecting and enhancing its core ad business. The key question is whether Mark Zuckerberg can keep Reality Labs’ cash burn under control and maintain shareholder‑friendly discipline; my judgment is cautiously yes.

## Entry Context

Cost basis: 379.72. I bought during the massive “Year of Efficiency” recovery — not at the panic lows, but at a still‑reasonable valuation relative to its free‑cash‑flow ramp and the launch of a dividend and larger buybacks.

- I am sitting on a gain that gives me psychological room to ride out normal mega‑cap tech volatility.  
- The purchase was price‑driven: META looked attractively valued versus its cash generation once the market believed Zuck’s efficiency pivot was real.

## Bull Case (Why Own META)

- Unrivaled distribution: Facebook, Instagram, and WhatsApp collectively command attention from billions of users; only Google rivals this reach for advertisers.  
- AI‑driven ads: Advantage+ and other AI tools help advertisers automatically create and target ads, improving ROAS and supporting higher ad pricing over time.  
- Llama strategy: Open‑sourcing Llama invites the developer community in, keeps big closed‑source competitors from monopolizing the model layer, and allows AI assistants to be natively embedded in Instagram and WhatsApp.  
- Capital returns: The combination of a growing dividend and large buybacks formalizes META’s shift into a mature cash‑return phase, putting a floor under the equity story.

## Key Risks

- Reality Labs cash burn: The Metaverse division continues to lose billions per year; if core ads falter, this becomes much harder for the market to tolerate.  
- Regulatory and political risk: Global regulators regularly target Meta for privacy, content, and market‑power issues; extreme outcomes could materially constrain targeted ads or even force divestitures.  
- Engagement fatigue and competition: If users tire of Reels/feeds or shift meaningfully to other platforms, engagement and ad inventory could structurally weaken.

## Position Sizing & Role

META is a core but not max‑size AI/attention compounder in the portfolio.

- Role: High‑cash‑flow consumer‑internet and AI‑ads pillar, complementary to MSFT’s enterprise/AI footprint.  
- Style ceiling: I will allow META to grow, but I cap it below MSFT due to higher regulatory and CEO‑concentration risk.

## Behavioral Guardrails

- I will tolerate normal tech drawdowns, sentiment swings, and headline noise as long as:  
  - Daily and monthly active users stay broadly stable or growing.  
  - Ad revenue and pricing per impression remain healthy.  
  - Reality Labs spend is bounded and clearly communicated.  
- I will not ignore a re‑acceleration in Metaverse spending or a breakdown in ad economics just because the stock is widely owned or “core FAANG.”

## Key KPIs to Monitor

- User and engagement metrics: DAUs/MAUs, time spent, Reels and Stories engagement trends.  
- Ad business health: Ad impression growth, pricing trends, ROAS feedback from advertisers.  
- Reality Labs: Operating loss size and trajectory; evidence of discipline vs. unconstrained experimentation.  
- Capital returns: Pace and consistency of buybacks and dividend growth relative to FCF.

## Hard Exit / Major Trim Conditions

I will trim or exit META if any of the following become clear, structural trends:

1. Ad revenue declines for several consecutive quarters due to new privacy rules or platform changes that Meta cannot route around.  
2. Zuckerberg abandons “Year of Efficiency” discipline and aggressively ramps Reality Labs spend without 

## Scaling State
next_step: **trim complete, hold remainder** — transcribed from Bill 2026-07-31, not
inferred. Partial trim executed on the Q2 conference call; staying in the position on
the strength of Zuckerberg's effectiveness as an operator. No further trim contemplated,
no add contemplated.

## Rotation Priority
priority: **low** — position has just been right-sized; the rotation is done, not
pending. [CONFIRM]

## Review Log

- **2026-07-31:** Partial trim. Bill's stated reason, verbatim in substance: **weak
  business case presented during the Q2 conference call**, while remaining in the
  position **for Zuckerberg's effectiveness**. Proceeds redeployed into two new
  positions the same day — ES (regulated utility, yield) and SNOW (AI data layer). See
  `ES_thesis.md` and `SNOW_thesis.md` for the buy-side of this rotation.

  Context recorded at the time: Q2 revenue $60.80B (+28% YoY) beat consensus, but
  diluted EPS of $6.18 missed the $7.22 estimate by ~14%, snapping a six-quarter beat
  streak, with expenses up 55% YoY. The trim was a judgment on the *spending case as
  presented on the call*, not on the ad business — ad impressions +14% and price per ad
  +12% YoY were both intact. This distinction matters for the exit conditions above:
  the Hard Exit criteria are written around ad economics breaking down, which is **not**
  what happened here. What triggered the trim was closer to criterion 2 — an
  unpersuasive case for a spending ramp — which the file leaves as an incomplete
  sentence.

  **Open item [BILL]:** the Hard Exit section ends mid-sentence at criterion 2
  ("...aggressively ramps Reality Labs spend without"). Worth finishing, since that
  criterion is the one this trim actually engaged.

  **System finding:** frontmatter sets `style_size_ceiling_pct: 4.0` (explicitly "below
  MSFT given higher idiosyncratic risk"), but the auto-synced sizing region below
  reports a 9.00% ceiling and a −6.79% drift, i.e. the GARP class default. The custom
  per-position ceiling is being ignored by whatever computes drift. Drift against the
  intended 4.0% ceiling is −1.79%, not −6.79%. Logged for the repo, not resolved here.
- 2026-08-09: trigger_type set explicit: fwd_pe (GARP default; existing 18/28 band retained as primary). Commented out price_trim_above: 841.00 -- non-primary once fwd_pe was confirmed primary, and left live it would have kept parsing as a dead trigger. See prompts/trigger_types_2026-08-09.md.

<!-- region:position_state -->
**Current Allocation:** 1.39%
**Cost Basis:** $8,852.82
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** GARP
**Size Ceiling:** 4.00%
**Drift:** -2.61%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-07-31: Sell -10.0 @ $549.82
- 2026-06-25: Buy 0.0231 @ $546.89
- 2026-06-25: Dividend 0.0 @ $0.00
- 2026-06-04: Buy 4.0 @ $639.18
- 2026-06-03: Buy 2.0 @ $616.12
- 2026-06-03: Buy 1.0 @ $616.12
- 2026-04-30: Buy 3.0 @ $605.12
- 2026-03-26: Buy 0.0134 @ $552.20
- 2026-03-26: Dividend 0.0 @ $0.00
- 2025-12-23: Buy 0.008 @ $663.91
- 2025-09-29: Buy 0.0078 @ $744.67
- 2025-06-26: Buy 0.0102 @ $721.34
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-08-08 09:05: Auto-sync allocation 1.39%, drift -2.61%
<!-- endregion:change_log -->
