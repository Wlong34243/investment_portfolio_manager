# Investment Portfolio Manager — CLAUDE.md

## Project Identity

A headless Python CLI system that produces **clean, deterministic portfolio data** and hands it off to external LLMs (Claude, GPT-5) for reasoning. Python owns the pipeline; Google Sheets is the dashboard; external frontier models handle the thinking.

**Architectural philosophy (April 2026 pivot):**
> **APIs calculate locally. LLMs reason externally.**

Bill is the reasoning engine. The software's job is to feed him high-signal data with zero friction. Autonomous local agents were decommissioned because maintaining agent logic, Pydantic schemas, prompt files, and orchestration was distracting from actual investing. Frontier models accessed via copy-paste give higher-quality reasoning at a fraction of the maintenance cost.

Companion system to the RE Property Manager (shared GCP project `re-property-manager-487122`).

---

## The Pivot: What Changed and Why

### What was removed (stashed in `deprecated/`)

- **The 12-agent squad** — Valuation Agent, Thesis Screener, New Idea Screener, Re-Buy Analyst, Add-Candidate, Tax Agent, Concentration Hedger, Macro-Cycle, Bagger Screener, Behavioral Auditor, Value Investing Screener, Options Agent
- **The nine-file agent kit** (never built, cancelled in planning)
- **Vault framework loader** (`agents/framework_selector.py`) and framework JSONs
- **Van Tharp pre-computation layer** (math stays in `utils/risk.py`; agent integration is gone)
- **Disagreements tab** and agent cross-validation logic
- **Podcast pipeline's Gemini summarizer + sandbox writer + GitHub Actions cron** (transcript fetching kept; summarization moved to external LLM via export)
- **`analyze-all` command and `agent` Typer group**

### What stayed and hardened

- **Schwab API integration** — positions, balances, transactions, quotes, price history
- **Bundle system** — immutable, SHA256-hashed snapshots (`core/bundle.py`, `core/composite_bundle.py`, `core/vault_bundle.py`)
- **Enrichment tasks** — ATR, technicals, fundamentals (now all default-on in `snapshot`)
- **Google Sheets writers** — single-batch, fingerprint-deduped, archive-before-overwrite
- **Dashboard tabs** — `Valuation_Card`, `Decision_View`, `Holdings_Current`, `Daily_Snapshots`, `Transactions`
- **GCP token keep-alive** — Cloud Function + Scheduler, GCS token storage
- **Thesis files** (`vault/theses/{TICKER}_thesis.md`) — now consumed by the export engine, not agents

### What's new

- **Dashboard color-coding** in `tasks/format_sheets_dashboard_v2.py` (Phase 2)
- **Tax module** — `Tax_Control` tab + `tax-impact` CLI command (Phase 3)
- **Export engine** — `manager.py export position|portfolio|etfs|podcast-digest|tax-position` (Phase 4)
- **`manager.py health` command** — single-command pipeline health check (Phase 1)
- **`tasks/enrich_fmp.py`** — bakes FMP fundamentals into the bundle at snapshot time (Phase 1)
- **Tax-lot ingestion in `core/bundle.py`** — pulls Schwab lot detail at snapshot time (Phase 1, prerequisite for Phase 3)

---

## User

**Bill (Primary & Only User)**
- CPA/CISA, intermediate Python, uses Claude Code and Gemini CLI for development
- Solo operator. No multi-user, no remote dashboard needs
- Runs the system locally: `python manager.py ...`
- Knows the thesis behind every current position — thesis files are drift anchors, not discovery tools

## Investment Philosophy & Style

Bill's investment approach spans four natural styles, codified in `styles.json`:

1. **GARP-by-intuition** — undervalued companies with strong product/market understanding
2. **Thematic Specialists** — buying market position over company quality
3. **Boring Fundamentals + dip-buying** — low P/E, long profitability, fear-driven discounts
4. **Sector/Thematic ETFs** — macro expressions, broad index and bond ETFs as ballast

