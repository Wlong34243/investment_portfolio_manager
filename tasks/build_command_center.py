"""
tasks/build_command_center.py — Build the 0_DASHBOARD Command Center tab.

Reads from: Holdings_Current, Daily_Snapshots, Tax_Control, Risk_Metrics,
            Target_Allocation, Valuation_Card.
Writes to:  0_DASHBOARD (clear-and-rebuild, single batch_update call).
No original computation — aggregates values already present on other tabs.
"""

import json
import logging
import time
import os
import sys
from datetime import datetime
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

logger = logging.getLogger(__name__)

_NCOLS = 9  # grid width (Ticker|Weight|MV|UGL%|Price|Trim|Add|DistTrim|DistAdd)


def _pad(row: list, n: int = _NCOLS) -> list:
    return (row + [""] * n)[:n]


# ---------------------------------------------------------------------------
# Formatters — pre-bake strings so DRY RUN and LIVE output are identical
# ---------------------------------------------------------------------------

def _dollar(v) -> str:
    try:
        f = float(v)
        return f"${f:,.2f}" if f >= 0 else f"-${abs(f):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _dollar_signed(v) -> str:
    try:
        f = float(v)
        return f"+${f:,.2f}" if f >= 0 else f"-${abs(f):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _pct(v, signed: bool = False, decimals: int = 1) -> str:
    try:
        f = float(v)
        if signed:
            return f"{f:+.{decimals}f}%"
        return f"{f:.{decimals}f}%"
    except (TypeError, ValueError):
        return "—"


def _float2(v) -> str:
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return "—"


def _normalize_pct(series: pd.Series) -> pd.Series:
    """Convert 0-1 fractions to 0-100 percentages if the max is <= 1.5."""
    numeric = pd.to_numeric(series, errors="coerce").fillna(0)
    if numeric.abs().max() <= 1.5:
        return numeric * 100
    return numeric


# ---------------------------------------------------------------------------
# Tab readers — never raise; return [] / [[]] on failure
# ---------------------------------------------------------------------------

def _read_records(ss, tab: str) -> list[dict]:
    try:
        ws = ss.worksheet(tab)
        df = read_gsheet_robust(ws)
        return df.to_dict("records")
    except Exception as e:
        logger.warning("Could not read tab %s: %s", tab, e)
        return []


