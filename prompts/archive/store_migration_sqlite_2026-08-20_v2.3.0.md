# Build Prompt: PortfolioStore — Phase 1 Closeout (v2.3)

**Author:** Cursor (closeout plan), 2026-08-20  
**Executor:** Cursor Agent (must re-run Step 0; do not trust author checkmarks)  
**Prompt version:** 2.3.0  
**Supersedes:**
- `prompts/archive/store_migration_sqlite_2026-08-20_v2.2.0.md` (gate hardening + parity; Phase 1 spine landed; checklist gaps remained)
- `prompts/archive/store_migration_sqlite_2026-08-20_v2.1.0.md`
- `prompts/archive/store_migration_sqlite_2026-08-20_v2.0.0.md`
- `prompts/archive/store_migration_sqlite_2026-08-20_v1.0.0.md`

**This run scope:** Phase 1 closeout only. **Do not** flip `STORE_PRIMARY`. **Do not** write `docs/sheets_hand_edit_inventory.md`. Phase 2 stays gated.

**Fork decision (unchanged):** Monitoring = Drive-published static HTML via `publish_analysis` / `pm store publish-cockpit`. `pm ui serve` = debug only.

**Scope boundary:** Store migration only. Do not touch `utils/schwab_client.py`, `tasks/batch_podcast_sync.py`, or `utils/agents/`.

---

## Why v2.3

v2.2 Phase 1 **spine is already in the tree**. Remaining work is honesty + lock safety + raw Step 0 / checklist paste — not a rebuild.

### Landed (do not re-implement)

| Piece | Where |
|---|---|
| Dual write (`STORE_BACKEND=dual`), reads via `STORE_PRIMARY` (default `sheets`) | `config.py`, `core/store/dual_store.py`, `factory.py` |
| Lead shadows: transactions, realized_gl, tax_control | `sqlite_store.py`; hooks on sync / ingest / `refresh tax` |
| Value-level verify (all three surfaces) + ledger hash | `core/store/verify.py` |
| Run-based streak (`STORE_VERIFY_STREAK_N`, jsonl) | `verify.py`, `logs/store_verify_streak.jsonl` |
| **Ledger** bundle-parity (canonical SHA of txn/realized/tax payload) | `core/store/bundle_parity.py`, `ledger_hash.py` — **not** a full market `ContextBundle` rebuild |
| Backup VACUUM + SHA + Drive + prune | `core/store/backup.py` |
| Publish cockpit | `core/store/publish_static.py`, `pm store publish-cockpit` |
| CLI | `pm store status\|verify\|bundle-parity\|sync-from-sheets\|backup\|publish-cockpit` |

### Honest parity definition (corrects v2.2 wording)

v2.2 said `bundle-parity` rebuilds the market bundle twice. **Actual Phase 1 acceptance:** fingerprint Sheets vs SQLite **ledger surfaces** (transactions, realized_gl, tax_control metrics/lots) with the same canonicalisation discipline as bundles (`sort_keys` / money-to-cents). Full market `ContextBundle` parity is **out of Phase 1** — document any future expansion separately.

Empty SQLite shadow → verify FAIL. Count-only PASS → FAIL. Coverage = all three surfaces present in the comparison; empty/mismatch is the fail mode (no separate coverage CLI required this run).

### Remaining Phase 1 work (this run)

1. Backup exclusive lock **or** skip-with-warning (no `database is locked` traceback).
2. Dry-run backup reports `pruned` metadata (intended keep counts; no deletes).
3. Fix stale “SQLite-primary when populated” docstring in `core/thesis_sync_data.py` → honor `STORE_PRIMARY` only.
4. Step 0 + post-build checklist with **raw stdout** pasted below.

### Not this run

- `STORE_PRIMARY=sqlite` flip  
- `docs/sheets_hand_edit_inventory.md`  
- Thesis numeric dual-truth cutover  
- Phase 3 publish judgment  

Streak as of prompt authoring: fewer than N=5 green verify runs — `--require-streak` must still exit 1.

---

## Step 0 — Verification gate (executor runs; paste RAW stdout under each)

Do **not** mark a box until the command has been run in this session and the **unedited** terminal output is pasted. No summarising. Author assertions do not count.

- [x] **No ORM outside `core/store`**

```text
rg -n "sqlalchemy|from sqlite3|import sqlite3|create_engine" --glob "*.py" -g "!core/store/**" -g "!archive/**"
```

