# Build Prompt: Dislocation Scanner (`tasks/dislocation_scan.py`)

**For:** Claude Code, working in this repo
**Why:** The pipeline's inputs are all inward-facing (own holdings, own theses, podcasts). Nothing systematically scans for the SKHY/IBM/TSM pattern — quality franchise, double-digit selloff, cheap forward multiple — so those setups only get caught by luck. This task adds a deterministic daily screen. Facts only; no recommendations.

---

## Step 0 — Verification gate (do this before writing any code)

1. Confirm actual state of: `utils/fmp_client.py`, `utils/schwab_client.py`, `core/bundle.py`, `manager.py`, `config.py`. Read them — do not assume from filenames or this prompt.
2. Confirm whether `data/watchlist.json` exists. It should not yet.
3. Confirm how `manager.py morning` sequences steps (STEP 10 is `derive_rotations` dry-run) so the new step slots in cleanly.
4. Confirm available FMP endpoints in `fmp_client.py` (screener/quote/ratios). Extend `fmp_client.py` if needed — do NOT add a new vendor.

## Step 1 — Create `data/watchlist.json`

```json
{
  "_comment": "Non-held names to screen daily for dislocations. Bill maintains this list manually.",
  "tickers": ["TSM"]
}
```

Seed with TSM only. Bill adds names; the scanner never adds names to this file.

## Step 2 — Build `tasks/dislocation_scan.py`

Header block per repo standard (purpose, inputs, outputs, dependencies).

**Universe:** current holdings (from the market bundle / sheet reader, excluding cash rows) + `data/watchlist.json` tickers + FMP biggest-losers screen (large/mid-cap, e.g. market cap > $10B) for the trailing 1d and 5d.

**Metrics per ticker (deterministic, from FMP/yfinance already in the stack):**
- 1d / 5d / 20d return
- Drawdown from 52w high; 52w range position
- Forward P/E, PEG, P/FCF (or FCF yield), gross margin
- Sector-relative context where cheaply available (sector median forward P/E from FMP screener is fine; skip if it adds a new dependency)

**Flag logic (config-driven constants in `config.py`, not hardcoded):**
- `DISLOCATION_MIN_DRAWDOWN` (default 0.15 from 52w high, or ≤ −0.10 5d return)
- `DISLOCATION_MAX_FWD_PE` (default 18)
- Quality floor: gross margin > 30% OR positive FCF — to keep it in "boring fundamentals / GARP" territory
- Output tags each flagged name with the closest style from `data/styles.json` and whether it is HELD / WATCHLIST / SCREEN-DISCOVERED

**Output:**
- `exports/dislocation_scan_{YYYY-MM-DD_HHMMSS}.json` — full results, SHA-256 hashed per bundle conventions
- A compact markdown table appended to nothing — written as a NEW file `agent_outputs/dislocation_scan/dislocation_scan_{YYYY-MM-DD}.md` (create dir; archive-before-overwrite not needed since filenames are dated; never overwrite)
- NO Sheet writes in v1. If later promoted, target a new sandbox tab, never `Target_Allocation`.

**Hard rules:** DRY_RUN semantics not needed (no Sheet writes), but keep `--live` plumbing consistent with other tasks for future promotion. No price targets, no predictions, no buy/sell language in output — columns are metrics, not opinions.

## Step 3 — Wire into `manager.py`

- New command: `python manager.py dislocation-scan`
- Add as a step at the end of `manager.py morning` (after the AI briefing export) so the export lands before the 8:20 scheduled brief reads it.

## Step 4 — Verification checklist

- [ ] `python manager.py dislocation-scan` runs clean on live data
- [ ] Output JSON hashed; markdown table renders; both files dated, nothing overwritten
- [ ] SKHY backtest sanity check: with late-July inputs, SKHY's ~20% selloff at ~4.5x forward P/E would have been flagged
- [ ] TSM appears in universe via watchlist.json
- [ ] Cash rows / QACDS / CASH_MANUAL excluded
- [ ] No new vendors; `fmp_client.py` extended only if required
- [ ] `STATE.md` updated
- [ ] Optional: `GEMINI_REVIEW_REQUEST.md` checkpoint if design decisions came up

---

*Once this ships, the scheduled morning brief will automatically pick up `exports/dislocation_scan_*.json` as its primary idea source instead of relying on ad-hoc web search. (Tell Claude in Cowork when it ships so the task prompt gets a one-line update.)*
