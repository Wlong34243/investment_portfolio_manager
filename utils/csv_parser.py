"""
Investment Portfolio Manager — Schwab Positions CSV Parser
Ported from Colab V3.2 with production-grade error handling.
"""

import pandas as pd
import numpy as np
import re
import io
import os
import sys

# Add project root to path so config is importable when run directly
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import config
except ImportError:
    pass

def clean_numeric(value) -> float | None:
    """
    Robust number parsing for Schwab CSVs (Positions and Realized G/L).
    Handles: 
    - "3,535.86" (commas)
    - "(694.72)" (parens = negative in Positions CSV)
    - "-$3.43" (minus sign = negative in Realized G/L CSV)
    - "$1,200.00" (dollar signs)
    - "nan", "--", "-", "", None -> return None
    """
    if pd.isna(value) or value is None:
        return None
    
    if isinstance(value, (int, float)):
        return float(value)
    
    s = str(value).strip()
    
    if not s or s.lower() in ['nan', 'none', '-', '--', 'n/a']:
        return None
    
    # Check for parentheses for negative numbers (Positions CSV)
    is_negative = (s.startswith('(') and s.endswith(')')) or s.startswith('-')
    if s.startswith('(') and s.endswith(')'):
        s = s[1:-1]
    elif s.startswith('-'):
        s = s[1:]
    
    # Strip currency symbols and commas
    s = re.sub(r'[^\d.]', '', s)
    
    if not s:
        return None
    
    try:
        val = float(s)
        return -val if is_negative else val
    except ValueError:
        return None

# Add assertions for robustness
assert clean_numeric("3,535.86") == 3535.86
assert clean_numeric("(694.72)") == -694.72
assert clean_numeric("-$3.43") == -3.43
assert clean_numeric("$1,200.00") == 1200.00
assert clean_numeric("--") is None
assert clean_numeric("") is None

def find_column_indices(df_raw) -> dict:
    """
    Scan rows for the row containing "symbol" (case-insensitive).
    Return dict: {"symbol": 0, "description": 1, "quantity": 2, ...}
    NEVER use hardcoded column positions.
    Raise ValueError with clear message if Symbol row not found.
    """
    for idx, row in df_raw.iterrows():
        row_str = [str(x).lower().strip() for x in row.values]
        if 'symbol' in row_str:
            # We found the header row
            indices = {}
            for i, col_val in enumerate(row_str):
                if col_val:
                    # Map the column name to its index
                    indices[col_val] = i
            return indices
            
    raise ValueError("Could not find 'Symbol' header row in Schwab CSV.")

def find_account_sections(df_raw) -> list[dict]:
    """
    Scan for account type labels from config.ACCOUNT_SECTION_PATTERNS.
    Return: [{"account_type": str, "start_row": int, "end_row": int}]
    Handle single-account CSVs gracefully (return one section).
    """
    sections = []
    patterns = [p.lower() for p in config.ACCOUNT_SECTION_PATTERNS]
    
    current_section = None
    
    for idx, row in df_raw.iterrows():
        first_cell = str(row.iloc[0]).strip().lower()
        
        # Check if first cell matches any account pattern
        matched_pattern = None
        for p in patterns:
            if p in first_cell:
                matched_pattern = p
                break
        
        if matched_pattern:
            if current_section:
                current_section['end_row'] = idx - 1
                sections.append(current_section)
            
            current_section = {
                'account_type': first_cell,
                'start_row': idx
            }
        
        # End of sections indicator
        if 'positions total' in first_cell:
            if current_section:
                current_section['end_row'] = idx - 1
                sections.append(current_section)
                current_section = None
            # Do NOT break; there may be more sections (e.g., Contributory, Roth, etc.)
            continue

    # If no sections found, treat as one big section
    if not sections:
        sections.append({
            'account_type': 'Default',
            'start_row': 0,
            'end_row': len(df_raw) - 1
        })
    elif current_section: # Close the last section if it wasn't closed
        current_section['end_row'] = len(df_raw) - 1
        sections.append(current_section)
        
    return sections

