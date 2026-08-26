"""
Investment Portfolio Manager — Realized Gain/Loss Lot Details Parser
Parses Schwab "Realized Gain/Loss – Lot Details" export CSV.
"""

import pandas as pd
import re
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

    def _cell0(row) -> str:
        v = row.iloc[0]
        if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
            return ""
        s = str(v).strip().strip('"')
        return "" if s.lower() in ("nan", "none", "") else s

    def _trailing_empty(row) -> bool:
        """True when columns 1..9 are blank/NaN (account banner rows)."""
        for j in range(1, 10):
            if j >= len(row):
                continue
            v = row.iloc[j]
            if v is None or (isinstance(v, float) and pd.isna(v)) or pd.isna(v):
                continue
            s = str(v).strip().strip('"')
            if s and s.lower() not in ("nan", "none"):
                return False
        return True

    for i in range(len(df_raw)):
        row = df_raw.iloc[i]
        first_cell = _cell0(row)
        first_cell_lower = first_cell.lower()

        if not first_cell_lower:
            continue

        if "realized gain/loss - lot details" in first_cell_lower:
            continue

        is_account_row = any(first_cell_lower.startswith(p) for p in ACCOUNT_PATTERNS)
        empty_trailing = _trailing_empty(row)

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
        if section["data_start"] < 0 or section["data_end"] < section["data_start"]:
            continue
        if section["data_start"] <= section["data_end"]:
            has_valid_data = False
            for i in range(section["data_start"], section["data_end"] + 1):
                row_val_0 = _cell0(df_raw.iloc[i]).lower()
                if row_val_0 and row_val_0 != "there are no transactions available for your search criteria...":
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

def _single_account_section_from_title(df_raw: pd.DataFrame) -> list[dict]:
    """
    Single-account Schwab exports have no per-account section banner.
    Title row looks like: 'Realized Gain/Loss - Lot Details for ...119 as of ...'
    followed by a Symbol header row. Synthesize one section so the lot loop works.
    """
    title_acct = None
    header_row = -1
    for i in range(min(len(df_raw), 10)):
        first = str(df_raw.iloc[i, 0]).strip().strip('"')
        lower = first.lower()
        if title_acct is None and "lot details for" in lower:
            m = re.search(r"lot details for\s+(\.{2,}\d+)", lower)
            if m:
                # Match existing Realized_GL labels: 'Individual ...119'
                title_acct = f"Individual {m.group(1)}"
            else:
                title_acct = first
        if lower == "symbol":
            header_row = i
            break

    if header_row < 0:
        return []

    account = title_acct or "Individual ...unknown"
    return [{
        "account": account,
        "header_row": header_row,
        "data_start": header_row + 1,
        "data_end": len(df_raw) - 1,
    }]


def parse_realized_gl(file_or_path) -> pd.DataFrame:
    """
    Parse Schwab Realized G/L Lot Details CSV.
    Returns clean DataFrame with one row per closed lot.

    Supports multi-account exports (account section banners) and single-account
    exports titled 'Lot Details for ...NNNN'.
    """
    # 1. Read raw with no assumed header
    df_raw = pd.read_csv(
        file_or_path,
        header=None,
        names=range(30),
        encoding="utf-8-sig",
        dtype=str,
        skip_blank_lines=False,
    )

    # 2. Find account sections (multi-account), else single-account title fallback
    sections = _find_account_sections_gl(df_raw)
    if not sections:
        sections = _single_account_section_from_title(df_raw)

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
            # Protected = tax-deferred or tax-advantaged accounts where cap gains are NOT owed.
            # Taxable = any account where realized gains trigger a federal tax liability.
            _PROTECTED_KEYWORDS = {
                "401", "ira", "roth", "sep", "simple", "hsa",
                "rollover", "beneficiary", "custodial", "contributory",
            }
            acct_lower = section["account"].lower()
            lot["is_primary_acct"] = not any(kw in acct_lower for kw in _PROTECTED_KEYWORDS)
            lot["fingerprint"]   = _make_fingerprint(lot)
            lot["winner"] = lot["gain_loss_dollars"] > 0

            all_rows.append(lot)

    return pd.DataFrame(all_rows)


_PROTECTED_ACCOUNT_KEYWORDS = {
    "401", "ira", "roth", "sep", "simple", "hsa",
    "rollover", "beneficiary", "custodial", "contributory",
}


def _is_taxable_account_label(account: str) -> bool:
    return not any(kw in account.lower() for kw in _PROTECTED_ACCOUNT_KEYWORDS)


