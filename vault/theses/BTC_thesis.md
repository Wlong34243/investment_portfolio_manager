---
ticker: BTC
style:
framework_preference: macro_hedge_v1
entry_date:
last_reviewed: '2026-09-02'
cost_basis: 1049.85
current_allocation: 0.17%
time_horizon:
triggers:
  trigger_type: price          # no earnings; fwd_pe / trailing_pe / PEG impossible. Same argued
                               # exception as GLD (prompts/trigger_types_2026-08-09.md).
  entry_price:
  seed_position_weight: 0.17%
  price_add_below:             # [BILL] — must be set on the SHARE, not on bitcoin. See Instrument note.
  price_trim_above:            # [BILL] — same.
  discount_from_52w_high_add:  # [BILL]
  style_size_ceiling_pct: 0.0  # [BILL] — blocked on the style key below.
---
# BTC — Investment Thesis

**STATUS: Bill-authored thesis recorded 2026-08-29.** Supersedes the 2026-08-28 Motley Fool
redraft for **Core Thesis voice** (store-of-value / digital monetary commodity, not regulatory
event optionality). Pre-edit file archived to
`vault/theses/archive/BTC_thesis.md.bak.2026-08-29`.

**History correction (2026-08-29):** Position Story surfaced a **2026-02-06 Sell, −10 shares
@ $30.60** in scoped Transactions — not reflected in prior drafts. Current 30-share lot (Aug
2026 entry) is a **re-entry** after a full exit ~6.5 months earlier, not a first-time exposure.
Motive for the February sale is **not recorded** here.

**Still `[BILL]`:** style key, `style_size_ceiling_pct`, price levels, scaling, rotation priority,
exit conditions.

---

## Instrument — read this before setting any level

The position is **Grayscale Bitcoin Mini Trust ETF (`BTC`, NYSE Arca)**, not spot bitcoin
custody. Schwab description `GRAYSCALE BITCOIN MINI TR ETF`, Schwab asset class `Equity`,
expense ratio **0.15%**.

