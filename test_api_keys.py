#!/usr/bin/env python3
"""
Investment Portfolio Manager — API Key & Service Connectivity Test
=================================================================
Tests all external services used across Phases 1-4:
  1. GCP Service Account  → Google Sheets (read-only probe)
  2. yfinance             → Yahoo Finance (no key needed)
  3. Finnhub              → News feed (Phase 2)
  4. FMP                  → Financial Modeling Prep (Phase 4)
  5. Anthropic            → Claude AI research (Phase 4)
  6. Gemini               → Core AI research (Phase 4)

Usage:
  python test_api_keys.py                      # uses config.py / st.secrets
  FINNHUB_API_KEY=xxx python test_api_keys.py  # env var override
"""

import os
import sys
import json
import time
from datetime import datetime

# ── Helpers ─────────────────────────────────────────────────────────────

PASS = "✅ PASS"
FAIL = "❌ FAIL"
SKIP = "⏭️  SKIP"

results = []

def report(service, status, detail=""):
    tag = PASS if status == "pass" else (FAIL if status == "fail" else SKIP)
    results.append({"service": service, "status": status, "detail": detail})
    print(f"  {tag}  {service}" + (f"  —  {detail}" if detail else ""))


def load_config_key(key):
    """Try config.py → env var → empty string."""
    try:
        import config
        val = getattr(config, key, None)
        if val:
            return val
    except Exception:
        pass
    return os.getenv(key.upper(), "")


# ── 1. GCP Service Account → Google Sheets ─────────────────────────────

