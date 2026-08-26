# Prompt — Schwab Data Expansion, Phase 1: Client Extension

**Created:** 2026-08-25
**Executor:** Claude Code or Gemini CLI, run locally in `C:\Dev\Investment_Portfolio`
**Phase:** 1 of 4 (see `## Roadmap Position` at the end)
**Nature:** Purely additive. No existing consumer changes behaviour in this phase.

---

## Why this exists

An audit on 2026-08-25 established that `utils/schwab_client.py` calls **four** Schwab
endpoints — `get_accounts(fields=POSITIONS)`, `get_account_numbers()`,
`get_transactions()`, `get_quotes()` — while the price-history, fundamentals,
market-hours, movers and instrument-search families are unused. Meanwhile **yfinance is
the price-history backbone for at least nine modules**, including
`compute_rotation_attribution.py`, which benchmarks every rotation against SPY/VTI/QQQ.

This phase adds the missing gatherers and a reconciliation harness. It migrates nothing.
Phase 2 migrates consumers, and only against evidence this phase produces.

---

## Hard constraints (do not violate; these are repo rules, not preferences)

1. **Do not import, reference, or call `place_order`, `replace_order`, `cancel_order`,
   `get_orders_for_account`, or `get_orders_for_all_linked_accounts`.** Read-only on the
   brokerage is Hard Rule 1 and applies at module level, not verb level.
2. **Python gathers; LLMs reason.** Everything here is a deterministic Python gatherer.
   No agent call in this phase.
3. **No new vendor.** Schwab is already authenticated; this adds no third-party key.
   Do not touch `utils/fmp_client.py` or `utils/finnhub_client.py`.
4. **No Sheet writes in this phase at all.** Not gated behind `--live` — absent entirely.
5. **Do not modify `fetch_positions()`, `fetch_transactions()`, or `fetch_tax_lots()`.**
   They are correct as of the 2026-08-03 account-scope fix and are out of scope here.
6. Account scoping via `_require_account_scope()` applies to any new **accounts-client**
   call. Market-data calls are not account-scoped and must not call it.

---

## Step 0 — Verification gate (STOP if any check fails)

Run each check and paste **literal stdout** into your report. Do not proceed on a
mismatch; report the discrepancy and stop.

```
0.1  wc -l utils/schwab_client.py
     EXPECT: 780 (±20 acceptable; a large delta means the file moved under you — stop)

0.2  grep -nE "^def " utils/schwab_client.py
     EXPECT to see, in order: get_accounts_client(26), get_market_client(52),
     _force_unscoped_allowed(82), _require_account_scope(91), _is_primary_account(115),
     _classify_tax_treatment(129), fetch_positions(147), _normalize_action(411),
     _fetch_account_transactions(429), fetch_transactions(492), fetch_tax_lots(636),
     fetch_quotes(736), is_api_available(773)

0.3  grep -nE "client\.get_[a-z_]+" utils/schwab_client.py
     EXPECT exactly four distinct endpoints: get_accounts, get_account_numbers,
     get_transactions, get_quotes. If a fifth appears, this prompt's premise is stale — stop.

0.4  python -c "import schwab, inspect; c=schwab.client.Client; print([m for m in dir(c) if m.startswith('get_price_history') or m in ('get_instruments','get_market_hours','get_movers','get_instrument_by_cusip','get_user_preferences')])"
     EXPECT the installed schwab-py exposes get_price_history_every_day,
     get_price_history_every_minute (and the 5/10/15/30-minute variants),
     get_price_history, get_instruments, get_market_hours, get_movers.
     If the installed version lacks any of these, record the version
     (pip show schwab-py) and stop.

0.5  grep -nE "SCHWAB_TOKEN_BLOB_ACCOUNTS|SCHWAB_TOKEN_BLOB_MARKET|SCHWAB_PRIMARY_ACCOUNT_SUFFIXES" config.py
     EXPECT all three present. Confirm the market-data client uses the MARKET blob.

0.6  sed -n '60,130p' tasks/health.py
     EXPECT _token_expiry_seconds() reading token["expires_at"] with an
     issued_at + expires_in fallback. Confirm nothing in this file inspects
     refresh-token age.

0.7  ls data/ | head -30
     Record whether a cache directory convention already exists
     (data/fmp_cache/ is known to exist). New caches follow that convention.
```

---

## Step 1 — Config constants

Add to `config.py`, adjacent to the existing `SCHWAB_*` block. **Do not invent names that
collide with existing constants** — grep first.

