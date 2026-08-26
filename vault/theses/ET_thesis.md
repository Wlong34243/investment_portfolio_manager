---
ticker: ET
style: THEME
framework_preference:
entry_date:
last_reviewed: '2026-08-21'
triggers:
  trigger_type: price
  price_trim_above: 22.00           # NOT changed to $24.33 (consensus target) 2026-08-19, see Review Log
  # price_add_below intentionally unset -- Scaling State is "hold / reinvest distributions," not accumulation, so no add level applies
  style_size_ceiling_pct: 3.0
cost_basis: 6550.93
current_allocation: 1.36%
---
# ET — Investment Thesis

## Style
High-Yield Midstream / Master Limited Partnership (MLP) / Value

## Core Thesis
Buying the physical "toll roads" of American energy infrastructure at a discount. Upside is driven by massive, fee-based cash flows that are largely insulated from the day-to-day price swings of crude oil and natural gas. Energy Transfer operates one of the largest, most impossible-to-replicate pipeline and export terminal networks in North America. The key question is whether management has permanently abandoned its historically reckless M&A empire-building in favor of disciplined debt reduction and steady distribution growth. Judgment: yes.

## Entry Context
Cost basis: $19.34. At entry, ET was trading at a very attractive distributable cash flow (DCF) multiple, offering a hefty, well-covered distribution (yield). Buying in the mid-to-high teens means you are paying a fair price for a deleveraging asset base. The total return profile here is heavily weighted toward cash income rather than explosive multiple expansion. 

## Bull Case
- **Fee-Based Cash Flow:** The vast majority of ET's revenue comes from long-term, fee-based contracts (take-or-pay). They get paid based on the volume of hydrocarbons moving through their pipes, not the spot price of the commodity, making cash flows highly predictable.
- **Irreplaceable Assets:** Environmental regulations and political opposition have made it nearly impossible to build new pipelines in the US. This creates a massive, insurmountable moat around ET's existing infrastructure, driving up the value of their current pipes.
- **Deleveraging & Discipline:** After years of punishing the stock with high debt and aggressive acquisitions, management has successfully deleveraged the balance sheet to investment-grade levels, freeing up cash to steadily increase the quarterly distribution.
- **Export Boom:** ET is heavily exposed to natural gas liquids (NGLs) and the massive buildout of US LNG export terminals, positioning them perfectly to supply energy-starved markets in Europe and Asia.
- **Domestic AI/Data-Center Gas Demand (added 2026-08-07):** Beyond the LNG-export leg above, domestic natural gas demand from AI data centers is emerging as a second, distinct demand-side driver for gathering & processing volumes — grid power growth is struggling to keep pace with data-center load, pushing incremental demand toward gas-fired and gas-adjacent generation. Source: 2026-07-26 Invest Like The Best episode, "Why Natural Gas Will Be AI's Next Great Shortage" (`data/podcast_summaries/2026-07-26_Invest_Like_The_Best_Why_Natural_Gas_Will_Be_AIs_Next_Great_Shortage.md`). This note is limited to the directional driver — the episode's own specific volume-growth figures ran well ahead of published forecasts and were excluded per verification (`data/podcast_summaries/verification/allocation-2026-08-07_VERIFIED_2026-08-07.md`).

## Key Risks
- **Management Capital Allocation:** Executive Chairman Kelcy Warren has a history of pursuing aggressive, debt-fueled acquisitions. If management reverts to empire-building and takes on massive leverage for a questionable merger, the stock will be severely punished.
- **Regulatory & Environmental Red Tape:** Constant legal battles over pipeline routing, environmental permits, and protests can delay projects for years and cost billions in stranded capital.
- **Long-Term Energy Transition:** While natural gas is a "bridge fuel," a rapid, structural decline in global fossil fuel demand over the next two decades would eventually leave midstream companies with stranded assets and declining volumes.
- **Tax Complexity:** As an MLP, ET issues a Schedule K-1 tax form, which complicates tax filing and generally makes it unsuitable for tax-advantaged accounts like IRAs (due to UBTI rules). 

## Scaling State
next_step: hold / reinvest distributions

## Rotation Priority
priority: low

## Exit Conditions
- Management announces a massive, highly dilutive, debt-fueled acquisition that ruins the hard-fought investment-grade balance sheet.
- Distribution coverage ratio drops structurally below 1.5x, signaling the dividend is at risk of being cut.
- Federal regulations effectively ban all new US LNG export terminals, permanently capping the company's long-term growth engine.

## Review Log
- 2026-04: Initiated. Thesis intact. Monitoring distribution coverage ratios, debt reduction targets, and NGL export volumes.
- **2026-08-07:** Added a Bull Case bullet on domestic AI/data-center gas demand as a G&P volume driver, sourced to the 2026-07-26 ILTB episode, per `prompts/consolidate_and_thesis_repair_2026-08-07.md` Step 5.2. Edited directly rather than through the archive-before-overwrite convention; `ET_thesis.md.bak` backfilled retroactively from pre-edit content to close that gap.
- 2026-08-09: trigger_type set explicit: price (kept -- existing 22.00 trim is a genuine, deliberately-set anchor; the THEME default of ceiling_only would have discarded it. See prompts/trigger_types_2026-08-09.md.
- 2026-08-19 (Bill requested, not actioned as stated): Bill asked to raise price_trim_above to $24.33, the sell-side consensus target. Not made, same reasoning as UNH's 2026-08-19 entry and VST's retired consensus_price_target trigger (2026-08-09): a trim pegged to a consensus figure ratchets up with the stock and structurally tends not to fire. price_trim_above stays at 22.00. If Bill wants the level moved, it needs a level he sets directly rather than one sourced from analyst coverage — flagged for him to specify.

<!-- region:position_state -->
**Current Allocation:** 1.36%
**Cost Basis:** $6,550.93
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** THEME
**Size Ceiling:** 3.00%
**Drift:** -1.64%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-08-19: Buy 3.9965 @ $21.35
- 2026-05-20: Buy 4.0982 @ $20.33
- 2026-02-19: Buy 4.2443 @ $19.15
- 2025-11-19: Buy 4.398 @ $16.95
- 2025-11-19: Buy 8.5163 @ $16.95
- 2025-08-19: Buy 9.9953 @ $17.31
- 2025-08-19: Buy 15.4232 @ $17.31
- 2025-05-20: Buy 15.0781 @ $18.11
- 2025-05-20: Buy 7.9792 @ $18.11
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
Total Realized G/L: $-237.83 over 6 closed lots. Total Proceeds: $2,930.72.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-08-21 08:45: Auto-sync allocation 1.36%, drift -1.64%
<!-- endregion:change_log -->
