---
ticker: VRT
style: THEME
framework_preference: thematic_specialist_v1, lynch_garp_v1
entry_date: 2026-05
last_reviewed: '2026-09-02'
current_allocation: 2.92%
cost_basis: 19854.970000001602
time_horizon: 2 to 4 years
triggers:
  trigger_type: fwd_pe
  fwd_pe_add_below: 28              # add on cyclical / multiple-compression pullbacks
  fwd_pe_trim_above: 50             # trim if multiple gets into peak-AI-infrastructure-mania territory
  fwd_pe_historical_median:
  price_add_below:                  # build to target weight on volatility, not on a specific level yet
  price_trim_above:                 # set once position is sized; thematic, not level-driven yet
  discount_from_52w_high_add: 0.20  # add on 20%+ drawdowns from highs absent structural news
  revenue_growth_floor_pct: 15
  operating_margin_floor_pct:
  style_size_ceiling_pct: 3.0       # thematic single names cap lower than GARP core
drawdown_tolerance_pct: 0.35
panic_buy_trigger_drawdown_pct: 0.25
add_triggers_suspended: true
pattern:
  name: accumulate_on_decline
  established: '2026-08-19'
  note: Accumulated because "I like the company and the price was dropping — it 
    got big, same as COF."
---
# VRT (Vertiv) — Investment Thesis (New 2026-05-18)

## Style
Thematic Specialist / AI Infrastructure Picks-and-Shovels

## Origin
Stephanie Link recommendation. Consistent with my AI buildout thesis. Initiated as a small position to participate in the data center capex cycle without taking direct chip-cycle risk.

## Core Thesis: The Datacenter Power-and-Cooling Buildout

Vertiv builds the physical infrastructure that AI datacenters cannot exist without: power delivery, thermal management, busways, switchgear, liquid cooling, rack-level cooling, and the integrated systems that keep a 50MW AI facility from melting itself.

The thesis is not about Vertiv winning a specific contract or designing a specific chip. It's that **AI datacenter capex is being committed at unprecedented scale by hyperscalers, neoclouds, and increasingly by sovereigns**, and every one of those buildouts needs the kind of integrated power-and-thermal infrastructure that Vertiv specializes in.

The picks-and-shovels framing matters because:

- I don't have to pick which AI chip wins (CUDA vs. ROCm vs. custom silicon).
- I don't have to pick which hyperscaler wins (AWS vs. Azure vs. GCP vs. neoclouds).
- I don't have to pick which model wins.
- I just have to be right that the datacenter buildout continues.

That's a much higher-confidence bet than picking individual AI winners at this stage of the cycle.

## Why This Fits My Portfolio

- **Diversifies AI exposure away from mega-cap tech.** My mega-tech/AI complex is at 30% even after the rebalance. VRT gives me AI cycle exposure that isn't correlated with GOOG/AMZN/NVDA/MSFT day-to-day.
- **Industrial/infrastructure characteristic.** VRT is more of an industrial than a tech name — different earnings sensitivity, different multiple dynamics, different drawdown behavior in tech-led selloffs.
- **Real revenue, real margins, real backlog.** This isn't a story stock. The thesis is grounded in visible order flow and capacity expansion.

## Position Sizing Plan

Current allocation 1.20% (30 shares, cost basis $9,693.23, avg $323.11). This remains starter size. The plan:

- **Target weight: 2.0-2.5%** at full sizing.
- **Build path:** add on broader market pullbacks or AI-infrastructure-specific de-rating. Don't chase strength.
- **Build path GATED as of 2026-07-29.** The drawdown add-triggers below are firing (see Scaling State) but are suspended pending resolution of the management-execution question. Price weakness alone is not a sufficient add signal for this position.
- **Hard cap: 3.0%** — thematic single names get a lower cap than GARP-core positions because the thesis is more cycle-dependent.
- **Position sizing discipline:** at least three legs into the position; if I can't get to target weight on volatility, the position stays small.

## Bull Case Drivers