**The share price and the bitcoin price are different numbers and are routinely confused.**
Roughly **0.000437 BTC per share** ([btcetfcalc](https://btcetfcalc.com/education/tickers/grayscale-mini-btc/)).
Derived arithmetic at that ratio, **not a target and not a forecast**:

| Share price | Implied bitcoin (approx.) |
|---|---|
| $35.22 (bundle `8b3a2928…`, 2026-08-28) | ≈ $80,600 |
| $25.65 (52w low) | ≈ $58,700 |
| $55.96 (52w high) | ≈ $128,100 |
| — | $100,000 → ≈ **$43.70/share** |

The ratio **declines over time** as the 0.15% fee is paid in bitcoin, so this mapping drifts
and must be re-derived, not cached. Every price figure in third-party research below that cites
**bitcoin** prices must be converted before writing **share** trigger levels.

## Known Facts (sourced, not judgment)

- **Instrument:** Grayscale Bitcoin Mini Trust ETF (`BTC`), not spot custody.
- **Current lot:** 30.0 shares, avg cost $34.995/share, cost basis $1,049.85 (Aug 2026 entry window).
- **Current** (bundle `8b3a29284ad2…`, 2026-08-28): price $35.22, MV $1,056.60, weight **0.17%**,
  unrealized **+$6.75 / +0.64%**.
- **52-week context** (Valuation_Card, 2026-08-28): low $25.65, high $55.96, 52w position **32.0%**,
  **36.8%** off the high.
- **Account:** Schwab suffix `...8767`, inside `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES`. Taxable.
- **Prior exposure (Transactions, scoped accounts):** **2026-02-06 Sell, −10 shares @ $30.60.**
  With the current 30-share Aug 2026 lot as the only open position, the ledger implies a **prior
  position was fully closed in February 2026** before this re-entry. Earlier buy dates for the
  closed lot are not recorded in this file — query `Transactions` if needed.
- **Re-entry window:** Position absent from bundle `6bacf63dd536` (2026-08-25); present in
  `55874cf2a62f` (2026-08-26) — brackets Aug buy to ~24h, not a substitute for fill records.

## Style

`[BILL]` — **still unassigned.** BTC remains excluded from the Style Size Ceiling Check until
Bill assigns a style key. GLD precedent (`ETF`, `trigger_type: price`) is the obvious candidate
for a non-earnings monetary proxy; not applied here without Bill's call.

## Core Thesis

**Bitcoin is a high-volatility, non-yielding monetary asset whose long-run upside depends on broader adoption as a globally liquid, credibly scarce store of value—while its downside depends on that adoption stalling, regulation becoming hostile, or demand proving mainly speculative.**

The investable version is not "BTC replaces all money." It is: **a relatively small but growing share of global savings, collateral, and reserve assets may seek exposure to an asset with a fixed issuance schedule, portable self-custody, and no central issuer.** Bitcoin's original design was peer-to-peer electronic cash, but the strongest contemporary investment case is closer to "digital monetary commodity" or "digital gold." [bitcoin](https://bitcoin.org/bitcoin.pdf)

## The bull case

1. **Credible scarcity**
   - Bitcoin's protocol targets a maximum supply of 21 million BTC and reduces issuance over time through halvings.
   - Unlike fiat currencies, bank deposits, or most financial assets, issuance is not governed by a central bank, corporation, or commodity producer responding to price.
   - The key distinction is not merely that supply is limited; it is that the rules are broadly visible, rule-based, and expensive for the network's economic participants to change.

2. **A monetary asset suited to the internet**
   - BTC can be transferred globally, settled without a traditional banking intermediary, divided into very small units, and held directly by its owner.
   - It combines some attributes of gold—scarcity and no issuer—with native digital transferability and verifiability.
   - This makes it potentially useful for cross-border savings, capital mobility, collateral, and reserve diversification, especially where local money or banking systems are weak.

3. **Network effects and liquidity**
   - Bitcoin has the longest operating history, largest recognition, deepest liquidity, and broadest infrastructure among cryptoassets.
   - The investment thesis strengthens as more holders, custodians, exchanges, payment rails, derivatives markets, miners, regulated investment products, and corporate or sovereign allocators participate.
   - A store-of-value asset does not need universal adoption. It only needs a meaningful and persistent share of global wealth to choose it as a savings vehicle. Fidelity frames this as Bitcoin's "aspirational store of value" case. [fidelitydigitalassets](https://www.fidelitydigitalassets.com/research-and-insights/bitcoin-investment-thesis-bitcoin-aspirational-store-value-system)

4. **Asymmetric portfolio exposure**
   - If BTC remains a niche speculative asset, it can decline severely.
   - If it becomes a recognized reserve-style asset alongside gold, sovereign debt, and other stores of value, its market capitalization could rise substantially from a lower base.
   - That creates a potential asymmetric payoff—but only for an allocation small enough that a major drawdown does not impair the overall portfolio.

5. **Macro optionality**
   - BTC may benefit when investors worry about currency debasement, capital controls, banking fragility, geopolitical fragmentation, or the long-run credibility of sovereign debt and monetary policy.
   - It should not be described as a reliable short-term inflation hedge: its trading behavior is often dominated by liquidity, risk appetite, leverage, and market positioning. The macro case is better thought of as a **long-duration hedge against monetary-system uncertainty**, not a month-to-month CPI trade.

## The bear case

| Risk | Why it matters | What would validate it |
|---|---|---|
| No intrinsic cash flow | BTC produces no earnings, dividends, coupon, or contractual claim on assets | Investors continue valuing it primarily as a trade rather than a durable monetary asset |
| Extreme volatility | Large drawdowns can force selling, undermine institutional use, and make adoption psychologically difficult | Volatility stays persistently too high for reserve or collateral use |
| Store-of-value competition | Gold, short-duration government debt, stablecoins, other crypto networks, and future digital money compete for savings demand | BTC's share of crypto and alternative-store-of-value demand erodes |
| Regulatory and custody risk | Access often relies on exchanges, ETFs, banks, miners, and custodians even if the protocol itself is decentralized | Major jurisdictions restrict ownership, on/off-ramps, custody, mining, or institutional distribution |
| Security-budget transition | Over time Bitcoin relies increasingly on transaction fees rather than new issuance to pay miners | Hashrate/security weaken materially, or fee economics fail to support robust network security |
| Concentration and leverage | Whales, ETF flows, derivatives liquidations, and leverage can amplify price moves | Market structure remains dominated by reflexive flows rather than organic adoption |
| Narrative failure | "Digital gold" is not guaranteed; money is a social and institutional convention | Adoption fails to expand through multiple economic cycles |

The central bear rebuttal is simple: **scarcity alone does not create value.** Beanie Babies were scarce; value requires durable demand. BTC's long-term value must be supported by increasing willingness to hold it, accept it, custody it, or use it as collateral.

## What would prove it right

Judged against observable milestones, not price targets alone:

- A rising share of long-term, non-speculative ownership rather than leverage-driven trading.
- Deepening global liquidity and resilient trading across venues and jurisdictions.
- Continued security: strong hashrate, distributed mining, and no material protocol compromise.
- Growing institutional infrastructure: qualified custody, derivatives, accounting clarity, lending/collateral acceptance, and regulated access.
- Measurable adoption in savings, treasury management, remittances, and cross-border settlement.
- BTC retaining its relative dominance as the primary non-sovereign monetary cryptoasset.
- Resilience through severe risk-off periods, political pressure, and market drawdowns.

A healthy thesis does **not** require BTC to become a daily medium of exchange everywhere. It requires it to become sufficiently trusted as a monetary reserve asset for a persistent minority of global capital.

## What breaks the thesis

Invalidation criteria:

- A credible technical or cryptographic failure that compromises ownership, issuance rules, or settlement finality.
- Sustained loss of liquidity, security, or developer/miner participation.
- Structural regulatory restrictions across major capital markets that materially reduce legal access and institutional ownership.
- A superior competing asset meaningfully captures the "neutral, scarce digital reserve asset" role.
- The market repeatedly fails to show durable demand beyond liquidity cycles and speculative leverage.
- Political consensus changes the 21 million cap or other core monetary rules in a way that damages confidence in Bitcoin's credibility.

## Practical conclusion

> **BTC is a venture-style position in the monetization of a decentralized digital commodity.** Its core advantage is credible scarcity combined with global, bearer-style digital transferability. Its value rises if more investors and institutions treat it as a long-term reserve asset; it falls if that social consensus, access, security, or relative dominance weakens. Because BTC has no cash flows and can suffer very large drawdowns, position sizing and custody discipline matter more than conviction alone.

The most defensible portfolio framing: **small, deliberate, long-horizon exposure; no leverage; explicit rebalancing rules; and a willingness to own zero if invalidation criteria are met.** The case is inherently probabilistic, not a certainty or a guaranteed hedge.

## What I Watch

`[BILL]` to confirm or replace. The milestone list under **What would prove it right** is the
starting watchlist from Bill's 2026-08-29 thesis. Instrument-specific: BTC-per-share ratio drift
(since every share-price level depends on it).

## Scaling State
next_step: `[BILL]`

## Rotation Priority
priority: `[BILL]`

## Exit Conditions
`[BILL]` — none written. Bill's invalidation criteria above define what would break the thesis;
operational exit rules (size, timing, share-price bands) remain unset.

## Research Inputs (superseded 2026-08-29)

*The 2026-08-28 Motley Fool redraft (regulatory-event / Clarity Act framing) is archived here
for audit trail only. It does **not** state Bill's current thesis voice. Pre-edit file:
`vault/theses/archive/BTC_thesis.md.bak.2026-08-29`.*

**Primary source (superseded):** Motley Fool, 2026-08-27 — verification table from 2026-08-28 pass:

| # | Source claim | Verdict | Correction |
|---|---|---|---|
| 1 | White House crypto event 2026-08-19; Trump backed the Clarity Act | **CONFIRMED** | Attendees and quote verified. |
| 2 | Trump "hinted the U.S. might start accumulating Bitcoin for the Strategic Bitcoin Reserve" | **CONTRADICTED** | Reserve established by EO 2025-03-06; forfeiture-sourced; no purchase authority 18 months in. |
| 3 | "Quick gain of 20% in the price of Bitcoin" caused by the event | **OVERSTATED** | ~20% is the week 08-17→08-24; event day ~+5%. |
| 4 | Spot bitcoin ETFs best week since October 2025 | **CONFIRMED (context omitted)** | $1.92B week; 2026 net flows still ≈ **−$2.91B**. |
| 5 | Clarity Act "already priced in?" | **MISFRAMED** | Passage priced below 20%; 09-15 is cloture only. |
| 6 | No blockchain upgrade, no halving, treasury companies cutting purchases | **UNVERIFIED** | Author characterisation only. |
| 7 | Kalshi odds (various) | **RECORDED, NOT VERIFIED** | Not eligible for trigger levels. |

## Review Log

- **2026-08-29: Bill-authored thesis + history correction.** Archived prior file to
  `vault/theses/archive/BTC_thesis.md.bak.2026-08-29`. **Voice:** replaced Motley Fool
  regulatory-optionality draft with Bill's store-of-value / digital monetary commodity thesis
  (2026-08-29). **History:** added 2026-02-06 Sell −10 @ $30.60 from scoped Transactions;
  reframed Aug 2026 entry as re-entry after full February exit — not first-time exposure.
  Motley Fool material moved to **Research Inputs (superseded)**; verification table retained.
  **`[BILL]` unchanged:** style, ceiling, price levels, scaling, rotation, exit rules.
- **2026-08-28: Drafted from Bill-supplied Motley Fool source; scaffold superseded.** See
  archived `BTC_thesis.md.bak.2026-08-28T08-40-00`. Superseded for thesis voice by 2026-08-29 entry.
- **2026-08-27: Scaffold file created** — `NEW_POSITION_NO_THESIS` flag; no prose invented.

<!-- region:position_state -->
**Current Allocation:** 0.17%
**Cost Basis:** $1,049.85
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** None
**Size Ceiling:** 0.00%
**Drift:** +0.00%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-08-25: Buy 30.0 @ $34.99
- 2026-02-06: Sell -10.0 @ $30.60
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
Total Realized G/L: $-185.56 over 1 closed lots. Total Proceeds: $306.00.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-09-02 11:36: Auto-sync allocation 0.17%, drift +0.00%
<!-- endregion:change_log -->