def get_sector_fast(description: str) -> str:
    """
    Description-based sector from config.ETF_KEYWORDS.
    Return sector string or "Other" if no match.
    """
    desc_upper = str(description).upper()
    for sector, keywords in config.ETF_KEYWORDS.items():
        for kw in keywords:
            if kw.upper() in desc_upper:
                return sector
    return "Other"

def parse_schwab_csv(file_bytes: bytes) -> pd.DataFrame:
    """
    Orchestrate full parse:
    a. Read with header=None, names=range(25), encoding="utf-8-sig"
    b. find_column_indices()
    c. find_account_sections()
    d. Extract positions, skip summary/total rows
    e. clean_numeric() on all numeric columns
    f. Aggregate across accounts (groupby Symbol, sum Market_Value + Quantity)
    g. Return DataFrame with POSITION_COLUMNS schema from config.py
    CRITICAL: do NOT round fractional quantities (GOOG = 100.2781)
    """
    if isinstance(file_bytes, bytes):
        content = file_bytes.decode('utf-8-sig')
    else:
        content = file_bytes
        
    df_raw = pd.read_csv(io.StringIO(content), header=None, names=range(25))
    
    col_indices = find_column_indices(df_raw)
    sections = find_account_sections(df_raw)
    
    # Locate symbol row to know where data starts
    symbol_row_idx = -1
    for idx, row in df_raw.iterrows():
        if 'symbol' in [str(x).lower().strip() for x in row.values]:
            symbol_row_idx = idx
            break
            
    all_positions = []
    
    # Map from CSV column names to our internal names
    # Prompt 4 doesn't specify the exact map, but Prompt 5 mentions POSITION_COLUMNS
    # We need to map: symbol, description, quantity, price, market_value, cost_basis, etc.
    
    # Find the best matches for required columns in CSV headers
    qty_col = next((c for c in col_indices if 'qty' in c or 'quantity' in c), None)
    mkt_val_col = next((c for c in col_indices if 'mkt val' in c or 'market value' in c), None)
    cost_basis_col = next((c for c in col_indices if 'cost basis' in c), None)
    price_col = next((c for c in col_indices if 'price' in c), None)
    
    for section in sections:
        # Start reading after the symbol header row, but within section bounds
        start_scan = max(section['start_row'], symbol_row_idx + 1)
        
        for idx in range(start_scan, section['end_row'] + 1):
            row = df_raw.iloc[idx]
            symbol = str(row.iloc[col_indices.get('symbol', 0)]).strip()
            
            # Skip empty, headers, or totals
            if not symbol or symbol.lower() in ['nan', 'symbol', '--', 'total']:
                description = str(row.iloc[col_indices.get('description', 1)]).strip()
                if "cash" in description.lower():
                    symbol = "QACDS"
                else:
                    continue
            
            # Map descriptive cash rows to a standard ticker
            if "cash & cash investments" in symbol.lower():
                symbol = "QACDS"

            # Skip account label rows (e.g., "Individual ...119")
            is_account_label = False
            for p in config.ACCOUNT_SECTION_PATTERNS:
                if p.lower() in symbol.lower():
                    is_account_label = True
                    break
            if is_account_label:
                continue

            if 'account total' in symbol.lower() or 'positions total' in symbol.lower():
                continue
            
            mv = clean_numeric(row.iloc[col_indices[mkt_val_col]]) if mkt_val_col else 0.0
            cb = clean_numeric(row.iloc[col_indices[cost_basis_col]]) if cost_basis_col else 0.0
            
            # If it's a cash ticker, ensure cost_basis equals market_value (Schwab often reports 0 cost)
            if symbol.upper() in config.CASH_TICKERS:
                cb = mv

            pos = {
                'ticker': symbol,
                'description': str(row.iloc[col_indices.get('description', 1)]).strip(),
                'quantity': clean_numeric(row.iloc[col_indices[qty_col]]) if qty_col else 0.0,
                'price': clean_numeric(row.iloc[col_indices[price_col]]) if price_col else 0.0,
                'market_value': mv,
                'cost_basis': cb,
            }
            
            # Add other columns if they exist
            if 'gain/loss $' in col_indices:
                pos['unrealized_gl'] = clean_numeric(row.iloc[col_indices['gain/loss $']])
            if 'gain/loss %' in col_indices:
                pos['unrealized_gl_pct'] = clean_numeric(row.iloc[col_indices['gain/loss %']])
            if 'est annual income' in col_indices:
                pos['est_annual_income'] = clean_numeric(row.iloc[col_indices['est annual income']])
            if 'dividend yield' in col_indices:
                pos['dividend_yield'] = clean_numeric(row.iloc[col_indices['dividend yield']])
            if 'acquisition date' in col_indices:
                pos['acquisition_date'] = str(row.iloc[col_indices['acquisition date']]).strip()
                
            all_positions.append(pos)
            
    df = pd.DataFrame(all_positions)
    
    # Fill missing columns with 0.0
    for col in ['quantity', 'price', 'market_value', 'cost_basis', 'unrealized_gl', 'unrealized_gl_pct', 'est_annual_income', 'dividend_yield']:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].fillna(0.0)
            
    # f. Aggregate across accounts (groupby Symbol, sum Market_Value + Quantity)
    agg_dict = {
        'quantity': 'sum',
        'market_value': 'sum',
        'cost_basis': 'sum',
        'unrealized_gl': 'sum',
        'description': 'first',
        'price': 'first',
        'dividend_yield': 'max',
        'est_annual_income': 'sum',
    }
    # Keep any other columns by taking 'first'
    for col in df.columns:
        if col not in agg_dict and col != 'ticker':
            agg_dict[col] = 'first'
            
    df_agg = df.groupby('ticker').agg(agg_dict).reset_index()
    
    # Recalculate unit cost
    df_agg['unit_cost'] = df_agg['cost_basis'].div(df_agg['quantity'].replace(0, np.nan)).fillna(0)
    
    # Set is_cash
    df_agg['is_cash'] = df_agg['ticker'].isin(config.CASH_TICKERS)
    
    # Apply get_sector_fast as baseline classification
    df_agg['asset_class'] = df_agg['description'].apply(get_sector_fast)
    df_agg['asset_strategy'] = "Other"

    # Apply Gemini Smart Categorization (lazy import avoids circular dependency)
    try:
        from utils.enrichment import apply_smart_categorization
        df_agg = apply_smart_categorization(df_agg)
    except Exception:
        pass

    return df_agg

