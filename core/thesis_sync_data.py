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
from utils.sheet_readers import get_holdings_current, get_realized_gl, get_trade_log, get_transactions
from utils.thesis_utils import ThesisManager

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

def gather_thesis_sync_data(
    as_of_date: Optional[str] = None,
    tickers: Optional[List[str]] = None,
    txn_limit: Optional[int] = None,
) -> Dict[str, TickerSyncPayload]:
    """
    Gather data for syncing vault theses.
    """
    if as_of_date is None:
        as_of_date = datetime.now().strftime("%Y-%m-%d")
    if txn_limit is None:
        txn_limit = config.THESIS_TXN_LOG_LIMIT
        
    logging.info(f"Gathering thesis sync data as of {as_of_date}...")
    
    # 1. Load Data
    holdings_df = get_holdings_current()
    if holdings_df.empty:
        logging.warning("Holdings_Current is empty. Cannot sync.")
        return {}
        
    realized_df = get_realized_gl()
    transactions_df = get_transactions()
    
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
    total_market_value = full_portfolio_df['Market Value'].sum()

    # Filter tickers if provided
    if tickers:
        holdings_df = holdings_df[holdings_df['Ticker'].isin(tickers)]
        
    payloads = {}
    
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
            fm = mgr.get_frontmatter()
            if fm and 'style' in fm:
                style = fm['style']
                # Sometimes style is "GARP / Defensive Compounder", we want the first word if it matches styles.json
                if style and ' / ' in style:
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
        market_value = float(row.get('Market Value', 0.0) or 0.0)
        if total_market_value > 0:
            weight = (market_value / total_market_value) * 100.0
        else:
            # Degenerate case only (no priced positions). Fall back to the
            # stored column, coercing a fractional value up to percent.
            weight = float(row.get('Weight', 0.0) or 0.0)
            if 0.0 < weight <= 1.5:
                weight *= 100.0

        payloads[ticker] = TickerSyncPayload(
            ticker=ticker,
            style=style,
            size_ceiling_pct=size_ceiling,
            current_allocation_pct=weight,
            cost_basis=row.get('Cost Basis', 0.0),
            last_reviewed=as_of_date,
            transactions=transactions,
            transactions_total_count=txn_total_count,
            realized_gl=realized,
            drift_pct=weight - size_ceiling if size_ceiling > 0 else 0.0
        )
        
    return payloads

if __name__ == "__main__":
    # Test run
    logging.basicConfig(level=logging.INFO)
    data = gather_thesis_sync_data(datetime.now().strftime("%Y-%m-%d"), tickers=["UNH", "AMZN"])
    for ticker, payload in data.items():
        print(f"--- {ticker} ---")
        print(payload.model_dump_json(indent=2))