def test_gcp_sheets():
    """Authenticate with service account and read one cell from Portfolio Sheet."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as e:
        report("GCP / Google Sheets", "fail", f"Missing package: {e}")
        return

    # Locate credentials
    sa_json = None

    # A) Try Streamlit secrets dict
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
            sa_json = dict(st.secrets["gcp_service_account"])
    except Exception:
        pass

    # B) Try service_account.json file
    if sa_json is None:
        for path in ["service_account.json", ".streamlit/service_account.json"]:
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        sa_json = json.load(f)
                    break
                except json.JSONDecodeError as e:
                    report("GCP / Google Sheets", "fail",
                           f"service_account.json is invalid JSON: {e}")
                    return

    if sa_json is None:
        report("GCP / Google Sheets", "fail",
               "No credentials found (st.secrets, service_account.json)")
        return

    # Authenticate
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(sa_json, scopes=scopes)
        client = gspread.authorize(creds)
    except Exception as e:
        report("GCP / Google Sheets", "fail", f"Auth error: {e}")
        return

    # Read from Portfolio Sheet
    sheet_id = load_config_key("PORTFOLIO_SHEET_ID")
    if not sheet_id:
        report("GCP / Google Sheets", "fail", "PORTFOLIO_SHEET_ID not set in config")
        return

    try:
        spreadsheet = client.open_by_key(sheet_id)
        tabs = [ws.title for ws in spreadsheet.worksheets()]
        report("GCP / Google Sheets", "pass",
               f"Sheet '{spreadsheet.title}' — {len(tabs)} tabs: {', '.join(tabs[:5])}{'…' if len(tabs) > 5 else ''}")
    except gspread.exceptions.SpreadsheetNotFound:
        report("GCP / Google Sheets", "fail",
               f"Sheet ID {sheet_id} not found or not shared with service account")
    except Exception as e:
        report("GCP / Google Sheets", "fail", f"Sheet read error: {e}")


# ── 2. yfinance (no API key) ───────────────────────────────────────────

def test_yfinance():
    """Pull a single ticker quote to confirm Yahoo Finance is reachable."""
    try:
        import yfinance as yf
    except ImportError:
        report("yfinance / Yahoo Finance", "fail", "yfinance not installed")
        return

    try:
        ticker = yf.Ticker("SPY")
        info = ticker.fast_info
        price = getattr(info, "last_price", None)
        if price and price > 0:
            report("yfinance / Yahoo Finance", "pass",
                   f"SPY last price: ${price:,.2f}")
        else:
            report("yfinance / Yahoo Finance", "fail",
                   "Connected but got no price data — Yahoo may be rate-limiting")
    except Exception as e:
        report("yfinance / Yahoo Finance", "fail", f"{e}")


# ── 3. Finnhub ─────────────────────────────────────────────────────────

def test_finnhub():
    """Hit Finnhub /quote endpoint with the configured API key."""
    key = load_config_key("FINNHUB_API_KEY")
    if not key:
        report("Finnhub (news feed)", "skip", "No FINNHUB_API_KEY configured — needed for Phase 2")
        return

    try:
        import urllib.request
        url = f"https://finnhub.io/api/v1/quote?symbol=AAPL&token={key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data.get("c", 0) > 0:
            report("Finnhub (news feed)", "pass",
                   f"AAPL current price: ${data['c']:,.2f}")
        elif data.get("error"):
            report("Finnhub (news feed)", "fail", f"API error: {data['error']}")
        else:
            report("Finnhub (news feed)", "fail", "Connected but got empty quote")
    except Exception as e:
        report("Finnhub (news feed)", "fail", f"{e}")


# ── 4. Financial Modeling Prep (FMP) ────────────────────────────────────

def test_fmp():
    """Hit FMP /profile endpoint with the configured API key."""
    key = load_config_key("FMP_API_KEY")
    if not key:
        report("FMP (earnings data)", "skip", "No FMP_API_KEY configured — needed for Phase 4")
        return

    try:
        import urllib.request
        # Using the new Stable API pattern
        url = f"https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey={key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if isinstance(data, list) and len(data) > 0 and data[0].get("companyName"):
            report("FMP (earnings data)", "pass",
                   f"AAPL → {data[0]['companyName']}, mktCap ${data[0].get('mktCap', 0)/1e9:.0f}B")
        elif isinstance(data, dict) and data.get("Error Message"):
            report("FMP (earnings data)", "fail", f"Invalid key: {data['Error Message']}")
        else:
            report("FMP (earnings data)", "fail", "Connected but unexpected response format")
    except Exception as e:
        report("FMP (earnings data)", "fail", f"{e}")


# ── 4b. FRED (Economic Data) ───────────────────────────────────────────

def test_fred():
    """Hit FRED API to fetch the current Fed Funds Rate."""
    key = load_config_key("FRED_API_KEY")
    if not key:
        report("FRED (economic data)", "skip", "No FRED_API_KEY configured — needed for Phase 2")
        return

    try:
        import urllib.request
        # Series: FEDFUNDS (Effective Federal Funds Rate)
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key={key}&file_type=json&limit=1&sort_order=desc"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        
        if data.get("observations"):
            obs = data["observations"][0]
            report("FRED (economic data)", "pass",
                   f"Fed Funds Rate (FEDFUNDS): {obs['value']}% (as of {obs['date']})")
        else:
            report("FRED (economic data)", "fail", f"Connected but got no observations: {data}")
    except Exception as e:
        report("FRED (economic data)", "fail", f"{e}")


# ── 5. Secondary AI (Reserved) ──────────────────────────────────────────

def test_secondary_ai():
    """Placeholder for secondary AI validation."""
    key = load_config_key("AI_SECONDARY_API_KEY")
    if not key:
        report("Secondary AI", "skip",
               "No AI_SECONDARY_API_KEY configured")
        return
    report("Secondary AI", "pass", "Key is present (test logic not implemented)")


# ── 6. Gemini (Google AI) ──────────────────────────────────────────

def test_gemini():
    """Send a minimal completion request to validate the API key."""
    key = load_config_key("GEMINI_API_KEY")
    if not key:
        report("Gemini (Core AI)", "skip",
               "No GEMINI_API_KEY configured — used for Core AI")
        return

    try:
        from google import genai
        client = genai.Client(api_key=key)
        model_name = load_config_key("GEMINI_MODEL") or "gemini-3.1-pro-preview"
        response = client.models.generate_content(
            model=model_name,
            contents="Say PASS"
        )
        if response.text:
            report("Gemini (Core AI)", "pass",
                   f"Model '{model_name}' responded: '{response.text[:30].strip()}'")
        else:
            report("Gemini (Core AI)", "fail", f"Connected to {model_name} but got no response text")
    except ImportError:
        report("Gemini (Core AI)", "fail", "google-genai not installed")
    except Exception as e:
        report("Gemini (Core AI)", "fail", f"{e}")


# ── Main ────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Investment Portfolio Manager — Service Connectivity Test")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    test_gcp_sheets()
    test_yfinance()
    test_finnhub()
    test_fmp()
    test_fred()
    test_secondary_ai()
    test_gemini()

    print()
    print("-" * 60)
    passed  = sum(1 for r in results if r["status"] == "pass")
    failed  = sum(1 for r in results if r["status"] == "fail")
    skipped = sum(1 for r in results if r["status"] == "skip")
    print(f"  Results:  {passed} passed  |  {failed} failed  |  {skipped} skipped")

    if failed:
        print(f"\n  ⚠️  {failed} service(s) need attention before those phases will work.")
    if skipped:
        print(f"  ℹ️  {skipped} service(s) skipped — add API keys when ready for those phases.")
    if not failed and not skipped:
        print("\n  🎉  All services connected — full pipeline ready.")

    print()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
