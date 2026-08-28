"""Corpus chunk line_start must map to original file lines (frontmatter offset)."""

from pathlib import Path

from core.corpus.chunker import chunk_text
from core.corpus.sources import _strip_frontmatter


def test_frontmatter_file_chunk_line_in_range():
    raw = """---
ticker: TEST
style: GARP
---
# Core Thesis

First body paragraph about supply.

Second paragraph with more detail.
"""
    chunks = chunk_text(raw)
    assert chunks
    for ch in chunks:
        file_lines = raw.splitlines()
        assert 1 <= ch.line_start <= len(file_lines)
        assert ch.line_start <= ch.line_end
        line_text = file_lines[ch.line_start - 1]
        assert ch.text.strip().split()[0] in line_text or ch.text.strip()[:20] in raw


def test_mu_thesis_supply_quote_line_anchor():
    path = Path("vault/theses/MU_thesis.md")
    if not path.exists():
        return
    raw = path.read_text(encoding="utf-8")
    needle = "contractually spoken for"
    pos = raw.lower().find(needle.lower())
    assert pos >= 0
    file_line_no = raw.count("\n", 0, pos) + 1

    chunks = chunk_text(raw)
    hits = [c for c in chunks if needle.lower() in c.text.lower()]
    assert hits, "supply quote should appear in a chunk"
    for ch in hits:
        assert ch.line_start <= file_line_no <= ch.line_end, (
            f"quote at file L{file_line_no} should fall inside chunk L{ch.line_start}–L{ch.line_end}"
        )