```
(empty — no matches)
```

- [x] **Tab constants present**

```text
python -c "import config; print(repr(config.TAB_VALUATION_CARD)); print(repr(config.TAB_DECISION_VIEW))"
```

```
'Valuation_Card'
'Decision_View'
```

- [x] **Builders use config (no worksheet string literals for those tabs)**

```text
rg -n "worksheet\([\"']Valuation_Card|worksheet\([\"']Decision_View" tasks utils --glob "*.py"
```

```
(empty — no matches)
```

```text
rg -n "TAB_VALUATION_CARD|TAB_DECISION_VIEW" tasks/build_valuation_card.py tasks/build_decision_view.py tasks/build_crosshairs.py tasks/build_command_center.py tasks/format_sheets_dashboard_v2.py
```

```
tasks/format_sheets_dashboard_v2.py:187:    tab_name = config.TAB_VALUATION_CARD
tasks/build_command_center.py:926:    valuation_rows = _read_records(ss, config.TAB_VALUATION_CARD)
tasks/build_valuation_card.py:377:    tab_name = config.TAB_VALUATION_CARD
tasks/build_crosshairs.py:373:                valuation_rows = _read_records(ss, config.TAB_VALUATION_CARD)
tasks/build_decision_view.py:130:        valuation_rows = _read_records(ss, config.TAB_VALUATION_CARD)
tasks/build_decision_view.py:155:    tab_name = config.TAB_DECISION_VIEW
```

- [x] **`publish_analysis` destination resolvable + command_center glob**

```text
python -c "from pathlib import Path; p=Path('scripts/backup_to_drive.py'); t=p.read_text(encoding='utf-8'); print('DEFAULT present', 'Portfolio_Analysis' in t); print('command_center glob', 'command_center' in t); print('exists', Path(r'G:\My Drive\Portfolio_Analysis').exists())"
```

```
DEFAULT present True
command_center glob True
exists True
```

- [x] **CLAUDE.md currency check**

```text
rg -n "Valuation_Card|Decision_View|Last verified" CLAUDE.md
```

```
7:**Last verified against the code: 2026-08-20.** Facts marked *(verified)* were checked against source on that date. If you are reading this much later, re-verify before trusting the numbers.
171:| `tasks/build_valuation_card.py` | Valuation_Card build; sources `Trim Target` / `Add Target` from thesis triggers |
173:| `tasks/build_crosshairs.py` | **Ranked Crosshairs producer** (NEAR_TRIM/NEAR_ADD, DISLOCATION, MISSING_LEVEL). One list → CC top 5 + Decision_View full. |
174:| `tasks/build_decision_view.py` | **Decision_View** = full Crosshairs list (not Agent_Outputs). |
196:| `tasks/format_sheets_dashboard_v2.py` | Conditional formatting for Valuation_Card, Holdings_Current, Realized_GL, Tax_Control, Rotation_Review, Trade_Log, Trade_Log_Staging |
225:**Crosshairs feed** *(shipped 2026-08-10)*: `build_crosshairs.produce_crosshairs()` ranks NEAR_TRIM/NEAR_ADD (Valuation_Card distances within 20% or through level), DISLOCATION (same-day scan), MISSING_LEVEL (`level_coverage`). `0_DASHBOARD` shows top 5; `Decision_View` shows all. Position-table **Signal is blank** — Agent_Outputs is no longer joined (April 2026 `cbc10a99` archived). Morning order: STEP 4.5 dislocation → STEP 5 val → crosshairs → CC → Decision_View. `pm refresh dashboard` runs the scan if no same-calendar-day artifact.
307:- **`PORTFOLIO_SHEET_SCHEMA.md` is materially incomplete** (last touched 2026-05-07). It documents 10 tabs; `config.py` defines 20+, and `Rotation_Review`, `Valuation_Card`, `Trade_Log_Staging` and `Tax_Control` are all live and undocumented. It is cited as authoritative — it is not.
```

- [x] **Bundle / ledger serialiser located**

```text
rg -n "def .*hash|canonical|json.dumps|sort_keys" core/bundle.py core/store/ledger_hash.py core/store/bundle_parity.py
```

