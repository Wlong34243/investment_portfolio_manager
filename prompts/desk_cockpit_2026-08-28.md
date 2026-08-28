# Desk Cockpit — one local surface: read the book, launch the routines

**Created:** 2026-08-28
**Executor:** Cursor (Agent mode).
**Depends on:** prompts 1–10 (all shipped), `surface_delivery_2026-08-28.md` Step 1.
**Source:** Bill, 2026-08-28 — sidebar of routines, main area with charts and position views, a way to
launch CLI routines from the browser, landing at the end of the morning run.

> **This extends `ui/app.py`. It does not add a second server.**
>
> Bill's request named Node/Express. Do not build that. FastAPI + Jinja already serves `/`,
> `/decision`, `/tax`, `/rotations`, `/position/{ticker}`, `/search`, `/doc/{id}` and `/ask`, all
> reading through `core/retrieval` with a hash-stamped, logged, read-only path. A second server
> means a second data path that bypasses `core/retrieval` — which `CLAUDE.md` **What NOT to Do**
> forbids outright — plus a second process to keep alive and a second thing to debug at 7:50am.
> Everything Bill asked for is a set of routes and templates on the app that exists.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — the app and its current surface
grep -n "@app.get\|@app.post\|UI_WRITE_ROUTE_ALLOWLIST" ui/app.py
ls ui/ ui/templates/ ui/templates/partials/ 2>/dev/null

# 0.2 — the routine surface to expose
grep -n '@\w\+_app\.command("' manager.py | wc -l
cat Portfolio_Manager.bat | grep -n "manager.py\|call \"%PROJECT_DIR%"

# 0.3 — chart seam
grep -n "class ChartSpec" -A 20 ui/charts.py

# 0.4 — lock + exit-code semantics built 2026-08-28
grep -n "pipeline.lock\|exit /b 3\|SKIP: pipeline lock" morning_auto.bat manager.py | head

# 0.5 — has surface_delivery Step 1 landed? (cockpit tax tiles depend on it)
grep -n "est_tax_cost_low\|days_to_lt" tasks/build_decision_view.py

# 0.6 — retrieval templates available to new pages
python -c "from core.retrieval.queries import TEMPLATES; [print(t) for t in TEMPLATES]"
```

---

## Step 1 — Shell: sidebar, header strip, content, console

Rework `ui/templates/base.html` into a three-region shell. No framework, no build step, no CDN —
the offline constraint from prompt 4 stands.

**Left sidebar**, grouped exactly like `Portfolio_Manager.bat` so the two surfaces teach the same
vocabulary:

```
COCKPIT          /                     today
POSITIONS        /positions            all held, sortable
  └ ticker       /position/{ticker}
DECIDE           /decision             crosshairs + tax
  Tax            /tax
  Pre-commit     /precommit
SEARCH           /search
ASK              /ask
REVIEW           /judgment
  Rotations      /judgment/rotations
  Lifecycle      /judgment/lifecycle
