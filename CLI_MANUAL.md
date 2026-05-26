# Investment Portfolio Manager: CLI Manual

## Overview
The Investment Portfolio Manager CLI is designed with a **Headless, Immutable, and Auditable** philosophy. It serves as the orchestration layer for a production-grade investment pipeline, moving data from the Schwab API to a structured Google Sheets dashboard. It delegates complex reasoning to external Frontier LLMs (like Gemini and Claude) by compiling system context into export packages rather than making live automated LLM calls against production tabs.

The application follows a "frozen state" pattern: every significant operation begins by capturing the current market and research state into an immutable **Context Bundle**. This ensures that downstream tools are always analyzing a consistent snapshot of data.

## Global Flags & Concepts

### The `pm` Command
The CLI is globally available as `pm` (after running `pip install -e .`). You should use `pm <command>` to run all operations.

### The `--live` Flag
By default, all commands run in **Dry-Run Mode**. This means the CLI will perform all calculations, fetch market data, and compile bundles, but it will **NOT** write results to Google Sheets. 
* To persist changes to your dashboard, you must explicitly include the `--live` flag.
* This safety mechanism allows you to verify data integrity before committing to the cloud.

### Context Bundles
Commands rely on bundles stored in the `bundles/` directory:
* **Market Bundle:** A snapshot of your holdings and prices.
* **Vault Bundle:** A snapshot of your local investment theses and research transcripts.
* **Composite Bundle:** A joined view of both, used to bridge qualitative and quantitative facts.

---

## Core Command Groups

### Unified Ingestion (`pm ingest`)
Bring external data into the system. All ingestion commands support the `--purge` flag for automatic session hygiene.
* `pm ingest transactions --live`: Sync Schwab transaction history (default: 90 days).
* `pm ingest realized-gl <CSV_PATH> --live`: Import realized G/L lots from Schwab CSV export.
* `pm ingest podcasts --live`: Fetch transcripts and update allocation signals.
* `pm ingest all --live`: Run the full ingestion suite (transactions + podcasts).

### Computed View Refresh (`pm refresh`)
Rebuild and format complex Google Sheet views from processed data.
* `pm refresh dashboard --live`: Rebuild Valuation Card, Decision View, Command Center, and UI formatting. Supports `--update` to fetch live prices.
* `pm refresh tax --live`: Update YTD tax posture and rebalance candidates based on Realized G/L.
* `pm refresh rotations --live`: Refresh P&L attribution for historical trades.

### Filesystem Hygiene (`pm clean`)
Manage the local disk footprint by purging obsolete artifacts based on shared retention windows.
* `pm clean exports`: Purge old LLM packages (>7 days).
* `pm clean podcasts`: Purge old transcript files (>30 days).
* `pm clean bundles`: Purge old JSON state snapshots (>30 days).
* `pm clean all --live`: Full system cleanup.

### Morning Routine (`pm morning`)
Run the full market-open pipeline.
* `pm morning --live`: Executes Health Check -> Schwab Sync -> Snapshot -> Dashboard Refresh sequentially. Includes options to `--skip-health`, `--skip-transactions`, or `--skip-tax`.

---

## Core Operations

### `pm snapshot`
Captures the current market state and positions into an immutable JSON bundle.

**Primary Purpose:** Freezes your portfolio data (tickers, quantities, prices) so it can be analyzed.

**Optional Flags:**
* `--source [auto|schwab|csv]`: Where to get data. `auto` (default) tries the API then falls back to CSV.
* `--csv PATH`: Path to a Schwab export file (required if source is `csv`).
* `--cash FLOAT`: Manual cash balance to include (default: `0.0`).
* `--enrich-atr`: Automatically computes 14-day ATR technical stops for the snapshot.
* `--live`: Appends the snapshot to the `Daily_Snapshots` and pushes current Holdings.

**Practical Examples:**
```bash
# Basic dry-run snapshot using Schwab API
pm snapshot

# Live snapshot from a CSV file with manual cash
pm snapshot --source csv --csv ./positions.csv --cash 5000 --live
```

---

### `pm journal promote`
Moves manual research and rotation entries from staging to the master log.

**Primary Purpose:** Commits "Approved" rows from `Trade_Log_Staging` into the permanent `Trade_Log`.

**Optional Flags:**
* `--yes`: Skips the manual confirmation prompt.
* `--live`: Moves the data to the master sheet and marks staging rows as "promoted".

**Practical Examples:**
```bash
# Preview which rows are ready to be promoted
pm journal promote

# Commit approved rotations to the master log
pm journal promote --live --yes
```

---

### `pm vault sync`
Syncs Sheets data into local thesis files.

**Primary Purpose:** Injects the latest quantitative facts (drift, valuation) into the structured markdown regions of your vault theses without altering the prose.

**Optional Flags:**
* `--ticker [TICKER]`: Update only a single ticker.
* `--live`: Persists the markdown file changes.
* `--force`: Forces recreation of regions if they are malformed.

**Practical Examples:**
```bash
pm vault sync --live
```

### `pm vault snapshot`
Freezes research documents for analysis.

**Primary Purpose:** Packages your local markdown theses and transcripts into a bundle.

**Optional Flags:**
* `--drive`: Pulls missing thesis files from Google Drive if not found locally.
* `--live`: Marks the vault snapshot as the authoritative research state.

**Practical Examples:**
```bash
pm vault snapshot --drive --live
```