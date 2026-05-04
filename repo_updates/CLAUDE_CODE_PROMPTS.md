# Claude Code Prompts — Streamlit → CLI Migration
## Personal Expense Tracker (PersonalSpending repo)

**How to use this file**

Each prompt is self-contained. Paste one into Claude Code (in the repo root), let it execute fully in automode, then commit before moving on. **Do not run two prompts back-to-back without a commit and a manual sanity check between them.** Sequence is enforced — later prompts assume earlier prompts succeeded.

**Tooling split (firm rule):**
- These prompts → **Claude Code** (local repo only)
- Anything touching Google Sheets structure → **Gemini CLI** (see `GEMINI_CLI_PROMPTS.md`)
- Never aim Claude Code at the Sheets API surface for tab creation / schema changes.

**Pre-check pattern used in every prompt:**
1. Read the listed files first.
2. Verify the listed assumptions before writing any code.
3. Run the listed validation command after writing.
4. Stop and surface anything that doesn't match. Never paper over a mismatch.

---

## Prompt M0 — Pre-flight verification (read-only)

**Goal:** Confirm the repo is in the state these prompts assume before any changes.
**Tool:** Claude Code
**Risk:** None (read-only)
**Pre-checks:** None
**Constraints:** Make no code changes. Output is a status report only.

```
Run a read-only audit of the PersonalSpending repo and produce a status report.

1. Read the following files in full:
   - app.py
   - pipeline.py
   - config.py
   - variance_sheets.py
   - variance_tab.py
   - amazon_enricher.py
   - utils/type_utils.py
   - requirements.txt
   - CLAUDE.md
   - CHANGELOG.md
   - README.md (if present)

2. For each of the following functions, confirm it exists and report its
   exact signature (file, line number, parameters):
   - pipeline.phase1_collect
   - pipeline.phase2_categorize
   - pipeline.phase3_validate
   - pipeline.phase4_publish
   - pipeline.phase5_distribute
   - pipeline.detect_stale_categories
   - pipeline.log_to_system_logs
   - pipeline.load_fixed_expenses
   - pipeline.generate_fixed_expense_rows
   - pipeline.dedup_manual_vs_bank
   - variance_sheets.write_variance_to_sheets
   - amazon_enricher.run_amazon_csv_enrichment
   - amazon_enricher.run_amazon_enrichment

3. Confirm the following are present in config.py:
   - EXPENSE_SHEET_ID
   - DASHBOARD_SHEET_ID
   - CLEAN_TXN_COLUMNS (list)
   - CATEGORY_ALIASES (dict)
   - VALID_DASHBOARD_CATEGORIES (set)
   - All TAB_* constants

4. Run: python -c "import ast; ast.parse(open('pipeline.py').read())"
   Then the same for app.py, config.py, variance_sheets.py, variance_tab.py,
   amazon_enricher.py. Report any parse failures.

5. Produce a single markdown report at the end with:
   - All function signatures found
   - Anything missing or unexpected
   - A go / no-go verdict for proceeding to M1

Do not modify any file. Do not create any file.
```

---

## Prompt M1 — Scaffold CLI alongside Streamlit

**Goal:** Add `manager.py`, console-script registration, auth helper, console helper, runs/ directory. Streamlit must remain runnable.
**Tool:** Claude Code
**Risk:** Low (additive only)
**Pre-checks:** M0 returned a go verdict.
**Constraints:** Do not delete or modify app.py, variance_tab.py, pipeline.py, variance_sheets.py, config.py, or amazon_enricher.py. Additive changes only.

