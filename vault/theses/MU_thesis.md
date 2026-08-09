---
ticker: MU
style: GARP                         # set by Bill 2026-08-07
framework_preference:
entry_date: '2026-08-07'
last_reviewed: '2026-08-08'
cost_basis: 7845.409999999998
current_allocation: 1.30%
triggers:
  entry_price: 875.65               # 5 sh, average cost
  seed_position_weight: 0.72%
  price_add_below:                  # [BILL] — not set at entry
  price_trim_above:                 # [BILL] — not set at entry
  style_size_ceiling_pct: 9.0       # GARP default
---
# MU — Investment Thesis

**STATUS: Drafted 2026-08-07 at entry from Bill-supplied thesis text, with company figures
independently verified this session.** Position, style and ceiling are set. Outstanding
`[BILL]`: price triggers, priority, exit conditions, the combined-memory ceiling decision,
source authorship, and the SKHY cross-reference.

> **Provenance note.** The thesis text was supplied by Bill on 2026-08-07; authorship is not
> recorded (own work or third-party research being cited). Reasoning and figures are
> transcribed. Accumulation language is filed under Scaling State, which is this file's own
> field for a scaling plan, rather than carried as prose recommendation.
> **[BILL] — confirm authorship.**

## Style

**GARP — set by Bill 2026-08-07. Ceiling 9.0%.** The thesis is a valuation-disconnect
argument: earnings power and forward multiple have re-rated faster than the market's
"cyclical semiconductor" framing, and the entry is on that gap. That is GARP reasoning, not
a market-position bet.

⚠️ **Taxonomy consequence — flag, not an objection.** SKHY is tagged **THEME (3.0%)** and is
the same underlying memory/HBM trade in a different jurisdiction. The two are now governed by
different buckets and different ceilings, so **nothing in the ceiling check measures the
combined memory exposure**: MU could run to 9.0% and SKHY to 3.0% — 12% across two tickers on
one bet — without a single BREACH flag firing. This is the same shape as the documented
`styles.json` taxonomy problem in `CLAUDE.md` (one key covering two different things), now
appearing as two keys covering one thing.

**[BILL] — two coherent resolutions, pick one and record it:**
1. Set a per-ticker `style_size_ceiling_pct` on MU below the 9.0 GARP default, sized so
   MU + SKHY together stay inside an intended memory budget. Per-ticker overrides are
   established practice (UNH 5.0, META 4.0, XOM 5.0).
2. Accept the 9.0 and record an explicit combined-memory budget in both files as a manual
   check, since no automated one exists.

Doing neither leaves the largest single-theme concentration in the book unmonitored.

## Core Thesis

Micron is being priced as cyclical semiconductor beta while its earnings profile has already
re-rated to something else. AI servers require far more HBM and DRAM content per unit than
conventional servers, and Micron's supply is contractually spoken for well past the current
quarter. The entry premise is that a broad rotation out of crowded mega-cap technology drags
MU with the group even as company-specific fundamentals keep improving — and that the
disconnect between tape and fundamentals is the opportunity.

The fiscal Q3 2026 print is the evidence. **Revenue $41.46B against a $35.69B consensus**
(+74% sequential, +346% YoY), **GAAP gross margin 84.6% versus 37.7% a year earlier**
(non-GAAP 84.9%), **operating income $33.68B on $41.46B of revenue.** Fiscal Q4 is guided to
**$50.0B ±$1.0B at ~86% gross margin** — a guide that exceeds consensus by **$6.55B**. Shares
rose 14.6% on the print.

**The supply position is the part that changes the framing.** Micron's HBM capacity is **sold
out through 2026, with demand exceeding supply by an estimated 50–67%**, and **HBM3E and HBM4
are fully booked through 2027.** That is not a demand forecast; it is a contracted order book.
It moves the near-term question away from "will AI demand hold" and toward "when does supply
catch up and what happens to pricing when it does."

## Entry Context

Opened 2026-08-07: **5 shares, cost basis $4,378.25 ($875.65 average)**, seed weight **~0.72%**
of book. Marked at $865.69 on entry day for a market value of $4,328.45 and an unrealized
**−$49.80 (−1.14%)**.

*(Day Change and Gain/Loss both reading −1.14% is expected for a position opened the same day.
The −1.79% price change is the stock's full-session move; the position only participated from
the fill.)*

**This is a small seed — 0.72% against a 9.0% ceiling.** Consistent with the staged
accumulation described under Scaling State, and it means the sizing question below is about
what the position is permitted to become, not what it is.

**Funded by a partial COF sale — a rotation with two legs.** Proceeds went to MU and XLF.
Read separately:

