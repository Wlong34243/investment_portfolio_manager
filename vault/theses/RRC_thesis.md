---
ticker: RRC
style: THEME
framework_preference:
entry_date: '2026-08-07'
last_reviewed: '2026-09-02'
cost_basis: 7439.530000000021
current_allocation: 1.35%
triggers:
  trigger_type: price_to_book
  pb_trim_above: 2.36
  pb_add_below: 2.05
  entry_price: 38.66
  seed_position_weight: 0.61%
  price_add_below:                  # [BILL] — not set at entry
  price_trim_above:                 # [BILL] — not set at entry
  style_size_ceiling_pct: 3.0       # THEME default; single-name thematic cap
---
# RRC — Investment Thesis

**STATUS: Drafted 2026-08-07 at entry; selection rationale added same day.** Built from
sourced Q2-2026 company data plus the gas-deliverability research under Research Inputs, and
from a comparative EXE-vs-RRC analysis Bill supplied on 2026-08-07. **`next_step`, `priority`
and both price triggers remain `[BILL]`.**

> **Provenance note.** The comparative analysis was supplied by Bill but its authorship is not
> recorded — it may be his own work or a third-party research output he is citing. Its
> *reasoning and figures* are transcribed below; its ranking language ("I would favor RRC,"
> "choose RRC if...") is deliberately **not** carried into this file, per the project rule
> against buy/sell recommendations in thesis documents. **[BILL] — confirm authorship so the
> Research Inputs attribution is correct.**

## Style

THEME — Thematic Specialists. This is a macro expression: buying a position in a structural
supply/deliverability constraint, not an assertion that Range is the highest-quality operator
in its basin. Same classification logic applied to PWR on 2026-08-07. Ceiling 3.0%.

## Core Thesis

The bottleneck in US natural gas is **deliverability, not geology.** The country is not
running out of gas; it is running out of ways to move it. Interstate pipeline permitting has
been effectively blocked for most of a decade — Mountain Valley (303 mi, in service June 2024
after ten years of litigation) is the only major new interstate line of the period, and 2022
saw the least interstate capacity added since records began in 1995. Into that fixed takeaway
system arrive two demand sources that are contractually hard to unwind: LNG exports, where
the US is committed to more than a third of global supply into the early 2030s, and
incremental gas-fired load from AI data centers.

**Why RRC and not EXE — the selection rationale.** Both express the constraint. They were
weighed on five axes and RRC was chosen on four of them:

| Factor | EXE | RRC | Basis for choice |
|---|---|---|---|
| Q2-26 production | 7.48 Bcfe/d, 92% gas | 2.30 Bcfe/d, ~67% gas | EXE has scale; RRC has mix |
| Commodity mix | primarily dry gas | **>30% liquids, NGL-heavy** | RRC — resilience to a weak dry-gas tape |
| Q2-26 realized price | $3.12/Mcfe incl. realized derivatives | **$3.53/Mcfe after hedges** | RRC — the mix shows up in realizations |
| Net debt | $3.1B, ~0.5x net debt/EBITDAX | **$881M** | RRC — lower absolute financial risk |
| 2026 capital budget | $2.75–2.95B | **$650–700M** | RRC — far lower capital intensity per unit of growth |
| Basin | Haynesville + NE/SW Appalachia | Appalachia/Marcellus concentrated | EXE — diversification |
| Execution risk | Twin Eagle acquisition and marketing integration | organic | RRC — no integration risk |

The trade accepted is **basin concentration and smaller scale in exchange for commodity-mix
resilience, a materially lighter balance sheet, and capital efficiency.** Appalachia is the
basin *most* stranded by the permitting blockage, which cuts both ways: constrained takeaway
compresses realized in-basin prices, but a producer already inside the constraint captures
regional price recovery without needing new pipe. EXE's Haynesville barrels sitting next to
Gulf Coast LNG demand on short haul is the opposite bet. **That basin exposure is the single
largest risk in this position and it was taken knowingly.**

## Entry Context

Opened 2026-08-07: **95 shares @ $38.66, cost basis $3,672.70**, seed weight ~0.61% of book.

Reference point, not a valuation claim: Range repurchased **2.0M shares during Q2 2026 at
roughly $39.18** — the entry is modestly below the company's own average repurchase price for
the quarter.

**Funded by a partial QQQM sale — this is a rotation and the implicit bet should be read as
one.** Capital moved out of broad AI/large-cap tech beta and into the physical energy input
that same buildout depends on. Selling the presumed winners of the AI trade to buy its
constraint is a different bet from simply adding energy exposure. QQQM carried an unrealized
gain (+5.09% at bundle `6c531c97`), so the sale realizes gain — **[BILL] verify lot selection
and short- vs long-term holding period; the bundle does not carry holding periods.**

Entered as a seed, consistent with small-step scaling. No adds contemplated at entry.

## Bull Case

