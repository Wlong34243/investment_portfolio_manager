# CLAUDE.md — Project Conventions

This file tells Claude (and Claude Code, and Gemini CLI) how to work in this repo. Keep it tight.

For current build state, read `state.md` (lowercase — the file is `state.md`, not `STATE.md`).

**Last verified against the code: 2026-08-01.** Facts marked *(verified)* were checked against source on that date. If you are reading this much later, re-verify before trusting the numbers.

---

## What This Project Is

A headless Python CLI portfolio operating system for Bill's primary Schwab investment account. Google Sheets is the authoritative user-facing surface and system of record.

**Scale (verified 2026-08-01, bundle `2026-07-31T12:23:13Z`):** ~$596K, **35 positions**, 35 active thesis files in `vault/theses/` (38 archived). Do not cite "~$550K / 50+ positions" — that is a March 2026 figure and has been wrong since.

This is the liquid-investments companion to the RE Property Manager. They share a GCP service account but no code.

---

## Core Architecture Principle

**CLI owns execution. Sheets owns persistence. Visual layer is read-only and replaceable.**

Python gathers and calculates everything deterministically. LLMs reason over immutable, hash-fingerprinted context bundles and write only to sandbox surfaces. Manual promotion is the only path from suggestion to authoritative state.

The product should feel like a portfolio control system, not an agent showcase. AI is optional, sandboxed, and subordinate to the deterministic data model.

---

## Hard Rules (Non-Negotiable)

1. **Read-only on brokerage.** No order/trading endpoints imported or called, ever.
2. **Agents never browse or fetch.** Python gathers; LLMs reason.
3. **Every write requires an explicit `--live` flag.** Each command enforces dry-run-by-default independently via its own flag — that is the real mechanism and it works.
   ⚠️ **`config.DRY_RUN` does NOT default to true.** `config.py:505` reads `os.getenv("DRY_RUN", "False")`, so an unset env var yields `False` *(verified 2026-08-01)*. Currently harmless because the constant is dead in the active path — only `archive/streamlit_legacy/` and the `pipeline.py` shim read it — but do not cite `config.DRY_RUN` as a safety guarantee and do not make a command depend on it. See `state.md` Known Issues.
4. **No price targets, no market predictions, no buy/sell recommendations** in any agent output.
5. **All AI output is sandboxed.** Writes go to `Agent_Outputs`, `AI_Suggested_Allocation`, or local markdown under `agent_outputs/`. `Target_Allocation` is manual-only.
6. **Single-batch gspread writes with fingerprint dedup.** Never cell-by-cell.
7. **Archive-before-overwrite** on all pipeline writes.
8. **Bundle immutability.** Bundles are SHA-256 hashed at creation. Any mutation requires explicit rehash. `composite_hash` stamps every agent response.

---

## Analysis Rules (how any LLM must read Bill's data)

These live in `PROMPT_PAYLOAD` inside `tasks/export_ai_briefing.py` and are enforced on the briefing. Restated here because they are the most behaviorally consequential rules in the system and were previously invisible to anyone reading only this file. **`export_ai_briefing.py` is authoritative; this is a summary.**

### The governing principle

**Bill is the authoritative source on Bill's decisions. The vault and the log are lagging records of those decisions, not evidence against them.** Where files and observed trades disagree, the default inference is "the file is stale," NOT "the behavior is incoherent." Report the gap as a documentation task naming the file and section to update.

### The eight rules, condensed

1. **Never infer liquidity posture from the export.** `CASH_MANUAL` does not represent the cash position; cash sits outside what the bundle captures. Do not compute a cash percentage or draw conclusions about dry powder. Ask instead.
2. **Do not relitigate the role of an established position.** Where a thesis states a role, describe drift *within* that role. Explaining an instrument's mechanics back to a CPA/CISA who selected it deliberately is noise.
3. **Style size ceilings apply only to SECTOR_ETF, GARP, THEME and FUND — never to ballast/core.** JEPI, JPIE, VTI, COWZ and VEA are ballast and have no meaningful ceiling; suppress BREACH flags on those tickers. See the taxonomy note under Investment Style Context.
4. **Check for an offsetting leg before calling anything drift.** Scan every other position's transaction log for buys of comparable size within ±3 days. A sell funding a buy is a rotation and must be reported as one, with the substitution thesis named.
5. **A sale at a loss, or against the thesis's stated direction, is presumptively a conviction change** — not a data artifact or evidence of undisciplined trading. Correct output: "this trade implies the thesis changed; the file still says X."
6. **Do not moralize about process.** Deliver the finding, name the file to update, stop. Candor is wanted on *analysis* — a theme, an omitted risk, an unpriced tax consequence — not on Bill's adherence to his own conventions.
7. **Separate tax facts from behavioral narrative.** Wash-sale windows, disallowed losses and unrealized G/L are objective and always in scope, stated without judgment about the trade that created them.
8. **Rank flags by whether Bill can act on them.** Export-time flags reflecting a taxonomy gap, a stale file, or missing data are SYSTEM findings — group them separately, never lead with one, never build a recommendation on one.

