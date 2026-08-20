# Build Prompt: PortfolioStore + SQLite Shadow Ledger + Local UI

**Author:** Cursor (plan execution), 2026-08-20  
**Executor:** Cursor Agent  
**Prompt version:** 1.0.0  
**Source plan:** `.cursor/plans/sqlite_store_migration_1cc4c265.plan.md`

## Objective

Introduce a `PortfolioStore` abstraction, SQLite shadow dual-write, reconcile CLI, SQLite-primary reads for computed views, and a local FastAPI+HTMX read-mostly Command Center — without breaking Sheets as the daily cockpit through Phase 2, and without moving thesis prose or hash-stamped bundles into SQL.

## Hard constraints (do not violate)

- CLI owns execution; brokerage remains read-only.
- Every mutating path stays behind `--live` (dry-run by default).
- AI never writes Holdings / Trade_Log / Target_Allocation.
- Bundles stay file-based SHA-256 snapshots.
- Thesis prose stays markdown; only numeric regions may be machine-written.
- No Streamlit Cloud, no MCP platform bet, no auto-trading.

## Step 0 — Verification gate (confirm before / as you code)

- [ ] Grep confirms **no** existing `sqlite3` / `sqlalchemy` / `duckdb` / ORM usage in active `*.py`.
- [ ] `config.py` lacks `TAB_VALUATION_CARD` / `TAB_DECISION_VIEW` (string literals in builders).
- [ ] Sheets is the only live UI (`archive/streamlit_legacy/` only).
- [ ] Tab role inventory matches plan: authoritative / computed / sandbox / manual.

If Step 0 finds a pre-existing DB layer, STOP and report.

## Phase 0 — Contract freeze

1. Add `TAB_VALUATION_CARD` / `TAB_DECISION_VIEW` to `config.py`; replace literals in builders.
2. Document tab roles (extend `PORTFOLIO_SHEET_SCHEMA.md` authority matrix for Agent_Outputs*).
3. Add `core/store/` with `PortfolioStore` Protocol + `SheetsPortfolioStore`.
4. Wire Tax_Control refresh through the store seam (prove the interface).

## Phase 1 — SQLite shadow ledger

1. SQLAlchemy models + `data/portfolio_store.db` (path via config).
2. `DualPortfolioStore`: on `--live` writes, write Sheets then SQLite (or both via dual).
3. CLI: `pm store verify` comparing key aggregates; `pm store status`.
4. Shadow writes only when live path would have written Sheets.

## Phase 2 — Read cutover for computed views

1. Config `STORE_READ_PRIMARY=sqlite|sheets` (default `sqlite` when DB has rows, else sheets fallback).
2. Tax / rotation / holdings readers used by vault sync and builders prefer store.
3. `pm export sheets` stub that re-exports from SQLite for cockpit continuity.

## Phase 3 — Local UI

1. FastAPI + Jinja/HTMX app under `ui/` serving Command Center KPIs, Decision/Crosshairs, Tax, Rotations from SQLite (fallback Sheets via store).
2. CLI: `pm ui serve [--port 8765]`.
3. Read-mostly; no new promotion semantics.

## Out of scope

- Migrating podcast corpora, bundles, or Review Log prose into SQL.
- FMP/ETF cache DB move (Phase 4 optional; skip unless trivial).
- Editing the plan file itself.

## Post-build checklist (literal stdout)

- [ ] `python -c "from core.store import get_store; print(get_store())"`
- [ ] `python manager.py store status`
- [ ] `python manager.py store verify` (dry compare; may warn if Sheets unreachable)
- [ ] Builders import `config.TAB_VALUATION_CARD` / `TAB_DECISION_VIEW`
- [ ] `python manager.py ui serve --help`
