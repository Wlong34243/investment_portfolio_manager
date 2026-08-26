# Prompt — Schwab Data Expansion, Phase 4: Risk_Metrics and the Market Calendar

**Created:** 2026-08-25
**Executor:** Claude Code or Gemini CLI, run locally in `C:\Dev\Investment_Portfolio`
**Phase:** 4 of 4
**Prerequisites:** Phase 1 complete (bars available). Phase 2 complete **or** explicitly
waived — if waived, this phase's metrics are computed from whatever
`PRICE_HISTORY_SOURCE` currently resolves to, and the source must be stamped on the tab.

---

## Why this exists

Two gaps, both cheap to close, both currently producing wrong or missing output every day.

### Gap 1 — `Risk_Metrics` is a tab the dashboard reads and nothing writes

`config.py` defines `TAB_RISK_METRICS`. `utils/sheet_readers.py` (~line 208) reads it.
`tasks/build_command_center.py` (~line 940) consumes it into `0_DASHBOARD`. **No module
in the repo writes it.** The dashboard has been rendering from an empty or hand-stale tab.

`utils/risk.py` already computes beta and volatility (line ~117, a 1-year multi-ticker
download). The calculation layer exists; the persistence layer was never built.

### Gap 2 — nothing in the system knows whether the market was open

`grep -rniE "market_hours|is_trading_day|holiday|calendar"` across `utils`, `tasks`,
`core` and `manager.py` returns only FMP's *earnings* calendar. There is no trading-day
awareness anywhere. Consequences observable today:

- `build_command_center.py` (~line 287) computes STALE by comparing calendar days between
  `Daily_Snapshots` and `Holdings_Current`. Every long weekend and every market holiday
  manufactures a STALE flag against data that is perfectly current.
- The 7:45 AM `morning` run does full work on days no session exists, writing a
  `Daily_Snapshots` row for a non-trading day and diluting every subsequent
  period-over-period comparison.
- Per Analysis Rule 8, an export-time flag caused by a taxonomy or data gap is a SYSTEM
  finding, not an actionable one. Holiday-induced STALE flags are pure SYSTEM noise
  competing for attention with real Crosshairs rows.

Phase 1 added `fetch_market_hours()` and `is_trading_day()`. This phase wires them in.

---

## Hard constraints

1. Order/trading endpoints remain forbidden.
2. **No price targets, no predictions, no buy/sell language on `Risk_Metrics`.** Beta,
   volatility, drawdown and correlation are descriptive statistics about the past. A
   "risk score", a ranking implying action, or a column named anything like
   `Recommended_Trim` violates Hard Rule 4. Facts only.
3. **Do not write to `0_DASHBOARD` outside `build_command_center.py`'s grid
   construction.** It is clear-and-rebuild; anything written elsewhere is erased.
4. `--live` required for every Sheet write; archive-before-overwrite; single batch write.
5. All Sheet reads through `read_gsheet_robust()`. **`read_gsheet_robust()` maintains a
   `text_indicators` allowlist of column names** — the 2026-08-24 typed-trigger build
   shipped a silent read-back zeroing because a new column was not registered there.
   Every new `Risk_Metrics` column must be checked against that allowlist explicitly, and
   the check must appear in the verification output.
6. Do not modify `utils/risk.py`'s existing formulas. Persist what it computes; extend
   only where a metric is genuinely absent.

---

## Step 0 — Verification gate (STOP on any mismatch)

