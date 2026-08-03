"""
utils/agents/moment_extractor.py — High-signal moment extraction agent.

Purpose:
    Second extraction pass over podcast transcripts, parallel to (not a
    replacement for) podcast_analyst.PodcastStrategy. Where PodcastStrategy
    answers "what is the macro allocation view," this answers "does this
    change what Bill holds, or what he'd consider holding" by pulling out
    specific, falsifiable, verbatim moments: reversals, non-consensus
    claims, disclosed positions, specific numeric claims, and disagreements.

Inputs:
    - Cue-phrase windows from utils.moment_windows.find_windows() (Python,
      deterministic, no LLM). This module only judges windows Python has
      already located; it never selects them.
    - vault/theses/*_thesis.md and the live position set, but ONLY for
      relevance resolution at read time (see architecture note below) —
      extraction itself never touches either.

Outputs:
    - MomentCandidate objects. Extraction (extract_moment_from_window /
      extract_moments_for_transcript) is called by tasks/extract_moments.py
      and produces candidates cached WITHOUT a resolved relevance tag.
      Relevance resolution (resolve_relevance et al.) is called by
      tasks/export_ai_briefing.py's build_moments_md() at read time.

Dependencies:
    - utils.gemini_client.ask_gemini() (SAFETY_PREAMBLE auto-prepended —
      do not duplicate it in the system_instruction here)
    - utils.etf_holdings.compute_lookthrough() (cache-only, no new network
      calls — see the ADJACENT design note below)
    - utils.moment_windows

Architecture note — extraction/relevance split (2026-08-02, do not revert):
    Transcripts are immutable once written, so their extracted moments are
    immutable too; re-running Gemini on the same window on every export is
    repeated work with no new input, and it's nondeterministic besides
    (podcasts.md would stop being diffable for unchanged inputs). Relevance
    is the opposite: it's a cheap Python lookup, but it's POSITION-
    DEPENDENT and the position set is mutable (SKHY is the live example —
    a moment cached as ZERO_EXPOSURE before SKHY was bought should render
    as HELD today). So:
      - extraction is cached to data/moments/{transcript_stem}.moments.json
        by tasks/extract_moments.py, position-independent, run once per
        transcript, never re-run just because positions changed.
      - relevance is NEVER persisted to that cache. It's computed fresh
        every time the cache is read, using whatever position/thesis set
        is live at read time.
    Gemini's own relevance guess IS kept in the cache, under the key
    gemini_relevance_guess (not "relevance") — purely as an audit trail
    for logging Python-vs-Gemini disagreement at read time. It is never
    treated as authoritative.

Design note on ADJACENT (2026-08-02 design decision, do not revert):
    The spec originally called for a GICS-sector leg on ADJACENT ("same
    sector as a held name"). Sector is empty on every position in every
    bundle checked, and cached on only 2 of 38 held tickers via FMP. But
    the deeper problem isn't missing data: at 38 positions spanning nearly
    every GICS sector, a *working* sector match would resolve almost every
    mentioned ticker to ADJACENT and empty the ZERO_EXPOSURE subsection --
    the one section this build exists to populate. Rejected outright, not
    deferred pending the FMP-bundle-migration gap (see state.md) -- do NOT
    re-add sector-based ADJACENT matching once sector data backfills. A
    ticker wrongly falling through to ZERO_EXPOSURE costs a slightly
    noisier idea list; a real idea wrongly buried in ADJACENT is never
    seen at all. ADJACENT resolves via two legs only:
      (a) ETF look-through — ticker appears in a held fund's cached top-10
      (b) thesis mention — ticker/company name appears in the BODY text of
          some OTHER thesis file (not its own), i.e. already on Bill's
          radar via analysis of a name he holds
"""

from __future__ import annotations

import glob
import json
import logging
import os
import re
from typing import Literal, Optional

from pydantic import BaseModel

from utils.gemini_client import ask_gemini
from utils.moment_windows import load_ticker_aliases

logger = logging.getLogger(__name__)

THESIS_DIR = os.path.join("vault", "theses")
CACHE_DIR = os.path.join("data", "moments")

RELEVANCE_PRIORITY = {"HELD": 0, "THESIS_ON_FILE": 1, "ADJACENT": 2, "ZERO_EXPOSURE": 3}

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


