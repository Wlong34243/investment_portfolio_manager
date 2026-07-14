# Cleanup Pass 2 Results — 2026-05-27

## Commits Made

1. `f8f0fe0` cleanup: revert Gemini model to gemini-2.5-pro
2. `f7e373f` cleanup: archive 9 stale root planning docs to docs/archive/pre-reframe/
3. `9d54c2e` cleanup: update gemini.md + archive CODEBASE_INVENTORY and Schwab API Integration
4. `ecbe8cd` cleanup: fix factual errors in STATE.md and CLAUDE.md

---

## Commit 1 — Model Revert

### Files Changed
- `config.py` line 69: `gemini-3.5-flash` → `gemini-2.5-pro`
- `utils/gemini_client.py` line 96 fallback: `gemini-3.1-pro-preview-customtools` → `gemini-2.5-pro`
- `utils/gemini_client.py` docstring comment updated (referenced gemini-3.5-flash)

### Note on `.env`
`.env` also had `GEMINI_MODEL="gemini-3.5-flash"` which overrides `config.py`. Updated to `gemini-2.5-pro`.
`.env` is gitignored — this change is not in the commit but is required for the fix to take effect.

### Note on GEMINI_API_KEY
`.env` has a `GEMINI_API_KEY` value that returns 400 INVALID_ARGUMENT. When this key is present,
`gemini_client.py` uses it as Path 1 (Developer API) and never falls back to ADC/Vertex AI. The
`gemini-2.5-pro` model is accessible via ADC on `re-property-manager-487122` but NOT via the
invalid Developer API key. **To restore LLM function: either remove `GEMINI_API_KEY` from `.env`
or replace it with a valid AI Studio key.**

### Verification
`python manager.py agent ideas --dry-run` runs, finds 3 transcripts, reaches the LLM call, and
now shows `gemini-2.5-pro` in the error log. Code path is correct.

---

## Commit 2 — Root Doc Archive

### 9 Files Moved to `docs/archive/pre-reframe/`

| Original Path | Archive Path | What it was |
|---|---|---|
| `build_command_center_prompts.md` | `docs/archive/pre-reframe/build_command_center_prompts.md` | Build prompts for 0_DASHBOARD (shipped) |
| `gemini_cli_simplification_prompt.md` | `docs/archive/pre-reframe/gemini_cli_simplification_prompt.md` | Gemini CLI handoff for CLI audit (implemented) |
| `cli_audit.md` | `docs/archive/pre-reframe/cli_audit.md` | Pre-reframe CLI audit findings |
| `cli_proposal.md` | `docs/archive/pre-reframe/cli_proposal.md` | CLI v3.2 proposal (adopted) |
| `phase5_test_suite.md` | `docs/archive/pre-reframe/phase5_test_suite.md` | Phase 5 test plan (shipped) |
| `phase6_prompts.md` | `docs/archive/pre-reframe/phase6_prompts.md` | Phase 6 docs prompts (superseded) |
| `sheets_dashboard_v2_prompt.md` | `docs/archive/pre-reframe/sheets_dashboard_v2_prompt.md` | Dashboard v2 build prompt (shipped) |
| `sheets_ui_formatting_prompt.md` | `docs/archive/pre-reframe/sheets_ui_formatting_prompt.md` | Formatting prompt (shipped) |
| `TASK_thesis_sync.md.md` | `docs/archive/pre-reframe/TASK_thesis_sync.md` | Vault sync task plan (shipped) — also fixed double .md extension |

Archival HTML comment headers prepended to all 9 files.

---

## Commit 3 — INVESTIGATE Files Resolved

### `gemini.md` — Updated
User explicitly requested this update. Changes:
- Added `utils/agents/idea_generator.py` to Key Files with description
- Added `prompts/idea_generator.md` to Key Files with SAFETY_PREAMBLE note
- Added pipeline.py active-import count warning to prevent premature deletion

### `CODEBASE_INVENTORY.md` — Archived
Moved to `docs/archive/pre-reframe/CODEBASE_INVENTORY.md`. Reason: agents section listed
7 agents that were planned but never built (`valuation_agent.py`, `tax_agent.py`,
`macro_cycle_agent.py`, `concentration_hedger.py`, `thesis_screener.py`, `bagger_screener.py`,
`analyze_all.py`). Active at root, it would mislead any session reading it. Archival header added.

### `Schwab API Integration.md` — Archived
Moved to `docs/archive/pre-reframe/Schwab_API_Integration.md`. Reason: build prompt for Phase 5-S
(already shipped). References deprecated `secrets.toml` (Streamlit). Space removed from filename.

---

## Commit 4 — STATE.md / CLAUDE.md Corrections

### STATE.md Errors Fixed
| Error | Was | Now |
|---|---|---|
| Auth order | "ADC primary, API key fallback" | "API key primary (GEMINI_API_KEY env), ADC/Vertex AI fallback" |
| Gemini model | `gemini-3.0-flash` | `gemini-2.5-pro` |
| How to Resume step 2 | Read `BUNDLE_AND_AGENT_AUDIT.md` | Removed (file now archived) |
| How to Resume step 6 | `bundle inspect` | `bundle verify` |
| Last updated | 2026-05-26 | 2026-05-27 |

### CLAUDE.md Errors Fixed
| Error | Change |
|---|---|
| Intro referenced `BUNDLE_AND_AGENT_AUDIT.md` | Removed that line |
| Key Files table had `BUNDLE_AND_AGENT_AUDIT.md` row | Removed that row |
| `fmp_client.py` bare path | Fixed to `utils/fmp_client.py` |

### CLAUDE.md Already Correct
- `app.py` was already absent from the Key Files table (removed in a prior session)
- `utils/agents/idea_generator.py` and `prompts/idea_generator.md` were already in the table

### `prompts/idea_generator.md` — Verified Clean
No SAFETY_PREAMBLE duplication. The "Hard rules" section is investment-specific (no price targets,
no buy/sell) — distinct from the generic safety preamble, and appropriate to keep.

---

## Root Status After Pass 2

Files remaining at root that were flagged as KEEP in Pass 1:
- `IDEA_GENERATOR_V1_RESULTS.md` — KEEP (v1 verification results)
- `lessonsLearned.md` — KEEP (active lessons log)
- `re_portfolio_math.md` — KEEP (cross-portfolio RE reference)

Files remaining at root that were flagged for future work:
- `CLEANUP_PASS_1_RESULTS.md` — this session's pass 1 results doc
- `CLEANUP_PASS_2_RESULTS.md` — this file

---

## Open Issue: GEMINI_API_KEY Invalid

The `.env` `GEMINI_API_KEY` value returns 400 INVALID_ARGUMENT from the Google Developer API.
This blocks the ADC fallback path from being reached. To restore full LLM function:

**Option A (recommended):** Remove `GEMINI_API_KEY` from `.env`. The ADC path will take over
and `gemini-2.5-pro` is confirmed working on `re-property-manager-487122`.

**Option B:** Replace with a valid AI Studio key from https://aistudio.google.com/apikey.

---

## Suggested Next Steps

**Immediate:** Fix the GEMINI_API_KEY (see above) so `pm agent ideas` runs end-to-end.

**Next build:** Valuation Drift Monitor — see STATE.md for acceptance criteria.

**Future:** Migrate 7 active `pipeline.py` imports before retiring that file.
