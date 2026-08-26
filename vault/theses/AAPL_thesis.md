---
ticker: AAPL
style: GARP
framework_preference:
entry_date:
last_reviewed: '2026-08-21'
cost_basis: 9924.61
current_allocation: 1.56%
triggers:
  trigger_type: trailing_pe
  trailing_pe_trim_above: 36.06
  trailing_pe_add_below: 27.76
  style_size_ceiling_pct: 9.0
---
# AAPL — Investment Thesis

## Style
GARP-by-intuition / Product Conviction

## Core Thesis
Fell in love with the products, and the price is right. Classic GARP-by-intuition: the ecosystem lock-in is something experienced firsthand as a customer — hardware, services, and switching costs that compound quietly. Entered at a valuation that felt fair for the quality, with Bill's stated expectation of a path to $400 as the position matures.

## Entry Context
Small starter position (~0.85%), consistent with small-step scaling. The entry bet is that the market was underpricing the services attach rate and the durability of the installed base, not that a specific catalyst was imminent.

## Bull Case
- Ecosystem lock-in: services revenue grows on the installed base with software margins.
- On-device AI could drive the first real upgrade supercycle in years.
- Capital-return machine: buybacks steadily shrink the float.
- Brand pricing power holds through consumer downturns better than peers.

## Key Risks
- China: both a demand market and a manufacturing dependency, doubly exposed geopolitically.
- Regulatory pressure on App Store economics and the Google default-search payment.
- Product cycle staleness: if AI features underwhelm, upgrade cycles keep stretching.
- Valuation already reflects quality; multiple compression is the quiet risk.

## Scaling State
next_step: trim

## Rotation Priority
priority: low

## Exit Conditions
- Product quality conviction breaks (the "love the products" premise is the thesis).
- Services growth stalls while hardware cycles lengthen — ecosystem flywheel slowing.
- China disruption forces structural margin reset.

## Review Log
- 2026-07: Thesis file created. Product-conviction GARP entry; Bill's stated expectation is a path to $400.
- 2026-08-09: trigger_type: trailing_pe, not fwd_pe -- forward P/E has no backfillable historical series (analyst-estimate snapshot only); band on trailing, trigger on trailing, never cross the two. FY2022-2025 annual trailing P/E (n=4 annual observations, 2.1x range 20.1-42.3): trailing_pe_add_below=27.76 (~p25), trailing_pe_trim_above=36.06 (~p75). Live current trailing P/E 35.97 falls inside the range. See prompts/trigger_types_2026-08-09.md.
- 2026-08-14: Scaling State `accumulate` replaced with `trim` (Bill). The 2026-08-10 Sell -14 @ $305.70 is the first trim leg, not a file error. Core Thesis unchanged.

<!-- region:position_state -->
**Current Allocation:** 1.56%
**Cost Basis:** $9,924.61
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** GARP
**Size Ceiling:** 9.00%
**Drift:** -7.44%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-08-10: Sell -14.0 @ $305.70
- 2026-07-31: Buy 5.0 @ $302.03
- 2026-07-30: Buy 4.0 @ $332.13
- 2026-07-20: Buy 10.0 @ $328.36
- 2026-07-17: Buy 10.0 @ $332.66
- 2026-07-15: Buy 5.0 @ $323.43
- 2026-07-14: Buy 10.0 @ $313.83
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
Total Realized G/L: $0.00 over 2 closed lots. Total Proceeds: $4,279.71.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-08-21 08:45: Auto-sync allocation 1.56%, drift -7.44%
<!-- endregion:change_log -->
