# Phase 1 — Pipeline Hardening

**Prompt series for Claude Code, to be executed in order.**

Each prompt is independently runnable and scoped to a single commit. Do not start prompt N+1 until prompt N's gate criteria are met.

This series corresponds to Phase 1 in `CLAUDE.md`. At the end of this series, the pipeline produces a bundle that is fully trustworthy for the Phase 2 dashboard and Phase 3 tax module. If any prompt in this series exposes something more serious than what it's scoped to fix, **stop and flag it** rather than expanding scope inside the prompt.

---

## Context Claude Code must read first (every prompt)

Before executing any prompt in this series, read:

1. `CLAUDE.md` at the repo root — especially the "Critical Guardrails", "Data Sources", and "Phased Roadmap" sections
2. `CHANGELOG.md` — last three entries, to understand recent state
3. `PORTFOLIO_SHEET_SCHEMA.md` — the fingerprint and tab standards
4. `config.py` — all constants and thresholds

Then execute the prompt's specific steps. Do not refactor anything outside the prompt's scope.

---

## Prompt 1.1 — Fix Schwab transaction sync reliability

### Context

`tasks/sync_transactions.py` is flaky. Bill reported transactions are intermittently missing or duplicated. Before the tax module (Phase 3) can trust `RealizedGL` data, transaction sync has to be reliable. Transaction reliability is also a canary for Schwab API health in general — if transactions are flaky, assume other API paths may be too.

The root cause is likely one or more of:
- Schwab API pagination not being handled (transactions beyond the first page dropped)
- Fingerprint collisions on same-day multi-lot trades
- Multi-account aggregation bug in `fetch_positions()` leaking into transaction handling
- Silent 429/auth errors being swallowed instead of retried

### Task

1. **Diagnose first, fix second.** Read `tasks/sync_transactions.py` and `utils/schwab_client.py` end-to-end before changing anything. Write a diagnosis note to `/tmp/transaction_sync_diagnosis.md` listing:
   - What endpoint is called, with what params
   - How pagination is handled (if at all)
   - How fingerprints are computed
   - How errors are handled
   - What you believe the failure modes are

2. **Fix the identified issues.** For each failure mode in the diagnosis, implement the fix. Likely fixes:
   - Handle pagination explicitly — loop until `nextPageToken` is absent or results are empty
   - Enhance the fingerprint to include a stable per-trade Schwab ID if available (`transactionId` or similar); fall back to `trade_date|ticker|action|net_amount|settlement_date` if not
   - Add explicit retry with exponential backoff for 429 and 5xx responses (3 retries max, 2s → 4s → 8s)
   - Log every discarded transaction with a reason, so duplicates vs. errors are distinguishable

3. **Add a dry-run reconciliation mode.** New flag: `python manager.py sync transactions --reconcile`. This reads what's currently in the `Transactions` tab, fetches 90 days of transactions from Schwab, and prints a diff table: rows present in Schwab but missing from sheet, rows present in sheet but missing from Schwab, rows with changed values. No writes in this mode.

4. **Fix the multi-account aggregation bug in `fetch_positions()` if it affects transaction scope.** If transactions are being fetched per-account and not aggregated correctly, fix that at the same time. If it's a positions-only bug, note it and defer to Prompt 1.3.

### Constraints

- **Read-only API endpoints only.** Do not import or call `place_order`, `replace_order`, `cancel_order`, or any `get_orders_*` endpoint. These are prohibited per `CLAUDE.md`.
- **Do not expand the `Transactions` tab schema.** If you need more fields for fingerprinting, keep them internal to Python and only write the fields already documented in `PORTFOLIO_SHEET_SCHEMA.md`.
- **Do not touch `tasks/derive_rotations.py`** unless the transaction fingerprint change breaks it — in which case, minimally adapt `derive_rotations.py` to the new fingerprint and note it in the commit message.

### Gate criteria

All of the following must be true before moving to Prompt 1.2:

- [ ] `python manager.py sync transactions --reconcile` runs in under 60 seconds and shows zero diffs after two back-to-back runs (second run should be idempotent)
- [ ] Running `sync transactions --live` twice in a row produces zero new rows on the second run
- [ ] Reconcile run against 365 days of history shows <5 diffs (some minor drift from old data is acceptable; structural gaps are not)
- [ ] `/tmp/transaction_sync_diagnosis.md` is committed to `docs/phase1/` so the reasoning is preserved
- [ ] `CHANGELOG.md` has a new entry dated today describing the fix
- [ ] Single commit with message: `Phase 1.1: Harden transaction sync (pagination, fingerprint, retry)`

