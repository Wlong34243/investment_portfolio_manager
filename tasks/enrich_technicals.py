"""
tasks/enrich_technicals.py
──────────────────────────
Computes Murphy TA indicators (MA50/200, RSI-14, MACD, volume) for all non-cash
positions and injects `calculated_technicals` into the composite bundle JSON
in-place.

Safe to append: load_composite_bundle() verifies SHA256(market_hash + vault_hash).
Appended keys do not invalidate the hash.

Run after enrich_atr.py (shares the same yfinance OHLC data requirement).
Can run standalone or via --enrich-technicals flag on manager.py snapshot.

Usage:
    python tasks/enrich_technicals.py                            # enriches latest composite
    python tasks/enrich_technicals.py --bundle path/to/composite.json
    python manager.py snapshot --enrich-technicals
    python manager.py snapshot --enrich-atr --enrich-technicals  # both in sequence
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

# Project root on path
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skip rules (per prompt spec)
# ---------------------------------------------------------------------------
SKIP_ASSET_CLASSES = {"CASH_EQUIVALENT", "MMMF", "FIXED_INCOME", "BOND"}
# Pure cash sweep tickers — no price series worth computing TA on
SKIP_TICKERS = set(config.CASH_TICKERS) | {"CASH_MANUAL", "QACDS"}
# ETFs ARE included — MA/RSI/MACD are meaningful for ETFs.


# ---------------------------------------------------------------------------
# Pure-Python indicator implementations (no pandas_ta, no ta-lib)
# ---------------------------------------------------------------------------

def _compute_rsi(close: pd.Series) -> Optional[float]:
    """
    14-period RSI using Wilder smoothing (EWM with alpha=1/14).
    Returns None if fewer than 14 periods available.
    """
    if len(close) < 15:
        return None
    delta    = close.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    last_loss = avg_loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs  = avg_gain.iloc[-1] / last_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(float(rsi), 1)


def _compute_macd(close: pd.Series) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Returns (macd_line, signal_line, histogram) — all rounded to 4 decimals.
    Returns (None, None, None) if series too short.
    """
    if len(close) < 35:
        return None, None, None
    ema12     = close.ewm(span=12, adjust=False).mean()
    ema26     = close.ewm(span=26, adjust=False).mean()
    macd      = ema12 - ema26
    signal    = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return (
        round(float(macd.iloc[-1]),      4),
        round(float(signal.iloc[-1]),    4),
        round(float(histogram.iloc[-1]), 4),
    )


def _cross_occurred(series_a: pd.Series, series_b: pd.Series, lookback: int, direction: str) -> bool:
    """
    Detect whether series_a crossed series_b within the last `lookback` rows.

    direction='up'   → golden cross: diff went from negative to positive
    direction='down' → death cross:  diff went from positive to negative
    """
    if len(series_a) < lookback + 1 or len(series_b) < lookback + 1:
        return False
    diff = (series_a - series_b).iloc[-(lookback + 1):]
    for i in range(len(diff) - 1):
        prev, curr = diff.iloc[i], diff.iloc[i + 1]
        if direction == "up"   and prev < 0 and curr >= 0:
            return True
        if direction == "down" and prev > 0 and curr <= 0:
            return True
    return False


def _macd_cross_occurred(histogram: pd.Series, lookback: int, direction: str) -> bool:
    """
    Detect whether MACD histogram crossed zero within last `lookback` rows.

    direction='up'   → bullish cross (histogram went negative → positive)
    direction='down' → bearish cross (histogram went positive → negative)
    """
    if len(histogram) < lookback + 1:
        return False
    window = histogram.iloc[-(lookback + 1):]
    for i in range(len(window) - 1):
        prev, curr = window.iloc[i], window.iloc[i + 1]
        if direction == "up"   and prev <= 0 and curr > 0:
            return True
        if direction == "down" and prev >= 0 and curr < 0:
            return True
    return False


# ---------------------------------------------------------------------------
# Per-ticker computation
# ---------------------------------------------------------------------------

