# Investment Portfolio Manager — Current State

**Last updated:** 2026-05-26
**Maintainer:** Bill (sole user)

This is the "where are we" document. Open this at the start of any coding session.

---

## What's Working Today

### Bundle infrastructure (May 2026 audit confirmed)
- `core/bundle.py` — market bundle assembly with SHA-256 canonical hashing
- `core/vault_bundle.py` — thesis files, transcripts, research; per-document hashing
- `core/composite_bundle.py` — thin wrapper linking market + vault + recent rotations from `Trade_Log`
- 62 thesis files parsed from `vault/theses/`
- `bundles/` directory holds serialized JSON bundles with hash-verified integrity
- Composite bundle includes Tier 2 data (`recent_rotations` from Google Sheets `Trade_Log`)

### Gemini integration
- `utils/gemini_client.py` — `ask_gemini()` with auto-prepended `SAFETY_PREAMBLE`
- `ask_gemini_composite()` — enforces `bundle_hash` in agent output schemas for end-to-end audit trail
- Dual-path auth: ADC primary, API key fallback
- Retry + backoff on `429 RESOURCE_EXHAUSTED`

### Data ingestion
- Schwab Developer API integration (read-only, primary path)
- CSV fallback retained for disaster recovery and realized G/L history
- yFinance enrichment (prices, sector, dividend yield, beta)
- FMP client (`fmp_client.py`) for fundamentals
- Podcast transcript ingestion via existing pipeline → writes to `vault/transcripts/`

### Agent layer
- **Idea Generator v1 (shipped May 26, 2026)**
  - `utils/agents/idea_generator.py` — Pydantic schemas + `run_idea_generator()` + `write_idea_report()`
  - `prompts/idea_generator.md` — system prompt for Gemini
  - CLI: `python manager.py agent ideas [--since-days 7] [--bundle-path PATH] [--dry-run]`
  - Output: markdown reports in `agent_outputs/ideas/`, named `ideas_{YYYY-MM-DD}_{hash_prefix}.md`
  - First real run (2026-05-26): 3 transcripts → 7 candidates with style classification, portfolio overlap detection, and substantive concerns. Hard rule compliance verified (no price targets, no buy/sell language).

### Google Sheets persistence
- Sheet ID: `1DuY68xVvyHq-0dyb7XUQgcoK7fqcVS0fv7UoGdTnfxA`
- Authoritative tabs: `Holdings_Current`, `Holdings_History`, `Daily_Snapshots`, `Transactions`, `Target_Allocation` (manual only), `Config`
- Computed views: `Risk_Metrics`, `Income_Tracking`, `RealizedGL`
- Sandbox layers: `AI_Suggested_Allocation`, `Agent_Outputs`, `Agent_Outputs_Archive`
- Provenance: `Logs`

### Automation
- GitHub Actions: podcast pipeline Friday 5pm EST cron + `workflow_dispatch`
- GCP Cloud Scheduler + Cloud Function: Schwab token refresh every 25 min during market hours
- GCP project: `re-property-manager-487122` (shared with RE Property Manager)

---

## What's Next

### Immediate priority: Valuation Drift Monitor
Sell-side signal generation. Tracks changes in fundamentals (forward P/E, PEG, three-statement quality, dividend coverage) across current holdings vs original thesis baseline. Likely requires adding FMP fundamentals to the market bundle.

Acceptance criteria for v1:
- Reads current holdings from bundle
- For each position, fetches current fundamentals via FMP
- Compares to a baseline (thesis file entry valuation if available, or rolling 12-month average if not)
- Flags positions where valuation has materially drifted (definition TBD after v1 output)
- Writes markdown report to `agent_outputs/drift/`
- No automatic sell signals; surfaces "worth re-examining" only

Not started yet. Following same fire-fire-aim pattern as Idea Generator: ship minimum viable version, iterate based on real output.

