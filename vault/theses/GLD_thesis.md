---
ticker: GLD
style: ETF
framework_preference: macro_hedge_v1
entry_date: 2026-05-03
last_reviewed: '2026-09-02'
current_allocation: 1.14%
cost_basis: 6957.990000000001
time_horizon: 3 to 5 years
triggers:
  trigger_type: price
  fwd_pe_add_below:                 # gold has no earnings; PE triggers not applicable
  fwd_pe_trim_above:
  fwd_pe_historical_median:
  price_add_below: 220              # add on meaningful pullback if macro hedge thesis intact
  price_trim_above: 400             # evaluate-if-momentum only; does not override size-and-role (see Scaling State)
  trim_trigger_role: informational   # approved 2026-09-01: size-and-role governs; 400 is evaluate-if-momentum only
  discount_from_52w_high_add: 0.15  # add on 15% pullback; gold drawdowns tend to be buy opportunities
  revenue_growth_floor_pct:
  operating_margin_floor_pct:
  style_size_ceiling_pct: 8.0
pattern:
  name: debasement_hedge
  established: '2026-08-24'
  note: Monetary policies driving down USD purchasing power; world moving off 
    USD as a core store of value and into more gold.
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

## Scaling State
next_step: starter size; build toward 3-5% over time as a portfolio stabilizer

Governing rule: size-and-role, not the 400 print. `price_trim_above: 400` is an evaluate-if-momentum flag. It does not override "I will NOT trim GLD based on gold price moving up alone" or this 3–5% build path while the position is a ~1% starter. Reduction test is Exit condition 4 (extreme vs real rates), not a print through 400. Rotation: add on pullbacks, not on momentum.

## Rotation Priority
priority: low -- add opportunistically on pullbacks, not on momentum

## Review Log
- 2026-08-24: `pattern: debasement_hedge` tagged from 2026-08-24 dollar/gold store-of-value statement.
- 2026-08-09: trigger_type set explicit: price (argued exception, same logic as JPIE -- gold has no earnings, so fwd_pe/price_to_book are impossible; existing 220/400 band is a deliberate nominal range, the only option available. See prompts/trigger_types_2026-08-09.md.
- 2026-08-14: Named the governing rule at ~$401 / 1.05% weight. Size-and-role (build toward 3–5%; do not trim on price up alone) wins over the 400 print. 400 remains an evaluate-if-momentum flag, not a close-out. Core Thesis unchanged.

<!-- region:position_state -->
**Current Allocation:** 1.14%
**Cost Basis:** $6,957.99
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** ETF
**Size Ceiling:** 8.00%
**Drift:** -6.86%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-08-21: Buy 1.0 @ $420.56
- 2026-07-21: Sell -1.0 @ $373.18
- 2026-06-25: Buy 6.0 @ $368.33
- 2026-06-02: Sell -5.0 @ $413.39
- 2026-05-08: Buy 3.0 @ $435.14
- 2026-05-01: Buy 3.0 @ $425.84
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
Total Realized G/L: $0.00 over 3 closed lots. Total Proceeds: $2,440.07.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-09-02 11:36: Auto-sync allocation 1.14%, drift -6.86%
<!-- endregion:change_log -->
