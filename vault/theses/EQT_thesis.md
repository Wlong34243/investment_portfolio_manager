---
ticker: EQT
style:                        # [BILL] — GARP vs. physical-AI-infra theme, see Style section
framework_preference:         # [BILL]
entry_date: '2026-08-31'
last_reviewed: '2026-09-02'
cost_basis: 11503.819999999974
current_allocation: 1.95%
triggers:
  trigger_type:                # [BILL] — blocked on style key above
  entry_price:                 # [BILL]
  seed_position_weight: 0.69%
  price_add_below:             # [BILL]
  price_trim_above:            # [BILL]
  style_size_ceiling_pct: 0.0  # [BILL] — blocked on the style key above; not a coverage bug (see BTC)
---
# EQT (EQT Corporation) — Investment Thesis

**STATUS: Initiated 2026-08-31.** Same-day rotation: funded by selling XLF. Bill's own
stated rationale is the rotation itself ("bought today selling xlf") — no further
personal justification given. Everything below the Known Facts section is a research
summary Bill supplied in the same message, **fact-checked against primary sources this
session** — one figure in the original summary was wrong and is corrected, not
transcribed, below.

## Known Facts (sourced, not judgment)

- **Position (per context bundle `f165f5711a07…`, 2026-09-02 12:57 UTC):** 210.0 shares,
  cost basis $11,503.82 (unit cost $54.78), market value $11,655.00 at $55.50/share.
  Weight 1.96% of that bundle's $595,650.77 total. Up from 190.0 shares / $10,412.62 on
  2026-09-01 — a further +20-share add, funded as part of the same-day EMXC trim
  (95→45 sh) that also funded CF/RRC/NOW adds; see Review Log below and
  `EMXC_thesis.md` for the funding leg (not updated here — out of scope for this task).
- **Live (Schwab positions fetch, 2026-08-31, superseded by the bundle line above):**
  price $54.83, market value $4,112.25, unrealized -$27.67 (~-0.67%) — close to Bill's
  own pasted snapshot ($54.99 / -0.38% unrealized) at original entry.
- **Account:** Schwab tax-lot hash `30498767` → suffix `...8767`, inside
  `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES`. In scope. **Taxable.**
- **Acquisition date: not recorded** by Schwab for this lot (same gap as every other
  same-day entry this vault has hit — BTC, CF, QXO's later lots).
- **Funding leg — rotation, not a standalone buy.** Bill states he sold XLF to fund
  this entry. Confirmed directionally: XLF's live position (45 sh, $2,533.29 cost
  basis) is sharply below what `XLF_thesis.md` had on file from this morning's sync
  (before this trade, $8,192.79 cost basis) — a real, same-day reduction, not noise.
  **Exact XLF shares/proceeds not available**: neither the Sheets `Transactions` tab
  nor a live Schwab transaction-history pull (3-day window) shows the trade yet —
  broker activity-feed lag behind the position/lot endpoints, not a missing trade.
  Cross-referenced in `XLF_thesis.md`'s Review Log. Per Analysis Rule 4 (`CLAUDE.md`):
  this is a rotation and is reported as one, not a standalone add.
- **Approximate weight:** 0.69%, computed as $4,112.25 against the last known bundle
  total ($600,705.08, 2026-08-31 08:15 bundle `14f293f2d594…`). **Unofficial** — the
  authoritative weight is whatever the next sync writes to Holdings_Current.

## Style

`[BILL]` — unassigned. Worth naming a candidate rather than deciding it: the research
below frames EQT as a natural-gas producer benefiting from data-center/AI power
demand — the same thematic frame as the existing physical-AI-infrastructure sleeve
(`VST_thesis.md` names VST/IFRA/ETN/VRT explicitly). Whether EQT belongs in that sleeve,
or is closer to a GARP value/production-growth story, is a real style question, not a
formality — flagged, not decided.

## Core Thesis

*What the supplied research supports, corrected against primary sources — not Bill's
own words, since none were given beyond the rotation fact above.*

