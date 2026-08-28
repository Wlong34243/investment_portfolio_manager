# Evidence Capture — permanent signal, bar and fundamentals record

**Created:** 2026-08-27
**Executor:** Cursor (Agent mode, `claude-opus-5` or equivalent). Claude Code / Gemini CLI also acceptable.
**Prompt 1 of 10** in the Instrument build set. **Depends on: nothing. Gates: all nine others.**
**Source:** `docs/architecture/06_the_instrument_roadmap.md` (amended 2026-08-27) — Phase 1 (Memory), evidence half.

> **Naming note, read once.** The roadmap's "Phase 1–6" is a *third* numbering scheme in this repo.
> `docs/phase-prompts/phase1..5_prompts.md` (Apr–May 2026) and the Schwab data-expansion "Phases 1–4"
> (Aug 2026, `prompts/schwab_data_expansion_2026-08-25.md` et al.) already use those numbers for
> different work. **This build set is therefore named by capability, never by phase number.** Do not
> introduce `phase1_*` filenames, CLI names, or table names.

> **Correction to the roadmap.** The roadmap states this work is already specced at
> `prompts/evidence_capture_phase1_2026-08-26.md`. **That file does not exist in the repo**
> (verified 2026-08-27 against the working tree). This file is the spec, not a supplement to one.

---

## Why this is first

Every other prompt in this set reads something this one writes. Two of the three retrospective
questions in the roadmap are computable from data already on disk; the third loses one day of
permanent record per day it isn't built. Nothing here is backfillable.

---

## Step 0 — Verification gate (no code until every line is confirmed)

Run each check and **paste literal stdout**. If any check disagrees with the expectation, **STOP and
report.** Do not adapt silently.

```bash
# 0.1 — the roadmap's claimed spec file must be ABSENT. If it exists, stop: this file duplicates it.
ls prompts/evidence_capture_phase1_2026-08-26.md 2>&1

# 0.2 — store models are blob-per-tab today; no typed evidence tables exist
grep -n "__tablename__" core/store/models.py

# 0.3 — live DB path and whether it sits inside the Drive-synced tree
python -c "import config; print(config.SQLITE_DB_PATH)"
ls -d .tmp.drivedownload .tmp.driveupload 2>&1

# 0.4 — current physical schema
python -c "import sqlite3,config;\
[print(r[0]) for r in sqlite3.connect(str(config.SQLITE_DB_PATH)).execute(\
\"select name from sqlite_master where type='table' order by name\")]"

# 0.5 — the producers this prompt will tap
grep -n "def produce_crosshairs" tasks/build_crosshairs.py
grep -n "def get_bars" utils/price_history.py
grep -n "def fetch_instrument_fundamentals" utils/schwab_client.py
grep -n "def _emit\|MISSING_LEVEL\|NEAR_TRIM\|DISLOCATION" tasks/build_crosshairs.py | head -20

# 0.6 — the exact morning step sequence, so the new step lands in the right place
grep -n "STEP " manager.py | head -40

# 0.7 — backup surface to extend rather than duplicate
grep -n "^def \|^class " core/store/backup.py
```

**Expected at 0.1:** `No such file or directory`.
**Expected at 0.2:** ten tables, all `payload_json`-shaped, none named `signal_events`, `bars_daily`
or `fundamentals_snapshot`.
**Expected at 0.3:** a path under `data/`, and both `.tmp.drive*` directories present — i.e. the live
ledger is inside a Google-Drive-synced tree. That is the defect Step 4 fixes.

---

## Design constraints (non-negotiable, from `CLAUDE.md`)

1. **Append-only.** These three tables are the permanent record. No `UPDATE`, no `DELETE`, no
   clear-and-rebuild. The `_replace_table()` pattern in `core/store/sqlite_store.py` is for the
   Sheets mirror tables and **must not be reused here**.
