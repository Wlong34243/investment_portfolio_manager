---
ticker: SKHY
style: THEME
framework_preference: thematic_specialist_v1
entry_date: 2026-07-29
last_reviewed: '2026-08-21'
current_allocation: 1.06%
cost_basis: 5284.48
time_horizon: TBD - see open items
triggers:
  trigger_type: ceiling_only
  entry_price: 138.00
  seed_position_weight: 0.47%
  price_add_below:
  price_trim_above:
  style_size_ceiling_pct: 3.0
drawdown_tolerance_pct:
---
# SKHY (SK Hynix) — Investment Thesis

**STATUS: DRAFT, created 2026-07-29 to unblock the briefing export. Sections marked
[CONFIRM] are transcribed from Bill's stated reasoning in conversation and need his
sign-off. Sections marked [BILL] require input only he can supply.**

## Style
Thematic Specialist / AI Memory Bottleneck

## Origin

Position opened 2026-07-29: 20 shares @ $138.00, $2,760.00, approximately 0.47% of
portfolio. SK Hynix listed on Nasdaq 2026-07-10 in a roughly $28B offering, making
direct US-listed exposure available for the first time.

Path to the decision: the Kospi triggered circuit breakers on consecutive sessions
with SK Hynix down roughly 13% and Samsung down roughly 8%. The initial idea was to
express this through EMXC, then through MU. Both were rejected — EMXC because the two
target names are only about 19% of the fund at the look-through floor and because a
purchase within 30 days of the 2026-07-20 loss sale would have triggered a wash sale;
MU because it holds only 5-10% HBM share against SK Hynix's 50-55%. The direct listing
made the proxy unnecessary.

## Core Thesis [CONFIRM]

Owning the binding constraint in AI compute rather than a downstream beneficiary of it.

The argument, in Bill's framing from 2026-07-29: memory bandwidth — not raw compute —
is the constraint on when enterprise AI produces measurable returns at scale. This is
Steve Hou's point on Forward Guidance (2026-07-26), and if it is right, the economics
accrue to whoever controls the constrained input. SK Hynix is the largest supplier of
that input at roughly 50-55% HBM market share.

This is a THEME position by construction: buying market position over company quality.
The bet is on SK Hynix's share of a constrained product, not on it being the best-run
or best-valued business in semiconductors. That framing is what caps the size.

## Market Context at Entry (verified 2026-07-29)

Recorded as facts at the time of entry, not as forecast:

- SK Hynix reports HBM, DRAM and NAND capacity essentially sold out for 2026.
- HBM3E supply prices raised approximately 20% for 2026 orders (Samsung and SK Hynix).
- Conventional DRAM contract prices up roughly 55-60% in Q1 2026; server DRAM forecast
  above 60%.
- Goldman Sachs put the 2026 DRAM supply-demand gap at 4.9%, described as the most
  severe shortage in 15 years.
- BofA characterized 2026 as a memory supercycle comparable to the 1990s boom, with
  DRAM revenue +51% and NAND +45% year over year, and named SK Hynix its top pick in
  the sector.
- HBM production consumes roughly 3x the wafer capacity per gigabyte of standard DRAM,
  so HBM output structurally removes conventional DRAM supply.
- Peer context: Micron up roughly 68% YTD 2026 with Q3 guidance near $33.5B revenue at
  approximately 81% gross margins.

## Key Risks

- **This is a cycle-peak entry, not a discount.** The single most important risk. Memory
  is the most cyclical business in semiconductors, and the entry is being made into 81%
  peer gross margins and DRAM pricing up 55-60%. Peak margins mean-revert. A low
  multiple on a cyclical at peak earnings is historically a warning, not a bargain —
  the Lynch cyclical rule. **The entire thesis rests on whether contracted HBM has
  genuinely changed the cycle or merely delayed it.**

- **Contracted revenue is a claim to be tested, not a fact to be assumed.** Capacity
  "sold out" through 2026 with orders into 2027-2028 is the load-bearing structural
  argument. If those contracts carry volume flexibility, price resets, or cancellation
  provisions, the visibility is weaker than the headline implies. **[BILL] — this is
  the question to answer before adding.**

- **Chinese memory competition.** CXMT and peers scaling conventional DRAM pressures
  pricing on the non-HBM book. This is also the specific risk Bob Elliott named on On
  The Tape (2026-07-28) as the thing consensus ignores about US AI margins — the same
  argument applied to memory.

- **Customer concentration.** HBM demand is concentrated in a small number of AI
  accelerator programs. Reported supply commitments to NVIDIA through 2026 are a
  strength and a concentration at the same time.

- **Competitive share is contested at the top.** Samsung at 35-40% is a well-capitalized
  competitor with every incentive to close the gap, and Micron is expanding. A 50-55%
  share in a high-margin product invites capacity response.

- **New-listing mechanics.** A July 2026 Nasdaq listing means limited US trading
  history, potential lockup expirations, and index-inclusion flows that can move the
  stock independent of fundamentals. **[BILL] — check lockup schedule.**

- **Currency and jurisdiction.** Korean issuer; KRW exposure and Korean market policy
  risk pass through regardless of the US listing.

