# Build Prompt: Post-Hardening Cleanup

**Author:** Chief Architect (Claude, 2026-07-29)
**Executor:** Claude Code / Gemini CLI
**Prompt version:** 1.0.0
**Predecessor:** `prompts/briefing_integrity_hardening_2026-07-29.md` (P0-P2 shipped and verified same day)

## Objective

Six small, isolated items surfaced during verification of the hardening batch. None are large. Two close holes that silently destroy or misreport data.

---

## HARD CONSTRAINT — read before anything else

**Do not modify `tasks/export_ai_briefing.py` in this batch.**

That file was substantially rewritten today (thesis section extraction, state-field parsing, provenance block, health sentinel banner) and has not yet survived a single unattended `morning_auto.bat` run. Tomorrow's 07:45 execution is its first integration test.

Every deliverable below lives in a different file. If a fix appears to require touching the exporter, **STOP and report it** rather than making the change — it goes in the next batch, after tomorrow's run validates the current one.

Same applies to `manager.py morning`'s step sequence. Additive CLI subcommands are fine; changes to the morning pipeline order are not.

---

## Step 0 — Verification gate

1. `python manager.py --help` runs from repo root.
2. `pm clean theses --help` exists (added 2026-07-29). Read the implementation and report which glob pattern it uses and how it determines "held."
3. `vault/theses/SKHY_thesis.md` exists. Confirm `entry_date: 2026-07-29` in frontmatter.
4. Confirm SKHY is **not** present in the `Holdings_Current` Sheet tab. (Position opened 2026-07-29 after the 08:22 refresh.)
5. `utils/etf_holdings.py` exists. Report how it keys symbols in the look-through output.
6. Both export directories exist: `exports/ai_briefing_2026-07-29_082650/` and `exports/ai_briefing_2026-07-29_095946/`.
7. `tests/test_bundle_smoke.py` — 10 tests, all passing.

---

## Deliverable 1: Archival guard on `pm clean theses`

**The hole.** `pm clean theses` archives thesis files for tickers absent from `Holdings_Current`. A position bought between Schwab syncs is absent from `Holdings_Current` by definition. Running `--live` in that window archives the thesis for a position that was just opened.

**Live case:** `SKHY_thesis.md` was created 2026-07-29 10:04 for a position opened the same day. `Holdings_Current` last refreshed 08:22 and does not contain SKHY. The file survived today's sweep only because it did not yet exist when the sweep ran. The next `--live` run archives it.

**Fix.** Before archiving any file, skip it when either condition holds:
- frontmatter `entry_date` is on or after the `Holdings_Current` refresh timestamp, or
- file mtime is on or after the `Holdings_Current` refresh timestamp

Report skipped files explicitly: `SKIPPED SKHY: thesis newer than Holdings_Current refresh (2026-07-29 08:22) — position may not have synced yet.` A silent skip trades one invisible failure for another.

If the refresh timestamp is not readable from the Sheet footer, fall back to a `--min-age-days` guard defaulting to 7 and say so in the output.

**Also:** confirm `.bak.*` files cannot be matched by the archival glob. There are dozens in `vault/theses/`.

---

## Deliverable 2: Issuer-level aggregation in the look-through

**The defect.** The ETF look-through keys on ticker symbol, so the same issuer under two symbols reports as two companies. Already visible in the 2026-07-29 output: `GOOG` at 6.06% and `GOOGL` at 0.54% appear as separate rows.

**Now material.** SKHY (Nasdaq, direct) and 000660.KS (KRX, held inside EMXC 0.20% and VEA 0.09%) are SK Hynix. Reported direct exposure is 0.47%; true exposure is approximately **0.76%**. Concentration reporting understates by roughly 60% on this position.

**Fix.** Add an issuer alias map to `config.py`:

```python
ISSUER_ALIASES = {
    "GOOGL": "GOOG",
    "SKHY": "000660.KS",
    # extend as dual listings appear
}
```

Apply it in `utils/etf_holdings.py` when aggregating direct + indirect weight. Keep the constituent symbols visible in the Sources column so the provenance is not lost — collapse the row, not the evidence.

Do not attempt automated issuer resolution via any vendor. A hand-maintained map of the handful of dual listings actually held is correct here and costs nothing to extend.

---

## Deliverable 3: Account for the `portfolio.md` size delta

`portfolio.md` went **9,120 bytes (08:26 export) → 7,489 bytes (09:59 export)**, a 1,631-byte reduction, while every other file in the package grew or held steady.

**Diagnostic only. Do not change code until the delta is explained.**

Diff the two files and account for the difference. Candidate causes: `current_weight_pct` removal from thesis frontmatter feeding the style map, changes to the Style Size Ceiling Check, changes to the ETF Look-Through section, or a holdings change between 08:26 and 09:59.

Report which sections shrank and by how much. If any section lost content that should have been retained, that is a P0 finding — report it and stop rather than patching.

