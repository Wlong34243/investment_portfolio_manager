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


def enrich_holdings_from_df(df: pd.DataFrame, output_file: str = "data/ticker_mapping.json") -> tuple[bool, str]:
    """
    DataFrame-native entry point for Streamlit UI.
    Accepts a DataFrame with 'Ticker'/'ticker' and 'Description'/'description' columns.
    Returns (success: bool, message: str).
    """
    # Normalize to Title Case column names for lookup
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
    holdings_str = "\n".join([
        f"- {h['Ticker']}: {h['Description']}"
        for h in holdings if pd.notna(h['Ticker']) and str(h['Ticker']).strip()
    ])

    if not holdings_str:
        return False, "No valid tickers found in DataFrame."

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

        if not res:
            return False, "Gemini returned an empty response."

        mapping_dict = {item.ticker: {"asset_class": item.asset_class, "sector_strategy": item.sector_strategy}
                        for item in res.holdings}
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(mapping_dict, f, indent=4)
        return True, f"Categorized {len(mapping_dict)} tickers -> {output_file}"

    except Exception as e:
        return False, f"Enrichment failed: {e}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Categorize Portfolio Holdings via Gemini")
    parser.add_argument("--input", required=True, help="Path to raw portfolio CSV")
    parser.add_argument("--output", default="data/ticker_mapping.json", help="Output JSON path")
    args = parser.parse_args()
    enrich_holdings(args.input, args.output)
