"""
Investment Portfolio Manager — Realized Gain/Loss Lot Details Parser
Parses Schwab "Realized Gain/Loss – Lot Details" export CSV.
"""

import pandas as pd
from datetime import datetime

# --- Helper Functions ---
def _clean_dollar(value) -> float:
    """
    Parse Schwab G/L dollar values.
    Handles: "$1,552.85", "-$3.43", "$0.00", "", None
    NOTE: G/L CSV uses -$ prefix for negatives (NOT parentheses).
    Different from positions CSV clean_numeric() — do not reuse.
    """
    if pd.isna(value) or str(value).strip() in ("", "-", "N/A"):
        return 0.0
    s = str(value).strip().replace(",", "").replace("$", "")
    try:
        return float(s)
    except ValueError:
        return 0.0

def _clean_pct(value) -> float:
    """
    Parse percentage strings like "6.56688352686%" or "-0.567674026017%"
    Returns float (e.g., 6.567) — NOT divided by 100. Store as-is.
    """
    if pd.isna(value) or str(value).strip() in ("", "-"):
        return 0.0
    s = str(value).strip().rstrip("%")
    try:
        return float(s)
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
    except ValueError:
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
    Returns list of dicts:
    [
        {"account": "Individual ...119", "header_row": 418, "data_start": 419, "data_end": 641},
        ...
    ]
    """
    sections = []
    current_account = None
    account_header_row = -1
    data_start_row = -1

    # Define account patterns (lower-cased)
    ACCOUNT_PATTERNS = [
        "individual 401", "contributory", "joint tenant", "hsa brokerage",
        "individual", "roth", "custodial", "trust", "rollover", "beneficiary",
    ]

    for i in range(len(df_raw)):
        row_values = df_raw.iloc[i].astype(str).str.strip()
        first_cell_lower = row_values[0].lower() if row_values.iloc[0] else ""

        # Check for account section label
        if any(first_cell_lower.startswith(p) for p in ACCOUNT_PATTERNS) and row_values.iloc[1:].apply(lambda x: x == "" or pd.isna(x)).all():
            if current_account is not None: # End previous section
                sections.append({
                    "account": current_account,
                    "header_row": account_header_row,
                    "data_start": data_start_row,
                    "data_end": i - 1  # Previous row was the end of data
                })
            current_account = row_values[0]
            account_header_row = -1 # Reset for next section
            data_start_row = -1
        
        # Check for column headers (appears after account label)
        if first_cell_lower == "symbol" and account_header_row == -1:
            account_header_row = i
            data_start_row = i + 1

    # Add the last section if any
    if current_account is not None and data_start_row != -1:
        sections.append({
            "account": current_account,
            "header_row": account_header_row,
            "data_start": data_start_row,
            "data_end": len(df_raw) - 1
        })
    
    # Filter out sections with no actual data rows (e.g., "no transactions" msg takes one row)
    # This also handles the case where the data_end might be before data_start due to "no transactions"
    # or blank lines immediately following the header
    final_sections = []
    for section in sections:
        # Check if the section contains actual data rows or "no transactions" message
        if section["data_start"] <= section["data_end"]:
            # Check the content of the potential data rows
            # A section is valid if it contains at least one row that isn't the "no transactions" message
            has_valid_data = False
            for i in range(section["data_start"], section["data_end"] + 1):
                row_val_0 = str(df_raw.iloc[i, 0]).strip().lower()
                if not (row_val_0 == "there are no transactions available for your search criteria..." or row_val_0 == ""):
                    has_valid_data = True
                    break
            if has_valid_data:
                final_sections.append(section)
        
    return final_sections


def parse_realized_gl(file_or_path) -> pd.DataFrame:
    """
    Parse Schwab Realized G/L Lot Details CSV.
    Returns clean DataFrame with one row per closed lot.
    Preserves account label for cross-account wash sale detection.
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
        # data_end could be a blank row or "no transactions" message, so iterate up to it
        for idx in range(section["data_start"], section["data_end"] + 1):
            row = df_raw.iloc[idx]
            symbol = str(row[0]).strip().strip('"')

            # Skip: empty rows, header repeats, "no transactions" messages
            if not symbol or symbol.lower() in ("symbol", ""):
                continue
            if "no transactions" in symbol.lower():
                continue
            
            # Skip blank separator rows (all cells are empty strings)
            if row.iloc[:].apply(lambda x: str(x).strip() == "").all():
                continue


            # Parse each field
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

            # Derived fields
            lot["holding_days"]  = _holding_days(lot["opened_date"], lot["closed_date"])
            lot["is_primary_acct"] = "individual" in section["account"].lower() 
                                     and "401" not in section["account"].lower() 
                                     and "contributory" not in section["account"].lower()
            lot["fingerprint"]   = _make_fingerprint(lot)
            lot["winner"] = lot["gain_loss_dollars"] > 0 # Add for behavioral analysis

            all_rows.append(lot)

    return pd.DataFrame(all_rows)