- **US domestic-facility policy pressure (added 2026-08-25):** US policy pressure on Korean
  chipmakers to invest in domestic US facilities (2026-08-24). Same-day market reaction:
  KOSPI −2.66%, SKHY ADR −4.92% — policy/jurisdiction risk that can move the ADR independent
  of HBM fundamentals.

## Position Sizing Plan

- **Current: 0.47%** (20 shares @ $138.00). Seed size.
- **Ceiling: 3.0%** — THEME. Roughly 2.5% of headroom exists, which is capacity, not
  a target.
- **Target weight: [BILL] — not yet set.**
- Build path per standing practice: at least three legs, on volatility, never chasing.
  Given the cycle-peak entry, adds should require thesis evidence rather than price
  weakness alone. See the VRT precedent from the same week.

## Concentration Note — read before sizing

SK Hynix is already held indirectly. At the ETF look-through floor: 000660.KS is 0.20%
via EMXC and 0.09% via VEA, or **0.29% before this purchase**. Total SK Hynix exposure
is therefore approximately **0.76%**, not 0.47%.

**The look-through table will not catch this.** It keys on ticker symbol, and SKHY
(Nasdaq) and 000660.KS (KRX) are the same issuer under different symbols — the same
way GOOG and GOOGL already appear as two separate rows. Any concentration figure for
this position must be computed by hand until the look-through resolves dual listings.
Logged as a system finding.

Semiconductor exposure overall: approximately 8.5% at the look-through floor before
this purchase, roughly 9.0% after. The floor undercounts because it reflects top-10
fund holdings only.

## Scaling State

next_step: **Hold the 20-share seed. No adds pending confirmation of the contracted-HBM
structure.** Entry was made into peak-cycle economics deliberately; the position is
sized so that being early-and-wrong on the cycle costs roughly 0.47% of book. Price
weakness alone is not an add trigger — the add trigger is evidence that HBM contracts
carry firm volume and pricing rather than flexibility.

## Rotation Priority

priority: low — seed position, recently opened, no action contemplated.

## Exit Conditions [BILL — draft, needs confirmation]

1. HBM contract structure proves soft: volume flexibility, price resets, or material
   cancellations disclosed in any quarter.
2. HBM market share falls below approximately 45% as Samsung or Micron close the gap.
3. Conventional DRAM pricing rolls over more than one quarter ahead of HBM, indicating
   the cycle is turning before the structural story matures.
4. Gross margins compress two consecutive quarters while capacity is still described
   as sold out — that combination would mean pricing power is going, not demand.
5. Chinese conventional DRAM capacity reaches a scale that resets non-HBM pricing.

## Open Items

- [ ] **Set Trim and Add levels in the portfolio Sheet.** Both cells are blank, which
      means the morning brief will report no proximity for this position — the same
      gap identified on VRT on 2026-07-29.
- [ ] Confirm or rewrite the Core Thesis above.
- [ ] Set target weight and drawdown tolerance.
- [ ] Verify lockup expiration schedule for the July 2026 listing.
- [ ] Determine tax treatment: Korean issuer on a US listing — confirm withholding on
      any dividend and whether this is a PFIC-adjacent structure. CPA question, and
      cheaper to answer now than at filing.
- [ ] Decide whether EMXC and VEA indirect exposure should be netted against target
      sizing or treated as separate.

## Review Log

- 2026-08-25: Key Risks — US policy pressure on Korean chipmakers for domestic US facilities (2026-08-24; KOSPI −2.66%, SKHY ADR −4.92%). Source: scheduled morning brief, bundle `6bacf63dd536`.
- **2026-07-29:** Position opened, 20 shares @ $138.00. Draft thesis created same day
  to unblock the briefing export, which treats a held position with no thesis file as
  a BLOCKING preflight issue. Idea path ran EMXC to MU to SKHY across one session;
  the direct Nasdaq listing removed the need for a proxy. Entry made with explicit
  acknowledgement that memory is at cycle-peak economics — this is a bet on contracted
  HBM having changed the cycle, not a bet that memory is cheap.
- 2026-08-09: trigger_type: ceiling_only. Cyclicality re-examined and corrected: SKHY is SK hynix -- a memory maker, the same cycle as MU -- so the cyclical override class applies regardless of this file's own prose (checking for the word "cyclical" in the thesis text, rather than what the business is, was the wrong test). price_to_book not computed: yfinance's fundamentals for this ticker mix KRW-denominated equity with USD price/shares, producing nonsensical book-value-per-share figures (hundreds of thousands per share) -- a currency-handling bug, not a thin-history problem, and not worth fixing since the 3.0% THEME ceiling binds at 0.86% weight long before a valuation trigger would matter. See prompts/trigger_types_2026-08-09.md.

<!-- region:position_state -->
**Current Allocation:** 1.06%
**Cost Basis:** $5,284.48
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** THEME
**Size Ceiling:** 3.00%
**Drift:** -1.94%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
- 2026-07-31: Buy 5.0 @ $146.05
- 2026-07-31: Buy 5.0 @ $147.79
- 2026-07-31: Buy 5.0 @ $147.79
- 2026-07-29: Buy 3.0 @ $127.39
- 2026-07-29: Buy 20.0 @ $134.71
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->

<!-- region:change_log -->
2026-08-21 08:45: Auto-sync allocation 1.06%, drift -1.94%
<!-- endregion:change_log -->
