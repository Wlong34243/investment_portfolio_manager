"""Cockpit landing page assembly — one retrieve() for ledger tables."""

from __future__ import annotations

from datetime import date
from typing import Any

from core.retrieval.api import TemplateCall, retrieve
from core.store.evidence import evidence_status
from ui.crosshairs_table import crosshair_row
from ui.last_run import read_last_run
from ui.sparkline import sparkline_from_values


def _safe_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _kpis_from_holdings(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0.0
    cash_mv = 0.0
    import config

    cash_tickers = {str(t).upper() for t in getattr(config, "CASH_TICKERS", ["CASH_MANUAL"])}
    for r in rows:
        mv = _safe_float(r.get("market_value") or r.get("Market Value"))
        ticker = str(r.get("ticker") or r.get("Ticker") or "").upper()
        if mv:
            total += mv
            if ticker in cash_tickers:
                cash_mv += mv
    cash_pct = (cash_mv / total) if total else None
    return {
        "total_value": total or None,
        "cash_pct": cash_pct,
        "day_change_dollar": None,
        "day_change_pct": None,
        "mtd_pct": None,
        "ytd_pct": None,
        "vs_spy": None,
        "portfolio_value_series": [],
    }


def _enrich_kpis(kpis: dict[str, Any]) -> dict[str, Any]:
    try:
        from tasks.build_command_center import _compute_headline_kpis, _read_records
        import config

        daily = _read_records(config.TAB_DAILY_SNAPSHOTS)
        holdings = _read_records(config.TAB_HOLDINGS_CURRENT)
        extra = _compute_headline_kpis(daily, holdings)
        for k in (
            "total_value", "cash_pct", "day_change_dollar", "day_change_pct",
            "mtd_pct", "ytd_pct", "stale", "stale_as_of",
        ):
            if extra.get(k) is not None:
                kpis[k] = extra[k]
        series: list[float] = []
        if not daily.empty and "Total Value" in daily.columns:
            for _, row in daily.iterrows():
                v = _safe_float(row.get("Total Value"))
                if v is not None:
                    series.append(v)
        kpis["portfolio_value_series"] = series
        try:
            from tasks.build_command_center import _spy_ytd_pct

            spy = _spy_ytd_pct()
        except Exception:
            spy = None
        if spy is not None and kpis.get("ytd_pct") is not None:
            kpis["vs_spy"] = kpis["ytd_pct"] - (spy / 100.0)
    except Exception:
        pass
    return kpis


def _build_kpi_tiles(kpis: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    tiles: list[dict[str, Any]] = []
    omissions: list[str] = []

    if kpis.get("total_value") is not None:
        tiles.append({
            "label": "Total value",
            "kind": "money",
            "key": "total_value",
            "value": kpis["total_value"],
            "sparkline_key": "portfolio_sparkline",
        })
    else:
        omissions.append("total value")

    if kpis.get("day_change_dollar") is not None or kpis.get("day_change_pct") is not None:
        tiles.append(
            {
                "label": "Day $ / %",
                "kind": "day",
                "dollar": kpis.get("day_change_dollar"),
                "pct": kpis.get("day_change_pct"),
            }
        )
    else:
        omissions.append("day change")

    if kpis.get("mtd_pct") is not None:
        tiles.append({"label": "MTD", "kind": "pct", "value": kpis["mtd_pct"]})
    else:
        omissions.append("MTD")

    if kpis.get("ytd_pct") is not None:
        tiles.append(
            {
                "label": "YTD / vs SPY",
                "kind": "ytd",
                "ytd": kpis["ytd_pct"],
                "vs_spy": kpis.get("vs_spy"),
            }
        )
    else:
        omissions.append("YTD")

    if kpis.get("cash_pct") is not None:
        tiles.append({"label": "Cash %", "kind": "pct", "value": kpis["cash_pct"], "note": True})
    else:
        omissions.append("cash %")

    return tiles, omissions


def _pending_precommits() -> list[dict[str, Any]]:
    try:
        from core.journal.precommit import list_pending_firings

        rows = []
        for p in list_pending_firings():
            rows.append(
                {
                    "ticker": p.get("ticker"),
                    "declared_at": str(p.get("declared_at", ""))[:10],
                    "trigger_type": p.get("trigger_type"),
                    "band_side": p.get("band_side"),
                    "band_level": p.get("band_level"),
                    "event_date": p.get("event_date"),
                    "metric_value": p.get("metric_value"),
                    "intended_action": p.get("intended_action"),
                }
            )
        return rows
    except Exception:
        return []


def assemble_cockpit() -> dict[str, Any]:
    today = date.today()
    rs = retrieve(
        label="cockpit",
        caller="ui",
        queries=[
            TemplateCall("holdings_current", {}),
            TemplateCall("decision_view", {}),
            TemplateCall("signal_events_for_date", {"event_date": today}),
        ],
    )
    holdings = rs.tables.get("holdings_current", [])
    decision = rs.tables.get("decision_view", [])
    signals_today = rs.tables.get("signal_events_for_date", [])

    kpis = _enrich_kpis(_kpis_from_holdings(holdings))
    portfolio_sparkline = sparkline_from_values(kpis.get("portfolio_value_series") or [])
    kpi_tiles, kpi_omissions = _build_kpi_tiles(kpis)
    for tile in kpi_tiles:
        if tile.get("sparkline_key") == "portfolio_sparkline":
            tile["sparkline"] = portfolio_sparkline
    crosshairs = [crosshair_row(r, rank=i + 1) for i, r in enumerate(decision[:5])]

    ev = evidence_status()
    last_run = read_last_run()

    return {
        "kpis": kpis,
        "kpi_tiles": kpi_tiles,
        "kpi_omissions": kpi_omissions,
        "crosshairs": crosshairs,
        "crosshairs_total": len(decision),
        "pending_precommits": _pending_precommits(),
        "evidence": {
            "signals_today": len(signals_today),
            "accrual_day": ev.get("clean_trading_days", 0),
            "accrual_total": 10,
            "first_accrual": ev.get("evidence_first_accrual_date"),
            "gate_met": ev.get("gate_met"),
            "gate_remaining": ev.get("gate_remaining"),
        },
        "last_run": last_run,
        "retrieval_hash": rs.retrieval_hash,
        "cash_scope_note": "Cash % is three of six Schwab accounts in scope — not net worth.",
    }
