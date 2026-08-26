---
ticker: JPIE
style: ETF
framework_preference: psychology_of_money
entry_date: 2026-04-20
last_reviewed: '2026-08-21'
current_allocation: 0.84%
cost_basis: 5099.85
time_horizon: 0 to 3 years (tactical cash & ballast)
triggers:
  trigger_type: price
  fwd_pe_add_below:
  fwd_pe_trim_above:
  fwd_pe_historical_median:
  price_add_below: 45.0        # opportunistic adds only if discount + spreads widen
  price_trim_above: 47.5       # happy to trim/harvest near top of historical range
  discount_from_52w_high_add:
  revenue_growth_floor_pct:
  operating_margin_floor_pct:
  style_size_ceiling_pct: 10.0 # cap “dry powder with risk” so equities still drive returns
---
# JPIE — Investment Thesis

## Core Thesis (Dry Powder With Yield)

I use JPIE as a **yielding dry‑powder sleeve**: an actively managed, short‑duration bond ETF that pays me ~5.5–6% while I wait for equity opportunities, with much less rate risk than traditional bond funds.[file:10][web:18] Upside is almost entirely from monthly income, not price appreciation; the goal is to beat T‑bills and money markets modestly without taking equity‑like drawdowns.[file:10][web:18]

JPIE sits between pure cash/SGOV and riskier credit (HYG): higher yield and some credit risk, but still relatively low volatility due to its ~2‑year duration and diversified, securitized‑heavy portfolio.[file:10][web:13][web:18]

## Why JPIE (vs. Cash, SGOV, or Long Bonds)

- Yield: Recent distribution/SEC yield around 5.5–5.7%, paid monthly, versus ~3.5% on ultra‑short Treasuries like SGOV.[web:18][web:19]  
- Duration: Effective duration ~2–2.3 years, meaning much lower interest‑rate sensitivity than core bond funds (AGG/TLT) while still earning a term/yield premium.[file:10][web:13][web:18]  
- Structure: Actively allocated mix of securitized credit (MBS/CMBS/ABS) plus corporates, which historically boosted yield versus a simple Treasury ladder.[file:10][web:18]  

It’s not “risk‑free dry powder” like SGOV, but it’s a good compromise: decent yield, modest price volatility, and easy liquidity when you need to fund risk‑on moves.[file:10][web:18]

## Role & Behavioral Rules

- Role:  
  - Cash‑plus / ballast sleeve.  
  - Source of funds for future high‑conviction equity adds.  
  - Income engine in the background.

- Rules:  
  - I will not treat JPIE as a capital‑gains vehicle; total return is primarily yield.  
  - I’m comfortable with **modest** NAV wiggles, but I will not let this sleeve creep far beyond ~10% of the portfolio, so it doesn’t dilute equity compounding.  
  - When a major equity fat‑pitch appears, JPIE is a **primary funding source**.  

## Key Risks & When It’s *Not* Better Than Simpler Cash

- Credit spread risk: Non‑agency MBS, CMBS, and high‑yield corporates can sell off in a recession; NAV can drop even if rates are stable.[file:10][web:18]  
- Rate‑cut risk: If the Fed cuts aggressively, JPIE’s yield will roll down over time as bonds mature and are reinvested at lower rates, shrinking the advantage over SGOV.[file:10][web:16]  
- Complexity: You’re taking structured‑credit and corporate risk rather than just Treasury risk; in a true credit event, SGOV (pure T‑bills) will hold up better.[file:10][web:19]  

So “better than” depends on your priority:
- If you want *max safety and instant liquidity*: SGOV/short T‑bills likely superior.  
- If you want *meaningfully higher income with tolerable risk*: JPIE is fine as your dry powder sleeve.[file:10][web:18][web:19]

## Hard Exit / Reduce Conditions

I will reduce or exit JPIE and move to simpler cash/T‑bills if:

1. The yield spread vs. SGOV/T‑bills compresses so much that the extra credit risk is no longer worth it (e.g., spread < ~1% for several months).[file:10][web:18][web:19]  
2. Credit spreads widen sharply, signaling rising default risk in MBS/credit that could lead to sustained NAV drawdowns.[file:10][web:18]  
3. The Fed cuts rates aggressively and JPIE’s yield drifts down toward money‑market levels, removing its edge.[file:10][web:16][web:18]  
4. I want to fund a large, high‑conviction equity purchase during a major dislocation; JPIE is a first source of liquidity.  

## Scaling State
next_step: exited — completed 2026-08-21 (110 sh liquidated in Schwab...8767). See Review Log 2026-08-24. Archive deferred pending Realized_GL multi-account re-import.

## Rotation Priority
priority: n/a — position exited 2026-08-21.

## Review Log
- 2026-08-24: Exit completed. Held 2026-08-11 (Holdings_History): 110 sh, basis $5,099.85 ($46.36227/sh). Sold 2026-08-21 in Schwab...8767 (Contributory ...767): four broker lots totaling 110 sh — proceeds $5,044.42, realized G/L **-$55.43** Short Term (broker Realized_GL after All_Accounts import; matches prior Holdings_History-derived figure). Lot opens 2025-09-22 / 2025-09-24 / 2025-12-08. Supersedes the Holdings_History-only estimate recorded earlier the same day. Account is tax-deferred (Contributory) — does not enter Tax_Control / Est. Fed Cap Gains Tax. Thesis left live pending archive sign-off. Multi-account Realized_GL re-import: `prompts/realized_gl_multi_account_2026-08-24.md` / CSV `All_Accounts_GainLoss_Realized_Details_20260824-120714.csv`.
- 2026-08-09: trigger_type set explicit: price (named exception in the build -- existing 45.0/47.5 band is tied to a historical NAV range). See prompts/trigger_types_2026-08-09.md.

<!-- region:position_state -->
**Current Allocation:** 0.84%
**Cost Basis:** $5,099.85
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** ETF
**Size Ceiling:** 10.00%
**Drift:** -9.16%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-08-06: Sell -25.0 @ $45.80
- 2026-08-04: Sell -200.0 @ $45.78
- 2026-08-03: Sell -100.0 @ $45.68
- 2026-07-31: Sell -10.0 @ $45.84
- 2026-07-31: Sell -40.0 @ $45.84
- 2026-07-31: Sell -100.0 @ $45.84
- 2026-07-23: Sell -75.0 @ $45.74
- 2026-07-13: Sell -100.0 @ $45.78
- 2026-07-06: Sell -110.0 @ $45.90
- 2026-06-30: Sell -100.0 @ $46.05
- 2026-06-25: Sell -19.0 @ $46.04
- 2026-06-25: Sell -10.0 @ $46.04
- 2026-06-25: Sell -71.0 @ $46.04
- 2026-06-01: Sell -100.0 @ $45.88
- 2026-05-27: Sell -150.0 @ $46.01
- 2026-05-14: Sell -17.0 @ $46.00
- 2026-05-08: Buy 100.0 @ $46.06
- 2026-05-08: Buy 100.0 @ $46.06
- 2026-04-17: Sell -75.0 @ $46.25
- 2026-04-16: Buy 200.0 @ $46.16
(showing 20 most recent of 38)
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
Total Realized G/L: $-193.50 over 61 closed lots. Total Proceeds: $89,955.08.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-08-21 08:45: Auto-sync allocation 0.84%, drift -9.16%
<!-- endregion:change_log -->
