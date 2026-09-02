"""Load and validate data/podcast_channels.json."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "data" / "podcast_channels.json"

UC_PATTERN = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
VALID_TRACKS = frozenset({"finance", "ai"})


def _load_raw() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(f"Channel registry not found: {REGISTRY_PATH}")
    with REGISTRY_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or "channels" not in data:
        raise ValueError("podcast_channels.json must contain a 'channels' array")
    return data


def _validate_entry(entry: dict[str, Any], seen_names: set[str], seen_ids: set[str]) -> None:
    name = entry.get("name")
    if not name or not isinstance(name, str):
        raise ValueError(f"Channel entry missing non-empty name: {entry!r}")
    if name in seen_names:
        raise ValueError(f"Duplicate channel name: {name!r}")
    seen_names.add(name)

    track = entry.get("track")
    if track not in VALID_TRACKS:
        raise ValueError(f"Channel {name!r}: invalid track {track!r} (must be finance or ai)")

    enabled = entry.get("enabled", True)
    channel_id = entry.get("channel_id", "")
    if enabled:
        if not channel_id or not UC_PATTERN.match(channel_id):
            raise ValueError(f"Channel {name!r}: enabled entry needs valid UC… channel_id")
        if channel_id in seen_ids:
            raise ValueError(f"Duplicate channel_id {channel_id!r} (entry {name!r})")
        seen_ids.add(channel_id)


def load_channels(track: str | None = None, enabled_only: bool = True) -> list[dict[str, Any]]:
    """
    Read podcast_channels.json, validate every entry, return matching channels.

    Raises on malformed file rather than silently dropping entries.
    """
    if track is not None and track not in VALID_TRACKS:
        raise ValueError(f"track filter must be finance, ai, or None — got {track!r}")

    data = _load_raw()
    seen_names: set[str] = set()
    seen_ids: set[str] = set()
    out: list[dict[str, Any]] = []

    for entry in data["channels"]:
        if not isinstance(entry, dict):
            raise ValueError(f"Each channel must be an object, got {type(entry)}")
        _validate_entry(entry, seen_names, seen_ids)
        if enabled_only and not entry.get("enabled", True):
            continue
        if track is not None and entry.get("track") != track:
            continue
        out.append(dict(entry))

    return out


def channels_as_legacy_dict(track: str = "finance") -> dict[str, dict[str, Any]]:
    """Return {name: {channel_id, title_filter?}} for backward-compatible callers."""
    legacy: dict[str, dict[str, Any]] = {}
    for ch in load_channels(track=track, enabled_only=True):
        cfg: dict[str, Any] = {"channel_id": ch["channel_id"]}
        tf = ch.get("title_filter")
        if tf:
            cfg["title_filter"] = tf
        legacy[ch["name"]] = cfg
    return legacy


def dedup_track(record: dict[str, Any]) -> str:
    """Missing track key means finance (historical dedup entries)."""
    return record.get("track") or "finance"
