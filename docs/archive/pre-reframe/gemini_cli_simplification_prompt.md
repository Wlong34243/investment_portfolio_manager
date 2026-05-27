<!--
ARCHIVED 2026-05-27
Gemini CLI handoff for CLI audit and simplification. CLI v3.2 proposal adopted May 2026.
See STATE.md for current state.
-->

# Gemini CLI 3.1 Pro Preview â€” Handoff Prompt

**Mission:** Audit the Investment Portfolio Manager codebase, propose a simplified CLI surface organized around **powerful single commands per workflow**, and update `portfolio_manager_user_docs.html` to reflect the proposed surface.

**Operating mode:** `--yolo` is **not** authorized. Run with default safety. **Read-only audit + proposed diffs only.** No code edits land without my explicit "approve" reply.

**Standard promotion sequence applies:** DRY RUN proposal â†’ I review â†’ I say "approve <section>" â†’ you produce the patch â†’ I run it. No live writes. No git commits without explicit instruction.

---

## Phase 0 â€” Preflight audit (read-only, no code generation)

Use `view` / `read_file` against the repo root. Build a working model of the current CLI surface before proposing anything.

**Files to read in this order:**

1. `manager.py` â€” full file. Inventory every Typer group and command. Note: it is ~2,800 lines with groups `journal`, `trade`, `vault`, `bundle`, `sync`, `tax`, `dashboard`, `export`, `podcast` plus top-level `health`, `snapshot`, `morning`.
2. `config.py` â€” note `EXPORT_SCENARIOS`, `EXPORTS_DIR`, all `TAB_*` constants, `DRY_RUN`, `PORTFOLIO_SHEET_ID`, podcast config.
3. `CLAUDE.md` â€” current operating philosophy.
4. `PORTFOLIO_SHEET_SCHEMA.md` â€” sheet model.
5. `CHANGELOG.md` â€” read the most recent ~6 entries to understand the latest pivots (`pm morning`, podcast restructuring, sync `--reconcile`, export engine).
6. `portfolio_manager_user_docs.html` â€” current docs version 3.x. Find the `cli-reference` and `export-engine` sections.
7. `tasks/` directory tree â€” list every file and its top-level `def` so you can see what each CLI command is wrapping.
8. `core/` directory tree â€” bundle / vault_bundle / composite_bundle.
9. `scripts/` directory tree â€” note utility scripts (these are NOT part of the CLI surface but may indicate workflows that should be promoted into it).

**Deliverable for Phase 0 â€” a single markdown report titled `cli_audit.md` with these sections:**

- **Section A â€” Current Surface Map.** A table: `Command â†’ Wraps (file::function) â†’ Writes? â†’ Notes`. Every command in `manager.py` listed.
- **Section B â€” Workflow Clusters.** Group commands by *user intent*, not by Typer group. For example: "Daily operating loop," "Tax visibility," "LLM handoff (export)," "Trade decision capture," "Thesis maintenance," "Podcast research feed," "Hygiene & cleanup," "Diagnostics."
- **Section C â€” Friction Inventory.** Concrete friction points only. Examples I expect you to find or refute:
  - Are there commands that are almost always run in sequence (suggesting a composite)?
  - Are there `--flag` permutations that should be split into separate commands, or vice versa?
  - Are there commands that share 80%+ of setup code?
  - Are `clean` / `cleanup` operations scattered across groups (`podcast clean`, `export cleanup`, ad-hoc CSV deletion, old bundles in `bundles/`)?
  - Where does the user have to remember a sub-sub-command path that could be flattened?
- **Section D â€” Verdict.** Per workflow cluster, one of: `ALREADY GOOD â€” leave alone`, `CONSOLIDATE â€” merge into one command`, `SPLIT â€” too overloaded`, `RENAME â€” wrong mental model`, `MISSING â€” workflow exists in scripts/ but not in CLI`.

**Stop after Phase 0 and wait for me to reply "proceed to Phase 1."** Do not propose the new surface yet.

---

## Phase 1 â€” Propose the simplified surface

Only after I approve Phase 0.

**Constraints â€” non-negotiable, do not violate:**

- `pm morning` already exists as the daily composite. **Do not propose replacing it or wrapping it inside a different command.** Propose changes to it only if Phase 0 found a real friction point.
- DRY RUN remains the default everywhere. `--live` remains the explicit promotion flag. Do not propose any command that defaults to writing.
- The four-layer Sheets model is fixed: authoritative state, computed views, sandbox suggestions, archive. Do not propose commands that mutate `Target_Allocation` from anything other than manual entry, or that promote `AI_Suggested_Allocation` content directly.
- Read-only is a hard rule. No order-entry, no trading endpoints, ever.
- Backward compatibility: every existing command must either survive unchanged, or have a deprecation path with a clearly documented replacement. **Do not silently rename.**
- The pivot away from agent-centric framing is intentional. Do not propose new "agent" commands. Reasoning workflows go through `export <scenario>` â†’ external LLM â†’ manual review.

**Propose a target surface organized around these candidate workflow verbs.** Validate each against Phase 0's findings before including it. If a cluster doesn't justify a consolidation, say so â€” the right answer to "should this be one command?" is sometimes "no."

Candidates to evaluate (not a mandate):

