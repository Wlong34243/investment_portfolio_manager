# Build Prompt: PortfolioStore — Phase 2 Read Flip (v2.4)

**Author:** Cursor (Phase 2 plan), 2026-08-21  
**Executor:** Cursor Agent (must re-run Step 0; do not trust author checkmarks)  
**Prompt version:** 2.4.0  
**Supersedes:**
- `prompts/archive/store_migration_sqlite_2026-08-20_v2.3.0.md` (Phase 1 closeout)
- `prompts/archive/store_migration_sqlite_2026-08-20_v2.2.0.md`
- `prompts/archive/store_migration_sqlite_2026-08-20_v2.1.0.md`
- `prompts/archive/store_migration_sqlite_2026-08-20_v2.0.0.md`
- `prompts/archive/store_migration_sqlite_2026-08-20_v1.0.0.md`

**This run scope:** Phase 2 — finish streak, hand-edit inventory, route Tier-2 readers through `get_store()`, hand-flip `STORE_PRIMARY=sqlite`. Dual-write stays on. Market bundle stays Schwab/API.

**Fork decision (unchanged):** Monitoring = Drive-published static HTML. `pm ui serve` = debug only.

**Scope boundary:** Store migration only. Do not touch `utils/schwab_client.py`, `tasks/batch_podcast_sync.py`, or `utils/agents/`.

---

## Hash governance (post-flip — read before Step 0)

Two different lineages; do not conflate them:

| Surface | Governs | Source after Phase 2 |
|---|---|---|
| Market `bundle_hash` / positions / prices | Market snapshot reproducibility | **Schwab (or CSV)** via `core/bundle.py` — **not** `STORE_PRIMARY` |
| Ledger fingerprint / `pm store bundle-parity` | Sheets↔SQLite agreement on txn, realized_gl, tax_control | Dual-write; verify compares both |
| Composite Tier-2 `Trade_Log` / recent_rotations | Rotation context baked into composite | **`get_store()` → `STORE_PRIMARY`** (must be sqlite after flip) |
| Thesis sync numerics | Vault frontmatter/size figures | **`get_store()` → `STORE_PRIMARY`** |

Before flip, ledger parity MATCH proves Sheets and SQLite agree. After flip, `get_store()` consumers must not bypass to raw `sheet_readers` for Trade_Log / holdings / realized / transactions — or two “current states” coexist (violates hard rule #2).

---

## Why v2.4

Phase 1 spine + closeout landed. Remaining: streak N=5, inventory, route `composite_bundle` (and peers) through `get_store()`, hand flip.

**Depth (locked):** option 2 — env flip + route leftover Tier-2 readers. Not a market-bundle rewrite.

---

## Step 0 — Verification gate (paste RAW stdout)

- [x] **Hash governance paragraph present in this file** (above) — confirm by rg:

```text
rg -n "Hash governance|STORE_PRIMARY|Schwab" prompts/store_migration_sqlite_2026-08-20.md
```

```
13:**This run scope:** Phase 2 — ... STORE_PRIMARY=sqlite ... Market bundle stays Schwab/API.
21:## Hash governance (post-flip — read before Step 0)
27:| Market `bundle_hash` ... | **Schwab (or CSV)** ... — **not** `STORE_PRIMARY` |
29:| Composite Tier-2 `Trade_Log` ... | **`get_store()` → `STORE_PRIMARY`** ...
```

- [x] **No ORM outside `core/store`**

```text
rg -n "sqlalchemy|from sqlite3|import sqlite3|create_engine" --glob "*.py" -g "!core/store/**" -g "!archive/**"
```

```
(empty — no matches)
```

- [x] **composite_bundle Trade_Log path (post-route)**

```text
rg -n "get_store|sheet_readers" core/composite_bundle.py
```

```
40:    recent_rotations: list[dict]  # From Trade_Log via get_store() / STORE_PRIMARY
117:        from core.store import get_store
119:        trade_log_df = get_store().get_trade_log()
```

- [x] **Streak status (pre-flip)**

```text
python manager.py store verify --require-streak
```

```
VERIFY PASS ...
streak PASS: 5 consecutive green verify runs (latest
ts=2026-08-21T13:39:03.312495+00:00); max_realized_rows=636; parity_ok_count=3
STREAK_EXIT=0
```

---

## Hard constraints

- CLI owns execution; brokerage read-only; `--live` gates writes.
- Hand flip only; never auto-flip because SQLite has rows.
- Dual-write remains (`STORE_BACKEND=dual`).
- Revert: set `STORE_PRIMARY=sheets` in `.env` (and `$env:STORE_PRIMARY="sheets"` for the current shell).
- Any post-flip verify FAIL → revert immediately.

---

## Phase 2 tasks

1. Write `docs/sheets_hand_edit_inventory.md` — Bill sign-off on any **blocked** row before flip.
2. Route `core/composite_bundle.py` Trade_Log (and grep peers under `core/` / vault sync) through `get_store()`.
3. Streak + same-day `bundle-parity` MATCH.
4. Set `STORE_PRIMARY=sqlite`; smoke; verify; update `state.md` / `CHANGELOG.md`.

**Executed 2026-08-21.** No blocked inventory rows. Flip via `.env` `STORE_PRIMARY=sqlite` (ASCII; UTF-8 rewrite after a Windows-1252 em-dash broke `load_dotenv`).

---

## Post-build checklist (raw stdout)

- [x] Inventory file exists; no unresolved blocked rows (or Bill override noted)

```
docs/sheets_hand_edit_inventory.md — Blocked rows: None.
```

- [x] `rg -n "get_store\(\)\.get_trade_log|sheet_readers" core/composite_bundle.py` — store path, no direct sheet_readers Trade_Log

```
117:        from core.store import get_store
119:        trade_log_df = get_store().get_trade_log()
(no sheet_readers)
```

- [x] `pm store verify` + `bundle-parity` + `verify --require-streak` green **before** flip

```
VERIFY PASS; streak PASS 5/5; PARITY MATCH sheets_hash=sqlite_hash=b037bbda…
```

- [x] Flip command used + `pm store status` shows `STORE_PRIMARY=sqlite`

```
.env: STORE_PRIMARY=sqlite
$env:STORE_PRIMARY = "sqlite"
backend: dual (STORE_BACKEND=dual STORE_PRIMARY=sqlite)
  ...
  STORE_PRIMARY=sqlite
SMOKE: reader SqlitePortfolioStore; trade_log_rows 116
```

- [x] Post-flip `pm store verify` PASS; dual-write still on

```
VERIFY PASS ... streak PASS ... VERIFY_EXIT=0
PARITY MATCH ... PARITY_EXIT=0
STORE_BACKEND=dual
```

- [x] Archives: `*_v2.3.0.md` exists; this file is **2.4.0**

```
prompts/archive/store_migration_sqlite_2026-08-20_v2.3.0.md
**Prompt version:** 2.4.0
```
