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
    parser.add_argument(
        "--min-words",
        type=int,
        default=None,
        help="Skip if transcript shorter than this (optional; finance path has no default floor)",
    )
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
            transcript_segments = list(YouTubeTranscriptApi().fetch(args.video_id))
            full_text = " ".join([seg.text for seg in transcript_segments])
        except Exception as e:
            print(f"ERROR: Could not download transcript for {args.video_id}: {e}")
            from tasks.podcast_fetcher import EXIT_TRANSCRIPT_BLOCKED, is_transcript_block

            if is_transcript_block(e):
                print("BLOCKED: YouTube is rate-limiting this IP. Stop and wait; do not retry.")
                sys.exit(EXIT_TRANSCRIPT_BLOCKED)
            sys.exit(1)

        word_count = len(full_text.split())
        print(f"Transcript loaded: {word_count} words")
        if args.min_words is not None and word_count < args.min_words:
            print(f"SKIPPED: transcript too short ({word_count} words; floor {args.min_words})")
            sys.exit(0)
        if word_count > 12000:
            print("WARNING: Transcript exceeds 12,000 words. Gemini can handle it but results may "
                  "lose focus on earlier segments.")

        # --- Save raw transcript so idea_generator can find it ---
        try:
            from pathlib import Path
            import re
            TRANSCRIPTS_DIR = Path(__file__).parent.parent / "data" / "podcast_transcripts"
            TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            slug = re.sub(r"[^\w\s-]", "", source_name).strip()
            slug = re.sub(r"[\s]+", "_", slug)[:80]
            transcript_path = TRANSCRIPTS_DIR / f"{date_str}_{slug}_{args.video_id}.txt"
            transcript_path.write_text(full_text, encoding="utf-8")
            print(f"Transcript saved: {transcript_path.name}")
        except Exception as e:
            print(f"WARNING: Could not save transcript to disk: {e}")

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

    # Remove any existing rows for this source (by matching Source column = col index 1)
    # then append the new rows — preserves other sources on the same date
    existing = ws.get_all_values()
    header = existing[0] if existing else []
    other_rows = [r for r in existing[1:] if len(r) > 1 and r[1] != source_name]

    # Build new rows for this source
    today = datetime.now().strftime("%Y-%m-%d")
    new_rows = []
    for sector in targets:
        asset_class    = str(sector.get("asset_class", "Other"))
        asset_strategy = str(sector.get("asset_strategy", "N/A"))
        target_pct     = float(sector.get("target_pct", 0.0))
        min_pct        = float(sector.get("min_pct", target_pct - 5.0))
        max_pct        = float(sector.get("max_pct", target_pct + 5.0))
        confidence     = str(sector.get("confidence", "Medium"))
        notes          = str(sector.get("notes", ""))
        fingerprint    = f"{today}|{source_name}|{asset_class}"
        new_rows.append([
            today, source_name, asset_class, asset_strategy,
            target_pct, min_pct, max_pct, confidence,
            notes, str(exec_summary), fingerprint,
        ])

    # Write header + all rows (other sources preserved + this source updated).
    # Archive prior body first; then overwrite with a single update — never
    # batch_clear first (a failed update after clear permanently empties the tab).
    all_rows = [header] + other_rows + new_rows if header else (
        [["Date", "Source", "Asset Class", "Strategy", "Target %", "Min %",
          "Max %", "Confidence", "Notes", "Summary", "Fingerprint"]]
        + other_rows + new_rows
    )
    if not header:
        header = all_rows[0]

    run_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        existing_tabs = {w.title for w in spreadsheet.worksheets()}
        if existing and len(existing) > 1:
            arc_name = config.TAB_AGENT_OUTPUTS_ARCHIVE
            if arc_name not in existing_tabs:
                ws_arc = spreadsheet.add_worksheet(
                    title=arc_name, rows=10000, cols=max(len(header) + 2, 12)
                )
                time.sleep(0.5)
                ws_arc.update(
                    range_name="A1",
                    values=[["archived_at", "tab"] + list(header)],
                    value_input_option="USER_ENTERED",
                )
                time.sleep(0.5)
            else:
                ws_arc = spreadsheet.worksheet(arc_name)
            archive_rows = [
                [run_ts, config.TAB_AI_SUGGESTED_ALLOCATION] + list(row)
                for row in existing[1:]
            ]
            if archive_rows:
                ws_arc.append_rows(archive_rows, value_input_option="USER_ENTERED")
                time.sleep(0.5)
                print(f"Archived {len(archive_rows)} prior row(s) to {arc_name}.")
    except Exception as e:
        print(f"WARNING: archive before overwrite failed: {e}")
        raise

    # Single-shot overwrite — no preceding clear. On failure the prior grid remains.
    ws.update(range_name="A1", values=all_rows, value_input_option="USER_ENTERED")
    time.sleep(1.0)

    print(f"SUCCESS: Wrote {len(new_rows)} rows for '{source_name}' "
          f"({len(other_rows)} rows from other sources preserved)")

    # --- Write markdown summary file ---
    try:
        from utils.podcast_digest import write_summaries_from_sheet, purge_old_summaries
        purge_old_summaries()
        written = write_summaries_from_sheet()
        for p in written:
            print(f"  Summary written: {p}")
    except Exception as e:
        print(f"WARNING: Could not write podcast summaries: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