```python
# --- Schwab market data (added 2026-08-25, Phase 1) -------------------------
PRICE_HISTORY_SOURCE       = os.getenv("PRICE_HISTORY_SOURCE", "yfinance")  # yfinance | schwab | auto
PRICE_HISTORY_CACHE_DIR    = Path("data/schwab_price_cache")
PRICE_HISTORY_CACHE_TTL_H  = int(os.getenv("PRICE_HISTORY_CACHE_TTL_H", "20"))
SCHWAB_MAX_RETRIES         = int(os.getenv("SCHWAB_MAX_RETRIES", "3"))
SCHWAB_REFRESH_TOKEN_WARN_DAYS = float(os.getenv("SCHWAB_REFRESH_TOKEN_WARN_DAYS", "2.0"))
```

`PRICE_HISTORY_SOURCE` defaults to `yfinance` deliberately: **this phase must not change
any existing behaviour.** Phase 2 flips it per-consumer.

**Verified 2026-08-25: `config.py` has no `DATA_DIR` constant.** Use the literal
`Path("data/schwab_price_cache")` above, matching the existing `Path("data/fmp_cache")`
style. Do not introduce a `DATA_DIR` abstraction as a side effect of this phase.

---

## Step 2 — `fetch_price_history()`

Add to `utils/schwab_client.py`, after `fetch_quotes()`.

```python
def fetch_price_history(
    client: "schwab.client.Client",
    ticker: str,
    period_days: int = 365,
    interval: str = "daily",      # "daily" | "weekly" | "30min" | "15min" | "5min" | "1min"
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Daily/intraday OHLCV bars from the Schwab market-data client.

    Returns a DataFrame indexed by tz-aware UTC datetime with columns:
        open, high, low, close, volume
    Returns an EMPTY DataFrame on any failure — never raises, never returns partial
    data silently. Callers must check .empty.
    """
```

Requirements:

- Use the **market-data client** (`get_market_client()`), not the accounts client.
- Map `interval` to the schwab-py convenience methods
  (`get_price_history_every_day`, `_every_week`, `_every_thirty_minutes`, etc.).
  Do not hand-roll `get_price_history()` with raw enums unless an interval has no
  convenience method.
- Schwab returns epoch **milliseconds** in `candles[].datetime`. Convert to
  tz-aware UTC. Getting this wrong by a factor of 1000 is the single most likely
  defect in this step — assert the first candle's year is between 1985 and the
  current year, and log an ERROR and return empty if not.
- Retry on HTTP 429 and 5xx with exponential backoff, `SCHWAB_MAX_RETRIES` attempts.
  Do not retry 4xx other than 429.
- Disk cache to `PRICE_HISTORY_CACHE_DIR/{ticker}_{interval}_{period_days}.parquet`
  (fall back to CSV if pyarrow is absent — check, do not assume). Cache is valid for
  `PRICE_HISTORY_CACHE_TTL_H` hours. `use_cache=False` bypasses read but still writes.
- **Document the adjustment semantics in the docstring.** Schwab daily bars are
  split-adjusted; whether they are dividend-adjusted is NOT assumed by this prompt.
  Step 5 measures it. Until then the docstring must say
  `adjustment: split-adjusted; dividend adjustment UNVERIFIED (see Step 5)`.
- Depth ceilings, enforced with a warning rather than a silent truncation:
  1-minute ≈ 30–35 days, 5/10/15/30-minute ≈ 9 months, daily/weekly effectively
  unlimited. If `period_days` exceeds the ceiling for the requested interval, log a
  WARNING naming both numbers and clamp.

Also add a batch helper:

```python
def fetch_price_history_batch(
    client, tickers: list[str], period_days: int = 365, interval: str = "daily"
) -> dict[str, pd.DataFrame]:
```

Sequential with a small inter-request sleep. **Do not parallelise.** The published
per-app rate limit could not be confirmed in official documentation during the audit;
treat it as unknown and stay conservative until a 429 tells you otherwise. Log any 429
at WARNING with the ticker and attempt number so the real ceiling becomes observable.

---

## Step 3 — `fetch_instrument_fundamentals()`

```python
def fetch_instrument_fundamentals(
    client: "schwab.client.Client", tickers: list[str]
) -> pd.DataFrame:
    """
    Fundamentals via get_instruments(projection=FUNDAMENTAL).
    One row per ticker; missing tickers are omitted, not zero-filled.
    """
```

