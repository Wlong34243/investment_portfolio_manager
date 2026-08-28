"""Natural-language question → deterministic retrieval plan (no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from core.retrieval.api import CorpusQuery, TemplateCall
from utils.moment_windows import load_ticker_aliases

_INTENT_RULES: list[tuple[tuple[str, ...], list[str]]] = [
    (
        ("weight", "holding", "position", "allocation", "how much", "size"),
        ["holdings_current", "thesis_state_for_ticker"],
    ),
    (
        ("bought", "sold", "buy", "sell", "when did i", "transaction", "trade"),
        ["position_transactions", "trade_log_for_ticker"],
    ),
    (
        ("lot", "long-term", "long term", "holding period", "days to lt", "cost basis"),
        ["position_lots", "tax_control_lots"],
    ),
    (
        ("realized", "gain", "loss", "tax", "wash"),
        ["position_realized_gl", "tax_control_lots"],
    ),
    (
        ("signal", "trigger", "fired", "crosshair", "near trim", "near add"),
        ["signal_events_for_ticker"],
    ),
    (
        ("p/e", "pe", "multiple", "valuation", "fundamental", "forward"),
        ["fundamentals_series"],
    ),
    (
        ("rotation", "swapped", "rotated", "residual"),
        ["rotation_review_for_ticker", "trade_log_for_ticker"],
    ),
]

_CORPUS_KEYWORDS = (
    "said", "mentioned", "thesis", "why", "podcast", "digest", "project", "lake charles",
)

_STOP_WORDS = frozenset({
    "what", "has", "been", "said", "about", "the", "a", "an", "is", "are", "was", "were",
    "i", "my", "me", "and", "or", "for", "to", "of", "in", "on", "at", "by", "with",
    "when", "did", "how", "much", "why", "that", "this", "any", "have",
})


def _corpus_query_strings(question: str, tickers: list[str], *, corpus_intent: bool) -> list[str]:
    """Extract FTS-friendly phrases; over-retrieve rather than under-retrieve."""
    ql = question.lower()
    queries: list[str] = []

    for m in re.finditer(r"[a-z][a-z']+(?:\s+[a-z][a-z']+)+", ql):
        phrase = m.group(0).strip()
        if phrase.endswith("'s"):
            phrase = phrase[:-2].strip()
        words = [w for w in phrase.split() if w not in _STOP_WORDS]
        if len(words) >= 2:
            queries.append(" ".join(words))

    content = [w for w in re.findall(r"[a-z']+", ql) if w not in _STOP_WORDS and len(w) > 2]
    if content:
        queries.append(" ".join(content[-4:]))

    if tickers and corpus_intent:
        for phrase in ("export terminal", "LNG export"):
            queries.append(phrase)
        aliases = load_ticker_aliases()
        for t in tickers:
            for alias in aliases.get(t, []):
                if len(alias) >= 4:
                    queries.append(alias)
                    break

    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out[:8]

_DATE_SINCE_RE = re.compile(
    r"\bsince\s+(\d{4}-\d{2}-\d{2}|\w+\s+\d{4}|\w+)\b", re.I
)
_DATE_IN_YEAR_RE = re.compile(r"\bin\s+(20\d{2})\b", re.I)
_DATE_EXPLICIT_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


@dataclass
class QuestionPlan:
    question: str
    label: str
    slug: str
    tickers: list[str] = field(default_factory=list)
    since: Optional[date] = None
    until: Optional[date] = None
    template_ids: list[str] = field(default_factory=list)
    corpus_queries: list[CorpusQuery] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.template_ids and not self.corpus_queries

    def template_calls(self) -> list[TemplateCall]:
        calls: list[TemplateCall] = []
        for tid in self.template_ids:
            if tid == "holdings_current":
                calls.append(TemplateCall(tid, {}))
            elif tid in (
                "thesis_state_for_ticker",
                "position_lots",
                "position_realized_gl",
                "fundamentals_series",
                "trade_log_for_ticker",
                "rotation_review_for_ticker",
                "signal_events_for_ticker",
                "tax_control_lots",
                "position_transactions",
            ):
                for t in self.tickers:
                    params: dict[str, Any] = {"ticker": t}
                    if tid in ("position_realized_gl", "fundamentals_series"):
                        params["since"] = self.since
                    if tid == "signal_events_for_ticker":
                        params["since"] = self.since
                        params["until"] = self.until
                    if tid == "position_transactions":
                        params["since"] = self.since
                        params["until"] = self.until
                    calls.append(TemplateCall(tid, params))
        return calls


def _slugify(question: str, tickers: list[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", question.lower())[:48].strip("_")
    if tickers:
        base = f"{'_'.join(tickers[:2]).lower()}_{base}"[:56]
    return base or "question"


def extract_tickers(question: str) -> list[str]:
    aliases = load_ticker_aliases()
    text = question
    upper = question.upper()
    found: list[tuple[int, str]] = []

    for ticker, alias_list in aliases.items():
        if ticker.startswith("_"):
            continue
        if len(ticker) <= 3:
            if not re.search(r"\b" + re.escape(ticker) + r"(?:'s)?\b", text):
                continue
            found.append((text.find(ticker), ticker))
            continue
        if re.search(r"\b" + re.escape(ticker) + r"\b", upper):
            found.append((upper.find(ticker), ticker))
            continue
        for alias in alias_list:
            if len(alias) < 4:
                continue
            m = re.search(r"\b" + re.escape(alias) + r"\b", text, re.I)
            if m:
                found.append((m.start(), ticker))
                break

    found.sort(key=lambda x: x[0])
    out: list[str] = []
    seen: set[str] = set()
    for _, t in found:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def extract_date_range(question: str) -> tuple[Optional[date], Optional[date]]:
    m = _DATE_EXPLICIT_RE.search(question)
    if m:
        try:
            return date.fromisoformat(m.group(1)), None
        except ValueError:
            pass
    m = _DATE_IN_YEAR_RE.search(question)
    if m:
        y = int(m.group(1))
        return date(y, 1, 1), date(y, 12, 31)
    if re.search(r"last quarter", question, re.I):
        today = date.today()
        return today - timedelta(days=90), today
    m = _DATE_SINCE_RE.search(question)
    if m:
        token = m.group(1)
        if re.match(r"20\d{2}-\d{2}-\d{2}", token):
            return date.fromisoformat(token), None
    return None, None


def plan_question(question: str, *, since: Optional[date] = None) -> QuestionPlan:
    q = (question or "").strip()
    tickers = extract_tickers(q)
    since_d, until_d = extract_date_range(q)
    if since:
        since_d = since
    ql = q.lower()

    template_ids: list[str] = []
    for keywords, templates in _INTENT_RULES:
        if any(kw in ql for kw in keywords):
            for t in templates:
                if t not in template_ids:
                    template_ids.append(t)

    corpus_queries: list[CorpusQuery] = []
    corpus_intent = any(kw in ql for kw in _CORPUS_KEYWORDS)

    if tickers:
        if "thesis_state_for_ticker" not in template_ids:
            template_ids.append("thesis_state_for_ticker")
        for qstr in _corpus_query_strings(q, tickers, corpus_intent=corpus_intent or True):
            corpus_queries.append(
                CorpusQuery(
                    query=qstr,
                    tickers=tickers,
                    since=since_d,
                    until=until_d,
                    limit=25,
                )
            )
    elif corpus_intent and q:
        for qstr in _corpus_query_strings(q, [], corpus_intent=True) or [q]:
            corpus_queries.append(
                CorpusQuery(query=qstr, since=since_d, until=until_d, limit=25)
            )

    if not tickers and not template_ids and not corpus_queries:
        slug = _slugify(q, tickers)
        return QuestionPlan(question=q, label=f"analyst:{slug}", slug=slug)

    slug = _slugify(q, tickers)
    return QuestionPlan(
        question=q,
        label=f"analyst:{slug}",
        slug=slug,
        tickers=tickers,
        since=since_d,
        until=until_d,
        template_ids=template_ids,
        corpus_queries=corpus_queries,
    )
