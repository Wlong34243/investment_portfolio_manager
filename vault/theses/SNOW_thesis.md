---
ticker: SNOW
style: THEME
framework_preference: thematic_specialist_v1
entry_date: '2026-07-31'
last_reviewed: '2026-08-03'
current_allocation: 1.01%
cost_basis: 8930.3
time_horizon: TBD - see open items
triggers:
  entry_price:
  price_add_below:
  price_trim_above:
  style_size_ceiling_pct: 3.0
drawdown_tolerance_pct:
---
# SNOW (Snowflake) — Investment Thesis

**STATUS: DRAFT, created 2026-07-31 same day as entry to unblock the briefing export.
Sections marked [CONFIRM] are transcribed from Bill's stated reasoning and need his
sign-off. Sections marked [BILL] require input only he can supply. Cost basis and
allocation are placeholders (0.00) until the trade clears Schwab sync — do not treat
those figures as real until the next `vault sync` overwrites them.**

## Style
Thematic Specialist / AI Data Layer [CONFIRM — see note]

Style note: assigned THEME (3.0% ceiling) rather than GARP. GARP in this portfolio means
"undervalued companies with strong product/market understanding," and SNOW does not
clear the undervalued half of that test — consensus analyst target sits roughly at the
current price (see Market Context). The product/market-quality read is real, but the
position is being bought for market position in the AI data stack rather than for a
valuation discount, which is the THEME definition. THEME also sets the more conservative
ceiling, which is the right default while the thesis is unproven. **[CONFIRM].**

## Origin

Position opened 2026-07-31. Funded by trimming META following that company's Q2
conference call (see Rotation Context below).

Bill's stated rationale, verbatim in substance: a great service in the AI space, with
multiple analysts calling for roughly 40% upside.

## Core Thesis [CONFIRM]

The data layer is where enterprise AI actually gets built. Models are increasingly
commoditized and interchangeable; the governed, queryable corporate data they run
against is not. Snowflake's position is as the platform enterprises have already
standardized on for that data — which makes it a toll on AI adoption rather than a bet
on any particular model winning.

This pairs structurally with the SKHY thesis rather than duplicating it: SKHY owns the
*physical* constraint on AI compute (memory bandwidth), SNOW owns a *software* control
point over the data AI consumes. Both are "own the bottleneck, not the beneficiary"
expressions. **Note this raises aggregate AI-infrastructure exposure — see Concentration
Note.**

## Market Context at Entry (verified 2026-07-31)

Recorded as facts at the time of entry, not as forecast:

- Consensus analyst price target approximately $291.57 across 38 analysts; a separate
  51-analyst average of $298.23 was described as roughly 1% above the then-current price.
- Range: high $370 (UBS, 2026-06-03), low $200 (Macquarie, 2026-06-03).
- Recent target raises: Wells Fargo to $500 citing AI-driven customer spending;
  BofA to $330 from $300; Jefferies to $310 from $300; Scotiabank $320; Mizuho to $260
  from $235; TD Cowen to $230 from $210; Barclays to $219 from $203.
- Aggregate rating characterized as "Strong Buy."

**Reconciliation — RESOLVED 2026-07-31, source identified.** Bill's stated basis is the
Wells Fargo note of 2026-07-29: analyst Ryan MacWilliams raised the target **from $320
to $500** and maintained Overweight, arguing AI *drives* Snowflake's growth rather than
disrupting it, that AI agents increase platform spend, and that investors are
underestimating AI as the primary growth engine. That target implies approximately
**85% upside from the 2026-07-28 close of $270.36** — not 40%. It is **the highest
target on Wall Street**, against a #2 of UBS $370 and a consensus near $291.

Two things follow, and both belong in the file:

1. The upside figure in the original rationale understated what the source actually
   said. Not a problem — but it means the entry was made on a number Bill had not yet
   pinned down, which is worth knowing about his own process.
2. **The basis is one analyst, not "multiple analysts."** A single firm moving its
   target 56% in one note is by definition an outlier, and it sits $130 above the
   next-highest target. The raise-cycle at other firms (BofA $330, Jefferies $310,
   Scotiabank $320, Mizuho $260, TD Cowen $230, Barclays $219) is real but clusters far
   below $500. **Anchoring the position's expected return on the Street's single most
   bullish note is the specific behavioral risk here.** See Key Risks.

