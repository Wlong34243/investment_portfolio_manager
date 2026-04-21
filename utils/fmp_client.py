import json
import os
import time
import requests
import logging
import pandas as pd
from pathlib import Path
from functools import lru_cache
from typing import List
from datetime import datetime, timedelta

try:
    import config
except ImportError:
    config = None

BASE_URL = "https://financialmodelingprep.com/stable"

# ---------------------------------------------------------------------------
# Endpoint availability flags (set False on first 404; suppresses per-ticker spam)
# ---------------------------------------------------------------------------
FMP_EARNINGS_AVAILABLE: bool = True      # /stable/earnings-surprises
_fmp_earnings_404_logged: bool = False   # gate for the one-time warning log

# ---------------------------------------------------------------------------
# Cache + rate-limiter config
# ---------------------------------------------------------------------------
FMP_CACHE_DIR = Path("data/fmp_cache")
FMP_CACHE_TTL_DAYS = 14
FMP_MIN_CALL_INTERVAL = 2.5   # seconds between live FMP HTTP calls (~24/min to stay under free-tier burst)

_fmp_last_call_time: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_fmp_api_key() -> str:
    return getattr(config, 'FMP_API_KEY', os.environ.get('FMP_API_KEY', ''))


def _safe_float(v) -> float | None:
    """Return float or None; rejects NaN."""
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None   # NaN check
    except (TypeError, ValueError):
        return None


def _fmp_rate_limit() -> None:
    """
    Enforce 1.2s minimum spacing between FMP HTTP calls.
    Cache hits bypass this entirely — only fires before real requests.get() calls.
    Uses time.monotonic() to avoid over-sleeping when natural gaps already exist.
    """
    global _fmp_last_call_time
    elapsed = time.monotonic() - _fmp_last_call_time
    if elapsed < FMP_MIN_CALL_INTERVAL:
        time.sleep(FMP_MIN_CALL_INTERVAL - elapsed)
    _fmp_last_call_time = time.monotonic()


def _cache_path(ticker: str, suffix: str = "") -> Path:
    FMP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return FMP_CACHE_DIR / f"{ticker.upper()}{suffix}.json"


def _cache_valid(path: Path) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(days=FMP_CACHE_TTL_DAYS)


def _get_fmp_cached(ticker: str) -> dict | None:
    """
    Returns cached FMP key-metrics-ttm for ticker if < 7 days old, else calls FMP.
    Returns None on 402 / 429 / network error (never raises).
    Cache: data/fmp_cache/{TICKER}.json
    """
    path = _cache_path(ticker)
    if _cache_valid(path):
        try:
            cached = json.loads(path.read_text())
            return cached if cached else None
        except Exception:
            pass

    # Cache miss or stale
    try:
        data = get_key_metrics(ticker)
        if data:
            path.write_text(json.dumps(data))
        return data if data else None
    except Exception as e:
        logging.warning("FMP _get_fmp_cached failed for %s: %s", ticker, e)
        return None


def _fetch_yf_fallback(ticker: str) -> dict:
    """
    Fallback to yfinance when FMP returns 402/429.
    Maps: trailingPE, forwardPE, priceToBook, pegRatio, beta, sector, etc.
    """
    import yfinance as yf
    try:
        yt = yf.Ticker(ticker)
        info = yt.info
        return {
            'pe_ratio':                 _safe_float(info.get('trailingPE')),
            'forward_pe':               _safe_float(info.get('forwardPE')),
            'pb_ratio':                 _safe_float(info.get('priceToBook')),
            'peg_ratio':                _safe_float(info.get('pegRatio')),
            'dividend_yield':           _safe_float(info.get('dividendYield')),  # Pass as raw decimal (e.g. 0.02 for 2%)
            'roe':                      _safe_float(info.get('returnOnEquity')),
            'debt_to_equity':           _safe_float(info.get('debtToEquity')),
            'beta':                     _safe_float(info.get('beta')),
            'sector':                   info.get('sector'),
            'industry':                 info.get('industry'),
            'description':              info.get('description'),
            'market_cap':               _safe_float(info.get('marketCap')) / 1_000_000_000 if info.get('marketCap') else None,
            'yearHigh':                 _safe_float(getattr(yt.fast_info, 'year_high', None)),
            'yearLow':                  _safe_float(getattr(yt.fast_info, 'year_low', None)),
            'eps':                      _safe_float(info.get('trailingEps')),
        }
    except Exception as e:
        logging.warning("yfinance fallback failed for %s: %s", ticker, e)
        return {}