2. **Typed columns, not `payload_json`.** The existing mirror tables are blobs because they shadow
   Sheet tabs. Evidence tables are queried by range, ticker and date by four downstream prompts, so
   they get real columns. Keep a `payload_json` column *in addition*, holding the full source row, so
   nothing is lost to schema choices made today.
3. **Idempotent.** Re-running `pm morning --live` twice in one day must not double-write. Every table
   gets a `UNIQUE` constraint and writers use `INSERT OR IGNORE`, reporting the ignored count.
4. **`--live` gated.** A write to these tables is a mutation of the permanent record and requires
   `--live`, exactly like a Sheets write. This is a deliberate resolution of code-audit item A8
   ("dry-run `pm morning` still writes to disk") *for these tables only* — record the decision, do
   not generalise it to the rest of A8.
5. **Read-only on the brokerage.** Nothing here calls an order endpoint. Fundamentals and bars come
   from existing clients only.
6. **No new vendor.** Extend `utils/fmp_client.py` / `utils/schwab_client.py` / `utils/price_history.py`.

---

## Step 1 — Typed evidence models

Append to `core/store/models.py`. Do **not** create a parallel models module — `get_engine()` calls
`Base.metadata.create_all(_engine)`, so new subclasses of `Base` are created automatically and no
migration framework is needed. **Note the corollary and write it into the docstring:** because there
is no Alembic, a *changed* column on an existing table will not migrate. Get these right now.

### `signal_events`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `event_date` | Date | trading date the signal describes |
| `captured_at` | DateTime(tz) | when the row was written |
| `ticker` | String(32), indexed | |
| `signal_type` | String(32) | `NEAR_TRIM` / `NEAR_ADD` / `DISLOCATION` / `MISSING_LEVEL` / `HOLD_TAX` |
| `trigger_type` | String(32), nullable | `price` / `fwd_pe` / `trailing_pe` / `discount_from_high` / `price_to_book` / `ceiling_only` |
| `metric_value` | Float, nullable | the reading that fired it |
| `band_level` | Float, nullable | the declared level it was measured against |
| `band_side` | String(8), nullable | `trim` / `add` |
| `distance_pct` | Float, nullable | signed distance to the level |
| `rank_bucket` | Int | Crosshairs bucket (400+ = doctrine-downgraded) |
| `rank` | Int | position within the day's list |
| `source` | String(32) | `crosshairs` / `dislocation_scan` / `level_coverage` |
| `doctrine_downgraded` | Bool | true when `doctrine_reader.downgrade_rule` re-ranked it |
| `payload_json` | Text | the full Crosshairs row as emitted |
| `fingerprint` | String(128) UNIQUE | `sha256(event_date|ticker|signal_type|trigger_type|source)` |

**Capture the whole ranked list, not the dashboard's top 5.** `build_crosshairs.produce_crosshairs()`
produces one list; `0_DASHBOARD` shows five and `Decision_View` shows all. The evidence table takes
all. A signal that never reached the top 5 is exactly the "signal you passed on" that Phase 3's
calibration table is built to score — dropping it would silently bias the retrospective toward
signals Bill saw.

**Capture doctrine-downgraded rows too**, with the flag set. A `HOLD_TAX` downgrade is a decision the
system made on Bill's behalf and belongs in the record.

### `bars_daily`

`ticker`, `bar_date`, `open`, `high`, `low`, `close`, `volume`, `source` (`yfinance` | `schwab`),
`captured_at`. `UNIQUE(ticker, bar_date, source)` — **source is part of the key, not a tiebreak.**
`Rotation_Review` is frozen at `Price_Source=yfinance|frozen_pre_schwab_2026-08-25` (Bill, 2026-08-25);
two sources must be able to coexist for the same bar without either overwriting the other. Index
`(ticker, bar_date)`.

Populate through `utils/price_history.get_bars()` — the existing router — never by calling yfinance or
Schwab directly from the writer.

### `fundamentals_snapshot`

