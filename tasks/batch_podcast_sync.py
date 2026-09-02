# Batch Podcast Sync — Scheduled Orchestrator
#
# Registry-driven RSS walk; forks to weekly_podcast_sync (finance) or ai_track_sync (ai).
#
# Usage:
#   python tasks/batch_podcast_sync.py                              # Dry run, all tracks
#   python tasks/batch_podcast_sync.py --track finance --live       # Morning-style finance only
#   python tasks/batch_podcast_sync.py --track ai --max-per-channel 3 --since 2026-08-01

import argparse
import json
import logging
import os
import random
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from tasks.podcast_fetcher import EXIT_TRANSCRIPT_BLOCKED
from utils.channel_registry import channels_as_legacy_dict, dedup_track, load_channels

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Backward-compatible finance shim (manager.py imports this name)
PODCAST_CHANNELS = channels_as_legacy_dict(track="finance")

DEDUP_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "processed_videos.json")

YT_NS = "http://www.youtube.com/xml/schemas/2015"
ATOM_NS = "http://www.w3.org/2005/Atom"


def load_processed_videos() -> dict:
    if os.path.exists(DEDUP_FILE):
        try:
            with open(DEDUP_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load dedup file: %s", e)
            return {}
    return {}


def save_processed_videos(data: dict) -> None:
    os.makedirs(os.path.dirname(DEDUP_FILE), exist_ok=True)
    with open(DEDUP_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _parse_feed_entries(channel_id: str) -> list[dict]:
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    with urllib.request.urlopen(feed_url, timeout=15) as response:
        root = ET.fromstring(response.read())
    out: list[dict] = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        vid_el = entry.find(f"{{{YT_NS}}}videoId")
        title_el = entry.find(f"{{{ATOM_NS}}}title")
        pub_el = entry.find(f"{{{ATOM_NS}}}published")
        if vid_el is None or not vid_el.text:
            continue
        out.append(
            {
                "video_id": vid_el.text,
                "title": title_el.text if title_el is not None else "Unknown Title",
                "published": pub_el.text if pub_el is not None else "",
            }
        )
    return out


def get_recent_videos(
    channel_id: str,
    title_filter: str | None = None,
    since: str | None = None,
    limit: int = 1,
) -> list[tuple[str, str, str]]:
    """
    Return up to `limit` entries as (video_id, title, published), oldest-first.
    Feed order is newest-first; reversed before return.
    """
    try:
        entries = _parse_feed_entries(channel_id)
    except Exception as e:
        logger.error("Failed to fetch RSS for channel %s: %s", channel_id, e)
        return []

    filtered: list[dict] = []
    since_date = since  # YYYY-MM-DD compare on published prefix
    for ent in entries:
        title = ent["title"]
        if title_filter and title_filter.lower() not in title.lower():
            continue
        pub = ent["published"]
        if since_date and pub and pub[:10] < since_date:
            continue
        filtered.append(ent)

    # newest-first in feed -> take first `limit` matching, then oldest-first for processing
    batch = filtered[:limit]
    batch.reverse()
    return [(e["video_id"], e["title"], e["published"]) for e in batch]


def get_latest_video(
    channel_id: str, title_filter: str | None = None
) -> tuple[str, str] | tuple[None, None]:
    rows = get_recent_videos(channel_id, title_filter=title_filter, limit=1)
    if not rows:
        return None, None
    vid, title, _pub = rows[0]
    return vid, title


def _transcript_word_count(video_id: str) -> int | None:
    """Word count from an ALREADY-SAVED transcript. Never fetches.

    This used to download the full transcript purely to print a word count on the
    plan line -- and the child process then downloaded the same transcript again.
    Two requests per video, fired even on a dry run, was the single largest
    contributor to the 2026-08-31 RequestBlocked incident. Local files only now;
    a video with no cached transcript reports None and the plan line says so.
    """
    root = os.path.join(os.path.dirname(__file__), "..", "data", "podcast_transcripts")
    for pattern in (root, os.path.join(root, "ai")):
        try:
            for name in os.listdir(pattern):
                if name.endswith(f"_{video_id}.txt"):
                    with open(os.path.join(pattern, name), "r", encoding="utf-8") as fh:
                        return len(fh.read().split())
        except FileNotFoundError:
            continue
    return None


def _throttle(first: bool) -> None:
    """Sleep between transcript requests. No sleep before the first of a run."""
    if first:
        return
    delay = getattr(config, "TRANSCRIPT_FETCH_DELAY_SEC", 4.0)
    jitter = getattr(config, "TRANSCRIPT_FETCH_JITTER_SEC", 2.0)
    time.sleep(delay + random.uniform(0.0, jitter))


def _track_filter_arg(track: str) -> str | None:
    if track == "all":
        return None
    return track


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch podcast sync via YouTube RSS")
    parser.add_argument("--live", action="store_true", help="Persist dedup + enable downstream writes")
    parser.add_argument(
        "--track",
        choices=["finance", "ai", "all"],
        default="all",
        help="Which registry rows to walk (default: all)",
    )
    parser.add_argument("--max-per-channel", type=int, default=1, help="Max unprocessed entries per channel")
    parser.add_argument("--since", type=str, default=None, help="Ignore entries published before YYYY-MM-DD")
    parser.add_argument("--channel", action="append", default=[], help="Restrict to registry name (repeatable)")
    args = parser.parse_args()

    mode = "LIVE" if args.live else "DRY RUN"
    logger.info("=== Batch Podcast Sync — %s (track=%s) ===", mode, args.track)

    processed = load_processed_videos()
    results = {"processed": [], "skipped": [], "filter_skipped": [], "failed": [], "aborted": []}
    blocked = False
    fetch_count = 0

    channels = load_channels(track=_track_filter_arg(args.track))
    if args.channel:
        allowed = set(args.channel)
        channels = [c for c in channels if c["name"] in allowed]

    for cfg in channels:
        if blocked:
            results["aborted"].append(cfg["name"])
            continue
        channel_name = cfg["name"]
        channel_id = cfg["channel_id"]
        title_filter = cfg.get("title_filter")
        track = cfg["track"]
        min_words = cfg.get("min_words")

        logger.info(
            "Checking: %s (%s) [track=%s]%s",
            channel_name,
            channel_id,
            track,
            f" [filter: '{title_filter}']" if title_filter else "",
        )

        candidates = get_recent_videos(
            channel_id,
            title_filter=title_filter,
            since=args.since,
            limit=args.max_per_channel * 3,  # fetch extra for dedup skips
        )
        if not candidates and title_filter:
            logger.info("  No recent episode matching '%s' — skipping", title_filter)
            results["filter_skipped"].append(channel_name)
            continue
        if not candidates:
            logger.warning("  Could not fetch videos for %s", channel_name)
            results["failed"].append(channel_name)
            continue

        to_run: list[tuple[str, str, str]] = []
        for video_id, title, published in candidates:
            if len(to_run) >= args.max_per_channel:
                break
            if video_id in processed:
                continue
            # --since: entries without published in dedup are already processed
            if args.since and published and published[:10] < args.since:
                continue
            to_run.append((video_id, title, published))

        if not to_run:
            logger.info("  SKIP — no new episodes (dedup)")
            results["skipped"].append(channel_name)
            continue

        script = "weekly_podcast_sync.py" if track == "finance" else "ai_track_sync.py"

        for video_id, title, published in to_run:
            wc = _transcript_word_count(video_id)
            wc_s = f"{wc} words" if wc is not None else "word count unavailable"
            logger.info("  Plan: %s | %s | %s | -> %s (%s)", video_id, published[:10], title[:50], script, wc_s)

            cmd = [
                sys.executable,
                os.path.join(os.path.dirname(__file__), script),
                video_id,
                "--source-name",
                f"{channel_name}: {title}",
            ]
            if min_words is not None:
                cmd.extend(["--min-words", str(min_words)])
            if args.live:
                cmd.append("--live")

            logger.info("  Running: %s", " ".join(cmd))
            _throttle(first=(fetch_count == 0))
            fetch_count += 1
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info("  SUCCESS for %s / %s", channel_name, video_id)
                if result.stdout:
                    for line in result.stdout.strip().split("\n")[-5:]:
                        logger.info("    %s", line)
                processed[video_id] = {
                    "channel": channel_name,
                    "title": title,
                    "track": track,
                    "published": published,
                    "processed_at": datetime.now().isoformat(),
                }
                if args.live:
                    save_processed_videos(processed)
            elif result.returncode == EXIT_TRANSCRIPT_BLOCKED:
                # Global condition, not a per-channel failure. Walking the remaining
                # channels would fire one more blocked request each and extend the
                # block. Stop the run.
                logger.error(
                    "  ABORTED — YouTube transcript endpoint is rate-limiting this IP. "
                    "Remaining channels skipped."
                )
                output = (result.stdout or "") + (result.stderr or "")
                for line in output.strip().split("\n")[-6:]:
                    logger.error("    %s", line)
                results["failed"].append(channel_name)
                blocked = True
                break
            else:
                logger.error("  FAILED for %s (exit %s)", channel_name, result.returncode)
                output = (result.stdout or "") + (result.stderr or "")
                for line in output.strip().split("\n")[-10:]:
                    logger.error("    %s", line)
                results["failed"].append(channel_name)
                break

        if channel_name not in results["failed"]:
            results["processed"].append(channel_name)

    logger.info("=== Summary ===")
    logger.info("  Processed: %s", results["processed"] or "None")
    logger.info("  Skipped (already done): %s", results["skipped"] or "None")
    logger.info("  Skipped (no filter match): %s", results["filter_skipped"] or "None")
    logger.info("  Failed: %s", results["failed"] or "None")
    logger.info("  Aborted (not walked): %s", results["aborted"] or "None")

    # Exit codes. main() used to return None -- a run in which every channel failed
    # exited 0 and read as success to anything checking a return code.
    if blocked:
        logger.error("Exiting 3: transcript endpoint blocked. Do not retry immediately.")
        sys.exit(EXIT_TRANSCRIPT_BLOCKED)
    if results["failed"] and not results["processed"]:
        logger.error("Exiting 1: nothing processed and %d channel(s) failed.", len(results["failed"]))
        sys.exit(1)


if __name__ == "__main__":
    main()
