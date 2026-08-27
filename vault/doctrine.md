---
doctrine_version: 1
updated: 2026-08-27
constraints:
  - id: no_withdrawal_need
    established: 2026-08-19
    restated: 2026-08-24
    scope: portfolio
    summary: >
      Real estate cash flow covers living expenses and cost of living has been
      reduced. This portfolio does not fund withdrawals; it exists to grow.
    affects: [ceiling_breach_acceptance, risk_tolerance]
    action: context_only

  - id: accumulation_phase
    established: 2026-08-24
    scope: portfolio
    summary: >
      Accumulation phase. Pushing money into appreciating assets and waiting for
      recent acquisitions to pay off. Not harvesting.
    affects: [rotation_bias]
    action: context_only

  - id: tax_hold_runners
    established: 2026-08-24
    scope: position
    tickers: [UNH, COF]
    summary: >
      Acute awareness of realized-gain exposure. Selling runners is not
      attractive. These are not sale candidates on a valuation trigger alone.
    affects: [NEAR_TRIM]
    action: downgrade_informational

  - id: cost_basis_method
    established: 2026-08-27
    scope: portfolio
    summary: >
      Schwab selects lots by tax consequence (Tax Lot Optimizer) on all three
      allowlisted accounts — …6499, …8767, …5119 — as of 2026-08-27. Uniform.
      Election date not established; periods before 2026-08-27 are not asserted.
      Relief order: ST losses (largest first), LT losses, ST flat, LT flat,
      LT gains (smallest first), ST gains (smallest first). NOT FIFO.
      Realized_GL remains the sole authority on which lot went.
    affects: [lot_relief_estimate]
    action: context_only
    method: tax_lot_optimizer
    effective_date: unknown
---

# Portfolio Doctrine

Standing constraints that govern decisions across positions. This file is the single
source; thesis files point here rather than restating.

**This file is hand-maintained and manual-only. No agent writes to it** — same rule as
`Target_Allocation`. Changes are Bill's, dated, and additive: supersede an entry by
adding a new one with a later `established` date, do not silently edit history.

## Review Log
- 2026-08-24: File created. `no_withdrawal_need` migrated out of QQQM/VST/VRT thesis
  Review Logs (see prompts/doctrine_layer_2026-08-24.md Step 5). `accumulation_phase`
  and `tax_hold_runners` recorded from Bill's 2026-08-24 statement. `tax_hold_runners`
  applies to any NEAR_TRIM (not exits only); tickers UNH and COF as named.
- 2026-08-27: `cost_basis_method` added — Tax Lot Optimizer on all three allowlisted
  accounts, uniform as of 2026-08-27; `effective_date: unknown` (election date not
  established). COF/MU Review Logs corrected for FIFO narration error (corpus risk).
