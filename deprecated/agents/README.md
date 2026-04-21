# Buy List Agent Kit

A set of four contextualized agents plus supporting config and templates for
constructing and maintaining Bill's investment buy list. Designed to slot into
the existing `investment-portfolio-manager` project architecture (CLI-first,
Google Sheets as frontend, `ask_gemini()` + SAFETY_PREAMBLE already in place).

## What This Solves

Bill is currently at ~18% cash, strategically building dry powder for an expected
pullback. He needs a **buy list** — a pre-made shopping plan written while calm
— so that when sentiment turns, he's executing a plan instead of reacting
emotionally. The buy list is the bridge between planning and execution in his
broader investment workflow.

These four agents help him construct and maintain that list, anchored against
his specific four-style framework and his current portfolio state.

## The Four Agents

| Order | Agent | Purpose | Build Effort |
|---|---|---|---|
| 1 | **Re-buy Analyst** | Closes the loop on dry-powder sells. For each recently-sold ticker, determines if Bill wants the exposure back and drafts a candidate entry. | Half day |
| 2 | **Add-Candidate Analyst** | For each current holding, determines if it's a name Bill would welcome a lower entry to add to. Produces the highest-conviction section of the list. | Half day |
| 3 | **New Idea Screener** | Evaluates candidate names against Bill's four styles. Refuses to approve names that don't clearly fit. | Half day |
| 4 | **List Coherence Checker** | Reads the full draft list and flags balance problems (style mix, trigger distribution, deployment ratios). Diagnostic only — doesn't prescribe. | Half day |

Total: ~2 days of implementation on top of existing `ask_gemini()` and Sheets
infrastructure.

## Build Order (Important)

**Build the Re-buy Analyst first.** It produces immediate useful output (a draft
re-buy section for the buy list) and it tests whether the context bundle you've
assembled is actually sufficient for good agent output. If the Re-buy Analyst
produces good suggestions, the other three agents will work. If it produces
generic mush, the context bundle needs more structure before scaling up.

Build as standalone CLI scripts first. Each takes the same context bundle shape
(specified in `config/context_bundle_spec.md`). Each writes JSON output that
a Python post-processor converts to markdown sections in `buy_list.md`.

## Directory Structure

```
buy_list_kit/
├── README.md                          ← this file
├── config/
│   ├── styles.json                    ← canonical four-style definition
│   └── context_bundle_spec.md         ← what Python assembles before each agent run
├── templates/
│   ├── thesis_template.md             ← template for _thesis.md files
│   └── buy_list_template.md           ← template for the buy list itself
└── agents/
    ├── 01_rebuy_analyst_prompt.md
    ├── 02_add_candidate_analyst_prompt.md
    ├── 03_new_idea_screener_prompt.md
    └── 04_list_coherence_checker_prompt.md
```

## What Bill Should Do Before Building

These two things are prerequisites for the agents to work well. Neither requires
any code.

**1. Review and edit `config/styles.json`.** This is the canonical definition of
your four styles. The draft reflects everything we've discussed in conversation,
but *your* framework, so review it carefully. The agents anchor against this file
for every classification decision. If something feels wrong, fix it now — later
revisions will require re-running the agents.

**2. Backfill thesis files for your top 10 holdings.** One evening at your desk,
using the `thesis_template.md`. This serves two purposes:
   - The Add-Candidate Analyst reads thesis files to assess add priority. Without
     them it has to reason from ticker symbol alone.
   - The exercise of writing the theses is valuable in itself — you'll find 2-3
     where you don't remember exactly why you bought them, and that discovery is
     the point.

Top 10 by value from the current snapshot: UNH, GOOG, JPIE, AMZN, QQQM, VEA, XOM,
IGV, XBI, IFRA.

For EEM specifically (the one you just sold), write a retroactive thesis anyway —
the Re-buy Analyst needs it to produce a useful Re-Buy recommendation.

## What Bill Should Do During the Build

**3. Log the 18% cash rotation.** Before the first agent runs, log the rotation
that built the current dry powder. You need one Trade_Log entry per sell,
tagged as `type: dry_powder`, with the implicit bet and the redeployment trigger
in writing. This is the data the Re-buy Analyst reads. Without it, the agent has
nothing to close the loop on.