### Watchlist items (deferred, not blocking)
- Tax-control layer surfacing YTD realized G/L, wash-sale visibility, estimated-tax planning numbers from `RealizedGL` + `Config` — wait until drift monitor produces real sell candidates that touch tax considerations
- Google Sheets landing path for agent outputs — currently local markdown only; promote once output format stabilizes
- Looker Studio dashboard — only if a specific visibility gap emerges
- Options chain scanner for covered call / cash-secured put yield strategy (Phase 6+)
- Schwab API `fetch_positions()` multi-account aggregation bug fix — workaround in place via account filtering

---

## What's Explicitly Dropped

### Deprecated agent kit (May 2026 reframe)
- ~~Re-buy Analyst~~ — User already re-bought broad ETFs after 30% run-up; this agent solved a problem that no longer exists
- ~~Add-Candidate Analyst~~ — Idea Generator covers candidate sourcing more broadly
- ~~New Idea Screener~~ — Idea Generator absorbs this function
- ~~List Coherence Checker~~ — User judgment + Sheets visibility is sufficient for now
- ~~Nine-file agent kit nomenclature~~ — Replaced with research-and-monitoring framing

### Architectural decisions
- Streamlit Cloud deployment — local execution is the default
- Gemma and MCP integrations — wrong fit for server-side, low-volume work
- Financial Datasets MCP — duplicates FMP coverage
- Auto-trading of any kind — read-only is a hard rule, forever

---

## Operating Principles (Unchanged)

- **LLMs synthesize, APIs calculate.** Python gathers data deterministically; agents reason over immutable bundles.
- **Agents never browse or fetch.** All external data goes through Python first.
- **DRY_RUN defaults true.** Every write path requires explicit `--live` flag.
- **All AI output is sandboxed.** Writes go to `Agent_Outputs` or local markdown; `Target_Allocation` is manual-only.
- **Single-batch gspread writes with fingerprint dedup.** Never cell-by-cell.
- **Fire-fire-aim development.** Ship minimum viable agents, learn from real output, iterate. The bundle layer keeps the discipline; agents on top are cheap to try and throw away.
- **No price targets, no market predictions, no buy/sell recommendations** in any agent output.

---

## Quick Reference

| | |
|---|---|
| **Portfolio size** | ~$550K across 50+ positions + strategic cash |
| **Primary data path** | Schwab API (read-only) |
| **Fallback data path** | Schwab CSV |
| **Execution model** | Local CLI (`python manager.py`) |
| **Authoritative frontend** | Google Sheets |
| **Sheet ID** | `1DuY68xVvyHq-0dyb7XUQgcoK7fqcVS0fv7UoGdTnfxA` |
| **GCP Project** | `re-property-manager-487122` |
| **Gemini model** | `gemini-3.0-flash` via Vertex AI |
| **Repo** | `Wlong34243/investment-portfolio-manager` |
| **Reserve account** | Schwab `...8895` — tracked separately in RE Property Manager |

---

## How to Resume Work

1. Read this file first
2. Read `BUNDLE_AND_AGENT_AUDIT.md` for infrastructure ground truth
3. Read `CLAUDE.md` for project conventions
4. Most recent agent output is in `agent_outputs/ideas/` — open the latest markdown file to see what the system produced
5. To run the idea generator manually: `python manager.py agent ideas`
6. To inspect a bundle: `python manager.py bundle inspect <path>`

---

## Recent Decisions Log

- **2026-05-26** — Reframed agent kit. Dropped Re-buy/Add-Candidate/Screener/Coherence agents. New direction is Idea Generator (shipped) + Valuation Drift Monitor (next).
- **2026-05-26** — Shipped Idea Generator v1. First real run produced 7 candidates from 3 podcast transcripts with reliable style classification and overlap detection.
- **2026-05-26** — Bundle infrastructure audited and confirmed working. No hardening pass needed before agent layer.
- **April 2026** — Architectural pivot away from Streamlit-first to CLI + Sheets spine.
