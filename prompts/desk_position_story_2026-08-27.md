# The Desk I — Position Story

**Created:** 2026-08-27
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 4 of 10.** **Depends on:** prompts 1, 2, 3. **Soft-gated on** prompt 1's ten-day accrual —
the page renders before the gate clears, but the signal lane must say so rather than look empty.
**Source:** `docs/architecture/06_the_instrument_roadmap.md` (amended 2026-08-27) — Phase 2 (The Desk), Position Story.

> "One ticker, one timeline. Scroll it and you see the whole campaign."

---

## What this is not

Not a replacement for the Sheet. Sheets stays exactly as-is as the glanceable remote surface — the
roadmap is explicit that no second remote path is needed, and `pm store publish-cockpit` already
covers phone access. This is a localhost desk surface on the Geekom, **read-only**, that does one
thing the Sheet structurally cannot: put a position's entire history on a single scrollable page.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — dependencies landed
python manager.py store evidence-status
python manager.py corpus status
python -c "from core.retrieval.api import retrieve; print('retrieval OK')"
python -c "from core.retrieval.queries import REGISTRY; [print(t.id) for t in REGISTRY]"

# 0.2 — the UI as it actually exists today
sed -n '1,40p' ui/app.py
grep -n "@app.get" ui/app.py
ls ui/templates/
grep -n "block\|extends\|href" ui/templates/base.html

# 0.2b — the static mirror that Step 1's decision turns on
grep -n "def publish_cockpit\|render\|template" core/store/publish_static.py

# 0.3 — how the server is launched
grep -n "ui_app\|def serve" manager.py | head -20

# 0.4 — what is installed (do NOT add a JS build step)
grep -n "fastapi\|jinja\|htmx\|uvicorn" requirements.txt
python -c "import fastapi, jinja2, uvicorn; print('ok')"

# 0.5 — lot and tax data shape for the ladder
python -c "from core.retrieval.api import retrieve; from core.retrieval.queries import TemplateCall;\
r=retrieve(queries=[TemplateCall('position_lots',{'ticker':'MU'})],label='probe');\
print(r.tables['position_lots'][:3])"
```

**Expected at 0.2:** four routes (`/`, `/decision`, `/tax`, `/rotations`), five templates, HTMX via
CDN or inline — **note which.** `publish_static.py` confirms the second render path: it emits static
HTML with no API behind it, which is the fact Step 1's decision rests on.

---

## Step 1 — Charting: decided, not a gate

> **This was roadmap open decision 3. It is now closed: server-rendered inline SVG.** Do not re-open
> it, do not present options, do not add a JavaScript charting library. Build to the decision.

**The argument that settles it is not framework avoidance — it is that Phase 2 has to serve two
render paths from one codebase.** `pm ui serve` on localhost, and the static mirror published by
`pm store publish-cockpit --live --publish`. A client library (uPlot or otherwise) needs JavaScript
plus a data fetch, and **the static mirror has no API to fetch from** — you would inline the series
as JSON into the static page and maintain two divergent render paths for the same chart. Inline SVG
is byte-identical in both. One `charts.py`, one partial, two surfaces.

Everything else that recommends SVG here — no build step, works offline, prints — is true and
secondary. The two-render-path argument is the one that holds when someone proposes uPlot again in
four months.

**The cost is real. Name it, accept it for v1:** Position Story with three years of daily bars has
**no zoom and no hover readout.** Reading a specific day's close means the table beneath the chart,
or a page reload with narrowed date params. On a 750-point series that is a genuine ergonomic loss,
not a rounding error. It is accepted because the alternative is two render paths, and because the
page's job is showing the shape of a campaign, not reading individual closes.

**The hedge:** `ui/charts.py` produces a `ChartSpec` (series, markers, bands, axis ranges) and one
Jinja partial renders it. Nothing else in the codebase constructs SVG or knows the chart's internals.
Reversing this decision then touches exactly two files — which is the correct blast radius for a
decision made on a v1 with no usage data behind it.

---

## Step 2 — Route and data assembly

New route `GET /position/{ticker}` in `ui/app.py`, plus `ui/position_story.py` for assembly (keep
`app.py` thin — it is already doing pandas coercion inline in `home()`, and that pattern should not
spread).

**Every read goes through `core/retrieval`.** No direct store calls, no `open()`, no SQL in the UI
layer. One `retrieve()` call per page render, with `caller="ui"` and `label=f"position_story:{ticker}"`,
so the whole page has one `retrieval_hash` and appears as one row in `retrieval_log`.

Templates it needs: `position_transactions`, `position_lots`, `position_realized_gl`,
`signal_events_for_ticker`, `bars_for_ticker`, `fundamentals_series`, `trade_log_for_ticker`,
`thesis_state_for_ticker`, `rotation_review_for_ticker`, plus a corpus query filtered to that ticker.

Unknown ticker → a 404 page listing held tickers, not a stack trace.

---

## Step 3 — The page, top to bottom

**Header.** Ticker, name, style (from `styles.json` taxonomy via `thesis_reader`, not `## Style`
prose — `CLAUDE.md` is specific about this), current weight, style ceiling and headroom, market
value, unrealized. Where the position is ballast (JEPI, JPIE, VTI, COWZ, VEA), **suppress the ceiling
readout entirely** — style ceilings do not apply to ballast, and rendering an over-ceiling figure
there is the exact noise `CLAUDE.md` Analysis Rule 3 exists to kill.