- **Hyperscaler capex sustained at $300B+ annually** through at least 2027. VRT is in the supply chain for a meaningful fraction of that.
- **Liquid cooling adoption accelerating** — AI rack densities (60-120kW per rack and rising) make air cooling structurally inadequate. Liquid cooling is becoming standard, and VRT has invested heavily in this product line.
- **Backlog visibility extends 12-18 months out** — gives me higher-confidence revenue forecasting than typical industrial cyclicals.
- **Sovereign AI buildouts** (Middle East, EU) add a second leg of demand beyond US hyperscalers.

## Key Risks

- **Cyclical capex risk** — if hyperscaler capex disappoints in any given quarter, the stock gets re-rated hard. Industrial multiples compress fast on growth deceleration.
- **Margin pressure from competition** — Schneider Electric, Eaton, Delta, and Chinese suppliers all compete in adjacent segments. Pricing power is real but not unlimited.
- **Customer concentration** — a few large hyperscalers drive a meaningful share of revenue. Loss of one would matter.
- **Multiple compression risk** — currently trading at a meaningful premium to industrial peers on AI optionality. If AI narrative cools, the multiple compresses even if fundamentals are intact.

- **Management execution and guidance credibility (added 2026-07-29).** This is the risk that is actually biting and it was absent from this file through the first three months of the position. Vertiv is being asked to execute at a project scale it has not executed at before — the Q2 2026 shortfall was concentrated in the Americas (~$106M) and management attributed it to supply-chain congestion and "multi-phased project execution as AI infrastructure deployments become larger and more complex." That language cuts two ways: it is either an honest description of lumpy timing, or the early signature of an operator that has outgrown its delivery capability. The distinguishing evidence is whether deferred revenue actually converts. Compounding the concern: management raised the FY revenue guide *while* missing the quarter, which back-loads the year into a Q4 that cannot be verified until February. **I do not currently have confidence in this management team. That is a position-level judgment, not a company-quality judgment, and it is the binding constraint on sizing.**

- **Multiple leaves no room for volume misses.** Entered Q2 at roughly 49x forward with the stock up ~66% YTD. At that multiple the beat came from operating leverage (margin +2.7pts YoY) rather than volume, and volume is what the AI-infrastructure thesis is priced on. Revenue misses de-rate this name regardless of margin performance. Beta ~2.0; the 52-week range of $118.70-$379.94 is the honest picture of the dispersion here.

## Hard Exit Conditions

1. Hyperscaler capex guidance comes down 20%+ in aggregate and stays down — the core demand driver is breaking.
2. Margin compression sustained over 3+ quarters indicating loss of pricing power.
3. Loss of a top-3 hyperscaler customer to a competitor.
4. Multiple expands past 60x forward EPS — at that point the risk-reward is asymmetric to the downside even if the thesis is right.

5. **Backlog conversion fails (added 2026-07-29).** Any one of the following is a thesis break, not a bad quarter:
   - Q3 2026 revenue lands below the $3.75B guided midpoint. Management set this number one quarter after missing; missing their own fresh guide is a credibility event.
   - Backlog declines sequentially from the ~$15B base, or management stops disclosing it at the same granularity.
   - FY 2026 revenue guidance is revised down from ~$14B, or the Q4 implied ramp is walked back.
   - Management quantifies a cancellation rate, or declines to answer the question when asked directly.
   - The Americas shortfall repeats in Q3 — one region missing twice is not congestion, it is a delivery problem.

## Scaling State

next_step: hold — ceiling breach reconciled (Bill, 2026-08-19): the size run-up past the 3.00% ceiling was a deliberate accumulation, not an accidental add through the "closed" event-gate. Rationale as stated: "VRT was accumulated because I like the company and the price was dropping — it got big, same as COF." Standing risk-tolerance rationale moved to vault/doctrine.md (`no_withdrawal_need`, established 2026-08-19). Not trimmed solely to close the ceiling drift.

