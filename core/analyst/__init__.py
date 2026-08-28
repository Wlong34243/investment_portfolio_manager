"""Grounded Q&A over retrieval + corpus — plan, narrate, validate."""

from core.analyst.plan import QuestionPlan, plan_question
from core.analyst.run import run_ask, write_report
from core.analyst.validate import ValidationResult, validate_answer

__all__ = [
    "QuestionPlan",
    "ValidationResult",
    "plan_question",
    "run_ask",
    "validate_answer",
    "write_report",
]
