import os
import sys
from pathlib import Path

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = Path(_HERE).parent
sys.path.append(str(_ROOT))

import config
from utils.schwab_client import get_market_client, fetch_quotes

def test_quotes():
    client = get_market_client()
    if not client:
        print("No market client")
        return
    
    tickers = ["UNH", "GOOG", "JPIE"]
    df = fetch_quotes(client, tickers)
    print(df)

if __name__ == "__main__":
    test_quotes()