### What NOT to do

- Do not build the `health` command (Prompt 1.4)
- Do not touch FMP code (Prompt 1.2)
- Do not add tax-lot ingestion (Prompt 1.3)
- Do not refactor `utils/schwab_client.py` beyond what's needed to fix the bug

---

## Prompt 1.2 — Bake FMP fundamentals into the bundle at snapshot time

### Context

FMP fundamentals are currently fetched live by consumers (e.g., `tasks/build_valuation_card.py`) at run-time. With 50+ positions on FMP's free tier, this reliably hits 429 rate limits and makes the dashboard refresh unreliable.

The correct fix (per `CLAUDE.md`): fetch FMP once during `manager.py snapshot`, cache on disk for 14 days, bake into the bundle, and have all downstream consumers read from the bundle.

### Task

1. **Create `tasks/enrich_fmp.py`.** This task:
   - Takes a bundle path as input
   - For each ticker in the bundle (skipping excluded tickers like `CASH_MANUAL`, `QACDS`), fetches FMP fundamentals
   - Uses the existing 14-day disk cache at `data/fmp_cache/` (check and set)
   - Uses `utils/fmp_client._fmp_rate_limit()` (1.2s between HTTP calls, cache hits bypass)
   - Writes a new field `fmp_fundamentals` into each bundle position, containing at minimum: `pe_ratio`, `forward_pe`, `peg_ratio`, `debt_to_equity`, `roic`, `revenue_growth_yoy`, `gross_margin`, `net_margin`, `dividend_yield`, `payout_ratio`, `market_cap`
   - On per-ticker failure, writes `fmp_fundamentals: {"error": "reason", "fetched_at": timestamp}` and continues. One ticker failing does not abort the run.
   - Re-hashes the bundle and rewrites it (per the "bundles are immutable" guardrail — mutation requires rehash)

2. **Wire `enrich_fmp` into `snapshot` by default.** In `manager.py snapshot`:
   - Currently `--enrich-atr` and `--enrich-technicals` are opt-in flags
   - Change them to default-on, with `--no-enrich-atr` and `--no-enrich-technicals` to disable
   - Add `--no-enrich-fmp` to disable FMP enrichment if needed (e.g., for offline testing)
   - The default `snapshot` call should do: core bundle → ATR enrichment → technicals enrichment → FMP enrichment → final hash

3. **Update `tasks/build_valuation_card.py` to read from bundle, not live FMP.** Change the code path so `Valuation_Card` reads `position.fmp_fundamentals` from the bundle. If the field is missing or contains `error`, mark the row as `MONITOR` and grey it out (per existing Valuation_Card rules). Do NOT fall back to a live FMP call.

4. **Extend the cache to 14 days** (currently 7). Update `utils/fmp_client.py` cache TTL constant.

### Constraints

- **FMP is fill-in only.** yfinance remains the primary source. FMP fetches should only happen for fields yfinance couldn't provide. Preserve the existing tiered pattern in `get_fundamentals()`.
- **Do not add new vendors.** Extend `utils/fmp_client.py`. Do not introduce Alpha Vantage, Polygon, or any other source.
- **Do not expand the FMP endpoint list** beyond what's needed for the fields listed above. More endpoints means more rate-limit pressure.
- **ETFs get partial fundamentals.** Don't fail-stop if an ETF doesn't have P/E or revenue growth; record what's available, mark the rest `null`.

### Gate criteria