**Risk management is built around small-step scaling in and out**, not binary entries/exits. Exits are almost always **rotations** funding something perceived as better. The **rotation is the unit of analysis** — Trade_Log captures linked sell-buy pairs with an explicit implicit bet.

---

## Portfolio Snapshot (current)

- ~$550K total value, 50+ positions + strategic cash
- Heavy tech, energy, healthcare, selective international
- Top 10 concentrations: UNH (~9%), GOOG, JPIE, AMZN, QQQM, VEA, XOM, IGV, XBI, IFRA
- Meaningful strategic cash position (manual entry, money market ~4.5% yield)
- **Excluded from beta/allocation calcs:** `QACDS`, `CASH_MANUAL`

---

## Architecture: The Spine

### Core principle: "APIs calculate locally, LLMs reason externally"

Python gathers all data deterministically. Data is hash-fingerprinted, written to Sheets, and exportable as clean Markdown for paste into frontier LLMs. No local LLM reasoning layer.

### Data flow

```text
┌────────────────────┐   ┌──────────────────┐   ┌───────────────────┐
│ Schwab API (live)  │──▶│                  │──▶│ Google Sheets     │
│ or CSV (fallback)  │   │   manager.py     │   │ (dashboard w/     │
└────────────────────┘   │   CLI spine      │   │  color-coding +   │
┌────────────────────┐   │                  │   │  Tax_Control)     │
│ yFinance / FMP     │──▶│  • core/bundle   │   └───────────────────┘
└────────────────────┘   │  • tasks/*       │            │
┌────────────────────┐   │  • export/*      │            ▼
│ YouTube transcripts│──▶│                  │   ┌───────────────────┐
└────────────────────┘   │  DRY_RUN=true    │──▶│ Export Engine     │
                         │  by default      │   │ (Markdown → clip) │
                         └──────────────────┘   └───────────────────┘
                                                         │
                                                         ▼
                                                ┌───────────────────┐
                                                │ External LLM      │
                                                │ (Claude / GPT-5)  │
                                                │ — paste & reason  │
                                                └───────────────────┘
```

### Pipeline stages

```text
Ingest → Enrich (ATR, technicals, FMP, tax lots) → Bundle (hashed, immutable) →
  Sheet write (color-coded) → Export on demand → External LLM conversation
```

---

## Technical Stack

### Core
- **Language:** Python
- **Execution:** Local CLI (`python manager.py ...`); headless
- **Data store:** Google Sheets via `gspread` (single-batch writes, fingerprint dedup)
- **Clipboard:** `pyperclip` for export → paste workflow
- **Auth:** ADC (Application Default Credentials) as primary path

### Key files

