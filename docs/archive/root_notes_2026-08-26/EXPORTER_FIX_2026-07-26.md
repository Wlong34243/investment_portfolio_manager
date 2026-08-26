# Exporter Fix — `tasks/export_ai_briefing.py` (2026-07-26)

Follow-on from the review of the 2026-07-20 briefing package (`composite_hash 921d5245bed6`).
Scope: exporter code only. No thesis content was edited, no vault file was touched.
`git diff tasks/export_ai_briefing.py` → **+440 / −35**, plus one new module
`utils/etf_holdings.py`.

---

## The finding that mattered

The 7/20 package looked like a data-quality problem. It wasn't — you had already
repaired the mis-keyed theses (AMZN, MSFT, ETN, VEU) in the vault. Every remaining
defect was in the exporter.

The biggest one: **`strip_regions()` was deleting the per-position transaction logs
before export.** Every one of your 41 thesis files carries a populated
`<!-- region:transaction_log -->` block — **196 transaction lines in total**, with
dates, direction, quantity and price. All of it was being thrown away at export,
while prompt §5 instructed the analyst to check scaling state "per the transaction
logs." The data was there the whole time.

That single change is most of the value here. Drift control now has something real
to check against instead of a three-month-old rotation row.

---

## Changes

### 1. Transaction logs preserved (`extract_region`, `build_theses_md`)
`strip_regions()` still removes `position_state`, `sizing`, and `change_log` noise,
but `transaction_log` is now pulled out first and emitted under each thesis:

```
### AMZN -- style: GARP | scaling: (missing) | priority: (missing) | reviewed: 2026-07-26
GARP-by-intuition, anchored in daily product use. AWS is the stable, durable...

Recent transactions (AMZN):
- 2026-07-14: Buy 10.0 @ $245.33
- 2026-05-11: Sell -15.0 @ $270.60
- 2026-05-08: Sell -4.0 @ $272.24
- 2026-04-15: Buy 5.0 @ $247.57
```

### 2. Coverage gate — theses for positions you no longer hold are dropped
`build_theses_md` now takes the held-ticker set from the bundle and skips any thesis
whose position isn't in it, logging each skip. This is what let ZETA ship as a live
thesis on 7/20.

Running against the 7/26 bundle it immediately caught six real exits:
**AMD, CRWV, DELL, LRCX, MSFT, SPCX** — theses still sitting in `vault/theses/`
for positions you've closed. They're excluded from the package; they still need
archiving in the vault.

The reverse check also runs: held positions with no thesis file are flagged BLOCKING.

### 3. Preflight report + `--force`
Issues are printed before writing and recorded in `manifest.json` under
`preflight_issues`. Anything tagged BLOCKING aborts the export with exit code 1
unless `--force` is passed. Current run reports 9 issues, 0 blocking.

### 4. Style column + deterministic ceiling check (`build_ceiling_check`)
`portfolio.md` positions table gains a `Style` column sourced from thesis
frontmatter, and a new `## Style Size Ceiling Check` section does the join
arithmetic so no model has to. Against the 7/26 bundle:

| Ticker | Style | Weight % | Ceiling % | Status |
|---|---|---|---|---|
| JEPI | ETF | 9.89 | 8.00 | **BREACH** |
| QQQM | ETF | 8.70 | 8.00 | **BREACH** |
| MELI | THEME | 3.06 | 3.00 | **BREACH** |
| XOM | THEME | 2.73 | 3.00 | near ceiling |
| VST | THEME | 2.63 | 3.00 | near ceiling |

Aggregate: ETF 50.66%, GARP 31.99%, THEME 12.72%, FUND 4.33%.

JEPI and QQQM are both meaningfully through the 8% ETF ceiling now — JEPI has grown
from $46.2K to $58.3K since 7/20. Worth a look independent of this exporter work.

### 5. Rotation staleness warning (`rotation_staleness`)
If the newest `Trade_Log` row is >30 days older than the bundle, `portfolio.md` says
so in bold and redirects the reader to the per-position transaction logs. Current
run: **97 days**. Also handles the empty-`Trade_Log` case, which previously emitted
a bare header with an empty table.

### 6. Podcast noise filter (`podcast_signal`)
Summaries whose allocation table is a single catch-all `Broad Market` row, or which
carry an explicit `No actionable thesis` tag, are withheld and named in a header
note. Current run: **8 of 24 withheld**, cutting `podcasts.md` from 43.3KB to 40.7KB
while removing zero information.

### 7. Citation markers stripped at export (`strip_citation_markers`)
`[file:N]` / `[web:N]` markers pointing at documents not shipped in the package are
removed from thesis text at export time. The vault files keep them. Current run
stripped 8 markers across IGV, JPIE, XOM.

### 8. Prompt corrections (`PROMPT_PAYLOAD`)
- §5 now points at the per-position transaction logs, tells the model to say
  "(missing)" rather than infer a scaling state from prose, and states plainly that
  `Trade_Log` is an incomplete manual log.
- §6 no longer says "*if* you have web access" — that soft framing invited the model
  to skip the step. It now requires the search up front and demands links.
- New ground rule: no number that isn't in the files or a cited source —
  **explicitly naming ETF constituent weights and fund sector percentages**, which is
  the open item below.

### 9. ETF look-through concentration (`utils/etf_holdings.py`, `build_lookthrough`)

New `## ETF Look-Through` section in `portfolio.md` computing direct + indirect
single-name exposure — i.e. your true NVDA weight once QQQM and VTI are counted.

