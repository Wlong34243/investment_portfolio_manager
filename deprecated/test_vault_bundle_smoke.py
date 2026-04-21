"""Smoke test for core/vault_bundle.py and core/composite_bundle.py."""
import json
from pathlib import Path
import pytest

from core.vault_bundle import (
    build_vault_bundle, write_vault_bundle, load_vault_bundle,
    THESES_DIR, VAULT_DIR,
)
from core.composite_bundle import (
    build_composite_bundle, write_composite_bundle, load_composite_bundle,
)
from core.bundle import build_bundle, write_bundle

SAMPLE_CSV = Path("-Positions-2025-12-31-082029.csv")

@pytest.fixture
def sample_thesis(tmp_path, monkeypatch):
    """Write a minimal thesis file and point THESES_DIR at tmp."""
    theses = tmp_path / "theses"
    theses.mkdir()
    monkeypatch.setattr("core.vault_bundle.THESES_DIR", theses)
    monkeypatch.setattr("core.vault_bundle.VAULT_BUNDLE_DIR", tmp_path)
    (theses / "UNH_thesis.md").write_text(
        "# UNH — Investment Thesis\n\n"
        "## Style\nBoring Fundamentals\n\n"
        "## Scaling State\nnext_step: hold\n\n"
        "## Rotation Priority\npriority: medium\n"
    )
    return theses

def test_vault_bundle_roundtrip(sample_thesis, tmp_path, monkeypatch):
    monkeypatch.setattr("core.vault_bundle.VAULT_BUNDLE_DIR", tmp_path)
    monkeypatch.setattr("core.vault_bundle.VAULT_DIR", tmp_path)
    monkeypatch.setattr("core.vault_bundle.TRANSCRIPTS_DIR", tmp_path / "transcripts")
    monkeypatch.setattr("core.vault_bundle.RESEARCH_DIR", tmp_path / "research")
    bundle = build_vault_bundle(ticker_list=["UNH", "GOOG"])
    assert len(bundle.vault_hash) == 64
    assert "UNH" in bundle.theses_present
    assert "GOOG" in bundle.theses_missing
    path = write_vault_bundle(bundle)
    loaded = load_vault_bundle(path)
    assert loaded["vault_hash"] == bundle.vault_hash

def test_vault_hash_tamper_detection(sample_thesis, tmp_path, monkeypatch):
    monkeypatch.setattr("core.vault_bundle.VAULT_BUNDLE_DIR", tmp_path)
    monkeypatch.setattr("core.vault_bundle.VAULT_DIR", tmp_path)
    monkeypatch.setattr("core.vault_bundle.TRANSCRIPTS_DIR", tmp_path / "transcripts")
    monkeypatch.setattr("core.vault_bundle.RESEARCH_DIR", tmp_path / "research")
    bundle = build_vault_bundle(ticker_list=["UNH"])
    path = write_vault_bundle(bundle)
    data = json.loads(path.read_text())
    data["vault_doc_count"] = 999
    path.write_text(json.dumps(data, indent=2))
    with pytest.raises(ValueError, match="hash"):
        load_vault_bundle(path)

def test_composite_bundle_roundtrip(sample_thesis, tmp_path, monkeypatch):
    if not SAMPLE_CSV.exists():
        pytest.skip("sample CSV not present")
    monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)
    monkeypatch.setattr("core.vault_bundle.VAULT_BUNDLE_DIR", tmp_path)
    monkeypatch.setattr("core.vault_bundle.VAULT_DIR", tmp_path)
    monkeypatch.setattr("core.vault_bundle.TRANSCRIPTS_DIR", tmp_path / "transcripts")
    monkeypatch.setattr("core.vault_bundle.RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr("core.composite_bundle.COMPOSITE_BUNDLE_DIR", tmp_path)
    market = build_bundle(csv_path=SAMPLE_CSV, cash_manual=10000.0)
    market_path = write_bundle(market)
    vault = build_vault_bundle(ticker_list=["UNH"])
    vault_path = write_vault_bundle(vault)
    composite = build_composite_bundle(market_path, vault_path)
    assert len(composite.composite_hash) == 64
    comp_path = write_composite_bundle(composite)
    loaded = load_composite_bundle(comp_path)
    assert loaded["composite_hash"] == composite.composite_hash
