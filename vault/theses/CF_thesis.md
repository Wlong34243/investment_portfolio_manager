---
ticker: CF
style:
framework_preference:
entry_date: '2026-08-28'
last_reviewed: '2026-08-28'
cost_basis: 3131.63
current_allocation: 0.52%
triggers:
  trigger_type:
  entry_price: 125.00
  seed_position_weight: 0.52%
  price_add_below:
  price_trim_above:
  fwd_pe_add_below:
  fwd_pe_trim_above:
  style_size_ceiling_pct:
---
# CF (CF Industries) — Investment Thesis

**STATUS: Initiated 2026-08-28.** Seed position entered same-day; this file is drafted from
Bill's own stated rationale plus a research summary he supplied in the same message. Sourced
facts are verified against live Schwab data below. `style`, `trigger_type`, and all trigger
levels are `[BILL]` — none were specified and none are inferred here.

## Known Facts (sourced, not judgment)

- **Position:** 25.0 shares, single lot, cost basis $3,131.63 ($125.265/share) — matches Bill's
  stated entry of "$125."
- **Live (Schwab positions fetch, 2026-08-28, same-day — Holdings_Current/Sheet not yet synced
  to this trade):** price $125.34, market value $3,133.38, unrealized +$1.76 (~+0.06%).
- **Account:** Schwab tax-lot hash `84045119` → suffix `...5119`, inside
  `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES`. In scope. **Taxable.**
- **Acquisition date: not recorded** by Schwab for this lot (same gap seen on BTC/PWR at entry).
- **Dividend yield (live quote):** 1.91% — consistent with the $0.60/quarter payout Bill cites
  below (~$2.40/yr against $125.34).
- **Approximate weight:** 0.52%, computed as $3,133.38 against the last known bundle total
  ($604,274.32, 2026-08-28 08:07 bundle `8b3a29284ad2…`) plus this position. **Unofficial** —
  the authoritative weight is whatever the next `pm morning` / `pm snapshot` sync writes to
  Holdings_Current; do not cite this figure past the next sync.

## Style

`[BILL]` — unassigned. Not inferred here, but worth naming the candidate for whoever sets it:
Bill's own rationale below ("valuation and likely stability and upside") reads as GARP-by-
intuition — an established, real-earnings industrial bought on valuation rather than a theme —
closer to XOM/APO than to a THEME name. That is a read of his words, not a decision made for him.

## Core Thesis

**In Bill's words (2026-08-28):** bought based on **valuation and likely stability and upside.**

*What that pairs with, from the research summary Bill supplied in the same message — reproduced
here as sourced facts, not independently verified against primary filings:*

CF Industries is advancing its low-carbon initiatives with the groundbreaking of the **Blue
Point One** ammonia plant, targeted to produce **1.4 million metric tons annually by 2029**.
H1 2026 earnings were strong, but the company carries execution risk on major capital projects
and faces mixed analyst sentiment — consensus rating **Hold** — on future performance. The
stability/upside framing in Bill's own rationale sits against that backdrop: an established,
profitable, cash-generative producer with a project-driven growth leg, entered at a price Bill
judged attractive on valuation, not on the project's outcome being assured.

## Bull Case

*Facts as supplied by Bill, sourced to his summary — treat every figure as a claim pending
independent verification, per the standing rule on unverified source material (`CLAUDE.md`,
Bundle Architecture).*

- **Financial strength (H1 2026):** net earnings **$1.3B**; trailing free cash flow **~$1.8B**.
- **Shareholder returns:** **~$1.3B** returned via buybacks and dividends in the period;
  quarterly dividend raised **20% to $0.60/share** — corroborated by the live 1.91% quote yield
  above, which is consistent with that payout at the current price.
- **Growth project:** Blue Point One low-carbon ammonia plant — groundbreaking underway,
  targeted 1.4 MMT/year capacity by 2029.
- **Entry rationale (Bill):** valuation-driven, with an expectation of relative stability plus
  upside — not a momentum or thematic entry.

## Key Risks

*Also from Bill's supplied summary:*

- **Execution risk on major projects.** Blue Point One and other capital projects carry
  standard large-industrial-project execution risk; the summary flags this explicitly as a
  factor behind the Hold-rating sentiment, without giving specifics on what could go wrong or
  by how much. `[BILL]` — worth naming the specific execution risk (cost overrun, timeline
  slip, permitting) if/when more is known.
- **Geopolitical tensions** — named as a risk in the supplied summary with no further detail
  given. Plausibly relevant to CF given nitrogen/ammonia trade exposure and energy-input costs,
  but that connection is inference, not something the summary itself states — flagged as such.
- **Recent softness in customer demand** — named directly in the summary; no magnitude or
  duration given.
- **Mixed analyst sentiment / Hold rating** — the summary states analysts are maintaining Hold
  amid mixed sentiment on future performance, despite the strong H1 print. That gap (strong
  trailing results, cautious forward rating) is itself worth tracking, not resolving here.

## Scaling State

next_step: `[BILL]`

## Rotation Priority

priority: `[BILL]`

## Exit Conditions

`[BILL]` — none stated. Do not infer exit conditions from the risks listed above; those are
factors to watch, not thresholds Bill has set.

## Review Log

- 2026-08-28: Thesis file created same-day as entry. Core Thesis is Bill's own stated rationale
  (valuation, stability, upside); Bull Case / Key Risks transcribed from a research summary Bill
  supplied in the same message, organized but not expanded or independently fact-checked beyond
  what's noted inline. Live position facts (25 sh @ $125.265, account `...5119`, taxable)
  verified against a fresh Schwab positions/tax-lots fetch, since Holdings_Current had not yet
  synced to this trade. Style, trigger_type, and all trigger levels left `[BILL]` — none given.

<!-- region:position_state -->
**Current Allocation:** 0.52% (approximate — pending next sync, see Known Facts)
**Cost Basis:** $3,131.63
<!-- endregion:position_state -->

<!-- region:sizing -->
**Style:** None
**Size Ceiling:** 0.00%
**Drift:** +0.52%
<!-- endregion:sizing -->

<!-- region:transaction_log -->
No transaction log available — Schwab lot record carries no acquisition date and the Sheets
`Transactions` tab was not queried in this pass. Populate on next `write_thesis_updates.py` sync.
<!-- endregion:transaction_log -->

<!-- region:realized_gl -->
No realized G/L history.
<!-- endregion:realized_gl -->
