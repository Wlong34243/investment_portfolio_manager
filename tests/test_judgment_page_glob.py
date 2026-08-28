"""Judgment artifact glob — catches timestamp-prefixed lifecycle files."""

from pathlib import Path

from ui.judgment_artifacts import list_lifecycle_artifacts, parse_lifecycle_ticker


def test_lifecycle_glob_matches_timestamp_prefix():
    name = "2026-08-28_1405_lifecycle_unh.md"
    ticker = parse_lifecycle_ticker(Path(name))
    assert ticker == "UNH"


def test_lifecycle_glob_not_old_pattern():
    """Old glob lifecycle_*.md would miss timestamp-prefixed names."""
    old = list(Path(".").glob("lifecycle_*.md")) if False else []
    name = "2026-08-28_1405_lifecycle_unh.md"
    assert not name.startswith("lifecycle_")
    assert parse_lifecycle_ticker(Path(name)) == "UNH"


def test_list_lifecycle_artifacts_from_fixture(tmp_path, monkeypatch):
    out = tmp_path / "agent_outputs" / "judgment"
    out.mkdir(parents=True)
    (out / "2026-08-28_1405_lifecycle_unh.md").write_text("**legs:** 23\n", encoding="utf-8")
    (out / "2026-08-28_1405_lifecycle_unh.json").write_text(
        '{"ticker":"UNH","legs":23,"single_entry_return_pct":0.1}', encoding="utf-8"
    )
    import ui.judgment_artifacts as ja

    monkeypatch.setattr(ja, "OUTPUT_DIR", out)
    items = list_lifecycle_artifacts()
    assert len(items) == 1
    assert items[0]["ticker"] == "UNH"
    assert items[0]["legs"] == 23


def test_list_lifecycle_dedupes_ticker(tmp_path, monkeypatch):
    out = tmp_path / "agent_outputs" / "judgment"
    out.mkdir(parents=True)
    old = out / "2026-08-27_1200_lifecycle_unh.md"
    new = out / "2026-08-28_1405_lifecycle_unh.md"
    old.write_text("**legs:** 20\n", encoding="utf-8")
    new.write_text("**legs:** 23\n", encoding="utf-8")
    import ui.judgment_artifacts as ja

    monkeypatch.setattr(ja, "OUTPUT_DIR", out)
    items = list_lifecycle_artifacts()
    assert len(items) == 1
    assert items[0]["ticker"] == "UNH"
    assert items[0]["legs"] == 23
