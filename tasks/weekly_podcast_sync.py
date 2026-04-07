# Podcast Automation Pipeline — Orchestrator
#
# Usage:
#   python tasks/weekly_podcast_sync.py VIDEO_ID --source-name "Forward Guidance EP 412"
#   python tasks/weekly_podcast_sync.py VIDEO_ID --source-name "The Compound" --live
#
# Default: DRY RUN (prints JSON, no Sheet writes)
# Use --live to enable Sheet writes.

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import argparse
import json
import time
import traceback
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(
        description="Podcast Automation Pipeline -- YouTube transcript -> Gemini -> AI_Suggested_Allocation"
    )
    parser.add_argument("video_id", type=str, nargs="?", help="YouTube video ID")
    parser.add_argument("--import-json", type=str, help="Path to pre-analyzed strategy JSON file (overrides AI step)")
    parser.add_argument("--source-name", type=str, default="Unknown Podcast",
                        help="Podcast name + episode identifier (e.g. 'Forward Guidance EP 412')")
    parser.add_argument("--live", action="store_true",
                        help="Enable Sheet writes. Without this flag, always runs in dry-run mode.")
    args = parser.parse_args()

    strategy = None
    source_name = args.source_name

    # --- Strategy Source (JSON or AI) ---
    if args.import_json:
        print(f"Loading strategy from {args.import_json}...")
        try:
            with open(args.import_json, "r") as f:
                strategy = json.load(f)
            if source_name == "Unknown Podcast":
                source_name = os.path.basename(args.import_json)
        except Exception as e:
            print(f"ERROR: Could not load JSON file {args.import_json}: {e}")
            sys.exit(1)
    elif args.video_id:
        # --- Transcript download ---
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError:
            print("ERROR: youtube-transcript-api not installed. Run: pip install youtube-transcript-api")
            sys.exit(1)

        try:
            transcript_segments = YouTubeTranscriptApi.get_transcript(args.video_id)
            full_text = " ".join([seg["text"] for seg in transcript_segments])
        except Exception as e:
            print(f"ERROR: Could not download transcript for {args.video_id}: {e}")
            sys.exit(1)

        word_count = len(full_text.split())
        print(f"Transcript loaded: {word_count} words")
        if word_count > 12000:
            print("WARNING: Transcript exceeds 12,000 words. Gemini can handle it but results may "
                  "lose focus on earlier segments.")

        # --- AI analysis ---
        from utils.agents.podcast_analyst import analyze_podcast

        strategy = analyze_podcast(full_text, source_name=source_name)
        if strategy is None:
            print("ERROR: Gemini returned no result")
            sys.exit(1)
    else:
        print("ERROR: Either video_id or --import-json must be provided.")
        parser.print_help()
        sys.exit(1)

    # --- Data Resolution & Validation ---
    # Handle schema variations (e.g. 'target_allocations' vs 'allocations')
    targets = strategy.get("target_allocations") or strategy.get("allocations")
    if not targets or not isinstance(targets, list):
        print("ERROR: JSON file must contain a list of 'target_allocations' or 'allocations'.")
        sys.exit(1)

    # Resolve executive summary
    exec_summary = strategy.get("executive_summary")
    if not exec_summary and "metadata" in strategy:
        exec_summary = strategy["metadata"].get("executive_summary")
    
    if not exec_summary:
        exec_summary = "Strategy imported from JSON."

    # Validate allocation sum
    try:
        total = sum(float(s.get("target_pct", 0)) for s in targets)
    except (ValueError, TypeError):
        print("ERROR: 'target_pct' values must be numeric.")
        sys.exit(1)

    if abs(total - 100.0) > 0.5:
        print(f"ERROR: Allocations sum to {total}%, expected 100%")
        sys.exit(1)

    # Always print full strategy JSON
    print(json.dumps(strategy, indent=2))

    # --- Dry-run gate ---
    if not args.live:
        print("\n--- DRY RUN COMPLETE --- No Sheet writes. Use --live to write.")
        sys.exit(0)

    print("\n--- LIVE MODE --- Writing to Sheet...")

    # --- Sheet write ---
    from utils.sheet_readers import get_gspread_client
    import config

    client = get_gspread_client()
    spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = spreadsheet.worksheet(config.TAB_AI_SUGGESTED_ALLOCATION)

    # Archive existing rows to Logs tab before overwrite
    existing_rows = ws.get_all_values()[1:]
    if existing_rows:
        ws_logs = spreadsheet.worksheet(config.TAB_LOGS)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prev_source = existing_rows[0][1] if existing_rows else "N/A"
        ws_logs.append_row([
            timestamp,
            "INFO",
            "Podcast_Sync",
            f"Archived {len(existing_rows)} rows before overwrite",
            f"Previous source: {prev_source}",
        ])
        time.sleep(1.0)

    # Clear data rows, preserve header
    ws.batch_clear(["A2:K1000"])
    time.sleep(1.0)

    # Build rows
    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for sector in targets:
        # Use .get() with defaults for missing fields
        asset_class = str(sector.get("asset_class", "Other"))
        asset_strategy = str(sector.get("asset_strategy", "N/A"))
        target_pct = float(sector.get("target_pct", 0.0))
        min_pct = float(sector.get("min_pct", target_pct - 5.0))
        max_pct = float(sector.get("max_pct", target_pct + 5.0))
        confidence = str(sector.get("confidence", "Medium"))
        notes = str(sector.get("notes", ""))

        fingerprint = f"{today}|{source_name}|{asset_class}"
        rows.append([
            today,
            source_name,
            asset_class,
            asset_strategy,
            target_pct,
            min_pct,
            max_pct,
            confidence,
            notes,
            str(exec_summary),
            fingerprint,
        ])

    # Batch write
    ws.update(f"A2:K{1 + len(rows)}", rows, value_input_option="USER_ENTERED")
    time.sleep(1.0)

    print(f"SUCCESS: Wrote {len(rows)} allocation rows to AI_Suggested_Allocation")



if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