```
investment-portfolio-manager/
├── manager.py                    # Main CLI entry point (Typer + Rich)
├── config.py                     # Centralized constants & column maps
├── core/
│   ├── bundle.py                 # Market bundle (Schwab API / CSV) + tax lots
│   ├── vault_bundle.py           # Vault bundle (theses)
│   └── composite_bundle.py       # Composite bundle (market + vault)
├── tasks/
│   ├── enrich_atr.py             # ATR 14-day stops
│   ├── enrich_technicals.py      # MA/RSI/MACD/volume (Murphy TA)
│   ├── enrich_fundamentals.py    # Tiered P/E enrichment
│   ├── enrich_fmp.py             # FMP fundamentals baked into bundle  [Phase 1]
│   ├── build_valuation_card.py   # Valuation_Card tab refresh
│   ├── build_decision_view.py    # Decision_View tab refresh
│   ├── build_tax_control.py      # Tax_Control tab refresh             [Phase 3]
│   ├── sync_transactions.py      # Schwab transaction history → Sheets
│   ├── derive_rotations.py       # Group trades into rotation events
│   └── format_sheets_dashboard_v2.py  # Color-coded formatting
├── export/                       # [Phase 4]
│   ├── position.py               # Single-ticker deep dive
│   ├── tax_position.py           # Single-ticker, lot-level tax detail
│   ├── portfolio.py              # Macro view export
│   ├── etfs.py                   # ETF-filtered export
│   └── podcast_digest.py         # Transcript aggregation
├── utils/
│   ├── schwab_client.py          # OAuth2 client (read-only, enforced)
│   ├── schwab_token_store.py     # GCS token storage
│   ├── fmp_client.py             # FMP fundamentals (14-day cache)
│   ├── sheet_readers.py          # Three-way credential resolution
│   ├── sheet_writers.py          # Archive-before-overwrite writes
│   ├── column_guard.py           # Title Case normalization
│   ├── risk.py                   # Beta, VaR, correlation math
│   ├── tax.py                    # Tax-lot math, wash sale, cap gains   [Phase 3]
│   └── formatters.py             # Markdown table generation for exports
├── vault/
│   └── theses/                   # TICKER_thesis.md (~30+ positions, backfill ongoing)
├── scripts/                      # Schwab auth, debugging utilities
├── cloud_functions/
│   └── token_refresh/            # GCP Cloud Function for Schwab tokens
├── bundles/                      # Immutable JSON snapshots (git-ignored)
├── data/
│   ├── fmp_cache/                # 14-day FMP response cache
│   └── podcast_transcripts/      # YouTube transcript files
├── deprecated/                   # Stashed agent layer — do not import
│   ├── agents/                   # 12-agent squad (reference only)
│   ├── frameworks/               # Vault framework JSONs
│   └── podcast_gemini_summarizer/  # Old automated summarization
├── PORTFOLIO_SHEET_SCHEMA.md     # Sheet schema & fingerprint standard
├── CHANGELOG.md                  # Development history
└── CLAUDE.md                     # This file
```

---

## Critical Guardrails

1. **No LLM reasoning in Python.** Every local computation is deterministic. No `ask_gemini()` calls in the production path. The only LLM in the pipeline is Claude/GPT-5, invoked manually by Bill via paste.
2. **No trading.** Schwab integration is read-only. `place_order`, `replace_order`, `cancel_order`, `get_orders_*` are **never imported anywhere**. This is enforced by convention and review, not runtime checks — but the convention is absolute.
3. **DRY_RUN defaults true.** All writes to Google Sheets require an explicit `--live` flag.
4. **Sheet is not the source of truth for AI output.** There is no AI output. `Target_Allocation` is Bill's manual edit; `AI_Suggested_Allocation` tab is retired (delete on next Sheet cleanup).
5. **Bundles are immutable.** Any enrichment that mutates a bundle re-hashes and rewrites it. Never edit a bundle in place without rehashing.
6. **Exports carry provenance.** Every export begins with bundle hash, timestamp, data source, and cache ages.
7. **Tax math is a planning aid, not a filing.** All `Tax_Control` numbers are estimates at config-set marginal rates. Authoritative tax figures come from the Schwab 1099 at year-end.

---

## Data Sources

### Schwab Developer API (primary)

- Two Schwab apps: Accounts and Trading + Market Data
- Tokens in `gs://portfolio-manager-tokens/{token_accounts.json, token_market.json}`
- Cloud Function `schwab-token-refresh` runs every 25 min (Cloud Scheduler)
- Scoped clients:
    - `utils/schwab_client.get_accounts_client()` → positions, balances, transactions, **tax lots** (Phase 1)
    - `utils/schwab_client.get_market_client()` → quotes, price history
- **Known issue:** transaction sync flaky — fix in Phase 1
- CSV fallback preserved in `utils/csv_parser.py` (ported from Colab V3.2)

### Market & fundamental data

- **yFinance** — primary source for prices, sector, dividend yield, beta, and most fundamentals
- **FMP (free tier)** — fill-in only for fields yfinance can't provide (forward P/E, PEG, select three-statement). 14-day cache on disk (`data/fmp_cache/`). Rate limiter: 1.2s between calls. Bake fundamentals into bundle at snapshot time (`tasks/enrich_fmp.py`) so consumers read from bundle, not live API.
- **Finnhub** — news (used in exports only)

### Podcast transcripts