CURRENT_SCHEMA_VERSION = 2

# Context is snapped outward to the nearest sentence/turn boundary within
# this many chars of the target window before falling back to a raw cut.
CONTEXT_MIN_CHARS = 400
CONTEXT_MAX_CHARS = 800
CONTEXT_SNAP_TOLERANCE = 120
CONTEXT_SNAP_MARKERS = (". ", "? ", "! ", ">> ")


class GeminiMomentResponse(BaseModel):
    """Schema for the Gemini call ONLY -- deliberately has no `context`
    field. context is Python-sliced from the source transcript and must
    never be something the model writes (see Fix 1 non-goals)."""
    source_episode: str
    char_offset: int
    fragment: str
    speaker: str
    moment_type: Literal["reversal", "non_consensus", "position_disclosure",
                         "specific_claim", "disagreement"]
    tickers_touched: list[str]
    relevance: Literal["HELD", "THESIS_ON_FILE", "ADJACENT", "ZERO_EXPOSURE"]
    why_it_matters: str


class MomentCandidate(BaseModel):
    source_episode: str
    char_offset: int
    fragment: str
    context: str
    speaker: str
    moment_type: Literal["reversal", "non_consensus", "position_disclosure",
                         "specific_claim", "disagreement"]
    tickers_touched: list[str]
    relevance: Literal["HELD", "THESIS_ON_FILE", "ADJACENT", "ZERO_EXPOSURE"]
    why_it_matters: str


# ---------------------------------------------------------------------------
# Relevance resolution — read-time-only Python lookup, never trust the
# model's guess, never call this from the extraction path
# ---------------------------------------------------------------------------

def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1)


def build_thesis_body_index(thesis_dir: str = THESIS_DIR) -> dict[str, str]:
    """ticker -> thesis body text (frontmatter stripped), active vault only."""
    index = {}
    for path in sorted(glob.glob(os.path.join(thesis_dir, "*_thesis.md"))):
        ticker = os.path.basename(path).replace("_thesis.md", "")
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            continue
        index[ticker] = _strip_frontmatter(raw)
    return index


def build_lookthrough_symbols(positions: list[dict], use_network: bool = False) -> set[str]:
    """Symbols appearing inside any held fund's cached top-10 holdings.

    Passing every held ticker as a look-through candidate is safe: non-fund
    tickers simply have no cache file and are skipped (see
    utils.etf_holdings.get_top_holdings). use_network=False by design —
    this must never trigger a live fetch.
    """
    from utils.etf_holdings import compute_lookthrough

    all_tickers = [p["ticker"] for p in positions if p.get("ticker")]
    rows, _resolved, _unresolved = compute_lookthrough(
        positions, all_tickers, use_network=use_network
    )
    return {row["symbol"] for row in rows}


def _mentioned_in_other_thesis(
    ticker: str, aliases: list[str], thesis_bodies: dict[str, str]
) -> Optional[str]:
    # Never force-match the bare ticker -- data/ticker_aliases.json is the
    # single source of truth for which tickers are safe to match bare (it
    # deliberately omits SNOW/GILD/ES/ET/NOW/META and most of the S&P-500-
    # generated entries precisely because the bare symbol collides with
    # ordinary English words). Forcing it here would silently reintroduce
    # that exact false-positive class.
    compiled = [re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE) for p in aliases if p]
    for other_ticker, body in thesis_bodies.items():
        if other_ticker == ticker:
            continue
        for pat in compiled:
            if pat.search(body):
                return other_ticker
    return None


def resolve_ticker_relevance(
    ticker: str,
    held_tickers: set[str],
    thesis_tickers: set[str],
    lookthrough_symbols: set[str],
    ticker_aliases: dict[str, list[str]],
    thesis_bodies: dict[str, str],
) -> tuple[str, dict]:
    ticker = ticker.upper()
    if ticker in held_tickers:
        return "HELD", {}
    if ticker in thesis_tickers:
        return "THESIS_ON_FILE", {}
    if ticker in lookthrough_symbols:
        return "ADJACENT", {"via": "etf_lookthrough"}
    mention_file = _mentioned_in_other_thesis(
        ticker, ticker_aliases.get(ticker, []), thesis_bodies
    )
    if mention_file:
        return "ADJACENT", {"via": "thesis_mention", "file": "%s_thesis.md" % mention_file}
    return "ZERO_EXPOSURE", {}


