import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime
import pandas as pd

# Add project root to path
sys.path.insert(0, os.getcwd())

import config
from utils.thesis_utils import ThesisManager


def _store_frames():
    """Load frames via PortfolioStore (`get_store()` honors STORE_PRIMARY); fall back to sheet_readers."""
    try:
        from core.store import get_store

        store = get_store()
        return (
            store.get_holdings_current(),
            store.get_realized_gl(),
            store.get_transactions(),
            store.get_trade_log(),
        )
    except Exception:
        from utils.sheet_readers import (
            get_holdings_current,
            get_realized_gl,
            get_trade_log,
            get_transactions,
        )

        return (
            get_holdings_current(),
            get_realized_gl(),
            get_transactions(),
            get_trade_log(),
        )


def _newest_composite_positions() -> Dict[str, dict]:
    """Map ticker -> position dict from the newest composite bundle.

    Holdings_Current can temporarily show Quantity with Price/MV/Cost at 0
    after a partial live update (observed 2026-08-07). Bundle weight_pct /
    market_value remain authoritative for thesis sync when the sheet is blank.
    """
    bundles_dir = Path("bundles")
    if not bundles_dir.exists():
        return {}
    candidates = sorted(bundles_dir.glob("composite_bundle_*.json"))
    if not candidates:
        return {}
    try:
        data = json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logging.warning("Could not read composite bundle for thesis sync: %s", e)
        return {}
    positions = (data.get("_market_data") or {}).get("positions") or []
    out = {}
    for p in positions:
        t = p.get("ticker")
        if t and t not in config.CASH_TICKERS:
            out[str(t)] = p
    return out


def _bundle_weight_pct(pos: dict) -> Optional[float]:
    if not pos:
        return None
    raw = pos.get("weight_pct")
    if raw is None:
        raw = pos.get("weight")
    try:
        w = float(raw)
    except (TypeError, ValueError):
        return None
    # Bundle stores percent in weight_pct; some older shapes used fraction.
    if 0.0 < w <= 1.5 and pos.get("weight_pct") is None:
        w *= 100.0
    return w


class TickerSyncPayload(BaseModel):
    ticker: str
    style: Optional[str]
    size_ceiling_pct: float
    current_allocation_pct: float
    cost_basis: float
    last_reviewed: str
    transactions: List[dict] = []
    transactions_total_count: int = 0
    realized_gl: List[dict] = []
    drift_pct: float = 0.0


class ThesisSyncGatherResult(BaseModel):
    """Payloads plus per-ticker frontmatter parse failures (omit-from-payloads)."""
    payloads: Dict[str, TickerSyncPayload] = {}
    parse_errors: List[dict] = []  # [{"ticker": "...", "error": "..."}, ...]


