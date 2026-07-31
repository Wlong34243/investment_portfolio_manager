# Build Prompt: Briefing Integrity Hardening

**Author:** Chief Architect (Claude, 2026-07-29)
**Executor:** Claude Code / Gemini CLI
**Prompt version:** 1.0.0
**Trigger:** 2026-07-29 morning brief produced three false findings and missed one real failure. Root causes traced to `tasks/export_ai_briefing.py` and to the absence of alerting on pipeline degradation.

## Objective

Stop the briefing pipeline from silently corrupting the analysis that runs on top of it.

Every defect below was found by comparing what the briefing bundle said against what the underlying files actually contain. The pattern is consistent: **the export layer is lossy in ways it does not disclose, and the failure layer is quiet in ways it should not be.** An analyst — human or model — reading the bundle has no way to detect either.

Concrete damage on 2026-07-29:
- A "VRT thesis has no risk section" finding, escalated to a lead item in the saved analysis. The file has a full `## Key Risks` block and four `## Hard Exit Conditions`. The exporter never shipped them.
- A "10 thesis files missing `## Scaling State`" preflight warning. The sections exist in those files. The parser was looking for a key format they do not use, and the error message named the wrong cause.
- A recommendation to halt trading and "fix the price feed" because VRT showed -12.2%. The feed was correct — it was a live pre-market quote on an earnings morning. Nothing in the brief indicated VRT was reporting that day.
- A `morning_auto.bat` FAIL on 2026-07-27 (Schwab token, critical health gate) that reached no one. It was discovered two days later by reading the log by hand.

---

## Step 0 — Verification gate

Confirm each before writing any code. If a check fails, STOP and report rather than building.

1. `python manager.py --help` runs from repo root. Note which Python (no `.venv`; system 3.12 expected).
2. `tasks/export_ai_briefing.py` exists and contains functions `extract_section`, `first_paragraph`, `extract_key_value`, `build_theses_md`, `strip_citation_markers`, `extract_region`.
3. Open `vault/theses/VRT_thesis.md`. Confirm it contains `## Key Risks`, `## Hard Exit Conditions`, `## Scaling State`, `## Rotation Priority`. (This file was edited 2026-07-29; if the headers differ from that list, re-read before proceeding.)
4. Open `vault/theses/VST_thesis.md`. Confirm `## Scaling State` contains a line beginning `next_step:` and `## Rotation Priority` contains a line beginning `priority:`.
5. Open the newest `exports/ai_briefing_*/theses.md`. Confirm that for any given ticker it contains only a one-paragraph core thesis and a transaction list — **no risk section, no exit conditions.** This is the bug; see it before fixing it.
6. `logs/morning_auto.log` exists and contains at least one `FAIL:` line.
7. `tasks/derive_rotations.py` exists. Confirm whether it is invoked anywhere in `manager.py morning`.
8. Confirm whether `Trim` / `Add` level values are sourced from a Sheet tab, a local config, or thesis frontmatter. **Do not assume.** Report what you find before Deliverable 5.

---

# P0 — Data integrity

These corrupt downstream analysis. Fix first, in order.

## Deliverable 1: Ship the whole thesis, not the first paragraph

**Root cause (confirmed in source).** In `build_theses_md`:

```python
core_section = extract_section(body, "Core Thesis")
core_para = first_paragraph(core_section)
```

`first_paragraph()` splits on the first blank line and returns element zero. Everything after the opening paragraph of `## Core Thesis` is discarded, and `## Key Risks`, `## Hard Exit Conditions`, `## Bull Case`, `## Position Sizing Plan` are never extracted at all. The analysis prompt in `prompt.md` §5 asks the model to "flag any thesis whose risk section omits the risk that is actually biting right now" — against a document from which every risk section has been removed. The prompt is asking a question the bundle makes unanswerable.

**Fix.** Extract and ship these sections per ticker, in this order, when present:

| Section | Treatment |
|---|---|
| `## Core Thesis` | full section, not first paragraph |
| `## Key Risks` | full |
| `## Hard Exit Conditions` / `## Exit Conditions` | full — accept both spellings |
| `## Scaling State` | full |
| `## Rotation Priority` | full |
| `## Review Log` | most recent 3 entries |

Omit `## Bull Case`, `## Origin`, `## Why This Fits My Portfolio` unless the size budget allows — they are context, not drift-control inputs.

**Size guard.** `theses.md` is currently ~26KB against a ~105KB `SUBMIT_ME.md`. Full sections will grow it materially. Add `--thesis-detail {full,standard,minimal}` defaulting to `standard` (the table above). `minimal` reproduces today's behavior for size-constrained runs. Print the resulting byte count per file in the manifest and warn above 250KB total.

**Disclosure requirement — this is the part that matters.** Whatever is dropped must be named. Add to the top of `theses.md`:

```
Sections included per position: Core Thesis, Key Risks, Exit Conditions, Scaling State,
Rotation Priority, Review Log (3 most recent). Sections omitted at export: <list>.
Transaction logs show the <N> most recent entries per position and are NOT complete
position history.
```

