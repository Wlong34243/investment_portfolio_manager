# Podcast Transcript Fetcher
# Usage: python tasks/podcast_fetcher.py VIDEO_ID --source-name "Forward Guidance EP 412"

import sys
import os
import re
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

TRANSCRIPTS_DIR = Path(__file__).parent.parent / "data" / "podcast_transcripts"


def fetch_transcript_to_file(video_id: str, source_name: str = None, out_dir: Path = None) -> Path:
    """
    Download a YouTube transcript and save it as plain text.

    Returns the path to the written file.
    Raises RuntimeError if the transcript cannot be downloaded.
    """
    from youtube_transcript_api import YouTubeTranscriptApi

    transcript_segments = list(YouTubeTranscriptApi().fetch(video_id))
    full_text = " ".join([seg.text for seg in transcript_segments])

    target_dir = out_dir or TRANSCRIPTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    if source_name:
        slug = re.sub(r"[^\w\s-]", "", source_name).strip()
        slug = re.sub(r"[\s]+", "_", slug)
        filename = f"{date_str}_{slug}_{video_id}.txt"
    else:
        filename = f"{date_str}_{video_id}.txt"

    save_path = target_dir / filename
    save_path.write_text(full_text, encoding="utf-8")
    return save_path


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Download YouTube transcript and save as plain text."
    )
    parser.add_argument("video_id", type=str, help="YouTube video ID")
    parser.add_argument("--source-name", type=str, default=None,
                        help="Optional source name for filename")
    args = parser.parse_args()

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("ERROR: youtube-transcript-api not installed. Run: pip install youtube-transcript-api")
        sys.exit(1)

    print(f"Fetching transcript for {args.video_id}...")
    try:
        save_path = fetch_transcript_to_file(args.video_id, source_name=args.source_name)
    except Exception as e:
        print(f"ERROR: Could not download transcript for {args.video_id}: {e}")
        sys.exit(1)

    word_count = len(save_path.read_text(encoding="utf-8").split())
    print(f"Transcript loaded: {word_count} words")
    print(f"SUCCESS: Transcript saved to {save_path}")


if __name__ == "__main__":
    main()
