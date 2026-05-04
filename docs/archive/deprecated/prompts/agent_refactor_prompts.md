# MISSION
You are a Principal Financial Engineer tasked with refactoring our Portfolio Manager agents. You must execute the following sequence strictly in order. Do not proceed to the next step until the current step is fully implemented and verified. 

# GUARDRAILS
1. No LLM Math: All yields, drift, and projections must be calculated in Python.
2. Architecture Strictness: Agents return structured data only; they do NOT write to sheets. The Orchestrator handles all I/O.
3. Nested vs Tabular: Use Markdown tables for flat data only. Use prose or YAML-lite for nested structures (like thesis files).

---

## STEP 1: Legacy Agent Triage & Archive
Before refactoring, we must decide what lives and what dies. 
1. Review the files in the legacy `utils/agents/` directory and compare them against the new `agents/` directory.
2. Identify which legacy agents are obsolete, already ported, or abandoned. Move these to `archive/streamlit_legacy/`.
3. Identify which legacy agents need to be ported to the new `agents/` directory. Move them and update their imports. 
4. Delete the empty `utils/agents/` directory once triage is complete.
*Do not proceed to Step 2 until the production path (`agents/`) contains only the surviving agents.*

## STEP 2: Centralize "Magic Lists" to config.py
We need to eliminate silent bugs caused by duplicate exclusion lists.
1. Scan all surviving agents in the `agents/` directory and `core/bundle.py`.
2. Extract all hardcoded sets/lists (e.g., `CASH_EQUIVALENT_TICKERS`, `VALUATION_SKIP_TICKERS`, `BETA_EXCLUDE`).
3. Move these into `config.py` under a unified naming convention.
4. Update the surviving agents to import and use these sets from `config.py`.

## STEP 3: DRY Out Google Sheets I/O
Agents must not touch the Google Sheets API directly.
1. Create a new file: `utils/sheet_writers.py`. Do NOT put write logic in `sheet_readers.py`.
2. Extract the massive `_archive_and_overwrite` logic (currently duplicated across agents like `tax_agent.py`, `valuation_agent.py`, etc.) and place it in `sheet_writers.py`.
3. Refactor all surviving agents so they only `yield` or `return` standard-schema rows (dictionaries/Pydantic models).
4. Update `agents/analyze_all.py` (the orchestrator) to import from `sheet_writers.py` and handle the batch writing of the agents' outputs.

## STEP 4: Token Optimization (Markdown Prompts)
We need to reduce context window burn by swapping `json.dumps()` for Markdown tables, but ONLY for flat data.
1. Create a helper function `dicts_to_markdown_table(data: list[dict]) -> str` in an appropriate utility file (e.g., `utils/formatters.py`).
2. In agents dealing with flat tabular data (like `tax_agent.py` for holdings lists/TLH candidates, or `valuation_agent.py` for valuation facts), replace the `json.dumps()` injection with the new Markdown formatter.
3. **CRITICAL:** Do NOT use this formatter for nested data like `thesis_files` or `recent_rotations` in the Context Bundle. Those must remain as compact prose or YAML-lite.

## STEP 5: HOLD ON SIGNAL MEMORY
*Instruction to AI:* Acknowledge that implementing "Signal Memory" (pulling yesterday's signal to prevent LLM jitter) is a requirement, but we are explicitly DEFERRING it. Do not attempt to build ad-hoc prompt injections for this. It will be implemented later as a first-class field (`last_signal`, `last_signal_date`) inside `core/bundle.py` once the Context Bundle is proven by the Re-buy Analyst.