def resolve_relevance(
    tickers_touched: list[str],
    held_tickers: set[str],
    thesis_tickers: set[str],
    lookthrough_symbols: set[str],
    ticker_aliases: dict[str, list[str]],
    thesis_bodies: dict[str, str],
) -> tuple[str, list[tuple[str, str, dict]]]:
    """Aggregate relevance across every ticker a moment touches: the moment
    is as relevant as its most-relevant ticker (HELD beats ADJACENT beats
    ZERO_EXPOSURE, etc.). Empty tickers_touched -> ZERO_EXPOSURE."""
    if not tickers_touched:
        return "ZERO_EXPOSURE", []
    resolved = [
        (t, *resolve_ticker_relevance(
            t, held_tickers, thesis_tickers, lookthrough_symbols, ticker_aliases, thesis_bodies
        ))
        for t in tickers_touched
    ]
    best = min(resolved, key=lambda r: RELEVANCE_PRIORITY[r[1]])
    return best[1], resolved


# ---------------------------------------------------------------------------
# Fix 2 — no-portfolio-hook filter, read-time only (needs the live position/
# thesis set, so it lives alongside relevance resolution, not extraction)
# ---------------------------------------------------------------------------

def passes_portfolio_hook_filter(
    candidate: "MomentCandidate",
    held_tickers: set[str],
    ticker_aliases: dict[str, list[str]],
    macro_terms: list[str],
) -> bool:
    """False means: drop this candidate entirely (not even ZERO_EXPOSURE) --
    it has no discernible relationship to Bill's book at all. A ticker-less
    reversal survives only if its context contains a macro term; philosophical
    musing about AI or an unrelated private-market anecdote does not."""
    if candidate.tickers_touched:
        return True

    context = candidate.context or ""
    for ticker in held_tickers:
        # Never force-match the bare ticker -- see _mentioned_in_other_thesis
        # for why (SNOW/GILD/ES/ET/NOW/META collide with ordinary words).
        for alias in ticker_aliases.get(ticker, []):
            if re.search(r"\b" + re.escape(alias) + r"\b", context, re.IGNORECASE):
                return True

    if candidate.moment_type == "reversal":
        for term in macro_terms:
            if re.search(r"\b" + re.escape(term) + r"\b", context, re.IGNORECASE):
                return True

    return False


# ---------------------------------------------------------------------------
# Extraction agent — position-independent, called only by
# tasks/extract_moments.py
# ---------------------------------------------------------------------------

