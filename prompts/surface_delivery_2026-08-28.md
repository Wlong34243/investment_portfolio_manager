# Surface Delivery — put the built capabilities where Bill already looks

**Created:** 2026-08-28
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Sits ahead of prompt 10 in the queue.** Depends on prompts 1, 2, 3, 4, 5, 6, 9 — all shipped.
**Source:** Bill, 2026-08-28: *"my problem is with the interface... i don't want these in a command
line tool only."*

> **The finding that prompted this file.** `build_crosshairs.py` computes `days_to_lt`,
> `wash_window_open` and `est_tax_cost_low/high`. `build_decision_view.py` and
> `build_command_center.py` contain **zero references to any of them** (verified 2026-08-28).
> The one dollar-denominated capability in the whole Instrument is invisible on the surface Bill
> actually opens every morning. That is not an interface preference — it is the feature not being
> delivered.
>
> **The governing rule for this prompt: a capability that only exists behind a terminal has not
> shipped.** Four steps, all of them plumbing, none of them new capability.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — confirm the gap this prompt exists to close
grep -n "est_tax_cost_low\|days_to_lt\|wash_window_open" tasks/build_crosshairs.py | head
grep -n "est_tax_cost_low\|days_to_lt\|wash_window_open" tasks/build_decision_view.py tasks/build_command_center.py

# 0.2 — the writers and their layouts
grep -n "^def \|HEADER\|_build_position_table\|batch_update" tasks/build_decision_view.py | head -20
grep -n "def _build_position_table" -A 25 tasks/build_command_center.py | head -40

# 0.3 — tab inventory and manual-authority precedent
grep -n "TAB_" config.py | head -30
grep -n -A6 "Target_Allocation\|Decision_Log" PORTFOLIO_SHEET_SCHEMA.md | head -30

# 0.4 — precommit CLI surface to mirror
python manager.py journal precommit --help

# 0.5 — the chunker line-anchor defect (Step 4)
sed -n '20,35p;130,150p' core/corpus/chunker.py
python -c "
from pathlib import Path
t=Path('vault/theses/MU_thesis.md').read_text(encoding='utf-8')
print('total lines:', t.count(chr(10))+1)
print('first 3 lines:', t.split(chr(10))[:3])
"
```

**Expected at 0.1:** hits in `build_crosshairs.py`, **none** in the two Sheet writers. If the Sheet
writers already carry them, this prompt's Step 1 is already done — stop and report that.

---

## Step 1 — Tax facts onto the Sheet *(highest value; do this first even if nothing else lands)*

Bill opens `0_DASHBOARD` and `Decision_View` every morning, on a phone. That is where a tax fact at
the moment of decision belongs.

### 1a — `Decision_View` (room for columns)

`tasks/build_decision_view.py` is clear-and-rebuild, so this is additive. Append after the existing
columns — **do not insert**, for the same reason the `Trade_Log` migration appended: positional
readers and a documented history of column misalignment.

| Column | Source | Notes |
|---|---|---|
| `Days_To_LT` | `days_to_lt` | nearest-crossing open lot |
| `Wash_Window` | `wash_window_open` | `OPEN through YYYY-MM-DD` or blank |
| `Est_Tax_Low` | `est_tax_cost_low` | |
| `Est_Tax_High` | `est_tax_cost_high` | |

**Header must carry the word ESTIMATE** on the two dollar columns — prompt 9's labelling rule is not
optional, and a bare number in a spreadsheet cell reads as authoritative.

**Annotate only where it means something.** `NEAR_TRIM` and `HOLD_TAX` rows get values;
`NEAR_ADD`, `DISLOCATION` and `MISSING_LEVEL` rows leave them blank. A days-to-LT figure on an add
signal is noise, and this dashboard already suffers from noise crowding out the actionable row.

### 1b — `0_DASHBOARD` top five (fixed grid, no room for columns)

The Command Center is a fixed layout and **anything written outside
`build_command_center`'s grid construction is erased on the next run** (`CLAUDE.md`, What NOT to Do).
So the change goes *inside* `_build_position_table()`, and it adds no columns.

One compact cell appended to each top-5 row that has a trim-side signal:

```
77d→LT · wash open · est $0–1,038
```

Blank when there is no trim-side signal. Keep it under ~40 characters so it survives a phone column
width. If the grid genuinely cannot take another cell, put it in the Tax Posture block (rows 6–8)
as a single line naming the nearest-crossing ticker instead — but try the row first, because the
value is in it sitting next to the name it applies to.

### 1c — Formatting

`tasks/format_sheets_dashboard_v2.py` already conditionally formats `Decision_View`. Extend it:
`Wash_Window` non-blank → amber; `Days_To_LT` ≤ 30 → amber. No red. These are facts, not alarms, and
`CLAUDE.md` Analysis Rule 8 says rank by actionability rather than shouting.

---

## Step 2 — The local UI runs itself

`pm ui serve` from a terminal is why Position Story and Corpus Search have not been used. Make
`http://127.0.0.1:8765` a bookmark that is simply always live.