- YouTube RSS → `youtube-transcript-api` → plain text files in `data/podcast_transcripts/`
- Fetcher runs on-demand; no automated LLM summarization
- `manager.py export podcast-digest` aggregates the most recent ~4 weeks for paste into external LLM

---

## CLI Surface

The CLI is split between **shipped today**, **planned by phase**, and **deferred / optional**. Anything marked `[planned]` is part of the agreed roadmap but not yet built; anything marked `[deferred]` is not committed.

### Shipped today

```bash
python manager.py snapshot --source auto              # Freeze market state + enrichments
python manager.py snapshot --source csv --csv ...     # CSV fallback path
python manager.py dashboard refresh --update --live   # Pull Schwab + refresh dashboard
python manager.py bundle composite                    # Build composite bundle
python manager.py bundle verify                       # Verify latest bundle integrity
python manager.py vault snapshot                      # Freeze theses to vault bundle
python manager.py vault add-thesis TICKER             # Create/open thesis file
python manager.py vault thesis-audit                  # Report thesis coverage
python manager.py journal promote                     # Promote Trade_Log_Staging → Trade_Log
python manager.py journal rotation                    # Record a sell-buy rotation
```

### Phase 1 — Pipeline hardening [planned]

```bash
python manager.py health                              # Pipeline health check
# Plus: snapshot now ingests tax lots by default; transaction sync hardened.
```

### Phase 3 — Tax module [planned]

```bash
python manager.py tax-impact TICKER QTY               # Pre-trade tax impact for a sell
python manager.py tax status                          # Print current YTD tax posture to console
# Plus: Tax_Control tab is built/refreshed inside dashboard refresh.
```

### Phase 4 — Export engine [planned]

```bash
python manager.py export position TICKER              # Single-position deep dive
python manager.py export tax-position TICKER          # Position + lot-level tax detail
python manager.py export portfolio                    # Macro view
python manager.py export etfs                         # ETF-filtered
python manager.py export podcast-digest               # 4-week transcript aggregation
```

All write operations require `--live`. Default is DRY RUN. All export commands write to stdout **and** copy to clipboard via `pyperclip`.

---

## Dashboard Design (Google Sheets)

The Sheet is a **read-optimized control panel**, not a data lake. It answers three questions at a glance, in this order:

1. **What's broken?** Data staleness, a position that looks wrong, a stop triggered, a tax surprise brewing.
2. **What's moving?** What changed since yesterday — price, weight, technical signal, income profile.
3. **What's interesting?** Positions where fundamentals and technicals disagree, positions near key levels, rotations and tax angles worth thinking about.

All tabs are populated from immutable bundles and are safe to overwrite from the CLI; manual edit zones are explicitly marked.

### Global dashboard rules

- **Single source of truth.** All computed fields originate from the latest composite bundle or normalized transaction data; no formulas are hand-edited outside `Config` and clearly marked manual columns.
- **Idempotent writes.** All writes are single-batch and fingerprint-deduped; append-only tabs (`Holdings_History`, `Daily_Snapshots`, `Transactions`, `RealizedGL`, `IncomeTracking`) use fingerprint columns to prevent double ingestion.
- **Time semantics.** "Today vs prior" comparisons are bundle-to-bundle (latest vs most recent prior snapshot), not intra-day Schwab ticks.
- **Config-driven thresholds.** Any alert or color (RSI bands, MA200 proximity, drift, concentration, cash yield assumptions, tax rates) reads its parameters from the `Config` tab.

---

### Holdings_Current — live positions pane

**Purpose:** Current truth for positions, weights, styles, and drift vs target. This is the "is anything structurally off?" starting point.

**Key fields (illustrative):**

- Identity: `Ticker`, `Name`, `Account`, `Asset Class`, `Style` (GARP / THEME / FUND / ETF).
- Size: `Quantity`, `Price`, `Market Value`, `Weight % of Portfolio`.
- Targeting: `Target_Weight %` (from `Target_Allocation`), `Drift %` (Weight – Target).
- Risk / meta: `Beta`, `Sector`, `Country`, `Yield %`, `Projected Annual Income`.

