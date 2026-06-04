# ⚡ Portfolio Manager CLI: Quick Reference

### 🚀 Windows Automation (Recommended for Periodic Use)
Double-click these batch files in the root folder to automate common workflows:
* **`run_morning_sync.bat`**: Runs the entire end-to-end morning sync pipeline (health, transaction sync, live update, snapshot, podcast sync, dashboard refresh, local thesis sync, and composite bundle building) in `--live` mode.
* **`run_idea_generator.bat`**: Runs the Idea Generator agent and opens the resulting markdown report automatically.
* **`schwab_emergency_reauth.bat`**: Runs the emergency Schwab reauthentication login flow.

### ☀️ Daily/Weekly CLI Workflows
| Command Context | Exact Command | What it Does |
| :--- | :--- | :--- |
| **Morning Routine** | `pm morning --live` | Runs the full daily loop (health -> ingest -> snapshot -> refresh -> vault sync -> composite) |
| **Schwab Auth** | `pm login` | Runs the Schwab OAuth login flow to update expired credentials |
| **Backup Project** | `pm backup` | Archives the project and uploads a timestamped zip file to Google Drive |
| **Full Update** | `pm snapshot --live` | Syncs Schwab, updates Holdings & Daily Snapshot |
| **UI Refresh** | `pm refresh dashboard --live` | Updates Decision View and re-applies formatting |
| **Transactions** | `pm ingest transactions --live` | Fetches last 90 days of trades from Schwab |

### 🧠 Data Pipeline & Export Engine
| Command Context | Exact Command | What it Does |
| :--- | :--- | :--- |
| **List Scenarios** | `pm export list` | Lists available context scenarios for AI analysis |
| **Inspect Export** | `pm export inspect [PATH]` | Inspects an existing export package |
| **Realized G/L** | `pm ingest realized-gl [CSV_PATH] --live` | Imports realized G/L lots for tax visibility |
| **Podcast Data** | `pm ingest podcasts --live` | Fetches and processes podcast transcripts |

### 🔧 Maintenance & Hygiene
| Command Context | Exact Command | What it Does |
| :--- | :--- | :--- |
| **Promote Log** | `pm journal promote --live` | Moves "Approved" staging trades to Master Log |
| **Record Trade** | `pm journal rotation --sold [T] --bought [T] --proceeds [N] ... --live` | Manually records a portfolio rotation |
| **Vault Sync** | `pm vault sync --live` | Syncs Sheets data into local thesis files via managed regions |
| **Vault Audit** | `pm vault sync-status` | Audits the staleness and drift of all thesis files |
| **New Thesis** | `pm vault add-thesis [TICKER]` | Generates a blank thesis template for a ticker |
| **Cleanup All** | `pm clean all --live` | Purges old exports, podcasts, and bundles |
| **Verify Integrity** | `pm bundle verify [PATH]` | Checks the SHA256 hash of any context bundle |

### 💡 Pro-Tips
* **Help:** Append `--help` to any command for full flag details: `pm snapshot --help` or `pm morning --help`
* **Safety:** Every command defaults to **Dry-Run**. If you don't see `SUCCESS` or a Sheet update, you likely forgot `--live`.
* **Bundles:** The `bundles/` folder is your source of truth. If data feels "stale," run `run_morning_sync.bat` first.