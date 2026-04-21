# Focus the agent roster: Thesis + Valuation + New Idea

**Goal:** Stop running seven agents by default. Run three. Retire (do not delete)
the other five from the default path. Align Thesis and Valuation on a shared
verdict vocabulary so disagreement between them becomes a usable signal.

**Non-goals for this prompt:** No prompt-surgery on the agent system prompts
themselves. No FMP caching fixes. No Decision_View cleanup. No Agent_Dashboard
column-shift fix. Those land in follow-up prompts after this one is green.

**Estimated time:** 60–90 minutes of Claude Code work, mostly verification.

---

## Step 0 — Starting-state verification

**Do not write any code yet.** Confirm these four facts by reading the actual
files. Report back each as a one-line verification.

1. In `manager.py`, the `analyze-all` command's `--agents` default currently is:
   `rebuy,tax,valuation,concentration,macro,thesis,bagger`
2. `from agents.new_idea_screener import app as new_idea_app` is present in the
   imports block at the top of `manager.py`
3. `agents/new_idea_screener.py` exists and defines a callable entry point the
   orchestrator can invoke
4. In `agents/valuation_agent.py`, the Pydantic schema's signal field uses one
   of these enum sets:
   - `accumulate | hold | trim | monitor` (lowercase — current)
   - `ADD | HOLD | TRIM | MONITOR` (uppercase — target)

   Report which.

If any of those four facts is not what I said, **stop and tell me before
proceeding**. Do not silently adapt.

---

## Step 1 — Change the default agent roster

Edit `manager.py`. Change the default value of the `--agents` option on
`analyze-all` from:

```python
agents: str = typer.Option(
    "rebuy,tax,valuation,concentration,macro,thesis,bagger",
    "--agents",
    help="Comma-separated list of agents to run. Default: all.",
),
```

to:

```python
agents: str = typer.Option(
    "thesis,valuation,new_idea",
    "--agents",
    help=(
        "Comma-separated list of agents to run. Default: the focused "
        "three (thesis, valuation, new_idea). Retired agents "
        "(rebuy, tax, concentration, macro, bagger, behavioral, "
        "options, value) can still be invoked explicitly — pass them "
        "via --agents to run them."
    ),
),
```

**Do not delete any imports from `manager.py`.** The retired agents stay
importable so they can be invoked by explicit `--agents` for ad-hoc runs. Only
the default string changes.

---

## Step 2 — Wire `new_idea` into `analyze_all.py`

Open `agents/analyze_all.py`. Locate the dispatch table that maps agent-name
strings to the functions that actually run each agent (there will be a
dict or if/elif chain keyed on strings like `"rebuy"`, `"tax"`, `"valuation"`,
etc.).

Verify that `"new_idea"` is present as a dispatch key. If it is not, add it,
routing to whatever entry point `agents/new_idea_screener.py` exposes (inspect
the file to find the right function name — likely `run_new_idea_screener` or
similar based on the pattern of the other agents).

If `new_idea_screener.py` expects a `--tickers` list to evaluate, make the
`analyze-all` path tolerate that: when no candidate tickers are provided, the
agent should return a structured "no candidates provided, nothing evaluated"
record, not error. Do not make it scan the market automatically — that violates
the agent's hard-rules spec from the April-20 design.

---

## Step 3 — Align Valuation's signal enum with Thesis

Open `agents/valuation_agent.py`. Find the Pydantic model for the per-ticker
output. The signal field currently uses lowercase `accumulate | hold | trim |
monitor`. Change it to uppercase matching Thesis's verdict vocabulary:
`ADD | HOLD | TRIM | MONITOR`.

**Migration guidance:**

- In the Pydantic `Literal[...]` or `Enum`, update the allowed values
- In the system prompt (`agents/prompts/valuation_agent_system.txt` or
  wherever the Valuation prompt lives — find it), replace every instance of
  the lowercase verbs in the output-format section with the uppercase
  equivalents. Do NOT rewrite the rest of the prompt; only update the
  signal enum.
- If there is any post-processing or sheet-writing code that checks for
  lowercase verbs (`if signal == "accumulate"`, etc.), update those checks
  to uppercase. Grep the codebase: `grep -rn "accumulate\|'trim'\|'monitor'"
  agents/ tasks/ utils/` and fix every lowercase match that refers to
  the valuation signal field.
- `Agent_Outputs` historical rows with lowercase values are fine — do not
  touch historical data. Only new writes will use uppercase.

Thesis already uses `ADD | HOLD | TRIM | EXIT | MONITOR` (or similar — verify).
Do not change Thesis. The goal is alignment, and Thesis's vocabulary wins
because it includes `EXIT`, which Valuation genuinely should not emit.

**If Thesis's current verdict enum does not match the above**, report back
what it actually is before changing Valuation. The two schemas must share
`ADD | HOLD | TRIM | MONITOR` as a common subset so downstream disagreement
detection can compare them.

---

## Step 4 — Add a disagreement section to the CLI output

In `agents/analyze_all.py`, after both Thesis and Valuation have run and their
per-ticker verdicts are collected, compute a disagreement list:

```python
def _is_disagreement(thesis_verdict: str, val_signal: str) -> bool:
    # Symmetric opposing pairs. MONITOR on either side = no disagreement.
    if thesis_verdict == "MONITOR" or val_signal == "MONITOR":
        return False
    opposing = {
        ("ADD", "TRIM"),
        ("TRIM", "ADD"),
        ("HOLD", "TRIM"),
        ("ADD", "HOLD"),  # optional — flag as yellow, not red
    }
    return (thesis_verdict, val_signal) in opposing
```

After both agents complete:

