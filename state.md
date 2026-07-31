# Investment Portfolio Manager — Current State

**Last updated:** 2026-07-31
**Maintainer:** Bill (sole user)

This is the "where are we" document. Open this at the start of any coding session.

---

## What's Working Today

### Bundle infrastructure (May 2026 audit confirmed)
- `core/bundle.py` — market bundle assembly with SHA-256 canonical hashing
- `core/vault_bundle.py` — thesis files, transcripts, research; per-document hashing
- `core/composite_bundle.py` — thin wrapper linking market + vault + recent rotations from `Trade_Log`
- 35 thesis files parsed from `vault/theses/` (38 archived in `vault/theses/archive/`, including 6 orphans archived 2026-07-29: AMD, CRWV, DELL, LRCX, MSFT, SPCX; IGV and VEU archived since as further orphans). New positions pending reconciliation: `IBM_thesis.md` (2026-07-27) and `SKHY_thesis.md` (2026-07-29) — see What's Next.
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
- **`manager.py morning` now produces this export automatically (STEP 9, committed 2026-07-27 in `7882b1c`)** — `run_morning_sync.bat` alone is sufficient; `make_ai_briefing.bat` remains for an export without a full sync. `--skip-export` opts out of a given morning run.
- **Manual (non-YouTube) source ingestion is currently hand-work**: finished summaries can be dropped straight into `data/podcast_summaries/` — this path is fully downstream of the YouTube fetcher and requires no video ID. Mark such files with a `PROVENANCE:` footer so they are not mistaken for transcript-derived summaries
- **Briefing integrity hardening (2026-07-29)** — full P0/P1/P2 pass. See CHANGELOG `[2026-07-29] — Briefing integrity hardening` for the complete list; headline changes:
  - `theses.md` ships full Key Risks/Exit Conditions/Scaling State/Rotation Priority/Review Log per position by default (`--thesis-detail standard`), not just the Core Thesis first paragraph, with a disclosure line naming what's included/omitted
  - Scaling State / Rotation Priority parsing now handles prose and bulleted/bold labels instead of silently misreporting a present section as missing
  - `current_weight_pct` removed from thesis frontmatter (region block is now the only source of truth for current weight — the field could never actually stay in sync)
  - Transaction log cap raised from a hardcoded 5 to `config.THESIS_TXN_LOG_LIMIT` (20), with inline `(showing N of M)` disclosure when still capped
  - New level-coverage report (`utils/level_coverage.py`), health-failure sentinel + pipeline lock (`logs/HEALTH_FAILURE.flag`, `logs/pipeline.lock`), and an Earnings-proximity column on the Command Center
  - `derive_rotations` now runs as STEP 10 of `pm morning` (dry-run staging only)
- **Post-hardening cleanup + thesis prose hygiene (2026-07-29)** — two same-day follow-up batches. See CHANGELOG `[2026-07-29] — Post-hardening cleanup + thesis prose hygiene`. Headline changes:
  - `pm clean theses --live` now skips any thesis newer than the `Holdings_Current` refresh instead of archiving a position opened since the last sync
  - ETF look-through aggregates dual-listed issuers (`config.ISSUER_ALIASES`: GOOGL→GOOG, SKHY→000660.KS) instead of splitting one company's exposure across two symbol rows
  - CSV fallback parser now has smoke test coverage (previously zero) after an `ETF_KEYWORDS` `AttributeError` reached runtime
  - New standalone `tasks/lint_theses.py` — read-only vault linter for stale prose weight claims, duplicate state values, combined headers, unresolved `[BILL]` placeholders, stale reviews
  - GLD/META prose weight claims deleted (not corrected) to stop silently drifting from the synced figure; 14 files scaffolded with empty `## Scaling State`/`## Rotation Priority` sections (`[BILL]` placeholder, no inferred values)
- **Pipeline-lock duplicate bug fixed (2026-07-30)** — a leftover primitive lock block in `morning()`, never removed when `_acquire_pipeline_lock()` was added, made every `pm morning --live` run fail immediately with "another instance is currently running" even with no second instance present. See CHANGELOG `[2026-07-30]`.