```
0.1  grep -n "TAB_RISK_METRICS" config.py utils/sheet_readers.py tasks/*.py
     EXPECT: definition in config, reader in sheet_readers (~208),
     consumer in build_command_center (~940), zero writers. Confirm zero writers.

0.2  sed -n '320,340p;930,960p' tasks/build_command_center.py
     VERIFIED 2026-08-25 — the dashboard's entire dependency on this tab is ONE value:
     _compute_beta() (~line 325) takes the LAST row of Risk_Metrics and reads
     latest.get("Portfolio Beta"); the caller is at ~940/946.

     This is a schema collision with Step 1's per-ticker design and it is the
     highest-risk item in this phase. A per-ticker tab sorted by ticker puts some
     equity in the last row, that row has no "Portfolio Beta" key, _compute_beta
     returns None, and the dashboard KPI breaks SILENTLY — no exception, just a
     missing number.

     Read _compute_beta() IN FULL and reproduce its exact row-selection logic
     (does it take [-1] unconditionally, or filter first?). Paste the function
     body into your report. Step 1's row ordering is dictated by what you find,
     not by this prompt's guess.

0.3  Open the live Risk_Metrics tab (pm store / gspread read) and print its
     current header row and row count.
     If it holds hand-entered data, STOP and report before overwriting anything.

0.4  sed -n '1,140p' utils/risk.py
     Record every metric already computed and its exact window/formula.

0.5  sed -n '275,300p' tasks/build_command_center.py
     Record the current STALE logic verbatim. This is what Step 3 changes.

0.6  grep -nE "^def (fetch_market_hours|is_trading_day)" utils/schwab_client.py
     EXPECT both present from Phase 1. If absent, STOP.

0.7  grep -n "text_indicators" utils/sheet_readers.py
     Record the current allowlist contents.
```

---

## Step 1 — `Risk_Metrics` writer

New `tasks/build_risk_metrics.py`. Schema is whatever Step 0.2 established the dashboard
consumes, **plus** the columns below where they are not already required. If the
dashboard expects a column this prompt does not name, keep it and say so; if this prompt
names a column the dashboard ignores, keep it anyway — the tab is also read by a human.

| Column | Definition | Notes |
|---|---|---|
| `Ticker` | — | Position set from the newest bundle, cash excluded |
| `Beta_1Y_SPY` | OLS beta of daily returns vs SPY, trailing 252 trading days | Reuse `utils/risk.py`'s formula exactly |
| `Vol_90D_Ann` | Stdev of daily returns over 90 trading days × √252 | |
| `Vol_1Y_Ann` | Same over 252 days | |
| `Max_Drawdown_1Y` | Largest peak-to-trough close decline, trailing 252 days | Negative number |
| `Drawdown_From_52W_High` | Current close vs trailing 252-day max close | Cross-check against `dislocation_scan`'s figure; a disagreement is a finding, report it |
| `Corr_1Y_SPY` | Pearson correlation of daily returns vs SPY | |
| `Contribution_To_Portfolio_Vol` | Weight × beta-adjusted vol, normalised to sum to 100% | Descriptive decomposition. **Not** a risk ranking |
| `Obs_Count` | Bars actually used | A 40-bar beta and a 252-bar beta are not comparable |
| `Data_Source` | `schwab` / `yfinance` / `mixed` | From `df.attrs["source"]` |
| `As_Of_UTC` | Bar timestamp of the last observation | Not wall-clock time |

### Backwards compatibility with `_compute_beta` — non-negotiable

The per-ticker rows above are **additive**. The existing dashboard contract must survive
unchanged:

- The tab must still yield a numeric `Portfolio Beta` to `_compute_beta()` on every run.
- Write the per-ticker rows first, then a **final portfolio-summary row** carrying
  `Portfolio Beta` (and, where meaningful, portfolio-level vol and max drawdown), so that
  a `[-1]` selection lands on it. **If Step 0.2 shows `_compute_beta` filters rather than
  taking `[-1]` blindly, follow what the code does** — this ordering rule exists to
  satisfy that function, not the other way round.
- Compute the portfolio beta with `utils/risk.py::calculate_portfolio_beta()`. Do not
  write a second beta implementation; two portfolio betas that disagree is worse than
  none.
- **Verification is behavioural, not structural:** run `build_command_center` after the
  first `--live` write and show the dashboard beta KPI rendering a number. A tab that
  looks right but returns `None` to `_compute_beta` is the exact failure this section
  exists to prevent.

### Reusing `utils/risk.py` without migrating it

