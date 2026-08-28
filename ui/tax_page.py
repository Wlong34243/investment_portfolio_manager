"""Tax Control desk page — lots via retrieval; metrics via MetaKV store."""

from __future__ import annotations

from typing import Any

from core.retrieval.api import TemplateCall, retrieve


def _safe_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def assemble_tax(store: Any) -> dict[str, Any]:
    rs = retrieve(
        label="tax",
        caller="ui",
        queries=[TemplateCall("tax_control_lots", {})],
    )
    lots = rs.tables.get("tax_control_lots", [])
    # MetaKV metrics — no retrieval template exists; store is the read path.
    metrics_raw = store.get_tax_control_metrics() if hasattr(store, "get_tax_control_metrics") else {}

    metrics: list[dict[str, Any]] = []
    if metrics_raw:
        for k, v in metrics_raw.items():
            metrics.append({"key": k, "value": v, "raw": v})

    lot_rows: list[dict[str, Any]] = []
    for row in lots[:50]:
        lot_rows.append(dict(row))

    return {
        "metrics": metrics,
        "metrics_raw": metrics_raw or {},
        "lots": lot_rows,
        "lot_count": len(lots),
        "retrieval_hash": rs.retrieval_hash,
    }