- [ ] `python manager.py snapshot --source auto` (no flags) completes ATR + technicals + FMP enrichment in one run
- [ ] Second `snapshot` run within 14 days uses cache and completes in <20 seconds
- [ ] `Valuation_Card` in dashboard refresh reads from bundle; no live FMP calls during dashboard refresh
- [ ] Zero 429 errors during a clean (cache-wiped) full snapshot
- [ ] Bundle JSON contains `fmp_fundamentals` dict per non-excluded position
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 1.2: Bake FMP fundamentals into bundle at snapshot time`

### What NOT to do

- Do not add tax-lot handling (that's 1.3)
- Do not touch transaction sync
- Do not add the `health` command
- Do not refactor `utils/fmp_client.py` beyond extending TTL and the rate limiter

---

## Prompt 1.3 — Add tax-lot ingestion to snapshot

### Context

Phase 3 (tax module) requires lot-level detail: acquisition date, cost basis, quantity, holding period, and days-until-long-term per lot. Schwab's API returns this on `/accounts/{accountHash}?fields=positions` when the `includeFields` parameter is set correctly.

The bundle currently captures aggregate position data (total quantity, average cost basis) but not lot detail. This prompt adds lot detail as a first-class citizen of the bundle.

### Task

1. **Extend `utils/schwab_client.py`** to fetch lot detail when requesting positions. The Schwab Accounts API supports this via `fields=positions` — verify the exact parameter name in the Schwab docs before changing the request (do not guess). If lot detail requires a separate endpoint, use it.

2. **Extend `core/bundle.py`** to include a new top-level key `tax_lots` in the bundle, structured as:
   ```json
   {
     "tax_lots": [
       {
         "ticker": "UNH",
         "account_hash": "...",
         "lot_id": "schwab-provided-id-if-available",
         "acquisition_date": "2024-03-15",
         "quantity": 25.0,
         "cost_basis_per_share": 487.23,
         "cost_basis_total": 12180.75,
         "holding_period": "long_term",   // or "short_term"
         "days_until_long_term": 0         // int, 0 if already long-term
       },
       ...
     ]
   }
   ```

3. **Account tagging preserved.** Each lot carries its `account_hash` so tax treatment can be filtered by account type later (taxable vs. IRA vs. Roth). Do not strip the account identifier. A simple `account_type` enrichment field is acceptable if the Schwab API exposes it.

4. **Derive lot detail from transactions as a fallback.** If Schwab's position endpoint does not return lot detail for a given position (some accounts, some assets), reconstruct lots from `Transactions` history using FIFO. Mark reconstructed lots with `"source": "derived"` vs. `"source": "schwab"`. The reconstruction lives in `utils/tax.py` (new file) as a pure function.

5. **`utils/tax.py` scaffolding.** Create the file with at minimum:
   - `reconstruct_lots_fifo(transactions: list, ticker: str) -> list[Lot]`
   - `classify_holding_period(acquisition_date: date, as_of: date) -> Literal["short_term", "long_term"]`
   - `days_until_long_term(acquisition_date: date, as_of: date) -> int`
   - All functions pure, no I/O, fully unit-testable. Do NOT add wash-sale or tax-estimate math in this prompt — that's Phase 3.

6. **Bundle hash includes tax lots.** The SHA256 hash computation must cover the `tax_lots` key. Verify by running `manager.py bundle verify` on a bundle produced with lot detail.

### Constraints

- **No tax math yet.** This prompt is pure data ingestion. Wash sale detection, TLH logic, estimated-tax calculations all live in Phase 3.
- **Excluded tickers.** `CASH_MANUAL` and `QACDS` don't need lot detail; skip them.
- **Do not write tax lots to a Sheet tab.** The bundle is the authoritative source; dashboard consumers will read from the bundle in Phase 3.
- **Read-only Schwab endpoints only.**

### Gate criteria

- [ ] `python manager.py snapshot --source auto` produces a bundle with `tax_lots` populated for all non-excluded positions
- [ ] At least 80% of lots should come directly from Schwab (`source: schwab`); the rest may be derived
- [ ] For 5 spot-checked tickers, the sum of lot quantities equals the total position quantity (within 0.001)
- [ ] `manager.py bundle verify` passes on a new bundle
- [ ] `utils/tax.py` has at least 5 unit tests covering holding period classification edge cases (boundary at 365 days, same-day buy-sell, etc.) — put them in `tests/test_tax.py`
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 1.3: Add tax-lot ingestion to snapshot`

### What NOT to do

- Do not compute wash sales
- Do not compute estimated tax
- Do not build the `Tax_Control` tab
- Do not add the `tax-impact` command (all Phase 3)
- Do not write lots to any Sheet tab

---

## Prompt 1.4 — Add the `health` command

### Context

The pipeline now has several trust points: Schwab API, FMP, yfinance, Google Sheets, GCS tokens, bundle recency. Before every export session (and especially before making any real trade decision), Bill needs a one-command verification that the full pipeline is green.

The `health` command is simple in design but high-value in practice: it's the single command Bill runs every morning to know whether the data he's about to look at is trustworthy.

### Task

1. **Create `manager.py health` command.** It runs a series of checks, each with a ✓/✗ status and a one-line detail. Rich table output. Exit code 0 if all pass, exit code 1 if any critical check fails, exit code 2 if only warnings.

