# Prompt — Schwab Data Expansion, Phase 3: Cash Completeness and the Income / Flow Ledger

**Created:** 2026-08-25
**Executor:** Claude Code or Gemini CLI, run locally in `C:\Dev\Investment_Portfolio`
**Phase:** 3 of 4 — independent of Phase 2, runs in parallel with it
**Prerequisite:** Phase 1 complete. The cash probe in Step 0.2 needs no Phase 1 code and
is technically runnable earlier, but **do not start it before Phase 1 lands** — Phase 1
establishes the probe/verification conventions this phase reuses, and a cash-figure
correction landing while the client layer is still moving makes two changes hard to
attribute. Nothing in this phase depends on Phase 2's router.

---

## Why this exists

Two findings from the 2026-08-25 audit, one of them potentially a live defect.

### Finding 1 — `CASH_MANUAL` may be understating cash, and the name is a lie

`utils/schwab_client.py::fetch_positions()` is not manual at all. At lines ~196–197 it
reads `securitiesAccount.currentBalances.cashBalance` per allowlisted account, sums it,
and appends a synthetic `CASH_MANUAL` row at ~line 281.

At the same time, line ~183 defines:

```python
PURE_CASH_SWEEP_TICKERS = {'QACDS', 'CASH & CASH INVESTMENTS'}
```

and skips those positions on the stated assumption that they are *"usually reflected in
cashBalance."*

**That assumption is unverified and is the whole risk.** Schwab's `currentBalances`
carries several distinct cash-adjacent fields — `cashBalance`,
`cashAvailableForTrading`, `moneyMarketFund`, `availableFunds`, `liquidationValue`,
`totalCash` among them. If the sweep money-market fund's value lands in
`moneyMarketFund` rather than in `cashBalance`, then QACDS is skipped as a position
**and** absent from the cash row, and that money is invisible to the entire system:
total value, every weight denominator, every style-ceiling calculation.

This is a hypothesis, not a conclusion. Step 0 tests it against live data before a line
of code changes.

### Finding 2 — Analysis Rule 1 is stale, and `Income_Tracking` is a dead tab

`CLAUDE.md` Analysis Rule 1 instructs every LLM: *"Never infer liquidity posture from the
export. `CASH_MANUAL` does not represent the cash position."* Given Finding 1, that rule
is either correct-for-the-wrong-reason or simply stale. Per the governing principle —
**the file is presumed stale, not the behaviour incoherent** — this is a documentation
task, and it is named here: `CLAUDE.md` Analysis Rules, and the `PROMPT_PAYLOAD` block
inside `tasks/export_ai_briefing.py` that is authoritative for it.

Separately, `config.py` defines `TAB_RISK_METRICS` and `TAB_INCOME_TRACKING`;
`utils/sheet_readers.py` has readers for both (lines ~208 and ~219);
`tasks/build_command_center.py` line ~940 **reads `Risk_Metrics`**. No module writes
either tab. The dashboard consumes tabs nothing populates. `Income_Tracking` is Phase 3's
to fill; `Risk_Metrics` is Phase 4's.

The Schwab transactions endpoint accepts a `transaction_types` filter —
`DIVIDEND_OR_INTEREST`, `ACH_RECEIPT`, `ACH_DISBURSEMENT`, `WIRE_IN`, `WIRE_OUT`,
`JOURNAL`, `CASH_RECEIPT`, `CASH_DISBURSEMENT`, `MONEY_MARKET`, and others. Those are
exactly the categories needed to (a) fill `Income_Tracking` and (b) separate deposits
from returns, which is the precondition for any honest time-weighted return.

---

## Hard constraints

1. Order/trading endpoints remain forbidden.
2. **Do not write to `Holdings_Current`, `Trade_Log`, `Target_Allocation`, or
   `0_DASHBOARD`.** `0_DASHBOARD` in particular is clear-and-rebuild inside
   `build_command_center.py`; anything written elsewhere is erased next run.
3. Every Sheet write requires an explicit `--live` flag on its own command. Do not rely
   on `config.DRY_RUN` — it reads `os.getenv("DRY_RUN", "False")` and is not a safety
   guarantee.
4. Archive-before-overwrite on every pipeline write. A `.bak` taken *after* an edit is
   not a backup; prove pre-edit content by grep.
