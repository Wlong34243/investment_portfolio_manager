# Build: Crosshairs Fresh Feed

**Repo:** `C:\Dev\Investment_Portfolio` (authoritative).
**Date:** 2026-08-10.
**Source:** plan `crosshairs_fresh_feed` — one producer, two renderers; drop stale Agent_Outputs.

Standing conventions: archive-before-overwrite; dry run → verify → `--live`; no price targets or buy/sell language in output.

---

## Step 0 — Verification gate (LOCKED 2026-08-10)

| # | Assertion | Result |
|---|---|---|
| 0.1 | Agent_Outputs contents | 77 rows; one run `cbc10a99` / `2026-04-20 17:37`; agents = `valuation`, `thesis` only. **Whole-tab archive is safe.** |
| 0.2 | Dashboard write scope | `build_command_center.py` does `ws.clear()` + full-grid `update`. **Not range-scoped.** |
| 0.3 | Dislocation ordering | STEP 11 today; no dependency on briefing. **Safe to move before STEP 5.** |

Because of 0.2, a late reserved-range Crosshairs patch cannot work. Dislocation must run **before** the dashboard rebuild.

---

## Goal

- One ranked Crosshairs producer (Trim/Add distance, missing levels, dislocation).
- `0_DASHBOARD` renders top 5; `Decision_View` renders the full list (same array).
- Drop Agent_Outputs from the feed; archive April rows to `Agent_Outputs_Archive`.
- Move dislocation before STEP 5 so Crosshairs sees today’s scan.

## Out of scope

Typed-trigger plumbing; reviving agent writers; TWR / cash KPI honesty.

## Sequence

1. Producer `tasks/build_crosshairs.py`
2. Move dislocation before STEP 5; wire STEP 5: val → crosshairs → CC → DV
3. Strip Agent_Outputs Signal from CC/DV
4. Archive Agent_Outputs (`--live`)
5. Docs + literal verification

## Verification checklist (literal Sheet evidence, 2026-08-10)

| Check | Evidence |
|---|---|
| Decision_View header not `cbc10a99` | `CROSSHAIRS — as of 2026-08-10 09:29 — 13 items` |
| Top 5 ⊆ full list, same order | CC: GLD, JPIE, GILD, UNH, ET = Decision_View rows 1–5 |
| Missing-level visible | ET rationale includes `MISSING_LEVEL: SYSTEM: no add level (price)` |
| Agent_Outputs live | Header-only (9 cols); Archive has 75 `cbc10a99` hits |
| Signal blank | Position rows QQQM/GOOG/AMZN/JEPI/UNH Signal empty |
| Morning order | `manager.py`: STEP 4.5 Dislocation before STEP 5 Dashboard; no second scan after derive |

