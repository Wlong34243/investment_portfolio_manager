# Code Audit — 2026-08-09

Structured pass over the Investment Portfolio repo. Not a line-by-line read of every file; findings are code-backed (definitions vs callers, live paths vs docs).

**Passes:** Data integrity → Dead / unreachable code → Inefficiency → Aggregated here.

**Out of scope:** Style nits, vault thesis prose, `archive/` contents (except as “already archived”), bundle/data artifacts, micro-optimizations that don’t matter at current scale.

---

## Executive priority

Fix integrity before deleting dead code. Then cut morning wall-clock (Schwab overlap + format sleeps + `.info` loops). Dead modules that can *overwrite live Sheets* (especially `tasks/create_dashboard.py`) should be archived early so they cannot be run by accident.

| Priority | Item | Pass |
|---|---|---|
| 1 | Flip `derive_rotations` CLI to dry-run-by-default / `--live` | Integrity |
| 2 | Gate `journal promote` `Promoted_At` schema ensure behind `--live` | Integrity |
| 3 | Route `build_tax_control` + `pipeline.py` strippers through `coerce_sheet_numeric_series` | Integrity |
| 4 | Align Tax_Control account filter with `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES` | Integrity |
| 5 | Archive `tasks/create_dashboard.py` + `scripts/create_dashboard.py` (can clear-rebuild `0_DASHBOARD`) | Dead |
| 6 | Unify Schwab fetch for morning STEP 0–3 (positions/txns/lots once) | Inefficiency |
| 7 | Drop or throttle daily `format_sheets_dashboard_v2` 30s×6 sleeps (~3 min every live morning) | Inefficiency |
| 8 | Enrich morning bundle **or** stop Valuation_Card per-ticker `yf.Ticker.info`; share bulk Yahoo with Command Center | Inefficiency |
| 9 | Remove no-op `snapshot --enrich-atr/--enrich-technicals` flags; archive enrich tasks | Dead |
| 10 | Fix or pause auto-staging until nested supersets solved | Integrity |
| 11 | Archive Streamlit leftover utils (`formatters`, `validators`, `finnhub`, `chat_engine`, `ai_research`, `technicals`) | Dead |

---

# Part A — Data integrity

## CRITICAL

### A1. `derive_rotations` CLI writes Sheets by default
- **Evidence:** `tasks/derive_rotations.py` — `--dry-run` is `store_true` (default `False`); `write_staging(..., dry_run=args.dry_run)`. Function default is `dry_run=True`, but CLI overrides it.
- **Safe path:** Morning uses `dry_run=not live` (`manager.py`).
- **Impact:** Accidental staging pollution; worsens nested-superset problem.
- **Fix:** Require `--live` to write; default dry-run.

### A2. `journal promote` can mutate Sheets before the dry-run gate
- **Evidence:** `manager.py` — `staging_ws.update_cell(...)` adds `Promoted_At` when the column is missing, **before** `if not live:`.
- **Impact:** A dry-run alters the live staging header (cell-by-cell write).
- **Fix:** Schema ensure only under `--live`, or a separate migrate command.

---

## HIGH

### A3. Pandas ≥3 sanitizer residuals (tax + pipeline)
- **Fixed:** `utils/sheet_readers.py` `coerce_sheet_numeric_series()`; `build_valuation_card.py` Position MV uses it. (`CLAUDE.md` / `state.md` still list Position MV $0 as open — **docs stale**.)
- **Still vulnerable** (local strip gated on `dtype == object`):
  - `tasks/build_tax_control.py` `get_realized_gl_robust()` — YTD ST/LT / wash / est. tax can silently zero
  - `pipeline.py` `append_daily_snapshot` / `calculate_income_metrics` / `write_risk_metrics` — Daily_Snapshots / income / risk if fed currency-formatted strings
- **Safer local parsers:** `compute_rotation_attribution._parse_money`, `derive_rotations._clean`, `create_dashboard.compute_metrics` (per-cell strip).
- **Fix:** Route through `coerce_sheet_numeric_series()`; delete local `dtype == object` gates.

