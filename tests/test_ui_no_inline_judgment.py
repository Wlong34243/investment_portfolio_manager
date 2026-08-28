"""ui/ must never call retrieve_campaign or build_campaign inline."""

from pathlib import Path


def test_ui_no_inline_judgment_compute():
    ui_root = Path("ui")
    forbidden = ("retrieve_campaign", "build_campaign")
    allowed = {"judgment_artifacts.py"}  # reads artifacts only
    hits: list[str] = []
    for path in ui_root.glob("*.py"):
        if path.name in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                hits.append(f"{path.name}: {token}")
    assert hits == [], f"inline judgment compute in ui/: {hits}"
