# Phase 4 Prompts — Export Engine for Frontier LLM Analysis

**Status:** QUEUED. Do not start until Phase 3 is boring.

**Owner:** Bill. **Executor:** Claude Code or Gemini CLI, one prompt at a time.

**Governing rules:**
- Phase 4 does not start until Phase 3 is boring. No exceptions.
- Prompts run in order. Each is a single clean commit.
- DRY RUN → verify → `--live`, as always.
- This phase delivers the **reasoning workflow** your system was architected around: deterministic local computation, LLM reasoning performed externally by frontier models via manual paste.

---

## Why this phase exists

The April 2026 architectural pivot decommissioned the local agent squad in favor of a cleaner philosophy: **APIs calculate locally, LLMs reason externally.** The dashboard and Tax_Control give you deterministic 30-second scans. For deep analysis — "should I rotate UNH given my YTD tax posture?", "what's my RSI picture on growth tech right now?", "is my concentration in tech getting out of hand?" — you want to hand a high-signal package to Claude, Gemini, or Perplexity and get a frontier-quality response.

Today, that hand-off is manual and ad hoc. You have to remember which thesis files to paste, copy numbers from the sheet, re-explain your investment styles every time. This wastes the best feature of the system — the already-computed composite bundle with hashed provenance.

Phase 4 turns that into a single command: `manager.py export <scenario>` produces a package — context JSON, prompt template, relevant thesis files — ready to paste into any frontier LLM.

---

## Scope

In scope:
- `manager.py export` command group with subcommands for each analysis scenario
- `exports/` directory (gitignored) for generated packages
- A library of **prompt templates** tuned to your investment philosophy (four styles, rotation-based thinking, tax awareness)
- Scenario types: rotation analysis, single-position deep dive, tax-aware rebalancing, RSI/technical scan, macro review, concentration check, thesis health review
- **Context packaging** — each export bundles the relevant composite bundle slice + thesis files + tax state + any scenario-specific data (e.g., Trade_Log for rotation analysis)
- A small CLI helper (`export inspect <path>`) that prints the package structure so you can verify before pasting
- User documentation updated with the export workflow and template catalog

