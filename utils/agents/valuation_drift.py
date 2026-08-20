"""
utils/agents/valuation_drift.py — Fundamentals drift vs thesis baseline (Option A).

Python gathers metrics from the market/composite bundle's `fundamentals` block.
LLM narrates measured change only — never fetches, never recommends trades.
Baseline: first-run snapshot-forward (Option A). Day-one drift is definitionally zero.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

BASELINE_PATH = Path("data/valuation_drift_baselines.json")
OUTPUT_DIR = Path("agent_outputs/valuation_drift")
PROMPT_PATH = Path("prompts/valuation_drift.md")

DRIFT_FIELDS = (
    "forward_pe",
    "pe_ratio",  # trailing
    "peg_ratio",
    "ev_ebitda",
    "price_to_sales",
    "gross_margin",
    "gross_margin_trend",
    "fcf_trend",
    "revenue_growth_yoy",
    "net_debt_ebitda",
)


class FieldDrift(BaseModel):
    field: str
    baseline: Any = "UNAVAILABLE"
    current: Any = "UNAVAILABLE"
    baseline_date: Optional[str] = None
    current_date: Optional[str] = None


class PositionDrift(BaseModel):
    ticker: str
    fields: list[FieldDrift]
    thesis_note: Optional[str] = None


class ValuationDriftOutput(BaseModel):
    bundle_hash: str
    composite_hash: Optional[str] = None
    baseline_option: Literal["A"] = "A"
    baseline_option_note: str = (
        "Option A snapshot-forward: first run wrote today's fundamentals as baseline; "
        "day-one drift is definitionally zero."
    )
    generated_at: Optional[datetime] = None
    positions: list[PositionDrift] = Field(default_factory=list)
    notes: Optional[str] = None


def _unavailable(v: Any) -> Any:
    if v is None or v == "" or (isinstance(v, float) and v != v):
        return "UNAVAILABLE"
    if isinstance(v, dict) and v.get("error"):
        return "UNAVAILABLE"
    return v


def _load_baselines() -> dict:
    if not BASELINE_PATH.exists():
        return {}
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("baseline load failed: %s", e)
        return {}


def _save_baselines(data: dict) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _normalize_fundamentals(raw: dict | None) -> dict[str, Any]:
    if not raw or raw.get("error"):
        return {f: "UNAVAILABLE" for f in DRIFT_FIELDS}
    out = {}
    # alias trailing
    mapping = {
        "forward_pe": "forward_pe",
        "pe_ratio": "pe_ratio",
        "peg_ratio": "peg_ratio",
        "ev_ebitda": "ev_ebitda",
        "price_to_sales": "price_to_sales",
        "gross_margin": "gross_margin",
        "gross_margin_trend": "gross_margin_trend",
        "fcf_trend": "fcf_trend",
        "revenue_growth_yoy": "revenue_growth_yoy",
        "net_debt_ebitda": "net_debt_ebitda",
    }
    for field, key in mapping.items():
        out[field] = _unavailable(raw.get(key))
    # trailing_pe alias if pe_ratio missing
    if out["pe_ratio"] == "UNAVAILABLE":
        out["pe_ratio"] = _unavailable(raw.get("trailing_pe"))
    return out


def build_drift_table(
    fundamentals: dict[str, dict],
    *,
    tickers: list[str] | None = None,
    as_of: str | None = None,
) -> tuple[list[PositionDrift], bool]:
    """
    Compare current fundamentals to Option A baselines.
    Returns (rows, baselines_were_created).
    """
    as_of = as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    baselines = _load_baselines()
    created = False
    rows: list[PositionDrift] = []

    keys = tickers or sorted(fundamentals.keys())
    for t in keys:
        t = t.upper()
        cur_raw = fundamentals.get(t) or {}
        current = _normalize_fundamentals(cur_raw)
        cur_date = cur_raw.get("fetched_at") or as_of

        entry = baselines.get(t)
        if not entry:
            baselines[t] = {
                "baseline_date": as_of,
                "metrics": {k: current[k] for k in DRIFT_FIELDS},
            }
            entry = baselines[t]
            created = True

        base_metrics = entry.get("metrics") or {}
        base_date = entry.get("baseline_date")
        fields = []
        for f in DRIFT_FIELDS:
            fields.append(
                FieldDrift(
                    field=f,
                    baseline=_unavailable(base_metrics.get(f)),
                    current=current.get(f, "UNAVAILABLE"),
                    baseline_date=base_date,
                    current_date=str(cur_date)[:10] if cur_date else as_of,
                )
            )
        rows.append(PositionDrift(ticker=t, fields=fields))

    if created:
        _save_baselines(baselines)
    return rows, created


def run_valuation_drift(
    *,
    composite_bundle_path: str | None = None,
    ticker: str | None = None,
    dry_run: bool = False,
) -> ValuationDriftOutput:
    from utils.gemini_client import ask_gemini_composite
    from core.composite_bundle import load_composite_bundle

    def _find_latest_composite(bundle_dir: Path = Path("bundles")) -> Path:
        files = sorted(
            bundle_dir.glob("composite_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not files:
            raise FileNotFoundError(f"No composite bundles found in {bundle_dir}")
        return files[-1]

    path = Path(composite_bundle_path) if composite_bundle_path else _find_latest_composite()
    data = load_composite_bundle(path)

    market_path = Path(data.get("market_bundle_path") or "")
    market: dict = {}
    if market_path.exists():
        market = json.loads(market_path.read_text(encoding="utf-8"))

    fundamentals = market.get("fundamentals") or {}
    tickers = [ticker.upper()] if ticker else None
    positions, created = build_drift_table(fundamentals, tickers=tickers)

    bundle_hash = market.get("bundle_hash") or data.get("market_hash") or "UNKNOWN"
    composite_hash = data.get("composite_hash")

    system_instruction = ""
    if PROMPT_PATH.exists():
        system_instruction = PROMPT_PATH.read_text(encoding="utf-8")

    measured = {
        "baseline_option": "A",
        "baselines_created_this_run": created,
        "positions": [p.model_dump() for p in positions],
    }
    user_prompt = (
        "Measure-only valuation drift narration.\n"
        "You are given Python-computed baseline→current field tables. "
        "Describe what changed. Do not recommend buys/sells/trims/adds. "
        "Do not invent numbers. Use UNAVAILABLE when present.\n\n"
        f"MEASURED_JSON:\n{json.dumps(measured, indent=2, default=str)}\n"
    )

    result = ask_gemini_composite(
        prompt=user_prompt,
        composite_bundle_path=path,
        response_schema=ValuationDriftOutput,
        system_instruction=system_instruction,
        max_tokens=8000,
        include_vault_context=True,
    )
    if result is None:
        return ValuationDriftOutput(
            bundle_hash=str(bundle_hash),
            composite_hash=str(composite_hash) if composite_hash else None,
            positions=positions,
            notes="LLM call returned None — measured table only.",
            generated_at=datetime.now(timezone.utc),
        )
    if not result.positions:
        result.positions = positions
    result.baseline_option = "A"
    result.generated_at = datetime.now(timezone.utc)
    if not result.bundle_hash:
        result.bundle_hash = str(bundle_hash)
    if not result.composite_hash and composite_hash:
        result.composite_hash = str(composite_hash)
    return result


def write_drift_report(output: ValuationDriftOutput, *, dry_run: bool = False) -> str | Path:
    lines = [
        f"# Valuation Drift — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        f"**baseline_option:** {output.baseline_option} — {output.baseline_option_note}",
        f"**bundle_hash:** `{output.bundle_hash}`",
        f"**composite_hash:** `{output.composite_hash or 'n/a'}`",
        "",
    ]
    for pos in output.positions:
        lines.append(f"## {pos.ticker}")
        lines.append("")
        lines.append("| Field | Baseline | Current | Baseline date | Current date |")
        lines.append("|---|---|---|---|---|")
        for f in pos.fields:
            lines.append(
                f"| {f.field} | {f.baseline} | {f.current} | {f.baseline_date} | {f.current_date} |"
            )
        lines.append("")
        if pos.thesis_note:
            lines.append(pos.thesis_note)
            lines.append("")
    if output.notes:
        lines.append("## Notes")
        lines.append(output.notes)
        lines.append("")

    text = "\n".join(lines)
    if dry_run:
        return text

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    prefix = (output.composite_hash or output.bundle_hash or "nohash")[:12]
    path = OUTPUT_DIR / (
        f"valuation_drift_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}_{prefix}.md"
    )
    path.write_text(text, encoding="utf-8")
    return path
