# Desk Redesign Phase 2 — remaining pages, daily-use gaps, header TTFB

**Created:** 2026-08-28
**Executor:** Cursor (Agent mode).
**Depends on:** `prompts/desk_redesign_2026-08-28.md` (Phases 0–3, shipped 2026-08-28).
**Scope:** the five pages that never got the template layer, four workflow gaps found in daily use,
header request cost, and navigation polish. No new surfaces.

> **Audit corrections to the source plan (verified in-repo 2026-08-28 — read before starting).**
> The plan this file supersedes was written before the code was read. Five of its assumptions are wrong:
>
> 1. **`logs/last_run.json` does not exist on disk.** Header-cache invalidation cannot be keyed on its
>    mtime alone. Missing file ⇒ TTL-only expiry; never treat absence as "invalidate."
> 2. **`pm judge lifecycle` has no `--live` gate today** (`manager.py:951`) — it writes artifacts
>    unconditionally. Adding `--live` to `--missing-json` only is a deliberate asymmetry: batch
>    recompute is bounded-but-expensive, single-ticker is not. Do **not** retrofit `--live` onto the
>    existing `--ticker` / `--all` paths in this phase.
> 3. **`ui/static/desk.js` binds only `.launch-routine` inside a `.run-card`** and reads
>    `card.getAttribute("data-routine-id")`. A bare button on Position Story will not fire. Either wrap
>    it in a `.run-card` or widen the `closest()` lookup — pick one, stated in A3.
> 4. **There is no `tax_control_metrics` retrieval template.** `tax_control_lots` exists
>    (`core/retrieval/queries.py:367`); metrics live in `MetaKV` behind `store.get_tax_control_metrics()`.
>    Lots migrate to retrieval; metrics stay a store read with a one-line comment saying why.
> 5. **The stray sidebar "Rotations tab" is already gone** — Phase 0 fixed it. `base.html` links
>    `/judgment/rotations`, not the legacy `/rotations` route. C3 is a rename/dead-route decision only.

---

## Step 0 — Verification gate

Paste literal stdout for every command. **Expected** is what the 2026-08-28 audit saw. Any
disagreement ⇒ **STOP and report** — do not adapt silently.

```bash
# 0.1 — pages still on the old template layer  (expected: no output, five files unstyled)
grep -l "data-table\|signal_chip\|pct|" ui/templates/decision.html ui/templates/tax.html \
  ui/templates/precommit.html ui/templates/search.html ui/templates/ask.html

# 0.2 — header cost  (expected: retrieve() at :83, _TOKEN_CACHE only)
grep -n "retrieve\|_TOKEN_CACHE\|_TTL" ui/header_context.py

# 0.3 — sidecars missing  (expected: 0 json, 8 lifecycle md)
ls agent_outputs/judgment/*.json 2>/dev/null | wc -l
ls agent_outputs/judgment/*lifecycle*.md 2>/dev/null | wc -l

# 0.4 — uvicorn reload hardcoded  (expected: manager.py:1870 reload=False)
grep -n "reload=" manager.py

# 0.5 — crosshair row shaping lives only in cockpit  (expected: ui/cockpit.py:26 and :215, no app.py hit)
grep -n "_crosshair_row" ui/cockpit.py ui/app.py

# 0.6 — launcher binding contract  (expected: .launch-routine / .run-card / prefill_ticker)
grep -n "launch-routine\|run-card\|prefill_ticker" ui/static/desk.js

# 0.7 — last_run.json presence  (expected: No such file)
ls -la logs/last_run.json
```

---

## Phase 2A — Function (ship first, in order)

### A1 — Sidecar backfill: `pm judge lifecycle --missing-json`

**Problem:** every campaign UI path reads the `.json` sidecar; disk has markdown only, so
Position Story and `/judgment/lifecycle` fall back to regex or blanks.

Extend `judge_lifecycle` in `manager.py:951` with two options — `--missing-json` and `--live`:

- Glob `agent_outputs/judgment/*lifecycle_*.md`, skipping `lifecycle_all`, and parse the ticker with
  `ui.judgment_artifacts.parse_lifecycle_ticker` — **import it, do not re-implement the regex.**
- Dedupe to newest `.md` per ticker using the same rule as
  `judgment_artifacts.list_lifecycle_artifacts` (max mtime, path as tiebreak).
- Skip any ticker whose `.md` already has a `.json` sibling (`Path.with_suffix(".json").is_file()`).
- For each remaining ticker: `run_lifecycle(ticker=t)` then `write_judgment_report(..., slug=f"lifecycle_{t.lower()}", campaign=camp)` — that writer already emits the sidecar and calls `upsert_campaign` (`core/judgment/run.py:79`). No new writer.
- Print a table before doing anything: `ticker | action (run/skip) | md path`.
- **Dry run by default.** `--live` required to recompute. Without it, print the table and exit 0.
- Mutually exclusive with `--ticker` / `--all`; error and exit 1 if combined.
- Echo the ~2.5 min/ticker cost and the "do not pipe stdout" warning when the run list is non-empty,
  matching the `--all` warning text.

