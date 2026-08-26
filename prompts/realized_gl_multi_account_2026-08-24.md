# Realized_GL multi-account re-import — 2026-08-24

**Why.** Live `Realized_GL` is a **single Schwab-account table**. Account column
counts (verified 2026-08-24): `Individual ...119` (5119) = 555 lots; Chase
`...8895` = 80; **zero** rows containing `6499` or `8767` for any ticker.
Both suffixes are in `config.SCHWAB_PRIMARY_ACCOUNT_SUFFIXES`. Tax_Control is
built from Realized_GL after that suffix filter, so YTD figures (Net ST / Net LT /
disallowed / Est. Fed Cap Gains Tax) understate the in-scope book.

The JPIE 2026-08-21 exit in Schwab...8767 (110 sh, proceeds $5,044.42) is the
newest instance — documented in `vault/theses/JPIE_thesis.md` Review Log as
Holdings_History-derived, **not** broker-confirmed. Archive of that thesis is
**held** until this prompt lands lots for 6499/8767 (or Bill explicitly accepts
archive with the gap documented).

`utils/gl_parser.py` already parses multi-account Schwab Lot Details CSVs
(`_find_account_sections_gl`) and single-account titles. The 2026-08-12 import
was a single-account (...119) file plus Chase — not a parser defect. The
2026-08-20 `--merge` per-account completeness guard refuses when a file has
*fewer* lots for an account than the sheet; an account **entirely absent** from
the import never trips it.

Doctrine note: `tax_hold_runners` (UNH/COF) is still the right constraint; its
**magnitude is unverified** until Realized_GL covers all three primary accounts.

---

## STEP 0 — Verification gate

Stop and report if any item fails.

1. `python -c "import config; print(config.SCHWAB_PRIMARY_ACCOUNT_SUFFIXES)"` —
   must be `['6499','8767','5119']` (order may vary).
2. Live Sheet account inventory (paste stdout):
   ```
   Account unique values + row counts on Realized_GL
   ```
   Expect only `Individual ...119` and Chase `...8895` (plus possibly blank).
   Confirm substring counts for `6499` and `8767` are **0**.
3. List files under `data/realized_gl_archive/` — note which 2026-08-12 CSV was
   the last replace source; check its title/section banners for account masks
   (readonly; do not re-import yet).
4. Confirm CLI: `python manager.py ingest realized-gl --help` shows `--merge`,
   `--replace`, `--force-partial-merge`, `--live`.
5. Confirm `vault/theses/JPIE_thesis.md` still live (not in `archive/`) and its
   2026-08-24 Review Log exit bullet is present.

---

## STEP 1 — Bill exports (manual; agent does not browse)

Export Schwab **Realized Gain/Loss – Lot Details** covering **all three**
primary accounts (6499, 8767, 5119). Prefer one multi-account CSV with per-account
section banners. Acceptable alternative: three single-account files, one per
suffix.

Chase `...8895` is **out of scope** for this prompt (already present; Tax_Control
correctly excludes it). Do not `--replace` a Schwab-only file in a way that drops
Chase rows — use `--merge` so Chase lots remain.

Place the export(s) under a dated path, e.g.
`data/realized_gl_incoming/2026-08-24/`, and record the path in the run log.

---

## STEP 2 — Dry-run parse (no Sheet write)

For each file:

```
python manager.py ingest realized-gl <path>   # no --live
```

Paste: detected kind, lot count, **account list**, ST/LT net, disallowed.

**Gate:** every primary suffix must appear as a parseable Account mask
(`Individual ...119` / `...499` / `...767` or equivalent). If 6499 or 8767 is
still missing from the parse, STOP — the export is incomplete; do not merge.

---

## STEP 3 — Merge dry-run planning, then `--live --merge`

1. Snapshot current Tax_Control YTD KPIs (Net ST, Net LT, disallowed, Est. Fed
   Cap Gains Tax) and Realized_GL row counts by account — paste before numbers.
2. `python manager.py ingest realized-gl <schwab_path> --merge` **without**
   `--live` first if the CLI supports a dry path; otherwise print the merge
   plan (accounts that will be replaced, lot counts in/out) and STOP for
   Bill sign-off.
3. After sign-off: `--live --merge` for the Schwab export(s). Do **not** pass
   `--force-partial-merge` unless Bill explicitly authorizes shrinking an
   account. Do **not** use bare `--replace` unless Chase lots are included in
   the same write or re-merged immediately after.
4. Rebuild Tax_Control (`pm refresh tax --live` or the morning path equivalent).
5. Paste after: Realized_GL account counts (must show non-zero 6499 and 8767
   masks), Tax_Control YTD before/after, JPIE lots closed on/after 2026-08-21
   if present.

---

## STEP 4 — JPIE exit confirmation + archive gate

Once 8767 lots exist in Realized_GL:

1. Locate the 2026-08-21 JPIE disposal lots. Compare proceeds and G/L to the
   thesis Review Log derived figures (proceeds $5,044.42, derived G/L −$55.43).
   Paste the broker rows. Update the Review Log with broker-confirmed numbers
   if they differ — label the prior line as superseded.
2. Present archive proposal: `pm clean theses --live` for JPIE (or the
   established archive command). **STOP for Bill sign-off** before archiving.
3. After archive: next briefing should drop the JPIE `SKIPPED` preflight and
   the `EXITED_POSITION_LIVE_THESIS` finding.

---

## Verification checklist

**Literal stdout for every item.**

1. Realized_GL Account value counts include non-zero rows for masks matching
   6499 and 8767 (paste).
2. Tax_Control before/after YTD table (paste). Est. Fed Cap Gains Tax must move
   if material lots were added — if it does not, investigate scope filter /
   `Is Primary Acct` before declaring PASS.
3. JPIE 08-21 lots present or explicitly absent with reason (paste).
4. Chase `...8895` row count unchanged vs pre-merge (or explain delta).
5. No `--force-partial-merge` unless Bill authorized it in the run log.
6. `state.md` / `CHANGELOG.md` updated with the understatement correction.

## Update on completion

- `state.md` Recent Decisions — one dated entry; clear or rewrite the
  "Realized_GL 5119-only" What's Next flag.
- `CHANGELOG.md` — dated entry.
- Optional one-line note under doctrine / Trim Triggers in `CLAUDE.md` only if
  Tax YTD magnitude language needs a standing caveat; default is state.md only.
