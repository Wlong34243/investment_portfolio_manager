"""
tasks/build_command_center.py — Build the 0_DASHBOARD Command Center tab.

Reads from: Holdings_Current, Daily_Snapshots, Risk_Metrics, Valuation_Card, Agent_Outputs.
Writes to:  0_DASHBOARD (clear-and-rebuild, single batch_update call).
One position row per holding (sorted by Market Value descending), joined against
Valuation_Card and the latest Agent_Outputs run, plus one bulk yfinance call for
52-week range (not baked into any tab yet). No price targets or recommendations
originate here — Trim/Add/Signal are all read from existing sandboxed surfaces.
"""

import json
import logging
import statistics
import time
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Force project root to front of path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
else:
    sys.path.remove(_ROOT)
    sys.path.insert(0, _ROOT)

import pandas as pd

import config
from utils.sheet_readers import get_gspread_client, read_gsheet_robust
from utils.sheet_writers import safe_execute
from utils.agent_signals import get_latest_agent_outputs, ACTION_SEVERITIES
from utils.level_coverage import compute_level_coverage, format_footer_line
from tasks.compute_rotation_attribution import (
    HORIZONS as ROTATION_HORIZONS,
    _as_float as _rotation_as_float,
    compute_vti_qqq_signflips,
    partition_rotation_rows,
)

logger = logging.getLogger(__name__)

# Position table columns, left to right (A..P)
_POS_COLS = [
    "Ticker", "MV", "Wt%", "Price", "Day%", "UGL $", "UGL %",
    "Fwd P/E", "PEG", "52w %", "Trim", "Add", "->Trim %", "->Add %", "Signal", "Earnings",
]
_NCOLS = 18  # widest row is the KPI strip (9 label/value pairs = 18 cells)
_DATA_START_ROW = 5


def _pad(row: list, n: int = _NCOLS) -> list:
    return (row + [""] * n)[:n]


# ---------------------------------------------------------------------------
# Tab readers — never raise; return [] on failure
# ---------------------------------------------------------------------------

def _read_records(ss, tab: str) -> list[dict]:
    try:
        ws = ss.worksheet(tab)
        df = read_gsheet_robust(ws)
        return df.to_dict("records")
    except Exception as e:
        logger.warning("Could not read tab %s: %s", tab, e)
        return []


def _rotation_performance(rotation_rows: list[dict]) -> dict:
    """
    Surface the aggregate the attribution module already computed -- reuses
    partition_rotation_rows()/compute_vti_qqq_signflips() from
    compute_rotation_attribution.py so this can't drift from the module of
    record. No new classification or return math happens here.
    """
    included, excluded = partition_rotation_rows(rotation_rows)
    flip_count, _ = compute_vti_qqq_signflips(included)

    horizons = {}
    for h in ROTATION_HORIZONS:
        residuals, vs_idx, sell_vs, dates = [], [], [], []
        for r in included:
            res = _rotation_as_float(r.get(f"Residual_Pair_{h}d"))
            if res is None:
                continue
            residuals.append(res)
            v = _rotation_as_float(r.get(f"Vs_Index_{h}d"))
            s = _rotation_as_float(r.get(f"Sell_Vs_Index_{h}d"))
            if v is not None:
                vs_idx.append(v)
            if s is not None:
                sell_vs.append(s)
            d = str(r.get("Date") or "")
            if d:
                dates.append(d)

        n = len(residuals)
        horizons[h] = {
            "n": n,
            "window": f"{min(dates)} -> {max(dates)}" if dates else "-",
            "residual_median": statistics.median(residuals) if residuals else None,
            "hit_rate": (sum(1 for x in residuals if x > 0) / n) if n else None,
            "vs_index_median": statistics.median(vs_idx) if vs_idx else None,
            "sell_vs_index_median": statistics.median(sell_vs) if sell_vs else None,
        }

    total = len(included) + len(excluded)
    return {
        "included_n": len(included),
        "excluded_n": len(excluded),
        "excluded_pct": (len(excluded) / total) if total else None,
        "signflip_count": flip_count,
        "signflip_total": len(included),
        "horizons": horizons,
    }


# ---------------------------------------------------------------------------
# System health helpers
# ---------------------------------------------------------------------------

