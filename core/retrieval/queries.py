"""Whitelisted retrieval query templates. Parameters are values only — never SQL."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional

from core.store.serialize import payloads_to_df


@dataclass(frozen=True)
class QueryTemplate:
    id: str
    sql: str
    params: dict[str, type]
    returns: list[str]
    description: str
    # Optional post-processor: (rows as list[dict], params) -> list[dict]
    unpack: Optional[Callable[[list[dict], dict], list[dict]]] = None


def _unpack_payloads(rows: list[dict], _params: dict) -> list[dict]:
    payloads = [r["payload_json"] for r in rows if r.get("payload_json")]
    if not payloads:
        return []
    df = payloads_to_df(payloads)
    return df.to_dict(orient="records")


def _holdings_rows(rows: list[dict], _params: dict) -> list[dict]:
    out = []
    for rec in _unpack_payloads(rows, _params):
        out.append(
            {
                "ticker": rec.get("Ticker") or rec.get("ticker"),
                "market_value": rec.get("Market Value") or rec.get("market_value"),
                "weight": rec.get("Weight") or rec.get("weight"),
                "style": rec.get("Asset Strategy") or rec.get("style"),
                "cost_basis": rec.get("Cost Basis") or rec.get("cost_basis"),
            }
        )
    return out


def _txn_rows(rows: list[dict], params: dict) -> list[dict]:
    ticker = (params.get("ticker") or "").upper()
    since = params.get("since")
    until = params.get("until")
    out = []
    for rec in _unpack_payloads(rows, params):
        t = str(rec.get("Ticker") or rec.get("Symbol") or rec.get("ticker") or "").upper()
        if ticker and t != ticker:
            continue
        d = rec.get("Trade Date") or rec.get("Date") or rec.get("trade_date")
        if since and d and str(d)[:10] < str(since)[:10]:
            continue
        if until and d and str(d)[:10] > str(until)[:10]:
            continue
        out.append(
            {
                "trade_date": d,
                "action": rec.get("Action") or rec.get("action"),
                "shares": rec.get("Quantity") or rec.get("shares"),
                "price": rec.get("Price") or rec.get("price"),
                "net_amount": rec.get("Net Amount") or rec.get("Amount") or rec.get("net_amount"),
                "account": rec.get("Account") or rec.get("account"),
            }
        )
    return out


def _trade_log_rows(rows: list[dict], params: dict) -> list[dict]:
    ticker = (params.get("ticker") or "").upper()
    out = []
    for rec in _unpack_payloads(rows, params):
        sell = str(rec.get("Sell_Ticker") or "").upper()
        buy = str(rec.get("Buy_Ticker") or "").upper()
        sell_parts = {p.strip() for p in sell.split(",") if p.strip()}
        buy_parts = {p.strip() for p in buy.split(",") if p.strip()}
        if ticker and ticker not in sell_parts and ticker not in buy_parts:
            continue
        out.append(
            {
                "Date": rec.get("Date"),
                "Sell_Ticker": rec.get("Sell_Ticker"),
                "Buy_Ticker": rec.get("Buy_Ticker"),
                "Implicit_Bet": rec.get("Implicit_Bet"),
                "Rotation_Type": rec.get("Rotation_Type"),
                "Proposed_Bet": rec.get("Proposed_Bet"),
                "Rationale_Provenance": rec.get("Rationale_Provenance"),
            }
        )
    return out


def _lot_rows(rows: list[dict], params: dict) -> list[dict]:
    """
    Map Tax_Control lot payloads into the position_lots return shape.

    Live Tax_Control lots zone is closed/wash-sale rows (Closed Date, Gain Loss,
    Wash Sale, …) — not Schwab open-lot detail. Missing open-lot fields stay None
    so declared returns stay honest; callers see empty-ish rows rather than a
    silent zero from a wrong json_extract.
    """
    ticker = (params.get("ticker") or "").upper()
    out = []
    for rec in _unpack_payloads(rows, params):
        t = str(rec.get("Ticker") or rec.get("ticker") or "").upper()
        if ticker and t != ticker:
            continue
        out.append(
            {
                "lot_open_date": rec.get("Opened Date")
                or rec.get("Open Date")
                or rec.get("lot_open_date")
                or rec.get("Acquired"),
                "shares": rec.get("Quantity") or rec.get("shares"),
                "cost_basis": rec.get("Cost Basis") or rec.get("cost_basis"),
                "unrealized": rec.get("Gain/Loss")
                or rec.get("Gain Loss")
                or rec.get("unrealized")
                or rec.get("Unrealized G/L"),
                "holding_days": rec.get("Holding Days") or rec.get("holding_days"),
                "term": rec.get("Term") or rec.get("term"),
            }
        )
    return out


def _realized_rows(rows: list[dict], params: dict) -> list[dict]:
    ticker = (params.get("ticker") or "").upper()
    since = params.get("since")
    out = []
    for rec in _unpack_payloads(rows, params):
        t = str(rec.get("Ticker") or rec.get("Symbol") or rec.get("ticker") or "").upper()
        if ticker and t != ticker:
            continue
        d = (
            rec.get("Close Date")
            or rec.get("Closed Date")
            or rec.get("Date Sold")
            or rec.get("close_date")
        )
        if since and d and str(d)[:10] < str(since)[:10]:
            continue
        out.append(
            {
                "close_date": d,
                "shares": rec.get("Quantity") or rec.get("shares"),
                "proceeds": rec.get("Proceeds") or rec.get("proceeds"),
                "basis": rec.get("Cost Basis") or rec.get("basis"),
                "gain_loss": rec.get("Gain/Loss")
                or rec.get("Gain Loss $")
                or rec.get("gain_loss"),
                "term": rec.get("Term") or rec.get("term"),
                "holding_days": rec.get("Holding Days") or rec.get("holding_days"),
            }
        )
    return out


def _rotation_rows(rows: list[dict], params: dict) -> list[dict]:
    ticker = (params.get("ticker") or "").upper()
    out = []
    for rec in _unpack_payloads(rows, params):
        sell = str(rec.get("Sell_Ticker") or "").upper()
        buy = str(rec.get("Buy_Ticker") or "").upper()
        sell_parts = {p.strip() for p in sell.split(",") if p.strip()}
        buy_parts = {p.strip() for p in buy.split(",") if p.strip()}
        if ticker and ticker not in sell_parts and ticker not in buy_parts:
            continue
        out.append(rec)
    return out


def _tax_rows(rows: list[dict], params: dict) -> list[dict]:
    ticker = (params.get("ticker") or "").upper() if params.get("ticker") else ""
    out = []
    for rec in _unpack_payloads(rows, params):
        t = str(rec.get("Ticker") or rec.get("ticker") or "").upper()
        if ticker and t != ticker:
            continue
        # Prefer a stable key set for wash-sale Tax_Control lots zone
        out.append(
            {
                "Ticker": rec.get("Ticker") or rec.get("ticker"),
                "Closed Date": rec.get("Closed Date"),
                "Account": rec.get("Account"),
                "Term": rec.get("Term"),
                "Gain Loss": rec.get("Gain Loss") or rec.get("Gain/Loss"),
                "ST Gain Loss": rec.get("ST Gain Loss"),
                "LT Gain Loss": rec.get("LT Gain Loss"),
                "Wash Sale": rec.get("Wash Sale"),
                "Disallowed Loss": rec.get("Disallowed Loss"),
                **{k: v for k, v in rec.items() if k not in {
                    "Ticker", "Closed Date", "Account", "Term", "Gain Loss",
                    "ST Gain Loss", "LT Gain Loss", "Wash Sale", "Disallowed Loss",
                }},
            }
        )
    return out


def _thesis_state(rows: list[dict], params: dict) -> list[dict]:
    """Not a SQL blob — filled by api.py from vault; placeholder template for registry."""
    return rows


TEMPLATES: dict[str, QueryTemplate] = {}


def _reg(t: QueryTemplate) -> None:
    TEMPLATES[t.id] = t


def _decision_view_rows(rows: list[dict], _params: dict) -> list[dict]:
    out = []
    for r in rows:
        payload = r.get("payload_json")
        if not payload:
            continue
        if isinstance(payload, str):
            rec = json.loads(payload)
        else:
            rec = payload
        rec["_rank"] = r.get("rank", len(out))
        out.append(rec)
    return out


_reg(QueryTemplate(
    id="decision_view",
    sql="SELECT rank, payload_json FROM decision_view ORDER BY rank",
    params={},
    returns=["rank", "Ticker", "Reason", "Days_To_LT", "Wash_Window"],
    description="Decision_View / Crosshairs mirror rows in rank order",
    unpack=_decision_view_rows,
))

_reg(QueryTemplate(
    id="holdings_current",
    sql="SELECT payload_json FROM holdings_current",
    params={},
    returns=["ticker", "market_value", "weight", "style", "cost_basis"],
    description="Current holdings with MV, weight, style, cost basis",
    unpack=_holdings_rows,
))

_reg(QueryTemplate(
    id="position_transactions",
    sql="SELECT payload_json FROM transactions",
    params={"ticker": str, "since": date, "until": date},
    returns=["trade_date", "action", "shares", "price", "net_amount", "account"],
    description="Transactions for a ticker in an optional date window",
    unpack=_txn_rows,
))

_reg(QueryTemplate(
    id="position_lots",
    sql="SELECT payload_json FROM tax_control_lots",
    params={"ticker": str},
    returns=["lot_open_date", "shares", "cost_basis", "unrealized", "holding_days", "term"],
    description=(
        "Tax_Control lot rows for a ticker mapped to open-lot shaped fields "
        "(live mirror is wash/closed zone — open fields often None)"
    ),
    unpack=_lot_rows,
))

_reg(QueryTemplate(
    id="position_realized_gl",
    sql="SELECT payload_json FROM realized_gl",
    params={"ticker": str, "since": date},
    returns=["close_date", "shares", "proceeds", "basis", "gain_loss", "term", "holding_days"],
    description="Realized G/L lots for a ticker since optional date",
    unpack=_realized_rows,
))

_reg(QueryTemplate(
    id="signal_events_for_ticker",
    sql=(
        "SELECT id, event_date, ticker, signal_type, trigger_type, metric_value, "
        "band_level, band_side, distance_pct, rank_bucket, rank, source, "
        "doctrine_downgraded, payload_json, fingerprint "
        "FROM signal_events WHERE ticker = :ticker "
        "AND (:since IS NULL OR event_date >= :since) "
        "AND (:until IS NULL OR event_date <= :until) "
        "ORDER BY event_date, rank"
    ),
    params={"ticker": str, "since": date, "until": date},
    returns=[
        "id", "event_date", "ticker", "signal_type", "trigger_type", "metric_value",
        "band_level", "band_side", "distance_pct", "rank_bucket", "rank", "source",
        "doctrine_downgraded", "payload_json", "fingerprint",
    ],
    description="Evidence signal_events for one ticker in a window",
))

_reg(QueryTemplate(
    id="signal_events_for_date",
    sql=(
        "SELECT id, event_date, ticker, signal_type, trigger_type, metric_value, "
        "band_level, band_side, distance_pct, rank_bucket, rank, source, "
        "doctrine_downgraded, payload_json, fingerprint "
        "FROM signal_events WHERE event_date = :event_date ORDER BY rank"
    ),
    params={"event_date": date},
    returns=[
        "id", "event_date", "ticker", "signal_type", "trigger_type", "metric_value",
        "band_level", "band_side", "distance_pct", "rank_bucket", "rank", "source",
        "doctrine_downgraded", "payload_json", "fingerprint",
    ],
    description="Full ranked Crosshairs capture for one event_date",
))

_reg(QueryTemplate(
    id="bars_for_ticker",
    sql=(
        "SELECT ticker, bar_date, open, high, low, close, volume, source "
        "FROM bars_daily WHERE ticker = :ticker "
        "AND bar_date >= :since AND bar_date <= :until "
        "AND (:source IS NULL OR source = :source) "
        "ORDER BY bar_date"
    ),
    params={"ticker": str, "since": date, "until": date, "source": str},
    returns=["ticker", "bar_date", "open", "high", "low", "close", "volume", "source"],
    description="Daily OHLCV bars for a ticker/source window",
))

_reg(QueryTemplate(
    id="fundamentals_series",
    sql=(
        "SELECT ticker, as_of_date, fwd_pe, trailing_pe, price_to_book, market_cap, "
        "dividend_yield, week52_high, week52_low, eps, source "
        "FROM fundamentals_snapshot WHERE ticker = :ticker "
        "AND (:since IS NULL OR as_of_date >= :since) ORDER BY as_of_date"
    ),
    params={"ticker": str, "since": date},
    returns=[
        "ticker", "as_of_date", "fwd_pe", "trailing_pe", "price_to_book", "market_cap",
        "dividend_yield", "week52_high", "week52_low", "eps", "source",
    ],
    description="Fundamentals snapshot series for a ticker",
))

_reg(QueryTemplate(
    id="rotation_review_for_ticker",
    sql="SELECT payload_json FROM rotation_review",
    params={"ticker": str},
    returns=[],  # full attribution row keys vary; unpack returns dicts as-is
    description="Rotation_Review attribution rows touching a ticker",
    unpack=_rotation_rows,
))

_reg(QueryTemplate(
    id="trade_log_for_ticker",
    sql="SELECT payload_json FROM trade_log",
    params={"ticker": str},
    returns=["Date", "Sell_Ticker", "Buy_Ticker", "Implicit_Bet", "Rotation_Type", "Proposed_Bet", "Rationale_Provenance"],
    description="Trade_Log rotations involving a ticker",
    unpack=_trade_log_rows,
))

_reg(QueryTemplate(
    id="tax_control_lots",
    sql="SELECT payload_json FROM tax_control_lots",
    params={"ticker": str},
    returns=[
        "Ticker", "Closed Date", "Account", "Term", "Gain Loss",
        "ST Gain Loss", "LT Gain Loss", "Wash Sale", "Disallowed Loss",
    ],
    description="Tax_Control lot detail (+ wash-sale fields) optional ticker filter",
    unpack=_tax_rows,
))

_reg(QueryTemplate(
    id="thesis_state_for_ticker",
    sql="",  # vault filesystem — executed in api.py
    params={"ticker": str},
    returns=["ticker", "style", "trigger_type", "bands", "ceiling", "path"],
    description="Thesis frontmatter: style, trigger_type, bands, ceiling",
    unpack=_thesis_state,
))

_reg(QueryTemplate(
    id="corpus_source_type_counts",
    sql=(
        "SELECT source_type, COUNT(*) AS doc_count FROM corpus_docs "
        "WHERE deleted_at IS NULL GROUP BY source_type ORDER BY doc_count DESC"
    ),
    params={},
    returns=["source_type", "doc_count"],
    description="Corpus vocabulary: source_type counts for search facet rail",
))

_reg(QueryTemplate(
    id="corpus_doc_by_id",
    sql=(
        "SELECT id, source_type, path, doc_date, date_is_inferred, title, tickers, "
        "is_bills_writing, is_model_output FROM corpus_docs "
        "WHERE id = :doc_id AND deleted_at IS NULL"
    ),
    params={"doc_id": int},
    returns=[
        "id", "source_type", "path", "doc_date", "date_is_inferred", "title",
        "tickers", "is_bills_writing", "is_model_output",
    ],
    description="Corpus document metadata for /doc reader",
))

_reg(QueryTemplate(
    id="corpus_chunks_for_doc",
    sql=(
        "SELECT id, doc_id, chunk_ix, line_start, line_end, heading, char_start, char_end "
        "FROM corpus_chunks WHERE doc_id = :doc_id ORDER BY chunk_ix"
    ),
    params={"doc_id": int},
    returns=[
        "id", "doc_id", "chunk_ix", "line_start", "line_end", "heading",
        "char_start", "char_end",
    ],
    description="All chunks for a corpus document",
))


REQUIRED_PARAMS = {
    "position_transactions": {"ticker"},
    "position_lots": {"ticker"},
    "position_realized_gl": {"ticker"},
    "signal_events_for_ticker": {"ticker"},
    "signal_events_for_date": {"event_date"},
    "bars_for_ticker": {"ticker", "since", "until"},
    "fundamentals_series": {"ticker"},
    "rotation_review_for_ticker": {"ticker"},
    "trade_log_for_ticker": {"ticker"},
    "thesis_state_for_ticker": {"ticker"},
    "corpus_doc_by_id": {"doc_id"},
    "corpus_chunks_for_doc": {"doc_id"},
}


def validate_call(template_id: str, params: dict[str, Any]) -> QueryTemplate:
    if template_id not in TEMPLATES:
        raise KeyError(f"unknown retrieval template id: {template_id!r}")
    tmpl = TEMPLATES[template_id]
    allowed = set(tmpl.params) | set(REQUIRED_PARAMS.get(template_id, set()))
    for k in params:
        if k not in tmpl.params and k not in allowed:
            raise KeyError(f"unknown param {k!r} for template {template_id}")
    for req in REQUIRED_PARAMS.get(template_id, set()):
        if req not in params or params[req] is None or params[req] == "":
            raise KeyError(f"missing required param {req!r} for template {template_id}")
    for name, typ in tmpl.params.items():
        if name not in params or params[name] is None:
            continue
        val = params[name]
        if typ is date and isinstance(val, str):
            try:
                date.fromisoformat(val[:10])
            except ValueError as e:
                raise TypeError(f"param {name} expected date, got {val!r}") from e
        elif typ is str and not isinstance(val, str):
            raise TypeError(f"param {name} expected str, got {type(val).__name__}")
        elif typ is date and not isinstance(val, (date, str)):
            raise TypeError(f"param {name} expected date, got {type(val).__name__}")
    return tmpl
