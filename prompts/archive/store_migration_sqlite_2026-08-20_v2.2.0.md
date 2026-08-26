# Build Prompt: PortfolioStore — Gate Hardening + Bundle Parity (Tax Ledger First + Monitoring Publish)

**Author:** Cursor (gate correction) / Claude (parity + reconcile coverage), 2026-08-20
**Executor:** Cursor Agent (must re-run Step 0; do not trust author checkmarks)
**Prompt version:** 2.2.0
**Supersedes:**
- `prompts/archive/store_migration_sqlite_2026-08-20_v2.1.0.md` (gate hardening; incomplete reconcile coverage, no bundle parity, calendar-day streak)
- `prompts/archive/store_migration_sqlite_2026-08-20_v2.0.0.md` (structural fixes; soft gates)
- `prompts/archive/store_migration_sqlite_2026-08-20_v1.0.0.md` (positions-first + localhost UI)

**Fork decision:** **Monitoring** (multi-device). Phase 3 = Drive-published static HTML via existing `publish_analysis`, not localhost FastAPI. Sheets stays phone-readable for Tax_Control / Command Center until that publish path is trusted.

**Scope boundary:** This prompt covers the store migration only. Three unrelated backlog items are deliberately NOT in this file and must not be bundled into it:
- `prompts/fix_schwab_multi_account_2026-08-20.md`
- `prompts/fix_podcast_multi_signal_merge_2026-08-20.md`
- `prompts/agent_valuation_drift_monitor_2026-08-20.md`

If the executor finds itself touching `utils/schwab_client.py`, `tasks/batch_podcast_sync.py`, or `utils/agents/` while working this prompt, STOP — that is scope leak.

---

## Why v2.2

v2.1 restored the gates correctly. Three gaps remained:

1. **No bundle-hash parity check.** Phase 2 flips exactly the surfaces `core/bundle.py` consumes. If SQLite `NUMERIC` canonicalises differently from a Sheets string, every `composite_hash` shifts at cutover and pre-cutover agent outputs become unreproducible. The parity diff is only possible *while both backends are live* — it must be Phase 1 acceptance, not a Phase 2 discovery.
2. **Reconcile covered 2 of 3 lead surfaces.** `tax_control` shadows on `refresh tax --live` but never appeared in the verify table. The streak could go green while the surface that motivated the migration drifted unchecked.
3. **Streak defined in calendar days.** Morning runs are weekday-scheduled; a literal calendar-day implementation resets every Saturday and never reaches N.

---

## Step 0 — Verification gate (executor runs; paste RAW stdout under each)

Do **not** mark a box until the command has been run in this session and the **unedited** terminal output is pasted. No summarising, no `BAD_LITERALS=NONE`-style digests, no merging two commands' output into one block. Ugly raw paste is the requirement. Author assertions do not count.

- [ ] **No ORM outside `core/store`**

```text
rg -n "sqlalchemy|from sqlite3|import sqlite3|create_engine" --glob "*.py" -g "!core/store/**" -g "!archive/**"
# Expected: no matches (or only comments). Paste raw stdout, including empty output.
```

- [ ] **Tab constants present**

```text
python -c "import config; print(repr(config.TAB_VALUATION_CARD)); print(repr(config.TAB_DECISION_VIEW))"
# Expected: 'Valuation_Card' / 'Decision_View'. Paste raw stdout only for THIS command.
```

- [ ] **Builders use config (no worksheet string literals for those tabs)**

```text
rg -n "worksheet\([\"']Valuation_Card|worksheet\([\"']Decision_View" tasks utils --glob "*.py"
# Expected: no matches. Paste raw stdout.
```

```text
rg -n "TAB_VALUATION_CARD|TAB_DECISION_VIEW" tasks/build_valuation_card.py tasks/build_decision_view.py tasks/build_crosshairs.py tasks/build_command_center.py tasks/format_sheets_dashboard_v2.py
# Paste raw matches, one line per hit as rg emits them.
```

- [ ] **`publish_analysis` destination resolvable + command_center glob**

```text
python -c "from pathlib import Path; p=Path('scripts/backup_to_drive.py'); t=p.read_text(encoding='utf-8'); print('DEFAULT present', 'Portfolio_Analysis' in t); print('command_center glob', 'command_center' in t); print('exists', Path(r'G:\My Drive\Portfolio_Analysis').exists())"
# Paste raw stdout. If Drive unmounted, report False — do not invent True.
```

