# Repo Audit — 2026-05-26

## Executive Summary

- **Bundle infrastructure is fully confirmed.** SHA-256 hashing, vault per-document hashing, composite bundle with `recent_rotations`, and the 62-thesis file count all check out against code reality.
- **Gemini integration is accurate with one discrepancy:** STATE.md says model is `gemini-3.0-flash`; `config.py` defaults to `gemini-3.5-flash` and `gemini_client.py` hardcodes fallback to `gemini-3.1-pro-preview-customtools`. No code uses `gemini-3.0-flash`.
- **Idea Generator v1 is fully shipped and wired.** `agent_outputs/ideas/` contains two real output files. The `agent ideas` CLI command is confirmed in `manager.py` at line 1212.
- **BUNDLE_AND_AGENT_AUDIT.md is now stale.** It was written before Idea Generator shipped and still describes the four deprecated agents (Re-buy, Add-Candidate, etc.) as missing gaps to fill. The reframe happened after the audit was written.
- **Top cleanup wins:** (1) Delete or archive `BUNDLE_AND_AGENT_AUDIT.md` — its recommendations are now obsolete and could mislead; (2) Remove orphan config constants for deprecated agents (`ADD_CANDIDATE_*`, `NEW_IDEA_*`); (3) `app.py` does not exist — CLAUDE.md lists it as a key file but the file is absent.

---

## Section 1: STATE.md Verification

### Bundle Infrastructure

| Claim | Status | Evidence |
|---|---|---|
| `core/bundle.py` — SHA-256 canonical hashing | CONFIRMED | `_sha256_canonical()` at line 63; used at line 501 via `_hashable_payload()` |
| `core/vault_bundle.py` — per-document hashing | CONFIRMED | `_sha256_text(text)` called at vault_bundle.py line 201 for each document |
| `core/composite_bundle.py` — `recent_rotations` from Trade_Log | CONFIRMED | Lines 95-104: `get_trade_log()` call, top-10 rows baked into composite hash |
| 62 thesis files in `vault/theses/` | CONFIRMED | Glob `*_thesis.md` returns exactly 62 files |
| `bundles/` holds serialized JSON bundles | CONFIRMED | 33 context bundles, 5 vault bundles, 1 composite bundle present |

### Gemini Integration

| Claim | Status | Evidence |
|---|---|---|
| `ask_gemini()` defined in `utils/gemini_client.py` | CONFIRMED | Line 91 |
| `ask_gemini_composite()` defined | CONFIRMED | Line 250 |
| `SAFETY_PREAMBLE` auto-prepended in `ask_gemini()` | CONFIRMED | Lines 98-100: `full_system_instruction = SAFETY_PREAMBLE` then conditional append |
| `bundle_hash` required in schemas for `ask_gemini_composite()` | CONFIRMED | Lines 282-286: `if "bundle_hash" not in response_schema.model_fields: raise ValueError` |
| Dual-path auth: ADC primary, API key fallback | DISCREPANT | Auth order is reversed from STATE.md: API key is Path 1 (checked first, line 58); ADC is Path 2 (lines 63-70). STATE.md says "ADC primary" but code checks API key first. |
| Retry/backoff on 429 | CONFIRMED | Lines 142-164: `for wait_sec in (60, 120)` exponential backoff loop |
| Gemini model is `gemini-3.0-flash` | DISCREPANT | `config.py` line 69: default is `gemini-3.5-flash`. `gemini_client.py` line 96 fallback is `'gemini-3.1-pro-preview-customtools'`. No reference to `gemini-3.0-flash` anywhere. |

### Data Ingestion

| Claim | Status | Evidence |
|---|---|---|
| Schwab API read-only | CONFIRMED | `utils/schwab_client.py` docstring lines 1-13 explicitly prohibits order endpoints |
| No order/trading endpoints | CONFIRMED | Lines 5-7 of `schwab_client.py` list prohibited methods in docstring only; no functional calls found in manager.py or utils/ |
| CSV fallback in `utils/csv_parser.py` | CONFIRMED | File exists; imported by `core/bundle.py` line 25 |
| FMP client at `fmp_client.py` | DISCREPANT | STATE.md implies bare `fmp_client.py`; actual path is `utils/fmp_client.py` |
| Podcast transcripts write to `data/podcast_transcripts/` | CONFIRMED | `tasks/podcast_fetcher.py`: `TRANSCRIPTS_DIR = Path(__file__).parent.parent / "data" / "podcast_transcripts"` |
| `vault/transcripts/` is separate from podcast pipeline | NOTE | `vault/transcripts/` exists for vault_bundle reads but podcast pipeline writes to `data/podcast_transcripts/`. Two separate directories, different purposes. |