def _compute_for_ticker(ticker: str, ohlcv: pd.DataFrame) -> dict:
    """
    Given a 1-year daily OHLCV DataFrame for one ticker, compute all
    technical indicators. Returns the full indicator dict including data_gap.
    """
    result: dict = {"ticker": ticker}

    if ohlcv is None or ohlcv.empty:
        result.update({k: None for k in [
            "as_of_date", "current_price", "ma_50", "ma_200",
            "price_vs_ma50_pct", "price_vs_ma200_pct", "ma_signal",
            "golden_cross", "death_cross", "rsi_14", "rsi_signal",
            "macd_line", "macd_signal_line", "macd_histogram", "macd_signal",
            "volume_20d_avg", "volume_ratio", "volume_signal",
            "trend_score", "trend_label",
        ]})
        result["data_gap"] = "no_data"
        return result

    # Normalise column names — yfinance multi-index produces (Field, Ticker) tuples
    if isinstance(ohlcv.columns, pd.MultiIndex):
        ohlcv = ohlcv.droplevel(1, axis=1)

    ohlcv = ohlcv.sort_index()

    close  = ohlcv["Close"].dropna()
    volume = ohlcv["Volume"].dropna() if "Volume" in ohlcv.columns else pd.Series(dtype=float)

    n = len(close)
    data_gap: Optional[str] = None

    if n < 50:
        result.update({k: None for k in [
            "as_of_date", "current_price", "ma_50", "ma_200",
            "price_vs_ma50_pct", "price_vs_ma200_pct", "ma_signal",
            "golden_cross", "death_cross", "rsi_14", "rsi_signal",
            "macd_line", "macd_signal_line", "macd_histogram", "macd_signal",
            "volume_20d_avg", "volume_ratio", "volume_signal",
            "trend_score", "trend_label",
        ]})
        result["data_gap"] = "insufficient_history"
        return result

    partial = n < 200
    if partial:
        data_gap = "partial"  # MA50 available but MA200 not

    as_of_date    = str(close.index[-1].date())
    current_price = round(float(close.iloc[-1]), 4)

    # ── Moving averages ──────────────────────────────────────────────────
    ma50_series  = close.rolling(50).mean()
    ma200_series = close.rolling(200).mean() if n >= 200 else pd.Series([None] * n, index=close.index)

    ma_50  = round(float(ma50_series.iloc[-1]),  4) if not pd.isna(ma50_series.iloc[-1])  else None
    ma_200 = round(float(ma200_series.iloc[-1]), 4) if (n >= 200 and not pd.isna(ma200_series.iloc[-1])) else None

    price_vs_ma50_pct  = round((current_price - ma_50)  / ma_50  * 100, 2) if ma_50  else None
    price_vs_ma200_pct = round((current_price - ma_200) / ma_200 * 100, 2) if ma_200 else None

    above_50  = ma_50  is not None and current_price > ma_50
    above_200 = ma_200 is not None and current_price > ma_200

    if above_50 and above_200:
        ma_signal = "above_both"
    elif above_200 and not above_50:
        ma_signal = "above_200_below_50"
    else:
        ma_signal = "below_both"

    # ── Cross detection ──────────────────────────────────────────────────
    lookback = config.TA_CROSS_LOOKBACK_DAYS
    if ma_200 is not None and n >= 200:
        golden_cross = _cross_occurred(ma50_series, ma200_series, lookback, "up")
        death_cross  = _cross_occurred(ma50_series, ma200_series, lookback, "down")
    else:
        golden_cross = False
        death_cross  = False

    # ── RSI ──────────────────────────────────────────────────────────────
    rsi_14 = _compute_rsi(close)
    if rsi_14 is None:
        rsi_signal = None
    elif rsi_14 > config.TA_RSI_OVERBOUGHT:
        rsi_signal = "overbought"
    elif rsi_14 < config.TA_RSI_OVERSOLD:
        rsi_signal = "oversold"
    else:
        rsi_signal = "neutral"

    # ── MACD ─────────────────────────────────────────────────────────────
    macd_line, macd_signal_line, macd_histogram = _compute_macd(close)

    if macd_histogram is not None:
        hist_series  = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        hist_series -= hist_series.ewm(span=9, adjust=False).mean()   # histogram series
        macd_lookback = config.TA_MACD_CROSS_LOOKBACK
        if macd_histogram > 0 and _macd_cross_occurred(hist_series, macd_lookback, "up"):
            macd_signal = "bullish"
        elif macd_histogram < 0 and _macd_cross_occurred(hist_series, macd_lookback, "down"):
            macd_signal = "bearish"
        else:
            macd_signal = "neutral"
    else:
        macd_signal = None

    # ── Volume ───────────────────────────────────────────────────────────
    if len(volume) >= 20:
        vol_20d_avg  = int(round(float(volume.iloc[-21:-1].mean())))
        current_vol  = float(volume.iloc[-1])
        volume_ratio = round(current_vol / vol_20d_avg, 2) if vol_20d_avg > 0 else None
        if volume_ratio is None:
            volume_signal = None
        elif volume_ratio > config.TA_VOLUME_HIGH_RATIO:
            volume_signal = "high"
        elif volume_ratio < config.TA_VOLUME_LOW_RATIO:
            volume_signal = "low"
        else:
            volume_signal = "normal"
    else:
        vol_20d_avg   = None
        volume_ratio  = None
        volume_signal = None

    # ── Trend score (+3 to −3, Python-only) ─────────────────────────────
    score = 0
    if above_50:
        score += 1
    else:
        score -= 1
    if above_200:
        score += 1
    else:
        score -= 1
    if rsi_14 is not None and 40 <= rsi_14 <= 70:
        score += 1
    elif rsi_14 is not None:
        score -= 1
    if macd_histogram is not None and macd_histogram > 0:
        score += 1
    elif macd_histogram is not None:
        score -= 1

    trend_score = max(-3, min(3, score))
    if trend_score == 3:
        trend_label = "strong_uptrend"
    elif trend_score in (1, 2):
        trend_label = "uptrend"
    elif trend_score == 0:
        trend_label = "neutral"
    elif trend_score in (-1, -2):
        trend_label = "downtrend"
    else:
        trend_label = "strong_downtrend"

    result.update({
        "as_of_date":           as_of_date,
        "current_price":        current_price,
        "ma_50":                ma_50,
        "ma_200":               ma_200,
        "price_vs_ma50_pct":    price_vs_ma50_pct,
        "price_vs_ma200_pct":   price_vs_ma200_pct,
        "ma_signal":            ma_signal,
        "golden_cross":         golden_cross,
        "death_cross":          death_cross,
        "rsi_14":               rsi_14,
        "rsi_signal":           rsi_signal,
        "macd_line":            macd_line,
        "macd_signal_line":     macd_signal_line,
        "macd_histogram":       macd_histogram,
        "macd_signal":          macd_signal,
        "volume_20d_avg":       vol_20d_avg,
        "volume_ratio":         volume_ratio,
        "volume_signal":        volume_signal,
        "trend_score":          trend_score,
        "trend_label":          trend_label,
        "data_gap":             data_gap,
    })
    return result


