# AI Dispatch Ingestion (STEP 4d)
#
# Reads ai-dispatch-YYYY-MM-DD.txt from the Spotify Studio artifacts directory --
# the same folder STEP 4b reads for allocation-*.txt digests -- and routes them to
# the AI-track analyst, NOT the allocation summariser.
#
# Why a separate path from STEP 4b: ingest_spotify_digests treats its input as an
# already-synthesized allocation aggregate and emits a GICS sector table. An AI
# dispatch is capability research; forcing it through that path fabricates an
# allocation, which is the defect data/ai_briefs/ exists to avoid. It also arrives
# on local disk, so it needs no YouTube fetch and is unaffected by transcript-endpoint
# IP blocks.
#
# Reads:
#   - config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR/ai-dispatch-YYYY-MM-DD.txt
#   - data/ai_dispatches/.ingested.json  (sha256 ledger, dedup)
# Writes (only with --live):
#   - data/ai_dispatches/ai-dispatch-YYYY-MM-DD.txt   (corpus copy of raw source)
#   - data/ai_briefs/<date>_AI_Dispatch_<slug>.md + .json
#
# Usage:
#   python tasks/ingest_ai_dispatch.py                 # dry run
#   python tasks/ingest_ai_dispatch.py --live
#   python tasks/ingest_ai_dispatch.py --days 3 --live

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = REPO_ROOT / "data" / "ai_dispatches"
BRIEFS_DIR = REPO_ROOT / "data" / "ai_briefs"
LEDGER_PATH = CORPUS_DIR / ".ingested.json"

# Suffix tolerated so a second dispatch on one day is not silently dropped, which
# is exactly what happened to allocation-2026-08-07b.txt under STEP 4b's stricter
# regex.
FILENAME_RE = re.compile(r"^ai-dispatch-(\d{4}-\d{2}-\d{2})([a-z])?\.txt$")

SOURCE_LABEL = "AI Dispatch"
MIN_WORDS = 300


def _slug(text: str, max_len: int = 80) -> str:
    s = re.sub(r"[^\w\s-]", "", text).strip()
    return re.sub(r"\s+", "_", s)[:max_len]


def _load_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return {}
    try:
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: could not read ledger ({e}); treating as empty")
        return {}


def _save_ledger(ledger: dict) -> None:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def main(days: int = None, live: bool = False) -> dict:
    result = {"ingested": [], "skipped": [], "failed": [], "warn": False}

    studio_dir = Path(config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR)
    if not studio_dir.exists():
        print(f"Studio directory not found: {studio_dir}")
        result["warn"] = True
        return result

    window = days if days is not None else getattr(config, "SPOTIFY_DIGEST_WINDOW_DAYS", 7)
    cutoff = (datetime.now() - timedelta(days=window)).date()

    ledger = _load_ledger()
    source_files = sorted(studio_dir.glob("ai-dispatch-*.txt"))
    if not source_files:
        print(f"No ai-dispatch-*.txt in {studio_dir}")
        return result

    for src in source_files:
        m = FILENAME_RE.match(src.name)
        if not m:
            # Named like a dispatch but not parseable -- say so. A file that cannot
            # be matched must never be dropped in silence.
            print(f"SKIP (unparseable name, NOT ingested): {src.name}")
            result["failed"].append(src.name)
            result["warn"] = True
            continue

        date_str, suffix = m.group(1), m.group(2) or ""
        try:
            file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            print(f"SKIP (bad date): {src.name}")
            result["failed"].append(src.name)
            result["warn"] = True
            continue

        if file_date < cutoff:
            continue

        raw = src.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        if sha256 in ledger:
            result["skipped"].append(src.name)
            continue

        text = raw.decode("utf-8", errors="replace")
        word_count = len(text.split())
        if word_count < MIN_WORDS:
            print(f"SKIP (too short, {word_count} words): {src.name}")
            result["failed"].append(src.name)
            result["warn"] = True
            continue

        source_name = f"{SOURCE_LABEL}: {date_str}{suffix}"
        print(f"Analyzing {src.name} ({word_count} words) as '{source_name}'...")

        from utils.agents.ai_research_analyst import (
            analyze_ai_research,
            brief_to_markdown,
            validate_brief,
        )

        brief = analyze_ai_research(text, source_name=source_name)
        if brief is None:
            print(f"FAILED: analyst returned nothing for {src.name}")
            result["failed"].append(src.name)
            continue

        violations = validate_brief(brief)
        if violations:
            # Not written, not deduped -- retryable after a prompt fix.
            print(f"REJECTED {src.name} — validator violations:")
            for v in violations:
                print(f"  - {v}")
            result["failed"].append(src.name)
            continue

        if not brief.get("claims") and brief.get("novelty") == "commentary":
            print(f"Empty commentary brief for {src.name} — nothing to write.")
            result["skipped"].append(src.name)
            continue

        base = f"{date_str}_AI_Dispatch_{_slug(brief.get('headline', date_str))}"
        md = brief_to_markdown(
            brief,
            source_name=source_name,
            video_id=f"ai-dispatch-{date_str}{suffix}",
            transcript_sha256=sha256,
            source_ref=f"{src.name} (Spotify Studio artifacts)",
            source_kind="Spotify Studio AI dispatch transcript",
        )

        if not live:
            print(f"\n--- DRY RUN --- would write data/ai_briefs/{base}.md")
            print(md[:800])
            result["ingested"].append(src.name)
            continue

        CORPUS_DIR.mkdir(parents=True, exist_ok=True)
        BRIEFS_DIR.mkdir(parents=True, exist_ok=True)

        (CORPUS_DIR / src.name).write_bytes(raw)
        (BRIEFS_DIR / f"{base}.md").write_text(md, encoding="utf-8")
        (BRIEFS_DIR / f"{base}.json").write_text(
            json.dumps(
                {**brief, "channel": SOURCE_LABEL, "video_id": f"ai-dispatch-{date_str}{suffix}"},
                indent=2,
            ),
            encoding="utf-8",
        )
        ledger[sha256] = {
            "source_file": src.name,
            "date": date_str,
            "brief": f"{base}.md",
            "ingested_at": datetime.now().isoformat(),
        }
        _save_ledger(ledger)
        print(f"SUCCESS: wrote data/ai_briefs/{base}.md")
        result["ingested"].append(src.name)

    print(
        f"\n=== AI Dispatch Summary ({'LIVE' if live else 'DRY RUN'}) ===\n"
        f"  Ingested: {result['ingested'] or 'None'}\n"
        f"  Skipped (already done / empty): {result['skipped'] or 'None'}\n"
        f"  Failed: {result['failed'] or 'None'}"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Spotify Studio AI dispatch transcripts")
    parser.add_argument("--days", type=int, default=None, help="Window in days")
    parser.add_argument("--live", action="store_true", help="Write files. Default: DRY RUN.")
    args = parser.parse_args()
    r = main(days=args.days, live=args.live)
    sys.exit(1 if r["failed"] and not r["ingested"] else 0)
