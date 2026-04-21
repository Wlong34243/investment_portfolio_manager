# Phase 1.1 — Transaction Sync Diagnosis

**Date:** 2026-04-21  
**Files analyzed:** `utils/schwab_client.py`, `tasks/sync_transactions.py`

---

## Endpoint and Parameters

`fetch_transactions` in `utils/schwab_client.py`:

- Calls `client.get_accounts()` first to enumerate all account hashes.
- For each account hash, calls `client.get_transactions(acct_hash, start_datetime=..., end_datetime=...)`.
- No `types` or `symbol` filter is passed — all transaction types are fetched.
- Date range defaults to 30 days in `fetch_transactions` but `sync_transactions.py` passes 90 days.

---

## Pagination

**Not handled.** The Schwab API `GET /trader/v1/accounts/{accountHash}/transactions` returns a flat
JSON list with no `nextPageToken` or offset parameter exposed by schwab-py. For a personal portfolio
over 90–365 days the result count will not exceed the implicit API limit (~3 000), so silent
truncation is unlikely in practice. Added a warning log if result count is suspiciously round
(multiples of 500) to catch future edge cases.

---

## Fingerprint Computation (Before Fix)

```
Date|Ticker|Action|Quantity|Price
```

**Failure modes:**

1. `Action` stored as raw Schwab API type (`TRADE`, `DIVIDEND_OR_INTEREST`, etc.) rather than
   human-readable `Buy`/`Sell`/`Dividend`. This means `derive_rotations.py`'s `SELL_ACTIONS` and
   `BUY_ACTIONS` sets (which check lowercase `"sell"` / `"buy"`) never match any row — rotation
   detection has been silently broken since first deployment.

2. Same-day multi-lot trades with identical ticker, action, and price (e.g., two dividend
   reinvestment lots) would share the same fingerprint and deduplicate to one row, dropping a trade.

3. `Quantity` is extracted from `transferItems[0].get("amount")`, which for non-trade transactions
   (dividends, transfers) contains a dollar amount, not a share count. This produces spurious floats
   in the Quantity column for non-equity transactions.

4. No `activityId` / `transactionId` usage. Every Schwab transaction has a stable `activityId`
   field that is unique per transaction. Not using it means fingerprinting depends entirely on
   field-value coincidence rather than a native primary key.

---

## Error Handling (Before Fix)

```python
try:
    for acc in accounts:
        r_tx = client.get_transactions(...)
        r_tx.raise_for_status()   # <-- raises inside the loop
        ...
except Exception as e:
    logging.error(...)
    return pd.DataFrame(columns=...)   # <-- drops ALL collected data
```

If any account's transaction fetch returns 429 or 5xx:

- The exception propagates out of the per-account loop.
- The outer `except` catches it and returns an empty DataFrame.
- All transactions already fetched for previous accounts are silently discarded.
- The caller (`sync_transactions`) sees `df.empty = True` and prints "No transactions found" with no
  indication that an error occurred mid-sweep.

No retry logic exists for 429 or 5xx responses.

---

## Identified Failure Modes

| # | Mode | Severity | Root cause |
|---|------|----------|------------|
| 1 | All collected data lost on any per-account 429/5xx | High | Error handling in wrong scope |
| 2 | Action field stores raw API type, not Buy/Sell | High | No action normalization; breaks derive_rotations |
| 3 | Fingerprint collision on same-day multi-lot same-price trades | Medium | Fingerprint missing settlement_date and activityId |
| 4 | Quantity field wrong for non-equity transactions | Medium | transferItems[0].amount is dollars for dividends |
| 5 | Silent error swallowing: 429 returns empty DataFrame | Medium | No retry, no re-raise, no caller-visible signal |
| 6 | No use of Schwab-native activityId | Low | Never implemented; fallback fingerprint is fragile |

---

## Multi-Account Aggregation Bug in fetch_positions

`fetch_positions` is NOT affected by transaction handling. Positions fetch uses
`client.get_accounts(fields=...)` which is a single call that returns all accounts' positions in one
response — no per-account looping. The multi-account aggregation in `fetch_positions` is correct.
The only bug in `fetch_positions` was the silent swallowing of errors (same pattern), which was not
the transaction bug scope. Deferred to Prompt 1.3 note.

---

## Fixes Applied (Phase 1.1)

1. **Per-account error isolation**: moved each account's fetch inside its own try/except. A failed
   account is logged and skipped; other accounts' data is preserved.

2. **Exponential-backoff retry**: 3 attempts max, delays 2s → 4s → 8s, triggered on status 429 or
   HTTP 5xx. Applied at the per-account level so one slow account does not delay others indefinitely.

3. **Action normalization**: TRADE + positionEffect=OPENING → "Buy"; TRADE + CLOSING → "Sell";
   fallback to netAmount sign (negative=Buy, positive=Sell). DIVIDEND_OR_INTEREST → "Dividend".
   ELECTRONIC_FUND / WIRE_IN / WIRE_OUT / ACH_RECEIPT / ACH_DISBURSEMENT → "Transfer". Others kept
   as-is. This fixes derive_rotations silently.

4. **Enhanced fingerprint**: use `activityId` if present (stable Schwab primary key). Fallback:
   `trade_date|ticker|normalized_action|net_amount|settlement_date`. Eliminates same-day collision.

5. **Quantity extraction fix**: for TRADE transactions, use `transferItems[0].amount` (share count);
   for non-trade transactions, default Quantity to 0.0 since dollar amounts in that field are
   misleading and already captured in Net Amount.

6. **Discard logging**: every skipped transaction logs ticker, date, type, and reason at WARNING.

7. **Reconcile mode**: `--reconcile` flag in `sync transactions` fetches 90 days from Schwab,
   reads the current sheet, and prints a diff table (Schwab-only, Sheet-only, value-changed rows).
   No writes in this mode.
