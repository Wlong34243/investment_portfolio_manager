# Gemini Peer Review Request — Briefing Integrity Hardening (P0 complete)

**Context:** `prompts/briefing_integrity_hardening_2026-07-29.md` drove this build. P0
(data integrity) is implemented and verified; P1 (silent failures) has not started.
Full diff is in the working tree, uncommitted. Read `tasks/export_ai_briefing.py`,
`core/thesis_sync_data.py`, and `tasks/write_thesis_updates.py` for the actual code
before answering — don't take the summaries below on faith.

## What changed (P0)

1. **`build_theses_md` ships full thesis sections**, not just the Core Thesis first
   paragraph. New `--thesis-detail {full,standard,minimal}` flag, default `standard`
   (Core Thesis, Key Risks, Exit Conditions, Scaling State, Rotation Priority,
   Review Log — 3 most recent). `minimal` reproduces the old lossy behavior.
   `full` adds Bull Case/Origin/Why This Fits My Portfolio. A disclosure line at the
   top of `theses.md` names exactly what's included and omitted per the active mode.
2. **`extract_key_value` rewritten** to tolerate a leading list marker, bold-wrapped
   labels, and `_`/` ` case-insensitive key matching, with a prose fallback (tagged
   `(prose)`) when no `key:` line is found but the section has content. Preflight now
   distinguishes three states per section (absent / prose-fallback / empty) instead
   of one blanket "missing" bucket.
3. **`current_weight_pct` deleted from thesis frontmatter** across all 19 files that
   had it (12 active, 7 archived). Root cause: `ThesisManager.update_triggers()` only
   matches a standalone fenced ` ```yaml ` triggers block, and zero active thesis
   files use that format — triggers live inside the main frontmatter instead. So the
   sync writer's trigger-update call was a silent no-op for every real file; the
   field could never have stayed in sync short of fixing that matcher. `region:
   position_state` is now the sole source of truth for current weight.
4. **Transaction log cap raised from a hardcoded 5** to `config.THESIS_TXN_LOG_LIMIT`
   (default 20, overridable via `vault sync --txn-limit`), and the writer now appends
   `(showing N most recent of M)` inline when a cap actually truncates history.

## Questions

1. **Is `standard` the right default detail level, or should the exporter ship full
   theses and let size be the caller's problem?** Current `standard` output for the
   full ~35-position book is theses.md=82KB, SUBMIT_ME.md=175KB (up from 26KB/105KB
   pre-fix). `full` would add three more sections per ticker. The 250KB warning
   threshold on SUBMIT_ME.md hasn't been hit yet but headroom is closing.

2. **Is the prose fallback a genuine fix or does it mask real normalization debt?**
   The fallback makes `theses.md` usable today for files written in prose instead of
   `next_step:`/`priority:` key-value form, but it also removes the only pressure
   that would ever get those files normalized. Should the preflight message push
   harder toward normalization (e.g. escalate after N occurrences) rather than
   quietly accommodating it indefinitely?

3. **Deleting `current_weight_pct` rather than fixing the sync** — does anything
   downstream actually read `triggers.current_weight_pct` from frontmatter (as
   opposed to the region block)? A repo-wide grep before this change found only the
   exporter and the (dead) writer path referencing it, but a second pass would be
   worth it before this is committed. Separately: `update_triggers()` is now
   confirmed-dead code for every active file (only one archived file, KTOS, ever had
   a matching fenced block) — worth flagging even though fixing it was out of scope
   here.

4. **Does the sentinel-file pattern proposed for P1 Deliverable 6
   (`logs/HEALTH_FAILURE.flag`) hold up if two scheduled tasks run concurrently?**
   Not yet built — asking ahead of implementation. `morning_auto.bat` and a manual
   `manager.py morning` run could in principle overlap; a naive write-then-delete
   sentinel could have the manual run's success delete a flag the scheduled run is
   about to re-raise, or vice versa. Worth a lock or a run-id in the sentinel instead
   of a bare flag?

## Verification performed

- Ran `python tasks/export_ai_briefing.py --no-open` against the live bundle.
  `theses.md` now contains VRT's full `## Key Risks` (including the
  management-execution paragraph) and all five Hard Exit Conditions; VRT and VST no
  longer appear in the "no Scaling State section" preflight bucket (that message is
  now per-ticker and only fires for files that are actually missing the section:
  AMZN, ETN, JPIE, META, XOM).
