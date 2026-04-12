"""Smoke test for core/bundle.py hashing and round-trip integrity."""
import json
from pathlib import Path

import pytest

from core.bundle import build_bundle, write_bundle, load_bundle


def _find_sample_csv() -> Path | None:
    """Return the most recent Schwab positions CSV in the repo root, or None."""
    root = Path(__file__).parent.parent
    candidates = sorted(root.glob("*Positions*.csv"), reverse=True)
    return candidates[0] if candidates else None


def test_bundle_roundtrip(tmp_path, monkeypatch):
    """Build → write → load must produce the same hash."""
    monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)

    sample_csv = _find_sample_csv()
    if sample_csv is None:
        pytest.skip("No Schwab positions CSV found in repo root")

    bundle = build_bundle(csv_path=sample_csv, cash_manual=10000.0)

    assert len(bundle.bundle_hash) == 64, "bundle_hash must be a 64-char SHA256 hex string"
    assert bundle.position_count > 0, "bundle must contain at least one position"
    assert bundle.total_value > 0, "total_value must be positive"

    path = write_bundle(bundle)
    assert path.exists(), "write_bundle must create a file"

    loaded = load_bundle(path)  # raises ValueError on hash mismatch
    assert loaded["bundle_hash"] == bundle.bundle_hash, "round-trip hash must match"


def test_bundle_hash_tamper_detection(tmp_path, monkeypatch):
    """Mutating any field after writing must cause load_bundle to raise."""
    monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)

    sample_csv = _find_sample_csv()
    if sample_csv is None:
        pytest.skip("No Schwab positions CSV found in repo root")

    bundle = build_bundle(csv_path=sample_csv, cash_manual=10000.0)
    path = write_bundle(bundle)

    # Tamper: change total_value
    data = json.loads(path.read_text())
    data["total_value"] = 999999999.99
    path.write_text(json.dumps(data, indent=2))

    with pytest.raises(ValueError, match="hash"):
        load_bundle(path)


def test_bundle_missing_hash_field(tmp_path):
    """load_bundle must raise on a bundle that lacks the bundle_hash field."""
    bad = tmp_path / "bad_bundle.json"
    bad.write_text(json.dumps({"total_value": 1.0}))

    with pytest.raises(ValueError, match="bundle_hash"):
        load_bundle(bad)


def test_cash_manual_always_present(monkeypatch, tmp_path):
    """CASH_MANUAL row must exist even when cash_manual=0."""
    monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)

    sample_csv = _find_sample_csv()
    if sample_csv is None:
        pytest.skip("No Schwab positions CSV found in repo root")

    bundle = build_bundle(csv_path=sample_csv, cash_manual=0.0)
    cash_rows = [p for p in bundle.positions if p["ticker"] == "CASH_MANUAL"]

    assert len(cash_rows) == 1, "exactly one CASH_MANUAL row must exist"
    assert cash_rows[0]["quantity"] == 0.0
    assert cash_rows[0]["price_source"] == "manual"


def test_price_source_on_every_position(monkeypatch, tmp_path):
    """Every position (including CASH_MANUAL) must carry a price_source field."""
    monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)

    sample_csv = _find_sample_csv()
    if sample_csv is None:
        pytest.skip("No Schwab positions CSV found in repo root")

    bundle = build_bundle(csv_path=sample_csv, cash_manual=5000.0)

    missing = [p["ticker"] for p in bundle.positions if "price_source" not in p]
    assert not missing, f"positions missing price_source: {missing}"

    valid_sources = {"yfinance_live", "csv_fallback", "manual"}
    invalid = [
        (p["ticker"], p["price_source"])
        for p in bundle.positions
        if p["price_source"] not in valid_sources
    ]
    assert not invalid, f"invalid price_source values: {invalid}"
