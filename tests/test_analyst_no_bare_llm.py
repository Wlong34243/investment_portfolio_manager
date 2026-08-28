from unittest.mock import patch

from core.analyst.run import run_ask


def test_empty_plan_never_calls_gemini():
    with patch("core.analyst.narrate.ask_gemini") as mock:
        mock.side_effect = AssertionError("ask_gemini must not be called")
        result = run_ask("what's the weather", dry_run=False)
    assert result["status"] == "REFUSED"
    assert result["answer"] is None
