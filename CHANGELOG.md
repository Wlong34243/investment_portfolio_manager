# CHANGELOG — Investment Portfolio Manager

## [2026-08-27] — Trade_Log rationale columns Q–S (Instrument prompt 7 Step 1)

Appended `Proposed_Bet`, `Rationale_Provenance`, `Rationale_Evidence` after `Fingerprint`
(Sheet header Q1:S1). Pre-edit archive `data/Trade_Log_bak_20260827T135331Z.csv` — Fingerprint
present, Proposed_Bet absent. `utils.column_guard.ensure_trade_log_columns` added;
`get_trade_log()` routes through it. Formatter A–S.

## [2026-08-27] — Instrument Wave A: evidence capture, corpus FTS, ledger off Drive

- **Ledger relocate:** `SQLITE_DB_PATH=C:\Users\wlong\AppData\Local\Investment_Portfolio\portfolio_store.db` (`.env` only). Drive-tree guard in `get_engine()`; first use blocked `C:\Dev\_local` because `C:\Dev` itself is synced. Pre-move backup Drive copy landed. Post-move guard silent; corpus **848/10,666** intact.
- **`BACKUP_DIR` repo-rooted** in `core/store/backup.py`; `pm store snapshot` / `provenance` added. Snapshots stay under `data/portfolio_store_backups/` (Drive offsite).
- **Evidence tables** `signal_events` / `bars_daily` / `fundamentals_snapshot` + `core/store/evidence.py`; morning wire after Decision_View; `--live`-gated. First accrual `2026-08-27`. Checklist rows 5/6/7 verified literal (15=15 full list; second live `inserted=0`; doctrine flags=2).
- **Corpus FTS** `core/corpus/` + `pm corpus`; empty `framework` source dropped; research JSON gap recorded in `state.md`.

## [2026-08-27] — Schwab token status divergence, root-caused (no fix — proposal only)

Third observation of the known issue (`state.md` 2026-07-29, 2026-08-07; `CLAUDE.md` Known Issues):
Command Center printed `AUTH REQUIRED` at 2026-08-26 12:12 while `tasks/health.py` raised no
`HEALTH_FAILURE.flag`, `Risk_Metrics` carried a Schwab `as_of` of `2026-08-26T04:00Z`, and the
composite bundle built cleanly at 12:17. This entry documents what each check path actually
measures and why they can disagree — **no code changed**, per instruction.

### What `tasks/health.py` measures (`_check_schwab_token_accounts` / `_check_schwab_token_market`)
- Two **independent, CRITICAL-level** checks — one for the "accounts" Schwab OAuth token blob,
  one for the "market" token blob (`config.SCHWAB_TOKEN_BLOB_ACCOUNTS` /
  `_MARKET`). Command Center's status string covers only the accounts token; a degraded market
  token is invisible to it.
- Reads via `utils/schwab_token_store.load_token()`, which resolves GCS credentials from
  `GCP_SERVICE_ACCOUNT_JSON` and **falls back to a local token file** if the GCS client itself
  fails to construct (`_get_storage_client()` returning `None`).
- Computes `expires_at - now()` on the **access token**. **FAIL if < 15 minutes remaining**
  (imminent expiry — the token will not survive the next pipeline step). Missing/unparseable
  expiry is `WARN`, not `FAIL` — an unknown state is reported as unknown, not as broken.
- Runs fresh, in parallel with every other check, on every `run_all_checks()` call — stateless,
  no caching, no memory of a prior run.
- Only a CRITICAL+FAIL result here (or from `_check_schwab_api_positions` /
  `_check_sheet_reachable` / `_check_latest_bundle_exists`, the other three CRITICAL checks)
  causes `write_failure_sentinel()` to write `logs/HEALTH_FAILURE.flag`, recording which check(s)
  failed and a UTC timestamp. A passing run calls `clear_failure_sentinel()` (`manager.py`
  `morning()`, around line 1905/1912) and deletes the flag. **The flag is written and cleared
  only inside `pm morning`'s STEP 0** — nothing else calls `write_failure_sentinel` or
  `clear_failure_sentinel`.

### What `build_command_center._schwab_token_status()` measures
This is a **different function measuring a different thing**, not a second copy of the same
check:
1. **First, and preferentially, it reads the sentinel file** (`read_failure_sentinel()`) — i.e.
   whatever `pm morning`'s STEP 0 last recorded, which can be arbitrarily stale if no morning
   run has completed since. If a sentinel exists:
   - and any `failing_checks[].name` contains `"schwab_token"` → returns `"AUTH REQUIRED"`,
     **regardless of whether the live token is fine right now**.
   - else (the CRITICAL failure was `sheet_reachable` / `bundle_exists` / `schwab_api_positions`,
     something unrelated to the token) → returns `"STALE (Nd)"` or `"DEGRADED"` from the
     sentinel's age, not `"AUTH REQUIRED"`.
2. **Only when no sentinel exists** does it fall through to a **live GCS read** — but this is a
   *second, independent* implementation of the same download, written inline in
   `build_command_center.py` rather than calling `schwab_token_store.load_token()`. It
   constructs its own `storage.Client()` with ambient default credentials (no
   `GCP_SERVICE_ACCOUNT_JSON` resolution, no local-file fallback), so the two code paths can
   authenticate to GCS differently and diverge on grounds that have nothing to do with the
   token's actual state.
3. The live path's threshold is **`< 2 days` → `"Expiring soon"`**, not 15 minutes — a
   coarser, differently-calibrated number answering a different operational question
   ("does Bill need to re-auth soon") than health.py's ("will the *next pipeline step* have a
   token").
4. **Any exception anywhere in step 2** — a transient GCS hiccup, a credentials error, a
   malformed blob, `blob.exists()` returning false — is caught and collapses to the single
   `except:` branch, which re-checks the sentinel once more and, failing that,
   **defaults to `"AUTH REQUIRED"`** as the final fallback. There is no way from the rendered
   string to tell "the token is actually expired" apart from "this function could not find out."

### Why 08-26 12:12 vs 12:17 is consistent with both mechanisms, and why neither is provable after the fact
- **Path 1 (stale sentinel):** if any CRITICAL check had failed earlier in the session and the
  flag naming a `schwab_token` check hadn't yet been cleared by a subsequent clean `pm morning`
  run, Command Center would print `AUTH REQUIRED` on every render until the next passing STEP 0 —
  independent of whether the token was fine a minute later. `logs/HEALTH_FAILURE.flag` does not
  exist as of this write-up (2026-08-27), so the historical 12:12 state can't be re-read directly;
  it was presumably cleared by a later clean `pm morning` run the same day or the next.
- **Path 2 (silent exception → worst-case default):** this requires no stale file at all — a
  transient failure in Command Center's own inline GCS call at exactly 12:12, self-healed by
  12:17, produces the identical symptom. `state.md`'s 2026-08-07 occurrence (`AUTH REQUIRED` with
  the flag *confirmed absent*) is only explainable by this path, which is why both mechanisms are
  recorded here rather than picking one.
- Either way, the bundle export succeeding at 12:17 and `Risk_Metrics`' `04:00Z` `as_of` both used
  the Schwab API directly and are strong evidence the underlying token was never actually broken
  that morning — Command Center's `AUTH REQUIRED` was a reporting-path artifact, not a real outage.

### Proposal — not implemented, Bill's call
A single shared `get_schwab_token_status(blob_name) -> TokenStatus` in `utils/schwab_token_store.py`
that both `health.py` and `build_command_center.py` call, returning a small typed result
(`state: PASS|WARN|FAIL|UNKNOWN`, `detail: str`, `checked_live: bool`) rather than two
independently-formatted strings. Sketch, for Bill to accept/reject/amend — **do not build without
sign-off**:
- One credential-resolution path (`schwab_token_store._get_storage_client()`), so the two
  consumers can no longer diverge on auth grounds alone.
- One threshold, or two named thresholds both consumers agree on explicitly (e.g. `imminent`
  at 15 minutes for pipeline-gating, `renewal_due` at 2 days for the human-facing display) —
  today's 15-minute/2-day split is incidental, not a deliberate two-tier design.