def _slice_context(transcript: str, center: int) -> str:
    """400-800 chars of VERBATIM transcript centered on `center`, Python-
    sliced -- Gemini never sees or writes this. Snaps outward to the
    nearest sentence/turn boundary within a small tolerance where cheap;
    falls back to a raw cut otherwise. Never produces less than
    CONTEXT_MIN_CHARS unless the transcript itself is that short."""
    half = CONTEXT_MAX_CHARS // 2
    start = max(0, center - half)
    end = min(len(transcript), center + half)

    best_start = start
    for marker in CONTEXT_SNAP_MARKERS:
        idx = transcript.rfind(marker, max(0, start - CONTEXT_SNAP_TOLERANCE), start + 1)
        if idx != -1:
            best_start = idx + len(marker)
            break
    start = best_start

    best_end = end
    for marker in CONTEXT_SNAP_MARKERS:
        idx = transcript.find(marker, max(end - 1, 0), min(len(transcript), end + CONTEXT_SNAP_TOLERANCE))
        if idx != -1:
            best_end = idx + len(marker)
            break
    end = best_end

    if end - start < CONTEXT_MIN_CHARS:
        deficit = CONTEXT_MIN_CHARS - (end - start)
        start = max(0, start - deficit // 2)
        end = min(len(transcript), end + (deficit - deficit // 2))

    return transcript[start:end]


SYSTEM_INSTRUCTION = """You are extracting a single high-signal moment from one window of a podcast transcript.

The window was pre-selected by a deterministic cue-phrase match (not by you). Your job is
NOT to judge whether the topic is interesting in general -- it is to decide whether this
specific window contains a genuine instance of the cue category it was tagged for, and if
so, extract it faithfully.

Rules:
- fragment MUST be a VERBATIM substring of the window text below, <=15 words. Do not
  paraphrase, correct grammar, or fix transcription errors. Copy exact words.
- If the window is a false positive (sponsor read, ad, show logistics, or the cue phrase
  appears but there is no genuine moment), return fragment="" and leave the other fields
  as best-effort placeholders -- the caller drops empty-fragment candidates.
- why_it_matters: <=25 words, why this bears on Bill's holdings or candidate ideas. No
  price targets, no forecasts, no buy/sell language.
- tickers_touched: tickers or company names actually referenced in the fragment's
  immediate context, using the ticker symbol (e.g. "NVDA" not "Nvidia").
- relevance: your best guess is fine -- it is never used directly, only logged against a
  deterministic lookup made later to measure how often you'd have gotten it right.
- speaker: leave as the turn index handed to you in the prompt; you cannot infer a name.
"""


DROP_MODEL_FAILED = "model_failed"
DROP_EMPTY_FRAGMENT = "empty_fragment"
DROP_VERBATIM_FAIL = "verbatim_fail"
DROP_REASONS = (DROP_MODEL_FAILED, DROP_EMPTY_FRAGMENT, DROP_VERBATIM_FAIL)


def extract_moment_from_window(
    window: dict, source_episode: str, transcript: str
) -> tuple[Optional[MomentCandidate], Optional[str]]:
    """One Gemini call for one pre-selected window. Returns
    (candidate, None) on success or (None, drop_reason) otherwise --
    drop_reason is one of DROP_REASONS, for Fix 0c instrumentation.

    Deliberately takes no position/thesis arguments -- extraction must stay
    position-independent (see module architecture note). candidate.relevance
    is Gemini's raw, unverified guess (gemini_relevance_guess at cache time).
    `transcript` is the FULL source text, needed only to Python-slice
    `context` -- Gemini never sees more than `window["text"]`.
    """
    prompt = (
        "moment_type (cue category): %s\n"
        "cue phrase matched: %s\n"
        "speaker (turn index, use verbatim): %s\n"
        "source_episode (use verbatim): %s\n"
        "char_offset (use verbatim): %d\n\n"
        "WINDOW TEXT:\n%s"
    ) % (
        window["cue_category"], window["cue_matched"], window.get("speaker") or "unknown",
        source_episode, window["char_start"], window["text"],
    )

    result = ask_gemini(
        prompt=prompt,
        system_instruction=SYSTEM_INSTRUCTION,
        response_schema=GeminiMomentResponse,
        max_tokens=2000,
    )
    if result is None:
        logger.warning("moment_extractor: Gemini call failed for %s @ %d",
                        source_episode, window["char_start"])
        return None, DROP_MODEL_FAILED

    fragment = result.fragment
    if not fragment.strip():
        return None, DROP_EMPTY_FRAGMENT

    frag_idx = window["text"].find(fragment)
    if frag_idx == -1:
        logger.warning(
            "moment_extractor: dropped non-verbatim fragment %r for %s @ %d",
            fragment, source_episode, window["char_start"],
        )
        return None, DROP_VERBATIM_FAIL

    absolute_frag_pos = window["char_start"] + frag_idx + len(fragment) // 2
    context = _slice_context(transcript, absolute_frag_pos)

    # Stronger verbatim check (Fix 1): fragment must also be a substring of
    # the Python-sliced context, not just the (larger) Gemini-visible
    # window. This subsumes the window-text check above; it should always
    # pass by construction since context is centered on the fragment's own
    # position, but a slicing edge case (fragment near transcript start/end)
    # is still a real, checkable failure mode, not just theoretical.
    if fragment not in context:
        logger.warning(
            "moment_extractor: dropped fragment %r not found in sliced context for %s @ %d",
            fragment, source_episode, window["char_start"],
        )
        return None, DROP_VERBATIM_FAIL

    candidate = MomentCandidate(
        source_episode=source_episode,
        char_offset=window["char_start"],
        fragment=fragment,
        context=context,
        speaker=window.get("speaker") or "unknown",
        moment_type=window["cue_category"],  # type: ignore[arg-type]
        tickers_touched=result.tickers_touched,
        relevance=result.relevance,
        why_it_matters=result.why_it_matters,
    )
    return candidate, None


def extract_moments_for_transcript(
    transcript_path: str,
    cues: list[dict],
    radius: int = 1200,
) -> tuple[list[MomentCandidate], dict]:
    """End-to-end: window a single transcript file and extract candidates.
    Position-independent -- callers persist the result to cache without
    ever touching candidate.relevance (Gemini's raw guess).

    Returns (candidates, stats) where stats has windows_found, windows_sent,
    candidates_returned, and dropped_by_reason (Fix 0c instrumentation).
    """
    from utils.moment_windows import find_windows

    with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
        transcript = f.read()

    source_episode = os.path.basename(transcript_path)
    ticker_aliases = load_ticker_aliases()
    windows = find_windows(transcript, cues, radius=radius, ticker_aliases=ticker_aliases)

    dropped_by_reason = {reason: 0 for reason in DROP_REASONS}
    candidates = []
    for window in windows:
        candidate, drop_reason = extract_moment_from_window(window, source_episode, transcript)
        if candidate is not None:
            candidates.append(candidate)
        else:
            dropped_by_reason[drop_reason] += 1

    stats = {
        "windows_found": len(windows),
        "windows_sent": len(windows),
        "candidates_returned": len(candidates),
        "dropped_by_reason": dropped_by_reason,
    }
    return candidates, stats


# ---------------------------------------------------------------------------
# Cache serialization — relevance is NEVER written; gemini_relevance_guess
# is the audit-only stand-in
# ---------------------------------------------------------------------------

def cache_path_for_transcript(transcript_filename: str, cache_dir: str = CACHE_DIR) -> str:
    stem = os.path.splitext(os.path.basename(transcript_filename))[0]
    return os.path.join(cache_dir, "%s.moments.json" % stem)


def moment_to_cache_dict(candidate: MomentCandidate) -> dict:
    data = candidate.model_dump(exclude={"relevance"})
    data["gemini_relevance_guess"] = candidate.relevance
    return data


def write_moments_cache(
    transcript_filename: str, candidates: list[MomentCandidate], cache_dir: str = CACHE_DIR
) -> str:
    """Writes the cache file (even an empty list) so a transcript with zero
    surviving candidates is not reprocessed on every run. Top-level
    schema_version lets extract_moments.py detect and re-extract stale
    (pre-context, v1) cache files."""
    os.makedirs(cache_dir, exist_ok=True)
    path = cache_path_for_transcript(transcript_filename, cache_dir)
    payload = {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "moments": [moment_to_cache_dict(c) for c in candidates],
    }
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, indent=2)
    return path


def read_cache_schema_version(cache_path: str) -> Optional[int]:
    """None means missing/unreadable/pre-versioning (v1 bare-list format) --
    all of which extract_moments.py treats as stale."""
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if isinstance(data, list):
        return None  # v1 format: a bare list, no schema_version at all
    return data.get("schema_version")


def load_cached_moments(cache_dir: str = CACHE_DIR) -> list[dict]:
    """Every cached moment dict across data/moments/*.moments.json. Each
    dict has no "relevance" key -- only "gemini_relevance_guess". Tolerates
    stale v1 (bare-list) cache files still on disk rather than crashing on
    them; they simply won't have a "context" key until re-extracted."""
    moments = []
    for path in sorted(glob.glob(os.path.join(cache_dir, "*.moments.json"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning("moment_extractor: could not read cache %s: %s", path, e)
            continue
        moments.extend(data if isinstance(data, list) else data.get("moments", []))
    return moments


def rehydrate_cached_moment(cached: dict, relevance: str) -> MomentCandidate:
    """Reconstruct a MomentCandidate from a cache dict plus a freshly
    resolved relevance tag (never the cached gemini_relevance_guess)."""
    fields = {k: v for k, v in cached.items() if k in MomentCandidate.model_fields}
    fields["relevance"] = relevance
    return MomentCandidate(**fields)
