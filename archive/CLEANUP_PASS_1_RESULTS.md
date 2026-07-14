# Cleanup Pass 1 Results — 2026-05-27

## Commits Made

1. `378a51e` cleanup: remove orphaned config constants for dropped agents
2. `ed8fbbb` cleanup: archive pre-reframe planning docs to docs/archive/pre-reframe/

(Two commits instead of three — see "Audit Overcalls" section below.)

---

## Files Deleted / Changed

### config.py — 21 lines removed

Constants deleted (zero active-code usage confirmed via grep):

| Constant | Reason |
|---|---|
| `GEMINI_MAX_TOKENS_VALUATION` | Only referenced in `docs/archive/deprecated/agents/` |
| `GEMINI_MAX_TOKENS_CONCENTRATION` | Only referenced in `docs/archive/deprecated/agents/` |
| `GEMINI_MAX_TOKENS_MACRO` | Only referenced in `docs/archive/deprecated/agents/` |
| `GEMINI_MAX_TOKENS_REBUY` | Zero references anywhere |
| `GEMINI_MAX_TOKENS_BAGGER` | Zero references anywhere |
| `GEMINI_MAX_TOKENS_THESIS` | Zero references anywhere |
| `ADD_CANDIDATE_STYLE_PCT` | Zero references anywhere |
| `ADD_CANDIDATE_MAX_STARTER_PCT` | Zero references anywhere |
| `ADD_CANDIDATE_MAX_CANDIDATES` | Zero references anywhere |
| `ADD_CANDIDATE_STALE_THRESHOLD_DAYS` | Zero references anywhere |
| `NEW_IDEA_MAX_CANDIDATES_PER_RUN` | Zero references anywhere |
| `NEW_IDEA_STARTER_SIZE_PCT` | Zero references anywhere |
| `NEW_IDEA_MAX_STARTER_PCT` | Zero references anywhere |

Kept: `GEMINI_MAX_TOKENS_PODCAST` — actively used by `utils/agents/podcast_analyst.py` line 86.

### Files Archived

| Original Path | New Path | Notes |
|---|---|---|
| `BUNDLE_AND_AGENT_AUDIT.md` | `docs/archive/pre-reframe/BUNDLE_AND_AGENT_AUDIT.md` | Archival header prepended |

---

## Audit Overcalls — What the Audit Got Wrong

The REPO_AUDIT_2026-05-26.md flagged three cleanup targets that turned out to be wrong:

### 1. "Dropped agent files to delete" — files don't exist
The audit named `rebuy_analyst.py`, `add_candidate.py`, `new_idea_screener.py`, `coherence_checker.py` as targets for deletion. None of these files ever existed. The nine-file kit was planned but never built. Nothing to delete.

### 2. "podcast_analyst.py — not imported anywhere active"
**Wrong.** Three active imports found:
- `manager.py` line 1012 (inside `podcast_batch --analyze` branch)
- `tasks/stax_sync.py` line 33
- `tasks/weekly_podcast_sync.py` line 69

`podcast_analyst.py` remains in place.

### 3. "pipeline.py — zero active imports"
**Wrong.** Seven active imports found:
- `manager.py` lines 630, 695
- `scripts/live_update.py` line 13
- `scripts/schwab_test_fetch_write.py` line 17
- `tasks/sync_transactions.py` line 20
- `tests/test_transaction_pandas_bug.py` lines 98, 133
- `utils/risk.py` line 320

`pipeline.py` cannot be deleted without a migration pass. Flagged as future work.

---

## Verification

- [x] `python manager.py --help` succeeds
- [x] `python manager.py agent ideas --dry-run` finds 3 transcripts, runs to LLM call
- [x] No broken imports — `python -c "import config"` and `python -c "import manager"` both clean
- [x] Git status clean after both commits

---

## Stale Root-Level Docs — Flagged, Not Acted On

The following files exist at repo root and appear to be stale planning prompts. Per the cleanup prompt rules, only `BUNDLE_AND_AGENT_AUDIT.md` was acted on without further authorization. These are flagged here for the next cleanup decision:

| File | Contents | Recommendation |
|---|---|---|
| `build_command_center_prompts.md` | Build prompts for 0_DASHBOARD (already shipped) | ARCHIVE to `docs/archive/pre-reframe/` |
| `gemini_cli_simplification_prompt.md` | Gemini CLI handoff for CLI audit | ARCHIVE |
| `cli_audit.md` | Pre-reframe CLI audit findings | ARCHIVE |
| `cli_proposal.md` | CLI v3.2 proposal (pre-reframe) | ARCHIVE |
| `phase5_test_suite.md` | Phase 5 test plan | ARCHIVE |
| `phase6_prompts.md` | Phase 6 build prompts | ARCHIVE |
| `sheets_dashboard_v2_prompt.md` | Dashboard v2 build prompt (shipped) | ARCHIVE |
| `sheets_ui_formatting_prompt.md` | Formatting prompt (shipped) | ARCHIVE |
| `TASK_thesis_sync.md.md` | Task file with double `.md` extension | INVESTIGATE + fix extension |
| `gemini.md` | Unknown — not inspected | INVESTIGATE |
| `CODEBASE_INVENTORY.md` | Inventory — may still be current | INVESTIGATE |
| `IDEA_GENERATOR_V1_RESULTS.md` | Current — v1 verification results | KEEP at root |
| `lessonsLearned.md` | Active lessons log | KEEP at root |
| `re_portfolio_math.md` | RE portfolio math reference | KEEP (cross-portfolio reference) |
| `Schwab API Integration.md` | Schwab API notes | INVESTIGATE |

---

## Active Issue: Gemini Model Access

`pm agent ideas --dry-run` runs (finds transcripts, routes to LLM) but returns "LLM call failed" with the current `gemini-3.5-flash` default. The successful run yesterday used `$env:GEMINI_MODEL=gemini-2.5-flash` override. This suggests `gemini-3.5-flash` may not be accessible via the ADC/Vertex AI path on project `re-property-manager-487122`. To fix: either set `GEMINI_API_KEY` in `.env` for the Developer API path (which tries first per current auth order), or revert `GEMINI_MODEL` to `gemini-2.5-flash`.

---

## Suggested Next Steps

**Next prompt (State/Doc Corrections):** Fix factual errors in STATE.md and CLAUDE.md per the audit findings:
1. Gemini model string: `gemini-3.5-flash` (not `gemini-3.0-flash`)
2. Auth order: API key primary, ADC fallback (reversed from STATE.md description)
3. FMP client path: `utils/fmp_client.py` (not bare `fmp_client.py`)
4. Command: `pm bundle verify` (not `pm bundle inspect`)
5. Remove `app.py` from CLAUDE.md key files table — file does not exist
6. Add `pm agent ideas` to CLI_CHEATSHEET.md

**Following prompt (Root Doc Cleanup):** Archive or delete the 8 stale planning-prompt `.md` files at repo root listed in the table above. Low-risk, text-only changes.

**Future prompt (pipeline.py retirement):** Migrate the 7 active `pipeline.py` imports to their proper homes before deleting. Moderate scope — needs a file-by-file dependency trace before execution.