Sources: [CNBC — Wells Fargo 85% upside call](https://www.cnbc.com/2026/07/29/wells-fargo-says-this-software-stock-has-85percent-upside.html) ·
[TheStreet — Street's highest target](https://www.thestreet.com/investing/stocks/wells-fargo-snowflake-snow-stock-highest-price-target-500) ·
[Benzinga — target raise](https://www.benzinga.com/trading-ideas/movers/26/07/60769174/snowflake-stock-rises-as-wells-fargo-lifts-target-to-500)

## Fundamental Leg — ADDED 2026-07-31 (previously an open item)

The Open Items list originally flagged that the thesis rested on analyst targets with no
operating metric behind it. Bill supplied the missing leg: **guidance raised on early AI
product traction.** Verified detail:

- FY product revenue guidance raised to **$4.395B, +27% YoY**, with management
  attributing the raise specifically to early AI product traction rather than to general
  platform growth.
- Quarterly product revenue $1.09B, **+32% YoY**.
- CFO Brian Robins characterized tools including Cortex Code as driving a **"step
  function change"** in AI revenue potential.
- Adoption metrics reported: AI influenced nearly 50% of new logos won; Snowflake AI
  components powering ~25% of deployed use cases; **6,100+ customer accounts using
  Snowflake AI weekly.**
- Market reaction to the AI-driven quarter: **+36% in a single session on 2026-05-28,
  the stock's best day ever.**

**Why this matters more than the price target:** consumption-priced software is
supposed to convert AI workload growth into revenue mechanically. Management raising
guidance and attributing it to a *named* AI product is the conversion actually showing
up in the numbers — which is precisely the evidence the Exit Conditions (criterion 3)
were written to test for. This materially strengthens the thesis relative to where it
stood at file creation.

**[BILL] — confirm the vintage of these figures.** Snowflake's fiscal calendar runs
offset from the calendar year, and search results mixed FY2026 and FY2027 reporting
periods. The direction is not in doubt, but the specific quarter these metrics belong to
should be pinned down before they are cited as current.

Sources: [Seeking Alpha — guidance raise to $4.395B](https://seekingalpha.com/news/4489810-snowflake-raises-fy-2026-product-revenue-guidance-to-4_395b-as-ai-adoption-accelerates) ·
[Yahoo Finance — AI traction fuels guidance boost](https://finance.yahoo.com/technology/ai/articles/ai-traction-fuels-snowflake-snow-140430991.html) ·
[CNBC — best day ever, +36%](https://www.cnbc.com/2026/05/28/snowflake-snow-software-stock-rally.html)

Sources: [Benzinga — SNOW analyst ratings](https://www.benzinga.com/quote/SNOW/analyst-ratings) ·
[StockAnalysis — SNOW forecast](https://stockanalysis.com/stocks/snow/forecast/) ·
[TipRanks — Mizuho raise](https://www.tipranks.com/news/the-fly/snowflake-price-target-raised-to-260-from-235-at-mizuho-thefly)

## Technical Context — added 2026-07-31 [BILL to set levels]

Bill's read at entry, transcribed: the chart shows **two prior highs and is building a
third now**. Per Josh Brown's framing — *"I don't believe in a triple top, it could
easily break out, but the floor is in."* Position is down roughly **3% from Bill's
entry** on the day it was opened.

The market-structure argument behind that view: repeated tests of the same resistance
absorb overhead supply, so a third approach more often precedes a breakout than a
reversal. That is a legitimate and widely held read. It is also **genuinely contested** —
in classical technical analysis the formation being described, a triple top, *is* the
bearish reversal pattern. Saying "I don't believe in triple tops" is a considered
rejection of that classical reading, not an absence of a bearish case. Recorded this way
so that if the pattern does resolve downward, the file shows it was a known
interpretation that was consciously overruled, not something nobody saw.

### Derived levels (computed from chart data 2026-07-31 — for Bill's confirmation, not his input)

The qualitative read is sufficient to infer the levels; they are derived here rather
than requested. Reconstructed structure:

| Level | Price | Basis |
|---|---|---|
| Resistance / the "two heads" | **~$285** | June 2026 peak (~$285), then 52-week high $285.74 on 2026-07-29 — two tests of the same zone |
| Breakout print | **~$298** | 2026-07-30 close $298.10, above the $285.74 high — the third approach cleared the zone |
| **Near floor** | **~$285** | The twice-tested resistance zone. Classic resistance-turned-support: if the breakout is real, this is the level that must hold |
| **Structural floor** | **~$253** | Cited key support and the swing low of the mid-year decline. Below this, the multi-test base has failed outright |

Context: SNOW fell roughly in half in a mid-year plunge (a pivot-top sell signal on
2026-06-01 preceded a −17.76% leg) before rebounding to retest the June peak. So the
"two heads" are the pre-plunge June high and the post-recovery July high, and the
current action is the third approach — which on 2026-07-30 printed above both.

**This maps cleanly onto "the floor is in."** With entry around $298 and a ~3% same-day
decline putting price near $289, the position sits just above the $285 shelf. That
makes $285 the operative near-term floor and $253 the level at which the technical
premise is finished rather than merely tested.

**Proposed Sheet entries — Add: $285. No Trim level** (the breakout thesis has no
natural ceiling; a trim level here would contradict the premise). **[BILL] — confirm or
adjust; these are inferred from public price data, not from Bill's own chart work.**

Sources: [Investing.com — 52-week high $285.74](https://www.investing.com/news/company-news/snowflake-stock-hits-52week-high-at-28574-usd-93CH-4820505) ·
[24/7 Wall St — $282.90, near June peak](https://247wallst.com/cards/snowflake-hits-282-90-nearly-matching-its-june-peak-as-the-snow-price-extreme-01kyr4aw1btgerpep02tc1695v) ·
[Traders Union — resistance $285, support $253](https://tradersunion.com/news/financial-news/show/2591691-snowflake-tests-resistance/)

### On confluence (correcting an earlier framing in this file)

An earlier version of this section asked which leg — fundamental or technical — was
"load-bearing," as though the position had to rest on one. **That framing was wrong and
is withdrawn.** Requiring single-factor attribution is a rule appropriate to systematic
strategies; it does not describe how this portfolio is run. Bill's documented process is
discretionary and explicitly multi-input — `styles.json` defines GARP-*by-intuition*,
and risk is managed by small-step scaling rather than binary triggers. Chart structure,
fundamentals, and trusted commentary are legitimately combined, and multiple independent
signals agreeing is stronger evidence than any one of them alone, not weaker.

What survives, restated correctly: the legs can diverge, and divergence is *information*
rather than a rule violation. If the $285 shelf breaks while AI adoption metrics and
guidance keep improving, that is a genuine conflict worth noticing — and the response
under a small-step scaling discipline is to re-evaluate and size accordingly, not to
mechanically exit. The purpose of writing the levels down is to make a divergence
visible when it happens, not to pre-commit to what to do about it.

**Proportion note:** a 3% move on a seed-sized position is noise, and the position was
deliberately sized so that being early costs little. This section exists to structure the
decision, not to suggest the move requires one.

**Source-concentration note:** both positions opened 2026-07-31 — ES and SNOW — carry a
Josh Brown technical component in their rationale. Not a problem in itself; worth
tracking so that a single commentator does not quietly become the portfolio's dominant
idea source without that being a deliberate choice.

## Key Risks

- **Entry is momentum-priced, not discount-priced.** Unlike IBM (~19 P/E fear discount)
  or SKHY (sector-contagion selloff), there is no dislocation being exploited here. The
  stock is near consensus fair value with sentiment already strongly positive. That
  removes the margin of safety that the dip-buying style normally supplies, and means
  the return has to come from the business outrunning an already-optimistic bar.

- **Single-analyst anchoring.** *Partly resolved 2026-07-31 — a fundamental leg now
  exists (see Fundamental Leg section), which removes the original "sentiment only"
  objection.* What remains: the return expectation is anchored on Wells Fargo's $500,
  the Street's highest target, sitting $130 above the next-highest and roughly $210
  above consensus. One analyst can be right and the consensus wrong — but a thesis that
  needs the most bullish person on the Street to be correct has no margin for the merely
  good outcome. **The honest framing is that consensus (~$291) is the base case and
  $500 is one firm's bull case, not the expected value.**

- **Bought near a 52-week high, one day after the Street's most bullish note.** This
  should be said plainly because it is the *opposite* of the SKHY/IBM pattern — those
  were dislocations bought into fear at a discount. This is a momentum entry into
  strength on a positive catalyst. Both can work; they are different games with
  different risk profiles, and conflating them in memory would be the actual error.
  A dip-buying discipline does not transfer to a momentum entry.

- **Consumption pricing cuts both ways.** Revenue scales with customer workload, which
  is excellent in an AI-adoption ramp and unforgiving if enterprises optimize spend in
  a downturn. Net revenue retention is the number that reveals this first.

- **Competitive position is genuinely contested.** Databricks, and the native data
  platforms of the hyperscalers — including AWS and Google, both of which Bill owns
  directly — compete for exactly this workload. Owning AMZN and GOOG alongside SNOW
  means holding both sides of that contest.

- **This is the same debate the bundle already flagged as unresolved.** The
  briefing bundle's central tension is AI-infrastructure-bull vs.
  dot-com-bubble-bear, with sources genuinely split. This position leans further onto
  the bull side of an argument Bill's own research inputs have not settled.

- **[BILL] — verify current valuation on a fundamental measure** (EV/Sales, FCF margin,
  net revenue retention, path to GAAP profitability). None of these were checked at
  entry; the entry rested on analyst targets alone.

## Concentration Note — read before sizing

SNOW increases exposure to a theme the portfolio already expresses several ways:
QQQM and VTI (index-level), NVDA and AVGO and SKHY (silicon/memory), VRT and ETN and
VST (power and data-center infrastructure), GOOG and AMZN and META (hyperscalers),
NOW and IBM (enterprise software). AI-adjacent exposure is already the portfolio's
largest de facto theme.

**[BILL] — compute aggregate AI exposure at ETF look-through before adding to SNOW.**
The style ceiling governs SNOW individually at 3.0%, but there is no ceiling enforcing
a limit on the *theme* across positions, and that is where the real concentration sits.
This is the same structural blind spot noted in the SKHY concentration analysis.

## Position Sizing Plan

- **Current: seed position** — share count and cost basis pending Schwab sync.
- **Ceiling: 3.0%** — THEME. Ceiling is capacity, not a target.
- **Target weight: [BILL] — not yet set.**
- Build path per standing practice: at least three legs, on volatility, never chasing.
  Given the momentum-priced entry, adds should require a fundamental data point
  (retention, margin, or a genuine valuation reset) rather than continued strength.

## Scaling State

next_step: **[CONFIRM] hold the seed pending a fundamental leg.** The position was
opened on a product-quality judgment plus analyst sentiment. Before adding, the thesis
should rest on at least one verifiable operating metric — net revenue retention or FCF
trajectory — so that a sentiment reversal alone does not invalidate it.

## Rotation Priority

priority: low — seed position, opened today, no action contemplated.

## Exit Conditions [BILL — draft, needs confirmation]

1. Net revenue retention deteriorates materially — the earliest signal that consumption
   pricing has turned from tailwind to headwind.
2. Evidence of share loss to Databricks or a hyperscaler-native platform in competitive
   enterprise deals.
3. Two consecutive quarters where AI-attributed workload growth fails to show up in
   consumption revenue — would mean the "toll on AI adoption" premise is not converting.
4. The analyst-sentiment cycle reverses without a corresponding change in fundamentals
   *and* that reversal is the main thing that changed — which would confirm the position
   was a sentiment trade all along.
5. Aggregate portfolio AI-theme exposure requires reduction and SNOW is the least
   differentiated expression of it.

## Rotation Context

Funded by a partial META trim on 2026-07-31, alongside ES. Bill's stated reason for the
META trim: **weak business case presented during the Q2 conference call**, while
remaining in the position **for Zuckerberg's effectiveness**. See `META_thesis.md`
Review Log for the sell-side of this rotation.

**Coherence note worth surfacing:** META was trimmed because its AI spending case was
unpersuasive on the call, and part of the proceeds went into SNOW, a position whose
thesis depends on that same enterprise AI spending materializing. These are reconcilable
— skepticism about *one company's* capital allocation is not skepticism about the theme,
and moving from a spender to a toll-taker is a coherent expression of exactly that
distinction. Recorded because it is the kind of tension that reads as a contradiction
later if the reasoning is not written down now.

## Open Items

- [ ] **Set Trim and Add levels in the portfolio Sheet.** Both cells will be blank,
      which means the morning brief will report no proximity for this position — the
      same gap identified on VRT (2026-07-29) and SKHY (2026-07-29).
- [x] ~~Reconcile the "~40% upside" figure against the published target range.~~
      **Resolved 2026-07-31:** source is the Wells Fargo $500 note (2026-07-29),
      implying ~85% from the 7/28 close — the Street's highest target, one analyst.
- [x] ~~Establish a fundamental leg.~~ **Resolved 2026-07-31:** guidance raised to
      $4.395B product revenue (+27% YoY) attributed to early AI product traction; see
      Fundamental Leg section.
- [x] ~~Set the floor and breakout levels.~~ **Derived 2026-07-31** from public price
      data: near floor ~$285 (twice-tested resistance turned support), structural floor
      ~$253. See Technical Context.
- [ ] **Confirm the derived levels** and write Add: $285 into the Sheet so the morning
      brief reports proximity. No Trim level proposed.
- [ ] ~~Decide which leg is load-bearing.~~ **Withdrawn** — false dichotomy; the
      position rests on confluence by design. See Technical Context.
- [ ] Confirm the fiscal-period vintage of the guidance/adoption figures.
- [ ] Confirm style assignment: THEME (3.0%) vs. GARP (9.0%). Determines the ceiling.
- [ ] Still outstanding: net revenue retention specifically — the metric that reveals
      consumption-pricing risk first, and not covered by the guidance raise.
- [ ] Compute aggregate AI-theme exposure across all positions before adding.
- [ ] Set target weight and drawdown tolerance.
- [ ] Confirm or rewrite the Core Thesis above — the "own the data layer" framing is
      drafted from Bill's "great service in the AI space," which is a shorter statement
      than the thesis built on top of it.

## Review Log

- **2026-07-31:** Position opened. Draft thesis created same day to unblock the briefing
  export, which treats a held position with no thesis file as a BLOCKING preflight
  issue. Stated rationale: great service in the AI space, multiple analysts calling for
  ~40% upside. Funded by a partial META trim (see Rotation Context). Entry recorded
  explicitly as momentum-priced rather than discount-priced — this is a different setup
  from the IBM and SKHY entries of the prior week, and the distinction should not blur
  in memory. The Core Thesis section above is a drafted expansion of a one-line
  rationale and needs Bill's confirmation before it is treated as his reasoning.

- **2026-07-31 (same day, second entry):** Bill supplied the source behind the entry —
  guidance raised on early AI product success, plus the Wells Fargo $500 target. Both
  verified and added above. Net effect on the thesis: **materially stronger.** It now
  rests on management raising guidance and attributing it to a named AI product, which
  is an operating fact, rather than on analyst sentiment alone. The original "no
  fundamental leg" objection is withdrawn.

  Two things sharpened rather than softened in the process, and are recorded so the
  position is not remembered more favorably than it was underwritten: the upside figure
  is **one analyst's** (the Street's highest, $130 above #2), not multiple analysts'
  consensus; and the entry was a **momentum buy near a 52-week high**, structurally
  opposite to the SKHY and IBM dislocation entries of the prior week. Neither is a
  criticism of the trade. Both are the kind of detail that gets smoothed over in
  hindsight, which is what this file exists to prevent.

- **2026-07-31 (third entry):** Technical leg added — see Technical Context. Position
  down ~3% from entry on day one; Bill's read is two prior highs with a third forming,
  and per Josh Brown, no belief in a triple top, with the floor considered in.

  Observation for the record, offered as process rather than judgment: the thesis has
  now acquired three distinct rationales in a single day — analyst target, then
  guidance/AI traction, then chart structure — with the second and third arriving after
  the position was already open. Each is individually sound and the fundamental leg in
  particular is a real strengthening. But a thesis that accumulates supporting arguments
  *after* entry is the shape thesis drift takes, and this file's purpose is to make that
  visible early rather than obvious later.

- **2026-07-31 (fourth entry — correction):** Bill pushed back on two points in the
  entry above, and both corrections stand.

  First, the "which leg is load-bearing" framing was a false dichotomy. He makes buy
  decisions on technicals, fundamentals, and trusted commentary *together*, and that is
  confluence, not confusion — multiple independent signals agreeing is stronger than any
  one alone. The single-factor-attribution rule I imported belongs to systematic
  strategies and contradicts this portfolio's own documented approach
  (GARP-*by-intuition*, small-step scaling). Withdrawn from the file.

  Second, and more useful going forward: **the floor was inferable from the chart, so
  deriving it was my job, not his.** A qualitative read ("two heads, third forming, floor
  is in") contains enough information to compute the levels from public price data. The
  levels are now derived and recorded above. **Standing division of labor from here:
  Bill supplies the read and the judgment; I do the reconstruction, verification, and
  quantification.** Asking him to hand back a number he had already implied was work
  transferred in the wrong direction.

<!-- region:position_state -->
**Current Allocation:** 1.01%
**Cost Basis:** $8,930.30
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** THEME
**Size Ceiling:** 3.00%
**Drift:** -1.99%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-07-31: Buy 10.0 @ $297.26
- 2026-07-31: Buy 10.0 @ $297.00
- 2026-07-31: Buy 10.0 @ $298.77
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-08-03 09:36: Auto-sync allocation 1.01%, drift -1.99%
<!-- endregion:change_log -->
