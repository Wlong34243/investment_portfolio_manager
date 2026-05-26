# Bundle & Agent Workflow Audit — May 26, 2026

## Executive Summary
- **Bundle Infrastructure is Robust:** The `core/bundle.py`, `vault_bundle.py`, and `composite_bundle.py` files successfully implement the immutable, content-hashed assembly required by the spec. Data is fetched, deterministically hashed via SHA-256 (canonical JSON), and written to disk in the `bundles/` directory.
- **Agent Invocation Path Exists:** `utils/gemini_client.py` contains `ask_gemini_composite()`, which enforces Pydantic schemas equipped with a `bundle_hash` field for end-to-end tracing. A global `SAFETY_PREAMBLE` is successfully applied to all calls.
- **Agent Layer is Missing:** Only legacy/stub agents (e.g., `podcast_analyst.py`) exist. The four primary analysts from the Nine-File Agent Kit (Re-buy, Add-Candidate, New Idea, List Coherence) are completely missing.
- **Recommended First Step:** Implement the **Re-buy Analyst** since the composite bundle already incorporates `recent_rotations` from the `Trade_Log` specifically for this agent's use case.

---

## Section 0: Verification Gate Results
- **`core/bundle.py`**: EXISTS_AND_WORKS (494 lines)
- **`utils/gemini_client.py`**: EXISTS_AND_WORKS (317 lines)
- **`manager.py`**: EXISTS_AND_WORKS (969 lines)
- **`pipeline.py`**: EXISTS_AND_WORKS (500 lines) - Note: serves as a legacy shim.
- **`config.py`**: EXISTS_AND_WORKS (476 lines)
- **`data/styles.json`**: EXISTS_AND_WORKS (18 lines) - 4 Canonical Styles found.
- **`_thesis.md`**: EXISTS_AND_WORKS - 62 matching files discovered in `vault/theses/`.
- **Agents directory**: EXISTS_STUB_ONLY - `utils/agents/podcast_analyst.py` is present; legacy agents found under `archive/legacy_agents/`.
- **`context_bundle_spec.md`**: EXISTS_STUB_ONLY - Found at `docs/archive/deprecated/agents/context_bundle_spec.md` (148 lines).
- **`buy_list_template.md`**: EXISTS_STUB_ONLY - Found at `docs/archive/deprecated/agents/buy_list_template.md` (103 lines).

---

## Section 1: Bundle Export Functions
The core logic resides in `core/bundle.py`, `core/vault_bundle.py`, and `core/composite_bundle.py`.

- **Market Bundle (`build_bundle`)**: 
  - *Data Sources*: Schwab API (`_build_from_schwab`), CSV fallback (`_build_from_csv`), yfinance (for zero-price fallback and CSV enrichment).
  - *Hashing*: Deterministic SHA-256 hash using `_sha256_canonical()` applied to an isolated `_hashable_payload()` view.
  - *Serialization*: Python datatypes are normalized (NaN handling, NumPy unboxing) before serialization to ensure a loss-less JSON round trip. Output is an in-memory `ContextBundle` dataclass that is persisted as JSON to `bundles/` via `write_bundle()`.
- **Vault Bundle (`build_vault_bundle`)**:
  - *Data Sources*: Local markdown files from `vault/theses/`, `vault/transcripts/`, and `vault/research/`. Drive fallback noted as not implemented.
  - *Features*: Parses `_thesis.md` files for fields (`style`, `scaling_state`, `rotation_priority`, and YAML `triggers`).
  - *Hashing*: SHA-256 is applied over the UTF-8 text bytes of individual documents. A canonical JSON hash wraps the entire bundle (omitting timestamp to ensure stability).
- **Composite Bundle (`build_composite_bundle`)**:
  - *Function*: Creates a lightweight metadata object linking both market and vault bundles.
  - *Data Sources*: Also fetches Tier 2 data: `recent_rotations` from the Google Sheets `Trade_Log`.
  - *Hashing*: Implements an order-sensitive `_composite_hash` computed from `SHA256(market_hash + vault_hash + recent_rotations)`. Agents interact strictly with this hash.

---

## Section 2: Prompt Construction Methods
The LLM interaction sits heavily in `utils/gemini_client.py`.

