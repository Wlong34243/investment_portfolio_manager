"""
Categorize portfolio holdings into Asset Class and Sector/Strategy using Gemini.
Produces a JSON mapping file consumed by apply_smart_categorization() in enrichment.py.

Usage:
    python utils/agents/portfolio_enricher.py --input path/to/positions.csv
    python utils/agents/portfolio_enricher.py --input path/to/positions.csv --output data/ticker_mapping.json
"""

import pandas as pd
import json
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from pydantic import BaseModel, Field
from typing import List
from utils.gemini_client import ask_gemini

TAXONOMY = """
Asset Classes:
- Equity, Fixed Income, Real Estate, Commodities, Crypto, Cash

Sectors / Strategies:
- For Single Stocks: Technology, Healthcare, Financials, Energy, Industrials,
  Consumer Discretionary, Consumer Staples, Utilities, Materials,
  Communication Services
- For ETFs: Broad Market US, Broad Market International, Emerging Markets,
  Dividend/Yield, Growth, Value, Sector-Specific
"""


class TickerCategory(BaseModel):
    ticker: str = Field(description="The ticker symbol exactly as provided")
    asset_class: str = Field(description="Asset class from the taxonomy")
    sector_strategy: str = Field(description="Sector or strategy from the taxonomy")


class PortfolioMapping(BaseModel):
    holdings: List[TickerCategory] = Field(description="One entry per ticker")


def enrich_holdings(input_csv: str, output_file: str = "data/ticker_mapping.json"):
    print(f"Loading data from {input_csv}...")
    df = pd.read_csv(input_csv)

    if 'Ticker' not in df.columns or 'Description' not in df.columns:
        print("Missing required columns: Ticker, Description")
        return

    holdings = df[['Ticker', 'Description']].drop_duplicates().to_dict('records')
    holdings_str = "\n".join([
        f"- {h['Ticker']}: {h['Description']}"
        for h in holdings if pd.notna(h['Ticker'])
    ])

    prompt = f"Please categorize the following portfolio holdings:\n{holdings_str}"

    system_instruction = (
        "You are a financial data enrichment expert. Categorize each ticker into a "
        "specific 'Asset Class' and 'Sector/Strategy' based ONLY on the following taxonomy:\n\n"
        f"{TAXONOMY}"
    )

    try:
        res = ask_gemini(
            prompt=prompt,
            system_instruction=system_instruction,
            response_schema=PortfolioMapping,
            max_tokens=4000,
        )

        if res:
            mapping_dict = {item.ticker: {"asset_class": item.asset_class, "sector_strategy": item.sector_strategy}
                            for item in res.holdings}
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(mapping_dict, f, indent=4)
            print(f"Successfully categorized {len(mapping_dict)} tickers -> {output_file}")
        else:
            print("Gemini returned an empty response.")

    except Exception as e:
        print(f"Error during generation or parsing: {e}")


def sync_from_holdings(df: pd.DataFrame, output_file: str = "data/ticker_mapping.json") -> tuple[bool, str]:
    """
    Build ticker_mapping.json directly from Asset Class / Asset Strategy columns
    already in the holdings DataFrame — no AI call required.
    Use this when the sheet has already been manually enriched.
    """
    ticker_col = 'Ticker' if 'Ticker' in df.columns else 'ticker'
    ac_col = 'Asset Class' if 'Asset Class' in df.columns else 'asset_class'
    as_col = 'Asset Strategy' if 'Asset Strategy' in df.columns else 'asset_strategy'

    if ticker_col not in df.columns:
        return False, "DataFrame missing Ticker column."

    mapping = {}
    for _, row in df.iterrows():
        ticker = str(row.get(ticker_col, '')).strip()
        if not ticker or ticker.lower() in ('nan', ''):
            continue
        asset_class = str(row.get(ac_col, 'Other')).strip() if ac_col in df.columns else 'Other'
        sector_strategy = str(row.get(as_col, 'Other')).strip() if as_col in df.columns else 'Other'
        if asset_class.lower() in ('nan', '', 'n/a'):
            asset_class = 'Other'
        if sector_strategy.lower() in ('nan', '', 'n/a'):
            sector_strategy = 'Other'
        mapping[ticker] = {'asset_class': asset_class, 'sector_strategy': sector_strategy}

    if not mapping:
        return False, "No tickers found in DataFrame."

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(mapping, f, indent=4)
    return True, f"Synced {len(mapping)} tickers from sheet -> {output_file}"


