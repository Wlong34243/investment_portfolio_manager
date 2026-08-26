"""
tasks/build_income_tracking.py — fill Income_Tracking from Schwab DIVIDEND_OR_INTEREST.

Facts only. No invented qualified/non-qualified when the payload lacks the flag.
--live required for Sheet writes.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import typer

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from utils.schwab_client import get_accounts_client, fetch_transactions, fetch_positions
from utils.sheet_readers import get_gspread_client

logger = logging.getLogger(__name__)
app = typer.Typer()

# Schwab dividend payloads often omit the equity symbol and only carry an issuer
# description. Map known fragments → tickers for holdings Bill actually owns or
# recently owned. Unmatched rows keep Description and Ticker=UNRESOLVED.
_DESC_ALIASES: list[tuple[str, str]] = [
    # Longer / more specific needles first
    ("STATE STREET ENERGY SELECT SECTOR", "XLE"),
    ("ENERGY SELECT SECTOR SPDR", "XLE"),
    ("ENERGY TRANSFER", "ET"),
    ("EXXON", "XOM"),
    ("NVIDIA", "NVDA"),
    ("APPLE", "AAPL"),
    ("META PLATFORMS", "META"),
    ("GILEAD", "GILD"),
    ("EATON CORP", "ETN"),
    ("VERTIV", "VRT"),
    ("VISTRA", "VST"),
    ("AMGEN", "AMGN"),
    ("CISCO", "CSCO"),
    ("DISNEY", "DIS"),
    ("PFIZER", "PFE"),
    ("HOWMET", "HWM"),
    ("KRAFT", "KHC"),
    ("LAM RESH", "LRCX"),
    ("REALTY", "O"),
    ("AGREE REALTY", "ADC"),
    ("ARES CAPITAL", "ARCC"),
    ("STATE STREET SPDR S&P BIOTECH", "XBI"),
    ("FINANCIAL SELECT SECTOR", "XLF"),
    ("PACER US CASH COWS", "COWZ"),
    ("INVESCO NASDAQ", "QQQM"),
    ("FIFTH THIRD", "FITB"),
    ("BANK INT", "CASH_INT"),
]


def _fingerprint(row: dict) -> str:
    raw = "|".join(
        str(row.get(k, ""))
        for k in ("Ticker", "Account", "Pay Date", "Type", "Gross", "Tax Treatment")
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _resolve_ticker(desc: str, fake: str, pos: pd.DataFrame) -> str:
    """Map Schwab dividend description → ticker. Prefer explicit aliases, then holdings."""
    desc_u = (desc or "").upper().strip()
    if not desc_u:
        return str(fake or "UNRESOLVED").upper()

    for needle, sym in _DESC_ALIASES:
        if needle in desc_u:
            return sym

    # Exact ticker already present and held
    if fake and re.fullmatch(r"[A-Z]{1,5}", str(fake).upper()):
        if not pos.empty:
            tcol = "ticker" if "ticker" in pos.columns else "Ticker"
            held = set(pos[tcol].astype(str).str.upper())
            if str(fake).upper() in held:
                return str(fake).upper()

    if not pos.empty:
        tcol = "ticker" if "ticker" in pos.columns else "Ticker"
        dcol = "description" if "description" in pos.columns else "Description"
        if dcol in pos.columns:
            best_sym, best_score = None, 0
            tokens = set(re.findall(r"[A-Z0-9]+", desc_u)) - {
                "INC", "CORP", "CO", "LTD", "LP", "ETF", "THE", "AND", "OR", "USD",
                "STATE", "STREET", "SPDR", "CLASS", "A", "F",
            }
            for _, prow in pos.iterrows():
                pdesc = str(prow.get(dcol, "") or "").upper()
                if not pdesc or len(pdesc) <= 3:
                    continue  # skip ticker-as-description stubs like "ET"
                pt = set(re.findall(r"[A-Z0-9]+", pdesc))
                score = len(tokens & pt)
                if desc_u in pdesc or pdesc in desc_u:
                    score += 5
                if score > best_score:
                    best_score = score
                    best_sym = str(prow.get(tcol, "")).upper()
            if best_sym and best_score >= 2:
                return best_sym

    return "UNRESOLVED"


def _account_tax_treatment(account_label: str) -> str:
    """Best-effort from account suffix mask; blank if unknown."""
    # Positions carry tax_treatment; Cash_Flows consumers care. Map common IRA
    # suffixes if present in config comments — otherwise leave blank.
    return ""


def build_frames(days: int = 400) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    client = get_accounts_client()
    if client is None:
        raise RuntimeError("accounts client unavailable")

    end = datetime.now()
    start = end - timedelta(days=days)
    tt = [client.Transactions.TransactionType.DIVIDEND_OR_INTEREST]

    tx = fetch_transactions(client, start_date=start, end_date=end, transaction_types=tt)
    positions = fetch_positions(client)
    pos = positions if positions is not None else pd.DataFrame()

    # Re-fetch raw for qualifiedDividend (stripped by TRANSACTION_COLUMNS filter)
    # Prefer a single lightweight pass via get_transactions per account.
    qual_by_fp: dict[str, bool | None] = {}
    try:
        r_nums = client.get_account_numbers()
        r_nums.raise_for_status()
        mappings = r_nums.json()
        cursor = start
        chunks = []
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=60), end)
            chunks.append((cursor, chunk_end))
            cursor = chunk_end
        for mapping in mappings:
            acct_num = str(mapping.get("accountNumber") or "")
            if not any(acct_num.endswith(s) for s in config.SCHWAB_PRIMARY_ACCOUNT_SUFFIXES):
                continue
            h = mapping.get("hashValue")
            if not h:
                continue
            for c0, c1 in chunks:
                rr = client.get_transactions(
                    h,
                    start_date=c0.date(),
                    end_date=c1.date(),
                    transaction_types=tt,
                )
                if rr.status_code != 200:
                    continue
                for t in rr.json() or []:
                    aid = str(t.get("activityId") or "")
                    if aid:
                        qual_by_fp[aid] = t.get("qualifiedDividend")
    except Exception as e:
        logger.warning("qualifiedDividend side-pass failed: %s", e)

    block_a_rows = []
    has_any_qual = False
    if tx is not None and not tx.empty:
        for _, r in tx.iterrows():
            desc = str(r.get("Description") or "")
            fake = str(r.get("Ticker") or "")
            ticker = _resolve_ticker(desc, fake, pos)
            acct = str(r.get("Account") or "")
            pay = str(r.get("Trade Date") or "")[:10]
            action = str(r.get("Action") or "Dividend")
            gross = float(pd.to_numeric(r.get("Net Amount"), errors="coerce") or 0)
            fp = str(r.get("Fingerprint") or "")
            qual = qual_by_fp.get(fp)
            if qual is not None:
                has_any_qual = True
            tax = _account_tax_treatment(acct)
            # Enrich tax from positions if same account+ticker held
            if not tax and not pos.empty and ticker != "UNRESOLVED":
                tcol = "ticker" if "ticker" in pos.columns else "Ticker"
                ttcol = "tax_treatment" if "tax_treatment" in pos.columns else None
                if ttcol:
                    m = pos[pos[tcol].astype(str).str.upper() == ticker]
                    if not m.empty:
                        tax = str(m.iloc[0].get(ttcol) or "")
            row = {
                "Ticker": ticker,
                "Account": acct,
                "Pay Date": pay,
                "Type": action,
                "Gross": gross,
                "Tax Treatment": tax,
                "Description": desc,
                "Source": "schwab:DIVIDEND_OR_INTEREST",
            }
            if has_any_qual or qual is not None:
                row["Qualified"] = qual
            row["Fingerprint"] = _fingerprint(row)
            block_a_rows.append(row)

    block_a = pd.DataFrame(block_a_rows)
    # If any row got Qualified, ensure column on all
    if not block_a.empty and "Qualified" in block_a.columns:
        pass
    elif not block_a.empty and has_any_qual:
        block_a["Qualified"] = None

    block_b_rows = []
    if not block_a.empty:
        ttm = block_a.groupby("Ticker", as_index=False)["Gross"].sum().rename(
            columns={"Gross": "TTM Income"}
        )
        tcol = "ticker" if "ticker" in pos.columns else "Ticker"
        mvcol = "market_value" if "market_value" in pos.columns else "Market Value"
        eicol = "est_annual_income" if "est_annual_income" in pos.columns else "Est Annual Income"
        total_ttm = float(ttm["TTM Income"].sum()) or 1.0
        for _, row in ttm.iterrows():
            t = row["Ticker"]
            mv = 0.0
            est = 0.0
            if not pos.empty and t != "UNRESOLVED":
                m = pos[pos[tcol].astype(str).str.upper() == str(t).upper()]
                if not m.empty:
                    mv = float(pd.to_numeric(m.iloc[0].get(mvcol), errors="coerce") or 0)
                    est = float(pd.to_numeric(m.iloc[0].get(eicol), errors="coerce") or 0)
            ttm_inc = float(row["TTM Income"])
            block_b_rows.append({
                "Ticker": t,
                "TTM Income": ttm_inc,
                "Current Position Value": mv,
                "TTM Yield on Value": (ttm_inc / mv) if mv else None,
                "Est Forward Annual Income": est,
                "Share of Portfolio TTM Income": ttm_inc / total_ttm,
            })
    block_b = pd.DataFrame(block_b_rows)

    n_unres = int((block_a["Ticker"] == "UNRESOLVED").sum()) if not block_a.empty else 0
    if not block_a.empty and "Qualified" in block_a.columns:
        qual_note = "Qualified column from Schwab qualifiedDividend boolean (payload field, not inferred)"
    else:
        qual_note = "Qualified column omitted (no qualifiedDividend values in window)"
    header = (
        f"INCOME_TRACKING — as of {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')} — "
        f"days={days} — {qual_note} — unresolved_tickers={n_unres}"
    )
    return block_a, block_b, header


def main(live: bool = False, days: int = 400) -> None:
    block_a, block_b, header = build_frames(days=days)
    print(header)
    print("\n=== Block A — realised income ===")
    print(block_a.to_string(index=False) if not block_a.empty else "(empty)")
    print("\n=== Block B — trailing summary ===")
    print(block_b.to_string(index=False) if not block_b.empty else "(empty)")
    if not live:
        print("\nDRY RUN — no Sheet write. Re-run with --live after sign-off.")
        return

    client = get_gspread_client()
    ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
    try:
        ws = ss.worksheet(config.TAB_INCOME_TRACKING)
        prior = ws.get_all_values()
        bak = Path("data") / f"Income_Tracking_bak_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
        bak.parent.mkdir(parents=True, exist_ok=True)
        bak.write_text("\n".join(",".join(r) for r in prior), encoding="utf-8")
        print(f"Archived prior tab → {bak}")
    except Exception:
        ws = ss.add_worksheet(config.TAB_INCOME_TRACKING, rows=500, cols=12)
    values = [[header], []]
    if not block_a.empty:
        values.append(list(block_a.columns))
        values.extend(block_a.fillna("").astype(str).values.tolist())
        values.append([])
    if not block_b.empty:
        values.append(list(block_b.columns))
        values.extend(block_b.fillna("").astype(str).values.tolist())
    ws.clear()
    ws.update("A1", values, value_input_option="USER_ENTERED")
    print(f"Wrote {config.TAB_INCOME_TRACKING} ({len(block_a)} A rows, {len(block_b)} B rows)")


@app.command()
def cli(
    live: bool = typer.Option(False, "--live"),
    days: int = typer.Option(400, "--days"),
):
    main(live=live, days=days)


if __name__ == "__main__":
    app()
