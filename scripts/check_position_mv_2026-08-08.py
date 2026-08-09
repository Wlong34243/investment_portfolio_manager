"""Quick check: Position MV coercion via shared sanitizer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

import config
from utils.column_guard import ensure_display_columns
from utils.sheet_readers import coerce_sheet_numeric_series, get_gspread_client

ss = get_gspread_client().open_by_key(config.PORTFOLIO_SHEET_ID)
ws = ss.worksheet(config.TAB_HOLDINGS_CURRENT)
vals = ws.get_all_values()
hdr_i = next(i for i, r in enumerate(vals[:5]) if "Ticker" in r)
df = pd.DataFrame(vals[hdr_i + 1 :], columns=vals[hdr_i])
df = ensure_display_columns(df)
df = df[df["Ticker"].astype(str).str.len() > 0]
df = df[~df["Ticker"].astype(str).str.contains(r"SNAPSHOT|TICKER|CASH_MANUAL|📊", regex=True, na=False)]
df["_mv"] = coerce_sheet_numeric_series(df["Market Value"])
top = df.sort_values("_mv", ascending=False).head(5)
print("TOP 5 Position MV (coerced via coerce_sheet_numeric_series):")
for _, r in top.iterrows():
    print(f"  {r['Ticker']:6} raw={str(r['Market Value']):18} coerced={float(r['_mv']):,.2f}")
print(f"nonzero={int((df['_mv'] > 0).sum())} of {len(df)}")
