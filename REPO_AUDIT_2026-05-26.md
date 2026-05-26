# Repo Audit — 2026-05-26

## Executive Summary
- **Strong Conceptual Adherence:** The headless CLI architecture, deterministic Python math, and immutable SHA-256 hashed bundles are firmly established in code. `manager.py`, `bundle.py`, and `gemini_client.py` execute the design patterns described in `STATE.md` perfectly.
- **Pathing Drift:** `STATE.md` claims transcripts are saved to `vault/transcripts/`, but the code (`idea_generator.py` and pipeline) actually reads/writes from `data/podcast_transcripts/`. 
- **Legacy Phantoms:** Remnants of the old Streamlit era linger. Specifically, `gemini.md` has not been updated and still enforces Streamlit UI boundaries. `.streamlit/` configuration files and run logs still exist in the root directory.

## Section 1: STATE.md Verification
- **Bundle Infrastructure:**
  - Market bundle canonical hashing verified in `core/bundle.py` via SHA-256 (`hashlib.sha256` digest). 
  - Vault bundle per-document hashing verified in `core/vault_bundle.py` (`_vault_hash()` logic).
  - Composite bundle inclusion of `recent_rotations` via `get_trade_log()` from the `Trade_Log` tab verified in `core/composite_bundle.py`.
  - **Vault Files:** Claimed 62 thesis files. Found exactly 62 `.md` files + 1 `.txt` file in `vault/theses/`. **CONFIRMED**.
  - **Bundles:** The `bundles/` directory exists and has ~38 JSON files. **CONFIRMED**.
- **Gemini Integration:**
  - `ask_gemini()` and `ask_gemini_composite()` signatures and `SAFETY_PREAMBLE` auto-prepends verified in `utils/gemini_client.py`.
  - `bundle_hash` schema enforcement logic confirmed (`if "bundle_hash" not in response_schema.model_fields...`).
  - Dual-path Auth (ADC and API key fallback) and exponential backoff on 429/Resource Exhausted confirmed.
- **Data Ingestion:**
  - Schwab API read-only confirmed. No `/orders` endpoints referenced anywhere outside safety comments.
  - CSV fallback (`utils/csv_parser.py`) and FMP client (`utils/fmp_client.py`) exist and match descriptions.
  - Podcast transcripts: **DISCREPANT.** `STATE.md` claims `vault/transcripts/` but `idea_generator.py` points to `data/podcast_transcripts/`.
- **Agent Layer:**
  - Idea Generator components (`utils/agents/idea_generator.py` and `prompts/idea_generator.md`) exist with matching Pydantic schemas and Typer CLI subcommands.
  - Agent output lands in `agent_outputs/ideas/` and generates correctly (found `ideas_2026-05-26_a536e9fc.md`).
- **Google Sheets / Automation:**
  - Correct Sheet ID and tab constants exist in `config.py`.
  - GitHub Actions cron exists (`.github/workflows/podcast_sync.yml`) executing at 10 PM UTC Fridays (5 PM EST).

## Section 2: CLAUDE.md Convention Verification
- **DRY_RUN Defaults:** While `config.py` has a legacy `DRY_RUN = False` string parser, all CLI commands in `manager.py` explicitly default the `--live` flag to `False`, enforcing the dry-run-first convention.
- **Bundle Immutability:** Hash mismatch checking is strongly enforced in `core/composite_bundle.py` and `utils/gemini_client.py`.
- **Single-batch Gspread Writes:** Enforced via `append_rows()` in `manager.py` journal functions and `pipeline.py`.
- **File Table Match:** All files listed in the Key Files table exist and serve their documented purposes.
- **Agent Outputs:** The `idea_generator.py` writer correctly matches the `{agent_name}_{YYYY-MM-DD}_{hash_prefix}.md` naming convention.