Register in `ui/routines.py` as **Tier 0, dry-run only**:

```python
_reg(_routine(
    "judge-lifecycle-missing-json",
    "Judgment — backfill missing sidecars (dry run)",
    ("manager.py", "judge", "lifecycle", "--missing-json"),
    0,
    "Lists lifecycle artifacts with no JSON sidecar. Recompute is CLI-only (--live).",
    timeout_sec=120,
    group="REVIEW",
))
```

`build_argv` needs **no new branch** — the flag is in the frozen argv tuple. Do not add the `--live`
form to `UI_APPROVED_LIVE_IDS`; a 2.5-min-per-ticker batch is not a browser-button routine.

### A2 — Header cache (full dict, not just the token probe)

`ui/header_context.py` runs a full `retrieve(holdings_current)` per request; every page pays it.

- Add module-level `_HEADER_CACHE: tuple[float, dict] | None` with `_HEADER_TTL_SEC = 60.0`, same
  `time.monotonic()` pattern as `_TOKEN_CACHE`.
- Invalidate early when **either** `logs/last_run.json` **or** the newest `exports/ai_briefing_*/manifest.json`
  mtime differs from the mtime captured at cache fill. Store the observed mtimes in the cache tuple.
  **`last_run.json` is absent today** — a missing file is a stable sentinel (`None`), not an invalidation.
- Keep `_pipeline_lock_state()` **outside** the cache: lock state is the one field that must be live —
  a 60s-stale "idle" while the morning run holds the lock is a wrong answer, and it is a single `stat()`.
- Return a shallow copy on cache hit so a page mutating `header` cannot poison the next request.
- Add `pm ui cache-clear`? **No.** Out of scope; TTL plus mtime invalidation is the contract.

**Target:** second page load inside the TTL does zero retrieval — one `stat()` on the lock, one on
`last_run.json`, one on the manifest.

`tests/test_header_cache.py`: monkeypatch `ui.header_context.retrieve` with a call counter; assert
two `assemble_header()` calls inside the TTL invoke it once; assert a forced mtime bump invokes it
again; assert `lock_detail` still reflects a lock file created between the two calls.

### A3 — One-click campaign refresh from Position Story

Today `ui/templates/position_story.html:57` is a link to `/runs` with a `sessionStorage` prefill — a
navigation away from the page you are reading.

- Replace it with an in-place launcher for `judge-lifecycle`, pre-filled with `{{ refresh_ticker }}`
  in a hidden `input[name="arg-ticker"]`.
- **Binding decision (pick and state it in the commit):** widen the `desk.js` selector from
  `btn.closest(".run-card")` to `btn.closest("[data-routine-id]")` and put `data-routine-id` on the
  wrapper. Keep the `.run-card` markup on `/runs` untouched so its styling is unaffected. Keep the
  `prefill_ticker` sessionStorage path as the JS-off / fallback route — do not delete it.
- On the SSE `done` event, append an inline note next to the button:
  *"Refresh complete — reload to see the updated campaign."* **No auto-reload** (mid-read disruption).
- `UI_WRITE_ROUTE_ALLOWLIST` is unchanged; `POST /run/{routine_id}` is already allowlisted.
- The existing long-run warning ("~3 min") must render next to the button, not only on `/runs`.

### A4 — Campaign stale badge

`ui/position_story.py` already computes `fills_since_campaign` (`:299`, surfaced at `:378`). Add:

```python
CAMPAIGN_STALE_DAYS = 7  # module constant, not config
campaign_stale = bool(fills_since_campaign) or (age_days is not None and age_days > CAMPAIGN_STALE_DAYS)
campaign_stale_reason = f"{fills_since_campaign} fill(s) since campaign" if fills_since_campaign \
    else f"Campaign {age_days}d old"
```

`age_days` from `lifecycle_artifact["computed_at"]` via the existing `_parse_date`. Render as an amber
`tag tag-warn` chip beside the Campaign heading. **Never red** — staleness is not signed P&L.

On `/judgment/lifecycle`, add the same amber indicator where a registry row exists but the `.json`
sidecar is absent, with hover text naming `pm judge lifecycle --missing-json`.

### A5 — `/decision` full Crosshairs parity *(highest-value page)*

`ui/app.py:83-91` reads `store.get_crosshairs_items()` — a raw `decision_view` DataFrame dump that
bypasses `core/retrieval` and every formatter. Fix the data path and the template together.