def parse_chase_realized_gl(file_or_path) -> pd.DataFrame:
    """
    Parse Chase 'realizedGainOrLoss.xls' exports.

    Chase downloads these as UTF-8 HTML tables with a .xls extension (not real Excel).
    Returns the same lot schema as parse_realized_gl().
    """
    from html.parser import HTMLParser
    from pathlib import Path

    path = Path(file_or_path)
    raw = path.read_bytes()
    # Strip BOM if present
    if raw.startswith(b"\xef\xbb\xbf"):
        text = raw.decode("utf-8-sig")
    else:
        text = raw.decode("utf-8", errors="replace")

    if "<table" not in text.lower():
        raise ValueError(
            f"Chase G/L file does not look like an HTML table export: {path}"
        )

    class _TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.rows: list[list[str]] = []
            self._row: list[str] = []
            self._cell: list[str] | None = None
            self._in_cell = False

        def handle_starttag(self, tag, attrs):
            if tag == "tr":
                self._row = []
            elif tag in ("td", "th"):
                self._in_cell = True
                self._cell = []

        def handle_endtag(self, tag):
            if tag in ("td", "th") and self._in_cell:
                self._row.append("".join(self._cell).strip())
                self._in_cell = False
                self._cell = None
            elif tag == "tr" and self._row:
                self.rows.append(self._row)

        def handle_data(self, data):
            if self._in_cell and self._cell is not None:
                self._cell.append(data)

    parser = _TableParser()
    parser.feed(text)
    if not parser.rows:
        return pd.DataFrame()

    header = parser.rows[0]
    idx = {h: i for i, h in enumerate(header)}
    required = [
        "Ticker", "Description", "Quantity", "Acquired Date", "Sale Date",
        "Market Cost/Proceeds USD", "Cost Basis USD",
        "Short Term Realized Gain Loss USD", "Long Term Realized Gain Loss USD",
        "Total Realized Gain Loss USD", "Disallowed Loss",
        "Account Name", "Account Number", "Account Type",
    ]
    missing = [c for c in required if c not in idx]
    if missing:
        raise ValueError(f"Chase G/L missing columns: {missing}")

    def _cell(row: list[str], col: str) -> str:
        i = idx[col]
        return row[i] if i < len(row) else ""

    all_rows = []
    for row in parser.rows[1:]:
        ticker = _cell(row, "Ticker").strip()
        if not ticker or ticker.lower() == "ticker":
            continue

        st_gl = _clean_dollar(_cell(row, "Short Term Realized Gain Loss USD"))
        lt_gl = _clean_dollar(_cell(row, "Long Term Realized Gain Loss USD"))
        total_gl = _clean_dollar(_cell(row, "Total Realized Gain Loss USD"))
        proceeds = _clean_dollar(_cell(row, "Market Cost/Proceeds USD"))
        cost_basis = _clean_dollar(_cell(row, "Cost Basis USD"))
        qty = _clean_dollar(_cell(row, "Quantity"))
        disallowed = _clean_dollar(_cell(row, "Disallowed Loss"))
        unit_sale = _clean_dollar(_cell(row, "Unit Sale Price")) if "Unit Sale Price" in idx else 0.0
        unit_cost = _clean_dollar(_cell(row, "Unit Cost Basis")) if "Unit Cost Basis" in idx else 0.0
        disclaimer = _cell(row, "Disclaimers-Cost") if "Disclaimers-Cost" in idx else ""

        acct_name = _cell(row, "Account Name").strip() or "Chase"
        acct_num = _cell(row, "Account Number").strip()
        acct_type = _cell(row, "Account Type").strip()
        # Normalize to mask form Tax_Control can parse: 'Chase Self-Directed ...8895'
        if acct_num and not acct_num.startswith("."):
            acct_num = f"...{acct_num.lstrip('.')}"
        account = f"Chase {acct_name} {acct_num}".strip()

        opened = _parse_date(_cell(row, "Acquired Date"))
        closed = _parse_date(_cell(row, "Sale Date"))
        holding_days = _holding_days(opened, closed)
        # Term from holding period (IRS: >365 days = long-term), not from which
        # Chase ST/LT dollar column happens to be larger near breakeven.
        if holding_days < 0:
            # Dates unusable — fall back to Chase's own ST/LT column split.
            if abs(lt_gl) > abs(st_gl):
                term = "Long Term"
            else:
                term = "Short Term"
        elif holding_days > 365:
            term = "Long Term"
        else:
            term = "Short Term"

        lot = {
            "ticker": ticker,
            "description": _cell(row, "Description").strip(),
            "closed_date": closed,
            "opened_date": opened,
            "quantity": qty,
            "proceeds_per_share": unit_sale,
            "cost_per_share": unit_cost,
            "proceeds": proceeds,
            "cost_basis": cost_basis,
            "gain_loss_dollars": total_gl if total_gl != 0 else (st_gl + lt_gl),
            "gain_loss_pct": _clean_pct(_cell(row, "Total Realized Gain Loss %"))
                if "Total Realized Gain Loss %" in idx else 0.0,
            "lt_gain_loss": lt_gl,
            "st_gain_loss": st_gl,
            "term": term,
            "unadjusted_cost": _clean_dollar(_cell(row, "Original Cost"))
                if "Original Cost" in idx else cost_basis,
            "wash_sale": disallowed > 0 or "W" in disclaimer.upper(),
            "disallowed_loss": disallowed,
            "account": account,
            "holding_days": holding_days,
        }
        if not lot["closed_date"]:
            continue

        # Brokerage Self-Directed is taxable; IRA/401 keywords in name/type flip it off.
        taxable_probe = f"{account} {acct_type}"
        lot["is_primary_acct"] = _is_taxable_account_label(taxable_probe)
        lot["fingerprint"] = "chase|" + _make_fingerprint(lot)
        lot["winner"] = lot["gain_loss_dollars"] > 0
        all_rows.append(lot)

    return pd.DataFrame(all_rows)


def detect_realized_gl_parser(file_or_path):
    """Return 'chase' | 'schwab' based on file content."""
    from pathlib import Path
    path = Path(file_or_path)
    raw = path.read_bytes()[:500].lstrip()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    head = raw[:200].lower()
    if head.startswith(b"<table") or b"account name" in head:
        return "chase"
    return "schwab"


def parse_realized_gl_auto(file_or_path) -> pd.DataFrame:
    """Dispatch to Chase or Schwab parser."""
    kind = detect_realized_gl_parser(file_or_path)
    if kind == "chase":
        return parse_chase_realized_gl(file_or_path)
    return parse_realized_gl(file_or_path)