Add `scripts/install_ui_service.ps1` registering a scheduled task:

- **Trigger:** at logon, current user. No elevation — this runs in Bill's own context.
- **Action:** `C:\Dev\Investment_Portfolio\.venv\Scripts\pythonw.exe manager.py ui serve`
  (`pythonw`, not `python` — no console window).
- **Start in:** repo root.
- **Settings:** restart on failure (3 attempts, 1 minute apart); do not stop on idle; do not stop on
  battery.
- **Registration must verify:** query the task back and print its state, the way
  `setup_wake_timer.ps1` should have. A task that registers but never runs is a pattern this repo
  has already lived through once.

**Do not make this a Windows service** and do not add a supervisor. A logon task is the right
weight for a single-user localhost tool.

---

## Step 3 — Declare a pre-commitment without a terminal

> **This is the step that decides whether the expensive half of the build ever pays.** The judgment
> thesis is proportional to how many triggers Bill declares in advance, and
> `pm journal precommit --ticker META --type fwd_pe --side trim --level 28 --action "..."` is exactly
> the friction that killed blank-prompt journaling. Zero real declarations exist today.

**Route it through Sheets, not the UI.** Sheets owns manual entry and the CLI ingests it — the same
pattern as `Target_Allocation` and `Decision_Log`. This needs **no mutation amendment** (still
deferred to Phase 6a), works from Bill's phone, and puts declaration in the surface he already has
open when he is thinking about a position.

### 3a — New tab `Precommitments`, manual authority

| Col | Header | Notes |
|---|---|---|
| A | `Date_Declared` | **Bill types this.** It becomes `declared_at` — not the ingest date. |
| B | `Ticker` | |
| C | `Trigger_Type` | `price` / `fwd_pe` / `trailing_pe` / `discount_from_high` / `price_to_book` |
| D | `Side` | `trim` / `add` |
| E | `Level` | |
| F | `Intended_Action` | free text — "trim to 2%" |
| G | `Note` | free text — his reasoning at declaration time |
| H | `Ingested_At` | **written by the pipeline**, blank until ingested |
| I | `Precommit_ID` | written by the pipeline |
| J | `Status` | written by the pipeline: `open` / `fired` / `closed_*` |

Register in `config.TAB_*`, document in `PORTFOLIO_SHEET_SCHEMA.md` under **Manual** authority, and
cover it in `column_guard`.

### 3b — Ingest in the morning

New step in `pm morning`, immediately before precommit firing detection. Rows with blank
`Ingested_At` → `precommitments` table.

- **Append and mark only. Never clear-and-rebuild this tab** — Bill is typing into it, and a
  rebuild that lands while he has a half-written row open destroys his input. This is the one tab in
  the system where the human is the writer and the pipeline is the reader.
- `declared_at` comes from column A, not from ingest time. If A is blank, **skip the row and report
  it** rather than substituting today — a declaration with a manufactured date is the seeded-bootstrap
  problem in a different costume.
- Reject a level that references a sell-side price target (standing rule; consensus targets ratchet).
- Where the declared level disagrees with the thesis band, ingest it anyway and **flag it in the
  morning output**. Bill may be declaring a deliberate departure; the system does not get to refuse
  his declaration, only to notice.
- `--live` gated. Dry run prints what it would ingest.

### 3c — Response, same surface

Pending firings currently surface only via `pm journal precommit --pending`. Add the pending count to
the morning output **and** to `Decision_View` as a row per pending firing, so an unanswered firing is
visible where he already looks. Recording the response stays CLI or local UI for now — the
declaration is the high-friction half and it is the half this step fixes.

---

## Step 4 — Fix the citation line anchors *(a citation you cannot open is a surface failure too)*

