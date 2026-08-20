# Build Prompt: AI_Suggested_Allocation Atomic Write

**Author:** Claude (Chief Architect) / Cursor (audit re-author), 2026-08-20
**Executor:** Cursor Agent
**Prompt version:** 1.1.0
**Supersedes:** `prompts/fix_podcast_multi_signal_merge_2026-08-20.md` v1.0.0 (misdiagnosed last-write-wins)
**Type:** Data-loss fix.

**Audit finding (2026-08-20):** `tasks/batch_podcast_sync.py` does **not** write Sheets. `weekly_podcast_sync.py` already merges by preserving rows whose `Source` differs. The real bug is an **un-transacted clear-then-write**: `batch_clear(["A1:K1000"])` then `sleep` then `update`. If the update fails (429/500, parent timeout), the tab is left **empty** and later runs rewrite from nothing.

**Not in scope for v1:** weighted consensus, credibility scores, inventing a multi-channel accumulate loop that the code already approximates via per-source merge.

---

## Sequencing

Independent of store migration. Sandbox tab. Safe anytime.

---

## Scope boundary

**In scope:** `tasks/weekly_podcast_sync.py` write path to `AI_Suggested_Allocation`; archive-before-overwrite into `Agent_Outputs_Archive` if that path exists for this tab (or a dated archive tab / local archive — prefer existing project pattern).

**Out of scope:** `core/`, Spotify aggregate decomposition, `Target_Allocation`, transcript fetching, scoring rubrics.

---

## Step 0 — Verification gate (paste RAW stdout under each)

- [ ] **Locate the clear-then-write**

```text
rg -n "batch_clear|AI_Suggested|TAB_AI_SUGGESTED|update\(" tasks/weekly_podcast_sync.py
```

- [ ] **Confirm batch_podcast_sync does not write the tab**

```text
rg -n "AI_Suggested|worksheet|gspread|update\(" tasks/batch_podcast_sync.py
```

- [ ] **Existing archive pattern**

```text
rg -n "Agent_Outputs_Archive|archive.*before|TAB_AGENT_OUTPUTS_ARCHIVE" tasks utils --glob "*.py"
```

If `batch_clear` is absent, STOP and re-diagnose.

---

## Required behaviour after fix

1. **Never leave the tab empty.** Build the full replacement grid in memory first. Prefer: archive prior contents → single `update` of the full range **without** a preceding `batch_clear`, or clear only after a successful write to a staging range / swap. A failed update must leave the previous tab contents intact.
2. **Archive before overwrite** (hard rule 7) — prior tab body to `Agent_Outputs_Archive` or an equivalent dated archive surface before replacing.
3. Keep existing per-source merge semantics (other `Source` rows preserved).
4. Spotify aggregate remains one first-class source in its own voice.
5. No writes to `Target_Allocation`.

---

## Post-build verification checklist (raw stdout required)

- [ ] `rg -n "batch_clear" tasks/weekly_podcast_sync.py` — no matches (or only commented historical note)
- [ ] Dry-run path unchanged (no Sheet writes without `--live`)
- [ ] Code review / dry simulation: if `update` would raise after archive, previous values were never cleared
- [ ] `rg -n "Target_Allocation" tasks/weekly_podcast_sync.py` — no matches
- [ ] `git diff --stat` — no changes under `core/`
