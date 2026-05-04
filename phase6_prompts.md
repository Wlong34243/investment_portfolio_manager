# Phase 6 Prompts — User Documentation Consolidation

**Status:** QUEUED. Do not start until Phase 5 is boring.

**Owner:** Bill. **Executor:** Claude Code or Gemini CLI, one prompt at a time.

**Governing rules:**
- Phase 6 does not start until Phase 5 is boring. No exceptions.
- Phase 6 is primarily a documentation phase — little new code, lots of clarity.
- Single commit per prompt.

---

## Why this phase exists

Over Phases 1–5, the system changes meaningfully. Each phase updates `portfolio_manager_user_docs.html` in small increments. By the time Phase 5 is done, the HTML has:
- Out-of-sequence feature descriptions
- Multiple "workflow" sections that overlap
- CLI references that grew by accretion
- Old architectural framing ("agent-centric") that no longer applies

Phase 6 consolidates everything into a single, current, authoritative user manual that replaces the incremental edits. Think of it as the "release" document — what you'd send a CPA colleague if they asked you to show them the system.

It also takes the opportunity to update `CLAUDE.md` and `PORTFOLIO_SHEET_SCHEMA.md` so they reflect the post-Phase-5 reality.

---

## Scope

In scope:
- A full rewrite of `portfolio_manager_user_docs.html` (Version 3.0)
- Update to `CLAUDE.md` reflecting post-pivot philosophy and the full pipeline
- Update to `PORTFOLIO_SHEET_SCHEMA.md` consolidating all tabs with current column definitions
- A new `README.md` at the project root (if one doesn't exist) with a 60-second quick-start
- A `docs/architecture/` directory with focused architecture notes (the "why" behind the "what")
- Archival of stale prompt files into `docs/archive/`

Out of scope for Phase 6:
- Any new features
- Any refactors of working code
- Marketing content (this is a personal tool, not a product)

---

## Pre-flight

Before starting Phase 6:

- [ ] Phase 5 completion gate fully passed.
- [ ] Walk through the full weekly + monthly workflow one time using only the existing docs. Note every place you had to remember something the docs didn't tell you. Those are the gaps Phase 6 fills.
- [ ] Pull up the original `portfolio_manager_user_docs.html` (Version 2.0) and note how much of it is now obsolete.

---

## Prompt 6.1 — Rewrite `portfolio_manager_user_docs.html` to Version 3.0

### Context

The current HTML is versioned 2.0 (Phase 2 Pivot) with incremental additions for Phase 3 (Tax), Phase 4 (Export Engine), and Phase 5 (Decision Review). The incremental approach means the document has layered tone, dated phrasing, and no single place that describes the full system as it exists today.

Rewrite from scratch into Version 3.0 as a single authoritative user manual.

### Task

1. **Read first:** the current `portfolio_manager_user_docs.html`, all phase completion gates in `phase1_prompts.md` through `phase5_prompts.md`.

2. Structure Version 3.0 into exactly these sections, in this order:

   ```
   1. What This System Is (and What It Isn't)
      - One paragraph positioning
      - Explicit non-goals: not a robo-advisor, not an auto-trader, not a backtest

   2. The Operating Philosophy
      - APIs calculate locally, LLMs reason externally
      - Rotation is the unit of analysis
      - Small-step scaling, not binary entries/exits
      - Sheets as authoritative frontend

   3. Architecture at a Glance
      - One diagram: Schwab API → Bundles → Sheets → (dashboard scan or export package)
      - No more than 8 boxes and 10 arrows — if you need more, you're over-explaining

   4. The Weekly Cycle (5 minutes)
      - health / snapshot / sync transactions / dashboard refresh
      - What to scan in the sheet

   5. The Weekly Deep Dive (when something flags)
      - export deep-dive / export rotation
      - How to paste to Claude, Gemini, or Perplexity

   6. The Monthly Retrospective
      - export rotation-retrospective
      - What to look for

   7. The Sheet: Tab by Tab
      - One paragraph per tab with a purpose + "when to look here"
      - Tabs: Holdings_Current, Holdings_History, Daily_Snapshots, Transactions,
        Target_Allocation, AI_Suggested_Allocation, Risk_Metrics, Income_Tracking,
        RealizedGL, Valuation_Card, Decision_View, Tax_Control, Trade_Log,
        Trade_Log_Staging, Rotation_Review, Config, Disagreements, Logs
      - Clearly mark which are auto-populated vs manual-only vs read-only

   8. CLI Command Reference
      - Every command that matters in production use
      - Grouped by purpose: daily, weekly, export, maintenance
      - Each with: syntax, default behavior, --live semantics, common flags

   9. The Export Engine — LLM Reasoning Workflow
      - The scenario catalog (from Phase 4.6)
      - Which LLM for which scenario
      - How to read prompt.md and context.json
      - How to feed results back manually (if at all)

   10. Tax Visibility (CPA's corner)
      - Reading Tax_Control
      - What the estimated tax number does and doesn't include
      - Wash-sale mechanics in the system

   11. When Things Go Wrong
      - Schwab token expired → what to do
      - Sheet quota error → what to do
      - FMP 429 → what to do
      - Bundle hash mismatch → what to do
      - Duplicate transactions → what to do (reconcile mode)

   12. Maintenance Cadence
      - Saturday: thesis file updates, vault snapshot, bundle composite
      - Monthly: rotation retrospective
      - Quarterly: review styles.json for drift, check framework_routing.json
      - Annually: archive old Holdings_History, Tax_Control year rollover

   13. What's Deliberately Not Here
      - Auto-trading (never)
      - Auto-suggestion of rotations (never)
      - Automated fine-tuning of styles.json (manual, Saturday cadence)
      - A web UI (explicitly rejected; Sheets is the UI)
   ```

3. Tone rules:
   - **Direct and specific.** No "the system leverages" / "cutting-edge" / any marketing language.
   - **Assume the reader is Bill** (or a CPA colleague of Bill's). Don't over-explain basic investing concepts. Do explain anything system-specific.
   - **Screenshots or nothing.** If a section would be clearer with a screenshot of the Sheet or CLI output, include one. If not, don't fake it with ASCII art.
   - **No tables of contents longer than the sections themselves.**
   - **No emoji.** Functional document, not a pitch deck.

4. Version footer: "Version 3.0 — Consolidated after Phase 5. Supersedes all prior incremental versions."

5. Keep the same file path (`portfolio_manager_user_docs.html`). The old incremental content goes to `docs/archive/user_docs_v2_*.html` for reference.

### Constraints

- **Consolidation, not embellishment.** If something wasn't true or useful in the incremental docs, don't elevate it.
- **No new features described.** Phase 6 doesn't add features. If the docs need a feature to tell a clean story, that's a signal for Phase 7+, not a reason to scope-creep.
- **Screenshots are optional but preferred** for the Sheet tab descriptions and the export workflow.

### Gate criteria

- [ ] Version 3.0 HTML exists, replaces the prior file at the same path
- [ ] All 13 sections present, in order, with real content (no placeholders)
- [ ] Previous incremental versions archived to `docs/archive/`
- [ ] Read through start to finish — no contradictions, no "to be written" notes
- [ ] Fresh observer test: someone who hasn't seen the project can follow the weekly workflow from the docs alone
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 6.1: User docs Version 3.0 — full consolidation`

### What NOT to do

- Do not describe future phases or unimplemented features
- Do not use the word "leverage" as a verb
- Do not apologize for the tool's limits — just describe them

---

## Prompt 6.2 — Rewrite `CLAUDE.md` for post-pivot reality

### Context

`CLAUDE.md` is the conventions file that Claude Code, Gemini CLI, and future agents (if any) read to understand how to behave in this codebase. It's also the truth-in-advertising document for the project's philosophy.

The version in the project description is lengthy and has architectural decisions that are now settled rather than pending. Trim it to current reality.

### Task

1. **Read first:** The current `CLAUDE.md` (likely in the project root).

2. Rewrite to these sections:

   ```
   # CLAUDE.md — Investment Portfolio Manager

   ## What this project is
   A headless Python CLI portfolio operating system with Google Sheets as the
   authoritative frontend. APIs compute; Sheets persist; LLMs reason externally.

   ## What this project is not
   - Not an auto-trader
   - Not a backtest framework
   - Not a robo-advisor
   - Not a web app

   ## Core invariants (non-negotiable)
   - Read-only with respect to Schwab. No order endpoints imported or called.
   - DRY_RUN default true. Writes require explicit --live.
   - Bundle-first: deterministic data freezes to a hashed JSON before any reasoning.
   - Sheets is the authoritative frontend. Any other UI is an optional read-only consumer.
   - No automated LLM calls against production tabs. AI writes to sandbox or export packages only.
   - No emojis in code, logs, or docs unless the user explicitly requests them.

   ## Development conventions
   - Typer for the CLI.
   - Rich for terminal output.
   - Pydantic for schemas.
   - gspread for Sheets. Single-batch writes with fingerprint dedup.
   - Archive-before-overwrite standard for all pipeline writes.
   - Audit-before-build: read existing files via project_knowledge_search before generating new code.
   - One commit per Phase prompt. Scope discipline: no "while I'm here" additions.

   ## Data sources (priority order)
   1. Schwab Developer API (primary, read-only)
   2. Schwab CSV (fallback + realized G/L history)
   3. yFinance (prices, sector, beta, dividend yield)
   4. FMP (fundamentals — extend fmp_client.py before adding any new vendor)
   5. Finnhub (news)

   ## Tab authority
   - Target_Allocation: manual only; app reads but never writes
   - Config: manual only; app reads but never writes
   - AI_Suggested_Allocation: sandbox; AI writes, Bill promotes
   - Holdings_Current / Holdings_History / Daily_Snapshots / Transactions: pipeline writes
   - Valuation_Card / Decision_View / Tax_Control / Rotation_Review: computed views, clear-and-rebuild
   - Trade_Log / Trade_Log_Staging: rotation capture pipeline
   - RealizedGL: CSV ingestion, append with fingerprint dedup
   - Logs / Disagreements: append-only

   ## External LLM workflow
   - manager.py export produces packages for Claude, Gemini, Perplexity.
   - No auto-send. No auto-receive. Manual paste, manual review, optional manual journaling.

   ## If in doubt
   - Read PORTFOLIO_SHEET_SCHEMA.md.
   - Read portfolio_manager_user_docs.html.
   - Read the phase prompt files under docs/phase-prompts/.
   - Ask before changing architecture.
   ```

3. Remove all references to:
   - The 12-agent squad (decommissioned in Phase 0)
   - Streamlit Cloud deployment (rejected)
   - The old "nine-file agent kit" framing (superseded by export engine)
   - Any implementation details that are settled in code and don't need conventions enforcement

### Constraints

- **Keep it short.** The purpose of CLAUDE.md is to be read in full by any dev (human or AI) before making changes. If it exceeds ~200 lines, it's too long.
- **No historical archaeology.** The file reflects the current state, not how we got here. History lives in CHANGELOG.md.
- **Link, don't duplicate.** Detailed schemas go in PORTFOLIO_SHEET_SCHEMA.md. Architecture narrative goes in user_docs.html. CLAUDE.md points to both.

### Gate criteria

- [ ] CLAUDE.md rewritten, under ~200 lines
- [ ] No references to decommissioned features
- [ ] Claude Code and Gemini CLI can both read it and produce consistent behavior
- [ ] Archival: the old CLAUDE.md goes to `docs/archive/CLAUDE_md_pre_phase6.md` for reference
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 6.2: CLAUDE.md rewrite for post-pivot reality`

### What NOT to do

- Do not introduce new conventions that aren't already being followed
- Do not remove the "no emoji" rule
- Do not soften the "no auto-trading" invariant

---

## Prompt 6.3 — Consolidate `PORTFOLIO_SHEET_SCHEMA.md`

### Context

`PORTFOLIO_SHEET_SCHEMA.md` has accumulated tabs across phases. Some column definitions are now stale, some are marked "Phase 2" or "Phase 3" where the tab actually exists and is operational. Consolidate into a single current-truth document.

### Task

1. **Read first:** Current `PORTFOLIO_SHEET_SCHEMA.md`, all tabs actually present in the live sheet.

2. For each tab, produce a section with:
   - Tab name
   - Purpose (one sentence)
   - Authority (who writes: pipeline, manual, AI-sandbox, view-only)
   - Columns table (letter, header, type, example, notes)
   - Write pattern (clear-and-rebuild, append with dedup, manual)
   - Fingerprint format (if applicable)

3. Tabs to include (full current list):
   - Holdings_Current, Holdings_History, Daily_Snapshots, Transactions
   - Target_Allocation, AI_Suggested_Allocation
   - Risk_Metrics, Income_Tracking
   - RealizedGL
   - Valuation_Card, Decision_View
   - Tax_Control (Phase 3)
   - Trade_Log, Trade_Log_Staging
   - Rotation_Review (Phase 5)
   - Disagreements
   - Config, Logs

4. Remove "Phase N" tags where the tab is operational. Replace with a simple "Since Phase N" note at the bottom of the section for historical reference.

5. Add a new top-level section: **Tab Authority Matrix** — a single table showing which tabs are pipeline-written, manual-only, sandbox, view-only. This is the at-a-glance reference for anyone modifying the system.

6. The fingerprint formats section is retained and expanded to include Rotation_Review's fingerprint.

### Constraints

- **Column definitions must match the actual sheet.** Don't document what should be there; document what is there. If there's a mismatch, flag it and fix the sheet, not the doc.
- **Tab Authority Matrix is the most important addition.** It answers the question every new phase has to answer: "can I write to this tab?"

### Gate criteria

- [ ] All current tabs documented with accurate column definitions
- [ ] Tab Authority Matrix at the top
- [ ] No "Phase N" tags on operational tabs
- [ ] Fingerprint formats table current
- [ ] Cross-check every tab against the live sheet; fix any drift
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 6.3: PORTFOLIO_SHEET_SCHEMA.md consolidation`

### What NOT to do

- Do not add tabs that don't exist
- Do not remove tabs that do exist even if they look unused

---

## Prompt 6.4 — Project README, architecture notes, and archive cleanup

### Context

Two final pieces close out Phase 6: a project root `README.md` for 60-second orientation, and a small `docs/architecture/` directory that captures the handful of architectural decisions worth preserving as their own documents.

### Task

1. **Create or rewrite `README.md`** at the project root:

   ```markdown
   # Investment Portfolio Manager

   Headless Python CLI for managing a ~$550K Schwab portfolio through
   Google Sheets. APIs compute locally; LLMs reason externally via
   exportable context packages.

   ## 60-second quick start

       python manager.py health
       python manager.py snapshot --live
       python manager.py dashboard refresh --live

   Open the Google Sheet. Look at Decision_View, Valuation_Card, Tax_Control.

   For deep analysis on anything that flags:

       python manager.py export deep-dive <TICKER> --question "..."

   Paste the generated `prompt.md` + attach the `theses/` folder to
   Claude, Gemini, or Perplexity.

   ## Documentation

   - [User manual](portfolio_manager_user_docs.html) — full workflow
   - [Sheet schema](PORTFOLIO_SHEET_SCHEMA.md) — cell-level truth
   - [Conventions](CLAUDE.md) — for future devs
   - [Changelog](CHANGELOG.md) — phase-by-phase history
   - [Architecture notes](docs/architecture/) — the "why" behind the "what"

   ## Non-goals

   Not a robo-advisor. Not an auto-trader. Not a backtest. Not a web app.
   ```

2. **Create `docs/architecture/`** with 3–5 focused notes (one page each):
   - `01_bundle_first_reasoning.md` — why every decision traces to a hashed bundle
   - `02_sheets_as_authoritative_frontend.md` — why Sheets beat Streamlit for this use case
   - `03_external_llm_reasoning.md` — why the agent squad was decommissioned in favor of export packages
   - `04_rotation_as_unit_of_analysis.md` — the investment philosophy encoded in the data model
   - `05_tax_visibility_as_first_class.md` — why Tax_Control deserves its own tab, not agent narrative

   Each note: 1–2 screens of text, motivating question at top, decision/answer at bottom, "alternatives considered and why they lost" in the middle.

3. **Archive cleanup.** Move to `docs/archive/`:
   - All previously consolidated `*_prompts.md` files (phase1 through phase5). They served their purpose; the current state is in the code and the current docs.
   - Old `portfolio_manager_user_docs_v2_*.html` versions
   - Old `CLAUDE.md` pre-Phase 6
   - Any `deprecated/` directory contents that aren't already there

4. **`docs/phase-prompts/` directory** (or similar): keep the current Phase 6 prompt file (this one), Phase 2, 3, 4, 5 prompts for forward-reference. Future phases land here.

5. **Add a `.gitkeep` or short `README.md` in `docs/` and subdirectories** so the structure is self-documenting.

### Constraints

- **README.md is a front door, not a manual.** 60-second orientation. Anything longer belongs in the user docs.
- **Architecture notes are opinionated.** Each one should have a clear "here's what we chose and why" — not a survey of options.
- **No orphan files.** Every file in the repo should be either (a) active code, (b) active docs, (c) archived with a clear archive location, or (d) a test.

### Gate criteria

- [ ] Project root has a clean `README.md` with a working quick-start
- [ ] `docs/architecture/` has 3–5 focused notes, each readable in under 2 minutes
- [ ] `docs/archive/` contains the superseded incremental docs and phase prompts
- [ ] `docs/phase-prompts/` contains the current-generation phase prompt files for future reference
- [ ] No orphan files at the project root beyond the expected ones (README, CLAUDE.md, CHANGELOG.md, requirements.txt, pyproject or setup, .gitignore, main entry points)
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 6.4: README, architecture notes, archive cleanup`

### What NOT to do

- Do not add marketing language to the README
- Do not write architecture notes for decisions that aren't settled — those belong in active design discussion, not archive-worthy notes
- Do not delete old content; archive it

---

## Phase 6 Completion Gate

Phase 6 is complete when all four prompts have been executed, gated, and committed, **and** the following test passes:

```bash
# The "fresh colleague" test
# Someone who has never seen this project is given 20 minutes and the URL
# to the repo. They should be able to:
# 1. Read README.md and understand what this is
# 2. Read portfolio_manager_user_docs.html and understand the weekly workflow
# 3. Read PORTFOLIO_SHEET_SCHEMA.md and understand the tab structure
# 4. Explain back, in their own words, what "APIs compute, LLMs reason externally" means
# 5. Find where to look for a specific tab's column definitions in under 30 seconds
```

All of the following must be true:

- [ ] User docs at Version 3.0, fully consolidated
- [ ] CLAUDE.md under ~200 lines, current-state only
- [ ] PORTFOLIO_SHEET_SCHEMA.md has Tab Authority Matrix + current columns
- [ ] Project root README.md provides 60-second orientation
- [ ] docs/architecture/ has focused decision records
- [ ] docs/archive/ contains all superseded materials
- [ ] `CHANGELOG.md` has four Phase 6 entries
- [ ] Fresh observer can orient in 20 minutes

---

## Notes for Bill

- **This phase looks small but it's not.** Consolidation is where tools become systems. The difference between a project that's "mine because I built it" and one that's "mine because I understand it" is good documentation.
- **The fresh-colleague test is the real gate.** If you have a CPA friend or a tech-savvy partner, actually hand them the docs and watch them read. Every stumble is a fix.
- **After Phase 6, there's no canonical Phase 7.** The system is complete. New work is either bug fixes, incremental improvements to existing tabs/exports, or new phase ideas you'll scope when they emerge. The system should now sustain itself with ~1 hour/week of care.
- **Some ideas for post-Phase-6 work** (explicitly deferred, for your future consideration):
  - Looker Studio dashboard on top of Sheets (if you want a different visual surface)
  - Options overlay scenario in the export engine (covered calls, cash-secured puts)
  - Unified net-worth view across RE Property Manager and this project
  - Fine-tuning an open-weight model on your decision journal (research phase)
