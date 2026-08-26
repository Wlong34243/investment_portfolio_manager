# Build: Typed triggers reachable by Crosshairs

**Repo:** `C:\Dev\Investment_Portfolio` (authoritative).
**Date:** 2026-08-24.
**Source:** briefing `exports/ai_briefing_2026-08-24_091937` (composite_hash `3dc5387c762c09095857d6f7fb07f592c2ae26bec2633f850d1f19b60942b74c`).

Standing conventions: archive-before-overwrite; dry-run → verify → `--live`; no price targets, forecasts, or buy/sell language in agent output; do not write `Target_Allocation`; do not modify `data/styles.json` or any thesis file in this build.

This prompt **implements code**. Classification of trigger types is already on disk. Do not re-open Step 2 of `prompts/trigger_types_2026-08-09.md`.

---

## Step 0 — Verification gate

Confirm against the live tree and that briefing. **STOP and report** if any row fails. Do not adapt.

| # | Assertion | How to confirm |
|---|---|---|
| 0.1 | `exports/ai_briefing_2026-08-24_091937/manifest.json` `preflight_issues` contains `SKIPPED JPIE: thesis exists in vault/theses/ but the position is not held`. | grep the JSON |
| 0.2 | That briefing's `portfolio.md` has **no JPIE holdings row**. The 2026-08-21 briefing `exports/ai_briefing_2026-08-21_084524/portfolio.md` **does** (~0.84%, 110 shares). | grep `\| JPIE \|` in both |
| 0.3 | `vault/theses/JPIE_thesis.md` exists; Scaling State `[INFERRED] reduce`; `price_trim_above: 47.5` / `price_add_below: 45.0`. | read file |
| 0.4 | `tasks/build_crosshairs.py` sources trim/add **only** from `vdata["Trim Target"]` / `vdata["Add Target"]` via `_safe_float_nonzero`. It has **no** evaluation branch on `fwd_pe_*`, `trailing_pe_*`, `pb_*`, or `discount_from_high_*`. (`trigger_type_by_ticker` may exist only as a MISSING_LEVEL **label** — that is not evaluation.) | grep |
| 0.5 | `manifest.json` `trigger_type_by_ticker` non-price **numeric** primaries are exactly: GOOG/META/UNH/VRT `fwd_pe`, AAPL `trailing_pe`, RRC `price_to_book`, IBM/WSM `discount_from_high`. (`ceiling_only` and `price` exist too; they are not this list.) | grep |

**Pre-build audit (2026-08-24, locked):** all five PASS. Layer finding below is part of the gate — if the files have moved, STOP.

---

## Audit — which layer drops the non-price bands

Read, in order: `utils/thesis_reader.py` `resolve_band_levels`, `core/composite_bundle.py` `get_ticker_triggers`, `tasks/build_valuation_card.py`, `tasks/build_crosshairs.py`.

**Finding (do not invert):**

1. **`thesis_reader.resolve_band_levels`** already resolves the **declared** type's `trim_level` / `add_level` (`fwd_pe_trim_above` etc.). It also sets `valuation_trim` / `valuation_add` to **price-denominated** values only: if `trigger_type == "price"` use the typed levels; else fall back to `price_trim_above` / `price_add_below` (often blank).

2. **`get_ticker_triggers()` carries both.** It returns `trigger_type`, `trim_level`, `add_level`, `trim_field`, `add_field`, **and** `valuation_trim` / `valuation_add`. Typed bands are **not** dropped in the bundle accessor.

3. **`build_valuation_card.py` discards the typed levels.** It writes:
   ```
   "Trim Target": triggers.get("valuation_trim", ...)
   "Add Target":  triggers.get("valuation_add", ...)
   ```
   Those columns are the **price fallback**. `trim_level` / `add_level` / `trigger_type` are never written. The tab **does** already hold live metrics Crosshairs needs: `Forward P/E (yf)`, `Trailing P/E`, `P/B`, `Discount from 52w High %`, `Price`.

4. **`build_crosshairs._near_candidates`** only does **price-distance** math against Trim/Add. It never calls `get_ticker_triggers`. Consequence: UNH (`fwd_pe` primary, **secondary** `price_add_below: 290` / `price_trim_above: 380`) currently Crosshairs-fires on **price**, not forward P/E. META has empty secondary price fields, so its typed band is invisible.

**Fix at the layer that loses the data for Crosshairs: Valuation_Card write + Crosshairs distance math together.** Do not stuff P/E numbers into `Trim Target` and leave Crosshairs assuming dollars. Do not change thesis files.

---

## Goal

Crosshairs `NEAR_TRIM` / `NEAR_ADD` evaluate the **declared** `trigger_type` against the **same metric the band was written on**. Secondary bands on the thesis (UNH price 290/380) must **not** produce a second NEAR_* row.

`ceiling_only`: no NEAR_* from valuation (already covered for MISSING_LEVEL).

`price`: keep today's formula (`(trim - price) / price`, `(price - add) / add`, `NEAR_BAND_PCT = 0.20`, through-level when dist <= 0).

---

## Metric map (mandatory)

