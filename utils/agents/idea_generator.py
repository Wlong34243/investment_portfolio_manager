"""
utils/agents/idea_generator.py — Podcast → Investment Candidates pipeline.

Consumes composite bundle + vault/transcripts/ and produces a weekly
markdown file of investment candidates for human review.

Read-only w.r.t. bundles. No Sheets writes. Output is local markdown only.
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

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
    related_tickers: list[str] = Field(default_factory=list)


class MarketTheme(BaseModel):
    theme: str
    sources: list[str]
    summary: str


class IdeaGeneratorOutput(BaseModel):
    bundle_hash: str
    generated_at: Optional[datetime] = None
    transcripts_analyzed: list[str]
    candidates: list[Candidate]
    market_themes: list[MarketTheme] = []
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Transcript loader
# ---------------------------------------------------------------------------

TRANSCRIPTS_DIR = Path(__file__).parent.parent.parent / "data" / "podcast_transcripts"
SUMMARIES_DIR = Path(__file__).parent.parent.parent / "data" / "podcast_summaries"
VERIFICATION_DIR = SUMMARIES_DIR / "verification"
SHA_RE = re.compile(r"source_sha256[^\n]*?([0-9a-f]{64})", re.IGNORECASE)
DIGEST_SHA_RE = re.compile(r"source_sha256:\s*([0-9a-f]{64})", re.IGNORECASE)
VERIFIED_DATE_RE = re.compile(r"_VERIFIED_(\d{4}-\d{2}-\d{2})\.md$", re.IGNORECASE)


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


def _parse_cited_episodes(text: str) -> list[str]:
    """Lines under ## Cited Episodes until the next heading or PROVENANCE footer."""
    m = re.search(r"^## Cited Episodes\s*$", text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return []
    rest = text[m.end():]
    cited = []
    for line in rest.splitlines():
        if line.startswith("## ") or line.startswith("*PROVENANCE") or line.startswith("---"):
            if cited or line.startswith("## ") or line.startswith("*PROVENANCE"):
                break
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            cited.append(stripped[2:].strip())
    return cited


def _sidecar_verified_date(filename: str) -> str:
    m = VERIFIED_DATE_RE.search(filename)
    return m.group(1) if m else "9999-99-99"


def _load_sidecars_for_digest(digest_stem: str, digest_sha: str | None) -> dict:
    """
    Concatenate every verification/*.md whose name starts with the digest basename,
    in ascending verified-date order. SHA mismatch → skip that file (warn).
    """
    out = {"files": [], "text": None, "unverified": True}
    if not VERIFICATION_DIR.is_dir():
        return out

    matches = [
        p for p in VERIFICATION_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".md"
        and p.name.startswith(digest_stem)
        and p.parent.name != "archive"
    ]
    matches.sort(key=lambda p: (_sidecar_verified_date(p.name), p.name))

    chunks = []
    used = []
    for p in matches:
        try:
            body = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("Could not read sidecar %s: %s", p.name, e)
            continue
        sidecar_sha = None
        sm = SHA_RE.search(body)
        if sm:
            sidecar_sha = sm.group(1)
        if digest_sha and sidecar_sha and sidecar_sha != digest_sha:
            logger.warning(
                "Sidecar %s sha %s does not match digest sha %s — not pairing.",
                p.name, sidecar_sha, digest_sha,
            )
            continue
        chunks.append(f"--- SIDECAR FILE: {p.name} ---\n{body}")
        used.append(p.name)

    if chunks:
        out["files"] = used
        out["text"] = "\n\n".join(chunks)
        out["unverified"] = False
    return out


def load_spotify_aggregates(since_days: int = 7) -> list[dict]:
    """
    Spotify aggregate digests in the filename-date window (not mtime).
    Non-recursive glob — same pattern as export_ai_briefing.build_podcasts_md().
    Each dict: filename, content, source_sha256, cited_episodes, sidecar_text,
    sidecar_files, unverified.
    """
    from tasks.export_ai_briefing import parse_summary_date

    if not SUMMARIES_DIR.exists():
        logger.warning("Podcast summaries directory not found: %s", SUMMARIES_DIR)
        return []

    today = datetime.now().date()
    results = []

    for p in sorted(SUMMARIES_DIR.glob("*Spotify_Podcast_Aggregate*.md")):
        if not p.is_file():
            continue
        d = parse_summary_date(p.name)
        if d is None:
            continue
        age_days = (today - d).days
        if not (0 <= age_days <= since_days):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            logger.warning("Could not read aggregate %s: %s", p.name, e)
            continue
        sha_m = DIGEST_SHA_RE.search(content) or SHA_RE.search(content)
        sha = sha_m.group(1) if sha_m else None
        sidecars = _load_sidecars_for_digest(p.stem, sha)
        results.append({
            "filename": p.name,
            "content": content,
            "source_sha256": sha,
            "cited_episodes": _parse_cited_episodes(content),
            "sidecar_text": sidecars["text"],
            "sidecar_files": sidecars["files"],
            "unverified": sidecars["unverified"],
        })
    return results


def _normalize_for_match(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _overlap_score(filename: str, cited: str) -> int:
    """0 = no match. Higher = better title-token overlap after a show-name hit."""
    hay = _normalize_for_match(filename.replace("_", " "))
    if ":" in cited:
        show, title = cited.split(":", 1)
    else:
        show, title = cited, ""
    show_toks = [t for t in _normalize_for_match(show).split() if len(t) > 1]
    if not show_toks or not all(t in hay for t in show_toks):
        return 0
    title_toks = [t for t in _normalize_for_match(title).split() if len(t) > 2]
    if not title_toks:
        return 1
    hits = sum(1 for t in title_toks if t in hay)
    if hits == 0:
        return 0
    return 1 + hits


def match_cited_episodes_to_transcripts(
    aggregates: list[dict],
    transcript_filenames: list[str],
) -> list[tuple[str, str, str]]:
    """Python-side overlap: (digest_filename, cited_episode, matching_transcript_filename)."""
    pairs = []
    for agg in aggregates:
        for cited in agg.get("cited_episodes") or []:
            best_fn = None
            best_score = 0
            for fn in transcript_filenames:
                score = _overlap_score(fn, cited)
                if score > best_score:
                    best_score = score
                    best_fn = fn
            if best_fn:
                pairs.append((agg["filename"], cited, best_fn))
    return pairs


def assemble_source_blocks(
    transcripts: list[dict],
    aggregates: list[dict],
    overlap_pairs: list[tuple[str, str, str]],
) -> list[str]:
    """Labeled blocks actually sent to the model. Python gathers; the LLM does not infer overlap."""
    blocks = []
    for t in transcripts:
        blocks.append(
            f"--- TRANSCRIPT: {t['filename']} (modified: {t['modified_at']}) ---\n{t['content']}"
        )
    for a in aggregates:
        header = f"--- SPOTIFY AGGREGATE: {a['filename']} ---"
        if a.get("unverified"):
            header += "\n[UNVERIFIED — no sidecar found]"
        blocks.append(f"{header}\n{a['content']}")
        if a.get("sidecar_text"):
            blocks.append(
                f"--- VERIFICATION SIDECAR FOR ABOVE ({a['filename']}) ---\n{a['sidecar_text']}"
            )
    if overlap_pairs:
        lines = [
            "--- EPISODE/AGGREGATE OVERLAP (Python-matched; do not re-derive) ---",
            "Treat the transcript as the primary source for that theme and the aggregate as commentary.",
            "Do not emit two candidates for the same underlying idea.",
        ]
        for digest_fn, cited, transcript_fn in overlap_pairs:
            lines.append(f"- [{digest_fn}] \"{cited}\" <-> {transcript_fn}")
        blocks.append("\n".join(lines))
    return blocks


def prepare_idea_inputs(since_days: int = 7) -> dict:
    """Load transcripts + aggregates + overlap for one run. Used by run_idea_generator and tests."""
    transcripts = load_transcripts(since_days=since_days)
    aggregates = load_spotify_aggregates(since_days=since_days)
    overlap_pairs = match_cited_episodes_to_transcripts(
        aggregates, [t["filename"] for t in transcripts]
    )
    blocks = assemble_source_blocks(transcripts, aggregates, overlap_pairs)
    analyzed = [t["filename"] for t in transcripts] + [a["filename"] for a in aggregates]
    return {
        "transcripts": transcripts,
        "aggregates": aggregates,
        "overlap_pairs": overlap_pairs,
        "blocks": blocks,
        "analyzed_names": analyzed,
    }


def _held_tickers_from_composite(composite_data: dict) -> set[str]:
    """Actual position tickers from the market sub-bundle. Excludes CASH_MANUAL."""
    from core.bundle import load_bundle

    market_path = Path(composite_data["market_bundle_path"])
    market = load_bundle(market_path)
    held: set[str] = set()
    for pos in market.get("positions") or []:
        ticker = str(pos.get("ticker") or "").strip().upper()
        if ticker and ticker != "CASH_MANUAL":
            held.add(ticker)
    return held


def sanitize_candidate_overlaps(
    candidates: list[Candidate],
    held: set[str],
) -> list[tuple[str, str]]:
    """
    After the LLM returns:
      1. Any related_ticker that is a current holding must appear in
         current_holdings_overlap (keeps clustered names in sort group 2).
      2. Drop any overlap ticker that is not an actual position.
    Returns (candidate_ticker, dropped_symbol) pairs that were removed.
    """
    dropped: list[tuple[str, str]] = []
    held_upper = {t.upper() for t in held}
    for c in candidates:
        overlap: list[str] = []
        seen: set[str] = set()
        for raw in list(c.current_holdings_overlap or []) + list(c.related_tickers or []):
            t = str(raw).strip().upper()
            if not t or t in seen:
                continue
            if t in held_upper:
                overlap.append(t)
                seen.add(t)
            elif raw in (c.current_holdings_overlap or []):
                dropped.append((c.ticker, t))
                logger.info(
                    "Dropped %s from %s current_holdings_overlap — not a current position.",
                    t,
                    c.ticker,
                )
        c.current_holdings_overlap = overlap
    return dropped


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
    max_tokens: int = 16000,
) -> IdeaGeneratorOutput:
    """
    End-to-end idea generator.
    1. Resolves composite bundle path (auto-detects latest if not provided).
    2. Loads transcripts and Spotify aggregates within since_days window.
    3. If neither source exists, returns empty output with explanatory note.
    4. Calls ask_gemini_composite() with labeled source blocks as user prompt.
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

    # 2. Load transcripts + Spotify aggregates (Python gathers overlap / sidecars)
    prepared = prepare_idea_inputs(since_days=since_days)
    transcripts = prepared["transcripts"]
    aggregates = prepared["aggregates"]
    analyzed_names = prepared["analyzed_names"]
    transcript_blocks = prepared["blocks"]

    # 3. Handle empty window
    if not transcripts and not aggregates:
        logger.info(
            "No transcripts or Spotify aggregates found in the last %d days — returning empty output.",
            since_days,
        )
        return IdeaGeneratorOutput(
            bundle_hash=composite_hash,
            generated_at=datetime.now(timezone.utc),
            transcripts_analyzed=[],
            candidates=[],
            notes=(
                f"No new transcripts found within the last {since_days} days in {TRANSCRIPTS_DIR} "
                f"and no Spotify aggregates in {SUMMARIES_DIR}. "
                "Run 'pm ingest podcasts' to fetch new transcripts, then re-run this command."
            ),
        )

    # 4. Read system prompt
    prompt_path = Path("prompts/idea_generator.md")
    if not prompt_path.exists():
        raise FileNotFoundError("prompts/idea_generator.md not found — cannot run agent.")
    system_instruction = prompt_path.read_text(encoding="utf-8")

    # 5. Build user prompt
    n_tx = len(transcripts)
    n_agg = len(aggregates)
    user_prompt = (
        f"Analyze the following {n_tx} podcast transcript(s) and {n_agg} Spotify aggregate digest(s) "
        f"and extract actionable investment candidates using the schema provided. "
        f"Fill transcripts_analyzed with the exact filenames listed "
        f"(include both TRANSCRIPT and SPOTIFY AGGREGATE filenames).\n\n"
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
            transcripts_analyzed=analyzed_names,
            candidates=[],
            notes="LLM call failed — check Gemini credentials and logs.",
        )

    # 7. Stamp generated_at client-side (LLM value unreliable)
    result.generated_at = datetime.now(timezone.utc)
    if not result.transcripts_analyzed:
        result.transcripts_analyzed = analyzed_names

    # 8. Overlap is a holdings list, not a sector-proxy list. Related held
    # names must survive clustering so _sort_key() still places them in group 2.
    held = _held_tickers_from_composite(composite_data)
    sanitize_candidate_overlaps(result.candidates, held)

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
            if c.related_tickers:
                lines.append(
                    f"**Related tickers (same source):** {', '.join(c.related_tickers)}"
                )
            lines.append("")
            lines.append(c.thesis_summary)
            lines.append("")
            if c.notable_concerns:
                lines.append(f"**Concerns:** {c.notable_concerns}")
                lines.append("")
            lines.append("---")
            lines.append("")

    if output.market_themes:
        lines += ["## Market Themes & Macro Observations", ""]
        for mt in output.market_themes:
            lines.append(f"### {mt.theme}")
            lines.append("")
            if mt.sources:
                lines.append(f"**Sources:** {', '.join(mt.sources)}  ")
            lines.append(mt.summary)
            lines.append("")

    lines += ["## Notes", ""]
    lines.append(output.notes if output.notes else "_No additional notes._")
    lines.append("")
    lines += [
        "---",
        "",
        "_Want Claude's independent read of these same transcripts? Ask Claude Code: \"what would the idea generator list look like if you processed the transcripts instead of Gemini?\"_",
        "",
    ]

    markdown = "\n".join(lines)

    if dry_run:
        return markdown

    out_dir = Path(report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"ideas_{date_str}_{hash_prefix}.md"
    file_path = out_dir / filename
    file_path.write_text(markdown, encoding="utf-8")
    return str(file_path)
