# Gemini Peer Review Request — Post UI-Improvement-Plan Checkpoint

**Date:** 2026-07-14
**Requested by:** Bill, via Claude Code
**Run with:** Gemini CLI, from the repo root, with file-system access (this is not a copy-paste-into-chat package — read files directly).

---

## Why this checkpoint exists

Claude Code just finished a multi-session build sequence: rebuilding the Sheets UI (`0_DASHBOARD`, `Valuation_Card`, `Decision_View`), plus two emergency fixes discovered mid-stream (a live data-corruption incident and a silently-repeating podcast-sync waste bug). Per this project's own convention (see `CLAUDE.md` → "Gemini peer review"), a build sequence like this gets a second, independent set of eyes before it's trusted. That's this request.

You have full repo access. Don't take any finding below on faith — re-derive it from the code, and push back if you disagree.

---

## Step 0 — Orient yourself

1. Read `CLAUDE.md` in full (project conventions, hard rules, architecture principle).
2. Read `STATE.md` (last updated 2026-06-15 — note it predates this session's work and is known to be stale in places; see Finding #11 below).
3. Run `git status` and `git diff --stat`. You'll see a large number of modified files — most are **pre-existing uncommitted work unrelated to this session** (63 `vault/theses/*.md` files, `data/podcast_summaries/*.md`, etc.). This review is scoped to the file list in Section A below. Don't assume everything in `git status` is in scope.

---

## Section A — Files this session actually touched (primary review target)

| File | What changed and why |
|---|---|
| `utils/sheet_readers.py` | `read_gsheet_robust()`: was stripping `%` from cell strings without dividing by 100 — a cell displaying `"6.77%"` (the fraction 0.0677) was silently parsed as `6.77`. Fixed to detect a literal `%` per-cell and divide only then. |
| `utils/column_guard.py` | Same class of fix in `ensure_display_columns()`, plus added `Unrealized G/L`/`Unrealized G/L %` to the numeric-cast list (they previously fell through as uncast strings). |
| `utils/enrichment.py` | `enrich_positions()`: yfinance's `dividendYield` is now percent-scale (confirmed live: JEPI=8.45, not 0.0845), was being used directly, inflating `Est Annual Income` 100x. Fixed with unconditional `/100` + defensive re-scale. Also: was overwriting `Asset Class` (Equity/Fixed Income/Cash) with yfinance's GICS `sector` (Technology/Utilities/...) — now routes sector to a new `Sector` column instead, only explicit `TICKER_OVERRIDES` touch Asset Class. |
| `config.py` | Added `Sector` to `POSITION_COLUMNS` (appended at the end, so no existing column shifts index) + `POSITION_COL_MAP` entry. |
| `pipeline.py` | `sanitize_dataframe_for_sheets()`: removed a formula-injection branch (`'=G{ROW}-H{ROW}'`) that a prior fix wrongly assumed was dead code (see Finding #1 — this caused a real incident). `Unrealized G/L`/`%` are now always recomputed in Python from Market Value − Cost Basis, not trusted from whatever upstream field arrives. `write_holdings_current()`: switched to `value_input_option='RAW'`, added `_apply_holdings_number_formats()` to stamp consistent number formats on every write (dollar/percent/quantity columns), since `ws.clear()`/`batch_clear()` only clear values, not formatting. |
| `tasks/build_command_center.py` | Full rewrite of `0_DASHBOARD`: was a multi-section KPI/tax/risk/top-10/drift dashboard, now a single KPI strip + full position table (all ~42 holdings, sorted by Market Value descending) joined against `Valuation_Card` + latest `Agent_Outputs` run. Values written as raw numbers with real Sheets number formats (not baked strings) so `#NAME?`-type parsing errors are structurally impossible. Added a bulk 52-week-range yfinance fetch, conditional-format rules, and cell notes for agent rationale. |
| `tasks/build_decision_view.py` | Full rewrite: was duplicating the full 42-row position table with light agent-signal annotation; now shows **only** rows with an active signal (currently 8, all "ADD") with full untruncated rationale, reusing `build_command_center._build_position_table()` rather than re-deriving the join. |
| `tasks/build_valuation_card.py` | Removed the always-empty `Forward P/E (FMP)` column. Added `Position MV` (joined from `Holdings_Current`), now sorts by it instead of company market cap. Introduced `VALUATION_CARD_COLUMNS` as a single source of truth + `col_letter()` helper, replacing hardcoded column-letter formatting. Found and fixed: FMP's bundled `market_cap` field is stored in **billions**, not raw dollars (confirmed exact 1e9 ratio against yfinance for the same ticker/day) — was rendering as `"$0.0M"` for a multi-trillion-dollar company once a real number format was applied. |
| `tasks/format_sheets_dashboard_v2.py` | `format_valuation_card()`: rewrote to derive column letters from `build_valuation_card.col_letter()` instead of hardcoding them (they'd already drifted once). `format_decision_view()`: removed entirely — its hardcoded 14-column layout no longer matches the new 12-column Decision_View, and Decision_View now formats itself (matching the pattern `0_DASHBOARD` already uses). |
| `tasks/build_tax_control.py` | Added explicit per-column number formatting to the KPI row — wash sale *count* was rendering as a dollar amount (`"$111.00"`) because `ws.clear()` doesn't clear stale cell formatting. |
| `utils/agent_signals.py` | **New file.** `get_latest_agent_outputs()` + `ACTION_SEVERITIES` extracted out of `build_decision_view.py` so both builder modules can depend on it without a circular import. |
| `manager.py` | `bundle_push`: was only deriving `weight` from `weight_pct/100` when `weight` was *absent* from the dataframe — but the bundle has both a bogus always-zero `weight` field and a correct `weight_pct`, so the zero column silently won. Fixed to always prefer `weight_pct` when present. `morning`: raised the podcast-sync subprocess timeout from 180s to 600s. |
| `tasks/batch_podcast_sync.py` | `save_processed_videos()` now runs after every successfully-processed episode, not once at the end of the channel loop — a timeout mid-run was previously discarding all progress, causing the same episodes to be silently re-downloaded and re-analyzed by Gemini on every subsequent run (confirmed: 3 episodes reprocessed identically on 2026-07-09, 07-13, and 07-14 before this fix). |

---

## Section B — Findings already surfaced this session (verify, don't rediscover from scratch)

1. **A "confirmed dead code" diagnosis was wrong and caused a live incident.** Early in this session, a formula-injection branch in `pipeline.py` was concluded to be unreachable based on a manually-retyped string comparison test — not on reading the actual file bytes. It was live. Switching that write path to `RAW` input mode (a legitimate, separate fix) caused Sheets to store the literal text `"=G3-H3"` instead of evaluating it, corrupting `Unrealized G/L` for all 42 positions in production for one write cycle before it was caught and fixed. **Ask yourself: is there a general lesson here about verification methodology worth flagging, and are there other places in this codebase where a similar "I tested my assumption, not the actual code" pattern might be hiding?**
2. **`utils/csv_parser.py::get_sector_fast()` references `config.ETF_KEYWORDS`, which does not exist anywhere in `config.py`.** Confirmed via a live call — it raises `AttributeError`. Currently only guarded with a `try/except` (so it degrades to a warning instead of crashing the snapshot pipeline) — **not actually fixed**. Worth deciding whether this dead-end classifier should be removed or properly implemented.
3. **The bundle's own top-level `unrealized_gl`, `est_annual_income`, `dividend_yield`, and `daily_change_pct` fields are unreliable flat placeholders (observed as `0.0`)** in the `bundle_push` code path specifically — real data lives in nested `fundamentals`/`fmp_fundamentals` dicts or in separately-computed fields. `weight` was fixed this session; `dividend_yield`/`est_annual_income`/`daily_change_pct` were **not** — Holdings_Current currently shows `$0.00` Est Annual Income and `0.0%` Daily Change for every position pushed via this path. **This is a real, currently-live gap.**
4. **Windows console Unicode crashes recurred multiple times this session** (an arrow character, then a `✅` emoji) despite `CHANGELOG.md`'s 2026-06-04 entry explicitly documenting this exact failure mode and claiming it was fixed ("Replaced all five with ASCII equivalents"). That fix was evidently applied to specific files, not swept across the codebase. **Worth a `grep` for non-ASCII characters in every `print()`/`console.print()` call, repo-wide, rather than fixing these one at a time as they're hit.**
5. **The valuation/macro/thesis/concentration/tax "agent squad"** (`valuation_agent.py`, `macro_cycle_agent.py`, `thesis_screener.py`, `analyze_all.py`) that populates `Agent_Outputs` — the data source for `Decision_View`'s and `0_DASHBOARD`'s Signal column — **has been moved to `docs/archive/deprecated/agents/`**. Its last run is dated 2026-04-20. There is currently no active process that will ever refresh these signals; `manager.py agent` only exposes `ideas`, a different agent entirely. Both rebuilt views are, by design, silently displaying whatever was last true almost 3 months ago, with no staleness indicator. **Is this acceptable as-is, or does it need either a revival plan or a visible "stale" warning on the Signal column?**
6. **The `export` command group is significantly less complete than its own `list` subcommand implies.** `config.EXPORT_SCENARIOS` lists 7 scenarios with real descriptions; only `tax-rebalance` has an actual implementation (`_export_tax_rebalance()` in `manager.py`, using the genuinely well-built primitives in `tasks/export_package.py`). The other 6 (`rotation`, `deep-dive`, `technical-scan`, `macro-review`, `concentration`, `thesis-health`) hit a hardcoded `else: not yet implemented` and exit 1. None of this — including the one working scenario — is mentioned in `STATE.md`, `CHANGELOG.md`, or `CLAUDE.md`'s "Key Files" table.

---

## Section C — Ask for your independent judgment

1. **Systemic pattern check.** This session found the *same class* of bug — a value silently mis-scaled by a factor of 100 or 1e9 because a reader/writer assumed a unit convention that didn't hold — in at least four unrelated places (Holdings_Current percent columns, yfinance dividend yield, FMP market cap, bundle weight field). Is there a shared root cause worth fixing once (e.g., a stricter, fail-loud data-contract layer at the bundle/Sheet boundary) rather than continuing to patch each instance as it's discovered?
2. **Positional data access audit.** `scripts/diagnose_daily_change.py` hardcodes `ws.col_values(17)` assuming a specific Holdings_Current column position — this is why a planned column-reorder task (moving plumbing columns like `Fingerprint`/`Wash Sale` to the far right) was skipped this session rather than risk breaking it. Are there other scripts with similar positional (not name-based) column access that would silently break under a future schema change? A `grep` for `.col_values(`, `.iloc[`, and raw numeric column indexing across `scripts/` and `tasks/` would surface this.
3. **`column_guard.py` / `read_gsheet_robust()` philosophy.** Both take a "strip `$`/`%`/`,`, coerce to numeric, default to 0.0 on failure" approach — silently permissive rather than fail-loud. Given how many bugs this session trace back to silent misinterpretation of ambiguous cell content, is this still the right default, or should malformed/ambiguous data raise instead of coercing?
4. **Anything in Section A's diffs that looks wrong, fragile, or under-tested that Claude Code didn't flag.** Read the actual diffs (`git diff -- <file>` for each file in Section A), not just the summary table above.

---

## What to produce

A findings list, ranked by severity, each with a concrete file:line reference and a one-line description of the failure scenario (not just "this looks off" — what input/state actually breaks). Distinguish between: (a) bugs in this session's changes, (b) pre-existing issues this session's changes expose or make worse, (c) pre-existing issues unrelated to this session that you noticed along the way. If you agree with a finding in Section B, say so briefly rather than re-deriving it at length — spend your effort on what's *not* already covered above.
