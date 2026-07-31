# CHANGELOG — Investment Portfolio Manager

## [Unreleased]

## [2026-07-30] — Duplicate pipeline-lock bug fix

### Fixed
- **`pm morning --live` refused to start, every time** (`manager.py`) — the 2026-07-29 hardening batch added `_acquire_pipeline_lock()` (stale-lock takeover after 3h, released via `atexit`) and wired it into `morning()`. A second, older, primitive lock block (`os.open(lock_path, O_CREAT | O_EXCL | ...)` against the same `logs/pipeline.lock` path) was left in place a few lines later and was never removed. Since `_acquire_pipeline_lock()` had just created that file, the second block's `O_EXCL` open always raised `FileExistsError`, which printed "Another instance of the morning pipeline is currently running" and aborted the run unconditionally — there was never a live second instance. Deleted the dead duplicate block; `_acquire_pipeline_lock()` alone now owns acquisition, staleness, and release.

## [2026-07-29] — Post-hardening cleanup + thesis prose hygiene

Two follow-up batches run the same day as the hardening pass above, driven by `prompts/post_hardening_cleanup_2026-07-29.md` and `prompts/thesis_prose_hygiene_2026-07-29.md`. Both batches were constrained to leave `tasks/export_ai_briefing.py` and the `pm morning` step order untouched pending the first unattended run of the rewritten exporter.