### Automation
- GitHub Actions: podcast pipeline Friday 5pm EST cron + `workflow_dispatch` — **currently non-functional**: YouTube blocks transcript requests from Azure cloud runner IPs. The workflow reports green but processes 0 episodes. Last successful automated run: June 2, 2026.
- **Podcast ingestion workaround**: run `pm agent ideas` (or `pm ingest podcasts --live`) locally. Local machine IPs are not blocked by YouTube.
- GCP Cloud Scheduler + Cloud Function: Schwab token refresh every 25 min during market hours
- GCP project: `re-property-manager-487122` (shared with RE Property Manager)

---

## What's Next

### Do this first: review and promote `Trade_Log_Staging`
`tasks/derive_rotations.py` now runs automatically as STEP 10 of every `pm morning` (dry-run staging only, 2026-07-29), on top of the 17 candidate clusters already staged 2026-07-27 — `Trade_Log` had zero rotations logged in 97 days going into that first run. None are promoted yet; this needs a manual pass, not just a skim, because **the clustering algorithm bundles every sell and every buy inside its window into one row rather than pairing the actual substitution legs.** Concretely:
- The cluster anchored **2026-06-24** contains the real NOW + IGV → APO / KRE / MELI / LLY rotation, but bundled with five unrelated sells (XLE, APA, QQQM, SAP, MSFT, JPIE, PPA) and nine unrelated buys (COF, XLF, CFG, JEPI, META, VTI, FITB, SPCX, WSM, GLD).
- The cluster anchored **2026-07-20** contains the real EMXC → BBJP rotation, bundled with unrelated sells (MSFT, CRWV, NFLX, DELL, LRCX, GLD, AMD, SPCX) and buys (JEPI, AAPL, QQQM, WSM, UNH).

For each row: trim to the actual substitution pair, fill `Implicit_Bet`/`Thesis_Brief`, then promote. See CHANGELOG `[2026-07-27]` for the full diagnosis; the clustering logic itself (`window_days`, transitive same/adjacent-day grouping in `derive_clusters()`) is still unfixed and will produce the same conflation on every run, including the automatic ones now.

~~Six orphaned thesis files also need archiving~~ — done 2026-07-29: AMD, CRWV, DELL, LRCX, MSFT, SPCX moved to `vault/theses/archive/`.

### New positions to reconcile: IBM, SKHY
- **IBM** — initiated 2026-07-27 (`vault/theses/IBM_thesis.md`, style `FUND`), funded by trimming IGV/VEU/JEPI.
- **SKHY** — initiated 2026-07-29 (`vault/theses/SKHY_thesis.md`); opened after that morning's `Holdings_Current` refresh, so it wasn't yet in the bundle as of the post-hardening-cleanup batch and carries 4 unresolved `[BILL]` placeholders by design.

For each: run a Schwab sync (`pm morning --live` covers it), then `pm vault sync --live` to replace the thesis file's placeholder cost basis/allocation with real numbers. Verify neither was swept by `pm clean theses --live` before its first sync landed.

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
- **`config.DRY_RUN` defaults to `False`, not `True`** — `os.getenv("DRY_RUN", "False").lower() == "true"` is backwards from the stated hard rule if the env var is unset. Found 2026-07-29; not fixed because it's dead in the active path — only `archive/streamlit_legacy/` and the legacy `pipeline.py` shim read it, and every live command enforces dry-run-by-default independently via its own `--live` flag. Worth fixing or removing so the name stops being misleading.
- **`lint_theses.py` stale-weight regex has at least two known false-positive patterns** — first run (2026-07-29) flagged VRT and VST alongside the real GLD/META bug. On inspection neither was real: VRT's match was a `1.6%` figure describing *ETN's* ceiling headroom in a sentence about VRT, not VRT's own weight; VST's match was inside a dated Review Log entry (accurate as of 2026-07-28), not an undated current-state claim. Left both files untouched. Worth tightening the regex (subject scoping, and excluding dated Review Log lines) before wiring the linter into preflight.
- **Two Schwab-token health signals can disagree** — `tasks/health.py`'s check and `build_command_center.py`'s own GCS blob lookup (`_schwab_token_status()`) are independent and were observed to report different states (WARN "expiry unknown" vs. `AUTH REQUIRED`) in the same session, 2026-07-29. Both now correctly avoid rendering `n/a`, but they aren't reconciled to the same underlying check.
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
| **Portfolio size** | $593,201.73 across 36 positions (bundle `80262d14c656`, 2026-07-27) — IBM not yet included, pending sync |
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