```
Scaffold the CLI alongside the existing Streamlit app. Do not modify app.py,
pipeline.py, config.py, variance_sheets.py, variance_tab.py, or amazon_enricher.py
in this prompt — additive changes only.

PRE-READ
1. Read in full: app.py, config.py, requirements.txt, CLAUDE.md
2. Confirm utils/ directory exists with type_utils.py inside.
3. Confirm pyproject.toml does NOT exist yet. If it does, stop and report.

WORK

A. Create utils/auth.py
   - Function: get_sheets_client() -> gspread.Client
   - Loads credentials in this priority order:
     1. Environment variable GOOGLE_APPLICATION_CREDENTIALS (path to JSON file)
     2. ./.secrets/gcp_service_account.json (relative to repo root)
     3. ~/.config/personal-expense-tracker/gcp.json
   - Raises a clear FileNotFoundError listing all three paths checked if none found.
   - Uses scopes: https://spreadsheets.google.com/feeds and
     https://www.googleapis.com/auth/drive
   - Caches the client at module level (single client per process).
   - No Streamlit imports. No st.cache_resource. Pure function.

B. Create utils/console.py
   - Initializes a single rich.console.Console() at module level: `console`
   - Helper: print_table(rows, headers, title=None) — prints a rich Table
   - Helper: status(msg) — context manager wrapping console.status()
   - Helper: success(msg), warn(msg), error(msg) — colored prefixes
   - Helper: confirm(msg, default=False) — wraps typer.confirm
   - No emojis in any output string.

C. Create utils/run_log.py
   - Function: new_run_dir(phase: str) -> Path
     Creates ./runs/<YYYY-MM-DD_HHMMSS>_<phase>_<short_uuid>/ and returns the path.
   - Function: tee_stdout(run_dir: Path, log_name: str) -> context manager
     Captures stdout to BOTH the terminal and run_dir/<log_name>.log simultaneously.
     Uses contextlib.redirect_stdout combined with a tee writer class.
   - Function: archive_dataframe(df, run_dir: Path, name: str)
     Writes df to run_dir/<name>.csv with date-stamped header comment.

D. Create manager.py at repo root
   - Imports: typer, from utils.console import console, success, warn, error
   - Creates: app = typer.Typer(no_args_is_help=True, add_completion=False)
   - Add ONE command for now: `health`
       - Calls utils.auth.get_sheets_client()
       - Opens config.EXPENSE_SHEET_ID and config.DASHBOARD_SHEET_ID
       - Lists worksheet titles from each
       - Prints a green "OK" line per sheet, red "FAIL" with the exception otherwise
       - Exits 0 on full success, 1 on any failure
   - At bottom: if __name__ == "__main__": app()

E. Create pyproject.toml at repo root
   - [build-system] requires setuptools, build-backend setuptools.build_meta
   - [project] name = "personal-expense-tracker", version = "0.5.0",
     requires-python = ">=3.11"
   - dependencies = ["gspread", "google-auth", "pandas", "numpy",
     "typer[all]", "rich", "plotly"]  (keep plotly for now; remove at M5)
   - [project.scripts] pet = "manager:app"
   - [tool.setuptools] py-modules = ["manager", "pipeline", "config",
     "variance_sheets", "variance_tab", "amazon_enricher"]
   - [tool.setuptools.packages.find] where = ["."], include = ["utils*"]

F. Update .gitignore
   - Append (only if not already present):
     /runs/
     /.secrets/
     *.egg-info/
     build/
     dist/

G. Create runs/.gitkeep so the directory exists in the repo.

H. Create state.md at repo root with this exact content:
   # state.md — Personal Expense Tracker scratchpad
   ## Current focus
   CLI migration — Phase M1 complete, M2 next
   ## Working conclusions
   - Streamlit app remains runnable in parallel through M4
   - `pet` console script registered; `pet health` is the smoke test
   - Credentials: GOOGLE_APPLICATION_CREDENTIALS env var preferred
   ## Next steps
   - Run M2: implement `pet ingest`

I. Create GEMINI.md at repo root with this exact content:
   # GEMINI.md — Personal Expense Tracker
   ## Identity
   You operate inside the PersonalSpending repo. Five-phase pipeline
   (Collector → Categorizer → Validator → Publisher → Feeder) ingests Chase
   CSVs into Google Sheets. CLI-only frontend.
   ## Core invariants (non-negotiable)
   - DRY_RUN default true. Writes require explicit --live.
   - Phases 1–4 and Phase 5 NEVER chain automatically.
   - Business logic lives in Sheets (Reference_Rules, Budget_Rollup).
   - All Sheets writes via batch_update().
   - Idempotency via MD5 fingerprint, dual-ledger dedup.
   - No emojis in code, logs, or docs.
   - Sheets is the authoritative frontend. CLI is the operator console.
   - No Streamlit. No web UI. No PWA.
   ## Tooling split
   - Claude Code → local repo only
   - Gemini CLI → Sheets operations and read-only verification
   ## When in doubt
   Read CLAUDE.md, DASHBOARD_SCHEMA.md, CLI_MIGRATION_PLAN.md, then ask.

VALIDATION (run before declaring done)
1. python -c "import ast; ast.parse(open('manager.py').read())"
2. python -c "import ast; ast.parse(open('utils/auth.py').read())"
3. python -c "import ast; ast.parse(open('utils/console.py').read())"
4. python -c "import ast; ast.parse(open('utils/run_log.py').read())"
5. python -c "from manager import app; print('manager.py imports OK')"
6. Confirm streamlit run app.py would still work — do NOT actually run it,
   but confirm app.py is unchanged via `git diff --stat app.py` (should be empty).

OUTPUT
A summary listing every file created and the validation results. If any
validation step fails, stop and report; do not "fix forward."
```

