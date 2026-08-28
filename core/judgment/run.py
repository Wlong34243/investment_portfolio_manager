"""Judgment CLI orchestration and artifact writers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.judgment.calibration import build_calibration, format_calibration_markdown
from core.judgment.lifecycle import (
    Campaign,
    format_campaign_markdown,
    format_lifecycle_summary,
    list_held_tickers,
    retrieve_campaign,
)
from core.judgment.rotations import aggregate_rotations, format_rotations_markdown

OUTPUT_DIR = Path("agent_outputs/judgment")


def run_rotations() -> tuple[str, dict[str, Any], Any]:
    agg = aggregate_rotations()
    body = format_rotations_markdown(agg)
    meta = {
        "unit": "A",
        "included_n": agg.included_n,
        "excluded_n": agg.excluded_n,
        "superseded_n": agg.superseded_n,
        "freeze_stamp": agg.freeze_stamp,
    }
    if agg.included_date_min:
        meta["included_span"] = f"{agg.included_date_min} → {agg.included_date_max}"
    if agg.excluded_date_min:
        meta["excluded_span"] = f"{agg.excluded_date_min} → {agg.excluded_date_max}"
    return body, meta, agg


def run_lifecycle(*, ticker: str | None = None, all_tickers: bool = False) -> tuple[str, dict[str, Any], Optional[Campaign], Optional[list[Campaign]]]:
    if ticker:
        camp, rs = retrieve_campaign(ticker)
        if camp is None:
            body = f"# Judgment — Lifecycle: {ticker.upper()}\n\nNo campaign transactions in scope.\n"
            return body, {"unit": "B", "ticker": ticker.upper(), "retrieval_hash": rs.retrieval_hash}, None, None
        body = format_campaign_markdown(camp, retrieval_hash=rs.retrieval_hash)
        return body, {"unit": "B", "ticker": camp.ticker, "retrieval_hash": rs.retrieval_hash}, camp, None

    if all_tickers:
        campaigns = []
        last_hash = ""
        for t in list_held_tickers():
            camp, rs = retrieve_campaign(t)
            last_hash = rs.retrieval_hash
            if camp:
                campaigns.append(camp)
        body = format_lifecycle_summary(campaigns)
        return body, {
            "unit": "B",
            "tickers": len(campaigns),
            "retrieval_hash": last_hash,
            "runtime_warning": "~2.5 min/ticker; do not pipe stdout",
        }, None, campaigns

    raise ValueError("Specify --ticker or --all")


def run_calibration() -> tuple[str, dict[str, Any]]:
    result = build_calibration()
    body = format_calibration_markdown(result)
    meta = {
        "unit": "C",
        "gate_met": result.gate_met,
        "clean_trading_days": result.clean_trading_days,
        "firing_response_count": result.firing_response_count,
    }
    return body, meta


def write_judgment_report(
    body: str,
    meta: dict[str, Any],
    *,
    slug: str,
    campaign: Optional[Campaign] = None,
    rotation_agg: Any = None,
) -> Path:
    from core.judgment.artifacts import (
        calibration_to_sidecar,
        campaign_to_sidecar,
        rotations_to_sidecar,
        write_sidecar,
    )
    from core.judgment.registry import upsert_campaign

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    path = OUTPUT_DIR / f"{ts}_{slug}.md"
    computed_at = datetime.now(timezone.utc).isoformat()
    header = [
        f"<!-- Judgment Engine — {meta.get('unit', '?')} -->",
        f"**generated_at:** {computed_at}",
    ]
    if meta.get("retrieval_hash"):
        header.append(f"**retrieval_hash:** `{meta['retrieval_hash']}`")
    if "included_n" in meta:
        header.append(
            f"**N:** included={meta['included_n']} excluded={meta['excluded_n']} "
            f"superseded={meta.get('superseded_n', 0)}"
        )
    if meta.get("included_span"):
        header.append(f"**included_span:** {meta['included_span']}")
    if meta.get("excluded_span"):
        header.append(f"**excluded_span:** {meta['excluded_span']}")
    if meta.get("freeze_stamp"):
        header.append(f"**freeze_stamp:** `{meta['freeze_stamp']}`")
    if "gate_met" in meta:
        header.append(f"**unit_c_gate_met:** {meta['gate_met']}")
    if campaign is not None:
        header.append(f"**legs:** {len(campaign.legs)}")
    text = "\n".join(header) + "\n\n" + body
    path.write_text(text, encoding="utf-8")
    md_rel = str(path).replace("\\", "/")

    unit = meta.get("unit")
    if unit == "B" and campaign is not None:
        sidecar = campaign_to_sidecar(
            campaign,
            retrieval_hash=meta.get("retrieval_hash", ""),
            computed_at=computed_at,
            md_path=md_rel,
        )
        json_path = write_sidecar(path, sidecar)
        upsert_campaign(
            ticker=campaign.ticker,
            computed_at=computed_at,
            artifact_path=md_rel,
            json_path=str(json_path).replace("\\", "/"),
            legs=len(campaign.legs),
            retrieval_hash=meta.get("retrieval_hash", ""),
        )
    elif unit == "A" and rotation_agg is not None:
        write_sidecar(path, rotations_to_sidecar(rotation_agg, md_path=md_rel))
    elif unit == "C":
        write_sidecar(path, calibration_to_sidecar(meta, md_path=md_rel))

    return path
