# Investment Portfolio Manager: CLI Manual

## Overview
The Investment Portfolio Manager CLI is designed with a **Headless, Immutable, and Auditable** philosophy. It serves as the orchestration layer for a production-grade investment pipeline, moving data from the Schwab API through a series of "Intelligence Agents" (Gemini 2.5 Pro) and finally into a structured Google Sheets dashboard.

The application follows a "frozen state" pattern: every significant operation begins by capturing the current market and research state into an immutable **Context Bundle**. This ensures that downstream agents are always analyzing a consistent snapshot of data, preventing "drift" during long-running analysis sessions.

## Global Flags & Concepts

### The `--live` Flag
By default, all commands run in **Dry-Run Mode**. This means the CLI will perform all calculations, fetch market data, and even query AI agents, but it will **NOT** write results to Google Sheets. 
* To persist changes to your dashboard, you must explicitly include the `--live` flag.
* This safety mechanism allows you to verify data integrity and costs before committing to the cloud.

### Context Bundles
Most commands rely on bundles stored in the `bundles/` directory. 
* **Market Bundle:** A snapshot of your holdings and prices.
* **Vault Bundle:** A snapshot of your local investment theses and research transcripts.
* **Composite Bundle:** A joined view of both, required for full agent analysis.

---

## Core Commands

### `snapshot`
Captures the current market state and positions into an immutable JSON bundle.

**Primary Purpose:** Freezes your portfolio data (tickers, quantities, prices) so it can be analyzed.

**Optional Flags:**
* `--source [auto|schwab|csv]`: Where to get data. `auto` (default) tries the API then falls back to CSV.
* `--csv PATH`: Path to a Schwab export file (required if source is `csv`).
* `--cash FLOAT`: Manual cash balance to include (default: `0.0`).
* `--enrich-atr`: If set, automatically computes 14-day ATR technical stops for the snapshot.
* `--live`: Appends the snapshot to the `Daily_Snapshots` sheet.

**Behind the Scenes:** Generates a file in `bundles/`. If `--live` is used, it also updates `Daily_Snapshots`, `Holdings_Current`, and `Holdings_History`.

**Practical Examples:**
```bash
# Basic dry-run snapshot using Schwab API
python manager.py snapshot

# Live snapshot from a CSV file with manual cash
python manager.py snapshot --source csv --csv ./positions.csv --cash 5000 --live
```

---

### `analyze-all`
Runs the full suite of portfolio intelligence agents.

**Primary Purpose:** Executes the "Tactical Squad" of AI agents to generate signals (Accumulate, Trim, Hold).

**Optional Flags:**
* `--fresh-bundle`: Forces the regeneration of market, vault, and composite bundles before running.
* `--agents LIST`: Comma-separated list of agents to run (e.g., `valuation,tax`). Defaults to all 7.
* `--live`: Writes the batch of agent outputs to the `Agent_Outputs` sheet.

**Behind the Scenes:** Queries Gemini 2.5 Pro for every position. Writes a run manifest to `bundles/runs/`.

**Practical Examples:**
```bash
# Run all agents in dry-run mode
python manager.py analyze-all

# Run only Valuation and Tax agents and write to the dashboard
python manager.py analyze-all --agents valuation,tax --live
```

---

### `dashboard refresh`
Maintains the health and visual integrity of the Google Sheets dashboard.

**Primary Purpose:** Rebuilds the high-level views (Valuation Card, Decision View) and re-applies professional formatting.

**Optional Flags:**
* `--update`: If set, syncs latest positions from Schwab before rebuilding.
* `--tx-days INT`: Number of days of transaction history to fetch if `--update` is used (default: `90`).
* `--live`: Required to actually apply the updates and formatting to the sheet.

**Behind the Scenes:** Modifies `Valuation_Card`, `Decision_View`, and applies Navy/White formatting to all tabs.

**Practical Examples:**
```bash
# Re-apply formatting and update action views
python manager.py dashboard refresh --live

# Complete end-to-end refresh: sync Schwab -> build views -> format
python manager.py dashboard refresh --update --live
```

---

### `journal promote`
Moves manual research and rotation entries from staging to the master log.

**Primary Purpose:** Commits "Approved" rows from `Trade_Log_Staging` into the permanent `Trade_Log`.

**Optional Flags:**
* `--yes`: Skips the manual confirmation prompt.
* `--live`: Moves the data to the master sheet and marks staging rows as "promoted".

**Behind the Scenes:** Reads from `Trade_Log_Staging` and writes to `Trade_Log`.

**Practical Examples:**
```bash
# Preview which rows are ready to be promoted
python manager.py journal promote

# Commit approved rotations to the master log
python manager.py journal promote --live --yes
```

---

### `vault snapshot`
Freezes research documents for AI analysis.

**Primary Purpose:** Packages your local markdown theses and transcripts into a bundle the agents can read.

**Optional Flags:**
* `--drive`: Pulls missing thesis files from Google Drive if not found locally.
* `--live`: Marks the vault snapshot as the authoritative research state.

**Behind the Scenes:** Scans the `vault/` directory and generates a `vault_bundle_*.json`.

**Practical Examples:**
```bash
python manager.py vault snapshot
python manager.py vault snapshot --drive --live
```

---

### `sync transactions`
Fetches trade history directly from the brokerage.

**Primary Purpose:** Updates your transaction history to track sells, buys, and dividends.

**Optional Flags:**
* `--days INT`: How many days back to look (default: `90`).
* `--live`: Writes the transactions to the `Transactions` sheet.

**Behind the Scenes:** Queries the Schwab /transactions endpoint.

**Practical Examples:**
```bash
# Backfill a full year of transactions
python manager.py sync transactions --days 365 --live
```
