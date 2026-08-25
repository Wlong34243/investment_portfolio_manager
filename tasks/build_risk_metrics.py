"""
tasks/build_risk_metrics.py — persist descriptive risk stats to Risk_Metrics.

Uses utils.risk formulas with price_history.get_bars input.
Does NOT call build_price_histories, capm_projection, run_stress_tests,
or compute_van_tharp_sizing.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import typer

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from utils.price_history import get_bars
from utils.risk import calculate_portfolio_beta
from utils.sheet_readers import get_gspread_client

logger = logging.getLogger(__name__)
app = typer.Typer()


def _ols_beta(r_a: pd.Series, r_b: pd.Series) -> Optional[float]:
    common = r_a.index.intersection(r_b.index)
    if len(common) < 60:
        return None
    a = r_a.loc[common].dropna()
    b = r_b.loc[common].dropna()
    common = a.index.intersection(b.index)
    if len(common) < 60:
        return None
    a, b = a.loc[common], b.loc[common]
    var = float(b.var())
    if var == 0:
        return None
    return float(a.cov(b) / var)


def build_risk_table(lookback_days: int = 400) -> tuple[pd.DataFrame, str]:
    from core.bundle import load_bundle

    bundles = sorted(Path("bundles").glob("context_bundle_*.json"), key=lambda p: p.stat().st_mtime)
    if not bundles:
        raise RuntimeError("no context bundle")
    bundle = load_bundle(bundles[-1])
    positions = [p for p in bundle.get("positions", []) if not p.get("is_cash")]
    total_mv = sum(float(p.get("market_value") or 0) for p in bundle.get("positions", [])) or 1.0

    spy = get_bars("SPY", period_days=lookback_days, interval="daily", adjusted=True)
    spy_rets = spy["close"].pct_change().dropna() if not spy.empty else pd.Series(dtype=float)
    sources = {spy.attrs.get("source")} if not spy.empty else set()

    rows = []
    for p in positions:
        t = (p.get("ticker") or "").upper()
        if not t or t in getattr(config, "CASH_TICKERS", []):
            continue
        mv = float(p.get("market_value") or 0)
        w = mv / total_mv
        bars = get_bars(t, period_days=lookback_days, interval="daily", adjusted=True)
        if not bars.empty:
            sources.add(bars.attrs.get("source"))
        if bars.empty or len(bars) < 60:
            rows.append({
                "Ticker": t,
                "Beta_1Y_SPY": None,
                "Vol_90D_Ann": None,
                "Vol_1Y_Ann": None,
                "Max_Drawdown_1Y": None,
                "Drawdown_From_52W_High": None,
                "Corr_1Y_SPY": None,
                "Contribution_To_Portfolio_Vol": None,
                "Obs_Count": len(bars) if bars is not None else 0,
                "Data_Source": bars.attrs.get("source") if not bars.empty else None,
                "As_Of_UTC": None,
                "Weight": w,
                "Market Value": mv,
            })
            continue

        close = bars["close"].dropna()
        rets = close.pct_change().dropna()
        beta = _ols_beta(rets.tail(252), spy_rets.tail(252)) if not spy_rets.empty else None
        vol90 = float(rets.tail(90).std() * np.sqrt(252)) if len(rets) >= 60 else None
        vol1y = float(rets.tail(252).std() * np.sqrt(252)) if len(rets) >= 60 else None
        # Max drawdown
        peak = close.cummax()
        dd = (close / peak) - 1.0
        max_dd = float(dd.min()) if not dd.empty else None
        hi = float(close.tail(252).max()) if len(close) else None
        last = float(close.iloc[-1])
        dd52 = ((last - hi) / hi) if hi else None
        corr = None
        if not spy_rets.empty:
            common = rets.index.intersection(spy_rets.index)
            if len(common) >= 60:
                corr = float(rets.loc[common].corr(spy_rets.loc[common]))
        rows.append({
            "Ticker": t,
            "Beta_1Y_SPY": beta,
            "Vol_90D_Ann": vol90,
            "Vol_1Y_Ann": vol1y,
            "Max_Drawdown_1Y": max_dd,
            "Drawdown_From_52W_High": dd52,
            "Corr_1Y_SPY": corr,
            "Contribution_To_Portfolio_Vol": None,  # filled below
            "Obs_Count": len(close),
            "Data_Source": bars.attrs.get("source"),
            "As_Of_UTC": str(close.index.max()),
            "Weight": w,
            "Market Value": mv,
            "Beta": beta,  # None when uncomputable — never impute 1.0
        })

    df = pd.DataFrame(rows)
    # Contribution to portfolio vol — weight * |beta| * vol, normalised
    if not df.empty:
        raw = []
        for _, r in df.iterrows():
            try:
                v_f = float(r.get("Vol_1Y_Ann"))
                b_f = float(r.get("Beta_1Y_SPY"))
                w_f = float(r.get("Weight") or 0)
                if np.isnan(v_f) or np.isnan(b_f) or np.isnan(w_f):
                    raw.append(0.0)
                else:
                    raw.append(abs(w_f) * abs(b_f) * abs(v_f))
            except (TypeError, ValueError):
                raw.append(0.0)
        s = float(np.nansum(raw)) or 1.0
        df["Contribution_To_Portfolio_Vol"] = [100.0 * x / s for x in raw]

    # Portfolio summary row LAST — _compute_beta reads [-1]["Portfolio Beta"]
    port_df = df.copy()
    if "Market Value" in port_df.columns and "Beta" in port_df.columns:
        calc_in = port_df.rename(columns={
            "Ticker": "ticker", "Market Value": "market_value", "Beta": "beta",
        })
        cash_mv = total_mv - float(pd.to_numeric(port_df["Market Value"], errors="coerce").fillna(0).sum())
        if cash_mv > 0:
            calc_in = pd.concat([
                calc_in,
                pd.DataFrame([{
                    "ticker": "CASH_MANUAL", "market_value": cash_mv, "beta": 0.0,
                }]),
            ], ignore_index=True)
        try:
            port_beta = calculate_portfolio_beta(calc_in)
        except Exception as e:
            logger.warning("calculate_portfolio_beta failed: %s", e)
            port_beta = None
    else:
        port_beta = None

    summary = {
        "Ticker": "_PORTFOLIO_",
        "Beta_1Y_SPY": port_beta,
        "Vol_90D_Ann": None,
        "Vol_1Y_Ann": None,
        "Max_Drawdown_1Y": None,
        "Drawdown_From_52W_High": None,
        "Corr_1Y_SPY": None,
        "Contribution_To_Portfolio_Vol": None,
        "Obs_Count": None,
        "Data_Source": "mixed" if len(sources) > 1 else (next(iter(sources)) if sources else None),
        "As_Of_UTC": datetime.now(timezone.utc).isoformat(),
        "Portfolio Beta": port_beta,
    }
    out = df.drop(columns=["Weight", "Market Value", "Beta"], errors="ignore")
    out["Portfolio Beta"] = None
    out = pd.concat([out, pd.DataFrame([summary])], ignore_index=True)

    n_pos = len(df)
    n_gap = int(df["Beta_1Y_SPY"].isna().sum()) if not df.empty else 0
    src_label = "mixed" if len(sources) > 1 else (next(iter(sources)) if sources else "unknown")
    header = (
        f"RISK_METRICS — as of {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')} — "
        f"source {src_label} — {n_pos} positions, {n_gap} uncomputable — "
        f"Portfolio Beta excludes uncomputable (renormalised); cash dilutes at beta 0"
    )
    return out, header


def main(live: bool = False, lookback_days: int = 400) -> None:
    df, header = build_risk_table(lookback_days=lookback_days)
    print(header)
    print(df.to_string(index=False))
    if not live:
        print("DRY RUN — no Sheet write.")
        return

    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    try:
        ws = ss.worksheet(config.TAB_RISK_METRICS)
        prior = ws.get_all_values()
        bak = Path("data") / f"Risk_Metrics_bak_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
        bak.write_text("\n".join(",".join(r) for r in prior), encoding="utf-8")
        print(f"Archived → {bak}")
    except Exception:
        ws = ss.add_worksheet(config.TAB_RISK_METRICS, rows=200, cols=20)

    # Ensure Portfolio Beta column present for dashboard
    if "Portfolio Beta" not in df.columns:
        df["Portfolio Beta"] = None
        df.loc[df.index[-1], "Portfolio Beta"] = df.iloc[-1].get("Beta_1Y_SPY")

    values = [[header], list(df.columns)]
    values.extend(df.fillna("").astype(str).values.tolist())
    ws.clear()
    ws.update("A1", values, value_input_option="USER_ENTERED")
    print(f"Wrote {config.TAB_RISK_METRICS}")


@app.command()
def cli(
    live: bool = typer.Option(False, "--live"),
    lookback_days: int = typer.Option(400, "--lookback-days"),
):
    main(live=live, lookback_days=lookback_days)


if __name__ == "__main__":
    app()