RUNS             /runs                 launcher + history
```

**Header strip, always visible, on every page.** This is the freshness contract:
bundle hash (short) · `generated_at` · Schwab token state · accrual `day N of 10` · verify streak ·
lock state (`idle` / `running since HH:MM`). Amber when the bundle is not from today. These come
from one `retrieve()` plus `meta_kv`; render server-side, refresh on load, no polling.

**Console pane**, collapsible, docked bottom. Empty until a routine runs. Streams stdout.

Dark-first palette suited to financial data: neutral greys, one accent, semantic colour reserved
for gain/loss only. **No red for anything that is not a loss** — red on a wash-sale flag or a stale
badge trains the eye wrong. Tabular figures everywhere (`font-variant-numeric: tabular-nums`), right
aligned, consistent decimal places per column.

---

## Step 2 — Cockpit page (`/`), the morning landing

`morning_auto.bat` ends by opening this page (Step 6). It answers: what happened overnight, what
needs me today.

1. **KPI row** — total value, day $/%, MTD, YTD, vs SPY, cash %. **Cash carries a scope note**:
   three of six accounts, per `CLAUDE.md` Analysis Rule 1. Not net worth.
2. **Crosshairs top 5** — rank, ticker, signal, distance to level, and the tax trio
   (`days_to_lt`, wash window, `est_tax` LOW–HIGH labelled *est.*). Trim-side rows only for the tax
   columns. Row links to `/position/{ticker}`.
3. **Pending pre-commitment firings** — one row each, with the declared band and the reading that
   fired it. Empty state reads *"No declarations yet — declare one on the Precommitments tab"*,
   not a blank panel.
4. **Today's evidence** — signals captured, accrual day N of 10, and the date the gate clears.
5. **Last run** — reads `logs/last_run.json` (see Step 6). Fields: `routine`, `started_at`,
   `finished_at`, `exit_code`. Exit **3** renders as *"skipped — lock held"*, not as a failure.
   Link to `logs/morning_auto.log` for detail. **Do not parse the log tail** — the batch runs
   outside the UI and never writes `ui_runs`; scraping text would throw away the distinct exit
   codes built 2026-08-28.

Everything else on this page comes from one `retrieve()` call with `label="cockpit"`. One page load,
one `retrieval_log` row, one hash. (`last_run.json` is a separate filesystem read — intentional.)

---

## Step 3 — The routine launcher

> **⚠️ Sign-off gate. Build Tier 0 only. Present Tiers 1–2 and STOP.**

**A literal registry, never a command string.** In `ui/routines.py`:

```python
@dataclass(frozen=True)
class Routine:
    id: str              # url-safe, e.g. "judge-rotations"
    label: str
    argv: tuple[str, ...]   # ("manager.py", "judge", "rotations")
    tier: int            # 0 read-only | 1 dry-run | 2 writes
    description: str
    args: tuple[ArgSpec, ...] = ()   # typed prompts (ticker, shares…)