- Sentinel-awareness stays a Command-Center-only *rendering* decision (it wants "is the pipeline
  currently degraded," which is legitimately different from "is the token valid right now"), but
  it should render as e.g. `"AUTH REQUIRED (as of last health check, HH:MMZ)"` rather than a bare
  `"AUTH REQUIRED"` indistinguishable from a live read — the timestamp is the cheap fix for the
  worst part of the ambiguity.
- A caught exception should render distinctly from a confirmed-bad token (`"STATUS UNKNOWN"` vs
  `"AUTH REQUIRED"`) — collapsing "couldn't check" into "confirmed broken" is the single biggest
  contributor to false alarms in this history.
This is a proposal only. No code in `tasks/health.py` or `tasks/build_command_center.py` was
changed in this pass.

## [2026-08-26] — Repo hygiene (prompt closure + obsolete archive)

- Incomplete prompts presumed not useful — archived with declined stamps (no builds): `prompts/archive/surface_attribution_2026-08-09.md`, `vault_framework_visibility_2026-08-01.md`, `commit_recover_dashboard_2026-08-09.md` (partially shipped; historical recovery deferred by design). `schwab_signal_layer_PROPOSAL` kept at `prompts/`; remaining §§ stamped unauthorized.
- Root one-shot notes → `docs/archive/root_notes_2026-08-26/` (`EXPORTER_FIX_*`, `THESIS_SYNC_FIX_*`, `GEMINI_REVIEW_REQUEST.md`, `lessonsLearned.md`, `re_portfolio_math.md`, `Implementation Plan.md`, `Functions.txt`, `bundle_audit.md`). Working-tree deletions left deleted: `UI_IMPROVEMENT_*`, `OBSOLETE_FILES_TO_ARCHIVE.md`, `GEMINI_REVIEW_REQUEST_briefing_integrity.md`.
- One-shot scripts → `archive/one_shot_scripts_2026-08-26/` (incl. cash probe, Agent_Outputs archive helper). Byte-identical `vault/frameworks/Macro_super_cycle_framework.md` + `joys_of_compounding_framework.json` → `archive/vault_frameworks_dup_2026-08-26/` (`vault/research/` copy remains the live loader).
- Docs sync: `state.md` What’s Next / Deferred; `CLAUDE.md` Known Doc Gaps + `PRICE_HISTORY_SOURCE` default `auto`; Phase 3 Rule 1 line corrected below.

## [2026-08-25] — Schwab Phases 2–4 (router, cash truth, Risk_Metrics + calendar)

### Phase 2 — price_history router + consumer migration
- Added `utils/price_history.py` (`get_bars` with yfinance/schwab/auto; fallback counter via `pm probe price-source-stats`).
- Migrated enrich_atr, technicals, enrich_technicals, dislocation returns, valuation_card 52w bars, command_center SPY YTD + 52w ranges, derive_rotations, compute_rotation_attribution onto the router.
- Tier 8a: dislocation 52w high prefers Schwab quote over FMP (FMP remains for other fundamentals).
- Tier 8b: `fetch_positions` Dividend Yield from Schwab quotes or `None` (never 0.0 for unknown).
- Default `PRICE_HISTORY_SOURCE` flipped to `auto`.
- **Gate C (attribution historical rows):** **FREEZE** (Bill 2026-08-25). `Price_Source` column; frozen rows stamp `yfinance|frozen_pre_schwab_2026-08-25`; new rows stamp live `get_bars` vendor(s).

### Phase 3 — cash / income / flows
- Cash probe (`archive/one_shot_scripts_2026-08-26/probe_cash_balances_2026-08-25.py`, formerly under `scripts/`): **ASSUMPTION HOLDS** — A=D=$2,359.98, B=0 across ...8767/...6499/...5119. No cash-formula remediation.
- Added `fetch_account_balances`, optional `transaction_types` + 60d chunking on `fetch_transactions`.
- `tasks/build_income_tracking.py` / `pm build income-tracking`; `tasks/build_flow_ledger.py` / `pm build cash-flows`; `TAB_CASH_FLOWS`.
- Analysis Rule 1 **rewritten** in `export_ai_briefing.py` / `PROMPT_PAYLOAD`: cash from Schwab balances across the three allowlisted accounts, reconciles to `liquidationValue`; still three-of-six scope — state the scope; do not extrapolate to net worth.

### Phase 4 — Risk_Metrics + market calendar
- `tasks/build_risk_metrics.py` / `pm build risk-metrics`; portfolio-summary row last for `_compute_beta`; bars via `get_bars`; no capm/stress/van_tharp.
- Morning STEP 5 sub-step (after val, before CC); `--skip-risk-metrics`.
- `utils/market_calendar.py`; STALE uses trading-day lag; Daily_Snapshots skips closed sessions (`None` still writes); `pm health` `market_status` informational.

## [2026-08-25] — Schwab data expansion Phase 1 (client + harness)

Prompt: `prompts/schwab_data_expansion_2026-08-25.md`. Additive only — no consumer behaviour change; `PRICE_HISTORY_SOURCE` defaults to `yfinance`.

### Added
- `config.PRICE_HISTORY_SOURCE` / `PRICE_HISTORY_CACHE_DIR` (`data/schwab_price_cache`) / TTL / `SCHWAB_MAX_RETRIES` / `SCHWAB_REFRESH_TOKEN_WARN_DAYS`
- `utils/schwab_client.py`: `fetch_price_history`, `fetch_price_history_batch`, `fetch_instrument_fundamentals`, `fetch_market_hours`, `is_trading_day`; quote-field widening on `fetch_quotes` (52w high/low, div yield/amount, P/E, quote_time, extended) — extraction only, five legacy columns preserved
- `scripts/reconcile_price_history_2026-08-25.py` + `pm probe` (price-history, fundamentals, market-hours, reconcile)
- `tasks/health.py`: `schwab_refresh_token_age` (WARNING level; never writes `HEALTH_FAILURE.flag`)

### Findings on record
- **Schwab daily bars are NOT dividend-adjusted** — match yfinance `auto_adjust=False` (JEPI mean abs rel bps ~0.007 vs False, ~398 vs True; same pattern XOM/VTI). Split-adjusted only.
- Quote payload nested under `quote` / `fundamental` / `reference` / `extended`; `realtime` present; quote_time ≈ wall clock → real-time feed for this account.
- `get_market_hours` rejects dates more than ~7 days in the past (HTTP 400); `is_trading_day` returns `None` on that failure.

## [2026-08-24] — Realized_GL multi-account import + parser fix

- Fixed `utils/gl_parser._find_account_sections_gl`: blank CSV cells (float NaN) caused every lot to be attributed to the first account section. Multi-account Schwab "All_Accounts" exports now split correctly.
- Imported `All_Accounts_GainLoss_Realized_Details_20260824-120714.csv` via `pm ingest realized-gl --merge --live` → 871 lots (was 636). Chase ...8895 preserved (80). New sections: Contributory ...767 (8767), Individual 401(k) ...499 (6499), HSA, Joint Tenants.
- Tax_Control rebuilt; YTD unchanged ($45,404.67 on 555× ...119) — 6499/8767 are tax-deferred. Corrects the earlier "Tax_Control understates" read.
- JPIE 08-21 exit broker-confirmed: −$55.43 Short Term in Contributory ...767 (matches Holdings_History-derived figure). Thesis Review Log updated; thesis archived to `vault/theses/archive/` same day.

## [2026-08-24] — JPIE exit log; Realized_GL single-account finding

- `vault/theses/JPIE_thesis.md`: Review Log exit terms for 2026-08-21 liquidating sells in Schwab...8767 (110 sh, proceeds $5,044.42, derived G/L −$55.43 from Holdings_History — labeled not broker-confirmed). Scaling state → exited. Thesis left live (archive held).
- Finding: Realized_GL / Tax_Control cover Schwab 5119 (`Individual ...119`) + Chase 8895 only — **zero** lots for in-scope 6499/8767. Tax YTD understates. Prompt: `prompts/realized_gl_multi_account_2026-08-24.md`.

## [2026-08-24] — Doctrine layer, decision-capture detector, thesis pattern tags

Three sequenced prompts: `doctrine_layer_2026-08-24.md`, `decision_capture_detector_2026-08-24.md`, `thesis_pattern_tags_2026-08-24.md`.

### Doctrine
- Added `vault/doctrine.md` (manual-only) + `utils/doctrine_reader.py` (soft-fail; never HEALTH_FAILURE).
- Seed constraints: `no_withdrawal_need`, `accumulation_phase`, `tax_hold_runners` (UNH+COF, any NEAR_TRIM → informational).
- Crosshairs: post-merge downgrade to bucket 400+ with `doctrine_tag=HOLD_TAX`; `reason_code` stays `NEAR_TRIM`.
- Briefing ships sixth file `doctrine.md` (after prompt, before portfolio); PROMPT_PAYLOAD treats it as authoritative on constraints.
- Migrated restated RE-cash-flow rationale out of QQQM / VST / VRT theses (pointers only; VRT position-specific accumulation sentence retained).

### Decision-capture detector
- `tasks/detect_undocumented_changes.py`: `NEW_POSITION_NO_THESIS`, `EXITED_POSITION_LIVE_THESIS`, `MATERIAL_RESIZE_NO_REVIEW` (both ≥0.50pp and ≥25% relative; suppress when no txn in thesis `transaction_log`).
- Manifest sibling `undocumented_changes` (independent of `preflight_issues`). Read-only — no Trade_Log / Holdings / Target_Allocation writes.
- Verified 08-24 vs 08-21 → exactly one JPIE `EXITED_POSITION_LIVE_THESIS`.

### Pattern tags
- Optional frontmatter `pattern:` via `thesis_reader.get_pattern` + vault bundle; one line in `theses.md` at standard detail.
- Tagged: QXO+UNH (`turnaround_reversion`), GLD (`debasement_hedge`), VRT+COF (`accumulate_on_decline`). COWZ/LLY/WSM/XBI/RRC left untagged by design. Screener deliberately not built.

## [2026-08-24] — Typed triggers reachable by Crosshairs

Prompt `prompts/typed_trigger_crosshairs_2026-08-24.md`. Crosshairs `NEAR_TRIM`/`NEAR_ADD` previously evaluated every position's Trim/Add distance as a dollar price, even when the thesis's declared `trigger_type` was `fwd_pe`/`trailing_pe`/`price_to_book`/`discount_from_high` — those bands were computed (`utils/thesis_reader.resolve_band_levels`) and carried in the bundle (`get_ticker_triggers`) but dropped at `build_valuation_card.py`'s Sheet write, which only ever emitted the price-denominated fallback.

### Changed
- `build_valuation_card.py`: new `Trigger Type` column; `Trim Target`/`Add Target` now hold the declared-type numeric level (a P/E, a P/B, a discount %, or a price), not always the price fallback; `ceiling_only` → blank. Number format switched from CURRENCY to plain NUMBER (mixed units per row).
- `build_crosshairs.py`: `_near_candidates`/`_dislocation_candidates` branch on declared `trigger_type` (`METRIC_MAP`), compare against the matching live metric column, and emit metric-aware rationale (`"fwd P/E 15.90; add 18.00; ->Add -11.7%"`). One valuation NEAR_* row per ticker — a secondary/unused band (e.g. UNH's price 290/380) no longer produces a second row, since it's never written to Trim Target/Add Target in the first place.
- `build_command_center.py` (`_build_position_table`), `build_decision_view.py`, `format_sheets_dashboard_v2.py`: renderers and CF made type-aware so a non-price row isn't shown/formatted as a dollar figure. `format_sheets_dashboard_v2.py`'s "price trigger action zones" CF rule gated on `Trigger Type == "price"` — it was comparing raw share price against Trim/Add directly and would have misfired on every non-price row.
- **Found during implementation, not in the original audit:** `utils/sheet_readers.read_gsheet_robust()`'s `text_indicators` allowlist didn't know about the new `Trigger Type` column, so `coerce_sheet_numeric_series` zeroed it on every read (the Sheet cell itself was written correctly — only the read-back was broken). Added `'trigger'` to the allowlist. Masked in Crosshairs by an existing `level_coverage` fallback, but silently broke the Command Center position table (no such fallback) until the earlier `--live` write was re-run after this fix.
- **`discount_from_high` unit correction:** the live "Discount from 52w High %" reading round-trips through the Sheet as a fraction (PERCENT format), while thesis-stored `trim_below_discount_pct`/`add_above_discount_pct` are plain percentage points (IBM: 2.0/11.9) — scaled ×100 before comparison, or IBM/WSM (the two live `discount_from_high` tickers) would never have compared correctly.

### Verified (live data, 2026-08-24)
Dry-run harness + real `python tasks/build_crosshairs.py` against live Sheet data: META (fwd P/E 15.90, add 18) → `NEAR_ADD`, through level. VRT (fwd P/E 27.70, add 28) → `NEAR_ADD`. AAPL (trailing 35.90, trim 36.06) → `NEAR_TRIM`. UNH → exactly one row (`NEAR_TRIM`, fwd-P/E rationale, no `$290`/`$380`). GILD/XOM (price type) unchanged. Zero `ceiling_only` tickers appeared as `NEAR_*`. `--live` applied to Valuation_Card, 0_DASHBOARD, Decision_View; spot-checked round-trip on 9 tickers across all 6 trigger types.

## [2026-08-21] — PortfolioStore Phase 2 read flip

Prompt `store_migration_sqlite_2026-08-20.md` **2.4.0** (archives v2.3.0).

### Decisions
- **`STORE_PRIMARY=sqlite`** hand-flipped in `.env` (dual-write still on). Revert: `STORE_PRIMARY=sheets`.
- Market `bundle_hash` remains Schwab-sourced; ledger / composite Tier-2 `Trade_Log` honor `get_store()`.

### Added / changed
- `docs/sheets_hand_edit_inventory.md` — no blocked store-backed surfaces.
- `core/composite_bundle.py` reads Trade_Log via `get_store()` (closes Sheets-vs-SQLite dual-state gap).

### Verified
- `--require-streak` green before flip; post-flip `store status` reader=`SqlitePortfolioStore`; `store verify` + `bundle-parity` PASS/MATCH.

## [2026-08-20] — PortfolioStore v2.3 Phase 1 closeout

Prompt `store_migration_sqlite_2026-08-20.md` **2.3.0** (archives v2.2.0). No `STORE_PRIMARY` flip.

### Fixed / clarified
- **Backup:** advisory `.backup.lock` + soft-skip on contention; dry-run reports `pruned` metadata.
- **Docstring:** `thesis_sync_data._store_frames` honors `STORE_PRIMARY` only (removed “when populated”).
- **Parity wording:** Phase 1 `bundle-parity` is ledger fingerprint, not full market `ContextBundle`.

### Verified (raw stdout in prompt)
- `store verify` PASS; `bundle-parity` MATCH; `--require-streak` exit 1 (4/5); backup dry+live+lock skip.

## [2026-08-20] — Audit follow-up: Chase term, merge guard, Tax_Control cache

Fixes from scoped code review of PortfolioStore / Realized_GL / store CLI batch.

### Fixed
- **Chase `term`:** `parse_chase_realized_gl` derives Short/Long Term from `holding_days` (`>365` → LT), not from which ST/LT dollar column is larger near breakeven.
- **`--merge` completeness:** refuses when the import file has fewer lots for an account than the sheet unless `--force-partial-merge`.
- **Tax_Control fetch:** `SheetsPortfolioStore` caches one parse per instance for lots + metrics (verify / bundle-parity).
- Removed inert `pm store verify --rel-tol` and dead `if acct_type: pass` in Chase parser.

## [2026-08-20] — Audit-aligned repairs (Schwab fail-closed, podcast atomic write, valuation drift, store parity)

Driven by `agent_outputs/audit/repo_audit_2026-08-20.md` + re-authored prompts v1.1.0.

### Decisions
- **Chase / RE funding account out of scope** — dropped uncommitted `TAX_CONTROL_EXTRA_ACCOUNT_SUFFIXES` / `8895` widening; Tax_Control = primary Schwab suffixes only.
- **JPIE realized swing immaterial** vs overall gains — not a SQLite seed blocker.

### Fixed
- **Schwab:** empty `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES` fails closed unless `SCHWAB_FORCE_UNSCOPED=1`; docstrings match allowlist behavior.
- **Podcast:** `weekly_podcast_sync` archives then single `update` — no `batch_clear` before write (prevents empty-tab data loss).
- **Publish/UI:** Decision header via `get_store().get_decision_header()` (no STORE_PRIMARY bypass).

### Added
- **Valuation drift agent** (`pm agent valuation-drift`): Option A baselines; FMP fields in market bundle `fundamentals` (schema **1.1.0** — intentional `bundle_hash` lineage break).
- **`pm store bundle-parity`**: Sheets vs SQLite ledger fingerprint using bundle canonical SHA; streak requires ≥1 parity ok.

## [2026-08-20] — PortfolioStore v2.2 (tax reconcile + ledger hash + run streak)

Closes three gaps left in v2.1. Prompt: `prompts/store_migration_sqlite_2026-08-20.md` **v2.2.0** (v2.1.0 archived).

### Corrected / added
- **`tax_control` in verify** — Sheets multi-zone parse; KPI money metrics + lots sums to the cent (not txn/realized only).
- **Ledger hash parity** — `core/store/ledger_hash.py`; `pm store verify` requires Sheets vs SQLite canonical fingerprint match (bundle SHA discipline; money normalized to cents). Phase 1 acceptance during dual-write.
- **Streak = consecutive verify runs** (default N=5), not calendar days; weekends with no run neither advance nor break; non-vacuous via `realized_row_count > 0` in window.
- Phase 2 prep note: inventory hand-edited tabs before `STORE_PRIMARY` flip.

## [2026-08-20] — PortfolioStore v2.1 (gate hardening)

Hardens soft gates left in v2.0. Prompt: `prompts/store_migration_sqlite_2026-08-20.md` **v2.1.0**. Archives: `prompts/archive/store_migration_sqlite_2026-08-20_v1.0.0.md`, `…_v2.0.0.md`.

### Corrected
- **Step 0** is executor-run with paste-stdout boxes (not author `[x]`).
- **Value-level verify** to the cent (proceeds, cost, G/L, ST/LT, disallowed) — count-only is insufficient.
- **`STORE_PRIMARY`** explicit hand flip (default `sheets`); no auto-flip on SQLite row presence. Revert: `set STORE_PRIMARY=sheets`.
- **Streak gate restored:** `STORE_VERIFY_STREAK_N` (default 5) consecutive calendar days + ≥1 Realized_GL Closed Date in window; `pm store verify --require-streak`.
- **Backup retention:** keep-N-daily / keep-N-weekly prune after live VACUUM (local + Drive).

## [2026-08-20] — PortfolioStore v2 (tax ledger first + Drive monitoring)

Course correction on the same-day v1 pass. Prompt archived as v2.0.0 under `prompts/archive/`.

### Corrected
- **Phase 1 spine** is `transactions` + `realized_gl` + `tax_control` (not `positions_current` — that is a morning cache).
- **Backup in Phase 1:** `pm store backup --live` → `VACUUM INTO` + `.sha256` + copy to `G:\My Drive\Portfolio_Analysis\db_backups\`.
- **No Alembic in Phase 1** (removed from requirements); rebuild from Sheets/Schwab is free during dual-write.
- **Phase 3 = monitoring:** `pm store publish-cockpit --live [--publish]` writes static HTML to `agent_outputs/command_center/` and mirrors via existing Drive publish globs. Local `pm ui serve` is debug-only (phone access is the requirement).
- **Thesis numeric dual-truth** stays in Phase 2 (vault sync via PortfolioStore) — not optional Phase 4.

### Added (retained from v1)
- `core/store/` Protocol + Sheets/SQLite/Dual; `pm store status|verify|sync-from-sheets|backup|publish-cockpit`
- Live shadow on tax refresh, txn sync, realized-gl ingest, decision view, rotation review
- `config.TAB_VALUATION_CARD` / `TAB_DECISION_VIEW`

## [Unreleased]

- **Thesis housekeeping 2026-08-14 (Bill-confirmed, no inferred theses):** AAPL Scaling State `accumulate` → `trim` (08-10 −14sh is the first trim leg). VST Scaling State `[BILL — confirm]` → `hold` (over-ceiling size accepted; Aug 3 adds stand). GLD: named governing rule as size-and-role (build toward 3–5%; do not trim on price up alone) over the 400 print. ES thesis archived to `vault/theses/archive/` (exited; KRE precedent).

## [2026-08-13] — Idea generator source clustering + Spotify aggregates

Driven by `prompts/idea_generator_source_clustering_2026-08-13.md` v1.1.0. The 2026-08-13 ideas report emitted five near-identical candidates (BLK/BN/BX/GS/KKR) from one On The Tape episode's $500B Nvidia financing consortium, never read Spotify aggregate digests, and listed non-held tickers (XLE) as `Overlaps with`.

### Changed
- `utils/agents/idea_generator.py` — `Candidate.related_tickers`; `load_spotify_aggregates()` via non-recursive `glob()` and `export_ai_briefing.parse_summary_date()` (filename-date window, sidecar chain by digest basename, SHA match); Python-side episode/aggregate overlap; labeled `SPOTIFY AGGREGATE` / `VERIFICATION SIDECAR` / `EPISODE/AGGREGATE OVERLAP` blocks. After the LLM returns, `sanitize_candidate_overlaps()` unions held `related_tickers` into `current_holdings_overlap` (keeps clustered names in `_sort_key()` group 2) and drops any overlap ticker that is not a current position (INFO log). CLI flags unchanged (`--since-days`, `--bundle-path`, `--dry-run`, `--skip-ingest`).
- `prompts/idea_generator.md` — clustering rule (one candidate per shared thesis; primary = source emphasis, **not** un-held preference); sidecar CONTRADICTED/OVERSTATED handling via `notable_concerns`; transcript-primary when a cited episode is also in the batch; `current_holdings_overlap` is held tickers only, never a sector proxy.
- `write_idea_report()` renders `related_tickers` under Overlaps with.
- `CLAUDE.md` — delta-sidecar rule under Podcast ingestion (one chain per `source_sha256`; do not re-verify an unchanged digest from scratch).
- Archived `…_VERIFIED_2026-08-11.md` (08-10 digest addendum) to `data/podcast_summaries/verification/archive/`; kept the C1–C15 ledger as canonical `_VERIFIED_2026-08-10.md`. Digest `VERIFICATION: PENDING (manual)` footers untouched.

## [2026-08-11] — Vault sync YAML hardening

Driven by `prompts/vault_sync_yaml_hardening_2026-08-11.md`. Morning STEP 6 aborted when `NOW_thesis.md` had duplicate frontmatter `triggers:` keys (empty `{}` plus `ceiling_only`); strict ruamel raised and `gather_thesis_sync_data` had no per-ticker catch, so **zero** theses synced that run.

### Fixed
- **`ThesisManager.get_frontmatter_safe()`** (`utils/thesis_utils.py`) — returns `(data, error)` so callers can distinguish absent vs broken YAML. `get_frontmatter()` wraps it and returns `None` on either miss or parse failure.
- **`gather_thesis_sync_data`** (`core/thesis_sync_data.py`) — returns `ThesisSyncGatherResult(payloads, parse_errors)`. Unparseable frontmatter omits that ticker from payloads (skip write) and continues; does not abort the whole vault.
- **Morning STEP 6 / `vault sync` / `vault sync-status`** — print parse errors; STEP 6 marks `warn` when any parse or write errors remain; later morning steps still run. Does **not** raise `logs/HEALTH_FAILURE.flag` (that sentinel stays Schwab/auth-centric).
- **`lint_theses.py` check 6** — frontmatter must parse under the same ruamel path as vault sync (`UNPARSEABLE FRONTMATTER`). Report-only, exit 0.

### Notes
- Reader (`thesis_reader` / PyYAML + flat fallback) vs writer (`ThesisManager` / strict ruamel) still disagree on malformed frontmatter; this pass hardens the write path only. Unification deferred.
- NOW frontmatter repaired same day (single `triggers: { trigger_type: ceiling_only }`) before this hardening landed.

## [2026-08-08] — Promote rotation backlog + harden Status

Driven by `prompts/promote_backlog_and_harden_status_2026-08-08.md`. Bill signed off option 2 (3 clean rows + Aug 3 widest).

### Changed
- `Trade_Log` 1→5 rows (promoted EMXC→BBJP, NOW+IGV→APO/KRE/MELI/LLY, IGV/VEU/JEPI→IBM, Aug 3 basket). Staging statuses: 4 `promoted` (with `Promoted_At`), 9 `superseded`, 111 `needs_rationale`. Backup at `agent_outputs/trade_log_staging/backup_*.csv`.
- `journal promote` accepts `approve`/`approved`; writes `Promoted_At` UTC; warns on `promoted` + blank timestamp without auto-correct.
- `config.TRADE_LOG_STAGING_COLUMNS` adds `Promoted_At`.
- Attribution track-record summary (median Residual / Vs_Index / Sell_Vs_Index; VTI↔QQQ sign-flip count) in `agent_outputs/rotation_attribution/`.
- Position MV: `coerce_sheet_numeric_series` shared helper; `column_guard.ensure_display_columns` and valuation card use it (pandas 3.0 string-dtype gap was zeroing `$` cells).

## [2026-08-08] — Basket-aware rotation attribution

Driven by `prompts/build_basket_attribution_2026-08-08.md`.

### Changed
- `tasks/compute_rotation_attribution.py` — basket is the unit of analysis: dollar weights from `Transactions`, both-sides netting, weighted returns, SPY/VTI/QQQ benchmarks, beta decomposition vs SPY with `Residual_Pair_Nd` as headline, nested/superseded detection, local markdown under `agent_outputs/rotation_attribution/`, archive-before-overwrite on `--live`. New `--from-staging` read-only backfill path (never writes Sheets).
- `config.ROTATION_REVIEW_COLUMNS` — appended Status, Both_Sides_Tickers, Coverage_Pct, betas, Residual/Beta_Explained/Vs_Index/Sell_Vs_Index, Bench_SPY/VTI/QQQ/Spread, Bench_QQQ_Note. Existing column order preserved.

### Notes
- JEPI/JPIE-funded baskets: equity beta understates risk-managed income given up — flagged in output; not "fixed" in the beta math.
- Returns use yfinance `auto_adjust=True` (dividend-adjusted total return).

## [2026-08-08] — Dashboard-zeroing pandas 3.0 dtype bug

Bill reported `0_DASHBOARD` not populating: tickers, Fwd P/E and PEG rendered, but MV, Price, Wt%, Day% and UGL were all `$0`/`0.0%` for every position despite `Holdings_Current` holding correct, fresh data.

### Fixed
- **`utils/sheet_readers.py`'s `read_gsheet_robust()` — the shared Sheets-reading function used by `manager.py`, `build_command_center.py` and `build_tax_control.py` — silently stopped stripping `$`/`%`/`,` from numeric cells.** The gate `if df[col].dtype == object:` relied on pandas inferring plain-string columns as legacy `object` dtype; the `.venv`'s installed **pandas 3.0.5** infers a dedicated string dtype instead, so the check no longer matched, the strip block never ran, and every currency/percent cell fell straight into `pd.to_numeric(...).fillna(0.0)` — silently zeroing. Fixed by widening the check to `pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col])`, which is correct on both old and new pandas. Verified live against the Sheet before and after (Market Value column: all `0.0` → real values), then rebuilt `0_DASHBOARD` with `manager.py refresh dashboard --live` and confirmed the written tab shows real numbers (Total Value $591,549, per-position MV/Price/Trim/Add all correct).

### Found, not fixed (flagged only)
- **`build_valuation_card.py`'s "Position MV" column has its own, separate, likely long-standing bug** — it calls `pd.to_numeric()` directly on the raw `"$X,XXX.XX"`-formatted `Holdings_Current` string with no stripping at all (doesn't go through `read_gsheet_robust()`), so it has probably always read as 0 regardless of the pandas-version issue above. Low impact — it only affects that one preview table's sort order, not any Fwd P/E/PEG/valuation-signal data or anything downstream. Left alone; worth a follow-up fix.

## [2026-08-07] — Repo consolidation + thesis repair pass

Driven by `prompts/consolidate_and_thesis_repair_2026-08-07.md`. Full detail in `state.md` Recent Decisions Log.

### Fixed
- `data/spotify_digests/.ingested.json` `output_path` values repointed from the retired `C:\Users\WLong\Investment_Portfolio` tree to `C:\Dev\Investment_Portfolio` (sha256 keys/`ingested_at` preserved).
- STEP 4b Spotify digest ingestion had missed 4 days (08-04 through 08-07) because `morning_auto.bat`'s `DailyWake` scheduled task has never successfully fired, not because of a filter bug — live-ingested all 4 after confirming the dry run was clean.
- `VRT_thesis.md`, `ET_thesis.md`, `ES_thesis.md` — stale weights/sleeve-math corrected, domestic AI/data-center gas demand and ISO-NE input-cost risk notes added; `.bak` backfilled for all three.
- `KRE_thesis.md` archived (position exited between the 2026-08-03 and 2026-08-07 syncs, not previously recorded).

### Added
- `vault/theses/PWR_thesis.md` rewritten as a sourced fact-assembly interview scaffold (no thesis prose) — entry tranches, valuation snapshot, style question, sleeve/overlap context, and a cited Research Inputs section on the electrician-shortage podcast segment.
- `data/podcast_summaries/verification/allocation-2026-08-07_VERIFIED_2026-08-07.md` `source_sha256` filled in from the now-ingested digest, independently re-verified.

## [2026-08-03] — Schwab multi-account scope fix

Driven by `prompts/schwab_account_scope_fix_2026-08-03.md`, following an item-1 investigation the same day into why the 2026-08-02 composite bundle reported `total_value: $897,748.49` (vs. the Sheet's known ~$591-596K) with JEPI/JPIE weights ~3.5x too high while `Trade_Log` showed net *selling* in both.

### Fixed
- **`fetch_positions()`/`fetch_transactions()`/`fetch_tax_lots()` aggregated every Schwab account the API token could see, with zero account-level filtering anywhere in the codebase.** A live, read-only `get_accounts()` enumeration found **six** linked accounts, not the three the repo's CSV exports implied, with heavily overlapping holdings (JEPI in 5 of 6). Added `config.SCHWAB_PRIMARY_ACCOUNT_SUFFIXES` (a list, not a single value — the ~$591-596K primary portfolio is the *sum* of three accounts, masked `...6499`/`...8767`/`...5119`, confirmed by Bill against live evidence) and a shared `_is_primary_account()` check in all three fetch functions. Empty list preserves old (unscoped) behavior with a one-time warning logged.
- **Tax-treatment classifier only recognized `ROTH`/`IRA` substrings in the account `type` field**, silently tagging everything else — including any 401(k)/QRP account — as `'taxable'`, which is why the pre-existing cross-account `'mixed'`-tax-treatment safety net never caught this. New shared `_classify_tax_treatment()` (replacing two independent copies of the same logic in `fetch_positions()` and `fetch_tax_lots()`) also recognizes `401`/`QRP`, mapped to `'tax_deferred'` (same bucket as IRA, confirmed with Bill). **Finding, not just a fix**: none of the six real linked accounts' `type` field contains `IRA`/`ROTH`/`401`/`QRP` at all — they're `CASH` or `MARGIN` (a settlement-type field, not tax-treatment) — so this fix closes a real code gap but has nothing to match against in the accounts currently linked.
- **`style_size_ceiling_pct` thesis-file overrides were silently ignored on both the read and write side.** `build_ceiling_check()` (`tasks/export_ai_briefing.py`) always used the `styles.json` style default; `gather_thesis_sync_data()` (`core/thesis_sync_data.py`) did too, which meant `write_thesis_updates.py` would overwrite a manually-set override (e.g. META's `4.0`, deliberately below the GARP default of `9.0`) back to the default on every sync cycle — destructive, not cosmetic. Both now check the thesis file's own frontmatter override (nested under `triggers:`) first via a new `build_ceiling_overrides()` reader.

### Verified
- **A first guess at the primary account was tested live and found wrong before shipping.** The repo's CSV filename (`Individual_XXX119`) suggested a single-account identifier; testing it live returned $388,785.88/34 positions, missing 4 real tickers (XLF/ET/KRE/NOW) entirely — a *different* wrong number, not a fix. It matched one real account (`...5119`) that turned out to be only one of the three making up the true scope.
- **Live end-to-end verification** (dry-run `manager.py snapshot --source auto`, no Sheet writes) with the confirmed 3-account default active: `total_value: $595,527.33`, 38 positions — inside the known-correct range. JEPI 815 sh / JPIE 335 sh (down from the pre-contamination 881/460, consistent with real net selling since), not the contaminated 5131/1460.
- Style-ceiling override fix verified against the real `META_thesis.md`: resolves to `4.0` on both the sync-payload path and a live `build_ceiling_check()` render (5.79% weight → 1.79% drift against the 4.0 ceiling, matching the previously-reported-wrong 6.79%-against-9.0 case exactly).
- Full test suite: 58 passed, 0 failures (the one pre-existing unrelated failure from the prior session's run is gone — appears to have been a transient token issue, not a regression).
- Confirmed no Sheet-write path touched: all changes are in `utils/schwab_client.py` (read-only per its own hard-rule docstring), `core/thesis_sync_data.py` (gathers data only; the actual Sheet write lives in the untouched `write_thesis_updates.py`), `tasks/export_ai_briefing.py` (local-file-only exporter), and `config.py`.
- **Known residual, out of scope for this fix**: whether any `sync_transactions.py --live` run happened 2026-08-02 or later (after the account scope apparently expanded) pulled non-primary-account transactions into `Transactions`/`Trade_Log` needs a manual Sheet version-history check — not attempted here per the prompt's explicit instruction not to touch those tabs.

## [2026-08-02] — High-signal moment extraction v2 fix (fragment context, portfolio-hook filter, cue recall)

Driven by `prompts/moment_extraction_v2_fix_2026-08-02.md`, same day as the v1 build below. v1's 66-transcript verification sample yielded 19 moments (79% of transcripts zero) with fragments too short to be usable (`"And we bought it in January"` — bought *what*?). A mandatory Step 0 diagnostic (free, no Gemini calls) measured the actual bottleneck before touching anything: 0.41 windows/transcript, 50/66 zero, ~70% Gemini acceptance of what it *was* given — the loss was almost entirely at windowing (recall), not the judge (precision).

### Added
- **`context: str` on `MomentCandidate`** — 400-800 chars Python-sliced from the source transcript, centered on the fragment's real position, sentence/turn-boundary-snapped where cheap. Gemini's own response schema (`GeminiMomentResponse`) has no `context` field, so it cannot generate one even in principle. `fragment in context` is validated as a stronger version of the old verbatim check.
- **Cache schema bumped to `{"schema_version": 2, "moments": [...]}`** (was a bare list). `extract_moments.py` detects a missing/old version as stale and re-extracts; verified all 66 v1 files correctly flagged stale, 0 false negatives.
- **`scripts/generate_ticker_aliases.py`** — regenerates `data/ticker_aliases.json` from the public S&P 500 constituents dataset (a long-standing GitHub-hosted CSV, not a new paid vendor; FMP's own `/stable/sp500-constituent` returned a live 402, gated above the current subscription tier) plus a ~25-entry hand-curated ADR supplement. 37 → 547 tickers. Merges into, never overwrites, existing hand-curated multi-alias entries. A `COMMON_WORD_BLOCKLIST` prevents suffix-stripping from producing single-word aliases that collide with ordinary English words (`Target Corporation` → keeps the full name, does not add bare `Target`).
- **No-portfolio-hook filter** (`passes_portfolio_hook_filter()`, read-time only, needs the live position set) drops a candidate entirely — not even `ZERO_EXPOSURE` — when it has no ticker, no held-name mention in its own context, and (for a ticker-less `reversal`) no macro term from a new `data/moment_cues.json` `macro_terms` list nearby. Kills false positives like a private hotel-investing anecdote or philosophical AI musing with zero relationship to the book.
- **`only=[...]` param on `run_extract_moments()`** — re-extracts an explicit, named list of transcripts, bypassing the corpus scan entirely. The safe way to re-extract a hand-picked sample without any risk of it falling through into the full corpus.
- **Fix 0c instrumentation**: `extract_moments_for_transcript()` returns `(candidates, stats)` with `windows_found`/`windows_sent`/`candidates_returned`/`dropped_by_reason` (model_failed / empty_fragment / verbatim_fail); aggregated per run and persisted to `logs/moment_extraction_runs.jsonl`, so each fix's effect stays separately attributable.

### Fixed
- **The ticker-proximity gate structurally prevented zero-exposure discovery** — v1's 37-ticker-only alias list meant `specific_claim` could only ever fire next to a name Bill already owned, the exact opposite of this build's purpose. Fixed via the 547-ticker alias regeneration above plus relaxing `specific_claim`'s proximity from 120 chars to 1200 (the full window) — spoken podcasts use company names, never ticker symbols, so a tight radius actively worked against recall. A capitalized-proper-noun fallback heuristic proposed in the fix spec was evaluated and **not implemented**: this transcript corpus is 100% lowercase auto-captions with no capitalization signal at all (established in the v1 build), so it cannot fire on real data here regardless of implementation quality.
- **Five cue patterns had zero hits across the full 147-transcript corpus** (written-English phrasings like `"I was wrong about"`, `"nobody is talking about"`) — kept (cost nothing, may hit a future transcript) and supplemented with spoken variants (`"turns out I was wrong"`, `"we got out of"`, `"what people are missing"`, etc.) in `data/moment_cues.json`.
- **Real bug caught by this fix's own live verification, not unit tests**: `passes_portfolio_hook_filter()` force-included the bare ticker symbol in its alias check for every held ticker, silently reintroducing the exact SNOW/GILD/ES/ET/NOW/META collision class `ticker_aliases.json` exists to prevent. The Myrtle Beach hotel record — the checklist's own named regression test for this filter — initially *survived* because "at least **now** we are one of the largest owners..." false-matched ticker `NOW`. The same latent bug (present since v1, just never exercised this obviously) was also fixed in `_mentioned_in_other_thesis()`, the ADJACENT-via-thesis-mention helper. Both now trust `ticker_aliases.json` alone for what's safe to bare-match.
- **Speaker-field claim corrected, not fixed** — the fix prompt claimed "every cached record carries `speaker: unknown`." Audited: false as a generalization. It correctly carries a real `>>` turn index (`turn_81`) for the one `disagreement`-type moment in the sample, which is the only category ever designed to carry positional speaker info; the other four categories correctly show `unknown` since no `>>`-proximity signal was ever computed for them. No code change.

### Verified
- Live 10-transcript re-extraction sample (hand-picked from the 66 already-cached via the new `only=` param, so it can never fall through into the untouched 81): 31 windows → 25 candidates, yield **2.5 moments/transcript** (up from v1's 0.29 baseline — roughly 8.6x). `dropped_by_reason`: 1 model_failed, 2 empty_fragment, 3 verbatim_fail (including a real ellipsis-paraphrase catch, same guard class as the v1 drop).
- **Zero-exposure discovery proven possible with multiple real examples in one run** — structurally impossible under v1: `WMT` (Walmart), `FND` (Floor & Decor), `IBIT`/`MSTR`, `FIS`/`MFC`/`PAYX` all surfaced as genuine non-held-name moments.
- Myrtle Beach hotel record confirmed dropped by the no-hook filter after the bare-ticker-collision fix (both hotel-transcript moments verified: the named position_disclosure record and a reversal record with no macro term nearby, both correctly excluded).
- `context` Python-slicing confirmed via code inspection: `GeminiMomentResponse` (the actual Gemini call schema) has no `context` field, so the model literally cannot populate it; the code path constructing `MomentCandidate.context` runs entirely after the Gemini call returns, over the raw transcript string.
- `schema_version` staleness detection re-verified after the cache-format change: all 66 v1 files stale, 0 current, before the sample re-extraction; correctly current after.
- Full test suite: 57 passed (1 pre-existing, unrelated failure — an expired Schwab refresh token — confirmed present before this session's changes).
- Export path re-confirmed zero network calls, no `--moments` flag added or considered.

## [2026-08-02] — High-signal moment extraction

Driven by `prompts/moment_extraction_2026-08-02.md`. `podcast_analyst.PodcastStrategy` answers "what is the macro allocation view" — a summarization objective that systematically discards the thing that actually generates ideas: a specific, falsifiable, non-consensus claim made by one person at one moment. This adds a second, parallel extraction pass scored only against "does this change what Bill holds, or what he'd consider holding," without touching `PodcastStrategy`, `analyze_podcast()`, or the STEP 4 subprocess path.

### Added
- **`utils/moment_windows.py`** — pure-Python cue-phrase windowing, no LLM, no network. `find_windows(transcript, cues, radius=1200)` matches five cue categories (`reversal`, `non_consensus`, `position_disclosure`, `specific_claim`, `disagreement`) from `data/moment_cues.json` (tunable without a code change), merges overlapping hits into non-overlapping windows, and truncates to the 40 highest-density windows per transcript with a logged warning if the cue list is too loose. `specific_claim` requires a ticker/company-name proximity hit against `data/ticker_aliases.json` (built for the 37 held tickers; deliberately omits the bare ticker for `SNOW`/`GILD`/`ES`/`ET`/`NOW`/`META` since those collide with ordinary English words) — never a naive `[A-Z]{2,5}` regex, which would match `CEO`/`GDP`/`AI`/`ETF`/`CPI`/`IPO`. `disagreement` requires proximity to a `>>` speaker-change marker and sets `speaker` to a positional `turn_N` index, never a guessed name — the transcript corpus has no speaker identities. 10 unit tests in `tests/test_moment_windows.py`.
- **`utils/agents/moment_extractor.py`** — `MomentCandidate` Pydantic schema (parallel to `PodcastStrategy`, not replacing it) plus the extraction/relevance-resolution logic. Verbatim validation is the core guard: `fragment` must be a literal substring of the window text or the candidate is dropped (confirmed live — Gemini returned an ellipsis-compressed paraphrase for one real window and it was correctly rejected). Relevance (`HELD → THESIS_ON_FILE → ADJACENT → ZERO_EXPOSURE`) is resolved in Python, never trusted from the model, and is deliberately **not** computed during extraction — see the architecture note below.
- **`tasks/extract_moments.py`** + `python manager.py extract-moments [--force NAME] [--limit N]`, wired as STEP 4c of `pm morning` (after podcast sync, before the dashboard/composite/export steps), non-fatal per transcript. Idempotent: skips any transcript with an existing `data/moments/{stem}.moments.json`.
- **`## High-Signal Moments` block in `podcasts.md`**, via a new `build_moments_md()` called from `build_podcasts_md()` in `tasks/export_ai_briefing.py`. Two distinct static rank orders (not one ranker with conditionals): `position_disclosure` sorts first in `### Zero-Exposure Ideas` (a manager's own-money conviction stake in a name Bill doesn't hold is the highest-value signal in the set) and last in the main `### Portfolio-Relevant Moments` section (the same disclosure about a held name is confirmation fodder). Capped at 8/day, round-robin allocated between the two subsections so the cap can't silently bury the zero-exposure section this build exists to populate. The block prints its own zero-exposure share and Python-vs-Gemini relevance disagreement rate — reported, not silently auto-tuned, with a warning line if the zero-exposure share drops under 20%.

