# Investment Portfolio Manager — CLAUDE.md

## Project Identity
Headless CLI tool for tracking, analyzing, and managing a ~$480K liquid investment portfolio (50+ positions). Ingests positions from the Schwab API (CSV fallback), writes to Google Sheets, and runs AI-assisted analysis via 11 specialized agents over immutable hashed bundles. Companion system to the RE Property Manager (shared GCP project `re-property-manager-487122`). The legacy Streamlit app has been archived to `archive/streamlit_legacy/`.

## Technical Stack
- **CLI:** Typer (`manager.py`) — headless, deterministic, no server
- **Database:** Google Sheets (via `gspread`)
- **Market Data:** Schwab API (primary), yfinance, Financial Modeling Prep (FMP), Finnhub
- **AI:** Gemini 2.5 Flash (via `google-genai` SDK + Vertex ADC)
- **Model Isolation:** Python app → `gemini-2.5-flash` via `google-genai` + Vertex ADC. Dev assist → Gemini CLI with Code Assist free tier. These are independent.
- **Guardrails:** Pydantic (Schema), Python-only Math, PII stripping

## Project Structure
```
investment-portfolio-manager/
├── manager.py                    # CLI entry point (snapshot, vault, bundle, agent, journal)
├── config.py                     # Centralized column maps & constants
├── core/
│   ├── bundle.py                 # Market bundle builder + SHA256 hash
│   ├── vault_bundle.py           # Vault bundle (theses, transcripts, frameworks)
│   └── composite_bundle.py      # Composite = SHA256(market_hash + vault_hash)
├── agents/                       # 11 live agents (all Pydantic-enforced)
│   ├── rebuy_analyst.py          # Scale-in candidates (Lynch GARP + Van Tharp sizing)
│   ├── add_candidate_analyst.py  # New ticker displacement analysis
│   ├── new_idea_screener.py      # Style-bucket screening for user-supplied tickers
│   ├── tax_agent.py              # TLH candidates + wash-sale risk
│   ├── valuation_agent.py        # Multi-year P/E signals + accumulation plans
│   ├── concentration_hedger.py   # Concentration risk + correlation hedges
│   ├── macro_cycle_agent.py      # Carlota Perez macro cycle + FRED/VIX triggers
│   ├── thesis_screener.py        # English goals → quantitative screens (Baid)
│   ├── bagger_screener.py        # 100-bagger quantitative gate (Mayer)
│   ├── behavioral_auditor.py     # Trade audit against Morgan Housel principles
│   ├── Options_agent.py          # Covered call strategies OTM 5-15% (Phase 6 data dep.)
│   ├── analyze_all.py            # Orchestrator — runs all standard agents in one pass
│   ├── prompts/                  # Editable system prompt .txt files per agent
│   ├── schemas/                  # Pydantic output schemas per agent
│   └── utils/                    # Shared agent utilities (chunked_analysis, etc.)
├── tasks/
│   ├── enrich_fundamentals.py    # Pre-bake FMP/yfinance fundamentals into market bundle
│   ├── enrich_atr.py             # Pre-bake ATR stops into composite bundle
│   ├── build_valuation_card.py   # Write Valuation_Card tab to Google Sheets
│   ├── derive_rotations.py       # Cluster sell/buy pairs → Trade_Log_Staging
│   ├── format_sheets_dashboard_v2.py  # Apply formatting to all Sheet tabs
│   └── weekly_podcast_sync.py    # YouTube RSS → transcript → AI_Suggested_Allocation
├── utils/
│   ├── fmp_client.py             # Three-tier fundamentals: Schwab → yfinance → FMP cache
│   ├── gemini_client.py          # Centralized LLM interface (Pydantic support)
│   ├── sheet_readers.py          # Cached Google Sheets interface
│   ├── sheet_writers.py          # Batch writes, archive-before-overwrite pattern
│   ├── schwab_client.py          # Read-only Schwab API wrapper (no order endpoints)
│   └── schwab_token_store.py     # GCS token read/write for OAuth flow
├── vault/
│   ├── theses/                   # _thesis.md files per position (~54 files)
│   ├── frameworks/               # Investment framework JSON files
│   └── transcripts/              # Podcast/earnings transcripts
├── scripts/
│   ├── schwab_initial_auth.py    # First-time OAuth flow
│   └── schwab_manual_reauth.py   # Recovery when refresh token expires (>7 days offline)
├── cloud_functions/token_refresh/ # GCP Cloud Function: Schwab token keep-alive (every 25 min)
├── PORTFOLIO_SHEET_SCHEMA.md     # Authoritative fingerprint & tab schema
└── CHANGELOG.md                  # Development history & current status
```

## Critical Infrastructure

### Schwab API Integration (Phase 4 — COMPLETE)

- Two Schwab apps: Accounts and Trading + Market Data
- Each app has its own OAuth token stored in `gs://portfolio-manager-tokens/{token_accounts.json, token_market.json}`
- Token refresh handled by Cloud Function `schwab-token-refresh` on a 24/7 every-25-minute Cloud Scheduler trigger
- CLI uses two scoped clients:
    - `utils/schwab_client.get_accounts_client()` → positions, balances, transactions
    - `utils/schwab_client.get_market_client()` → quotes, price history
