"""Fix Trade_Log April-20 column misalignment; verify dispositions; Step 0.4.

Does NOT invent Implicit_Bet. Does NOT re-promote ca3bedba if already in Trade_Log.
Fingerprint is recomputed via tasks.derive_rotations._fingerprint — never guessed.
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import config
from tasks.derive_rotations import _fingerprint
from utils.sheet_readers import get_gspread_client

CA3 = "ca3bedba-25e7-4f82-a548-82773af02d8f"

# Detector's 9 nested narrowers (see nested_groups_2026-08-08.md).
# ae34e9ca + f0662cc8 were promoted as cleans under option 2 — do not re-supersede.
# c70504cb + 25e85f9b are messy widests already superseded — leave as-is.
DETECTOR_NARROWERS = {
    "ad75b763-1add-4295-909a-b790c1d01378",
    "ae34e9ca-8846-4a66-92f1-afd891c4e9bb",
    "f0662cc8-c081-4dd1-9d0c-8a49d6ca0b10",
    "7e23318f-f13d-49a2-b742-60fc2c74a50f",
    "1a8d75da-574a-41ab-97e4-93d746c47d41",
    "1e9bddfe-0d79-4419-a4b3-7e44bafe81f6",
    "29c3af31-92c7-4527-9a8c-de469d58dcd1",
    "85fc68ae-c7e1-436c-8b80-e56195d61b76",
    "bed6d5dc-4a75-4d7f-95b9-0821e3292156",
}
PROMOTED_CLEANS = {
    "ae34e9ca-8846-4a66-92f1-afd891c4e9bb",
    "f0662cc8-c081-4dd1-9d0c-8a49d6ca0b10",
    "f5b02584-6fe4-40ed-8fb2-9bdbf1740e4f",
    CA3,
}
TO_SUPERSEDE = DETECTOR_NARROWERS - PROMOTED_CLEANS  # 7 true narrowers


def split_tickers(raw: str) -> list[str]:
    parts: list[str] = []
    for chunk in str(raw).replace("|", ",").split(","):
        t = chunk.strip().upper()
        if t and t not in parts:
            parts.append(t)
    return parts


def main() -> None:
    ss = get_gspread_client().open_by_key(config.PORTFOLIO_SHEET_ID)
    tl_ws = ss.worksheet(config.TAB_TRADE_LOG)
    tl = tl_ws.get_all_values()
    header = tl[0]
    print("Trade_Log header:", header)
    print("Trade_Log rows:", len(tl) - 1)

    # --- Locate April 20 row ---
    row_idx = None
    row: dict[str, str] = {}
    for i, r in enumerate(tl[1:], start=2):
        padded = r + [""] * (len(header) - len(r))
        d = dict(zip(header, padded))
        if d.get("Date") == "2026-04-20" and "IFRA" in str(d.get("Sell_Ticker", "")):
            row_idx = i
            row = d
            break
    if row_idx is None:
        print("ERROR: April 20 row not found")
        sys.exit(1)

    print("\n=== BEFORE (sheet row %d) ===" % row_idx)
    for k in ("Trade_Log_ID", "Fingerprint", "Sell RSI", "Sell Trend",
              "Sell vs MA200", "Buy RSI", "Buy Trend", "Buy vs MA200"):
        print(f"  {k}: {row.get(k)!r}")

    sells = split_tickers(row["Sell_Ticker"])
    buys = split_tickers(row["Buy_Ticker"])
    dt = date.fromisoformat(row["Date"])
    fp = _fingerprint(dt, sells, buys)

    # Recover RSI/Trend from mis-placed ID/Fingerprint columns
    sell_rsi = (row.get("Sell RSI") or "").strip() or (row.get("Trade_Log_ID") or "").strip()
    sell_trend = (row.get("Sell Trend") or "").strip() or (row.get("Fingerprint") or "").strip()

    # Trade_Log_ID: this hand row never had a Stage UUID — ID field held RSI.
    # Deterministic ID from date + recomputed fingerprint (not a guessed hash).
    new_id = f"2026-04-20-{fp}"

    print("\n=== CORRECT VALUES ===")
    print(f"  Sell RSI       <- {sell_rsi!r}  (was in Trade_Log_ID)")
    print(f"  Sell Trend     <- {sell_trend!r}  (was in Fingerprint)")
    print(f"  Trade_Log_ID   <- {new_id!r}  (prior '63.5' was RSI, not an ID)")
    print(f"  Fingerprint    <- {fp!r}  (recomputed _fingerprint)")
    print(f"  sells={sells}")
    print(f"  buys={buys}")

    # Write only the four cells that need correction (+ Sell RSI/Trend)
    from gspread.utils import rowcol_to_a1

    def col(name: str) -> int:
        return header.index(name) + 1

    updates = [
        {"range": rowcol_to_a1(row_idx, col("Sell RSI")), "values": [[sell_rsi]]},
        {"range": rowcol_to_a1(row_idx, col("Sell Trend")), "values": [[sell_trend]]},
        {"range": rowcol_to_a1(row_idx, col("Trade_Log_ID")), "values": [[new_id]]},
        {"range": rowcol_to_a1(row_idx, col("Fingerprint")), "values": [[fp]]},
    ]
    tl_ws.batch_update(updates, value_input_option="USER_ENTERED")
    time.sleep(1)
    print("Wrote Trade_Log April 20 correction.")

    # Patch Rotation_Review references to old id
    try:
        rr_ws = ss.worksheet(config.TAB_ROTATION_REVIEW)
        rr = rr_ws.get_all_values()
        if len(rr) > 1 and "Trade_Log_ID" in rr[0]:
            id_col = rr[0].index("Trade_Log_ID")
            fp_col = rr[0].index("Fingerprint") if "Fingerprint" in rr[0] else -1
            for i, r in enumerate(rr[1:], start=2):
                padded = r + [""] * (len(rr[0]) - len(r))
                if padded[id_col] in ("63.5", new_id) or padded[id_col] == "63.5":
                    rr_ws.update_cell(i, id_col + 1, new_id)
                    time.sleep(0.4)
                    if fp_col >= 0:
                        rr_ws.update_cell(i, fp_col + 1, fp)
                        time.sleep(0.4)
                    print(f"Rotation_Review row {i}: id/fp -> {new_id} / {fp}")
    except Exception as e:
        print(f"Rotation_Review patch skipped: {e}")

    # --- Staging: ensure narrowers superseded; ca3 note ---
    st_ws = ss.worksheet(config.TAB_TRADE_LOG_STAGING)
    st = st_ws.get_all_values()
    h = st[0]
    si = h.index("Status")
    ii = h.index("Stage_ID")

    ca_row = None
    status_updates = []
    for i, r in enumerate(st[1:], start=2):
        p = r + [""] * (len(h) - len(r))
        rid = p[ii]
        if rid == CA3:
            ca_row = dict(zip(h, p))
        if rid in TO_SUPERSEDE and p[si] != "superseded":
            status_updates.append({"range": rowcol_to_a1(i, si + 1), "values": [["superseded"]]})

    if status_updates:
        st_ws.batch_update(status_updates, value_input_option="USER_ENTERED")
        time.sleep(1)
        print(f"Marked {len(status_updates)} narrowers superseded")
    else:
        print(f"Narrowers already superseded ({len(TO_SUPERSEDE)} expected)")

    print("\n=== ca3bedba promote note ===")
    if ca_row:
        print(f"  Status={ca_row.get('Status')!r}")
        print(f"  Implicit_Bet blank: {not bool(str(ca_row.get('Implicit_Bet') or '').strip())}")
        print(f"  Thesis_Brief present: {bool(str(ca_row.get('Thesis_Brief') or '').strip())}")
        print(
            "  RATIONALE OF RECORD: Thesis_Brief (Bill's own writing — transcription, "
            "not invention; same precedent as state.md 2026-07-31). Implicit_Bet left blank."
        )
    else:
        print("  ERROR: ca3bedba missing from staging")

    # --- Step 0.4 re-check (meaningful now that FP is a hash) ---
    tl2 = tl_ws.get_all_values()
    htl = tl2[0]
    tl_fps = set()
    print("\n=== Trade_Log after fix ===")
    for r in tl2[1:]:
        d = dict(zip(htl, r + [""] * (len(htl) - len(r))))
        fpv = (d.get("Fingerprint") or "").strip()
        print(f"  {d.get('Date')} id={d.get('Trade_Log_ID')!r} fp={fpv!r}")
        if fpv:
            tl_fps.add(fpv)

    st2 = st_ws.get_all_values()
    h2 = st2[0]
    fps_st = set()
    c = Counter()
    for r in st2[1:]:
        p = r + [""] * (len(h2) - len(r))
        c[p[h2.index("Status")]] += 1
        fpv = p[h2.index("Fingerprint")].strip() if "Fingerprint" in h2 else ""
        if fpv:
            fps_st.add(fpv)

    # Overlap excluding the 4 legitimately promoted fingerprints
    promoted_fps = set()
    for r in st2[1:]:
        p = r + [""] * (len(h2) - len(r))
        if p[h2.index("Status")] == "promoted":
            promoted_fps.add(p[h2.index("Fingerprint")].strip())

    overlap_all = fps_st & tl_fps
    # Unexpected overlap = staging rows that are NOT promoted but share a TL fp
    unexpected = set()
    for r in st2[1:]:
        p = r + [""] * (len(h2) - len(r))
        fpv = p[h2.index("Fingerprint")].strip()
        if fpv in tl_fps and p[h2.index("Status")] != "promoted":
            unexpected.add((p[h2.index("Stage_ID")][:8], p[h2.index("Status")], fpv))

    print("\n=== Step 0.4 re-check ===")
    print(f"  Trade_Log fingerprint count: {len(tl_fps)}")
    print(f"  staging ∩ Trade_Log (all): {len(overlap_all)} — expected the 4 promoted")
    print(f"  unexpected non-promoted overlaps: {unexpected or 'none'}")
    print(f"  April 20 recomputed fp present: {fp in tl_fps}")
    print(f"  staging status counts: {dict(c)}")
    print(f"  TO_SUPERSEDE ({len(TO_SUPERSEDE)}): {[x[:8] for x in sorted(TO_SUPERSEDE)]}")
    print(f"  left as-is messy: c70504cb, 25e85f9b")
    print(f"  needs_rationale remaining: {c.get('needs_rationale')}")


if __name__ == "__main__":
    main()
