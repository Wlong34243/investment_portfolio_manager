# Investment Portfolio Manager — CLAUDE.md

## Project Identity
Streamlit web app for tracking, analyzing, and managing a ~$480K liquid investment portfolio (50+ positions). Ingests Schwab brokerage CSV exports, writes to Google Sheets, and provides AI-assisted research via 12 specialized agents. Companion system to the RE Property Manager (shared GCP project `re-property-manager-487122`).

## Technical Stack
- **Frontend:** Streamlit (Multi-page)
- **Database:** Google Sheets (via `gspread`)
- **Market Data:** yfinance, Financial Modeling Prep (FMP), Finnhub, FRED
- **AI:** Gemini 2.5 Flash (via `google-genai` SDK + Vertex ADC)
- **Model Isolation:** Python app → `gemini-2.5-flash` via `google-genai` + Vertex ADC. Dev assist → Gemini CLI with Code Assist free tier, auto-routed to Gemini 3. These are independent.
- **Guardrails:** Pydantic (Schema), Python-only Math, PII stripping

## Project Structure
```
investment-portfolio-manager/
├── app.py                        # Main Dashboard (KPIs, Treemap, Signals)
├── pages/                        # Navigation Pages
│   ├── 1_Rebalancing.py          # Tax-aware drift analysis
│   ├── 2_Research.py             # AI Research Hub (Tickers, Screener)
│   ├── 3_Performance.py          # Performance & Projections
│   ├── 4_Tax.py                  # TLH and realized G/L insights
│   ├── 5_Net_Worth.py            # Unified Liquid + RE Net Worth
│   └── 6_Advisor.py              # AI Portfolio Chat
├── pipeline.py                   # core data flow (Ingest -> Normal -> Write)
├── config.py                     # Centralized Column Maps & Constants
├── utils/
│   ├── agents/                   # 12 Specialized AI Agents (Pydantic enforced)
│   ├── column_guard.py           # Self-healing Title Case normalization
│   ├── validators.py             # Data quality squad (outlier detection)
│   ├── sheet_readers.py          # Cached Google Sheets interface
│   ├── enrichment.py             # Metadata & benchmark data
│   ├── risk.py                   # Beta & Correlation math
│   └── gemini_client.py          # Centralized LLM interface (Pydantic support)
├── PORTFOLIO_SHEET_SCHEMA.md     # Authoritative Fingerprint & Tab Schema
└── CHANGELOG.md                  # Development history & current status
```

## Critical Infrastructure

### Schwab API Integration (Phase 5-S)

- Two Schwab apps: Accounts and Trading + Market Data
- Each app has its own OAuth token, stored in
  `gs://portfolio-manager-tokens/{token_accounts.json, token_market.json}`
- Token refresh handled by Cloud Function `schwab-token-refresh`
  on a 24/7 every-25-minute Cloud Scheduler trigger
- Streamlit app uses two scoped clients:
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

Repo additions:
  `utils/schwab_client.py`
  `utils/schwab_token_store.py`
  `scripts/schwab_initial_auth.py`
  `scripts/schwab_manual_reauth.py`
  `cloud_functions/token_refresh/main.py`
  `cloud_functions/token_refresh/requirements.txt`
  `cloud_functions/token_refresh/deploy.sh`

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

## Specialized AI Agents (The 12-Agent Squad)
- **Grand Strategist:** Cross-portfolio allocation (Liquid + RE).
- **Tax Intelligence:** Rebalancing & Loss Harvesting (TLH).
- **Valuation Agent:** Multi-year P/E and accumulation plans.
- **Thesis Screener:** Translates English goals into quantitative screens.
- **Price Narrator:** Explains significant daily movements via news catalysts.
- **Macro Monitor:** Connects FRED/VIX data to portfolio triggers.
- **Options Agent:** Covered call strategies (OTM 5-15%).
- ... (and 5 others covering Earnings, Concentration, Correlation, Cash, and Technicals)

## Vault Frameworks
Structured investment frameworks live in `vault/frameworks/`. Every file has `reviewed_by_bill: true` to be loadable by `agents/framework_selector.py`. Framework types:

