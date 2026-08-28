"""Unit A — rotation quality aggregates (read-only over Rotation_Review)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Optional

import config
from tasks.compute_rotation_attribution import (
    COVERAGE_FLAG_PCT,
    HORIZONS,
    PRICE_SOURCE_FROZEN_BOUNDARY,
    find_superseded_groups,
    partition_rotation_rows,
)

JUDGE_MIN_N = getattr(config, "JUDGE_MIN_N", 12)


def _as_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_rotation_review_rows() -> list[dict[str, Any]]:
    """Read-only load from SQLite shadow (Rotation_Review is not recomputed here)."""
    uri = f"file:{config.SQLITE_DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        return [json.loads(r[0]) for r in conn.execute("SELECT payload_json FROM rotation_review")]
    finally:
        conn.close()


def _median_label(values: list[float], n_included: int, n_excluded: int, reason: str) -> str:
    if len(values) < JUDGE_MIN_N:
        return f"N too small (n={len(values)}, need {JUDGE_MIN_N}; included={n_included}, excluded={n_excluded}: {reason})"
    med = median(values)
    return f"{med:+.2%} (N={len(values)}, excluded={n_excluded}: {reason})"


@dataclass
class HorizonStats:
    horizon: int
    n: int
    n_excluded: int
    exclusion_reason: str
    median_residual: Optional[float]
    q1: Optional[float]
    q3: Optional[float]
    label: str


@dataclass
class RotationAggregate:
    total_rows: int
    included_n: int
    excluded_n: int
    superseded_n: int
    price_sources: list[str]
    freeze_stamp: str
    included_date_min: str = ""
    included_date_max: str = ""
    excluded_date_min: str = ""
    excluded_date_max: str = ""
    horizons: list[HorizonStats] = field(default_factory=list)
    by_rotation_type: dict[str, list[HorizonStats]] = field(default_factory=dict)
    by_implicit_bet: dict[str, list[HorizonStats]] = field(default_factory=dict)
    by_provenance: dict[str, list[HorizonStats]] = field(default_factory=dict)
    exclusion_breakdown: dict[str, int] = field(default_factory=dict)


def _date_span(rows: list[dict]) -> tuple[str, str]:
    ds = sorted(str(r.get("Date", "")).strip() for r in rows if str(r.get("Date", "")).strip())
    if not ds:
        return "", ""
    return ds[0], ds[-1]


def _horizon_stats(
    rows: list[dict],
    *,
    horizon: int,
    n_pool: int,
    n_excluded: int,
    reason: str,
) -> HorizonStats:
    vals: list[float] = []
    for r in rows:
        v = _as_float(r.get(f"Residual_Pair_{horizon}d"))
        if v is not None:
            vals.append(v)
    vals.sort()
    if len(vals) < JUDGE_MIN_N:
        label = _median_label(vals, n_pool, n_excluded, reason)
        return HorizonStats(horizon, len(vals), n_excluded, reason, None, None, None, label)
    q1 = vals[len(vals) // 4]
    q3 = vals[(3 * len(vals)) // 4]
    med = median(vals)
    label = f"{med:+.2%} (N={len(vals)}, excluded={n_excluded}: {reason})"
    return HorizonStats(horizon, len(vals), n_excluded, reason, med, q1, q3, label)


def _aggregate_subset(
    subset: list[dict],
    *,
    n_total: int,
    n_excluded_global: int,
    reason: str,
) -> list[HorizonStats]:
    return [
        _horizon_stats(subset, horizon=h, n_pool=len(subset), n_excluded=n_excluded_global, reason=reason)
        for h in HORIZONS
    ]


def aggregate_rotations(rows: Optional[list[dict]] = None) -> RotationAggregate:
    rows = rows if rows is not None else load_rotation_review_rows()
    included, excluded = partition_rotation_rows(rows)
    superseded_map, _groups = find_superseded_groups(rows)
    superseded_n = len(superseded_map)

    exclusion_breakdown: dict[str, int] = {}
    for r in excluded:
        st = str(r.get("Status") or "")
        if st.startswith("SUPERSEDED"):
            key = "superseded"
        elif st == "WEIGHTS_UNRECONCILED":
            key = "weight_reconciliation"
        elif _as_float(r.get("Coverage_Pct")) is not None and _as_float(r.get("Coverage_Pct")) < COVERAGE_FLAG_PCT:
            key = "low_coverage"
        else:
            key = "status_not_ok"
        exclusion_breakdown[key] = exclusion_breakdown.get(key, 0) + 1

    reason = (
        "well-reconciled rotations only; excluded skew old/wide (Analysis Rule 9); "
        "effective N below nominal N"
    )
    price_sources = sorted({str(r.get("Price_Source") or "") for r in rows})
    inc_min, inc_max = _date_span(included)
    exc_min, exc_max = _date_span(excluded)

    agg = RotationAggregate(
        total_rows=len(rows),
        included_n=len(included),
        excluded_n=len(excluded),
        superseded_n=superseded_n,
        price_sources=price_sources,
        freeze_stamp=PRICE_SOURCE_FROZEN_BOUNDARY,
        included_date_min=inc_min,
        included_date_max=inc_max,
        excluded_date_min=exc_min,
        excluded_date_max=exc_max,
        exclusion_breakdown=exclusion_breakdown,
    )
    agg.horizons = _aggregate_subset(included, n_total=len(rows), n_excluded_global=len(excluded), reason=reason)

    by_type: dict[str, list[dict]] = {}
    for r in included:
        rt = str(r.get("Rotation_Type") or "unknown").strip() or "unknown"
        by_type.setdefault(rt, []).append(r)
    for rt, subset in sorted(by_type.items()):
        agg.by_rotation_type[rt] = _aggregate_subset(
            subset, n_total=len(rows), n_excluded_global=len(excluded), reason=f"{reason}; type={rt}"
        )

    documented = [r for r in included if str(r.get("Implicit_Bet") or "").strip()]
    undocumented = [r for r in included if not str(r.get("Implicit_Bet") or "").strip()]
    agg.by_implicit_bet["documented_Implicit_Bet"] = _aggregate_subset(
        documented, n_total=len(rows), n_excluded_global=len(excluded), reason=f"{reason}; documented bet"
    )
    agg.by_implicit_bet["blank_Implicit_Bet"] = _aggregate_subset(
        undocumented, n_total=len(rows), n_excluded_global=len(excluded), reason=f"{reason}; blank bet"
    )

    by_prov: dict[str, list[dict]] = {}
    for r in included:
        prov = str(r.get("Rationale_Provenance") or "blank").strip() or "blank"
        by_prov.setdefault(prov, []).append(r)
    for prov, subset in sorted(by_prov.items()):
        agg.by_provenance[prov] = _aggregate_subset(
            subset, n_total=len(rows), n_excluded_global=len(excluded), reason=f"{reason}; provenance={prov}"
        )

    return agg


def format_rotations_markdown(agg: RotationAggregate) -> str:
    lines = [
        "# Judgment — Rotation quality (Unit A)",
        "",
        "> **Analysis Rule 9:** The aggregate describes a documented subset, not Bill's investing. "
        "Excluded rows are non-random — they skew old and wide. Effective N is far below nominal N.",
        "",
        f"**Rotation_Review freeze stamp (not recomputed):** `{agg.freeze_stamp}`",
        f"**Price_Source in store:** {', '.join(agg.price_sources) or '—'}",
        f"**Rows:** {agg.total_rows} total · **included={agg.included_n}** · **excluded={agg.excluded_n}** · "
        f"**superseded={agg.superseded_n}** (counted separately)",
    ]
    if agg.included_date_min:
        lines.append(
            f"**Included spans:** {agg.included_date_min} → {agg.included_date_max} "
            f"(young sample — 180d horizon fills as 2026 rotations age in)"
        )
    if agg.excluded_date_min:
        lines.append(
            f"**Excluded spans:** {agg.excluded_date_min} → {agg.excluded_date_max} "
            f"(mostly pre-scope / weight-reconciliation failures)"
        )
    lines.extend([
        "",
        "**Exclusion breakdown:** "
        + ", ".join(f"{k}={v}" for k, v in sorted(agg.exclusion_breakdown.items())),
        "",
        "## Residual_Pair distribution (all included)",
        "",
        "| Horizon | Median (with N) | Q1 | Q3 |",
        "|---|---|---|---|",
    ])
    for h in agg.horizons:
        q1 = f"{h.q1:+.2%}" if h.q1 is not None else "—"
        q3 = f"{h.q3:+.2%}" if h.q3 is not None else "—"
        lines.append(f"| {h.horizon}d | {h.label} | {q1} | {q3} |")

    if agg.by_rotation_type:
        lines.extend(["", "## By Rotation_Type", ""])
        for rt, stats in agg.by_rotation_type.items():
            lines.append(f"### {rt}")
            for h in stats:
                lines.append(f"- **{h.horizon}d:** {h.label}")
            lines.append("")

    lines.extend(["", "## By Implicit_Bet documentation", ""])
    for label, stats in agg.by_implicit_bet.items():
        lines.append(f"### {label}")
        for h in stats:
            lines.append(f"- **{h.horizon}d:** {h.label}")
        lines.append("")

    lines.extend(["", "## By Rationale_Provenance", ""])
    for prov, stats in agg.by_provenance.items():
        lines.append(f"### {prov}")
        for h in stats:
            lines.append(f"- **{h.horizon}d:** {h.label}")
        lines.append("")

    lines.extend([
        "",
        "*Measurement only — no recommendation. Counterfactuals and triggers are out of scope.*",
    ])
    return "\n".join(lines)