*(Superseded 2026-08-19 — kept for record: [BILL] Position is now 68 shares / 3.14% — in breach of the 3.00% ceiling** (bundle 6c531c97, 2026-08-07). The figures above (30 shares, 1.20%, "nominal headroom") are stale: the position more than doubled between the 2026-07-29 review and this bundle despite the add path being described as closed pending backlog-conversion evidence. Flag for Bill to reconcile — was this a deliberate add through the "closed" gate, and does the position need to be trimmed back toward the 2.0-2.5% target / 3.00% ceiling? Not resolved here; no new scaling state inferred.)*

The file's own drawdown triggers are firing right now and are being deliberately overridden: `discount_from_52w_high_add: 0.20` and `panic_buy_trigger_drawdown_pct: 0.25` are both satisfied at current levels (roughly -36% from the $379.94 52-week high). Those triggers were written for a de-rating in an intact thesis. What is in front of me is a possible execution problem, and averaging down into an unresolved management question is the one move this framework has no answer for. **The add trigger is now event-based, not price-based: a quarter in which backlog converts on schedule.** Until then, price weakness is not a signal.

Drawdown tolerance of 35% from cost is not yet breached (~-7% at $271 against $291.99 avg). That tolerance stands, but it is a tolerance, not a target — it does not obligate me to hold to it if the Q3 evidence goes the wrong way.

Style note: this is THEME — market position over company quality. That tag is correct and it is the reason the position stays small. "I love the products, I am unsure about the operator" is precisely a thematic-specialist position and precisely not a dip-buying candidate; dip-buying belongs to the FUND sleeve and requires a durable business I trust, which by my own assessment this is not right now.

## Rotation Priority

priority: **high** — elevated from medium on 2026-07-29.

