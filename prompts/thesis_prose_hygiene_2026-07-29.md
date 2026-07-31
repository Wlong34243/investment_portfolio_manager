# Build Prompt: Thesis Prose Hygiene

**Author:** Chief Architect (Claude, 2026-07-29)
**Executor:** Claude Code / Gemini CLI
**Prompt version:** 1.0.0
**Predecessors:** `briefing_integrity_hardening_2026-07-29.md`, `post_hardening_cleanup_2026-07-29.md` (both shipped, verified, uncommitted in working tree)

## Objective

Three items. Deliverable 3 of the hardening batch deleted `current_weight_pct` from frontmatter and made `<!-- region:position_state -->` the sole machine-readable source of truth for position weight. It did not touch **prose** weight claims in the thesis bodies — and prose is what the LLM actually reads, because D1 now exports those sections.

Result: tomorrow's bundle will state two different weights for the same position in two files of the same package.

Small batch. Two files to edit, one lint script, one duplicate-section cleanup.

---

## HARD CONSTRAINT — still in force

**Do not modify `tasks/export_ai_briefing.py`.** It remains unvalidated against an unattended run; tomorrow's 07:45 execution is its first. The lint in Deliverable 3 is therefore a **standalone script**, not a preflight addition. Wiring it into preflight happens in a later batch, after tomorrow's run validates the current exporter.

`manager.py morning` step sequence also unchanged. Bugfixes to existing steps are fine (see the `timedelta` import precedent); reordering is not.

---

## Step 0 — Verification gate

1. Confirm the working tree still contains the uncommitted `timedelta` import at `manager.py:22`. **If it is missing, STOP and report** — tomorrow's 07:45 run throws `NameError` in STEP 10 without it.
2. Open `vault/theses/GLD_thesis.md`. Confirm it contains a `## Scaling State & Priority` header (combined), a prose line reading `- Current 0.18% is a starter...`, a prose line reading `- Rotation priority: low urgency...`, AND a separately appended `## Rotation Priority` section containing `priority: [BILL]`.
3. Open `vault/theses/META_thesis.md`. Confirm a prose line reading `Current allocation: 1.6%.`
4. Confirm actual current weights from `exports/ai_briefing_2026-07-29_082650/portfolio.md`: **GLD 1.00%**, **META 2.42%**.
5. Confirm `<!-- region:position_state -->` blocks in both files carry the correct current allocation.

---

## Deliverable 1: Remove stale weight claims from prose — do not correct them

**Two files affected.** A pattern sweep found only GLD and META; Deliverable 3 will confirm the sweep was complete.

| File | Prose claims | Actual |
|---|---|---|
| `GLD_thesis.md` | `Current 0.18% is a starter` | 1.00% |
| `META_thesis.md` | `Current allocation: 1.6%.` | 2.42% |

**The fix is deletion of the number, not correction of it.** Correcting `0.18%` to `1.00%` resets a clock that runs down again within weeks — it is the same failure that produced VRT reading 0.56% against an actual 1.20% for three months. The region block already carries the live figure and is auto-synced. Prose should express *intent*, which is durable, and never *state*, which is not.

Rewrite to preserve meaning while dropping the number:

- GLD: `- Starter size; build toward 3-5% over time as a portfolio stabilizer.`
- META: delete the line, or fold any surviving intent into the sizing plan without a current-weight figure.

Do not alter surrounding prose. Do not touch either file's `<!-- region:position_state -->` block.

**Note for Bill, not a code task:** GLD's prose says *build toward 3-5%* while its transaction log shows sells on 2026-07-21 and 2026-06-02 against a 1.00% position. Leave that contradiction in place — it is a live drift signal and resolving it is his call, not a cleanup task. Flag it in the output; do not edit it.

---

## Deliverable 2: Resolve GLD's duplicate rotation priority

GLD now states rotation priority twice:

```markdown
## Scaling State & Priority
- Current 0.18% is a starter; build toward 3-5% over time as a portfolio stabilizer.
- Rotation priority: low urgency; add opportunistically on pullbacks, not on momentum.

## Rotation Priority
priority: [BILL]
```

