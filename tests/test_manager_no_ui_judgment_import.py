"""CLI must not import ui.judgment_artifacts."""

from pathlib import Path


def test_manager_does_not_import_ui_judgment_artifacts():
    text = Path("manager.py").read_text(encoding="utf-8")
    assert "ui.judgment_artifacts" not in text