---

## Prompt M2 — `pet ingest` command (Phases 1–4)

**Goal:** Replace the Streamlit Upload tab. Same pipeline, different driver.
**Tool:** Claude Code
**Risk:** Medium — first command that calls into the live pipeline.
**Pre-checks:** M1 committed and `pet health` works.
**Constraints:** No changes to pipeline.py phase functions. Caller-side wiring only.

```
Implement the `pet ingest` command, replacing the Streamlit Upload tab.
Do not modify pipeline.py phase function signatures. The driver lives entirely
in manager.py.

PRE-READ
1. app.py — focus on the run_pipeline() function and the Upload tab block
2. pipeline.py — confirm signatures of phase1_collect, phase2_categorize,
   phase3_validate, phase4_publish, detect_stale_categories, log_to_system_logs
3. utils/run_log.py and utils/console.py from M1
4. config.py — confirm CLEAN_TXN_COLUMNS

WORK

In manager.py, add this command:

@app.command()
def ingest(
    file_7588: Path = typer.Argument(..., exists=True, readable=True,
                                     help="Path to Chase 7588 (checking) CSV"),
    file_2433: Path = typer.Argument(..., exists=True, readable=True,
                                     help="Path to Chase 2433 (credit card) CSV"),
    live: bool = typer.Option(False, "--live",
                              help="Write to Clean_Transactions. Default is dry-run."),
):
    """
    Run Phases 1-4: Collect, Categorize, Validate, Publish.
    Default is DRY-RUN (no Sheets writes). Pass --live to commit.
    Phase 5 (distribute) is a separate command and never runs automatically.
    """

Implementation requirements:

1. Create a run directory via utils.run_log.new_run_dir("ingest")
2. Read both CSVs into bytes (open(path, 'rb').read())
3. Get the gspread client via utils.auth.get_sheets_client()
4. Inside utils.run_log.tee_stdout(run_dir, "phase14"):
   a. Call pipeline.phase1_collect(file_7588=bytes_7588, file_2433=bytes_2433,
      sheets_client=gc)
   b. Call pipeline.phase2_categorize(df, sheets_client=gc)
   c. Call pipeline.phase3_validate(df, sheets_client=gc)
   d. Call pipeline.phase4_publish(df, sheets_client=gc, dry_run=not live)
   e. Call pipeline.detect_stale_categories(gc) and archive result to
      run_dir/stale.csv if non-empty
5. Archive the final df via utils.run_log.archive_dataframe(df, run_dir, "phase14_result")
6. After the pipeline runs, print a Rich table summary with these counts:
   - Total rows
   - Categorized
   - Uncategorized (category == '')
   - Transfers (category == 'TRANSFER')
   - Ignored (category == 'IGNORED')
   - Reconciled (category == 'RECONCILED')
   - Total absolute dollar amount
7. If uncategorized > 0, print a separate Rich table of those rows
   (date, vendor, description, amount, source) and warn the operator to
   add keywords to Reference_Rules before running --live again.
8. If --live, call pipeline.log_to_system_logs(gc, "PHASE_1_4", "INFO", ...)
   at start and complete; "ERROR" on exception.
9. On exception, write traceback to run_dir/error.log, print red error message,
   exit code 1.
10. On success, print the run_dir path so the operator knows where logs are.

Do not implement Phase 5 calls. Do not auto-chain. The function returns nothing
and only writes to Clean_Transactions if --live.

VALIDATION
1. python -c "import ast; ast.parse(open('manager.py').read())"
2. python -c "from manager import app; print('OK')"
3. Run: python manager.py ingest --help
   Confirm the help text shows file_7588, file_2433, --live.
4. Run a dry-run against the sample CSVs in /mnt/project/ if accessible:
   python manager.py ingest /mnt/project/Chase7588_Activity_7months.CSV \
                            /mnt/project/Chase2433_ActivityLstYrTOMarch.csv
   (No --live flag.) Confirm:
   - A runs/ subdirectory was created
   - phase14.log exists inside it
   - phase14_result.csv exists
   - The summary table printed to terminal
   - Exit code is 0

OUTPUT
Summary of files modified, validation results, and the path of the run directory
created during the validation dry-run.
```