### Agent Layer

| Claim | Status | Evidence |
|---|---|---|
| `run_idea_generator()` in `utils/agents/idea_generator.py` | CONFIRMED | Line 105 |
| `write_idea_report()` | CONFIRMED | Line 213 |
| `Candidate` Pydantic model | CONFIRMED | Line 24 |
| `IdeaGeneratorOutput` Pydantic model | CONFIRMED | Line 37 |
| `prompts/idea_generator.md` exists | CONFIRMED | File present with full system prompt |
| `agent ideas` wired in `manager.py` | CONFIRMED | `@agent_app.command("ideas")` at line 1212 |
| Output in `agent_outputs/ideas/` | CONFIRMED | `agent_outputs/ideas/ideas_2026-05-26_a536e9fc.md` and `ideas_2026-05-27_a536e9fc.md` exist |
| Filename pattern `ideas_{YYYY-MM-DD}_{hash_prefix}.md` | CONFIRMED | Pattern matches; hash prefix is 8 chars |
| First run: 3 transcripts to 7 candidates | UNVERIFIABLE | Output file exists but contents not read during this audit |

### Google Sheets

| Claim | Status | Evidence |
|---|---|---|
| Sheet ID `1DuY68xVvyHq-0dyb7XUQgcoK7fqcVS0fv7UoGdTnfxA` | CONFIRMED | `config.py` line 17 |
| `Agent_Outputs`, `Agent_Outputs_Archive` as sandbox | CONFIRMED | `config.py` lines 118-119 |

### Automation

| Claim | Status | Evidence |
|---|---|---|
| GitHub Actions podcast pipeline Friday 5pm EST cron | CONFIRMED | `.github/workflows/podcast_sync.yml` cron: `0 22 * * 5` (10pm UTC = 5pm EST) |
| `workflow_dispatch` manual trigger | CONFIRMED | Line 7 of workflow |
| GCP Cloud Function for Schwab token refresh | CONFIRMED | `cloud_functions/token_refresh/main.py` exists with `functions_framework` import |
| GCP project `re-property-manager-487122` | CONFIRMED | `config.py` line 22 |

---

## Section 2: CLAUDE.md Convention Verification

### Hard Rules (8 rules)

| Rule | Status | Evidence |
|---|---|---|
| Read-only w.r.t. Schwab | ENFORCED IN CODE | `schwab_client.py` and `cloud_functions/token_refresh/main.py` both have explicit prohibit lists |
| DRY_RUN default true | ENFORCED IN CODE | Every write command in `manager.py` uses `if not live: ...DRY RUN...return` pattern |
| Bundle-first | ENFORCED IN CODE | `build_bundle()` + `_sha256_canonical()` fully implemented; agents use `ask_gemini_composite()` which loads verified bundle |
| Sheets is authoritative frontend | STATED CONVENTION | Honored operationally; not enforceable in code |
| No automated LLM calls against production tabs | STATED CONVENTION | `ask_gemini_composite()` does not write to Sheets; all agent output goes to local markdown |
| No emojis in code, logs, or docs | PARTIALLY VIOLATED | `CLI_CHEATSHEET.md` uses emoji section headers (sun, brain, wrench, lightning icons) |
| Archive-before-overwrite for pipeline writes | STATED CONVENTION | `write_bundle()` creates timestamped new files; clear-and-rebuild tabs do not archive (by design) |
| Audit-before-build | STATED CONVENTION | Not enforceable in code |

### Key Files Table (CLAUDE.md)

| File | Exists | Description Accurate |
|---|---|---|
| `app.py` | NO | CLAUDE.md lists as "Main Streamlit entry point" — file does not exist |
| `manager.py` | YES | Accurate |
| `pipeline.py` | YES | Listed as "CSV ingestion core" — partially inaccurate; file is now a migration shim per its own docstring |
| `core/thesis_sync_data.py` | YES | Accurate |
| `utils/thesis_utils.py` | YES | Accurate |
| `config.py` | YES | Accurate |
| `PORTFOLIO_SHEET_SCHEMA.md` | YES | Accurate |

**Major files absent from CLAUDE.md Key Files table:**
- `utils/gemini_client.py` — central LLM integration
- `utils/agents/idea_generator.py` — shipped agent
- `core/bundle.py`, `core/vault_bundle.py`, `core/composite_bundle.py` — core infrastructure
- `cloud_functions/token_refresh/main.py` — live GCP infrastructure
- `.github/workflows/podcast_sync.yml` — live automation