A lossy export is acceptable. An undisclosed lossy export is not — it is the difference between a model saying "the file does not cover this" and "the export did not carry this."

## Deliverable 2: Fix the scaling-state parser and its error message

**Root cause (confirmed in source).** `extract_section` matches the heading fine — `^##\s+Scaling State.*?\n` also matches `## Scaling State & Priority`. The failure is one layer down:

```python
next_step = extract_key_value(scaling_section, "next_step")
```

`extract_key_value` requires `^next_step:\s*(.*)$` — line-start, exact case, no list marker. Files written in prose or bullet form (`- Next step: **hold starter position**`) return `None`, and the position is reported as having no Scaling State section at all.

**The diagnostic is wrong, and that is the more serious half of the bug.** The preflight told me ten files were missing a section that all ten of them have. I acted on that and reported it to Bill as a documentation gap. It was a parser gap.

**Fix.**
1. `extract_key_value` should tolerate an optional leading list marker (`-`, `*`), optional bold wrapping, and case-insensitive key matching. Accept `next_step`, `Next step`, `- **Next step:**`.
2. If the key is absent but the section exists and is non-empty, fall back to the section's first paragraph as the value and mark it `(prose)` in the digest rather than `(missing)`.
3. Distinguish the three states in preflight and use the right message for each:
   - section absent → `"%s: no '## Scaling State' section."`
   - section present, key absent, prose usable → `"%s: Scaling State is prose, not 'next_step:' — parsed by fallback, consider normalizing."`
   - section present but empty → `"%s: '## Scaling State' section is empty."`

Same treatment for `## Rotation Priority` / `priority:`.

**Do not "fix" this by rewriting the ten thesis files to match the parser.** The files are Bill's; the parser serves them.

## Deliverable 3: One source of truth for position weight

`vault/theses/VRT_thesis.md` carried `current_weight_pct: 0.56` in YAML frontmatter while its `<!-- region:position_state -->` block read `**Current Allocation:** 1.20%`. Auto-sync updates the region and not the frontmatter. Two numbers for the same fact in the same file, three months apart.

**Fix.** Pick the region block as authoritative (it is machine-written). Then either:
- have the sync writer update frontmatter `current_weight_pct` in the same pass, or
- delete the frontmatter key entirely and read weight only from the region.

Prefer deleting it. A field that can go stale silently is worse than no field. Audit all `vault/theses/*_thesis.md` for the same divergence and report the list before changing anything.

## Deliverable 4: Establish whether transaction logs are truncated, and where

`build_theses_md` ships every `-` line it finds in the `transaction_log` region, so the exporter is not the truncator. But VRT shows three transactions covering 20 shares against a 30-share position — roughly 10 shares of history are absent, which put a hole in the holding-period analysis that a tax-loss decision was resting on.

**Task.** Find the writer that populates `<!-- region:transaction_log -->`. Determine whether it caps entries (likely 5) and whether the cap is configurable. Then:
- Raise the cap to cover at least the full current position, or add `--txn-limit`.
- If a cap remains, the region must state it: `(showing N most recent of M)`.
- If the writer cannot see older transactions because the Schwab pull window is bounded, say that in the region instead — the two causes need different fixes and the current output cannot distinguish them.

---

# P1 — Silent failures

## Deliverable 5: Level-coverage report

VRT's `Trim` and `Add` cells are blank, so the morning brief's "Near your levels" section silently omitted the one position that most needed attention. A blank level and a level that is far away render identically: as nothing.

**Fix.** Per Step 0 item 8, once the level source is confirmed, add a coverage check to the morning run that reports:
- positions with no Trim level
- positions with no Add level
- positions whose levels have not been reviewed since a configurable staleness threshold (default 90 days), using `last_reviewed` from thesis frontmatter

Write it to the command center footer as a one-line count (`Levels: 24/34 trim, 19/34 add, 6 stale`) and to the bundle manifest as a list. Do not block on it.

## Deliverable 6: Health-gate alerting

`morning_auto.bat` failed on 2026-07-27 with a critical health gate on the Schwab token, printed a clear message to a log file nobody reads, and exited. The next two runs proceeded and the Sheet footer showed `Schwab Token | n/a` — visible, but not distinguishable from normal by anyone not looking for it.

**Fix.**
1. On critical health failure in unattended mode, write a sentinel file `logs/HEALTH_FAILURE.flag` containing timestamp, failing check, and remediation command.
2. On the next successful run, delete the sentinel.
3. The command center footer must render degraded state as degraded — not `n/a` but `STALE (3d)` or `AUTH REQUIRED`, so it reads as a problem at a glance.
4. Any downstream consumer that finds the sentinel present prepends a staleness banner to its output.

Email/Slack alerting is out of scope for v1. The sentinel plus a loud footer is enough.

## Deliverable 7: Earnings-proximity flag

The single largest one-day move in the 2026-07-29 snapshot was VRT at -12.2%, and nothing in the brief indicated VRT was reporting that morning. That absence produced a confidently wrong "the price feed is broken" call.