`ticker`, `as_of_date`, `fwd_pe`, `trailing_pe`, `price_to_book`, `market_cap`, `dividend_yield`,
`week52_high`, `week52_low`, `eps`, `source`, `captured_at`, `payload_json`.
`UNIQUE(ticker, as_of_date, source)`.

`week52_high` / `week52_low` / `dividend_yield` come from the widened Schwab quote extraction shipped
in `schwab_data_expansion_2026-08-25.md` Step 3b. **Verify in Step 0.5 that those fields are actually
populated** before wiring them; if the widening landed but consumers were never rewired (tier 8 of
`price_history_migration_2026-08-25.md`), the columns may exist and be empty. Record which, in stdout.

---

## Step 2 — Writers

New module `core/store/evidence.py`. One public function per table plus a status reader:

```
record_signal_events(rows: list[dict], *, event_date, live: bool) -> EvidenceWriteResult
record_bars(ticker: str, bars: pd.DataFrame, *, source: str, live: bool) -> EvidenceWriteResult
record_fundamentals(rows: list[dict], *, as_of_date, live: bool) -> EvidenceWriteResult
evidence_status() -> dict   # per table: row count, distinct trading days, first/last date
```

`EvidenceWriteResult` reports `attempted`, `inserted`, `ignored_duplicate`, `table`. Every writer
returns without touching the DB when `live is False` and prints what it *would* have written.

**Do not route these through `PortfolioStore`.** The `PortfolioStore` Protocol is a
replace-semantics contract over Sheet mirrors; append-only evidence is a different shape and adding
it to the Protocol would force `SheetsPortfolioStore` and `DualPortfolioStore` to implement writers
that make no sense for them. Evidence is SQLite-only, by design — say so in the module docstring.

---

## Step 3 — Wire into `pm morning`

From Step 0.6 you have the real step list. Insert evidence capture **after** Crosshairs is produced
and **after** Decision_View is written, so the captured list is byte-identical to what Bill saw.

- Signals: from the in-memory Crosshairs list. Do **not** re-read `Decision_View` back out of Sheets —
  that round-trips through `read_gsheet_robust()` and the pandas ≥3.0 string-dtype bug class
  (`CLAUDE.md` Known Issues) is exactly the sort of thing that would silently zero `distance_pct`.
- Bars: for every held ticker plus every ticker on the watchlist, incremental — request only dates
  after `max(bar_date)` per ticker.
- Fundamentals: one row per held ticker per trading day.

Skip capture entirely on a non-trading day, via `utils/market_calendar.is_trading_day`. Log the skip.

**New CLI surface** (extend the existing `store_app`, do not add a new Typer app):

```
pm store evidence-status        # counts, distinct trading days, first/last per table
pm store evidence-capture       # standalone capture for backfill/repair; --live required to write
```

---

## Step 4 — Relocate the live ledger off the Drive-synced tree

**⚠️ Mid-prompt sign-off gate. Present the plan and stop. Do not move the file until Bill says go.**

The repo root carries `.tmp.drivedownload` and `.tmp.driveupload`, so `C:\Dev\Investment_Portfolio`
is a Drive-synced tree and `data/portfolio_store.db` is a live SQLite file inside it. Drive syncing a
file with an open WAL is a corruption path, and it gets worse the moment this prompt starts appending
to it daily.

1. Propose `SQLITE_DB_PATH=C:\Dev\_local\portfolio_store.db` (outside any synced tree). Bill confirms
   or names another path.
2. Set it in `.env` only. **Do not change the default in `config.py`** — the default is what a fresh
   clone gets, and the relocation is machine-local.
3. Move, don't copy: `python manager.py store backup --live` first, then move the `.db` and any
   `-wal` / `-shm` siblings, then `pm store status` to prove the ledger reads from the new path.