**Observed 2026-08-28:** `[thesis:vault/theses/MU_thesis.md:L38]` — the quoted sentence is actually at
L57–58. The FTS snippet was correct; the chunk's `line_start` was wrong. Three of four citations in
that answer opened cleanly; the thesis one did not.

`_line_of(text, pos)` returns `text.count("\n", 0, pos) + 1`, which is correct **if `text` is the
original file**. The likely defect is that the chunker receives a preprocessed body — frontmatter
stripped, or normalized — while the citation renders against the file on disk. That produces a
constant offset per file rather than random drift, which matches an ~19-line discrepancy on a thesis
with a frontmatter block.

**Fix:** compute `line_start` / `line_end` against the original file bytes, carrying an offset if the
indexed body was derived from a slice. Then `pm corpus index --live --rebuild --yes`; the index is
regenerable and gitignored, so a rebuild costs minutes.

**Verification is a sample, not a spot-check.** Draw at least five hits from **every** `source_type`,
open each at `line_start` outside the app, and confirm the snippet appears verbatim. Report a table
of source_type → checked → passed. Any source_type below 100% is a fail; report the offset pattern
rather than fixing the one file.

Add `test_corpus_line_anchor_roundtrip.py`: for a synthetic document with frontmatter, every chunk's
`line_start` maps to the line in the original text where its `body` begins.

---

## Post-build verification checklist

**Literal stdout, plus a phone screenshot for rows 3–4.**

| # | Check | Expect |
|---|---|---|
| 1 | Step 0.1 re-run after Step 1 | Sheet writers now reference the tax fields |
| 2 | `Decision_View` columns | four new, appended, ESTIMATE in the dollar headers |
| 3 | Values only on trim-side rows | add / dislocation rows blank |
| 4 | `0_DASHBOARD` top five | compact tax cell on trim-signal rows; grid otherwise unchanged |
| 5 | Grid integrity | re-run `pm refresh dashboard`; layout unchanged, nothing erased |
| 6 | Conditional formatting | amber on open wash window and ≤30 days |
| 7 | UI task registered | `schtasks /query /tn "PortfolioUI" /fo list /v` |
| 8 | UI survives reboot | reboot, browse `http://127.0.0.1:8765/position/MU` with no terminal open |
| 9 | No console window | `pythonw`, nothing visible in the taskbar |
| 10 | `Precommitments` tab | created, headers correct, `column_guard` passes |
| 11 | Hand-typed row ingests | type one row, `pm morning` dry → reports; `--live` → row in `precommitments` |
| 12 | `declared_at` honest | equals column A, **not** the ingest timestamp |
| 13 | Blank date skipped | leave A blank → row skipped and named, no substitution |
| 14 | Tab never rebuilt | type a partial row, run morning `--live`, confirm the partial row survives untouched |
| 15 | Band mismatch flagged | declare off-thesis → ingested **and** flagged |
| 16 | Pending visible on Sheet | a pending firing appears on `Decision_View` |
| 17 | Line anchors | ≥5 hits per source_type opened at `line_start`; table of results, all 100% |
| 18 | MU citation | re-run the row-4 gate question; `[thesis:...MU_thesis.md:L…]` now opens to the quoted sentence |
| 19 | Tests | `python -m pytest tests/ -q` |

---

## Documentation to update on completion

- **`PORTFOLIO_SHEET_SCHEMA.md`** — `Precommitments` tab under Manual authority; new `Decision_View`
  columns; note that `Precommitments` is append-and-mark, never clear-and-rebuild.
- **`CLAUDE.md`** — `Precommitments` in the manual-authority list; one line under What NOT to Do:
  *do not clear-and-rebuild `Precommitments` — the human is the writer on that tab*; note that the
  local UI runs as a logon task.
- **`state.md`** — dated entry; record that the tax annotations were computed but unsurfaced from
  2026-08-27 to today, since that is the kind of gap worth not repeating.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- Any new analysis, agent, or capability. This prompt surfaces what exists.
- A remote/hosted UI. Sheets plus `publish-cockpit` remains the phone path; localhost stays local.
- The mutation amendment. Step 3 routes through Sheets precisely to avoid needing it.
- Response capture on the Sheet. Declaration is the high-friction half; responses stay CLI/UI.
- Reformatting `0_DASHBOARD` beyond the single added cell.
