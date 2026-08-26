---
ticker: ES
style: FUND
framework_preference:
entry_date: '2026-07-31'
last_reviewed: '2026-08-14'
current_allocation: 0.00%
cost_basis: 0.0
time_horizon: TBD - see open items
triggers:
  entry_price:
  price_add_below:
  price_trim_above:
  div_yield_add_above:
  style_size_ceiling_pct: 5.0
drawdown_tolerance_pct:
---
# ES (Eversource Energy) — Investment Thesis

**STATUS: ARCHIVED 2026-08-14.** Position exited (Trade_Log 2026-08-03: "i did not see a clear case for es position"). File moved to `vault/theses/archive/`.

**STATUS: DRAFT, created 2026-07-31 same day as entry to unblock the briefing export.
Sections marked [CONFIRM] are transcribed from Bill's stated reasoning and need his
sign-off. Sections marked [BILL] require input only he can supply. Cost basis and
allocation are placeholders (0.00) until the trade clears Schwab sync — do not treat
those figures as real until the next `vault sync` overwrites them.**

## Style
Boring Fundamentals / Regulated Monopoly + Dividend [CONFIRM — see note]

Style note: assigned FUND (5.0% ceiling) because the holding rationale is durable
regulated cash flow and dividend. The entry trigger, however, was partly technical
(Josh Brown), which is not a FUND characteristic. If the position is really being held
as a trade on technicals rather than as a yield-and-durability holding, it belongs in
THEME at a 3.0% ceiling instead. **[CONFIRM] — the style choice sets the ceiling, so
it matters.**

## Origin

Position opened 2026-07-31. Funded by trimming META following that company's Q2
conference call (see Rotation Context below).

Idea source: Josh Brown commentary. Three stated legs — technicals, market position
as a monopoly in energy, and the dividend.

## Core Thesis [CONFIRM]

In Bill's framing: a regulated utility is a legal monopoly in its service territory,
which makes its revenue base structurally defensible in a way an unregulated business
is not. The return comes from a well-covered dividend on a franchise that cannot easily
be competed away, with the technical setup providing the entry timing rather than the
reason to own it.

This is the "boring fundamentals" style doing what it is for: durable business, cash
return, low reliance on anything going right. It is also the portfolio's only direct
regulated-utility exposure outside of ETF look-through — VST is held as a
merchant/IPP power name, which is a different business model with different economics.

## Market Context at Entry (verified 2026-07-31)

Recorded as facts at the time of entry, not as forecast:

- Dividend yield approximately 4.2–4.45% depending on source and calculation date.
- Annual dividend $3.15 per share, paid quarterly. Payout ratio approximately 67.3%.
- FY2026 EPS guidance issued ~2026-07-30: $4.57–$4.72.
- Debt-to-equity 1.77, and increased — elevated leverage relative to history.
- Analyst price targets in circulation: Citigroup $81, Wells Fargo $76 (raised from
  $75), Capital One $73.

