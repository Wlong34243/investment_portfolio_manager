# Build: Basket-Aware Rotation Attribution

**Goal:** make `Rotation_Review` answer the question Bill actually asks when he rotates —
*"did the thing I bought beat the thing I sold to fund it, for reasons other than beta?"*

**Repo:** `C:\Dev\Investment_Portfolio` (authoritative). Extend
`tasks/compute_rotation_attribution.py`. Do not create a parallel module.

---

## Why this build exists

Bill's rotation pattern, in his words: he finds a new investment (a name that sold off 20%
with 80% margins and 100% growth), or a narrative turns (a hyperscaler reporting AI monetization
and 12–18 month order backlogs) — **and he funds it by selling low-beta, safe, or weaker
holdings.** The August 2026 rotation is the canonical shape: sold JEPI, JPIE, KRE, APO, ES, EWZ,
IFRA, GILD, QQQM, COF ($72,870.63) into QQQM, IBM, VST, XOM, PWR, VRT, UNH, IFRA, COWZ, RRC, MU,
XLF ($73,571.79).

**The basket is the unit of analysis. This is confirmed and is not to be redesigned.** One
conviction, one funding decision, expressed as dozens of transactions over several days. Do not
split baskets into synthetic pairs.

The current code assumes one ticker per side, so it has never produced a usable row. `Trade_Log`
has one entry (2026-04-20) and `Rotation_Review` has never held data — roughly 15 months of
rotations are unmeasured.

### The trap this build must not fall into

Bill systematically **sells low beta and buys high beta.** In a rising market a naive pair
return will be positive on essentially every rotation, and will report as skill what is
actually just beta. A tool that always says "risk-on worked" during a bull run tells him
nothing he does not already know, and would be actively misleading as a track record.

**The headline output must therefore separate the beta-explained portion from the residual.**
That residual is the only number that says anything about selection.

---

## Step 0 — Verification gate

Report a PASS/FAIL table with literal output. Stop and report on any discrepancy.

| # | Assertion |
|---|---|
| 0.1 | `tasks/compute_rotation_attribution.py` exists and defines `run_attribution(live: bool)`, `compute_return(ticker, anchor_date, trading_days, cash_yield)`, `get_ohlcv(ticker, start_date)`. |
| 0.2 | `config.ROTATION_REVIEW_COLUMNS` exists with the 20 columns ending `Attribution_As_Of`. |
| 0.3 | `config.TRADE_LOG_COLUMNS` uses singular `Sell_Ticker` / `Buy_Ticker`, and `Trade_Log` rows may contain comma-joined multi-ticker strings in those fields. |
| 0.4 | The Transactions tab (`config.TAB_TRANSACTIONS`) exposes per-transaction date, ticker, action and a dollar amount column (`net_amount` or `amount`) — confirm the actual header names, do not assume. `_read_transactions()` in `tasks/derive_rotations.py` already normalizes these; reuse that logic rather than rewriting it. |
| 0.5 | Existing caching behaviour: rows are skipped when computed <7 days ago AND all horizons are filled. Confirm before changing anything. |

---

## Step 1 — Dollar weights from the transaction ledger

The Trade_Log row gives aggregate `Sell_Proceeds` and `Buy_Amount` but not the per-ticker split.
Get the split from Transactions.

- For each Trade_Log row, use `Date` plus `Sell_Dates` / `Buy_Dates` (pipe-delimited in staging;
  may be absent in Trade_Log — fall back to a window anchored on `Date` spanning
  `Cluster_Window_Days`, defaulting to the observed span).
- Sum the dollar amount per ticker per side within that window.
- Weight = ticker dollars ÷ side total.
- **Reconcile against the row's stated `Sell_Proceeds` / `Buy_Amount`. If the reconstructed
  total differs by more than 2%, write the row's status as `WEIGHTS_UNRECONCILED` and skip the
  return computation.** A silently wrong weight is worse than a blank.
- Equal-weighting is not acceptable as a fallback. If weights cannot be reconstructed, skip.

## Step 2 — Tickers on both sides

