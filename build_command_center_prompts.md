# Prompt Set — 0_DASHBOARD Command Center

**Goal:** Build a single-screen `0_DASHBOARD` tab that gives Bill a 30-second answer to "what is the state of the portfolio right now?" Pure gspread writes, no formulas, fully rebuilt as part of `pm refresh dashboard`.

## Design constraints (decided, not open for discussion)

- **No formulas.** The `TAB_DASHBOARD` constant comment in `config.py` already commits the design to "hard-value KPIs, no formulas." Honor that. Every cell on this tab is a literal value written by gspread on each refresh.
- **No new computation.** Every value rendered on Command Center already exists on another tab (`Holdings_Current`, `Tax_Control`, `Risk_Metrics`, `Daily_Snapshots`, `Target_Allocation`). The builder reads them and presents them. It does not recalculate.
- **Authority:** computed view, clear-and-rebuild. Pipeline-only. No manual edits expected or preserved.
- **DRY_RUN default true.** `--live` flag required to write. Standard for the project.
- **Folds into `pm refresh dashboard`.** No new CLI command. Adds one task call to the existing `dashboard_refresh()` function in `manager.py`.

## Tab layout (single screen, ~36 rows)

```
Row 1     : "PORTFOLIO COMMAND CENTER  —  As of YYYY-MM-DD HH:MM"  (title, merged A1:G1)
Row 2     : (blank)

Row 3-4   : HEADLINE KPI STRIP
            A3: "Total Value"       B3: $ formatted
            C3: "Cash %"            D3: % formatted
            E3: "Strategic Cash"    F3: $ formatted
            A4: "Day Change"        B4: $ + (%)
            C4: "MTD"               D4: % formatted
            E4: "YTD"               F4: % formatted
            G4: "vs. SPY YTD"       H4: + or - bps formatted

Row 6     : "TAX POSTURE" section header
Row 7     : A7: "Net ST (YTD)"      B7: $    C7: "Net LT (YTD)"  D7: $
            E7: "Disallowed Wash"   F7: $    G7: "Wash Sales"    H7: count
Row 8     : A8: "Est. Fed Tax"      B8: $    C8: "Offset Capacity" D8: $

Row 10    : "RISK SNAPSHOT" section header
Row 11    : A11: "Portfolio Beta"   B11: float
            C11: "Top Position"     D11: ticker (% weight)
            E11: "Top Sector"       F11: sector (% weight)
            G11: "Stress -10%"      H11: $

Row 13    : "TOP 5 POSITIONS" section header
Row 14    : Headers: Ticker | Weight | Market Value | UGL % | Price | Trim Tgt | Add Tgt | Dist to Trim | Dist to Add
Row 15-19 : Top 5 positions by Market Value (excluding cash tickers per CASH_TICKERS)
            "Dist to Trim" = (Trim Target - Price) / Price as % (positive = below trim)
            "Dist to Add"  = (Price - Add Target) / Add Target as % (positive = above add)
            Trim/Add targets sourced from thesis triggers via existing Valuation_Card data

Row 21    : "DRIFT ALERTS" section header
Row 22    : Headers: Ticker | Current % | Target % | Drift % | Direction
Row 23-30 : Up to 8 positions where |current_weight - target_weight| > rebalance_threshold_pct
            Sorted by absolute drift, descending
            Direction: "OVER" or "UNDER"
            If no drift, single row: "No positions outside ±X% threshold."

Row 32    : "SYSTEM HEALTH" section header (smaller font)
Row 33    : A33: "Last Refresh"     B33: timestamp
            C33: "Bundle Hash"      D33: short hash (first 8 chars)
Row 34    : A34: "Schwab Token"     B34: "OK" / "Expiring soon" / "Expired"
            C34: "FMP Cache Age"    D34: "X days"
```

## Sourcing map (where each value comes from)