- The response schema descends from the TD Ameritrade API. Expected fields include
  `peRatio`, `pegRatio`, `pbRatio`, `beta`, `epsTTM`, `epsChangePercentTTM`,
  `revChangeTTM`, `returnOnEquity`, `marketCap`, `marketCapFloat`, `sharesOutstanding`,
  `dividendYield`, `dividendAmount`, `dividendDate`, `high52`, `low52`,
  `vol10DayAvg`, `vol3MonthAvg`, `bookValuePerShare`, `totalDebtToEquity`,
  `quickRatio`, `currentRatio`, `netProfitMarginTTM`.
- **Do not hardcode that list as a schema.** Dump the raw JSON for three tickers
  (one megacap, one ETF, one mid-cap — e.g. `AAPL`, `VTI`, `RRC`) to
  `agent_outputs/schwab_probe/fundamentals_raw_2026-08-25.json` and build the
  extraction from what actually comes back. Paste the observed key list into your
  report. ETFs will return a materially thinner payload than equities — say so
  explicitly rather than zero-filling.
- Missing numeric fields become `None`, never `0.0`. A zero P/E is a claim; a missing
  P/E is a fact about coverage. This distinction matters downstream — the
  pandas ≥3.0 string-dtype incident (CHANGELOG 2026-08-08) was exactly this class of bug.
- **This does not replace FMP.** It is a second, independently-sourced reading of
  overlapping fields, which is worth more as a cross-check than as a replacement.

---

## Step 3b — Quote-field widening (extraction only)

`fetch_quotes()` (~line 736) extracts five fields — `lastPrice`, `bidPrice`, `askPrice`,
`totalVolume`, `netPercentChange` — from a payload carrying roughly fifty. Two of the
unused ones are being sourced elsewhere today at higher cost:

- **52-week high/low** — `tasks/dislocation_scan.py` recomputes drawdown-from-52w-high
  from yfinance bars. Schwab reports it in a call the pipeline already makes daily.
- **Dividend yield** — `fetch_positions()` sets `'Dividend Yield': 0.0` with the comment
  *"Filled by enrichment"*, and enrichment goes to yfinance/FMP. Schwab supplies it in
  the same quote response.

**This step widens the extraction. It does not rewire anything.** New columns are added
to the returned DataFrame and no existing consumer reads them. Consumer rewiring is
Phase 2, tier 8 — see `price_history_migration_2026-08-25.md`.

Procedure:

1. Dump the raw `get_quotes()` JSON for three tickers (`AAPL`, `VTI`, `JEPI`) to
   `agent_outputs/schwab_probe/quotes_raw_2026-08-25.json`. **Build the extraction from
   the observed keys**, not from this prompt's field names. Paste the observed key list
   into your report. Schwab nests quote data under per-asset-type sub-objects
   (`quote`, `fundamental`, `reference`) and the shape differs between an equity and an
   ETF — report the difference rather than flattening it away.
2. Add columns for at least: 52-week high, 52-week low, net change, dividend yield,
   dividend amount, P/E, quote timestamp, and the extended-hours quote if present.
   Missing fields become `None`, never `0.0` — same rule as Step 3.
3. **Preserve the five existing column names exactly.** Any consumer reading
   `last_price` or `change_pct` must be unaffected. Renaming a column here breaks callers
   silently.
4. Determine and report whether this account's quotes are **real-time or delayed**. The
   payload carries quote timestamps; compare one against wall clock during a live
   session. Every use proposed for these fields tolerates a delayed feed, but a delayed
   feed labelled as live is a data-provenance defect. Record the answer in the docstring.

**Explicitly forbidden in this step:** touching `fetch_positions()`'s
`'Dividend Yield': 0.0` line, touching `dislocation_scan.py`, or removing any yfinance or
FMP call. Extraction only.

---

## Step 4 — `fetch_market_hours()` and `is_trading_day()`

```python
def fetch_market_hours(client, date_: "datetime.date | None" = None) -> dict:
    """Raw get_market_hours(EQUITY) payload for date_ (default today)."""

def is_trading_day(client, date_=None) -> bool | None:
    """
    True  — regular equity session open on date_
    False — market closed (weekend/holiday)
    None  — could not determine (API failure); CALLERS MUST TREAT None AS 'unknown',
            never as False. Degrading to 'market closed' on an API error would
            silently skip a real trading day.
    """
```

The `None` case is the whole point of this signature. A boolean-only return would let an
API outage masquerade as a market holiday.

Cache the day's answer to `PRICE_HISTORY_CACHE_DIR/market_hours_{YYYY-MM-DD}.json` so the
morning pipeline costs one call, not one per consumer.

---

## Step 5 — Reconciliation harness (this is the deliverable that matters)

Create `scripts/reconcile_price_history_2026-08-25.py`. Read-only, no Sheet writes, no
`--live` flag because it writes nothing outside `agent_outputs/`.

