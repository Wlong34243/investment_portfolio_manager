---
ticker: JPIE
style: ETF
framework_preference: psychology_of_money
entry_date: 2026-04-20
last_reviewed: '2026-05-03'
current_allocation: 7.32%
cost_basis: 50646.29
time_horizon: 0 to 3 years (tactical cash & ballast)
triggers:
  fwd_pe_add_below:
  fwd_pe_trim_above:
  fwd_pe_historical_median:
  price_add_below: 45.0        # opportunistic adds only if discount + spreads widen
  price_trim_above: 47.5       # happy to trim/harvest near top of historical range
  discount_from_52w_high_add:
  revenue_growth_floor_pct:
  operating_margin_floor_pct:
  style_size_ceiling_pct: 10.0 # cap “dry powder with risk” so equities still drive returns
  current_weight_pct: 8.5
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

<!-- region:position_state -->
**Current Allocation:** 7.32%
**Cost Basis:** $50,646.29
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** ETF
**Size Ceiling:** 8.00%
**Drift:** -0.68%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-04-17: Sell -75.0 @ $46.25
- 2026-04-16: Buy 200.0 @ $46.16
- 2026-04-16: Buy 100.0 @ $46.16
- 2026-04-16: Buy 200.0 @ $46.16
- 2026-04-10: Sell -500.0 @ $46.09
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
Total Realized G/L: $30.00 over 35 closed lots. Total Proceeds: $47,152.00.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-05-03 14:58: Auto-sync allocation 7.32%, drift -0.68%
<!-- endregion:change_log -->