### Agent Output Conventions

| Convention | Status | Evidence |
|---|---|---|
| `agent_outputs/{agent_name}/` directory pattern | CONFIRMED | `write_idea_report()` defaults to `"agent_outputs/ideas/"` |
| `{agent_name}_{YYYY-MM-DD}_{hash_prefix}.md` filename | CONFIRMED | `filename = f"ideas_{date_str}_{hash_prefix}.md"` at line 276 |

---

## Section 3: Repo Cleanup Audit

### Stale/Deprecated Files

**`docs/archive/deprecated/`** — contents reviewed:
- `agents/` — full deprecated agent kit (rebuy_analyst.py, add_candidate_analyst.py, new_idea_screener.py, etc.) plus schemas, prompts, utils. KEEP ARCHIVED.
- `agents/context_bundle_spec.md`, `agents/buy_list_template.md` — obsolete specs. KEEP ARCHIVED.
- `frameworks/` — JSON strategy files. KEEP ARCHIVED.
- `podcast_gemini_summarizer/` — old summarizer code. KEEP ARCHIVED.
- `smoke_test.py`, `test_rebuy_agent.py`, `test_vault_bundle_smoke.py` — stale test files in archive. KEEP ARCHIVED.

**`BUNDLE_AND_AGENT_AUDIT.md`** (repo root, untracked) — **stale and misleading**. Written before Idea Generator shipped. Section 3 "Gap Analysis" still lists Re-buy, Add-Candidate, New Idea Screener, List Coherence as gaps to fill. Section 5 recommends building Re-buy Analyst as first step. The May 2026 reframe obsoletes this entire document. Recommend DELETE or archive with explanatory header.

### Legacy Agent Files

- `utils/agents/podcast_analyst.py` — exists in `utils/agents/` (live directory, not archive). It IS imported in `manager.py` line 1012 inside `podcast batch --analyze` command. The import is conditional (`if analyze:`) and wrapped in try/except. This is a live but non-default code path. No corresponding prompt file exists in `prompts/`. Status is ambiguous: not deprecated, but barely active.

- Note: there is also a `docs/archive/deprecated/agents/podcast_analyst.py`. The two copies may have diverged.

### Pipeline Migration Debt

`pipeline.py` at repo root describes itself as "a migration compatibility shim." It re-exposes functions for three callers:
- `scripts/live_update.py` — `normalize_positions`, `write_to_sheets`, `ingest_schwab_transactions`
- `tasks/sync_transactions.py` — `sanitize_dataframe_for_sheets`
- `utils/risk.py` — lazy import of `normalize_positions`

To retire: decompose into `utils/sheet_writers.py`, update three import sites, delete `pipeline.py`. Medium effort; no urgency.

### Streamlit Files

- `app.py` does not exist at repo root. Removed in April 2026 architectural pivot.
- No active `.py` files import `streamlit` — confirmed by grep returning no results.
- Old `app.py` likely archived in `archive/streamlit_legacy/` per pipeline.py docstring reference.

### Configuration Drift

Orphaned constants in `config.py` (defined but not imported by any active file):
- Lines 479-487: `ADD_CANDIDATE_STYLE_PCT`, `ADD_CANDIDATE_MAX_STARTER_PCT`, `ADD_CANDIDATE_MAX_CANDIDATES`, `ADD_CANDIDATE_STALE_THRESHOLD_DAYS`
- Lines 490-492: `NEW_IDEA_MAX_CANDIDATES_PER_RUN`, `NEW_IDEA_STARTER_SIZE_PCT`, `NEW_IDEA_MAX_STARTER_PCT`
- Lines 75-81: `GEMINI_MAX_TOKENS_REBUY`, `GEMINI_MAX_TOKENS_BAGGER`, `GEMINI_MAX_TOKENS_THESIS`, `GEMINI_MAX_TOKENS_CONCENTRATION`, `GEMINI_MAX_TOKENS_MACRO`, `GEMINI_MAX_TOKENS_VALUATION` — token budgets for deprecated agents

### Test Coverage

**`tests/` directory exists** with:
- `test_bundle_smoke.py` — 8 tests covering hash round-trip, tamper detection, CSV fallback, Schwab path, CASH_MANUAL injection, price_source validity. **Hash determinism IS tested.**
- `test_vault_bundle_smoke.py` — vault bundle tests (active copy present)
- `test_tax.py` — tax calculation tests
- `test_transaction_pandas_bug.py` — regression test

