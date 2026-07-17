---
ticker: LRCX
style: GARP
framework_preference: lynch_garp_v1
entry_date: 2026-05-03
last_reviewed: '2026-07-17'
current_allocation: 0.02%
cost_basis: 8462.62
time_horizon: 3 to 5 years
triggers:
  fwd_pe_add_below: 18              # add on semi cycle fear; LRCX historically re-rates fast off trough
  fwd_pe_trim_above: 30             # trim when cycle optimism gets priced in fully
  fwd_pe_historical_median: 22
  price_add_below: 210              # meaningful discount from recent highs / cycle trough zone
  price_trim_above: 380             # approaching prior cycle peak territory
  discount_from_52w_high_add: 0.30  # add if 30%+ off 52w high on cycle/macro fear
  revenue_growth_floor_pct: 5       # floor for WFE growth environment; miss signals cycle deterioration
  operating_margin_floor_pct: 42    # world-class margins; contraction below here is a thesis check
  style_size_ceiling_pct: 9.0
  current_weight_pct:
drawdown_tolerance_pct: 0.35        # semi equipment is cyclical; 35% from cost is within thesis
panic_buy_trigger_drawdown_pct: 0.25
---
# LRCX — Investment Thesis

## Core Thesis (Semiconductor Etch & Deposition Duopoly)

I am buying the dominant etch and deposition equipment franchise in a semi-equipment market that has a structurally higher floor than any prior cycle. Lam Research controls roughly half of global etch capacity and a large share of deposition, giving it irreplaceable IP and customer lock-in at every foundry that matters — TSMC, Samsung, Intel Foundry, Micron, SK Hynix. The thesis is straightforward: every new process node, every logic-to-DRAM transition, every HBM stack for AI chips requires more Lam tools per wafer start, not fewer. Unit intensity is rising secularly even as WFE spend oscillates.

The entry was made during a soft patch in wafer fab equipment (WFE) spend where NAND weakness and China trade uncertainty compressed sentiment. I am paying a reasonable multiple for a company whose earnings trough is better than many peers' peaks, and whose installed base of tools generates a high-margin Customer Support Business Group (CSBG) recurring revenue stream regardless of where capex cycle stands.

## Entry Context & Valuation (Lynch GARP Lens)

Cost basis: ~$255.51 per share. At entry LRCX traded at a compressed forward multiple reflecting: (1) the NAND memory downturn delaying tool orders, (2) China export control overhang and (3) general capex caution at foundries. None of these change the long-term unit intensity thesis.

- GARP frame: buying a company with 40%+ operating margins, $4B+ annual FCF, and mid-teens revenue CAGR potential through the next upcycle at a sub-20x forward multiple during a recognized trough.
- Key insight: Lam's CSBG revenues (~50% of total) are relatively cycle-resistant, providing a durable earnings floor that the stock market tends to undervalue at cycle lows.

## Bull Case

- **HBM and AI memory demand:** HBM3/HBM4 production for AI accelerators requires 3-5x more etch steps per bit versus standard DRAM. Every NVIDIA H100/B200/GB300 chip sold creates a direct demand signal for Lam tools.
- **Trailing-edge NAND recovery:** NAND pricing has recovered and enterprise SSD demand is accelerating. When NAND capex restarts, Lam is first in line — no tool substitution risk at the process nodes customers need.
- **Gate-all-around (GAA) node transition:** The move from FinFET to GAA at 3nm and below is etch-intensive. TSMC N2 and Intel 18A both increase Lam content per wafer.
- **CSBG floor:** ~$4B/year in service, spares, and upgrades revenue tied to the 80,000+ tools in the installed base worldwide. Grows independently of new tool shipments.
- **Capital returns:** Management has returned >100% of FCF to shareholders over the past three years via buybacks and dividends; share count is shrinking.

## Behavioral Guardrails & What I Watch

- Drawdown tolerance: accept 30–35% drawdowns tied to cycle pessimism as long as the unit intensity thesis and CSBG floor are intact.
- I will not trade around quarterly WFE guidance noise. The signal is multi-year tool content per wafer start, not whether Q2 WFE is up $2B or down $2B.
- Watch: NAND capex restart timing (Micron, SK Hynix), TSMC N2 ramp pace, Intel 18A progress, and China customer mix as export controls evolve.

## Hard Exit Conditions

1. A credible alternative etch or deposition technology (e.g., directed self-assembly at scale) displaces Lam's core process in the dominant foundry roadmap.
2. China export controls expand to cover installed-base service and spares, materially impairing CSBG revenues.
3. WFE structurally shifts away from etch-heavy processes — for example, if chiplet packaging replaces advanced logic scaling more rapidly than expected, reducing new-node intensity.
4. Operating margins compress below 40% for more than two consecutive quarters without a clear cycle-trough explanation.

## Scaling State & Priority

- Next step: build toward a 3–4% position on weakness; current 0.93% is a starter.
- Rotation priority: medium; semi-equipment is cyclical but the unit intensity thesis is high conviction.

<!-- region:position_state -->
**Current Allocation:** 0.02%
**Cost Basis:** $8,462.62
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** GARP
**Size Ceiling:** 9.00%
**Drift:** -8.98%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-06-18: Sell -15.0 @ $395.90
- 2026-05-07: Buy 5.0 @ $285.95
- 2026-05-05: Buy 5.0 @ $272.38
- 2026-05-04: Buy 7.0 @ $256.32
- 2026-05-04: Buy 5.0 @ $259.14
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-07-17 09:51: Auto-sync allocation 0.02%, drift -8.98%
<!-- endregion:change_log -->