```

The browser posts a **registry id plus typed argument values**. It never posts a command, a flag, or
a path. `argv` is assembled server-side from the frozen tuple and validated args, executed with
`subprocess` and **`shell=False`**. Anything else is a remote shell on localhost, which is what this
constraint exists to prevent. Same reasoning as `core/retrieval`'s template rule: the caller names a
thing, Python builds the command.

**Tier 0 — read-only, build now, no amendment needed:**
`judge rotations` · `judge lifecycle` · `judge calibration` · `tax project` · `corpus search` ·
`corpus status` · `store evidence-status` · `store verify` · `store bundle-parity` ·
`store provenance` · `journal precommit --list` · `journal precommit --pending` ·
`journal reconcile` (dry) · `probe *`

These read and write nothing but `agent_outputs/`, which Hard Rule 5 already names as a sandbox
surface. **`POST /run/{routine_id}`** for tier 0 joins `UI_WRITE_ROUTE_ALLOWLIST` alongside
`POST /ask` on the same reasoning — a sandbox artifact arriving over HTTP is the existing
convention, not a new mutation class.

**Allowlist entry (exact — no prefix matching, no per-id enumeration):**

```python
UI_WRITE_ROUTE_ALLOWLIST: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/ask"),
    ("POST", "/run/{routine_id}"),
})
```

Starlette registers one route with that literal path template. The readonly test asserts **set
equality** against mutating routes — not a prefix, not a predicate. Prefix matching would quietly
admit the next `/run/...` route nobody decided on.

**Tier 1 — dry-run that touches the ledger** (`corpus index`, `journal reconcile --backlog-only`)
and **Tier 2 — `--live`** (`morning`, `refresh dashboard`, `journal promote`, `ingest *`):
**do not build.** These need the mutation amendment (roadmap open decision 1, deferred to Phase 6a).
**STOP and present a table** — not a yes/no — with columns: `routine_id`, `argv`, `tier`, **what it
would write** (Sheet tab / SQLite table / path). Bill decides per row. If authorised, Tier 2
additionally requires: typed confirmation of the routine name, a visible banner naming what will be
written, and a `ui_runs` row before execution rather than after.

**Execution mechanics for Tier 0:**

- `POST /run/{routine_id}` → returns a `run_id`; `GET /run/{run_id}/stream` streams stdout over SSE.
- Subprocess env must include **`PYTHONUNBUFFERED=1`** — especially when the parent is `pythonw`
  (logon task); without it, SSE appears silent until the process exits.
- Refuse to start if `logs/pipeline.lock` is held: return the routine's name and the holder's start
  time, exit-3 semantics, not an error.
- One run at a time. Queue depth zero — a second request while one is running is refused with the
  running routine named.
- Timeout per routine (default 300s; `judge lifecycle --all` needs 7200 — at 2.7 min/ticker across
  ~35 positions that is roughly 90 minutes, and the UI must say so on the button, not discover it).
- Every run appends to a `ui_runs` table: `routine_id`, `args_json`, `started_at`, `finished_at`,
  `exit_code`, `artifact_path` (parsed from stdout when the routine names one).
- When a run produces an artifact under `agent_outputs/`, link it from the console when it finishes.

---

## Step 4 — Pages

**`/positions`** — every held ticker: weight, style, ceiling and headroom (**suppressed for ballast**
— JEPI, JPIE, VTI, COWZ, VEA — per Analysis Rule 3), day %, unrealized, days-to-LT, open signal.
Sortable client-side, no library: one small sort function over a table already in the DOM.

**`/position/{ticker}`** — exists. Add the Campaign block from prompt 10 (already wired) and the
lifecycle counterfactual: **single-entry delta is the headline, TWR the supporting line.** Where DWR
is degenerate (invested base collapsed by trims), print `n/a — invested base degenerate` with the
dollar figures, never a four-figure percentage.

**`/judgment`** — **reads artifacts only; never recomputes on page load.** List and render the
newest files under `agent_outputs/judgment/` (rotations, lifecycle, calibration markdown). Unit B
at 2.7 min/ticker would hang the browser and block the single run slot if computed inline. Each
section has a **launcher button** (Tier 0 registry) to produce a fresh artifact; the page shows what
exists on disk. Unit A artifacts must show N, excluded-N, and date spans when present. Unit B list
sorted by leg count (parse from artifact headers or a lightweight index file written by the launcher).

**`/precommit`** — read-only list plus pending firings. Declaration happens on the Sheets tab
(`surface_delivery` Step 3), and this page links to it. Do not build a declaration form here; that is
Tier 2 and it is the amendment case.

**`/runs`** — launcher grid grouped as the sidebar, plus run history from `ui_runs` with exit codes
and artifact links.

---

## Step 5 — Charts: one spec, two renderers

Keep `ChartSpec` as the single data contract. Server renders inline SVG exactly as today — that is
what `publish-cockpit`'s static mirror consumes and it must keep working with no JS.

**On localhost only, progressively enhance.** Emit the same `ChartSpec` as a JSON `<script
type="application/json">` block beside the SVG. A ~100-line vanilla JS module reads it and adds
crosshair readout and drag-to-zoom **on top of the already-rendered SVG**. JS off, or static mirror:
the SVG stands alone, unchanged.

This resolves the 22-marker problem from UNH without a library and without two render paths. Also add
marker collision handling in `ChartSpec` itself — same-week fills aggregate to one mark with a count
badge — so the static render improves too.

**No charting library. No CDN.** If a dependency seems necessary, stop and report rather than adding
one.

---

## Step 6 — Land here after the morning

**6a — `logs/last_run.json` on every exit.** `morning_auto.bat` records start time at entry and
writes on the way out (all exit paths: **0**, **1**, **3**):

```json
{"routine": "morning", "started_at": "<ISO8601>", "finished_at": "<ISO8601>", "exit_code": 3}
```

Use PowerShell (already in the batch for lock check) or a tiny one-liner — four lines of batch logic,
deterministic. The cockpit last-run panel reads this file; do not scrape `morning_auto.log`.

**6b — Open cockpit on success only.** After exit **0**, before `exit /b 0`:

```bat
start "" "http://127.0.0.1:8765/"
```

**No HTTP probe.** Exit 0 is the guard — a failed morning must not open a browser. Whether the UI
server is up is a separate question; a connection error in the browser is a legible signal that the
logon task died. Do not add `curl`, PowerShell health checks, or other round-trips to the batch.

Also install the logon task from `surface_delivery` Step 2 so the server is usually up before the
morning runs.

---

## Post-build verification checklist

**Literal stdout, plus screenshots for the visual rows.**

| # | Check | Expect |
|---|---|---|
| 1 | Shell renders on every route | sidebar + header strip + content, no traceback |
| 2 | Header freshness | hash, generated_at, token, accrual day, lock state all populated |
| 3 | Stale bundle | force a stale `generated_at` → amber, not silent |
| 4 | Cockpit tax trio | present on trim-side rows only; blank when Decision_View lacks them |
| 5 | Cash scope note | visible next to the cash figure |
| 6 | Ballast suppression | `/positions` shows no ceiling breach on JEPI/JPIE/VTI/COWZ/VEA |
| 7 | Registry only | `grep -rn "shell=True" ui/` → no matches |
| 8 | No command injection | post a routine id of `judge-rotations; del *` → rejected, no execution |
| 9 | Arg validation | ticker `../../etc` and shares `1e9` both rejected |
| 10 | Allowlist exact | `UI_WRITE_ROUTE_ALLOWLIST == {("POST", "/ask"), ("POST", "/run/{routine_id}")}` — set equality, no prefix |
| 11 | Lock respected | hold `pipeline.lock`, launch a routine → refused, holder named, exit-3 wording |
| 12 | One at a time | launch two → second refused naming the first |
| 13 | Stream works | `judge rotations` streams stdout live (`PYTHONUNBUFFERED=1`), links artifact on completion |
| 14 | Long-run warning | `judge lifecycle --all` button states ~90 min before it starts |
| 15 | `ui_runs` populated | one row per **UI-launched** run with exit code and duration |
| 16 | Tier 1/2 absent | `grep -rn "\-\-live" ui/` → no matches; amendment table presented, not built |
| 17 | Chart degrades | JS disabled → SVG renders identically; static mirror unchanged |
| 18 | Marker collisions | UNH's 23 legs render legibly; same-week fills aggregated with counts |
| 19 | Lifecycle headline | `/position/UNH` leads with single-entry delta; no four-figure DWR anywhere |
| 20 | Judgment artifacts | `/judgment` renders newest `agent_outputs/judgment/*.md`; no inline `pm judge` compute |
| 21 | Last run JSON | `logs/last_run.json` written on exit 0/1/3; cockpit shows exit 3 as skipped not failed |
| 22 | Offline | disconnect network → every page renders |
| 23 | Morning hand-off | successful `morning_auto.bat` opens browser; exit 1/3 do not; no curl probe |
| 24 | Tests | `python -m pytest tests/ -q` |

---

## Documentation to update on completion

- **`CLAUDE.md`** — `ui/routines.py` and the registry rule in Key Files; update the `ui/app.py` row
  (no longer debug-only); note that tier-0 run routes are sandbox-surface writes under Hard Rule 5
  and that tiers 1–2 remain gated on the Phase 6a amendment.
- **`PORTFOLIO_SHEET_SCHEMA.md`** — `ui_runs` alongside the other local-ledger tables.
- **`state.md`**, **`CHANGELOG.md`** — dated entries.

## Out of scope — do not build

- Node, Express, or any second server.
- Any charting or UI library, and any CDN reference.
- Tier 1 and Tier 2 routines, until the amendment is decided.
- Arbitrary command execution, in any form, behind any flag.
- A pre-commitment declaration form (Sheets tab owns that).
- Remote or authenticated access. `127.0.0.1` only, single user, no login.
- Any new analysis. This surfaces what the ten prompts already built.
