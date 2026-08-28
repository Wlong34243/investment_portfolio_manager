---
ticker: BTC
style:
framework_preference: macro_hedge_v1
entry_date:
last_reviewed: '2026-08-28'
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
  style_size_ceiling_pct:      # [BILL] — blocked on the style key below.
---
# BTC — Investment Thesis

**STATUS: DRAFTED 2026-08-28 from Bill-supplied source material, with every factual claim
independently verified this session.** Supersedes the 2026-08-27 scaffold (backed up to
`BTC_thesis.md.bak.2026-08-28T08-40-00`).

**What changed:** Bill supplied the research input behind this position — a Motley Fool
article dated 2026-08-27 on the post-Clarity-Act sentiment shift. The descriptive and risk
sections below are drafted from that source **as corrected against primary reporting**.

**What has NOT changed:** Bill has not stated his own thesis, his style tag, his ceiling, his
levels, or his exit conditions. Those remain `[BILL]`. The source is an article, not Bill's
reasoning, and this file does not pretend otherwise. **Do not read the drafted sections as
Bill's stated intent.**

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
and must be re-derived, not cached. Every price figure in the source article below is a
**bitcoin** price. Any `price_add_below` / `price_trim_above` written into the frontmatter
must be a **share** price. Writing $100,000 into a trigger field would never fire.

## Known Facts (sourced, not judgment)

- **Size:** 30.0 shares, single lot, avg cost $34.995/share, cost basis $1,049.85.
- **Current** (bundle `8b3a29284ad2…`, 2026-08-28 12:07 UTC): price $35.22, MV $1,056.60,
  weight **0.17%**, unrealized **+$6.75 / +0.64%**.
- **52-week context** (Valuation_Card, 2026-08-28 07:57): low $25.65, high $55.96,
  52w position **32.0%**, **36.8%** off the high.
- **Account:** Schwab hash `30498767` → suffix `...8767`, inside
  `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES`. In scope. **Taxable.**
- **Acquisition date: still not recorded.** Position first appears in bundle `55874cf2a62f`
  (2026-08-26 12:17 UTC), absent from `6bacf63dd536` (2026-08-25 12:48 UTC). That brackets
  entry to a ~24h window but is not a fill record. `[BILL]` or a `Transactions` tab query.
- **Timing note, offered as context and not as causation:** that entry window falls six days
  after the 2026-08-19 White House crypto event described below. Bill has not stated a link
  and none is inferred here.

## Style

`[BILL]` — **still unassigned, and still the blocking decision.** BTC remains excluded from
the Style Size Ceiling Check for want of a style tag, and `style_size_ceiling_pct` cannot be
set until this is.

The 2026-08-27 scaffold's caution stands: whether any of the four keys should apply to a
spot-bitcoin proxy is itself a decision, not a formality. **The available precedent is GLD** —
also a non-earnings hard-asset proxy, also `trigger_type: price` by argued exception, tagged
`ETF` with an 8.0% ceiling and governed by a size-and-role rule rather than by its own price
band. That is the obvious candidate. It is not applied here because Bill has not said so, and
because an 8.0% ceiling on a 0.17% position governs nothing either way for now.

## Core Thesis (DRAFTED FROM SOURCE — not Bill's words)

*What the supplied source supports, stated no more strongly than the source states it.*

A starter-size, policy-optionality position in a liquid, low-fee bitcoin proxy, entered
during a sentiment shift driven by U.S. regulatory developments rather than by anything
intrinsic to bitcoin.

**The source's own argument is cautionary, and it is reproduced here rather than inverted.**
Its central claim is that *nothing fundamental changed*: no blockchain upgrade, no halving
event approaching, and bitcoin treasury companies still cutting back their purchase
appetite. On its telling the entire move is sentiment and risk appetite, with the possible
passage of the Clarity Act as the primary catalyst — and it closes by asking whether that is
already priced in, and advising that expectations be kept in check.

