# AI-track corpus registration and the AI Watch run — the second analysis

**Created:** 2026-08-31
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 4 of 4.** **Depends on:** prompts 1–3. Needs real briefs on disk from prompt 3's backfill.
**Gates:** nothing.

> Bill asked for "two analysis." The first already exists and is not touched here: the finance track
> summarises into `AI_Suggested_Allocation`, `data/podcast_summaries/`, and from there into
> `podcasts.md` in the hash-stamped bundle. This prompt builds the second: a periodic cross-source
> read of the AI briefs that answers *what changed in AI capability this period, what is contested,
> and what is asserted without evidence.* It never merges with the first, and its output never
> reaches the bundle.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — real briefs exist to analyse
ls data/ai_briefs/*.md | wc -l
ls data/ai_briefs/*.json | wc -l
head -25 "$(ls data/ai_briefs/*.md | head -1)"

# 0.2 — the corpus source registry, and how model output is flagged
sed -n '188,222p' core/corpus/sources.py
grep -n "is_model_output\|source_type" core/corpus/search.py | head -20

# 0.3 — SourceSpec's actual field order (do not guess it from the call sites)
grep -n "class SourceSpec" -A 15 core/corpus/sources.py

# 0.4 — corpus index status before the change
python manager.py corpus status

# 0.5 — the agent output convention this run must follow
ls agent_outputs/
grep -n "UI_WRITE_ROUTE_ALLOWLIST" -A 3 ui/app.py

# 0.6 — the composite bundle's file list, to prove ai_briefs is not in it
grep -rn "podcasts.md\|podcast_summaries" core/vault_bundle.py core/composite_bundle.py tasks/export_ai_briefing.py | head
```

**Expected at 0.6:** `podcasts.md` is assembled from `data/podcast_summaries/`. **`data/ai_briefs/`
must appear nowhere in that output.** If it does, prompt 2 was implemented wrongly and this prompt
stops until that is fixed — AI-capability briefs entering the hash-stamped portfolio bundle would
repeat the one unreviewed-input exposure `CLAUDE.md` already flags, in a second place.

---

## Design decisions, already made — do not relitigate

**AI briefs are corpus material, not bundle material.** Searchable via `pm corpus search` and the
desk `/search` page, with a *model output* provenance badge. Never in `podcasts.md`, never in the
composite hash, never on a Sheet.

**The AI Watch run is a Tier-0 sandbox agent.** Output to `agent_outputs/ai_watch/` as local
markdown. No Sheets write, no promotion path, no UI write route. Hard Rule 5 without an exception.

**It reads briefs, not transcripts.** The briefs are already the structured extraction; re-reading
raw transcripts would double the token cost and reintroduce the sponsor-read noise the analyst
already stripped.

**Theme deduplication is the core requirement, not a nicety.** Nine channels covering the same week
of AI news will describe one model release five times. The Spotify lesson is on record in `CLAUDE.md`
— decomposition once made one digest look like three agreeing sources, and consecutive digests
repeated each other. **Count a theme once across the run, and name every source that carried it.**
Five channels covering one launch is one theme with five sources, not five findings.

**Zero-exposure reporting is an explicit output section.** Bill's standing instruction is that he uses
this system partly to find ideas, so tell him what is *not* covered as readily as what is. For the AI
track that means: which of the nine channels published nothing this period, and which named systems
appeared in exactly one source.

**Still no tickers, still no positions.** `validate_brief`'s rules apply to the run's output too —
reuse the validator rather than writing a second one. An AI Watch report that says "this favours the
memory cycle" has crossed the line Hard Rule 4 draws, and it would be crossing it on the strength of
nine YouTube channels.

---

## Step 1 — Register the source type

In `core/corpus/sources.py`, add to `SOURCES`:

```python
SourceSpec("ai_brief", "data/ai_briefs/*.md", _read_markdown, False, True),
```

Confirm the positional order against Step 0.3 before writing it — the last positional is the
model-output flag, which must be `True` so `search.py`'s badge logic (line ~207) treats an `ai_brief`
hit as a claim. **Extend that line's tuple rather than adding a parallel check**: it currently reads
`hit.is_model_output or hit.source_type in ("podcast_summary", "agent_output")`.

And, so the AI transcripts prompt 2 diverted into a subdirectory stay searchable:

```python
SourceSpec("ai_transcript", "data/podcast_transcripts/ai/*.txt", _read_plain, False, False),
```

`is_model_output=False` — a transcript is a record of what was said, not model output. The existing
`transcript` spec globs `data/podcast_transcripts/*` non-recursively and therefore does not reach the
subdirectory; confirm that rather than assuming it (checklist item 15).

Do **not** register `data/ai_briefs/*.json`. The sidecar is the same content in a machine shape;
indexing both doubles every hit.

The `verification/` exclusion in `iter_source_files` is path-based (`"/verification/" in rel`) and
therefore already covers `data/ai_briefs/verification/` when Step 4 creates it. Confirm, do not
assume — checklist item 4.

## Step 2 — `utils/agents/ai_watch.py`

Deterministic gather, single LLM narration, sandbox write. Same spine as
`utils/agents/valuation_drift.py`: Python measures, the model narrates.

**`utils/agents/`, not a new `core/analysis/` package.** `core/` holds `analyst/` — the grounded Q&A
retrieval path — and a sibling named `analysis/` would be a permanent source of confusion between two
unrelated things. The agent that this most resembles, `valuation_drift`, lives in `utils/agents/`.

```python
def gather(days: int = 7) -> AIWatchInput      # reads data/ai_briefs/*.json in the window
def run(days: int = 7, live: bool = False) -> Path | None
```

`gather` is pure Python and does the counting, because counting is the part an LLM gets wrong:

- Briefs in the window, by channel. **Channels with zero briefs are recorded explicitly** — that is
  the zero-exposure signal.
- Claim inventory across briefs: every `claim` with its `claim_type`, `specificity`, `attributed_to`
  and source file.
- `named_systems` frequency across briefs, with the source list per system.
- Candidate theme clusters: systems or orgs appearing in ≥2 briefs. **Python proposes the clusters
  from co-occurrence; the model names and describes them.** Do not ask the model to do the counting.
- Every `novelty: "new_result"` brief, listed separately.
- Contradiction candidates: two briefs carrying a `named_figure` claim about the same benchmark or
  system with differing numbers.

One `ask_gemini()` call over that structure. The model writes prose; it does not get to change a
count. Where the narration states a number, it comes from `gather`.

Report sections, fixed:

1. **What is new** — `new_result` briefs only, one paragraph each, with source.
2. **Themes this period** — deduplicated clusters, each naming every source that carried it and the
   count. A theme carried by one source is labelled single-source.
3. **Contested** — the contradiction candidates, both figures shown, neither adjudicated.
4. **Unverified specifics** — every `named_figure` claim, flagged as unchecked. This is the section
   that earns its keep; it is the AI-track equivalent of the verification pass that caught the JPIE
   4.7%-vs-0.83% error on the finance side.
5. **Quiet channels** — zero-brief channels and single-source systems.

Output: `agent_outputs/ai_watch/YYYY-MM-DD_ai_watch.md`, with a PROVENANCE stamp naming the brief
files and the window. `--live` gates the write; dry run prints.

## Step 3 — CLI

```python
@agent_app.command("ai-watch")
def agent_ai_watch(days: int = 7, live: bool = False)
```

Match the existing `pm agent valuation-drift` registration pattern exactly. **Do not add a UI route
or a `ui/routines.py` registry entry** — the desk launch policy admits regenerable computed surfaces
and Bill's own authored input; a batch Gemini recompute is neither, and the policy says new routines
are judged against that sentence rather than against precedent.

## Step 4 — Verification sidecars for briefs

Mirror the Spotify discipline exactly, because it is the discipline that has caught real errors.

`data/ai_briefs/verification/<brief_basename>_VERIFIED_<YYYY-MM-DD>.md`, **one chain per
`transcript_sha256`**. A brief whose sha already has a sidecar is not re-verified from scratch; a
later re-check writes a `_delta.md` sidecar that names the prior file and records only new or
corrected claims.

This prompt builds the **path and the naming**, not an automated verifier. Verification is manual and
web-search-based, and it stays that way: it is the step where a benchmark number gets checked against
the primary source. Ship a template and a `pm podcast ai-verify --brief <path> --scaffold` command
that emits the empty sidecar with the claims table pre-populated from the JSON sidecar, ready for
Bill to fill.

**Never edit a brief's own `AI_BRIEF_VERIFICATION: PENDING (manual)` line** — same rule, same reason,
as the Spotify footer: it is the collision guard.

## Step 5 — Desk search surface

`ui/corpus_search.py` renders provenance badges per hit. An `ai_brief` hit must render as **model
output**. If the badge mapping is a dict keyed by `source_type`, add the key; if it falls through to
`is_model_output`, Step 1 already handled it. Read the code and do whichever is true — checklist
item 7.

---

## Verification checklist

**Paste literal stdout. An agent-reported PASS table is not evidence.**

| # | Check | Command / expected |
|---|---|---|
| 1 | Briefs indexed | `python manager.py corpus index --live` then `python manager.py corpus status` — `ai_brief` count equals `ls data/ai_briefs/*.md \| wc -l` |
| 2 | Searchable | `python manager.py corpus search "<a system named in a brief>"` — returns the brief with path:line |
| 3 | Badged as model output | that hit renders flagged as model output, not as authoritative |
| 4 | Sidecars excluded | create `data/ai_briefs/verification/x_VERIFIED_2026-08-31.md`, re-index, confirm it is **not** indexed |
| 5 | JSON not indexed | `ai_brief` count did not double |
| 6 | Bundle untouched | `python tasks/export_ai_briefing.py` (there is no `pm export ai-briefing` verb — `export_app` has `sheets`/`list`/`run`/`cleanup`/`inspect` only) then `grep -rc "ai_briefs" <newest exports/ai_briefing_*/manifest>` → `0` |
| 7 | Desk search badge | screenshot or literal HTML snippet of an `ai_brief` hit on `/search` |
| 8 | Counts are Python's | `python -c "from utils.agents.ai_watch import gather; g=gather(7); print(g.briefs_by_channel, g.zero_brief_channels)"` — paste it, then confirm the narration's numbers match |
| 9 | Dry run writes nothing | `python manager.py agent ai-watch --days 7` then `ls agent_outputs/ai_watch/ 2>/dev/null \| wc -l` → `0` |
| 10 | Live run | rerun `--live`; paste the **full report** |
| 11 | Theme dedup works | in that report, a launch covered by ≥2 channels appears **once**, naming every source. If every theme is single-source, say so — do not present that as success |
| 12 | No tickers | run `validate_brief`'s rule-2 check over the report text — zero violations |
| 13 | No Sheets, no UI route | `grep -n "gspread\|worksheet" utils/agents/ai_watch.py` → none; `grep -n "ai.watch" ui/routines.py` → none |
| 15 | AI transcripts indexed once | `ai_transcript` count equals `ls data/podcast_transcripts/ai/*.txt \| wc -l`; `transcript` count unchanged from Step 0.4 |
| 16 | No moment leakage | `select count(*) from corpus_docs where source_type='moment' and path like '%/ai/%'` → `0` |
| 14 | Tests | `python -m pytest tests/ -q` |

Item 11 is the honest one. If the first live report shows nine channels producing nine unrelated
single-source themes, the clustering is not working or the channel set is too broad — report that
plainly rather than presenting a list of nine findings as a successful run.

---

## Documentation to update on completion

- **`CLAUDE.md`** — `utils/agents/ai_watch.py` in Key Files; `ai_brief` in the corpus source list;
  `agent_outputs/ai_watch/` in the `agent_outputs/` row. Under Bundle Architecture, one sentence that
  the AI track is corpus-only and deliberately outside the composite bundle — the counterpart to the
  `podcasts.md` exception already documented there.
- **`state.md`** — dated entry with the first real report's counts.
- **`PORTFOLIO_SHEET_SCHEMA.md`** — no change. Say so in the completion note rather than leaving it
  ambiguous; nothing here touches a tab.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- Any link between the AI track and portfolio positions: no ticker mapping, no exposure scoring, no
  "AI capex implications" section. That is Bill's inference to draw, and Hard Rule 4 is why.
- An automated verifier. Scaffold only.
- A UI route or desk routine.
- Merging the two analyses into one report. They have different provenance, different trust and
  different cadence. Two reports.
- Retention or purge for `data/ai_briefs/`. Briefs are permanent by design; revisit when the directory
  is large enough for it to matter.