- [ ] **CLAUDE.md currency check**

```text
rg -n "Valuation_Card|Decision_View|Last verified" CLAUDE.md
# Paste raw stdout. If the tree's CLAUDE.md is older than 2026-08-10 or omits these tabs, Step 0 FAILS and stops.
```

- [ ] **Bundle serialiser located (new in v2.2)**

```text
rg -n "def .*hash|canonical|json.dumps|sort_keys" core/bundle.py
# Paste raw stdout. Identify the exact canonicalisation call the parity check must exercise.
```

If any box fails, **STOP** and report. Do not adapt silently.

---

## Hard constraints

- CLI owns execution; brokerage read-only; `--live` gates writes.
- AI never writes Holdings / Trade_Log / Target_Allocation.
- Bundles + thesis prose stay files.
- **No Alembic in Phase 1** — DB fully rebuildable from Schwab+Sheets during dual-write.
- Phase 3 must preserve phone access (Drive sync), not replace it with localhost.
- **Never convert a checkpoint into an assumption** (no author `[x]`, no auto read-flip, no vacuous streak).
- **No scope expansion beyond the tax vertical in Phase 1.** `holdings_current` may exist as a convenience cache; it is not acceptance and it does not pull rotations, style tables, or caches in behind it.

---

## Phase 0 — Contract freeze (keep)

Protocol + Sheets adapter + Tax_Control seam + tab roles. Unchanged intent.

---

## Phase 1 — Tax / lots / transactions vertical + backup + bundle parity (spine)

**Lead tables (not positions_current):**

1. `transactions` — shadow on `sync transactions --live`
2. `realized_gl` (lot-level) — shadow on `ingest realized-gl --live`
3. `tax_control` metrics + lots — shadow on `refresh tax --live`

`holdings_current` may exist as a convenience cache but is **not** Phase 1 acceptance.

### Backup (Phase 1 acceptance)

- `pm store backup --live`: `VACUUM INTO` dated file under `data/portfolio_store_backups/`
- SHA-256 sidecar
- Copy into Drive (`…/Portfolio_Analysis/db_backups/`) when mounted
- **Retention:** keep last `STORE_BACKUP_KEEP_DAILY` (default 14) + one-per-ISO-week for `STORE_BACKUP_KEEP_WEEKLY` (default 8); prune local and Drive after each live backup
- Dry-run by default
- **Lock safety:** backup must not run concurrently with a morning `--live` write. Acquire an exclusive lock or skip-with-warning; a `database is locked` traceback is a FAIL.

### Verify (value-level, all three lead surfaces)

`pm store verify` must compare Sheets vs SQLite **to the cent**:

| Surface | Fields |
|---|---|
| Realized_GL | row count, Proceeds, Cost Basis, Gain Loss $, ST Gain Loss, LT Gain Loss, Disallowed Loss |
| Transactions | row count, Net Amount, Amount, Fees |
| **Tax_Control** | **row count, every numeric metric key emitted by `refresh tax`, YTD realized ST total, YTD realized LT total, disallowed-loss total** |

Rules:
- Count-only PASS is a **FAIL**.
- Empty SQLite shadow is a **FAIL** (not a boot PASS).
- A surface absent from the comparison is a **FAIL** — verify must assert it covered all three, not silently skip one.
- Tolerance is exact-to-the-cent. No epsilon. If rounding differs, that is the finding.

### Bundle-hash parity (new in v2.2 — Phase 1 acceptance)

`pm store bundle-parity` builds the market bundle twice on the same run — once Sheets-sourced, once SQLite-sourced — and diffs.

- Report: `sheets_hash`, `sqlite_hash`, `MATCH` / `DIFFER`
- On `DIFFER`, emit the first N differing canonical-JSON paths (field-level), not just the hash
- Expected root causes: numeric type coercion (`"1234.5"` vs `1234.50`), date formatting, null-vs-empty-string, key ordering
- Must run inside the streak window, on a day with ≥1 transaction, and be recorded alongside verify results

Resolution is a **decision, not an auto-fix**:
- **Preferred:** normalise the serialiser so both backends canonicalise identically → hash lineage unbroken
- **Fallback:** declare a documented hash-lineage break in `CHANGELOG.md` recording the final Sheets-sourced `composite_hash`, the first SQLite-sourced hash, and the cutover date