Sources: [Daily Political — FY26 guidance](https://www.dailypolitical.com/2026/07/30/eversource-energy-nysees-releases-fy-2026-earnings-guidance.html) ·
[StockAnalysis — dividend history](https://stockanalysis.com/stocks/es/dividend/) ·
[MacroTrends — 51-yr dividend history](https://www.macrotrends.net/stocks/charts/ES/eversource-energy/dividend-yield-history)

## Key Risks

- **Rate sensitivity is the dominant risk, and the rate path just turned against it.**
  A leveraged utility bought primarily for yield is a bond proxy. The FOMC held at
  3.50–3.75% on 2026-07-29 on a 9-3 vote with three dissents favoring a *hike*, and the
  market is pricing two 25bp hikes by December. If that path is realized, the yield
  becomes less competitive and the debt gets more expensive at the same time. **This is
  the single risk most likely to make the entry look early.**

- **Leverage at 1.77 D/E and rising.** Utilities carry debt by design, but the direction
  of travel matters when refinancing into a higher-rate environment. Interest expense is
  the line to watch.

- **Payout ratio at 67% is comfortable but not generous.** It covers the dividend with
  room, but it is not the kind of coverage that absorbs a bad rate case or a large
  unplanned capex cycle without pressure.

- **Regulated does not mean risk-free — it means the risk is political.** Rate-case
  outcomes, allowed ROE decisions, and state regulatory posture in CT/MA/NH determine
  earnings power more than operating performance does. A regulator is a monopoly's
  counterparty, not its customer.

- **Technicals as entry basis have a short shelf life.** If the thesis is genuinely
  about durable cash flow, the technical setup should be irrelevant within a quarter.
  If the position is still being justified by technicals in six months, the style
  assignment above is wrong. **[BILL] — worth being honest about this at first review.**

- **[BILL] — verify capex/rate-base plans and any outstanding offshore-wind or
  large-project exposure.** Not researched at entry; a known category of risk for this
  issuer type that should be checked before adding.

- **ISO-NE natural gas input costs affect rate-case headroom (added 2026-08-07).**
  ES's own revenue is regulated/fee-based rather than directly commodity-exposed, but
  its New England service territory relies on natural gas to set the marginal price of
  electricity. Higher regional gas costs (heating-season constraints, pipeline capacity
  into New England) raise customer bills and narrow the political headroom regulators
  have to approve rate increases — a second-order channel from gas prices to allowed-ROE
  outcomes that the Key Risks above don't currently capture. Not yet researched in depth.

## Position Sizing Plan

- **Current: seed position** — share count and cost basis pending Schwab sync.
- **Ceiling: 5.0%** — FUND. Ceiling is capacity, not a target.
- **Target weight: [BILL] — not yet set.**
- Build path per standing practice: at least three legs, on volatility, never chasing.

## Scaling State

next_step: **[CONFIRM] hold the seed.** For a yield-and-durability position entered on a
technical trigger, the sensible add trigger is a better yield-to-risk, not a better
chart — i.e. weakness that raises the yield without impairing coverage. Adding on
strength would be buying the technical, not the thesis.

## Rotation Priority

priority: low — seed position, opened today, no action contemplated.

## Exit Conditions [BILL — draft, needs confirmation]

1. Dividend coverage deteriorates — payout ratio moves materially above ~80% without a
   clear one-off explanation.
2. An adverse rate-case outcome that structurally lowers allowed ROE.
3. Leverage continues climbing while rates rise, and interest expense begins visibly
   compressing EPS.
4. A dividend cut or freeze — thesis is dividend-dependent, so this is close to
   automatic.
5. The reason for holding drifts to price action alone with no fundamental leg standing.

## Rotation Context

Funded by a partial META trim on 2026-07-31, alongside SNOW. Bill's stated reason for
the META trim: **weak business case presented during the Q2 conference call**, while
remaining in the position **for Zuckerberg's effectiveness**. See `META_thesis.md`
Review Log for the sell-side of this rotation.

The implicit bet: proceeds from a mega-cap whose near-term spending case Bill found
unpersuasive are redeployed into a regulated-monopoly yield position and an AI data
platform (SNOW) — moving from one company's capital-allocation judgment into a
defensive cash-return holding plus a separate AI expression.

## Open Items

- [ ] **Set Trim and Add levels in the portfolio Sheet.** Both cells will be blank,
      which means the morning brief will report no proximity for this position — the
      same gap identified on VRT (2026-07-29) and SKHY (2026-07-29).
- [ ] Confirm style assignment: FUND (5.0%) vs. THEME (3.0%). Determines the ceiling.
- [ ] Confirm or rewrite the Core Thesis above.
- [ ] Set target weight and drawdown tolerance.
- [ ] Verify capex/rate-base plan and any large-project exposure.
- [ ] Record the specific Josh Brown commentary (date/source) so the origin is
      auditable later.
- [ ] Check ES exposure already held indirectly via VTI / XLF / IFRA look-through
      before sizing up.
- [ ] **RESEARCH QUEUE — flagged 2026-08-02, requested by Bill.** Stress-test this
      position against Russell Clark's long-end rate thesis (Monetary Matters, via the
      2026-08-02 Spotify aggregate). Clark's claim: the ten-year Treasury eventually
      reaches ten percent, driven structurally by a bipartisan political focus on wage
      growth and lower living costs, following Japan's arc. Real estate flat nominally,
      down sharply in real terms; low-rate-dependent sectors under sustained pressure.

      **This is the fully developed bear case for the risk already named as this
      position's dominant one.** The Key Risks section above states rate sensitivity is
      "the single risk most likely to make the entry look early" — Clark supplies the
      argument for why that risk is larger and more structural than a two-hike path.

      Specific questions to answer:
      1. What does a materially higher long end do to the dividend's relative
         attractiveness versus risk-free duration, at the current ~4.2-4.45% yield?
      2. What is the refinancing schedule against the 1.77 D/E — how much debt reprices
         over the next 24-36 months, and at what assumed cost?
      3. Rate-case mechanics: does allowed ROE adjust with prevailing rates, and on what
         lag? A regulated utility has a partial hedge here that an unregulated bond proxy
         does not — quantify it rather than assuming it.
      4. Does Clark's "real estate flat nominal, down in real terms" read extend to
         regulated rate base, which is nominally set?
      5. Sizing implication only — the Top Traders Unplugged framing in the same digest
         ("build portfolios to be wrong") applies directly: can this position be held
         through the Clark scenario at current size?
      6. Cross-check against the Sarasota rental portfolio. Both are rate-sensitive,
         income-producing, long-duration real-asset exposure. Clark's thesis hits both
         at once, which is an aggregate exposure question this file cannot see alone.

## Review Log

- **2026-07-31:** Position opened. Draft thesis created same day to unblock the
  briefing export, which treats a held position with no thesis file as a BLOCKING
  preflight issue. Idea sourced from Josh Brown: technicals, monopoly market position,
  dividend. Funded by a partial META trim (see Rotation Context). Entry made into a
  macro backdrop where the market is pricing two rate hikes by December — recorded
  explicitly because it is the main risk to a leveraged yield position and should not
  be forgotten if this trades poorly.
- **2026-08-07:** Added an ISO-NE natural gas input cost risk to Key Risks (rate-case-headroom factor), per `prompts/consolidate_and_thesis_repair_2026-08-07.md` Step 5.3. `next_step` left unresolved as `[CONFIRM] hold the seed` per instruction. Edited directly rather than through the archive-before-overwrite convention; `ES_thesis.md.bak` backfilled retroactively from pre-edit content to close that gap.
- **2026-08-14:** Archived. Position exited. Bill's stated reason in the 2026-08-03 Trade_Log basket: "i did not see a clear case for es position." Last logged sell 2026-08-04 -105sh @ $71.80. Allocation 0.00%. Moved to `vault/theses/archive/` (KRE precedent; state.md open item closed).

<!-- region:position_state -->
**Current Allocation:** 0.00%
**Cost Basis:** $0.00
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** FUND
**Size Ceiling:** 5.00%
**Drift:** -5.00%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-08-04: Sell -105.0 @ $71.80
- 2026-07-31: Buy 30.0 @ $71.98
- 2026-07-31: Buy 25.0 @ $72.38
- 2026-07-31: Buy 50.0 @ $72.16
- 2026-07-31: Buy 30.0 @ $71.98
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-08-07 14:18: Auto-sync allocation 0.00%, drift -5.00%
<!-- endregion:change_log -->