1. **New `ui/crosshairs_table.py`.** Move `_crosshair_row` out of `ui/cockpit.py:26` verbatim (rename
   to `crosshair_row`, public). `ui/cockpit.py` imports it — one definition, two callers.
2. Add `assemble_decision()` in the same module: one `retrieve(label="decision", caller="ui",
   queries=[TemplateCall("decision_view", {})])`, all rows (not `[:5]`), `crosshair_row` over each,
   returning `{"rows": [...], "count": n, "retrieval_hash": rs.retrieval_hash}`.
3. Rewrite `ui/templates/decision.html` on the cockpit pattern: `table-scroll` + `data-table`,
   columns rank / ticker / `signal_chip` / `delta_bar` / days LT / wash badge / est. tax, sticky rank
   and ticker columns, `meta_line` with the retrieval hash, `empty_state` partial for zero rows.
4. `ui/app.py` `/decision` route calls `assemble_decision()`. Drop the `get_decision_header()` branch
   only if the store method returns empty — otherwise keep it as a `meta_line` above the table.

`tests/test_ui_decision_parity.py`: `assemble_decision()` rows carry `signal`, `dist_display`,
`est_tax_display`; rendered `/decision` HTML contains no bare float (regex `\d\.\d{6,}`).

---

## Phase 2B — Remaining page parity + density

### B1 — `/tax`
New `ui/tax_page.py::assemble_tax()`. Lots via `TemplateCall("tax_control_lots", {})` (Hard Rule 2).
Metrics stay `store.get_tax_control_metrics()` — **no retrieval template exists for MetaKV metrics;
add a one-line comment saying so rather than inventing one.** Format metrics through `money` /
`pct_pts` by key rather than dumping `metrics.items()` raw; link tickers to `/position/{ticker}`;
`ESTIMATE` label on any tax-cost field surfaced. Rewrite `ui/templates/tax.html`
(`data-table`, `table-scroll`, `empty_state`).

### B2 — `/precommit`
Template-only. `ui/precommit_page.py` already shapes clean rows. Apply `data-table`, `table-scroll`,
`dt` on `declared_at` / `event_date` / `thesis_at`, ticker links to position story, `empty_state`
instead of `div.empty`. Match cockpit's pending-precommit table exactly.

### B3 — `/search` + `/ask` — light parity only
Not a redesign. `meta_line` for query context / retrieval hash; `table-scroll` on hit lists; `dt` on
dates; provenance badges untouched (they are the trust signal); `/ask` sandbox banner retained.

### B4 — Delta bar domain
`ui/templates/partials/delta_bar.html` currently does `width = min(|pct| * 2, 50)` — −0.7% and −15%
are visually indistinguishable at the low end and both saturate at 25%. Introduce
`DELTA_BAR_DOMAIN = 0.20` in `ui/format.py` with a `delta_bar_width(value)` helper:
`min(50.0, abs(v) / DELTA_BAR_DOMAIN * 50.0)`. Template calls the helper; the `title` keeps the exact
`dist_pct`. Test: `delta_bar_width(-0.007)` ≈ 1.75, `delta_bar_width(-0.15)` = 37.5, `(-0.4)` = 50.0.

### B5 — Portfolio sparkline (not SPY) on the total-value tile
`ui/cockpit.py:210` feeds the hero tile from `bars_for_ticker(SPY)`. Replace with the portfolio's own
history: `_enrich_kpis` already reads `Daily_Snapshots` via
`tasks.build_command_center._read_records`; return the `Total Value` series from that same read
(**one read, not a second**) and add `sparkline_from_values(values, tail=30)` to `ui/sparkline.py`
alongside the existing `sparkline_from_bars`. Keep the SPY retrieve only if the YTD/vs-SPY tile still
needs it — if `_spy_ytd_pct()` covers it, drop `bars_for_ticker` from the cockpit `retrieve()`
entirely and note the removed query in the commit. `tests/test_ui_cockpit_sparkline.py` gains a
`sparkline_from_values` case; the existing `sparkline_from_bars` tests stay green.

### B6 — Positions unrealized %
`ui/positions_page.py` carries `unrealized` in dollars only. `holdings_current` returns `cost_basis`
(`core/retrieval/queries.py:243`) — compute `unrealized_pct = unrealized / cost_basis` when both are
present and non-zero, `None` otherwise. Render beside the dollar figure with `polarity_class`.
Optional, same cell, non-ballast rows only: a thin secondary bar for `headroom` (already computed).

---

## Phase 2C — Navigation + workspace polish

- **C1 — Cross-links.** `crosshairs_total` from `len(decision)` in `assemble_cockpit()`; under the
  top-5 table: *"Full Crosshairs list (N) → /decision"*. `/decision` links back: *"Top 5 on Cockpit →"*.