Phase 2 cutover is **blocked** until parity is either MATCH or an accepted, logged lineage break.

### Streak gate (definition corrected in v2.2)

- Default `STORE_VERIFY_STREAK_N=5` consecutive **verify runs**, recorded in `logs/store_verify_streak.jsonl`
- A day with no scheduled run neither advances nor breaks the streak — weekends and holidays are skipped, not resets
- A FAIL breaks the streak and resets the counter to zero
- Window must include **≥1 Realized_GL Closed Date** (union across the N runs) — otherwise vacuous green on zero sales
- Window must include **≥1 `bundle-parity` result**
- Phase 2 cutover requires `pm store verify --require-streak` green

---

## Phase 2 — Explicit read flip + thesis numeric dual-truth

**Pre-flip requirement (new in v2.2):** produce `docs/sheets_hand_edit_inventory.md` listing every tab Bill edits by hand today, and for each: does a CLI path exist to make that edit after cutover? After the flip a manual Sheet edit is cosmetic — it survives until the next `pm export sheets` overwrites it and nothing downstream ever sees it. Any tab on that list without a CLI path blocks the flip for that surface.

- Reads honor **`STORE_PRIMARY` only** (default `sheets`). Never auto-flip because SQLite has rows.
- Flip by hand after streak: `set STORE_PRIMARY=sqlite` (or env / `.env`)
- One-line revert: `set STORE_PRIMARY=sheets`
- Vault sync numeric regions from store; prose untouched
- Alembic optional only when rebuild is no longer free

**Dual-write window discipline:** the window is the risk, not the reward — during it there are deliberately two systems of record, which is the condition the migration exists to end. Five green runs, parity resolved, then flip. A shadow ledger left running indefinitely because it is comfortable is worse than either endpoint.

---

## Phase 3 — Monitoring publish (static HTML → Drive)

Judge separately after living with Phase 2. Not part of the Phase 1–2 commitment.

- Render under `agent_outputs/command_center/`
- Publish via existing `publish_analysis` / `pm store publish-cockpit --live --publish`
- `pm ui serve` = debug only

---

## Explicit non-migrations

No thesis prose in SQL, no bundle rows, no Streamlit Cloud, no agent write-through.
**Phase 4 (cache/ledger tidy) is dropped, not deferred.** `data/fmp_cache`, ETF holdings cache, `.ingested.json`, `processed_videos.json` stay as files.

---

## Post-build verification checklist (raw stdout required)

Paste unedited command output under each. Agent-reported PASS tables do not count.

- [ ] `python -c "import config; print(config.STORE_BACKEND, config.STORE_PRIMARY, config.STORE_VERIFY_STREAK_N, config.STORE_BACKUP_KEEP_DAILY, config.STORE_BACKUP_KEEP_WEEKLY)"`
- [ ] `python manager.py store status` — shows `STORE_PRIMARY=sheets` by default
- [ ] `python manager.py store verify` — value-level lines for **all three** surfaces (`proceeds=…`, `tax_control.ytd_st=…`, `MATCH` / `FAIL`); exit code reflects result
- [ ] `python manager.py store verify` with one surface deliberately absent — must exit non-zero with a coverage error, not skip silently
- [ ] `python manager.py store bundle-parity` — prints `sheets_hash`, `sqlite_hash`, verdict; on DIFFER prints field paths
- [ ] `python manager.py store verify --require-streak` — exits 1 until N-green + ≥1 Closed Date + ≥1 parity result
- [ ] `python manager.py store backup` (dry-run) then `--live` once — result includes `pruned` keys
- [ ] Backup attempted during a simulated concurrent write — no `database is locked` traceback
- [ ] Confirm `prompts/archive/*_v1.0.0.md`, `*_v2.0.0.md`, `*_v2.1.0.md` exist; this file is **2.2.0**
- [ ] `rg -n "when SQLite populated|auto-flip|STORE_READ_PRIMARY" prompts/store_migration_sqlite_2026-08-20.md config.py core/store/dual_store.py` — no "populated → flip" language remains
- [ ] `git diff --stat` — no changes under `utils/schwab_client.py`, `tasks/batch_podcast_sync.py`, `utils/agents/` (scope-leak check)
