"""
PortfolioStore column-casing contract (2026-08-31 vault-sync regression).

`get_holdings_current()` etc. promise Sheets-cased frames regardless of
backend. That promise held only by coincidence while `STORE_PRIMARY=sheets`
-- SqlitePortfolioStore stored whatever casing a writer last used, and
`core/thesis_sync_data.py` hit `KeyError: 'Ticker'` when it happened to be
snake_case. `core/store/column_normalize.py` is the fix; these tests are
the contract enforcement that would have caught it on 2026-08-21.
"""

from __future__ import annotations

import os
import sqlite3
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from core.store.column_normalize import normalize_dataframe_columns


# ---------------------------------------------------------------------------
# Fast, offline: reproduces the exact 2026-08-21 regression against an
# isolated temp DB. No network, no credentials, always runs.
# ---------------------------------------------------------------------------


def _reset_engine_cache():
    """`get_engine()` caches a module-level singleton keyed on nothing but
    call order -- clearing it forces the next call to rebuild against
    whatever config.SQLITE_DB_PATH currently is. Must run at teardown too,
    or a later test in the same session silently inherits a temp-DB engine
    pointed at a directory pytest has already deleted."""
    import core.store.models as models

    models._engine = None
    models._SessionLocal = None


@pytest.fixture()
def sqlite_store(tmp_path, monkeypatch):
    db = tmp_path / "column_contract_test.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db))
    monkeypatch.setattr(config, "SQLITE_DB_PATH", db)
    _reset_engine_cache()
    from core.store.models import get_engine

    get_engine()  # create tables

    conn = sqlite3.connect(str(db))
    # Deliberately snake_case, matching fetch_positions()'s real shape --
    # this is the exact write-path casing that caused the outage.
    conn.execute(
        "INSERT INTO holdings_current (ticker, payload_json) VALUES (?, ?)",
        (
            "UNH",
            '{"ticker":"UNH","market_value":21587.5,"weight":0.0359,'
            '"cost_basis":19723.77,"unrealized_gl":1863.73,'
            '"unrealized_gl_pct":0.0945,"tax_treatment":"taxable"}',
        ),
    )
    conn.commit()
    conn.close()

    from core.store.sqlite_store import SqlitePortfolioStore

    try:
        yield SqlitePortfolioStore()
    finally:
        _reset_engine_cache()


def test_holdings_current_normalizes_snake_case_write(sqlite_store):
    """The exact 2026-08-21 regression: a snake_case row must read back
    Sheets-cased, not raise KeyError('Ticker') downstream."""
    df = sqlite_store.get_holdings_current()
    assert "Ticker" in df.columns
    assert "ticker" not in df.columns
    assert "Market Value" in df.columns
    assert df.loc[df["Ticker"] == "UNH", "Market Value"].iloc[0] == 21587.5


def test_holdings_current_keeps_unrealized_gl_and_pct_distinct(sqlite_store):
    """Regression guard: an earlier version of the normalizer collapsed
    'Unrealized G/L' and 'Unrealized G/L %' onto the same loose key and
    silently dropped one via a duplicate-column rename."""
    df = sqlite_store.get_holdings_current()
    assert not df.columns.duplicated().any()
    assert "Unrealized G/L" in df.columns
    assert "Unrealized G/L %" in df.columns
    row = df[df["Ticker"] == "UNH"].iloc[0]
    assert row["Unrealized G/L"] == 1863.73
    assert row["Unrealized G/L %"] == 0.0945


def test_holdings_current_preserves_unmapped_extra_column(sqlite_store):
    """tax_treatment has no Sheets counterpart -- must pass through, not drop."""
    df = sqlite_store.get_holdings_current()
    assert "tax_treatment" in df.columns


def test_holdings_current_idempotent_on_already_correct_row(tmp_path, monkeypatch):
    """A row already written Sheets-cased (e.g. by sync-from-sheets) must
    not be double-mangled."""
    db = tmp_path / "idempotent_test.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(db))
    monkeypatch.setattr(config, "SQLITE_DB_PATH", db)
    _reset_engine_cache()
    from core.store.models import get_engine

    get_engine()
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO holdings_current (ticker, payload_json) VALUES (?, ?)",
        ("VST", '{"Ticker":"VST","Market Value":1000,"Weight":0.02}'),
    )
    conn.commit()
    conn.close()

    from core.store.sqlite_store import SqlitePortfolioStore

    try:
        df = SqlitePortfolioStore().get_holdings_current()
        assert list(df.columns).count("Ticker") == 1
        assert df.loc[df["Ticker"] == "VST", "Market Value"].iloc[0] == 1000
    finally:
        _reset_engine_cache()


def test_normalize_dataframe_columns_raises_on_colliding_canonical_list():
    """Safety net: if a future canonical list has two names that collapse
    onto the same loose key, refuse rather than silently produce a
    duplicate-column rename."""
    df = pd.DataFrame([{"foo_pct": 1}])
    with pytest.raises(ValueError, match="collide"):
        normalize_dataframe_columns(df, ["Foo %", "Foo Pct"])


