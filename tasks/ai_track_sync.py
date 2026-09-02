# AI-track sync — YouTube transcript -> Gemini brief (no Sheets, no allocation)
#
# Usage:
#   python tasks/ai_track_sync.py VIDEO_ID --source-name "Google DeepMind: <title>"
#   python tasks/ai_track_sync.py VIDEO_ID --source-name "..." --live

import argparse
import hashlib
import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BRIEFS_DIR = Path(__file__).resolve().parents[1] / "data" / "ai_briefs"
AI_TRANSCRIPTS_DIR = Path(__file__).resolve().parents[1] / "data" / "podcast_transcripts" / "ai"
DEFAULT_MIN_WORDS = 300


def _slug(text: str, max_len: int = 80) -> str:
    slug = re.sub(r"[^\w\s-]", "", text).strip()
    slug = re.sub(r"[\s]+", "_", slug)
    return slug[:max_len]


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-track transcript -> research brief")
    parser.add_argument("video_id", type=str, help="YouTube video ID")
    parser.add_argument("--source-name", type=str, default="Unknown AI Channel")
    parser.add_argument("--live", action="store_true", help="Write brief files (default: dry run)")
    parser.add_argument(
        "--min-words",
        type=int,
        default=None,
        help="Skip if transcript shorter than this (default 300)",
    )
    args = parser.parse_args()

    min_words = args.min_words if args.min_words is not None else DEFAULT_MIN_WORDS

    from tasks.podcast_fetcher import (
        EXIT_TRANSCRIPT_BLOCKED,
        fetch_transcript_to_file,
        is_transcript_block,
    )
    from utils.agents.ai_research_analyst import (
        analyze_ai_research,
        brief_to_markdown,
        validate_brief,
    )

    try:
        transcript_path = fetch_transcript_to_file(
            args.video_id,
            source_name=args.source_name,
            out_dir=AI_TRANSCRIPTS_DIR,
        )
    except Exception as e:
        print(f"ERROR: Could not download transcript for {args.video_id}: {e}")
        if is_transcript_block(e):
            # Global rate-limit, not a problem with this video. Exit 3 so the batch
            # orchestrator aborts the whole walk instead of firing one more blocked
            # request per remaining channel.
            print("BLOCKED: YouTube is rate-limiting this IP. Stop and wait; do not retry.")
            sys.exit(EXIT_TRANSCRIPT_BLOCKED)
        sys.exit(1)

    full_text = transcript_path.read_text(encoding="utf-8")
    word_count = len(full_text.split())
    print(f"Transcript loaded: {word_count} words")

    if word_count < min_words:
        print(f"SKIPPED: transcript too short ({word_count} words; floor {min_words})")
        sys.exit(0)

    if word_count > 12000:
        print("WARNING: Transcript exceeds 12,000 words.")

    brief = analyze_ai_research(full_text, source_name=args.source_name)
    if brief is None:
        print("ERROR: Gemini returned no result")
        sys.exit(1)

    violations = validate_brief(brief)
    if violations:
        print("VALIDATION FAILED:")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)

    print(json.dumps(brief, indent=2))

    # Empty commentary brief — correct answer, do not write
    if not brief.get("claims") and brief.get("novelty") == "commentary" and brief.get("source_quality") == "Low":
        print("\nEmpty commentary brief — nothing to write.")
        sys.exit(0)

    if not args.live:
        print("\n--- DRY RUN COMPLETE --- No files written. Use --live to write.")
        sys.exit(0)

    transcript_sha = hashlib.sha256(transcript_path.read_bytes()).hexdigest()
    date_str = datetime.now().strftime("%Y-%m-%d")
    channel_part = args.source_name.split(":")[0].strip()
    title_part = args.source_name.split(":", 1)[1].strip() if ":" in args.source_name else args.video_id
    base = f"{date_str}_{_slug(channel_part)}_{_slug(title_part)}_{args.video_id}"

    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = BRIEFS_DIR / f"{base}.md"
    json_path = BRIEFS_DIR / f"{base}.json"

    md_path.write_text(
        brief_to_markdown(
            brief,
            source_name=args.source_name,
            video_id=args.video_id,
            transcript_sha256=transcript_sha,
        ),
        encoding="utf-8",
    )
    json_path.write_text(
        json.dumps({**brief, "channel": channel_part, "video_id": args.video_id}, indent=2),
        encoding="utf-8",
    )
    print(f"SUCCESS: Wrote {md_path.name} and {json_path.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