- CSV upload remains as the explicit fallback path
- PROHIBITED endpoints (never imported anywhere):
    `place_order`, `replace_order`, `cancel_order`,
    `get_orders_for_account`, `get_orders_for_all_linked_accounts`
- Recovery procedures:
    - Token expired (offline > 7 days): `python scripts/schwab_manual_reauth.py`
    - Token missing (first setup or wiped): `python scripts/schwab_initial_auth.py`
- Alert channels:
    - `alert.json` in GCS → banner in Streamlit app sidebar
    - Gmail (after 2+ consecutive Cloud Function failures, ~50 min)

## Critical Guardrails (CRITICAL)
1. **No LLM Math:** All yields, drift %, tax dollar estimates, and projections MUST be calculated in Python. Pass facts to Gemini for narrative ONLY.
2. **Pydantic Schemas:** Every `ask_gemini` call must use a Pydantic `BaseModel` passed via `response_schema`. Never trust raw JSON strings.
3. **Style Short Codes:** Style fields always use short_code values from `styles.json` — `GARP`, `THEME`, `FUND`, `ETF`. Never use long-form names in code or schemas.
4. **Column Guard:** All DataFrames consumed by the UI or agents must pass through `utils.column_guard.ensure_display_columns`.
5. **PII Privacy:** Strip account numbers and specific account labels from all DataFrames before passing to LLM context.
6. **Dry Run Pattern:** All writes to Google Sheets must be gated by `config.DRY_RUN`.

## Data Standard: Fingerprints
| Tab | Format |
|---|---|
| Holdings_History | `import_date|ticker|quantity` |
| Daily_Snapshots | `import_date|pos_count|total_value` (rounded) |
| Transactions | `trade_date|ticker|action|net_amount` |

## Agent Kit (11 Live Agents)

All agents live in `agents/`. No deployment needed — run via `manager.py agent <name> [subcommand]`.
System prompts are editable `.txt` files in `agents/prompts/`. Every agent uses:
- Composite bundle input (immutable, hashed)
- Pydantic output schema with required `bundle_hash` field
- Sandboxed output to `Agent_Outputs` tab — never writes to `Target_Allocation`

| CLI command | Agent file | What it answers |
|---|---|---|
| `agent rebuy analyze` | rebuy_analyst.py | Scale-in candidates. Lynch GARP + Van Tharp sizing pre-computed. |
| `agent add-candidate --tickers X` | add_candidate_analyst.py | Fit and displacement for a new ticker. |
| `agent new-idea --tickers X,Y` | new_idea_screener.py | Screens comma-separated tickers against style buckets. |
| `agent tax analyze` | tax_agent.py | TLH candidates, wash-sale risk, drift rebalancing. |
| `agent valuation analyze` | valuation_agent.py | P/E signals, accumulation plans. Reads pre-baked fundamentals. |
| `agent concentration analyze` | concentration_hedger.py | Concentration flags + correlation hedges. |
| `agent macro analyze` | macro_cycle_agent.py | Carlota Perez cycle positioning + FRED/VIX triggers. |
| `agent thesis analyze` | thesis_screener.py | Goals → quantitative screens (Baid framework). |
| `agent bagger analyze` | bagger_screener.py | Mayer 100-bagger gate. Reads pre-baked fundamentals. |
| `agent behavioral analyze --trade-days 60` | behavioral_auditor.py | Audits last N days of trades vs. Housel principles. |
| `agent options run-agent` | Options_agent.py | Covered call suggestions. Blocked on Schwab /chains (Phase 6). |

**`analyze-all` orchestrator** runs rebuy + tax + valuation + concentration + macro + thesis + bagger + value in one pass:
```
python manager.py analyze-all --bundle latest        # dry run
python manager.py analyze-all --fresh-bundle         # rebuild bundles then run all
python manager.py analyze-all --bundle latest --live # write to Agent_Outputs
```
Note: `rebuy` is included in the manifest summary but uses a legacy write path — its rows are not in the standard `Agent_Outputs` batch write. `behavioral`, `add-candidate`, `new-idea`, and `options` must be run standalone.

## Vault Frameworks
Structured investment frameworks live in `vault/frameworks/`. Every file has `reviewed_by_bill: true` to be loadable by `agents/framework_selector.py`. Framework types:

| File | Type | Used by |
|---|---|---|
| `lynch_garp_v1.json` | `screening` | Re-buy Analyst — GARP rule evaluation |
| `joys_of_compounding_framework.json` | `screening` | Thesis Screener — Baid management scoring |
| `100_bagger_framework.json` | `screening` | Bagger Screener — Mayer quantitative gate |
| `van_tharp_position_sizing.json` | `position_sizing` | Re-buy Analyst — ATR-based 1R sizing |
| `psychology_of_money.json` | `behavioral` | Behavioral Auditor — Housel principle audit |
| `Macro_super_cycle_framework.md` | `macro` | Macro Cycle Agent — Carlota Perez positioning |