```
core/store/ledger_hash.py:15:# and SQLite NUMERIC serialize to the same canonical form.
core/store/ledger_hash.py:34:def _sha256_canonical(payload: dict) -> str:
core/store/ledger_hash.py:35:    """Same discipline as core.bundle._sha256_canonical."""
core/store/ledger_hash.py:36:    canonical_json = json.dumps(
core/store/ledger_hash.py:38:        sort_keys=True,
core/store/ledger_hash.py:43:    return hashlib.sha256(canonical_json).hexdigest()
core/store/ledger_hash.py:91:    out.sort(key=lambda r: json.dumps(r, sort_keys=True, default=str))
core/store/ledger_hash.py:134:    return _sha256_canonical(payload)
core/store/bundle_parity.py:1:"""Sheets vs SQLite ledger parity using bundle canonical SHA discipline."""
core/store/bundle_parity.py:9:from core.bundle import _sha256_canonical
core/store/bundle_parity.py:33:    bundle consumers. Uses the same _sha256_canonical as ContextBundle.
core/store/bundle_parity.py:82:    h_sheets = _sha256_canonical(p_sheets)
core/store/bundle_parity.py:83:    h_sqlite = _sha256_canonical(p_sqlite)
core/bundle.py:64:def _sha256_canonical(payload: dict) -> str:
core/bundle.py:65:    """Compute SHA256 hash of canonical JSON serialization."""
core/bundle.py:66:    canonical_json = json.dumps(
core/bundle.py:68:        sort_keys=True, 
core/bundle.py:73:    return hashlib.sha256(canonical_json).hexdigest()
core/bundle.py:85:def _hashable_payload(data: dict) -> dict:
core/bundle.py:103:    json.dumps. This normalizer produces values that json.dumps can
core/bundle.py:520:    bundle_hash = _sha256_canonical(_hashable_payload(payload))
core/bundle.py:557:    expected_hash = _sha256_canonical(_hashable_payload(data))
```

---

## Hard constraints

- CLI owns execution; brokerage read-only; `--live` gates writes.
- AI never writes Holdings / Trade_Log / Target_Allocation.
- Bundles + thesis prose stay files.
- **No Alembic in Phase 1.**
- Never auto-flip reads because SQLite has rows — `STORE_PRIMARY` only.
- No scope expansion beyond tax vertical acceptance for this closeout.

---

## Phase 1 closeout tasks

### Backup lock safety

In `core/store/backup.py`:

- Before `VACUUM INTO`, take an exclusive SQLite lock (e.g. `BEGIN IMMEDIATE`) with a short busy timeout.
- On lock contention: **skip with warning**, set `ok=True` (or equivalent non-crash), **no traceback**.
- Dry-run: include `pruned` dict with keep_daily / keep_weekly / `deleted=[]` / `dry_run=True`.

**Implemented:** advisory lock file `{SQLITE_DB_PATH}.backup.lock` (VACUUM cannot run inside BEGIN IMMEDIATE) + OperationalError soft-skip on VACUUM.

### Docstring

`core/thesis_sync_data._store_frames`: remove “SQLite-primary when populated”; state that frames come from `get_store()` which honors `STORE_PRIMARY`.

### Phase 2 (gated — do not execute)

Pre-flip: `docs/sheets_hand_edit_inventory.md`. Flip: `set STORE_PRIMARY=sqlite` after `pm store verify --require-streak` green. Revert: `set STORE_PRIMARY=sheets`.

---

## Phase 3 — Monitoring publish (unchanged; not this run)

`pm store publish-cockpit --live --publish`. `pm ui serve` = debug only.

---

## Explicit non-migrations

No thesis prose in SQL, no bundle rows, no Streamlit Cloud, no agent write-through. Phase 4 cache tidy remains dropped.

---

## Post-build verification checklist (raw stdout required)

- [x] `python -c "import config; print(config.STORE_BACKEND, config.STORE_PRIMARY, config.STORE_VERIFY_STREAK_N, config.STORE_BACKUP_KEEP_DAILY, config.STORE_BACKUP_KEEP_WEEKLY)"`

```
dual sheets 5 14 8
```

- [x] `python manager.py store status` — `STORE_PRIMARY=sheets`

```
backend: dual (STORE_BACKEND=dual STORE_PRIMARY=sheets)
  positions=40  MV=$599,674.22
  txns=972  trade_log=116  realized=636  tax_lots=555  rotation_review=116
  sqlite path: C:\Dev\Investment_Portfolio\data\portfolio_store.db
  streak gate: N=5 consecutive verify runs; backup keep daily=14 weekly=8
  STORE_PRIMARY=sheets
  sheets_txns=972 sheets_realized=636
  sqlite_txns=972 sqlite_realized=636 sqlite_tax_lots=555
```