def enrich_holdings_from_df(df: pd.DataFrame, output_file: str = "data/ticker_mapping.json") -> tuple[bool, str]:
    """
    DataFrame-native entry point for Streamlit UI.
    Accepts a DataFrame with 'Ticker'/'ticker' and 'Description'/'description' columns.
    Returns (success: bool, message: str).
    Uses batch processing to stay within Gemini limits.
    """
    ticker_col = 'Ticker' if 'Ticker' in df.columns else 'ticker'
    desc_col = 'Description' if 'Description' in df.columns else 'description'

    if ticker_col not in df.columns or desc_col not in df.columns:
        return False, "DataFrame missing Ticker/Description columns."

    holdings = (
        df[[ticker_col, desc_col]]
        .drop_duplicates()
        .rename(columns={ticker_col: 'Ticker', desc_col: 'Description'})
        .to_dict('records')
    )
    
    # Load existing mapping if present
    mapping_dict = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r') as f:
                mapping_dict = json.load(f)
        except:
            pass

    # Batch process: 20 tickers at a time
    batch_size = 20
    total_processed = 0
    
    for i in range(0, len(holdings), batch_size):
        batch = holdings[i : i + batch_size]
        batch_str = "\n".join([
            f"- {h['Ticker']}: {h['Description']}"
            for h in batch if pd.notna(h['Ticker']) and str(h['Ticker']).strip()
        ])

        if not batch_str:
            continue

        print(f"  ... Categorizing batch {i//batch_size + 1} ({len(batch)} tickers)...")
        prompt = f"Please categorize the following portfolio holdings:\n{batch_str}"
        system_instruction = (
            "You are a financial data enrichment expert. Categorize each ticker into a "
            "specific 'Asset Class' and 'Sector/Strategy' based ONLY on the following taxonomy:\n\n"
            f"{TAXONOMY}"
        )

        try:
            from utils.gemini_client import ask_gemini_json
            res = ask_gemini_json(
                prompt=prompt,
                system_instruction=system_instruction,
                max_tokens=4000,
            )

            if "error" in res:
                print(f"❌ Batch {i//batch_size + 1} API error: {res['error']}")
                continue

            # Normalized conversion of various JSON shapes Gemini might return
            new_mappings = {}
            
            # Case 1: { "holdings": [ {ticker, asset_class, sector_strategy}, ... ] }
            if isinstance(res, dict) and "holdings" in res:
                for item in res["holdings"]:
                    t = item.get("ticker") or item.get("Ticker")
                    ac = item.get("asset_class") or item.get("Asset Class")
                    ss = item.get("sector_strategy") or item.get("Sector/Strategy") or item.get("sector_strategy")
                    if t: new_mappings[t] = {"asset_class": ac, "sector_strategy": ss}
            
            # Case 2: [ {ticker, asset_class, sector_strategy}, ... ]
            elif isinstance(res, list):
                for item in res:
                    t = item.get("ticker") or item.get("Ticker")
                    ac = item.get("asset_class") or item.get("Asset Class")
                    ss = item.get("sector_strategy") or item.get("Sector/Strategy") or item.get("sector_strategy")
                    if t: new_mappings[t] = {"asset_class": ac, "sector_strategy": ss}
            
            # Case 3: { "AAPL": {"asset_class": "Equity", ...}, "MSFT": {...} }
            elif isinstance(res, dict):
                for t, info in res.items():
                    if isinstance(info, dict):
                        ac = info.get("asset_class") or info.get("Asset Class")
                        ss = info.get("sector_strategy") or info.get("Sector/Strategy") or info.get("sector_strategy")
                        new_mappings[t] = {"asset_class": ac, "sector_strategy": ss}

            if new_mappings:
                mapping_dict.update(new_mappings)
                total_processed += len(new_mappings)
                print(f"✅ Batch {i//batch_size + 1}: Processed {len(new_mappings)} tickers.")
            else:
                print(f"⚠️ Batch {i//batch_size + 1} returned no valid mappings: {res}")

        except Exception as e:
            print(f"❌ Batch {i//batch_size + 1} failed: {e}")

    # Save final merged mapping
    if mapping_dict:
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(mapping_dict, f, indent=4)
        return True, f"Categorized {total_processed} tickers across {len(holdings)} identified -> {output_file}"
    else:
        return False, "No tickers were successfully categorized."


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Categorize Portfolio Holdings via Gemini")
    parser.add_argument("--input", required=True, help="Path to raw portfolio CSV")
    parser.add_argument("--output", default="data/ticker_mapping.json", help="Output JSON path")
    args = parser.parse_args()
    enrich_holdings(args.input, args.output)