Out of scope for Phase 4:
- Automated LLM calls (that's the whole point — LLM reasoning stays external)
- Back-feeding LLM responses into the Sheet (manual for now; Phase 5+ may revisit)
- Export packages that exceed any single LLM's context window — we split at generation time
- PDF / Word output formats (markdown and JSON only)

---

## Pre-flight

Before starting Phase 4:

- [ ] Phase 3 completion gate fully passed. `Tax_Control` must exist because the Export Engine reads from it.
- [ ] A meaningful majority of positions have `_thesis.md` files with populated YAML triggers (check with `manager.py vault thesis-audit`).
- [ ] You've done at least three "manual" analyses against Claude/Gemini/Perplexity so you have an intuition for what works in the prompts.
- [ ] Decide: which frontier LLM is the primary target? **Recommendation: don't pick.** The templates should be LLM-agnostic — plain markdown prompts with clean JSON context. All three (Claude, Gemini, Perplexity) handle this well.

---

## Prompt 4.1 — Scaffold the export command group and package structure

### Context

Before writing any scenario-specific logic, the CLI surface and the package format need to be in place. This prompt creates the skeleton that 4.2 through 4.6 fill in.

### Task

1. **Read first:** `manager.py` (bundle_app, vault_app, tax_app for pattern reference), `core/composite_bundle.py`, `config.py`.

2. In `config.py`, add:
   ```python
   EXPORTS_DIR = Path("exports")
   EXPORT_SCENARIOS = [
       "rotation",        # "should I rotate X into Y?"
       "deep-dive",       # single-position thesis + data snapshot
       "tax-rebalance",   # rebalancing with tax awareness
       "technical-scan",  # RSI/MA/volume snapshot across the book
       "macro-review",    # current positioning vs macro regime
       "concentration",   # concentration / correlation check
       "thesis-health",   # which theses are stale / violated / ADD / TRIM
   ]
   ```

3. In `manager.py`, add a new Typer group:
   ```python
   export_app = typer.Typer(help="Export context packages for frontier LLM analysis.")
   app.add_typer(export_app, name="export")

   @export_app.command("list")
   def export_list():
       """List available export scenarios with descriptions."""
       ...

   @export_app.command("inspect")
   def export_inspect(path: Path = typer.Argument(...)):
       """Print the structure of an export package (file sizes, hashes, preview)."""
       ...
   ```

4. Each export scenario will be a subcommand under `export_app` (added in later prompts). For this prompt, only scaffold `list` and `inspect` plus one placeholder subcommand (`export rotation --help`) that prints "Not implemented — coming in Phase 4.2."

5. **Package format.** An export package is a directory under `exports/` named `{scenario}_{YYYYMMDD_HHMMSS}_{short_hash}/` containing:
   ```
   exports/rotation_20260501_093000_a1b2c3d4/
   ├── README.md               # Human-readable summary of what's in this package
   ├── prompt.md               # The prompt template with scenario-specific context filled in
   ├── context.json            # Structured data: positions, KPIs, tax state, etc.
   ├── theses/                 # Relevant thesis markdown files for this scenario
   │   ├── UNH_thesis.md
   │   └── VEA_thesis.md
   └── manifest.json           # Metadata: scenario, composite_hash, timestamp, prompt_template_version
   ```

6. Create `exports/` directory and add to `.gitignore` if not already ignored.

7. Create a helper module `tasks/export_package.py` with primitives:
   - `create_package_dir(scenario) -> Path`
   - `write_manifest(pkg_dir, scenario, composite_hash, prompt_template_version, extra_metadata={})`
   - `write_readme(pkg_dir, scenario, summary_text, paste_instructions)`
   - `copy_thesis_files(pkg_dir, tickers)` — copies from `vault/theses/` into `pkg_dir/theses/`
   - `write_context_json(pkg_dir, context_dict)`

8. `export inspect <path>` should print a Rich table with: scenario, generated timestamp, composite hash, file list with sizes, first 500 chars of prompt.md.

### Constraints

- **Everything goes under `exports/`. Gitignored.** Packages are local-only by default. Don't check them in.
- **No LLM API calls.** Export packages are generated from local data and manually pasted.
- **Prompt templates have version numbers.** So you can improve them over time and track which template a given package used.
- **No scenario logic in this prompt.** Just scaffolding.

### Gate criteria

- [ ] `python manager.py export list` prints all 7 scenarios with short descriptions
- [ ] `python manager.py export inspect <some_path>` prints a table even for an empty package (just manifest)
- [ ] `exports/` is in `.gitignore`
- [ ] `tasks/export_package.py` has the helper functions, importable and tested
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 4.1: Export command scaffold + package primitives`

### What NOT to do

- Do not implement any scenario logic
- Do not write any prompt templates yet
- Do not call any LLM

---

## Prompt 4.2 — Rotation analysis scenario

### Context

The rotation is your unit of analysis. This scenario answers: "I'm thinking about selling X and buying Y — what does the full picture look like?" It packages the two positions' thesis files, current technicals, tax implications of the sell, and recent Trade_Log context so you can ask a frontier LLM for a structured opinion.

### Task

1. **Read first:** `core/composite_bundle.py` (the trigger accessor from Phase 2.2), `tasks/build_tax_control.py::compute_tax_control_data()` (from Phase 3.2), `config.TAB_TRADE_LOG` and related constants.

2. Add to `manager.py`:
   ```python
   @export_app.command("rotation")
   def export_rotation(
       sell: str = typer.Option(..., "--sell", help="Ticker you're considering selling."),
       buy: str = typer.Option(..., "--buy", help="Ticker you're considering buying (or 'CASH')."),
       size: str = typer.Option("partial", "--size", help="partial | full"),
       notes: str = typer.Option("", "--notes", help="Free-text context to include in the prompt."),
   ):
       """Package a rotation analysis for frontier LLM review."""
   ```

3. The command:

   a. Resolves the latest composite bundle.

   b. Pulls structured data for both tickers: current price, cost basis, unrealized G/L, weight, technicals (RSI, MA vs price, volume signal, trend_label), fundamentals (P/E, PEG, ROIC if available), triggers (price_trim_above, price_add_below if present), current thesis content.

   c. Pulls tax-relevant info for the sell-side: cost basis, estimated gain/loss, ST vs LT classification. Also pulls current `Tax_Control` state: YTD_Net_ST, YTD_Net_LT, Disallowed_Wash_Loss, Estimated_Federal_CapGains_Tax, Tax_Offset_Capacity.

   d. Pulls recent Trade_Log rows (last 90 days) for rotation pattern context.

   e. Assembles `context.json` with all of the above, structured for LLM consumption.

   f. Generates `prompt.md` from a template (see 4.2.1 below).

   g. Copies the sell and buy thesis files into `theses/`.

   h. Writes `manifest.json` and `README.md`.

   i. Prints the package path and a "paste this prompt + attach these files to Claude/Gemini/Perplexity" message.

4. **4.2.1 — The rotation prompt template** (save as `tasks/templates/rotation_v1.md`):

   ```markdown
   # Rotation Analysis — {SELL_TICKER} → {BUY_TICKER}

   You are reviewing a potential portfolio rotation for a CPA/CISA investor
   who runs a disciplined, rotation-based approach across four styles:
   GARP-by-intuition, Thematic Specialists, Boring Fundamentals + dip-buying,
   and Sector/Thematic ETFs with broad index and bond ballast. He uses
   small-step scaling, not binary entries/exits. Exits are typically rotations
   into something perceived as better, including strategic cash builds.

   ## The Proposed Rotation

   - Sell: {SELL_TICKER} ({SELL_SIZE} — {SELL_DOLLAR_AMOUNT} estimate)
   - Buy:  {BUY_TICKER}  ({BUY_DOLLAR_AMOUNT} estimate)
   - Bill's notes: {USER_NOTES}

   ## Current State (from composite bundle {COMPOSITE_HASH_SHORT})

   ### Sell-side: {SELL_TICKER}
   (structured data: price, cost basis, UGL, weight, technicals, fundamentals,
   triggers from thesis, full thesis markdown attached as theses/{SELL}_thesis.md)

   ### Buy-side: {BUY_TICKER}
   (same structure)

   ### Tax Implications of the Sell
   - Estimated realized G/L on this sell: {ESTIMATED_REALIZED_GL}
   - Term: {ST_OR_LT}
   - Current YTD tax posture: Net ST {YTD_NET_ST}, Net LT {YTD_NET_LT},
     Disallowed Wash Loss {WASH_DIS}, Est Tax {EST_TAX}, Offset Capacity {OFFSET}

   ### Recent Rotation Context (last 90 days)
   (Trade_Log rows summarized — helps the LLM see the pattern of recent
   substitutions and whether this rotation is consistent or a shift)

   ## What I Want From You

   Give me a structured opinion with the following sections:

   1. **The implicit bet.** In one sentence, what am I betting on with this rotation?
   2. **Style fit.** Which of my four styles does the buy-side fit? Is that style under- or over-weighted right now?
   3. **Tax-aware framing.** Given my YTD tax posture, does the timing make sense?
      Is there a wash-sale risk if I re-buy the sell-side within 30 days?
   4. **Technical posture.** Is the buy-side in an add zone per the written thesis triggers?
      Is the sell-side in a trim zone or just fully valued?
   5. **Objections.** Give me three reasons I might regret this trade in 6 months.
   6. **Scaled approach.** If I do this, how would you split it into small steps?

   Do not recommend a price target. Do not predict where the market goes.
   Stay grounded in the data in this package and the thesis files attached.
   ```

5. **Scale-in guidance rule.** The prompt must explicitly say "Do not recommend a price target. Do not predict where the market goes." This encodes Bill's agent hard rule into the prompt so external LLMs honor it.

### Constraints

- **Wash-sale check included by default.** The prompt explicitly asks the LLM to flag 30-day wash-sale risk.
- **Scale-in framing baked in.** The prompt always asks for a small-step plan, never all-or-nothing.
- **No price targets, no market predictions.** Hard rule, stated in the prompt itself.
- **The LLM gets your thesis files verbatim.** Don't summarize them in the prompt — attach them.

### Gate criteria

- [ ] `python manager.py export rotation --sell UNH --buy VEA --size partial --notes "testing the packager"` creates a package under `exports/`
- [ ] `python manager.py export inspect <the new path>` shows the package structure
- [ ] Manually open `prompt.md` — it contains real values (not `{PLACEHOLDERS}`)
- [ ] Thesis files for UNH and VEA are copied into `theses/`
- [ ] `context.json` validates as JSON and contains the expected structure
- [ ] Paste the contents into Claude.ai or Gemini — confirm a coherent response comes back
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 4.2: Rotation analysis export scenario`

### What NOT to do

- Do not send the package to an LLM programmatically
- Do not persist the LLM response anywhere in the sheet
- Do not add multiple rotation templates; `rotation_v1.md` is enough for now

---

## Prompt 4.3 — Single-position deep dive scenario

### Context

"I'm on the fence about UNH. Give me a full deep dive." Frontier LLMs are very good at this when you hand them all the data. This scenario packages a single position's complete picture: thesis, technicals, fundamentals, tax posture, recent behavior, for whatever size question you want to ask.

### Task

1. Add to `manager.py`:
   ```python
   @export_app.command("deep-dive")
   def export_deep_dive(
       ticker: str = typer.Argument(...),
       question: str = typer.Option(..., "--question", help="The specific question you want answered."),
   ):
       """Package a single-position deep dive for frontier LLM review."""
   ```

2. The command pulls everything relevant for a single ticker:
   - Composite bundle slice (position, technicals, fundamentals, triggers)
   - Full thesis markdown
   - Tax-lot detail from `RealizedGL` if the ticker has appeared there this year
   - Trade_Log rows involving this ticker over the last 365 days
   - Position weight and how that compares to the thesis's `style_size_ceiling_pct` if set
   - A "drift summary": current price vs trim target vs add target vs 52w high/low

3. Template `deep_dive_v1.md` structure:
   ```markdown
   # Deep Dive — {TICKER}

   ## My Specific Question

   {USER_QUESTION}

   ## Full Context

   ### My Written Thesis
   (attached — theses/{TICKER}_thesis.md)

   ### Current Position
   (structured data from composite bundle)

   ### Technical Picture
   (RSI, MA50/MA200, volume, trend_label, golden/death cross flags)

   ### Fundamental Picture
   (P/E, PEG, ROIC, margins, growth — if available; ETFs will have less)

   ### Action Zones From My Thesis
   - Trim target: {PRICE_TRIM_ABOVE}
   - Add target:  {PRICE_ADD_BELOW}
   - Current price: {CURRENT_PRICE}
   - Position: {IN_TRIM_ZONE | IN_ADD_ZONE | NEUTRAL}

   ### Recent Personal History
   - Trade_Log rotations involving this ticker in the last year: {COUNT}
   - Realized G/L on this ticker YTD: {AMOUNT}

   ## What I Want From You

   Answer my specific question above, grounded in the attached thesis
   and the data in this package. Before answering, briefly confirm:

   1. What style does this position fit under my four styles?
   2. Is the thesis still intact, or has something material shifted?
   3. Where does current price sit vs. my written triggers?

   Then give me the answer to my question. No price targets, no market
   predictions. Short, structured, honest.
   ```

### Constraints

- **The user's question is front-and-center in the prompt.** It's the first section after the title, not buried.
- **The LLM is asked to confirm style fit and thesis intactness before answering.** This forces grounding.
- **If the ticker has no thesis file, the command still works** but the prompt explicitly notes the gap and asks the LLM to be cautious.

### Gate criteria

- [ ] `python manager.py export deep-dive UNH --question "is the managed care thesis still intact after the recent pressure?"` creates a package
- [ ] Prompt contains the user question verbatim
- [ ] Thesis file is copied; if absent, the prompt says so
- [ ] Manual paste test produces a coherent LLM response
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 4.3: Deep-dive export scenario`

### What NOT to do

- Do not try to summarize the thesis in the prompt
- Do not apply any LLM-opinion coloring to the cell values

---

## Prompt 4.4 — Technical scan scenario

### Context

You mentioned you've been querying the CLI for RSI and similar. This scenario packages a portfolio-wide technical snapshot so you can ask: "Which of my positions look stretched? Which look like add zones from a pure technical read?" This is a close cousin to the old Re-buy Analyst and the retired technical agents — but now the LLM does the reasoning, not a local agent.

### Task

1. Add to `manager.py`:
   ```python
   @export_app.command("technical-scan")
   def export_technical_scan(
       filter_style: str = typer.Option("", "--style", help="Filter to a specific style (GARP/FUND/THEME/ETF)."),
       min_weight: float = typer.Option(0.0, "--min-weight", help="Only include positions ≥ this weight %."),
   ):
       """Package a portfolio-wide technical snapshot for frontier LLM review."""
   ```

2. The command pulls technical state for all (or filtered) positions from the composite bundle's `calculated_technicals`:
   - RSI, MA50/MA200, price vs MA signals, trend_score, trend_label, golden/death cross flags, volume_signal
   - Action zones (trim/add targets) from thesis triggers
   - Days from last rotation (from Trade_Log) — flags stale positions

3. Template `technical_scan_v1.md`:
   ```markdown
   # Portfolio Technical Scan — {TIMESTAMP}

   Portfolio of 50+ positions across four styles. Scan filtered to:
   style = {FILTER_STYLE_OR_ALL}, min_weight = {MIN_WEIGHT}%.

   ## Technical State (all positions in scope)

   (compact table: Ticker | Style | Weight | Price | RSI | Trend Label | Add Target | Trim Target | In Zone?)

   ## What I Want From You

   1. **Stretched positions.** Which positions look overbought (RSI > 70,
      well above MA200, death cross risk)? Rank top 5 with one-line rationale each.
   2. **Add-zone candidates.** Which positions are sitting in their written add zones
      (price ≤ add target) AND show stabilizing technical structure (RSI 35–60,
      above MA50 or approaching it)? Rank top 5.
   3. **Coherence check.** Is there a style imbalance in the technical picture?
      E.g., "all GARP positions look stretched, all FUND positions look cheap."
   4. **Nothing to do.** Which positions look like pure holds — no action signal?
      Just a count and a representative example.

   Do not give price targets. Do not predict market direction. Ground every
   call in the table data above.
   ```

### Constraints

- **The table is the payload.** Keep it compact so the LLM doesn't drown in filler.
- **Filter support matters** — 50 positions is too many to reason about at once for most LLMs.
- **No agent-like "BUY" or "SELL" language.** Use "add-zone candidate" / "stretched" / "neutral" only.

### Gate criteria

- [ ] `python manager.py export technical-scan --style GARP --min-weight 2.0` creates a package
- [ ] Compact table renders correctly in the prompt (markdown table, not JSON)
- [ ] Manual paste test produces a useful ranked response
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 4.4: Technical scan export scenario`

### What NOT to do

- Do not include full thesis files in this scenario — it's about technicals, not narrative
- Do not filter out ETFs (RSI and trend labels apply to them too)

---

## Prompt 4.5 — Tax-aware rebalancing, macro review, concentration, thesis health scenarios

### Context

Four more scenarios that follow the same pattern as 4.2–4.4. Bundle them in one prompt because each is structurally similar — a specific slice of the composite bundle plus a template that asks a specific question.

### Task

For each scenario, add the command + template:

**`export tax-rebalance`**
- Pulls: current holdings with UGL, Tax_Control KPIs (especially YTD_Net_ST, Tax_Offset_Capacity, Disallowed_Wash_Loss), positions with sizable unrealized losses.
- Template asks: "Given my YTD tax posture and my Tax_Offset_Capacity of ${X}, which positions are the best tax-loss harvesting candidates that don't violate my thesis? Flag any wash-sale risks."
- Bakes in: CPA-level tax awareness. The LLM must not recommend harvesting a loss if a position is currently in the thesis add zone (buying it back within 30 days would trigger wash sale).

**`export macro-review`**
- Pulls: sector weights, top 10 holdings, cash position, Target_Allocation vs current allocation drift.
- Template asks: "Given the current positioning and recent Trade_Log pattern, am I positioned consistently with a specific macro view, or is the book saying one thing while I'm saying another?"
- This is deliberately open-ended — macro is where frontier LLMs add the most value.

**`export concentration`**
- Pulls: top-10 weights, sector weights, style weights, correlation hints (from composite bundle if available, otherwise position-level descriptions).
- Template asks: "Identify concentrations that aren't obvious from single-stock weights. Are there correlated clusters I should be aware of? How would the book behave in a -15% equity drawdown given current weights?"

**`export thesis-health`**
- Pulls: thesis audit results (from `vault thesis-audit`), positions where price is outside their action zones for > 30 days, positions without thesis files.
- Template asks: "Which of my written theses look stale, violated, or out of sync with current price action? What's the prioritized list for me to re-read or re-write this weekend?"

For each, define a versioned template file under `tasks/templates/`.

### Constraints

- **Keep each scenario narrow.** Each one is for a specific question type — don't build a "universal" scenario.
- **Templates reference the data in the package, not data the LLM has to imagine.** Every claim the template asks for has to be answerable from `context.json` + thesis files.
- **No cross-scenario dependencies.** Each can run standalone.

### Gate criteria

- [ ] All four commands runnable, each produces a valid package
- [ ] Each template has a specific, narrow question — no vague "analyze my portfolio"
- [ ] Paste tests confirm the LLM can answer with the provided context
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 4.5: Four more export scenarios (tax-rebalance, macro-review, concentration, thesis-health)`

### What NOT to do

- Do not add a generic "export everything" scenario; scenarios are narrow by design
- Do not make one scenario call another
- Do not build a UI for choosing scenarios — `manager.py export list` is the UI

---

## Prompt 4.6 — Template refinement, user docs, and weekly workflow integration

### Context

The scenarios exist and work. The final prompt makes them easy to live with.

### Task

1. **Read first:** `portfolio_manager_user_docs.html`, all templates under `tasks/templates/`.

2. Add to each template: a consistent **preamble** that describes Bill's four styles and operating philosophy in one paragraph. This saves you from re-explaining context in every conversation. Template files can `{{ include preamble.md }}` via simple string substitution.

3. Add a **"paste instructions" section** to every `README.md` in a package:
   ```markdown
   # How to use this package

   1. Open Claude.ai, Gemini, or Perplexity.
   2. Copy the contents of `prompt.md` and paste as your first message.
   3. Attach (or paste) the files in `theses/` and the `context.json`.
   4. Ask the LLM for its structured response per the prompt.
   5. Save your conversation — nothing about this package is tracked anywhere
      else unless you choose to update `Decision_Journal` manually afterward.
   ```

4. Update `portfolio_manager_user_docs.html`:
   - Bump version to 2.2 (Export Engine Added).
   - Add a new section "Deep Analysis Workflow" explaining the export command, the scenarios, and how to use packages with frontier LLMs.
   - Include a scenario catalog table with columns: Scenario, Question it answers, Best LLM for it (Claude for tax nuance, Gemini for macro/technical, Perplexity for idea validation).
   - Update the weekly operational cycle to end with: "6. Deep analysis (optional). Generate export packages for any position, rotation, or question that needs frontier reasoning. Feed results back into Decision_Journal manually."

5. Add a `manager.py export list` output that now groups scenarios by category:
   ```
   Decision support:
     rotation         — Should I rotate X into Y?
     deep-dive        — Full picture on one position
     tax-rebalance    — Harvest candidates given YTD tax posture

   Portfolio review:
     technical-scan   — Overbought/oversold + action zones across the book
     macro-review     — Is my positioning consistent with a macro view?
     concentration    — Hidden concentrations and drawdown behavior
     thesis-health    — Which theses are stale / violated / need re-reading?
   ```

6. Add a weekly workflow example to the user docs and to `tasks/templates/WEEKLY_WORKFLOW.md`:
   ```markdown
   # Weekly Workflow — Tying It All Together

   ## Monday morning (5 minutes)
   python manager.py health
   python manager.py snapshot --live
   python manager.py sync transactions --live
   python manager.py dashboard refresh --live

   ## Monday morning (scan — 3 minutes)
   Open the sheet. Review:
   - Decision_View for action-severity signals
   - Valuation_Card for positions now in Trim/Add zones (colored cells)
   - Tax_Control for Est Tax and Offset Capacity

   ## Midweek if anything triggers (10–20 minutes)
   python manager.py export deep-dive <TICKER> --question "..."
   → paste to Claude or Gemini
   → review response
   → if action taken, record manually in Decision_Journal

   ## Saturday morning (20 minutes)
   python manager.py export thesis-health
   → review stale/violated theses
   → backfill or update thesis files
   python manager.py vault snapshot --live
   python manager.py bundle composite --live
   ```

### Constraints

- **Consistency over novelty.** All templates share the preamble.
- **User docs are the product of Phase 4** as much as the code. If someone reads `portfolio_manager_user_docs.html` and can't figure out how to use the export engine in 5 minutes, this prompt isn't done.
- **No new scenarios.** If a new scenario is obvious, note it for Phase 5+ and keep moving.

### Gate criteria

- [ ] All templates have the consistent preamble
- [ ] `README.md` in every generated package has clear paste instructions
- [ ] `portfolio_manager_user_docs.html` Version 2.2 section added with scenario catalog
- [ ] `tasks/templates/WEEKLY_WORKFLOW.md` exists and is referenced from user docs
- [ ] Walk a fresh observer through the docs — they can generate + use an export package without help
- [ ] `CHANGELOG.md` updated
- [ ] Single commit: `Phase 4.6: Template consistency + user docs + weekly workflow`

### What NOT to do

- Do not feed LLM responses back into the system automatically
- Do not add OAuth or "paste-back" parsing of LLM responses
- Do not build a web UI for this

---

## Phase 4 Completion Gate

Phase 4 is complete when all six prompts have been executed, gated, and committed, **and** the following test passes:

```bash
# Full morning cycle (unchanged from Phase 3)
python manager.py health
python manager.py snapshot --live
python manager.py sync transactions --live
python manager.py dashboard refresh --live

# Then:
python manager.py export list
python manager.py export rotation --sell UNH --buy VEA --size partial --notes "testing"
python manager.py export inspect exports/rotation_YYYYMMDD_...

# Paste the prompt.md contents + attached files to Claude / Gemini / Perplexity.
# Confirm a coherent, grounded response comes back in each of the three.
```

All of the following must be true:

- [ ] All 7 scenarios work and produce valid packages
- [ ] Each scenario's prompt template is grounded in the data in the package — no hallucination hooks
- [ ] Manual paste test against Claude, Gemini, and Perplexity each produces a useful response
- [ ] User docs updated with the new workflow
- [ ] `CHANGELOG.md` has six Phase 4 entries
- [ ] No regressions in Phases 1–3

Only after Phase 4 is boring do we start Phase 5 (Trade Log maturation).

---

## Notes for Bill

- **This phase completes the post-pivot architecture.** Phases 1–3 give you the deterministic spine. Phase 4 gives you the external reasoning surface. Together they are the full realization of "APIs calculate locally, LLMs reason externally."
- **The templates will evolve.** Version them (`rotation_v1.md`, `rotation_v2.md`). Don't edit v1 in place once you've used it in a real decision — you'll want to compare.
- **Trust the human in the loop.** The entire design assumes you're the decision-maker and the LLM is a research tool. Don't build any path that lets an LLM response auto-execute anything.
- **Re-buy Analyst is officially retired in this phase.** Its job is done by Phase 2's conditional formatting (for the deterministic part) and by `export deep-dive` or `export technical-scan` (for the reasoning part).
- **Scenario ideas to add later** (do NOT build now): "options overlay" (covered calls given current positions), "new idea screener" (external candidates vs your book), "rotation retrospective" (how did my last 10 rotations perform?). These are Phase 5+ candidates.
