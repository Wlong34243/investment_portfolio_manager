# Build Prompt: AI Briefing Export (.bat -> package for external frontier LLMs)

**Author:** Chief Architect (Claude, 2026-07-17)
**Executor:** Claude Code / Sonnet / Gemini CLI
**Prompt version:** 1.0.0

## Objective

Give Bill a Desktop .bat file that, when double-clicked, assembles a dated folder of
markdown files he can upload into an external AI (Claude.ai, Gemini, ChatGPT) to run a
portfolio-vs-podcast synthesis: cross-source theme extraction, holdings mapping,
coherence checks, tax-aware rotation candidates, and thesis-drift flags.

This is deliberately NOT part of the `pm export` scenario framework and does NOT touch
`manager.py`. One standalone script + two .bat files. The external AI interaction is
manual; Bill is the transport layer.

---

## Step 0 — Verification gate (do this before writing any code)

Confirm each of the following. If any check fails, STOP and report instead of building.

1. `python manager.py --help` runs without error from the repo root
   (`C:\Users\WLong\Investment_Portfolio`). Note which python is used — there is no
   `.venv` in this repo; system Python 3.12 is expected.
2. `python manager.py bundle composite --help` exists (used by the .bat for refresh).
3. At least one `bundles/composite_bundle_*.json` exists. Open the newest one and
   confirm this structure (spot-check, do not assume):
   - `composite_hash`, `timestamp_utc` at top level
   - `_market_data.positions[]` with keys: `ticker`, `market_value`, `cost_basis`,
     `weight_pct`, `asset_class`
   - `_market_data.tax_lots[]`, `_market_data.total_value`, `recent_rotations[]`
4. `data/podcast_summaries/` contains files named `YYYY-MM-DD_<Source>_<Title>.md`.
5. `vault/theses/*_thesis.md` files have YAML frontmatter (`ticker`, `style`,
   `last_reviewed`) and sections `## Core Thesis`, `## Scaling State`
   (`next_step: ...`), `## Rotation Priority` (`priority: ...`).
6. `data/styles.json` exists (style -> size_ceiling_pct map).
7. `exports/` exists (it does; tax-rebalance packages live there).
8. No existing file named `tasks/export_ai_briefing.py`, `make_ai_briefing.bat`, or
   a Desktop file named `Portfolio AI Briefing.bat`.

**Known data quirk (verified 2026-07-17):** `unrealized_gl` and `unrealized_gl_pct`
are zeroed for all positions in current bundles. ALWAYS compute gain/loss as
`market_value - cost_basis`. Never trust the stored unrealized fields.
**Second quirk:** tax lots have `holding_period: "unknown"` and null acquisition
dates. The generated portfolio.md must say so explicitly (the analysis prompt tells
the external AI to caveat short-term vs long-term treatment).

---

## Deliverable 1: `tasks/export_ai_briefing.py`

Standalone script, stdlib + existing repo deps only (json, pathlib, datetime, glob,
re). No imports from `manager.py`. No network calls. No Sheets access. Writes ONLY
under `exports/`. ASCII-safe output (no emoji, no arrows — see commit 7e0bc2c for
precedent).

CLI: `python tasks/export_ai_briefing.py [--days 14] [--out exports]`

Behavior:

1. **Locate bundle.** Newest `bundles/composite_bundle_*.json` by the timestamp in
   the filename. If its `timestamp_utc` is older than 24h, print a plain warning
   line (`WARNING: bundle is N hours old`) but continue.
2. **Create package dir** `exports/ai_briefing_{YYYY-MM-DD_HHMM}/`.
3. **Write `portfolio.md`:**
   - Header with `composite_hash`, bundle `timestamp_utc`, total value.
   - Table of all positions sorted by market value desc: Ticker | Market Value |
     Weight % | Cost Basis | Unrealized G/L $ (computed) | Unrealized G/L %
     (computed) | Asset Class.
   - Section `## Tax Lots` listing `_market_data.tax_lots` (ticker, quantity,
     cost/share, total) with the sentence: "Holding periods are unknown in this
     export; verify short-term vs long-term before acting on any tax math."
   - Section `## Recent Rotations` dumping `recent_rotations` fields Date,
     Sell_Ticker, Buy_Ticker, Thesis_Brief, Rotation_Type.