```python
disagreements = []
for ticker in sorted(set(thesis_by_ticker) & set(valuation_by_ticker)):
    t = thesis_by_ticker[ticker]
    v = valuation_by_ticker[ticker]
    if _is_disagreement(t, v):
        disagreements.append((ticker, t, v))
```

Render disagreements as a Rich table at the end of the `analyze-all` CLI
output, under a header like "Disagreements (Thesis vs Valuation)". Columns:
`Ticker | Thesis | Valuation | Weight %`. Sort by portfolio weight descending
so the biggest positions surface first.

**Do not create a new Sheet tab for this yet.** CLI-only for now. If the signal
proves useful over a few runs, a Sheet tab comes later.

If there are zero disagreements, print a single line:
`No Thesis/Valuation disagreements this run.`

---

## Step 5 — Update the run manifest to reflect the new default

In whatever code writes `bundles/runs/manifest_<id>_<date>.json`, the
`agents_requested` list will now be three entries by default. Verify the
manifest still serializes correctly with three agents. If the manifest schema
has a minimum-agent-count assumption anywhere, remove it — three is now normal.

Also: add a top-level field to the manifest called `"retired_agents"` whose
value is the list `["rebuy", "tax", "concentration", "macro", "bagger"]`. This
is documentation for future-you: a manifest reader who has forgotten the April
2026 retirement decision can see which agents the roster used to include.

---

## Step 6 — Smoke test (DRY RUN only)

Run:

```bash
python manager.py analyze-all --fresh-bundle
```

Note: **no `--live` flag**. This is dry-run. Expected behavior:

- Three agents run: thesis, valuation, new_idea
- `new_idea` runs with no candidate tickers and returns "no candidates
  provided" cleanly (not an error)
- A disagreement section prints at the end of the CLI output
- Manifest is written to `bundles/runs/` with three entries in
  `agents_requested` and the new `retired_agents` field
- **No writes to Google Sheets** (dry run)

If any of the above fails, report the exact failure mode before retrying.

---

## Step 7 — Live run (gated)

Only after Step 6 is clean:

```bash
python manager.py analyze-all --fresh-bundle --live
```

Verify on the Sheet:
- `Agent_Outputs` gets new rows for thesis and valuation only (new_idea with
  no candidates should write zero rows, not empty placeholder rows)
- The valuation rows' Signal Type column now shows uppercase values
  (`ADD`, `HOLD`, `TRIM`, `MONITOR`) — the historical lowercase rows stay as
  they were, which is correct
- Row count should be roughly 2× holdings count (one thesis row + one
  valuation row per analyzable position), much less than the 155 rows from
  manifest_a29f8de0

---

## Step 8 — Update CHANGELOG

Append a new CHANGELOG entry dated today:

```markdown
## [Unreleased] — 2026-04-20 — Focused three-agent roster

### Changed
- `manager.py analyze-all --agents` default changed from seven agents to
  three: `thesis,valuation,new_idea`. The retired five (rebuy, tax,
  concentration, macro, bagger) remain importable and can be invoked
  explicitly via `--agents` for ad-hoc runs.
- `agents/valuation_agent.py` signal enum aligned to uppercase
  `ADD | HOLD | TRIM | MONITOR`, matching Thesis Screener's verdict
  vocabulary. Enables cross-agent disagreement detection.
- `agents/analyze_all.py` now computes and prints a disagreements table
  (CLI-only for now) showing tickers where Thesis and Valuation produce
  opposing verdicts.

### Rationale
- Signal-to-noise was unacceptable: seven agents each emitting findings on
  48+ positions produced ~155 sheet rows per run, most of which were
  boilerplate. See April-20 personalization conversation for the design
  decision to focus on three agents.
- The disagreement signal is the actual alpha — when two independently-
  reasoning agents diverge on a name, that's where attention belongs.

### Not changed (intentionally)
- Retired agents' code is untouched and still importable
- No Sheet tabs were deleted or renamed
- No prompt-surgery on the agents' system prompts (follow-up work)
```

---

## What happens after this prompt lands

Follow-ups, each as its own prompt file, in this order:

1. **Valuation style-aware framing** — teach the Valuation prompt to reason
   differently for GARP vs FUND vs THEME vs ETF. This is the biggest
   signal-quality lever and was specced on April 20.
2. **Decision_View fix** — the "Not Evaluated" columns for Macro and Thesis
   are caused by a broken join. Rewrite the join against the latest run_id
   only.
3. **Agent_Outputs_Archive auto-rollover** — when a new `analyze-all` run
   writes, move previous runs' rows from `Agent_Outputs` to
   `Agent_Outputs_Archive`. Keeps the live tab scoped to the latest run.
4. **Agent_Dashboard column-shift fix** — header row is off by one column.
5. **Tab cleanup** — hide or archive tabs that aren't on the decision path:
   `Trade_Log_Staging` (keep but hide), `Agent_Outputs_Archive` (hide),
   `Logs` (hide).

---

## Success criteria for this prompt

- [ ] Step 0 verification reported for all four facts
- [ ] `python manager.py analyze-all --fresh-bundle` (no --live) runs three
      agents, prints disagreements section, writes manifest with
      `retired_agents` field
- [ ] `python manager.py analyze-all --fresh-bundle --live` writes only
      thesis + valuation rows to Agent_Outputs, row count ~2× holdings,
      uppercase Signal Type values
- [ ] CHANGELOG updated
- [ ] Old default agent list is recoverable by reading the CHANGELOG or by
      passing `--agents rebuy,tax,valuation,concentration,macro,thesis,bagger`
      explicitly
- [ ] No files deleted. No Sheet tabs deleted. No historical data modified.