For each of **eight** tickers — `AAPL`, `META`, `VTI`, `JEPI`, `XOM`, `RRC`, `SPY`, `GLD`
(deliberately mixed: megacap, ETF ballast, income ETF, energy, small energy, benchmark,
commodity ETF) — over the trailing 365 calendar days:

1. Pull Schwab daily bars via `fetch_price_history()`.
2. Pull yfinance daily bars two ways: `auto_adjust=True` and `auto_adjust=False`.
3. Inner-join on date and report, per ticker and per yfinance variant:
   - row count each side, and count of dates present in one but not the other
   - max absolute close deviation, and the date it occurs
   - max relative close deviation in bps, and the date
   - mean absolute relative deviation in bps
   - volume deviation (max relative)
4. Emit a markdown table to
   `agent_outputs/schwab_probe/price_history_reconciliation_2026-08-25.md`
   and print the same table to stdout.

**Interpretation rule, to be stated in the report, not decided by the script:**
if a dividend-paying ticker (`JEPI`, `XOM`, `VTI`) matches yfinance `auto_adjust=False`
far more closely than `auto_adjust=True`, Schwab bars are **not** dividend-adjusted, and
every consumer that currently relies on yfinance's default adjustment is computing a
different quantity. That finding governs Phase 2's migration order. Do not paper over it.

Also probe and report:
- `fetch_price_history('AAPL', period_days=7300)` — how far back does daily actually go?
- `fetch_price_history('AAPL', interval='1min', period_days=60)` — where does the
  intraday ceiling actually bite?
- Wall-clock seconds for a 39-ticker daily batch, cold cache and warm cache.
- Any 429 encountered, with the request rate at which it occurred.

---

## Step 6 — Refresh-token age check in `tasks/health.py`

Unrelated to market data, but it lives in this layer and `schwab_emergency_reauth.bat`
at repo root is standing evidence that it bites.

Schwab access tokens last ~30 minutes; **refresh tokens last ~7 days and an unused one
expires and requires a browser round-trip.** `health.py` currently checks access-token
expiry only. A 7:45 AM unattended run therefore has a standing weekly failure mode with
no advance warning.

Add a check that, for both token blobs:
- reads the refresh token's issue time (`creation_timestamp`, or whatever key the stored
  blob actually carries — **inspect a real token blob and report the observed keys before
  writing this**; do not assume a key name)
- computes days remaining against a 7-day life
- returns `warn` when fewer than `SCHWAB_REFRESH_TOKEN_WARN_DAYS` remain, `fail` when expired
- states the exact remediation in `result.detail`: run `schwab_emergency_reauth.bat`

**Do not** wire this to `logs/HEALTH_FAILURE.flag` as a hard failure in this phase. A
warning that a token expires in 36 hours must not halt the morning pipeline.

**Verified 2026-08-25:** the sentinel is written only for `CRITICAL` + `FAIL`. A `WARN`
returns exit code 2 and does not write the flag, and `morning`'s
`--continue-on-warning` defaults to True. A refresh-token **warn** therefore needs no
change to flag semantics — emit it at `warn` and stop there. If the executor finds
different behaviour, report it and stop rather than adjusting the sentinel.

---

## Step 7 — CLI surface

Add a hidden/debug command group in `manager.py`, following the existing Typer patterns:

```
pm probe price-history TICKER [--days 365] [--interval daily] [--no-cache]
pm probe fundamentals TICKER [TICKER ...]
pm probe market-hours [--date YYYY-MM-DD]
pm probe reconcile              # runs scripts/reconcile_price_history_2026-08-25.py
```

Read-only, prints to stdout, writes nothing outside `agent_outputs/schwab_probe/`.
No `--live` flag anywhere in this group — there is nothing to make live.

---

## Post-build verification checklist

Paste **literal stdout/stderr** for every item. An agent-reported "PASS" table is not
acceptable evidence and will be rejected — this repo has a documented history of
fabricated PASS rows (CLAUDE.md, Working Patterns).