**Visual rules:**

- **Concentration alert.** Red background when `Weight %` > 8% for a single name (configurable).
- **Drift alert.** Red background when `|Drift %|` > 5% from target; yellow when between 3–5%.
- **Excluded tickers.** Positions flagged as excluded (`QACDS`, `CASH_MANUAL`, etc.) are greyed out and omitted from beta/allocation calcs but still shown for awareness.

**Behavior:** `python manager.py dashboard refresh --update --live` rewrites the table from the latest bundle in a single batch. No formulas or filters are required to interpret core fields; sorting is allowed but not relied on in code.

---

### Holdings_History & Daily_Snapshots — longitudinal spine

**Holdings_History**

- **Purpose:** Position-level history for forensic analysis and rotation reconstruction.
- **Append-only:** One row per snapshot per ticker; fingerprint `import_date|ticker|quantity`.

**Daily_Snapshots**

- **Purpose:** Portfolio-level time series: size, count, and risk metrics by day.
- **Append-only:** Fingerprint `import_date|pos_count|total_value` (rounded).
- **Columns:** `Date`, `Total Value`, `Pos Count`, `Cash %`, `Portfolio Beta`, `Top Position Conc %`, `Top Sector`, `Estimated VaR 95`, `Stress -10 Impact`, `Fingerprint`.

These tabs are inputs for exports and audits, not day-to-day reading surfaces.

---

### Transactions, Trade_Log_Staging, Trade_Log — rotation pipeline

**Transactions**

- **Purpose:** Raw Schwab transaction feed normalized into a tab-safe schema.
- **Source:** `tasks/sync_transactions.py` (Schwab API primary, CSV fallback).
- **Fingerprint:** `trade_date|ticker|action|net_amount`.

**Trade_Log_Staging**

- **Purpose:** Automatically derived candidate rotations — sell–buy clusters over a time window, grouped and tagged.
- **Source:** `tasks/derive_rotations.py`.

**Trade_Log**

- **Purpose:** Curated journal of actual rotations, used as the unit of analysis in exports and external LLM conversations.
- **Population:** `python manager.py journal promote` copies rows from `Trade_Log_Staging` after manual review, optionally adding reasoning notes.

The rotation is the unit of analysis; these tabs answer "What did I actually do?" and feed realized P/L and thesis drift review.

---

### Target_Allocation — manual intent layer

**Purpose:** Human macro and style intent, used to compute drift and rebalance signals.

**Columns (current pattern):**

- `Asset Class`, `Asset Strategy`, `Target %`, `Min %`, `Max %`, `Notes`.

This tab is **manual edit only**; code may only read it. `Holdings_Current` joins on `Asset Class` / style to compute drift and color-coded concentration.

---

### Valuation_Card — valuation × trend grid

**Purpose:** "Is this cheap/rich against its trajectory?" panel for individual tickers.

**Core columns:**

- Valuation: `P/E`, `Forward P/E (FMP)`, `PEG`, `Dividend Yield`, `Valuation_Signal` (CHEAP / FAIR / RICH / MONITOR).
- Trend: `MA50`, `MA200`, `RSI`, `MACD_Signal`, `52w_high`, `52w_low`, `Trend_Signal` (UP / DOWN / NEUTRAL / EXTREME).
- Meta: `Ticker`, `Sector`, `Style`.

**Color rules (2×2 grid):**

- CHEAP + DOWN → deep yellow (dip-buy candidate).
- CHEAP + UP → light green (value catching a bid).
- RICH + UP → light red (trim candidate).
- RICH + DOWN → bold red (exit/thesis-check candidate).

Built exclusively by `tasks/build_valuation_card.py` from the latest composite bundle plus FMP enrichment; if fundamentals are incomplete (e.g., some ETFs), the row is marked `MONITOR` and greyed out rather than forced into the 2×2.

---

### Decision_View — 30-second primary dashboard

**Purpose:** Single page answer to "What's broken / moving / interesting?" using a tight subset of fields from multiple tabs.