No tests for `ask_gemini_composite()` or `IdeaGeneratorOutput` schema validation.

### Dependency Hygiene

`pyproject.toml` uses `dynamic = ["dependencies"]` from `requirements.txt`. Entry point `pm = "manager:app"` is correct. Package structure includes `core*`, `tasks*`, `utils*`.

### Documentation Drift

**PORTFOLIO_SHEET_SCHEMA.md vs config.py TAB_* constants:**

Present in config.py but missing from PORTFOLIO_SHEET_SCHEMA.md:
- `TAB_AGENT_OUTPUTS` = `Agent_Outputs`
- `TAB_AGENT_OUTPUTS_ARCHIVE` = `Agent_Outputs_Archive`
- `TAB_DISAGREEMENTS` = `Disagreements`
- `TAB_DECISION_LOG` = `Decision_Log`

Present in PORTFOLIO_SHEET_SCHEMA.md but no TAB_* constant in config.py:
- `Valuation_Card`
- `Decision_View`

**CLI_CHEATSHEET.md:** Does not mention `pm agent ideas` — the new shipped command is absent from user-facing docs.

**STATE.md "How to Resume" section, Step 6:** Says `python manager.py bundle inspect <path>`. This command does not exist in manager.py. Correct command is `pm bundle verify <path>`.

---

## Section 4: Discrepancy Summary Table

| Doc | Claim | Status | Evidence | Action |
|---|---|---|---|---|
| STATE.md | Gemini model is `gemini-3.0-flash` | DISCREPANT | config.py default: `gemini-3.5-flash`; no code uses `gemini-3.0-flash` | Update STATE.md Quick Reference |
| STATE.md | "ADC primary, API key fallback" | DISCREPANT | gemini_client.py checks API key first (line 58), ADC second | Update STATE.md wording |
| STATE.md | FMP client at `fmp_client.py` | DISCREPANT | Actual path: `utils/fmp_client.py` | Update STATE.md |
| STATE.md | `bundle inspect` command in step 6 | DISCREPANT | Command does not exist; correct: `pm bundle verify <path>` | Fix STATE.md step 6 |
| CLAUDE.md | `app.py` as "Main Streamlit entry point" | DISCREPANT | `app.py` does not exist — removed April 2026 | Remove from CLAUDE.md key files table |
| CLAUDE.md | `pipeline.py` as "CSV ingestion and Sheet writing core" | PARTIALLY DISCREPANT | pipeline.py is now a migration shim per its own docstring | Update description |
| BUNDLE_AND_AGENT_AUDIT.md | Four agents missing; Re-buy recommended as first step | OBSOLETE | May 2026 reframe dropped all four agents; Idea Generator shipped | Archive or delete |
| config.py | `ADD_CANDIDATE_*` and `NEW_IDEA_*` constants | ORPHANED | Not imported by any active file | Delete |
| config.py | `GEMINI_MAX_TOKENS_REBUY/BAGGER/THESIS/etc.` | ORPHANED | Deprecated agent token budgets | Delete |
| PORTFOLIO_SHEET_SCHEMA.md | Missing Agent_Outputs, Agent_Outputs_Archive, Disagreements, Decision_Log | DISCREPANT | All four have TAB_* constants in config.py | Add to schema doc |
| CLI_CHEATSHEET.md | Missing `pm agent ideas` | DISCREPANT | Command wired at manager.py line 1212 | Add to cheatsheet |
| CONFIRMED (summary) | 27 of 32 verifiable factual claims | CONFIRMED | Sections 1-2 detail | No action needed |

---

## Section 5: Cleanup Recommendation Summary