Verified 2026-08-25: `calculate_beta()`, `calculate_var()` and
`calculate_correlation_matrix()` all take `price_histories` as a **parameter**;
only `build_price_histories()` (line ~117) does its own `yf.download`.

So this phase passes `price_history.get_bars()` output into the existing formulas and
**does not call `build_price_histories()` and does not migrate it.** Phase 2 explicitly
leaves it alone; do not "finish the job" here.

### Hard Rule 4 boundary inside `utils/risk.py`

That module also contains `run_stress_tests()`, `capm_projection()` and
`compute_van_tharp_sizing()`. **None of their output goes on this tab.** A CAPM expected
return is a forecast and a Van Tharp size is a position-sizing recommendation — both are
squarely inside the no-predictions / no-recommendations rule. Persist only the
descriptive statistics named in the schema above. If you think one of them belongs, say
so in one line and stop; do not add it.

Rules:

- **A position with fewer than 60 usable bars gets `None`, not a number.** New positions
  and recent IPOs must show as uncomputable. A beta from 12 observations is noise wearing
  a decimal point.
- Cash (`CASH_MANUAL`) is excluded from every metric but included in the weight
  denominator for `Contribution_To_Portfolio_Vol`. State this in the tab header line.
- Header line on the tab: `RISK_METRICS — as of {ts} — source {schwab|yfinance|mixed} —
  N positions, M uncomputable`, matching the `Decision_View` / Crosshairs header
  convention already in use.
- CLI: `pm build risk-metrics [--live] [--lookback-days 400]`.
- **Mid-prompt sign-off gate:** print the full proposed tab and stop. Bill accepts,
  overrides or rejects before the first `--live` write.

---

## Step 2 — Wire into the morning pipeline

Insert **inside STEP 5, after `build_val` and before `build_cc`** — the dashboard reads
`Risk_Metrics`, so a stale tab at dashboard time defeats the purpose.

Confirm the surrounding call order in `manager.py` before inserting; do not trust this
paragraph over the code. It is a sub-step of an existing STEP, not a new numbered STEP —
renumbering the pipeline would invalidate every log line, runbook reference and
`--skip-*` flag that names a step number.

- Non-fatal on failure, matching STEP 4b's degradation pattern: a Schwab or bar failure
  logs a warning and leaves the previous tab contents intact rather than writing an empty
  tab. **An empty `Risk_Metrics` is worse than a stale one**, because the dashboard
  consumes it silently.
- Skippable via `--skip-risk-metrics`.
- Respects the health-failure sentinel like every other step.

---

## Step 3 — Trading-calendar gating

New `utils/market_calendar.py`, wrapping Phase 1's `is_trading_day()` with the day-cache
and a `previous_trading_day(date)` helper.

Three wiring points, and no more:

**3.1 — STALE detection in `build_command_center.py` (~line 287).**
Replace calendar-day arithmetic with trading-day arithmetic. Data from the previous
trading session is CURRENT; data older than one trading session is STALE. Record the
before/after behaviour for: a normal Tuesday, a Monday after a normal weekend, a Tuesday
after a Monday holiday, and a Friday.

**3.2 — `Daily_Snapshots` write in the morning pipeline.**
On a non-trading day, skip the snapshot row and log the reason. Do not write a duplicate
row for a closed session.
**`is_trading_day()` returning `None` (unknown) must behave exactly as it does today —
proceed and write.** Degrading an API outage into "market closed" would silently drop
real trading days from the history. State this explicitly in a code comment.

**3.3 — Health check.**
Add a `market_status` informational row to `pm health`: open / closed / unknown, with the
session times when open. Informational only — it must never set
`logs/HEALTH_FAILURE.flag`. A closed market is not a system fault.

**Explicitly not in scope:** skipping the whole morning run on holidays. Podcast
ingestion, thesis sync and health checks are all still worth running on a market holiday.
Gate the market-dependent steps, not the pipeline.

---

## Step 4 — Register new columns with the sanitizer

