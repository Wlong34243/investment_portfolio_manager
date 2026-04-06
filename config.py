"""
Investment Portfolio Manager — Configuration
All settings centralized here. Reads from Streamlit secrets in production,
falls back to environment variables or defaults for local dev.

Mirrors the config.py pattern from RE Property Manager.
"""

import os

# ---------------------------------------------------------------------------
# Try to import Streamlit secrets; fall back gracefully for testing/CLI use
# ---------------------------------------------------------------------------
def _secret(key, default=None):
    """
    Safely retrieves a secret.
    1. Tries st.secrets (if in a Streamlit app).
    2. Falls back to an environment variable.
    3. Falls back to a provided default.
    """
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except (ImportError, Exception):
        # This will catch both missing streamlit and other streamlit-related errors
        # when not running in a streamlit context.
        pass
    
    return os.getenv(key.upper(), default)

# ---------------------------------------------------------------------------
# Google Sheets IDs
# ---------------------------------------------------------------------------
PORTFOLIO_SHEET_ID = _secret(
    "portfolio_sheet_id",
    "1DuY68xVvyHq-0dyb7XUQgcoK7fqcVS0fv7UoGdTnfxA"  # TBD — create during Phase 1 setup, share with service account
)

# Cross-reference to RE Property Manager (READ ONLY — never write from this app)
RE_DASHBOARD_SHEET_ID = "1DXuY1iBo2GqZCCSZ7OrUa4iaunb5s8Kf1Rms8Z237rQ"

# ---------------------------------------------------------------------------
# API Keys (Phase 2+)
# ---------------------------------------------------------------------------
FINNHUB_API_KEY = _secret("finnhub_api_key", "")
FMP_API_KEY = _secret("fmp_api_key", "")        # Financial Modeling Prep (Phase 4)
FRED_API_KEY = _secret("fred_api_key", "")      # Federal Reserve Economic Data (Phase 2)
AI_SECONDARY_API_KEY = _secret("ai_secondary_api_key", "")  # Reserved for future secondary AI
GEMINI_API_KEY = _secret("gemini_api_key", "")      # Google Gemini (Core AI)

# ---------------------------------------------------------------------------
# AI Model Configuration
# ---------------------------------------------------------------------------
GEMINI_MODEL = _secret("gemini_model", "gemini-3.1-pro-preview")
GEMINI_MAX_TOKENS = _secret("gemini_max_tokens", 2000)

# ---------------------------------------------------------------------------
# Cash / Non-Investment Tickers
# ---------------------------------------------------------------------------
# These are cash sweep or money market positions — track as cash, not investments
CASH_TICKERS = {'CASH_MANUAL', 'QACDS', 'CASH & CASH INVESTMENTS'}

# Default cash yield for money market / sweep (editable in Sheet Config tab)
DEFAULT_CASH_YIELD_PCT = 4.50

# ---------------------------------------------------------------------------
# Portfolio Sheet Tab Names
# ---------------------------------------------------------------------------
TAB_HOLDINGS_CURRENT = "Holdings_Current"
TAB_HOLDINGS_HISTORY = "Holdings_History"
TAB_DAILY_SNAPSHOTS = "Daily_Snapshots"
TAB_TRANSACTIONS = "Transactions"
TAB_TARGET_ALLOCATION = "Target_Allocation"
TAB_RISK_METRICS = "Risk_Metrics"
TAB_INCOME_TRACKING = "Income_Tracking"
TAB_REALIZED_GL = "Realized_GL"
TAB_CONFIG = "Config"
TAB_LOGS = "Logs"
TAB_AI_SUGGESTED_ALLOCATION = "AI_Suggested_Allocation"
TAB_DECISION_LOG = "Decision_Log"

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
# Normalized Position Columns (output schema for Holdings tabs)
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
]

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
}

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

# ---------------------------------------------------------------------------
# Daily Snapshot Columns
# ---------------------------------------------------------------------------
# EXACT headers from PORTFOLIO_SHEET_SCHEMA.md
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