- **COF → XLF** is close to a same-sector swap: single-name financial into the sector ETF.
  Reduces idiosyncratic risk, keeps the financials exposure.
- **COF → MU** is the actual rotation: financials into memory/AI-infrastructure.

**The COF sale is consistent with COF's own file.** `COF_thesis.md` sets
`price_trim_above: 175.00` and COF traded **$218.46** — the sale was above Bill's own recorded
trim level. Noted because a trade matching its thesis file is worth recording as such. COF
carried an unrealized gain (+2.61% at bundle `6c531c97`), so the sale realizes gain —
**[BILL] verify lot selection and holding period.**

**Same-day cross-reference:** QQQM was also partially sold (to fund RRC). QQQM holds MU at
0.63% per the bundle's look-through. Selling the index sleeve that contained MU while buying
MU directly is a concentration move, not a wash sale — an ETF and a single constituent are not
substantially identical. Recorded so it is not later misread as a wash-sale problem.

## Bull Case

- **The order book, not the forecast.** HBM sold out through 2026 with demand running
  50–67% above supply; HBM3E and HBM4 fully booked through 2027. Near-term revenue is
  contracted rather than projected.
- **HBM4 is ramping faster than its predecessor.** Over **$1B of HBM4 revenue already shipped**,
  ramping roughly **twice as fast as HBM3E**, in high-volume shipment on the lead customer's
  platform with qualification samples out to multiple end-customers.
- **Data-center revenue is the whole story, and it compounded off a small base.**
  **$25B in fiscal Q3** — Cloud Memory **$13.77B** (from $3.39B a year earlier) and Core Data
  Center **$11.52B** (from $1.53B). Those are 4x and 7.5x year-over-year.
- **Operating leverage is extreme while supply stays tight.** 81% operating margin
  ($33.68B on $41.46B). Incremental margins of this shape mean trailing-cycle multiples
  understate earnings capacity if tightness persists — and mean the reverse if it does not.
- **The pullback is real and current, not hypothetical.** The memory complex sold off hard in
  the week of entry: SK hynix −8.27% in Seoul on 08-06 (KOSPI −4.37%, sidecar triggered),
  Micron −6%, SanDisk −9%, on a SanDisk guide that missed at the midpoint despite revenue
  +372% YoY and an EPS beat. Sector de-risking, not a Micron-specific fundamental break.

## Key Risks

- **This is still a cyclical, and the thesis says so.** A faster-than-expected supply response,
  weaker AI capex, or customer inventory correction reverses pricing and compresses margins
  quickly. 84.6% gross margins are a peak-cycle artifact of scarcity, not a structural moat —
  they will not persist through a supply response.
- **The "fully booked through 2027" cuts both ways.** It de-risks the next 18 months and
  concentrates all the uncertainty at the far end. The interesting question is not FY2027,
  it is what the pricing curve looks like when contracted capacity rolls off into whatever
  supply the industry has added by then.
- **Expectations are now extreme.** After a beat of this size and a guide $6.55B above
  consensus, merely good results are a disappointment. The bar re-rates with the print.
- **Concentration and execution.** HBM yield and ramp execution, customer concentration on the
  lead platform, and geopolitical exposure all introduce volatility independent of demand.
- **Portfolio-level: this doubles an existing bet.** See Position Sizing & Role.
- **Invalidation:** reduce conviction if DRAM/HBM pricing rolls over materially, data-center
  revenue decelerates sharply, HBM4 execution slips, or the fiscal-Q4 trajectory is
  meaningfully missed against the $50.0B ±$1.0B / ~86% guide.

## Position Sizing & Role

**This is the second expression of one bet, and the file should say so plainly.**

- **SKHY is already held at 0.88%** and is the same memory/HBM trade in a different
  jurisdiction. Adding MU concentrates rather than diversifies. **Combined direct memory
  exposure is now 1.59%** (MU 0.72% + SKHY 0.88%) against a combined permitted ceiling of
  **12.0%** (GARP 9.0 + THEME 3.0) — see the taxonomy flag under Style.
- Before this trade the memory-complex exposure floor was ~**2.20%**: SKHY direct 0.88%,
  000660.KS again inside VEA and EMXC (0.31%), MU 0.69% via QQQM/VTI, Samsung 0.32% via funds.
  Only 40% of that was deliberate. MU direct raises the deliberate share and the total.
- ⚠️ **`SKHY_thesis.md` currently reads `next_step: Hold the 20-share seed. No adds pending
  confirmation of the contracted-HBM...`** — an add path explicitly closed pending contracted
  HBM evidence. Micron's Q3 disclosure (sold out through 2026, HBM3E/HBM4 booked through 2027)
  is arguably that evidence, for the industry if not for SK hynix specifically.
  **[BILL] — either that condition is now met and SKHY's file should say so, or the evidence
  was judged insufficient for SKHY and MU was chosen instead. Both are coherent; the files
  currently record neither.** Add a cross-reference in both directions, as was done for
  EMXC↔SKHY on 2026-07-31.