**Inputs:** Joins across `Holdings_Current`, `Valuation_Card`, technical enrichments, risk metrics, and tax/timing flags.

**Suggested columns:**

- Identity: `Ticker`, `Name`, `Sector`, `Style`.
- Status: `Thesis_Status` (OK / DRIFT / MISSING), `Stop_Status` (Above / Hit / Not Set).
- Movement: `1d Price %`, `5d Price %`, `Weight %`, `Weight Δ vs prior snapshot`.
- Technicals: `RSI`, `RSI_Bucket`, `Price vs MA200 %`, `Below_MA200?`, `MA200_Proximity_Bucket`.
- Valuation: `Valuation_Signal`, `Valuation×Trend_Quadrant`.
- Tax hints: `Tax_Pressure_Flag` (e.g., large unrealized ST gains), `Rotation_Flag` (name appears in recent rotations).
- Flags: `Alerts` (comma list: CONC, DRIFT, STOP, DATA_STALE, THESIS_MISSING, TAX).

**Color rules (implemented in `tasks/format_sheets_dashboard_v2.py`):**

- **RSI traffic light (`Decision_View`).**
  - Green fill for RSI ≤ 30 (oversold).
  - White/neutral for 30–70.
  - Red fill for RSI ≥ 70 (overbought).
- **MA200 proximity (`Decision_View`).**
  - Bold red text if price < MA200.
  - Light green background if price within +3% of MA200.
  - White otherwise.
- Any row with non-empty `Alerts` gets a subtle left-edge band to visually separate "actionable" names from background noise.

Built only via `tasks/build_decision_view.py`; manual edits are discouraged except for temporary filters/sorts during review. Target <150 rows and <25 columns to keep it human-scannable.

---

### Tax_Control — tax situation at a glance

**Purpose:** Compact tax-state view: realized gains/losses, wash-sale drag, and a single "thinking number" for estimated capital-gains tax.

**Sources:**

- `RealizedGL` sheet: per-trade `Gain Loss`, `LT Gain Loss`, `ST Gain Loss`, `Term`, `Wash Sale`, `Disallowed Loss`.
- `Config` sheet: `taxrateshortterm`, `taxratelongterm`.

**Core aggregates:**

- `YTD_Realized_ST_Gains` / `YTD_Realized_ST_Losses`.
- `YTD_Realized_LT_Gains` / `YTD_Realized_LT_Losses`.
- `YTD_Net_ST` and `YTD_Net_LT` (netted separately).
- `YTD_Disallowed_Wash_Loss` and `Wash_Sale_Count`.
- `Net_Taxable_Capital_Gain_Est` (positive net ST + positive net LT only).
- `Estimated_Federal_CapGains_Tax` (config rates applied to positive nets only).

**Tax math rules:**

- Short-term and long-term realized results are computed by summing per-trade `ST Gain Loss` and `LT Gain Loss` from `RealizedGL`; rows marked as wash sales still contribute to realized results but their **Disallowed Loss** is tracked separately and not treated as currently deductible.
- Estimated tax uses `Config.taxrateshortterm` on positive `YTD_Net_ST` and `Config.taxratelongterm` on positive `YTD_Net_LT`, then sums the two; negative nets are treated as zero in this estimate to avoid showing a negative tax.
- A simple `Tax_Offset_Capacity` field can present how much remaining realized gain could still be fully offset if additional losses were harvested.

**Visual layout:**

- Top row: 4 KPI-style cells — `YTD_Net_ST`, `YTD_Net_LT`, `YTD_Disallowed_Wash_Loss`, `Estimated_Federal_CapGains_Tax`.
- Middle row: small bridge-style summary — ST gains vs ST losses, LT gains vs LT losses.
- Bottom table: top realized rows by magnitude and any wash-sale rows, for quick drill-in when something looks off.

Color is restrained: red for wash-sale/disallowed-loss and large current tax, green for usable loss offsets, amber for "watch" conditions such as rising short-term gains.

---

### IncomeTracking, RiskMetrics, Research, Config

**IncomeTracking**