## Section 3: Repo Cleanup Audit
- **Streamlit Phantoms:** Despite the headless pivot, `.streamlit/`, `streamlit_out.log`, and `streamlit_run.log` still sit in the root directory. Furthermore, the `gemini.md` context file is grossly out of date and tells LLMs to enforce Streamlit Global Scope rules.
- **Pipeline Migration Debt:** `pipeline.py` is actively imported by `manager.py` (e.g., `pipeline.sanitize_dataframe_for_sheets`, `pipeline.write_to_sheets`). It duplicates some logic but still provides essential shims.
- **Legacy Agent Files:** `archive/legacy_agents/` contains all the deprecated agents. However, `utils.agents.podcast_analyst` is still actively imported by `manager.py` (`pm podcast batch --analyze`), crossing the legacy/active boundary.
- **Configuration Drift:** `config.py` contains unused constants from legacy AI logic (e.g., `GEMINI_MAX_TOKENS_VALUATION`, `CONCENTRATION_SINGLE_THRESHOLD`).

## Section 4: Discrepancy Summary

| Doc | Claim | Status | Evidence | Action |
| --- | --- | --- | --- | --- |
| `STATE.md` | Podcast transcripts ingested to `vault/transcripts/` | **DISCREPANT** | `idea_generator.py` reads `data/podcast_transcripts/` | Update `STATE.md` to reflect `data/` or move path to `vault/` |
| `gemini.md` | Core tech stack is Streamlit, UI logic must be in `st.Page` | **DISCREPANT** | Repo is headless, Streamlit deprecated | Rewrite or delete `gemini.md` |
| `CLAUDE.md` | `pipeline.py` is a shim only; new work in `manager.py` | **CONFIRMED** (Partial) | It is a shim, but `manager.py` still relies heavily on it | Plan final extraction of `write_to_sheets` to `utils/` |

## Section 5: Cleanup Recommendation Summary

| Path | Type | Recommendation | Rationale |
| --- | --- | --- | --- |
| `.streamlit/` & `streamlit_*.log` | Legacy Config | **DELETE** | Streamlit is fully deprecated. Clutters root. |
| `gemini.md` | Prompt Context | **PROMOTE** | Contains highly outdated architectural mandates that directly conflict with the May 2026 CLI reframe. Needs rewrite to match `CLAUDE.md`. |
| `docs/archive/deprecated/agents/*` | Stale Docs | **DELETE** | Context bundle specs and buy lists are now superseded by actual bundle implementation. |
| `archive/streamlit_legacy/` | Legacy Code | **KEEP_BUT_DOCUMENT** | Retain for historical reference but ensure no active imports exist. |
| `utils/agents/podcast_analyst.py` | Legacy Shim | **INVESTIGATE** | Still imported by `manager.py` during `podcast batch --analyze`. Determine if this should be archived or formalized. |
| `pipeline.py` | Debt | **INVESTIGATE** | Move remaining gspread logic to `utils/sheet_writers.py` to allow final deletion of pipeline. |

## Section 6: Suggested Next Steps

1. **Prompt File:** `update_gemini_md_context.md`
   - **Scope:** Rewrite the system prompt in `gemini.md` to completely remove Streamlit mentions, aligning it with the CLI/Sheets data spine architecture.
   - **Complexity:** Small

2. **Prompt File:** `fix_transcript_path_drift.md`
   - **Scope:** Reconcile the discrepancy between `STATE.md` (claims `vault/transcripts/`) and the code (`data/podcast_transcripts/`).
   - **Complexity:** Small

3. **Prompt File:** `purge_streamlit_remnants.md`
   - **Scope:** Delete `.streamlit/` and old `streamlit_*.log` files from root, removing the last filesystem traces of the web app.
   - **Complexity:** Small

4. **Prompt File:** `retire_pipeline_shim.md`
   - **Scope:** Extract the `sanitize_dataframe_for_sheets` and `write_to_sheets` functions from `pipeline.py` into `utils/sheet_writers.py` and delete `pipeline.py`.
   - **Complexity:** Medium

## Appendix: Files Touched During Audit
- `portfolio_manager_user_docs.html`
- `STATE.md`
- `CLAUDE.md`
- `BUNDLE_AND_AGENT_AUDIT.md`
- `manager.py`
- `core/bundle.py`
- `core/vault_bundle.py`
- `core/composite_bundle.py`
- `utils/gemini_client.py`
- `utils/agents/idea_generator.py`
- `utils/schwab_client.py`
- `utils/fmp_client.py`
- `utils/csv_parser.py`
- `config.py`
- `pyproject.toml`
- `.github/workflows/podcast_sync.yml`