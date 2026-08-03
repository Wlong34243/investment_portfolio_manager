"""
utils/moment_windows.py — Cue-phrase transcript windowing for high-signal
moment extraction.

Purpose:
    Shrink a full podcast transcript down to the handful of character spans
    worth sending to an LLM: places where the speaker signals a conviction
    change, a non-consensus view, a disclosed position, a specific numeric
    claim near a held/tracked name, or a disagreement between speakers.
    This is pure haystack-shrinking. It never decides whether a moment is
    good, only where to look.

Inputs:
    - Raw transcript text (str) — lowercase YouTube auto-caption prose,
      no reliable sentence punctuation, ">>" marks a speaker change only
      (no identity). See prompts/moment_extraction_2026-08-02.md Step 0.4/0.5.
    - data/moment_cues.json — tunable cue-phrase config (load_cues()).
    - data/ticker_aliases.json — ticker -> company-name aliases used for the
      specific_claim ticker-proximity gate (load_ticker_aliases()).

Outputs:
    - find_windows(transcript, cues, radius) -> list of non-overlapping
      window dicts: char_start, char_end, cue_matched, cue_category, text,
      speaker (for disagreement windows), matched_cues (audit trail).

Dependencies:
    - Standard library only (re, json, logging, os). No network. No LLM
      calls — window selection must never be an LLM call.

Notes:
    Timestamps are not recoverable for the existing transcript corpus (the
    ingestion pipeline discards seg.start/seg.duration before writing the
    .txt). Windows are character-offset based, not time-based, by design.
"""

from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

DEFAULT_CUES_PATH = os.path.join("data", "moment_cues.json")
DEFAULT_ALIASES_PATH = os.path.join("data", "ticker_aliases.json")

MAX_WINDOWS_PER_TRANSCRIPT = 40

# Priority for resolving which cue "wins" when raw hits merge into one
# window. Step 3 of the build spec ranks reversal > disagreement >
# non_consensus > specific_claim for the final render; position_disclosure
# isn't covered by that ranking, so it's placed below specific_claim here
# as a judgment call — it's the least likely to be mistaken for noise but
# also the least novel of the five categories.
CATEGORY_PRIORITY = {
    "reversal": 0,
    "disagreement": 1,
    "non_consensus": 2,
    "specific_claim": 3,
    "position_disclosure": 4,
}


def load_cues(path: str = DEFAULT_CUES_PATH) -> list[dict]:
    """Read data/moment_cues.json and flatten it into cue-descriptor dicts
    consumable by find_windows(). Each dict has at least "category" and
    "kind"; kind-specific fields follow (see module docstring)."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    flattened: list[dict] = []
    for category, cfg in raw.items():
        if category.startswith("_") or category == "macro_terms":
            continue
        for pattern in cfg.get("patterns", []):
            kind = "simple"
            extra = {}
            if cfg.get("requires_ticker_proximity"):
                kind = "ticker_proximity"
                extra["proximity_chars"] = cfg.get("proximity_chars", 120)
            elif cfg.get("requires_speaker_marker_proximity"):
                kind = "speaker_proximity"
                extra["proximity_chars"] = cfg.get("proximity_chars", 200)
                extra["speaker_marker"] = cfg.get("speaker_marker", ">>")
            flattened.append({
                "category": category,
                "kind": kind,
                "pattern": pattern,
                **extra,
            })
        for pair in cfg.get("contrast_pairs", []):
            flattened.append({
                "category": category,
                "kind": "contrast",
                "pattern": pair["lead"],
                "contrast": pair["contrast"],
                "contrast_window": pair.get("window_chars", 300),
            })
    return flattened


def load_ticker_aliases(path: str = DEFAULT_ALIASES_PATH) -> dict[str, list[str]]:
    """ticker -> [alias strings]. See data/ticker_aliases.json for why bare
    tickers are deliberately omitted for a few common-word collisions."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def load_macro_terms(path: str = DEFAULT_CUES_PATH) -> list[str]:
    """Configurable macro-term list (data/moment_cues.json's 'macro_terms'
    key) used by Fix 2's no-portfolio-hook filter to let a ticker-less
    reversal survive when it's genuinely a macro-path call (rates, Fed,
    credit) rather than unrelated musing."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return raw.get("macro_terms", [])


def _word_pattern(literal: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(literal) + r"\b", re.IGNORECASE)


def _alias_patterns(ticker_aliases: dict[str, list[str]]) -> list[tuple[str, re.Pattern]]:
    """Flatten ticker -> aliases into (ticker, compiled_pattern) pairs."""
    pairs = []
    for ticker, aliases in ticker_aliases.items():
        for alias in aliases:
            pairs.append((ticker, _word_pattern(alias)))
    return pairs


def _nearest_ticker(text: str, start: int, end: int, alias_patterns) -> str | None:
    for ticker, pattern in alias_patterns:
        if pattern.search(text, start, end):
            return ticker
    return None


def _turn_index(transcript: str, position: int, marker: str) -> int:
    """How many speaker-change markers occur at or before `position`.
    Used as the honest, positional stand-in for a speaker identity we
    don't have (Step 0.5)."""
    return transcript.count(marker, 0, position)


