# AI-track analyst — a second summariser that is not allowed to produce an allocation

**Created:** 2026-08-31
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 2 of 4.** **Depends on:** prompt 1 (registry with `track: "ai"`).
**Gates:** prompts 3 and 4.

> The existing summariser cannot carry this content, and the reason is structural rather than a matter
> of prompt wording. `weekly_podcast_sync.py` exits 1 when the model's `target_allocations` do not sum
> to 100, and `utils/agents/podcast_analyst.py` instructs the model to emit a GICS sector table
> whatever the input is. Feed it a DeepMind paper review and you get one of two outcomes: a hard
> failure, or a fabricated allocation table that passes validation and enters the bundle. `CLAUDE.md`
> already documents the second outcome as a defect — a qualitative Capital Allocators interview that
> produced "Broad Market, Target 100%, Range 95–105%, Confidence Low." Here the validator *requires*
> that fabrication. So: a sibling analyst, a different schema, a different output surface.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — the constraint this prompt exists to route around
grep -n "sum to" -B 4 -A 6 tasks/weekly_podcast_sync.py
grep -n "MUST sum to exactly 100" -B 2 -A 2 utils/agents/podcast_analyst.py

# 0.2 — the purge that makes data/podcast_summaries/ the wrong home
grep -n "KEEP_DAYS\|def purge_old_summaries" -A 12 utils/podcast_digest.py
grep -n "purge_old_summaries" tasks/weekly_podcast_sync.py

# 0.3 — the Gemini client contract (SAFETY_PREAMBLE is auto-prepended — never duplicate it)
grep -n "^def ask_gemini\|SAFETY_PREAMBLE" -A 6 utils/gemini_client.py | head -40

# 0.4 — the Spotify PROVENANCE / VERIFICATION strings, so the new ones do not collide
grep -n "PROVENANCE\|VERIFICATION" tasks/ingest_spotify_digests.py

# 0.5 — registry from prompt 1 is in place
python -c "from utils.channel_registry import load_channels as L; print([c['name'] for c in L('ai')])"

