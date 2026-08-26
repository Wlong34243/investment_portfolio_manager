---
doctrine_version: 1
updated: 2026-08-24
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