2. **Checks to implement** (in order):

   **Critical (failure → exit 1):**
   - `schwab_token_accounts`: Can we read the Accounts token from GCS and does it have >15 min until expiry?
   - `schwab_token_market`: Same for Market token.
   - `schwab_api_positions`: Does a test call to `get_accounts_client().get_positions()` succeed?
   - `sheet_reachable`: Can we open the portfolio Sheet by ID?
   - `latest_bundle_exists`: Does at least one bundle exist in `bundles/`?

   **Warning (failure → exit 2):**
   - `latest_bundle_age`: Is the most recent bundle <24 hours old? Warn if 24–72h, fail if >72h.
   - `fmp_cache_coverage`: What % of current positions have a non-expired FMP cache entry? Warn if <80%.
   - `yfinance_connectivity`: Does a test fetch for SPY succeed?
   - `transactions_freshness`: Most recent transaction in sheet — is it within expected range? (Warn if oldest-new-transaction-in-sheet is older than 7 business days and no recent trades are known to be absent.)
   - `thesis_coverage`: What % of positions >2% weight have a `_thesis.md`? Warn if <90%.

3. **Output format.** Rich table with three columns: `Check`, `Status`, `Detail`. Status is ✓ (green), ⚠ (yellow), or ✗ (red). Detail is one line. After the table, a summary line: `X passed, Y warnings, Z failed`. Exit code per rules above.

4. **Fast by default.** The command should complete in <5 seconds on a warm run. If any check is slow (e.g., yfinance test fetch), parallelize with a thread pool.

5. **`--verbose` flag.** With `-v`, each check prints additional detail (full expiry times, full cache ages per ticker, etc.). Without it, one line per check.

### Constraints

- **No writes.** `health` is read-only. Does not touch Sheets, does not refresh caches, does not take `--live`.
- **No LLM calls.** No FMP calls either (it reads the cache metadata, doesn't test FMP live — FMP's 429s would produce false-negative health).
- **Every check is independently runnable.** If the Schwab API is down, the Sheet check should still run and report its own status.

### Gate criteria

- [ ] `python manager.py health` runs in <5 seconds on a warm system
- [ ] All critical checks pass on a healthy pipeline
- [ ] Exit codes behave correctly (test: temporarily break one check, confirm exit code)
- [ ] `-v` flag produces expanded detail
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 1.4: Add health command`

### What NOT to do

- Do not build a daemon or scheduled health monitor
- Do not send notifications or emails
- Do not auto-remediate (e.g., don't refresh tokens if they're expired — just report)
- Do not add checks for Phase 2 or Phase 3 features that don't exist yet
- Do not make `health` the entry point of other commands (it's explicit only)

---

## Phase 1 Completion Gate

Phase 1 is complete when all four prompts have been executed, gated, and committed, **and** the following end-to-end test passes on three different calendar days without any manual intervention:

```bash
# Morning check
python manager.py health
# Expect: all critical green, <=2 warnings

# Full refresh
python manager.py snapshot --source auto
python manager.py dashboard refresh --update --live

# Verify
python manager.py health
python manager.py bundle verify
```

All of the following must be true:

- [ ] `health` returns exit 0
- [ ] `snapshot` completes in <90 seconds (warm cache) or <4 minutes (cold)
- [ ] `dashboard refresh` completes without a 429 or rate-limit error
- [ ] Bundle contains `tax_lots`, `fmp_fundamentals`, `calculated_technicals`, `calculated_technical_stops`
- [ ] Re-running `sync transactions --live` immediately after produces zero new rows
- [ ] `Valuation_Card` in the Sheet has fundamentals populated for all non-ETF positions

Only after three boring mornings in a row does Phase 2 start.

---

## Notes for Bill

- **Order is non-negotiable.** Run 1.1 → 1.2 → 1.3 → 1.4. Each builds on the last. Tax-lot ingestion (1.3) will expose transaction-history gaps if 1.1 wasn't thorough.
- **If a prompt grows beyond one clean commit, stop.** That's a signal the scope was wrong or something worse is happening. Pause, write up what you found, and we'll discuss before continuing.
- **Keep the Phase 0 discipline.** No scope creep. No "while I'm here, I'll also fix X." Each prompt is a fence.
- **After Phase 1 completion,** ping for the Phase 2 prompt series (dashboard color-coding). That one's a single prompt, not a series.