---

## Deliverable 4: Smoke coverage for the CSV fallback path

An `AttributeError` on `ETF_KEYWORDS` reached runtime in the CSV parser and was fixed reactively by defining the constant in `config.py`. That it reached runtime means the fallback ingestion path has no smoke coverage.

This matters more than its size suggests: the CSV parser is the disaster-recovery path for when the Schwab API is unavailable, and **the Schwab token is currently showing `n/a`**. A broken primary with an untested fallback is not a fallback.

**Fix.** Add to `tests/test_bundle_smoke.py`:
- `utils/csv_parser.py` imports cleanly and every module-level constant it references resolves
- a parse run against one of the existing repo fixtures (`All-Accounts-Positions-*.csv`) returns positions with `ticker`, `market_value`, `cost_basis` populated
- multi-account section parsing and fractional share handling each covered by one assertion

Fixtures already exist in the repo root. Do not create new test data.

---

## Deliverable 5: Reconcile active thesis file count

`ls vault/theses/*_thesis.md | wc -l` returns **35**. Held positions are 33 tickers plus `CASH_MANUAL` (no thesis), plus `SKHY` (not yet in `Holdings_Current`) = 34 expected.

Identify the extra file. Report it. Do not archive anything — Deliverable 1's guard must land first.

---

## Deliverable 6: Scaffold missing state sections — STRUCTURE ONLY

Fourteen files are missing fields the drift-detection layer reads.

**Missing `## Scaling State` (5):** AMZN, ETN, JPIE, META, XOM
**Missing `## Rotation Priority` (9):** AMZN, ETN, GILD, GLD, GOOG, JPIE, META, UNH, XOM
**Prose-format Scaling State, parsed by fallback (1):** GLD

Append the missing sections to each file in the exact format the parser reads:

```markdown
## Scaling State
next_step: [BILL]

## Rotation Priority
priority: [BILL]
```

Place them before the `<!-- region:position_state -->` block. Do not touch GLD's existing prose Scaling State — the fallback reads it; only add its missing Rotation Priority.

### What NOT to do — this is the important part

**Do not infer, draft, or fill in any value.** Not from the thesis prose, not from the transaction log, not from the position's current weight or drift.

JPIE shows 404 shares sold across five transactions between 2026-06-25 and 2026-07-23. A plausible-looking `next_step: reduce` written by a tool would become the baseline that every future drift check measures against — a fabricated intent, laundered into a system of record, then reported back to Bill as if he had stated it.

The governing principle in `prompt.md` applies directly: Bill is the authoritative source on Bill's decisions; the vault is a lagging record of those decisions, not a source of them. Scaffolding the structure is mechanical and delegable. The fourteen values are his, and they are one line each.

Leave `[BILL]` literally in the file. It is meant to be conspicuous.

---

## No Gemini checkpoint this batch

Six isolated items, no architectural decisions, no schema changes. Reserve the peer-review step for the next batch, which will touch the export path.

---

## Post-build verification checklist

- [ ] `tasks/export_ai_briefing.py` is **unmodified**. Confirm by diff. This is the primary constraint of this batch.
- [ ] `manager.py morning` step sequence is unchanged.
- [ ] `pm clean theses --dry-run` reports `SKIPPED SKHY` with the newer-than-refresh reason.
- [ ] `pm clean theses --dry-run` archives nothing else unexpected; the six files archived on 2026-07-29 stay archived.
- [ ] `.bak.*` files are not matchable by the archival glob.
- [ ] Look-through output shows a single SK Hynix row at approximately 0.76% total, with EMXC, VEA and the direct position all named in Sources.
- [ ] GOOG and GOOGL collapse to one row without losing constituent detail.
- [ ] `portfolio.md` delta fully accounted for in writing, section by section.
- [ ] CSV fallback tests added and passing; full suite green (10 existing + new).
- [ ] Extra thesis file identified and reported. Nothing archived.
- [ ] Fourteen scaffolded sections present, all values literally `[BILL]`, no inferred content anywhere.
- [ ] `git diff vault/theses/` shows **only** appended sections — no existing thesis prose altered.

**Standing constraints (CLAUDE.md)**
- [ ] `DRY_RUN` defaults true; no new write path without `--live`.
- [ ] No writes to `Target_Allocation`.
- [ ] No Schwab order/trading endpoint.
- [ ] No new vendor.
- [ ] `core/bundle.py` not refactored.
- [ ] Nothing deleted from `vault/` — appends and new files only.

---

## Sequencing note

Deliverable 1 is the only time-sensitive item, and its interim mitigation is free: **do not run `pm clean theses --live` until a Schwab sync has picked up SKHY.** It is a manual command; nothing fires it automatically. That removes the urgency without removing the fix from the list.

Everything else here can wait for tomorrow's morning run to validate the hardening batch first. If tomorrow's run fails, diagnose that before adding these changes on top.