EQT is a natural-gas producer positioned at the intersection of two demand drivers:
rising electricity demand from data centers/AI load growth, and LNG export demand. A
newly-signed long-term supply contract (below) is the concrete evidence for the
data-center angle, not just narrative. Q2 2026 results were mixed — an EPS miss against
a small revenue beat — but production guidance was raised on operational execution, and
the company just signed a decade-long committed offtake deal. The near-term print and
the long-term contract point in different directions; which one governs the position
is not resolved here.

## Bull Case

*Facts as supplied by Bill, verified and corrected against primary sources this
session — see Review Log for what changed.*

- **Strategic contract, verified with more detail than supplied:** a **10-year gas
  supply agreement for 325,000 Dth/day**, tied to a **new 2 GW power plant in West
  Virginia**, with pricing **linked to PJM power prices** — not a flat-rate deal, so
  EQT's realized revenue on this contract moves with PJM power markets, not just gas
  prices. [Yahoo Finance](https://finance.yahoo.com/energy/articles/eqt-q2-earnings-call-highlights-140000628.html)
- **Production guidance raised** on operational strength: 2026 guidance lifted by
  ~90 Bcfe to a **2,375–2,450 Bcfe** range; Q2 sales volume (634 Bcfe) beat both
  prior-year and the high end of guidance. [Yahoo Finance](https://finance.yahoo.com/markets/stocks/articles/eqt-nyse-eqt-surprises-strong-204416888.html)
- **Analyst sentiment, as supplied by Bill** — "20 of 25 analysts Strong Buy," ~30.5%
  implied upside. Independently checked, not exactly reproduced: multiple sources this
  session show a Strong Buy consensus (one shows 21 buy / 0 sell / 4 hold = 25 raters,
  matching Bill's count almost exactly) with average-target upside estimates ranging
  ~25–55% depending on source and recency. Directionally correct, strongly bullish
  consensus confirmed — **the exact 30.5% figure is Bill's source's number, not
  independently reproduced to the decimal, and per standing rule this is never to be
  used as a trigger level** (`CLAUDE.md`: consensus targets ratchet and structurally
  cannot fire as a trim level).
- **Demand drivers named in the supplied summary** — rising natural gas prices, data
  center demand, LNG export demand — are the framing the contract above substantiates.

## Key Risks

- **Q2 2026 print was mixed, and the summary Bill supplied got one number backwards
  — corrected here, not transcribed.** Adjusted EPS **$0.39, missed** the ~$0.42
  consensus (Bill's figure was right). Revenue **$1.81B was a small beat** against an
  ~$1.80B forecast — **the supplied summary said this missed forecasts by 3.3%, which
  is wrong**; verified against three independent sources
  ([TradingView](https://es.tradingview.com/news/tradingview:6a04ae1306e87:0-eqt-reports-q2-2026-1-809b-operating-revenue-211-4m-net-income-0-39-adjusted-eps/),
  [Investing.com](https://www.investing.com/news/transcripts/earnings-call-transcript-eqt-tops-revenue-lifts-outlook-in-q2-2026-93CH-4806529),
  [Yahoo Finance](https://finance.yahoo.com/markets/stocks/articles/eqt-nyse-eqt-surprises-strong-204416888.html)).
  Net effect: the bottom-line miss is real, but it is not corroborated by a top-line
  miss the way the original summary implied — a narrower, more mixed picture than
  "missed on both."
- **Heavy reliance on natural gas and geographic concentration** — as supplied by Bill;
  a single-commodity, Appalachia-concentrated producer is exposed to regional
  basis/pricing risk and commodity-price cycles more than a diversified name.
- **Faster decarbonization / regulatory change** — as supplied; a real long-horizon
  risk for gas-specific demand assumptions, not quantified here.
- **The bull case leans on one contract.** The 325,000 Dth/day PJM-linked deal is
  concrete, but it is one counterparty/one plant. `[BILL]` — worth knowing whether more
  deals of this shape are in the pipeline or this is a single proof-point.

## Scaling State

next_step: `[BILL]`

## Rotation Priority

priority: `[BILL]`

## Exit Conditions

`[BILL]` — none stated. Do not infer exit conditions from the risks listed above.

## Review Log

- 2026-08-31: Thesis file created same-day as entry, funded by an XLF trim (rotation,
  not a standalone add — see Known Facts). Core content is a research summary Bill
  supplied in the same message, fact-checked this session: **EPS-miss claim confirmed
  correct** ($0.39 vs ~$0.42 consensus); **revenue-miss claim was wrong and corrected**
  — $1.81B was a small beat against ~$1.80B forecast, not a 3.3% miss; the 10-year gas
  deal confirmed and enriched (2 GW West Virginia plant, PJM-linked pricing); the
  raised production guidance confirmed (+~90 Bcfe to 2,375–2,450 Bcfe); analyst
  sentiment directionally confirmed Strong Buy, exact upside % not independently
  reproduced and explicitly not to be used as a trigger. Style, trigger_type, exit
  conditions all left `[BILL]` — none given. Position verified against live Schwab
  positions/tax-lots since Holdings_Current had not yet synced to the trade; exact
  XLF-side transaction detail unavailable (broker activity-feed lag), cross-referenced
  in `XLF_thesis.md`.
- 2026-09-01: Known Facts position line corrected from 75.0 sh / $4,139.92 to 190.0 sh
  across two 95.0-share lots / $10,412.62 per bundle `ai_briefing_2026-09-01_082404`
  tax lots. Rationale for the add is not on record — `[BILL]`. style, trigger_type,
  price_add_below, price_trim_above and style_size_ceiling_pct remain blank; whether
  that is the deliberate BTC/CF `[BILL]` pattern or an unfinished scaffold is `[BILL]`.
- 2026-09-02: Frontmatter gap confirmed **unresolved** — not the deliberate BTC/CF
  `[BILL]` exclusion pattern (those files mark intent explicitly; EQT does not).
  Blank `style`, `framework_preference`, `trigger_type`, `entry_price`,
  `price_add_below`, `price_trim_above`, and `style_size_ceiling_pct: 0.0` silently
  drop EQT (~1.73%, ~$10,328) from the Style Size Ceiling Check. Bill to assign
  style key and trigger type; agents do not invent bands. Run
  `python scripts/generate_eqt_frontmatter_signoff.py` for the blank-field table.
- 2026-09-02: Frontmatter blanks now carry explicit inline `[BILL]` comments
  (`style`, `framework_preference`, `trigger_type`, `entry_price`, `price_add_below`,
  `price_trim_above`, `style_size_ceiling_pct`), matching the `BTC_thesis.md` marking
  convention — same pattern, applied here rather than invented fresh. These are markers
  only; no values were assigned or inferred. `CLAUDE.md`'s Trim/Add Triggers coverage
  line updated to fold EQT into the deliberate BTC/CF/EQT holdout group. Position also
  refreshed this pass — see the Known Facts line above sourced to context bundle
  `f165f5711a07…` (2026-09-02T12:57:19Z): 210.0 shares, cost basis $11,503.82, market
  value $11,655.00, weight 1.96%. Sourced strictly from that bundle, not from Sheets or
  the 2026-09-01 export.

<!-- region:position_state -->
**Current Allocation:** 1.95%
**Cost Basis:** $11,503.82
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** None
**Size Ceiling:** 0.00%
**Drift:** +0.00%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-09-01: Buy 20.0 @ $54.56
- 2026-08-31: Buy 20.0 @ $54.08
- 2026-08-31: Buy 75.0 @ $55.20
- 2026-08-31: Buy 20.0 @ $54.25
- 2026-08-31: Buy 75.0 @ $54.75
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-09-02 11:36: Auto-sync allocation 1.95%, drift +0.00%
<!-- endregion:change_log -->
