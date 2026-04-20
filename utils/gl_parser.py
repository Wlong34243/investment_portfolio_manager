"""
Investment Portfolio Manager — Realized Gain/Loss Lot Details Parser
Parses Schwab "Realized Gain/Loss – Lot Details" export CSV.
"""

import pandas as pd
from datetime import datetime
from utils.csv_parser import clean_numeric

# --- Helper Functions ---
def _clean_dollar(value) -> float:
    """
    Wrapper for centralized clean_numeric.
    Returns 0.0 on failure to preserve existing G/L logic flow.
    """
    val = clean_numeric(value)
    return val if val is not None else 0.0

def _clean_pct(value) -> float:
    """
    Parse percentage strings like "6.56688352686%" or "-0.567674026017%"
    Returns raw decimal (e.g., 0.0657 for 6.57%) for Google Sheets % formatting.
    Sheets multiplies by 100 for display.
    """
    if pd.isna(value) or str(value).strip() in ("", "-"):
        return 0.0
    s = str(value).strip()
    s = s.rstrip("%")
    try:
        val = float(s)
        # Authoritative clean: always return raw decimal
        return val / 100.0
    except ValueError:
        return 0.0

def _parse_date(value) -> str:
    """
    Parse MM/DD/YYYY to ISO YYYY-MM-DD string.
    Returns "" on failure (don't crash — some lots may have quirks).
    """
    if pd.isna(value) or str(value).strip() == "":
        return ""
    try:
        return datetime.strptime(str(value).strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return ""

def _holding_days(opened: str, closed: str) -> int:
    """
    Compute calendar days held. Both args are ISO date strings.
    Returns -1 if either date is missing/invalid.
    """
    try:
        open_dt = datetime.strptime(opened, "%Y-%m-%d")
        close_dt = datetime.strptime(closed, "%Y-%m-%d")
        return (close_dt - open_dt).days
    except (ValueError, TypeError):
        return -1

def _make_fingerprint(row: dict) -> str:
    """
    Content-based dedup key. Uniquely identifies a closed lot.
    Format: closed_date|ticker|opened_date|quantity|proceeds|cost_basis
    Example: "2025-12-19|XLV|2025-10-03|10|1552.85|1457.16"
    """
    return "|".join([
        str(row["closed_date"]),
        str(row["ticker"]),
        str(row["opened_date"]),
        str(row["quantity"]),
        str(row["proceeds"]),
        str(row["cost_basis"]),
    ])

def _find_account_sections_gl(df_raw: pd.DataFrame) -> list[dict]:
    """
    Scan raw DataFrame for account section boundaries.
    """
    sections = []
    current_account = None
    account_header_row = -1
    data_start_row = -1

    ACCOUNT_PATTERNS = [
        "individual 401", "contributory", "joint tenant", "hsa brokerage",
        "individual", "roth", "custodial", "trust", "rollover", "beneficiary",
    ]

    for i in range(len(df_raw)):
        row_values = df_raw.iloc[i].astype(str).str.strip()
        first_cell = row_values.iloc[0]
        first_cell_lower = first_cell.lower()

        if "realized gain/loss - lot details" in first_cell_lower:
            continue

        is_account_row = any(first_cell_lower.startswith(p) for p in ACCOUNT_PATTERNS)
        empty_trailing = (row_values.iloc[1:10] == "").all() or (row_values.iloc[1:10] == "nan").all()

        if is_account_row and (empty_trailing or i < 5):
            if current_account is not None:
                sections.append({
                    "account": current_account,
                    "header_row": account_header_row,
                    "data_start": data_start_row,
                    "data_end": i - 1
                })
            current_account = first_cell
            account_header_row = -1
            data_start_row = -1
            continue
        
        if first_cell_lower == "symbol" and account_header_row == -1:
            account_header_row = i
            data_start_row = i + 1

    if current_account is not None and data_start_row != -1:
        sections.append({
            "account": current_account,
            "header_row": account_header_row,
            "data_start": data_start_row,
            "data_end": len(df_raw) - 1
        })
    
    final_sections = []
    for section in sections:
        if section["data_start"] <= section["data_end"]:
            has_valid_data = False
            for i in range(section["data_start"], section["data_end"] + 1):
                row_val_0 = str(df_raw.iloc[i, 0]).strip().lower()
                if not (row_val_0 == "there are no transactions available for your search criteria..." or row_val_0 == ""):
                    has_valid_data = True
                    break
            if has_valid_data:
                final_sections.append(section)
        
    return final_sections

def parse_transaction_history(file_or_path) -> pd.DataFrame:
    """
    Parse standard Schwab Transaction History CSV.
    Headers: Date, Action, Symbol, Description, Quantity, Price, Fees & Comm, Amount
    """
    df = pd.read_csv(file_or_path, encoding="utf-8-sig")
    
    # Handle dates like "01/06/2026 as of 01/05/2026" by taking the first part
    def _clean_tx_date(val):
        s = str(val).split(" as of")[0].strip()
        try:
            return pd.to_datetime(s).strftime('%Y-%m-%d')
        except:
            return ""

    df['Date'] = df['Date'].apply(_clean_tx_date)
    
    # Filter out rows with empty dates
    df = df[df['Date'] != ""].copy()
    
    # Clean numeric
    for col in ['Quantity', 'Price', 'Fees & Comm', 'Amount']:
        if col in df.columns:
            df[col] = df[col].apply(_clean_dollar)
            
    # Build fingerprint — unified format: Date|Ticker|Action|Quantity|Price (Task 3)
    df['Fingerprint'] = df.apply(
        lambda x: f"{x['Date']}|{x.get('Symbol', '')}|{x['Action']}|{x.get('Quantity', 0)}|{x.get('Price', 0)}",
        axis=1
    )
    
    return df

def parse_realized_gl(file_or_path) -> pd.DataFrame:
    """
    Parse Schwab Realized G/L Lot Details CSV.
    Returns clean DataFrame with one row per closed lot.
    """
    # 1. Read raw with no assumed header
    df_raw = pd.read_csv(
        file_or_path,
        header=None,
        names=range(25),
        encoding="utf-8-sig",
        dtype=str,
        skip_blank_lines=False,
    )

    # 2. Find account sections
    sections = _find_account_sections_gl(df_raw)

    # 3. For each section, extract data rows
    all_rows = []
    for section in sections:
        for idx in range(section["data_start"], section["data_end"] + 1):
            row = df_raw.iloc[idx]
            symbol = str(row[0]).strip().strip('"')

            if not symbol or symbol.lower() in ("symbol", ""):
                continue
            if "no transactions" in symbol.lower():
                continue
            
            if row.iloc[:].apply(lambda x: str(x).strip() == "").all():
                continue

            lot = {
                "ticker":              symbol,
                "description":         str(row[1]).strip().strip('"'),
                "closed_date":         _parse_date(row[2]),
                "opened_date":         _parse_date(row[3]),
                "quantity":            float(str(row[4]).strip().strip('"') or 0),
                "proceeds_per_share":  _clean_dollar(row[5]),
                "cost_per_share":      _clean_dollar(row[6]),
                "proceeds":            _clean_dollar(row[7]),
                "cost_basis":          _clean_dollar(row[8]),
                "gain_loss_dollars":   _clean_dollar(row[9]),
                "gain_loss_pct":       _clean_pct(row[10]),
                "lt_gain_loss":        _clean_dollar(row[11]),
                "st_gain_loss":        _clean_dollar(row[12]),
                "term":                str(row[13]).strip().strip('"'),
                "unadjusted_cost":     _clean_dollar(row[14]),
                "wash_sale":           str(row[15]).strip().strip('"').upper() == "YES",
                "disallowed_loss":     _clean_dollar(row[16]),
                "account":             section["account"],
            }

            # VALIDATION: If closed_date is empty, this is a header/metadata row, not a trade. Skip it.
            if not lot["closed_date"]:
                continue

            lot["holding_days"]  = _holding_days(lot["opened_date"], lot["closed_date"])
            lot["is_primary_acct"] = (
                "individual" in section["account"].lower() 
                and "401" not in section["account"].lower() 
                and "contributory" not in section["account"].lower()
            )
            lot["fingerprint"]   = _make_fingerprint(lot)
            lot["winner"] = lot["gain_loss_dollars"] > 0

            all_rows.append(lot)

    return pd.DataFrame(all_rows)
