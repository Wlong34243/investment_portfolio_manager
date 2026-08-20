# Build Prompt: PortfolioStore — Phase 1 Gate Complete (Tax + Hash Parity)

**Author:** Cursor (gap patch), 2026-08-20  
**Executor:** Cursor Agent (must re-run Step 0; do not trust author checkmarks)  
**Prompt version:** 2.2.0  
**Supersedes:**
- `prompts/archive/store_migration_sqlite_2026-08-20_v2.1.0.md`
- `prompts/archive/store_migration_sqlite_2026-08-20_v2.0.0.md`
- `prompts/archive/store_migration_sqlite_2026-08-20_v1.0.0.md`

**Fork decision:** **Monitoring** (multi-device). Phase 3 = Drive-published static HTML via existing `publish_analysis`, not localhost FastAPI.

## Why v2.2

v2.1 restored gates but left three holes: no ledger/bundle-hash parity during dual-write, `tax_control` unreconciled while in the Phase 1 spine, and streak defined as calendar days (weekend-reset under weekday mornings). v2.2 closes all three.

## Step 0 — Verification gate (executor runs; **raw paste only**)

Do **not** mark a box until the command has been run in this session. Paste **raw stdout/stderr** under each box — no tidying, no merging with other commands, no `BAD_LITERALS=NONE` paraphrases. Empty stdout is valid and must be pasted as empty (or note "exit 1, no lines").

- [ ] **No ORM outside `core/store`**

```text
rg -n "sqlalchemy|from sqlite3|import sqlite3|create_engine" --glob "*.py" -g "!core/store/**" -g "!archive/**"
```

- [ ] **Tab constants present**

```text
python -c "import config; print(repr(config.TAB_VALUATION_CARD)); print(repr(config.TAB_DECISION_VIEW))"
```

- [ ] **Builders use config (no worksheet string literals for those tabs)**

```text
rg -n "worksheet\([\"']Valuation_Card|worksheet\([\"']Decision_View" tasks utils --glob "*.py"
rg -n "TAB_VALUATION_CARD|TAB_DECISION_VIEW" tasks/build_valuation_card.py tasks/build_decision_view.py tasks/build_crosshairs.py tasks/build_command_center.py tasks/format_sheets_dashboard_v2.py
```

- [ ] **`publish_analysis` destination resolvable + command_center glob**

```text
python -c "from pathlib import Path; t=Path('scripts/backup_to_drive.py').read_text(encoding='utf-8'); print('DEFAULT present', 'Portfolio_Analysis' in t); print('command_center glob', 'command_center' in t); print('exists', Path(r'G:\\My Drive\\Portfolio_Analysis').exists())"
```

- [ ] **CLAUDE.md conflict check**

```text
rg -n "Valuation_Card|Decision_View|Last verified" CLAUDE.md
```

If any box fails, **STOP** and report.

## Hard constraints

- CLI owns execution; brokerage read-only; `--live` gates writes.
- AI never writes Holdings / Trade_Log / Target_Allocation.
- Bundles + thesis prose stay files.
- **No Alembic in Phase 1.**
- Phase 3 preserves phone access (Drive).
- Never convert a checkpoint into an assumption.
- **Raw stdout in checklists** — digests do not count.

## Phase 0 — Contract freeze (keep)

Protocol + Sheets adapter + Tax_Control seam + tab roles.

## Phase 1 — Tax / lots / transactions + backup + hash parity (spine)

**Lead tables:**

1. `transactions` — shadow on `sync transactions --live`
2. `realized_gl` — shadow on `ingest realized-gl --live`
3. `tax_control` metrics + lots — shadow on `refresh tax --live`

**Backup:** `pm store backup --live` with keep-daily / keep-weekly prune.

**Verify (all three surfaces, value-level):**

| Surface | Fields |
|---|---|
| Transactions | row count, Net Amount, Amount, Fees |
| Realized_GL | row count, Proceeds, Cost Basis, Gain Loss $, ST/LT, Disallowed Loss |
| Tax_Control | KPI money metrics (excl. timestamps); lots row count + Gain Loss / ST / LT / Disallowed sums |

**Ledger hash parity (Phase 1 acceptance — not deferred):**

`pm store verify` builds a canonical fingerprint of txn + realized + tax_control from **both** backends (money normalized to cents; same SHA-256 canonical JSON discipline as `core/bundle.py`) and requires `ledger_hash.sheets == ledger_hash.sqlite`. This is the dual-write window where serialization drift is cheap to catch. Empty shadow / count-only PASS is FAIL.

**Streak:**

- `STORE_VERIFY_STREAK_N` (default 5) consecutive **verify runs** with `ok=True`
- Days with no verify neither advance nor break the streak
- Non-vacuous: ≥1 run in the window had `realized_row_count > 0`
- Cutover: `pm store verify --require-streak`

## Phase 2 — Explicit `STORE_PRIMARY` flip + thesis numeric dual-truth

- Default `STORE_PRIMARY=sheets`; hand flip to `sqlite` only after streak; revert `set STORE_PRIMARY=sheets`
- Vault sync numeric regions from store

### Before flip — inventory hand-edited Sheets tabs

After `STORE_PRIMARY=sqlite`, Sheet cell edits on store-backed surfaces become cosmetic until the next export overwrites them. Before flip, inventory tabs Bill still edits by hand and ensure each has a CLI write path (or stays Sheets-primary intentionally).

Starting list (confirm / extend in Step 0 of Phase 2 — do not invent):

| Tab | Typical hand edit | CLI path today |
|---|---|---|
| `Target_Allocation` | weights / targets | none by design (manual-only) |
| `Trade_Log_Staging` | Status approve/reject | `pm journal promote` (acts on approved) |
| Thesis files (vault) | prose / triggers | `pm` thesis sync (numeric regions) |
| `Agent_Outputs` / AI surfaces | review only | sandbox — not authoritative |
| `Tax_Control` / `Holdings_Current` / `Transactions` / `Realized_GL` | should be pipeline-only | refresh / sync / ingest |

Anything on an extended hand-edit list that lacks a CLI path blocks the flip for that surface.

## Phase 3 — Monitoring publish (static HTML → Drive)

Unchanged: `pm store publish-cockpit --live --publish`; `pm ui serve` debug-only.

## Post-build verification checklist (raw stdout)

- [ ] `python -c "import config; print(config.STORE_BACKEND, config.STORE_PRIMARY, config.STORE_VERIFY_STREAK_N, config.STORE_BACKUP_KEEP_DAILY, config.STORE_BACKUP_KEEP_WEEKLY)"`
- [ ] `python manager.py store status`
- [ ] `python manager.py store verify` — must show txn + realized + tax_control MATCH lines **and** `ledger_hash MATCH`
- [ ] `python manager.py store verify --require-streak`
- [ ] `python manager.py store backup` then one `--live` (result includes `pruned`)
- [ ] Confirm archives: `v1.0.0`, `v2.0.0`, `v2.1.0` under `prompts/archive/`; this file is **2.2.0**
- [ ] `rg -n "calendar days|when SQLite populated|auto-flip" prompts/store_migration_sqlite_2026-08-20.md config.py core/store/verify.py`
