---
ticker: VRT
style: THEME
framework_preference: thematic_specialist_v1, lynch_garp_v1
entry_date: 2026-05
last_reviewed: '2026-08-03'
current_allocation: 0.94%
cost_basis: 10902.73
time_horizon: 2 to 4 years
triggers:
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
panic_buy_trigger_drawdown_pct: 0.25   # SUSPENDED 2026-07-29 — see Scaling State
add_triggers_suspended: true           # drawdown-based adds gated on Q3 backlog conversion
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

next_step: **Hold 30 shares. No adds.** Position is 1.20% against a 2.0-2.5% target and a 3.00% ceiling, so there is nominal headroom, but the add path is closed pending evidence, not price.

The file's own drawdown triggers are firing right now and are being deliberately overridden: `discount_from_52w_high_add: 0.20` and `panic_buy_trigger_drawdown_pct: 0.25` are both satisfied at current levels (roughly -36% from the $379.94 52-week high). Those triggers were written for a de-rating in an intact thesis. What is in front of me is a possible execution problem, and averaging down into an unresolved management question is the one move this framework has no answer for. **The add trigger is now event-based, not price-based: a quarter in which backlog converts on schedule.** Until then, price weakness is not a signal.

Drawdown tolerance of 35% from cost is not yet breached (~-25% at $243 against $323.11 avg). That tolerance stands, but it is a tolerance, not a target — it does not obligate me to hold to it if the Q3 evidence goes the wrong way.

Style note: this is THEME — market position over company quality. That tag is correct and it is the reason the position stays small. "I love the products, I am unsure about the operator" is precisely a thematic-specialist position and precisely not a dip-buying candidate; dip-buying belongs to the FUND sleeve and requires a durable business I trust, which by my own assessment this is not right now.

## Rotation Priority

priority: **high** — elevated from medium on 2026-07-29.

This position is the weakest leg of a physical-AI-infrastructure sleeve (VST 2.51%, IFRA 1.74%, ETN 1.41%, VRT 1.20% = 6.86% of book) whose theme I still believe in. If capital is rotated out of VRT it should stay inside that sleeve rather than leaving the theme. ETN is the natural destination: same power-infrastructure exposure, a business I rate more highly, not substantially identical for wash-sale purposes, and it currently carries ~1.6% of headroom to its own 3.00% THEME ceiling versus VST's 0.37%.

Tax posture if rotated: unrealized loss is roughly -$2,400 at $243. All lots in the transaction log were acquired 2026-05 through 2026-06, which implies **short-term** treatment — the more valuable offset, since it shelters short-term gains at ordinary rates. Verify holding periods and the ~10 shares predating 2026-05-27 in Schwab before acting; this file's transaction log shows only the five most recent entries. Wash-sale window is clean: no VRT purchase since 2026-06-11, so only the forward 30 days would constrain a re-entry.

## Review Log

- **2026-05-18:** Initiated as a starter position at 0.56% on a Stephanie Link recommendation. Funded from ETN gains (sold 7 @ $427.90 on 05-04 and 10 @ $403.68 on 05-08, ~$7,032 of proceeds). Built across three-plus legs to 30 shares at a $323.11 average.
- **2026-07-29 — Q2 2026 print and first material thesis review.** Revenue $3.27B vs. ~$3.39B consensus, a 3.4% miss but +24.1% YoY. Adjusted EPS $1.52 vs. $1.43, a 6.4% beat. FY26 adjusted EPS guidance raised to ~$6.70 midpoint from $6.30-6.40; FY revenue guide lifted to ~$14B from $13.75B. Q3 revenue guided to $3.75B midpoint, slightly above estimates. Operating margin 19.5%, up 2.7 points YoY. Shortfall concentrated in the Americas at roughly $106M. Stock traded down ~10.4% to roughly $243 on the print, following a 6.27% decline to $269.56 the prior session.
  - **Assessment:** demand is not the problem — backlog ~$15B, revenue +24% YoY, margins expanding, Q3 guided above consensus. The problem is that the FY raise now depends on a very large Q4 that no one can verify for six months, delivered by a management team whose first test at this project scale produced a regional miss. **The decisive near-term check is arithmetic: FY guide minus Q1 actual minus Q2 actual ($3.27B) minus Q3 guide ($3.75B) = implied Q4.** Near $4.0B is a normal seasonal step and the raise is credible. At $4.4B or above, the guide is carrying the year on an unverifiable quarter.
  - **Actions:** added management-execution risk (was absent from this file). Added Hard Exit Condition 5 on backlog conversion. Suspended price-based add triggers in favor of an event-based trigger. Raised rotation priority to high. Corrected stale allocation (file read 0.56%; actual 1.20%).
  - **Not changed:** the core picks-and-shovels thesis. Nothing in this print contradicts the claim that AI datacenter buildout continues and needs integrated power and thermal infrastructure. What changed is my confidence that this particular operator captures it at this particular multiple.
- **Open items:** (1) compute implied Q4 from the Q1 actual; (2) listen to the 11:00 ET call for orders growth, backlog conversion and cancellation-rate commentary — if backlog grew against the $15B base and orders held, the miss is logistics; if backlog flattened, the Americas gap is demand and this file needs rewriting rather than defending; (3) populate Trim and Add price cells for VRT in the portfolio Sheet, which are currently blank, so the morning brief reports proximity for this position.

<!-- region:position_state -->
**Current Allocation:** 0.94%
**Cost Basis:** $10,902.73
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** THEME
**Size Ceiling:** 3.00%
**Drift:** -2.06%
<!-- endregion:sizing -->

<!-- region:change_log -->
2026-08-03 09:36: Auto-sync allocation 0.94%, drift -2.06%
<!-- endregion:change_log -->

<!-- region:transaction_log -->
- 2026-07-31: Buy 5.0 @ $241.90
- 2026-06-11: Buy 5.0 @ $290.38
- 2026-06-01: Buy 5.0 @ $319.50
- 2026-05-27: Buy 10.0 @ $317.00
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->