# ---------------------------------------------------------------------------
# Bulk download + per-ticker fallback
# ---------------------------------------------------------------------------

def compute_technicals(positions: list[dict]) -> list[dict]:
    """
    Bulk-download 1y daily OHLCV for all eligible tickers, then compute
    Murphy TA indicators for each.

    Falls back to per-ticker downloads if the bulk call fails.
    Never raises — always appends a data_gap entry for failed tickers.
    """
    import yfinance as yf

    eligible = []
    for pos in positions:
        ticker      = pos.get("ticker", "")
        asset_class = (pos.get("asset_class") or "").upper().replace(" ", "_")
        if not ticker or ticker in SKIP_TICKERS:
            continue
        if asset_class in SKIP_ASSET_CLASSES:
            continue
        eligible.append((ticker, pos))

    if not eligible:
        return []

    ticker_list = [t for t, _ in eligible]
    ohlcv_map: dict[str, pd.DataFrame] = {}

    # ── Attempt bulk download ────────────────────────────────────────────
    bulk_ok = False
    try:
        raw = yf.download(
            tickers=ticker_list,
            period="1y",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if not raw.empty:
            if len(ticker_list) == 1:
                # Single-ticker: flat DataFrame — wrap in dict
                ohlcv_map[ticker_list[0]] = raw
            else:
                # Multi-ticker: (Field, Ticker) MultiIndex columns
                for t in ticker_list:
                    try:
                        ticker_df = raw[t] if t in raw.columns.get_level_values(1) else pd.DataFrame()
                        ohlcv_map[t] = ticker_df
                    except Exception:
                        ohlcv_map[t] = pd.DataFrame()
            bulk_ok = True
            logger.info("enrich_technicals: bulk download OK for %d tickers", len(ticker_list))
    except Exception as e:
        logger.warning("enrich_technicals: bulk download failed — falling back to per-ticker: %s", e)

    # ── Per-ticker fallback for any missing tickers ──────────────────────
    missing = [t for t in ticker_list if t not in ohlcv_map or ohlcv_map[t].empty]
    if missing:
        if not bulk_ok:
            print(f"⚠  Bulk download failed — fetching {len(missing)} tickers individually")
        for t in missing:
            try:
                df = yf.download(t, period="1y", interval="1d",
                                 auto_adjust=True, progress=False)
                ohlcv_map[t] = df
            except Exception as e:
                logger.warning("enrich_technicals: per-ticker download failed for %s: %s", t, e)
                ohlcv_map[t] = pd.DataFrame()
            time.sleep(0.25)   # rate-limiting discipline

    # ── Compute indicators ───────────────────────────────────────────────
    results = []
    for ticker, _ in eligible:
        df = ohlcv_map.get(ticker, pd.DataFrame())
        entry = _compute_for_ticker(ticker, df)
        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Bundle injection
# ---------------------------------------------------------------------------

def enrich_composite_bundle(composite_path: Path) -> dict:
    """
    Load the composite bundle, compute technical indicators for all positions,
    inject `calculated_technicals` into the JSON, and write it back.

    Returns the updated composite bundle dict.
    """
    composite = load_composite_bundle(composite_path)
    market    = load_bundle(Path(composite["market_bundle_path"]))
    positions = market.get("positions", [])

    technicals = compute_technicals(positions)

    composite["calculated_technicals"]        = technicals
    composite["technicals_enriched_at"]       = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    composite["technicals_indicator_version"] = "murphy_v1"

    with open(composite_path, "w") as f:
        json.dump(composite, f, indent=2)

    return composite


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(bundle_path: Optional[str] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if bundle_path:
        path = Path(bundle_path)
    else:
        candidates = sorted(
            Path("bundles").glob("composite_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            print("ERROR: No composite bundles found in bundles/. Run: python manager.py bundle composite")
            sys.exit(1)
        path = candidates[-1]

    print(f"Enriching composite bundle: {path.name}")
    composite  = enrich_composite_bundle(path)
    technicals = composite.get("calculated_technicals", [])

    data_gaps = [e for e in technicals if e.get("data_gap")]
    print(f"Technical indicators computed for {len(technicals)} position(s).")

    if data_gaps:
        print(f"⚠  Data gaps ({len(data_gaps)}):")
        for e in data_gaps:
            print(f"   {e['ticker']:8s} → {e['data_gap']}")

    # Trend distribution summary
    from collections import Counter
    dist = Counter(e.get("trend_label") for e in technicals if e.get("trend_label"))
    for label in ["strong_uptrend", "uptrend", "neutral", "downtrend", "strong_downtrend"]:
        if dist[label]:
            print(f"   {label:<20} {dist[label]}")

    print(f"Written back to: {path}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enrich composite bundle with Murphy TA indicators.")
    parser.add_argument("--bundle", default=None, help="Path to composite bundle JSON.")
    args = parser.parse_args()
    main(args.bundle)
