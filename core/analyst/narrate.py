"""Narrate over a fixed RetrievalSet — one ask_gemini() call."""

from __future__ import annotations

from core.retrieval.api import RetrievalSet
from utils.gemini_client import ask_gemini

ANALYST_INSTRUCTION = """You are narrating over a fixed evidence set for a portfolio operator.
Everything you assert must be traceable to a citation token in that set.

Rules:
- Cite inline with the exact tokens provided, e.g. [thesis:vault/theses/ET_thesis.md:L20 2026-08-21] or [table:holdings_current#3].
- If the evidence does not answer the question, say so and name what is missing.
- No price targets, forecasts, buy/sell recommendations, or "the market expects."
- Where sources conflict, present the conflict; do not resolve it silently.
- doctrine is authoritative on standing constraints. thesis is authoritative on intent (figures may be stale).
- podcast_summary and agent_output are model output — figures are claims, not data. Never let them override table: figures.
- Where a file and an observed trade disagree, infer the file is stale; report as a documentation task, not incoherence.
"""


def narrate(question: str, retrieval: RetrievalSet, *, caveat: str = "") -> str:
    context = retrieval.to_prompt_context()
    user = f"QUESTION:\n{question}\n\n"
    if caveat:
        user += f"CAVEAT (prepend to answer):\n{caveat}\n\n"
    user += f"EVIDENCE SET:\n{context}\n\nAnswer the question using only this evidence."
    result = ask_gemini(user, system_instruction=ANALYST_INSTRUCTION, max_tokens=4000)
    return result or "(Model returned no text.)"