### Architecture decision — extraction/relevance split (mid-build revision)
The prompt was revised mid-build (twice) after Step 0 verification surfaced problems with the original design:
- **Extraction is cached and position-independent; relevance is computed fresh at read time and never persisted.** Transcripts are immutable once written, so re-running Gemini on the same window at every `export_ai_briefing.py` invocation was repeated, nondeterministic work with no new input — `podcasts.md` would stop being diffable for unchanged inputs, and a 7-day window (~10-20 transcripts x up to 40 windows) meant several hundred Gemini calls per daily export. Splitting extraction (`tasks/extract_moments.py`, cached to `data/moments/*.json`, position-independent) from relevance tagging (computed in `build_moments_md()` from the live position/thesis set, never cached) means `export_ai_briefing.py` makes **zero network calls**, its documented invariant, with no opt-in flag weakening that guarantee. Gemini's own relevance guess is kept in the cache under `gemini_relevance_guess` (never the key `relevance`) purely as an audit trail for the disagreement-rate metric.
- **ADJACENT drops the originally-planned GICS-sector leg, not for a data-availability reason.** Sector is empty on every position in the bundle and cached for only 2 of 38 tickers via FMP — but the deeper problem is that 38 positions span nearly every GICS sector, so a *working* sector match would resolve almost every mentioned ticker to `ADJACENT` and empty the `ZERO_EXPOSURE` bucket, defeating the point of the build. Rejected outright and documented as such in `moment_extractor.py` — do not re-add once the FMP-sector-bundle gap (tracked separately, see Watchlist) eventually closes. ADJACENT resolves via ETF look-through (`utils/etf_holdings.py`, cache-only) plus a new leg: ticker/company name mentioned in the body text of some *other* thesis file (verified live: `TSM` → `ADJACENT` via `TSMC` named in `EMXC_thesis.md`).

