# Batch Podcast Sync — Scheduled Orchestrator
#
# Finds the newest episode for each tracked podcast channel via YouTube RSS,
# checks against a local dedup log, and runs weekly_podcast_sync.py for new episodes.
#
# Usage:
#   python tasks/batch_podcast_sync.py              # Dry run — detect episodes, no Sheet writes
#   python tasks/batch_podcast_sync.py --live        # Live — detect + process + write to Sheet
#
# Called by: .github/workflows/podcast_sync.yml (weekly cron)
# Can also be run manually from the terminal.

import subprocess
import sys
import os
import json
import logging
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# sys.path setup (same pattern as weekly_podcast_sync.py)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Constants
# Per-channel config dict. Keys flow into the Source field in Sheets — use clean show names
# once resolved from the first live run. Placeholder names (Channel UC...) should be updated
# after observing the episode titles logged on first run.
PODCAST_CHANNELS = {
    "Forward Guidance":      {"channel_id": "UCkrwgzhIBKccuDsi_SvZtnQ"},
    "The Compound":          {"channel_id": "UCBRpqrzuuqE8TZcWw75JSdw"},
    "BG2 Pod":               {"channel_id": "UC-yRDvpR99LUc5l7i7jLzew"},
    "Capital Allocators":    {"channel_id": "UCbzQ_YWf9RsBP9ATbmv5kxQ"},
    "Chat With Traders":     {"channel_id": "UCdnzT5Tl6pAkATOiDsPhqcg"},
    "On The Tape":           {"channel_id": "UCe8y7CzcjhMPTzem-Zn6sqA"},
    "CNBC Television":       {"channel_id": "UCrp_UI8XtuYfpiqluWLD7Lw"},
    "Top Traders Unplugged": {"channel_id": "UCt-_RaV_mFlyXDmhYnIm0Ug"},
    "Invest Like The Best":  {"channel_id": "UCpQBb0fToph3jrDulwz1iUQ"},
    "On Investing":          {"channel_id": "UCToe3dspZyw2L_JY-JmP3Mw",
                              "title_filter": "On Investing"},
}

DEDUP_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "processed_videos.json")

# YouTube Atom feed namespace
YT_NS = "http://www.youtube.com/xml/schemas/2015"
ATOM_NS = "http://www.w3.org/2005/Atom"

# Dedup helpers
def load_processed_videos() -> dict:
    """Load the dedup log. Returns dict of {video_id: {channel, title, processed_at}}."""
    if os.path.exists(DEDUP_FILE):
        try:
            with open(DEDUP_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load dedup file: {e}")
            return {}
    return {}

def save_processed_videos(data: dict) -> None:
    """Write the dedup log. Creates data/ directory if needed."""
    os.makedirs(os.path.dirname(DEDUP_FILE), exist_ok=True)
    try:
        with open(DEDUP_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save dedup file: {e}")

# RSS fetch function
def get_latest_video(channel_id: str, title_filter: str | None = None) -> tuple[str, str] | tuple[None, None]:
    """
    Fetch the YouTube RSS feed and return (video_id, title) for the most recent
    upload. If title_filter is provided, return the most recent upload whose title
    contains title_filter (case-insensitive). Returns (None, None) if no feed or
    no matching entry in the (up to 15) entries the feed provides.
    """
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        with urllib.request.urlopen(feed_url, timeout=15) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)

        entries = root.findall(f"{{{ATOM_NS}}}entry")
        if not entries:
            return None, None

        for entry in entries:  # feed is newest-first
            video_id_elem = entry.find(f"{{{YT_NS}}}videoId")
            title_elem = entry.find(f"{{{ATOM_NS}}}title")
            video_id = video_id_elem.text if video_id_elem is not None else None
            title = title_elem.text if title_elem is not None else "Unknown Title"
            if video_id is None:
                continue
            if title_filter is None or title_filter.lower() in title.lower():
                return video_id, title

        return None, None  # no entry matched the filter
    except Exception as e:
        logger.error(f"Failed to fetch RSS for channel {channel_id}: {e}")
        return None, None

# Main function
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch podcast sync via YouTube RSS")
    parser.add_argument("--live", action="store_true",
                        help="Enable Sheet writes (passes --live to weekly_podcast_sync.py)")
    args = parser.parse_args()

    mode = "LIVE" if args.live else "DRY RUN"
    logger.info(f"=== Batch Podcast Sync — {mode} ===")

    processed = load_processed_videos()
    results = {"processed": [], "skipped": [], "filter_skipped": [], "failed": []}

    for channel_name, cfg in PODCAST_CHANNELS.items():
        channel_id = cfg["channel_id"]
        title_filter = cfg.get("title_filter")
        logger.info(f"Checking: {channel_name} ({channel_id})"
                    + (f" [filter: '{title_filter}']" if title_filter else ""))
        video_id, title = get_latest_video(channel_id, title_filter)
        if video_id is None:
            if title_filter:
                logger.info(f"  No recent episode matching '{title_filter}' — skipping")
                results["filter_skipped"].append(channel_name)
            else:
                logger.warning(f"  Could not fetch latest video for {channel_name}")
                results["failed"].append(channel_name)
            continue

        logger.info(f"  Latest: '{title}' (ID: {video_id})")

        # Dedup check
        if video_id in processed:
            logger.info(f"  SKIP — already processed on {processed[video_id]['processed_at']}")
            results["skipped"].append(channel_name)
            continue

        # Build the command
        script_path = os.path.join(os.path.dirname(__file__), "weekly_podcast_sync.py")
        cmd = [
            sys.executable, script_path,
            video_id,
            "--source-name", f"{channel_name}: {title}",
        ]
        if args.live:
            cmd.append("--live")

        logger.info(f"  Running: {' '.join(cmd)}")

        # Execute
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            logger.info(f"  SUCCESS for {channel_name}")
            if result.stdout:
                # Print last 5 lines of output (summary)
                for line in result.stdout.strip().split("\n")[-5:]:
                    logger.info(f"    {line}")

            # Record in dedup log
            processed[video_id] = {
                "channel": channel_name,
                "title": title,
                "processed_at": datetime.now().isoformat(),
            }
        else:
            logger.error(f"  FAILED for {channel_name} (exit code {result.returncode})")
            if result.stderr:
                for line in result.stderr.strip().split("\n")[-5:]:
                    logger.error(f"    {line}")
            results["failed"].append(channel_name)
            continue

        results["processed"].append(channel_name)

    # Only persist the dedup log on --live runs. Dry runs are non-destructive
    # so a subsequent --live run sees the episodes as new and processes them.
    if args.live:
        save_processed_videos(processed)

    # Summary
    logger.info("=== Summary ===")
    logger.info(f"  Processed: {results['processed'] or 'None'}")
    logger.info(f"  Skipped (already done): {results['skipped'] or 'None'}")
    logger.info(f"  Skipped (no filter match): {results['filter_skipped'] or 'None'}")
    logger.info(f"  Failed: {results['failed'] or 'None'}")

if __name__ == "__main__":
    main()