---

## Prompt M3 — `pet review` and `pet distribute`

**Goal:** Replace Review tab and ▶ Run tab. Phase 5 gate stays intact.
**Tool:** Claude Code
**Risk:** Medium — `pet distribute --live` is the destructive command.
**Pre-checks:** M2 committed; `pet ingest` dry-run works.
**Constraints:** Phase 5 must require explicit confirmation when --live; no chaining ever.

```
Add `pet review` and `pet distribute` commands. Phase 5 must remain a hard
human-in-the-loop gate.

PRE-READ
1. pipeline.py: phase5_distribute signature
2. config.py: TAB_CLEAN_TRANSACTIONS, TAB_FLAGGED_ITEMS
3. app.py: the Run tab block (the existing Phase 5 gate UX)
4. utils/run_log.py from M1

WORK

A. In manager.py, add:

@app.command()
def review(
    stale_only: bool = typer.Option(False, "--stale", help="Show stale categorizations only"),
    export_csv: bool = typer.Option(False, "--csv", help="Also write tables to runs/<id>/review.csv"),
):
    """
    Print pending Clean_Transactions rows (Dist_Status = FALSE) and any
    stale categorizations. Read-only — no Sheets writes.
    """

Implementation:
1. Create run_dir via new_run_dir("review")
2. Get gspread client.
3. Open EXPENSE_SHEET_ID, read TAB_CLEAN_TRANSACTIONS via
   pipeline.sheets_read_with_retry().
4. Filter rows where the column matching 'dist_status' (case-insensitive,
   header-detected) is exactly the string 'FALSE'.
5. Build a Rich table: date, vendor, amount, category, source. Print it with a
   header "Pending rows: N".
6. Identify uncategorized rows in the same pending set (category empty string).
   Print a separate red-titled Rich table for them.
7. Call pipeline.detect_stale_categories(gc). Print a third table if non-empty.
8. If --stale, suppress the first two tables; show only stale.
9. If --csv, write each non-empty table to run_dir/<name>.csv.
10. Exit 0.

B. In manager.py, add:

@app.command()
def distribute(
    live: bool = typer.Option(False, "--live", help="Commit Phase 5 writes."),
    year: Optional[int] = typer.Option(None, "--year",
        help="Override target year. Default = current year."),
    yes: bool = typer.Option(False, "--yes",
        help="Skip the interactive confirmation. Use only in scripts."),
):
    """
    Run Phase 5: distribute pending Clean_Transactions rows to Transaction_Detail
    and copy them to Transaction_Ledger. Default is DRY-RUN. --live commits.
    Requires explicit confirmation when --live unless --yes is set.
    """

Implementation:
1. If year is None, year = datetime.now().year.
2. Create run_dir via new_run_dir("distribute").
3. Get gspread client.
4. Read Clean_Transactions, count rows where Dist_Status = FALSE for the target
   year. If count == 0, print "Nothing to distribute" in green and exit 0.
5. Print a confirmation summary table:
     Year:           {year}
     Pending rows:   {count}
     Mode:           DRY-RUN | LIVE
     Run dir:        {run_dir}
6. If live and not yes:
     Use console.confirm(
       f"About to distribute {count} row(s) to Transaction_Detail and "
       f"Transaction_Ledger for year {year}. This is a permanent write. Continue?",
       default=False
     )
     If confirmation is False, print "Aborted" in yellow and exit 0.
7. Inside utils.run_log.tee_stdout(run_dir, "phase5"):
     Call pipeline.phase5_distribute(
       expense_gc=gc,
       dashboard_gc=gc,
       dry_run=not live,
       target_year=year,
     )
8. If live, call pipeline.log_to_system_logs(gc, "PHASE_5", "INFO", ...)
   at start and complete; "ERROR" on exception.
9. On exception, write traceback to run_dir/error.log, exit 1.
10. On success, print run_dir path.

C. Add `from typing import Optional` and `from datetime import datetime` to
   manager.py imports if not already present.

D. NEVER call phase5_distribute() from inside the `ingest` command, regardless
   of any flag, env var, or config setting. The two commands are separate by
   design and that separation is non-negotiable.

VALIDATION
1. python -c "import ast; ast.parse(open('manager.py').read())"
2. python manager.py review --help
3. python manager.py distribute --help
4. Run: python manager.py review
   Confirm: tables printed (or empty-state message), no Sheet writes happened
   (verify via gspread or log inspection that no batch_update was called from
   the review path — review must be 100% read-only).
5. Run: python manager.py distribute (no --live)
   Confirm: dry-run summary printed, no confirmation prompt (because not --live),
   phase5.log created, no Sheet writes.

OUTPUT
Summary of files modified and the four validation outputs (--help for both
commands plus dry-run output).
```