| File | Type | Used by |
|---|---|---|
| `lynch_garp_v1.json` | `screening` | Re-buy Analyst — GARP rule evaluation |
| `joys_of_compounding_framework.json` | `screening` | Thesis Screener — Baid management scoring |
| `100_bagger_framework.json` | `screening` | Bagger Screener — Mayer quantitative gate |
| `van_tharp_position_sizing.json` | `position_sizing` | All agents — ATR-based 1R sizing |
| `psychology_of_money.json` | `behavioral` | Behavioral Auditor — Housel principle audit |

**Van Tharp position sizing framework lives in `vault/frameworks/van_tharp_position_sizing.json`.** Agents pre-compute 1R, position_size_units, stop_loss_price, and trailing_stop by calling `agents.framework_selector.compute_van_tharp_sizing(atr_14, entry_price, portfolio_equity)`. Gemini NEVER computes position sizes, R-multiples, or stop levels. ATR data comes from `composite["calculated_technical_stops"]` (populated by `tasks/enrich_atr.py`). Note: `enrich_atr.py` uses a 2.5x ATR multiplier for protective stops; Van Tharp uses 3.0x for 1R (different concepts — do not conflate).

**Van Tharp sizing is pre-computed in `rebuy_analyst.py` before any LLM call.** The sizing is stored in `RebuyAnalystResponse.van_tharp_sizing_map` (dict keyed by ticker) and overwritten post-LLM to enforce Python-computed values. Agents cite sizing values from the bundle — they never calculate position sizes themselves. Run `tasks/enrich_atr.py` before any agent run that uses Van Tharp sizing.

## Workflow Rules
- **Standard:** Use `git status` before committing.
- **Standard:** Update `CHANGELOG.md` with every working milestone.
- **Performance:** Use `ws.col_values()` for fingerprint checks instead of full sheet reads.
- **Visuals:** Prefer Treemaps for allocation; use `st.toast` for transient notifications.
- **Pricing:** Trust ingested CSV/API price during ingestion; avoid redundant yfinance refreshes in `enrich_positions`.

## FMP Data — Known Architectural Debt
FMP fundamentals (`pe_ratio`, `peg_ratio`, `debt_to_equity`) are fetched live by agents at run-time via `utils/fmp_client.get_fundamentals()`. With 50+ positions this fires 50+ sequential HTTP calls and reliably hits the free-tier rate limit (429).

**Short-term mitigations in place:**
- Module-level rate limiter in `fmp_client._fmp_rate_limit()`: 1.2s minimum between HTTP calls (cache hits bypass)
- 7-day file cache in `data/fmp_cache/`: repeated runs within a week skip FMP entirely
- Three-tier `get_fundamentals()`: Tier 0 = Schwab bundle_quote → Tier 1 = yfinance → Tier 2 = FMP (only for fields yfinance returned None)

**Correct fix (deferred — `tasks/enrich_fmp.py`):** FMP data should be fetched ONCE during `manager.py snapshot` and baked into bundle positions as fields. Agents then read from the bundle — zero API calls at agent-run time. The `bundle_quote` parameter on `get_fundamentals()` is the scaffold for this path.

## CLI Migration Status
- **Phase 1: Immutable Data Spine** — COMPLETE. `manager.py snapshot` freezes market state to SHA256-hashed bundles.
- **Phase 2: Vault Bundling** — COMPLETE. `manager.py vault snapshot` freezes qualitative context (theses).
- **Phase 3: Re-Buy Analyst** — COMPLETE. First agent ported to bundle interface; Peter Lynch GARP framework integrated.
- **Phase 4: Schwab API Source** — COMPLETE. Schwab API wired as pluggable data source; `auto` mode defaults to API with CSV fallback.
- **Phase 5: Agent Kit Completion** — IN PROGRESS.
  - Behavioral Auditor added (`agent behavioral analyze`) — Morgan Housel framework
  - Rotation pipeline added (`tasks/derive_rotations.py` + `journal promote`)
  - FMP 429 mitigated (rate limiter + yfinance-first tier); correct fix (`tasks/enrich_fmp.py`) still pending
  - `analyze-all --fresh-bundle` `model_dump()` bug fixed
  - **NEXT:** `tasks/enrich_fmp.py` — bake FMP fundamentals into bundle at snapshot time