Note: `OptionsFramework.json` lives in `agents/` (not `vault/frameworks/`) — it was not migrated to the vault pattern.

**Van Tharp position sizing framework lives in `vault/frameworks/van_tharp_position_sizing.json`.** Agents pre-compute 1R, position_size_units, stop_loss_price, and trailing_stop by calling `agents.framework_selector.compute_van_tharp_sizing(atr_14, entry_price, portfolio_equity)`. Gemini NEVER computes position sizes, R-multiples, or stop levels. ATR data comes from `composite["calculated_technical_stops"]` (populated by `tasks/enrich_atr.py`). Note: `enrich_atr.py` uses a 2.5x ATR multiplier for protective stops; Van Tharp uses 3.0x for 1R (different concepts — do not conflate).

**Van Tharp sizing is pre-computed in `rebuy_analyst.py` before any LLM call.** The sizing is stored in `RebuyAnalystResponse.van_tharp_sizing_map` (dict keyed by ticker) and overwritten post-LLM to enforce Python-computed values. Agents cite sizing values from the bundle — they never calculate position sizes themselves. Run `tasks/enrich_atr.py` before any agent run that uses Van Tharp sizing.

## FMP Fundamentals — Architecture (COMPLETE)

`tasks/enrich_fundamentals.py` runs automatically on every `manager.py snapshot` (unconditional post-snapshot step, manager.py lines 403–413). It calls the three-tier lookup for every non-cash position and writes a `fundamentals` dict into each position in the market bundle, then re-hashes.

**Three-tier lookup in `utils/fmp_client.get_fundamentals()`:**
- Tier 0: Schwab `bundle_quote` fields (zero API cost — only for Schwab API snapshots)
- Tier 1: yfinance `fast_info` + `info` + `financials` (no API key, most fields covered)
- Tier 2: FMP `key-metrics-ttm` via 7-day file cache in `data/fmp_cache/` (rate-limited at 1.2s; skipped for ETFs/funds)

**Agents read from the pre-baked bundle — no live FMP calls at agent run-time:**
- `valuation_agent.py` reads `pos["fundamentals"]` for `trailing_pe`, `forward_pe`, `peg_ratio`, `52w_high`, `52w_low`
- `bagger_screener.py` reads `pos["fundamentals"]` for `roic`, `revenue_growth`, `gross_margin`, `payout_ratio`, `market_cap`
- Earnings surprises (`get_earnings_surprises_cached`) are still fetched live in valuation_agent — not pre-baked

**Pre-baked field names (snake_case):** `trailing_pe`, `forward_pe`, `peg_ratio`, `debt_to_equity`, `eps_ttm`, `market_cap` (raw USD), `dividend_yield`, `revenue_growth`, `earnings_growth`, `beta`, `gross_margin`, `roic`, `payout_ratio`, `pb_ratio`, `current_ratio`, `52w_high`, `52w_low`, `sector`, `industry`

## Typical Weekly Workflow
```bash
# 1. Rebuild bundles
python manager.py snapshot --live-api --cash 85000   # enrich_fundamentals runs automatically
python manager.py vault snapshot
python manager.py bundle composite

# 2. Pre-compute ATR stops (required for rebuy Van Tharp sizing)
python tasks/enrich_atr.py

# 3. Run all agents (dry run first)
python manager.py analyze-all --bundle latest

# 4. Promote to Sheet after reviewing bundles/runs/ output
python manager.py analyze-all --bundle latest --live

# 5. Standalone agents (run as needed)
python manager.py agent new-idea --tickers NVDA,ARM
python manager.py agent behavioral analyze --bundle latest --trade-days 60
```

## CLI Migration Status
- **Phase 1: Immutable Data Spine** — COMPLETE. `manager.py snapshot` freezes market state to SHA256-hashed bundles.
- **Phase 2: Vault Bundling** — COMPLETE. `manager.py vault snapshot` freezes qualitative context (theses, frameworks, transcripts).
- **Phase 3: Re-Buy Analyst** — COMPLETE. First agent on bundle interface; Lynch GARP + Van Tharp sizing.
- **Phase 4: Schwab API Source** — COMPLETE. Schwab API wired as primary source; `auto` mode with CSV fallback.
- **Phase 5: Agent Kit Completion** — SUBSTANTIALLY COMPLETE.
  - 10 of 11 agents live and wired into `manager.py`
  - `analyze-all` orchestrator runs 8 standard agents in one pass
  - Fundamentals pre-baked at snapshot time via `tasks/enrich_fundamentals.py` — agents read from bundle (zero live FMP calls at agent run-time)
  - Behavioral Auditor added (`agent behavioral analyze`) — Morgan Housel framework
  - Rotation pipeline added (`tasks/derive_rotations.py` + `journal promote`)
  - **Remaining:** Options agent blocked on Schwab `/chains` endpoint (Phase 6 data dependency); thesis backfill ongoing (~54 files, fill stubs for top 15 by weight)
- **Phase 6 (next):** Schwab `/chains` endpoint for options chain data → unblock `Options_agent.py`