| Cell | Source tab | Column / Calculation |
|------|------------|---------------------|
| Total Value | Daily_Snapshots | latest row, col B |
| Cash % | Daily_Snapshots | (Cash Value / Total Value) latest row |
| Strategic Cash | Holdings_Current | sum of Market Value where Is Cash = TRUE |
| Day Change $ / % | Daily_Snapshots | latest minus prior row |
| MTD % | Daily_Snapshots | latest vs. first row of current month |
| YTD % | Daily_Snapshots | latest vs. first row of current year |
| vs. SPY YTD | yfinance | SPY YTD return; subtract from portfolio YTD |
| Net ST / LT | Tax_Control KPI strip | existing values |
| Disallowed Wash, Wash Sales count | Tax_Control KPI strip | existing values |
| Est. Fed Tax, Offset Capacity | Tax_Control KPI strip | existing values |
| Portfolio Beta | Risk_Metrics | latest row, col B |
| Top Position | Holdings_Current | max(Weight) ticker + value |
| Top Sector | computed inline | groupby(Asset Class) sum(Weight), take max |
| Stress -10% | Risk_Metrics | latest row, col H |
| Top 5 Positions | Holdings_Current | top 5 by Market Value, excluding CASH_TICKERS |
| Trim/Add Targets | Valuation_Card | cols F (Trim Target), G (Add Target) — joined on Ticker |
| Drift Alerts | Holdings_Current vs Target_Allocation | join on Ticker, compute drift, filter > threshold |
| Last Refresh | datetime.now() | at write time |
| Bundle Hash | latest bundle file | basename or hash field |
| Schwab Token | GCS bucket SCHWAB_TOKEN_BLOB_ACCOUNTS | check expiry timestamp; OK / Expiring (<2 days) / Expired |
| FMP Cache Age | local cache file mtime | days since modified |

---

## Prompt 0 — Pre-flight audit

Run this first. No code generation.

```
Audit pass for the upcoming `0_DASHBOARD` Command Center build. Read these files via `view`
and report back. Do not generate any code yet.

1. `config.py` — confirm:
   - `TAB_DASHBOARD = "0_DASHBOARD"` exists (line ~107)
   - `CASH_TICKERS` list and contents
   - `REBALANCE_THRESHOLD_PCT` value
   - `TAX_CONTROL_KPI_LABELS` list (we'll read from this tab)
   - `SCHWAB_TOKEN_BUCKET` and `SCHWAB_TOKEN_BLOB_ACCOUNTS`

2. `tasks/build_decision_view.py` — confirm:
   - Function signature of `main(live: bool)`
   - The gspread client / worksheet pattern (clear → batch update → format)
   - How it reads Holdings_Current and Valuation_Card

3. `tasks/build_tax_control.py` — confirm:
   - Function signature of `refresh_tax_control_sheet(live: bool)`
   - How it computes the KPI strip and where the values land in the sheet (A1:H3 or similar)
   - Whether the KPI values are accessible without re-running the calculation
     (i.e., can the Command Center builder just read them from Tax_Control directly?)

4. `tasks/format_sheets_dashboard_v2.py` — confirm:
   - The formatting pattern (border colors, header backgrounds, number formats)
   - This is the style we'll match for the Command Center

5. `manager.py` — confirm:
   - The `dashboard_refresh` function (lines ~755-772). This is where we'll add the
     `build_command_center` call.

6. `utils/sheet_writers.py` (if it exists) — list helper functions for batch writes,
   range formatting, and clear-and-rebuild patterns. We want to reuse, not reinvent.

7. The Google Sheet itself (use gspread client from `utils/sheet_readers.py`):
   - Confirm `0_DASHBOARD` tab exists. If not, flag it — Prompt 1 will create it.
   - List existing tabs in order to confirm `0_DASHBOARD` would be at position 0.
   - Inspect Tax_Control: confirm KPI strip layout (which rows/cols hold which labels).
   - Inspect Risk_Metrics: confirm latest row layout (column positions for beta, stress).
   - Inspect Daily_Snapshots: confirm column positions for Total Value, Cash Value.

8. `core/bundle.py` — confirm the bundle hash is accessible without rebuilding the bundle
   (we want to read the latest hash, not regenerate one).

For each file, report:
- 2-3 sentence summary
- Exact symbols / function signatures / column positions relevant to the build
- Anything that contradicts the assumptions in this spec

End with a "Ready / Not Ready" verdict and list any blocking unknowns.
```

---

## Prompt 1 — Build `tasks/build_command_center.py`

```
Generate `tasks/build_command_center.py`.

This task reads existing portfolio state from multiple Sheet tabs and writes a single
"command center" view to the `0_DASHBOARD` tab. It performs no original computation — it
aggregates and formats values that already exist elsewhere.

## Signature

```python
def main(live: bool = False) -> None:
    """
    Rebuild the 0_DASHBOARD Command Center tab.

    Reads from: Holdings_Current, Daily_Snapshots, Tax_Control, Risk_Metrics,
                Target_Allocation, Valuation_Card.
    Writes to:  0_DASHBOARD (clear-and-rebuild, single batch_update call).

    Args:
        live: If False (default), prints the rendered grid to stdout and exits without
              writing. If True, writes the grid to the sheet and applies formatting.
    """
