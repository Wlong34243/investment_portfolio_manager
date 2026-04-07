"""
STAX Market Intelligence Ingestion — CLI Script

Parses a Schwab STAX monthly summary and extracts a structured sector
allocation recommendation using the existing podcast_analyst agent.
Writes to AI_Suggested_Allocation tab in the Portfolio Sheet.

Usage:
  # Read STAX text from a file (recommended — paste PDF text into .txt file)
  python tasks/stax_sync.py --file reports/stax_march_2026.txt --source "Schwab STAX March 2026"

  # Read from stdin (pipe or heredoc)
  cat reports/stax_march_2026.txt | python tasks/stax_sync.py --source "Schwab STAX March 2026"

  # Write to Sheet (default is dry-run)
  python tasks/stax_sync.py --file reports/stax_march_2026.txt --source "Schwab STAX March 2026" --live

Default: DRY RUN — prints extracted JSON, no Sheet writes.
Use --live to enable Sheet writes.
"""

import sys
import os
import argparse
import json
import time
from datetime import datetime, date

# Add project root to sys.path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from utils.agents.podcast_analyst import analyze_podcast

def main():
    parser = argparse.ArgumentParser(description="STAX Market Intelligence Ingestion")
    parser.add_argument("--file", type=str, default=None,
                        help="Path to a .txt file containing the STAX report text. If not provided, read from stdin.")
    parser.add_argument("--source", type=str, required=True,
                        help="Source label (e.g. 'Schwab STAX March 2026')")
    parser.add_argument("--live", action="store_true",
                        help="Enable Sheet writes. Without this flag, always runs in dry-run mode.")
    args = parser.parse_args()

    # --- Text Loading ---
    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                report_text = f.read()
        except Exception as e:
            print(f"ERROR: Could not read file {args.file}: {e}")
            sys.exit(1)
    else:
        print("Reading from stdin... (Press Ctrl+D when finished)")
        report_text = sys.stdin.read()

    word_count = len(report_text.split())
    print(f"STAX report loaded: {word_count} words")

    if word_count < 200:
        print("ERROR: Report text is too short. Paste the full STAX summary.")
        sys.exit(1)

    if word_count > 15000:
        print("WARNING: Report exceeds 15,000 words. Consider trimming to the current month section only.")

    # --- AI Analysis ---
    print(f"Sending to Gemini ({config.GEMINI_MODEL})...")
    strategy = analyze_podcast(report_text, source_name=args.source)

    if strategy is None:
        print("ERROR: Gemini returned no result. Check API key and model availability.")
        sys.exit(1)

    # Validate that target_pct values sum to 100 (±0.5 tolerance)
    total_pct = sum(s["target_pct"] for s in strategy["target_allocations"])
    if abs(total_pct - 100.0) > 0.5:
        print(f"ERROR: Allocations sum to {total_pct:.1f}%, expected 100%.")
        print("Gemini output may be malformed. Aborting.")
        sys.exit(1)

    # Always pretty-print the full strategy JSON regardless of dry-run state
    print("\n--- EXTRACTED ALLOCATION ---")
    print(json.dumps(strategy, indent=2))
    print(f"\nSectors extracted: {len(strategy['target_allocations'])}")
    print(f"Total allocation: {total_pct:.1f}%")

    # --- Dry-Run Gate ---
    if not args.live:
        print("\n--- DRY RUN COMPLETE --- No Sheet writes. Use --live to write.")
        sys.exit(0)

    print("\n--- LIVE MODE --- Writing to Sheet...")

    # --- Sheet Write (Copy EXACTLY from weekly_podcast_sync.py logic) ---
    from utils.sheet_readers import get_gspread_client

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
            "STAX_Sync",
            f"Archived {len(existing_rows)} rows before overwrite",
            f"Previous source: {prev_source}",
        ])
        time.sleep(1.0)

    # Clear data rows, preserve header
    ws.batch_clear(["A2:K1000"])
    time.sleep(1.0)

    # Build rows
    today_str = date.today().isoformat()
    executive_summary = strategy.get("executive_summary", "")
    
    rows = []
    for sector in strategy["target_allocations"]:
        fingerprint = f"{today_str}|{args.source}|{sector['asset_class']}"
        rows.append([
            today_str,
            args.source,
            str(sector["asset_class"]),
            str(sector["asset_strategy"]),
            float(sector["target_pct"]),
            float(sector["min_pct"]),
            float(sector["max_pct"]),
            str(sector["confidence"]),
            str(sector["notes"]),
            str(executive_summary),
            fingerprint,
        ])

    # Batch write (use update instead of append_rows to match clear-and-replace pattern)
    ws.update(f"A2:K{1 + len(rows)}", rows, value_input_option="USER_ENTERED")
    time.sleep(1.0)

    # Log the write
    ws_logs = spreadsheet.worksheet(config.TAB_LOGS)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws_logs.append_row([
        timestamp,
        "INFO",
        "STAX_Sync",
        f"Wrote {len(rows)} rows to AI_Suggested_Allocation",
        f"Source: {args.source}"
    ])

    print(f"SUCCESS: {len(rows)} sectors written to AI_Suggested_Allocation.")

if __name__ == "__main__":
    main()
