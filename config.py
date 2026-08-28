"""
Investment Portfolio Manager — Configuration
All settings centralized here. Reads from .env file for development and production CLI usage.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# ---------------------------------------------------------------------------
# Google Sheets IDs
# ---------------------------------------------------------------------------
PORTFOLIO_SHEET_ID = os.getenv(
    "PORTFOLIO_SHEET_ID",
    "1DuY68xVvyHq-0dyb7XUQgcoK7fqcVS0fv7UoGdTnfxA"
)

# GCP Project Context
GCP_PROJECT_ID = "re-property-manager-487122"
GCP_REGION     = "us-central1"
GCP_LOCATION   = "us-central1"

# Cross-reference to RE Property Manager (READ ONLY — never write from this app)
RE_DASHBOARD_SHEET_ID = "1DXuY1iBo2GqZCCSZ7OrUa4iaunb5s8Kf1Rms8Z237rQ"

# ---------------------------------------------------------------------------
# API Keys (Phase 2+)
# ---------------------------------------------------------------------------
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
FMP_API_KEY = os.getenv("FMP_API_KEY", "")        # Financial Modeling Prep (Phase 4)
FRED_API_KEY = os.getenv("FRED_API_KEY", "")      # Federal Reserve Economic Data (Phase 2)
AI_SECONDARY_API_KEY = os.getenv("AI_SECONDARY_API_KEY", "")  # Reserved for future secondary AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")  # Now explicitly using GEMINI_API_KEY for CLI tools

# ---------------------------------------------------------------------------
# Schwab API (Phase 5-S)
# ---------------------------------------------------------------------------
SCHWAB_ACCOUNTS_APP_KEY    = os.getenv("SCHWAB_ACCOUNTS_APP_KEY", "")
SCHWAB_ACCOUNTS_APP_SECRET = os.getenv("SCHWAB_ACCOUNTS_APP_SECRET", "")
SCHWAB_MARKET_APP_KEY      = os.getenv("SCHWAB_MARKET_APP_KEY", "")
SCHWAB_MARKET_APP_SECRET   = os.getenv("SCHWAB_MARKET_APP_SECRET", "")

SCHWAB_TOKEN_BUCKET   = os.getenv("SCHWAB_TOKEN_BUCKET", "portfolio-manager-tokens")
SCHWAB_ACCOUNT_HASH   = os.getenv("SCHWAB_ACCOUNT_HASH", "")
SCHWAB_CALLBACK_URL   = os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1")

# Trailing digits (comma-separated) of the Schwab accounts this system
# represents. Live enumeration on 2026-08-03 (read-only get_accounts() call)
# found SIX accounts linked to this API token, not the three the repo's CSV
# exports implied -- with heavily overlapping holdings across them (JEPI in
# 5 of 6). Bill confirmed the primary portfolio (~$591-596K, matching
# CLAUDE.md/state.md) is the SUM of three of those six: masked ...6499,
# ...8767, ...5119 ($595,405.90 combined). The other three (...4151, ...0217,
# ...9753) are excluded. utils/schwab_client.py's fetch_positions()/
# fetch_transactions()/fetch_tax_lots() match each account's number's last
# 4 digits against this list and skip anything that doesn't match (see
# prompts/schwab_account_scope_fix_2026-08-03.md). Empty = no filtering (old,
# pre-fix behavior).
SCHWAB_PRIMARY_ACCOUNT_SUFFIXES = [
    s.strip() for s in os.getenv("SCHWAB_PRIMARY_ACCOUNT_SUFFIXES", "6499,8767,5119").split(",")
    if s.strip()
]

# Token blob names in GCS (one per app — Market Data client cannot read accounts blob)
SCHWAB_TOKEN_BLOB_ACCOUNTS = "token_accounts.json"
SCHWAB_TOKEN_BLOB_MARKET   = "token_market.json"
SCHWAB_ALERT_BLOB          = "schwab_alert.json"

# --- Schwab market data (added 2026-08-25, Phase 1) -------------------------
# Verified 2026-08-25: config has no DATA_DIR — literal Path matching fmp_cache style.
PRICE_HISTORY_SOURCE = os.getenv("PRICE_HISTORY_SOURCE", "auto")  # yfinance | schwab | auto
PRICE_HISTORY_CACHE_DIR = Path("data/schwab_price_cache")
PRICE_HISTORY_CACHE_TTL_H = int(os.getenv("PRICE_HISTORY_CACHE_TTL_H", "20"))
SCHWAB_MAX_RETRIES = int(os.getenv("SCHWAB_MAX_RETRIES", "3"))
SCHWAB_REFRESH_TOKEN_WARN_DAYS = float(os.getenv("SCHWAB_REFRESH_TOKEN_WARN_DAYS", "2.0"))

# Client cache TTL (Cloud Function does the actual refresh — this just caches the client object in Streamlit)
SCHWAB_CLIENT_CACHE_TTL = 1500   # 25 min

# ---------------------------------------------------------------------------
# Vault & Research Paths
# ---------------------------------------------------------------------------
VAULT_DIR = Path("vault")
THESES_DIR = VAULT_DIR / "theses"
TRANSCRIPTS_DIR = VAULT_DIR / "transcripts"
RESEARCH_DIR = VAULT_DIR / "research"

# Max transactions kept in a thesis file's <!-- region:transaction_log -->
# block. Default covers the current position for typical lot counts; override
# per-run with `vault sync --txn-limit`.
THESIS_TXN_LOG_LIMIT = int(os.getenv("THESIS_TXN_LOG_LIMIT", "20"))

# ---------------------------------------------------------------------------
# AI Model Configuration
# ---------------------------------------------------------------------------
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "2000"))  # default for lightweight agents

# Per-agent token budgets — overrides for agents that return large structured JSON.
# Gemini 2.5 Flash output cap is 65,536 tokens; these are well within bounds.
# Root cause of "EOF while parsing" errors: output truncated at the global 2000-token default.
GEMINI_MAX_TOKENS_PODCAST       = 8000    # full-episode transcripts (10k+ words) → structured JSON with 8–12 sectors

# ---------------------------------------------------------------------------
# Centralized Exclusions (Phase 5-Hardening)
# ---------------------------------------------------------------------------
# These are used to filter positions out of specific analysis tracks.
CASH_TICKERS     = ['CASH', 'SGOV', 'CASH_MANUAL', 'MMDA', 'REDEEMED', 'QACDS', 'CASH & CASH INVESTMENTS']
VALUATION_SKIP   = ['SGOV', 'JPIE', 'Fixed Income', 'CASH', 'QACDS', 'MMDA', 'CASH_MANUAL']
VALUATION_SKIP_TICKERS = ['SGOV', 'CASH_MANUAL']
BETA_EXCLUDE     = ['CASH', 'Fixed Income', 'MMDA', 'REDEEMED', 'SGOV']

# Backward compatibility / Aliases
CASH_EQUIVALENT_TICKERS = CASH_TICKERS

# ---------------------------------------------------------------------------
# Issuer aliases for ETF look-through aggregation
# ---------------------------------------------------------------------------
# The look-through keys on ticker symbol, so the same issuer under two
# symbols (a share class, or a direct US listing vs. the ETF-embedded
# foreign listing) reports as two separate companies -- e.g. GOOG/GOOGL, or
# SKHY (Nasdaq) vs. 000660.KS (KRX, held inside EMXC/VEA). Maps a symbol to
# the canonical symbol it should be aggregated under. Hand-maintained by
# design -- extend as dual listings actually get held; do not attempt
# automated issuer resolution via a vendor.
ISSUER_ALIASES = {
    "GOOGL": "GOOG",
    "SKHY": "000660.KS",
}

# ---------------------------------------------------------------------------
# Dislocation Scanner (tasks/dislocation_scan.py)
# ---------------------------------------------------------------------------
# A ticker is flagged when it clears the drawdown bar AND the multiple bar
# AND the quality floor -- all three, not any one. Facts only, no price
# targets: these are screen thresholds, not buy signals.
DISLOCATION_MIN_MARKET_CAP   = 10_000_000_000  # large/mid-cap only; excludes screener noise
DISLOCATION_MIN_DRAWDOWN_52W = 0.15            # 15% off the 52-week high ...
DISLOCATION_MIN_5D_RETURN    = -0.10           # ... or a -10% 5-day move (either trips it)
DISLOCATION_MAX_FWD_PE       = 18.0
DISLOCATION_MIN_GROSS_MARGIN = 0.30            # quality floor: margin > 30% OR positive FCF

# ---------------------------------------------------------------------------
# Valuation Agent Skips (Legacy - being replaced by VALUATION_SKIP)
# ---------------------------------------------------------------------------
# Asset classes and tickers to exclude from valuation analysis (ETFs, Funds, etc. have no P/E)
VALUATION_SKIP_ASSET_CLASSES = {
    "ETF", "FUND", "MUTUAL_FUND", "FIXED_INCOME", "CASH_EQUIVALENT",
    "INDEX", "BOND", "MMMF",
}

# ---------------------------------------------------------------------------
# Portfolio Sheet Tab Names
# ---------------------------------------------------------------------------
TAB_DASHBOARD        = "0_DASHBOARD"        # index-0 tab; hard-value KPIs, no formulas
TAB_HOLDINGS_CURRENT = "Holdings_Current"
TAB_HOLDINGS_HISTORY = "Holdings_History"
TAB_DAILY_SNAPSHOTS = "Daily_Snapshots"
TAB_TRANSACTIONS = "Transactions"
TAB_TARGET_ALLOCATION = "Target_Allocation"
TAB_RISK_METRICS = "Risk_Metrics"
TAB_INCOME_TRACKING = "Income_Tracking"
TAB_CASH_FLOWS = "Cash_Flows"
TAB_REALIZED_GL = "Realized_GL"
TAB_CONFIG = "Config"
TAB_LOGS = "Logs"
TAB_AGENT_OUTPUTS = "Agent_Outputs"
TAB_AGENT_OUTPUTS_ARCHIVE = "Agent_Outputs_Archive"
TAB_DISAGREEMENTS = "Disagreements"
TAB_AI_SUGGESTED_ALLOCATION = "AI_Suggested_Allocation"
TAB_DECISION_LOG = "Decision_Log"
TAB_TRADE_LOG = "Trade_Log"
TAB_TRADE_LOG_STAGING = "Trade_Log_Staging"
TAB_ROTATION_REVIEW   = "Rotation_Review"
TAB_TAX_CONTROL = "Tax_Control"
TAB_VALUATION_CARD = "Valuation_Card"   # computed; was string literal in builders
TAB_DECISION_VIEW = "Decision_View"     # computed; was string literal in builders
TAB_PRECOMMITMENTS = "Precommitments"   # manual authority; append-and-mark ingest only

PRECOMMITMENTS_COLUMNS = [
    "Date_Declared",
    "Ticker",
    "Trigger_Type",
    "Side",
    "Level",
    "Intended_Action",
    "Note",
    "Ingested_At",
    "Precommit_ID",
    "Status",
]

# Judgment Engine (prompt 10) — minimum N for aggregate cells
JUDGE_MIN_N = 12

# ---------------------------------------------------------------------------
# sheets = Sheets only (legacy)
# dual   = write Sheets + SQLite on --live; read ONLY from STORE_PRIMARY
# sqlite = SQLite primary reads/writes; Sheets optional via export
#
# STORE_PRIMARY is an EXPLICIT hand-flipped flag (default sheets).
# Do NOT auto-flip on "SQLite has rows" — a partial shadow must not change reads.
# Flip to sqlite only after pm store verify streak is green; revert with one line:
#   set STORE_PRIMARY=sheets
STORE_BACKEND = os.getenv("STORE_BACKEND", "dual").strip().lower()
STORE_PRIMARY = os.getenv("STORE_PRIMARY", os.getenv("STORE_READ_PRIMARY", "sheets")).strip().lower()
# Alias kept for older shells; STORE_PRIMARY wins.
STORE_READ_PRIMARY = STORE_PRIMARY
SQLITE_DB_PATH = Path(
    os.getenv("SQLITE_DB_PATH", str(Path(__file__).resolve().parent / "data" / "portfolio_store.db"))
)
# Phase-1 verify streak: N consecutive *verify runs* of VERIFY PASS (not
# calendar days — weekends with no morning neither advance nor break).
# Window must include ≥1 realized lot (non-vacuous realized_gl reconcile).
STORE_VERIFY_STREAK_N = int(os.getenv("STORE_VERIFY_STREAK_N", "5"))
STORE_VERIFY_STREAK_PATH = Path(
    os.getenv(
        "STORE_VERIFY_STREAK_PATH",
        str(Path(__file__).resolve().parent / "logs" / "store_verify_streak.jsonl"),
    )
)
# Backup retention (local + Drive db_backups/)
STORE_BACKUP_KEEP_DAILY = int(os.getenv("STORE_BACKUP_KEEP_DAILY", "14"))
STORE_BACKUP_KEEP_WEEKLY = int(os.getenv("STORE_BACKUP_KEEP_WEEKLY", "8"))


# Tax_Control has two zones: KPI strip (top) and tax-relevant lots table (bottom).
# We model it as a single tab with section headers, not two tabs.
TAX_CONTROL_KPI_LABELS = [
    "Net ST (YTD)",
    "Net LT (YTD)",
    "Disallowed Wash Loss (YTD)",
    "Est. Fed Cap Gains Tax",
    "Tax Offset Capacity",
    "Wash Sale Count",
    "Last Updated",
    "Refreshed",
]

TAX_CONTROL_LOTS_COLUMNS = [
    "Closed Date",
    "Ticker",
    "Account",
    "Term",
    "Gain Loss",
    "ST Gain Loss",
    "LT Gain Loss",
    "Wash Sale",
    "Disallowed Loss",
]

# ---------------------------------------------------------------------------
# Schwab CSV Parsing
# ---------------------------------------------------------------------------
# Account type labels that appear as section headers in multi-account CSV
ACCOUNT_SECTION_PATTERNS = [
    'Individual', 'Contributory', 'Joint', 'Custodial', 'Trust', 'Roth', 'HSA'
]

# Columns in Schwab CSV that need comma/parenthesis cleaning
# (dynamic detection is preferred, but these are the known patterns)
KNOWN_NUMERIC_COLUMNS = [
    'Quantity', 'Price', 'Market_Value', 'Cost', 'Unit_Cost',
    'Unrealized_GL', 'Unrealized_GL_Pct', 'Est_Annual_Income'
]

# ---------------------------------------------------------------------------
# EXACT headers from PORTFOLIO_SHEET_SCHEMA.md
POSITION_COLUMNS = [
    'Ticker',
    'Description',
    'Asset Class',
    'Asset Strategy',
    'Quantity',
    'Price',
    'Market Value',
    'Cost Basis',
    'Unit Cost',
    'Unrealized G/L',
    'Unrealized G/L %',
    'Est Annual Income',
    'Dividend Yield',
    'Acquisition Date',
    'Wash Sale',
    'Is Cash',
    'Daily Change %',
    'Weight',
    'Import Date',
    'Fingerprint',
    'Sector',
]

SNAPSHOT_COLUMNS = [
    'Date',
    'Total Value',
    'Total Cost',
    'Total Unrealized G/L',
    'Cash Value',
    'Invested Value',
    'Position Count',
    'Blended Yield',
    'Import Timestamp',
    'Fingerprint',
]

INCOME_COLUMNS = [
    'Date',
    'Projected Annual Income',
    'Blended Yield %',
    'Top Generator Ticker',
    'Top Generator Income',
    'Cash Yield Contribution',
    'Fingerprint',
]

RISK_COLUMNS = [
    'Date',
    'Portfolio Beta',
    'Top Position Conc %',
    'Top Position Ticker',
    'Top Sector Conc %',
    'Top Sector',
    'Estimated VaR 95%',
    'Stress -10% Impact',
    'Fingerprint',
]

TRANSACTION_COLUMNS = [
    'Trade Date',
    'Settlement Date',
    'Ticker',
    'Description',
    'Action',
    'Quantity',
    'Price',
    'Amount',
    'Fees',
    'Net Amount',
    'Account',
    'Fingerprint',
]

GL_COLUMNS = [
    'Ticker',
    'Description',
    'Closed Date',
    'Opened Date',
    'Holding Days',
    'Quantity',
    'Proceeds Per Share',
    'Cost Per Share',
    'Proceeds',
    'Cost Basis',
    'Unadjusted Cost',
    'Gain Loss $',
    'Gain Loss %',
    'LT Gain Loss',
    'ST Gain Loss',
    'Term',
    'Wash Sale',
    'Disallowed Loss',
    'Account',
    'Is Primary Acct',
    'Import Date',
    'Fingerprint',
]

AI_SUGGESTED_ALLOCATION_COLUMNS = [
    'Date',
    'Source',
    'Asset Class',
    'Asset Strategy',
    'Target %',
    'Min %',
    'Max %',
    'Confidence',
    'Notes',
    'Executive Summary',
    'Fingerprint',
]

DECISION_LOG_COLUMNS = [
    'Date',
    'Timestamp',
    'Tickers Involved',
    'Action',
    'Market Context',
    'Rationale',
    'Tags',
    'Fingerprint',
]

TRADE_LOG_COLUMNS = [
    'Date',
    'Sell_Ticker',
    'Sell_Proceeds',
    'Buy_Ticker',
    'Buy_Amount',
    'Implicit_Bet',
    'Thesis_Brief',
    'Rotation_Type',
    'Sell_RSI_At_Decision',
    'Sell_Trend_At_Decision',
    'Sell_Price_vs_MA200_At_Decision',
    'Buy_RSI_At_Decision',
    'Buy_Trend_At_Decision',
    'Buy_Price_vs_MA200_At_Decision',
    'Trade_Log_ID',
    'Fingerprint',
    # Appended 2026-08-27 (Instrument prompt 7) — Q/R/S after Fingerprint so
    # existing A–P letter positions stay stable. Implicit_Bet remains Bill-only.
    'Proposed_Bet',
    'Rationale_Provenance',
    'Rationale_Evidence',
]

TRADE_LOG_STAGING_COLUMNS = [
    'Stage_ID',
    'Date',
    'Sell_Tickers',
    'Sell_Proceeds',
    'Buy_Tickers',
    'Buy_Amount',
    'Rotation_Type',
    'Implicit_Bet',
    'Thesis_Brief',
    'Status',
    'Promoted_At',  # UTC ISO timestamp written by journal promote; blank = hand-typed 'promoted'
    'Cluster_Window_Days',
    'Sell_Dates',
    'Buy_Dates',
    'Sell_RSI_At_Decision',
    'Sell_Trend_At_Decision',
    'Sell_Price_vs_MA200_At_Decision',
    'Buy_RSI_At_Decision',
    'Buy_Trend_At_Decision',
    'Buy_Price_vs_MA200_At_Decision',
    'Fingerprint',
]

ROTATION_REVIEW_COLUMNS = [
    'Trade_Log_ID',
    'Date',
    'Sell_Ticker',
    'Buy_Ticker',
    'Rotation_Type',
    'Implicit_Bet',
    'Sell_RSI_At_Decision',
    'Buy_RSI_At_Decision',
    'Sell_Trend_At_Decision',
    'Buy_Trend_At_Decision',
    'Sell_Return_30d',
    'Sell_Return_90d',
    'Sell_Return_180d',
    'Buy_Return_30d',
    'Buy_Return_90d',
    'Buy_Return_180d',
    'Pair_Return_30d',
    'Pair_Return_90d',
    'Pair_Return_180d',
    'Attribution_As_Of',
    'Fingerprint',
    # --- Basket-aware attribution (appended 2026-08-08; do not reorder above) ---
    'Status',
    'Both_Sides_Tickers',
    'Coverage_Pct',
    'Sell_Beta_Weighted',
    'Buy_Beta_Weighted',
    'Beta_Reference',
    # Residual = selection net of the risk step-up (headline; listed before raw pair in md)
    'Residual_Pair_30d',
    'Residual_Pair_90d',
    'Residual_Pair_180d',
    'Beta_Explained_Pair_30d',
    'Beta_Explained_Pair_90d',
    'Beta_Explained_Pair_180d',
    'Vs_Index_30d',
    'Vs_Index_90d',
    'Vs_Index_180d',
    'Sell_Vs_Index_30d',
    'Sell_Vs_Index_90d',
    'Sell_Vs_Index_180d',
    'Bench_SPY_30d',
    'Bench_SPY_90d',
    'Bench_SPY_180d',
    'Bench_VTI_30d',
    'Bench_VTI_90d',
    'Bench_VTI_180d',
    'Bench_QQQ_30d',
    'Bench_QQQ_90d',
    'Bench_QQQ_180d',
    'Bench_Spread_30d',
    'Bench_Spread_90d',
    'Bench_Spread_180d',
    'Bench_QQQ_Note',
    # Gate C (2026-08-25): self-identifying bar vendor. Frozen historical rows
    # keep published numbers and stamp yfinance|frozen_pre_schwab_2026-08-25.
    'Price_Source',
]

# ---------------------------------------------------------------------------
# Column Name Mappings (Internal -> External)
# ---------------------------------------------------------------------------

POSITION_COL_MAP = {
    'ticker': 'Ticker',
    'description': 'Description',
    'asset_class': 'Asset Class',
    'asset_strategy': 'Asset Strategy',
    'quantity': 'Quantity',
    'price': 'Price',
    'market_value': 'Market Value',
    'cost_basis': 'Cost Basis',
    'unit_cost': 'Unit Cost',
    'unrealized_gl': 'Unrealized G/L',
    'unrealized_gl_pct': 'Unrealized G/L %',
    'est_annual_income': 'Est Annual Income',
    'dividend_yield': 'Dividend Yield',
    'acquisition_date': 'Acquisition Date',
    'wash_sale': 'Wash Sale',
    'is_cash': 'Is Cash',
    'daily_change_pct': 'Daily Change %',
    'weight': 'Weight',
    'import_date': 'Import Date',
    'fingerprint': 'Fingerprint',
    'sector': 'Sector',
}

AI_SUGGESTED_ALLOCATION_COL_MAP = {
    'date': 'Date',
    'source': 'Source',
    'asset_class': 'Asset Class',
    'asset_strategy': 'Asset Strategy',
    'target_pct': 'Target %',
    'min_pct': 'Min %',
    'max_pct': 'Max %',
    'confidence': 'Confidence',
    'notes': 'Notes',
    'executive_summary': 'Executive Summary',
    'fingerprint': 'Fingerprint',
}

TRANSACTION_COL_MAP = {
    'Date': 'Trade Date',
    'Action': 'Action',
    'Symbol': 'Ticker',
    'Description': 'Description',
    'Quantity': 'Quantity',
    'Price': 'Price',
    'Fees & Comm': 'Fees',
    'Amount': 'Net Amount',
    'import_date': 'Import Date',
    'Fingerprint': 'Fingerprint',
}

GL_COL_MAP = {
    'ticker': 'Ticker',
    'description': 'Description',
    'closed_date': 'Closed Date',
    'opened_date': 'Opened Date',
    'holding_days': 'Holding Days',
    'quantity': 'Quantity',
    'proceeds_per_share': 'Proceeds Per Share',
    'cost_per_share': 'Cost Per Share',
    'proceeds': 'Proceeds',
    'cost_basis': 'Cost Basis',
    'unadjusted_cost': 'Unadjusted Cost',
    'gain_loss_dollars': 'Gain Loss $',
    'gain_loss_pct': 'Gain Loss %',
    'lt_gain_loss': 'LT Gain Loss',
    'st_gain_loss': 'ST Gain Loss',
    'term': 'Term',
    'wash_sale': 'Wash Sale',
    'disallowed_loss': 'Disallowed Loss',
    'account': 'Account',
    'is_primary_acct': 'Is Primary Acct',
    'import_date': 'Import Date',
    'fingerprint': 'Fingerprint',
}

# ---------------------------------------------------------------------------
# Risk Analytics & Enrichment
# ---------------------------------------------------------------------------
# Minimum data points required for beta calculation
MIN_BETA_DATA_POINTS = 30

# Tickers to exclude from beta calculation (cash, money markets, etc.)
BETA_EXCLUDE_TICKERS = {'CASH_MANUAL', 'QACDS', 'CASH & CASH INVESTMENTS', 'SGOV'}

# Number of positions to enrich via yfinance (by market value, descending)
TOP_N_ENRICH = 50

# ---------------------------------------------------------------------------
# ETF Sector Classification Keywords
# ---------------------------------------------------------------------------
ETF_KEYWORDS = {
    "Technology": ["QQQ", "IGV", "XLK", "Technology", "Software", "Semiconductor"],
    "Financials": ["XLF", "Financial", "Bank", "Insurance"],
    "Healthcare": ["XLV", "Healthcare", "Biotech", "Medical", "Pharma"],
    "Energy": ["XLE", "Energy", "Oil", "Gas", "Pipeline"],
    "Materials": ["XLB", "Materials", "Gold", "Mining"],
    "Utilities": ["XLU", "Utilities", "Power", "Water"],
    "Real Estate": ["XLRE", "Real Estate", "REIT"],
    "Industrials": ["XLI", "Industrials", "Defense", "Aerospace"],
    "Consumer Discretionary": ["XLY", "Consumer Discretionary", "Retail"],
    "Consumer Staples": ["XLP", "Consumer Staples", "Food", "Beverage"],
}

# ---------------------------------------------------------------------------
# Ticker-specific Data Overrides (Manual Corrections)
# ---------------------------------------------------------------------------
TICKER_OVERRIDES = {
    'ET': {
        'dividend_yield': 0.085,  # Schwab/YFinance often miss LP distribution yields (raw decimal: 8.5%)
    },
    'BABA': {
        'asset_class': 'International', # Ensure BABA isn't just 'Other' or 'Equity'
    }
}
DRY_RUN = os.getenv("DRY_RUN", "False").lower() == "true"  # Set to False only when ready to write to live Sheet

# ---------------------------------------------------------------------------
# Phase 5: Agent Squad — Thresholds & Tab Names
# ---------------------------------------------------------------------------
# Concentration thresholds (used by concentration_hedger)
CONCENTRATION_SINGLE_THRESHOLD = 0.08    # 8% single-position flag
CONCENTRATION_SECTOR_THRESHOLD = 0.30    # 30% sector flag
CORRELATION_FLAG_THRESHOLD = 0.50        # |r| above this = high-correlation pair

# TLH threshold (used by tax_agent)
TLH_LOSS_THRESHOLD_USD = -500.0          # minimum unrealized loss to surface as TLH candidate

# Rebalancing threshold (used by tax_agent)
REBALANCE_THRESHOLD_PCT = 5.0            # drift % to trigger rebalance action

DEFAULT_CASH_YIELD_PCT = 4.5


# ---------------------------------------------------------------------------
# Technical Indicator Thresholds (Murphy TA — used by tasks/enrich_technicals.py)
# ---------------------------------------------------------------------------
TA_RSI_OVERBOUGHT      = 70    # RSI above this → "overbought"
TA_RSI_OVERSOLD        = 30    # RSI below this → "oversold"
TA_VOLUME_HIGH_RATIO   = 1.5   # volume_ratio above this → "high"
TA_VOLUME_LOW_RATIO    = 0.5   # volume_ratio below this → "low"
TA_CROSS_LOOKBACK_DAYS = 20    # days to look back for golden/death cross detection
TA_MACD_CROSS_LOOKBACK = 5     # days to look back for MACD signal cross

# --- Phase 4: Export Engine ---
EXPORTS_DIR = Path("exports")
PROMPT_TEMPLATE_VERSION_ROTATION = "1.0.0"
PROMPT_TEMPLATE_VERSION_DEEP_DIVE = "1.0.0"
PROMPT_TEMPLATE_VERSION_TECHNICAL_SCAN = "1.0.0"
PROMPT_TEMPLATE_VERSION_TAX_REBALANCE = "1.0.0"
PROMPT_TEMPLATE_VERSION_MACRO_REVIEW = "1.0.0"
PROMPT_TEMPLATE_VERSION_CONCENTRATION = "1.0.0"
PROMPT_TEMPLATE_VERSION_THESIS_HEALTH = "1.0.0"
EXPORT_SCENARIOS = {
    "rotation": "Should I rotate X into Y? (thesis + tax + technicals)",
    "deep-dive": "Full picture on one position (thesis + behavior + drift)",
    "tax-rebalance": "Harvest candidates given YTD tax posture",
    "technical-scan": "Overbought/oversold + action zones across the book",
    "macro-review": "Is my positioning consistent with a macro view?",
    "concentration": "Hidden concentrations and drawdown behavior",
    "thesis-health": "Which theses are stale / violated / need re-reading?",
}

# --- Phase 3.2: Hygiene & Purge Defaults ---
PURGE_DEFAULT_DAYS_PODCASTS = 30
PURGE_DEFAULT_DAYS_BUNDLES   = 30
PURGE_DEFAULT_DAYS_EXPORTS   = 7

# --- Spotify Studio digest ingestion (STEP 4b) ---
SPOTIFY_STUDIO_TRANSCRIPTS_DIR = os.getenv(
    "SPOTIFY_STUDIO_DIR",
    os.path.join(
        os.path.expanduser("~"),
        "AppData", "Local", "Studio by Spotify Labs",
        ".studio", "artifacts", "transcripts",
    ),
)
SPOTIFY_DIGEST_WINDOW_DAYS = 7
SPOTIFY_DIGEST_MIN_WORDS = 400          # below this, treat as truncated and skip
SPOTIFY_DIGEST_SOURCE_LABEL = "Spotify Podcast Aggregate"