For every new column landing on a Sheet tab in this phase, verify it against
`read_gsheet_robust()`'s `text_indicators` allowlist and register where needed. Then
**read the tab back through `read_gsheet_robust()` and prove no column silently zeroed.**

This is a required step, not a nicety. On 2026-08-24 a correct Sheet write plus an
unregistered column produced wrong Trim/Add values on `0_DASHBOARD` through a live run
before it was caught. `Data_Source` and the header line are text in a tab that is
otherwise numeric — precisely the shape that broke last time.

---

## Post-build verification checklist

Literal stdout/stderr for every row.

| # | Check | Evidence required |
|---|---|---|
| 1 | Order endpoints absent | `grep -rnE "place_order\|replace_order\|cancel_order\|get_orders" utils tasks core manager.py scripts` → zero |
| 2 | Pre-existing tab contents | Step 0.3 output, plus the archive path proving pre-write content was preserved |
| 3 | Dry run | Full proposed `Risk_Metrics` tab printed before any write |
| 4 | Sparse-history handling | At least one position with <60 bars showing `None`, not a number — name the ticker |
| 5 | Beta sanity | JEPI beta materially below 1.0 and a high-beta name materially above it. If JEPI prints near 1.0, the calculation is wrong — stop and investigate |
| 6 | Drawdown cross-check | `Drawdown_From_52W_High` vs the same figure from today's `dislocation_scan`, per overlapping ticker, with any disagreement explained |
| 7 | Contribution sums | `Contribution_To_Portfolio_Vol` sums to 100% ±0.1% |
| 8 | Live write | `pm build risk-metrics --live` stdout plus the resulting header line |
| 9 | Sanitizer round-trip | Read-back through `read_gsheet_robust()`; every numeric column non-zero where the write was non-zero; `text_indicators` diff shown |
| 9b | `_compute_beta` contract | The function body from Step 0.2, the last row of the written tab, and the dashboard beta KPI rendering a **number** after a live run — not a structural argument that it should |
| 9c | One beta implementation | Proof the portfolio beta came from `calculate_portfolio_beta()`, not a second local implementation |
| 9d | Rule 4 boundary | `grep -n "capm_projection\|run_stress_tests\|van_tharp" tasks/build_risk_metrics.py` → zero matches |
| 10 | Dashboard integration | `0_DASHBOARD` after a full `pm morning --live`, showing risk figures where it previously showed blanks |
| 11 | Non-fatal degradation | Force a bar-fetch failure; show the warning, the pipeline continuing, and the prior tab contents intact |
| 12 | STALE, four cases | Before/after for normal Tuesday, post-weekend Monday, post-holiday Tuesday, Friday |
| 13 | Holiday snapshot skip | A simulated non-trading day showing the snapshot skipped with a logged reason |
| 14 | Unknown ≠ closed | `is_trading_day()` forced to `None`; show the snapshot still written |
| 15 | `market_status` | `pm health` output including the row; confirm no `HEALTH_FAILURE.flag` created |
| 16 | Full pipeline | `pm morning --live` complete stdout, STEP sequence including the new step in the right position |

---

## What this phase explicitly does NOT do

- Does not add a composite risk score, a ranking, or any actionable framing.
- Does not skip the morning run wholesale on holidays.
- Does not modify `utils/risk.py`'s formulas.
- Does not touch `Income_Tracking` (Phase 3) or the Crosshairs ranking logic.
- Does not add movers, option chains, or streaming — see
  `schwab_signal_layer_PROPOSAL_2026-08-25.md`, which is a decision document and is
  **not authorised to build**.

---

## Documentation to update on completion

- `CHANGELOG.md` — dated entry
- `state.md` — `Risk_Metrics` moves from dead tab to live producer; calendar gating noted
- `CLAUDE.md` — `tasks/build_risk_metrics.py` and `utils/market_calendar.py` in Key Files;
  morning-pipeline step order updated
- `PORTFOLIO_SHEET_SCHEMA.md` — document `Risk_Metrics` properly; it is one of the
  undocumented tabs already on record as a known gap
