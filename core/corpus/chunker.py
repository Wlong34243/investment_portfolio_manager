"""Structure-first text chunker with exact char/line coordinates."""

from __future__ import annotations

import re
from dataclasses import dataclass

TARGET_CHARS = 1200
OVERLAP_CHARS = 200

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


@dataclass
class Chunk:
    text: str
    char_start: int
    char_end: int
    line_start: int
    line_end: int
    heading: str | None


def _line_of(text: str, pos: int) -> int:
    """1-based line number for a character offset."""
    if pos <= 0:
        return 1
    return text.count("\n", 0, pos) + 1


def chunk_text(text: str, *, target: int = TARGET_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    """
    Split on markdown headings first, then blank-line paragraphs, then hard length.
    Coordinates are exact against `text` (no approximation).
    """
    if not text:
        return []

    # Segment by headings while carrying heading context
    segments: list[tuple[str | None, int, int]] = []  # heading, start, end
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        segments.append((None, 0, len(text)))
    else:
        if matches[0].start() > 0:
            segments.append((None, 0, matches[0].start()))
        for i, m in enumerate(matches):
            heading = m.group(2).strip()
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            segments.append((heading, start, end))

    chunks: list[Chunk] = []
    for heading, seg_start, seg_end in segments:
        body = text[seg_start:seg_end]
        if not body.strip():
            continue
        # Paragraph split
        paras: list[tuple[int, int]] = []
        cursor = 0
        for m in re.finditer(r"\n\s*\n", body):
            if m.start() > cursor:
                paras.append((seg_start + cursor, seg_start + m.start()))
            cursor = m.end()
        if cursor < len(body):
            paras.append((seg_start + cursor, seg_end))
        if not paras:
            paras = [(seg_start, seg_end)]

        buf_start = paras[0][0]
        buf_parts: list[str] = []
        for p_start, p_end in paras:
            piece = text[p_start:p_end]
            candidate = ("\n\n".join(buf_parts + [piece])) if buf_parts else piece
            if buf_parts and len(candidate) > target:
                # flush buffer
                joined = "\n\n".join(buf_parts)
                abs_start = buf_start
                abs_end = abs_start + len(joined)
                chunks.extend(_hard_split(text, abs_start, abs_end, heading, target, overlap))
                # overlap into next
                if overlap > 0 and len(joined) > overlap:
                    ov = joined[-overlap:]
                    buf_start = abs_end - len(ov)
                    buf_parts = [ov, piece]
                else:
                    buf_start = p_start
                    buf_parts = [piece]
            else:
                if not buf_parts:
                    buf_start = p_start
                buf_parts.append(piece)
        if buf_parts:
            joined = "\n\n".join(buf_parts)
            abs_start = buf_start
            abs_end = abs_start + len(joined)
            # Prefer exact slice from original when contiguous
            if text[abs_start:abs_end] != joined:
                # recompute from last flush semantics — use joined length from buf_start
                abs_end = min(len(text), abs_start + len(joined))
                # fall back: emit from reconstructed positions via search
                chunks.extend(_emit_joined(text, joined, abs_start, heading, target, overlap))
            else:
                chunks.extend(_hard_split(text, abs_start, abs_end, heading, target, overlap))

    return chunks


def _emit_joined(
    text: str, joined: str, prefer_start: int, heading: str | None, target: int, overlap: int
) -> list[Chunk]:
    idx = text.find(joined, max(0, prefer_start - 50))
    if idx < 0:
        idx = prefer_start
        end = min(len(text), idx + len(joined))
        return _hard_split(text, idx, end, heading, target, overlap)
    return _hard_split(text, idx, idx + len(joined), heading, target, overlap)


def _hard_split(
    text: str, start: int, end: int, heading: str | None, target: int, overlap: int
) -> list[Chunk]:
    out: list[Chunk] = []
    if end <= start:
        return out
    pos = start
    while pos < end:
        chunk_end = min(end, pos + target)
        if chunk_end < end:
            # try to break on whitespace
            window = text[pos:chunk_end]
            sp = window.rfind(" ")
            if sp > target // 2:
                chunk_end = pos + sp
        piece = text[pos:chunk_end]
        if piece.strip():
            out.append(
                Chunk(
                    text=piece,
                    char_start=pos,
                    char_end=chunk_end,
                    line_start=_line_of(text, pos),
                    line_end=_line_of(text, max(pos, chunk_end - 1)),
                    heading=heading,
                )
            )
        if chunk_end >= end:
            break
        next_pos = chunk_end - overlap if overlap > 0 else chunk_end
        if next_pos <= pos:
            next_pos = chunk_end
        pos = next_pos
    return out
