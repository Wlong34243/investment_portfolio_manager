"""Trading-day helpers wrapping Schwab is_trading_day with day-cache."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def previous_trading_day(d: Optional[date] = None) -> Optional[date]:
    """Walk backward until is_trading_day is True. Returns None if unknown."""
    from utils.schwab_client import get_market_client, is_trading_day

    if d is None:
        d = date.today()
    client = get_market_client()
    if client is None:
        return None
    cursor = d - timedelta(days=1)
    for _ in range(15):
        flag = is_trading_day(client, date_=cursor)
        if flag is True:
            return cursor
        if flag is None:
            return None
        cursor -= timedelta(days=1)
    return None


def trading_days_between(earlier: date, later: date) -> Optional[int]:
    """Count trading sessions strictly after earlier up to and including later.

    Returns None if any day in the range is unknown (API failure).
    """
    from utils.schwab_client import get_market_client, is_trading_day

    if later < earlier:
        return 0
    client = get_market_client()
    if client is None:
        return None
    n = 0
    cursor = earlier + timedelta(days=1)
    while cursor <= later:
        flag = is_trading_day(client, date_=cursor)
        if flag is None:
            return None
        if flag:
            n += 1
        cursor += timedelta(days=1)
    return n


def is_session_open(d: Optional[date] = None) -> Optional[bool]:
    from utils.schwab_client import get_market_client, is_trading_day
    client = get_market_client()
    if client is None:
        return None
    return is_trading_day(client, date_=d)
