"""Read-only cash-balance probe (Phase 3 Step 0.2). No Sheet writes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from utils.schwab_client import get_accounts_client, _is_primary_account  # noqa: E402

SWEEP = {"QACDS", "CASH & CASH INVESTMENTS"}
OUT = _REPO / "agent_outputs" / "schwab_probe" / "cash_balances_2026-08-25.json"


def main() -> int:
    client = get_accounts_client()
    if client is None:
        print("ERROR: accounts client unavailable")
        return 1
    from utils.schwab_client import _require_account_scope
    _require_account_scope()

    r = client.get_accounts(fields=client.Account.Fields.POSITIONS)
    r.raise_for_status()
    accounts = r.json()
    if not isinstance(accounts, list):
        print("ERROR: unexpected accounts payload")
        return 1

    dump = []
    print(
        "| Account | cashBalance | moneyMarketFund | cashAvailableForTrading | "
        "availableFunds | totalCash | liquidationValue | longMarketValue | QACDS MV |"
    )
    print("|---|---|---|---|---|---|---|---|---|")

    tot_A = tot_B = tot_C = tot_D = 0.0
    for acct_idx, acc in enumerate(accounts):
        sa = acc.get("securitiesAccount", {})
        raw = sa.get("accountNumber") or sa.get("accountId") or ""
        if not _is_primary_account(raw):
            continue
        masked = f"...{str(raw)[-4:]}" if raw else f"acct_{acct_idx}"
        cur = sa.get("currentBalances") or {}
        ini = sa.get("initialBalances") or {}
        sweep_mv = 0.0
        sweep_pos = []
        for p in sa.get("positions") or []:
            sym = (p.get("instrument") or {}).get("symbol")
            if sym in SWEEP:
                mv = float(p.get("marketValue") or 0)
                sweep_mv += mv
                sweep_pos.append({"symbol": sym, "marketValue": mv})

        def _f(d, k):
            v = d.get(k)
            if v is None or v == "":
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        A = _f(cur, "cashBalance") or 0.0
        C = _f(cur, "moneyMarketFund")
        D_lv = _f(cur, "liquidationValue")
        D_lmv = _f(cur, "longMarketValue")
        D = (D_lv - D_lmv) if (D_lv is not None and D_lmv is not None) else None
        B = sweep_mv

        tot_A += A
        tot_B += B
        if C is not None:
            tot_C += C
        if D is not None:
            tot_D += D

        print(
            f"| {masked} | {A} | {C} | {_f(cur,'cashAvailableForTrading')} | "
            f"{_f(cur,'availableFunds')} | {_f(cur,'totalCash')} | {D_lv} | {D_lmv} | {B} |"
        )
        dump.append({
            "account_masked": masked,
            "currentBalances": cur,
            "initialBalances": ini,
            "sweep_positions": sweep_pos,
            "A_cashBalance": A,
            "B_sweep_mv": B,
            "C_moneyMarketFund": C,
            "D_liq_minus_long": D,
        })

    print()
    print(f"TOTAL A (cashBalance)={tot_A:.2f}")
    print(f"TOTAL B (sweep MV)={tot_B:.2f}")
    print(f"TOTAL C (moneyMarketFund)={tot_C:.2f}")
    print(f"TOTAL D (liquidationValue - longMarketValue)={tot_D:.2f}")
    print()
    if tot_B < 1.0 and abs(tot_A - tot_D) < 5.0:
        verdict = (
            "ASSUMPTION HOLDS: B~0 and A~D. Cash is complete via cashBalance. "
            "Skip Step 1 remediation; still widen balance capture."
        )
    elif tot_B >= 1.0 and abs((tot_A + tot_B) - tot_D) < 5.0:
        verdict = (
            f"SWEEP DROPPED: B=${tot_B:.2f} materially non-zero and A+B~D. "
            f"Live defect understating portfolio by ~${tot_B:.2f}."
        )
    else:
        verdict = (
            "INCONCLUSIVE: A/B/C/D do not reconcile cleanly. STOP — do not invent a formula."
        )
    print("VERDICT:", verdict)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"accounts": dump, "totals": {
            "A": tot_A, "B": tot_B, "C": tot_C, "D": tot_D,
        }, "verdict": verdict}, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    # Inline PURE_CASH — schwab_client keeps it local to fetch_positions
    raise SystemExit(main())