```

## Implementation outline

1. **Read all source tabs once.** Use `utils.sheet_readers.get_gspread_client()`. Pull the
   raw values for Holdings_Current, Daily_Snapshots, Tax_Control, Risk_Metrics,
   Target_Allocation, Valuation_Card. Load each into a list of dicts keyed by header.

2. **Compute the grid.** Build a list-of-lists `grid: list[list[str|float|int]]` matching
   the layout in the spec. All math is straightforward aggregation — no clever logic.
   Specific helpers to write:
   - `_compute_headline_kpis(daily_snapshots, holdings_current) -> dict`
   - `_read_tax_kpis(tax_control_rows) -> dict` — read the KPI strip cells directly; do not
     recalculate
   - `_compute_risk_snapshot(risk_metrics_rows, holdings_current) -> dict`
   - `_compute_top_5_positions(holdings_current, valuation_card) -> list[dict]`
   - `_compute_drift_alerts(holdings_current, target_allocation, threshold_pct) -> list[dict]`
   - `_check_system_health() -> dict` — last refresh, bundle hash, Schwab token status,
     FMP cache age

3. **vs. SPY YTD.** Use yfinance to fetch SPY's YTD return. Wrap in try/except — if
   yfinance fails, write "n/a" rather than crashing the dashboard. Cache the result in
   memory; do not call yfinance more than once per `main()` invocation.

4. **Drift alerts.** Inner-join Holdings_Current and Target_Allocation on Ticker. Compute
   `drift_pct = current_weight - target_weight`. Filter where
   `abs(drift_pct) > config.REBALANCE_THRESHOLD_PCT`. Sort descending by absolute drift.
   Cap at 8 rows. If the resulting list is empty, render a single row:
   `"No positions outside ±{threshold}% threshold."`

5. **Top 5 positions.** Sort Holdings_Current by Market Value descending, exclude any
   ticker in `config.CASH_TICKERS`, take the top 5. Left-join with Valuation_Card on
   Ticker to pull Trim/Add targets. If a position has no thesis (no Trim/Add target),
   render "—" in those columns and "n/a" in the distance columns.

6. **Render the grid.** Build the full grid as a list of lists matching the row/col layout
   in the spec. Use `""` (empty string) for blank cells — never None. Format numbers as
   strings with their final formatting baked in (`$1,234.56`, `+2.3%`, `9.0%`). The dashboard
   tab gets formatted display values, not raw floats. (This is consistent with the
   "no formulas, hard values" decision — but go one step further: pre-format strings so the
   formatting rules in step 8 only need to handle alignment and color, not number formats.)

   Note: this is opinionated and goes against the usual gspread practice of writing raw
   numbers and formatting via `format_cell_ranges`. The reasoning: the Command Center is a
   read-only summary tab. Pre-formatted strings eliminate any "did the format apply
   correctly?" debugging and make the grid identical to what stdout shows in DRY RUN mode.
   If you disagree with this choice, flag it and propose the alternative — don't silently
   change it.

7. **DRY RUN path.** If `live=False`, print the grid as a Rich table to stdout and exit
   without touching the sheet. Use the same row/col layout as the live write so visual
   verification is meaningful. Print a final line:
   `[dim]DRY RUN — no Sheet writes. Re-run with --live to apply.[/]`

8. **LIVE path.** Single batch operation:
   - Open `0_DASHBOARD` worksheet (create if missing — log a warning).
   - Clear rows 1-40 (defensive — covers any prior longer layout).
   - `worksheet.update("A1", grid, value_input_option="USER_ENTERED")`
   - Apply formatting via one `batch_update` call: section header rows bold + bg color,
     KPI labels right-aligned, KPI values bold, drift alerts colored (OVER = red bg,
     UNDER = orange bg), title row merged + centered + larger font.
   - Log: `Command Center refreshed. {rows} rows written.`

9. **Idempotency.** Re-running `main(live=True)` immediately should produce the same
   visual output. The only cell that changes is the "Last Refresh" timestamp. Don't add
   any append-only behavior.

## Imports & dependencies

- `gspread` (already in deps)
- `yfinance` (already in deps)
- `rich` for DRY RUN output (already in deps)
- `config` for tab names, thresholds, CASH_TICKERS, SCHWAB_TOKEN_BLOB_ACCOUNTS
- `utils.sheet_readers` for the gspread client
- Standard library: `datetime`, `pathlib`, `typing`

Do NOT add any new dependencies.

## Error handling

- If `0_DASHBOARD` tab is missing in LIVE mode: create it at index 0, log a warning, then
  proceed with the write.
- If any source tab is empty or missing expected columns: log a warning naming the tab
  and the missing column, render the affected cells as "—", and continue. The dashboard
  must always render — partial data is better than a crash.
- If Schwab token blob is unreachable (no GCS access in test env): render "n/a" for token
  status, do not raise.
- If yfinance times out or returns empty: render "n/a" for vs. SPY YTD.

## Out of scope (do not build)

- Conditional formatting based on price (red/green for distance to trim) — that's
  Decision_View's job. Command Center mirrors it but doesn't duplicate the formatting.
- Sparklines or charts. Hard values only. (Consistent with the `TAB_DASHBOARD` design
  comment in config.py.)
- Any write to tabs other than `0_DASHBOARD`.
- Any new computation. If a value isn't already on another tab, it doesn't go on the
  dashboard.
```