### Verified
- Free (no-LLM) `find_windows()` scan of the full 147-transcript corpus: median 0 windows/transcript, max 6, no transcript exceeded the 40-window guardrail. 34/147 transcripts produced at least one window; all five cue categories fired at least once on real data (position_disclosure 23, specific_claim 15, reversal 10, non_consensus 6, disagreement 1).
- Bounded live Gemini run against a hand-picked sample covering all five categories produced real validated `MomentCandidate`s in every category, two genuine empty-fragment false-positive drops, and one genuine non-verbatim (paraphrased) drop — not synthetic examples. Relevance spot-check: 4/7 agreed with Gemini's guess, 3/7 disagreed (43%), all three disagreements correctly resolved by the Python lookup (e.g. a `tickers_touched: []` moment Gemini guessed `HELD`, correctly resolved to `ZERO_EXPOSURE`).
- Two bugs found only because of this live verification, not present in unit tests: `max_tokens=1000` on the per-window Gemini call was too small for gemini-2.5-pro's schema overhead and silently truncated several real responses mid-JSON (raised to 2000, re-verified); `--limit` in `extract_moments.py` counted only successes toward its cap, so a run of real failures would blow through the throttle and attempt the entire remaining corpus rather than stopping at N (fixed to count total attempts, re-verified with a simulated-failure test).
- Idempotency confirmed safely (`limit=0`, guaranteeing zero new Gemini calls): 65 already-cached transcripts correctly skipped, 0 processed, cache files byte-identical before/after.
- `grep`-confirmed zero `"relevance"` keys across all 66 cache files written; `gemini_relevance_guess` present in every candidate instead.
- `PodcastStrategy`/`analyze_podcast()`/`batch_podcast_sync.py`/`weekly_podcast_sync.py` confirmed untouched (zero diff) — this build's non-goal held by construction, not by re-running and diffing output.
- **Known incomplete**: an operator error mid-verification (a re-run intended to test idempotency on 5 files instead invoked the default full-corpus scan) left 66/147 transcripts genuinely backfilled before being caught and stopped — 19 real moments cached, no corrupted files, confirmed idempotent on the already-done 66. The remaining ~81 are intentionally left for a deliberate throttled run (`python manager.py extract-moments --limit N`), not run automatically to avoid further unplanned Gemini spend. `TICKER: SKHY` — the spec's literal example for "relevance recomputes on position change" — does not appear anywhere in the current 147-transcript corpus, so that mechanism was instead demonstrated against real cached data with a hypothetically modified position set (`NRG`: `ZERO_EXPOSURE` before a hypothetical open, `HELD` after), not a real SKHY transcript mention.