### A4. Tax “primary” ≠ Schwab 3-account portfolio scope
- **Evidence:** Positions/txns/lots gated by `_is_primary_account` + suffixes `6499,8767,5119`. Tax lots / Realized_GL use IRA/401/roth-style `Is Primary Acct` (`utils/gl_parser.py`). `build_tax_control` filters on that column; if missing, **includes all rows**.
- **Impact:** Out-of-scope taxable lots (`…4151`, `…0217`, `…9753`) can inflate Tax_Control.
- **Fix:** Tag by account suffix and filter to `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES`, or ingest scoped CSVs only.

### A5. Nested-superset staging (deriver unfixed)
- **Evidence:** Fingerprint = `sha256(date|sorted_sells|sorted_buys)[:12]`; exact-fingerprint dedup only. Evolving windows → multiple rows. Attribution marks narrower as `SUPERSEDED_BY`; deriver unchanged.
- **Impact:** Promote backlog noise; wrong basket if a narrow row is approved.
- **Fix:** Stable cluster identity / widen-in-place.

### A6. Unverified `podcasts.md` in the briefing bundle
- **Evidence:** `export_ai_briefing.py` `build_podcasts_md` includes Gemini/Spotify summaries when `podcast_signal()` passes; hash-stamped into the package. Fabricated Sector Allocations still possible.
- **Impact:** Wrong weights/claims can steer briefing conclusions with composite-hash authority.
- **Fix:** Summarizer `allocation_view: none`; keep VERIFICATION gate visible; treat figures as claims.

### A7. One-off script always writes Sheets
- **Evidence:** `scripts/apply_staging_dispositions_2026-08-08.py` — backup then `batch_update` Status with **no `--live`**.
- **Impact:** Re-run overwrites staging dispositions.
- **Fix:** Require `--live`, or delete after one-time use.

---

## MEDIUM

### A8. Dry-run morning still mutates disk
STEP 3 bundle write, STEP 4c moments, STEP 7–9 vault/composite/export, STEP 11 dislocation files are **not** gated on `live`. Sheet writers generally are. Document “Sheets-dry / disk-live” or gate disk writes.

### A9. Dashboard cash KPIs from incomplete cash model
`_compute_headline_kpis` uses Daily_Snapshots Cash Value / `CASH_TICKERS` (includes `CASH_MANUAL`). Morning snapshot uses `cash_manual=0.0`. Briefing rule forbids inferring liquidity from `CASH_MANUAL`. Label cash incomplete or hide pct.

### A10. Typed triggers parsed but not surfaced
`vault_bundle` carries typed keys; `get_ticker_triggers` returns only `price_trim_above` / `price_add_below`; Valuation_Card maps those only. `fwd_pe` / etc. stay blank on Trim/Add.

### A11. Blank-field frontmatter bug — fixed
`utils/level_coverage._frontmatter_field` uses `[ \t]*` not `\s*`. No residual same bug in `vault_bundle`.