`QQQM` and `IFRA` appear on both sides of the August basket, because Bill trimmed and added
within the window.

- **Net them within the side they dominate**, and record the gross figures.
- Emit `Both_Sides_Tickers` listing any ticker that appeared on both sides, so the row is
  legible rather than quietly adjusted.
- Do not drop them.

## Step 3 — Weighted returns

Reuse the existing `compute_return()` per ticker — do not reimplement horizons or the
`CASH` cash-yield handling.

- `Sell_Return_Nd` = Σ(weight × return) across sell-side tickers.
- `Buy_Return_Nd` = same for buy side.
- `Pair_Return_Nd` = Buy − Sell. Horizons stay 30/90/180 trading days.
- If any ticker's price history is unavailable, exclude it and **renormalize the remaining
  weights**, then record `Coverage_Pct` = share of side dollars actually priced. Report a row
  with `Coverage_Pct` below 90% but flag it.

## Step 4 — Benchmarks and beta (the part that makes this honest)

### 4a. Three benchmarks, because they answer three different questions

Compute each over the same anchor date and horizon (30/90/180 trading days), total return:

| Ticker | Column | What it answers |
|---|---|---|
| **SPY** | `Bench_SPY_Nd` | The convention. Large-cap US, the default yardstick. |
| **VTI** | `Bench_VTI_Nd` | **The real counterfactual.** Bill *holds* VTI (3.66%) as core ballast, so "what if I had just added to VTI instead" is a decision he could actually have made. |
| **QQQ** | `Bench_QQQ_Nd` | Growth/tech. Bill holds **QQQM** (11.10%), the same index at a lower fee, and QQQM is frequently the *funding* side of these rotations. Use QQQ for the longer price history; record in `Bench_QQQ_Note` that the held equivalent is QQQM. |

### 4b. Two counterfactuals, reported side by side

These are different questions and both belong in the output:

- `Pair_Return_Nd` = `Buy_Return_Nd` − `Sell_Return_Nd`
  → *"Did what I bought beat what I sold to fund it?"*
- `Vs_Index_Nd` = `Buy_Return_Nd` − `Bench_VTI_Nd`
  → *"Did the new idea beat just putting the proceeds in the index?"*

The second is the harsher and more honest one, because doing nothing clever is always an
available option. **Report both. Do not collapse them into one number.**

Also emit `Sell_Vs_Index_Nd` = `Sell_Return_Nd` − `Bench_VTI_Nd`, which says whether the
funding side was actually dead weight or whether Bill sold something that went on to do fine.

### 4c. Beta decomposition

Beta needs a single reference. **Use SPY** and record it in `Beta_Reference` so the choice is
explicit and changeable.

- `Sell_Beta_Weighted` / `Buy_Beta_Weighted` — dollar-weighted beta per side. Source beta from
  the existing enrichment path if one exists (check `utils/fmp_client.py` and `tasks/enrich_*.py`
  before adding anything); otherwise compute trailing 1-year weekly beta vs SPY from `get_ohlcv`
  data already being fetched. **Do not add a new vendor.**
- `Beta_Explained_Pair_Nd` = (`Buy_Beta_Weighted` − `Sell_Beta_Weighted`) × `Bench_SPY_Nd`
- `Residual_Pair_Nd` = `Pair_Return_Nd` − `Beta_Explained_Pair_Nd`

`Residual_Pair_Nd` is the headline. Order the columns so it reads before the raw pair return,
and label it plainly — "selection, net of the risk step-up" or similar.

### 4d. Guard against benchmark shopping

Three benchmarks means three chances to find the flattering one. Mitigate in the output itself:

- **VTI is the primary.** `Vs_Index_Nd` uses VTI and is the number presented first among the
  index comparisons. SPY and QQQ are context columns.
- Emit `Bench_Spread_Nd` = max(SPY, VTI, QQQ) − min(SPY, VTI, QQQ) for the window. When that
  spread is wide, the choice of benchmark is doing real work and the comparison is fragile —
  surface it rather than letting it hide.
- Never emit a "best benchmark" or auto-select the one the rotation beats.