## [2026-08-01] — Spotify Studio digest ingestion (STEP 4b)

Driven by `prompts/spotify_digest_ingestion_2026-08-01.md`. Automates the manual-ingest workaround logged 2026-07-26: the daily "Allocation" digest written by Studio by Spotify Labs (`allocation-YYYY-MM-DD.txt`, already-synthesized third-party prose, not a transcript) had been hand-dropped into `data/podcast_summaries/` for the four prior editions.

### Added
- **`tasks/ingest_spotify_digests.py`** — `main(days, live)` glob-matches `allocation-YYYY-MM-DD.txt` in `config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR`, dedups by sha256 against `data/spotify_digests/.ingested.json`, skips sub-`SPOTIFY_DIGEST_MIN_WORDS` (400) files as truncated, and writes `data/podcast_summaries/<date>_Spotify_Podcast_Aggregate_<Slug>.md`. Executive Summary is the source prose itself (lightly reflowed), never a Gemini re-summary — decomposing or re-summarizing the aggregate was rejected by the 2026-07-26 decision. Gemini's only job (new `is_aggregate` branch in `utils/agents/podcast_analyst.py`) is the Sector Allocations table plus two new optional `PodcastStrategy` fields: `suggested_title` and `cited_sources` (shows/guests the digest names, written to a `## Cited Episodes` section). A literal `VERIFICATION: PENDING (manual)` placeholder is always written — never a fabricated verification block — since the real fact-checking value sits in a manual pass, evidenced by the four hand-verified editions catching a wrong Meta capex range, an inverted Alphabet framing, and a misattributed FOMC meeting.
- **Two independent collision guards**, both required because the first live run would otherwise regenerate and overwrite the two hand-verified editions still present in the Studio folder (2026-07-31, 2026-08-01): Guard 1 is `pm podcast ingest-spotify --seed-ledger --live`, a one-time backfill that writes ledger entries (`source: manual`) for dates already matching a `data/podcast_summaries/` file, generating nothing. Guard 2 is independent of the ledger — before writing any summary, a target matching `<date>_Spotify_Podcast_Aggregate_*.md` that does **not** contain `VERIFICATION: PENDING` is treated as hand-verified and skipped with a named warning, regardless of ledger state. Verified both guards live: seeding wrote two `manual` entries and generated no files; deleting the ledger and rerunning still skipped both hand-verified files via Guard 2 alone; a synthetic `VERIFICATION: PENDING` stub *was* overwritten normally with archive-before-overwrite firing, confirming Guard 2 doesn't over-trigger.
- **STEP 4b of `pm morning`** — runs immediately after STEP 4 (Batch Podcast Sync), in-process (not subprocess, unlike STEP 4), wrapped in the same non-fatal `try/except` pattern: a Studio folder that doesn't exist on a given machine (it's a local AppData path that can disappear on a Studio update) degrades to `warn` and the pipeline continues. `python manager.py podcast ingest-spotify [--days 7] [--live] [--seed-ledger]` also runs standalone.
- **Double-count mitigation, instruction-side**: the aggregate discusses episodes independently ingested by the YouTube fetcher in the same window (verified against the 2026-07-31 edition: 5 of 5 named episodes had their own summary file already in corpus). New Hard Rule #9 in `tasks/export_ai_briefing.py`'s `PROMPT_PAYLOAD`: one source counts once regardless of length, and where an aggregate and a cited episode both appear, the episode is the primary source and the aggregate is commentary on it. Whether this holds under load against ~26 summaries of raw text volume is an open question — see `GEMINI_REVIEW_REQUEST.md` checkpoint named in the build prompt, not yet run.
- **`config.py`**: `SPOTIFY_STUDIO_TRANSCRIPTS_DIR`, `SPOTIFY_DIGEST_WINDOW_DAYS` (7), `SPOTIFY_DIGEST_MIN_WORDS` (400), `SPOTIFY_DIGEST_SOURCE_LABEL`.