1. **`pm ingest`** â€” single command for "pull everything fresh from upstream sources." Should it merge `sync transactions`, the position-pull half of `snapshot`, `sync realized-gl`, and the podcast batch fetch? Or are those genuinely different cadences that should stay separate? Decide based on Phase 0.
2. **`pm export <scenario>`** â€” already exists. Is the surface clean, or are there scenarios that should be merged / renamed? Is `export cleanup` discoverable, or should hygiene move under a unified `pm clean`?
3. **`pm clean`** â€” unified hygiene command. Today: `podcast clean --days N`, `export cleanup --days N`, plus orphaned bundles in `bundles/`, old CSV uploads, log rotation. Should this be one command with `--target` flags (`--podcasts`, `--exports`, `--bundles`, `--all`)? Or does the cognitive overhead of one super-command exceed the win?
4. **`pm vault sync`** â€” already specced in `thesis_from_transactions_prompts.md`. Confirm whether it has shipped. If yes, just include it. If no, note it as planned.
5. **`pm doctor`** â€” diagnostic super-command. Today `health` exists. Is there a case for `pm doctor` covering health + bundle integrity + thesis coverage + Sheet schema drift in one read-only sweep? Or does that just duplicate `health`?
6. **`pm tax`** â€” already a group with `refresh`. Is there a case for `pm tax review` (read-only summary printed to terminal, no Sheet write) as a daily-glance tool?
7. **`pm rotation`** â€” does the current `trade review` + `journal promote` + `journal rotation` flow want a single `pm rotation` group with clearer sub-verbs (`stage`, `promote`, `review`)?

**Deliverable for Phase 1 â€” `cli_proposal.md` with:**

- For each proposed change: **Before â†’ After** with exact command strings, the friction it solves (cite Section C of `cli_audit.md`), backward-compat strategy, and a one-line "win statement" (e.g. "collapses 3 commands run in sequence weekly into 1").
- A **rejection list**: candidates from above that you evaluated and rejected, with one-sentence reasoning. I want to see what you considered and discarded, not just what survived.
- A **migration table**: every existing command â†’ its replacement (or "unchanged"). Deprecation aliases proposed where applicable.
- An **estimated effort** per change: `S` (under 50 lines), `M` (50â€“200), `L` (200+ or touches multiple files). I will use this to decide build order.

**Stop after Phase 1 and wait for "approve <command_name>" replies.** I may approve some and reject others. Do not write code yet.

---

## Phase 2 â€” Patch generation (only for approved items)

For each approved change:

- Produce a unified diff (`diff -u` style) against the current files. Do not write the files. Print the diff to stdout in a fenced block.
- One diff block per file. Group all diffs for a single approved change together under a `## Change: <name>` header.
- Include any new files (e.g. new `tasks/<x>.py`) as `New file: <path>` followed by full contents in a fenced block.
- For every new or changed CLI command, include the help string, the docstring, and a usage example.
- Test plan per change: one paragraph on how I'll verify it works (DRY RUN command sequence + expected output + LIVE command + verification step in Sheets/filesystem).
- **Do not modify** `vault/theses/*.md`, `Target_Allocation`, `Holdings_Current`, or anything in `Realized_GL`. The patches touch `manager.py`, `config.py`, `tasks/`, and `portfolio_manager_user_docs.html` only. If a proposed change requires touching anything else, **stop and flag it**.

---

## Phase 3 â€” Documentation update

After code patches are approved AND I confirm they ran clean in DRY RUN locally.

**Update `portfolio_manager_user_docs.html`** to reflect the new surface. Constraints:

- Bump the version in the header to the next minor (e.g., 3.1 â†’ 3.2).
- Update the navigation `<nav>` block, the `cli-reference` section, and any other section that references a renamed/merged command.
- Add a **"What changed in this version"** callout near the top of the body, listing the consolidated commands and any deprecations, so I can re-orient quickly when I open the doc next month.
- Each new or changed command gets:
  - The exact command string in `<code>`
  - One-sentence purpose
  - The `--live` and any other relevant flags listed
  - A "when to use it" callout if non-obvious
- For deprecated commands, add a strikethrough entry with "â†’ replaced by `<new>`."
- Update the "Daily routine" section if `pm morning` changes. If it doesn't change, leave that section alone.
- Preserve the existing `Files & Data` and `Podcast Workflow` nav structure unless an approved change requires touching them.
- Do not invent new sections that weren't justified by an approved code change.

Deliverable: a single unified diff against `portfolio_manager_user_docs.html`. Do not write the file. I'll review and apply.

---

## Hard rules for the whole session

- **Audit-before-build.** Phase 0 must complete and be approved before Phase 1. Phase 1 must complete and have at least one approved item before Phase 2.
- **No code without approval.** Diffs are proposals, not actions.
- **No silent renames.** Every renamed command gets a deprecation alias unless I explicitly waive it for that command.
- **No new vendors, no new dependencies** unless a proposed change genuinely cannot work otherwise. If you think one is needed, flag it in Phase 1 and justify it; don't sneak it into a Phase 2 diff.
- **No agent / LLM-reasoning commands.** This is a deterministic CLI. AI workflows go through `export â†’ external LLM â†’ manual review`.
- **`pm` is the install shortcut** (`pip install -e .` already done). All command examples use `pm`, not `python manager.py`.
- **If anything in this prompt conflicts with what you find in the codebase, stop and ask.** Don't paper over the contradiction.

---

## What good looks like at the end of this session

A `cli_audit.md` I trust, a `cli_proposal.md` where I can read each "Before â†’ After" in 30 seconds and decide, a small set of clean diffs that consolidate the daily-use surface into a smaller number of stronger commands, and an updated user doc that reads like a control panel rather than a feature catalog.

The end state should make the system feel like a portfolio control system, not a Typer app with 40 commands.

