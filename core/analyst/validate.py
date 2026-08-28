"""Citation validation and forecast-language backstop."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from core.retrieval.api import RetrievalSet

_CITATION_RE = re.compile(r"\[[^\]]+\]")
_FORECAST_RE = re.compile(
    r"\b(price target|fair value|we expect|should reach|will likely|is poised to|undervalued at)\b",
    re.I,
)


@dataclass
class ValidationResult:
    status: Literal["VALIDATION_PASSED", "VALIDATION_FAILED"]
    cited_tokens: list[str] = field(default_factory=list)
    fabricated_tokens: list[str] = field(default_factory=list)
    coverage_pct: float = 0.0
    forecast_flags: list[str] = field(default_factory=list)


def _paragraphs(text: str) -> list[str]:
    blocks = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return blocks or ([text.strip()] if text.strip() else [])


def _extract_citations(answer: str) -> list[str]:
    """Pull citation tokens; split comma-separated tokens inside one bracket."""
    tokens: list[str] = []
    for bracket in _CITATION_RE.findall(answer):
        inner = bracket[1:-1].strip()
        if "," in inner and all(
            part.strip().startswith(("table:", "thesis:", "digest:", "transcript:", "podcast_summary:", "agent_output:", "doctrine:", "research:"))
            for part in inner.split(",")
        ):
            tokens.extend(f"[{part.strip()}]" for part in inner.split(",") if part.strip())
        else:
            tokens.append(bracket)
    return tokens


def validate_answer(answer: str, retrieval: RetrievalSet) -> ValidationResult:
    valid = retrieval.citation_tokens()
    cited = _extract_citations(answer)
    fabricated = [t for t in cited if t not in valid]

    paragraphs = _paragraphs(answer)
    cited_paras = sum(1 for p in paragraphs if _CITATION_RE.search(p))
    coverage = (cited_paras / len(paragraphs) * 100.0) if paragraphs else 0.0

    forecast_flags = _FORECAST_RE.findall(answer)

    status: Literal["VALIDATION_PASSED", "VALIDATION_FAILED"] = (
        "VALIDATION_FAILED" if fabricated else "VALIDATION_PASSED"
    )
    return ValidationResult(
        status=status,
        cited_tokens=cited,
        fabricated_tokens=fabricated,
        coverage_pct=coverage,
        forecast_flags=forecast_flags,
    )