---

## Prompt 2 — Wire into `pm refresh dashboard`

```
Modify `manager.py` to call `tasks/build_command_center.py` as part of `dashboard_refresh`.

Specifically, in the `dashboard_refresh()` function (currently lines ~755-772):

1. Add the import at the top of the function:
   `from tasks.build_command_center import main as build_cc`

2. Add the call AFTER `build_dec(live=live)` and BEFORE `format_v2(live=live)`:
   ```python
   build_dec(live=live)
   build_cc(live=live)        # NEW: refresh 0_DASHBOARD Command Center
   format_v2(live=live)
   ```

3. Update the success message:
   ```python
   console.print("[green]Dashboard refresh complete (Valuation_Card, Decision_View, 0_DASHBOARD).[/]")
   ```

That's it. No other CLI changes. `pm morning --live` already calls `dashboard_refresh`,
so the Command Center will rebuild automatically on the daily loop.

Do NOT add a separate `pm refresh command-center` command. The Command Center is part of
the dashboard refresh; splitting it adds CLI surface for no benefit.

Do NOT modify any other Typer command groups.
```

---

## Prompt 3 — Documentation updates

```
Update three documentation surfaces to reflect the Command Center.

## File 1: `PORTFOLIO_SHEET_SCHEMA.md`

Add a new section between the Tab Authority Matrix and the existing tab definitions:

```
### Tab: 0_DASHBOARD (Command Center)
**Purpose:** Single-screen at-a-glance view of portfolio state. No original computation;
aggregates values from other tabs.
**Authority:** Pipeline (`tasks/build_command_center.py`, called by `pm refresh dashboard`)
**Write pattern:** Clear-and-rebuild. No formulas, hard values only.

Layout:
- Rows 1-2:    Title + timestamp
- Rows 3-4:    Headline KPIs (Total Value, Cash, Day/MTD/YTD, vs SPY)
- Rows 6-8:    Tax Posture (mirrors Tax_Control KPI strip)
- Rows 10-11:  Risk Snapshot (Beta, Top Position, Top Sector, Stress)
- Rows 13-19:  Top 5 Positions with Trim/Add target distances
- Rows 21-30:  Drift Alerts (positions outside ±REBALANCE_THRESHOLD_PCT)
- Rows 32-34:  System Health (last refresh, bundle hash, Schwab token, FMP cache age)
```

## File 2: `CLAUDE.md`

In the "Tab authority" section, add `0_DASHBOARD` to the "computed views" line:
```
- 0_DASHBOARD / Valuation_Card / Decision_View / Tax_Control / Rotation_Review:
  computed views, clear-and-rebuild