## Step 5 — Nested and superseded rows

`derive_rotations` clusters by date window. Re-running it daily against an open window emits a
new, larger superset each time — five rows exist for the single 2026-08-03 basket, each with a
different fingerprint, so fingerprint dedup does not catch them.

- Detect rows sharing an anchor `Date` where one row's sell and buy ticker sets are **supersets**
  of another's.
- Attribute **only the widest** row in each nested group. Mark the narrower ones
  `SUPERSEDED_BY: <Trade_Log_ID>` in the review output and skip computation.
- **Report the groups found. Do not delete or modify anything in `Trade_Log` or
  `Trade_Log_Staging`** — this build reads them, it does not clean them.

## Step 6 — Wiring and output

- Extend `config.ROTATION_REVIEW_COLUMNS` with the new fields. Preserve existing column order
  and append; do not reorder existing columns.
- Preserve the existing cache behaviour and the `--live` gate. **Dry run must print the full
  computed table without writing.**
- `Rotation_Review` is a derived, rebuildable tab, so a clear-and-rebuild is acceptable — but
  archive the prior contents first, per the repo's archive-before-overwrite convention.
- Also write a local markdown summary to `agent_outputs/rotation_attribution/` dated by run,
  so results are readable without opening the Sheet.

---

## Step 7 — Verification

Paste literal output for each.

- [ ] Step 0 table.
- [ ] Dry run on the current `Trade_Log` (one row, 2026-04-20) completes and prints a table.
- [ ] **Backfill test.** Promote nothing. Instead run the computation against the 2026-05-07 /
      2026-05-08 rows sitting in `Trade_Log_Staging` as a read-only exercise, and paste the
      result. Those two rows have identical ticker sets on both sides with different proceeds —
      the nested-group detector should catch them. If it does not, Step 5 is wrong.
- [ ] Weight reconciliation: for one basket, paste the per-ticker dollar splits and show the
      reconstructed total against the row's stated `Sell_Proceeds` / `Buy_Amount`.
- [ ] A row where `Both_Sides_Tickers` is non-empty, showing QQQM and IFRA handled per Step 2.
- [ ] A worked beta example: raw pair return, `Bench_SPY_Nd`, both weighted betas,
      beta-explained, residual — with the arithmetic shown so the decomposition can be checked
      by hand.
- [ ] All three benchmarks resolve and return sane values for one horizon. Paste
      `Bench_SPY_Nd`, `Bench_VTI_Nd`, `Bench_QQQ_Nd` and `Bench_Spread_Nd` for one row, and
      confirm they are total returns (distributions included), not price-only. If the data
      source gives price-only, say so explicitly rather than silently understating the
      benchmarks — VTI and SPY distributions are material over 180 days.
- [ ] Both counterfactuals present and distinct: `Pair_Return_Nd` and `Vs_Index_Nd` for the
      same row, with `Sell_Vs_Index_Nd` alongside.
- [ ] Nothing was written to the Google Sheet unless `--live` was passed. State explicitly.
- [ ] `state.md` and `CHANGELOG.md` updated with one dated entry each.

## Out of scope

- Do not modify `Trade_Log` or `Trade_Log_Staging` contents.
- Do not change `derive_rotations.py` clustering. The superset problem is real but it is a
  separate build; this one reads around it.
- Do not split baskets into synthetic pairs.
- Do not add a data vendor. Extend `utils/fmp_client.py` if fundamentals are needed.
- Do not attempt tax-lot or realized-G/L logic. This is price attribution only.
- No price targets, no forecasts, no buy/sell language in any output.

## Open question for Bill — answer before Step 4 is final

Beta is one way to normalize the risk step-up, and it is the cheapest. It is not the only one,
and it is weakest exactly where Bill trades: JEPI is not plain low-beta equity, it is
risk-managed income with an options overlay, so its realized beta understates what he is
actually giving up. If the residual looks wrong on the JEPI/JPIE-funded baskets, the fix is a
different normalizer — volatility-matched or a simple "what if I had held the funding side"
counterfactual — not a patch to the beta math. **Flag this rather than solving it silently.**