@pytest.mark.parametrize(
    "cols_name",
    [
        "POSITION_COLUMNS",
        "TRANSACTION_COLUMNS",
        "GL_COLUMNS",
        "TRADE_LOG_COLUMNS",
        "ROTATION_REVIEW_COLUMNS",
        "TAX_CONTROL_LOTS_COLUMNS",
    ],
)
def test_canonical_column_lists_have_no_loose_key_collisions(cols_name):
    """Every live canonical column list must be collision-free under the
    loose-key scheme -- this is what test_normalize_dataframe_columns_
    raises_on_colliding_canonical_list actually protects in production."""
    from core.store.column_normalize import _loose_key

    cols = getattr(config, cols_name)
    seen: dict[str, str] = {}
    for c in cols:
        key = _loose_key(c)
        assert key not in seen or seen[key] == c, (
            f"{cols_name}: {seen.get(key)!r} and {c!r} collide on {key!r}"
        )
        seen[key] = c


# ---------------------------------------------------------------------------
# Live cross-backend parity: the literal ask -- SheetsPortfolioStore,
# SqlitePortfolioStore and DualPortfolioStore must return an identical
# column set for every Protocol read method. Needs live Sheets credentials;
# skips cleanly if unavailable rather than failing CI elsewhere.
# ---------------------------------------------------------------------------

_READ_METHODS_AND_COLUMNS = [
    ("get_holdings_current", "POSITION_COLUMNS"),
    ("get_transactions", "TRANSACTION_COLUMNS"),
    ("get_trade_log", "TRADE_LOG_COLUMNS"),
    ("get_realized_gl", "GL_COLUMNS"),
    ("get_rotation_review", "ROTATION_REVIEW_COLUMNS"),
    ("get_tax_control_lots", "TAX_CONTROL_LOTS_COLUMNS"),
]


def _sheets_store_or_skip():
    try:
        from core.store.sheets_store import SheetsPortfolioStore

        store = SheetsPortfolioStore()
        store.get_holdings_current()  # touch it now; fail fast if unreachable
        return store
    except Exception as e:  # pragma: no cover - environment-dependent
        pytest.skip(f"Sheets unreachable in this environment: {e}")


_KNOWN_NON_CASING_DRIFT = {
    # trade_log's SQLite mirror predates the RSI/Trend/MA200 column rename
    # to *_At_Decision and the 2026-08-27 Proposed_Bet/Rationale_* addition
    # (config.py TRADE_LOG_COLUMNS comment). Real staleness, not a casing
    # bug -- normalize_dataframe_columns has no business guessing that
    # "Sell RSI" and "Sell_RSI_At_Decision" are the same field. Flagged
    # separately (state.md), not fixed here: gather_thesis_sync_data()'s
    # trade_log frame is unused (`_trade_log_df`), so this doesn't block
    # vault sync -- the bug this test file exists for is holdings_current.
    "get_trade_log": "trade_log SQLite mirror predates current Sheets schema (name drift, not casing)",
}


@pytest.mark.parametrize("method_name, cols_const", _READ_METHODS_AND_COLUMNS)
def test_sheets_and_sqlite_stores_agree_on_column_set(method_name, cols_const):
    """The contract the Protocol implies but never enforced. This is what
    would have caught the 2026-08-21 regression the day it happened."""
    if method_name in _KNOWN_NON_CASING_DRIFT:
        pytest.xfail(_KNOWN_NON_CASING_DRIFT[method_name])
    sheets = _sheets_store_or_skip()
    from core.store.sqlite_store import SqlitePortfolioStore

    sqlite = SqlitePortfolioStore()

    sheets_df = getattr(sheets, method_name)()
    sqlite_df = getattr(sqlite, method_name)()

    canonical = set(getattr(config, cols_const))
    sheets_cols = set(sheets_df.columns)
    sqlite_cols = set(sqlite_df.columns)

    # Every canonical column must be present on both sides. Extra columns
    # (e.g. sqlite's tax_treatment) are fine on either side -- the contract
    # is "the canonical shape is honored," not "no backend may know more."
    missing_sheets = canonical - sheets_cols
    missing_sqlite = canonical - sqlite_cols
    assert not missing_sheets, f"{method_name}: Sheets missing {missing_sheets}"
    assert not missing_sqlite, f"{method_name}: SQLite missing {missing_sqlite}"


def test_dual_store_read_matches_its_active_primary():
    """DualPortfolioStore.get_holdings_current() must match whichever
    backend STORE_PRIMARY actually points at -- not silently diverge."""
    from core.store.dual_store import DualPortfolioStore

    dual = DualPortfolioStore()
    primary = (config.STORE_PRIMARY or "sheets").strip().lower()
    reference = dual.sqlite if primary == "sqlite" else _sheets_store_or_skip()

    dual_cols = set(dual.get_holdings_current().columns)
    reference_cols = set(reference.get_holdings_current().columns)
    canonical = set(config.POSITION_COLUMNS)

    assert canonical.issubset(dual_cols)
    assert dual_cols == reference_cols
