"""
tasks/health.py — Pipeline health checks.

All checks are independent — one failure does not prevent others from running.
Checks run in parallel via ThreadPoolExecutor to keep total wall time <5s.

Exit codes (returned by run_all_checks as a summary):
    0 — all checks green
    1 — at least one CRITICAL check failed
    2 — no critical failures, but at least one WARNING check failed
"""

from __future__ import annotations

import json
import logging
import sys
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Level constants
CRITICAL = "critical"
WARNING  = "warning"

# Status constants
PASS = "pass"
WARN = "warn"
FAIL = "fail"


@dataclass
class CheckResult:
    name:    str
    label:   str    # human-readable name shown in the table
    level:   str    # CRITICAL | WARNING
    status:  str    # PASS | WARN | FAIL
    detail:  str    # one-line summary (always shown)
    verbose: str = ""  # expanded info shown only with --verbose


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe(fn: Callable[[], CheckResult]) -> CheckResult:
    """Wrap a check so an unexpected exception returns a FAIL result."""
    try:
        return fn()
    except Exception as exc:
        return CheckResult(
            name=fn.__name__, label=fn.__name__,
            level=WARNING, status=FAIL,
            detail=f"Check raised unexpected exception: {exc}",
        )


def _token_expiry_seconds(token: dict) -> float | None:
    """Return seconds until the access token expires, or None if unknown."""
    ea = token.get("expires_at")
    if ea is not None:
        return float(ea) - _time.time()
    # fallback: issued_at + expires_in
    issued  = token.get("access_token_issued_at")
    exp_in  = token.get("expires_in")
    if issued is not None and exp_in is not None:
        return float(issued) + float(exp_in) - _time.time()
    return None


def _fmt_seconds(secs: float) -> str:
    secs = int(secs)
    if secs < 0:
        return "expired"
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s"


# ---------------------------------------------------------------------------
# Critical checks
# ---------------------------------------------------------------------------

