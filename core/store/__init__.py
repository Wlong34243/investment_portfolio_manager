"""
core/store — PortfolioStore abstraction (Sheets + SQLite shadow ledger).

CLI owns execution. Store owns persistence. Visual layer reads through the store.
"""

from core.store.factory import get_store
from core.store.protocol import PortfolioStore, StoreSnapshot
from core.store.verify import verify_stores

__all__ = [
    "PortfolioStore",
    "StoreSnapshot",
    "get_store",
    "verify_stores",
]