A thesis written from this material honestly is therefore an **event-driven regulatory
optionality** thesis at deliberately small size, not a store-of-value or debasement thesis.
Those would be different arguments requiring different evidence, and the source makes
neither. `pattern:` is deliberately left unset for that reason — `debasement_hedge` would be
imported from GLD, not derived from anything here.

## Bull Case (as the source frames it, with verified specifics)

- **Regulatory clarity is the stated catalyst.** The Digital Asset Market Clarity Act would
  establish market-structure regulation split between the SEC and CFTC, removing the
  regulatory grey areas around holding and trading digital assets for institutions.
- **Explicit executive backing.** At a 2026-08-19 White House crypto event with SEC Chair
  Paul Atkins, CFTC Chair Michael Selig, and the CEOs of Coinbase, Kraken, Robinhood, Ripple
  and Chainlink, Trump pressed Congress to pass the Act, calling it "very, very powerful
  structured legislation."
  ([CoinDesk](https://www.coindesk.com/policy/2026/08/19/trump-pushes-congress-to-move-on-clarity-act-during-white-house-crypto-event))
- **Flows turned.** US spot bitcoin ETFs took in **$1.92B** in the week ending 2026-08-24 —
  the strongest week since October 2025, led by IBIT at $1.33B across five straight days.
  ([Cointelegraph](https://cointelegraph.com/markets/bitcoin-etf-inflows-billion-strongest-week-october))
- **Price responded.** Bitcoin rose more than 20% over that week, from roughly $63,000 to
  briefly above $79,000.
  ([Yahoo Finance](https://finance.yahoo.com/markets/crypto/articles/bitcoins-14-775-weekly-surge-043931784.html))
- **A dateable catalyst exists**, which the source article does not mention: the Senate has
  set a **cloture vote for 2026-09-15**.

## Key Risks

**The three corrections below are the most important content in this file.** Each is a place
where the supplied source is weaker than it reads, and all three cut against the position.

1. **The Strategic Bitcoin Reserve is not a new buyer, and is not new.** The source says
   Trump "hinted that the U.S. government might start accumulating Bitcoin for the Strategic
   Bitcoin Reserve." The Reserve was in fact **established by executive order on 2025-03-06**
   — roughly 17 months before the event described — with an initial tranche of ~200,000 BTC
   drawn **entirely from criminal and civil forfeitures** (Silk Road, Bitfinex recovery, and
   smaller actions). The EO does direct Treasury and Commerce to develop *budget-neutral*
   acquisition strategies, but that language is also 17 months old, and reporting at the
   18-month mark describes **no authority to buy**. Purchases at scale would require separate
   legislation — Senator Lummis's BITCOIN Act, which would direct 200,000 BTC/year for five
   years, has not passed. **Read plainly: there is no announced government bid.** The source's
   framing implies incremental demand that the underlying policy does not contain.
   ([The Block](https://www.theblock.co/learn/407371/what-is-the-u-s-strategic-bitcoin-reserve),
   [Crypto Impact Hub](https://cryptoimpacthub.com/strategic-bitcoin-reserve-reality-check-2026/))

2. **The Clarity Act is priced as unlikely to pass, not as priced in.** The source asks
   rhetorically whether passage is "already priced in." The better-specified answer is that
   prediction markets put passage **below 20%**, down from a high of 58%, with year-end odds
   around **17.5–18%**. The 2026-09-15 vote is a **cloture vote on the motion to proceed** —
   it needs 60 votes merely to open debate, and does not pass the bill. Republicans need
   Democratic votes that are not currently there. Brian Armstrong (Coinbase) predicting
   passage is an interested party, not evidence.
   **The asymmetry runs the other way from the article's framing:** the catalyst is not
   over-priced, it is improbable — which is a different risk (event failure) than the one the
   source describes (exhausted upside).
   ([DeFi Rate](https://defirate.com/clarity-act-fact-sheet/),
   [Motley Fool](https://www.fool.com/investing/2026/08/22/senators-plan-a-clarity-act-vote-on-sept-15/))

3. **One good week does not reverse the year.** The $1.92B weekly inflow is real and is
   correctly reported. But **US spot bitcoin ETFs remain roughly −$2.91B in net outflows for
   2026**. The "best week since October 2025" framing is true and simultaneously flattering:
   it is a strong week inside a bad year, and the source omits the denominator.
   ([Decrypt](https://decrypt.co/376683/bitcoin-etfs-draw-2-8b-in-eight-day-streak-as-btc-tests-80k))

**Further risks, on the source's own terms:**

4. **The source concedes the thesis is sentiment.** No blockchain upgrade, no halving
   approaching, treasury companies reducing purchase appetite. A position whose stated
   catalyst is a sub-20% legislative event and whose acknowledged driver is risk appetite is
   exposed to a sentiment reversal with no fundamental floor to fall back on.
5. **Attribution error in the move.** The source attributes the full ~20% gain to the
   2026-08-19 event. Bitcoin rose ~5% on the day of the meeting and ~12% over two days; the
   20% is the cumulative week 08-17 to 08-24. Some of the move is not event-attributable.
6. **September is a volatility cluster,** not a single event: the CLARITY cloture vote and an
   FOMC decision land in the same month.
7. **Structural drag.** 0.15%/yr, paid in bitcoin, permanently reducing BTC-per-share. Small,
   but it is the one certainty in this file.
8. **Taxable account, single lot, no acquisition date on record.** Holding period is
   therefore unverified. Under Schwab's **Tax Lot Optimizer** (doctrine `cost_basis_method`,
   established 2026-08-27 — **not FIFO**), a single-lot position offers no lot selection
   anyway. At +$6.75 unrealized the tax consequence of any action is immaterial today; the
   missing acquisition date matters for the ST/LT boundary, not for lot choice.

## What I Watch

`[BILL]` to confirm or replace. Candidates implied by the source, offered as a starting list:

- The 2026-09-15 cloture vote outcome, and whether it is a cloture failure or a
  postponement — those are different signals.
- Whether any **statutory purchase authority** advances (BITCOIN Act or equivalent). This is
  the item that would change risk 1 from "no bid" to "bid."
- Spot-ETF net flows on a **cumulative 2026** basis, not weekly. Weekly prints are noise at
  this position size.
- BTC-per-share ratio drift, since every level in this file depends on it.

## Scaling State
next_step: `[BILL]`

**Unset by design.** The size-and-role question — is this a 0.17% option premium on a
regulatory event, or a starter position building toward a real weight like GLD's stated 3–5%
path? — is exactly the judgment the source cannot supply and Bill has not stated. It also
determines the ceiling. Nothing here should be read as a build path.

## Rotation Priority
priority: `[BILL]`

## Exit Conditions
`[BILL]` — none written. Note for whenever these are set: an event-driven position with a
dated catalyst usually wants an exit condition keyed to **the event resolving**, not to a
price level, or the catalyst passes and the position silently becomes a permanent
unexamined holding. Flagging the shape of the question, not answering it.

## Research Inputs

**Primary source:** Motley Fool, 2026-08-27, on the post-Clarity-Act sentiment shift —
supplied by Bill 2026-08-28. Third-party opinion, treated per house rule as a **claim, not a
datum**. Verification below.

| # | Source claim | Verdict | Correction |
|---|---|---|---|
| 1 | White House crypto event 2026-08-19; Trump backed the Clarity Act | **CONFIRMED** | Attendees and quote verified. |
| 2 | Trump "hinted the U.S. might start accumulating Bitcoin for the Strategic Bitcoin Reserve" | **CONTRADICTED** | Reserve established by EO 2025-03-06; ~200,000 BTC all from forfeitures; no purchase authority 18 months in. No announced government bid. |
| 3 | "Quick gain of 20% in the price of Bitcoin" caused by the event | **OVERSTATED** | ~20% is the week 08-17→08-24 (~$63K → >$79K). Event day ~+5%; two days ~+12%. |
| 4 | Spot bitcoin ETFs recorded their best week since October 2025 | **CONFIRMED (context omitted)** | $1.92B, correct. But 2026 net flows remain ≈ **−$2.91B**. |
| 5 | Primary catalyst is possible passage of the Clarity Act; "isn't that already priced in?" | **CONFIRMED as catalyst / MISFRAMED as risk** | Passage priced **below 20%** (from 58%); year-end ≈17.5–18%. 09-15 is a **cloture** vote needing 60 to open debate. Risk is event failure, not exhausted upside. |
| 6 | No blockchain upgrade, no halving approaching, treasury companies cutting purchases | **UNVERIFIED** | Not independently checked this pass. Directionally consistent with the sentiment framing; treat as the author's characterisation. |
| 7 | Kalshi odds for bitcoin ≥$100K: 5% by Oct, 16% pre-Nov, 18% pre-Dec, 30% by Jan 2027; year-end 45% <$80K / 30% $80–100K / 25% >$100K | **RECORDED, NOT VERIFIED** | Third-party prediction-market prices as quoted by the author on 2026-08-27. Internally consistent (45+30+25=100). **Not verified against Kalshi and not re-checkable at this date.** Recorded as what one market priced on one day — **not a forecast, not a target, and explicitly not eligible to become a trigger level.** These decay within days. |

**House rule applied:** no figure in this table may be promoted into a trigger, a target, or
a sizing decision. Per `CLAUDE.md`, a trigger must never read a third-party price target or
forecast — the `VST_thesis.md` `consensus_price_target` failure is the standing proof, and
prediction-market quotes are the same species of number.

## Review Log

- **2026-08-28: Drafted from Bill-supplied source; scaffold superseded.** Pre-edit file backed
  up to `BTC_thesis.md.bak.2026-08-28T08-40-00` (10 `[BILL]` markers, scaffold header) per
  archive-before-overwrite. Verified all seven source claims against primary reporting before
  writing: **1 contradicted** (Strategic Bitcoin Reserve — the source implies a government bid
  that does not exist; Reserve predates the event by 17 months and is forfeiture-sourced with
  no purchase authority), **1 overstated** (20% attributed to the event day; it is a weekly
  figure), **1 confirmed-but-context-omitted** (ETF week strong, 2026 still ≈−$2.91B net),
  **1 misframed** (Clarity Act priced below 20% to pass — the risk is event failure, not
  "already priced in"), 2 confirmed, 1 recorded-unverified (Kalshi). Set
  `trigger_type: price` by the same argued exception as GLD and JPIE — bitcoin has no
  earnings, so `fwd_pe` / `trailing_pe` / PEG are impossible and a price band is the only
  option available (`prompts/trigger_types_2026-08-09.md`). Set
  `framework_preference: macro_hedge_v1` to match the only comparable non-earnings asset in
  the vault. Added the BTC-per-share mapping because the source discusses bitcoin at
  $79K–$100K while the instrument trades near $35 — a level written from the source without
  that conversion could never fire. **Left `[BILL]`:** style key, `style_size_ceiling_pct`,
  both price levels, `discount_from_52w_high_add`, `entry_date`, `time_horizon`, scaling
  next_step, rotation priority, and exit conditions. `pattern:` deliberately left unset —
  `debasement_hedge` would be imported from GLD, not derived from this source, which makes a
  regulatory-event argument and not a store-of-value one. No price target, forecast, or
  buy/sell recommendation is expressed anywhere in this file.
- 2026-08-27: Scaffold file created. Position first appears in bundle `55874cf2a62f`
  (2026-08-26 12:17 UTC), absent from `6bacf63dd536` (2026-08-25 12:48 UTC); flagged by
  `detect_undocumented_changes.py` as `NEW_POSITION_NO_THESIS` and by `level_coverage` as
  `no_thesis` / `no_trim_level` / `no_add_level` / `stale_review`. No prose invented.

<!-- region:position_state -->
**Current Allocation:** 0.17%
**Cost Basis:** $1,049.85
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** None
**Size Ceiling:** 0.00%
**Drift:** +0.17%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
No transaction log available — Schwab lot record carries no acquisition date and the Sheets `Transactions` tab was not queried in this pass. Populate on next `write_thesis_updates.py` sync.
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->
