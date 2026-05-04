# TASK_thesis_sync.md — Agentic Implementation Plan

## System Directive
You are operating as the Agentic Staff Engineer defined in `GEMINI.md`. You have been tasked with building the `pm vault sync` workflow. 
Read this entire document before taking action. You will execute this in three distinct phases. You MUST use the `/plan` command and wait for my explicit "Y" approval before writing any code in Phase 2.

## Core Objective
Build a CLI workflow (`pm vault sync`) that reads `Transactions`, `Holdings_Current`, and `Realized_GL`, then reflects the activity back into each `vault/theses/<TICKER>_thesis.md` file. 

## Invariants & Guardrails (DO NOT VIOLATE)
1. **DRY_RUN Default:** `--live` flag is strictly required to write to disk.
2. **Idempotency:** Re-running on the exact same Sheet data MUST produce zero diffs.
3. **Prose Preservation:** Hand-written prose outside of HTML-comment fences is NEVER touched.
4. **Trigger Preservation:** Sizing-decision trigger fields (e.g., `price_add_below`, `fwd_pe_add_below`) are NEVER touched. Only `current_weight_pct` and `style_size_ceiling_pct` are updated.
5. **Safe YAML:** You MUST use `ruamel.yaml` in round-trip mode for frontmatter and triggers to preserve comments and ordering.

---

## PHASE 1: Discovery & Specification 
**Action:** Use your local tools (`view_file`, `ripgrep`, etc.) to map the dependencies required for this task. 
1. Inspect `vault/theses/UNH_thesis.md` and `SGOV_thesis.md` to map the canonical structure.
2. Inspect `core/vault_bundle.py::_parse_thesis_fields` to ensure your writer won't break the existing parser.
3. Inspect `config.py` for exact constants: `TAB_TRANSACTIONS`, `TAB_HOLDINGS_CURRENT`, `TAB_REALIZED_GL` (verify actual name), `THESES_DIR`, `TAB_TRADE_LOG`.
4. Inspect `styles.json`. If it lacks a `size_ceiling_pct` field per style, you must generate a proposed schema update.

**Deliverable 1:** Write `docs/phase6/thesis_managed_regions_spec.md`. It must contain the exact HTML-comment fences for `position_state`, `transaction_log`, `realized_gl`, `sizing`, and `change_log` as detailed in the project requirements.
**Deliverable 2:** Output a "Pre-flight Audit" to the terminal. Ask me ONE clarifying question if anything in the codebase contradicts this document. 

*PAUSE AND WAIT FOR MY APPROVAL TO PROCEED.*

---

## PHASE 2: Implementation 
**Action:** Enter `/plan` mode. Present your intended changes for the following three files. Wait for my "Y" before writing.

### File 1: `core/thesis_sync_data.py` (Data Gathering)
* **Function:** `gather_thesis_sync_data(as_of_date, tickers)` -> `dict[str, TickerSyncPayload]`
* **Logic:** Pure Python read-only assembly. Trust the pipeline that populated `Holdings_Current`.
* **Resolution Chain:** `style` = frontmatter → `ticker_strategies.json` → None. `style_size_ceiling_pct` = `styles.json[style].size_ceiling_pct`.
* **Rotation Linkage:** Cross-reference fingerprints against `Trade_Log` and `Trade_Log_Staging`.

### File 2: `tasks/write_thesis_updates.py` (The Writer)
* **Function:** `write_thesis_updates(payloads, dry_run, force_recreate_regions)` -> `ThesisSyncReport`
* **Logic:** Diff first. If zero changes, skip completely. 
* **Live Mode:** Write `<path>.bak.<UTC-isoformat>` BEFORE any mutation.
* **Mutations:** Update frontmatter (`last_reviewed`, `cost_basis`, `current_allocation`). Update triggers (`current_weight_pct`, `style_size_ceiling_pct`). Replace/Append managed regions.
* **Change Log:** Append one line per run summarizing the exact changes (e.g., `weight 9.3% → 9.5%; +1 transaction`).

### File 3: `manager.py` (CLI Wiring)
* **Command 1:** `vault sync [--ticker] [--live] [--force] [--show-diff]`
    * *Dry Run:* Print Rich table of drift, print unified diffs, print styles.json warnings. Exit 0.
* **Command 2:** `vault sync-status`
    * *Logic:* Audit-only. Prints Rich table sorted by staleness/drift (worst first). Does not write.

*EXECUTE WRITES ONLY AFTER I APPROVE THE /PLAN.*

---

## PHASE 3: Testing & Verification
**Action:** Once the code is written, use your tools to run the following tests locally and report the output.
1. `pm vault sync-status` -> Verify it runs cleanly without errors.
2. `pm vault sync --ticker UNH` -> Verify it runs a dry-run and prints a diff showing the 4 managed regions are injected, but hand-written prose is untouched.

If errors occur, use your logs to self-correct autonomously as per `GEMINI.md` rules.