Template for the Trade_Log entry:
```
Date: [when you sold]
Type: dry_powder
Sold: [ticker, proceeds]
Bought: CASH
Implicit bet: "A pullback within [timeframe] will offer better entry points than
  current levels, especially in [categories]."
Redeployment trigger: [the condition that tells you to start working the buy list]
Notes: [any other context]
```

If you don't know the redeployment trigger yet, write "to be defined" — but
define it before the first Re-buy Analyst run. The point of the dry powder is
lost without a trigger.

## What Claude Code (or Gemini CLI) Should Do

The agent prompts in `agents/` are ready for direct use. Each one is a complete
system prompt. The implementation work is:

1. **Write `context_bundle.py`** — a Python module that assembles the bundle per
   the spec in `config/context_bundle_spec.md`. Reads from Google Sheets
   (Holdings_Current, Trade_Log), the Vault (thesis files), and
   `config/styles.json`. Produces a dict matching the bundle structure.

2. **Write `rebuy_analyst.py`** — CLI script that:
   - Calls `context_bundle.assemble("rebuy_analyst")`
   - Passes the bundle to `ask_gemini()` with the system prompt from
     `agents/01_rebuy_analyst_prompt.md`
   - Parses the JSON response (strict — reject non-JSON output)
   - Formats the candidates as markdown and appends to `buy_list.md` under
     Section 1, or writes to a review file for Bill to edit
   - Honors the existing DRY_RUN gate

3. **Write `add_candidate_analyst.py`** — same pattern, different agent prompt,
   different bundle contents. Writes to Section 2.

4. **Write `new_idea_screener.py`** — same pattern. Writes to Section 3. Takes
   candidate names from a CLI arg or config file (Bill specifies them).

5. **Write `list_coherence_checker.py`** — reads the full drafted `buy_list.md`,
   passes to the agent, writes the coherence report to the top of the file.

6. **Test each agent with DRY_RUN=True** against real bundle data before any
   Sheet writes are enabled.

## Non-Negotiable Architectural Rules (from project CLAUDE.md)

- SAFETY_PREAMBLE is auto-prepended by `ask_gemini()` — do NOT duplicate in
  agent system prompts.
- DRY_RUN defaults to True. Agents never write to authoritative Sheet tabs —
  only to the buy list markdown file or to an AI_Suggested_Allocation-style
  sandbox.
- Python gathers and calculates. LLM synthesizes. No LLM numerical outputs.
- Fingerprint dedup on every Sheet write. Single-batch gspread calls.
- `ask_gemini()` returns a Pydantic model instance requiring `.model_dump()`
  for serialization.
- `max_tokens` set to 4000 (sufficient for full agent output).

## After Phase 1 of the Kit Works

Once the four agents are running and producing a usable buy list, the next
logical extensions:

- **Weekly trigger monitor** — reads the current buy list and flags when any
  entry's trigger condition is approaching or hit. Purely deterministic,
  no LLM needed.
- **Thesis Memory agent** — on-demand, answers Bill's questions about current
  situations grounded in thesis files. The "smarter in the moment" tool.
- **Quarterly Thesis Drift reviewer** — reads transcripts against thesis files,
  updates the Review Log section of each `_thesis.md`.
- **Quarterly Rotation Review** — reads Trade_Log rotations and produces
  accounting on their outcomes. The discipline feedback loop.

Don't build these until the four buy-list agents are working. Each extension
depends on the thesis files and rotation log being populated.

## One Final Note on Discipline

The buy list's value is almost entirely in the fact that it's written *now*,
while you're calm, not during the pullback. The agents help you write it. They
don't replace the discipline of actually writing it. A buy list that's 60%
auto-generated but reflects your actual thinking is far more valuable than
a 100% auto-generated list you never edited.

Plan to spend 2-3 hours at your desk going through the agent outputs, editing
them, overriding them where they're wrong, and making the buy list *yours*.
That editing pass is the real discipline. The agents just save you the blank
page problem.

Sleep well. Review in the morning with fresh eyes.
