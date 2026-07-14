---
ticker: GLD
style: ETF
framework_preference: macro_hedge_v1
entry_date: 2026-05-03
last_reviewed: '2026-07-14'
current_allocation: 0.01%
cost_basis: 6910.6
time_horizon: 3 to 5 years
triggers:
  fwd_pe_add_below:                 # gold has no earnings; PE triggers not applicable
  fwd_pe_trim_above:
  fwd_pe_historical_median:
  price_add_below: 220              # add on meaningful pullback if macro hedge thesis intact
  price_trim_above: 400             # evaluate trimming if gold is running on pure momentum/panic
  discount_from_52w_high_add: 0.15  # add on 15% pullback; gold drawdowns tend to be buy opportunities
  revenue_growth_floor_pct:
  operating_margin_floor_pct:
  style_size_ceiling_pct: 8.0
  current_weight_pct:
---
# GLD — Investment Thesis

## Core Thesis (Macro Hedge / Dollar Debasement Insurance)

GLD (SPDR Gold Shares) is held as a portfolio hedge, not a growth position. The thesis is that a structurally deteriorating U.S. fiscal position, persistent above-target inflation, geopolitical fragmentation, and central bank de-dollarization purchases create a sustained tailwind for gold prices over a multi-year horizon. GLD provides liquid, cost-efficient exposure to spot gold without storage or counterparty risk.

This is not a "gold bug" permanent allocation. It is a measured hedge against the scenario where equity risk premia compress, real yields turn negative, or the dollar weakens materially relative to hard assets. The position is sized as insurance, not as a return driver — the goal is to own enough gold that a severe equity drawdown coinciding with dollar weakness is partially offset, without sacrificing too much equity upside through an outsized allocation.

## Entry Context

Cost basis: ~$1,278 total at entry. Gold had already moved significantly from 2023 lows driven by central bank buying (China, India, Russia alternatives), rate cut expectations, and geopolitical tension. The entry is not at a trough; it is an acknowledgment that the macro backdrop for gold holding value has strengthened structurally, not just cyclically.

## Bull Case for the Hedge

- **Fiscal deficit trajectory:** U.S. federal debt and deficits are on an unsustainable path by most independent projections. Gold historically performs well in environments where investors doubt long-run dollar purchasing power.
- **Central bank de-dollarization:** Emerging market central banks (China, India, Middle East) have been accumulating gold at record pace as a reserve alternative to U.S. Treasuries. This is structural demand, not speculative.
- **Real yield sensitivity:** Gold tends to outperform when real Treasury yields are negative or declining. If inflation proves stickier than expected while the Fed eases, real yields fall and gold benefits.
- **Geopolitical risk premium:** Heightened geopolitical fragmentation (Russia-Ukraine, Taiwan tensions, Middle East) sustains a geopolitical risk premium in gold that was absent through much of the 2010s.
- **Correlation benefit:** Gold has low-to-negative correlation to equities during severe risk-off events, providing the hedge value I want from this position.

## What I Watch

- Real Treasury yields (TIPS). Gold tends to move inversely.
- DXY dollar index trend. A sustained dollar weakening is the most powerful gold tailwind.
- Central bank reserve data (World Gold Council quarterly reports).
- I will NOT trim GLD based on gold price moving up alone — the hedge value comes from holding it through equity stress periods.

## Exit / Reduction Conditions

1. U.S. fiscal trajectory improves materially (deficit reduction deal, structural reforms) that credibly restores dollar confidence.
2. Real yields rise sustainably above 2.5% on credible Fed tightening — gold becomes expensive to hold versus risk-free real returns.
3. A higher-conviction portfolio hedge opportunity (TIPS ladder, alternative macro hedge) emerges that offers better risk-adjusted portfolio protection per dollar allocated.
4. Gold price runs to extreme valuation versus real rates or historical ranges, suggesting a momentum-driven overshoot disconnected from macro fundamentals.

## Scaling State & Priority

- Current 0.18% is a starter; build toward 3–5% over time as a portfolio stabilizer.
- Rotation priority: low urgency; add opportunistically on pullbacks, not on momentum.

<!-- region:position_state -->
**Current Allocation:** 0.01%
**Cost Basis:** $6,910.60
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** ETF
**Size Ceiling:** 8.00%
**Drift:** -7.99%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-06-25: Buy 6.0 @ $368.33
- 2026-06-02: Sell -5.0 @ $413.39
- 2026-05-08: Buy 3.0 @ $435.14
- 2026-05-01: Buy 3.0 @ $425.84
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-07-14 10:51: Auto-sync allocation 0.01%, drift -7.99%
<!-- endregion:change_log -->