4. **Write `podcasts.md`:** concatenate every file in `data/podcast_summaries/`
   whose filename date is within `--days` (default 14) of today, newest first,
   separated by `\n\n---\n\n`. Header line states the date range and file count.
5. **Write `theses.md`:** for every `vault/theses/*_thesis.md`, emit a compact
   block:
   ```
   ### {TICKER} — style: {style} | scaling: {next_step} | priority: {priority} | reviewed: {last_reviewed}
   {first paragraph of ## Core Thesis}
   ```
   Skip the `<!-- region:... -->` blocks entirely. If a section is missing, write
   `(missing)` rather than failing. Prepend the contents of `data/styles.json` as a
   short "Style size ceilings" table.
6. **Write `prompt.md`:** the VERBATIM text in Deliverable 2 below, with the single
   substitution `{DATE}` -> today's date. Do not edit, summarize, or improve it.
7. **Write `SUBMIT_ME.md`:** `prompt.md` + `portfolio.md` + `podcasts.md` +
   `theses.md` concatenated in that order with `\n\n---\n\n` separators.
8. **Write `manifest.json`:** composite_hash, bundle path, generated_at, days
   window, file list with byte sizes.
9. Print the package path and per-file sizes; exit 0.

## Deliverable 2: verbatim contents of `prompt.md`

Everything between the BEGIN/END markers is the payload. Embed it in the script as a
module-level string. Do not modify it.

<!-- BEGIN PROMPT PAYLOAD -->
# Portfolio Analysis Briefing — {DATE}

You are analyzing the portfolio of a self-directed investor (Bill). Attached are
four documents: this prompt, `portfolio.md` (positions, tax lots, recent
rotations, stamped with a data fingerprint), `podcasts.md` (summaries of the
investment podcasts he follows, most recent first), and `theses.md` (a digest of
his written investment thesis for each position, with style tags and size
ceilings).

## Who you are working for

Bill runs a ~$550-600K Schwab portfolio across four self-defined styles:
1. GARP-by-intuition — undervalued companies whose products he understands
2. Thematic Specialists — buying market position over company quality
3. Boring Fundamentals — durable businesses bought on fear-driven discounts
4. Sector/Thematic ETFs — macro expressions, with broad index and bond ETFs as ballast

His risk management is small-step scaling in and out — never binary entries or
exits. His unit of analysis is the rotation: a linked sell-buy pair with an
implicit substitution thesis. He carries strategic cash intentionally. He knows
the thesis behind every position; your job is drift control and synthesis, not
discovery.

## What to produce, in order

1. **Theme extraction.** Identify the recurring investment themes across the
   podcast summaries. For each theme, name which sources support it and — this
   matters — where sources DISAGREE with each other. Do not average away
   disagreements; state them as tensions and say which resolution would require
   the least change to this portfolio.

2. **Holdings map.** For each major theme, list Bill's actual exposure on both
   sides of it, with tickers and current weights from portfolio.md. Include
   indirect exposure (e.g., a broad ETF that concentrates the same names as his
   single-stock positions).

3. **Coherence checks.** Find places where his positions, recent rotations, or
   recent buys work against each other or against a theme he appears to be
   acting on. Example of the expected caliber: selling a semiconductor-equipment
   stock while averaging down into an EM ETF whose top holdings are 40%
   semiconductor names is self-cancelling. Check ETF look-through overlap
   explicitly.