**Fix.** Add an `Earnings` column to the command center: `TODAY`, `T-2`, `T+1`, or blank. Source from the existing FMP client — extend `utils/fmp_client.py`, do not add a vendor. Cache daily.

Flag any position within +/-3 days of an earnings date. A large day move next to an `Earnings: TODAY` marker is information; the same move alone is a puzzle that invites invention.

---

# P2 — Known debt

Do these only after P0 and P1 pass verification.

## Deliverable 8: Wire rotation derivation into the morning run

`Trade_Log`'s most recent entry is 2026-04-20 — 100 days stale as of this bundle. At least two clean rotations since are invisible to it and were reconstructed by hand from per-position transaction logs: the 2026-07-20 `EMXC -100sh ~$9.25K -> BBJP +125sh ~$9.18K` same-day pair, and the JPIE drawdown funding financials, Japan and JEPI across 07-17 and 07-20.

`tasks/derive_rotations.py` already exists and writes to `Trade_Log_Staging` for manual promotion. Call it from `manager.py morning` under `DRY_RUN` and report the staged candidate count. Do not auto-promote — the substitution thesis is Bill's to write.

## Deliverable 9: Orphan thesis archiving

AMD, CRWV, DELL, LRCX, MSFT, SPCX have thesis files with no corresponding position. They are re-flagged as preflight issues every single run, which is how a warning becomes furniture.

Add `python manager.py thesis archive <TICKER>` moving the file to `vault/theses/archive/` with a closing timestamp. Then archive the six. A warning that fires every run and is never actioned trains the reader to skip the preflight block — which is exactly where the real findings live.

## Deliverable 10: Citation-marker handling

`strip_citation_markers` removed 4 markers from JPIE and 2 from XOM. Stripping is correct — the referenced sources are not shipped. But the count currently surfaces only in `preflight_issues`, which reads as a defect report rather than a provenance note. Move it to a `provenance` block in the manifest and out of `preflight_issues`.

---

## Gemini peer-review checkpoint

After P0 passes verification and before starting P1, write `GEMINI_REVIEW_REQUEST_briefing_integrity.md` posing these questions:

1. Is `standard` the right default detail level, or should the exporter ship full theses and let size be the caller's problem?
2. Is the prose fallback in Deliverable 2 a genuine fix or does it mask a real normalization debt across the vault?
3. Deliverable 3 proposes deleting `current_weight_pct` rather than syncing it. Is removing a convenience field the right call, or does something downstream read it?
4. Does the sentinel-file pattern in Deliverable 6 hold up if two scheduled tasks run concurrently?

---

## Post-build verification checklist

The build is not done until every line passes.

**P0**
- [ ] `python tasks/export_ai_briefing.py` runs clean and writes to a new `exports/ai_briefing_*/`. No existing export directory is modified.
- [ ] New `theses.md` contains VRT's `## Key Risks` text including the management-execution paragraph, and all five Hard Exit Conditions.
- [ ] `theses.md` header names every omitted section and states the transaction-log limit.
- [ ] Preflight no longer reports "missing '## Scaling State'" for any file that has the section. Files parsed by prose fallback are reported with the prose-specific message.
- [ ] `manifest.json` records per-file byte counts.
- [ ] Frontmatter/region weight divergence audited across all thesis files; list reported.
- [ ] Diff every changed file and confirm no vault thesis content was rewritten. **The exporter changed; the theses did not.**
- [ ] Re-run against the 2026-07-29 bundle inputs and confirm the three false findings named at the top of this prompt no longer reproduce.

**P1**
- [ ] Level-coverage counts appear in the command center footer and match a hand count.
- [ ] Simulated health failure writes `logs/HEALTH_FAILURE.flag`; a subsequent clean run deletes it.
- [ ] Footer renders a degraded token as `AUTH REQUIRED` or `STALE (Nd)`, never `n/a`.
- [ ] Earnings column populates for at least one known upcoming report; verify against a second source before trusting it.

**P2**
- [ ] `derive_rotations` runs in the morning pipeline under DRY_RUN and stages the 2026-07-20 EMXC→BBJP pair.
- [ ] Six orphan theses archived; preflight orphan warnings drop to zero.
- [ ] Citation counts moved out of `preflight_issues`.

**Standing constraints (from CLAUDE.md)**
- [ ] `DRY_RUN` still defaults true; no write path added without `--live`.
- [ ] No writes to `Target_Allocation` from any code path touched here.
- [ ] No Schwab order/trading endpoint imported.
- [ ] No new vendor added; earnings data comes through `utils/fmp_client.py`.
- [ ] `core/bundle.py` not refactored.
- [ ] Nothing deleted or overwritten in `vault/` — new files and targeted edits only.

---

## The principle behind all of this

Every defect here is the same defect: **a layer that loses or suppresses information without saying so.** The exporter drops sections silently. The parser reports the wrong cause silently. The health gate fails silently. Blank levels render as absent levels silently.

The analysis sitting on top is only as good as its ability to know what it is not being told. Optimize for disclosure over completeness — a bundle that says "risk sections omitted at export" is more useful than one that ships them, and far more useful than one that drops them quietly.