def _check_schwab_token_accounts() -> CheckResult:
    import config
    from utils.schwab_token_store import load_token

    result = CheckResult(
        name="schwab_token_accounts",
        label="schwab_token_accounts",
        level=CRITICAL, status=FAIL,
        detail="Token missing or unreadable",
    )
    try:
        token = load_token(config.SCHWAB_TOKEN_BLOB_ACCOUNTS)
        if not token:
            result.detail = "Accounts token missing from GCS"
            return result

        secs = _token_expiry_seconds(token)
        if secs is None:
            result.status  = WARN
            result.detail  = "Token present but expiry unknown"
            result.verbose = f"Token keys: {list(token.keys())}"
            return result

        if secs < 15 * 60:
            result.status  = FAIL
            result.detail  = f"Token expires in {_fmt_seconds(secs)} — refresh needed"
            result.verbose = f"expires_at={token.get('expires_at')}"
            return result

        expiry_utc = datetime.fromtimestamp(
            token.get("expires_at", 0), tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")
        result.status  = PASS
        result.detail  = f"Valid, expires in {_fmt_seconds(secs)}"
        result.verbose = f"Full expiry: {expiry_utc}"
    except Exception as e:
        result.detail = f"Error reading accounts token: {e}"
    return result


def _check_schwab_token_market() -> CheckResult:
    import config
    from utils.schwab_token_store import load_token

    result = CheckResult(
        name="schwab_token_market",
        label="schwab_token_market",
        level=CRITICAL, status=FAIL,
        detail="Token missing or unreadable",
    )
    try:
        token = load_token(config.SCHWAB_TOKEN_BLOB_MARKET)
        if not token:
            result.detail = "Market token missing from GCS"
            return result

        secs = _token_expiry_seconds(token)
        if secs is None:
            result.status  = WARN
            result.detail  = "Token present but expiry unknown"
            result.verbose = f"Token keys: {list(token.keys())}"
            return result

        if secs < 15 * 60:
            result.status  = FAIL
            result.detail  = f"Token expires in {_fmt_seconds(secs)} — refresh needed"
            result.verbose = f"expires_at={token.get('expires_at')}"
            return result

        expiry_utc = datetime.fromtimestamp(
            token.get("expires_at", 0), tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M UTC")
        result.status  = PASS
        result.detail  = f"Valid, expires in {_fmt_seconds(secs)}"
        result.verbose = f"Full expiry: {expiry_utc}"
    except Exception as e:
        result.detail = f"Error reading market token: {e}"
    return result


def _check_schwab_api_positions() -> CheckResult:
    result = CheckResult(
        name="schwab_api_positions",
        label="schwab_api_positions",
        level=CRITICAL, status=FAIL,
        detail="Could not connect to Schwab API",
    )
    try:
        from utils.schwab_client import get_accounts_client

        client = get_accounts_client()
        if client is None:
            result.detail = "Schwab client returned None (token missing?)"
            return result

        r = client.get_accounts(fields=client.Account.Fields.POSITIONS)
        r.raise_for_status()
        accounts = r.json()
        if not isinstance(accounts, list):
            result.detail = "Unexpected response format from get_accounts()"
            return result

        pos_count = sum(
            len(acc.get("securitiesAccount", {}).get("positions", []))
            for acc in accounts
        )
        result.status  = PASS
        result.detail  = f"{len(accounts)} account(s), {pos_count} positions"
        result.verbose = f"Account hashes: {[acc.get('hashValue','?')[-4:] for acc in accounts]}"
    except Exception as e:
        result.detail = f"Schwab API error: {e}"
    return result


def _check_sheet_reachable() -> CheckResult:
    result = CheckResult(
        name="sheet_reachable",
        label="sheet_reachable",
        level=CRITICAL, status=FAIL,
        detail="Could not open portfolio Sheet",
    )
    try:
        import config
        from utils.sheet_readers import get_gspread_client

        gc = get_gspread_client()
        ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
        worksheets = ss.worksheets()
        result.status  = PASS
        result.detail  = f"Opened: {ss.title!r} ({len(worksheets)} tabs)"
        result.verbose = f"Tabs: {[ws.title for ws in worksheets]}"
    except Exception as e:
        result.detail = f"Sheet open failed: {e}"
    return result


def _check_latest_bundle_exists() -> CheckResult:
    result = CheckResult(
        name="latest_bundle_exists",
        label="latest_bundle_exists",
        level=CRITICAL, status=FAIL,
        detail="No market bundles found in bundles/",
    )
    try:
        candidates = sorted(
            Path("bundles").glob("context_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            return result

        latest = candidates[-1]
        result.status  = PASS
        result.detail  = f"{len(candidates)} bundle(s); latest: {latest.name}"
        result.verbose = "\n".join(f"  {p.name}" for p in candidates[-5:])
    except Exception as e:
        result.detail = f"Bundle scan failed: {e}"
    return result


# ---------------------------------------------------------------------------
# Warning checks
# ---------------------------------------------------------------------------

def _check_latest_bundle_age() -> CheckResult:
    result = CheckResult(
        name="latest_bundle_age",
        label="latest_bundle_age",
        level=WARNING, status=WARN,
        detail="No market bundles found",
    )
    try:
        candidates = sorted(
            Path("bundles").glob("context_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            return result

        latest = candidates[-1]
        age_secs = _time.time() - latest.stat().st_mtime
        age_h = age_secs / 3600

        if age_h < 24:
            result.status = PASS
            result.detail = f"Bundle is {age_h:.1f}h old — current"
        elif age_h < 72:
            result.status = WARN
            result.detail = f"Bundle is {age_h:.1f}h old — consider refreshing"
        else:
            result.status = FAIL
            result.detail = f"Bundle is {age_h/24:.1f}d old — stale"

        result.verbose = f"Latest bundle: {latest.name}"
    except Exception as e:
        result.detail = f"Bundle age check failed: {e}"
    return result


def _check_fmp_cache_coverage() -> CheckResult:
    result = CheckResult(
        name="fmp_cache_coverage",
        label="fmp_cache_coverage",
        level=WARNING, status=WARN,
        detail="Could not assess FMP cache",
    )
    try:
        import config
        from utils.fmp_client import FMP_CACHE_TTL_DAYS, FMP_CACHE_DIR
        from datetime import timedelta

        # Get tickers from latest bundle
        candidates = sorted(
            Path("bundles").glob("context_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            result.detail = "No bundle to compare against"
            return result

        with open(candidates[-1], "r", encoding="utf-8") as fh:
            bundle = json.load(fh)

        skip = set(config.CASH_TICKERS)
        tickers = [
            p.get("ticker") or p.get("Ticker")
            for p in bundle.get("positions", [])
            if (p.get("ticker") or p.get("Ticker")) not in skip
        ]
        total = len(tickers)
        if total == 0:
            result.status = WARN
            result.detail = "Bundle has no non-cash positions"
            return result

        cache_dir = FMP_CACHE_DIR
        ttl = timedelta(days=FMP_CACHE_TTL_DAYS)
        now = datetime.now()
        valid_tickers = []
        stale_tickers = []

        for t in tickers:
            p = cache_dir / f"{t}_bndl.json"
            if p.exists():
                age = now - datetime.fromtimestamp(p.stat().st_mtime)
                if age < ttl:
                    valid_tickers.append(t)
                else:
                    stale_tickers.append(t)
            else:
                stale_tickers.append(t)

        pct = len(valid_tickers) / total * 100
        if pct >= 80:
            result.status = PASS
            result.detail = f"{len(valid_tickers)}/{total} positions cached ({pct:.0f}%)"
        else:
            result.status = WARN
            result.detail = f"{len(valid_tickers)}/{total} positions cached ({pct:.0f}%) — run snapshot"

        result.verbose = (
            f"Valid cache: {sorted(valid_tickers)}\n"
            f"Missing/stale: {sorted(stale_tickers)}"
        )
    except Exception as e:
        result.detail = f"FMP cache check failed: {e}"
    return result


def _check_yfinance_connectivity() -> CheckResult:
    result = CheckResult(
        name="yfinance_connectivity",
        label="yfinance_connectivity",
        level=WARNING, status=FAIL,
        detail="yfinance SPY fetch failed",
    )
    try:
        import yfinance as yf

        t = yf.Ticker("SPY")
        price = t.fast_info.last_price
        if price and price > 0:
            result.status = PASS
            result.detail = f"SPY last price: ${price:.2f}"
        else:
            result.status = WARN
            result.detail = "SPY fetch returned no price"
    except Exception as e:
        result.detail = f"yfinance error: {e}"
    return result


def _check_transactions_freshness() -> CheckResult:
    result = CheckResult(
        name="transactions_freshness",
        label="transactions_freshness",
        level=WARNING, status=WARN,
        detail="Could not read Transactions tab",
    )
    try:
        import config
        from utils.sheet_readers import get_gspread_client

        gc = get_gspread_client()
        ss = gc.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_TRANSACTIONS)

        # Read Trade Date column (col 1) — fast single-column read
        dates_raw = ws.col_values(1)
        # Strip header and empty cells
        date_strs = [
            d.strip() for d in dates_raw[1:]
            if d.strip() and d.strip().lower() not in ("trade date", "date")
        ]

        if not date_strs:
            result.detail = "Transactions tab is empty"
            return result

        # Parse dates
        parsed = []
        for ds in date_strs:
            for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
                try:
                    parsed.append(datetime.strptime(ds, fmt).date())
                    break
                except ValueError:
                    pass

        if not parsed:
            result.status = WARN
            result.detail = f"{len(date_strs)} rows but no parseable dates"
            return result

        most_recent = max(parsed)
        today = datetime.now().date()
        days_ago = (today - most_recent).days

        # Approximate business-day check: 7 calendar days ≈ 5 business days
        if days_ago <= 10:
            result.status = PASS
            result.detail = f"Most recent: {most_recent} ({days_ago} days ago, {len(parsed)} total rows)"
        else:
            result.status = WARN
            result.detail = f"Most recent: {most_recent} ({days_ago} days ago) — may be stale"

        result.verbose = f"Date range: {min(parsed)} → {most_recent}  ({len(parsed)} rows)"
    except Exception as e:
        result.detail = f"Transactions check failed: {e}"
    return result


def _check_thesis_coverage() -> CheckResult:
    result = CheckResult(
        name="thesis_coverage",
        label="thesis_coverage",
        level=WARNING, status=WARN,
        detail="Could not assess thesis coverage",
    )
    try:
        # Load latest bundle for positions + weights
        candidates = sorted(
            Path("bundles").glob("context_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            result.detail = "No bundle to assess coverage against"
            return result

        with open(candidates[-1], "r", encoding="utf-8") as fh:
            bundle = json.load(fh)

        import config

        skip = set(config.CASH_TICKERS)
        theses_dir = Path("vault/theses")

        # Positions > 2% weight
        significant = [
            p for p in bundle.get("positions", [])
            if float(p.get("weight_pct") or p.get("weight") or 0) > 2.0
            and (p.get("ticker") or p.get("Ticker") or "") not in skip
        ]

        if not significant:
            result.status = PASS
            result.detail = "No positions > 2% weight found in bundle"
            return result

        with_thesis = []
        without_thesis = []
        for p in significant:
            ticker = p.get("ticker") or p.get("Ticker") or ""
            thesis_file = theses_dir / f"{ticker}_thesis.md"
            if thesis_file.exists():
                with_thesis.append(ticker)
            else:
                without_thesis.append(ticker)

        total = len(significant)
        pct = len(with_thesis) / total * 100

        if pct >= 90:
            result.status = PASS
            result.detail = f"{len(with_thesis)}/{total} positions >2% have theses ({pct:.0f}%)"
        else:
            result.status = WARN
            result.detail = (
                f"{len(with_thesis)}/{total} positions >2% have theses ({pct:.0f}%) "
                f"— missing: {', '.join(without_thesis)}"
            )

        result.verbose = (
            f"With thesis: {sorted(with_thesis)}\n"
            f"Missing:     {sorted(without_thesis)}"
        )
    except Exception as e:
        result.detail = f"Thesis coverage check failed: {e}"
    return result


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

# Ordered list of all check functions
_ALL_CHECKS: list[Callable[[], CheckResult]] = [
    _check_schwab_token_accounts,
    _check_schwab_token_market,
    _check_schwab_api_positions,
    _check_sheet_reachable,
    _check_latest_bundle_exists,
    _check_latest_bundle_age,
    _check_fmp_cache_coverage,
    _check_yfinance_connectivity,
    _check_transactions_freshness,
    _check_thesis_coverage,
]

_CHECK_ORDER = {fn.__name__.lstrip("_"): i for i, fn in enumerate(_ALL_CHECKS)}


def run_all_checks() -> list[CheckResult]:
    """
    Run all health checks in parallel and return results in display order.
    Each check is independently isolated — one failure cannot affect others.
    """
    results: list[CheckResult] = []

    with ThreadPoolExecutor(max_workers=len(_ALL_CHECKS)) as pool:
        futures = {pool.submit(_safe, fn): fn for fn in _ALL_CHECKS}
        for future in as_completed(futures):
            results.append(future.result())

    # Restore display order regardless of completion order
    results.sort(key=lambda r: _CHECK_ORDER.get(r.name, 99))
    return results


def exit_code(results: list[CheckResult]) -> int:
    """Return the appropriate CLI exit code for a set of check results."""
    has_critical_fail = any(
        r.level == CRITICAL and r.status == FAIL for r in results
    )
    has_any_fail_or_warn = any(r.status in (FAIL, WARN) for r in results)

    if has_critical_fail:
        return 1
    if has_any_fail_or_warn:
        return 2
    return 0