**Price line with fills plotted.** Daily close from `bars_daily`, full available history. Buys and
sells as markers sized by dollar amount, coloured by side. Markers carry an index keyed to the
transaction table below — there is no hover, per Step 1. Where a fill has a `Rotation_Type` in
`Trade_Log`, mark it —
a rotation leg is not a standalone trade and should not read as one.

**Cost-basis curve.** Average cost over time, drawn on the same axes as price. The visual answer to
"did scaling in actually improve my basis" — which is one of the three questions the roadmap says
nothing currently measures.

**Lot-level detail.** Every open lot: open date, shares, basis, unrealized, holding days, term,
**days to long-term**. Sort by days-to-LT ascending, not by date — the lot about to cross is the one
that matters. Closed lots from `position_realized_gl` in a second, collapsed table.

**Holding-period ladder.** A horizontal band per open lot spanning open date → LT crossover date, with
today marked. This is where the 74%-short-term problem becomes visible at the moment of decision
instead of on next April's 1099. **Do not compute which lot Schwab would relieve here** — that is
prompt 9's job and it is not FIFO. See the warning in Step 4.

**Realized and unrealized.** Realized G/L for this ticker split ST/LT, YTD and lifetime; unrealized
current, with the ST/LT split of the unrealized.

**Signal lane.** Every `signal_events` row that ever fired on this ticker, on the same time axis as
the price line: type, trigger type, the reading, the band, whether it was doctrine-downgraded.
**While the ten-day accrual gate is unmet, render the lane with an explicit banner** — "signal
capture began 2026-08-27; 6 of 10 trading days accrued" — never as an empty lane. An empty lane reads
as "no signals ever fired," which is false and the kind of false that quietly corrupts judgment.

**Thesis state.** Current frontmatter: style, `trigger_type`, bands, ceiling, `pattern` if present.
Plus the Review Log entries from the thesis file, dated, most recent first. Where the thesis is
archived, say so prominently.

**Rotation history.** `Rotation_Review` rows where this ticker is either leg, showing
`Residual_Pair_Nd`. Render the standing caveat inline, not in a footnote: the aggregate describes a
documented subset, effective N is far below nominal N, and it is evidence rather than a scorecard
(`CLAUDE.md` Analysis Rule 9).

**Corpus mentions.** The most recent N corpus hits for this ticker, with source type, date and
snippet, linking into prompt 5's search page for the full list. Model-output sources (`podcast_summary`,
`agent_output`) render visibly flagged.

---

## Step 4 — Three things this page must not do

1. **No price targets, no forecasts, no recommendations.** Anywhere. Including in a chart annotation,
   including as a "fair value" line. `CLAUDE.md` Hard Rule 4. If a number would function as a
   prediction, it does not belong on the page.
2. **No local derivation of lot relief.** The account uses Schwab's Tax Lot Optimizer, not FIFO
   (established 2026-08-26). This page displays lots as Schwab reports them and **never** computes
   which lot a sale would consume. Prompt 9 handles projection, labelled as projection.
3. **No writes.** No forms, no POST routes, no "edit thesis" button.

   > **Roadmap open decision 1 — the mutation amendment — is DEFERRED, deliberately, to Phase 6a
   > (prompt 7). This is a decision, not an omission.** Phase 2 does not need it: nothing on this
   > page authors Bill's prose into the record. Deciding it now would scope the UI wider than Phase 2
   > requires and leave that extra surface to be defended for six months before anything uses it.
   > The amendment becomes required at 6a, when the UI starts writing Bill's own commentary into
   > `Trade_Log`. **Until then, the structural test below is the rule** — provisionally, and by
   > design.

   **Mechanism: an explicit route allowlist, not a predicate.** Define in `ui/app.py`:

   ```python
   # Routes permitted to use a mutating HTTP method. An allowlist of literal
   # (method, path) pairs — NEVER a predicate. See prompt 4, Step 4.3.
   UI_WRITE_ROUTE_ALLOWLIST: frozenset[tuple[str, str]] = frozenset()
   ```

   At this prompt it is **empty**. Prompt 6 adds exactly one entry, `("POST", "/ask")`, and nothing
   else ever gets added without an edit to this constant showing up in a diff.

   A predicate — "POSTs that only write markdown", "endpoints that don't touch the ledger" — erodes.
   The second endpoint that happens to satisfy it slips through without anyone deciding, and the
   rule quietly becomes whatever the code does. An allowlist of one forces a diff to change.