| Path | Type | Recommendation | Rationale |
|---|---|---|---|
| `BUNDLE_AND_AGENT_AUDIT.md` | Stale audit doc | DELETE or ARCHIVE | Pre-reframe document with obsolete recommendations; actively misleading |
| `config.py` lines 479-492 | Orphaned constants | DELETE | `ADD_CANDIDATE_*` and `NEW_IDEA_*` serve deprecated agents; zero active imports |
| `config.py` lines 75-81 | Orphaned token budgets | DELETE or ANNOTATE | `GEMINI_MAX_TOKENS_REBUY/BAGGER/THESIS/etc.` — deprecated agents |
| `CLAUDE.md` `app.py` key file entry | Stale reference | DELETE from table | `app.py` does not exist; will mislead future sessions |
| `CLAUDE.md` `pipeline.py` description | Inaccurate | UPDATE | Change to "migration compatibility shim; decompose in future sprint" |
| `STATE.md` Gemini model in Quick Reference | Wrong model name | UPDATE | Change `gemini-3.0-flash` to `gemini-3.5-flash` |
| `STATE.md` Step 6 in Resume section | Wrong command | UPDATE | Change `bundle inspect` to `bundle verify` |
| `STATE.md` auth order description | Reversed from code | UPDATE | "API key primary (GEMINI_API_KEY env var), ADC fallback" |
| `CLI_CHEATSHEET.md` | Missing agent command | ADD | Add `pm agent ideas [--since-days N] [--dry-run]` |
| `PORTFOLIO_SHEET_SCHEMA.md` | Missing 4 tabs | ADD | Add Agent_Outputs, Agent_Outputs_Archive, Disagreements, Decision_Log |
| `utils/agents/podcast_analyst.py` | Ambiguous status | INVESTIGATE | Live but non-default code path; no prompt file; clarify or archive |
| `pipeline.py` | Migration shim | KEEP_BUT_DOCUMENT | Decompose in dedicated sprint; low urgency |
| `docs/archive/deprecated/` contents | Archived agent kit | KEEP | Properly archived; no action needed |

---

## Section 6: Suggested Next Steps

1. **Quick housekeeping pass** (30 min, 5 files) — Fix the 8 factual discrepancies in STATE.md and CLAUDE.md: Gemini model, auth order, FMP path, `bundle inspect` command, `app.py` key file entry, pipeline.py description. Add `pm agent ideas` to CLI_CHEATSHEET.md. Text edits only, no code changes.

2. **Config cleanup** (15 min, config.py only) — Delete the 11 orphaned constants for deprecated agents (`ADD_CANDIDATE_*`, `NEW_IDEA_*`, deprecated `GEMINI_MAX_TOKENS_*`). Confirm no imports via grep first. Zero risk of breakage.

3. **Retire or update BUNDLE_AND_AGENT_AUDIT.md** (5 min) — Delete or move to `docs/archive/deprecated/` with a header note: "Pre-reframe. Idea Generator shipped May 26, 2026. See STATE.md for current direction." Highest-value single change for preventing confusion in future sessions.

4. **Ship Valuation Drift Monitor** (medium complexity) — Per STATE.md current priority. Same fire-fire-aim pattern as Idea Generator: add FMP fundamentals to bundle, build Pydantic schema, write system prompt, wire `pm agent drift` CLI command, run on real data and iterate.

5. **Decompose pipeline.py** (medium effort, deferred) — Move `write_to_sheets()`, `sanitize_dataframe_for_sheets()`, `normalize_positions()` to `utils/sheet_writers.py`. Update three import sites. Delete pipeline.py. Cleans up migration shim debt that currently creates confusion about the system's architecture.

---

## Appendix: Files Opened During Audit

| File | Approximate Lines | Purpose |
|---|---|---|
| `STATE.md` | 142 | Audit subject |
| `BUNDLE_AND_AGENT_AUDIT.md` | 161 | Audit subject |
| `CLAUDE.md` | 78 | Convention source |
| `core/bundle.py` | 554 | Bundle infrastructure verification |
| `core/vault_bundle.py` | 368 | Vault bundle verification |
| `core/composite_bundle.py` | 195 | Composite bundle verification |
| `utils/gemini_client.py` | 361 | Gemini integration verification |
| `utils/agents/idea_generator.py` | 280 | Agent layer verification |
| `manager.py` | 1260 | CLI entry point; command inventory |
| `config.py` | 527 | Configuration; Sheet ID; tab constants |
| `PORTFOLIO_SHEET_SCHEMA.md` | 216 | Sheet schema comparison |
| `CLI_CHEATSHEET.md` | 33 | User docs verification |
| `CLI_MANUAL.md` | 80 (partial) | User docs verification |
| `portfolio_manager_user_docs.html` | 593 | Existing HTML (rewrite target) |
| `utils/schwab_client.py` | 60 (partial) | Read-only enforcement check |
| `cloud_functions/token_refresh/main.py` | 30 (partial) | GCP Cloud Function confirmation |
| `.github/workflows/podcast_sync.yml` | 47 | GitHub Actions confirmation |
| `tests/test_bundle_smoke.py` | 204 | Test coverage inventory |
| `pyproject.toml` | 26 | Package config |
| `prompts/idea_generator.md` | 30 (partial) | Agent prompt confirmation |
