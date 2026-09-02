"""
Normalize a DataFrame's columns to the canonical Sheets-cased names at the
PortfolioStore read boundary.

Why this exists (2026-08-31): `SqlitePortfolioStore` stores whatever column
casing a writer last used inside `payload_json` (a pure JSON round-trip —
see `core/store/serialize.py`). Two real write paths exist for the same
table and they don't agree: `pipeline.py`'s live-update path builds its
DataFrame from `utils.schwab_client.fetch_positions()`, which is snake_case;
`core/store/sync_from_sheets.py` reads via `SheetsPortfolioStore` first,
which is Sheets-cased ("Title Case"). Whichever wrote most recently wins,
silently. `core/thesis_sync_data.py` hit this as `KeyError: 'Ticker'` when
`holdings_current` happened to be snake_case — a *loud* failure. A consumer
that instead does `df.get('Weight', 0)` would have returned zeros instead of
crashing — same bug class as the pandas string-dtype incident (CLAUDE.md
Known Issues): not a one-off, a systemic contract gap.

The `PortfolioStore` Protocol is a contract; a contract whose return shape
depends on which backend (or which write path) is currently primary isn't
one. This module is the one place that keeps the promise, so no consumer
has to know or guess which backend produced the frame it's holding.

Scope: this fixes the *read* boundary, not the write paths — it's correct
regardless of which casing is sitting in an existing row, including rows
written before this file existed. `core/retrieval/` is a separate,
deliberately snake_case interface with its own contract; do not unify the
two here.
"""

from __future__ import annotations

import re

import pandas as pd

# Symbols that get spelled out as a word in snake_case (e.g. "%" -> "pct"),
# not just dropped. Must be applied *before* stripping non-alnum chars —
# stripping "%" and "$" outright collapses distinct canonical columns onto
# the same loose key (e.g. "Unrealized G/L" and "Unrealized G/L %" both
# reduce to "unrealizedgl", which silently drops one of the two real
# columns on rename — caught in testing, see tests/test_store_columns.py).
_SYMBOL_WORDS: dict[str, str] = {
    "%": "pct",
    "$": "usd",
}


def _loose_key(name: str) -> str:
    """Lowercase comparison key: spell out symbols, then drop punctuation."""
    s = name.lower()
    for sym, word in _SYMBOL_WORDS.items():
        s = s.replace(sym, word)
    return re.sub(r"[^a-z0-9]", "", s)


def normalize_dataframe_columns(
    df: pd.DataFrame, canonical_columns: list[str]
) -> pd.DataFrame:
    """
    Rename any column matching a canonical name's snake_case/loose form back
    to the canonical (Sheets) form.

    No-op for columns already canonical or unrecognized — extra columns
    (e.g. `tax_treatment` on holdings, which has no Sheets counterpart) pass
    through unchanged, never dropped. Safe to call on an already-correct
    frame (idempotent) or an empty one (returned as-is).

    Raises if the loose-key scheme would collapse two distinct canonical
    columns onto the same target — a silent duplicate-column rename is
    worse than a loud failure (the whole reason this module exists).
    """
    if df is None or df.empty or df.columns.empty:
        return df

    loose_to_canonical: dict[str, str] = {}
    for c in canonical_columns:
        key = _loose_key(c)
        prior = loose_to_canonical.get(key)
        if prior is not None and prior != c:
            raise ValueError(
                f"normalize_dataframe_columns: canonical columns {prior!r} and "
                f"{c!r} collide on loose key {key!r} — the loose-match scheme "
                f"can't disambiguate them. Fix _loose_key / _SYMBOL_WORDS."
            )
        loose_to_canonical[key] = c

    existing = set(df.columns)
    rename_map: dict[str, str] = {}
    for col in df.columns:
        if col in canonical_columns:
            continue
        canonical = loose_to_canonical.get(_loose_key(col))
        if canonical and canonical not in existing:
            rename_map[col] = canonical

    if not rename_map:
        return df

    out = df.rename(columns=rename_map)
    dupes = out.columns[out.columns.duplicated()].unique().tolist()
    if dupes:
        raise ValueError(
            f"normalize_dataframe_columns: rename {rename_map} produced "
            f"duplicate column(s) {dupes} — refusing to silently drop data."
        )
    return out