def _raw_hits(transcript: str, cues: list[dict], alias_patterns) -> list[dict]:
    hits = []
    for cue in cues:
        category = cue["category"]
        kind = cue["kind"]
        pattern = _word_pattern(cue["pattern"])

        if kind == "simple":
            for m in pattern.finditer(transcript):
                hits.append({
                    "match_start": m.start(),
                    "match_end": m.end(),
                    "category": category,
                    "cue_matched": cue["pattern"],
                    "speaker": None,
                })

        elif kind == "contrast":
            contrast_pattern = _word_pattern(cue["contrast"])
            window_chars = cue["contrast_window"]
            for m in pattern.finditer(transcript):
                tail = transcript[m.end():m.end() + window_chars]
                cm = contrast_pattern.search(tail)
                if not cm:
                    continue
                hits.append({
                    "match_start": m.start(),
                    "match_end": m.end() + cm.end(),
                    "category": category,
                    "cue_matched": "%s ... %s" % (cue["pattern"], cue["contrast"]),
                    "speaker": None,
                })

        elif kind == "ticker_proximity":
            proximity = cue["proximity_chars"]
            for m in pattern.finditer(transcript):
                lo = max(0, m.start() - proximity)
                hi = min(len(transcript), m.end() + proximity)
                ticker = _nearest_ticker(transcript, lo, hi, alias_patterns)
                if ticker is None:
                    continue
                hits.append({
                    "match_start": m.start(),
                    "match_end": m.end(),
                    "category": category,
                    "cue_matched": cue["pattern"],
                    "speaker": None,
                    "ticker_nearby": ticker,
                })

        elif kind == "speaker_proximity":
            proximity = cue["proximity_chars"]
            marker = cue["speaker_marker"]
            for m in pattern.finditer(transcript):
                lo = max(0, m.start() - proximity)
                hi = min(len(transcript), m.end() + proximity)
                if marker not in transcript[lo:hi]:
                    continue
                hits.append({
                    "match_start": m.start(),
                    "match_end": m.end(),
                    "category": category,
                    "cue_matched": cue["pattern"],
                    "speaker": "turn_%d" % _turn_index(transcript, m.start(), marker),
                })

    return hits


def find_windows(
    transcript: str,
    cues: list[dict],
    radius: int = 1200,
    ticker_aliases: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Return non-overlapping high-signal windows over `transcript`.

    cues: flattened cue-descriptor list, as produced by load_cues().
    ticker_aliases: ticker -> [alias strings], as produced by
        load_ticker_aliases(). Defaults to loading from disk so callers
        don't have to thread it through, but tests can inject a small
        fixture dict directly.
    """
    if ticker_aliases is None:
        ticker_aliases = load_ticker_aliases()
    alias_patterns = _alias_patterns(ticker_aliases)

    hits = _raw_hits(transcript, cues, alias_patterns)
    if not hits:
        return []

    for h in hits:
        h["char_start"] = max(0, h["match_start"] - radius)
        h["char_end"] = min(len(transcript), h["match_end"] + radius)

    hits.sort(key=lambda h: h["char_start"])

    merged: list[dict] = []
    current = None
    for h in hits:
        if current is None:
            current = {
                "char_start": h["char_start"],
                "char_end": h["char_end"],
                "contributors": [h],
            }
            continue
        if h["char_start"] <= current["char_end"]:
            current["char_end"] = max(current["char_end"], h["char_end"])
            current["contributors"].append(h)
        else:
            merged.append(current)
            current = {
                "char_start": h["char_start"],
                "char_end": h["char_end"],
                "contributors": [h],
            }
    if current is not None:
        merged.append(current)

    windows = []
    for m in merged:
        contributors = m["contributors"]
        winner = min(contributors, key=lambda h: CATEGORY_PRIORITY.get(h["category"], 99))
        windows.append({
            "char_start": m["char_start"],
            "char_end": m["char_end"],
            "cue_matched": winner["cue_matched"],
            "cue_category": winner["category"],
            "speaker": winner.get("speaker"),
            "text": transcript[m["char_start"]:m["char_end"]],
            "matched_cues": [
                {"category": c["category"], "cue_matched": c["cue_matched"]}
                for c in contributors
            ],
        })

    if len(windows) > MAX_WINDOWS_PER_TRANSCRIPT:
        logger.warning(
            "find_windows: %d windows exceeds guardrail of %d — cue list is "
            "likely too loose. Truncating to the %d highest-density windows.",
            len(windows), MAX_WINDOWS_PER_TRANSCRIPT, MAX_WINDOWS_PER_TRANSCRIPT,
        )
        windows.sort(key=lambda w: len(w["matched_cues"]), reverse=True)
        windows = windows[:MAX_WINDOWS_PER_TRANSCRIPT]
        windows.sort(key=lambda w: w["char_start"])

    return windows
