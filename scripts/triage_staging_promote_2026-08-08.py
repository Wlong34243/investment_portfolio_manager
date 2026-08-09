"""Step 0/1 triage for promote_backlog_and_harden_status_2026-08-08.md — read-only."""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from tasks.compute_rotation_attribution import (
    _row_get,
    _ticker_set,
    find_superseded_groups,
    load_staging,
)
from utils.sheet_readers import get_gspread_client

OUT = _ROOT / "agent_outputs" / "trade_log_staging"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    ss = get_gspread_client().open_by_key(config.PORTFOLIO_SHEET_ID)

    # --- Step 0 ---
    tl = ss.worksheet(config.TAB_TRADE_LOG).get_all_values()
    rr = ss.worksheet(config.TAB_ROTATION_REVIEW).get_all_values()
    st_raw = ss.worksheet(config.TAB_TRADE_LOG_STAGING).get_all_values()

    print("=== STEP 0 ===")
    print(f"0.1 Trade_Log rows: {max(0, len(tl) - 1)}")
    if len(tl) > 1:
        h = tl[0]
        for r in tl[1:]:
            d = dict(zip(h, r + [""] * (len(h) - len(r))))
            print(
                f"     id={d.get('Trade_Log_ID')} date={d.get('Date')} "
                f"fp={d.get('Fingerprint')!r}"
            )

    print(f"0.2 Rotation_Review rows: {max(0, len(rr) - 1)}")
    if len(rr) > 1:
        h = rr[0]
        for r in rr[1:]:
            d = dict(zip(h, r + [""] * (len(h) - len(r))))
            print(
                f"     id={d.get('Trade_Log_ID')} status={d.get('Status')!r} "
                f"residual_30d={d.get('Residual_Pair_30d')}"
            )

    h = st_raw[0]
    statuses = Counter()
    dates = []
    fps_staging = set()
    for r in st_raw[1:]:
        padded = r + [""] * (len(h) - len(r))
        d = dict(zip(h, padded))
        stt = (d.get("Status") or "").strip()
        statuses[stt or "<blank>"] += 1
        dates.append(d.get("Date", ""))
        fp = (d.get("Fingerprint") or "").strip()
        if fp:
            fps_staging.add(fp)

    promoted_n = sum(v for k, v in statuses.items() if k.lower() == "promoted")
    print(f"0.3 Trade_Log_Staging rows: {max(0, len(st_raw) - 1)}")
    print(f"     status_breakdown: {dict(statuses)}")
    print(f"     promoted_count: {promoted_n}")

    tl_fps = set()
    if len(tl) > 1:
        htl = tl[0]
        for r in tl[1:]:
            padded = r + [""] * (len(htl) - len(r))
            d = dict(zip(htl, padded))
            fp = (d.get("Fingerprint") or "").strip()
            if fp:
                tl_fps.add(fp)
    overlap = fps_staging & tl_fps
    print(f"0.4 fingerprint overlap staging vs Trade_Log: {overlap or 'none'}")
    print(f"     Trade_Log fps: {tl_fps}")

    print("0.5 journal promote filters Status=='approved' (case-insensitive); writes 'promoted' — confirmed in manager.py:172,294")

    dates_clean = sorted(d for d in dates if d)
    print(f"0.6 staging Date span: {dates_clean[0]} -> {dates_clean[-1]} ({len(set(dates_clean))} unique dates)")

    # --- Step 1 ---
    rows = load_staging(ss)
    superseded_map, groups = find_superseded_groups(rows)
    widest_ids = set()
    for g in groups:
        widest_ids.update(g["widest_ids"])

    print("\n=== STEP 1a NESTED GROUPS ===")
    print(f"groups={len(groups)} superseded_rows={len(superseded_map)}")

    ng_lines = [
        "# Nested / superseded groups (Step 1a)",
        "",
        f"Groups found: **{len(groups)}**. Superseded member rows: **{len(superseded_map)}**.",
        "",
        "| Date | Members | Widest Stage_ID | Ticker-set difference (widest vs each narrower) |",
        "|---|---|---|---|",
    ]

    for g in sorted(groups, key=lambda x: x["Date"]):
        wid = g["widest_ids"][0]
        wr = next(x for x in rows if str(_row_get(x, "Trade_Log_ID", "Stage_ID")) == wid)
        ws = _ticker_set(str(_row_get(wr, "Sell_Ticker", "Sell_Tickers")))
        wb = _ticker_set(str(_row_get(wr, "Buy_Ticker", "Buy_Tickers")))
        diffs = []
        for rid in g["member_ids"]:
            if rid == wid:
                continue
            r = next(x for x in rows if str(_row_get(x, "Trade_Log_ID", "Stage_ID")) == rid)
            s = _ticker_set(str(_row_get(r, "Sell_Ticker", "Sell_Tickers")))
            b = _ticker_set(str(_row_get(r, "Buy_Ticker", "Buy_Tickers")))
            plus_s = ",".join(sorted(ws - s)) or "—"
            plus_b = ",".join(sorted(wb - b)) or "—"
            diffs.append(f"`{rid[:8]}…`: +sell[{plus_s}] +buy[{plus_b}]")
        member_short = ", ".join(x[:8] + "…" for x in g["member_ids"])
        ng_lines.append(
            f"| {g['Date']} | {len(g['member_ids'])}: {member_short} | `{wid[:8]}…` | "
            + "<br>".join(diffs)
            + " |"
        )
        print(
            f"  {g['Date']}: n={len(g['member_ids'])} widest={wid[:8]}… "
            f"superseded={list(g['superseded'].keys())}"
        )

    (OUT / "nested_groups_2026-08-08.md").write_text("\n".join(ng_lines) + "\n", encoding="utf-8")

    print("\n=== STEP 1b BLANK RATIONALE ===")
    blank_rows = []
    for r in rows:
        rid = str(_row_get(r, "Trade_Log_ID", "Stage_ID"))
        ib = str(_row_get(r, "Implicit_Bet") or "").strip()
        tb = str(_row_get(r, "Thesis_Brief") or "").strip()
        if not ib or not tb:
            blank_rows.append(
                {
                    "Stage_ID": rid,
                    "Date": str(_row_get(r, "Date")),
                    "Status": str(_row_get(r, "Status")),
                    "Implicit_Bet_blank": str(not bool(ib)),
                    "Thesis_Brief_blank": str(not bool(tb)),
                    "Implicit_Bet": ib,
                    "Sell": str(_row_get(r, "Sell_Ticker", "Sell_Tickers"))[:80],
                    "Buy": str(_row_get(r, "Buy_Ticker", "Buy_Tickers"))[:80],
                }
            )
    print(f"rows with blank Implicit_Bet or Thesis_Brief: {len(blank_rows)}")
    print(f"  Implicit_Bet blank: {sum(1 for b in blank_rows if b['Implicit_Bet_blank']=='True')}")
    print(f"  Thesis_Brief blank: {sum(1 for b in blank_rows if b['Thesis_Brief_blank']=='True')}")
    print(
        f"  both blank: {sum(1 for b in blank_rows if b['Implicit_Bet_blank']=='True' and b['Thesis_Brief_blank']=='True')}"
    )

    with (OUT / "blank_rationale_2026-08-08.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(blank_rows[0].keys()) if blank_rows else ["Stage_ID"])
        w.writeheader()
        w.writerows(blank_rows)

    print("\n=== STEP 1c PROPOSED DISPOSITIONS ===")
    proposals = []
    disp = Counter()
    for r in rows:
        rid = str(_row_get(r, "Trade_Log_ID", "Stage_ID"))
        ib = str(_row_get(r, "Implicit_Bet") or "").strip()
        cur = str(_row_get(r, "Status") or "").strip()
        if rid in superseded_map:
            d = "superseded"
        else:
            d = "approved" if ib else "needs_rationale"
        disp[d] += 1
        proposals.append(
            {
                "Stage_ID": rid,
                "Date": str(_row_get(r, "Date")),
                "Current_Status": cur,
                "Proposed": d,
                "Sell_Tickers": str(_row_get(r, "Sell_Ticker", "Sell_Tickers")),
                "Buy_Tickers": str(_row_get(r, "Buy_Ticker", "Buy_Tickers")),
                "Sell_Proceeds": str(_row_get(r, "Sell_Proceeds")),
                "Buy_Amount": str(_row_get(r, "Buy_Amount")),
                "Implicit_Bet": ib,
                "Thesis_Brief": str(_row_get(r, "Thesis_Brief") or "").strip(),
                "Fingerprint": str(_row_get(r, "Fingerprint")),
                "Superseded_By": superseded_map.get(rid, ""),
            }
        )

    print(dict(disp))
    path = OUT / "proposed_dispositions_2026-08-08.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(proposals[0].keys()))
        w.writeheader()
        w.writerows(sorted(proposals, key=lambda x: (x["Date"], x["Proposed"], x["Stage_ID"])))
    print(f"wrote {path}")

    # Compact approve list for the chat
    print("\n--- Proposed APPROVED (promote) ---")
    for p in sorted(proposals, key=lambda x: x["Date"]):
        if p["Proposed"] != "approved":
            continue
        print(
            f"{p['Date']} | {p['Stage_ID'][:8]}… | bet={p['Implicit_Bet'][:60]!r} | "
            f"sell={p['Sell_Tickers'][:40]} | buy={p['Buy_Tickers'][:40]}"
        )

    print("\n--- Proposed NEEDS_RATIONALE (count by date, first 30) ---")
    nr = [p for p in proposals if p["Proposed"] == "needs_rationale"]
    print(f"total needs_rationale: {len(nr)}")
    for p in sorted(nr, key=lambda x: x["Date"])[:30]:
        print(f"{p['Date']} | {p['Stage_ID'][:8]}… | sell={p['Sell_Tickers'][:50]}")
    if len(nr) > 30:
        print(f"... and {len(nr) - 30} more")

    print("\n--- Proposed SUPERSEDED ---")
    for p in sorted(proposals, key=lambda x: x["Date"]):
        if p["Proposed"] != "superseded":
            continue
        print(
            f"{p['Date']} | {p['Stage_ID'][:8]}… → {p['Superseded_By'][:8]}… | "
            f"sell={p['Sell_Tickers'][:40]}"
        )


if __name__ == "__main__":
    main()
