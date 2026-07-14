---
ticker: GOOG
style: GARP
framework_preference: lynch_garp_v1, joys_of_compounding, psychology_of_money
entry_date: 2026-04-20
last_reviewed: '2026-07-14'
current_allocation: 0.05%
cost_basis: 20327.72
time_horizon: 3 to 5 years
triggers:
  fwd_pe_add_below: 20              # add on AI/reg fear-driven pullbacks
  fwd_pe_trim_above: 32             # trim only if multiple gets to peak-AI-mania territory
  fwd_pe_historical_median:
  price_add_below: 320              # lean in on panic, not on routine pullback
  price_trim_above: 450.00          # raised from $395 — ecosystem + optionality thesis intact
  discount_from_52w_high_add:
  revenue_growth_floor_pct: 8
  operating_margin_floor_pct:
  style_size_ceiling_pct: 9.0
  current_weight_pct: 5.29
drawdown_tolerance_pct: 0.30
panic_buy_trigger_drawdown_pct: 0.20
---
# GOOG — Investment Thesis (Revised 2026-05-18)

## Core Thesis (Multi-Engine AI Compounder + Private-Stake Optionality)

I am holding a **cash-gushing technology monopoly** that is hitting on all cylinders heading into Google I/O 2026, with multiple independent profit engines (Search, Cloud, YouTube, Android/Chrome) **and** material strategic stakes in some of the most valuable private AI and frontier-tech assets in the world: SpaceX, Anthropic, and several private biotech bets through Verily and GV. The publicly-listed compounder gets me paid; the private stakes give me embedded optionality I can't replicate by buying anything else in the market.

The market is gradually waking up to what GOOG actually owns. Search is more resilient than the AI-disruption narrative claimed. GCP is now a real profit center. Gemini has caught and arguably passed peer frontier models in several benchmarks. Waymo is the only autonomous driving program with scaled, paying revenue. And the private-stake portfolio is mark-to-market only in funding rounds, so the public market under-prices it.

## Why I'm Raising the Trim Trigger to $450

The earlier $395 trim trigger was a hedge against "AI mania prices in everything." That was the right concern when GOOG was at $300 and the question was whether the AI premium was already baked in. With visibility into the Gemini roadmap, Waymo's expansion path, and the embedded private-stake optionality, I now believe the fair upside ceiling for this thesis cycle is closer to **$450**, not $395. Above $450 I would expect the multiple to be in peak-mania territory and would trim aggressively; below $450 the position can run.

I am explicitly choosing **conviction over the standard 5% single-name cap** for GOOG. The thesis justifies up to a 6% conviction-exception allocation, which is captured in `style_size_ceiling_pct: 9.0` in the YAML above (the ceiling stays at 9% as a hard cap; my working soft cap is 6%).

## The Private-Stake Story Most People Miss

GOOG's balance sheet contains material stakes in:

- **SpaceX** — through prior investment rounds; one of the most valuable private companies in the world.
- **Anthropic** — direct equity investment plus a Cloud partnership that makes GCP one of the primary deployment surfaces for Claude.
- **Verily, Wing, Calico, and other "Other Bets"** — biotech, drone delivery, longevity research, each with optionality that a passive market price doesn't capture.

None of these are priced in. They're worth something between "rounding error" and "tens of billions in mark-to-market" depending on the next funding round. The point isn't to model them; the point is they're free options I get by owning GOOG, and they trend in my favor as the AI/frontier-tech cycle continues.

## Entry Context & Position State

Cost basis: $17,938 on the remaining position; unrealized gain of approximately +80% as of 2026-05-18. The position has been trimmed once in the May rebalance. Forward sizing is governed by:

- Hold-and-add zone: below $320 if pullback is sentiment-driven, not structural.
- Hold zone: $320 to $450, with adds only on visible panic.
- Trim zone: above $450, expect to take risk off and let LT tax treatment work in my favor (LT conversion on April 2026 lots happens April 2027).
- Hard exit: structural moat impairment, not headline noise.

## Behavioral Guardrails

I will hold this through Google I/O 2026 and into 2027 specifically to convert the April 2026 lots to long-term tax treatment before any further trimming. This is a deliberate tax-aware hold. The 2026 YTD realized gains posture is already heavy ($31K net ST, $11K net LT) and I do not want to compound that with another ST realization on my largest unrealized gainer.

If the market goes risk-off and GOOG drops 20%+ on macro fear (not on Google-specific bad news), I will add — the size ceiling is 9% and the working soft cap is 6%, so there is room to scale up on panic.

## Hard Exit Conditions

I will exit or sharply reduce only on **structural** breaks:

1. DOJ remedies that permanently impair distribution economics (forced breakup of ad-tech, ban on default-search payments) — not fines or settlements.
2. Sustained, accelerating Search share loss to AI competitors with no credible response.
3. GCP growth deceleration AND margin compression sustained over 3+ quarters.
4. Gemini visibly falling behind peer frontier models for 2+ consecutive product cycles.
5. A clearly superior risk-adjusted opportunity that justifies the tax cost of exiting.

## Scaling State & Priority

- Next step: **hold through Google I/O 2026 and into April 2027 for LT conversion**, then re-evaluate.
- Add bias: on >20% drawdown driven by sentiment, not structural news.
- Trim bias: only above $450 or on hard-exit trigger.
- Rotation priority: very low.

<!-- region:position_state -->
**Current Allocation:** 0.05%
**Cost Basis:** $20,327.72
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** GARP
**Size Ceiling:** 9.00%
**Drift:** -8.95%
<!-- endregion:sizing -->

<!-- region:change_log -->
2026-07-14 10:51: Auto-sync allocation 0.05%, drift -8.95%
<!-- endregion:change_log -->

<!-- region:transaction_log -->
- 2026-06-15: Buy 0.0389 @ $368.85
- 2026-06-02: Buy 6.0 @ $358.19
- 2026-05-26: Buy 5.0 @ $382.40
- 2026-05-11: Sell -5.0 @ $392.79
- 2026-05-11: Sell -5.0 @ $392.79
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
Total Realized G/L: $13,846.64 over 10 closed lots. Total Proceeds: $27,202.04.
<!-- endregion:realized_gl -->