---

## Prompt M4 — `pet variance`, `pet amazon enrich`, `pet rules`, `pet logs`

**Goal:** Cover the remaining Streamlit tabs and add operator quality-of-life commands.
**Tool:** Claude Code
**Risk:** Low — most are read-only or call existing functions.
**Pre-checks:** M3 committed.
**Constraints:** No new pipeline logic. Wire to existing functions only.

```
Add `pet variance`, `pet amazon`, `pet rules`, and `pet logs` commands.
Wire to existing functions only — no new pipeline logic.

PRE-READ
1. variance_tab.py — note which functions read which tabs
2. variance_sheets.py — confirm write_variance_to_sheets signature
3. amazon_enricher.py — confirm run_amazon_csv_enrichment signature
4. config.py — TAB_VARIANCE_SUMMARY, TAB_FLAGGED_ITEMS, TAB_REFERENCE_RULES

WORK

A. `pet variance` (read-only)

@app.command()
def variance(
    month: Optional[str] = typer.Option(None, "--month",
        help="Filter to YYYY-MM (e.g. 2026-04). Default: all months."),
):
    """
    Print the Variance_Summary scorecard and Flagged_Items table.
    Read-only — never writes.
    """

Implementation:
1. Read TAB_VARIANCE_SUMMARY from DASHBOARD_SHEET_ID.
2. If --month, filter rows where the Month column matches.
3. Print a Rich table with columns: Month, Actual, Baseline, Variance,
   Adj Variance, Status. Color the Variance and Adj Variance columns:
   green when <= 0, red when > 0.
4. Read TAB_FLAGGED_ITEMS from EXPENSE_SHEET_ID.
5. Print a second Rich table with all columns.
6. If either tab is empty, print a yellow "no data" message instead.

B. `pet amazon enrich`

amazon_app = typer.Typer(no_args_is_help=True)
app.add_typer(amazon_app, name="amazon")

@amazon_app.command("enrich")
def amazon_enrich(
    orders_csv: Path = typer.Argument(..., exists=True, readable=True,
        help="Path to Amazon Order History CSV export."),
    live: bool = typer.Option(False, "--live", help="Commit writes."),
):
    """
    Match Amazon Order History items to Chase 2433 transactions and append
    to the Amazon_Enrichment tab. Default is dry-run.
    """

Implementation:
1. Create run_dir via new_run_dir("amazon_enrich")
2. Get gspread client.
3. Inside tee_stdout, call:
     amazon_enricher.run_amazon_csv_enrichment(
       csv_path=str(orders_csv),
       sheets_client=gc,
       dry_run=not live,
     )
4. If the function signature differs from above (verify via PRE-READ),
   adapt to the actual signature and report the adaptation in your output.
5. Print run_dir path on completion.

C. `pet rules` group

rules_app = typer.Typer(no_args_is_help=True)
app.add_typer(rules_app, name="rules")

@rules_app.command("list")
def rules_list():
    """Print all rows from Reference_Rules in the Expense Sheet."""

Implementation:
1. Read TAB_REFERENCE_RULES.
2. Print as a Rich table with columns: Keyword, Category, Ignore_Flag, Notes.

@rules_app.command("check")
def rules_check(
    description: str = typer.Argument(..., help="Transaction description to test."),
):
    """
    Test what category a given description would resolve to under the
    current Reference_Rules. Read-only.
    """

Implementation:
1. Read Reference_Rules.
2. Apply the same matching logic the pipeline uses (TRANSFER pre-scan,
   Amazon fast-path stub, then standard keyword scan).
3. Print: input description, matched keyword (or "no match"), resolved
   category, ignore_flag.

D. `pet logs` group

logs_app = typer.Typer(no_args_is_help=True)
app.add_typer(logs_app, name="logs")

@logs_app.command("list")
def logs_list(
    n: int = typer.Option(10, "--n", help="Number of recent runs to list."),
):
    """List the N most recent run directories under ./runs/."""

@logs_app.command("tail")
def logs_tail(
    phase: Optional[str] = typer.Option(None, "--phase",
        help="Filter to ingest|distribute|amazon_enrich|review."),
):
    """Print the contents of the most recent run's main log file."""

Implementation for `tail`:
1. Glob ./runs/* sorted by modification time, descending.
2. If --phase, filter directories whose name contains the phase token.
3. Find the *.log file in the most recent matching directory and print it.

VALIDATION
1. python -c "import ast; ast.parse(open('manager.py').read())"
2. python manager.py --help    (confirm all subcommands appear)
3. python manager.py variance --help
4. python manager.py amazon enrich --help
5. python manager.py rules list --help
6. python manager.py rules check "TRADER JOE'S #123"
7. python manager.py logs list

OUTPUT
Files modified, validation results, and a screenshot-equivalent of
`pet --help` showing the full command tree.
```

