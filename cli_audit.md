# CLI Audit — Investment Portfolio Manager

## Section A — Current Surface Map

| Command | Wraps (file::function) | Writes? | Notes |
| :--- | :--- | :--- | :--- |
| `health` | `tasks/health.py::run_all_checks` | No | Connectivity & integrity check. |
| `snapshot` | `core/bundle.py::build_bundle` | Yes (JSON) | Enriches & freezes market state to a bundle. |
| `morning` | Orchestrator in `manager.py` | Yes (Multi) | Health -> Sync -> Snapshot -> Dashboard. |
| `journal promote` | `manager.py::journal_promote` | Yes (Sheet) | Moves approved staging rows to Trade_Log. |
| `journal rotation` | `manager.py::journal_rotation` | Yes (Sheet) | Manual trade/rotation recording. |
| `trade review` | `tasks/compute_rotation_attribution.py` | Yes (Sheet) | Refresh Rotation_Review with P&L attribution. |
| `vault snapshot` | `core/vault_bundle.py::build_vault_bundle`| Yes (JSON) | Freezes vault documents to a bundle. |
| `vault sync` | `tasks/write_thesis_updates.py` | Yes (Disk) | Syncs Sheets data into thesis MD files. |
| `vault sync-status`| `manager.py::vault_sync_status` | No | Audits thesis staleness and style drift. |
| `vault add-thesis` | `manager.py::vault_add_thesis` | Yes (Disk) | Scaffolds a new ticker thesis file. |
| `vault thesis-audit`| `manager.py::vault_thesis_audit` | No | Reports trigger completeness across theses. |
| `bundle composite` | `core/composite_bundle.py` | Yes (JSON) | Links Market + Vault bundles. |
| `bundle push` | `pipeline.py::write_to_sheets` | Yes (Sheet) | Pushes position data from bundle to Sheets. |
| `bundle verify` | `manager.py::bundle_verify` | No | Verifies bundle hash integrity. |
| `sync transactions`| `tasks/sync_transactions.py` | Yes (Sheet) | Pulls Schwab transaction history. |
| `sync realized-gl` | `utils/gl_parser.py` | Yes (Sheet) | Imports Schwab Realized G/L CSV. |
| `tax refresh` | `tasks/build_tax_control.py` | Yes (Sheet) | Rebuilds Tax_Control tab. |
| `dashboard refresh`| `tasks/format_sheets_dashboard_v2.py`| Yes (Sheet) | Rebuilds Valuation/Decision/Tax tabs + Formatting. |
| `export list` | `manager.py::export_list` | No | Lists available LLM scenarios. |
| `export cleanup` | `manager.py::export_cleanup` | Yes (Disk) | Deletes old export packages. |
| `export inspect` | `manager.py::export_inspect` | No | Previews package manifest/prompt. |
| `export <scenario>`| `tasks/export_package.py` | Yes (Disk) | Scenario-specific LLM context packaging. |
| `podcast fetch` | `tasks/podcast_fetcher.py` | Yes (Disk) | Download a single YouTube transcript. |
| `podcast batch` | `tasks/batch_podcast_sync.py` | Yes (Disk/S)| RSS-driven batch transcript ingest + opt AI. |
| `podcast list` | `manager.py::podcast_list` | No | Lists channels and cached transcripts. |
| `podcast clean` | `manager.py::podcast_clean` | Yes (Disk) | Deletes old transcript files. |
| `podcast bundle` | `manager.py::podcast_bundle` | Yes (Disk) | Concatenates transcripts for LLM copy-paste. |

## Section B — Workflow Clusters

- **Daily Operating Loop:** `morning`, `health`, `snapshot`, `sync transactions`, `dashboard refresh`, `tax refresh`.
- **Tax Visibility:** `tax refresh`, `export tax-rebalance`.
- **LLM Handoff (Export):** All `export` commands, `bundle composite`, `podcast bundle`.
- **Trade Decision Capture:** `journal rotation`, `journal promote`, `sync transactions`.
- **Thesis Maintenance:** `vault sync`, `vault sync-status`, `vault add-thesis`, `vault thesis-audit`, `vault snapshot`.
- **Podcast Research Feed:** All `podcast` commands.
- **Hygiene & Cleanup:** `export cleanup`, `podcast clean`, `bundle verify`.
- **Diagnostics:** `health`, `vault sync-status`, `vault thesis-audit`, `export inspect`.

## Section C — Friction Inventory

- **Fragmented Ingestion:** To get "fully updated," one might run `sync transactions`, `sync realized-gl` (if they have a CSV), and `podcast batch`. `pm morning` covers the daily path, but there's no single "ingest everything" for the non-daily or manual-fallback paths.
- **Scattered Cleanup:** `export cleanup` and `podcast clean` are separate. There is no CLI command to clean up the `bundles/` directory (which can grow large with immutable market/vault/composite JSONs), forcing the user to use shell commands like `find`.
- **Overlapping "Refresh" Verbs:** `tax refresh`, `dashboard refresh`, and `trade review` (which is effectively a refresh of `Rotation_Review`) use different verbs for similar "rebuild-this-view" intents.
- **Redundant Status/Audit:** `health`, `vault sync-status`, and `vault thesis-audit` all provide different types of "is the system/data okay?" feedback.
- **Vault Command Depth:** The `vault` group is robust but has many commands that could be streamlined (e.g., `sync` vs `sync-status`).

## Section D — Verdict

| Workflow Cluster | Verdict | Reasoning |
| :--- | :--- | :--- |
| **Daily Loop** | **ALREADY GOOD** | `pm morning` correctly orchestrates the high-frequency tasks. |
| **Ingestion** | **CONSOLIDATE** | Merge `sync transactions`, `sync realized-gl`, and `podcast batch` into a unified `pm ingest`. |
| **Hygiene** | **CONSOLIDATE** | Create a unified `pm clean` to handle exports, podcasts, and bundles with target flags. |
| **Diagnostics** | **RENAME/CONSOLIDATE** | Promote `health` to `pm doctor` and include data integrity audits (theses, bundles). |
| **Vault/Thesis** | **RENAME** | `vault sync` and `vault sync-status` are the core of thesis maintenance. `vault add-thesis` is a scaffolding utility. |
| **Trade Capture**| **ALREADY GOOD** | `journal promote` and `journal rotation` are distinct manual actions. |
| **Exports** | **ALREADY GOOD** | The scenario-based structure is the primary value of the export engine. |
