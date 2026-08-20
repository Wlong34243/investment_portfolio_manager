"""Factory for PortfolioStore backends."""

from __future__ import annotations

import logging

import config
from core.store.dual_store import DualPortfolioStore
from core.store.sheets_store import SheetsPortfolioStore
from core.store.sqlite_store import SqlitePortfolioStore

logger = logging.getLogger(__name__)

_cached = None


def get_store(backend: str | None = None):
    """Return the configured PortfolioStore (cached)."""
    global _cached
    name = (backend or config.STORE_BACKEND or "dual").strip().lower()
    if _cached is not None and getattr(_cached, "name", None) == name:
        return _cached
    if name == "sheets":
        _cached = SheetsPortfolioStore()
    elif name == "sqlite":
        _cached = SqlitePortfolioStore()
    else:
        if name != "dual":
            logger.warning("Unknown STORE_BACKEND=%r — using dual", name)
        _cached = DualPortfolioStore()
    return _cached


def reset_store_cache() -> None:
    global _cached
    _cached = None
