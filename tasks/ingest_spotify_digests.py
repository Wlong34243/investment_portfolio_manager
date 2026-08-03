"""
Spotify Studio Digest Ingestion — STEP 4b.

Purpose:
  Ingest the daily third-party "Allocation" digest written by Studio by
  Spotify Labs into the same podcast-summary corpus used by the AI briefing
  export. The digest is an already-synthesized weekly aggregate, not a raw
  transcript — see prompts/spotify_digest_ingestion_2026-08-01.md for the
  full design rationale (do not re-summarize; Gemini's only job is the
  Sector Allocations table + title + cited-episode extraction).

Inputs:
  - config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR/allocation-YYYY-MM-DD.txt
    (local Studio app output; may not exist on every machine)
  - data/podcast_summaries/*.md (to detect pre-existing hand-ingested files)

Outputs:
  - data/spotify_digests/allocation-YYYY-MM-DD.txt (corpus copy of the raw source)
  - data/spotify_digests/.ingested.json (sha256 ledger, dedup + Guard 2 record)
  - data/podcast_summaries/<date>_Spotify_Podcast_Aggregate_<Slug>.md
  - data/podcast_summaries/archive/ (archive-before-overwrite copies)

Dependencies:
  - utils.agents.podcast_analyst.analyze_podcast (Gemini call; aggregate branch)

Usage:
    python tasks/ingest_spotify_digests.py                    # dry run, default window
    python tasks/ingest_spotify_digests.py --days 7 --live
    python tasks/ingest_spotify_digests.py --seed-ledger --live
"""

import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from rich.console import Console

import config
from utils.agents.podcast_analyst import analyze_podcast

console = Console()

FILENAME_RE = re.compile(r"^allocation-(\d{4}-\d{2}-\d{2})\.txt$")
VERIFICATION_PENDING_MARKER = "VERIFICATION: PENDING"

CORPUS_DIR = _ROOT / "data" / "spotify_digests"
LEDGER_PATH = CORPUS_DIR / ".ingested.json"
SUMMARIES_DIR = _ROOT / "data" / "podcast_summaries"
ARCHIVE_DIR = SUMMARIES_DIR / "archive"


# ---------------------------------------------------------------------------
# Ledger helpers
# ---------------------------------------------------------------------------