4. **Rotation candidates.** Where the evidence supports it, propose small-step
   rotations (sell-buy pairs) consistent with his styles. For every candidate,
   show the tax math from portfolio.md: computed unrealized gain/loss per
   position, whether losses offset gains within the pair, and wash-sale timing
   constraints. Holding periods are unknown in the data — say so and tell him to
   verify short-term vs long-term before executing.

5. **Thesis drift flags.** Compare what is currently happening (from the
   podcasts and from current news) against the written theses in theses.md.
   Flag any thesis whose risk section omits the risk that is actually biting
   right now, and any position whose scaling state (e.g., "hold") conflicts
   with what he has recently been doing per the transaction logs.

6. **Current events check.** If you have web access, look up current news for
   his foreign and EM holdings (currency moves, policy, geopolitics) and for
   any position where the podcasts hint at a live situation. Cite sources. If
   you do not have web access, list the specific questions he should check.

7. **The obvious move.** End with a short section titled "The obvious move":
   the single most coherent next action (or deliberate non-action) given
   everything above, in plain language, followed by the two or three open
   questions he should resolve before acting.

## Ground rules

- Be candid and specific. He wants pushback, not validation.
- Anchor every claim to a ticker, weight, or source. No generic market
  commentary.
- Respect his style: small steps, rotations not liquidations, strategic cash is
  intentional and not idle money.
- All data in portfolio.md is read-only truth as of its fingerprint timestamp.
  If something looks wrong or internally inconsistent, flag it rather than
  silently working around it.
<!-- END PROMPT PAYLOAD -->

## Deliverable 3: `make_ai_briefing.bat` (repo root)

```bat
@echo off
cd /d C:\Users\WLong\Investment_Portfolio
echo Refreshing composite bundle...
python manager.py bundle composite
if errorlevel 1 echo WARNING: bundle refresh failed, using newest existing bundle.
python tasks\export_ai_briefing.py
if errorlevel 1 (
  echo Export FAILED. See errors above.
  pause
  exit /b 1
)
for /f "delims=" %%d in ('dir /b /ad /o-d exports\ai_briefing_*') do (
  start "" explorer "exports\%%d"
  goto done
)
:done
```

Adjust the final loop if needed so it opens the package just created (the script may
instead print the path to a temp file or the script can open Explorer itself via
`os.startfile` — executor's choice, but the folder MUST open automatically).

## Deliverable 4: Desktop launcher

Write `%USERPROFILE%\Desktop\Portfolio AI Briefing.bat` containing exactly:

```bat
@echo off
call "C:\Users\WLong\Investment_Portfolio\make_ai_briefing.bat"
```

---

## Constraints (from CLAUDE.md — non-negotiable)

- No writes outside `exports/` and the two .bat files named above.
- No Sheets writes, no Schwab order endpoints, no network calls in the export script.
- Do not modify `manager.py`, `core/bundle.py`, or anything in `utils/`.
- ASCII only in all generated output (Windows console chokes on emoji/arrows).

## Verification checklist (build is not done until all pass)

- [ ] Double-clicking the Desktop .bat opens an Explorer window on a new
      `exports/ai_briefing_*/` folder within ~60 seconds.
- [ ] Folder contains exactly: prompt.md, portfolio.md, podcasts.md, theses.md,
      SUBMIT_ME.md, manifest.json.
- [ ] portfolio.md position count and total value match the newest bundle;
      unrealized G/L figures are nonzero (computed, not the zeroed bundle fields).
- [ ] podcasts.md contains only summaries from the last 14 days, newest first.
- [ ] theses.md has one block per thesis file; missing sections say "(missing)".
- [ ] prompt.md is byte-identical to the payload above except the {DATE} substitution.
- [ ] SUBMIT_ME.md is under 1 MB.
- [ ] manifest.json composite_hash matches the bundle used.
- [ ] Running the .bat twice creates two separate dated folders (no overwrite).
- [ ] With the bundle refresh deliberately failed (e.g., temporarily rename
      manager.py? No — instead test by noting the fallback message path in code
      review), the script still exports from the newest existing bundle.
