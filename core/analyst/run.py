"""Analyst orchestration — plan → retrieve → narrate → validate → write."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.analyst.narrate import narrate
from core.analyst.plan import QuestionPlan, plan_question
from core.analyst.validate import ValidationResult, validate_answer
from core.retrieval.api import RetrievalSet, retrieve
from core.store.evidence import EVIDENCE_GATE_DAYS, evidence_status

OUTPUT_DIR = Path("agent_outputs/analyst")


def _signal_gate_caveat(plan: QuestionPlan) -> str:
    if "signal_events_for_ticker" not in plan.template_ids:
        return ""
    ev = evidence_status()
    if ev.get("gate_met"):
        return ""
    clean = int(ev.get("clean_trading_days") or 0)
    first = ev.get("evidence_first_accrual_date") or "unknown"
    remaining = max(0, EVIDENCE_GATE_DAYS - clean)
    return (
        f"Signal capture began {first}; only {clean} of {EVIDENCE_GATE_DAYS} trading days "
        f"accrued ({remaining} remaining). Signal evidence is partial, not a full record."
    )


def retrieve_for_plan(plan: QuestionPlan) -> RetrievalSet:
    return retrieve(
        queries=plan.template_calls(),
        corpus=plan.corpus_queries or None,
        label=plan.label,
        caller="analyst",
    )


def run_ask(
    question: str,
    *,
    since: Optional[date] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    plan = plan_question(question, since=since)
    if plan.is_empty:
        return {
            "status": "REFUSED",
            "reason": "No ticker or portfolio intent resolved — refusing bare LLM answer.",
            "plan": plan,
            "retrieval": None,
            "answer": None,
        }

    retrieval = retrieve_for_plan(plan)
    caveat = _signal_gate_caveat(plan)

    if dry_run:
        return {
            "status": "DRY_RUN",
            "plan": plan,
            "retrieval": retrieval,
            "caveat": caveat,
            "context_preview": retrieval.to_prompt_context()[:4000],
        }

    answer = narrate(plan.question, retrieval, caveat=caveat)
    validation = validate_answer(answer, retrieval)

    return {
        "status": validation.status,
        "plan": plan,
        "retrieval": retrieval,
        "answer": answer,
        "validation": validation,
        "caveat": caveat,
    }


def write_report(result: dict[str, Any], *, dry_run: bool = False) -> str | Path:
    plan: QuestionPlan = result["plan"]
    retrieval: RetrievalSet | None = result.get("retrieval")
    validation: ValidationResult | None = result.get("validation")

    lines = [
        f"# Analyst — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"**question:** {plan.question}",
        f"**status:** {result.get('status')}",
    ]
    if retrieval:
        lines.append(f"**retrieval_hash:** `{retrieval.retrieval_hash}`")
        lines.append(f"**templates:** {', '.join(plan.template_ids) or '—'}")
        lines.append(f"**tickers:** {', '.join(plan.tickers) or '—'}")
    if validation:
        lines.append(f"**citation_coverage:** {validation.coverage_pct:.0f}%")
        lines.append(f"**validation:** {validation.status}")
        if validation.fabricated_tokens:
            lines.append(f"**fabricated_tokens:** {validation.fabricated_tokens}")
        if validation.forecast_flags:
            lines.append(f"**forecast_flags:** {validation.forecast_flags}")
    lines.append("")
    if result.get("caveat"):
        lines.append(f"> {result['caveat']}")
        lines.append("")
    if result.get("answer"):
        lines.append(result["answer"])
    elif result.get("reason"):
        lines.append(result["reason"])
    elif result.get("context_preview"):
        lines.append("## Dry-run context preview")
        lines.append("```")
        lines.append(result["context_preview"])
        lines.append("```")

    text = "\n".join(lines)
    if dry_run or result.get("status") in ("DRY_RUN", "REFUSED"):
        return text

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    h = (retrieval.retrieval_hash[:12] if retrieval else "nohash")
    path = OUTPUT_DIR / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}_{plan.slug}_{h}.md"
    path.write_text(text, encoding="utf-8")
    return path
