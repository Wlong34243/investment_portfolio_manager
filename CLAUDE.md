# CLAUDE.md — Project Conventions

This file tells Claude (and Claude Code, and Gemini CLI) how to work in this repo. Keep it tight.

For current build state, read `STATE.md`.

---

## What This Project Is

A headless Python CLI portfolio operating system for Bill's primary Schwab investment account (~$550K, 50+ positions). Google Sheets is the authoritative user-facing surface and system of record.

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
3. **DRY_RUN defaults true.** Every write requires explicit `--live` flag.
4. **No price targets, no market predictions, no buy/sell recommendations** in any agent output.
5. **All AI output is sandboxed.** Writes go to `Agent_Outputs` tab, `AI_Suggested_Allocation` tab, or local markdown. `Target_Allocation` is manual-only.
6. **Single-batch gspread writes with fingerprint dedup.** Never cell-by-cell.
7. **Archive-before-overwrite** on all pipeline writes.
8. **Bundle immutability.** Bundles are SHA-256 hashed at creation. Any mutation requires explicit rehash. `composite_hash` stamps every agent response.

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
Implementation work is codified as sequenced markdown prompt files for handoff to Claude Code or Gemini CLI. The Chief Architect role (Claude in chat) produces prompts; Claude Code or Gemini CLI executes them locally.

### Audit-before-build
Read existing files before generating new prompts. Never assume infrastructure exists based on filenames or project memory — verify.

### DRY RUN → verify → flip `--live`
Standard promotion sequence. Always.

### Gemini peer review
Major build sequences should include a `GEMINI_REVIEW_REQUEST.md` checkpoint where the user can pressure-test design decisions through Gemini CLI separately.

### Post-build verification checklists
Major prompt files end with a verification checklist. The build isn't done until the checklist passes.

### Step 0 verification gate
Every prompt file starts with a Step 0 that confirms actual file state before writing any code.

---

## Bundle Architecture

Three bundles, each SHA-256 hashed using canonical JSON serialization:

- **Market bundle** (`core/bundle.py`) — positions, prices, cash, realized G/L, target allocation snapshot
- **Vault bundle** (`core/vault_bundle.py`) — thesis files, transcripts, research, styles.json
- **Composite bundle** (`core/composite_bundle.py`) — thin wrapper linking both component bundles + Tier 2 data (recent rotations from `Trade_Log`)

Agents interact strictly with the composite hash via `ask_gemini_composite()`.

---

## Key Files

| Path | Purpose |
|---|---|
| `manager.py` | CLI spine (Typer) |
| `config.py` | Constants: `PORTFOLIO_SHEET_ID`, `GEMINI_MODEL`, `DRY_RUN`, `GCP_PROJECT_ID`, tax rates |
| `core/bundle.py` | Market bundle assembly + hashing |
| `core/vault_bundle.py` | Vault bundle assembly |
| `core/composite_bundle.py` | Composite bundle assembly |
| `utils/gemini_client.py` | `ask_gemini()`, `ask_gemini_composite()`, `SAFETY_PREAMBLE` |
| `utils/sheet_readers.py` | Google Sheets reads with three-way credential chain (ADC → Streamlit secrets → local file) |
| `utils/csv_parser.py` | Schwab CSV fallback parser |
| `utils/schwab_client.py` | Schwab API client (read-only) |
| `utils/agents/idea_generator.py` | Idea Generator agent (v1 shipped May 2026) |
| `prompts/idea_generator.md` | Idea Generator system prompt |
| `pipeline.py` | Legacy orchestrator (shim only; new work goes to `manager.py`) |
| `STATE.md` | Current build state — read first |
| `PORTFOLIO_SHEET_SCHEMA.md` | Sheet tab definitions |

---

## Agent Output Conventions

### Local markdown (v1 default for new agents)
Agents write to `agent_outputs/{agent_name}/` as markdown files named `{agent_name}_{YYYY-MM-DD}_{hash_prefix}.md`.

Rationale: fast iteration. We promote to Sheets tabs once output format stabilizes.

### Sheets sandbox (when promoted)
- `AI_Suggested_Allocation` — allocation suggestions only
- `Agent_Outputs` — general agent outputs
- `Agent_Outputs_Archive` — historical agent outputs (append-only)

Never write directly to `Target_Allocation`. That's Bill's manual-only authoritative surface.

---

## Investment Style Context

Bill's portfolio approach spans four styles, codified in `data/styles.json`:

1. **GARP-by-intuition** — undervalued companies with strong product/market understanding
2. **Thematic Specialists** — buying market position over company quality
3. **Boring Fundamentals + dip-buying** — durable businesses, fear-driven discounts
4. **Sector/Thematic ETFs** — macro expressions with broad index and bond ETFs as ballast

Risk management is small-step scaling in and out, not binary entries/exits. The rotation (linked sell-buy pair with implicit substitution thesis) is the unit of analysis, captured in `Trade_Log`.

Bill carries strategic cash as intentional dry powder. He knows the thesis behind every current position. Thesis files anchor drift control, not discovery.

---

## What NOT to Do

- Do not write to `Target_Allocation` from any agent
- Do not call any Schwab order/trading endpoint
- Do not add new vendors before extending `utils/fmp_client.py`
- Do not duplicate the `SAFETY_PREAMBLE` in agent prompts — `ask_gemini()` auto-prepends it
- Do not refactor `core/bundle.py` while building new agents on top of it
- Do not over-spec agents before seeing real output
- Do not assume project memory or documentation reflects current code state — verify with `view`
- Do not deploy to Streamlit Cloud
- Do not propose MCP integrations
- Do not propose auto-trading features
