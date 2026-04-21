"""
tests/test_tax.py — Unit tests for utils/tax.py pure functions.

Run with:  python -m pytest tests/test_tax.py -v
"""

import sys
import os
from datetime import date, datetime

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.tax import (
    classify_holding_period,
    days_until_long_term,
    reconstruct_lots_fifo,
    Lot,
)


# ---------------------------------------------------------------------------
# classify_holding_period
# ---------------------------------------------------------------------------

class TestClassifyHoldingPeriod:
    """IRS rule: MORE THAN 365 days → long_term; else short_term."""

    def test_exact_365_days_is_short_term(self):
        # 2025 is a non-leap year: Jan 1 2025 → Jan 1 2026 = exactly 365 days
        acq = date(2025, 1, 1)
        ref = date(2026, 1, 1)
        assert (ref - acq).days == 365
        assert classify_holding_period(acq, ref) == "short_term"

    def test_366_days_is_long_term(self):
        # One day past the 365-day boundary
        acq = date(2025, 1, 1)
        ref = date(2026, 1, 2)   # 366 days
        assert (ref - acq).days == 366
        assert classify_holding_period(acq, ref) == "long_term"

    def test_364_days_is_short_term(self):
        # One day before the 365-day boundary
        acq = date(2025, 1, 1)
        ref = date(2025, 12, 31)  # 364 days (2025 is non-leap)
        assert (ref - acq).days == 364
        assert classify_holding_period(acq, ref) == "short_term"

    def test_same_day_buy_sell_is_short_term(self):
        d = date(2025, 3, 15)
        assert classify_holding_period(d, d) == "short_term"

    def test_zero_days_is_short_term(self):
        acq = date(2025, 6, 1)
        ref = date(2025, 6, 1)
        assert classify_holding_period(acq, ref) == "short_term"

    def test_clearly_long_term(self):
        acq = date(2022, 1, 1)
        ref = date(2025, 1, 1)   # ~3 years
        assert classify_holding_period(acq, ref) == "long_term"

    def test_none_acquisition_date_returns_unknown(self):
        assert classify_holding_period(None, date(2025, 1, 1)) == "unknown"

    def test_string_dates_accepted(self):
        assert classify_holding_period("2023-01-01", "2024-01-02") == "long_term"
        assert classify_holding_period("2023-01-01", "2024-01-01") == "short_term"

    def test_datetime_objects_accepted(self):
        acq = datetime(2023, 6, 1, 9, 30)
        ref = datetime(2024, 6, 2, 16, 0)  # 367 days
        assert classify_holding_period(acq, ref) == "long_term"


# ---------------------------------------------------------------------------
# days_until_long_term
# ---------------------------------------------------------------------------

class TestDaysUntilLongTerm:

    def test_not_yet_held_at_all(self):
        d = date(2025, 1, 1)
        assert days_until_long_term(d, d) == 366

    def test_held_100_days(self):
        acq = date(2025, 1, 1)
        ref = date(2025, 4, 11)  # 100 days later
        assert (ref - acq).days == 100
        assert days_until_long_term(acq, ref) == 266

    def test_held_exactly_365_days_needs_one_more(self):
        # 2025 is non-leap: Jan 1 2025 → Jan 1 2026 = exactly 365 days → 1 more day needed
        acq = date(2025, 1, 1)
        ref = date(2026, 1, 1)
        assert (ref - acq).days == 365
        assert days_until_long_term(acq, ref) == 1

    def test_held_366_days_already_long_term(self):
        acq = date(2024, 1, 1)
        ref = date(2025, 1, 2)   # 366 days
        assert days_until_long_term(acq, ref) == 0

    def test_held_many_years_still_zero(self):
        acq = date(2020, 1, 1)
        ref = date(2025, 1, 1)
        assert days_until_long_term(acq, ref) == 0

    def test_none_acquisition_returns_none(self):
        assert days_until_long_term(None, date(2025, 1, 1)) is None

    def test_string_dates_accepted(self):
        result = days_until_long_term("2025-01-01", "2025-01-01")
        assert result == 366