- **`ask_gemini()`**:
  - *Signature*: `def ask_gemini(prompt: str, system_instruction: str = None, json_mode: bool = False, max_tokens: int = 2000, response_schema: Type[T] = None) -> str | T`
  - *Auth*: Dual-path resolving ADC first (gcloud Vertex AI context), falling back to API Key if unavailable.
  - *Safety*: Automatically prepends `SAFETY_PREAMBLE` to system instructions. Includes explicit retries + backoff for `429 RESOURCE_EXHAUSTED` responses.
- **`SAFETY_PREAMBLE`**:
  - *Text*: `"You must NEVER recommend executing specific trades. You provide analysis and considerations only. All buy/sell decisions are the investor's."*
  - *Location*: Hardcoded constant at the top of `utils/gemini_client.py`.
- **`ask_gemini_bundled()` & `ask_gemini_composite()`**:
  - These are specialized wrapper methods enforcing strict schemas. They load the bundle from disk, verify the hash, prepend a stringified context window directly to the user prompt, and require the Pydantic `response_schema` to include a `bundle_hash` field for output tracing.
- **Agent Prompts**: 
  - Current prompts are limited to strings embedded in Python, primarily within `utils/agents/podcast_analyst.py`. Strict, separate markdown-based system prompts explicitly decoupled from logic were `NOT_FOUND` in production paths.

---

## Section 3: Gap Analysis vs Nine-File Kit

| # | Component | Expected | Current State | Gap |
|---|-----------|----------|---------------|-----|
| 1 | `styles.json` | Four-style definitions | EXISTS_AND_WORKS | None (in `data/styles.json`) |
| 2 | `_thesis.md` template | Scaling state + rotation priority fields | EXISTS_AND_WORKS | Fully parsed in `vault_bundle.py` |
| 3 | `buy_list_template.md` | Deployment rules + execution log | EXISTS_STUB_ONLY | Currently archived/deprecated |
| 4 | `context_bundle_spec.md` | Deterministic Python assembly spec | EXISTS_STUB_ONLY | Currently archived/deprecated |
| 5 | Re-buy Analyst | JSON-only system prompt + Pydantic schema | NOT_FOUND | Requires creation & CLI wiring |
| 6 | Add-Candidate Analyst | JSON-only system prompt + Pydantic schema | NOT_FOUND | Requires creation & CLI wiring |
| 7 | New Idea Screener | JSON-only, requires `--tickers` CLI arg | NOT_FOUND | Requires creation & CLI wiring |
| 8 | List Coherence Checker | JSON-only system prompt + Pydantic schema | NOT_FOUND | Requires creation & CLI wiring |
| 9 | Hard rules encoded | In `SAFETY_PREAMBLE` and Pydantic validators | EXISTS_AND_WORKS | Embedded in `gemini_client.py` |

---

## Section 4: Integration Points
1. **Trigger**: Handled by Typer in `manager.py`. `manager.py bundle composite` initiates manual composite generation. No explicit subcommands for the Agents currently exist.
2. **Data fetch**: Fully implemented. `utils/schwab_client.py`, `utils/sheet_readers.py`, and `yfinance` function robustly.
3. **Assembly**: Functional in `core/bundle.py`, `vault_bundle.py`, and `composite_bundle.py`.
4. **Hashing**: Correctly computing deterministic SHA-256 canonical outputs prior to bundle persistence.
5. **Persistence**: In-memory payloads are safely flushed to JSON in the `bundles/` directory.
6. **Agent invocation**: Implemented safely via `ask_gemini_composite()`.
7. **Output landing**: NOT_FOUND. There is no pipeline for taking the JSON response from an agent and landing it in an `Agent_Outputs` tab or formatted markdown report. 

---

## Section 5: Re-buy Analyst Readiness Assessment
The infrastructure is exceptionally well-positioned to support the Re-buy Analyst.

- **Bundle Context:** The `CompositeBundle` perfectly anticipates the Re-buy Analyst. It includes the `market` state, `vault` thesis documents, and a top-10 slice of `recent_rotations` via `Trade_Log` — precisely what is needed to review recently sold assets.
- **Output Schema:** Not defined.
- **Sandbox Write Path:** Not built.
- **Minimum Work Needed:** 
  1. Draft the `rebuy_analyst_prompt.md`.
  2. Implement the Pydantic Response Schema in `utils/agents/rebuy_analyst.py`.
  3. Wire a `manager.py agent rebuy` CLI command that prints or safely writes the output locally.

---

## Section 6: Proposed Workflow to Build Out the Process

1. **`01_rebuy_analyst_agent.md`**
   - *Scope*: Implement the Re-buy Analyst system prompt, its Pydantic schema (inheriting `bundle_hash`), and wire up a CLI command to invoke it.
   - *Inputs*: `manager.py`, `utils/gemini_client.py`, `core/composite_bundle.py`
   - *Outputs*: `prompts/rebuy_analyst.md`, `utils/agents/rebuy_analyst.py`, modified `manager.py`.
   - *Verification step*: Run `python manager.py agent rebuy` and verify console output returns properly formatted Pydantic data aligned with the active composite bundle.
   - *Complexity*: Medium

2. **`02_agent_sandbox_landing.md`**
   - *Scope*: Build a safe text/sheet write path for Agent Outputs, preserving the `DRY_RUN=true` default.
   - *Inputs*: `utils/agents/rebuy_analyst.py`, `pipeline.py` / `utils/sheet_writers.py`
   - *Outputs*: `utils/agent_landing.py` (or added to `manager.py`).
   - *Verification step*: Run `python manager.py agent rebuy --live` and verify the results cleanly append to the designated Sandbox destination.
   - *Complexity*: Small

3. **`03_add_candidate_analyst.md`**
   - *Scope*: Implement the Add-Candidate Analyst using current holdings and thesis files.
   - *Inputs*: `manager.py`, new sandbox landing logic.
   - *Outputs*: `prompts/add_candidate.md`, `utils/agents/add_candidate.py`, modified `manager.py`.
   - *Verification step*: Run `python manager.py agent add-candidate` without errors.
   - *Complexity*: Small

4. **`04_new_idea_screener.md`**
   - *Scope*: Implement New Idea Screener ensuring standard 4-style classification.
   - *Inputs*: `data/styles.json`, `manager.py`.
   - *Outputs*: `prompts/new_idea_screener.md`, `utils/agents/new_idea_screener.py`, modified `manager.py` (requiring `--tickers`).
   - *Verification step*: Run `python manager.py agent screener --tickers XYZ` and parse the analysis correctly.
   - *Complexity*: Small

5. **`05_list_coherence_checker.md`**
   - *Scope*: Implement the List Coherence Checker and structure its output to mimic `buy_list_template.md`. Integrate the tax-layer by querying `Tax_Control`.
   - *Inputs*: Outputs from previous agents, `docs/archive/deprecated/agents/buy_list_template.md`.
   - *Outputs*: `prompts/coherence_checker.md`, `utils/agents/coherence_checker.py`, un-archived `buy_list_template.md`.
   - *Verification step*: Run the coherence check and verify the aggregate math/styles validate correctly against dry powder.
   - *Complexity*: Medium

---

## Section 7: Risks & Open Questions

- **Archived Context Specs:** Both `context_bundle_spec.md` and `buy_list_template.md` are currently nested deep in `docs/archive/deprecated/agents/`. Is the decision to archive them intentional, or should they be promoted back to a living `docs/architecture/` folder?
- **Missing Write Path:** `pipeline.py` currently shims legacy functionality, but there is no explicitly defined destination (like an `Agent_Outputs` tab) for generated buy lists. Should this simply be written to a local `.md` file, or formally synced to Google Sheets?
- **Thesis Template Drift:** The `_parse_thesis_fields` method handles multiple YAML trigger blocks safely, hinting at legacy drift. We should ensure the `vault add-thesis` command enforces a unified template moving forward.

---

## Appendix A: File Inventory
Paths & configurations accessed during audit:
- `core/bundle.py` (494 lines)
- `core/composite_bundle.py` (140 lines)
- `core/vault_bundle.py` (260 lines)
- `utils/gemini_client.py` (317 lines)
- `manager.py` (969 lines)
- `pipeline.py` (500 lines)
- `config.py` (476 lines)
- `data/styles.json` (18 lines)
- `utils/agents/podcast_analyst.py` (80 lines)
- `docs/archive/deprecated/agents/context_bundle_spec.md` (148 lines)
- `docs/archive/deprecated/agents/buy_list_template.md` (103 lines)