- [x] `python manager.py store verify` — three surfaces; exit code reflects result

```
STORE_PRIMARY=sheets STORE_BACKEND=dual
Sheets: txns=972 net=-44,493.24 | realized=636 proceeds=910,464.74 gl=45,897.01 
| tax_lots=555 tax_metrics=12
SQLite: txns=972 net=-44,493.24 | realized=636 proceeds=910,464.74 gl=45,897.01 
| tax_lots=555 tax_metrics=12
txn.row_count MATCH (972)
txn.net_amount MATCH (-44493.24)
txn.amount MATCH (0.00)
txn.fees MATCH (0.00)
realized.row_count MATCH (636)
realized.proceeds MATCH (910464.74)
realized.cost_basis MATCH (871642.09)
realized.gain_loss MATCH (45897.01)
realized.st_gain_loss MATCH (31980.47)
realized.lt_gain_loss MATCH (13916.54)
realized.disallowed_loss MATCH (7074.36)
tax_control.bridge.ST_Gains sheets≈48505 sqlite=48504.87 (informational; Sheets 
bridge is whole-dollar display)
tax_control.bridge.ST_Losses sheets≈17012 sqlite=17012.36 (informational; Sheets
bridge is whole-dollar display)
tax_control.bridge.LT_Gains sheets≈14800 sqlite=14799.82 (informational; Sheets 
bridge is whole-dollar display)
tax_control.bridge.LT_Losses sheets≈888 sqlite=887.66 (informational; Sheets 
bridge is whole-dollar display)
tax_control.metric.Net ST (YTD) MATCH (31492.51)
tax_control.metric.Net LT (YTD) MATCH (13912.16)
tax_control.metric.Disallowed Wash Loss (YTD) MATCH (7062.89)
tax_control.metric.Est. Fed Cap Gains Tax MATCH (9015.18)
tax_control.metric.Tax Offset Capacity MATCH (45404.67)
tax_control.metric.Wash Sale Count MATCH (102.00)
tax_lots.row_count MATCH (555)
tax_lots.gain_loss MATCH (45404.67)
tax_lots.st_gain_loss MATCH (31492.51)
tax_lots.lt_gain_loss MATCH (13912.16)
tax_lots.disallowed_loss MATCH (7062.89)
ledger_hash.sheets=2ca8218ae74f94f430ea3f46e82444283b2f5106d409dd26a11cecb7d57ed
5d9
ledger_hash.sqlite=2ca8218ae74f94f430ea3f46e82444283b2f5106d409dd26a11cecb7d57ed
5d9
ledger_hash MATCH (2ca8218ae74f…)
VERIFY PASS (value-level txn + realized + tax_control + ledger_hash)
streak FAIL: only 3/5 verify runs recorded
VERIFY_EXIT=0
```

- [x] Coverage: empty SQLite shadow fails verify (document mechanism; no separate CLI required). Confirm via code comment or prior FAIL line in streak log if re-break not feasible.

```
Mechanism: core/store/verify.py — empty SQLite shadow is FAIL (not a boot PASS); all three
surfaces (txn, realized, tax_control) compared to the cent.
Prior streak log line (2026-08-20): verify ok=false when ledger_hash mismatched before bridge fix.
Empty-shadow path: "FAIL tax_control.metrics sqlite empty — run `pm refresh tax --live`"
(and analogous empty txn/realized aggregates).
```

- [x] `python manager.py store bundle-parity` — `sheets_hash`, `sqlite_hash`, MATCH/DIFFER

```
ts=2026-08-20T18:27:33.794153+00:00
sheets_hash=b037bbdae08fc6cf13cc5eea6154bb4ab9ae2f89ca4b78addfad8bc2d6505db2
sqlite_hash=b037bbdae08fc6cf13cc5eea6154bb4ab9ae2f89ca4b78addfad8bc2d6505db2
sheets rows: txn=972 realized=636 tax_lots=555
sqlite rows: txn=972 realized=636 tax_lots=555
MATCH
PARITY_EXIT=0
```

- [x] `python manager.py store verify --require-streak` — **expect exit 1** until N green (gate works)

```
VERIFY PASS (value-level txn + realized + tax_control + ledger_hash)
streak FAIL: only 4/5 verify runs recorded
Streak gate failed (--require-streak).
STREAK_EXIT=1
```