This position is the weakest leg of a physical-AI-infrastructure sleeve (VST 3.55%, IFRA 1.90%, ETN 1.64%, VRT 3.14% = 10.23% of book) whose theme I still believe in — sleeve math corrected 2026-08-07 against bundle 6c531c97 (prior figures were stale). If capital is rotated out of VRT it should stay inside that sleeve rather than leaving the theme. ETN is the natural destination: same power-infrastructure exposure, a business I rate more highly, not substantially identical for wash-sale purposes, and it currently carries ~1.36% of headroom to its own 3.00% THEME ceiling. [BILL — VST's own headroom figure (previously cited as 0.37%) needs re-check: at 3.55% it now appears to be over its own 3.00% THEME ceiling, which may rule it out as a rotation destination.]

Tax posture if rotated: unrealized loss is roughly -$1,200 at $271.00 against a $291.99 avg cost across 58 shares. All lots are **short-term** (oldest: 2026-05-27, 84 days held as of 2026-08-19). Wash-sale constraint: the most recent VRT purchases are 2026-08-04 (33 shares) and 2026-07-31 (5 shares) — both within the 30-day look-back window. A sale today would trigger wash-sale adjustments on those 38 shares unless no VRT repurchase occurs within the forward 30 days (through 2026-09-18). The pre-July lots (2026-05-27 through 2026-06-11, 20 shares) are outside the look-back and would realize clean short-term losses.

## Review Log
- 2026-08-24: Standing rationale for this breach acceptance moved to `vault/doctrine.md` (`no_withdrawal_need`, established 2026-08-19). Text unchanged; single-sourced.
- 2026-08-24: `pattern: accumulate_on_decline` tagged from 2026-08-19 next_step rationale (company liked; price dropping).

- **2026-05-18:** Initiated as a starter position at 0.56% on a Stephanie Link recommendation. Funded from ETN gains (sold 7 @ $427.90 on 05-04 and 10 @ $403.68 on 05-08, ~$7,032 of proceeds). Built across three-plus legs to 30 shares at a $323.11 average.
- **2026-08-19 (Bill):** Resolves the 2026-08-07 open flag on how the position doubled past the ceiling. It was deliberate: "I like the company and the price was dropping, so it got big — same as COF." Recorded as the actual scaling behavior rather than an inferred execution error. This sits alongside, not in place of, the file's own management-confidence caveat under Scaling State — both can be true: he added on price weakness because he likes the business, while remaining unconvinced on this particular operator's execution.
- **2026-07-29 — Q2 2026 print and first material thesis review.** Revenue $3.27B vs. ~$3.39B consensus, a 3.4% miss but +24.1% YoY. Adjusted EPS $1.52 vs. $1.43, a 6.4% beat. FY26 adjusted EPS guidance raised to ~$6.70 midpoint from $6.30-6.40; FY revenue guide lifted to ~$14B from $13.75B. Q3 revenue guided to $3.75B midpoint, slightly above estimates. Operating margin 19.5%, up 2.7 points YoY. Shortfall concentrated in the Americas at roughly $106M. Stock traded down ~10.4% to roughly $243 on the print, following a 6.27% decline to $269.56 the prior session.
  - **Assessment:** demand is not the problem — backlog ~$15B, revenue +24% YoY, margins expanding, Q3 guided above consensus. The problem is that the FY raise now depends on a very large Q4 that no one can verify for six months, delivered by a management team whose first test at this project scale produced a regional miss. **The decisive near-term check is arithmetic: FY guide minus Q1 actual minus Q2 actual ($3.27B) minus Q3 guide ($3.75B) = implied Q4.** Near $4.0B is a normal seasonal step and the raise is credible. At $4.4B or above, the guide is carrying the year on an unverifiable quarter.
  - **Actions:** added management-execution risk (was absent from this file). Added Hard Exit Condition 5 on backlog conversion. Suspended price-based add triggers in favor of an event-based trigger. Raised rotation priority to high. Corrected stale allocation (file read 0.56%; actual 1.20%).
  - **Not changed:** the core picks-and-shovels thesis. Nothing in this print contradicts the claim that AI datacenter buildout continues and needs integrated power and thermal infrastructure. What changed is my confidence that this particular operator captures it at this particular multiple.
- **Open items:** (1) compute implied Q4 from the Q1 actual; (2) listen to the 11:00 ET call for orders growth, backlog conversion and cancellation-rate commentary — if backlog grew against the $15B base and orders held, the miss is logistics; if backlog flattened, the Americas gap is demand and this file needs rewriting rather than defending; (3) populate Trim and Add price cells for VRT in the portfolio Sheet, which are currently blank, so the morning brief reports proximity for this position.
- **2026-08-07:** `next_step` and the Rotation Priority sleeve-math paragraph corrected in-session (68 shares / 3.14%, ceiling breach flagged `[BILL]`; sleeve total updated to 10.23%) ahead of `prompts/consolidate_and_thesis_repair_2026-08-07.md` Step 4, which specified the same edits. Edited directly rather than through the archive-before-overwrite convention; `VRT_thesis.md.bak` backfilled retroactively from pre-edit content to close that gap.
- 2026-08-09: trigger_type set explicit: fwd_pe (argued exception to the THEME default of ceiling_only -- existing 28/50 band is a genuine, fully-populated anchor). See prompts/trigger_types_2026-08-09.md.

<!-- region:position_state -->
**Current Allocation:** 2.92%
**Cost Basis:** $19,854.97
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** THEME
**Size Ceiling:** 3.00%
**Drift:** -0.08%
<!-- endregion:sizing -->

<!-- region:change_log -->
2026-09-02 11:36: Auto-sync allocation 2.92%, drift -0.08%
<!-- endregion:change_log -->

<!-- region:transaction_log -->
- 2026-08-04: Buy 5.0 @ $270.45
- 2026-08-04: Buy 15.0 @ $272.00
- 2026-08-04: Buy 3.0 @ $270.13
- 2026-08-04: Buy 10.0 @ $270.96
- 2026-07-31: Buy 5.0 @ $241.90
- 2026-06-11: Buy 5.0 @ $290.38
- 2026-06-01: Buy 5.0 @ $319.50
- 2026-05-27: Buy 10.0 @ $317.00
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->