def get_fmp_quote(ticker: str) -> dict:
    """
    Call FMP /quote endpoint for a single ticker.
    Falls back to yfinance on 402/429.
    Returns dict with: price, pe, forwardPE, eps, yearHigh, yearLow.
    """
    api_key = get_fmp_api_key()
    if api_key:
        url = f"{BASE_URL}/quote?symbol={ticker}&apikey={api_key}"
        try:
            _fmp_rate_limit()
            resp = requests.get(url, timeout=10)
            if resp.status_code in (402, 429):
                logging.warning("FMP %d for %s quote — using yfinance fallback", resp.status_code, ticker)
                yf_data = _fetch_yf_fallback(ticker)
                return {
                    'price':     yf_data.get('price'), # Fast info?
                    'pe':        yf_data.get('pe_ratio'),
                    'forwardPE': yf_data.get('forward_pe'),
                    'eps':       yf_data.get('eps'),
                    'yearHigh':  yf_data.get('yearHigh'),
                    'yearLow':   yf_data.get('yearLow'),
                }
            resp.raise_for_status()
            data = resp.json()
            if data and isinstance(data, list) and len(data) > 0:
                return data[0]
        except Exception as e:
            logging.warning("FMP quote fetch failed for %s: %s", ticker, e)

    # Final fallback if no API key or FMP error
    yf_data = _fetch_yf_fallback(ticker)
    import yfinance as yf
    try:
        price = yf.Ticker(ticker).fast_info.last_price
    except:
        price = None

    return {
        'price':     price,
        'pe':        yf_data.get('pe_ratio'),
        'forwardPE': yf_data.get('forward_pe'),
        'eps':       yf_data.get('eps'),
        'yearHigh':  yf_data.get('yearHigh'),
        'yearLow':   yf_data.get('yearLow'),
    }