def _latest_bundle_hash() -> str:
    try:
        candidates = sorted(
            Path("bundles").glob("context_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            return "n/a"
        with open(candidates[-1], "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data.get("bundle_hash", "n/a")[:8]
    except Exception:
        return "n/a"


def _schwab_token_status() -> str:
    try:
        from datetime import timezone
        # Check sentinel first for an active failure
        from tasks.health import read_failure_sentinel
        sentinel = read_failure_sentinel()
        if sentinel:
            # Check if schwab token was a failing check
            for fc in sentinel.get("failing_checks", []):
                if "schwab_token" in fc.get("name", ""):
                    return "AUTH REQUIRED"
            # Parse timestamp to report how long the pipeline has been degraded
            ts_str = sentinel.get("timestamp_utc")
            if ts_str:
                try:
                    ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    delta_days = (datetime.now(timezone.utc) - ts).days
                    return f"STALE ({delta_days}d)"
                except Exception:
                    return "STALE"
            return "DEGRADED"

        from google.cloud import storage
        client = storage.Client()
        blob = client.bucket(config.SCHWAB_TOKEN_BUCKET).blob(config.SCHWAB_TOKEN_BLOB_ACCOUNTS)
        data = json.loads(blob.download_as_text())
        expires_at = data.get("expires_at")
        if not expires_at:
            return "AUTH REQUIRED"
        delta_days = (float(expires_at) - time.time()) / 86400
        if delta_days < 0:
            return f"STALE ({abs(delta_days):.0f}d)"
        if delta_days < 2:
            return "Expiring soon"
        return "OK"
    except Exception:
        try:
            from tasks.health import read_failure_sentinel
            sentinel = read_failure_sentinel()
            if sentinel:
                return "AUTH REQUIRED"
        except Exception:
            pass
        return "AUTH REQUIRED"


def _fmp_cache_age() -> str:
    try:
        candidates = (
            list(Path(".").glob("*fmp_cache*"))
            + list(Path("data").glob("*fmp*"))
        )
        if not candidates:
            return "n/a"
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
        age_days = (time.time() - newest.stat().st_mtime) / 86400
        return f"{age_days:.0f}d"
    except Exception:
        return "n/a"


def _spy_ytd_pct() -> Optional[float]:
    """Return SPY YTD return as a float percentage (e.g. 8.5 for 8.5%), or None on failure."""
    try:
        import yfinance as yf
        hist = yf.Ticker("SPY").history(period="ytd")
        if hist.empty:
            return None
        return (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
    except Exception:
        return None


def _check_system_health() -> dict:
    return {
        "last_refresh": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "bundle_hash": _latest_bundle_hash(),
        "schwab_token": _schwab_token_status(),
        "fmp_cache_age": _fmp_cache_age(),
    }


# ---------------------------------------------------------------------------
# Headline KPIs — returns raw numbers (or None), never pre-formatted strings.
# Writing raw numbers with a real Sheets number format (instead of a baked
# string like "+$530.00") is what makes the old #NAME? bug impossible: Sheets
# never has to parse a leading '+' as a formula, because nothing here is a
# string.
# ---------------------------------------------------------------------------

def _compute_headline_kpis(daily_rows: list[dict], holdings_rows: list[dict]) -> dict:
    out = {
        "total_value": None, "cash_pct": None, "strategic_cash": None,
        "day_change_dollar": None, "day_change_pct": None,
        "mtd_pct": None, "ytd_pct": None, "snapshot_date": None,
    }
    if not daily_rows:
        return out

    df = pd.DataFrame(daily_rows)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).sort_values("Date")
    if df.empty:
        return out

    for col in ["Total Value", "Cash Value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    latest = df.iloc[-1]
    total_value = latest.get("Total Value")
    cash_value = latest.get("Cash Value") or 0.0
    out["snapshot_date"] = latest["Date"]

    if total_value and total_value > 0:
        out["total_value"] = float(total_value)
        out["cash_pct"] = float(cash_value) / float(total_value)

    # Strategic cash: Market Value sum for CASH_TICKERS
    if holdings_rows:
        df_h = pd.DataFrame(holdings_rows)
        df_h["Market Value"] = pd.to_numeric(df_h.get("Market Value", pd.Series(dtype=float)), errors="coerce").fillna(0)
        strat_cash = df_h.loc[df_h["Ticker"].astype(str).isin(config.CASH_TICKERS), "Market Value"].sum()
        out["strategic_cash"] = float(strat_cash)

    # Day change
    if len(df) >= 2 and total_value:
        prev_val = pd.to_numeric(df.iloc[-2].get("Total Value"), errors="coerce")
        if prev_val:
            out["day_change_dollar"] = float(total_value - prev_val)
            out["day_change_pct"] = float((total_value - prev_val) / prev_val)

    now = latest["Date"]

    # MTD
    month_rows = df[df["Date"].dt.month == now.month]
    if not month_rows.empty and total_value:
        start_val = pd.to_numeric(month_rows.iloc[0].get("Total Value"), errors="coerce")
        if start_val:
            out["mtd_pct"] = float(total_value / start_val - 1)

    # YTD
    year_rows = df[df["Date"].dt.year == now.year]
    if not year_rows.empty and total_value:
        start_val = pd.to_numeric(year_rows.iloc[0].get("Total Value"), errors="coerce")
        if start_val:
            out["ytd_pct"] = float(total_value / start_val - 1)

    return out


def _compute_beta(risk_rows: list[dict]) -> Optional[float]:
    if not risk_rows:
        return None
    latest = risk_rows[-1]
    try:
        return float(latest.get("Portfolio Beta"))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 52-week range — not baked into any tab yet, so one bulk yfinance call here.
# ---------------------------------------------------------------------------

def _fetch_52w_ranges(tickers: list[str]) -> dict[str, tuple[float, float]]:
    if not tickers:
        return {}
    try:
        import yfinance as yf
        data = yf.download(tickers, period="1y", progress=False, group_by="ticker", threads=True)
    except Exception as e:
        logger.warning("52-week range bulk fetch failed: %s", e)
        return {}

    ranges: dict[str, tuple[float, float]] = {}
    for t in tickers:
        try:
            closes = data[t]["Close"].dropna() if len(tickers) > 1 else data["Close"].dropna()
            if not closes.empty:
                ranges[t] = (float(closes.min()), float(closes.max()))
        except Exception:
            continue
    return ranges


# ---------------------------------------------------------------------------
# Agent signal — reuses get_latest_agent_outputs(); picks the highest-priority
# active signal for a ticker the same way build_decision_view.py does, so the
# two views agree on what "ADD"/"TRIM" means for a given ticker. No price
# targets or new recommendations are generated here, only surfaced.
# ---------------------------------------------------------------------------

_SIGNAL_PRIORITY = ("valuation", "macro", "thesis")


def _ticker_signal(df_agent: pd.DataFrame, ticker: str) -> tuple[str, str]:
    """Return (signal_chip, rationale) for a ticker, or ("", "") if no active signal."""
    if df_agent.empty:
        return "", ""
    ticker_agents = df_agent[df_agent["ticker"] == ticker]
    if ticker_agents.empty:
        return "", ""
    for agent_name in _SIGNAL_PRIORITY:
        agent_rows = ticker_agents[ticker_agents["agent"] == agent_name]
        if agent_rows.empty:
            continue
        row = agent_rows.iloc[0]
        sev = str(row.get("severity", "")).lower()
        if sev not in ACTION_SEVERITIES:
            continue
        signal = str(row.get("signal_type", "") or row.get("action", ""))
        if signal:
            rationale = str(row.get("rationale", "") or row.get("action", ""))
            return signal.upper(), rationale
    return "", ""


# ---------------------------------------------------------------------------
# Position table assembly — Holdings_Current x Valuation_Card x Agent signals
# ---------------------------------------------------------------------------

def _safe_float(val):
    try:
        return float(val) if val not in (None, "", "—") else None
    except (TypeError, ValueError):
        return None


def _safe_float_nonzero(val):
    """
    Like _safe_float, but also treats 0.0 as missing. read_gsheet_robust()
    fillna(0.0)s every numeric Valuation_Card column, so a blank Trim Target /
    Add Target / PEG / Forward P/E cell (normal for a pure ETF) comes back as
    a real 0.0, not None -- and a genuine 0.0 in any of these fields is never
    meaningful data, so treating it as missing is always correct here.
    """
    f = _safe_float(val)
    return f if f else None


def _build_position_table(
    holdings_rows: list[dict],
    valuation_rows: list[dict],
    df_agent: pd.DataFrame,
) -> list[dict]:
    if not holdings_rows:
        return []

    df_h = pd.DataFrame(holdings_rows)
    for col in ["Market Value", "Weight", "Price", "Daily Change %", "Unrealized G/L", "Unrealized G/L %"]:
        if col in df_h.columns:
            df_h[col] = pd.to_numeric(df_h[col], errors="coerce").fillna(0)
    df_h = df_h[~df_h["Ticker"].astype(str).isin(config.CASH_TICKERS)]
    df_h = df_h.sort_values("Market Value", ascending=False)

    val_map: dict[str, dict] = {}
    for row in (valuation_rows or []):
        ticker = str(row.get("Ticker", "")).strip()
        if ticker:
            val_map[ticker] = row

    tickers = df_h["Ticker"].astype(str).tolist()
    ranges_52w = _fetch_52w_ranges(tickers)

    # Fetch cached earnings calendar dates +/- 3 days from FMP
    from utils.fmp_client import get_earnings_calendar_cached
    earnings_map = get_earnings_calendar_cached(tickers)

    results = []
    for _, row in df_h.iterrows():
        ticker = str(row["Ticker"])
        price = float(row["Price"]) if row["Price"] else 0.0
        vdata = val_map.get(ticker, {})

        fwd_pe = _safe_float_nonzero(vdata.get("Forward P/E (yf)"))
        peg = _safe_float_nonzero(vdata.get("PEG"))
        trim = _safe_float_nonzero(vdata.get("Trim Target"))
        add = _safe_float_nonzero(vdata.get("Add Target"))

        dist_trim = (trim - price) / price if trim and price else None
        dist_add = (price - add) / add if add and price else None

        lo_hi = ranges_52w.get(ticker)
        pos_52w = None
        if lo_hi and price:
            lo, hi = lo_hi
            if hi > lo:
                pos_52w = (price - lo) / (hi - lo)

        signal, rationale = _ticker_signal(df_agent, ticker)
        no_valuation = fwd_pe is None and peg is None and trim is None and add is None

        # Compute Earnings proximity flag (+/- 3 days)
        earnings_val = ""
        earning_date_str = earnings_map.get(ticker)
        if earning_date_str:
            try:
                e_date = datetime.strptime(earning_date_str, "%Y-%m-%d").date()
                today_date = datetime.now().date()
                delta_days = (e_date - today_date).days
                if delta_days == 0:
                    earnings_val = "TODAY"
                elif delta_days > 0:
                    earnings_val = f"T+{delta_days}"
                else:
                    earnings_val = f"T-{abs(delta_days)}"
            except Exception:
                pass

        results.append({
            "Ticker": ticker,
            "MV": float(row["Market Value"]),
            "Wt%": float(row["Weight"]),
            "Price": price,
            "Day%": float(row["Daily Change %"]),
            "UGL $": float(row["Unrealized G/L"]),
            "UGL %": float(row["Unrealized G/L %"]),
            "Fwd P/E": fwd_pe,
            "PEG": peg,
            "52w %": pos_52w,
            "Trim": trim,
            "Add": add,
            "->Trim %": dist_trim,
            "->Add %": dist_add,
            "Signal": signal,
            "Rationale": rationale,
            "no_valuation": no_valuation,
            "Earnings": earnings_val,
        })
    return results


# ---------------------------------------------------------------------------
# Grid builder
# ---------------------------------------------------------------------------

def _rp_pct(v) -> str:
    """Signed percent, for returns/residuals (direction matters)."""
    return f"{v:+.1%}" if v is not None else "-"


def _rp_pct_u(v) -> str:
    """Unsigned percent, for shares (hit rate, excluded %)."""
    return f"{v:.1%}" if v is not None else "-"


def _rotation_block_rows(rp: dict) -> list[list]:
    """
    Rotation-performance block, appended after the KPI/position table.
    Surfaces exactly what compute_rotation_attribution.py already computed
    (via _rotation_performance()/partition_rotation_rows()/
    compute_vti_qqq_signflips()) -- no new classification or return math.
    Deliberately labeled as evidence, not a scorecard: no rank/grade/trend arrow.
    """
    rows: list[list] = []
    rows.append(_pad([
        "ROTATION ATTRIBUTION -- EVIDENCE, ONE REGIME, OVERLAPPING WINDOWS"
    ]))
    rows.append(_pad([
        "Included", rp["included_n"],
        "Excluded", f"{rp['excluded_n']} ({_rp_pct_u(rp['excluded_pct'])})",
        "VTI/QQQ sign-flips", f"{rp['signflip_count']} of {rp['signflip_total']}",
    ]))
    rows.append(_pad([]))
    rows.append(_pad([
        "Horizon", "N Matured", "Window", "Residual Median (headline)",
        "Hit Rate", "Vs_Index (VTI) Median", "Sell_Vs_Index Median",
    ]))
    for h in ROTATION_HORIZONS:
        hz = rp["horizons"].get(h, {})
        rows.append(_pad([
            f"{h}d", hz.get("n", 0), hz.get("window", "-"),
            _rp_pct(hz.get("residual_median")),
            _rp_pct_u(hz.get("hit_rate")),
            _rp_pct(hz.get("vs_index_median")),
            _rp_pct(hz.get("sell_vs_index_median")),
        ]))
    return rows


def _build_grid(
    headline: dict,
    beta: Optional[float],
    positions: list[dict],
    health: dict,
    spy_ytd_raw: Optional[float],
    level_coverage: Optional[dict] = None,
    rotation_perf: Optional[dict] = None,
) -> list[list]:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    vs_spy = None
    if spy_ytd_raw is not None and headline.get("ytd_pct") is not None:
        vs_spy = headline["ytd_pct"] - (spy_ytd_raw / 100.0)

    grid: list[list] = []

    # R1: Title
    grid.append(_pad([f"PORTFOLIO COMMAND CENTER  —  As of {now_str}"]))

    # R2: KPI strip (9 label/value pairs)
    grid.append(_pad([
        "Total Value", headline.get("total_value"),
        "Day Change $", headline.get("day_change_dollar"),
        "Day %", headline.get("day_change_pct"),
        "MTD %", headline.get("mtd_pct"),
        "YTD %", headline.get("ytd_pct"),
        "vs SPY YTD", vs_spy,
        "Cash %", headline.get("cash_pct"),
        "Strategic Cash $", headline.get("strategic_cash"),
        "Beta", beta,
    ]))

    # R3: blank
    grid.append(_pad([]))

    # R4: position table header
    grid.append(_pad(_POS_COLS))

    # R5+: position rows, sorted by Market Value descending, cash excluded
    for pos in positions:
        grid.append(_pad([
            pos["Ticker"], pos["MV"], pos["Wt%"], pos["Price"], pos["Day%"],
            pos["UGL $"], pos["UGL %"], pos["Fwd P/E"], pos["PEG"], pos["52w %"],
            pos["Trim"], pos["Add"], pos["->Trim %"], pos["->Add %"], pos["Signal"], pos["Earnings"],
        ]))

    # blank
    grid.append(_pad([]))

    # Last row: system health
    footer_row = [
        "Last Refresh", health["last_refresh"],
        "Bundle Hash", health["bundle_hash"],
        "Schwab Token", health["schwab_token"],
        "FMP Cache Age", health["fmp_cache_age"],
    ]
    if level_coverage:
        footer_row += ["Levels", format_footer_line(level_coverage)]
    grid.append(_pad(footer_row))

    if rotation_perf is not None:
        grid.append(_pad([]))
        grid.extend(_rotation_block_rows(rotation_perf))

    # None -> "" so gspread never has to serialize a bare null into a cell
    return [["" if c is None else c for c in row] for row in grid]


# ---------------------------------------------------------------------------
# DRY RUN output
# ---------------------------------------------------------------------------

def _fmt_preview(val, kind: str) -> str:
    if val is None or val == "":
        return "—"
    try:
        f = float(val)
    except (TypeError, ValueError):
        return str(val)
    if kind == "$":
        return f"${f:,.2f}"
    if kind == "$0":
        return f"${f:,.0f}"
    if kind == "%":
        return f"{f * 100:+.1f}%"
    if kind == "%u":
        return f"{f * 100:.1f}%"
    if kind == "f2":
        return f"{f:.2f}"
    if kind == "f1":
        return f"{f:.1f}"
    return str(val)


def _print_dry_run(
    headline: dict, beta: Optional[float], positions: list[dict],
    health: dict, spy_ytd_raw: Optional[float], n_rules: int, n_notes: int,
    level_coverage: Optional[dict] = None,
    rotation_perf: Optional[dict] = None,
) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()

    vs_spy = None
    if spy_ytd_raw is not None and headline.get("ytd_pct") is not None:
        vs_spy = headline["ytd_pct"] - (spy_ytd_raw / 100.0)

    console.print(
        f"Total Value {_fmt_preview(headline.get('total_value'), '$0')}  |  "
        f"Day {_fmt_preview(headline.get('day_change_dollar'), '$')} "
        f"({_fmt_preview(headline.get('day_change_pct'), '%')})  |  "
        f"MTD {_fmt_preview(headline.get('mtd_pct'), '%')}  |  "
        f"YTD {_fmt_preview(headline.get('ytd_pct'), '%')}  |  "
        f"vs SPY {_fmt_preview(vs_spy, '%')}  |  "
        f"Cash {_fmt_preview(headline.get('cash_pct'), '%u')}  |  "
        f"Strategic Cash {_fmt_preview(headline.get('strategic_cash'), '$0')}  |  "
        f"Beta {_fmt_preview(beta, 'f2')}"
    )

    table = Table(show_header=True, header_style="bold")
    for col in _POS_COLS:
        table.add_column(col)
    for pos in positions:
        table.add_row(
            pos["Ticker"],
            _fmt_preview(pos["MV"], "$0"),
            _fmt_preview(pos["Wt%"], "%u"),
            _fmt_preview(pos["Price"], "$"),
            _fmt_preview(pos["Day%"], "%"),
            _fmt_preview(pos["UGL $"], "$0"),
            _fmt_preview(pos["UGL %"], "%"),
            _fmt_preview(pos["Fwd P/E"], "f1"),
            _fmt_preview(pos["PEG"], "f2"),
            _fmt_preview(pos["52w %"], "%u"),
            _fmt_preview(pos["Trim"], "$"),
            _fmt_preview(pos["Add"], "$"),
            _fmt_preview(pos["->Trim %"], "%"),
            _fmt_preview(pos["->Add %"], "%"),
            pos["Signal"] or "",
            pos["Earnings"] or "",
        )
    console.print(table)
    footer = (
        f"Last Refresh {health['last_refresh']}  |  Bundle {health['bundle_hash']}  |  "
        f"Schwab {health['schwab_token']}  |  FMP Cache {health['fmp_cache_age']}"
    )
    if level_coverage:
        footer += f"  |  {format_footer_line(level_coverage)}"
    console.print(footer)
    console.print(f"[dim]Would write {n_rules} conditional-format rules and {n_notes} cell notes.[/]")

    if rotation_perf is not None:
        console.print("\n[bold]ROTATION ATTRIBUTION — EVIDENCE, ONE REGIME, OVERLAPPING WINDOWS[/]")
        console.print(
            f"Included {rotation_perf['included_n']}  |  "
            f"Excluded {rotation_perf['excluded_n']} ({_rp_pct_u(rotation_perf['excluded_pct'])})  |  "
            f"VTI/QQQ sign-flips {rotation_perf['signflip_count']} of {rotation_perf['signflip_total']}"
        )
        rp_table = Table(show_header=True, header_style="bold")
        for col in ["Horizon", "N Matured", "Window", "Residual Median", "Hit Rate", "Vs_Index (VTI)", "Sell_Vs_Index"]:
            rp_table.add_column(col)
        for h in ROTATION_HORIZONS:
            hz = rotation_perf["horizons"].get(h, {})
            rp_table.add_row(
                f"{h}d", str(hz.get("n", 0)), hz.get("window", "-"),
                _rp_pct(hz.get("residual_median")), _rp_pct_u(hz.get("hit_rate")),
                _rp_pct(hz.get("vs_index_median")), _rp_pct(hz.get("sell_vs_index_median")),
            )
        console.print(rp_table)

    console.print("[dim]DRY RUN — no Sheet writes. Re-run with --live to apply.[/]")


# ---------------------------------------------------------------------------
# Formatting (LIVE only)
# ---------------------------------------------------------------------------

_N_CONDITIONAL_RULES = 8  # Day% (2) + UGL% (2) + Trim gradient (1) + Add gradient (1) + banding (1) + ETF grey-text (1)


def _apply_formatting(ws, headline: dict, positions: list[dict]) -> None:
    try:
        from gspread_formatting import (
            CellFormat, Color, TextFormat, NumberFormat,
            ConditionalFormatRule, BooleanRule, BooleanCondition,
            GradientRule, InterpolationPoint, GridRange,
            get_conditional_format_rules, format_cell_ranges,
            set_frozen, set_column_widths,
        )
    except ImportError:
        logger.warning("gspread_formatting not installed; skipping Command Center formatting.")
        return

    NAVY = Color(0.10, 0.15, 0.27)
    STALE_RED = Color(0.72, 0.11, 0.11)
    WHITE = Color(1, 1, 1)
    GREY_BG = Color(0.95, 0.95, 0.95)
    GREY_TEXT = Color(0.6, 0.6, 0.6)
    GREEN = Color(0.20, 0.66, 0.33)
    RED_TEXT = Color(0.80, 0.20, 0.20)

    data_end = _DATA_START_ROW - 1 + max(len(positions), 1)

    is_stale = False
    snap_date = headline.get("snapshot_date")
    if snap_date is not None:
        try:
            is_stale = (datetime.now() - snap_date.to_pydatetime()) > timedelta(hours=24)
        except Exception:
            is_stale = False

    dollar_fmt = NumberFormat(type='CURRENCY', pattern='$#,##0')
    dollar2_fmt = NumberFormat(type='CURRENCY', pattern='$#,##0.00')
    dollar_signed_fmt = NumberFormat(type='CURRENCY', pattern='+$#,##0;-$#,##0')
    pct_fmt = NumberFormat(type='PERCENT', pattern='0.0%')
    pct_unsigned_fmt = NumberFormat(type='PERCENT', pattern='0%')
    pct_signed_fmt = NumberFormat(type='PERCENT', pattern='+0.0%;-0.0%')
    float2_fmt = NumberFormat(type='NUMBER', pattern='0.00')
    float1_fmt = NumberFormat(type='NUMBER', pattern='0.0')

    title_bg = STALE_RED if is_stale else NAVY

    ranges = [
        ("A1:R1", CellFormat(backgroundColor=title_bg, textFormat=TextFormat(bold=True, fontSize=12, foregroundColor=WHITE), horizontalAlignment="LEFT")),
    ]
    # R2 labels bold + right-aligned
    for col in ("A", "C", "E", "G", "I", "K", "M", "O", "Q"):
        ranges.append((f"{col}2:{col}2", CellFormat(textFormat=TextFormat(bold=True), horizontalAlignment="RIGHT")))
    # R2 values bold + number formats
    ranges.append(("B2:B2", CellFormat(textFormat=TextFormat(bold=True), numberFormat=dollar_fmt)))
    ranges.append(("D2:D2", CellFormat(textFormat=TextFormat(bold=True), numberFormat=dollar_signed_fmt)))
    ranges.append(("F2:F2", CellFormat(textFormat=TextFormat(bold=True), numberFormat=pct_signed_fmt)))
    ranges.append(("H2:H2", CellFormat(textFormat=TextFormat(bold=True), numberFormat=pct_signed_fmt)))
    ranges.append(("J2:J2", CellFormat(textFormat=TextFormat(bold=True), numberFormat=pct_signed_fmt)))
    ranges.append(("L2:L2", CellFormat(textFormat=TextFormat(bold=True), numberFormat=pct_signed_fmt)))
    ranges.append(("N2:N2", CellFormat(textFormat=TextFormat(bold=True), numberFormat=pct_fmt)))
    ranges.append(("P2:P2", CellFormat(textFormat=TextFormat(bold=True), numberFormat=dollar_fmt)))
    ranges.append(("R2:R2", CellFormat(textFormat=TextFormat(bold=True), numberFormat=float2_fmt)))

    # R4 header row
    ranges.append(("A4:P4", CellFormat(backgroundColor=GREY_BG, textFormat=TextFormat(bold=True))))

    # Position table columns
    d0, d1 = _DATA_START_ROW, data_end
    ranges.append((f"A{d0}:A{d1}", CellFormat(textFormat=TextFormat(bold=True))))
    ranges.append((f"B{d0}:B{d1}", CellFormat(textFormat=TextFormat(bold=True), numberFormat=dollar_fmt)))
    ranges.append((f"C{d0}:C{d1}", CellFormat(numberFormat=pct_fmt)))
    ranges.append((f"D{d0}:D{d1}", CellFormat(numberFormat=dollar2_fmt)))
    ranges.append((f"E{d0}:E{d1}", CellFormat(numberFormat=pct_signed_fmt)))
    ranges.append((f"F{d0}:F{d1}", CellFormat(numberFormat=dollar_fmt)))
    ranges.append((f"G{d0}:G{d1}", CellFormat(numberFormat=pct_signed_fmt)))
    ranges.append((f"H{d0}:H{d1}", CellFormat(numberFormat=float1_fmt)))
    ranges.append((f"I{d0}:I{d1}", CellFormat(numberFormat=float2_fmt)))
    ranges.append((f"J{d0}:J{d1}", CellFormat(numberFormat=pct_unsigned_fmt)))
    ranges.append((f"K{d0}:K{d1}", CellFormat(numberFormat=dollar2_fmt)))
    ranges.append((f"L{d0}:L{d1}", CellFormat(numberFormat=dollar2_fmt)))
    ranges.append((f"M{d0}:M{d1}", CellFormat(numberFormat=pct_signed_fmt)))
    ranges.append((f"N{d0}:N{d1}", CellFormat(numberFormat=pct_signed_fmt)))

    try:
        format_cell_ranges(ws, ranges)
    except Exception as e:
        logger.warning("0_DASHBOARD static/number formatting failed: %s", e)

    # --- Conditional formatting, one rules.save() batch ---
    try:
        rules = get_conditional_format_rules(ws)
        rules.clear()

        for col in ("E", "G"):  # Day%, UGL%
            rng = f"{col}{d0}:{col}{d1}"
            grid_rng = GridRange.from_a1_range(rng, ws)
            rules.append(ConditionalFormatRule(
                ranges=[grid_rng],
                booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_LESS", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=RED_TEXT))),
            ))
            rules.append(ConditionalFormatRule(
                ranges=[grid_rng],
                booleanRule=BooleanRule(condition=BooleanCondition("NUMBER_GREATER", ["0"]), format=CellFormat(textFormat=TextFormat(foregroundColor=GREEN))),
            ))

        for col in ("M", "N"):  # ->Trim %, ->Add %
            rng = f"{col}{d0}:{col}{d1}"
            rules.append(ConditionalFormatRule(
                ranges=[GridRange.from_a1_range(rng, ws)],
                gradientRule=GradientRule(
                    minpoint=InterpolationPoint(color=GREEN, type="NUMBER", value="0"),
                    midpoint=InterpolationPoint(color=WHITE, type="NUMBER", value="0.15"),
                    maxpoint=InterpolationPoint(color=GREY_TEXT, type="NUMBER", value="0.30"),
                ),
            ))

        # Row banding on the position table
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range(f"A{d0}:P{d1}", ws)],
            booleanRule=BooleanRule(condition=BooleanCondition("CUSTOM_FORMULA", ["=ISEVEN(ROW())"]), format=CellFormat(backgroundColor=GREY_BG)),
        ))

        # Grey text on the valuation columns for ETF-style rows with no
        # Fwd P/E, PEG, Trim, or Add (Sheets applies the anchor row's formula
        # relatively to every row in the range, same as ISEVEN(ROW()) above).
        rules.append(ConditionalFormatRule(
            ranges=[GridRange.from_a1_range(f"H{d0}:N{d1}", ws)],
            booleanRule=BooleanRule(
                condition=BooleanCondition("CUSTOM_FORMULA", [f'=AND($H{d0}="",$I{d0}="",$K{d0}="",$L{d0}="")']),
                format=CellFormat(textFormat=TextFormat(foregroundColor=GREY_TEXT)),
            ),
        ))

        rules.save()
    except Exception as e:
        logger.warning("0_DASHBOARD conditional formatting failed: %s", e)

    # --- Cell notes: full agent rationale on the Signal cell ---
    notes = {}
    for i, pos in enumerate(positions):
        if pos.get("Rationale"):
            notes[f"O{_DATA_START_ROW + i}"] = pos["Rationale"]
    if notes:
        try:
            ws.update_notes(notes)
        except Exception as e:
            logger.warning("0_DASHBOARD notes write failed: %s", e)

    try:
        set_frozen(ws, rows=4, cols=1)
    except Exception as e:
        logger.warning("Freeze failed: %s", e)

    try:
        set_column_widths(ws, [
            ("A", 70), ("B", 110), ("C", 70), ("D", 90), ("E", 80),
            ("F", 100), ("G", 80), ("H", 80), ("I", 70), ("J", 70),
            ("K", 90), ("L", 90), ("M", 90), ("N", 90), ("O", 90), ("P", 90),
        ])
    except Exception as e:
        logger.warning("Column widths failed: %s", e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(live: bool = False) -> None:
    """
    Rebuild the 0_DASHBOARD Command Center tab: a KPI strip plus one row per
    position (sorted by Market Value descending), joined against Valuation_Card
    and the latest Agent_Outputs run.

    Args:
        live: If False (default), prints the rendered table to stdout without writing.
    """
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)

    holdings_rows = _read_records(ss, config.TAB_HOLDINGS_CURRENT)
    daily_rows = _read_records(ss, config.TAB_DAILY_SNAPSHOTS)
    risk_rows = _read_records(ss, config.TAB_RISK_METRICS)
    valuation_rows = _read_records(ss, "Valuation_Card")
    rotation_rows = _read_records(ss, config.TAB_ROTATION_REVIEW)
    rotation_perf = _rotation_performance(rotation_rows) if rotation_rows else None

    try:
        ws_agent = ss.worksheet(config.TAB_AGENT_OUTPUTS)
        df_agent = get_latest_agent_outputs(ws_agent)
    except Exception as e:
        logger.warning("Could not read %s: %s", config.TAB_AGENT_OUTPUTS, e)
        df_agent = pd.DataFrame()

    headline = _compute_headline_kpis(daily_rows, holdings_rows)
    beta = _compute_beta(risk_rows)
    positions = _build_position_table(holdings_rows, valuation_rows, df_agent)
    health = _check_system_health()
    spy_ytd_raw = _spy_ytd_pct()
    level_coverage = compute_level_coverage([p["Ticker"] for p in positions])

    n_notes = sum(1 for p in positions if p.get("Rationale"))

    if not live:
        _print_dry_run(headline, beta, positions, health, spy_ytd_raw, _N_CONDITIONAL_RULES, n_notes, level_coverage, rotation_perf)
        return

    grid = _build_grid(headline, beta, positions, health, spy_ytd_raw, level_coverage, rotation_perf)

    existing_tabs = {ws.title for ws in ss.worksheets()}
    if config.TAB_DASHBOARD not in existing_tabs:
        logger.warning("Tab %s not found; creating at index 0.", config.TAB_DASHBOARD)
        ws = safe_execute(ss.add_worksheet, title=config.TAB_DASHBOARD, rows=max(50, len(grid) + 5), cols=_NCOLS, index=0)
    else:
        ws = ss.worksheet(config.TAB_DASHBOARD)

    safe_execute(ws.clear)
    # RAW: every value here is a Python-computed number or plain text, so
    # nothing can be mis-parsed as a formula (the old "+$530.00" #NAME? bug
    # required a leading-'+' STRING under USER_ENTERED; there are no baked
    # strings here at all).
    safe_execute(ws.update, range_name="A1", values=grid, value_input_option="RAW")
    _apply_formatting(ws, headline, positions)

    logger.info("Command Center refreshed. %d rows written.", len(grid))


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    main(live="--live" in sys.argv)