---

## Prompt M5 — Cutover (deprecate Streamlit)

**Goal:** Move app.py and variance_tab.py into _deprecated/, remove Streamlit deps, update README and CLAUDE.md.
**Tool:** Claude Code
**Risk:** High — first prompt that breaks Streamlit. Run only after one full month of CLI-only operation.
**Pre-checks:** Bill confirms one full monthly cycle (ingest → review → distribute → variance) ran cleanly via CLI. Streamlit not used in 30+ days.
**Constraints:** Files are MOVED to _deprecated/, not deleted. M6 deletes them after the second month.

```
Cut over from Streamlit. This is a destructive prompt — do not run it unless
Bill has confirmed one full month of CLI-only operation.

PRE-READ
1. Read app.py, variance_tab.py, requirements.txt, CLAUDE.md, README.md
2. Confirm via `ls runs/` that there are at least 4 run directories
   (suggesting at least one monthly cycle has occurred).
3. If runs/ has fewer than 4 entries, STOP and report — do not proceed.

WORK

A. Create _deprecated/ directory.
B. Move app.py → _deprecated/app.py (use git mv)
C. Move variance_tab.py → _deprecated/variance_tab.py (use git mv)
D. Move .streamlit/ → _deprecated/.streamlit/ if it exists
E. Delete runtime.txt if it exists (Streamlit Cloud-specific)
F. Update requirements.txt:
   - Remove the streamlit line
   - Confirm typer, rich, gspread, google-auth, pandas, numpy, plotly remain
G. Update pyproject.toml [project] dependencies to match requirements.txt.
H. Update CLAUDE.md:
   - In the Streamlit UI table, mark every row with status "Deprecated (moved to _deprecated/)"
   - Add a new section "## CLI Interface (current)" with the full `pet` command list
   - Update the "Current Status / Safe to Run" section to reflect CLI-only operation
   - Add a Key Decisions Log entry dated today: "Streamlit deprecated. CLI is
     the sole operator interface. _deprecated/ retains the old code for one
     month before deletion (M6)."
I. Update README.md with the CLI quick-start (use the README from the docs
   bundle if Bill provides one; otherwise generate a CLI-first README from
   scratch using the manager.py command list).
J. Add a CHANGELOG.md entry under a new ## [0.6.0] heading dated today:
   - Removed: Streamlit UI (moved to _deprecated/)
   - Removed: streamlit dependency, runtime.txt, .streamlit/
   - Added: Reference to _deprecated/ for rollback
   - Status: CLI-only. Safe to run.
K. Update state.md current focus: "M5 cutover complete. M6 (deletion) scheduled
   for one month from today."

VALIDATION
1. python -c "import ast; ast.parse(open('manager.py').read())"
2. python -c "from manager import app; print('OK')"
3. Run: python manager.py health
   Confirm exit code 0 — auth still works without any Streamlit imports.
4. Run: pip check
   Confirm no broken dependencies after streamlit removal.
5. Confirm `streamlit` does NOT appear in requirements.txt or pyproject.toml.
6. Confirm app.py and variance_tab.py are NOT in the repo root anymore.

OUTPUT
Full diff summary plus all validation results. If `pet health` fails for any
reason, immediately revert all changes via `git checkout .` and report.
```

