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


# --- CSV fallback path smoke coverage ---
#
# The CSV parser is the disaster-recovery path for when the Schwab API is
# unavailable. An AttributeError on config.ETF_KEYWORDS reached runtime
# uncaught (fixed reactively by defining the constant in config.py) precisely
# because this path had no smoke coverage of its own -- only exercised
# indirectly through core.bundle's CSV-source tests above, which don't touch
# get_sector_fast()/find_account_sections() directly.

def test_csv_parser_imports_and_constants_resolve():
    """utils/csv_parser.py must import cleanly, and every module-level
    config.* constant it references must resolve -- this is exactly the
    AttributeError class of bug (config.ETF_KEYWORDS) that reached runtime
    uncaught."""
    import config
    from utils import csv_parser  # noqa: F401 - import must not raise

    for name in ("ACCOUNT_SECTION_PATTERNS", "ETF_KEYWORDS", "CASH_TICKERS", "DEFAULT_CASH_YIELD_PCT"):
        assert hasattr(config, name), f"config.{name} referenced by csv_parser.py but not defined"


def test_csv_parser_fixture_returns_populated_positions():
    """A parse run against an existing repo fixture must return positions
    with ticker/market_value/cost_basis populated -- no new test data."""
    from utils.csv_parser import parse_schwab_csv

    sample_csv = _find_sample_csv()
    if sample_csv is None:
        pytest.skip("No Schwab positions CSV found in repo root")

    df = parse_schwab_csv(sample_csv.read_bytes())

    assert not df.empty, "parser must return at least one position"
    for col in ("ticker", "market_value", "cost_basis"):
        assert col in df.columns, f"missing column: {col}"
    assert df["ticker"].notna().all()
    assert (df["market_value"] > 0).any(), "at least one position must carry a positive market value"


def test_csv_parser_aggregates_multi_account_positions():
    """The same ticker held in multiple accounts must be summed, not
    duplicated -- find_account_sections()'s reason for existing.
    All-Accounts-Positions-2026-04-07-113205.csv holds AMD in three accounts
    (10 + 8 + 27 shares); the aggregated row must total 45."""
    from utils.csv_parser import parse_schwab_csv

    root = Path(__file__).parent.parent
    fixture = root / "All-Accounts-Positions-2026-04-07-113205.csv"
    if not fixture.exists():
        pytest.skip("Expected multi-account fixture not present")

    df = parse_schwab_csv(fixture.read_bytes())
    amd_rows = df[df["ticker"] == "AMD"]

    assert len(amd_rows) == 1, "multi-account AMD must aggregate to a single row, not one per account"
    assert amd_rows.iloc[0]["quantity"] == pytest.approx(45.0)


def test_csv_parser_preserves_fractional_shares():
    """Fractional share quantities must never be rounded (the parser's own
    stated invariant). Same fixture: GOOG is split 10 + 90.2781 shares across
    two accounts, aggregating to 100.2781 -- rounding either the per-account
    or the aggregated quantity would silently misstate the position."""
    from utils.csv_parser import parse_schwab_csv

    root = Path(__file__).parent.parent
    fixture = root / "All-Accounts-Positions-2026-04-07-113205.csv"
    if not fixture.exists():
        pytest.skip("Expected multi-account fixture not present")

    df = parse_schwab_csv(fixture.read_bytes())
    goog_rows = df[df["ticker"] == "GOOG"]

    assert len(goog_rows) == 1
    assert goog_rows.iloc[0]["quantity"] == pytest.approx(100.2781)


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
        return df, "abc1234567890def", [], []

    monkeypatch.setattr("core.bundle._build_from_schwab", fake_schwab)

    bundle = build_bundle(
        source=SOURCE_SCHWAB,
        csv_path=None,
        cash_manual=10000.0,
    )
    assert bundle.data_source == "schwab"
    assert bundle.data_source_fingerprint == "abc1234567890def"
    assert bundle.tax_treatment_available is True
