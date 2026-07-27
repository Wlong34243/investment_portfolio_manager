# Thesis Sync Allocation Bug — 2026-07-26

**Severity:** high (silent). Corrupted the sizing block of all 35 synced thesis files and suppressed every ceiling breach in the vault.
**Status:** fixed in `core/thesis_sync_data.py`. Vault files need one resync to pick up correct values.

---

## Symptom

Every thesis file carried an allocation ~100x too small, and a drift figure that was negative for all 35 positions:

```
NOW_thesis.md    current_allocation: 0.01%   **Drift:** -8.99%     (actual weight 1.09%)
EMXC_thesis.md   current_allocation: 0.02%   **Drift:** -7.98%     (actual weight 2.27%)
JEPI_thesis.md   current_allocation: 0.10%   **Drift:** -7.90%     (actual weight 9.92%)
```

Because `drift = weight - ceiling` and weight was ~0, drift was ≈ `-ceiling` for every position. The vault therefore reported that nothing was anywhere near its size ceiling.

**Three genuine breaches were hidden:**

| Ticker | Ceiling | True weight | True drift | Drift as written |
|---|---|---|---|---|
| JEPI | 8.00% | 9.92% | **+1.92%** | −7.90% |
| QQQM | 8.00% | 8.72% | **+0.72%** | −7.91% |
| MELI | 3.00% | 3.07% | **+0.07%** | −2.97% |

The bundle-level `Style Size Ceiling Check` in `export_ai_briefing` was **correct** throughout — this bug was isolated to the thesis-file sync path, which is why the two surfaces disagreed.

## Root cause

`core/thesis_sync_data.py` (pre-fix, ~line 112):

```python
market_value = row.get('Market Value', 0.0)
weight = row.get('Weight', 0.0)
if weight == 0.0 and total_market_value > 0:
    weight = (market_value / total_market_value) * 100.0
```

The Holdings sheet's `Weight` column stores a **fraction** (position MV ÷ total MV), not a percentage — consistent with `utils/risk.py:69` (`Where Weight = Position_MV / Total_Portfolio_MV`).

The fallback branch scales correctly (`* 100.0`), but it only fires when `Weight == 0.0`. Whenever the column was populated — i.e. essentially always — the raw fraction was used unscaled. `0.0109` was written as `0.01%`.

`manager.py:850` already compensates for the same column with a heuristic:

```python
if df_h["Weight"].max() <= 1.5:
    df_h["Weight"] = df_h["Weight"] * 100
```

`thesis_sync_data.py` had no equivalent guard. That asymmetry is the whole bug.

## Fix

Recompute weight deterministically from market value instead of trusting the ambiguous column. The stored-column path is retained only for the degenerate case where no positions are priced.

Verified against both storage conventions — fraction-stored (actual) and percent-stored (hypothetical) — producing identical, correct output in each, and surfacing all three breaches.

## Action required

The thesis files still contain the bad values; they are rewritten on next sync.

```
python manager.py vault sync                 # DRY RUN — inspect the diff
python manager.py vault sync --show-diff     # optional, per-file detail
python manager.py vault sync --live          # promote
```

Expect all 35 files to show a changed `current_allocation` and `**Drift:**`, and JEPI / QQQM / MELI to flip to positive drift.

## Follow-up (not fixed — flagged)

`manager.py:850`'s `max <= 1.5` heuristic is unsafe in principle: a sufficiently diversified book whose largest position is under 1.5% *and* stored as percent would be multiplied by 100 (1.2% → 120%). It does not misfire on the current portfolio (max 9.92%), so it was left alone rather than touched while unrelated work was in flight. The durable fix is to make the producer write a percentage and drop both workarounds — or to have every consumer recompute from market value, as `thesis_sync_data.py` now does.

## Files touched

| File | Change | Backup |
|---|---|---|
| `core/thesis_sync_data.py` | weight recomputed deterministically | `.bak.2026-07-26T11-45-04.587469` |