def _load_ledger() -> dict:
    if not LEDGER_PATH.exists():
        return {}
    try:
        with open(LEDGER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        console.print(f"[yellow]! Ledger unreadable ({e}) -- treating as empty[/]")
        return {}


def _save_ledger(ledger: dict) -> None:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LEDGER_PATH, "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _existing_summary_for_date(date_str: str) -> Path | None:
    matches = sorted(SUMMARIES_DIR.glob(f"{date_str}_Spotify_Podcast_Aggregate_*.md"))
    return matches[0] if matches else None


def _archive_existing(path: Path) -> Path:
    """Copy path into archive/ with a timestamp suffix. Caller decides whether
    to remove the original afterward."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = ARCHIVE_DIR / f"{path.stem}_{ts}{path.suffix}"
    shutil.copy2(path, dest)
    return dest


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned[:60].rstrip("_") or "Untitled"


def _title_from_first_sentence(body: str) -> str:
    stripped = body.strip()
    first_line = stripped.splitlines()[0] if stripped else ""
    m = re.match(r"(.+?[.!?])(\s|$)", first_line)
    sentence = m.group(1) if m else first_line
    words = sentence.split()
    return " ".join(words[:10]).rstrip(".,;:") or "Spotify Podcast Aggregate"


def _fmt_pct(value) -> str:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{f:.0f}%" if f == int(f) else f"{f:.1f}%"


def _fmt_range(min_pct, max_pct) -> str:
    def _num(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return str(v)
        return f"{f:.0f}" if f == int(f) else f"{f:.1f}"
    return f"{_num(min_pct)}-{_num(max_pct)}%"


def _reflow(body: str) -> str:
    """Light reflow only -- this is the source's own prose, not a summary of it.
    Normalizes line endings and collapses runs of 3+ blank lines."""
    text = body.replace("\r\n", "\n").strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def _render_summary(date_str, title, body, target_allocations, cited_sources, sha256) -> str:
    lines = [
        f"# Spotify Financial Podcast Aggregate: {title}",
        f"**Date:** {date_str}",
        "",
        "## Executive Summary",
        _reflow(body),
        "",
        "## Sector Allocations",
        "| Asset Class | Strategy | Target % | Range | Confidence | Notes |",
        "|-------------|----------|----------|-------|------------|-------|",
    ]
    for row in target_allocations:
        lines.append(
            "| {asset_class} | {strategy} | {target} | {range_} | {confidence} | {notes} |".format(
                asset_class=row.get("asset_class", ""),
                strategy=row.get("asset_strategy", ""),
                target=_fmt_pct(row.get("target_pct")),
                range_=_fmt_range(row.get("min_pct"), row.get("max_pct")),
                confidence=row.get("confidence", ""),
                notes=row.get("notes", ""),
            )
        )
    lines.append("")

    lines.append("## Cited Episodes")
    if cited_sources:
        for src in cited_sources:
            lines.append(f"- {src}")
    else:
        lines.append("*(none named in this digest)*")
    lines.append("")

    lines.append("---")
    lines.append(
        "*PROVENANCE: This is a third-party Spotify podcast-aggregate digest, ingested as its own\n"
        "source in its own voice. It is NOT a transcript of a single episode and was NOT produced\n"
        "by the YouTube fetcher. Allocation percentages are inferred from the aggregate's stated\n"
        "emphasis, not figures it published. Ingested automatically from Spotify Studio artifacts;\n"
        f"source_sha256: {sha256}.*"
    )
    lines.append("")
    lines.append(
        "*VERIFICATION: PENDING (manual). This digest has not been fact-checked. Treat every\n"
        "specific figure as unconfirmed until a verification pass replaces this line.*"
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Seed-ledger backfill (Guard 1)
# ---------------------------------------------------------------------------

def seed_ledger(live: bool = False) -> dict:
    """Backfill the ledger for allocation-*.txt files that already have a
    hand-ingested summary on disk, so the first normal ingestion run does not
    regenerate and overwrite them. Generates no summary files."""
    result = {"seeded": [], "skipped_no_match": [], "warn": None}

    studio_dir = Path(config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR)
    try:
        if not studio_dir.is_dir():
            result["warn"] = f"Spotify Studio folder not found: {studio_dir}"
            return result
        source_files = sorted(studio_dir.glob("allocation-*.txt"))
    except OSError as e:
        result["warn"] = f"Spotify Studio folder unreadable: {e}"
        return result

    ledger = _load_ledger()

    for src_path in source_files:
        m = FILENAME_RE.match(src_path.name)
        if not m:
            continue
        date_str = m.group(1)

        existing = _existing_summary_for_date(date_str)
        if existing is None:
            result["skipped_no_match"].append(date_str)
            continue

        try:
            sha256 = hashlib.sha256(src_path.read_bytes()).hexdigest()
        except OSError as e:
            console.print(f"[red]! Could not read {src_path.name}: {e}[/]")
            continue

        if live:
            ledger[sha256] = {
                "filename": src_path.name,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
                "output_path": str(existing),
                "source": "manual",
            }
        result["seeded"].append({"date": date_str, "output_path": str(existing)})

    if live:
        _save_ledger(ledger)

    mode = "LIVE" if live else "DRY RUN"
    console.print(f"[bold cyan]Seed Ledger -- {mode}[/]")
    for entry in result["seeded"]:
        console.print(f"  [green]seed[/] {entry['date']} -> {entry['output_path']}")
    for date_str in result["skipped_no_match"]:
        console.print(f"  [dim]no matching summary for {date_str} -- not seeded[/]")
    if not live and result["seeded"]:
        console.print("[yellow]DRY RUN -- ledger not written. Use --live to persist.[/]")

    return result


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------

def main(days: int = None, live: bool = False) -> dict:
    if days is None:
        days = config.SPOTIFY_DIGEST_WINDOW_DAYS

    result = {"ingested": [], "skipped": [], "failed": [], "warn": None}

    studio_dir = Path(config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR)
    try:
        if not studio_dir.is_dir():
            result["warn"] = f"Spotify Studio folder not found: {studio_dir}"
            console.print(f"[yellow]! {result['warn']} -- skipping Spotify digest ingestion[/]")
            return result
        source_files = sorted(studio_dir.glob("allocation-*.txt"))
    except OSError as e:
        result["warn"] = f"Spotify Studio folder unreadable: {e}"
        console.print(f"[yellow]! {result['warn']}[/]")
        return result

    ledger = _load_ledger()
    today = datetime.now().date()
    mode = "LIVE" if live else "DRY RUN"
    console.print(f"[bold cyan]Spotify Digest Ingestion -- {mode}[/]")

    for src_path in source_files:
        m = FILENAME_RE.match(src_path.name)
        if not m:
            continue  # non-matching name -- skip rather than guess
        date_str = m.group(1)
        file_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        age_days = (today - file_date).days
        if abs(age_days) > days:
            continue

        try:
            raw_bytes = src_path.read_bytes()
        except OSError as e:
            result["failed"].append({"date": date_str, "error": f"read failed: {e}"})
            console.print(f"  [red]FAILED[/] {src_path.name}: read failed: {e}")
            continue

        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        if sha256 in ledger:
            result["skipped"].append({"date": date_str, "reason": "already in ledger"})
            console.print(f"  [dim]skip[/] {src_path.name} -- already in ledger")
            continue

        body = raw_bytes.decode("utf-8", errors="replace")
        word_count = len(body.split())
        if word_count < config.SPOTIFY_DIGEST_MIN_WORDS:
            reason = f"{word_count} words, below minimum {config.SPOTIFY_DIGEST_MIN_WORDS} -- treated as truncated"
            result["skipped"].append({"date": date_str, "reason": reason})
            console.print(f"  [yellow]skip[/] {src_path.name} -- {reason}")
            continue

        # Guard 2: never overwrite a hand-verified file, independent of the ledger.
        existing = _existing_summary_for_date(date_str)
        if existing is not None:
            try:
                existing_text = existing.read_text(encoding="utf-8", errors="replace")
            except OSError:
                existing_text = ""
            if VERIFICATION_PENDING_MARKER not in existing_text:
                reason = f"{existing.name} is hand-verified -- not overwritten"
                result["skipped"].append({"date": date_str, "reason": reason})
                console.print(f"  [yellow]skip[/] {reason}")
                if live:
                    ledger[sha256] = {
                        "filename": src_path.name,
                        "ingested_at": datetime.now(timezone.utc).isoformat(),
                        "output_path": str(existing),
                        "source": "guard2_protected",
                    }
                continue

        if not live:
            result["ingested"].append({"date": date_str, "path": None, "title": None})
            console.print(f"  [green]would ingest[/] {src_path.name} ({word_count} words)")
            continue

        try:
            CORPUS_DIR.mkdir(parents=True, exist_ok=True)
            (CORPUS_DIR / src_path.name).write_bytes(raw_bytes)
        except OSError as e:
            result["failed"].append({"date": date_str, "error": f"corpus copy failed: {e}"})
            console.print(f"  [red]FAILED[/] {src_path.name}: corpus copy failed: {e}")
            continue

        source_name = f"{config.SPOTIFY_DIGEST_SOURCE_LABEL}: {date_str}"
        try:
            analysis = analyze_podcast(body, source_name=source_name)
        except Exception as e:
            result["failed"].append({"date": date_str, "error": f"analyze_podcast raised: {e}"})
            console.print(f"  [red]FAILED[/] {src_path.name}: analyze_podcast raised: {e}")
            continue

        if analysis is None:
            result["failed"].append({"date": date_str, "error": "analyze_podcast returned None"})
            console.print(f"  [red]FAILED[/] {src_path.name}: Gemini analysis returned None")
            continue

        title = analysis.get("suggested_title") or _title_from_first_sentence(body)
        slug = _slugify(title)
        target_path = SUMMARIES_DIR / f"{date_str}_Spotify_Podcast_Aggregate_{slug}.md"

        if existing is not None:
            _archive_existing(existing)
            if existing != target_path:
                existing.unlink()
        elif target_path.exists():
            _archive_existing(target_path)

        markdown = _render_summary(
            date_str=date_str,
            title=title,
            body=body,
            target_allocations=analysis.get("target_allocations", []),
            cited_sources=analysis.get("cited_sources", []),
            sha256=sha256,
        )

        try:
            SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
            target_path.write_text(markdown, encoding="utf-8")
        except OSError as e:
            result["failed"].append({"date": date_str, "error": f"write failed: {e}"})
            console.print(f"  [red]FAILED[/] {src_path.name}: write failed: {e}")
            continue

        ledger[sha256] = {
            "filename": src_path.name,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "output_path": str(target_path),
        }
        result["ingested"].append({"date": date_str, "path": str(target_path), "title": title})
        console.print(f"  [green]ingested[/] {src_path.name} -> {target_path.name}")

    if live:
        _save_ledger(ledger)
    elif result["ingested"]:
        console.print("[yellow]DRY RUN -- no files written, ledger not updated. Use --live to persist.[/]")

    console.print(
        f"[bold]Done:[/] {len(result['ingested'])} ingested, "
        f"{len(result['skipped'])} skipped, {len(result['failed'])} failed"
    )
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ingest Spotify Studio daily allocation digests")
    parser.add_argument("--days", type=int, default=None, help="Ingestion window in days")
    parser.add_argument("--live", action="store_true", help="Write files and ledger. Default: dry run.")
    parser.add_argument("--seed-ledger", action="store_true", help="Backfill ledger for already hand-ingested digests; generates nothing.")
    args = parser.parse_args()

    if args.seed_ledger:
        seed_ledger(live=args.live)
    else:
        main(days=args.days, live=args.live)