---

## Development Philosophy

**Fire-fire-aim, not NASA.** Ship minimum viable agents, learn from real output, iterate.

- Bundle layer keeps the discipline (hashing, immutability, Pydantic schemas)
- Agents on top are cheap to try and cheap to throw away
- Do NOT over-spec scoring rubrics, diversity metrics, or upside estimates before seeing actual agent output
- When the user is in planning/architecture mode, avoid defaulting to implementation-stage caution about complexity

---

## Working Patterns

### Prompt-file-driven development
Implementation work is codified as sequenced markdown prompt files in `prompts/` for handoff to Claude Code or Gemini CLI. The Chief Architect role (Claude in chat) produces prompts; Claude Code or Gemini CLI executes them locally.

### Audit-before-build
Read existing files before generating new prompts. Never assume infrastructure exists based on filenames or project memory — verify.

### Step 0 verification gate
Every prompt file starts with a Step 0 that confirms actual file state before writing any code. If Step 0 finds a discrepancy, STOP and report rather than adapting silently.

### DRY RUN → verify → flip `--live`
Standard promotion sequence. Always.

### Gemini peer review
Major build sequences should include a `GEMINI_REVIEW_REQUEST.md` checkpoint to pressure-test design decisions through Gemini CLI separately.

### Post-build verification checklists
Major prompt files end with a verification checklist. The build isn't done until the checklist passes. Demand literal stdout/stderr — do not accept an agent-reported "PASS" table.

### Extend, don't proliferate
Default is to extend `CLAUDE.md`, `state.md`, `PORTFOLIO_SHEET_SCHEMA.md`, `CHANGELOG.md` — not to create parallel documentation.

---

## Bundle Architecture

Three bundles, each SHA-256 hashed using canonical JSON serialization *(all verified present 2026-08-01)*:

- **Market bundle** (`core/bundle.py`) — positions, prices, cash, realized G/L, target allocation snapshot
- **Vault bundle** (`core/vault_bundle.py`) — thesis files, transcripts, research, styles.json
- **Composite bundle** (`core/composite_bundle.py`) — thin wrapper linking both component bundles + Tier 2 data (recent rotations from `Trade_Log`)

Agents interact strictly with the composite hash via `ask_gemini_composite()`.

---

## Key Files

*All paths verified present 2026-08-01.*

### Spine
| Path | Purpose |
|---|---|
| `manager.py` | CLI spine (Typer). Entry point for everything. |
| `config.py` | Constants: `PORTFOLIO_SHEET_ID`, `GEMINI_MODEL` (=`gemini-2.5-pro`), tax rates, `GCP_PROJECT_ID`, 20 `TAB_*` names, `PURGE_DEFAULT_DAYS_PODCASTS` (=30) |
| `state.md` | Current build state — **read first** |
| `PORTFOLIO_SHEET_SCHEMA.md` | Sheet tab definitions — **incomplete, see Known Doc Gaps** |
| `CHANGELOG.md` | Dated change history |
| `pipeline.py` | Migration compatibility shim only; Streamlit code archived to `archive/streamlit_legacy/`. New work goes to `manager.py`. |

### Bundles
| Path | Purpose |
|---|---|
| `core/bundle.py` | Market bundle assembly + hashing |
| `core/vault_bundle.py` | Vault bundle assembly |
| `core/composite_bundle.py` | Composite bundle assembly |
| `core/thesis_sync_data.py` | Sheet → thesis frontmatter sync data |