### A12. Thesis sync ceiling — gather fixed; write path no-op on live files
`thesis_sync_data` preserves override. `ThesisManager.update_triggers` only matches fenced ```yaml blocks — dead for all 39 nested-frontmatter theses. Nested trigger keys are not overwritten (good); ceiling in frontmatter can drift from region display.

### A13. Promote Status vocabulary — partially hardened
Accepts `approve`/`approved`; writes `promoted` + `Promoted_At`; warns on promoted + blank `Promoted_At`. Hand-typed `promoted` still invisible. Still cell-by-cell staging marks.

### A14. Command Center Signal column has no staleness
Agent_Outputs rows joined without age; stale ADD/TRIM chips look current.

### A15. Dual Schwab token health signals
`tasks/health.py` vs `build_command_center._schwab_token_status` — independent; can disagree same morning.

### A16. `fetch_balances` unscoped (unused)
`utils/schwab_client.py` sums all accounts; no callers. Latent ~$935K vs ~$605K if wired. Delete or scope before any consumer.

### A17. Transactions overwrite risk — lower than some docs imply
Live sync **appends** fingerprint-new rows. Docstring “archive-before-overwrite” is misleading. Real hazards: `clean_junk_tickers` clear+rewrite; empty `SCHWAB_PRIMARY_ACCOUNT_SUFFIXES`.

---

## LOW

### A18. `config.DRY_RUN` defaults `"False"` — not a safety guarantee (documented).
### A19. Morning double-ingests transactions (STEP 1 + STEP 2); fingerprint dedup should prevent doubles.
### A20. Fallback transaction fingerprints omit account — rare collision if `activityId` missing.

### Known-doc status (integrity)

| Claim in CLAUDE.md / state.md | Status |
|---|---|
| pandas ≥3 zeroing in `read_gsheet_robust` | Fixed centrally; residuals in tax/pipeline |
| Position MV $0 | **Fixed in code**; docs still list as open |
| Account scope on fetch_* | Present |
| Nested supersets | Still present |
| Status / promoted collision | Partially fixed |
| DailyWake never fired | Still present (ops) |
| Dual token signals | Still present |
| Blank-field frontmatter | Fixed |
| Style ceiling overwrite | Gather fixed; write-side no-op on live theses |
| CASH_MANUAL / liquidity | Still a dashboard KPI hazard |
| podcasts.md unverified | Still by design |

---

# Part B — Dead / unreachable code

## Already archived
`archive/streamlit_legacy/`, `archive/legacy_agents/`, `docs/archive/deprecated/agents/` — former callers of many orphaned utils below.

---

## DEAD (safe remove / archive candidates)

| Path | Symbol / surface | Evidence | Recommendation |
|---|---|---|---|
| `utils/formatters.py` | module | Callers only under deprecated agents | Archive |
| `utils/validators.py` | module | Only archive Streamlit | Archive |
| `utils/finnhub_client.py` | module | Archive/legacy only; `FINNHUB_API_KEY` unused in active code | Archive; drop config key |
| `utils/chat_engine.py` | module | Only archive Advisor page | Archive |
| `utils/ai_research.py` | module | Only archive Research page | Archive |
| `utils/technicals.py` | module | Only archive concentration_hedger | Archive |
| `tasks/format_sheets_ui.py` | module | Zero imports; morning uses `format_sheets_dashboard_v2` | Archive |
| `tasks/create_dashboard.py` | module | Not wired; clear-rebuilds `0_DASHBOARD` | **Archive ASAP** |
| `scripts/create_dashboard.py` | obsolete Agent_Dashboard | Formula-based legacy | Archive |
| `tasks/enrich_atr.py` | `enrich_composite_bundle` | No active importer | Archive with flag cleanup |
| `tasks/enrich_technicals.py` | `enrich_composite_bundle` | Same; `config.TA_*` only here | Archive with ATR |
| `tasks/stax_sync.py` | module | Only archive Rebalancing page | Archive |
| `pipeline.py` | `append_decision_log`, `write_risk_metrics` | Archive Streamlit only | Delete functions; keep live shim |
| `utils/sheet_readers.py` | `get_risk_metrics`, `get_income_history`, `get_target_allocation`, `get_ai_suggested_allocation` | No active callers | Delete after create_dashboard archived |
| `utils/sheet_writers.py` | `archive_and_overwrite_agent_outputs`, `append_agent_outputs` | Deprecated agents only | Archive |
| `utils/risk.py` | Most of module | Production uses **`get_ticker_beta_fast` only** | Trim to that, or archive rest |
| `utils/schwab_client.py` | `fetch_balances` | Zero callers | Delete (also integrity A16) |
| `utils/schwab_client.py` | `is_api_available` | Archive only | Delete or keep as intentional helper |
| `utils/fmp_client.py` | several unused exports | Live path: fundamentals, movers, earnings calendar cached | Delete unused carefully |
| `utils/gemini_client.py` | `ask_gemini_bundled`, `ask_gemini_json` | No active callers | Delete after archiving `ai_research` |
| `utils/podcast_digest.py` | `load_digest`, `build_trade_prompt` | Archive Advisor only; keep sheet summary helpers | Delete those two |
| `utils/enrichment.py` | `get_live_price` | Archive Journal only | Delete |
| `tasks/export_package.py` | `copy_thesis_files` | Only test script | Delete or keep as test helper |
| `core/composite_bundle.py` | `load_composite` | Alias; zero callers | Delete alias |
| `tasks/templates/` | rotation/deep_dive templates | No Python reads; briefing uses inline `PROMPT_PAYLOAD` | Archive + dead version constants |
| `audit.py`, `audit_config.py` | modules | One-off; not wired | Archive |
| `scripts/re-enrich_all.py` | module | Imports missing `utils.agents.portfolio_enricher` | **Delete** (already broken) |
| `manager.py` | unused `List` import | Never used as a type | Delete |
| `config.py` | `FRED_API_KEY`, `AI_SECONDARY_API_KEY`, `CONCENTRATION_*`, `CORRELATION_FLAG_THRESHOLD`, `REBALANCE_THRESHOLD_PCT`, `PROMPT_TEMPLATE_VERSION_*` | No active reads | Delete with leftover cleanup |
| Dated `scripts/*_2026-08-*.py` one-offs | various | Not CLI/batch | Archive after use |

**Keep (not dead):** `pipeline.py` shim (`write_to_sheets`, `sanitize_*`, `normalize_positions`, `ingest_schwab_transactions`); `weekly_podcast_sync.py`; `lint_theses.py`.

---

## UNREACHABLE / NEVER EXERCISED

| Path | Symbol | Evidence | Recommendation |
|---|---|---|---|
| `core/vault_bundle.py` | Strategy 1 fenced ```yaml triggers | Only archived `KTOS_thesis.md`; 39 live files use nested FM | Keep with note, or delete Strategy 1 |
| `manager.py` `snapshot` | `--enrich-atr` / `--enrich-technicals` | Flags default True but body never calls enrich tasks; CLI_MANUAL lies | Delete flags + archive tasks, or wire them |
| `manager.py` `export_run` | scenarios ≠ `tax-rebalance` | Six of seven `EXPORT_SCENARIOS` stub | Delete stubs or implement |
| `core/vault_bundle.py` | `include_drive=True` | Logs “not yet implemented”; morning passes False | Keep with note or remove flag |
| `utils/agents/podcast_analyst.py` | `is_stax` branch | Only if source name contains STAX; `stax_sync` unused | Keep with note or archive with stax |
| `utils/sheet_readers.py` | `smoke_test` | `__main__` only | Delete or keep as local check |

---

## LATENT / RISKY IF WIRED

| Path | Why risky | Recommendation |
|---|---|---|
| `config.DRY_RUN` default False | False safety signal | Keep with note or remove |
| `tasks/create_dashboard.py` | Clear-rebuilds `0_DASHBOARD` outside Command Center | Archive ASAP |
| `pipeline.write_risk_metrics` | Callable with no CLI `--live` gate | Delete |
| `utils/agent_signals.get_latest_agent_outputs` | Still read by dashboard; Sheet writers dead → empty/stale Signal | Keep with note, or stop reading |
| `scripts/re-enrich_all.py` | Looks runnable; ImportError | Delete |
| Weight heuristic `max <= 1.5 → *100` in export/clean | Latent bug if book highly diversified | Note (not dead) |

---

## DEPRECATED BUT STILL WIRED (hidden Typer)

| Hidden group | Alias | Prefer |
|---|---|---|
| `trade` | `trade review` | `refresh rotations` |
| `sync` | `sync transactions`, `sync realized-gl` | `ingest *` |
| `tax` | `tax refresh` | `refresh tax` |
| `dashboard` | `dashboard refresh` | `refresh dashboard` |

Dual non-hidden: `export cleanup` ≡ `clean exports`; `podcast clean` ≡ `clean podcasts`.

Keep short-term for muscle memory; remove after `CLI_*` / HTML docs updated.

**Misleading help:** `vault thesis-audit` is filesize-only, not trigger completeness.

---

# Part C — Inefficiency

Hot paths: `pm morning`, dashboard refresh, snapshot, attribution, podcast sync. Qualitative cost; no profiling run attached.

## HIGH

### C1. Triple (plus health) Schwab position / transaction overlap in one morning
- **Evidence:** STEP 0 health `get_accounts(POSITIONS)` (`tasks/health.py`); STEP 1 `fetch_transactions` (`sync_transactions`); STEP 2 `fetch_positions` **and** `fetch_transactions` again (`scripts/live_update.py`); STEP 3 `build_bundle` → positions + quotes + `fetch_tax_lots` (another positions pull) (`core/bundle.py`).
- **Cost:** ~2× txn window sync (default `tx_days=7`); ~3× positions; extra quotes/lots. Minutes + Schwab rate risk every morning.
- **Fix:** One Schwab fetch phase → positions + txns + lots; STEP 1/2/3 consume it. Health can use token/TTL without full positions.

### C2. `format_sheets_dashboard_v2` — fixed ~180s sleeps every live morning
- **Evidence:** Six `time.sleep(30)` between tabs (`tasks/format_sheets_dashboard_v2.py` ~810–839); morning always calls `format_v2(live=live)` after dashboard builds.
- **Cost:** **~3 minutes wall clock** every `--live` morning, even when tabs barely changed; plus formatting API churn on tabs just rewritten.
- **Fix:** Format only dirty tabs; skip sleeps under quota; or format-on-write / weekly schema pass — drop from daily path.

### C3. Valuation_Card: sequential `yfinance.Ticker(...).info` for every holding
- **Evidence:** Per-ticker `.info` + `sleep(0.1)` (`build_valuation_card.py` ~151–152, ~333–343). Morning STEP 3 writes an **unenriched** bundle (no `enrich_fmp` unlike `pm snapshot`), so card often falls through to `.info` for fundamentals and still calls `.info` for price/52w even when FMP is present.
- **Cost:** ~39 heavy Yahoo scrapes every dashboard refresh; tens of seconds to minutes. Worse after morning’s bare snapshot.
- **Fix:** Enrich morning bundle like `snapshot`, or skip `.info` when bundle fields exist; prefer one bulk OHLCV (Command Center already bulk-downloads 52w).

### C4. Nested subprocess podcast pipeline
- **Evidence:** Morning shells `batch_podcast_sync.py` → shells `weekly_podcast_sync.py` per new channel. Dry-run still downloads transcript + Gemini; Sheet write gated only.
- **Cost:** Per new episode: process spawn + full import + YouTube + Gemini. Dry-run still burns Gemini/network.
- **Fix:** In-process analyze; gate Gemini on `--live` or `--fetch-only`.

---

## MEDIUM

### C5. Dashboard STEP 5: same tabs re-read by 3–4 builders
Valuation_Card, Decision_View, Tax_Control, Command Center each `open_by_key` / `get_all_values` Holdings (and overlapping tabs). `get_gspread_client()` is not process-cached. **Fix:** Pass one `ss` + in-memory DataFrames through STEP 5.

### C6. Decision_View ≈ subset of Command Center
Both clear-and-rebuild from Holdings ∪ Valuation ∪ Agent_Outputs every morning. **Fix:** Derive Decision_View from Command Center’s in-memory table, or drop from daily morning if unused.

### C7. 52w / price data fetched twice in STEP 5
Valuation_Card per-ticker `.info` 52w; Command Center bulk `yf.download(..., period="1y")`; plus separate SPY YTD after health already hit SPY. **Fix:** One market-data bag for the morning.

### C8. Dislocation scan: N+1 yfinance + fundamentals over large universe
Per-ticker `history` + `get_fundamentals` over held + watchlist + up to 50 FMP losers; always writes JSON/MD; `live` unused for network. Morning STEP 11 always runs. **Fix:** Bulk history once; reuse morning fundamentals; skip or thin on dry mornings.

### C9. STEP 10 derive_rotations: yfinance technicals before staging dedup
Technicals fetched for every cluster; fingerprint skip happens **after**. Dry-run still pays full Yahoo cost. **Fix:** Technicals only for new fingerprints, or defer to promote time.

### C10. STEP 9 export always `--lookthrough refresh` in a fresh process
Subprocess + ETF look-through network + re-glob/re-parse theses after STEP 7 already built a vault bundle. **Fix:** In-process export; `--lookthrough cache` on morning; read from vault/composite JSON.

### C11. Cell-by-cell gspread on hot-ish paths
`format_trade_log*` header loops via `update_cell`; `journal promote` per-row status `update_cell`. **Fix:** Single `batch_update` / range update.

### C12. live_update enrichment: top-N sequential `.info`
`utils/enrichment.py` uses `yf.Tickers` then `.info` per top ticker in STEP 2 — overlaps Valuation_Card later. **Fix:** Skip when Schwab has price/yield; share metadata with Valuation_Card.

---

## LOW

### C13. Thesis / vault files scanned repeatedly (STEP 7 + level_coverage + export + dislocation style). Seconds at ~39 theses.
### C14. `get_gspread_client` re-authorize every call (no `@lru_cache` despite import). Smaller than full tab reads.
### C15. Attribution sequential `yf.download` per ticker (within-run cache is good; not on morning unless `refresh rotations`). Batch union once.
### C16. `append_holdings_history` reads fingerprint column twice (`col_values`). Minor.

---

## Intentional costs (do not “fix”)

| Pattern | Why keep |
|---|---|
| Fingerprint dedup on txns / staging / history | Prevents duplicate authoritative rows |
| Archive-before-overwrite | Hard rule; safety over speed |
| Bundle SHA-256 + rehash after enrich | Immutability / reproducibility |
| Command Center clear-and-rebuild | No stale cells; documented |
| FMP disk cache + rate limiter | Quota protection |
| Attribution `_YF_CACHE` / `_BETA_CACHE` | Correct within-run micro-cache |
| Moment extraction cache skip | Already optimized for new transcripts only |
| format_v2 30s sleeps | Quota defense — wasteful as *daily default*, but not accidental |

---

## Morning STEP cost map

```
Health     → Schwab positions (probe)           ← overlap C1
STEP 1     → Schwab txns → Sheet                 ← overlap C1
STEP 2     → Schwab positions + txns + yf.info   ← overlap C1, C12
STEP 3     → Schwab positions + quotes + lots    ← overlap C1; unenriched bundle → C3
STEP 4/4b/4c → podcasts (subprocess nest) / Spotify / moments  ← C4
STEP 5     → Valuation (yf.info×N) → Decision_View → Tax → CC (yf 52w bulk) → format (+180s)  ← C2–C7
STEP 6–8   → thesis sync → vault → composite
STEP 9     → export subprocess + lookthrough refresh + re-parse theses  ← C10
STEP 10    → derive rotations + yf technicals×clusters  ← C9
STEP 11    → dislocation N+1 APIs  ← C8
STEP 12    → Drive publish
```

---

# Part D — Aggregated cleanup backlog

### Do first (integrity + collision risk)
1. `derive_rotations` CLI → `--live` required
2. `journal promote` schema ensure → `--live` only
3. Tax + pipeline → `coerce_sheet_numeric_series`
4. Tax_Control filter → primary Schwab suffixes
5. Archive both `create_dashboard*` before accidental overwrite of `0_DASHBOARD`

### Do next (morning wall-clock — biggest ROI)
6. Unify Schwab fetch for STEP 0–3
7. Drop or throttle daily `format_v2` sleeps / reformat-all
8. Enrich morning bundle **or** eliminate Valuation_Card `.info` loop; share bulk Yahoo with Command Center
9. Collapse podcast subprocess nesting; don’t Gemini on dry-run
10. Single Sheet snapshot for STEP 5 builders; demote Decision_View / dislocation / derive technicals to “only when needed”

### Then (dead code that docs/CLI currently lie about)
11. Remove no-op snapshot ATR/technicals flags; archive `enrich_atr` / `enrich_technicals`
12. Archive Streamlit leftover utils + Finnhub
13. Trim `pipeline.py` / `utils/risk.py` to live surfaces
14. Delete broken `scripts/re-enrich_all.py`
15. Decide Strategy 1 fenced-YAML: delete vs intentional safety net

### Then (integrity quality)
16. Nested-superset deriver fix (or stop auto-writing staging)
17. Dashboard cash labeling / Signal staleness
18. Single shared Schwab token status helper
19. Refresh `CLAUDE.md` / `state.md` Position MV + residual sanitizer list
20. Podcast summarizer `allocation_view: none`

### Optional hygiene
21. Remove hidden Typer aliases after docs catch up
22. Prune unused `config.py` keys and FMP/Gemini dead exports
23. Archive dated one-off scripts under `scripts/`
24. Process-level `get_gspread_client` + spreadsheet singleton
25. Batch attribution `yf.download` for sell/buy/benchmark union

---

## Method notes

- Integrity, dead-code, and inefficiency passes used targeted greps + definition/caller / hot-path tracing — not a single full-repo context dump.
- Gemini’s large window can *fit* a curated slice of this repo; it does not substitute for caller tracing, and stuffing the whole tree (venv/bundles/theses/archive) degrades reliability.
- Re-verify before acting if this file is read long after 2026-08-09.

**Related chat audits:** integrity [2dcb7ff5](2dcb7ff5-3620-408a-baaf-138c2a9e9025), dead code [0c3c80a7](0c3c80a7-b0ea-46fe-a8f5-2640af4b2633), inefficiency [3ffc189f](3ffc189f-1745-4b31-8391-b3cdcab061cf).