def _read_raw(ss, tab: str) -> list[list]:
    try:
        return ss.worksheet(tab).get_all_values()
    except Exception as e:
        logger.warning("Could not read tab %s (raw): %s", tab, e)
        return []


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
        from google.cloud import storage
        client = storage.Client()
        blob = client.bucket(config.SCHWAB_TOKEN_BUCKET).blob(config.SCHWAB_TOKEN_BLOB_ACCOUNTS)
        data = json.loads(blob.download_as_text())
        expires_at = data.get("expires_at")
        if not expires_at:
            return "n/a"
        delta_days = (float(expires_at) - time.time()) / 86400
        if delta_days < 0:
            return "Expired"
        if delta_days < 2:
            return "Expiring soon"
        return "OK"
    except Exception:
        return "n/a"


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
    """Return SPY YTD return as a float percentage, or None on failure."""
    try:
        import yfinance as yf
        hist = yf.Ticker("SPY").history(period="ytd")
        if hist.empty:
            return None
        return (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
    except Exception:
        return None


# ---------------------------------------------------------------------------
# KPI computers
# ---------------------------------------------------------------------------

def _compute_headline_kpis(daily_rows: list[dict], holdings_rows: list[dict]) -> dict:
    out = {
        "total_value": "—",
        "cash_pct": "—",
        "strategic_cash": "—",
        "day_change": "—",
        "mtd_pct": "—",
        "ytd_pct": "—",
        "ytd_raw": None,
    }
    if not daily_rows:
        return out

    df = pd.DataFrame(daily_rows)
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

    if total_value and total_value > 0:
        out["total_value"] = _dollar(total_value)
        out["cash_pct"] = _pct(cash_value / total_value * 100)

    # Strategic cash: Market Value sum for CASH_TICKERS
    if holdings_rows:
        df_h = pd.DataFrame(holdings_rows)
        df_h["Market Value"] = pd.to_numeric(df_h.get("Market Value", pd.Series(dtype=float)), errors="coerce").fillna(0)
        strat_cash = df_h.loc[df_h["Ticker"].astype(str).isin(config.CASH_TICKERS), "Market Value"].sum()
        out["strategic_cash"] = _dollar(strat_cash)

    # Day change
    if len(df) >= 2 and total_value:
        prev_val = pd.to_numeric(df.iloc[-2].get("Total Value"), errors="coerce")
        if prev_val:
            delta = total_value - prev_val
            delta_pct = delta / prev_val * 100
            out["day_change"] = f"{_dollar_signed(delta)} ({_pct(delta_pct, signed=True)})"

    now = latest["Date"]

    # MTD
    month_rows = df[df["Date"].dt.month == now.month]
    if not month_rows.empty and total_value:
        start_val = pd.to_numeric(month_rows.iloc[0].get("Total Value"), errors="coerce")
        if start_val:
            out["mtd_pct"] = _pct(total_value / start_val * 100 - 100, signed=True)

    # YTD
    year_rows = df[df["Date"].dt.year == now.year]
    if not year_rows.empty and total_value:
        start_val = pd.to_numeric(year_rows.iloc[0].get("Total Value"), errors="coerce")
        if start_val:
            ytd = total_value / start_val * 100 - 100
            out["ytd_pct"] = _pct(ytd, signed=True)
            out["ytd_raw"] = ytd

    return out


def _read_tax_kpis(tax_raw: list[list]) -> dict:
    """Read KPI strip from Tax_Control raw values (row 1=labels, row 2=values)."""
    result = {label: "—" for label in config.TAX_CONTROL_KPI_LABELS}
    if len(tax_raw) < 3:
        return result
    labels = tax_raw[1]
    values = tax_raw[2]
    for i, label in enumerate(labels):
        if label in result and i < len(values):
            result[label] = values[i]
    return result


def _compute_risk_snapshot(risk_rows: list[dict]) -> dict:
    out = {
        "beta": "—",
        "top_pos": "—",
        "top_sector": "—",
        "stress_10": "—",
    }
    if not risk_rows:
        return out
    latest = risk_rows[-1]

    out["beta"] = _float2(latest.get("Portfolio Beta"))

    ticker = str(latest.get("Top Position Ticker", "—"))
    conc = latest.get("Top Position Conc %")
    if conc not in (None, ""):
        conc_f = float(conc) if float(conc) > 1 else float(conc) * 100
        out["top_pos"] = f"{ticker} ({_pct(conc_f)})"
    else:
        out["top_pos"] = ticker

    sector = str(latest.get("Top Sector", "—"))
    sec_conc = latest.get("Top Sector Conc %")
    if sec_conc not in (None, ""):
        sec_f = float(sec_conc) if float(sec_conc) > 1 else float(sec_conc) * 100
        out["top_sector"] = f"{sector} ({_pct(sec_f)})"
    else:
        out["top_sector"] = sector

    out["stress_10"] = _dollar(latest.get("Stress -10% Impact"))
    return out


def _compute_top_n(holdings_rows: list[dict], valuation_rows: list[dict], n: int = 10) -> list[dict]:
    if not holdings_rows:
        return []

    df_h = pd.DataFrame(holdings_rows)
    df_h["Market Value"] = pd.to_numeric(df_h.get("Market Value", pd.Series(dtype=float)), errors="coerce").fillna(0)
    df_h["Weight"] = _normalize_pct(df_h.get("Weight", pd.Series(dtype=float)))
    df_h["Unrealized G/L %"] = _normalize_pct(df_h.get("Unrealized G/L %", pd.Series(dtype=float)))
    df_h["Price"] = pd.to_numeric(df_h.get("Price", pd.Series(dtype=float)), errors="coerce").fillna(0)

    df_h = df_h[~df_h["Ticker"].astype(str).isin(config.CASH_TICKERS)]
    df_h = df_h.nlargest(n, "Market Value")

    val_map: dict[str, dict] = {}
    for row in (valuation_rows or []):
        ticker = str(row.get("Ticker", "")).strip()
        if ticker:
            val_map[ticker] = {
                "trim": row.get("Trim Target"),
                "add": row.get("Add Target"),
            }

    results = []
    for _, row in df_h.iterrows():
        ticker = str(row["Ticker"])
        price = float(row["Price"]) if row["Price"] else 0.0

        def _safe_float(val):
            try:
                return float(val) if val not in (None, "", "—") else None
            except (TypeError, ValueError):
                return None

        vdata = val_map.get(ticker, {})
        trim = _safe_float(vdata.get("trim"))
        add = _safe_float(vdata.get("add"))

        dist_trim = _pct((trim - price) / price * 100, signed=True) if trim and price else "n/a"
        dist_add = _pct((price - add) / add * 100, signed=True) if add and price else "n/a"

        results.append({
            "Ticker": ticker,
            "Weight": _pct(row["Weight"]),
            "Market Value": _dollar(row["Market Value"]),
            "UGL %": _pct(row["Unrealized G/L %"], signed=True),
            "Price": _dollar(price),
            "Trim Tgt": _dollar(trim) if trim else "—",
            "Add Tgt": _dollar(add) if add else "—",
            "Dist to Trim": dist_trim,
            "Dist to Add": dist_add,
        })
    return results


def _compute_drift_alerts(holdings_rows: list[dict], target_rows: list[dict]) -> list[dict]:
    """
    Aggregate Holdings_Current weights by Asset Class and compare with Target_Allocation.
    Target_Allocation is an asset-class table, not a ticker table — joining on Asset Class.
    """
    if not holdings_rows or not target_rows:
        return []

    df_h = pd.DataFrame(holdings_rows)
    df_t = pd.DataFrame(target_rows)

    df_h["Weight"] = _normalize_pct(df_h.get("Weight", pd.Series(dtype=float)))
    if "Asset Class" not in df_h.columns:
        return []

    df_current = df_h.groupby("Asset Class")["Weight"].sum().reset_index()
    df_current.columns = ["Asset Class", "Current %"]

    target_col = next(
        (c for c in df_t.columns if "target" in c.lower() and "%" in c.lower()),
        next((c for c in df_t.columns if "target" in c.lower()), None),
    )
    asset_col = next((c for c in df_t.columns if "asset" in c.lower()), None)
    if not target_col or not asset_col:
        return []

    df_t = df_t[[asset_col, target_col]].copy()
    df_t.columns = ["Asset Class", "Target %"]
    df_t["Target %"] = _normalize_pct(df_t["Target %"])

    merged = pd.merge(df_current, df_t, on="Asset Class", how="inner")
    merged["Drift %"] = merged["Current %"] - merged["Target %"]
    merged = merged[merged["Drift %"].abs() > config.REBALANCE_THRESHOLD_PCT]
    merged = merged.iloc[merged["Drift %"].abs().argsort()[::-1]]

    results = []
    for _, row in merged.head(8).iterrows():
        drift = row["Drift %"]
        results.append({
            "Asset Class": row["Asset Class"],
            "Current %": _pct(row["Current %"]),
            "Target %": _pct(row["Target %"]),
            "Drift %": _pct(drift, signed=True),
            "Direction": "OVER" if drift > 0 else "UNDER",
        })
    return results


def _read_account_balances() -> list[dict]:
    """Read per-account balance data saved by the bundle builder. Returns [] on any failure."""
    try:
        path = Path("data/account_balances.json")
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def _check_system_health() -> dict:
    return {
        "last_refresh": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "bundle_hash": _latest_bundle_hash(),
        "schwab_token": _schwab_token_status(),
        "fmp_cache_age": _fmp_cache_age(),
    }


# ---------------------------------------------------------------------------
# Grid builder
# ---------------------------------------------------------------------------

def _build_grid(
    headline: dict,
    tax: dict,
    risk: dict,
    top10: list[dict],
    drift: list[dict],
    health: dict,
    spy_ytd_raw: Optional[float],
    accounts: list[dict] | None = None,
) -> list[list]:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if spy_ytd_raw is not None and headline["ytd_raw"] is not None:
        try:
            delta = float(headline["ytd_raw"]) - float(spy_ytd_raw)
            vs_spy = _pct(delta, signed=True)
        except (TypeError, ValueError):
            vs_spy = "n/a"
    else:
        vs_spy = "n/a"

    grid: list[list] = []

    # R1: Title
    grid.append(_pad([f"PORTFOLIO COMMAND CENTER  —  As of {now_str}"]))
    # R2: blank
    grid.append(_pad([]))
    # R3: Headline line 1
    grid.append(_pad(["Total Value", headline["total_value"], "Cash %", headline["cash_pct"], "Strategic Cash", headline["strategic_cash"]]))
    # R4: Headline line 2
    grid.append(_pad(["Day Change", headline["day_change"], "MTD", headline["mtd_pct"], "YTD", headline["ytd_pct"], "vs. SPY YTD", vs_spy]))
    # R5: blank
    grid.append(_pad([]))
    # R6: Tax header
    grid.append(_pad(["TAX POSTURE"]))
    # R7: Tax KPIs line 1
    grid.append(_pad([
        "Net ST (YTD)", tax.get("Net ST (YTD)", "—"),
        "Net LT (YTD)", tax.get("Net LT (YTD)", "—"),
        "Disallowed Wash", tax.get("Disallowed Wash Loss (YTD)", "—"),
        "Wash Sales", tax.get("Wash Sale Count", "—"),
    ]))
    # R8: Tax KPIs line 2
    grid.append(_pad(["Est. Fed Tax", tax.get("Est. Fed Cap Gains Tax", "—"), "Offset Capacity", tax.get("Tax Offset Capacity", "—")]))
    # R9: blank
    grid.append(_pad([]))
    # R10: Risk header
    grid.append(_pad(["RISK SNAPSHOT"]))
    # R11: Risk data
    grid.append(_pad(["Portfolio Beta", risk["beta"], "Top Position", risk["top_pos"], "Top Sector", risk["top_sector"], "Stress -10%", risk["stress_10"]]))
    # R12: blank
    grid.append(_pad([]))
    # R13: Top 10 header
    grid.append(_pad(["TOP 10 POSITIONS"]))
    # R14: Top 10 column headers
    grid.append(_pad(["Ticker", "Weight", "Market Value", "UGL %", "Price", "Trim Tgt", "Add Tgt", "Dist to Trim", "Dist to Add"]))
    # R15-24: Top 10 data (pad to 10 rows)
    for pos in top10:
        grid.append(_pad([pos["Ticker"], pos["Weight"], pos["Market Value"], pos["UGL %"], pos["Price"], pos["Trim Tgt"], pos["Add Tgt"], pos["Dist to Trim"], pos["Dist to Add"]]))
    for _ in range(10 - len(top10)):
        grid.append(_pad([]))
    # R25: blank
    grid.append(_pad([]))
    # R26: Drift header
    grid.append(_pad(["DRIFT ALERTS"]))
    # R27: Drift column headers
    grid.append(_pad(["Asset Class", "Current %", "Target %", "Drift %", "Direction"]))
    # R28-35: Drift data (8 rows)
    if drift:
        for alert in drift:
            grid.append(_pad([alert["Asset Class"], alert["Current %"], alert["Target %"], alert["Drift %"], alert["Direction"]]))
        for _ in range(8 - len(drift)):
            grid.append(_pad([]))
    else:
        grid.append(_pad([f"No positions outside ±{config.REBALANCE_THRESHOLD_PCT:.0f}% threshold."]))
        for _ in range(7):
            grid.append(_pad([]))
    # R36: blank
    grid.append(_pad([]))
    # R37: System Health header
    grid.append(_pad(["SYSTEM HEALTH"]))
    # R38: Health line 1
    grid.append(_pad(["Last Refresh", health["last_refresh"], "Bundle Hash", health["bundle_hash"]]))
    # R39: Health line 2
    grid.append(_pad(["Schwab Token", health["schwab_token"], "FMP Cache Age", health["fmp_cache_age"]]))
    # R40: blank
    grid.append(_pad([]))
    # R41: Account Balances header
    grid.append(_pad(["ACCOUNT BALANCES"]))
    # R42: Account Balances column headers
    grid.append(_pad(["Account", "Total Value", "Cash"]))
    # R43-47: Account data (up to 5 accounts, padded)
    _N_ACCT_ROWS = 5
    acct_list = accounts or []
    for acct in acct_list[:_N_ACCT_ROWS]:
        grid.append(_pad([
            acct.get("account_number", "—"),
            _dollar(acct.get("total_value", 0)),
            _dollar(acct.get("cash_value", 0)),
        ]))
    if not acct_list:
        grid.append(_pad(["No data — run snapshot with CSV to populate"]))
        for _ in range(_N_ACCT_ROWS - 1):
            grid.append(_pad([]))
    else:
        for _ in range(_N_ACCT_ROWS - len(acct_list[:_N_ACCT_ROWS])):
            grid.append(_pad([]))

    return grid


# ---------------------------------------------------------------------------
# DRY RUN output
# ---------------------------------------------------------------------------

def _print_dry_run(grid: list[list]) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(show_header=False, box=None, padding=(0, 1))
    for _ in range(_NCOLS):
        table.add_column()
    for row in grid:
        table.add_row(*[str(c) for c in row])
    console.print(table)
    console.print("[dim]DRY RUN — no Sheet writes. Re-run with --live to apply.[/]")


# ---------------------------------------------------------------------------
# Formatting (LIVE only)
# ---------------------------------------------------------------------------

def _apply_formatting(ws, drift: list[dict]) -> None:
    try:
        from gspread_formatting import (
            CellFormat, Color, TextFormat,
            format_cell_range, set_frozen, set_column_widths,
        )
    except ImportError:
        logger.warning("gspread_formatting not installed; skipping Command Center formatting.")
        return

    NAVY = Color(0.10, 0.15, 0.27)
    WHITE = Color(1, 1, 1)
    GREY = Color(0.95, 0.95, 0.95)
    RED_LIGHT = Color(0.99, 0.91, 0.90)
    ORANGE_LIGHT = Color(1.0, 0.93, 0.80)

    def _fmt(bg=None, bold=False, size=None, fg=None, halign=None):
        return CellFormat(
            backgroundColor=bg,
            textFormat=TextFormat(bold=bold, fontSize=size, foregroundColor=fg),
            horizontalAlignment=halign,
        )

    def _apply(rng, **kw):
        try:
            format_cell_range(ws, rng, _fmt(**kw))
        except Exception as e:
            logger.warning("Formatting failed for %s: %s", rng, e)

    # Title — left-aligned
    _apply("A1:I1", bg=NAVY, bold=True, size=12, fg=WHITE, halign="LEFT")

    # Section headers (rows shifted by 5 for top-10 expansion; account section added at 41)
    for r in [6, 10, 13, 26, 37, 41]:
        _apply(f"A{r}:I{r}", bg=GREY, bold=True)

    # KPI label/value pairs
    for r in [3, 4, 7, 8, 11]:
        for col in ["A", "C", "E", "G"]:
            _apply(f"{col}{r}:{col}{r}", bold=True, halign="RIGHT")
        for col in ["B", "D", "F", "H"]:
            _apply(f"{col}{r}:{col}{r}", bold=True)

    # Table column headers
    _apply("A14:I14", bold=True, bg=GREY)
    _apply("A27:I27", bold=True, bg=GREY)
    _apply("A42:I42", bold=True, bg=GREY)

    # Drift alert row colors (drift data now starts at row 28)
    for i, alert in enumerate(drift[:8]):
        row_num = 28 + i
        bg = RED_LIGHT if alert["Direction"] == "OVER" else ORANGE_LIGHT
        _apply(f"A{row_num}:I{row_num}", bg=bg)

    # System Health labels (shifted to rows 38-39)
    for r in [38, 39]:
        _apply(f"A{r}:A{r}", bold=True, halign="RIGHT")
        _apply(f"C{r}:C{r}", bold=True, halign="RIGHT")

    try:
        set_column_widths(ws, [
            ("A", 140), ("B", 110), ("C", 120), ("D", 90),
            ("E", 130), ("F", 110), ("G", 110), ("H", 110), ("I", 110),
        ])
    except Exception as e:
        logger.warning("Column widths failed: %s", e)

    try:
        set_frozen(ws, rows=1)
    except Exception as e:
        logger.warning("Freeze row failed: %s", e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(live: bool = False) -> None:
    """
    Rebuild the 0_DASHBOARD Command Center tab.

    Reads from: Holdings_Current, Daily_Snapshots, Tax_Control, Risk_Metrics,
                Target_Allocation, Valuation_Card.
    Writes to:  0_DASHBOARD (clear-and-rebuild, single batch_update call).

    Args:
        live: If False (default), prints the rendered grid to stdout without writing.
    """
    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)

    holdings_rows = _read_records(ss, config.TAB_HOLDINGS_CURRENT)
    daily_rows = _read_records(ss, config.TAB_DAILY_SNAPSHOTS)
    tax_raw = _read_raw(ss, config.TAB_TAX_CONTROL)
    risk_rows = _read_records(ss, config.TAB_RISK_METRICS)
    target_rows = _read_records(ss, config.TAB_TARGET_ALLOCATION)
    valuation_rows = _read_records(ss, "Valuation_Card")

    headline = _compute_headline_kpis(daily_rows, holdings_rows)
    tax = _read_tax_kpis(tax_raw)
    risk = _compute_risk_snapshot(risk_rows)
    top10 = _compute_top_n(holdings_rows, valuation_rows, n=10)
    drift = _compute_drift_alerts(holdings_rows, target_rows)
    health = _check_system_health()
    spy_ytd_raw = _spy_ytd_pct()
    accounts = _read_account_balances()

    grid = _build_grid(headline, tax, risk, top10, drift, health, spy_ytd_raw, accounts=accounts)

    if not live:
        _print_dry_run(grid)
        return

    existing_tabs = {ws.title for ws in ss.worksheets()}
    if config.TAB_DASHBOARD not in existing_tabs:
        logger.warning("Tab %s not found; creating at index 0.", config.TAB_DASHBOARD)
        ws = safe_execute(ss.add_worksheet, title=config.TAB_DASHBOARD, rows=50, cols=_NCOLS, index=0)
    else:
        ws = ss.worksheet(config.TAB_DASHBOARD)

    safe_execute(ws.clear)
    safe_execute(ws.update, range_name="A1", values=grid, value_input_option="USER_ENTERED")
    _apply_formatting(ws, drift=drift)

    logger.info("Command Center refreshed. %d rows written.", len(grid))


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    main(live="--live" in sys.argv)