### Morning pipeline (`manager.py morning`, STEP 0–11)
| Path | Purpose |
|---|---|
| `tasks/health.py` | Health checks; owns the `logs/HEALTH_FAILURE.flag` sentinel that `morning`, `build_command_center.py` and `export_ai_briefing.py` all read to disclose degraded state instead of going silently stale |
| `tasks/sync_transactions.py` | Schwab transaction/position sync |
| `tasks/batch_podcast_sync.py` | STEP 4 — per-channel RSS → transcript → Gemini summary |
| `tasks/build_command_center.py` | STEP 5 — dashboard rebuild from bundle |
| `tasks/write_thesis_updates.py` | STEP 6 — Sheets → local thesis files |
| `tasks/export_ai_briefing.py` | STEP 9 — assembles `prompt.md`/`portfolio.md`/`podcasts.md`/`theses.md`/`SUBMIT_ME.md`. **Owns the analysis rules above.** |
| `tasks/derive_rotations.py` | STEP 10 — clusters sell/buy pairs into candidate rotations, writes to `Trade_Log_Staging` for manual promotion |
| `tasks/dislocation_scan.py` | STEP 11 |

### Ingestion & enrichment
| Path | Purpose |
|---|---|
| `utils/schwab_client.py` | Schwab API client (read-only) |
| `utils/schwab_token_store.py` | GCS-backed token lifecycle |
| `utils/csv_parser.py` | Schwab CSV fallback parser |
| `utils/gl_parser.py` | Realized G/L parsing |
| `utils/fmp_client.py` | FMP fundamentals — **extend this before adding any new vendor** |
| `utils/finnhub_client.py` | News |
| `utils/etf_holdings.py` | ETF look-through (yfinance, disk-cached); top-10 only, so every figure is a floor |
| `tasks/enrich_*.py` | ATR, FMP, fundamentals, styles, technicals |

### Agents & analysis
| Path | Purpose |
|---|---|
| `utils/gemini_client.py` | `ask_gemini()`, `ask_gemini_composite()`, `SAFETY_PREAMBLE` (auto-prepended — never duplicate it in a prompt file) |
| `utils/agents/idea_generator.py` | Idea Generator agent (v1, shipped May 2026) |
| `utils/agents/podcast_analyst.py` | Gemini allocation extractor; Pydantic `SectorTarget`/`PodcastStrategy`. Branches on source type (`is_stax`). |
| `prompts/` | 7 prompt files incl. `idea_generator.md` and dated build prompts |
| `agent_outputs/` | `ideas/`, `dislocation_scan/`, `ai_briefing_analysis/` |

### Support
| Path | Purpose |
|---|---|
| `utils/sheet_readers.py` / `sheet_writers.py` | Sheets I/O; three-way credential chain (ADC → Streamlit secrets → local file) |
| `utils/level_coverage.py` | Thesis frontmatter Trim/Add + `last_reviewed` coverage gaps; filesystem only |
| `utils/hygiene.py` | `purge_obsolete_data()` |
| `utils/risk.py`, `utils/tax.py`, `utils/technicals.py`, `utils/validators.py`, `utils/column_guard.py` | Calculation and guard layers |
| `tasks/lint_theses.py` | Read-only vault linter (stale weight claims, `[BILL]` placeholders, stale reviews) |

---

## Agent Output Conventions

### Local markdown (v1 default for new agents)
Agents write to `agent_outputs/{agent_name}/` as `{agent_name}_{YYYY-MM-DD}_{hash_prefix}.md`.

Rationale: fast iteration. Promote to Sheets tabs once output format stabilizes.

### Sheets sandbox (when promoted)
- `AI_Suggested_Allocation` — allocation suggestions only
- `Agent_Outputs` — general agent outputs
- `Agent_Outputs_Archive` — historical, append-only

Never write directly to `Target_Allocation`. That's Bill's manual-only authoritative surface.

---

## Podcast & Third-Party Source Ingestion

Two distinct paths. Do not merge them.

**Path 1 — YouTube transcripts (automated).** `tasks/batch_podcast_sync.py` runs as STEP 4: RSS → `youtube-transcript-api` → `podcast_analyst.analyze_podcast()` → per-episode summary in `data/podcast_summaries/`.

**Path 2 — third-party aggregate digests (currently manual).** Standing decision, 2026-07-26: the Spotify aggregate is ingested **as a single first-class source in its own voice**, NOT decomposed into constituent episodes and NOT re-summarized. Rationale on record — decomposition made one digest appear as three agreeing sources during theme extraction and discarded the aggregate's own synthesis.

