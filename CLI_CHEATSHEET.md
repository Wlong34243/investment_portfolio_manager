# ⚡ Portfolio Manager CLI: Quick Reference

### ☀️ Daily Workflows
| Command Context | Exact Command | What it Does |
| :--- | :--- | :--- |
| **Full Update** | `python manager.py snapshot --live` | Syncs Schwab, updates Holdings & Daily Snapshot |
| **Agent Run** | `python manager.py analyze-all --live` | Runs 7 agents and writes to Agent_Outputs |
| **UI Refresh** | `python manager.py dashboard refresh --live` | Updates Decision View and re-applies formatting |
| **Transactions** | `python manager.py sync transactions --live` | Fetches last 90 days of trades from Schwab |

### 🤖 Agent Operations
| Command Context | Exact Command | What it Does |
| :--- | :--- | :--- |
| **Specific Agent** | `python manager.py agent [name] analyze --live` | Runs one agent (e.g. `valuation`, `tax`, `macro`) |
| **Custom Tickers** | `python manager.py agent valuation analyze --ticker AAPL --live` | Analyzes specific symbols only |
| **Behavioral** | `python manager.py agent behavioral analyze --trade-days 60` | Audits recent trades against logic |
| **New Idea** | `python manager.py agent new-idea analyze --ticker TSLA` | Screens a potential new buy candidate |

### 🔧 Maintenance & Formatting
| Command Context | Exact Command | What it Does |
| :--- | :--- | :--- |
| **Promote Log** | `python manager.py journal promote --live` | Moves "Approved" staging trades to Master Log |
| **Record Trade** | `python manager.py journal rotation --sold [T] --bought [T] --proceeds [N] --live` | Manually records a portfolio rotation |
| **Vault Sync** | `python manager.py vault snapshot --drive --live` | Syncs research theses from Local/Drive |
| **New Thesis** | `python manager.py vault add-thesis --ticker [T]` | Generates a blank thesis template for a ticker |
| **Verify Integrity** | `python manager.py bundle verify [PATH]` | Checks the SHA256 hash of any context bundle |

### 💡 Pro-Tips
* **Help:** Append `--help` to any command for full flag details: `python manager.py snapshot --help`
* **Safety:** Every command defaults to **Dry-Run**. If you don't see `SUCCESS` or a Sheet update, you likely forgot `--live`.
* **Bundles:** The `bundles/` folder is your source of truth. If data feels "stale," run `snapshot` first.
