"""
Read-only scan for decision-relevant prose the schema cannot hold.

Output: JSON array to stdout for Cowork to reason over.
Does not propose decisions or write anything.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from tasks.lint_theses import DIRECTIVE_PHRASE_PATTERNS

THESES_DIR = os.path.join(_ROOT, "vault", "theses")

_CONJUNCTION_RE = re.compile(r"\b(and|unless|only if|both)\b|\+", re.I)
_REVISION_RE = re.compile(r"\b(raised from|lowered from|changed from)\b", re.I)
_TEMPORARY_RE = re.compile(r"\b(revisit|pending|until)\b", re.I)


def _ticker_from_path(path: str) -> str:
    base = os.path.basename(path)
    return base.replace("_thesis.md", "").upper()


def _line_number_at(text: str, offset: int) -> int:
    return text[:offset].count("\n") + 1


def _review_log_chunk(text: str) -> str:
    idx = text.find("## Review Log")
    if idx < 0:
        return ""
    chunk = text[idx + len("## Review Log") :]
    stop = len(chunk)
    nxt_h2 = re.search(r"\n## ", chunk)
    nxt_region = re.search(r"\n<!-- region:", chunk)
    if nxt_h2:
        stop = min(stop, nxt_h2.start())
    if nxt_region:
        stop = min(stop, nxt_region.start())
    return chunk[:stop]


def _scan_file(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    ticker = _ticker_from_path(path)
    rel = os.path.relpath(path, _ROOT).replace("\\", "/")
    out: list[dict] = []

    fm_end = text.find("\n---\n", 4)
    fm_block = text[: fm_end + 5] if fm_end >= 0 else ""
    body = text[fm_end + 5 :] if fm_end >= 0 else text
    review_chunk = _review_log_chunk(text)

    review_header_idx = text.find("## Review Log")

    for line_no, line in enumerate(fm_block.splitlines(), start=1):
        if "#" not in line:
            continue
        comment = line.split("#", 1)[1] if "#" in line else ""
        if _CONJUNCTION_RE.search(comment):
            key = line.split(":", 1)[0].strip().lstrip("-").strip()
            out.append(
                {
                    "file": rel,
                    "line": line_no,
                    "ticker": ticker,
                    "category": "yaml_comment_conjunction",
                    "quote": line.strip()[:120],
                    "current_frontmatter_key": key or "triggers",
                }
            )
        if _REVISION_RE.search(comment):
            key = line.split(":", 1)[0].strip()
            out.append(
                {
                    "file": rel,
                    "line": line_no,
                    "ticker": ticker,
                    "category": "frontmatter_revision",
                    "quote": line.strip()[:120],
                    "current_frontmatter_key": key,
                }
            )

    chunk_start = review_header_idx + len("## Review Log") if review_header_idx >= 0 else len(text)
    offset = chunk_start
    for raw_line in review_chunk.splitlines(keepends=True):
        file_line_no = _line_number_at(text, offset)
        stripped = raw_line.strip()
        offset += len(raw_line)
        if not stripped.startswith("- "):
            continue
        for pat, implied_key in DIRECTIVE_PHRASE_PATTERNS:
            if pat.search(raw_line):
                out.append(
                    {
                        "file": rel,
                        "line": file_line_no,
                        "ticker": ticker,
                        "category": "review_log_directive",
                        "quote": stripped[:120],
                        "current_frontmatter_key": implied_key,
                    }
                )
                break

    if "trigger_type: ceiling_only" in fm_block or "trigger_type: ceiling_only" in text[:800]:
        offset = chunk_start
        for raw_line in review_chunk.splitlines(keepends=True):
            file_line_no = _line_number_at(text, offset)
            offset += len(raw_line)
            if _TEMPORARY_RE.search(raw_line):
                out.append(
                    {
                        "file": rel,
                        "line": file_line_no,
                        "ticker": ticker,
                        "category": "ceiling_only_temporary",
                        "quote": raw_line.strip()[:120],
                        "current_frontmatter_key": "trigger_type",
                    }
                )
                break

    return out


def gather_candidates(theses_dir: str = THESES_DIR) -> list[dict]:
    paths = sorted(
        p
        for p in glob.glob(os.path.join(theses_dir, "*_thesis.md"))
        if ".bak" not in os.path.basename(p) and "archive" not in p.replace("\\", "/")
    )
    out: list[dict] = []
    for path in paths:
        out.extend(_scan_file(path))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Gather decision candidate sites from vault")
    parser.add_argument("--vault", default=THESES_DIR, help="Theses directory")
    args = parser.parse_args()
    candidates = gather_candidates(args.vault)
    print(json.dumps(candidates, indent=2))


if __name__ == "__main__":
    main()