5. Single-batch gspread writes with fingerprint dedup. Never cell-by-cell.
6. All Sheet reads route through `read_gsheet_robust()` /
   `coerce_sheet_numeric_series()`. Do not add a local currency stripper — the
   2026-08-08 pandas string-dtype incident is a bug class, not a one-off, and any new
   `pd.to_numeric()` on raw Sheet strings reproduces it.
7. **Do not change the account allowlist.** `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES` scoping
   applies to every fetch in this phase exactly as it does today.

---

## Step 0 — Verification gate, and the live cash probe (STOP on any mismatch)

### 0.1 Static checks

```
grep -n "PURE_CASH_SWEEP_TICKERS" utils/schwab_client.py
    EXPECT one definition containing 'QACDS' and 'CASH & CASH INVESTMENTS'

grep -n "currentBalances\|cashBalance\|CASH_MANUAL" utils/schwab_client.py
    EXPECT: balances read ~196-197, cash row appended ~281. Record actual lines.

grep -rn "CASH_MANUAL" utils tasks core manager.py --include=*.py
    Record EVERY consumer. This is the blast radius of any change to the cash row.

grep -n "TAB_INCOME_TRACKING\|read_income" utils/sheet_readers.py tasks/*.py
    EXPECT a reader, no writer. Confirm.

sed -n '429,500p' utils/schwab_client.py
    Record how _fetch_account_transactions windows its date range, and whether it
    already passes transaction_types.
```

### 0.2 The live cash probe — this decides the phase

Write `scripts/probe_cash_balances_2026-08-25.py`. **Read-only. No Sheet writes. No
`--live` flag, because it writes nothing outside `agent_outputs/`.**

For each of the three allowlisted accounts, dump the **complete** `currentBalances` and
`initialBalances` objects, plus every position whose symbol is in
`PURE_CASH_SWEEP_TICKERS`, to
`agent_outputs/schwab_probe/cash_balances_2026-08-25.json`, and print a table:

| Account (masked) | cashBalance | moneyMarketFund | cashAvailableForTrading | availableFunds | totalCash | liquidationValue | longMarketValue | QACDS position marketValue |
|---|---|---|---|---|---|---|---|---|

Then compute and print, per account and in total:

```
A = cashBalance  (what the code uses today)
B = sum of marketValue for skipped PURE_CASH_SWEEP_TICKERS positions
C = moneyMarketFund (if the field exists)
D = liquidationValue - longMarketValue   (an independent cross-check on cash)
```

**The verdict, stated explicitly in your report:**

- If `B` is ~0 and `A ≈ D`, the current assumption holds. Cash is complete. Say so
  plainly and skip Step 1's remediation — but still do Step 1's field widening, because
  the other balance fields are useful regardless.
- If `B` is materially non-zero and `A + B ≈ D`, **the sweep is being dropped**. That is
  a live defect understating total portfolio value by `B`. Report the dollar figure.
- If nothing reconciles, report the numbers and **STOP**. Do not guess a formula. A cash
  figure invented to make an equation balance is worse than the current one.

Cite `liquidationValue` as the reference total in whichever direction the evidence runs —
it is Schwab's own account total and does not depend on this repo's assumptions.

### 0.3 Sign-off gate

**Present the probe table and the verdict to Bill. Stop. Do not proceed to Step 1 until
he accepts the reading.** If the sweep is being dropped, the size of the correction is a
number he needs to see before any downstream weight moves.

---

## Step 1 — Widen balance capture

Add to `utils/schwab_client.py`:

```python
def fetch_account_balances(client: "schwab.client.Client") -> pd.DataFrame:
    """
    One row per allowlisted account, full cash/liquidity picture.
    Columns: account_masked, tax_treatment, cash_balance, money_market_fund,
             cash_available_for_trading, available_funds, total_cash,
             long_market_value, liquidation_value, as_of_utc
    Fields absent from a given account's payload are None, never 0.0.
    """
```

Uses the accounts client, honours `_require_account_scope()`, and reuses
`_is_primary_account()` and `_classify_tax_treatment()` — do not write a fourth copy of
the masking logic.

Then, **only if Step 0.3 confirmed a gap**, correct the cash figure in
`fetch_positions()`:

- Change the cash total to whatever Step 0's evidence supports (most likely
  `cashBalance + moneyMarketFund`, or `cashBalance` plus the sweep positions' market
  value — pick the one the probe actually validated, and cite the probe file in a code
  comment).
- Keep the row's ticker as `CASH_MANUAL`. **Do not rename it.** Step 0.1 enumerated its
  consumers; renaming a key that many modules read is a separate, larger change and is
  not authorised here.