- **Purpose:** Track projected annual portfolio income, blended yield, and top income generators over time.
- **Columns:** `Date`, `Projected Annual Income`, `Blended Yield`, `Top Generator Ticker`, `Top Generator Income`, `Cash Yield Contribution`, `Fingerprint`.

**RiskMetrics**

- **Purpose:** Summarize daily risk posture: beta, top position/sector concentration, VaR, stress scenarios.
- **Columns:** `Date`, `Portfolio Beta`, `Top Position Conc`, `Top Position Ticker`, `Top Sector Conc`, `Top Sector`, `Estimated VaR 95`, `Stress -10 Impact`, `Fingerprint`.

**Research**

- **Purpose:** Freeform scratchpad and notes. Code must never write here; this is manual-only space.

**Config**

- **Purpose:** Central parameter registry for the entire dashboard.
- Example keys: `rebalancethresholdpct`, `cashyieldpct`, `benchmarkticker`, `taxrateshortterm`, `taxratelongterm`, `riskfreerate`, `marketpremium`.

---

### Retired / legacy tabs

- `AI_Suggested_Allocation`, `Disagreements`, and any legacy agent-driven views are deprecated; they should not be referenced by any current CLI task or export and can be deleted or archived on the next Sheet cleanup.

---

## Export Engine

The export engine is the replacement for the local agent layer. Each command produces a self-contained Markdown block, written to stdout **and** copied to clipboard. Bill alt-tabs to Claude/GPT-5 and pastes.

### Design rules

- **Single output** per command: Markdown to stdout + clipboard (`pyperclip`).
- **Every export starts with a provenance header:** bundle hash, timestamp, Schwab data source, FMP cache ages.
- **Every export ends with `## Your question`** — empty section, forces Bill to ask something specific.
- **No LLM-generated commentary in any export.** Pure data + verbatim thesis files.
- **Token-conscious:** target <20K tokens per export to keep LLM conversations snappy.

### The five exports

| Command | Contents |
|---|---|
| `export position TICKER` | Current state (price, weight, cost basis, unrealized G/L), FMP fundamentals, technicals (MA50/200, RSI, MACD, 52w high/low), dividend history, full realized G/L for this ticker, verbatim thesis file |
| `export tax-position TICKER` | Same as `export position` plus lot-level detail and a "tax character of various sell sizes" table |
| `export portfolio` | Total value, cash %, top 10 by weight, sector allocation, style allocation (GARP/THEME/FUND/ETF), beta, correlation clusters >\|0.5\|, drift summary, RSI extremes, positions below MA200, Tax_Control KPIs |
| `export etfs` | Filtered view of all `style == ETF` positions with full fields |
| `export podcast-digest` | Concatenated transcripts from last 4 weeks, source+date headers, no summarization |

### Standard external prompts (kept outside the codebase)

Bill maintains a small set of standardized prompts in a personal notes doc — not in the repo. The repo's job is to produce the data; the prompts are Bill's tools. Examples:

- *Position review:* "Here is my current state on [TICKER]. Given my thesis and the current data, what are the strongest arguments for adding, trimming, or holding? What would make you change your mind?"
- *Portfolio review:* "Here is my portfolio state. What risks am I underpricing? What concentrations should I be thinking about? What does my allocation say about my implicit macro view?"
- *Rotation check:* "I'm considering selling [A] to fund [B]. Here is the data on both. Is this a coherent rotation?"
- *Tax review:* "Here is my YTD tax posture and current candidate sells. What sequencing would minimize tax drag without distorting the investment thesis?"

---

## Data Standard: Fingerprints

| Tab | Format |
|---|---|
| `Holdings_History` | `import_date\|ticker\|quantity` |
| `Daily_Snapshots` | `import_date\|pos_count\|total_value` (rounded) |
| `Transactions` | `trade_date\|ticker\|action\|net_amount` |
| `RealizedGL` | `trade_date\|ticker\|action\|net_amount\|gain_loss` |
| `IncomeTracking` | `date\|projected_annual_income` (rounded) |