def gather_thesis_sync_data(
    as_of_date: Optional[str] = None,
    tickers: Optional[List[str]] = None,
    txn_limit: Optional[int] = None,
) -> ThesisSyncGatherResult:
    """
    Gather data for syncing vault theses.

    Tickers whose thesis frontmatter is unparseable under ruamel are omitted
    from payloads and listed in parse_errors (skip write; do not abort gather).
    """
    if as_of_date is None:
        as_of_date = datetime.now().strftime("%Y-%m-%d")
    if txn_limit is None:
        txn_limit = config.THESIS_TXN_LOG_LIMIT
        
    logging.info(f"Gathering thesis sync data as of {as_of_date}...")
    
    # 1. Load Data (PortfolioStore — reads honor STORE_PRIMARY; default sheets)
    holdings_df, realized_df, transactions_df, _trade_log_df = _store_frames()
    if holdings_df.empty:
        logging.warning("Holdings_Current is empty. Cannot sync.")
        return ThesisSyncGatherResult()
        
    bundle_by_ticker = _newest_composite_positions()
    
    # Load styles.json
    styles_path = Path("data/styles.json")
    styles_config = {}
    if styles_path.exists():
        styles_config = json.loads(styles_path.read_text())
        
    # Load ticker_strategies.json as fallback
    strategies_path = Path("data/ticker_strategies.json")
    strategies = {}
    if strategies_path.exists():
        strategies = json.loads(strategies_path.read_text())
    
    # Calculate total market value from full portfolio for weight calculation
    full_portfolio_df = holdings_df[~holdings_df['Ticker'].isin(config.CASH_TICKERS)]
    total_market_value = float(pd.to_numeric(full_portfolio_df['Market Value'], errors='coerce').fillna(0).sum())
    # If the sheet blanked prices (MV sum ~0) but the composite still has
    # valued positions, use the bundle total instead.
    if total_market_value <= 0 and bundle_by_ticker:
        total_market_value = sum(
            float(p.get("market_value") or 0.0) for p in bundle_by_ticker.values()
        )
        logging.warning(
            "Holdings_Current Market Value sum is 0; using composite bundle "
            "total_market_value=%.2f for thesis allocation sync.",
            total_market_value,
        )

    # Filter tickers if provided
    if tickers:
        holdings_df = holdings_df[holdings_df['Ticker'].isin(tickers)]
        
    payloads = {}
    parse_errors: List[dict] = []
    
    for _, row in holdings_df.iterrows():
        ticker = row['Ticker']
        if not ticker or str(ticker) in config.CASH_TICKERS:
            continue
            
        # Resolve Style
        # 1. Check thesis frontmatter (if exists)
        thesis_path = Path(config.THESES_DIR) / f"{ticker}_thesis.md"
        style = None
        fm = None
        mgr = None
        if thesis_path.exists():
            mgr = ThesisManager(thesis_path)
            fm, fm_err = mgr.get_frontmatter_safe()
            if fm_err is not None:
                # Omit from payloads: writing would fail on update_frontmatter
                # anyway; leaving the file untouched beats a partial region update.
                parse_errors.append({"ticker": str(ticker), "error": fm_err})
                logging.warning(
                    "Thesis frontmatter unparseable for %s — omitting from sync: %s",
                    ticker,
                    fm_err,
                )
                continue
        if fm and 'style' in fm:
            style = fm['style']
            # YAML list placeholders like [BILL] must not reach styles_config lookup.
            if not isinstance(style, str):
                style = None
            # Sometimes style is "GARP / Defensive Compounder", we want the first word if it matches styles.json
            elif style and ' / ' in style:
                style = style.split(' / ')[0]
        
        # 2. Fallback to ticker_strategies.json
        if not style or style not in styles_config:
            style = strategies.get(ticker)
            
        # 3. Final cleanup - ensure it exists in styles.json
        if style not in styles_config:
            if style == "BORING":
                style = "FUND"
            elif style == "CASH":
                style = "ETF" # Or similar, or None
        
        # Preserve a manually-set per-ticker override (style_size_ceiling_pct,
        # nested under the frontmatter's `triggers:` block) instead of always
        # recomputing the style default. Before this fix, a deliberate
        # override like META's 4.0 (below the GARP default of 9.0, "below
        # MSFT given higher idiosyncratic risk") was silently overwritten
        # back to the style default on every sync -- destructive, not just
        # a display bug. Only the style default is used when no override
        # exists yet.
        size_ceiling_override = None
        if fm:
            triggers_fm = fm.get('triggers') or {}
            raw_override = triggers_fm.get('style_size_ceiling_pct')
            if raw_override in (None, '') and mgr is not None:
                triggers_block = mgr.get_triggers() or {}
                raw_override = triggers_block.get('style_size_ceiling_pct')
            if raw_override not in (None, ''):
                try:
                    size_ceiling_override = float(raw_override)
                except (TypeError, ValueError):
                    size_ceiling_override = None

        if size_ceiling_override is not None:
            size_ceiling = size_ceiling_override
        else:
            size_ceiling = styles_config.get(style, {}).get("size_ceiling_pct", 0.0)

        # Recent transactions, capped at txn_limit. Track the true total so
        # the thesis file can disclose "(showing N most recent of M)" rather
        # than silently dropping older history.
        transactions = []
        txn_total_count = 0
        if not transactions_df.empty:
            all_ticker_tx = transactions_df[transactions_df['Ticker'] == ticker].sort_values('Trade Date', ascending=False)
            txn_total_count = len(all_ticker_tx)
            transactions = all_ticker_tx.head(txn_limit).to_dict('records')
        
        # Get realized GL
        realized = []
        if not realized_df.empty:
            ticker_gl = realized_df[realized_df['Ticker'] == ticker].to_dict('records')
            realized = ticker_gl
        
        # Weight: always recompute from market value rather than trusting the
        # sheet's 'Weight' column.
        #
        # BUGFIX 2026-07-26: that column stores a FRACTION (position MV / total
        # MV), not a percentage. The previous code used it raw whenever it was
        # non-zero, so every thesis file was written with an allocation 100x too
        # small (NOW 1.09% -> "0.01%", JEPI 9.92% -> "0.10%"). Because drift is
        # weight - ceiling, that made drift negative for all 35 positions and
        # silently suppressed every real ceiling breach (JEPI, QQQM, MELI).
        # manager.py already worked around this with a `max <= 1.5` heuristic;
        # that heuristic is itself unsafe for a book whose largest position is
        # under 1.5%, so recompute deterministically here instead.
        #
        # BUGFIX 2026-08-07: when Holdings_Current has Quantity but Price/MV
        # blanked to 0 (partial live update), prefer the newest composite
        # bundle's weight_pct / market_value / cost_basis so frontmatter and
        # region:position_state stop writing a fake 0.00%.
        bpos = bundle_by_ticker.get(str(ticker)) or {}
        market_value = float(row.get('Market Value', 0.0) or 0.0)
        if market_value <= 0 and bpos:
            try:
                market_value = float(bpos.get("market_value") or 0.0)
            except (TypeError, ValueError):
                market_value = 0.0

        if total_market_value > 0 and market_value > 0:
            weight = (market_value / total_market_value) * 100.0
        else:
            bw = _bundle_weight_pct(bpos)
            if bw is not None and bw > 0:
                weight = bw
            else:
                # Degenerate case only (no priced positions). Fall back to the
                # stored column, coercing a fractional value up to percent.
                weight = float(row.get('Weight', 0.0) or 0.0)
                if 0.0 < weight <= 1.5:
                    weight *= 100.0

        cost_basis = float(row.get('Cost Basis', 0.0) or 0.0)
        if cost_basis <= 0 and bpos:
            try:
                cost_basis = float(bpos.get("cost_basis") or 0.0)
            except (TypeError, ValueError):
                pass

        payloads[ticker] = TickerSyncPayload(
            ticker=ticker,
            style=style,
            size_ceiling_pct=size_ceiling,
            current_allocation_pct=weight,
            cost_basis=cost_basis,
            last_reviewed=as_of_date,
            transactions=transactions,
            transactions_total_count=txn_total_count,
            realized_gl=realized,
            drift_pct=weight - size_ceiling if size_ceiling > 0 else 0.0
        )
        
    return ThesisSyncGatherResult(payloads=payloads, parse_errors=parse_errors)

if __name__ == "__main__":
    # Test run
    logging.basicConfig(level=logging.INFO)
    result = gather_thesis_sync_data(datetime.now().strftime("%Y-%m-%d"), tickers=["UNH", "AMZN"])
    if result.parse_errors:
        print("parse_errors:", result.parse_errors)
    for ticker, payload in result.payloads.items():
        print(f"--- {ticker} ---")
        print(payload.model_dump_json(indent=2))