- Add a one-line INFO log stating the composition: `cash $X = cashBalance $Y +
  moneyMarketFund $Z across N accounts`.
- Emit a reconciliation warning whenever
  `abs((cash + long_market_value) - liquidation_value) > $1.00`, naming all three
  figures. This is a standing integrity check, not a one-off.

---

## Step 2 — Typed transaction fetch

Extend `_fetch_account_transactions()` / `fetch_transactions()` to accept an optional
`transaction_types` argument passed through to the Schwab call. **Default `None`
preserves today's behaviour exactly** — existing callers must be untouched and
unaffected.

Constraints to respect and to state in the docstring:

- The endpoint caps at roughly a **60-day** window per call. Any longer range must be
  chunked, with the chunk boundaries logged. History is build-once-then-append; do not
  design anything that requires re-pulling years on every run.
- **Do not re-sync the live `Transactions` tab unfiltered.** That undoes the 2026-08-03
  account scope fix. New data in this phase goes to new surfaces only.

---

## Step 3 — `Income_Tracking` writer

New `tasks/build_income_tracking.py`. Fills the tab that has had a reader and no writer
since at least May 2026.

Source: `fetch_transactions(transaction_types=[DIVIDEND_OR_INTEREST])` over the
allowlisted accounts, plus `Est Annual Income` already captured per position in
`fetch_positions()`.

Two blocks in one tab:

**Block A — realised income by ticker and period**

| Ticker | Account | Pay Date | Type (dividend / interest / cap gain distribution) | Gross | Tax Treatment | Source |
|---|---|---|---|---|---|---|

**Block B — trailing summary**

| Ticker | TTM Income | Current Position Value | TTM Yield on Value | Est Forward Annual Income | Share of Portfolio TTM Income |
|---|---|---|---|---|---|

Rules:

- Facts only. No yield projections beyond Schwab's own `estimatedAnnualIncome`, no
  "attractive yield" language, no recommendations. Hard Rule 4 applies to computed views
  as much as to agent prose.
- Schwab's transaction payload does not always cleanly distinguish qualified from
  non-qualified dividends. **Do not infer that distinction.** Carry a `Qualified` column
  only if the payload supports it; otherwise omit the column and say why in the tab
  header line. A guessed qualified/non-qualified split feeding a tax view is worse than
  no column.
- Tag every row's source account tax treatment — income in `tax_deferred` accounts is a
  different animal from taxable income, and `Tax_Control` consumers will care.
- Archive-before-overwrite; single batch write; `--live` required.
- CLI: `pm build income-tracking [--live] [--days 400]`.

**Mid-prompt sign-off gate:** print the full proposed tab contents as a table and stop.
Bill accepts, overrides, or rejects before the first `--live` write.

---

## Step 4 — Contribution / withdrawal ledger

This is the piece that makes performance measurement honest.

`Daily_Snapshots` records portfolio value over time. Without a record of external cash
flows, a rise in value cannot be told apart from a deposit. Every performance figure the
system can currently produce conflates the two.

New `tasks/build_flow_ledger.py`, writing a **new** tab `Cash_Flows`:

| Date | Account | Type (ACH_RECEIPT / ACH_DISBURSEMENT / WIRE_IN / WIRE_OUT / JOURNAL / CASH_RECEIPT / CASH_DISBURSEMENT) | Amount (signed, + into portfolio) | Description | Transaction ID | Fingerprint |
|---|---|---|---|---|---|---|

- `JOURNAL` needs care: a journal between two **allowlisted** accounts is internal and
  nets to zero — it must be flagged `internal` and excluded from external-flow totals. A
  journal from an allowlisted account to one of the three descoped accounts
  (`...4151`, `...0217`, `...9753`) **is** an external flow from this system's point of
  view. Detect this by matching both legs where the payload permits; where it does not,
  mark the row `unclassified` and surface the count. Do not guess.
- Append-only with fingerprint dedup, same pattern as `Trade_Log`.
- `--live` required; archive-before-overwrite.
- CLI: `pm build cash-flows [--live] [--days 90] [--backfill-from YYYY-MM-DD]`.
- Register `Cash_Flows` in `config.py` as `TAB_CASH_FLOWS` and **document it in
  `PORTFOLIO_SHEET_SCHEMA.md`** — that file is already materially incomplete (10 tabs
  documented against 20+ defined) and this phase must not widen the gap.

