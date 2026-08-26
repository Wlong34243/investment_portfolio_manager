"""
Diagnose ae34e9ca's WEIGHTS_UNRECONCILED, per Bill's request 2026-08-08.

Hypothesis to confirm/refute: ae34e9ca is a hand-trimmed subset row, so ledger
reconstruction over its window over-collects transactions deliberately excluded
from this row (they belong to a sibling row instead).

Read-only. No Sheet writes.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

_ROOT = Path(__file__).parent.parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from tasks.compute_rotation_attribution import (
    _parse_date,
    _parse_money,
    _row_get,
    _split_tickers,
    load_staging,
    reconstruct_side_dollars,
    reconcile_weights,
    resolve_window,
)
from tasks.derive_rotations import _read_transactions
from utils.sheet_readers import get_gspread_client

TARGET_PREFIX = "ae34e9ca"

client = get_gspread_client()
ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
rows = load_staging(ss)

target = None
for r in rows:
    rid = str(_row_get(r, "Trade_Log_ID", "Stage_ID", default=""))
    if rid.startswith(TARGET_PREFIX):
        target = r
        break

if target is None:
    print(f"No staging row found with Stage_ID starting '{TARGET_PREFIX}'")
    sys.exit(1)

rid = str(_row_get(target, "Trade_Log_ID", "Stage_ID", default=""))
dt_str = str(_row_get(target, "Date", default=""))
anchor = _parse_date(dt_str)
sell_tickers = _split_tickers(str(_row_get(target, "Sell_Ticker", "Sell_Tickers", default="")))
buy_tickers = _split_tickers(str(_row_get(target, "Buy_Ticker", "Buy_Tickers", default="")))
stated_sell = _parse_money(_row_get(target, "Sell_Proceeds", default=0))
stated_buy = _parse_money(_row_get(target, "Buy_Amount", default=0))
status = str(_row_get(target, "Status", default=""))

print("=" * 78)
print(f"Row: {rid}  Date: {dt_str}  Status(as staged): {status}")
print(f"Sell_Tickers: {sell_tickers}  stated_sell=${stated_sell:,.2f}")
print(f"Buy_Tickers:  {buy_tickers}  stated_buy=${stated_buy:,.2f}")
print("=" * 78)

w_start, w_end, win_days = resolve_window(
    target, anchor, sell_tickers, buy_tickers, None, stated_sell, stated_buy
)
w_start_ex = w_start - timedelta(days=2)
w_end_ex = w_end + timedelta(days=2)
print(f"Resolved window: {w_start} -> {w_end}  (win_days={win_days})")
print(f"Expanded lookup window (+/-2d): {w_start_ex} -> {w_end_ex}")

since = w_start_ex - timedelta(days=14)
until = w_end_ex + timedelta(days=14)
txns = _read_transactions(since, until)
print(f"\nLoaded {len(txns)} transactions {since} -> {until}")

sell_gross = reconstruct_side_dollars(
    txns, sell_tickers, "sell", w_start_ex, w_end_ex, target_amount=stated_sell, anchor=anchor
)
buy_gross = reconstruct_side_dollars(
    txns, buy_tickers, "buy", w_start_ex, w_end_ex, target_amount=stated_buy, anchor=anchor
)
recon_sell = sum(sell_gross.values())
recon_buy = sum(buy_gross.values())
sell_ok = reconcile_weights(recon_sell, stated_sell) if stated_sell else recon_sell > 0
buy_ok = reconcile_weights(recon_buy, stated_buy) if stated_buy else recon_buy > 0

print("\n--- SELL side (post target-fit greedy selection) ---")
for t, v in sell_gross.items():
    print(f"  {t:8s} ${v:>12,.2f}")
print(f"  {'TOTAL':8s} ${recon_sell:>12,.2f}  vs stated ${stated_sell:>12,.2f}  "
      f"diff={recon_sell - stated_sell:+,.2f} ({(recon_sell-stated_sell)/stated_sell*100 if stated_sell else 0:+.1f}%)  OK={sell_ok}")

print("\n--- BUY side (post target-fit greedy selection) ---")
for t, v in buy_gross.items():
    print(f"  {t:8s} ${v:>12,.2f}")
print(f"  {'TOTAL':8s} ${recon_buy:>12,.2f}  vs stated ${stated_buy:>12,.2f}  "
      f"diff={recon_buy - stated_buy:+,.2f} ({(recon_buy-stated_buy)/stated_buy*100 if stated_buy else 0:+.1f}%)  OK={buy_ok}")

# Now show the FULL-WINDOW (pre-greedy-fit) raw ticker totals, to see what the
# window picks up before any target-fitting -- this is what "over-collects" means.
print("\n--- RAW full-window totals (no target-fit) — what the window sees ---")
df = txns[
    (txns["trade_date"] >= w_start_ex)
    & (txns["trade_date"] <= w_end_ex)
].copy()
from tasks.compute_rotation_attribution import _classify_side
df["side"] = df["action_lc"].apply(_classify_side)
df["_abs"] = df["net_amount"].apply(lambda x: abs(float(x)))

sell_all = df[(df["side"] == "sell") & (df["ticker"].isin([t.upper() for t in sell_tickers]))]
buy_all = df[(df["side"] == "buy") & (df["ticker"].isin([t.upper() for t in buy_tickers]))]
print("Full-window SELL by ticker (all txns in window matching sell_tickers, no target-fit):")
for t, g in sell_all.groupby("ticker"):
    print(f"  {t:8s} ${g['_abs'].sum():>12,.2f}  ({len(g)} txn(s), dates: {sorted(g['trade_date'].unique())})")
print(f"  Full-window SELL total: ${sell_all['_abs'].sum():,.2f}  (stated ${stated_sell:,.2f})")

print("Full-window BUY by ticker (all txns in window matching buy_tickers, no target-fit):")
for t, g in buy_all.groupby("ticker"):
    print(f"  {t:8s} ${g['_abs'].sum():>12,.2f}  ({len(g)} txn(s), dates: {sorted(g['trade_date'].unique())})")
print(f"  Full-window BUY total: ${buy_all['_abs'].sum():,.2f}  (stated ${stated_buy:,.2f})")

# Any tickers in the window (broader than sell/buy_tickers) that ALSO show up
# as sell/buy targets of OTHER staging rows on nearby dates -- evidence of a
# hand-trimmed subset whose companion transactions belong to a sibling row.
print("\n--- Sibling staging rows within +/-5 days sharing a ticker with this row ---")
this_tickers = set(t.upper() for t in sell_tickers + buy_tickers)
for r in rows:
    other_rid = str(_row_get(r, "Trade_Log_ID", "Stage_ID", default=""))
    if other_rid == rid:
        continue
    other_dt = _parse_date(str(_row_get(r, "Date", default="")))
    if other_dt is None or anchor is None:
        continue
    if abs((other_dt - anchor).days) > 5:
        continue
    other_sell = set(t.upper() for t in _split_tickers(str(_row_get(r, "Sell_Ticker", "Sell_Tickers", default=""))))
    other_buy = set(t.upper() for t in _split_tickers(str(_row_get(r, "Buy_Ticker", "Buy_Tickers", default=""))))
    overlap = this_tickers & (other_sell | other_buy)
    if overlap:
        print(f"  {other_rid} (Date {other_dt}, Status={_row_get(r, 'Status', default='')}): "
              f"sell={sorted(other_sell)} buy={sorted(other_buy)}  overlap_with_ae34e9ca={sorted(overlap)}")

print("\nDone.")