- **C2 — Console persistence.** `desk.js`: on `done`, append the buffer to `sessionStorage`
  `desk_console_log` (cap 50KB, trim from the front); restore on load; "Clear" control in the
  `console-dock` summary.
- **C3 — Sidebar.** The stray Rotations entry is already gone. Remaining decision: rename the Review
  sub-nav to *"Lifecycle index"* / *"Rotations summary"* so they read as artifact browsers, and
  confirm the legacy `/rotations` route (`ui/app.py:109`) is unlinked — if it is, either delete it or
  `RedirectResponse` to `/judgment/rotations`. **Ask Bill before deleting the route.**
- **C4 — Dev reload flag.** `manager.py:1870`:
  `reload = os.getenv("PM_UI_RELOAD", "").lower() in ("1", "true", "yes")`, passed to `uvicorn.run`.
  The PortfolioUI logon task is unchanged (env unset ⇒ `reload=False`).

---

## Architecture rules (carry forward, unchanged)

- No inline `retrieve_campaign` / `build_campaign` anywhere in `ui/`. `tests/test_ui_no_inline_judgment.py`
  globs `ui/*.py` with an allowlist of `{judgment_artifacts.py}` — **new modules (`crosshairs_table.py`,
  `tax_page.py`) must pass without being added to that allowlist.**
- Ledger reads go through `core/retrieval`. The two documented exceptions this phase keeps are
  `Daily_Snapshots` (B5) and tax metrics in MetaKV (B1) — both commented in place.
- No chart library, no CDN, no new write routes.
- Red/green on signed P&L only; staleness and warnings are amber.
- Campaign refresh launches the **existing** registry routine. No new subprocess entry points.

---

## Post-build verification checklist — paste literal stdout for each

| #  | Check | Command / action | Expect |
|----|-------|------------------|--------|
| 1  | Backfill dry run | `python manager.py judge lifecycle --missing-json` | table of tickers, `action=run`, **no files written** (`ls agent_outputs/judgment/*.json \| wc -l` still 0) |
| 2  | Backfill live, one ticker | `python manager.py judge lifecycle --missing-json --live` (stop after first) | `.json` on disk; `get_campaign_registry(T)` returns a row with `computed_at` |
| 3  | Mutually exclusive flags | `python manager.py judge lifecycle --missing-json --all` | exit 1, explicit message |
| 4  | Header cache | `pytest tests/test_header_cache.py -q` | pass; retrieve called once for two calls in TTL |
| 5  | Header TTFB | two `curl -w "%{time_total}\n" -o NUL -s http://127.0.0.1:8765/positions` inside 60s | second materially faster; paste both numbers |
| 6  | `/decision` | browser at 800px | signal chips, delta bars, days LT / wash / est. tax all visible; `grep -c "0\.[0-9]\{6,\}"` on saved HTML = 0 |
| 7  | `/tax`, `/precommit` | saved HTML | same raw-float grep = 0 |
| 8  | Position Story refresh | click Refresh campaign on `/position/UNH` | POST `/run/judge-lifecycle` streams into the console dock; **no navigation**; done-note appears |
| 9  | Stale badge | `/position/<ticker with fills_since_campaign > 0>` | amber chip with fill count |
| 10 | Delta bar | `pytest -k delta_bar -q` | −0.7% / −15% / −40% → 1.75 / 37.5 / 50.0 |
| 11 | Cockpit sparkline | hover the total-value tile | tracks portfolio total; SPY appears only in the YTD tile text |
| 12 | Console persistence | launch a routine, navigate to `/positions` | output still in the dock |
| 13 | Reload flag | `set PM_UI_RELOAD=1 && python manager.py ui serve`, edit a template | picked up without restart; unset ⇒ no reloader in stdout |
| 14 | Full suite | `pytest -q` | green; paste the summary line |
| 15 | Structural test | `pytest tests/test_ui_no_inline_judgment.py -q` | green with the new modules present |

**Do not report a PASS table you did not produce.** Every row above is stdout or a screenshot.

---

## Docs (last step)

- `CHANGELOG.md` — one `## [2026-08-28] — Desk redesign Phase 2` entry, same bullet style as the
  Phase 0 and Phase 1–3 entries.
- `state.md` — extend the existing Desk line (`:56`); add the `--missing-json` backfill command and
  the header-cache contract. Do not add a new section.
- `CLAUDE.md` — one line under the UI section **only** if the header-cache invalidation contract
  (TTL + last_run/manifest mtime, lock always live) needs stating. No other file.

---

## Out of scope (do not build)

- Chart library, light theme, remote access, auto-refresh / WebSocket prices.
- Combined MU+SKHY ceiling UI — denominator question still open.
- Tier 1/2 launcher expansion; `--live` batch backfill as a browser button.
- Rebuilding `/rotations` as a first-class page.
- Retrofitting `--live` onto `judge lifecycle --ticker` / `--all`.