# ---------------------------------------------------------------------------
# reconstruct_lots_fifo
# ---------------------------------------------------------------------------

def _txn(trade_date: str, action: str, ticker: str, qty: float, price: float) -> dict:
    return {
        "Trade Date": trade_date,
        "Action": action,
        "Ticker": ticker,
        "Quantity": qty,
        "Price": price,
        "Account": "test",
    }


class TestReconstructLotsFifo:

    def test_single_buy_returns_one_lot(self):
        txns = [_txn("2024-01-15", "Buy", "AAPL", 10.0, 150.0)]
        lots = reconstruct_lots_fifo(txns, "AAPL")
        assert len(lots) == 1
        assert lots[0].quantity == 10.0
        assert lots[0].cost_basis_per_share == 150.0
        assert lots[0].source == "derived"

    def test_buy_then_full_sell_returns_empty(self):
        txns = [
            _txn("2024-01-15", "Buy",  "AAPL", 10.0, 150.0),
            _txn("2024-06-01", "Sell", "AAPL", 10.0, 180.0),
        ]
        lots = reconstruct_lots_fifo(txns, "AAPL")
        assert lots == []

    def test_buy_then_partial_sell_fifo(self):
        txns = [
            _txn("2024-01-15", "Buy",  "AAPL", 10.0, 150.0),
            _txn("2024-06-01", "Sell", "AAPL",  4.0, 180.0),
        ]
        lots = reconstruct_lots_fifo(txns, "AAPL")
        assert len(lots) == 1
        assert abs(lots[0].quantity - 6.0) < 1e-5
        assert lots[0].cost_basis_per_share == 150.0

    def test_two_buys_fifo_sell_consumes_oldest_first(self):
        txns = [
            _txn("2023-01-01", "Buy",  "MSFT", 5.0, 200.0),
            _txn("2024-01-01", "Buy",  "MSFT", 5.0, 300.0),
            _txn("2024-06-01", "Sell", "MSFT", 5.0, 350.0),
        ]
        lots = reconstruct_lots_fifo(txns, "MSFT", as_of=date(2025, 1, 1))
        # The sell should consume the oldest 5 shares (Jan 2023 lot)
        assert len(lots) == 1
        assert abs(lots[0].quantity - 5.0) < 1e-5
        assert lots[0].cost_basis_per_share == 300.0  # 2024 lot remains
        assert lots[0].acquisition_date == date(2024, 1, 1)

    def test_holding_period_applied_to_derived_lot(self):
        as_of = date(2025, 6, 15)
        txns = [_txn("2024-01-01", "Buy", "GOOG", 3.0, 100.0)]
        lots = reconstruct_lots_fifo(txns, "GOOG", as_of=as_of)
        assert len(lots) == 1
        # 2024-01-01 to 2025-06-15 is > 365 days
        assert lots[0].holding_period == "long_term"
        assert lots[0].days_until_long_term == 0

    def test_irrelevant_tickers_ignored(self):
        txns = [
            _txn("2024-01-01", "Buy", "AAPL", 10.0, 150.0),
            _txn("2024-01-01", "Buy", "MSFT", 10.0, 200.0),
        ]
        lots = reconstruct_lots_fifo(txns, "AAPL")
        assert len(lots) == 1
        assert lots[0].ticker == "AAPL"

    def test_fifo_partial_split_across_two_lots(self):
        txns = [
            _txn("2023-06-01", "Buy",  "NVDA",  8.0, 100.0),
            _txn("2024-06-01", "Buy",  "NVDA",  8.0, 200.0),
            _txn("2025-01-01", "Sell", "NVDA", 10.0, 400.0),
        ]
        lots = reconstruct_lots_fifo(txns, "NVDA")
        # Sells consume 8 from lot-1, then 2 from lot-2 → 6 remain in lot-2
        assert len(lots) == 1
        assert abs(lots[0].quantity - 6.0) < 1e-5
        assert lots[0].cost_basis_per_share == 200.0