Aggregate files carry a mandatory `PROVENANCE` stamp and an independent `VERIFICATION` footer. Verification requires web search and the current position set, so it stays manual (hard rule 2 forbids agents fetching). Automation of the ingest half is specced in `prompts/spotify_digest_ingestion_2026-08-01.md` — not yet built.

**Known corpus risk:** an aggregate discusses episodes that are *also* independently ingested in the same window, so a theme can be double-counted — once as its source episode, once as the aggregate's commentary on it. Mitigation is a `## Cited Episodes` cross-reference plus a counting rule; see the prompt file.

---

## Investment Style Context

Four styles, codified in `data/styles.json` *(verified 2026-08-01)*:

| Key | Name | Ceiling |
|---|---|---|
| `GARP` | GARP-by-intuition — undervalued companies whose products Bill understands | 9.0% |
| `THEME` | Thematic Specialists — buying market position over company quality | 3.0% |
| `FUND` | Boring Fundamentals — durable businesses on fear-driven discounts | 5.0% |
| `ETF` | Sector/Thematic ETFs — macro expressions, index and bond ETFs as ballast | 8.0% |

**⚠️ Known taxonomy bug.** The `ETF` key covers two different things: ballast/core (JEPI, JPIE, VTI, COWZ, VEA) and sector/thematic (XBI, KRE, XLF, IFRA, EWZ, EMXC, BBJP, GLD). The 8% ceiling is meaningful only for the second group, so ballast positions surface as false BREACH flags. The exemption currently lives **only** in analysis rule 3 above and in `export_ai_briefing.py` — `styles.json` does not encode it.

The fix logged in `state.md` (split into `BALLAST_CORE` and `SECTOR_ETF`) is **insufficient**: it would put JEPI, JPIE, VTI, COWZ and VEA in one bucket and recreate the problem one level down. JEPI and JPIE are risk-managed income — roughly 0.5 beta, high distribution, dampened drawdowns — which is not plain index beta. **Three buckets are needed:** income-with-downside-management (JEPI, JPIE), plain beta ballast (VTI, VEA, COWZ), and sector/thematic (the rest).

Risk management is small-step scaling in and out, not binary entries/exits. The rotation — a linked sell-buy pair with an implicit substitution thesis — is the unit of analysis, captured in `Trade_Log`. Bill carries strategic cash as intentional dry powder. He knows the thesis behind every position; thesis files anchor drift control, not discovery.

---

## Known Doc Gaps

Recorded so they are not rediscovered. Fix or delete; do not let them rot silently.

- **`PORTFOLIO_SHEET_SCHEMA.md` is materially incomplete** (last touched 2026-05-07). It documents 10 tabs; `config.py` defines 20. Undocumented: `AI_Suggested_Allocation`, `Agent_Outputs`, `Agent_Outputs_Archive`, `Daily_Snapshots`, `Decision_Log`, `Disagreements`, `Holdings_History`, `Income_Tracking`, `Logs`, `Realized_GL`, `Risk_Metrics`. This file is cited as authoritative — it is not currently.
- **Tab naming inconsistency:** `config.py` uses `Realized_GL`; some external docs say `RealizedGL`. `config.py` wins.
- **`state.md` vs `STATE.md`:** the file is `state.md`. Any reference to `STATE.md` works on Windows and breaks on case-sensitive filesystems, including CI and Linux tooling.
- **Root has ~19 loose markdown files**, several one-off fix notes (`EXPORTER_FIX_2026-07-26.md`, `THESIS_SYNC_FIX_2026-07-26.md`, `UI_IMPROVEMENT_*.md`, `OBSOLETE_FILES_TO_ARCHIVE.md`). These should fold into `CHANGELOG.md` or move to `docs/archive/`.

---

## What NOT to Do

- Do not write to `Target_Allocation` from any agent
- Do not call any Schwab order/trading endpoint
- Do not add new vendors before extending `utils/fmp_client.py`
- Do not duplicate the `SAFETY_PREAMBLE` in agent prompts — `ask_gemini()` auto-prepends it
- Do not cite `config.DRY_RUN` as a safety guarantee (see hard rule 3)
- Do not refactor `core/bundle.py` while building new agents on top of it
- Do not over-spec agents before seeing real output
- Do not assume project memory or documentation reflects current code state — verify
- Do not deploy to Streamlit Cloud
- Do not propose MCP integrations
- Do not propose auto-trading features
- Do not add unrequested scope. Deliver exactly what was asked.
