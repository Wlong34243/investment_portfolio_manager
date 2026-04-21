# Podcast Transcript Fetcher
# Usage: python tasks/podcast_fetcher.py VIDEO_ID --source-name "Forward Guidance EP 412"

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
from datetime import datetime

TRANSCRIPTS_DIR = Path("data/podcast_transcripts")

def main():
    parser = argparse.ArgumentParser(
        description="Download YouTube transcript and save as plain text."
    )
    parser.add_argument("video_id", type=str, help="YouTube video ID")
    parser.add_argument("--source-name", type=str, default=None,
                        help="Optional source name for filename")
    args = parser.parse_args()

    # --- Transcript download ---
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("ERROR: youtube-transcript-api not installed. Run: pip install youtube-transcript-api")
        sys.exit(1)

    print(f"Fetching transcript for {args.video_id}...")
    try:
        transcript_segments = list(YouTubeTranscriptApi().fetch(args.video_id))
        full_text = " ".join([seg.text for seg in transcript_segments])
    except Exception as e:
        print(f"ERROR: Could not download transcript for {args.video_id}: {e}")
        sys.exit(1)

    word_count = len(full_text.split())
    print(f"Transcript loaded: {word_count} words")

    # --- Save to file ---
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    if args.source_name:
        import re
        slug = re.sub(r"[^\w\s-]", "", args.source_name).strip()
        slug = re.sub(r"[\s]+", "_", slug)
        filename = f"{date_str}_{slug}_{args.video_id}.txt"
    else:
        filename = f"{date_str}_{args.video_id}.txt"
    
    save_path = TRANSCRIPTS_DIR / filename
    save_path.write_text(full_text, encoding="utf-8")
    
    print(f"SUCCESS: Transcript saved to {save_path}")

if __name__ == "__main__":
    main()
