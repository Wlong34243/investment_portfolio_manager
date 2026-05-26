"""
utils/agents/idea_generator.py — Podcast → Investment Candidates pipeline.

Consumes composite bundle + vault/transcripts/ and produces a weekly
markdown file of investment candidates for human review.

Read-only w.r.t. bundles. No Sheets writes. Output is local markdown only.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------

class Candidate(BaseModel):
    ticker: str
    company_name: str
    source_transcript: str
    source_speaker: Optional[str] = None
    thesis_summary: str
    style_fit: Literal["GARP", "Thematic", "BoringFundamentals", "SectorETF", "Unclear"]
    style_fit_reasoning: str
    portfolio_relationship: str
    current_holdings_overlap: list[str]
    notable_concerns: Optional[str] = None


class IdeaGeneratorOutput(BaseModel):
    bundle_hash: str
    generated_at: Optional[datetime] = None
    transcripts_analyzed: list[str]
    candidates: list[Candidate]
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Transcript loader
# ---------------------------------------------------------------------------

TRANSCRIPTS_DIR = Path(__file__).parent.parent.parent / "data" / "podcast_transcripts"


def load_transcripts(
    transcript_dir: str | None = None,
    since_days: int = 7,
) -> list[dict]:
    """
    Returns transcripts modified within since_days.
    Each dict: {filename, content, modified_at}.
    Empty list if no recent transcripts exist.
    Defaults to data/podcast_transcripts/ (where podcast_fetcher writes).
    """
    dir_path = Path(transcript_dir) if transcript_dir else TRANSCRIPTS_DIR
    if not dir_path.exists():
        logger.warning("Transcript directory not found: %s", dir_path)
        return []

    cutoff = datetime.now(timezone.utc).timestamp() - (since_days * 86400)
    results = []

    for p in sorted(dir_path.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".txt", ".md", ".text"):
            continue
        if p.stat().st_mtime >= cutoff:
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                results.append({
                    "filename": p.name,
                    "content": content,
                    "modified_at": datetime.fromtimestamp(
                        p.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                })
            except Exception as e:
                logger.warning("Could not read transcript %s: %s", p.name, e)

    return results


def _find_latest_composite(bundle_dir: Path = Path("bundles")) -> Path:
    candidates = sorted(
        bundle_dir.glob("composite_bundle_*.json"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError(f"No composite bundles found in {bundle_dir}")
    return candidates[-1]


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

def run_idea_generator(
    composite_bundle_path: Optional[str] = None,
    since_days: int = 7,
    max_tokens: int = 8000,
) -> IdeaGeneratorOutput:
    """
    End-to-end idea generator.
    1. Resolves composite bundle path (auto-detects latest if not provided).
    2. Loads transcripts within since_days window.
    3. If no transcripts, returns empty output with explanatory note.
    4. Calls ask_gemini_composite() with transcript content as user prompt.
    5. Returns validated IdeaGeneratorOutput with generated_at stamped.
    """
    from core.composite_bundle import load_composite_bundle
    from utils.gemini_client import ask_gemini_composite

    # 1. Resolve bundle path
    if composite_bundle_path is None:
        bundle_path = _find_latest_composite()
    else:
        bundle_path = Path(composite_bundle_path)

    # Verify bundle is loadable and grab composite_hash for empty-case
    composite_data = load_composite_bundle(bundle_path)
    composite_hash = composite_data["composite_hash"]

    # 2. Load transcripts
    transcripts = load_transcripts(since_days=since_days)
    transcript_filenames = [t["filename"] for t in transcripts]

    # 3. Handle empty transcript window
    if not transcripts:
        logger.info("No transcripts found in the last %d days — returning empty output.", since_days)
        return IdeaGeneratorOutput(
            bundle_hash=composite_hash,
            generated_at=datetime.now(timezone.utc),
            transcripts_analyzed=[],
            candidates=[],
            notes=f"No new transcripts found within the last {since_days} days in {TRANSCRIPTS_DIR}. Run 'pm ingest podcasts' to fetch new transcripts, then re-run this command.",
        )

    # 4. Read system prompt
    prompt_path = Path("prompts/idea_generator.md")
    if not prompt_path.exists():
        raise FileNotFoundError("prompts/idea_generator.md not found — cannot run agent.")
    system_instruction = prompt_path.read_text(encoding="utf-8")

    # 5. Build user prompt with all transcript content
    transcript_blocks = []
    for t in transcripts:
        block = f"--- TRANSCRIPT: {t['filename']} (modified: {t['modified_at']}) ---\n{t['content']}"
        transcript_blocks.append(block)

    user_prompt = (
        f"Analyze the following {len(transcripts)} podcast transcript(s) and extract actionable investment candidates "
        f"using the schema provided. Fill transcripts_analyzed with the exact filenames listed.\n\n"
        + "\n\n".join(transcript_blocks)
    )

    # 6. Call Gemini
    result = ask_gemini_composite(
        prompt=user_prompt,
        composite_bundle_path=bundle_path,
        response_schema=IdeaGeneratorOutput,
        system_instruction=system_instruction,
        max_tokens=max_tokens,
        include_vault_context=True,
    )

    if result is None:
        logger.error("ask_gemini_composite returned None — LLM call failed.")
        return IdeaGeneratorOutput(
            bundle_hash=composite_hash,
            generated_at=datetime.now(timezone.utc),
            transcripts_analyzed=transcript_filenames,
            candidates=[],
            notes="LLM call failed — check Gemini credentials and logs.",
        )

    # 7. Stamp generated_at client-side (LLM value unreliable)
    result.generated_at = datetime.now(timezone.utc)
    if not result.transcripts_analyzed:
        result.transcripts_analyzed = transcript_filenames

    return result


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _sort_key(candidate: Candidate) -> tuple[int, str]:
    """
    Sort order:
      0 — no overlap (new exposure)
      1 — overlap but relationship suggests complement
      2 — overlap / rotation
    Then alphabetical by ticker within each group.
    """
    has_overlap = bool(candidate.current_holdings_overlap)
    if not has_overlap:
        return (0, candidate.ticker)
    rel = candidate.portfolio_relationship.lower()
    if "complement" in rel:
        return (1, candidate.ticker)
    return (2, candidate.ticker)


def write_idea_report(
    output: IdeaGeneratorOutput,
    report_dir: str = "agent_outputs/ideas/",
    dry_run: bool = False,
) -> str:
    """
    Renders the IdeaGeneratorOutput as a human-readable markdown report.
    If dry_run=True, returns the rendered markdown string without writing to disk.
    Otherwise writes to report_dir and returns the file path string.
    """
    ts = output.generated_at or datetime.now(timezone.utc)
    date_str = ts.strftime("%Y-%m-%d")
    hash_prefix = output.bundle_hash[:8] if output.bundle_hash else "unknown"

    # Sort candidates
    sorted_candidates = sorted(output.candidates, key=_sort_key)

    # Build markdown
    lines = [
        f"# Idea Generator Report — {ts.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"**Bundle hash:** `{output.bundle_hash}`  ",
        f"**Transcripts analyzed:** {len(output.transcripts_analyzed)}",
    ]

    for fname in output.transcripts_analyzed:
        lines.append(f"- {fname}")

    lines += ["", "---", "", "## Candidates", ""]

    if not sorted_candidates:
        lines.append("_No actionable candidates found in the analyzed transcripts._")
        lines.append("")
    else:
        for c in sorted_candidates:
            lines.append(f"### {c.ticker} — {c.company_name}")
            lines.append("")
            speaker_str = f" — {c.source_speaker}" if c.source_speaker else ""
            lines.append(f"**Source:** {c.source_transcript}{speaker_str}  ")
            lines.append(f"**Style fit:** {c.style_fit} — {c.style_fit_reasoning}  ")
            lines.append(f"**Portfolio relationship:** {c.portfolio_relationship}")
            if c.current_holdings_overlap:
                lines.append(f"**Overlaps with:** {', '.join(c.current_holdings_overlap)}")
            lines.append("")
            lines.append(c.thesis_summary)
            lines.append("")
            if c.notable_concerns:
                lines.append(f"**Concerns:** {c.notable_concerns}")
                lines.append("")
            lines.append("---")
            lines.append("")

    lines += ["## Notes", ""]
    lines.append(output.notes if output.notes else "_No additional notes._")
    lines.append("")

    markdown = "\n".join(lines)

    if dry_run:
        return markdown

    out_dir = Path(report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"ideas_{date_str}_{hash_prefix}.md"
    file_path = out_dir / filename
    file_path.write_text(markdown, encoding="utf-8")
    return str(file_path)
