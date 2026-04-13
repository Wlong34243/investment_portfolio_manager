"""Smoke test for core/bundle.py hashing and round-trip integrity."""
import json
from pathlib import Path

import pytest
import pandas as pd

from core.bundle import build_bundle, write_bundle, load_bundle, SOURCE_CSV, SOURCE_AUTO, SOURCE_SCHWAB


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

    bundle = build_bundle(source=SOURCE_CSV, csv_path=sample_csv, cash_manual=10000.0)

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

    bundle = build_bundle(source=SOURCE_CSV, csv_path=sample_csv, cash_manual=10000.0)
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

    bundle = build_bundle(source=SOURCE_CSV, csv_path=sample_csv, cash_manual=0.0)
    cash_rows = [p for p in bundle.positions if p["ticker"] == "CASH_MANUAL"]

    assert len(cash_rows) == 1, "exactly one CASH_MANUAL row must exist"
    assert cash_rows[0]["quantity"] == 1.0 # New logic in build_bundle sets qty=1.0, price=cash
    assert cash_rows[0]["price_source"] == "manual"


def test_price_source_on_every_position(monkeypatch, tmp_path):
    """Every position (including CASH_MANUAL) must carry a price_source field."""
    monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)

    sample_csv = _find_sample_csv()
    if sample_csv is None:
        pytest.skip("No Schwab positions CSV found in repo root")

    bundle = build_bundle(source=SOURCE_CSV, csv_path=sample_csv, cash_manual=5000.0)

    missing = [p["ticker"] for p in bundle.positions if "price_source" not in p]
    assert not missing, f"positions missing price_source: {missing}"

    valid_sources = {"yfinance_live", "csv_fallback", "manual", "schwab_quote"}
    invalid = [
        (p["ticker"], p["price_source"])
        for p in bundle.positions
        if p["price_source"] not in valid_sources
    ]
    assert not invalid, f"invalid price_source values: {invalid}"


# --- Phase 4 Dispatcher Tests ---

def test_invalid_source_raises():
    with pytest.raises(ValueError, match="Invalid source"):
        build_bundle(source="garbage", csv_path=None, cash_manual=0.0)


def test_csv_source_requires_path():
    with pytest.raises(ValueError, match="requires csv_path"):
        build_bundle(source=SOURCE_CSV, csv_path=None, cash_manual=0.0)


def test_auto_falls_back_to_csv_when_schwab_fails(
    tmp_path, monkeypatch
):
    '''
    Simulate Schwab auth failure and verify auto mode falls back
    to CSV with an enrichment_error recording the fallback.
    '''
    monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)

    sample_csv = _find_sample_csv()
    if sample_csv is None:
        pytest.skip("sample CSV not present")

    # Monkeypatch _build_from_schwab to raise RuntimeError, simulating
    # a missing token or expired refresh scenario
    def fake_schwab(cash_manual):
        raise RuntimeError("Simulated Schwab auth failure")
    monkeypatch.setattr(
        "core.bundle._build_from_schwab", fake_schwab
    )

    bundle = build_bundle(
        source=SOURCE_AUTO,
        csv_path=sample_csv,
        cash_manual=10000.0,
    )
    assert bundle.data_source == "csv"
    assert any("fell back to CSV" in err for err in bundle.enrichment_errors)
    assert bundle.position_count > 0


def test_auto_raises_when_schwab_fails_and_no_csv(
    tmp_path, monkeypatch
):
    '''
    Auto mode with no csv fallback path must raise rather than
    producing an empty bundle.
    '''
    def fake_schwab(cash_manual):
        raise RuntimeError("Simulated Schwab failure")
    monkeypatch.setattr("core.bundle._build_from_schwab", fake_schwab)

    with pytest.raises(RuntimeError, match="no csv_path provided"):
        build_bundle(
            source=SOURCE_AUTO,
            csv_path=None,
            cash_manual=10000.0,
        )


def test_schwab_path_sets_data_source(monkeypatch, tmp_path):
    '''
    When the Schwab path is taken, the bundle's data_source field
    must be 'schwab' and the source_fingerprint must be non-empty.
    '''
    monkeypatch.setattr("core.bundle.BUNDLE_DIR", tmp_path)

    # Fake _build_from_schwab to return a minimal valid DataFrame
    def fake_schwab(cash_manual):
        df = pd.DataFrame([
            {
                "ticker": "UNH",
                "description": "UnitedHealth",
                "quantity": 10.0,
                "price": 500.0,
                "market_value": 5000.0,
                "cost_basis": 4500.0,
                "asset_class": "Equities",
                "asset_strategy": "US Large Cap",
                "is_cash": False,
                "price_source": "schwab_quote",
                "tax_treatment": "taxable",
            }
        ])
        return df, "abc1234567890def", []

    monkeypatch.setattr("core.bundle._build_from_schwab", fake_schwab)

    bundle = build_bundle(
        source=SOURCE_SCHWAB,
        csv_path=None,
        cash_manual=10000.0,
    )
    assert bundle.data_source == "schwab"
    assert bundle.data_source_fingerprint == "abc1234567890def"
    assert bundle.tax_treatment_available is True
