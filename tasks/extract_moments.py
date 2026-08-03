"""
tasks/extract_moments.py — cached high-signal moment extraction.

Purpose : Windows + Gemini-extracts high-signal moments (reversal,
          non_consensus, position_disclosure, specific_claim, disagreement)
          out of podcast transcripts, once per transcript, cached to disk.
          Deliberately position-independent -- see the architecture note
          in utils/agents/moment_extractor.py. Relevance tagging (HELD /
          THESIS_ON_FILE / ADJACENT / ZERO_EXPOSURE) is position-dependent
          and happens later, at export_ai_briefing.py read time, never
          here and never persisted to the cache.
Inputs  : data/podcast_transcripts/*.txt, data/moment_cues.json,
          data/ticker_aliases.json.
Outputs : data/moments/{transcript_stem}.moments.json -- {"schema_version":
          2, "moments": [...]}. Written even when moments is empty, so a
          transcript with zero surviving candidates is not reprocessed.
          A cache file lacking schema_version (or predating it -- the v1
          bare-list format) is treated as stale and re-extracted.
          logs/moment_extraction_runs.jsonl -- one line per run: aggregated
          windows_found / windows_sent / candidates_returned /
          dropped_by_reason across every transcript processed that run
          (Fix 0c instrumentation, prompts/moment_extraction_v2_fix_2026-08-02.md).
Depends : utils/moment_windows.py, utils/agents/moment_extractor.py,
          utils/gemini_client.py (SAFETY_PREAMBLE auto-prepended there).
Usage   : python tasks/extract_moments.py [--force NAME] [--limit N] [--only A,B,C]
          python manager.py extract-moments [--force NAME] [--limit N]
"""

import argparse
import glob
import json
import logging
import os
import sys
from datetime import datetime, timezone

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from utils.moment_windows import load_cues
from utils.agents.moment_extractor import (
    CURRENT_SCHEMA_VERSION,
    extract_moments_for_transcript,
    write_moments_cache,
    cache_path_for_transcript,
    read_cache_schema_version,
)

logger = logging.getLogger(__name__)

TRANSCRIPTS_DIR = os.path.join("data", "podcast_transcripts")
RUN_LOG_PATH = os.path.join("logs", "moment_extraction_runs.jsonl")


def _cache_is_current(cache_path: str) -> bool:
    return read_cache_schema_version(cache_path) == CURRENT_SCHEMA_VERSION


def _empty_stats() -> dict:
    return {
        "windows_found": 0,
        "windows_sent": 0,
        "candidates_returned": 0,
        "dropped_by_reason": {"model_failed": 0, "empty_fragment": 0, "verbatim_fail": 0},
    }


def _add_stats(total: dict, stats: dict) -> None:
    total["windows_found"] += stats["windows_found"]
    total["windows_sent"] += stats["windows_sent"]
    total["candidates_returned"] += stats["candidates_returned"]
    for reason, n in stats["dropped_by_reason"].items():
        total["dropped_by_reason"][reason] = total["dropped_by_reason"].get(reason, 0) + n


def _resolve_transcript_path(name: str) -> str:
    if name.endswith(".txt"):
        return os.path.join(TRANSCRIPTS_DIR, name)
    return os.path.join(TRANSCRIPTS_DIR, name + ".txt")


def run_extract_moments(
    force: str | None = None,
    limit: int | None = None,
    only: list[str] | None = None,
) -> dict:
    """Process transcripts, writing cache files.

    Default (only=None): walks the full corpus in filename order, skipping
    any transcript whose cache is already schema_version-current, unless it
    matches `force`. `limit` bounds total attempts (successes + failures),
    not just successes.

    only: an explicit list of transcript filenames/stems to (re-)extract,
    bypassing the staleness scan and the full-corpus walk entirely. This is
    the safe way to re-extract a hand-picked sample -- it can never fall
    through into processing the rest of the corpus.

    Returns a summary dict including aggregated Fix 0c instrumentation
    (windows_found / windows_sent / candidates_returned / dropped_by_reason
    across every transcript processed this run), which is also appended to
    logs/moment_extraction_runs.jsonl.
    """
    cues = load_cues()
    force_stem = os.path.splitext(os.path.basename(force))[0] if force else None

    if only is not None:
        transcript_paths = [_resolve_transcript_path(name) for name in only]
    else:
        transcript_paths = sorted(glob.glob(os.path.join(TRANSCRIPTS_DIR, "*.txt")))

    processed, skipped, failed = [], [], []
    total_candidates = 0
    total_stats = _empty_stats()
    per_transcript = {}

    for path in transcript_paths:
        filename = os.path.basename(path)
        stem = os.path.splitext(filename)[0]
        cache_path = cache_path_for_transcript(filename)

        force_this = only is not None or (force_stem is not None and stem == force_stem)
        if not force_this and _cache_is_current(cache_path):
            skipped.append(filename)
            continue

        if only is None and limit is not None and len(processed) + len(failed) >= limit:
            break

        try:
            candidates, stats = extract_moments_for_transcript(path, cues)
            write_moments_cache(filename, candidates)
            total_candidates += len(candidates)
            _add_stats(total_stats, stats)
            per_transcript[filename] = stats
            processed.append(filename)
            logger.info("extract_moments: %s -> %d candidate(s) (%d windows)",
                        filename, len(candidates), stats["windows_found"])
        except Exception as e:
            # Non-fatal by design: one bad transcript (Gemini outage, a
            # malformed transcript, whatever) must not break manager.py
            # morning's STEP 4c or the rest of the backfill.
            logger.error("extract_moments: FAILED on %s: %s", filename, e)
            failed.append(filename)
            continue

    result = {
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "total_candidates": total_candidates,
        "stats": total_stats,
        "per_transcript": per_transcript,
    }

    if processed:
        _append_run_log(result)

    return result


def _append_run_log(result: dict) -> None:
    os.makedirs(os.path.dirname(RUN_LOG_PATH), exist_ok=True)
    entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "schema_version": CURRENT_SCHEMA_VERSION,
        "processed_count": len(result["processed"]),
        "failed_count": len(result["failed"]),
        "total_candidates": result["total_candidates"],
        "stats": result["stats"],
    }
    with open(RUN_LOG_PATH, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Cached high-signal moment extraction.")
    parser.add_argument("--force", type=str, default=None,
                         help="Transcript filename or stem to force re-extraction of "
                              "(ignores existing cache) -- for cue-list tuning.")
    parser.add_argument("--limit", type=int, default=None,
                         help="Max number of NEW transcripts to process this run "
                              "(throttle for the initial backfill).")
    parser.add_argument("--only", type=str, default=None,
                         help="Comma-separated transcript filenames/stems to "
                              "(re-)extract, bypassing the full-corpus scan.")
    args = parser.parse_args()

    only = [name.strip() for name in args.only.split(",")] if args.only else None
    result = run_extract_moments(force=args.force, limit=args.limit, only=only)

    print(
        "Processed: %d, Skipped (current cache): %d, Failed: %d, Candidates written: %d"
        % (len(result["processed"]), len(result["skipped"]), len(result["failed"]),
           result["total_candidates"])
    )
    stats = result["stats"]
    print(
        "windows_found=%d windows_sent=%d candidates_returned=%d dropped_by_reason=%s"
        % (stats["windows_found"], stats["windows_sent"], stats["candidates_returned"],
           stats["dropped_by_reason"])
    )
    if result["processed"]:
        print("Processed: %s" % ", ".join(result["processed"]))
    if result["failed"]:
        print("Failed: %s" % ", ".join(result["failed"]))


if __name__ == "__main__":
    main()
