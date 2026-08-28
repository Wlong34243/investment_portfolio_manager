# Desk Redesign — function first, then a real visual system

**Created:** 2026-08-28
**Executor:** Cursor (Agent mode).
**Depends on:** `desk_cockpit_2026-08-28.md` (shipped).
**Source:** Bill, 2026-08-28 — major redesign around visuals and function, benchmarked against the
best dense-financial-data interfaces (Koyfin / TradingView / OpenBB class).

> **Live review findings (2026-08-28, browser + code), in severity order. Phase 0 fixes these
> before any visual work — a redesign painted over them would hide three real defects:**
>
> 1. **`/judgment/lifecycle` reports "No lifecycle artifacts on disk" while 11 artifacts exist.**
>    `ui/judgment_page.py` globs `lifecycle_*.md` and `lifecycle_all*.md`, but `pm judge` writes
>    `2026-08-28_1405_lifecycle_unh.md` — timestamp prefix, so the glob never matches. The ticker
>    parse (`stem.replace("lifecycle_","")`) breaks the same way.
> 2. **`/position/UNH` hangs for minutes.** `ui/position_story.py:275` calls
>    `core.judgment.lifecycle.retrieve_campaign()` **inline in the request** — a full campaign
>    recompute with benchmark counterfactuals (~2.7 min for UNH's 23 legs) on every page load.
>    The "reads artifacts, never recomputes" rule was applied to `/judgment` and missed here.
> 3. **Raw float dumps.** Cockpit Crosshairs renders `-0.006611570247933744` in →TRIM and
>    `0.6597777777777777` in →ADD. No number formatting layer exists.
> 4. Crosshairs SIGNAL column renders blank; DAYS LT / WASH crop off the right edge at pane width.
> 5. KPI row: DAY $/%, MTD, YTD/vs SPY all "—" — three of five tiles are empty chrome.
> 6. Header shows `Schwab AUTH REQUIRED` — the known dual token-signal disagreement
>    (`tasks/health.py` vs `_schwab_token_status()`, `CLAUDE.md` Known Issues) now has a third
>    surface repeating whichever signal it happened to read.
> 7. Sidebar carries a stray `Rotations tab` entry under SYSTEM.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — reproduce the glob bug
ls agent_outputs/judgment/ | head -12
python -c "from pathlib import Path; print(list(Path('agent_outputs/judgment').glob('lifecycle_*.md')))"

# 0.2 — reproduce the inline recompute
grep -n "retrieve_campaign" ui/position_story.py core/judgment/lifecycle.py

# 0.3 — confirm no formatter exists
grep -rn "def fmt_\|tabular\|format_pct\|format_money" ui/ | head

# 0.4 — the two token-status implementations
grep -n "_schwab_token_status\|def check_schwab" tasks/build_command_center.py tasks/health.py | head

# 0.5 — judge writers (for the JSON sidecar step)
grep -n "def format_.*markdown\|\.md\"" core/judgment/run.py core/judgment/lifecycle.py | head
```

---

## Phase 0 — Function (ship before any CSS)

### 0a — Fix the judgment globs
`*lifecycle*.md` / `*lifecycle_all*.md`; parse the ticker from the segment **after** `lifecycle_`,
not from the stem prefix. Add `test_judgment_page_glob.py` with a real-format filename — the test
that would have caught this.

### 0b — Kill the inline recompute
`/position/{ticker}` must render in **under one second** with no campaign on disk. Replace the
`retrieve_campaign()` call with a read of the newest `*lifecycle_<ticker>.md` artifact (plus the
JSON sidecar from Phase 2a once it exists). No artifact → render the Campaign block as
*"No campaign computed — run Lifecycle from Runs"* with the launcher link, exactly the `/judgment`
pattern. Never compute in a request handler; that rule is now global to `ui/` — add it as a comment
where the call was, and a `test_ui_no_inline_judgment.py` structural test (grep `ui/` for
`retrieve_campaign|build_campaign` → only artifact-reading modules allowed).

### 0c — One formatting layer
New `ui/format.py`, registered as Jinja filters, used by **every** template. No template renders a
raw model value again.

| Filter | Rule |
|---|---|
| `pct` | signed, 1 dp: `-0.66%`, `+30.8%` — from fractional or percent input, declared per call site |
| `money` | `$604,257` whole dollars; `$1.2M` past 7 digits |
| `money_range` | `$0–1,038 est.` |
| `days` | `77d` |
| `hash8` | first 8 chars + `…` |
| `dt` | `08:07` today, `Aug 27` this year, ISO otherwise |

All numerics: `font-variant-numeric: tabular-nums`, right-aligned, consistent dp per column.

### 0d — Small fixes
SIGNAL column populated (it's in the payload — bind it); remove the stray sidebar entry; tables get
`overflow-x: auto` on a wrapper so DAYS LT / WASH survive narrow panes instead of cropping.

### 0e — One token status
Header calls **one** function. Reconcile to `tasks/health.py`'s check as the single source (it owns
`HEALTH_FAILURE.flag`); `_schwab_token_status()` in the Command Center builder either delegates to it
or is documented as the phone-surface variant — decide, write it down in `CLAUDE.md` Known Issues,
and close the third occurrence of this two-signal disagreement.

---

## Phase 1 — Visual system (tokens first, pages second)

Benchmarks for density and restraint: Koyfin's watchlist tables, TradingView's dark chrome,
OpenBB's terminal layouts. The common grammar: **dark neutral surfaces, one accent, semantic
red/green reserved exclusively for P&L polarity, dense tabular type, charts that recede.**

### 1a — Design tokens (`ui/static/tokens.css`)
Single dark theme (deliberate single look — the Desk is a localhost instrument, not a themed site):

```css
--surface-0: #141517;  /* app background */
--surface-1: #1a1c1f;  /* cards, tables */
--surface-2: #22252a;  /* hover, table header */
--ink-1: #e8eaed;  --ink-2: #9aa0a8;  --ink-3: #6a7078;
--accent: #3987e5;                     /* links, active nav, focus — the ONLY accent */
--gain: #199e70;  --loss: #e66767;     /* P&L polarity ONLY — never status, never decoration */
--warn: #c98500;                       /* amber: stale, wash-window, ≤30d LT */
--grid: #2a2d33;
```

Rules that are not preferences: red/green appear **only** on signed P&L values; amber is the only
warning colour (the no-red-except-losses rule survives the redesign); every colour used on text
clears 3:1 on its surface; identity in charts is never colour-alone (direct labels stand in).

### 1b — Type & spacing
System font stack; 13px base for tables, 12px captions; **one hero number per page maximum**;
4/8/12/16 spacing scale; cards are flat `--surface-1` with 1px `--grid` borders — no shadows, no
gradients, no rounded-corner inflation.

### 1c — Components (Jinja partials, one each)
`stat_tile` (label, value, delta with polarity colour, optional 30-bar sparkline from `bars_daily`),
`data_table` (sticky header, right-aligned numerics, row hover, sortable), `signal_chip` (NEAR_TRIM
amber-outline / NEAR_ADD accent-outline / HOLD_TAX amber-filled / DISLOCATION neutral), `delta_bar`
(a signed inline bar for distance-to-trigger: accent toward add, amber toward trim, zero-centred),
`empty_state` (message + the launcher action that fills it), `meta_line` (hash, timestamps, N /
excluded-N — `--ink-3`, one line).

---

## Phase 2 — Backend build-outs that the UX actually needs

### 2a — JSON sidecars from `pm judge` *(the load-bearing one)*
The UI currently regex-parses markdown headers (`_parse_header`) — fragile, and it's why the page
knows almost nothing about its artifacts. Every judge writer emits `artifact.json` beside the `.md`:
campaign legs, dates, TWR, single-entry delta, counterfactuals, N / excluded-N / date ranges,
`retrieval_hash`, `computed_at`. UI renders from JSON; the `.md` stays the human/archival record.
Backfill is unnecessary — next run per ticker produces the sidecar.

### 2b — Campaign freshness registry
Table `judgment_campaigns` (ticker, computed_at, artifact_path, json_path, legs, retrieval_hash),
upserted by the lifecycle writer. Position Story reads it to show *"campaign as of Aug 28 — 2 fills
since"* (fills-since from `position_transactions`, a count query, not a recompute) with a refresh
launcher button. Stale is visible, never silently served.

### 2c — Morning increment
After evidence capture: for tickers with a fill in yesterday's transactions **only**, recompute the
campaign (bounded — a fill day touches one or two names, not 35). The cockpit stays current without
ever paying the 90-minute `--all` in a request or a morning.

### 2d — Sparkline data
`bars_for_ticker` last-30-closes, assembled in the cockpit's existing single `retrieve()` — no new
endpoint, no polling.

---

## Phase 3 — Page redesigns (using Phases 0–2)

**Cockpit `/`** — KPI row renders **only tiles with data**; missing fields collapse into the
existing one-line omission note instead of em-dash chrome. Total value gets the sparkline (SPY or
portfolio series if present). Crosshairs top 5 becomes: rank · ticker · `signal_chip` ·
`delta_bar` with `pct` label · `days`→LT · wash badge · `money_range` est. tax · earnings. The
`Cash %` caveat stays. Verify streak in the header shows its expected-green date on hover.

**`/positions`** — add signed Day% and Unrealized% with polarity colour; weight as a thin inline
bar against ceiling (ballast rows: no bar, no ceiling — suppression rule stands); `signal_chip`
column; sticky first column.

**`/position/{ticker}`** — artifact-read Campaign block (0b) leading with the **single-entry
delta**, TWR supporting, DWR suppressed when degenerate; holding-period ladder rendered as the
horizontal per-lot band chart (open → LT-crossover, today marked) it was specced as in the original
prompt 4 — the data is already on the page as a table; signal lane keeps its accrual banner.

**`/judgment`** — artifact cards from JSON sidecars: Unit A with N / excluded-N / date ranges
inline; Unit B a `data_table` of campaigns (ticker, legs, span, TWR, single-entry delta,
computed_at) sorted by legs; Unit C the calibration table with its live counter, unchanged.

**`/runs`** — running routine gets an elapsed timer and its ~duration estimate; history rows show
exit-code chips (0 green-outline, 3 neutral "skipped — lock held", 1 `--warn`); artifact links
inline.

**Charts (`ChartSpec` + partial only)** — grid to `--grid`, price line `--accent` 2px, cost-basis
line `--ink-3` dashed, buys `--gain` / sells `--loss` triangles with the 2px surface ring on
overlaps, same-week aggregation badges as built; axis labels `--ink-3` 11px; `chart_enhance.js`
crosshair readout restyled to tokens. **No library, no CDN** — the constraint stands.

---

## Post-build verification checklist

**Literal stdout + screenshots (cockpit, positions, position/UNH, judgment/lifecycle, runs).**

| # | Check | Expect |
|---|---|---|
| 1 | Lifecycle page lists artifacts | all 11 current files, sorted by legs |
| 2 | `/position/UNH` renders **< 1s** | time it; campaign from artifact; no `retrieve_campaign` in `ui/` |
| 3 | No raw floats anywhere | grep rendered HTML of all pages for `\d\.\d{6,}` → zero matches |
| 4 | SIGNAL populated | chips on all 5 cockpit rows |
| 5 | No cropped columns | tax trio visible at 800px pane width |
| 6 | Empty KPI tiles gone | missing fields → one omission line |
| 7 | Token status single-source | one function; `CLAUDE.md` note written |
| 8 | Red/green audit | grep templates/CSS: `--loss`/`--gain` only on P&L values |
| 9 | Contrast | every ink/surface pair ≥ 3:1 (list the computed ratios) |
| 10 | JSON sidecars | next `pm judge` run writes `.json`; UI reads it |
| 11 | Freshness registry | Position Story shows "as of / fills since"; refresh button launches |
| 12 | Morning increment bounded | log shows recompute only for yesterday's fill tickers |
| 13 | Ladder chart | per-lot bands on position page, today marked |
| 14 | Offline + static mirror | no CDN requests; publish-cockpit SVG unchanged |
| 15 | Tests | full suite green, including the two new structural tests |

## Out of scope
Tier 1/2 launcher routines (amendment decision stands) · any JS/chart library or CDN · light theme ·
remote access · any new analysis. Function and presentation only.