```

In the "Command Cheatsheet" section, no change needed — `pm refresh dashboard` and
`pm morning --live` already cover the Command Center transitively.

## File 3: `portfolio_manager_user_docs.html`

Bump version to 3.5. Add a new section after "The Weekly Cycle":

```html
<section id="command-center">
    <h2>4.5 The Command Center (0_DASHBOARD)</h2>
    <p>The first tab in the workbook is your single-screen daily view. It refreshes every
    time you run <code>pm morning</code> or <code>pm refresh dashboard</code> and contains
    no formulas — every value is a literal write from the pipeline.</p>
    <p><strong>What's on it:</strong></p>
    <ul>
        <li><strong>Headline KPIs:</strong> Total value, cash %, day change, MTD/YTD,
        vs. SPY.</li>
        <li><strong>Tax Posture:</strong> Mirrors Tax_Control KPIs in compact form.</li>
        <li><strong>Risk Snapshot:</strong> Beta, top position, top sector, stress -10%.</li>
        <li><strong>Top 5 Positions:</strong> Largest holdings with distance to trim/add
        targets sourced from your thesis files.</li>
        <li><strong>Drift Alerts:</strong> Positions outside ±5% (or your configured
        threshold) of target allocation.</li>
        <li><strong>System Health:</strong> Last refresh time, bundle hash, Schwab token
        status, FMP cache age.</li>
    </ul>
    <div class="callout">
        <strong>Read-only by design.</strong> Don't edit cells on this tab — they'll be
        overwritten on the next refresh. For everything you can act on, follow the link in
        each section to the underlying tab (Decision_View for trim/add, Tax_Control for
        harvesting, Target_Allocation for rebalancing).
    </div>
</section>
```

Update the navigation sidebar to include the new section link.

## CHANGELOG.md

Add to the top under `[Unreleased]`:

```
### Added
- **0_DASHBOARD Command Center**: Single-screen daily view aggregating headline KPIs, tax
  posture, risk snapshot, top 5 positions, drift alerts, and system health. Built by
  `tasks/build_command_center.py` and refreshed automatically as part of
  `pm refresh dashboard` (and therefore `pm morning`).
```
```

---

## Prompt 4 — Verification checklist

```
Post-build verification. Run after Prompts 1-3 ship.

POST-BUILD CHECKLIST:

1. `python manager.py refresh dashboard` (DRY RUN)
   - Should print the Command Center grid as a Rich table to stdout
   - Should print "DRY RUN — no Sheet writes" at the end
   - No exceptions raised
   - All section headers present (Headline, Tax Posture, Risk Snapshot, Top 5, Drift
     Alerts, System Health)

2. Visually inspect the DRY RUN output:
   - Headline numbers match what you'd expect from your latest Daily_Snapshot
   - Tax KPIs match what's currently in Tax_Control
   - Top 5 positions match `Holdings_Current` sorted by Market Value (excluding cash)
   - Drift alerts include only positions where |current - target| > 5% (or your
     configured threshold)
   - System Health row shows real values (not n/a everywhere)

3. `python manager.py refresh dashboard --live`
   - Open the Sheet, click the leftmost tab — should be `0_DASHBOARD`
   - Verify the layout matches the DRY RUN output
   - Section headers are formatted (bold, bg color)
   - Drift alerts have row backgrounds (red for OVER, orange for UNDER)
   - Title row is merged and centered

4. Re-run `python manager.py refresh dashboard --live` immediately
   - Output should be identical to the previous run except for the "Last Refresh"
     timestamp
   - No error spam, no duplicate rows

5. Edge cases to verify:
   - Drift alerts when no positions are outside threshold: single row with
     "No positions outside ±5% threshold."
   - Top 5 positions when one has no thesis (no Trim/Add target): "—" in those columns
   - vs SPY YTD when yfinance is unavailable: "n/a" without crashing
   - Schwab token check when GCS is unreachable: "n/a" without crashing

6. `python manager.py morning --live`
   - Confirm the morning loop calls Command Center refresh as part of dashboard refresh
   - Confirm completion message mentions Valuation_Card, Decision_View, AND 0_DASHBOARD

7. Open the Sheet on your phone (the actual mobile experience matters):
   - Command Center should be readable without horizontal scrolling on a typical phone
   - Numbers should be large enough to scan
   - If anything is too small or wraps awkwardly, adjust column widths in the formatting
     batch_update call
```

---

## Out of scope (deliberately deferred)

- **Conditional formatting on individual position rows.** That's Decision_View territory.
  Command Center is a summary, not a control surface.
- **Sparklines or trend visualizations.** The `TAB_DASHBOARD` config comment commits to
  hard values, no formulas. Honor it. If you later want a sparkline tab, build it
  separately as `Performance_Charts` or similar.
- **Mobile-optimized layout.** The current layout is desktop-first. Mobile is acceptable
  but not optimized. Revisit only if Bill flags it as a real problem.
- **Real-time refresh (mid-day).** Refresh cadence is whatever `pm morning` runs at, plus
  any manual `pm refresh dashboard` Bill triggers. No webhooks, no polling.
- **Cross-portfolio (RE + liquid) summary.** Stays a Phase 6+ goal. Command Center is
  liquid-portfolio only.