The scaffold was correct per its prompt — GLD genuinely had no `## Rotation Priority` header. The content nonetheless already existed, in prose, under the combined header. A file that can answer the same question two ways will eventually answer it two different ways.

**Fix.** Split the combined header and move the existing content into the machine-readable slots, preserving Bill's own words:

```markdown
## Scaling State
next_step: starter size; build toward 3-5% over time as a portfolio stabilizer

## Rotation Priority
priority: low — add opportunistically on pullbacks, not on momentum
```

**This is the one place in this batch where transcription is permitted, and only because the value is already written in Bill's own prose in the same file.** Move it verbatim in substance. Do not summarize, sharpen, or extend it. Do not infer anything not literally present.

Removing the `[BILL]` placeholder is correct here **only** because the answer already exists in the file. The other 13 placeholders across the vault stay untouched — those genuinely have no stated value, and inventing one would fabricate intent and launder it into a system of record.

Check whether any other thesis file uses a combined `## Scaling State & Priority` header and report them. Do not normalize any file whose prose does not already contain both values.

---

## Deliverable 3: Standalone thesis lint

Create `tasks/lint_theses.py` — read-only, no writes, no Sheets access, no network.

CLI: `python tasks/lint_theses.py [--vault vault/theses]`

Checks, reported per file:

1. **Stale prose weight.** Any percentage in the body that reads as a current-allocation claim, compared against `<!-- region:position_state -->`. Flag divergence above 0.05 percentage points. Match on phrasing variants: `Current allocation`, `Current N%`, `currently N%`, `allocation is N%`, `position is N%`. Report the line number and both figures.
2. **Duplicate state values.** A `priority:` or `next_step:` value present in more than one section.
3. **Combined headers.** `## Scaling State & Priority` or similar, since these parse today only by regex accident.
4. **Unresolved placeholders.** Count `[BILL]` markers per file. This is informational, not a failure — they are deliberate.
5. **Stale review dates.** `last_reviewed` older than 90 days.

Exit 0 always. This is a report, not a gate — the gate goes in preflight later, once the exporter is validated.

Run it across the vault and include the full output in the build report. **If it finds prose weight divergence in any file other than GLD and META, my sweep was incomplete — say so explicitly rather than quietly fixing the extras.**

---

## Post-build verification checklist

- [ ] `tasks/export_ai_briefing.py` unmodified — confirm by mtime (should still read 2026-07-29 09:59:26).
- [ ] `manager.py:22` `timedelta` import still present.
- [ ] No percentage figure remains in GLD or META prose that purports to state current allocation.
- [ ] Both files' `<!-- region:position_state -->` blocks untouched.
- [ ] GLD has exactly one `## Scaling State` and one `## Rotation Priority`, both in `key: value` form, both carrying Bill's original wording in substance.
- [ ] GLD's `[BILL]` placeholder removed; **13 placeholders remain across the vault** (9 scaffolded minus GLD's 1, plus 4 in `SKHY_thesis.md` which are deliberate open items).
- [ ] `git diff vault/theses/` shows changes to GLD and META only.
- [ ] `lint_theses.py` runs clean, output included in the report.
- [ ] Lint finds no prose weight divergence outside GLD and META — or says plainly that it did.
- [ ] `tests/test_bundle_smoke.py` still 14/14.

**Standing constraints (CLAUDE.md)**
- [ ] `DRY_RUN` default unchanged; no new write paths.
- [ ] No writes to `Target_Allocation`.
- [ ] No Schwab order/trading endpoint.
- [ ] No new vendor.
- [ ] Nothing deleted from `vault/` beyond the two stale weight figures named above.

---

## Sequencing

None of this is urgent. Tomorrow's 07:45 run is the priority, and the only thing that must be true for it is the `timedelta` import surviving in the working tree.

The stale-weight contradiction will appear in tomorrow's bundle if this is not done tonight. That is tolerable — it is now a known, documented discrepancy affecting two positions, which is a different thing from a silent one. If tomorrow's run is clean, do this batch and then wire the lint into preflight.