### Fixed
- **`pm clean theses --live` could archive a thesis for a position opened minutes earlier** — it flags any ticker absent from `Holdings_Current`, which is true by definition for a position bought since the last Schwab sync (live case: `SKHY_thesis.md`, opened 2026-07-29 after that morning's 08:22 refresh). `clean_theses()` now skips a file when its frontmatter `entry_date` or file mtime is on or after `Holdings_Current`'s `Import Date` footer (falls back to a `--min-age-days 7` guard if that footer isn't readable), and reports skips explicitly (`SKIPPED SKHY: thesis newer than Holdings_Current refresh...`) rather than silently passing over it.
- **ETF look-through understated dual-listed issuer exposure by ~60% on SK Hynix** — the look-through (`utils/etf_holdings.py`) keys purely on ticker symbol, so the same company under two symbols (GOOG/GOOGL, or SKHY's Nasdaq listing vs. 000660.KS held inside EMXC/VEA) reported as two unrelated companies. Added a hand-maintained `config.ISSUER_ALIASES` map (`GOOGL→GOOG`, `SKHY→000660.KS`) and aggregate on the canonical symbol while keeping constituent symbols visible in the Sources column. Deliberately not automated via a vendor lookup — extend the map by hand as new dual listings are actually held.
- **`AttributeError` on `ETF_KEYWORDS` reached runtime in the CSV fallback parser with zero smoke coverage** — added the missing `config.ETF_KEYWORDS` constant, and added `tests/test_bundle_smoke.py` coverage for `utils/csv_parser.py`: clean import, a parse run against an existing repo CSV fixture asserting `ticker`/`market_value`/`cost_basis` populate, and one assertion each for multi-account section parsing and fractional-share handling. This is the disaster-recovery path for when the Schwab API is down; it had no tests at all before this.
- **Two thesis files stated a current-allocation percentage in prose that silently drifted from the machine-synced figure** (`GLD_thesis.md`, `META_thesis.md`) — same failure class as the VRT 0.56%-vs-1.20% incident that motivated this whole hardening effort. Fix is deletion of the stale number, not correction of it (correcting it just resets the same clock); `<!-- region:position_state -->` is the sole synced source of current weight. GLD's combined `## Scaling State & Priority` header was also split into the separate `## Scaling State` / `## Rotation Priority` sections the parser and exporter expect, transcribing Bill's existing prose verbatim rather than inferring new content — this was the one case in the batch where transcription was permitted, because the value already existed in his own words in the same file.

### Added
- **`tasks/lint_theses.py`** — standalone, read-only vault linter (no writes, no Sheets, no network). Flags prose current-allocation claims that diverge from `<!-- region:position_state -->` by more than 0.05pp, duplicate `priority:`/`next_step:` values across sections, combined `## Scaling State & Priority` headers, unresolved `[BILL]` placeholders (informational), and `last_reviewed` older than 90 days. Exit code always 0 — a report, not a gate; wiring into preflight is deferred until the rewritten exporter survives an unattended run. First run surfaced two likely false positives worth noting rather than auto-fixing: VRT's flag matched a `1.6%` figure describing ETN's ceiling headroom, not VRT's own weight; VST's flag matched a `2.63%` inside a dated Review Log entry (accurate as of 2026-07-28, not a silent current-state claim). Left both files untouched — see Watchlist in `state.md`.
- **Fourteen thesis files scaffolded with empty `## Scaling State` / `## Rotation Priority` sections** (structure only, values left as a literal `[BILL]` placeholder) — AMZN, ETN, JPIE, META, XOM (Scaling State) and those plus GILD, GLD, GOOG, UNH (Rotation Priority), wherever the section was genuinely absent rather than present in an unparsed prose format. Deliberately no inferred content: Bill is the authoritative source on his own scaling/rotation intent, and a plausible-looking auto-filled value would become a fabricated baseline that future drift checks measure against.

## [2026-07-29] — Briefing integrity hardening (P0/P1/P2)

Driven by `prompts/briefing_integrity_hardening_2026-07-29.md`, triggered by the 2026-07-29 morning brief producing three false findings and missing one real failure. Built jointly across two sessions working the same prompt file in parallel (this one, and Gemini CLI) — each read the other's on-disk changes as they landed; see the last bullet under Fixed for the one place that caused a real (caught) bug.

### Fixed
- **Exporter shipped only the Core Thesis first paragraph** (`tasks/export_ai_briefing.py`) — `## Key Risks`, `## Hard Exit Conditions`, `## Scaling State`, `## Rotation Priority` were never extracted at all, so the analysis prompt asked the model to flag risks a document couldn't possibly contain them in. `build_theses_md()` now ships full sections per a `--thesis-detail {full,standard,minimal}` flag (default `standard`), with a disclosure line at the top of `theses.md` naming exactly what's included/omitted and the transaction-log cap. `minimal` reproduces the old behavior for size-constrained runs.
- **Scaling State / Rotation Priority parser reported the wrong cause of failure** — `extract_key_value()` required an exact `next_step:`/`priority:` line at column 0; files written in prose or with a bulleted/bold label (`- **Next step:**`) came back `None` and were reported as missing the section entirely, when the section existed and was populated. Rewrote to tolerate a leading list marker, bold-wrapped labels, and `_`/` ` case-insensitive keys, with a prose fallback tagged `(prose)`. Preflight now distinguishes three real states (section absent / parsed via prose fallback / section present but empty) instead of one blanket "missing" bucket.
- **`current_weight_pct` in thesis frontmatter could never stay in sync** — traced to `ThesisManager.update_triggers()` only matching a standalone fenced ` ```yaml ` triggers block; zero active thesis files use that format (triggers live inside the main frontmatter instead), so the sync writer's trigger update was a silent no-op for every real file. Audited all 19 files carrying the field; 6 had already diverged from `region:position_state` (AMD, GOOG, JPIE, META, UNH, XOM). Deleted the field entirely rather than fixing the dead sync path — the region block is now the sole source of truth for current weight.
- **Transaction log silently capped at 5 entries** (`core/thesis_sync_data.py`) — a position with more than 5 trades in its history had older lots invisible to a holding-period/tax-loss read with no indication anything was cut. Cap raised to `config.THESIS_TXN_LOG_LIMIT` (default 20, overridable via `vault sync --txn-limit`); the region now states `(showing N most recent of M)` inline whenever it's still truncated.
- **Citation-marker disclosure was being silently dropped** — a same-day edit added a `provenance` parameter to `build_theses_md()` (to move `[file:N]`/`[web:N]` strip counts out of `preflight_issues` into a manifest `provenance` block, since a stripped-marker count reads as a defect report rather than a provenance note) but `main()` never passed a `provenance` dict through, so the information vanished from both the old and new locations. Wired it through; verified `manifest.json` now carries `{"provenance": {"stripped_markers": {...}}}` and the line no longer appears in `preflight_issues`.

### Added
- **Level-coverage report** (`utils/level_coverage.py`) — cross-references held positions against thesis frontmatter (`price_trim_above`/`price_add_below`/`last_reviewed`) to report positions missing a Trim level, missing an Add level, or stale (>90 days, configurable) since review. Surfaces as a one-line footer count on the Command Center (`Levels: 14/34 trim, 8/34 add, 0 stale`) and as a full list in both the Command Center's own computation and the AI briefing `manifest.json`.
- **Health-failure sentinel** (`tasks/health.py`) — `write_failure_sentinel()`/`read_failure_sentinel()`/`clear_failure_sentinel()` write `logs/HEALTH_FAILURE.flag` (timestamp, failing checks, remediation command, a `run_id`) on a critical health failure in an unattended `pm morning` run, instead of failing silently to a log file nobody reads. Cleared automatically on the next run that isn't a critical failure. `build_command_center.py`'s Schwab Token footer cell now renders `AUTH REQUIRED` / `STALE (Nd)` / `DEGRADED` instead of `n/a` when the sentinel is present or the GCS token lookup itself fails. `export_ai_briefing.py` prepends a plain-ASCII staleness banner to `portfolio.md`/`theses.md`/`SUBMIT_ME.md` whenever the sentinel is set.
- **Pipeline lock** (`manager.py`) — `logs/pipeline.lock`, acquired at the top of `morning()` and released via `atexit`, refuses to start a second `morning` run while one is in progress (stale locks >3h are taken over). Added per Gemini's review of the sentinel design: a scheduled run and a manual run overlapping could otherwise race on `HEALTH_FAILURE.flag` — one run's success deleting a flag the other just raised, or vice versa.
- **Earnings-proximity column** (`utils/fmp_client.py`'s `get_earnings_calendar_cached()`, wired into `build_command_center.py`) — new `Earnings` column showing `TODAY`/`T-2`/`T+1`/blank, cached daily, sourced from FMP's earnings calendar within a ±3 day window. Directly addresses the 2026-07-29 briefing's confidently-wrong "the price feed is broken" call on a −12.2% VRT move that was actually a pre-market earnings reaction.
- **`derive_rotations` wired into `pm morning`** (STEP 10) — runs under dry-run by default, stages candidate clusters to `Trade_Log_Staging`, never auto-promotes. Verified it correctly stages the 2026-07-20 EMXC→BBJP pair.
- **`GEMINI_REVIEW_REQUEST_briefing_integrity.md`** — the mandated P0→P1 checkpoint; contains real Gemini CLI answers on default detail level (`standard` confirmed), the prose-fallback tradeoff, the `current_weight_pct` deletion call, and the sentinel concurrency question.

### Changed
- **Six orphan thesis files archived** (`vault/theses/archive/`): AMD, CRWV, DELL, LRCX, MSFT, SPCX — positions with no corresponding holding, previously re-flagged as a preflight warning on every single run.

### Diagnosed (not fixed — flagged for decision)
- **`config.DRY_RUN` (`config.py`) defaults to `False`, not `True`** — `os.getenv("DRY_RUN", "False").lower() == "true"` evaluates false when the env var is unset, which reads backwards against the stated "DRY_RUN defaults true" rule. Not touched: grep confirms every live command path (`manager.py`, `tasks/*`) enforces dry-run-by-default independently via its own `--live` flag, and the only callers of `config.DRY_RUN` itself are in `archive/streamlit_legacy/` and the legacy `pipeline.py` shim. Dead in the active path today, but the name is misleading if anyone wires it up again.
- **Two independent, disagreeing Schwab-token health signals** — `tasks/health.py`'s check reported `WARN: token present but expiry unknown` in the same session where `build_command_center.py`'s own GCS blob lookup reported `AUTH REQUIRED`. Both are now correctly non-`n/a` (the actual D6 fix), but the two mechanisms can still tell different stories about the same token; not reconciled here.

## [2026-07-27] — Morning export fix committed + Trade_Log_Staging populated + IBM initiated

### Committed
- **The entire 2026-07-26 exporter/thesis-sync fix landed in `7882b1c`** — it had been sitting uncommitted in the working tree since the prior session (STEP 9 in `manager.py`, the `thesis_sync_data.py` weight fix, the exporter rewrite, `utils/etf_holdings.py`, and all 41 rewritten thesis files). Verified working end-to-end before committing: `exports/ai_briefing_2026-07-27_084807/` was produced by `run_morning_sync.bat` against a same-morning bundle, carrying Ground Rules v2 and the corrected NOW/EMXC thesis content. Folded in `.gitignore` cleanup for the `*.bak.*` archive-before-overwrite backups and `data/etf_holdings_cache/`, neither of which had a rule before.

### Added
- **`Trade_Log_Staging` populated for the first time in 97 days.** Ran `tasks/derive_rotations.py` (dry-run reviewed first, then a live run) over the last 90 days of transactions; wrote 17 candidate rotation clusters. Includes clusters touching the two rotations flagged in `STATE.md` (2026-07-20 EMXC/BBJP-adjacent, 2026-06-25 NOW+IGV/APO-KRE-MELI-LLY-adjacent) — see Diagnosed below for why "touching" isn't "matching." Rows are unreviewed; promotion into `Trade_Log` is still manual.
- **New position: IBM**, initiated 2026-07-27. Funded by trimming IGV (stub, ~0.08% of book), VEU (stub, ~0.42%), and JEPI (trimmed off its over-ceiling ~9.87%). Thesis (`vault/theses/IBM_thesis.md`) filed under the `FUND` style (Boring Fundamentals / fear-driven dip-buy) — value case at a ~19 P/E after a post-guidance-cut selloff, sourced from Stephanie Link commentary, plus IBM's Open Secure AI Alliance participation. Cost basis and allocation are explicit placeholders (`0.00`) pending Schwab sync; the position isn't in any bundle yet.

### Diagnosed (not fixed — flagged for decision)
- **`derive_rotations.py`'s clustering conflates unrelated trades that share a window.** `derive_clusters()` groups *every* sell and *every* buy inside `window_days` (default ±1 day, and the sell-side grouping chains transitively across a run of adjacent trading days) into one cluster, rather than pairing the specific substitution legs. At 36+ positions with small-step scaling, unrelated trades routinely land in the same multi-day span: the cluster anchored 2026-06-24 bundles the real NOW/IGV → APO/KRE/MELI/LLY rotation together with five unrelated sells (XLE, APA, QQQM, SAP, MSFT, JPIE, PPA) and nine unrelated buys (COF, XLF, CFG, JEPI, META, VTI, FITB, SPCX, WSM, GLD); the 2026-07-20 cluster does the same to EMXC → BBJP. All 17 clusters were written to staging as-is rather than pre-trimmed — `Trade_Log_Staging` is the intended review surface — but the clustering algorithm itself doesn't isolate real rotation pairs, so every row needs a human pass before promotion, not just a skim.
- **Retracting a 2026-07-26 diagnosed item as moot**: that entry claimed `CLAUDE.md` states a `gemini-3.0-flash` model string that disagrees with `config.py`'s `gemini-2.5-pro`. Checked `CLAUDE.md` directly — it contains no model-version string at all (only references `GEMINI_MODEL` as a named constant). No disagreement exists; nothing to fix.

## [2026-07-26] — Thesis sync allocation bugfix + briefing ground rules v2 + vault reconciliation

### Fixed
- **Thesis sync wrote allocations 100x too small, hiding every ceiling breach** (`core/thesis_sync_data.py`): the Holdings sheet stores `Weight` as a *fraction* (position MV ÷ total MV, per `utils/risk.py:69`), but `gather_thesis_sync_data()` only applied the `* 100.0` scaling in its fallback branch — the one that fires when `Weight == 0.0`. Whenever the column was populated (i.e. always), the raw fraction was written straight through: NOW `1.09%` → `0.01%`, JEPI `9.92%` → `0.10%`. Because `drift = weight - ceiling`, drift came out ≈ `-ceiling` for **all 35 synced positions**, so the vault reported nothing anywhere near a size ceiling. Three genuine breaches were suppressed: JEPI (true drift **+1.92%**, written −7.90%), QQQM (**+0.72%**, written −7.91%), MELI (**+0.07%**, written −2.97%). Fixed by recomputing weight deterministically from market value rather than trusting the ambiguous column; the stored-column path is retained only for the degenerate no-priced-positions case. Verified to produce identical correct output under both fraction-stored and percent-stored conventions. **Bundle-level `Style Size Ceiling Check` in `export_ai_briefing.py` was correct throughout** — this was isolated to the thesis-file sync path, which is why the two surfaces disagreed. See `THESIS_SYNC_FIX_2026-07-26.md`. Requires one `pm vault sync --live` to rewrite the affected files.
- **Dead trigger in `NOW_thesis.md`**: `price_trim_above: 250.00` against a ~$98.78 share price — unreachable, would never have fired. Removed.

### Added
- **Briefing prompt Ground Rules v2** (`tasks/export_ai_briefing.py`): a governing principle plus 8 numbered hard rules appended to the `## Ground rules` block of the generated `prompt.md`. Each rule traces to a specific failure in the 2026-07-26 briefing. Governing principle: *Bill is the authoritative source on Bill's decisions; the vault and log are lagging records, not evidence against them* — where files and observed trades disagree, the default inference is "the file is stale," not "the behavior is incoherent." Rules cover: never infer liquidity posture from this export (`CASH_MANUAL` does not represent the cash position); do not relitigate the role of an established position (JEPI is held for low beta, settled); suppress ceiling flags on ballast/core holdings; scan ±3 days for an offsetting leg before calling anything drift; treat a sale at a loss as a presumptive conviction change, not a data artifact; no process moralizing; separate tax facts from behavioral narrative; rank system findings separately from portfolio findings.
- **Spotify podcast aggregate as a first-class source** (`data/podcast_summaries/2026-07-26_Spotify_Podcast_Aggregate_*.md`): third-party weekly aggregate ingested in its own voice rather than decomposed into constituent episodes. Carries a `PROVENANCE:` footer marking it as non-transcript and non-fetcher-produced, plus an independent `VERIFICATION:` block. Confirms NY Executive Order 62 (signed 2026-07-14, hyperscale data centers ≥50 MW, up to one year, first statewide moratorium), Microsoft ~$190B and Alphabet $195–205B CY2026 capex; flags the digest's Meta "$145B" figure as **disputed** against contemporaneous $115–135B reporting; notes the 12 GW interconnection-queue figure as unverified.

### Changed
- **`NOW_thesis.md` rewritten to match a made decision**: position was exited on a conviction break (unwilling to underwrite a seat-and-module-priced workflow vendor through the AI transition — the risk is the category deflating from inside an intact customer relationship, so renewal rate is the wrong metric and seats/modules-per-customer is the right one). Scaling `hold → reduce`, priority `very low → high`. Prior bull case retained but marked non-operative. Entry Context corrected — the "phenomenal legacy entry / immune to multiple compression" framing was written against a much lower basis and no longer described the remaining 65 shares.
- **`EMXC_thesis.md` rewritten to match a made decision**: position reduced 2026-07-20 on Taiwan concentration risk — "ex-China removes one country and overweights two." Concentration promoted to the primary risk above the geopolitical line, with the note that it stacks on QQQM/NVDA/AVGO rather than diversifying them. Scaling `hold → reduce`. Placeholder cost basis `~$82.50 (Assumed)` replaced with actual ($97.61/sh blended).

### Diagnosed (not fixed — flagged for decision)
- **`manager.py:850` weight heuristic is unsafe in principle**: `if df_h["Weight"].max() <= 1.5: df_h["Weight"] *= 100` misfires on any book whose largest position is under 1.5% *and* percent-stored (1.2% → 120%). Does not misfire on the current portfolio (max 9.92%), so left untouched rather than modified while unrelated work was in flight. Durable fix is to have the producer write a percentage and drop both workarounds, or have every consumer recompute from market value as `thesis_sync_data.py` now does.
- **Two executed rotations absent from `Trade_Log`**: 2026-07-20 EMXC −100 sh (≈$9,250) → BBJP +125 sh (≈$9,181), same day; and 2026-06-25 NOW + IGV proceeds (≈$15.1K) → APO / KRE / MELI / LLY (≈$15.5K). The second is inferred from top-5 per-position transaction logs only and needs confirmation before promotion. `Trade_Log` currently shows zero rotations in 97 days. Run `derive_rotations` → review `Trade_Log_Staging` → promote.
- **`styles.json` `ETF` bucket conflates ballast with sector bets**: JEPI, JPIE, VTI, COWZ and VEA carry the same 8% ceiling as XBI, IGV, KRE and EWZ. Recommend splitting into `BALLAST_CORE` (high/no ceiling) and `SECTOR_ETF` (8%). Until then, ceiling BREACH flags on ballast positions are noise — and they crowd out the one flag that survives recalibration (MELI, 0.06% over).
- **`ET_thesis.md` may be stale on Lake Charles**: thesis describes "pipeline **and export terminal** networks." Reporting indicates Energy Transfer suspended the ~$5.3B Lake Charles LNG project to redirect capital toward its pipeline backlog serving power generation and data campuses, though other sources still describe an early-2026 FID with ~11.9 mt/yr contracted. Reporting genuinely conflicts — verify against primary filings before relying on either.
- **`STATE.md` drift**: claimed 62 thesis files (actual: 41) and `~$550K` portfolio (actual: $589,395.86 per bundle `75caa01bedab`). Corrected in this pass.
- **`CLAUDE.md` model string disagrees with code**: `CLAUDE.md` states `gemini-3.0-flash`; `config.py:69` and `STATE.md` both say `gemini-2.5-pro`. Not changed — confirm which is authoritative.

## [2026-06-15] — Podcast pipeline diagnosis + idea generator auto-ingest

### Fixed
- **`weekly_podcast_sync.py` never saved raw transcripts**: The automated pipeline fetched YouTube transcripts into memory, ran Gemini analysis, and wrote to Sheets — but never wrote `.txt` files to `data/podcast_transcripts/`. The idea generator reads exclusively from that directory, so it found 0 transcripts on every run since June 2. Fixed by saving the full transcript text to `data/podcast_transcripts/` immediately after the YouTube fetch, before the Gemini step.
- **`batch_podcast_sync.py` swallowed subprocess errors**: On failure, it logged `result.stderr` — but all error messages in `weekly_podcast_sync.py` go to stdout via `print()`. The actual error was invisible in both local runs and GitHub Actions logs. Fixed to combine stdout + stderr in the failure log output (last 10 lines).

### Diagnosed (not fixed — requires architectural decision)
- **GitHub Actions podcast cron silently failing**: YouTube blocks transcript requests from Azure cloud IPs (GitHub Actions runner infrastructure). Every episode fails with `RequestBlocked` within ~2 seconds. The workflow reports green because `batch_podcast_sync.py` exits 0 regardless of channel failures. Last successful GitHub Actions podcast run was June 2, 2026. Workaround: run `pm ingest podcasts --live` locally; local machine IPs are not blocked.

### Changed
- **`pm agent ideas` now auto-ingests before analyzing**: Added podcast ingestion as Step 1 of the `agent ideas` command. Calls `podcast_batch(live=True)` to fetch new transcripts (respecting the dedup log), then runs the idea generator on whatever is on disk. If ingestion fails, the generator still runs with existing transcripts. Use `--skip-ingest` to bypass and go straight to the generator.

## [2026-06-04] — Morning cascade extension + reliability fixes

### Added
- **`pm morning` cascade steps 7–9**: after dashboard refresh, the pipeline now runs Vault Sync (Sheets → thesis files), Vault Snapshot (freeze local vault bundle), and Composite Bundle (link market + vault). All three are non-fatal and wrapped in try/except like the podcast step. Full step ordering: health → transactions → live update → snapshot → podcast sync → dashboard → **vault sync → vault snapshot → composite bundle**.
- **`pm morning --skip-vault-sync`**: bypass vault sync + vault snapshot + composite bundle in a single flag.
- **`pm morning --skip-composite`**: bypass vault snapshot and composite bundle only.
- **`pm login`**: new CLI command that runs the Schwab OAuth manual reauth script directly (`scripts/schwab_manual_reauth.py`).
- **`pm backup`**: new CLI command that archives the project and uploads to Google Drive (`scripts/backup_to_drive.py`). Accepts `--name` and `--folder-id`.
- **Schwab reauth prompt on critical health failure**: when `pm morning` hits a CRITICAL health failure, it now offers an interactive prompt to run the reauth script immediately rather than requiring a separate terminal.
- **`.bat` shortcuts**: `run_morning_sync.bat`, `run_idea_generator.bat`, `schwab_emergency_reauth.bat` — activate `.venv` and launch the relevant command without a pre-activated shell.

### Changed
- **Health table rendering**: `✓` / `⚠` / `✗` replaced with `PASS` / `WARN` / `FAIL`. Windows cp1252 terminals cannot render those Unicode symbols and the table was silently garbled.
- **Gemini credential resolution order** (`utils/gemini_client.py`): ADC (Vertex AI / `gcloud auth application-default login`) is now tried first; `GEMINI_API_KEY` env var is the fallback. Previous order caused the stale API key to win over valid ADC credentials, producing 400s on every local CLI run.

### Fixed
- **`pm morning` always exiting code 1 on Windows** (`scripts/live_update.py`): STEP 2 (Live Update) raised `UnicodeEncodeError: 'charmap' codec can't encode character '✅'` on every run because `print("✅ ...")`, `print("❌ ...")`, `print("ℹ️ ...")`, and `print("... →")` all contain characters cp1252 cannot encode. Replaced all five with ASCII equivalents (`[OK]`, `[ERROR]`, `[INFO]`, `->`). The cascade exit code now correctly reflects actual step outcomes.
- **Podcast step hang** (`manager.py`): `subprocess.run(cmd, capture_output=True)` had no timeout. `YouTubeTranscriptApi().fetch()` also has no timeout, so one captionless or slow-responding video blocked the entire morning pipeline indefinitely. Added `timeout=180`; `subprocess.TimeoutExpired` is caught by the existing `except Exception` block and recorded as WARN.
- **Podcast step silent failure masking** (`manager.py`): `batch_podcast_sync.py` uses `logging`, which writes to stderr. The count-parsing regex was searching `pod_result.stdout` (always empty); `n_processed` and `n_failed` were always 0, so every podcast run reported PASS even when channels failed. Switched to `pod_result.stderr`. The summary label now correctly shows `Podcasts (N new)` and surfaces WARN when channels fail.
- **Thesis frontmatter ticker mismatches** (`vault/theses/`): `AMZN_thesis.md` had `ticker: COF`, `ETN_thesis.md` had `ticker: NVDA`, `VEU_thesis.md` had `ticker: IFRA`. `gather_thesis_sync_data()` reads `fm['style']` from the frontmatter to determine position sizing rules — the wrong ticker meant style lookups were pulling from the wrong position's data. Corrected all three to match their filenames.

---

### Added
- **`pm morning --skip-podcasts`**: new flag to bypass the podcast batch sync step in the morning pipeline.
- **Podcast step in `pm morning`**: after snapshot, before dashboard — runs `batch_podcast_sync.py` via subprocess (non-fatal; a failed RSS fetch logs ⚠ and the dashboard still runs). Step ordering: health → transactions → live update → snapshot → **podcast sync** → dashboard. Summary table shows `Podcasts (N new)` with ✓/⚠/SKIP treatment.
- **Podcast ingestion universe expanded**: `PODCAST_CHANNELS` in `tasks/batch_podcast_sync.py` rebuilt to 10 verified channels — Forward Guidance, The Compound, BG2 Pod, Capital Allocators, Chat With Traders, On The Tape, CNBC Television, Top Traders Unplugged, Invest Like The Best, On Investing. All channel IDs confirmed live via YouTube RSS. Placeholder names and dead IDs removed.
- **Per-channel title filtering**: `PODCAST_CHANNELS` upgraded from flat `{name: channel_id}` to `{name: {channel_id, title_filter?}}` config dicts; the separate `TITLE_FILTERS` dict is removed.
- **`get_latest_video` title filter**: scans all feed entries (newest-first) and returns the first whose title contains `title_filter` (case-insensitive). A filtered channel with no matching episode logs an info-level skip and routes to `results["filter_skipped"]` — not `results["failed"]`.

### Changed
- **`batch_podcast_sync.py` main loop**: unpacks `cfg` dict per channel; logs `[filter: '...']` when a filter is active; summary now reports `Skipped (no filter match)` separately from dedup skips and failures.
- **`manager.py podcast_batch`**: fixed stale import of removed `TITLE_FILTERS` dict; loop updated to unpack per-channel config dicts matching the new `PODCAST_CHANNELS` format.

- **Idea Generator Agent (v1)**: New `pm agent ideas` command that consumes the composite bundle and recent podcast transcripts and writes a markdown report of investment candidates to `agent_outputs/ideas/`.
  - Pydantic schema: `Candidate` (ticker, company, style fit, portfolio relationship, concerns) + `IdeaGeneratorOutput` wrapper with `bundle_hash` traceability.
  - System prompt in `prompts/idea_generator.md` — style-aware, no price targets, no buy/sell recommendations.
  - Candidates sorted: new exposures first, then complements, then overlaps.
  - `--since-days N` to control transcript lookback window (default 7).
  - `--bundle-path` to override composite bundle (auto-detects latest if omitted).
  - `--dry-run` to print report to stdout without writing to disk.
- **`pm agent` CLI group**: New Typer group for AI agents. `agent ideas` is the first command under it.
- **`podcast_batch()` implementation**: The `pm ingest podcasts` / `pm podcast batch` function body was a stub. Fully implemented: iterates `PODCAST_CHANNELS` via YouTube RSS, checks dedup log, downloads transcripts via `fetch_transcript_to_file()`, reports per-channel status with Rich output.

### Changed
- **`config.py` — Gemini model**: Default `GEMINI_MODEL` corrected from `gemini-3.1-pro-preview-customtools` (invalid, 404 on this project) to `gemini-2.5-flash` (confirmed accessible).
- **`utils/agents/idea_generator.py` — transcript directory**: Reads from `data/podcast_transcripts/` (where `podcast_fetcher.py` writes `.txt` files) instead of `vault/transcripts/` (which holds vault `.md` docs — a different purpose).

### Fixed
- **`pm ingest podcasts` silent exit**: Command printed "Checking channels..." and immediately returned because `podcast_batch()` had no implementation. Now runs the full RSS → dedup → download loop.
- **Gemini credential resolution order inverted** (`utils/gemini_client.py`): ADC (Vertex AI / `gcloud auth application-default login`) is now tried first; API key is the fallback. Previous order caused the stale `GEMINI_API_KEY` env var to win over valid ADC credentials, producing 400s on every local CLI run.
- **Gemini Pydantic fallback strips markdown fences** (`utils/gemini_client.py`): When `response.parsed` is `None` (Vertex AI backend does not populate it), the fallback path now strips ` ```json ... ``` ` fences with a regex before calling `model_validate_json()`. Previously, a markdown-wrapped JSON response from Vertex caused the parse to fail silently and return `None`.

---

## [Prior]

### Added
- **0_DASHBOARD Command Center**: Single-screen daily view aggregating headline KPIs, tax posture, risk snapshot, top 5 positions (with trim/add target distances), drift alerts, and system health. Built by `tasks/build_command_center.py` and refreshed automatically as part of `pm refresh dashboard` and `pm morning`.
- **Unified Ingestion Workflow**: Introduced `pm ingest` group to centralize all data pull operations.
  - `pm ingest transactions`: Syncs Schwab transaction history (aliased from `pm sync transactions`).
  - `pm ingest realized-gl`: Imports Schwab Realized G/L CSV (aliased from `pm sync realized-gl`).
  - `pm ingest podcasts`: Fetches latest transcripts and runs optional AI analysis.
  - `pm ingest all`: Orchestrated command to run transactions and podcast updates in sequence.
- **Centralized Hygiene**: Introduced `pm clean` group for filesystem maintenance.
  - `pm clean exports`: Deletes old LLM context packages.
  - `pm clean podcasts`: Deletes old transcript files.
  - `pm clean bundles`: Deletes old market/vault/composite JSON bundles.
  - `pm clean all`: Runs all cleanup tasks using shared retention windows.
- **Consistent View Refresh**: introduced `pm refresh` group for rebuilding computed Sheet views.
  - `pm refresh dashboard`: Rebuilds Valuation_Card and Decision_View (aliased from `pm dashboard refresh`).
  - `pm refresh tax`: Rebuilds Tax_Control KPIs and lots (aliased from `pm tax refresh`).
  - `pm refresh rotations`: Rebuilds Rotation_Review attribution (aliased from `pm trade review`).
- **Shared Retention Constants**: Defined default purge windows in `config.py`:
  - `PURGE_DEFAULT_DAYS_PODCASTS = 30`
  - `PURGE_DEFAULT_DAYS_BUNDLES = 30`
  - `PURGE_DEFAULT_DAYS_EXPORTS = 7`
- **Session Purge Flag**: Added `--purge` flag to all `pm ingest` commands, allowing for "fresh start" hygiene automatically after data ingestion.

### Changed
- **CLI Architecture**: Major reorganization of `manager.py` to consolidate Typer app definitions at the module level. This resolves decorator dependency issues and supports cleaner command aliasing.
- **Deprecation Aliases**: Existing commands (`sync`, `tax`, `dashboard`, `trade review`) are preserved as hidden aliases to maintain compatibility with existing scripts.
- **CLI Docs**: Updated `CLAUDE.md` and `portfolio_manager_user_docs.html` to reflect the new workflow-oriented surface.

### Fixed
- **`tasks/sync_transactions.py`**: Fixed `UnboundLocalError` in the dry-run path when no new transactions were found. (Note: This bug only affected dry-runs and did not impact `pm morning --live` runs).
