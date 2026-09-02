"""
Position Story page assembly — all ledger reads via core.retrieval.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from core.retrieval.api import CorpusQuery, RetrievalSet, TemplateCall, retrieve
from core.store.evidence import EVIDENCE_GATE_DAYS, evidence_status

CAMPAIGN_STALE_DAYS = 7
from ui.charts import build_chart_spec, render_chart_svg
from ui.format import weight_to_pct_points
from utils.thesis_reader import (
    THESES_DIR,
    get_pattern,
    get_style,
    load_frontmatter,
    read_thesis_text,
    thesis_path_for_ticker,
)

BALLAST_TICKERS = frozenset({"JEPI", "JPIE", "VTI", "COWZ", "VEA"})
MODEL_OUTPUT_SOURCE_TYPES = frozenset(
    {"podcast_summary", "agent_output", "spotify_digest", "moments"}
)
STYLES_PATH = Path("data") / "styles.json"
ARCHIVE_DIR = THESES_DIR / "archive"
_REVIEW_LOG_RE = re.compile(
    r"^##\s+Review\s+Log\s*$", re.IGNORECASE | re.MULTILINE
)
_REVIEW_ENTRY_RE = re.compile(
    r"^###\s+(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE
)


def _parse_date(val: Any) -> Optional[date]:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def _safe_float(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _style_ceiling(style: Optional[str], thesis_ceiling: Any) -> Optional[float]:
    if thesis_ceiling is not None:
        v = _safe_float(thesis_ceiling)
        if v is not None:
            return v
    if not style:
        return None
    try:
        import json as _json

        data = _json.loads(STYLES_PATH.read_text(encoding="utf-8"))
        return _safe_float(data.get(style, {}).get("size_ceiling_pct"))
    except (OSError, ValueError, TypeError):
        return None


def _parse_review_log(text: str) -> list[dict[str, str]]:
    if not text:
        return []
    m = _REVIEW_LOG_RE.search(text)
    if not m:
        return []
    section = text[m.end() :]
    entries: list[dict[str, str]] = []
    matches = list(_REVIEW_ENTRY_RE.finditer(section))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(section)
        body = section[start:end].strip()
        entries.append({"date": match.group(1), "body": body})
    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries


def _thesis_meta(ticker: str) -> dict[str, Any]:
    live = thesis_path_for_ticker(ticker)
    archive = ARCHIVE_DIR / f"{ticker.upper()}_thesis.md"
    path = live if live.exists() else archive if archive.exists() else live
    text = read_thesis_text(path) if path.exists() else None
    is_archived = not live.exists() and archive.exists()
    fm = load_frontmatter(text) if text else {}
    pattern = get_pattern(text=text) if text else None
    return {
        "path": str(path).replace("\\", "/"),
        "is_archived": is_archived,
        "style": get_style(text=text) if text else None,
        "pattern": pattern,
        "frontmatter": fm,
        "review_log": _parse_review_log(text or ""),
        "text": text,
    }


def _rotation_txn_dates(trade_log: list[dict], transactions: list[dict]) -> set[str]:
    """Dates on this ticker that are legs of a logged rotation."""
    rot_dates: set[str] = set()
    for row in trade_log:
        if not row.get("Rotation_Type"):
            continue
        d = str(row.get("Date") or "")[:10]
        if d:
            rot_dates.add(d)
    return rot_dates


def _lot_days_to_lt(lot: dict[str, Any], as_of: date) -> Optional[int]:
    open_d = _parse_date(lot.get("lot_open_date"))
    if open_d is None:
        return None
    hd = lot.get("holding_days")
    try:
        holding = int(hd) if hd is not None else (as_of - open_d).days
    except (TypeError, ValueError):
        holding = (as_of - open_d).days
    term = str(lot.get("term") or "").upper()
    if "LONG" in term or holding >= 365:
        return 0
    return max(0, 365 - holding)


def _build_ladder_lots(open_lots: list[dict[str, Any]], as_of: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for lot in open_lots:
        open_d = _parse_date(lot.get("lot_open_date"))
        if open_d is None:
            continue
        hd = lot.get("holding_days")
        try:
            holding = int(hd) if hd is not None else (as_of - open_d).days
        except (TypeError, ValueError):
            holding = (as_of - open_d).days
        fill_pct = min(100.0, max(0.0, (holding / 365.0) * 100.0))
        days_to_lt = lot.get("days_to_lt")
        out.append(
            {
                "open_date": open_d.isoformat(),
                "holding_days": holding,
                "days_to_lt": days_to_lt,
                "fill_pct": round(fill_pct, 1),
            }
        )
    return out


def _split_realized(rows: list[dict]) -> dict[str, float]:
    st = lt = 0.0
    ytd_st = ytd_lt = 0.0
    ytd_year = date.today().year
    for r in rows:
        gl = _safe_float(r.get("gain_loss")) or 0.0
        term = str(r.get("term") or "").upper()
        is_lt = "LONG" in term
        if is_lt:
            lt += gl
        else:
            st += gl
        cd = _parse_date(r.get("close_date"))
        if cd and cd.year == ytd_year:
            if is_lt:
                ytd_lt += gl
            else:
                ytd_st += gl
    return {
        "lifetime_st": st,
        "lifetime_lt": lt,
        "ytd_st": ytd_st,
        "ytd_lt": ytd_lt,
    }


def held_tickers_from_tables(tables: dict[str, list[dict]]) -> list[str]:
    rows = tables.get("holdings_current", [])
    out = []
    for r in rows:
        t = str(r.get("ticker") or "").upper()
        if t and t != "CASH_MANUAL":
            out.append(t)
    return sorted(set(out))


def assemble_position_story(ticker: str) -> tuple[dict[str, Any], RetrievalSet]:
    """One retrieve() call; returns template context + RetrievalSet."""
    t = ticker.upper()
    as_of = date.today()
    since_bars = as_of - timedelta(days=365 * 3)

    rs = retrieve(
        queries=[
            TemplateCall("holdings_current", {}),
            TemplateCall("position_transactions", {"ticker": t, "since": None, "until": None}),
            TemplateCall("position_lots", {"ticker": t}),
            TemplateCall("position_realized_gl", {"ticker": t, "since": None}),
            TemplateCall("signal_events_for_ticker", {"ticker": t, "since": None, "until": None}),
            TemplateCall(
                "bars_for_ticker",
                {"ticker": t, "since": since_bars, "until": as_of, "source": None},
            ),
            TemplateCall("fundamentals_series", {"ticker": t, "since": None}),
            TemplateCall("trade_log_for_ticker", {"ticker": t}),
            TemplateCall("thesis_state_for_ticker", {"ticker": t}),
            TemplateCall("rotation_review_for_ticker", {"ticker": t}),
        ],
        corpus=[
            CorpusQuery(query=t, tickers=[t], limit=8),
        ],
        label=f"position_story:{t}",
        caller="ui",
    )

    tables = rs.tables
    held = held_tickers_from_tables(tables)
    if t not in held:
        return {"ticker": t, "held_tickers": held, "not_found": True}, rs

    holdings_row = next(
        (r for r in tables.get("holdings_current", []) if str(r.get("ticker", "")).upper() == t),
        {},
    )
    thesis_rows = tables.get("thesis_state_for_ticker", [])
    thesis_row = thesis_rows[0] if thesis_rows else {}
    thesis_meta = _thesis_meta(t)

    style = thesis_row.get("style") or thesis_meta.get("style")
    is_ballast = t in BALLAST_TICKERS
    ceiling = None if is_ballast else _style_ceiling(style, thesis_row.get("ceiling"))
    weight = weight_to_pct_points(_safe_float(holdings_row.get("weight")))
    headroom = (ceiling - weight) if ceiling is not None and weight is not None else None

    transactions = tables.get("position_transactions", [])
    trade_log = tables.get("trade_log_for_ticker", [])
    rot_dates = _rotation_txn_dates(trade_log, transactions)

    lots_raw = tables.get("position_lots", [])
    open_lots = [
        lot
        for lot in lots_raw
        if not (lot.get("close_date") or lot.get("Closed Date"))
        and lot.get("lot_open_date")
    ]
    closed_lots = [lot for lot in lots_raw if lot not in open_lots]
    for lot in open_lots:
        lot["days_to_lt"] = _lot_days_to_lt(lot, as_of)

    open_lots.sort(key=lambda x: (x.get("days_to_lt") is None, x.get("days_to_lt", 9999)))

    realized_rows = tables.get("position_realized_gl", [])
    realized = _split_realized(realized_rows)

    ev = evidence_status()
    clean_days = int(ev.get("clean_trading_days") or 0)
    first_accrual = ev.get("evidence_first_accrual_date") or "2026-08-27"
    gate_met = bool(ev.get("gate_met"))
    gate_remaining = max(0, EVIDENCE_GATE_DAYS - clean_days)
    signals = tables.get("signal_events_for_ticker", [])

    chart_spec = build_chart_spec(
        bars=tables.get("bars_for_ticker", []),
        transactions=transactions,
        signals=signals,
        open_lots=open_lots,
        rotation_txn_dates=rot_dates,
        as_of=as_of,
    )
    chart_svg = render_chart_svg(chart_spec)
    chart_spec_json = __import__("json").dumps(chart_spec.to_render_dict())

    corpus_hits = []
    for h in rs.corpus_hits:
        corpus_hits.append(
            {
                "source_type": h.source_type,
                "path": h.path,
                "doc_date": h.doc_date.isoformat() if h.doc_date else None,
                "snippet": h.snippet,
                "line_start": h.line_start,
                "is_model_output": h.source_type in MODEL_OUTPUT_SOURCE_TYPES,
            }
        )

    lifecycle_summary = None
    lifecycle_artifact = None
    fills_since_campaign = 0
    # Never compute campaigns in request handlers — read artifacts only (desk_redesign Phase 0b).
    from ui.judgment_artifacts import load_lifecycle_for_ticker
    from core.judgment.registry import get_campaign_registry

    lifecycle_artifact = load_lifecycle_for_ticker(t)
    registry_row = get_campaign_registry(t)
    if registry_row and registry_row.get("computed_at"):
        if lifecycle_artifact is None:
            lifecycle_artifact = {"computed_at": registry_row["computed_at"], "path": registry_row.get("artifact_path")}
        elif not lifecycle_artifact.get("computed_at"):
            lifecycle_artifact["computed_at"] = registry_row["computed_at"]

    if lifecycle_artifact and lifecycle_artifact.get("summary"):
        summary = lifecycle_artifact["summary"]
        has_data = lifecycle_artifact.get("has_sidecar") or summary.get("legs")
        if has_data:
            lifecycle_summary = summary
        computed_at = lifecycle_artifact.get("computed_at")
        if computed_at:
            since_d = _parse_date(computed_at[:10])
            for txn in transactions:
                td = _parse_date(txn.get("trade_date"))
                if since_d and td and td > since_d:
                    act = str(txn.get("action") or "").upper()
                    if "BUY" in act or "SELL" in act:
                        fills_since_campaign += 1

    ladder_lots = _build_ladder_lots(open_lots, as_of)

    campaign_stale = False
    campaign_stale_reason = ""
    age_days = None
    computed_at = (lifecycle_artifact or {}).get("computed_at")
    if computed_at:
        cd = _parse_date(computed_at[:10])
        if cd:
            age_days = (as_of - cd).days
    if fills_since_campaign:
        campaign_stale = True
        campaign_stale_reason = f"{fills_since_campaign} fill(s) since campaign"
    elif age_days is not None and age_days > CAMPAIGN_STALE_DAYS:
        campaign_stale = True
        campaign_stale_reason = f"Campaign {age_days}d old"

    mv = _safe_float(holdings_row.get("market_value"))
    cb = _safe_float(holdings_row.get("cost_basis"))
    unrealized = (mv - cb) if mv is not None and cb is not None else None

    ctx: dict[str, Any] = {
        "ticker": t,
        "not_found": False,
        "held_tickers": held,
        "style": style,
        "style_name": style,
        "is_ballast": is_ballast,
        "weight": weight,
        "ceiling": ceiling,
        "headroom": headroom,
        "market_value": mv,
        "cost_basis": cb,
        "unrealized": unrealized,
        "transactions": transactions,
        "trade_log": trade_log,
        "open_lots": open_lots,
        "closed_lots": closed_lots,
        "realized": realized,
        "signals": signals,
        "signal_count": len(signals),
        "gate_met": gate_met,
        "gate_banner": (
            None
            if gate_met
            else (
                f"Signal capture began {first_accrual}; "
                f"{clean_days} of {EVIDENCE_GATE_DAYS} trading days accrued "
                f"({gate_remaining} remaining)."
            )
        ),
        "thesis": thesis_row,
        "thesis_meta": thesis_meta,
        "bands": thesis_row.get("bands") or {},
        "pattern": thesis_meta.get("pattern"),
        "review_log": thesis_meta.get("review_log", []),
        "is_archived": thesis_meta.get("is_archived", False),
        "rotations": tables.get("rotation_review_for_ticker", []),
        "fundamentals": tables.get("fundamentals_series", []),
        "chart_svg": chart_svg,
        "chart_spec_json": chart_spec_json,
        "chart_marker_count": len(chart_spec.markers),
        "retrieval_hash": rs.retrieval_hash,
        "corpus_hits": corpus_hits,
        "lifecycle_summary": lifecycle_summary,
        "lifecycle_artifact": lifecycle_artifact,
        "fills_since_campaign": fills_since_campaign,
        "ladder_lots": ladder_lots,
        "refresh_ticker": t,
        "campaign_stale": campaign_stale,
        "campaign_stale_reason": campaign_stale_reason,
        "page": "position",
        "as_of": as_of.isoformat(),
    }
    return ctx, rs