def get_income_statements_cached(ticker: str, limit: int = 4) -> list[dict]:
    """
    Fetch FMP annual income statements with 7-day file cache + rate limiter.
    Returns list of dicts newest-first, [] on any failure.

    Used by bagger_screener for 3-yr revenue CAGR and gross margin when
    yfinance financials are unavailable (ETFs, foreign tickers).
    """
    path = _cache_path(ticker, f"_income{limit}")
    if _cache_valid(path):
        try:
            data = json.loads(path.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass

    api_key = get_fmp_api_key()
    if not api_key:
        return []

    _fmp_rate_limit()
    url = (
        f"{BASE_URL}/income-statement"
        f"?symbol={ticker}&period=annual&limit={limit}&apikey={api_key}"
    )
    try:
        resp = requests.get(url, timeout=12)
        if resp.status_code in (402, 429):
            logging.warning("FMP %d for %s income-statement", resp.status_code, ticker)
            # Cache empty result so repeat calls within TTL skip the HTTP request silently
            try:
                path.write_text(json.dumps([]))
            except Exception:
                pass
            return []
        resp.raise_for_status()
        data = resp.json()
        result = data if isinstance(data, list) else []
        if result:
            try:
                path.write_text(json.dumps(result))
            except Exception:
                pass
        return result
    except Exception as e:
        logging.warning("FMP income-statement failed for %s: %s", ticker, e)
        return []


# ---------------------------------------------------------------------------
# Streamlit-app FMP functions (Streamlit @CACHE decorator applied)
# All live HTTP calls go through _fmp_rate_limit() to stay under free tier.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=128)
def get_earnings_calendar(tickers: List[str], days_ahead: int = 14) -> pd.DataFrame:
    api_key = get_fmp_api_key()
    if not api_key:
        return pd.DataFrame()

    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    url = f"{BASE_URL}/earnings-calendar?from={start_date}&to={end_date}&apikey={api_key}"
    try:
        _fmp_rate_limit()
        response = requests.get(url, timeout=10)
        if response.status_code == 402:
            logging.warning("FMP 402 — earnings-calendar subscription limit")
            return pd.DataFrame()
        response.raise_for_status()
        data = response.json()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df = df[df['symbol'].isin(tickers)]
        if df.empty:
            return pd.DataFrame()
        return df[['symbol', 'date', 'epsEstimated', 'revenueEstimated']].rename(
            columns={
                'symbol': 'ticker',
                'epsEstimated': 'eps_estimated',
                'revenueEstimated': 'revenue_estimated',
            }
        )
    except Exception as e:
        logging.warning("FMP earnings calendar error: %s", e)
        return pd.DataFrame()


@lru_cache(maxsize=128)
def get_earnings_transcript(ticker: str, year: int = None, quarter: int = None) -> str:
    api_key = get_fmp_api_key()
    if not api_key:
        return ""

    url = f"{BASE_URL}/earning-call-transcript?symbol={ticker}&"
    if year and quarter:
        url += f"year={year}&quarter={quarter}&"
    url += f"apikey={api_key}"
    try:
        _fmp_rate_limit()
        response = requests.get(url, timeout=10)
        if response.status_code == 402:
            logging.warning("FMP 402 — earnings-transcript subscription limit")
            return ""
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            return data[0].get('content', '')[:4000]
        return ""
    except Exception as e:
        logging.warning("FMP transcript error for %s: %s", ticker, e)
        return ""


@lru_cache(maxsize=128)
def get_key_metrics(ticker: str) -> dict:
    api_key = get_fmp_api_key()
    if not api_key:
        return _fetch_yf_fallback(ticker)

    url = f"{BASE_URL}/key-metrics-ttm?symbol={ticker}&apikey={api_key}"
    try:
        _fmp_rate_limit()
        response = requests.get(url, timeout=10)
        if response.status_code in (402, 429):
            logging.warning("FMP %d — key-metrics-ttm for %s, falling back", response.status_code, ticker)
            return _fetch_yf_fallback(ticker)
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            m = data[0]
            pe = m.get('peRatioTTM')
            if not pe and m.get('earningsYieldTTM'):
                ey = float(m.get('earningsYieldTTM'))
                pe = 1.0 / ey if ey != 0 else None
            
            # FMP 'dividendYieldPercentageTTM' is a whole number (e.g. 2.5 for 2.5%)
            # Task 1: Pass as raw decimal (0.025)
            div_yield_raw = _safe_float(m.get('dividendYieldPercentageTTM'))
            div_yield = div_yield_raw / 100.0 if div_yield_raw is not None else None

            return {
                'pe_ratio':                 pe,
                'pb_ratio':                 m.get('pbRatioTTM'),
                'dividend_yield':           div_yield,
                'roe':                      m.get('returnOnEquityTTM'),
                'debt_to_equity':           m.get('debtToEquityTTM'),
                'revenue_per_share':        m.get('revenuePerShareTTM'),
                'free_cash_flow_per_share': m.get('freeCashFlowPerShareTTM'),
                'peg_ratio':                m.get('pegRatioTTM'),
            }

        return _fetch_yf_fallback(ticker)
    except Exception as e:
        logging.warning("FMP key metrics error for %s: %s", ticker, e)
        return _fetch_yf_fallback(ticker)


@lru_cache(maxsize=128)
def get_earnings_surprises_cached(ticker: str) -> list[dict]:
    """
    Fetch last 2 quarters of earnings surprises from FMP.
    Returns list of dicts with: date, actual, estimated, surprise_pct.
    Returns [] silently when the endpoint is unavailable (404) or rate-limited.
    """
    global FMP_EARNINGS_AVAILABLE, _fmp_earnings_404_logged
    if not FMP_EARNINGS_AVAILABLE:
        return []

    api_key = get_fmp_api_key()
    if not api_key:
        return []

    url = (
        f"{BASE_URL}/earnings-surprises"
        f"?symbol={ticker}&limit=2&apikey={api_key}"
    )
    try:
        _fmp_rate_limit()
        resp = requests.get(url, timeout=10)
        if resp.status_code == 404:
            FMP_EARNINGS_AVAILABLE = False
            if not _fmp_earnings_404_logged:
                logging.warning(
                    "FMP /stable/earnings-surprises returned 404 — endpoint unavailable on free tier; "
                    "suppressing further earnings-surprise requests this session"
                )
                _fmp_earnings_404_logged = True
            return []
        if resp.status_code in (402, 429):
            logging.warning("FMP %d for %s earnings-surprises", resp.status_code, ticker)
            return []
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []
        surprises = []
        for row in data[:2]:
            actual = row.get("actualEarningResult") or row.get("actual")
            est = row.get("estimatedEarning") or row.get("estimated")
            if actual is None or est is None:
                continue
            try:
                # Task 1: Pass as raw decimal (remove * 100)
                surprise_pct = ((float(actual) - float(est)) / abs(float(est))) if est != 0 else 0.0
            except (TypeError, ZeroDivisionError):
                surprise_pct = 0.0
            surprises.append({
                "date": row.get("date", ""),
                "actual_eps": actual,
                "estimated_eps": est,
                "surprise_pct": round(surprise_pct, 4),
            })
        return surprises
    except Exception as e:
        logging.warning("FMP earnings surprises error for %s: %s", ticker, e)
        return []


@lru_cache(maxsize=128)
def get_historical_pe(ticker: str, years: int = 5) -> pd.DataFrame:
    api_key = get_fmp_api_key()
    if not api_key:
        return pd.DataFrame()

    url = f"{BASE_URL}/ratios?symbol={ticker}&period=annual&limit={years}&apikey={api_key}"
    try:
        _fmp_rate_limit()
        response = requests.get(url, timeout=10)
        if response.status_code in (402, 429):
            logging.warning("FMP %d — ratios subscription limit for %s", response.status_code, ticker)
            # yfinance doesn't easily give historical annual PE series without more work
            return pd.DataFrame()
        response.raise_for_status()
        data = response.json()
        if data:
            df = pd.DataFrame(data)
            if 'priceEarningsRatio' in df.columns:
                return df[['date', 'priceEarningsRatio']].rename(
                    columns={'priceEarningsRatio': 'pe_ratio'}
                )
        return pd.DataFrame()
    except Exception as e:
        logging.warning("FMP historical PE error for %s: %s", ticker, e)
        return pd.DataFrame()


@lru_cache(maxsize=128)
def get_company_profile(ticker: str) -> dict:
    api_key = get_fmp_api_key()
    if not api_key:
        return _fetch_yf_fallback(ticker)

    url = f"{BASE_URL}/profile?symbol={ticker}&apikey={api_key}"
    try:
        _fmp_rate_limit()
        response = requests.get(url, timeout=10)
        if response.status_code in (402, 429):
            logging.warning("FMP %d — profile for %s, falling back", response.status_code, ticker)
            return _fetch_yf_fallback(ticker)
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            p = data[0]
            return {
                'sector':      p.get('sector'),
                'industry':    p.get('industry'),
                'description': p.get('description'),
                'market_cap':  float(p.get('mktCap') or 0.0),
                'beta':        float(p.get('beta') or 0.0),
            }
        return _fetch_yf_fallback(ticker)
    except Exception as e:
        logging.warning("FMP profile error for %s: %s", ticker, e)
        return _fetch_yf_fallback(ticker)


@lru_cache(maxsize=128)
def screen_by_metrics(criteria: dict) -> pd.DataFrame:
    """Screen stocks by metric thresholds (marketCapMoreThan, peRatioLowerThan, etc.)."""
    api_key = get_fmp_api_key()
    if not api_key:
        return pd.DataFrame()

    url = f"{BASE_URL}/stock-screener?apikey={api_key}"
    for key, val in criteria.items():
        if val is not None:
            url += f"&{key}={val}"
    try:
        _fmp_rate_limit()
        response = requests.get(url, timeout=10)
        if response.status_code == 402:
            logging.warning("FMP 402 — screener subscription limit")
            return pd.DataFrame()
        response.raise_for_status()
        data = response.json()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        cols = ['symbol', 'companyName', 'marketCap', 'pe', 'dividendYield', 'sector']
        existing_cols = [c for c in cols if c in df.columns]
        return df[existing_cols].rename(columns={
            'symbol':      'ticker',
            'companyName': 'company_name',
            'marketCap':   'market_cap',
            'dividendYield': 'dividend_yield',
        })
    except Exception as e:
        logging.warning("FMP screener error: %s", e)
        return pd.DataFrame()


@lru_cache(maxsize=128)
def get_financial_statements(ticker: str) -> dict:
    """
    Fetches annual income statement + cash flow to extract R&D, CapEx, ROIC.
    Used by utils/agents/valuation_agent.py (Streamlit app layer).
    """
    api_key = get_fmp_api_key()
    if not api_key:
        return {}

    results = {}
    try:
        _fmp_rate_limit()
        is_res = requests.get(
            f"{BASE_URL}/income-statement/{ticker}?limit=1&apikey={api_key}", timeout=10
        )
        if is_res.status_code == 200:
            is_data = is_res.json()
            if is_data:
                results['research_and_development_expenses'] = is_data[0].get('researchAndDevelopmentExpenses', 0)
                results['operating_income']  = is_data[0].get('operatingIncome', 0)
                results['net_income']        = is_data[0].get('netIncome', 0)
        elif is_res.status_code in (402, 429):
             logging.warning("FMP %d — income-statement for %s", is_res.status_code, ticker)

        _fmp_rate_limit()
        cf_res = requests.get(
            f"{BASE_URL}/cash-flow-statement/{ticker}?limit=1&apikey={api_key}", timeout=10
        )
        if cf_res.status_code == 200:
            cf_data = cf_res.json()
            if cf_data:
                results['capital_expenditure'] = cf_data[0].get('capitalExpenditure', 0)
        elif cf_res.status_code in (402, 429):
             logging.warning("FMP %d — cash-flow-statement for %s", cf_res.status_code, ticker)

        _fmp_rate_limit()
        km_res = requests.get(
            f"{BASE_URL}/key-metrics/{ticker}?limit=1&apikey={api_key}", timeout=10
        )
        if km_res.status_code == 200:
            km_data = km_res.json()
            if km_data:
                results['roic'] = km_data[0].get('roic', 0)
        elif km_res.status_code in (402, 429):
             logging.warning("FMP %d — key-metrics for %s", km_res.status_code, ticker)

    except Exception as e:
        logging.warning("FMP financial statements error for %s: %s", ticker, e)

    return results


# ---------------------------------------------------------------------------
# get_fundamentals — three-tier: Schwab bundle → yfinance → FMP cache
# Used by CLI agents (rebuy_analyst, bagger_screener, tasks/enrich_fundamentals).
# ---------------------------------------------------------------------------

_FMP_SKIP_ASSET_CLASSES = {
    "ETF", "FUND", "MUTUAL_FUND", "FIXED_INCOME", "CASH_EQUIVALENT",
    "INDEX", "BOND", "MMMF",
}


def get_fundamentals(ticker: str, bundle_quote: dict = None, asset_class: str = "") -> dict:
    """
    Fetch fundamentals with tiered priority:

    Tier 0 — Schwab bundle_quote (zero API cost)
        Populated when data_source='schwab_api'. Empty for CSV-sourced bundles.
        Fields: trailing_pe, forward_pe, eps_ttm, market_cap, dividend_yield,
                52w_high, 52w_low.

    Tier 1 — yfinance (fast_info + info + financials)
        fast_info: market_cap, 52w_high, 52w_low (faster, fewer scrape issues).
        info: PE, PEG, debt/equity, gross margin, ROE, payout ratio, beta, sector.
        financials: 3-yr revenue CAGR (Total Revenue over 4 annual periods).
        Wraps all yfinance calls in try/except — yfinance scrapes public endpoints
        and can fail silently without warning.

    Tier 2 — FMP key-metrics-ttm via 7-day file cache
        Only called for fields still None after yfinance AND when asset_class is
        not in _FMP_SKIP_ASSET_CLASSES. ETFs/funds/fixed-income have no meaningful
        PE/PEG/ROIC, so FMP is skipped entirely — avoids burning free-tier quota.
        402/429 returns None, never raises.

    Returns {} on complete failure. Callers treat all fields as optional.
    """
    import yfinance as yf

    result: dict = {}

    # --- Tier 0: Schwab bundle_quote ---
    if bundle_quote:
        _t0_map = {
            "trailing_pe":    "peRatio",
            "forward_pe":     "forwardPE",
            "eps_ttm":        "eps",
            "market_cap":     "marketCap",
            "dividend_yield": "dividendYield",
            "52w_high":       "52WeekHigh",
            "52w_low":        "52WeekLow",
        }
        for internal, schwab_key in _t0_map.items():
            if (v := _safe_float(bundle_quote.get(schwab_key))) is not None:
                result[internal] = v

    # --- Tier 1: yfinance ---
    try:
        yt = yf.Ticker(ticker)

        # fast_info — price / market cap (faster path, lower scrape risk)
        try:
            fi = yt.fast_info
            for internal, attr in [
                ("market_cap", "market_cap"),
                ("52w_high",   "year_high"),
                ("52w_low",    "year_low"),
            ]:
                if result.get(internal) is None:
                    if (v := _safe_float(getattr(fi, attr, None))) is not None:
                        result[internal] = v
        except Exception:
            pass

        # info — full fundamentals dict
        try:
            info = yt.info
            _YF_MAP = {
                "trailing_pe":    ["trailingPE"],
                "forward_pe":     ["forwardPE"],
                "peg_ratio":      ["pegRatio", "trailingPegRatio"],
                "debt_to_equity": ["debtToEquity"],
                "eps_ttm":        ["trailingEps"],
                "dividend_yield": ["dividendYield", "trailingAnnualDividendYield"],
                "revenue_growth": ["revenueGrowth"],
                "earnings_growth":["earningsGrowth", "earningsQuarterlyGrowth"],
                "beta":           ["beta"],
                "gross_margin":   ["grossMargins"],
                "roic":           ["returnOnEquity"],   # best proxy available in yfinance
                "payout_ratio":   ["payoutRatio"],
                "pb_ratio":       ["priceToBook"],
                "current_ratio":  ["currentRatio"],
            }
            for internal, yf_keys in _YF_MAP.items():
                if result.get(internal) is None:
                    for key in yf_keys:
                        if (v := _safe_float(info.get(key))) is not None:
                            result[internal] = v
                            break

            # sector — string, not numeric; handled separately
            if not result.get("sector"):
                sector = info.get("sector") or ""
                if sector:
                    result["sector"] = sector

        except Exception:
            pass

        # financials — 3-yr revenue CAGR (Total Revenue, 4 annual periods)
        if result.get("revenue_growth_3yr") is None:
            try:
                stmt = yt.financials
                if not stmt.empty and "Total Revenue" in stmt.index:
                    revs = stmt.loc["Total Revenue"].dropna().values
                    if len(revs) >= 4:
                        cagr = (float(revs[0]) / float(revs[3])) ** (1 / 3) - 1
                        result["revenue_growth_3yr"] = cagr   # raw fraction — use _safe_pct() to convert
            except Exception:
                pass

    except Exception as e:
        logging.debug("yfinance outer error for %s: %s", ticker, e)

    # --- Tier 2: FMP cached fallback (only for fields still None) ---
    # Skip FMP entirely for ETFs, funds, fixed income — these have no meaningful
    # PE/PEG/ROIC and burning free-tier quota on them causes 429s for real stocks.
    _ac = asset_class.upper().replace(" ", "_") if asset_class else ""
    fmp_skipped_by_class = bool(_ac and _ac in _FMP_SKIP_ASSET_CLASSES)
    needs_fmp = not fmp_skipped_by_class and any(
        result.get(f) is None
        for f in ["trailing_pe", "peg_ratio", "market_cap", "gross_margin", "roic"]
    )
    if needs_fmp:
        km = _get_fmp_cached(ticker)
        if km:
            _fmp_map = {
                "trailing_pe":    km.get("pe_ratio"),
                "peg_ratio":      km.get("peg_ratio"),      # not in standard get_key_metrics output — will be None
                "roic":           km.get("roe"),
                "debt_to_equity": km.get("debt_to_equity"),
                "dividend_yield": km.get("dividend_yield"),
            }
            for internal, raw in _fmp_map.items():
                if result.get(internal) is None:
                    if (v := _safe_float(raw)) is not None:
                        result[internal] = v

    # alias used by rebuy_analyst framework rules
    result["earnings_growth_rate_3yr"] = result.get("earnings_growth")

    return {k: v for k, v in result.items() if v is not None}


# ---------------------------------------------------------------------------
# Bundle-time FMP enrichment  (Phase 1.2)
# Called once per ticker at snapshot time; cache key {TICKER}_bndl.json (14d).
# Consumers read position["fmp_fundamentals"] — never call FMP live at dashboard time.
# ---------------------------------------------------------------------------

def get_fmp_fundamentals_bundle(ticker: str, asset_class: str = "", forward_pe_override: float | None = None) -> dict:
    """
    Fetch all bundle-time FMP fundamentals for one ticker.  14-day disk cache.

    Calls two FMP endpoints per ticker (key-metrics-ttm + ratios-ttm) plus the
    cached income-statement endpoint for revenue_growth_yoy.  Rate limiter fires
    only on real HTTP calls; cache hits bypass it entirely.

    Returns a dict with fields:
        pe_ratio, forward_pe, peg_ratio, debt_to_equity, roic,
        revenue_growth_yoy, gross_margin, net_margin, dividend_yield,
        payout_ratio, market_cap, fetched_at

    Returns {"error": reason, "fetched_at": ts} only on complete API failure.
    ETFs / fixed-income receive partial results (nulls are expected; no error flag).
    """
    path = _cache_path(ticker, "_bndl")
    if _cache_valid(path):
        try:
            cached = json.loads(path.read_text())
            if isinstance(cached, dict):
                # Inject caller-supplied forward_pe if the cached entry lacks it
                if forward_pe_override is not None and cached.get("forward_pe") is None:
                    cached["forward_pe"] = forward_pe_override
                return cached
        except Exception:
            pass

    now_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    ac_upper = asset_class.upper().replace(" ", "_")
    is_equity_like = ac_upper not in _FMP_SKIP_ASSET_CLASSES

    api_key = get_fmp_api_key()
    
    result: dict = {
        "fetched_at":         now_ts,
        "pe_ratio":           None,
        "forward_pe":         forward_pe_override,
        "peg_ratio":          None,
        "debt_to_equity":     None,
        "roic":               None,
        "revenue_growth_yoy": None,
        "gross_margin":       None,
        "net_margin":         None,
        "dividend_yield":     None,
        "payout_ratio":       None,
        "market_cap":         None,
    }

    if not is_equity_like:
        # Skip FMP for ETFs/Funds/Fixed Income to save quota
        # No error, just empty results as expected for these types
        return result

    if not api_key:
        err = {"error": "no_fmp_api_key", "fetched_at": now_ts}
        try:
            path.write_text(json.dumps(err))
        except Exception:
            pass
        return err
    fetch_errors: list[str] = []
    endpoints_ok = 0

    # ------------------------------------------------------------------ #
    # key-metrics-ttm  →  pe, peg, d/e, roic, market_cap, dividend_yield  #
    # ------------------------------------------------------------------ #
    try:
        _fmp_rate_limit()
        r = requests.get(
            f"{BASE_URL}/key-metrics-ttm?symbol={ticker}&apikey={api_key}",
            timeout=10,
        )
        if r.status_code in (402, 429):
            fetch_errors.append(f"key-metrics-ttm: HTTP {r.status_code}")
        elif r.ok:
            km_raw = r.json()
            m = (km_raw[0] if isinstance(km_raw, list) and km_raw
                 else km_raw if isinstance(km_raw, dict) else {})
            if m:
                endpoints_ok += 1
                pe = _safe_float(m.get("peRatioTTM"))
                if not pe:
                    ey = _safe_float(m.get("earningsYieldTTM"))
                    pe = (1.0 / ey) if ey else None
                result["pe_ratio"]       = pe
                result["peg_ratio"]      = _safe_float(m.get("pegRatioTTM"))
                result["debt_to_equity"] = _safe_float(m.get("debtToEquityTTM"))
                result["roic"]           = _safe_float(m.get("roicTTM"))
                result["market_cap"]     = _safe_float(m.get("marketCapTTM"))
                raw_dy = _safe_float(m.get("dividendYieldPercentageTTM"))
                if raw_dy is not None:
                    result["dividend_yield"] = raw_dy / 100.0
        else:
            fetch_errors.append(f"key-metrics-ttm: HTTP {r.status_code}")
    except Exception as e:
        fetch_errors.append(f"key-metrics-ttm: {e}")

    # ------------------------------------------------------------------ #
    # ratios-ttm  →  gross_margin, net_margin, payout_ratio               #
    # ------------------------------------------------------------------ #
    try:
        _fmp_rate_limit()
        r = requests.get(
            f"{BASE_URL}/ratios-ttm?symbol={ticker}&apikey={api_key}",
            timeout=10,
        )
        if r.status_code in (402, 429):
            fetch_errors.append(f"ratios-ttm: HTTP {r.status_code}")
        elif r.ok:
            rt_raw = r.json()
            m = (rt_raw[0] if isinstance(rt_raw, list) and rt_raw
                 else rt_raw if isinstance(rt_raw, dict) else {})
            if m:
                endpoints_ok += 1
                result["gross_margin"] = _safe_float(m.get("grossProfitMarginTTM"))
                result["net_margin"]   = _safe_float(m.get("netProfitMarginTTM"))
                result["payout_ratio"] = _safe_float(m.get("payoutRatioTTM"))
                if result["pe_ratio"] is None:
                    result["pe_ratio"] = _safe_float(m.get("priceEarningsRatioTTM"))
        else:
            fetch_errors.append(f"ratios-ttm: HTTP {r.status_code}")
    except Exception as e:
        fetch_errors.append(f"ratios-ttm: {e}")

    # ------------------------------------------------------------------ #
    # revenue_growth_yoy — equities only, from cached income statements   #
    # ------------------------------------------------------------------ #
    if is_equity_like:
        try:
            stmts = get_income_statements_cached(ticker, limit=2)
            if len(stmts) >= 2:
                rev_new = (_safe_float(stmts[0].get("revenue"))
                           or _safe_float(stmts[0].get("totalRevenue"))
                           or 0.0)
                rev_old = (_safe_float(stmts[1].get("revenue"))
                           or _safe_float(stmts[1].get("totalRevenue"))
                           or 0.0)
                if rev_old and rev_old != 0.0:
                    result["revenue_growth_yoy"] = round(
                        (rev_new - rev_old) / abs(rev_old), 4
                    )
        except Exception as e:
            fetch_errors.append(f"income-statement: {e}")

    if fetch_errors:
        result["fetch_warnings"] = fetch_errors

    # If both primary endpoints failed hard (auth/rate), signal as error
    if endpoints_ok == 0 and len(fetch_errors) >= 2:
        err_result = {"error": "; ".join(fetch_errors), "fetched_at": now_ts}
        try:
            path.write_text(json.dumps(err_result))
        except Exception:
            pass
        return err_result

    try:
        path.write_text(json.dumps(result, default=str))
    except Exception:
        pass

    return result


if __name__ == "__main__":
    print("Testing FMP Client...")
    print(get_key_metrics("AMZN"))
