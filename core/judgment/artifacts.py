"""Judgment artifact sidecars — structured JSON beside markdown."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.judgment.lifecycle import Campaign
from core.judgment.rotations import RotationAggregate

OUTPUT_DIR = Path("agent_outputs/judgment")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def campaign_to_sidecar(
    camp: Campaign,
    *,
    retrieval_hash: str,
    computed_at: str | None = None,
    md_path: str = "",
) -> dict[str, Any]:
    computed_at = computed_at or _iso_now()
    first = camp.first_buy_date.isoformat() if camp.first_buy_date else None
    last = camp.legs[-1].trade_date.isoformat() if camp.legs else None
    return {
        "unit": "B",
        "ticker": camp.ticker,
        "computed_at": computed_at,
        "retrieval_hash": retrieval_hash,
        "artifact_md": md_path,
        "legs": len(camp.legs),
        "is_open": camp.is_open,
        "span_start": first,
        "span_end": last,
        "single_entry_return_pct": camp.single_entry_return_pct,
        "campaign_economic_return_pct": camp.campaign_economic_return_pct,
        "scaling_delta_pct": camp.scaling_delta_pct,
        "scaling_delta_dollars": camp.scaling_delta_dollars,
        "time_weighted_return_pct": camp.time_weighted_return_pct,
        "dollar_weighted_return_pct": camp.dollar_weighted_return_pct,
        "dwr_degenerate": camp.dwr_degenerate,
        "benchmark_vti_return_pct": camp.benchmark_vti_return_pct,
        "benchmark_spy_return_pct": camp.benchmark_spy_return_pct,
        "adds_into_strength": camp.adds_into_strength,
        "adds_into_weakness": camp.adds_into_weakness,
        "style_key": camp.style_key,
        "total_invested": camp.total_invested,
        "total_realized": camp.total_realized,
        "current_value": camp.current_value,
        "leg_rows": [
            {
                "trade_date": leg.trade_date.isoformat(),
                "action": leg.action,
                "shares": leg.shares,
                "price": leg.price,
                "net_amount": leg.net_amount,
            }
            for leg in camp.legs
        ],
    }


def rotations_to_sidecar(agg: RotationAggregate, *, md_path: str = "") -> dict[str, Any]:
    return {
        "unit": "A",
        "computed_at": _iso_now(),
        "artifact_md": md_path,
        "included_n": agg.included_n,
        "excluded_n": agg.excluded_n,
        "superseded_n": agg.superseded_n,
        "included_date_min": agg.included_date_min,
        "included_date_max": agg.included_date_max,
        "excluded_date_min": agg.excluded_date_min,
        "excluded_date_max": agg.excluded_date_max,
        "freeze_stamp": agg.freeze_stamp,
    }


def calibration_to_sidecar(meta: dict[str, Any], *, md_path: str = "") -> dict[str, Any]:
    return {
        "unit": "C",
        "computed_at": _iso_now(),
        "artifact_md": md_path,
        **meta,
    }


def write_sidecar(md_path: Path, payload: dict[str, Any]) -> Path:
    json_path = md_path.with_suffix(".json")
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return json_path