- **2026-07-30** — Found and fixed a bug where `pm morning --live` refused to start on every run: a leftover primitive lock block in `morning()` collided with `_acquire_pipeline_lock()` (added the day before), which had already created the same lock file a few lines earlier. Removed the dead duplicate; not a stale-lock issue, there was never a real second instance.
- **2026-07-29** — Ran the full briefing-integrity-hardening prompt (P0/P1/P2), jointly with a parallel Gemini CLI session working the same prompt file. Notable calls: deleted `current_weight_pct` from thesis frontmatter rather than fixing the sync path that could never actually write it (it matched a fenced-block format no active file uses); serialized `pm morning` behind a `logs/pipeline.lock` file (auto-released via `atexit`) after Gemini's review flagged a race between a scheduled and a manual run both touching `logs/HEALTH_FAILURE.flag`. Caught one live bug mid-build from the parallel session: a `provenance` param had been added to `build_theses_md()` without ever being passed from `main()`, silently dropping the citation-marker disclosure it was meant to carry — fixed before it shipped.
- **2026-07-29** — Ran two same-day follow-up batches (post-hardening cleanup, thesis prose hygiene). Notable calls: fixed `pm clean theses` to skip theses newer than the `Holdings_Current` refresh rather than archiving a just-opened position (live case: SKHY); added a hand-maintained `ISSUER_ALIASES` map instead of automated issuer resolution for the ETF look-through; deleted (not corrected) GLD/META's stale prose weight claims, and left VRT/VST alone after `lint_theses.py` flagged them but manual inspection showed both were false positives, not the same bug.
- **2026-07-27** — Committed the 2026-07-26 exporter/thesis-sync fix (`7882b1c`) after verifying it end-to-end — it had been sitting uncommitted since the prior session. Also ran `derive_rotations` for the first time in 97 days (17 candidates staged, unreviewed — see What's Next) and initiated a new position, IBM, on a Stephanie-Link-sourced value thesis (~19 P/E post-selloff), funded by trimming IGV/VEU/JEPI.
- **2026-07-26** — Ingested the Spotify weekly podcast aggregate as a single first-class source in its own voice, rather than decomposing it into constituent episode files. Rationale: decomposition made one digest appear as three agreeing sources in theme extraction, and discarded the aggregate's own synthesis. Manual-ingest CLI command deferred; hand-drop into `data/podcast_summaries/` for now.
- **2026-07-26** — Established the standing principle that **the vault and `Trade_Log` lag Bill's decisions and are not evidence against them**. Encoded as Ground Rules v2 in the briefing prompt. Three of the sharpest findings in the 2026-07-26 briefing (cash posture, EMXC "drift", NOW "data artifact") dissolved on contact with actual intent; all three were documentation gaps reported as behavioral incoherence.
- **2026-07-26** — Fixed the thesis sync allocation bug that hid all ceiling breaches. Chose deterministic recomputation from market value over replicating `manager.py`'s `max <= 1.5` heuristic, which is itself unsafe for a sufficiently diversified book.
- **2026-07-26** — NOW conviction break formalized (seat-priced workflow vendors through the AI transition); EMXC reduced on Taiwan concentration. Both thesis files rewritten to match decisions already executed.
- **2026-05-26** — Reframed agent kit. Dropped Re-buy/Add-Candidate/Screener/Coherence agents. New direction is Idea Generator (shipped) + Valuation Drift Monitor (next).
- **2026-05-26** — Shipped Idea Generator v1. First real run produced 7 candidates from 3 podcast transcripts with reliable style classification and overlap detection.
- **2026-05-26** — Bundle infrastructure audited and confirmed working. No hardening pass needed before agent layer.
- **April 2026** — Architectural pivot away from Streamlit-first to CLI + Sheets spine.
