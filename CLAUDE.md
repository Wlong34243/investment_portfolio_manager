# CLAUDE.md — Investment Portfolio Manager

## What this project is
A headless Python CLI portfolio operating system with Google Sheets as the authoritative frontend. APIs compute; Sheets persist; LLMs reason externally.

## What this project is not
- Not an auto-trader
- Not a backtest framework
- Not a robo-advisor
- Not a web app

## Core invariants (non-negotiable)
- Read-only with respect to Schwab. No order endpoints imported or called.
- DRY_RUN default true. Writes require explicit --live.
- Bundle-first: deterministic data freezes to a hashed JSON before any reasoning.
- Sheets is the authoritative frontend. Any other UI is an optional read-only consumer.
- No automated LLM calls against production tabs. AI writes to sandbox or export packages only.
- No emojis in code, logs, or docs unless the user explicitly requests them.

## Development conventions
- Typer for the CLI.
- Rich for terminal output.
- Pydantic for schemas.
- gspread for Sheets. Single-batch writes with fingerprint dedup.
- Archive-before-overwrite standard for all pipeline writes.
- Audit-before-build: read existing files via codebase search before generating new code.
- One commit per Phase prompt. Scope discipline: no "while I'm here" additions.

## Data sources (priority order)
1. Schwab Developer API (primary, read-only)
2. Schwab CSV (fallback + realized G/L history)
3. yFinance (prices, sector, beta, dividend yield)
4. FMP (fundamentals — extend fmp_client.py before adding any new vendor)
5. Finnhub (news)

## Tab authority
- Target_Allocation: manual only; app reads but never writes
- Config: manual only; app reads but never writes
- AI_Suggested_Allocation: sandbox; AI writes, Bill promotes
- Holdings_Current / Holdings_History / Daily_Snapshots / Transactions: pipeline writes
- Valuation_Card / Decision_View / Tax_Control / Rotation_Review: computed views, clear-and-rebuild
- Trade_Log / Trade_Log_Staging: rotation capture pipeline
- RealizedGL: CSV ingestion, append with fingerprint dedup
- Logs / Disagreements: append-only

## CLI invocation
- Preferred: `pm <command>` — available after `pip install -e .` registers the console script.
- Equivalent: `python manager.py <command>` — always works; preferred in CI for explicit interpreter binding.
- The Typer app object is `app` at module level in `manager.py`.

## Key Files
- `app.py`: Main Streamlit entry point.
- `manager.py`: CLI entry point (Snapshot, Vault, Bundling).
- `pipeline.py`: CSV ingestion and Sheet writing core.
- `core/thesis_sync_data.py`: Gathers data for vault synchronization.
- `utils/thesis_utils.py`: `ThesisManager` for surgical Markdown/YAML/Region updates.
- `config.py`: Central settings and constants.
- `PORTFOLIO_SHEET_SCHEMA.md`: Authoritative Sheet structure.

## Command Cheatsheet
- `python manager.py snapshot --csv <path> --live`: Ingest Schwab positions.
- `python manager.py vault sync`: Dry-run sync Sheets data to local theses.
- `python manager.py vault sync --live --show-diff`: Commit Sheets data to theses.
- `python manager.py vault snapshot --live`: Freeze vault state to hash.
- `streamlit run app.py`: Launch the dashboard.

## Current Focus (May 2026)
- **Hardening:** Bracing for FMP API failures and Gemini response truncation.
- **Risk Bridge:** Closing the loop between qualitative thesis "drift" and quantitative rebalancing.
- **Thesis Coverage:** Ensuring 100% coverage for all portfolio positions.
- **Van Tharp Sizing:** Moving to ATR-based risk-unit (1R) position sizing.

## If in doubt
- Read `state.md` for current task status.
- Read `PORTFOLIO_SHEET_SCHEMA.md`.
- Read `lessonsLearned.md` to avoid "Is Cash" and "Nuclear Type" pitfalls.
- Use `ThesisManager` for any file edits involving `vault/theses/*.md`.
- Ask before changing core architectural patterns.
