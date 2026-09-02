"""Judgment artifacts page — disk reads only, no inline compute."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.judgment.lifecycle_index import list_lifecycle_artifacts

from ui.judgment_artifacts import load_artifact_bundle, newest_artifact


def assemble_judgment(section: str | None = None) -> dict[str, Any]:
    rotations_md = newest_artifact("*rotations*.md")
    calibration_md = newest_artifact("*calibration*.md")
    lifecycle_all_md = newest_artifact("*lifecycle_all*.md")

    rotations = load_artifact_bundle(rotations_md)
    calibration = load_artifact_bundle(calibration_md)
    lifecycle_all = load_artifact_bundle(lifecycle_all_md)
    lifecycle_index = list_lifecycle_artifacts()

    for row in lifecycle_index:
        sc = row.get("sidecar") or {}
        row["twr"] = sc.get("time_weighted_return_pct")
        row["single_entry"] = sc.get("single_entry_return_pct")
        row["scaling_delta"] = sc.get("scaling_delta_pct")
        row["computed_at"] = sc.get("computed_at")
        row["span_start"] = sc.get("span_start")
        row["span_end"] = sc.get("span_end")
        row["missing_sidecar"] = not (sc or Path(row["path"]).with_suffix(".json").is_file())
        if row["span_start"] and row["span_end"]:
            row["span"] = f"{row['span_start']}–{row['span_end']}"
        else:
            row["span"] = ""

    if rotations and rotations.get("sidecar"):
        rotations["meta"] = rotations["sidecar"]
    if calibration and calibration.get("sidecar"):
        calibration["meta"] = calibration["sidecar"]

    rotation_why_cards: list[dict[str, Any]] = []
    if section in ("rotations", "overview"):
        try:
            from ui.why_cards import load_rotation_cards

            rotation_why_cards = load_rotation_cards()
        except Exception:
            rotation_why_cards = []

    cal_meta = (calibration or {}).get("meta") or {}

    return {
        "section": section or "overview",
        "rotations": rotations,
        "calibration": calibration,
        "calibration_meta": cal_meta,
        "lifecycle_all": lifecycle_all,
        "lifecycle_index": lifecycle_index,
        "lifecycle_count": len(lifecycle_index),
        "rotation_why_cards": rotation_why_cards,
        "rotation_why_count": len(rotation_why_cards),
    }