| `trigger_type` | Current reading (Valuation_Card col) | Trim field | Add field | Through trim | Through add |
|---|---|---|---|---|---|
| `price` | `Price` | `price_trim_above` | `price_add_below` | current >= trim | current <= add |
| `fwd_pe` | `Forward P/E (yf)` | `fwd_pe_trim_above` | `fwd_pe_add_below` | current >= trim | current <= add |
| `trailing_pe` | `Trailing P/E` | `trailing_pe_trim_above` | `trailing_pe_add_below` | current >= trim | current <= add |
| `price_to_book` | `P/B` | `pb_trim_above` | `pb_add_below` | current >= trim | current <= add |
| `discount_from_high` | `Discount from 52w High %` | `trim_below_discount_pct` | `add_above_discount_pct` | current **<=** trim (near highs) | current **>=** add (deep discount) |
| `ceiling_only` | — | none | none | n/a | n/a |

Distance: reuse the existing relative formula with `current` and `level` substituted (`NEAR_BAND_PCT` still 0.20). **Never** band on trailing and evaluate on forward (or the reverse). If the live metric cell is missing/non-numeric, skip NEAR_* for that ticker (do not fall back to the other P/E).

Rationale strings must name the metric (`fwd P/E 15.85; add 18; ->Add …`), not a dollar trim, when the type is not `price`.

---

## Implementation (extend, don't proliferate)

1. **`build_valuation_card.py`**
   - Write a `Trigger Type` column (derive letter from `VALUATION_CARD_COLUMNS.index`, do not hardcode). Put it next to Trim/Add.
   - Keep `Trim Target` / `Add Target` as the **declared-type** numeric levels (`trim_level` / `add_level`), **not** the secondary price fallback. `ceiling_only` → blank Trim/Add.
   - Update `format_sheets_dashboard_v2.py` only if a column insert would misalign existing CF. Prefer append-at-end if CF is letter-fragile; say which you chose.
   - Dry-run default; `--live` already on this task — do not add a second write path.

2. **`build_crosshairs.py`**
   - `_near_candidates` must branch on declared type (from Val_Card `Trigger Type`, else `get_ticker_triggers` / `level_coverage.trigger_type_by_ticker`).
   - Current metric from the matching Val_Card column in the table above.
   - **One NEAR_* reason per ticker from valuation** — declared type only. UNH must not also fire on 290/380.
   - DISLOCATION / MISSING_LEVEL: do not start using price Trim/Add as if they were still dollars without checking type. MISSING_LEVEL already uses typed coverage — leave that path unless a regression shows otherwise.

3. **Command Center / Decision_View** — they consume `produce_crosshairs()`. If they display Trim/Add as `$`, fix the renderer so a fwd_pe row is not shown as a price. `0_DASHBOARD` is clear-and-rebuild; only change `build_command_center.py` grid construction.

4. **Do not** write a trigger that reads a sell-side price target.

---

## Acceptance tests (live numbers from the 2026-08-24 briefing)

Use the Valuation_Card / yfinance figures **as of the implementation run** if they have moved; the **relationships** must still hold. The briefing cited:

| Ticker | Type | Current | Level | Expected Crosshairs |
|---|---|---|---|---|
| META | `fwd_pe` | fwd P/E 15.85 | `fwd_pe_add_below` 18 | **NEAR_ADD, through level** |
| VRT | `fwd_pe` | fwd P/E 28.79 | `fwd_pe_add_below` 28 | **NEAR_ADD**, ~2.8% to add (inside 20% band) |
| AAPL | `trailing_pe` | trailing 35.48 | `trailing_pe_trim_above` 36.06 | **NEAR_TRIM**, ~1.6% to trim |
| UNH | `fwd_pe` | — | primary 14/18; secondary price 290/380 | **Must not double-report** NEAR_* from both bands |

Print Crosshairs stdout (or a unit test over `_near_candidates` with fixture rows) showing these four. Literal output in the checklist.

---

## Dry-run → `--live`

- `python tasks/build_valuation_card.py` (or `pm refresh dashboard`) dry-run first; **no Sheet writes**.
- `python tasks/build_crosshairs.py` already prints dry-run and does not write Sheets; CC/DV writes still need `--live`.
- Flip `--live` only after the four acceptance rows are visible in dry-run stdout.

---

## Out of scope

- JPIE archive / thesis Review Log (separate sign-off).
- `styles.json`, thesis frontmatter, `Target_Allocation`.
- New trigger types.
- MCP, Streamlit, auto-trading.

---

## Post-build checklist (literal stdout, not a PASS table)

Paste actual terminal output for each:

1. `rg -n "valuation_trim|Trigger Type|trim_level" tasks/build_valuation_card.py tasks/build_crosshairs.py`
2. Dry-run Crosshairs list including META, VRT, AAPL lines (full rationale strings).
3. UNH: at most one valuation NEAR_* row; rationale is fwd P/E, not $290/$380.
4. A ticker that is `price` (GILD or XOM) still NEAR_* on **price** if it was before.
5. `ceiling_only` names are not newly NEAR_TRIM/NEAR_ADD from empty Trim/Add.
6. `pytest` for any new unit tests you added.
7. Docs: one paragraph in `CHANGELOG.md` + `state.md` pointing at this prompt. No new root markdown files.

If a checklist item cannot be shown with stdout, it is not done.