# ---------------------------------------------------------------------------
# Transaction History Columns
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Realized G/L Columns
# ---------------------------------------------------------------------------
# EXACT headers from REALIZED_GL_PARSER_SPEC.md
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

# ---------------------------------------------------------------------------
# Asset Class Mapping
# ---------------------------------------------------------------------------
# Maps Schwab's verbose Asset Class values to simplified allocation categories
ASSET_CLASS_MAP = {
    'Equity': 'Equities',
    'Fixed Income & Cash': 'Cash & Fixed Income',
    'Alternative Assets': 'Alternatives',
}

# ---------------------------------------------------------------------------
# Sector Classification (description-based, from Colab V3.2 get_sector_fast)
# ---------------------------------------------------------------------------
# Used for positions not in the top-20 enrichment tier (no yfinance call)
ETF_KEYWORDS = {
    'Fixed Income': ['BOND', 'INCOME', 'TREASURY', 'AGGREGATE'],
    'Technology': ['TECH', 'SOFTWARE'],
    'Healthcare': ['HEALTH'],
    'Energy': ['ENERGY'],
    'Broad Market': ['S&P', '500', 'TOTAL STOCK', 'TOTAL MARKET'],
}

# ---------------------------------------------------------------------------
# Performance Benchmarks
# ---------------------------------------------------------------------------
BENCHMARK_TICKERS = ['SPY', 'VTI', 'QQQM']

# ---------------------------------------------------------------------------
# Risk Analytics (Phase 2 — from Colab V3.2)
# ---------------------------------------------------------------------------
# CAPM parameters (should eventually move to Sheet Config tab)
RISK_FREE_RATE = 0.045        # ~4.5% (T-bill rate)
MARKET_PREMIUM = 0.055        # ~5.5% equity risk premium
BASE_VOLATILITY = 0.16        # ~16% annualized market volatility

# Stress test scenarios: (name, market_change)
STRESS_SCENARIOS = [
    ("Nasdaq falls 2% (Correction)", -0.02),
    ("Market rises 1.5% (Good Day)", 0.015),
    ("Market falls 10% (Major Sell-off)", -0.10),
    ("Market falls 20% (Bear Market)", -0.20),
    ("Market rises 5% (Rally)", 0.05),
]

# Minimum data points required for beta calculation
MIN_BETA_DATA_POINTS = 30

# Number of positions to enrich via yfinance (by market value, descending)
TOP_N_ENRICH = 20

# ---------------------------------------------------------------------------
# Concentration Risk Thresholds
# ---------------------------------------------------------------------------
SINGLE_POSITION_WARN_PCT = 10.0   # Warn if any position > 10% of portfolio
SECTOR_CONCENTRATION_WARN_PCT = 30.0  # Warn if any sector > 30% of portfolio

# ---------------------------------------------------------------------------
# Contribution Modeling
# ---------------------------------------------------------------------------
DEFAULT_MONTHLY_CONTRIBUTIONS = [2000, 5000]  # From Colab projection scenarios

# ---------------------------------------------------------------------------
# Cache Settings
# ---------------------------------------------------------------------------
CACHE_TTL_SECONDS = 300       # 5 minutes — same as RE project
YFINANCE_CACHE_TTL = 300      # Minimum seconds between yfinance refreshes

# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------
SHEETS_SLEEP_BETWEEN_TABS = 1.0   # seconds between Google Sheets tab operations
SHEETS_RETRY_BACKOFF = 60         # seconds to wait on APIError before retry

# ---------------------------------------------------------------------------
# Ticker-specific Data Overrides (Manual Corrections)
# ---------------------------------------------------------------------------
TICKER_OVERRIDES = {
    'ET': {
        'dividend_yield': 8.5,  # Schwab/YFinance often miss LP distribution yields
    },
    'BABA': {
        'asset_class': 'International', # Ensure BABA isn't just 'Other' or 'Equity'
    }
}
DRY_RUN = False  # Set to False only when ready to write to live Sheet