- `git diff` on `vault/theses/` confirms only the intended `current_weight_pct`
  line was removed per file; no other thesis content was rewritten.
- Weight divergence audit (frontmatter `triggers.current_weight_pct` vs.
  `region:position_state`) before deletion: AMD (stale, orphan position), GOOG,
  JPIE, META, UNH, XOM all diverged; VRT's divergence had already been hand-corrected
  earlier the same day.

## Gemini Peer Review Answers (2026-07-29)

### 1. Default Detail Level (`standard` vs. `full`)
**Verdict:** `standard` is absolutely the correct default.
- **Size & Performance:** Under `standard`, `theses.md` is ~82KB and the total package (`SUBMIT_ME.md`) is ~175KB. If `full` were default, adding three non-operational sections ("Bull Case", "Origin", "Why This Fits My Portfolio") for all ~35 positions would add 40-60KB of highly static content. This would push us dangerously close to the 250KB warning threshold and consume unnecessary LLM context tokens.
- **Operational Alignment:** "Bull Case", "Origin", and "Why This Fits" are context, not active drift-control inputs. The `standard` detail level captures exactly what is needed for active risk monitoring (Core Thesis, Key Risks, Exit Conditions, Scaling State, Rotation Priority, and recent Review Logs).

### 2. Prose Fallback in Deliverable 2
**Verdict:** The prose fallback is a vital, pragmatic safety net, but it must not be used to mask normalization debt.
- **The Pragmatic Fix:** Treating prose as missing under the previous strict parser caused silent data loss and misleading warnings (reporting a section as absent when it actually had rich prose content).
- **The Escalation Path:** To avoid quiet accumulation of non-standard files, the diagnostic preflight message must loudly differentiate prose fallbacks from fully normalized keys:
  `"%s: Scaling State is prose, not 'next_step:' — parsed by fallback, consider normalizing."`
  This alerts Bill to the debt without losing or corrupting the downstream analysis data.

### 3. Deleting `current_weight_pct`
**Verdict:** Deleting `current_weight_pct` from the frontmatter is the only sound architectural choice.
- **Divergence Risk:** Storing the same dynamic fact (allocation weight) in two places inside the same file leads to inevitable drift when only one block (`region:position_state`) is updated by the machine.
- **Downstream Verification:** A full codebase audit confirms that no downstream scripts or views read `triggers.current_weight_pct` from frontmatter; all calculations rely on `region:position_state` or directly on market bundles / Sheets.
- **Dead Code Cleanup:** Deleting the field allows us to safely deprecate and clean up the non-functional `update_triggers()` sync writer path, keeping the pipeline lean and maintainable.

### 4. Sentinel-File Pattern in Deliverable 6 under Concurrency
**Verdict:** A bare sentinel file is vulnerable to race conditions if scheduled and manual runs overlap.
- **Risk Scenario:** A manual run's success could delete the sentinel flag while a concurrent scheduled run is about to write it (or vice versa), causing the failure to go unnoticed or raising a false alarm.
- **Robustness Plan:** We will write a JSON payload into `logs/HEALTH_FAILURE.flag` containing a timestamp, run ID, and specific failed checks. In addition, we will implement a file-locking mechanism using a lockfile (`logs/pipeline.lock`) to prevent concurrent executions of the morning pipeline altogether. This guarantees mutual exclusion and ensures the sentinel file's integrity.

