"""
podcast_digest.py — Reads AI_Suggested_Allocation from Sheets and writes
per-source markdown summaries to data/podcast_summaries/.

Summaries older than KEEP_DAYS are purged automatically.
The load_digest() function returns a single string ready to paste into
any Gemini prompt for portfolio-aware buy/sell analysis.
"""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

SUMMARIES_DIR = Path(__file__).parent.parent / "data" / "podcast_summaries"
KEEP_DAYS = 7

def _safe_filename(source: str) -> str:
    """Slugify a source name for use as a filename."""
    slug = re.sub(r"[^\w\s-]", "", source).strip()
    slug = re.sub(r"[\s]+", "_", slug)
    return slug[:80]


def write_summaries_from_sheet() -> list[str]:
    """
    Reads AI_Suggested_Allocation, groups rows by source, writes one .md
    file per source into data/podcast_summaries/.  Returns list of written paths.
    """
    from utils.sheet_readers import get_gspread_client
    import config

    client = get_gspread_client()
    spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    ws = spreadsheet.worksheet(config.TAB_AI_SUGGESTED_ALLOCATION)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return []

    headers = rows[0]
    data = [dict(zip(headers, r)) for r in rows[1:]]

    # Group by Source
    sources: dict[str, list[dict]] = {}
    for row in data:
        src = row.get("Source", "Unknown")
        sources.setdefault(src, []).append(row)

    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    written = []

    for source, allocations in sources.items():
        date_str = allocations[0].get("Date", datetime.now().strftime("%Y-%m-%d"))
        exec_summary = allocations[0].get("Executive Summary", "")
        quality = allocations[0].get("Confidence", "")

        # Build markdown
        lines = [
            f"# {source}",
            f"**Date:** {date_str}",
            f"",
            f"## Executive Summary",
            f"{exec_summary}",
            f"",
            f"## Sector Allocations",
            f"| Asset Class | Strategy | Target % | Range | Confidence | Notes |",
            f"|-------------|----------|----------|-------|------------|-------|",
        ]
        for a in allocations:
            lines.append(
                f"| {a.get('Asset Class','')} "
                f"| {a.get('Asset Strategy','')} "
                f"| {a.get('Target %','')}% "
                f"| {a.get('Min %','')}–{a.get('Max %','')}% "
                f"| {a.get('Confidence','')} "
                f"| {a.get('Notes','')} |"
            )

        # Thesis screener prompts aren't stored in sheet — note that
        lines += [
            f"",
            f"---",
            f"*Source quality derived from Gemini analysis of transcript.*",
        ]

        filename = f"{date_str}_{_safe_filename(source)}.md"
        path = SUMMARIES_DIR / filename
        path.write_text("\n".join(lines), encoding="utf-8")
        written.append(str(path))

    return written


def purge_old_summaries():
    """Delete summary files older than KEEP_DAYS."""
    cutoff = datetime.now() - timedelta(days=KEEP_DAYS)
    for f in SUMMARIES_DIR.glob("*.md"):
        try:
            date_str = f.name[:10]
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                f.unlink()
        except Exception:
            pass


def load_digest(max_files: int = 6) -> str:
    """
    Returns a single markdown string containing the most recent podcast
    summaries (up to max_files), ready to inject into a Gemini prompt.

    If no local files exist, falls back to reading from Google Sheets live.
    """
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(SUMMARIES_DIR.glob("*.md"), reverse=True)[:max_files]

    if not files:
        # No local files — pull from sheet and write them first
        write_summaries_from_sheet()
        files = sorted(SUMMARIES_DIR.glob("*.md"), reverse=True)[:max_files]

    if not files:
        return "No podcast summaries available yet."

    parts = []
    for f in files:
        parts.append(f.read_text(encoding="utf-8"))
        parts.append("\n\n---\n\n")

    return "".join(parts).strip()


def build_trade_prompt(holdings_df, digest: str = None) -> str:
    """
    Builds a Gemini prompt combining the podcast digest with the current
    portfolio holdings for buy/sell/hold recommendations.
    """
    if digest is None:
        digest = load_digest()

    # Summarise holdings (strip PII — no account numbers)
    top_holdings = holdings_df.nlargest(15, "Market Value")[
        ["Ticker", "Description", "Asset Class", "Market Value", "Weight", "Unrealized G/L %"]
    ].to_string(index=False)

    return f"""You are a portfolio strategist. Using the macro signals from recent analyst podcasts
and the investor's current holdings, generate specific, actionable buy/sell/hold recommendations.

## Recent Analyst Podcast Signals (last 7 days)

{digest}

## Current Portfolio (Top 15 by Market Value)

{top_holdings}

## Instructions

1. For each podcast signal, identify which current holdings are ALIGNED or MISALIGNED.
2. Suggest up to 5 specific BUY candidates (ticker + rationale tied to a podcast thesis).
3. Suggest up to 3 REDUCE/SELL candidates (positions that contradict the consensus signal).
4. Flag any HOLD positions where the thesis is confirmed by multiple sources.
5. Keep each recommendation to 2 sentences max. Be specific — name tickers.
6. Do NOT recommend selling everything or going to cash. Work within the existing portfolio.
"""


if __name__ == "__main__":
    print("Writing summaries from sheet...")
    paths = write_summaries_from_sheet()
    for p in paths:
        print(f"  Written: {p}")
    print("\n--- Digest Preview ---")
    print(load_digest()[:2000])
