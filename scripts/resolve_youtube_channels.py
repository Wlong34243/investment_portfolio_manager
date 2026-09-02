#!/usr/bin/env python3
"""
One-shot YouTube channel resolver — dry-run by default.

Resolves @handles and user/ URLs to canonical UC… channel IDs, verifies via Atom feed,
prints a review table. Writes data/podcast_channels.json only with --live after sign-off.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "data" / "podcast_channels.json"

UC_PATTERN = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
CHANNEL_ID_IN_HTML = re.compile(
    r'"(?:channelId|externalId)"\s*:\s*"(UC[A-Za-z0-9_-]{22})"'
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS = "http://www.youtube.com/xml/schemas/2015"

# Existing 10 finance channels (byte-identical migration)
EXISTING_FINANCE = [
    {"name": "Forward Guidance", "channel_id": "UCkrwgzhIBKccuDsi_SvZtnQ", "title_filter": None},
    {"name": "The Compound", "channel_id": "UCBRpqrzuuqE8TZcWw75JSdw", "title_filter": None},
    {"name": "BG2 Pod", "channel_id": "UC-yRDvpR99LUc5l7i7jLzew", "title_filter": None},
    {"name": "Capital Allocators", "channel_id": "UCbzQ_YWf9RsBP9ATbmv5kxQ", "title_filter": None},
    {"name": "Chat With Traders", "channel_id": "UCdnzT5Tl6pAkATOiDsPhqcg", "title_filter": None},
    {"name": "On The Tape", "channel_id": "UCe8y7CzcjhMPTzem-Zn6sqA", "title_filter": None},
    {"name": "CNBC Television", "channel_id": "UCrp_UI8XtuYfpiqluWLD7Lw", "title_filter": None},
    {"name": "Top Traders Unplugged", "channel_id": "UCt-_RaV_mFlyXDmhYnIm0Ug", "title_filter": None},
    {"name": "Invest Like The Best", "channel_id": "UCpQBb0fToph3jrDulwz1iUQ", "title_filter": None},
    {
        "name": "On Investing",
        "channel_id": "UCToe3dspZyw2L_JY-JmP3Mw",
        "title_filter": "On Investing",
    },
]

# 4 new finance + 9 new AI (from prompt)
NEW_CHANNELS = [
    # finance
    {"name": "Excess Returns Clips", "input": "UCr5lgfnWV8bp23qWQGHZRlg", "track": "finance", "notes": "clips channel — candidate for min_words"},
    {"name": "Goldman Sachs", "input": "@GoldmanSachs", "track": "finance", "notes": "high upload volume; candidate for title_filter"},
    {"name": "Moonshots Highlights", "input": "@MoonshotsHighlights", "track": "finance", "notes": "highlights channel — candidate for min_words"},
    {"name": "Fundstrat", "input": "@fundstratcapital", "track": "finance", "notes": "verify feed title and recent episodes"},
    # ai
    {"name": "Google DeepMind", "input": "@googledeepmind", "track": "ai", "notes": None},
    {"name": "IBM Technology", "input": "@IBMTechnology", "track": "ai", "notes": None},
    {"name": "OpenAI", "input": "@OpenAI", "track": "ai", "notes": None},
    {"name": "Two Minute Papers", "input": "@TwoMinutePapers", "track": "ai", "notes": "legacy user/keeroyz also resolves"},
    {"name": "Yannic Kilcher", "input": "UCZHmQk67mSJgfCCTn7xBfew", "track": "ai", "notes": None},
    {"name": "AI Explained", "input": "UCNJ1Ymd5yFuUPtn21xtRbbw", "track": "ai", "notes": None},
    {"name": "Matthew Berman", "input": "UCuar6bhYQon68ppqmU-wYXA", "track": "ai", "notes": None},
    {"name": "David Shapiro", "input": "@DaveShap", "track": "ai", "notes": "handle may be renamed"},
    {
        "name": "Fireship",
        "input": "@Fireship",
        "track": "ai",
        "notes": "mostly non-AI dev content; title_filter candidate if signal-to-noise poor",
    },
]


def _fetch_url(url: str, timeout: int = 15) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def resolve_input(raw_input: str) -> str | None:
    """Return UC… channel ID or None (UNRESOLVED)."""
    raw = raw_input.strip()
    if UC_PATTERN.match(raw):
        return raw

    if raw.startswith("@"):
        handle = raw[1:]
        url = f"https://www.youtube.com/@{handle}"
    elif raw.startswith("user/"):
        url = f"https://www.youtube.com/user/{raw[5:]}"
    else:
        return None

    status, html = _fetch_url(url)
    if status != 200 or not html:
        return None
    m = CHANNEL_ID_IN_HTML.search(html)
    return m.group(1) if m else None


def verify_channel(channel_id: str) -> tuple[str, list[str]]:
    """Return (feed_title, latest_3_titles)."""
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        with urllib.request.urlopen(feed_url, timeout=15) as resp:
            root = ET.fromstring(resp.read())
    except Exception:
        return "—", []

    title_el = root.find(f"{{{ATOM_NS}}}title")
    feed_title = title_el.text if title_el is not None else "—"
    latest: list[str] = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry")[:3]:
        t = entry.find(f"{{{ATOM_NS}}}title")
        if t is not None and t.text:
            latest.append(t.text[:80])
    return feed_title, latest


def resolve_all() -> list[dict]:
    rows: list[dict] = []
    for ch in NEW_CHANNELS:
        time.sleep(2)
        resolved = resolve_input(ch["input"])
        feed_title = "—"
        latest_3: list[str] = []
        if resolved:
            time.sleep(2)
            feed_title, latest_3 = verify_channel(resolved)
        rows.append(
            {
                "name": ch["name"],
                "input": ch["input"],
                "track": ch["track"],
                "notes": ch.get("notes"),
                "resolved_id": resolved or "UNRESOLVED",
                "feed_title": feed_title,
                "latest_3": latest_3,
            }
        )
    return rows


def _safe_console(text: str) -> str:
    """Avoid Windows cp1252 encode failures on feed titles."""
    return text.encode("ascii", errors="replace").decode("ascii")


def print_table(rows: list[dict]) -> None:
    hdr = f"{'NAME':<24} {'INPUT':<28} {'RESOLVED_ID':<28} {'FEED_TITLE':<30} {'LATEST_3'}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        latest = " | ".join(_safe_console(t) for t in r["latest_3"]) if r["latest_3"] else "-"
        print(
            f"{r['name']:<24} {r['input']:<28} {r['resolved_id']:<28} "
            f"{_safe_console(r['feed_title'][:28]):<30} {latest}"
        )


def build_registry(rows: list[dict]) -> dict:
    channels: list[dict] = []

    for ex in EXISTING_FINANCE:
        channels.append(
            {
                "name": ex["name"],
                "channel_id": ex["channel_id"],
                "handle": None,
                "track": "finance",
                "enabled": True,
                "title_filter": ex["title_filter"],
                "min_words": None,
                "added": "2026-04-01",
                "notes": "migrated from PODCAST_CHANNELS dict",
            }
        )

    for r in rows:
        if r["track"] != "finance":
            continue
        handle = r["input"] if r["input"].startswith("@") else None
        enabled = r["resolved_id"] != "UNRESOLVED"
        note_parts = []
        if r.get("notes"):
            note_parts.append(r["notes"])
        if not enabled:
            note_parts.append(f"UNRESOLVED from input {r['input']}")
        channels.append(
            {
                "name": r["name"],
                "channel_id": r["resolved_id"] if enabled else "",
                "handle": handle,
                "track": "finance",
                "enabled": enabled,
                "title_filter": None,
                "min_words": None,
                "added": "2026-08-31",
                "notes": "; ".join(note_parts) if note_parts else None,
            }
        )

    for r in rows:
        if r["track"] != "ai":
            continue
        handle = r["input"] if r["input"].startswith("@") else None
        enabled = r["resolved_id"] != "UNRESOLVED"
        note_parts = []
        if r.get("notes"):
            note_parts.append(r["notes"])
        if not enabled:
            note_parts.append(f"UNRESOLVED from input {r['input']}")
        channels.append(
            {
                "name": r["name"],
                "channel_id": r["resolved_id"] if enabled else "",
                "handle": handle,
                "track": "ai",
                "enabled": enabled,
                "title_filter": None,
                "min_words": None,
                "added": "2026-08-31",
                "notes": "; ".join(note_parts) if note_parts else None,
            }
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        "channels": channels,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve YouTube channels for podcast registry")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Write data/podcast_channels.json (default: print table only)",
    )
    args = parser.parse_args()

    print("Resolving new channels (2s rate limit between requests)...")
    rows = resolve_all()
    print_table(rows)

    if not args.live:
        print("\nDRY RUN — no files written. Re-run with --live after sign-off.")
        return 0

    registry = build_registry(rows)
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {REGISTRY_PATH} ({len(registry['channels'])} channels)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
