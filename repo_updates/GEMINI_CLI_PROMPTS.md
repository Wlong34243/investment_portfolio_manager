# Gemini CLI Prompts — Streamlit → CLI Migration
## Sheet-side verifications and edits

**How to use this file**

Run these from the PersonalSpending repo root with Gemini CLI. They are intentionally minimal — most of the migration is local repo work, not Sheet work. Use these to verify Sheet state before each Claude Code prompt and to make small Sheet edits the CLI cutover requires.

**Tooling split (firm rule):**
- Sheet structure (tab creation, headers, schema verification) → **Gemini CLI**
- Local repo files (manager.py, utils/, etc.) → **Claude Code**

**Pre-flight setup (one time per Gemini session):**

```
/autoctx:bootstrap
```

Then ensure GEMINI.md has been read into context (Gemini does this automatically when present).

---

## Prompt G0 — Sheet state verification (before M1)

**Goal:** Confirm both sheets are in the state the CLI assumes.
**Risk:** None (read-only).

```
Read-only audit of the Personal Expense Tracker Google Sheets.

EXPENSE SHEET (id: 1RHMXajMrP9CrOyndnO24Tvv4tjiJqwhX3I5uvfjGXp0)
For each tab below, list the headers in row 1 and the row count:
  - Clean_Transactions
  - Reference_Rules
  - Budget_Rollup
  - Budget_Targets
  - Fixed_Expenses
  - Expenses
  - Amazon_Feed
  - Flagged_Items
  - Transaction_Ledger
  - System_Logs

DASHBOARD SHEET (id: 1dK0UvujD8xRGkiZRjuFroPcuhyheUNgrCQGvuEk3dO0)
For each tab below, list the headers in row 1 and the row count:
  - Transaction_Detail
  - Summary
  - Monthly_Trends
  - Variance_Summary
  - Amazon_Enrichment (may not exist yet)

VALIDATION
- Confirm Clean_Transactions row 1 contains: date, vendor, description, amount,
  category, source, transaction_id, Dist_Status, Notes, Capital_Flag
  (order matters for downstream code, but content-based detection means small
  reorderings are OK — flag any missing column.)
- Confirm Transaction_Detail has columns G and H present (formula columns).
  Read row 2 of column G; if blank, flag as "formula seed missing."

OUTPUT
A markdown report listing every tab, its headers, its row count, and any
discrepancies. Do not write to any sheet.
```

---

## Prompt G1 — System_Logs entry for migration start

**Goal:** Mark the migration cutover in the persistent log tab.
**Risk:** Low (single append).

```
Append one row to System_Logs in the Expense Sheet recording the start of the
Streamlit-to-CLI migration.

Row contents (use batch_update or append_row, value_input_option='USER_ENTERED'):
  Column A (timestamp): now in YYYY-MM-DD HH:MM:SS format
  Column B (phase):     'MIGRATION'
  Column C (level):     'INFO'
  Column D (message):   'CLI migration M1 scaffold starting. Streamlit remains active in parallel.'
  Column E (run_id):    a fresh uuid4 string

Do not modify any other tab. Confirm the row was written by reading back the
last row of System_Logs.
```

---

## Prompt G2 — System_Logs entry for cutover (run before M5)

**Goal:** Mark Streamlit deprecation in the persistent log.
**Risk:** Low (single append).

```
Append one row to System_Logs in the Expense Sheet recording the Streamlit
deprecation cutover.

Row contents:
  timestamp: now in YYYY-MM-DD HH:MM:SS
  phase:     'MIGRATION'
  level:     'INFO'
  message:   'CLI migration M5 cutover. Streamlit moved to _deprecated/. CLI is sole interface.'
  run_id:    fresh uuid4

Confirm by reading back the last row.
```

---

## Prompt G3 — Post-cutover sheet verification (run after M5)

**Goal:** Confirm sheet state is healthy after Streamlit deprecation.
**Risk:** None (read-only).

```
Read-only verification after CLI cutover.

1. Read the last 5 rows of Clean_Transactions in the Expense Sheet.
   Confirm at least one row has Dist_Status = TRUE — proves the CLI
   distribute command wrote successfully.

2. Read the last 5 rows of Transaction_Detail in the Dashboard Sheet.
   Confirm dates are recent (within last 60 days).

3. Read Variance_Summary in full.
   Confirm at least one row exists for the most recent month.

4. Read the last 10 rows of System_Logs.
   Confirm the most recent rows have phase 'PHASE_1_4' or 'PHASE_5'
   (proving the CLI has been writing logs through the same code path).
   Confirm no recent rows reference 'STREAMLIT' or similar.

OUTPUT
Pass/fail per check, with any anomalies flagged. Do not write to any sheet.
```

---

## Prompt G-AppScript-Reminder (informational only)

**Note:** This is NOT a Gemini CLI prompt. It's a reminder that the AppScript
Amazon parser (if currently active) is independent of the migration. It does not
need to be touched at any phase. If Bill chose to disable Amazon email parsing
per the 2026-03-22 design decision, the AppScript trigger should already be
disabled and `Amazon_Feed` is read-only for reference. No action required for
the CLI migration.
