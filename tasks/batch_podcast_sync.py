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
PODCAST_CHANNELS = {
    "Forward Guidance": "UCkrwgzhIBKccuDsi_SvZtnQ",  # verified: Forward Guidance (@ForwardGuidanceBW)
    "The Compound": "UCBRpqrzuuqE8TZcWw75JSdw",    # verified: The Compound (Josh Brown / Ritholtz)
    "Risk Reversal": "UCRAOycPjsSgcEyQcuJD_ENA",   # verified: RiskReversal Media (@RiskReversalMedia)
}

# Optional title filters — if set, skip videos whose titles don't contain the keyword.
# Prevents short clips / highlights from being processed instead of full episodes.
TITLE_FILTERS = {
    "The Compound": "TCAF",   # Only process full "The Compound and Friends" episodes
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
def get_latest_video(channel_id: str, title_filter: str = None) -> tuple[str, str] | tuple[None, None]:
    """
    Fetch the YouTube RSS feed for a channel and return (video_id, title)
    for the most recent upload matching the optional title_filter keyword.
    Scans up to 15 recent videos. Returns (None, None) on failure.
    """
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        with urllib.request.urlopen(feed_url, timeout=15) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)

        entries = root.findall(f"{{{ATOM_NS}}}entry")
        for entry in entries[:15]:
            video_id_elem = entry.find(f"{{{YT_NS}}}videoId")
            title_elem    = entry.find(f"{{{ATOM_NS}}}title")
            video_id = video_id_elem.text if video_id_elem is not None else None
            title    = title_elem.text    if title_elem    is not None else "Unknown Title"

            if title_filter and title_filter.lower() not in title.lower():
                logger.info(f"  Skipping '{title}' (doesn't match filter '{title_filter}')")
                continue

            return video_id, title

        logger.warning(f"No video matching filter '{title_filter}' found in last 15 uploads")
        return None, None
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
    results = {"processed": [], "skipped": [], "failed": []}

    for channel_name, channel_id in PODCAST_CHANNELS.items():
        logger.info(f"Checking: {channel_name} ({channel_id})")

        title_filter = TITLE_FILTERS.get(channel_name)
        video_id, title = get_latest_video(channel_id, title_filter=title_filter)
        if video_id is None:
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

    # Save dedup log (even in dry-run, so we remember what we've seen)
    save_processed_videos(processed)

    # Summary
    logger.info("=== Summary ===")
    logger.info(f"  Processed: {results['processed'] or 'None'}")
    logger.info(f"  Skipped (already done): {results['skipped'] or 'None'}")
    logger.info(f"  Failed: {results['failed'] or 'None'}")

if __name__ == "__main__":
    main()
