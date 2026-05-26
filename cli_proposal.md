# CLI Proposal — Investment Portfolio Manager

This proposal outlines the simplified CLI surface for version 3.2, focusing on ergonomic workflows for a semi-retired auditor.

## 1. Unified Ingestion: `pm ingest`

Combines all data pull operations into a single verb.

**Before → After:**
- `pm sync transactions` → `pm ingest transactions`
- `pm sync realized-gl --csv <path>` → `pm ingest realized-gl --csv <path>`
- `pm podcast batch` → `pm ingest podcasts`
- (New) `pm ingest --all` → Runs all of the above.

**Friction Solved:** Collapses 3 distinct "sync/batch" commands across 2 Typer groups into 1.
**Win Statement:** "Single entry point for bringing any external data into the system."

**Flags:**
- `--all`: Ingest transactions, realized-gl (if possible), and podcasts.
- `--csv <path>`: Required for `realized-gl`.
- `--purge`: Convenience flag. After successful ingestion, deletes obsolete data (old transcripts past 30-day window, stale bundles older than 30 days, old exports older than 7 days).

---

## 2. Unified Hygiene: `pm clean`

Standalone filesystem hygiene command.

**Before → After:**
- `pm export cleanup --days N` → `pm clean exports --days N`
- `pm podcast clean --days N` → `pm clean podcasts --days N`
- (New) `pm clean bundles --days N` → Cleans `bundles/` directory.
- (New) `pm clean all` → Cleans everything.

**Friction Solved:** Moves cleanup out of functional groups (`export`, `podcast`) into a dedicated hygiene group. Adds missing bundle cleanup.
**Win Statement:** "Centralized control for managing the system's disk footprint."

**Boundary with `pm ingest --purge`:** `pm clean` is for intentional manual maintenance. `pm ingest --purge` is a convenience for the "start of session" ingestion loop.

---

## 3. Refresh-Verb Consolidation: `pm refresh`

Unified command for rebuilding computed Sheet views.

**Before → After:**
- `pm dashboard refresh` → `pm refresh dashboard`
- `pm tax refresh` → `pm refresh tax`
- `pm trade review` → `pm refresh trade` (or `attribution`)

**Friction Solved:** Standardizes the verb for "recompute this tab and write it."
**Win Statement:** "Replaces three different verbs across three groups with a single, predictable command."
**Verdict:** Consolidation approved. An auditor thinking about "reports" would naturally look for a `refresh` or `report` command. `refresh` is already established.

---

## 4. The `vault` → `data` Rename

Removing "Vault" framing in favor of "Data" to align with user preference.

**Full Blast Radius / Touchpoints:**
- **Filesystem:**
    - `vault/` → Contents moved into `data/`.
    - `data/theses/`, `data/research/`, `data/frameworks/`, `data/transcripts/` (curated).
    - `core/vault_bundle.py` → `core/data_bundle.py`.
- **Code (Constants in `config.py`):**
    - `VAULT_DIR` → `DATA_ROOT_DIR`
    - `THESES_DIR`, `RESEARCH_DIR`, `FRAMEWORKS_DIR`.
- **Code (Typer):**
    - `vault_app` → `data_app`.
    - `pm vault` → `pm data`.
- **Code (Models):**
    - `VaultBundle` → `DataBundle`.
    - `VaultDocument` → `DataDocument`.
- **JSON / Bundles:**
    - `vault_hash` → `data_hash`.
    - `vault_bundle_path` → `data_bundle_path`.
- **Documentation:**
    - `CLAUDE.md`, `PORTFOLIO_SHEET_SCHEMA.md`, `portfolio_manager_user_docs.html`.
- **Backward Compat:**
    - `pm vault` becomes a hidden alias for `pm data`.
    - `config.VAULT_DIR` preserved as a deprecated alias pointing to `data/`.

**Win Statement:** "Aligns system terminology with user mental model; simplifies filesystem structure to a single data root."

---

## Migration Table

| Existing Command | New Command | Note |
| :--- | :--- | :--- |
| `pm sync transactions` | `pm ingest transactions` | Deprecated alias preserved. |
| `pm sync realized-gl` | `pm ingest realized-gl` | |
| `pm podcast batch` | `pm ingest podcasts` | |
| `pm export cleanup` | `pm clean exports` | |
| `pm podcast clean` | `pm clean podcasts` | |
| `pm dashboard refresh` | `pm refresh dashboard` | |
| `pm tax refresh` | `pm refresh tax` | |
| `pm trade review` | `pm refresh trade` | |
| `pm vault <cmd>` | `pm data <cmd>` | `vault` becomes a hidden alias. |
| `pm health` | `pm health` | **UNCHANGED** (per user instruction). |
| `pm morning` | `pm morning` | **UNCHANGED**. |
| `pm snapshot` | `pm snapshot` | **UNCHANGED**. |

---

## Rejection List

1. **`health` → `pm doctor`**: Rejected. `health` is self-evident and well-integrated into `pm morning`.
2. **Expanding `health`**: Rejected. Overlap with `data sync-status` is acceptable for context-specific use.
3. **Consolidating `snapshot` into `ingest`**: Rejected. `snapshot` is a core "freeze state" operation that often runs without new external data (e.g., to re-enrich technicals).

---

## Estimated Effort

1. **`pm ingest`**: `S` (Pure orchestration over existing functions).
2. **`pm clean`**: `S` (Simple file deletion logic).
3. **`pm refresh`**: `S` (Typer aliasing/moving).
4. **`vault` → `data` rename**: `L` (High blast radius, touches multiple files and bundle schemas). **Recommended to be done as the final step.**

**Next Steps:**
Wait for "approve <command_name>" to proceed to Phase 2 (Patch Generation).
