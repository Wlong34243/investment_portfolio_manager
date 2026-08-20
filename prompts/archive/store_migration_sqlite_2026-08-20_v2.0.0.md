# Build Prompt: PortfolioStore — Corrected Plan (Tax Ledger First + Monitoring Publish)

**Author:** Cursor (course correction), 2026-08-20  
**Executor:** Cursor Agent  
**Prompt version:** 2.0.0  
**Supersedes:** `prompts/store_migration_sqlite_2026-08-20.md` v1.0.0  
**Fork decision:** **Monitoring** (multi-device). Phase 3 = Drive-published static HTML, not localhost FastAPI. Sheets stays phone-readable for Tax_Control / Command Center until that publish path is trusted.

## Why v2

v1 led with `positions_current` (a morning-rebuild cache), put thesis dual-truth in optional Phase 4, treated backup as a parenthetical, and made Phase 3 a localhost UI — an access downgrade vs Sheets on phone. v2 fixes all four.

## Step 0 — Verification (resolved 2026-08-20)

- [x] No pre-existing ORM before this work.
- [x] `Valuation_Card` / `Decision_View` **are** documented in current `CLAUDE.md` (morning pipeline / Crosshairs, verified notes 2026-08-10). The stale claim was `PORTFOLIO_SHEET_SCHEMA.md` incompleteness and an old "last verified 2026-08-01" header — not missing tabs. Inventory was correct; schema doc was lagging.
- [x] `config.TAB_VALUATION_CARD` / `TAB_DECISION_VIEW` added; builders use them.
- [x] Publish path already exists: `scripts/backup_to_drive.publish_analysis` → `G:\My Drive\Portfolio_Analysis` (phone-readable).

## Hard constraints

- CLI owns execution; brokerage read-only; `--live` gates writes.
- AI never writes Holdings / Trade_Log / Target_Allocation.
- Bundles + thesis prose stay files.
- **No Alembic in Phase 1** — DB fully rebuildable from Schwab+Sheets during dual-write; introduce Alembic only at Phase 2 cutover if needed.
- Phase 3 must preserve phone access (Drive sync), not replace it with localhost.

## Phase 0 — Contract freeze (done / keep)

Protocol + Sheets adapter + Tax_Control seam + tab roles. Unchanged intent.

## Phase 1 — Tax / lots / transactions vertical + backup (spine)

**Lead tables (not positions_current):**

1. `transactions` — shadow on `sync transactions --live`
2. `realized_gl` (lot-level) — shadow on `ingest realized-gl --live`
3. `tax_control` metrics + lots — already shadowed on `refresh tax --live`

`holdings_current` may exist as a convenience cache but is **not** Phase 1 acceptance.

**Backup (Phase 1 acceptance, not Phase 4):**

- `pm store backup --live`: `VACUUM INTO` dated file under `data/portfolio_store_backups/`
- SHA-256 sidecar
- Copy into Drive publish dest (`…/Portfolio_Analysis/db_backups/`) when mounted
- Dry-run by default

**Verify:** compare Sheets vs SQLite on txn count, realized_gl count, tax lot count / metrics keys — not position MV first.

## Phase 2 — Reads + thesis numeric dual-truth (not optional)

- Store-primary reads for tax/txn/realized when SQLite populated.
- Vault sync already routes through PortfolioStore — keep and harden: numeric regions (`position_state`, `transaction_log`, `realized_gl`, ceilings) sourced from store; prose untouched.
- Alembic optional only when rebuild is no longer free.

## Phase 3 — Monitoring publish (static HTML → Drive)

- Render Command Center / Decision / Tax / Rotations to **static HTML** under `agent_outputs/command_center/`.
- Publish via existing Drive mirror (`publish_analysis` glob or `pm publish cockpit`).
- Local `pm ui serve` remains optional debug only — not the product surface.
- Tax_Control and full Sheets Command Center stay in Sheets until static publish is trusted on phone.

## Explicit non-migrations

Same as v1: no thesis prose in SQL, no bundle rows, no Streamlit Cloud, no agent write-through.