---

## Prompt M6 — Final cleanup (delete _deprecated/)

**Goal:** Permanent deletion of the deprecated Streamlit code.
**Tool:** Claude Code
**Risk:** Low (deleting code already moved aside and confirmed unused for a month).
**Pre-checks:** M5 committed and at least 30 days have passed; no rollbacks happened.
**Constraints:** None beyond standard.

```
Delete the _deprecated/ directory now that the CLI cutover is confirmed stable.

PRE-READ
1. Confirm _deprecated/ exists.
2. Confirm git log shows the M5 commit is at least 30 days old. If younger,
   STOP and report.
3. Confirm `pet health` exits 0.
4. Confirm runs/ has run directories from at least 2 distinct months since
   the M5 commit. If not, STOP and report.

WORK
A. git rm -r _deprecated/
B. Add CHANGELOG.md entry under a new ## [0.7.0] heading dated today:
   - Removed: _deprecated/ directory (formerly app.py, variance_tab.py, .streamlit/)
   - Status: CLI-only, no Streamlit code remains. Safe to run.
C. Update state.md current focus: "Migration complete."

VALIDATION
1. python manager.py health  (must exit 0)
2. ls _deprecated/  (must fail — directory should not exist)
3. git status  (must be clean after commit)

OUTPUT
Confirmation that _deprecated/ is gone and `pet health` still passes.
```

---

## Recovery / rollback procedures

### If M2 produces wrong output during dry-run
- `git checkout manager.py utils/`
- The Streamlit app is untouched; fall back to it for that monthly cycle.

### If M5 breaks anything
- The `_deprecated/` directory still has app.py and variance_tab.py. Move them back:
  - `git mv _deprecated/app.py app.py`
  - `git mv _deprecated/variance_tab.py variance_tab.py`
  - Restore `streamlit` to requirements.txt
- This is why M6 has a 30-day waiting period.

### Universal rollback
- Every M-prompt is one commit. `git revert <commit>` restores the previous state.