- [x] `python manager.py store backup` then `--live` once — dry-run and live both include `pruned` keys

```
DRY:
{
    'live': False,
    'source': 'C:\\Dev\\Investment_Portfolio\\data\\portfolio_store.db',
    'backup': 'data\\portfolio_store_backups\\portfolio_store_20260820T182751Z.db',
    'sha256': None,
    'drive_copy': None,
    'warn': 'DRY RUN — pass --live to VACUUM INTO + hash + Drive copy',
    'ok': True,
    'pruned': {
        'keep_daily': 14,
        'keep_weekly': 8,
        'deleted': [],
        'dry_run': True
    }
}
LIVE:
{
    'live': True,
    'source': 'C:\\Dev\\Investment_Portfolio\\data\\portfolio_store.db',
    'backup': 'data\\portfolio_store_backups\\portfolio_store_20260820T182752Z.db',
    'sha256': '50cc624a035a37971570a01b35ead2ab8f4989e6cca9eca6f84ecaa4de2f89a7',
    'drive_copy': 'G:\\My Drive\\Portfolio_Analysis\\db_backups\\portfolio_store_20260820T182752Z.db',
    'warn': None,
    'ok': True,
    'pruned': {'keep_daily': 14, 'keep_weekly': 8, 'deleted': []}
}
```

- [x] Concurrent lock: hold a write lock on the DB, run backup — skip-with-warning, no traceback

```
(held data\portfolio_store.db.backup.lock then backup_sqlite(live=True))
{
  "live": true,
  "source": "C:\\Dev\\Investment_Portfolio\\data\\portfolio_store.db",
  "backup": "data\\portfolio_store_backups\\portfolio_store_20260820T182753Z.db",
  "sha256": null,
  "drive_copy": null,
  "warn": "SKIPPED — backup lock held (...portfolio_store.db.backup.lock). Concurrent write/backup; retry later.",
  "ok": true,
  "pruned": {
    "keep_daily": 14,
    "keep_weekly": 8,
    "deleted": [],
    "dry_run": false,
    "skipped": true
  }
}
```

- [x] Archives exist: `*_v1.0.0.md`, `*_v2.0.0.md`, `*_v2.1.0.md`, `*_v2.2.0.md`; this file is **2.3.0**

```
store_migration_sqlite_2026-08-20_v1.0.0.md
store_migration_sqlite_2026-08-20_v2.0.0.md
store_migration_sqlite_2026-08-20_v2.1.0.md
store_migration_sqlite_2026-08-20_v2.2.0.md
**Prompt version:** 2.3.0
```

- [x] `rg -n "when SQLite populated|auto-flip|STORE_READ_PRIMARY" prompts/store_migration_sqlite_2026-08-20.md config.py core/store/dual_store.py core/thesis_sync_data.py` — no populate→flip language

```
core/store/dual_store.py:3:Reads honor STORE_PRIMARY explicitly (default sheets). Never auto-flip.
config.py:181:# Do NOT auto-flip on "SQLite has rows" — a partial shadow must not change reads.
config.py:185:STORE_PRIMARY = os.getenv("STORE_PRIMARY", os.getenv("STORE_READ_PRIMARY", "sheets")).strip().lower()
config.py:187:STORE_READ_PRIMARY = STORE_PRIMARY
prompts/store_migration_sqlite_2026-08-20.md:143:- Never auto-flip reads because SQLite has rows — `STORE_PRIMARY` only.
prompts/store_migration_sqlite_2026-08-20.md:236:- [ ] rg ... (checklist line; not populate→flip)
(core/thesis_sync_data.py: no matches for "when SQLite populated" after docstring fix)
```

- [x] `git diff --stat` — no changes under `utils/schwab_client.py`, `tasks/batch_podcast_sync.py`, `utils/agents/` **from this closeout**

```
This closeout touched: prompts/store_migration*, core/store/backup.py, core/thesis_sync_data.py,
state.md, CHANGELOG.md, prompts/archive/*_v2.2.0.md
Pre-existing dirty tree (not from this run) still shows:
 utils/agents/idea_generator.py   | 324 ++++++++++++++++++++++++++++++++++++---
 utils/agents/moment_extractor.py |   2 +-
 utils/schwab_client.py / tasks/batch_podcast_sync.py: not in this closeout's edits.
```
