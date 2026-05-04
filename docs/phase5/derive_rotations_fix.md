# Phase 5.1 — Fix `derive_rotations.py` and harden the capture side

## Audit Results

A thorough audit of `tasks/derive_rotations.py`, `config.py`, and `manager.py` was conducted to identify the reported `Sell_Proceeds` / `Buy_Amount` column mismatch.

### Column Alignment Verification

In `tasks/derive_rotations.py`, the data is clustered and assigned to a dictionary that eventually populates the `Trade_Log_Staging` sheet.

**Before/After alignment check:**
- **Sell Proceeds:** Correctly derived from `cluster_sells["net_amount"]` and assigned to the `Sell_Proceeds` key.
- **Buy Amount:** Correctly derived from `candidate_buys["net_amount"]` and assigned to the `Buy_Amount` key.

**Example Rotation (2025 Data Simulation):**
| Cluster Side | Ticker | Amount | Column Assignment |
| :--- | :--- | :--- | :--- |
| Sell | UNH | $10,000 | `Sell_Proceeds` |
| Buy | VEA | $9,850 | `Buy_Amount` |

The code logic consistently maps these values to their respective columns in `Trade_Log_Staging` (Indices 3 and 5) and subsequently to `Trade_Log` (Indices 2 and 4) during the `journal promote` phase.

## Hardening & Fixes

While no active misalignment was found in the current code version, the following hardening measures were implemented to prevent future data corruption:

1.  **Defensive Validation:** Added `try-except` blocks around amount summation to catch and log non-numeric data issues before they reach the staging sheet.
2.  **Sanity Check (3x Bound):** If the ratio between `Sell_Proceeds` and `Buy_Amount` exceeds 3.0x (or vice versa), the `Rotation_Type` is automatically tagged as `anomalous` to alert the user during review.
3.  **Dry Run Verify:** Introduced the `--dry-run-verify` flag which provides a formatted Rich table preview of the first 5 candidates, allowing for visual confirmation of column alignment before any data is committed.

## Deduplication Fingerprint

Verified that the fingerprint formula in `tasks/derive_rotations.py`:
`hashlib.sha256(f"{dt}|{','.join(sorted(sell_tickers))}|{','.join(sorted(buy_tickers))}".encode()).hexdigest()[:12]`
is correctly carried through from `Trade_Log_Staging` to `Trade_Log` by `manager.py journal promote`, ensuring consistent deduplication across re-runs.
