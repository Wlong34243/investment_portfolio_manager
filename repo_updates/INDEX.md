# CLI Migration Bundle — Personal Expense Tracker

This bundle contains everything needed to migrate the Personal Expense Tracker from Streamlit to a CLI interface, plus the user-facing documentation and updated repo files.

## What's in this bundle

```
prompts/
  CLAUDE_CODE_PROMPTS.md       7 sequenced prompts (M0 → M6) for Claude Code
  GEMINI_CLI_PROMPTS.md        Minimal Sheet-side prompts for Gemini CLI

docs/
  USER_GUIDE.html              Standalone HTML operator manual (open in browser)

repo_updates/
  README.md                    CLI-first README to drop into the repo
  CLAUDE.md                    Updated project memory reflecting migration plan
  CHANGELOG.md                 Updated changelog with [Unreleased] migration entry
  STATUS_2026-05-03.md         Status snapshot for this week's commit
```

## How to use this bundle

### 1. Drop the docs and repo updates into the repo

| Bundle file | Repo destination |
|---|---|
| `docs/USER_GUIDE.html` | `docs/USER_GUIDE.html` (create `docs/` if needed) |
| `repo_updates/README.md` | `README.md` (replace existing) |
| `repo_updates/CLAUDE.md` | `CLAUDE.md` (replace existing) |
| `repo_updates/CHANGELOG.md` | `CHANGELOG.md` (replace existing — preserves all prior entries) |
| `repo_updates/STATUS_2026-05-03.md` | `STATUS_2026-05-03.md` (new file, top-level) |

The `prompts/` directory should also live in the repo (under `prompts/`) so the migration prompts are version-controlled alongside the code they will produce.

Commit message suggestion:
```
docs: CLI migration plan + user guide + status update

- Add CLI_MIGRATION_PLAN.md and migration prompts (Claude Code + Gemini CLI)
- Add docs/USER_GUIDE.html operator manual
- Replace README with CLI-first version
- Update CLAUDE.md to reflect migration plan and recent fixed-expense work
- Add STATUS_2026-05-03.md snapshot
```

### 2. Execute migration prompts in order

Each prompt is self-contained. Paste into Claude Code, let it run, commit, then proceed.

| Prompt | Purpose | Risk |
|---|---|---|
| **M0** | Read-only verification of current repo state | None |
| **M1** | Scaffold CLI alongside Streamlit | Low (additive) |
| **M2** | `pet ingest` (Phases 1–4) | Medium |
| **M3** | `pet review` and `pet distribute` (Phase 5) | Medium |
| **M4** | `pet variance`, `pet amazon enrich`, `pet rules`, `pet logs` | Low |
| **M5** | Cutover — deprecate Streamlit | High (run only after 30 days CLI-only) |
| **M6** | Delete `_deprecated/` | Low |

**Do not chain prompts.** Run each, commit, sanity-check, then proceed.

### 3. Use the Gemini CLI prompts for Sheet-side work

`prompts/GEMINI_CLI_PROMPTS.md` has just three Sheet operations:
- **G0** — read-only audit before M1 (verify both sheets are in expected state)
- **G1** — append migration-start row to System_Logs (run before M1)
- **G2** — append migration-cutover row to System_Logs (run before M5)
- **G3** — read-only verification after M5 (confirm CLI is writing through normal pipeline path)

The migration is overwhelmingly local repo work; the Sheet API surface is barely touched.

### 4. Open the user guide

`docs/USER_GUIDE.html` is a single self-contained HTML file. Open it in any browser — no server, no JavaScript dependencies. Bookmark it locally for reference during monthly runs.

---

## Design choices in this bundle

**Why these prompts and not others.** Every prompt encodes the project's hard rules: dry-run default, no auto-chaining, content-based column detection, batch_update only, archive-before-overwrite. The prompts are written so that even if Claude Code interpreted them loosely, the validation steps would catch any deviation.

**Why HTML for user docs.** Markdown renders inconsistently outside GitHub. The HTML guide is self-contained, prints cleanly, and renders identically on any machine. It also has structure (sidebar nav, callouts, color-coded badges) that markdown can't reliably express.

**Why no PWA.** Per direct instruction. Lisa's manual entry path is the `Expenses` tab; `dedup_manual_vs_bank()` handles overlap with bank rows. No second interface is needed.

**Why drop Plotly chart.** Streamlit-bound. The data lives in `Variance_Summary` in the Dashboard Sheet, which is where the analysis is being built going forward. Adding a kaleido dependency to render PNGs of a chart that nobody asked for would be feature creep.

**Why parallel migration.** The Streamlit app works. Breaking it before the CLI is proven is unnecessary risk. M1–M4 are additive; M5 is the only destructive step and waits 30 days for confidence.

---

## Safe stopping point

Bundle generated. Nothing in the live repo has been changed yet. To proceed:

1. Read `prompts/CLAUDE_CODE_PROMPTS.md` end-to-end before running anything.
2. Commit the docs and repo updates from `repo_updates/` first (they're informational, no code change).
3. Run prompt M0 in a fresh Claude Code session and review its report.
4. If M0 returns a go verdict, proceed to M1 in a new session.
