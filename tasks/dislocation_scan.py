"""
tasks/dislocation_scan.py — deterministic daily dislocation screen.

Purpose : Facts-only scan for the "quality franchise, double-digit selloff,
          cheap forward multiple" pattern (the SKHY/IBM/TSM shape) across
          current holdings, a hand-maintained watchlist, and FMP's daily
          biggest-losers list. Nothing in the pipeline scanned for this
          before -- these setups were only caught by luck. No price
          targets, no predictions, no buy/sell language: columns are
          metrics, not opinions.
Inputs  : bundles/context_bundle_*.json (latest, for held tickers),
          data/watchlist.json (hand-maintained, Bill adds names -- the
          scanner never writes to it), FMP /stable/biggest-losers.
Outputs : exports/dislocation_scan_{ts}.json (SHA-256 hashed per bundle
          conventions), agent_outputs/dislocation_scan/dislocation_scan_
          {date}.md (dated, never overwritten). No Sheet writes in v1.
Depends : utils/fmp_client.py (get_fundamentals, get_market_movers),
          yfinance, config.py DISLOCATION_* thresholds.
Usage   : python tasks/dislocation_scan.py [--live] [--losers-limit N]
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

# Support both `python tasks/dislocation_scan.py` (sys.path[0] == tasks/)
# and `from tasks.dislocation_scan import ...` from manager.py (repo root
# already on path in that case, but this makes the script runnable standalone
# too -- same fix export_ai_briefing.py / level_coverage.py use).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import config
from utils.fmp_client import get_fundamentals, get_market_movers

THESES_DIR = os.path.join("vault", "theses")
WATCHLIST_PATH_DEFAULT = os.path.join("data", "watchlist.json")
EXPORTS_DIR = "exports"
OUTPUT_DIR = os.path.join("agent_outputs", "dislocation_scan")


def _sha256_canonical(payload: dict) -> str:
    """Same convention as core/bundle.py's _sha256_canonical -- not
    imported directly since that module is explicitly not to be refactored
    or coupled against for new callers."""
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _load_watchlist(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [t.upper() for t in data.get("tickers", [])]


def _latest_bundle_positions() -> list:
    candidates = sorted(
        Path("bundles").glob("context_bundle_*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return []
    try:
        data = json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data.get("positions", [])


def _thesis_style(ticker: str):
    """Ground-truth style for a HELD ticker via shared thesis_reader."""
    from utils.thesis_reader import get_style, thesis_path_for_ticker

    path = thesis_path_for_ticker(ticker)
    if not path.exists():
        return None
    return get_style(path=path)


def _price_history_returns(ticker: str) -> dict:
    """1d/5d/20d close-to-close returns from ~3mo of daily history. Missing
    history (new listing, bad ticker, yfinance hiccup) degrades to None
    fields rather than raising -- callers treat all fields as optional."""
    out = {"return_1d": None, "return_5d": None, "return_20d": None, "last_close": None}
    try:
        hist = yf.Ticker(ticker).history(period="3mo")
        closes = hist["Close"].dropna()
        if closes.empty:
            return out
        out["last_close"] = float(closes.iloc[-1])
        for key, n in (("return_1d", 1), ("return_5d", 5), ("return_20d", 20)):
            if len(closes) > n:
                prior = float(closes.iloc[-1 - n])
                if prior:
                    out[key] = (float(closes.iloc[-1]) / prior) - 1.0
    except Exception:
        pass
    return out


def _build_universe(losers_limit: int):
    """ticker -> classification. HELD takes priority over WATCHLIST over
    SCREEN-DISCOVERED when a ticker appears in more than one source --
    setdefault() below preserves whichever classification is inserted
    first, so sources must be added in that priority order."""
    universe = {}

    held_positions = _latest_bundle_positions()
    held_by_ticker = {}
    for p in held_positions:
        if p.get("is_cash"):
            continue
        ticker = p.get("ticker")
        if ticker:
            held_by_ticker[ticker] = p
            universe[ticker] = "HELD"

    for ticker in _load_watchlist(WATCHLIST_PATH_DEFAULT):
        universe.setdefault(ticker, "WATCHLIST")

    for row in get_market_movers("losers")[:losers_limit]:
        ticker = (row.get("symbol") or "").upper()
        if ticker:
            universe.setdefault(ticker, "SCREEN-DISCOVERED")

    return universe, held_by_ticker


def _scan_ticker(ticker: str, classification: str, held_by_ticker: dict):
    bundle_pos = held_by_ticker.get(ticker) or {}
    asset_class = bundle_pos.get("asset_class", "")

    fund = get_fundamentals(ticker, bundle_quote=None, asset_class=asset_class)
    hist = _price_history_returns(ticker)

    price = bundle_pos.get("price") or hist.get("last_close")
    market_cap = fund.get("market_cap")
    week52_high = fund.get("52w_high")
    forward_pe = fund.get("forward_pe")
    gross_margin = fund.get("gross_margin")
    fcf = fund.get("free_cashflow")

    # Screen-discovered names are unfiltered market noise (penny stocks,
    # leveraged ETFs) until they clear the cap floor. Held and watchlist
    # names are deliberate -- never cap-filtered out of the report, even if
    # market cap can't be resolved.
    if classification == "SCREEN-DISCOVERED":
        if market_cap is None or market_cap < config.DISLOCATION_MIN_MARKET_CAP:
            return None

    drawdown_52w = None
    if price is not None and week52_high:
        drawdown_52w = (week52_high - price) / week52_high

    hit_drawdown = bool(drawdown_52w is not None and drawdown_52w >= config.DISLOCATION_MIN_DRAWDOWN_52W)
    hit_5d = bool(hist.get("return_5d") is not None and hist["return_5d"] <= config.DISLOCATION_MIN_5D_RETURN)
    hit_pe = bool(forward_pe is not None and 0 < forward_pe <= config.DISLOCATION_MAX_FWD_PE)
    hit_quality = bool(
        (gross_margin is not None and gross_margin > config.DISLOCATION_MIN_GROSS_MARGIN)
        or (fcf is not None and fcf > 0)
    )

    flagged = (hit_drawdown or hit_5d) and hit_pe and hit_quality
    flag_reasons = [
        reason for reason, hit in (
            (f"drawdown>={config.DISLOCATION_MIN_DRAWDOWN_52W*100:.0f}% from 52w high", hit_drawdown),
            (f"5d return<={config.DISLOCATION_MIN_5D_RETURN*100:.0f}%", hit_5d),
        ) if hit
    ] if flagged else []

    return {
        "ticker": ticker,
        "classification": classification,
        "style": _thesis_style(ticker) if classification == "HELD" else None,
        "price": price,
        "return_1d": hist.get("return_1d"),
        "return_5d": hist.get("return_5d"),
        "return_20d": hist.get("return_20d"),
        "52w_high": week52_high,
        "52w_low": fund.get("52w_low"),
        "drawdown_from_52w_high": drawdown_52w,
        "forward_pe": forward_pe,
        "trailing_pe": fund.get("trailing_pe"),
        "peg_ratio": fund.get("peg_ratio"),
        "gross_margin": gross_margin,
        "free_cashflow": fcf,
        "market_cap": market_cap,
        "flagged": flagged,
        "flag_reasons": flag_reasons,
    }


def run_scan(losers_limit: int = 50, live: bool = False) -> dict:
    universe, held_by_ticker = _build_universe(losers_limit)

    results = []
    for ticker, classification in sorted(universe.items()):
        row = _scan_ticker(ticker, classification, held_by_ticker)
        if row is not None:
            results.append(row)

    flagged = [r for r in results if r["flagged"]]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")

    payload = {
        "schema_version": "1.0.0",
        "timestamp_utc": timestamp,
        "thresholds": {
            "min_market_cap":   config.DISLOCATION_MIN_MARKET_CAP,
            "min_drawdown_52w": config.DISLOCATION_MIN_DRAWDOWN_52W,
            "min_5d_return":    config.DISLOCATION_MIN_5D_RETURN,
            "max_forward_pe":   config.DISLOCATION_MAX_FWD_PE,
            "min_gross_margin": config.DISLOCATION_MIN_GROSS_MARGIN,
        },
        "universe_size": len(results),
        "flagged_count": len(flagged),
        "results": results,
    }
    payload["scan_hash"] = _sha256_canonical(payload)

    os.makedirs(EXPORTS_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    json_path = os.path.join(EXPORTS_DIR, f"dislocation_scan_{timestamp}.json")
    Path(json_path).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    md_path = os.path.join(OUTPUT_DIR, f"dislocation_scan_{date_str}.md")
    Path(md_path).write_text(_render_markdown(payload), encoding="utf-8")

    return {"json_path": json_path, "md_path": md_path, "payload": payload}


def _render_markdown(payload: dict) -> str:
    lines = [
        f"# Dislocation Scan — {payload['timestamp_utc']}",
        "",
        f"Universe: {payload['universe_size']} tickers scanned, {payload['flagged_count']} flagged.",
        "",
        "Facts only -- no price targets, no buy/sell recommendations. "
        "A flag means the metrics below cleared the configured thresholds, nothing more.",
        "",
        "| Ticker | Class | Style | Price | 5d | Drawdown 52w | Fwd P/E | Gross Margin | Reasons |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    flagged = sorted(
        (r for r in payload["results"] if r["flagged"]),
        key=lambda r: r.get("drawdown_from_52w_high") or 0,
        reverse=True,
    )
    for r in flagged:
        lines.append(
            "| {ticker} | {cls} | {style} | {price} | {r5d} | {dd} | {pe} | {gm} | {reasons} |".format(
                ticker=r["ticker"],
                cls=r["classification"],
                style=r["style"] or "n/a",
                price=f"{r['price']:.2f}" if r["price"] is not None else "n/a",
                r5d=f"{r['return_5d']*100:.1f}%" if r["return_5d"] is not None else "n/a",
                dd=f"{r['drawdown_from_52w_high']*100:.1f}%" if r["drawdown_from_52w_high"] is not None else "n/a",
                pe=f"{r['forward_pe']:.1f}" if r["forward_pe"] is not None else "n/a",
                gm=f"{r['gross_margin']*100:.1f}%" if r["gross_margin"] is not None else "n/a",
                reasons="; ".join(r["flag_reasons"]),
            )
        )
    if not flagged:
        lines.append("| — | — | — | — | — | — | — | — | no names cleared all three thresholds today |")

    t = payload["thresholds"]
    lines += [
        "",
        f"Thresholds: drawdown >= {t['min_drawdown_52w']*100:.0f}% from 52w high OR "
        f"5d return <= {t['min_5d_return']*100:.0f}%, "
        f"AND forward P/E <= {t['max_forward_pe']}, "
        f"AND gross margin > {t['min_gross_margin']*100:.0f}% or positive FCF. "
        f"Screen-discovered names also require market cap >= ${t['min_market_cap']/1e9:.0f}B.",
        f"Scan hash: `{payload['scan_hash'][:16]}`",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Deterministic daily dislocation screen (facts only, no recommendations)."
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Reserved for future Sheet-write promotion; currently a no-op -- v1 only writes local files.",
    )
    parser.add_argument(
        "--losers-limit", type=int, default=50,
        help="Max FMP biggest-losers candidates to evaluate before the market-cap floor.",
    )
    args = parser.parse_args(argv)

    result = run_scan(losers_limit=args.losers_limit, live=args.live)
    payload = result["payload"]
    print(f"Universe: {payload['universe_size']} tickers, {payload['flagged_count']} flagged.")
    print(f"JSON: {result['json_path']}")
    print(f"Markdown: {result['md_path']}")


if __name__ == "__main__":
    main()