| # | Check | Evidence required |
|---|---|---|
| 1 | `grep -nE "place_order\|cancel_order\|replace_order\|get_orders" utils/ tasks/ manager.py scripts/` | Literally zero matches |
| 2 | `pm probe price-history AAPL --days 30` | First and last 3 rows with real dates and a plausible AAPL price range |
| 3 | Epoch conversion | Print `df.index.min()` and `df.index.max()`; both must be tz-aware UTC and inside 1985–2026 |
| 4 | `pm probe price-history AAPL --days 30` run twice | Second run visibly hits cache (log line + wall-clock delta) |
| 5 | `pm probe fundamentals AAPL VTI RRC` | Full observed key list per ticker, plus the raw-JSON dump path |
| 6 | ETF thinness | Explicit statement of which fields VTI returns `None` for vs AAPL |
| 7 | `pm probe market-hours` today, plus `--date` for a known holiday and a Saturday | Three results: True / False / False, and the raw payload for one |
| 8 | `is_trading_day` failure path | Force an API failure (bad token blob path or network off) and show it returns `None`, not `False` |
| 9 | `pm probe reconcile` | The full reconciliation table, both yfinance variants |
| 10 | Dividend-adjustment verdict | One sentence: adjusted, not adjusted, or inconclusive — with the JEPI/XOM numbers that support it |
| 11 | `pm health` | Existing checks still pass; new refresh-token row present with days remaining |
| 12 | Warn does not halt | Show `pm health` with a warn-state refresh token does NOT create `logs/HEALTH_FAILURE.flag` |
| 13 | Behaviour unchanged | `pm morning --skip-export` dry-run completes with identical STEP sequence to a pre-change run; `PRICE_HISTORY_SOURCE` still reads `yfinance` |
| 14 | No Sheet writes | `grep -n "sheet_writers\|batch_update\|update_cells" utils/schwab_client.py scripts/reconcile_price_history_2026-08-25.py` → zero matches |
| 15 | Quote widening | Observed key list per ticker from the raw dump, plus the equity-vs-ETF shape difference stated |
| 16 | Quote back-compat | `fetch_quotes(["AAPL","VTI"])` before/after: the five original columns present, same names, same values |
| 17 | Quote fields unconsumed | `grep -rn "52_week\|fifty_two\|div_yield" tasks utils core --include=*.py` shows the new columns read by nothing; `fetch_positions()` still contains `'Dividend Yield': 0.0` |
| 18 | Feed latency | Real-time or delayed, with the timestamp comparison that establishes it |

---

## What this phase explicitly does NOT do

- Does not change any existing consumer. yfinance remains the live source everywhere.
- Does not touch `Risk_Metrics`, `Income_Tracking`, or any other tab.
- Does not touch cash or `CASH_MANUAL` handling — that is Phase 3, and there is a real
  finding waiting there.
- Does not add streaming, movers, or option chains. **Step 3b is not an exception to
  this** — quote-field widening extends an endpoint already in daily use; it adds no new
  endpoint family.
- Does not rewire any consumer onto the new quote fields. `dislocation_scan.py` keeps
  computing its own 52-week high from bars, and `fetch_positions()` keeps zero-filling
  `Dividend Yield`, until Phase 2 tier 8.
- Does not delete, archive, or deprecate anything.

---

## Roadmap position

| Phase | Prompt file | Gate to proceed |
|---|---|---|
| **1** | `schwab_data_expansion_2026-08-25.md` (this file) | Checklist above passes with literal output |
| 2 | `price_history_migration_2026-08-25.md` | Phase 1 reconciliation shows acceptable deviation, and the dividend-adjustment question is answered |
| 3 | `cash_income_truth_2026-08-25.md` | Independent of Phase 2; can run in parallel |
| 4 | `risk_metrics_market_calendar_2026-08-25.md` | Requires Phase 1 (bars) and Phase 2 (a settled price source) |

---

## Documentation to update on completion

Per **extend, don't proliferate** — no new root-level markdown files.

- `CHANGELOG.md` — dated entry, including the dividend-adjustment finding and the
  real-time-vs-delayed quote verdict as facts on record
- `state.md` — new subsection under "What's Working Today"
- `CLAUDE.md` — add `fetch_price_history` / `fetch_instrument_fundamentals` /
  `fetch_market_hours` to the `utils/schwab_client.py` row in Key Files, and record
  `PRICE_HISTORY_SOURCE` in the config line
- `CLAUDE.md` → **What NOT to Do** — append this line verbatim, alongside the existing
  MCP and auto-trading exclusions:

  > - Do not propose Schwab streaming (WebSocket L1/L2, order books, `ACCT_ACTIVITY`).
  >   Evaluated and declined 2026-08-25: a daily batch pipeline consumes no sub-daily
  >   latency, a persistent daemon exceeds current operational maturity, and a stream is
  >   not re-runnable, which defeats the reproducibility rationale behind "Python
  >   gathers, LLMs reason." Reasoning: `prompts/schwab_signal_layer_PROPOSAL_2026-08-25.md` §5.

  This is a standing decision, not a consequence of Phase 1's build. If Bill applies it
  by hand before this phase ships, skip it here and note that it is already present.