def inject_cash_manual(df: pd.DataFrame, cash_amount: float) -> pd.DataFrame:
    """
    Add CASH_MANUAL row: beta=0.0, yield=4.5%, is_cash=True.
    Only add if CASH_MANUAL not already present and amount > 0.
    """
    if cash_amount <= 0:
        return df

    if 'CASH_MANUAL' in df['ticker'].values:
        return df
        
    cash_row = {
        'ticker': 'CASH_MANUAL',
        'description': 'Manual Cash Entry',
        'quantity': float(cash_amount),
        'price': 1.0,
        'market_value': float(cash_amount),
        'cost_basis': float(cash_amount),
        'unit_cost': 1.0,
        'unrealized_gl': 0.0,
        'unrealized_gl_pct': 0.0,
        'est_annual_income': float(cash_amount) * (config.DEFAULT_CASH_YIELD_PCT / 100),
        'dividend_yield': config.DEFAULT_CASH_YIELD_PCT,
        'is_cash': True,
        'asset_class': 'Cash',
        'asset_strategy': 'Cash'
    }
    
    return pd.concat([df, pd.DataFrame([cash_row])], ignore_index=True)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        df = parse_schwab_csv(open(file_path, "rb").read())
        df = inject_cash_manual(df, 10000)
        print(f"Parsed {len(df)} positions")
        # Use available columns
        cols_to_print = [c for c in ["ticker", "market_value", "quantity"] if c in df.columns]
        print(df[cols_to_print].head(10).to_string())
