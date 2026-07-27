# Investment Portfolio Manager — Current State

**Last updated:** 2026-07-26
**Maintainer:** Bill (sole user)

This is the "where are we" document. Open this at the start of any coding session.

---

## What's Working Today

### Bundle infrastructure (May 2026 audit confirmed)
- `core/bundle.py` — market bundle assembly with SHA-256 canonical hashing
- `core/vault_bundle.py` — thesis files, transcripts, research; per-document hashing
- `core/composite_bundle.py` — thin wrapper linking market + vault + recent rotations from `Trade_Log`
- 41 thesis files parsed from `vault/theses/`
- `bundles/` directory holds serialized JSON bundles with hash-verified integrity
- Composite bundle includes Tier 2 data (`recent_rotations` from Google Sheets `Trade_Log`)

### Gemini integration
- `utils/gemini_client.py` — `ask_gemini()` with auto-prepended `SAFETY_PREAMBLE`
- `ask_gemini_composite()` — enforces `bundle_hash` in agent output schemas for end-to-end audit trail
- Dual-path auth: API key primary (GEMINI_API_KEY env), ADC/Vertex AI fallback
- Retry + backoff on `429 RESOURCE_EXHAUSTED`

### Data ingestion
- Schwab Developer API integration (read-only, primary path)
- CSV fallback retained for disaster recovery and realized G/L history
- yFinance enrichment (prices, sector, dividend yield, beta)
- FMP client (`fmp_client.py`) for fundamentals
- Podcast transcript ingestion via existing pipeline → writes to `data/podcast_transcripts/`

### Agent layer
- **Idea Generator v1 (shipped May 26, 2026; updated June 15, 2026)**
  - `utils/agents/idea_generator.py` — Pydantic schemas + `run_idea_generator()` + `write_idea_report()`
  - `prompts/idea_generator.md` — system prompt for Gemini
  - CLI: `python manager.py agent ideas [--since-days 7] [--bundle-path PATH] [--dry-run] [--skip-ingest]`
  - **Auto-ingests podcasts before analyzing** — `pm agent ideas` now runs `pm ingest podcasts --live` as Step 1, then generates the report. No need to run ingestion separately. Use `--skip-ingest` to go straight to the generator.
  - Output: markdown reports in `agent_outputs/ideas/`, named `ideas_{YYYY-MM-DD}_{hash_prefix}.md`

### Google Sheets persistence
- Sheet ID: `1DuY68xVvyHq-0dyb7XUQgcoK7fqcVS0fv7UoGdTnfxA`
- Authoritative tabs: `Holdings_Current`, `Holdings_History`, `Daily_Snapshots`, `Transactions`, `Target_Allocation` (manual only), `Config`
- Computed views: `Risk_Metrics`, `Income_Tracking`, `RealizedGL`
- Sandbox layers: `AI_Suggested_Allocation`, `Agent_Outputs`, `Agent_Outputs_Archive`
- Provenance: `Logs`

### AI briefing export (`tasks/export_ai_briefing.py`)
- Assembles `prompt.md` + `portfolio.md` + `podcasts.md` + `theses.md` into a dated `exports/` package plus a concatenated `SUBMIT_ME.md` for pasting into a frontier LLM
- `build_podcasts_md()` reads `data/podcast_summaries/*.md`, selects by filename date within the `--days` window, and filters via `podcast_signal()` — summaries whose Sector Allocations table is a single catch-all `Broad Market` row, or tagged `No actionable thesis`, are withheld and listed
- **Ground Rules v2 added 2026-07-26** — governing principle plus 8 hard rules, each traceable to a specific failure in the 2026-07-26 briefing. See CHANGELOG. Key standing constraints: never infer liquidity posture from this export (`CASH_MANUAL` does **not** represent the cash position); ballast/core holdings are exempt from ceiling flags; scan ±3 days for an offsetting leg before calling anything drift
- **Manual (non-YouTube) source ingestion is currently hand-work**: finished summaries can be dropped straight into `data/podcast_summaries/` — this path is fully downstream of the YouTube fetcher and requires no video ID. Mark such files with a `PROVENANCE:` footer so they are not mistaken for transcript-derived summaries

### Automation
- GitHub Actions: podcast pipeline Friday 5pm EST cron + `workflow_dispatch` — **currently non-functional**: YouTube blocks transcript requests from Azure cloud runner IPs. The workflow reports green but processes 0 episodes. Last successful automated run: June 2, 2026.
- **Podcast ingestion workaround**: run `pm agent ideas` (or `pm ingest podcasts --live`) locally. Local machine IPs are not blocked by YouTube.
- GCP Cloud Scheduler + Cloud Function: Schwab token refresh every 25 min during market hours
- GCP project: `re-property-manager-487122` (shared with RE Property Manager)

---

## What's Next

### Do this first: apply the thesis sync fix
`core/thesis_sync_data.py` was fixed 2026-07-26 but **the thesis files still contain the bad values** — they are only rewritten on next sync.

```
python manager.py vault sync                 # DRY RUN - inspect the diff
python manager.py vault sync --live          # promote
```

Expect all 35 synced files to show a changed `current_allocation` and `**Drift:**`, and JEPI / QQQM / MELI to flip to positive drift. Until this runs, every drift figure in the vault is wrong and no ceiling breach is visible. See `THESIS_SYNC_FIX_2026-07-26.md`.