**Vendor note worth knowing before you spend anything:** FMP gates ETF holdings
behind their **Ultimate tier, $149/mo**. Your `fmp_client.py` comments say free tier
and rate-limit accordingly, so extending `fmp_client.py` per the usual rule would
have meant a subscription upgrade. yfinance is already in `requirements.txt` and
exposes `funds_data.top_holdings` for free, so the module uses that — no new vendor,
no new key, no new cost.

Design points:

- **Every figure is labelled a floor.** yfinance gives the top ~10 holdings, which
  don't sum to 100% of a fund. True exposure is at least the stated number and
  probably more. The section says so in the body text so the analyst can't quietly
  treat a floor as an exact figure.
- **Unresolved funds are named explicitly** and flagged "treat as opaque, do not
  guess their contents."
- **Degrades to a hard warning, never a crash.** With no cache and no network the
  section prints "do not estimate fund constituent weights from memory" rather than
  silently vanishing — the failure mode makes hallucination *less* likely, not more.
- **30-day disk cache** under `data/etf_holdings_cache/`. Holdings drift slowly.
- **`--lookthrough {off,cache,refresh}`**, default `cache`. Network is only touched
  on `refresh`, so the default export stays offline and deterministic.

### 10. Manifest provenance
Added `file_sha256` per file, `days_window_applies_to: "podcast summaries only"`
(the 14-day window never governed the rotation data, which read as if it did), and
`preflight_issues`.

---

## Verified

- `python3 -m py_compile` clean on both files.
- Full run against `composite_bundle_2026-07-26T125215Z_c022681b71a9.json` produced a
  complete package: prompt 4,954 / portfolio 7,619 / podcasts 40,674 / theses 27,333 /
  SUBMIT_ME 80,601 bytes.
- `compute_lookthrough` unit-tested against synthetic fixtures. Hand-check:
  NVDA 3.44% direct + (8.70% × 9.00%) via QQQM + (3.84% × 6.00%) via VTI = 4.45%,
  function returned 4.45%. Fixtures deleted afterwards — **no fake holdings data was
  left in `data/`**, verified.
- All three `--lookthrough` modes exercised: `off`, `cache` with no cache present
  (degrades to the warning), and `cache` with a seeded entry (renders the table).
- Test output written to scratch dirs, **not** to `exports/`. Nothing in `exports/`
  was overwritten.

### Not verified — needs one local run

The sandbox blocks outbound network to both financialmodelingprep.com and Yahoo, so
`get_top_holdings()` has **never made a live call**. The parsing logic against
yfinance's `funds_data.top_holdings` DataFrame is written from its documented shape,
not observed output. First real run:

```
python tasks/export_ai_briefing.py --lookthrough refresh
```

Check that `data/etf_holdings_cache/` fills with plausible files and that the
resolved/unresolved split in `portfolio.md` looks sane. If yfinance returns a
different column name than `Holding Percent`, the parser returns None and the fund
lands in "unresolved" — a visible, safe failure, not a wrong number.

---

## Workflow change — morning now produces the briefing (STEP 9)

`manager.py morning` did every piece of work the briefing needs — Schwab sync,
portfolio state, context bundle, vault sync, composite bundle at STEP 8 — and then
stopped, leaving `make_ai_briefing.bat` to be run separately by hand. There was no
reason for the split.

Added **STEP 9 — Exporting AI Briefing Package** after the composite bundle:

- Shells out to `tasks/export_ai_briefing.py --lookthrough refresh --no-open`.
- Prints the package path and a reminder to upload `SUBMIT_ME.md`.
- Echoes the preflight lines (SKIPPED / BLOCKING / missing-section counts) into the
  morning console so vault problems surface daily instead of only when you go
  looking for them.
- Non-fatal by design: a failed export marks the step `warn` and morning still
  finishes and writes its summary. It can't take down the Sheets sync.
- `--skip-export` opts out of any given run.
- New `--no-open` flag on the exporter suppresses the Explorer pop-up, so an
  automated morning run doesn't throw a window at you.

`make_ai_briefing.bat` is unchanged in purpose — use it when you want a fresh package
without a full sync.

**Net effect: `run_morning_sync.bat` is now the only thing you need to run.**

---

## Still open — needs your judgment, not code

1. **Archive the six exited theses** — AMD, CRWV, DELL, LRCX, MSFT, SPCX. The
   exporter skips them; the vault still lists them as live.
2. **13 theses have no `## Scaling State` / `## Rotation Priority` section** — AMZN,
   ETN, GILD, GLD, GOOG, IGV, JPIE, META, UNH, VRT, XOM (+2). There's also no
   frontmatter key for either, so there is no authoritative home for the field.
   Worth deciding: body section, or frontmatter? The parser currently only reads
   body sections.
3. **Run `--lookthrough refresh` once** to populate the holdings cache and confirm
   the yfinance parse works against live data.
4. **`Trade_Log` is 97 days stale.** `tasks/derive_rotations.py` exists; whether it
   can backfill from the Schwab transaction CSVs is worth a look.
5. **JEPI at 9.89% and QQQM at 8.70%** are both through your 8% ETF ceiling, and
   JEPI grew ~$12K in six days. Nothing to do with this code — just newly visible.

---

*Boundary note: this changes how portfolio data is packaged and presented, not what
any position is worth or whether it should be held. The ceiling breaches above are
arithmetic against your own stated ceilings, not a recommendation.*