## Scaling State

next_step: **accumulate in tranches on sector-driven weakness, not on strength.** The supplied
thesis is explicit that the approach is staged accumulation during broad semiconductor or
mega-cap de-risking rather than chasing the tape — consistent with small-step scaling.
**[BILL] — the tranche size and the trigger are unstated.** Given `price_add_below` is unset,
there is currently no recorded condition that would define "weakness," which makes this
instruction unactionable as written.

## Rotation Priority

priority: **[BILL]** — not stated at entry.

## Exit Conditions

- **[BILL]** — none recorded. Candidates from the invalidation criteria above:
  - DRAM/HBM contract pricing rolls over materially on renewal.
  - Data-center revenue decelerates sharply on a sequential basis.
  - HBM4 yield or ramp execution slips against the stated 2x-HBM3E pace.
  - Fiscal Q4 lands meaningfully below the $50.0B ±$1.0B / ~86% GM guide.
  - Industry supply additions become visible enough to close the 50–67% demand-over-supply gap.

## Catalysts

1. Sustained DRAM and HBM pricing through fiscal 2027.
2. Continued HBM4 qualification and share gains at hyperscale and AI-accelerator customers.
3. Fiscal Q4 landing near the $50.0B guide at ~86% gross margin.
4. Evidence that data-center demand stays robust while supply additions remain disciplined.
5. Renewed market focus on earnings revisions after the sector-rotation consolidation.

## Research Inputs

- Thesis text supplied by Bill 2026-08-07 — authorship `[BILL]` to confirm.
- **All company figures independently verified this session** against Micron's fiscal Q3 2026
  release and Q4 guidance. Verified: $41.46B revenue, 84.6% GAAP / 84.9% non-GAAP gross
  margin, $33.68B operating income, $50.0B ±$1.0B Q4 guide at ~86% GM, $25B data-center
  revenue. **No overstatements found** — unusual for this session, and worth noting.
- **Added beyond the supplied text:** the $35.69B consensus figure the revenue beat, the
  $6.55B consensus beat on the Q4 guide, the 14.6% share move on the print, the HBM
  sold-out/50–67% supply-gap detail, HBM3E and HBM4 booked through 2027, the >$1B HBM4
  revenue and 2x-HBM3E ramp, and the Cloud Memory / Core Data Center segment splits.
- One source in the supplied text was a YouTube link for the Q4 guide; replaced with the
  company release and coverage below.
- Sources:
  [Micron Q3 FY26 release](https://investors.micron.com/news-releases/news-release-details/micron-technology-inc-reports-record-results-third-quarter),
  [Q3 FY26 slides coverage](https://www.investing.com/news/company-news/micron-q3-fy2026-slides-record-415b-revenue-85-margins-93CH-4759286),
  [Futurum on HBM/LPDRAM](https://futurumgroup.com/insights/micron-q3-fy-2026-hbm-and-lpdram-drive-the-next-phase-of-ai-memory-growth/),
  [memory selloff context](https://www.tradingkey.com/analysis/stocks/more/262081187-skhynix-samsung-semiconductor-stock-rout-tradingkey).

## Review Log

- 2026-08-07: Position opened, funded by partial COF sale (COF sold above its own recorded
  `price_trim_above: 175.00`). Thesis drafted from Bill-supplied text; all company figures
  independently verified, none overstated.
- 2026-08-07: Style set **GARP / 9.0% ceiling** by Bill. Raised the resulting taxonomy gap —
  MU (GARP 9.0) and SKHY (THEME 3.0) are the same bet under different ceilings, so combined
  memory exposure is unmonitored by the ceiling check. Resolution options recorded under
  Style; neither selected yet.
- 2026-08-07: Position filled in — 5 sh, $4,378.25 cost basis ($875.65 avg), 0.72% seed.
  Combined direct memory exposure with SKHY is 1.59%.
- Outstanding `[BILL]`: the combined-memory ceiling decision, price triggers, priority, exit
  conditions, source authorship, and the SKHY cross-reference on the contracted-HBM condition.

<!-- region:position_state -->
**Current Allocation:** 1.30%
**Cost Basis:** $7,845.41
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** GARP
**Size Ceiling:** 9.00%
**Drift:** -7.70%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-08-07: Buy 4.0 @ $866.79
- 2026-08-07: Buy 5.0 @ $875.65
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-08-08 09:05: Auto-sync allocation 1.30%, drift -7.70%
<!-- endregion:change_log -->