### Verified
- Confirmed `PURGE_DEFAULT_DAYS_PODCASTS` (30 days) purges only `data/podcast_transcripts/` (raw YouTube), never `data/podcast_summaries/` — no purge conflict exists, nothing changed. `data/spotify_digests/` (corpus mirror + ledger) added to `.gitignore` alongside the existing `data/podcast_summaries/` entry.
- Full live/dry-run pass against the two real Studio files plus synthetic zero-byte, 100-word, and future-dated (`2026-08-02`, testing the actual current date) files: dry-run writes nothing, live run is idempotent on rerun, `parse_summary_date()`/`podcast_signal()`/`to_ascii()` all handle generated files correctly, `pm morning` (dry) completes with `Spotify Digests (0 new)` in the final step table.

## [2026-07-31] — Dislocation Scanner

Driven by `prompts/build_dislocation_scan.md`. The pipeline's inputs were all inward-facing (own holdings, own theses, podcasts) — nothing systematically scanned for the SKHY/IBM/TSM pattern (quality franchise, double-digit selloff, cheap forward multiple), so those setups only got caught by luck.

### Added
- **`tasks/dislocation_scan.py`** — deterministic daily screen, facts only (no price targets, no buy/sell language). Universe is current holdings (latest `bundles/context_bundle_*.json`, cash excluded) + `data/watchlist.json` (hand-maintained, seeded with `TSM`) + FMP `/stable/biggest-losers` filtered to market cap ≥ `config.DISLOCATION_MIN_MARKET_CAP` ($10B default). Flags a ticker only when it clears all three: drawdown ≥15% from 52w high OR 5d return ≤-10%, AND forward P/E ≤18, AND (gross margin >30% OR positive FCF) — thresholds are `config.py` constants. Style tag is read from thesis frontmatter for HELD names only; deliberately not inferred for unheld names, since there is no reliable per-ticker style map outside the vault and guessing one would fabricate a classification. Output: SHA-256-hashed `exports/dislocation_scan_{ts}.json` and a dated `agent_outputs/dislocation_scan/dislocation_scan_{date}.md`, never overwritten. No Sheet writes in v1 — `--live` is accepted but currently a no-op, reserved for future promotion to a sandbox tab.
- **`python manager.py dislocation-scan`** command, and STEP 11 of `pm morning` (after `derive_rotations`, skippable via `--skip-dislocation`).
- **`utils/fmp_client.py`**: `get_market_movers()` — thin wrapper on FMP `/stable/biggest-losers` / `/biggest-gainers`, graceful `[]` on any failure. `get_fundamentals()`'s yfinance tier gained `free_cashflow`. No new vendor.
- **`data/watchlist.json`** — Bill-maintained list of non-held tickers to screen; the scanner never writes to it.

### Verified
- First live run: 42-ticker universe, 9 flagged. SKHY correctly flagged at 18.9% drawdown / 4.5x forward P/E (~20% off high, ~4.5x forward earnings), matching the build prompt's stated backtest expectation. TSM (watchlist-only, not held) correctly scanned but not flagged — 18.8x forward P/E sits just over the 18.0 cutoff, a sensible edge case rather than a vacuous pass. `CASH_MANUAL` and other cash rows confirmed absent from output.

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