All append operations use fingerprint-based deduplication for idempotency. Fingerprints include timestamp where collision is possible.

---

## Workflow Rules

- **Standard:** Run `python manager.py health` before every export session.
- **Standard:** Use `git status` before committing.
- **Standard:** Update `CHANGELOG.md` with every working milestone.
- **Standard:** DRY RUN → verify → `--live` promotion sequence for all Sheet-mutating operations.
- **Performance:** Use `ws.col_values()` for fingerprint checks instead of full sheet reads.
- **Pricing:** Trust ingested CSV/API price during ingestion; avoid redundant yfinance refreshes.

---

## What This System Is Not

- **Not a trading system.** No order endpoints, ever.
- **Not an autonomous analyst.** No local LLM reasoning layer. All reasoning is done by Bill, assisted by external frontier models via paste.
- **Not a Streamlit app.** Deprioritized. Local CLI + Google Sheets is the default.
- **Not real-time.** Snapshots are immutable and on-demand. Intra-day decisions use the Schwab UI directly. No push notifications, no scanners, no alert daemons.
- **Not multi-user.** Single operator, local execution.
- **Not a tax filing tool.** `Tax_Control` is a planning aid; the Schwab 1099 is authoritative at year-end.

---

## Phased Roadmap

| Phase | Scope | Gate to next phase |
|---|---|---|
| **0** | Decommission agent layer + podcast automation to `deprecated/` | `manager.py snapshot` runs end-to-end with no agent imports |
| **1** | Pipeline hardening: transaction sync fix, FMP bake-in, tax-lot ingestion, `health` command | Three clean dashboard refreshes on three different days, zero manual intervention |
| **2** | Dashboard color-coding (RSI traffic light, MA200 proximity, Valuation×Trend 2×2, concentration & drift) | 30-second-glance test passes — Bill can name 3-5 attention-worthy positions without sorting |
| **3** | Tax module: `Tax_Control` tab, `tax-impact` command, wash-sale visibility | Estimated federal cap-gains tax number is trusted for planning at a glance; wash-sale disallowed loss surfaced as a KPI |
| **4** | Export engine + thesis backfill for stragglers | Used in 3 real trade decisions; theses current for all positions >2% weight |
| **5** | Deferred / optional | Unified net worth view across RE + liquid; possible Looker Studio dashboard if Phase 2 proves insufficient (likely unnecessary) |

**Gating rule:** Phase N+1 does not start until Phase N is *boring* — repeatable, reliable, requires no thinking to operate.

---

## Success Criteria

- [x] Colab V3.2 logic absorbed
- [x] Schwab API integrated (positions solid)
- [x] Bundle system with SHA256 hashing
- [x] GCP token keep-alive deployed
- [ ] **Phase 0:** Agent layer + podcast automation decommissioned to `deprecated/`
- [ ] **Phase 1:** Transaction sync reliable; FMP baked into bundle; tax-lot ingestion live; `health` command works
- [ ] **Phase 2:** Dashboard color-coding live; 30-second-glance test passes
- [ ] **Phase 3:** `Tax_Control` live; estimated-tax number trusted for planning at a glance; wash-sale disallowed loss surfaced as a KPI
- [ ] **Phase 4:** Export engine shipped; used in 3 real trade decisions; thesis files backfilled for all positions >2% weight
- [ ] Unified net worth view across RE + liquid (deferred)

---

## Quick Reference

- **Portfolio size:** ~$550K across 50+ positions + strategic cash
- **Primary data path:** Schwab API; CSV fallback retained
- **Execution model:** Local CLI (`python manager.py`)
- **Dashboard:** Google Sheets (color-coded, with `Tax_Control` Phase 3+)
- **Reasoning:** External LLM via manual paste from export engine
- **Sheet ID:** `1DuY68xVvyHq-0dyb7XUQgcoK7fqcVS0fv7UoGdTnfxA`
- **GCP Project:** `re-property-manager-487122`
- **Reserve account (separate project):** Schwab ...8895, RE Property Manager `Reserve_Ledger`