# 0.6 — token budget knob
grep -n "GEMINI_MAX_TOKENS_PODCAST" config.py
```

**Expected at 0.2 (verified 2026-08-31):** `KEEP_DAYS = 7`; `purge_old_summaries()` unlinks every
`data/podcast_summaries/*.md` whose filename date is older than the cutoff, **with no `--live` gate**,
and it is called from `weekly_podcast_sync.py` on every live run. That is the single reason AI briefs
do not live in that directory — they would be deleted on day 8 by a function nobody would think to
look at.

**Expected at 0.4:** `VERIFICATION_PENDING_MARKER = "VERIFICATION: PENDING"`. The new footer must not
reuse that exact string — it is the Spotify ingestion collision guard.

---

## Design decisions, already made — do not relitigate

**No allocation field exists in the schema.** Not "optional", not "empty when not applicable" —
absent. A field the model can see is a field the model will fill. This is the whole lesson of the
`## Sector Allocations` defect.

**No tickers, no positions, no sizing, ever.** Hard Rule 4 forbids price targets, market predictions
and buy/sell recommendations in any agent output. An AI-advancement brief that says "this favours
MU" has crossed that line, and it has done so on the basis of a YouTube video. The brief describes
*mechanism* — what was announced, what it can do, what it costs, who is competing — and stops there.
A ban enforced by a post-validator, not by hoping the prompt holds.

**Output goes to `data/ai_briefs/`, not `data/podcast_summaries/`.** Three reasons, all mechanical:
the 7-day unconditional purge (0.2); `write_summaries_from_sheet()` round-trips summaries through the
`AI_Suggested_Allocation` tab, which an AI brief has no business touching; and
`core/corpus/sources.py` registers `data/podcast_summaries/*.md` as `source_type="podcast_summary"`,
which is the wrong provenance badge.

**No Sheets write at all.** Not to `AI_Suggested_Allocation`, not to a new tab. Google Sheets is the
authoritative user-facing surface for the *portfolio*; AI-capability research is not portfolio state.
It is corpus material, and prompt 4 is where it becomes searchable.

**Disk writes still require `--live`.** Hard Rule 3 is about writes, not about Sheets. Dry run prints
the brief to stdout and writes nothing.

**Every brief carries a PROVENANCE stamp and a PENDING verification footer.** Same discipline as the
Spotify path, different marker string. This is model output summarising a video: a claim, not a datum.

**AI-track transcripts go to `data/podcast_transcripts/ai/`, not the flat directory.** This is the
one decision in this prompt that is not about the summariser, and it is the most important one.

`tasks/extract_moments.py` globs `data/podcast_transcripts/*.txt` — non-recursive — and
`run_extract_moments()` is called from the morning pipeline (`manager.py` ~line 2588). It runs
finance cue-phrase matching (`data/moment_cues.json`: reversals, conviction statements) and ticker
tagging (`data/ticker_aliases.json`) across every transcript it finds, writing `.moments.json` files
that are corpus-indexed as `source_type="moment"` and consumed by `ui/position_story.py` and
`core/analyst/plan.py`.

Drop AI transcripts into that flat directory and a Two Minute Papers video saying *"we've completely
changed our mind about scaling laws"* fires the reversal cue, gets tagged with whatever tickers its
alias map matches on a mention of Nvidia or Gemini, and surfaces as a conviction moment inside a
position story. That is model-generated noise entering a decision surface through a side door.

A subdirectory fixes it for free: every relevant glob — `extract_moments`, the corpus `transcript`
SourceSpec (`data/podcast_transcripts/*`), and `purge_obsolete_data` — is non-recursive, so a
subdirectory is excluded by all three with no code change. **Verify all three rather than trusting
this paragraph** — checklist items 13–15. Prompt 4 registers `data/podcast_transcripts/ai/*.txt` as
its own corpus source type so the transcripts stay searchable.

Pass `out_dir` to `fetch_transcript_to_file` — the function already takes it — rather than
reimplementing the naming.

---

## Step 1 — `utils/agents/ai_research_analyst.py`

A sibling to `podcast_analyst.py`. Same `ask_gemini` + Pydantic response-schema pattern; do not
duplicate `SAFETY_PREAMBLE` (the client prepends it).

```python
class Claim(BaseModel):
    claim: str            # one sentence, as the source states it
    claim_type: str       # capability | benchmark | release | cost | policy | opinion
    specificity: str      # named_figure | qualitative
    attributed_to: str    # speaker or organization the source attributes it to; "" if unattributed

class AIResearchBrief(BaseModel):
    headline: str                  # 6-10 words, the lead idea
    summary: str                   # 3-5 sentences, mechanism-level
    claims: List[Claim]            # 3-12
    named_systems: List[str]       # models, chips, frameworks named
    named_orgs: List[str]
    benchmarks: List[str]          # benchmark name + reported score, verbatim; [] if none
    open_questions: List[str]      # what the source asserts but does not evidence
    novelty: str                   # new_result | incremental | explainer | commentary
    source_quality: str            # High | Medium | Low
```

System instruction, condensed — the executor writes the full text but these constraints are
non-negotiable:

- Role: technical analyst summarising an AI-research video for a reader who tracks capability
  progress. **Not** an investment analyst.
- **Never name a public company as an investment implication.** Naming Nvidia as the maker of a chip
  the source discusses is a fact and is fine. "This is bullish for Nvidia" is forbidden.
- No allocation, no percentage of a portfolio, no buy/sell/overweight/underweight, no price target,
  no market forecast.
- `claims` are extracted **as the source states them**, not endorsed. A benchmark number the video
  asserts is `specificity: named_figure` and stays unverified.
- `novelty` is the honest classification: most uploads on most of these channels are `explainer` or
  `commentary`, not `new_result`. Do not inflate it — the field exists so prompt 4 can rank.
- Ignore sponsor reads, course promotions, Patreon appeals, and channel self-promotion.
- If the transcript carries no AI-technical content at all (a Fireship video on CSS, say), return
  `novelty: "commentary"`, `source_quality: "Low"`, empty `claims`. **Do not manufacture content to
  fill the schema.** An empty brief is a correct answer and prompt 3 will skip writing it.

## Step 2 — The post-validator, in Python, not in the prompt

`validate_brief(brief: dict) -> list[str]` returning violations. Called before any write. **A brief
with violations is not written; the violation list is printed and the video is left un-deduped so it
can be retried after a prompt fix.**

Checks:

1. No key anywhere in the payload matches `alloc|target_pct|min_pct|max_pct|weight`.
2. No string value matches, case-insensitively, `\b(buy|sell|overweight|underweight|price target|long|short)\b`
   **when it appears within 60 characters of a `$TICKER`-shaped token or a company name from
   `named_orgs`.** A bare "long context window" must not trip it — write the check to require
   proximity, and unit-test both the true positive and that false positive.
3. No `%` figure that is described as a portfolio or allocation share (`\d+(\.\d+)?\s*%` within 40
   characters of `portfolio|allocation|position|exposure`). Benchmark percentages are fine.
4. `claims` non-empty **or** `novelty == "commentary"` and `source_quality == "Low"`.
5. Every `claim_type` and `specificity` in its allowed set.

Rule 2 is the one that will be tempting to soften on a false positive. Do not soften it — tighten the
proximity window and add the case to the tests.

## Step 3 — `tasks/ai_track_sync.py`

Mirrors `weekly_podcast_sync.py`'s shape so it is recognisable, but writes a brief instead of an
allocation.

```
python tasks/ai_track_sync.py VIDEO_ID --source-name "Google DeepMind: <title>"          # dry run
python tasks/ai_track_sync.py VIDEO_ID --source-name "Google DeepMind: <title>" --live   # writes
```

Flow: fetch transcript → save to `data/podcast_transcripts/ai/` via
`fetch_transcript_to_file(video_id, source_name=…, out_dir=AI_TRANSCRIPTS_DIR)` — the function
already accepts `out_dir`; do not reimplement the slug logic → word count →
`analyze_ai_research()` → `validate_brief()` → print → gate on `--live` → write brief + JSON sidecar.

Word-count handling: warn above 12,000 words as the finance path does. **Below 300 words, skip
entirely** and exit 0 with a `SKIPPED: transcript too short (N words)` line — a 90-second clip cannot
support a brief and should not cost a Gemini call. Prompt 3's per-channel `min_words` overrides this
floor upward when set.

## Step 4 — Output format

`data/ai_briefs/YYYY-MM-DD_<Channel_slug>_<title_slug>_<video_id>.md`, plus a `.json` sidecar holding
the raw `model_dump()` next to it. Slug rules identical to `weekly_podcast_sync.py` (80-char cap) so
filenames stay consistent across the repo.

Markdown body:

```markdown
# <headline>

**Source:** <channel name>
**Video:** https://www.youtube.com/watch?v=<video_id>
**Published:** <feed publish date>   **Ingested:** <YYYY-MM-DD>
**Novelty:** <novelty>   **Source quality:** <source_quality>

*PROVENANCE: Model-generated brief. Gemini summary of a YouTube transcript from <channel name>.
Not reviewed. source_video_id: <video_id>. transcript_sha256: <sha>.*

## Summary
<summary>

## Claims
| # | Claim | Type | Specificity | Attributed to |
|---|---|---|---|---|

## Named systems
## Named organizations
## Reported benchmarks
## Open questions

*AI_BRIEF_VERIFICATION: PENDING (manual). No figure in this brief has been checked against a primary
source. Treat every benchmark number and capability claim as unconfirmed.*
```

**`AI_BRIEF_VERIFICATION: PENDING (manual)` is this path's collision guard** — deliberately distinct
from the Spotify `VERIFICATION: PENDING` string so a re-ingest check on one path can never match the
other. Never edit that line in place; a verification pass writes a sidecar (prompt 4).

`transcript_sha256` is the sha of the saved transcript file, and it is what a verification sidecar
chains to — the same one-chain-per-sha discipline the Spotify verification sidecars already follow.

## Step 5 — CLI

```python
@podcast_app.command("ai-brief")
def podcast_ai_brief(video_id: str, source_name: str = "Unknown AI Channel", live: bool = False)
```

Delegates to `tasks/ai_track_sync.py`. Nothing else in `manager.py` changes.

## Step 6 — Purge exclusion

Add `data/ai_briefs/` to nothing. That is the point: `purge_obsolete_data()` in `utils/hygiene.py`
touches `exports/`, `data/podcast_transcripts/` and `bundles/` only, and `purge_old_summaries()`
globs `data/podcast_summaries/*.md`. A new directory is untouched by both, which is the intended
retention: briefs are permanent, transcripts are not.

**Confirm this rather than assuming it** — checklist item 9.

---

## Verification checklist

**Paste literal stdout. An agent-reported PASS table is not evidence.**

| # | Check | Command / expected |
|---|---|---|
| 1 | Schema has no allocation surface | `python -c "from utils.agents.ai_research_analyst import AIResearchBrief as B; print(list(B.model_fields))"` — no `alloc`/`target_pct`/`weight` |
| 2 | Real dry run, real video | `python tasks/ai_track_sync.py <a Two Minute Papers ID> --source-name "Two Minute Papers: <title>"` — paste the full printed brief |
| 3 | Nothing written on dry run | `ls data/ai_briefs/ 2>/dev/null | wc -l` → `0` after check 2 |
| 4 | Live run writes both files | rerun with `--live`; `ls -la data/ai_briefs/` shows the `.md` and `.json` |
| 5 | PROVENANCE + footer present | `grep -c "PROVENANCE" <the .md>` → 1; `grep -c "AI_BRIEF_VERIFICATION: PENDING" <the .md>` → 1 |
| 6 | No Spotify guard collision | `grep -n "VERIFICATION: PENDING" <the .md>` — matches only inside the `AI_BRIEF_` line |
| 7 | Validator blocks a bad brief | hand-craft a payload containing "this is bullish for NVDA, go long"; `validate_brief` returns a violation naming rule 2 |
| 8 | Validator false-positive test | a payload containing "long context window" and "short training run" returns **no** violation |
| 9 | Purge leaves briefs alone | `python manager.py clean podcasts --days 1` (dry run) — report names zero files under `data/ai_briefs/`; then `python -c "from utils.podcast_digest import purge_old_summaries; purge_old_summaries()"` and confirm the brief still exists |
| 10 | Empty-content path | run against a non-AI Fireship video — brief comes back `novelty: commentary`, `source_quality: Low`, empty claims, and nothing is written |
| 11 | No Sheets call | `grep -n "gspread\|get_gspread_client\|worksheet" tasks/ai_track_sync.py` → no matches |
| 13 | **Moments do not eat AI transcripts** | after a live run: `python manager.py extract-moments` (dry run) — output names **zero** files under `data/podcast_transcripts/ai/`; `ls data/moments/ \| wc -l` unchanged |
| 14 | Corpus does not double-index them | `python manager.py corpus index --live` — `transcript` count unchanged from before the AI run |
| 15 | Purge does not reach them | `python manager.py clean podcasts --days 1` (dry run) — report names zero files under `data/podcast_transcripts/ai/` |
| 16 | Transcript still lands | `ls data/podcast_transcripts/ai/` shows the fetched `.txt`, and the brief's `transcript_sha256` matches `sha256sum` of that file |
| 12 | Tests | `python -m pytest tests/ -q` |

---

## Documentation to update on completion

- **`CLAUDE.md`** — `tasks/ai_track_sync.py` and `utils/agents/ai_research_analyst.py` in Key Files.
  Under Podcast & Third-Party Source Ingestion, a **Path 3** subsection: AI-track briefs, why they do
  not pass through the allocation summariser, and the distinct `AI_BRIEF_VERIFICATION` guard string.
  Under Hard Rule 4, a line that the AI track is mechanism-only and enforced by `validate_brief()`.
- **`state.md`** — dated entry with the first real brief's output.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- Batch orchestration across channels. Prompt 3.
- Corpus registration or the cross-source analysis run. Prompt 4.
- Any verification pass. Briefs ship PENDING; verification is a separate manual discipline and it is
  the thing that has historically caught the errors.
- Editing `utils/agents/podcast_analyst.py` or `tasks/weekly_podcast_sync.py`. The finance path is
  working and is not in scope. If the AI schema suggests an improvement to the finance one, write it
  down for Bill — do not implement it here.
- A `## Sector Allocations` section in the brief template, in any form, for any reason.
