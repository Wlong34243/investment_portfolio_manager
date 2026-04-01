from utils.csv_parser import parse_schwab_csv, inject_cash_manual
from pipeline import normalize_positions, write_to_sheets, sanitize_for_sheets
import datetime
import pandas as pd
import numpy as np
import config

def run_test():
    print("--- E2E Phase 1 Test ---")
    file_path = "All-Accounts-Positions-2026-03-30-103853.csv"
    
    # 1. PARSE
    print("\n1. PARSE")
    try:
        content = open(file_path, "rb").read()
        df = parse_schwab_csv(content)
        print(f"Position count: {len(df)}")
        print(f"Tickers: {', '.join(df['ticker'].tolist()[:10])}...")
        total_mkt_val = df['market_value'].sum()
        print(f"Total market value: ${total_val:,.2f}" if 'total_val' in locals() else f"Total market value: ${total_mkt_val:,.2f}")
        
        # Fractional shares check
        fractional = df[df['quantity'] % 1 != 0]
        if not fractional.empty:
            print(f"Fractional shares found for: {', '.join(fractional['ticker'].tolist())}")
        else:
            print("No fractional shares found (or all are integers).")
    except Exception as e:
        print(f"Parse error: {e}")
        return

    # 2. CASH INJECTION
    print("\n2. CASH INJECTION")
    df = inject_cash_manual(df, 10000)
    cash_row = df[df['ticker'] == 'CASH_MANUAL']
    if not cash_row.empty:
        print(f"CASH_MANUAL row: {cash_row.to_dict('records')[0]}")
    else:
        print("CASH_MANUAL injection failed.")

    # 3. NORMALIZE
    print("\n3. NORMALIZE")
    df = normalize_positions(df, str(datetime.date.today()))
    print(df[['Ticker', 'Market Value', 'Weight', 'Fingerprint']].head(5).to_string())
    
    # Concentration check
    conc = df[df['Weight'] > 8.0]
    if not conc.empty:
        for _, row in conc.iterrows():
            print(f"High concentration alert: {row['Ticker']} at {row['Weight']:.2f}%")
            
    # 4. SANITIZE CHECK
    print("\n4. SANITIZE CHECK")
    data = sanitize_for_sheets(df)
    
    violations = []
    for row in data:
        for val in row:
            if isinstance(val, (np.float64, np.float32, np.int64, np.int32)):
                violations.append(type(val))
    
    if not violations:
        print("Serialization check passed (no numpy types).")
    else:
        print(f"Serialization check FAILED. Found types: {set(violations)}")

    # 5. DRY RUN WRITE
    print("\n5. DRY RUN WRITE")
    result = write_to_sheets(df, 10000, dry_run=True)
    print(f"Dry run result: {result}")

    # 6. LIVE WRITE (only if config.DRY_RUN == False)
    print(f"\n6. LIVE WRITE (config.DRY_RUN is {config.DRY_RUN})")
    if config.DRY_RUN == False:
        result = write_to_sheets(df, 10000, dry_run=False)
        print(f"Live write result: {result}")
    else:
        print("Skipping live write (DRY_RUN is True).")

if __name__ == "__main__":
    run_test()