### Then: reconcile `Trade_Log`
Zero rotations logged in 97 days while at least two occurred. Run `derive_rotations`, review `Trade_Log_Staging`, promote:
- **2026-07-20** EMXC −100 sh (≈$9,250) → BBJP +125 sh (≈$9,181). Substitution thesis: reduce single-strait Taiwan/foundry concentration, redeploy into Japanese governance reform.
- **2026-06-25** NOW + IGV proceeds (≈$15.1K) → APO / KRE / MELI / LLY (≈$15.5K). *Inferred from top-5 per-position logs only — confirm before promoting.*

Six orphaned thesis files also need archiving or exit confirmation: AMD, CRWV, DELL, LRCX, MSFT, SPCX. MSFT/HWM/IREN/CFG were April 2026 rotation buys that no longer appear in holdings with no logged exit.

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
- **Split the `ETF` style in `styles.json`** into `BALLAST_CORE` (JEPI, JPIE, VTI, COWZ, VEA — high or no ceiling) and `SECTOR_ETF` (XBI, IGV, KRE, XLF, IFRA, EWZ, EMXC, BBJP, GLD — 8%). Until then, ceiling flags on ballast are noise and crowd out the one that survives recalibration (MELI, 0.06% over). The briefing prompt suppresses these flags as a stopgap; the taxonomy is the real fix.
- **Manual source-ingest CLI command** — a `pm vault add-summary` style path that runs the same Gemini summarization on a pasted transcript or third-party digest, writes to `data/podcast_summaries/` with a non-YouTube provenance stamp. Reuses existing code, no new vendor. Currently hand-work; deferred by decision 2026-07-26.
- **`manager.py:850` weight heuristic** — `max <= 1.5 → *100` is unsafe for a book whose largest position is under 1.5% and percent-stored. Harmless at current concentration (max 9.92%). Durable fix is producer-side: write percentages, drop both workarounds.
- **`ET_thesis.md` Lake Charles status** — thesis says "export terminal networks"; reporting conflicts on whether ET suspended the project to redirect capital to pipelines serving data campuses. Verify against primary filings.
- Tax-control layer surfacing YTD realized G/L, wash-sale visibility, estimated-tax planning numbers from `RealizedGL` + `Config` — wait until drift monitor produces real sell candidates that touch tax considerations. *Note: three wash-sale windows are already live and unpriced — EMXC (5 sh of the 7/20 loss disallowed by the 7/15 buy), GLD (6/25 buy vs 7/21 loss sale), XLF (6/30 sale vs 7/17 rebuy 5% higher).*
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
| **Portfolio size** | $589,395.86 across 36 positions (bundle `75caa01bedab`, 2026-07-26) |
| **Cash** | **Not captured in this export.** `CASH_MANUAL` ($1,755.56 / 0.30%) does not represent the cash position — cash is held outside what the bundle sees. Draw no liquidity conclusions from bundle data. |
| **Primary data path** | Schwab API (read-only) |
| **Fallback data path** | Schwab CSV |
| **Execution model** | Local CLI (`python manager.py`) |
| **Authoritative frontend** | Google Sheets |
| **Sheet ID** | `1DuY68xVvyHq-0dyb7XUQgcoK7fqcVS0fv7UoGdTnfxA` |
| **GCP Project** | `re-property-manager-487122` |
| **Gemini model** | `gemini-2.5-pro` (API key primary; ADC/Vertex AI fallback on `re-property-manager-487122`) |
| **Repo** | `Wlong34243/investment-portfolio-manager` |
| **Reserve account** | Schwab `...8895` — tracked separately in RE Property Manager |

---

## How to Resume Work

1. Read this file first
2. Read `CLAUDE.md` for project conventions
3. Most recent agent output is in `agent_outputs/ideas/` — open the latest markdown file to see what the system produced
4. To run the idea generator manually: `python manager.py agent ideas`
5. To verify a bundle: `python manager.py bundle verify <path>`

---

## Recent Decisions Log

- **2026-07-26** — Ingested the Spotify weekly podcast aggregate as a single first-class source in its own voice, rather than decomposing it into constituent episode files. Rationale: decomposition made one digest appear as three agreeing sources in theme extraction, and discarded the aggregate's own synthesis. Manual-ingest CLI command deferred; hand-drop into `data/podcast_summaries/` for now.
- **2026-07-26** — Established the standing principle that **the vault and `Trade_Log` lag Bill's decisions and are not evidence against them**. Encoded as Ground Rules v2 in the briefing prompt. Three of the sharpest findings in the 2026-07-26 briefing (cash posture, EMXC "drift", NOW "data artifact") dissolved on contact with actual intent; all three were documentation gaps reported as behavioral incoherence.
- **2026-07-26** — Fixed the thesis sync allocation bug that hid all ceiling breaches. Chose deterministic recomputation from market value over replicating `manager.py`'s `max <= 1.5` heuristic, which is itself unsafe for a sufficiently diversified book.
- **2026-07-26** — NOW conviction break formalized (seat-priced workflow vendors through the AI transition); EMXC reduced on Taiwan concentration. Both thesis files rewritten to match decisions already executed.
- **2026-05-26** — Reframed agent kit. Dropped Re-buy/Add-Candidate/Screener/Coherence agents. New direction is Idea Generator (shipped) + Valuation Drift Monitor (next).
- **2026-05-26** — Shipped Idea Generator v1. First real run produced 7 candidates from 3 podcast transcripts with reliable style classification and overlap detection.
- **2026-05-26** — Bundle infrastructure audited and confirmed working. No hardening pass needed before agent layer.
- **April 2026** — Architectural pivot away from Streamlit-first to CLI + Sheets spine.