4. Add a guard in `core/store/models.get_engine()`: walk up from the resolved DB path; if any parent
   contains `.tmp.drivedownload` or `.tmp.driveupload`, emit a `logger.warning` naming the path. A
   warning, not a hard fail — a fresh clone on a machine with no Drive should still work, and Bill
   may knowingly run it from a synced tree on another box.
5. Confirm `.gitignore` still covers the *old* path so a stale copy can't be committed. It already
   ignores `data/portfolio_store.db` and `data/portfolio_store.db-*` — verify, don't assume.

---

## Step 5 — `VACUUM INTO` snapshots with retention

**Extend `core/store/backup.py`.** Do not create a new backup module.

```
pm store snapshot            # dry run: names the file it would write, reports source size
pm store snapshot --live     # VACUUM INTO data/portfolio_store_backups/portfolio_store_YYYYMMDD.db
```

- `VACUUM INTO` specifically, not a file copy — it is transactionally consistent against an open
  database, which a copy is not.
- Destination stays inside the Drive-synced tree. **That is the point:** after Step 4 the live ledger
  is local and unsynced, so the snapshot is the thing Drive carries offsite. Say this in the
  docstring, or someone will "fix" it later by moving the snapshots out too.
- Retention: keep 14 daily, then 8 weekly (Monday's), then 12 monthly (the 1st). Prune under `--live`
  only, and **print every filename before deleting it**.
- Refuse to prune if the newest snapshot is older than 48 hours — a broken snapshot job must not
  quietly eat the history it stopped adding to.

---

## Step 6 — Provenance inventory

The question this answers: *if the local ledger were lost tomorrow, what could Schwab not give back?*

Add `pm store provenance`, printing a markdown table to stdout with one row per data class:

| Data class | Location | Regenerable from | Verdict |
|---|---|---|---|

Rows to include, at minimum — verify each against the working tree rather than copying this list:
`transactions`, `realized_gl`, `holdings_current`, `tax_control_lots` (Schwab-regenerable, bounded by
the broker's own retention window — state the window, don't guess it); `Trade_Log` `Implicit_Bet` /
`Thesis_Brief` (Bill's writing — **not regenerable by anything**); `vault/theses/` and
`vault/doctrine.md` (Bill's writing, in git); `data/podcast_transcripts/`, `data/podcast_summaries/`,
`data/spotify_digests/`, `data/moments/` (gitignored, re-fetchable only while the source URL lives —
**effectively not regenerable**); `agent_outputs/` (gitignored, model output, not reproducible even
from the same bundle); `signal_events` / `bars_daily` / `fundamentals_snapshot` (**not regenerable —
this prompt's entire justification**).

**Extend, don't proliferate.** The generated table lands as a new `## Data Provenance` section in
`CLAUDE.md`, placed immediately after `## Bundle Architecture`. Do not create a standalone
`PROVENANCE.md` — per `CLAUDE.md`, standalone analysis docs get written once and never opened.

---

## Step 7 — The accrual gate

Write `evidence_first_accrual_date` into `meta_kv` on the first successful `--live` capture.

`pm store evidence-status` prints, and this is the gate the whole roadmap turns on:

```
signal_events: 1,204 rows | 7 trading days accrued | first 2026-08-27 | last 2026-09-05
GATE: NOT MET — 3 more clean trading days required before any retrospective reads this table.
```

Ten clean trading days. "Clean" means captured on a day `is_trading_day()` returned true, with no
`HEALTH_FAILURE.flag` raised. Downstream prompts (4, 6, 7, 8) must call `evidence_status()` and refuse
to produce a retrospective while the gate is unmet — **and must say so out loud rather than degrading
to a partial answer.**

Note for whoever reads this in six weeks: the *ten-day* gate is a data-hygiene gate for the writers.
Phase 3's calibration table has its own, much longer, six-month gate. They are not the same gate and
meeting the first does not release the second.

---

## Tests

Add to `tests/` (extend the existing pytest layout; no new runner):

- `test_evidence_idempotent.py` — write the same day's signal rows twice, assert
  `inserted == n` then `inserted == 0, ignored_duplicate == n`.
- `test_evidence_dry_run.py` — assert zero rows written when `live=False`, and that the function
  still returns a populated `attempted` count.
- `test_evidence_bars_dual_source.py` — same `(ticker, bar_date)` from `yfinance` and `schwab` both
  persist, neither overwrites the other.
- `test_evidence_gate.py` — `evidence_status()` reports GATE NOT MET below 10 distinct trading days.

---

## Post-build verification checklist

**Paste literal stdout/stderr for every row. An agent-reported "PASS" table is not evidence** —
on 2026-08-08 a checklist item was reported PASS while the artifact header contradicted it.

| # | Check | Command | Expect |
|---|---|---|---|
| 1 | Tables created | `sqlite_master` query from Step 0.4 | three new names present |
| 2 | Columns typed | `PRAGMA table_info(signal_events)` | typed columns, not a lone `payload_json` |
| 3 | Dry run writes nothing | `pm store evidence-capture` then row count | count unchanged |
| 4 | Live run writes | `pm store evidence-capture --live` then row count | count increases; `inserted` matches |
| 5 | Second live run is a no-op | repeat 4 | `inserted == 0`, `ignored_duplicate == n` |
| 6 | Full list captured | count of `signal_events` for today vs `len(Decision_View)` | **equal** — not 5 |
| 7 | Downgrades captured | `select count(*) ... where doctrine_downgraded=1` | matches the day's HOLD_TAX count |
| 8 | Non-trading day skips | run on a weekend | logged skip, zero rows |
| 9 | DB relocated | `python -c "import config;print(config.SQLITE_DB_PATH)"` + `pm store status` | new path, ledger reads |
| 10 | Sync guard fires | temporarily point `SQLITE_DB_PATH` back into the repo | warning names the path |
| 11 | Snapshot consistent | `pm store snapshot --live`, then open the snapshot and count a table | opens; counts match |
| 12 | Retention prints before deleting | `pm store snapshot --live` with >14 dailies present | filenames listed, then pruned |
| 13 | Stale-snapshot refusal | backdate the newest snapshot >48h | prune refused, reason printed |
| 14 | Provenance table | `pm store provenance` | table renders; evidence rows marked not-regenerable |
| 15 | Gate reports | `pm store evidence-status` | GATE line with a real remaining-day count |
| 16 | Morning integrates | `pm morning` then `pm morning --live` | dry writes nothing; live captures once |
| 17 | Tests | `python -m pytest tests/ -q` | all pass, paste the summary line |
| 18 | No `--live` bypass | `grep -rn "record_signal_events\|record_bars\|record_fundamentals" --include=*.py` | every call site passes `live=` |

---

## Documentation to update on completion

- **`CLAUDE.md`** — new `## Data Provenance` section (Step 6); `core/store/evidence.py` added to Key
  Files; a Hard Rules sub-note that evidence tables are append-only and `--live`-gated, and that this
  resolves A8 *for these tables only*; the no-Alembic corollary from Step 1.
- **`state.md`** — under *What's Working Today*, a dated entry with the real first-accrual date and
  the gate status. Under *What's Next*, the date the ten-day gate is expected to clear.
- **`PORTFOLIO_SHEET_SCHEMA.md`** — extend the *Local ledger* paragraph (currently line ~43) to
  distinguish mirror tables from evidence tables. These are not Sheet tabs and must not be described
  as if they were.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- Any retrospective, scoring or calibration logic. That is gated on six months of accrual.
- The FTS index. That is prompt 2, deliberately separate: it is backfillable and has no clock.
- Rewiring existing consumers onto `bars_daily`. They read `utils/price_history` today and that is
  fine; a rewire is its own gated tier, per the tier-8 precedent in `price_history_migration_2026-08-25.md`.
- Any Sheet tab for evidence. It is local-ledger-only.