- **Inventory duration is the differentiator.** 30+ years of Marcellus inventory, with
  management stating production could double and still leave 15+ years. Where the thesis is
  "the constraint persists for years," inventory life is the asset that matters most.
- **The liquids mix is the practical edge over a dry-gas peer.** ~67% gas / >30% liquids
  produced a **Q2-26 realized $3.53/Mcfe after hedges against EXE's $3.12/Mcfe** including
  realized derivatives. NGLs realized a **$3.49/bbl premium to Mont Belvieu in Q2**, driven by
  international pricing through the export program. *Note the guidance figure is lower:
  full-year 2026 NGL guidance is a **$2.00–2.50/bbl premium**, raised from $1.25–2.50. Q2's
  $3.49 is an actual, not a run-rate — do not model the quarter as the year.*
- **Balance sheet does not force the outcome.** Net debt **$881M** at Q2-26, ~0.6x
  Debt/EBITDAX, after retiring/refinancing higher-cost notes earlier in 2026. A producer that
  does not have to sell into weakness can wait for the constraint to bind.
- **Capital efficiency is the cleanest contrast with the alternative.** 2026 budget of
  **$650–700M** against guidance of 2.35–2.40 Bcfe/d, growing to 2.5 Bcfe/d exiting 2026 and
  2.6 Bcfe/d in 2027 — supported by DUC inventory. EXE's comparable budget is $2.75–2.95B.
- **Free cash generation at current strip.** ~14% FCF yield per the company's Q2-26
  materials (company figure, not independently recomputed).
- **Contracted long-dated demand, partially confirmed.** A **ten-year agreement for 75 MMcf/d
  at a premium to Midwest regional prices**, serviced from previously announced transportation
  capacity additions beginning mid-2026, contingent on facility construction completing late
  2027. ⚠️ **The end user is not disclosed in public reporting. Do not record this as a
  data-center contract** — the source characterizing it as a "Midwest power contract" is
  making an attribution the company filings do not support. Treated here as contracted
  long-dated volume at a premium, which is what is actually evidenced.
- **Capital returned while waiting.** $78M repurchased in Q2, $105M in H1 2026, with **$1.4B
  of authorization remaining.** Dividend is $0.10/quarter — small, and not the reason to own it.

## Key Risks

- **The demand case underneath this thesis is overstated at source.** The podcast framing that
  surfaced the idea used 5 Bcf/d base / 12–15 Bcf/d upside for AI gas demand. Published
  forecasts are materially lower: East Daley 4.2–6.1 Bcf/d by 2030, S&P Global base 3 with
  upside approaching 6. **The upside case as originally stated runs 2–2.5x the highest
  published figure.** The thesis survives on published numbers — it is simply less dramatic
  and slower. Re-underwrite on the published range, never the podcast range.
- **An extended sub-$3 Henry Hub tape is the shared risk with any gas producer.** RRC is
  partially insulated by the liquids mix, but its gathering, processing and transport cost
  base is substantial and does not shrink when prices fall. Partial insulation is not a hedge.
- **Basin exposure is the risk and the thesis simultaneously.** If the squeeze expresses as
  takeaway discounts rather than regional price strength, Appalachian producers absorb it.
  This was chosen knowingly — see Core Thesis.
- **The growth guide is the thing to watch, not the gas price.** 2.6 Bcfe/d in 2027 on a
  $650–700M budget is the whole capital-efficiency argument. The open question is whether that
  growth arrives without sacrificing the historical capital discipline. **If capex creeps to
  fund the volume target, the reason this was chosen over EXE has gone.**
- **The 75 MMcf/d agreement is contingent.** It depends on third-party facility construction
  completing late 2027. Contingent contracted volume is not delivered volume.
- **Timing risk is long-dated and unfalsifiable near-term.** The constraint thesis points at
  2028–2030 — far enough out that nothing between now and then confirms or refutes it, which
  invites both premature adds and premature exits.
- **Permitting is a policy variable, not a physical one.** The constraint exists because
  approvals stopped. A policy reversal restoring interstate construction removes the thesis
  with no change in gas demand.
- **Scale and liquidity.** ~$9.55B market cap / ~$10.53B EV — smaller and less liquid than the
  alternative considered, with correspondingly higher single-name volatility.

## Position Sizing & Role

Seed at 0.61% against a 3.0% THEME ceiling. Role is a **direct expression of the gas
deliverability constraint** — distinct from, and not a substitute for, the existing energy
sleeve:

- **XOM (3.12%)** — integrated, crude-weighted, different commodity exposure.
- **ET (1.27%)** — midstream. ET is the *toll road* on this constraint; RRC is the *molecule*.
  Related bet, different point in the chain. ET's thesis was extended 2026-08-07 with the
  domestic AI/data-center demand driver from the same research.
- **Energy sleeve becomes ~5.0% of book** with RRC added. **[BILL]** — this makes one macro
  call expressed three ways (XOM, ET, RRC); confirm that concentration is intended.

## Scaling State