---

## Step 5 — Navigation

Add `/position/{ticker}` links from the existing pages: ticker cells on `/` (top-10 table),
`/decision` (Crosshairs rows), `/tax` (lot rows). One line each in the existing templates; extend
`base.html`'s nav with a ticker jump box.

---

## Tests

- `test_ui_position_route.py` — 200 for a held ticker; 404-with-list for an unknown one.
- `test_ui_position_readonly.py` — **the decisive test.** Walk `app.routes`, collect every
  `(method, path)` using POST/PUT/PATCH/DELETE, and assert the set equals
  `UI_WRITE_ROUTE_ALLOWLIST` **exactly** — not a subset, not "no unexpected writes to the ledger".
  Set equality is what makes adding a route fail loudly instead of passing quietly. This test is
  standing in for a `CLAUDE.md` rule until Phase 6a; treat a failure as a governance event, not a
  test to relax.
- `test_ui_position_ballast.py` — a ballast ticker's rendered page contains no ceiling-breach text.
- `test_ui_position_gate_banner.py` — with fewer than 10 accrued days, the signal lane banner renders.
- `test_charts_spec.py` — `ChartSpec` construction from a known bar series is deterministic.

---

## Post-build verification checklist

**Literal stdout, plus screenshots for the visual rows.**

| # | Check | Expect |
|---|---|---|
| 1 | Page renders | `pm ui serve`, open `/position/MU` | full page, no traceback |
| 2 | Every fill plotted | count markers vs `position_transactions` row count | equal |
| 3 | Cost-basis curve | spot-check one date against `tax_control_lots` | matches |
| 4 | Lot ladder sorted | days-to-LT ascending | yes |
| 5 | Ballast suppression | `/position/JEPI` | no ceiling figure |
| 6 | Gate banner | while accrual < 10 days | banner text with real counts |
| 7 | Signal lane complete | signal count on page vs `select count(*) from signal_events where ticker=...` | equal |
| 8 | Archived thesis | a ticker with an archived thesis (e.g. ES) | flagged as archived |
| 9 | Model-output flags | corpus lane on a ticker with podcast hits | flagged |
| 10 | One retrieval per render | `select count(*) from retrieval_log where label like 'position_story:%'` before/after one load | +1 |
| 11 | No write routes | the readonly test | passes; paste the asserted set — must be **empty** here |
| 12 | No forecast text | `grep -rniE "price target\|fair value\|we expect\|forecast" ui/` | no matches |
| 13 | Unknown ticker | `/position/ZZZZ` | 404 page listing held tickers |
| 14 | Works offline | disconnect network, reload | page renders; no CDN request in the network log |
| 14b | Chart survives the static path | render one `ChartSpec` through `publish_static` | identical SVG in both surfaces |
| 15 | Tests | `python -m pytest tests/ -q` |

---

## Documentation to update on completion

- **`CLAUDE.md`** — update the `ui/app.py` Key Files row: it currently says "debug-only," which stops
  being true here. State plainly that the UI is read-only, that `UI_WRITE_ROUTE_ALLOWLIST` is the
  enforcement, and that **the mutation amendment is deferred to Phase 6a by decision** — write the
  deferral down, so it reads as a choice rather than a gap when someone finds it.
- **`state.md`** — dated entry recording **two closed decisions**: charting is inline SVG, settled on
  the two-render-path argument, with the zoom/hover loss accepted for v1; and the mutation amendment
  is deferred to Phase 6a with the route allowlist as the provisional rule. Both belong in *Recent
  Decisions Log* so neither is rediscovered as an open question.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- Corpus Search. Prompt 5.
- The confirmation-bias counterweight (contrary evidence above the fold). That is Phase 5 and is not
  in this build set. **Do not add it because it looks like a small addition here** — it is a ranking
  problem, not a layout one.
- Any retrospective or scoring. Phase 3, gated on six months.
- Any write path.
