import pandas as pd
import json
import argparse
import os
import sys
from pydantic import BaseModel
from typing import Dict

# Add project root to path so utils is importable
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from utils.gemini_client import ask_gemini, SAFETY_PREAMBLE

# 1. Define the Pydantic schemas to force Gemini's output structure
class HoldingCategory(BaseModel):
    asset_class: str
    sector_strategy: str

class PortfolioMapping(BaseModel):
    mapping: Dict[str, HoldingCategory]

# 2. Define the strict taxonomy
TAXONOMY = """
Asset Classes: 
- Equity, Fixed Income, Real Estate, Commodities, Crypto, Cash

Sectors / Strategies:
- For Single Stocks: Technology, Healthcare, Financials, Energy, Industrials, Consumer Discretionary, Consumer Staples, Utilities, Materials, Communication Services
- For ETFs: Broad Market US, Broad Market International, Emerging Markets, Dividend/Yield, Growth, Value, Sector-Specific (e.g., Tech ETF, Defense ETF)
"""

def enrich_holdings(input_csv: str, output_file: str):
    print(f"Loading data from {input_csv}...")
    # Read the CSV. Schwab CSV might have headers that need cleaning, but let's assume raw CSV for now or use the parser if it's a Schwab CSV.
    # However, the script suggests it just needs Ticker and Description.
    try:
        df = pd.read_csv(input_csv)
    except Exception as e:
        # If it's a Schwab CSV, it might fail raw read due to footer/header.
        # But let's try to be smart.
        from utils.csv_parser import parse_schwab_csv
        with open(input_csv, 'rb') as f:
            df = parse_schwab_csv(f.read())
            # Map back to expected columns if needed, though parse_schwab_csv returns normalized names
            df = df.rename(columns={'ticker': 'Ticker', 'description': 'Description'})

    # Extract unique tickers and descriptions
    holdings = df[['Ticker', 'Description']].drop_duplicates().to_dict('records')
    holdings_str = "\n".join([f"- {h['Ticker']}: {h['Description']}" for h in holdings if pd.notna(h['Ticker'])])
    
    print(f"Found {len(holdings)} unique holdings. Requesting categorization from Gemini...")
    
    prompt = f"Please categorize the following portfolio holdings:\n{holdings_str}"
    
    system_instruction = f"""
    {SAFETY_PREAMBLE}
    You are a financial data enrichment expert. Your job is to categorize each ticker into a specific 'Asset Class' and 'Sector/Strategy' based ONLY on the following taxonomy:
    
    {TAXONOMY}
    
    Map each ticker to its appropriate asset_class and sector_strategy.
    """
    
    try:
        # 3. Use your built-in ask_gemini client!
        res = ask_gemini(
            prompt=prompt, 
            system_instruction=system_instruction, 
            response_schema=PortfolioMapping
        )
        
        if res:
            # Convert Pydantic model to dictionary
            mapping_dict = res.model_dump()["mapping"]
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            with open(output_file, 'w') as f:
                json.dump(mapping_dict, f, indent=4)
                
            print(f"✅ Successfully categorized holdings and saved to {output_file}")
        else:
            print("❌ Gemini returned an empty response.")
            
    except Exception as e:
        print(f"❌ Error during generation or parsing: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Categorize Portfolio Holdings using existing Gemini Client")
    parser.add_argument("--input", required=True, help="Path to the raw portfolio CSV")
    parser.add_argument("--output", default="data/ticker_mapping.json", help="Output JSON mapping file path")
    
    args = parser.parse_args()
    enrich_holdings(args.input, args.output)