**Explicitly out of scope:** computing TWR or IRR. This phase builds the input the
calculation needs. Whether Bill wants a return figure, and which one, is his call and a
separate prompt. Do not build it because it is now possible.

---

## Step 5 — Retire or rewrite Analysis Rule 1

**Only if Step 0.3 and Step 1 together establish that the cash figure is complete and
reconciles to `liquidationValue`.** If they do not, skip this step entirely and record
why.

The rule currently reads, in substance: *"Never infer liquidity posture from this export.
`CASH_MANUAL` does not represent the cash position. Do not compute a cash percentage or
draw conclusions about dry powder. Ask instead."*

Proposed replacement, to be presented for approval, not applied unilaterally:

> **Cash is now sourced from Schwab account balances across the three allowlisted
> accounts and reconciles to Schwab's own `liquidationValue`.** A cash percentage
> computed against the bundle total is therefore meaningful *for those three accounts*.
> It is still not Bill's total liquidity — three further accounts are out of scope, and
> strategic dry powder may sit outside Schwab entirely. State the scope whenever citing
> a cash figure; do not extrapolate to net worth.

Locations to change, both of them, in the same commit:

1. `tasks/export_ai_briefing.py` → `PROMPT_PAYLOAD` — **authoritative**
2. `CLAUDE.md` → Analysis Rules → rule 1 — the summary

The summary in `CLAUDE.md` drifting from `PROMPT_PAYLOAD` is exactly the failure mode the
Analysis Rules section was written to prevent. Change both or neither.

**Sign-off gate:** present both diffs. Stop. Bill approves the wording before it ships.

---

## Post-build verification checklist

Literal stdout/stderr for every row.

| # | Check | Evidence required |
|---|---|---|
| 1 | Order endpoints absent | `grep -rnE "place_order\|replace_order\|cancel_order\|get_orders" utils tasks core manager.py scripts` → zero |
| 2 | Cash probe | Full probe table, all three accounts, all balance fields, plus the A/B/C/D verdict |
| 3 | Reconciliation | `cash + long_market_value` vs `liquidation_value` per account, delta under $1.00 or explained |
| 4 | Cash delta | If corrected: old total vs new total, in dollars, and the resulting change to the largest five position weights |
| 5 | Ceiling impact | Whether any style-ceiling flag changes state as a result of a new denominator — list every affected ticker |
| 6 | Backwards compatibility | `fetch_transactions()` with no `transaction_types` returns a frame identical to pre-change; show row counts and a hash |
| 7 | 60-day chunking | A 400-day fetch showing chunk boundaries in the log and no gaps at the seams |
| 8 | `Income_Tracking` dry run | Full proposed tab, both blocks, printed before any write |
| 9 | `Income_Tracking` live | `pm build income-tracking --live` stdout, plus a read-back of the tab through `read_gsheet_robust()` proving no zeroed currency cells |
| 10 | Qualified-dividend honesty | Explicit statement of whether the payload supports the distinction, and what you did about it |
| 11 | `Cash_Flows` dry run | Full proposed ledger; internal journals flagged; `unclassified` count stated |
| 12 | `Cash_Flows` live + dedup | `--live` twice in a row; second run adds zero rows |
| 13 | Schema doc | `PORTFOLIO_SHEET_SCHEMA.md` diff showing `Cash_Flows` and `Income_Tracking` documented |
| 14 | Rule 1 | Both diffs (`PROMPT_PAYLOAD` and `CLAUDE.md`), or a recorded reason for skipping |
| 15 | Pipeline intact | `pm morning --skip-export` dry run, full stdout, no traceback, STEP sequence unchanged |

---

## What this phase explicitly does NOT do

- Does not compute TWR, IRR, or any return figure.
- Does not rename `CASH_MANUAL`.
- Does not change the account allowlist or touch the three descoped accounts.
- Does not write to `Risk_Metrics` — that is Phase 4.
- Does not re-sync the `Transactions` tab.
- Does not infer qualified vs non-qualified dividend status.

---

## Documentation to update on completion

- `CHANGELOG.md` — dated entry; if a cash gap was found, record the dollar figure and the
  date range over which it was understated
- `state.md` — Known Issues entry resolved or added, depending on the verdict
- `CLAUDE.md` — Analysis Rule 1 (if Step 5 ran), plus `fetch_account_balances` in Key Files
- `PORTFOLIO_SHEET_SCHEMA.md` — `Cash_Flows` and `Income_Tracking`