next_step: **[BILL]** — not stated at entry. A 0.61% seed against a 3.0% ceiling leaves
substantial headroom, but no add path or condition has been recorded. If the intent is "seed
and wait for evidence," name the evidence — the capital-efficiency test in Key Risks (2.6
Bcfe/d in 2027 on an unchanged budget) is the obvious candidate.

## Rotation Priority

priority: **[BILL]** — not stated at entry.

## Exit Conditions

- **[BILL]** — none recorded at entry. Candidates implied by the thesis, to accept, edit or reject:
  - **Capital discipline breaks:** the 2027 volume target is met by raising the budget
    materially above $650–700M. This is the condition that voids the selection rationale.
  - Interstate pipeline permitting materially reopens, restoring Appalachian takeaway.
  - Inventory-duration advantage erodes — downward reserve revision, or peers closing the gap.
  - Net debt rises structurally off the ~$881M base, removing the ability to wait.
  - The AI gas-demand driver fails to appear in published forecasts by the 2028 window.

## Research Inputs

Assembled 2026-08-07. **Research, not thesis** — recorded so the reasoning is traceable.

- Deliverability framing originates with Matthew Smith (Chronometer Partners) on *Invest Like
  the Best*, ingested 2026-07-26 as
  `data/podcast_summaries/2026-07-26_Invest_Like_The_Best_Why_Natural_Gas_Will_Be_AIs_Next_Great_Shortage.md`,
  and restated in the 2026-08-07 Spotify aggregate. **Count as one source, not two** — see the
  corpus-integrity section of
  `data/podcast_summaries/verification/allocation-2026-08-07_VERIFIED_2026-08-07.md`.
  Two claims from that source came back overstated in verification (the 12–15 Bcf/d upside
  case; the "only pipeline in twelve years" framing) and are carried here corrected only.
- Comparative EXE/RRC analysis supplied by Bill 2026-08-07 — authorship `[BILL]` to confirm.
  Figures transcribed; ranking language excluded per the no-recommendations rule.
- Company figures: Range Q2-2026 release and July 2026 corporate presentation
  ([Q2 release](https://ir.rangeresources.com/news-releases/news-release-details/range-announces-second-quarter-2026-results),
  [Q2 slides summary](https://www.investing.com/news/company-news/range-resources-q2-2026-slides-30-years-inventory-14-fcf-yield-93CH-4806347));
  Expand Q2-2026 release
  ([globenewswire](https://www.globenewswire.com/news-release/2026/07/28/3334689/0/en/expand-energy-corporation-reports-second-quarter-2026-results.html)).
  The 75 MMcf/d agreement detail is from Range's 8-K
  ([SEC](https://www.sec.gov/Archives/edgar/data/315852/000119312526069413/rrc-ex99_1.htm)).
- **Verified this session:** the $3.49/bbl NGL figure is a **Q2 actual**, while $2.00–2.50/bbl
  is **full-year guidance** — both correct, different things, and previously conflated. The
  Midwest agreement's end user is **not** disclosed; the data-center attribution was not
  supported by filings.

## Review Log

- 2026-08-07: Position opened, 95 sh @ $38.66 ($3,672.70), funded by partial QQQM sale.
  Thesis drafted from session research. Style set THEME / 3.0% by analogy to the PWR
  classification the same day. Price triggers left unset.
- 2026-08-07: Selection rationale (EXE vs RRC) added from Bill-supplied comparative analysis;
  Bull Case and Key Risks re-cut around commodity mix, realized pricing, capital intensity and
  the 75 MMcf/d agreement. Corrected two figures in the process — NGL premium (Q2 actual vs
  full-year guidance) and the Midwest agreement's unconfirmed end user. `next_step`,
  `priority`, exit conditions and source authorship remain `[BILL]`.
- 2026-08-09: trigger_type: price_to_book (cyclical override -- gas E&P commodity, GARP-style multiple-based triggers fail on cyclicals). Band from FY2022-2025 annual book value (price ÷ book equity/share at each fiscal year-end, n=4 annual observations, tight 1.7x range 1.74-3.02): pb_add_below=2.05 (~p25), pb_trim_above=2.36 (~p75). Live current P/B 1.90 sits near the add zone. See prompts/trigger_types_2026-08-09.md.

<!-- region:position_state -->
**Current Allocation:** 1.35%
**Cost Basis:** $7,439.53
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** THEME
**Size Ceiling:** 3.00%
**Drift:** -1.65%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-09-01: Buy 15.0 @ $41.79
- 2026-08-31: Buy 10.0 @ $41.42
- 2026-08-10: Buy 10.0 @ $39.81
- 2026-08-10: Buy 10.0 @ $39.81
- 2026-08-07: Buy 50.0 @ $38.62
- 2026-08-07: Buy 95.0 @ $38.65
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-09-02 11:36: Auto-sync allocation 1.35%, drift -1.65%
<!-- endregion:change_log -->
