# Build Prompt: High-Signal Moment Extraction

**For:** Claude Code or Gemini CLI, working in this repo
**Created:** 2026-08-02
**Status:** Ready to execute after Step 0 passes

---

## Why this exists

The existing podcast path answers "what is the macro allocation view in this episode."
That is a *summarization* objective, and it systematically discards the thing that
actually generates ideas: a specific, falsifiable, non-consensus claim made by one
person at one moment.

This build adds a **second extraction pass with a different objective function** over
the same transcripts already on disk. It does not replace `PodcastStrategy` or modify
`analyze_podcast()`.

The scoring question is fixed and therefore scoreable: **does this change what Bill
holds, or what he would consider holding?** That is deliberately *not* a
generic-memorability rubric — a moving anecdote about a fund manager's childhood scores
high on a shareability scorecard and is worth nothing here.

**Division of labor:** Python does haystack-shrinking (deterministic, auditable,
diffable). Gemini does judging (not reducible to regex). Window selection must never be
an LLM call.

---

## Step 0 — Verification gate

**Do not write code until every item below is confirmed against the actual files.**
Findings from the 2026-08-02 audit are recorded so you can confirm or refute them, not
so you can trust them. If any item comes back different, **STOP and report** rather than
adapting silently.

| # | Claim to verify | Where | Expected (audit 2026-08-02) |
|---|---|---|---|
| 0.1 | `analyze_podcast()` signature has no position/thesis access | `utils/agents/podcast_analyst.py:57` | `analyze_podcast(transcript: str, source_name: str = "Unknown Podcast")` — confirmed no portfolio context |
| 0.2 | STEP 4 crosses a process boundary | `tasks/batch_podcast_sync.py:157` | `subprocess.run(cmd, ...)` shelling to `weekly_podcast_sync.py`; `podcast_analyst` is **not** imported here |
| 0.3 | Transcripts persist to disk | `tasks/weekly_podcast_sync.py:68-81` | Written to `data/podcast_transcripts/{date}_{slug}_{video_id}.txt` |
| 0.4 | **Timestamps are discarded** | `tasks/weekly_podcast_sync.py:56-57` | `full_text = " ".join([seg.text for seg in transcript_segments])` — `seg.start` / `seg.duration` dropped |
| 0.5 | Transcripts have no speaker names | any file in `data/podcast_transcripts/` | YouTube auto-caption `>>` markers denote speaker *changes*, not identities |
| 0.6 | STEP 9 has the position set | `tasks/export_ai_briefing.py:257-258` | `bundle["_market_data"]["positions"]` |
| 0.7 | STEP 9 has ticker→style from thesis frontmatter | `tasks/export_ai_briefing.py:677-679` | `build_style_map()` globs `vault/theses/*_thesis.md` |
| 0.8 | `build_podcasts_md()` reads summaries, not transcripts | `tasks/export_ai_briefing.py:~618, 1071` | Takes a days window; operates on `data/podcast_summaries/` |
| 0.9 | `idea_generator` already reads transcripts + bundle | `utils/agents/idea_generator.py:56, 112-168` | Consumes `data/podcast_transcripts/` + composite bundle via `ask_gemini_composite()` |
| 0.10 | Transcript corpus size | `data/podcast_transcripts/` | ~148 files as of 2026-08-01 |

### Two Step 0 findings that change the design

**0.4 is a blocker for the spec as originally written.** The `±90-second window` and
`transcript_offset` fields cannot be computed from the 148 transcripts already on disk —
the timing data was thrown away before the file was written. Consequences:

- **Windows must be character-offset based, not time-based**, for the existing corpus.
  Use `±1200 characters` around the cue hit (roughly 90 seconds of speech at ~160 wpm)
  and name the field `char_offset`, not `transcript_offset`. Do not invent a timestamp
  you cannot derive.
- A separate 3-line fix to `weekly_podcast_sync.py` can persist `seg.start` going
  forward (see Step 4, optional). It does **not** retroactively help; do not sequence
  this build behind it.

**0.5 weakens one cue.** "Explicit disagreement between named speakers" is not reliably
detectable — the transcripts carry `>>` speaker-change markers with no identities. Keep
the cue, but detect it as *speaker-change proximity to a contrastive marker* and set
`speaker` to the `>>` turn index (e.g. `"turn_47"`), never a guessed name. The
`moment_type: disagreement` tag stays; the `speaker` field must be honest about being
positional.

### The architecture decision Step 0 resolves

The original plan offered two options: extraction at STEP 4, or extraction at STEP 4 with
scoring moved to STEP 9. **Step 0 findings support a third option that is simpler than
either:**

> **Do the whole thing at STEP 9.** Transcripts are already durable on disk (0.3). The
> position set (0.6) and thesis style map (0.7) are already in hand at STEP 9. Nothing
> about moment extraction needs to happen inside STEP 4, and putting it there means
> crossing a `subprocess` boundary (0.2) that would force either an unwieldy CLI payload
> or a redundant Sheet read per episode.

Consequence: **`batch_podcast_sync.py`, `weekly_podcast_sync.py`, and
`podcast_analyst.py` are not modified by this build** (excepting the optional timestamp
fix). That is a meaningful reduction in blast radius on the pipeline's most fragile path.

**Also confirm before building (0.9):** `idea_generator.py` already reads the same
transcripts against the same bundle and emits `Candidate` objects. Moment extraction is
distinct — verbatim fragments and provenance, not synthesized candidates — but the two
must not silently become parallel systems. **If Step 0 finds material overlap, stop and
report it as a design question before writing code.**

---

## Step 1 — Cue-phrase windowing (`utils/moment_windows.py`)

Pure Python. No LLM calls. No network. Deterministic and unit-testable.

Header block per repo standard (purpose, inputs, outputs, dependencies).

```
def find_windows(transcript: str, cues: list[dict], radius: int = 1200) -> list[dict]
```

Returns non-overlapping windows (merge any that overlap) with `char_start`, `char_end`,
`cue_matched`, `cue_category`, `text`.

**Cue list** — conviction and reversal markers. Put these in
`data/moment_cues.json`, not hardcoded, so they can be tuned without a code change:

| Category | Patterns |
|---|---|
| `reversal` | `I've changed my mind`, `I was wrong about`, `we sold`, `we exited`, `used to think` |
| `non_consensus` | `the consensus is` … `but` (within 2 sentences), `nobody is talking about`, `the thing people miss`, `everyone thinks` … `but` |
| `position_disclosure` | `I own`, `we're long`, `we bought`, `my largest position`, `our biggest holding` |
| `specific_claim` | numeric-adjacent conviction — `trading at`, `multiple of`, `capex`, `margin`, `guidance` within ~120 chars of a ticker or company name |
| `disagreement` | contrastive marker (`I disagree`, `that's wrong`, `I'd push back`) within ~200 chars of a `>>` speaker-change marker |

Case-insensitive. Word-boundary anchored. **`specific_claim` requires a ticker/company
proximity test** — otherwise every sponsor read about a mattress company matches
`trading at`.

**Ticker resolution:** match against the held position set *plus* a company-name alias
map. Do not naively regex `[A-Z]{2,5}` — that matches `CEO`, `GDP`, `AI`, `ETF` and will
poison the output. Build `data/ticker_aliases.json` if one does not exist.

**Guardrail:** if a single transcript produces more than ~40 windows, the cue list is
too loose. Log a warning and truncate to the 40 highest-density windows rather than
sending a wall of text to Gemini.

---

## Step 2 — `MomentCandidate` schema + extraction agent (`utils/agents/moment_extractor.py`)

Pydantic, parallel to `PodcastStrategy` — **not replacing it**.

```python
class MomentCandidate(BaseModel):
    source_episode: str        # transcript filename, exact
    char_offset: int           # start offset in the source transcript (NOT a timestamp)
    fragment: str              # <=15 words, VERBATIM, no paraphrase
    speaker: str               # ">>" turn index, e.g. "turn_47" — positional, never a guessed name
    moment_type: Literal["reversal", "non_consensus", "position_disclosure",
                         "specific_claim", "disagreement"]
    tickers_touched: list[str]
    relevance: Literal["HELD", "THESIS_ON_FILE", "ADJACENT", "ZERO_EXPOSURE"]
    why_it_matters: str        # <=25 words, why it bears on holdings or candidates
```

**Relevance is resolved in Python, not by Gemini** — it is a lookup, and a model will
hallucinate it. Resolution order:

1. `HELD` — ticker in `bundle["_market_data"]["positions"]`
2. `THESIS_ON_FILE` — `vault/theses/{TICKER}_thesis.md` exists but not currently held
3. `ADJACENT` — either:
   a. appears in ETF look-through (`utils/etf_holdings.py`, disk-cached, no new network), **or**
   b. **the ticker or company name appears in the body text of any
      `vault/theses/*_thesis.md`** — e.g. a competitor named in a Key Risks section.
      Pure filesystem grep, zero new data. Record which thesis file matched.
4. `ZERO_EXPOSURE` — everything else

### ADJACENT design decision — resolved 2026-08-02, do not re-litigate

**The GICS-sector leg is dropped, and not because the data is missing.** Sector is
empty for all 38 held positions and cached for 2/38 elsewhere — but that is the lesser
problem. The real problem is that the sector leg is **wrong at this portfolio's
granularity**:

- 38 positions span nearly every GICS sector. A *working* sector match would resolve
  almost every mentioned ticker to `ADJACENT` and empty the `ZERO_EXPOSURE` subsection —
  the one section this entire build exists to populate.
- Therefore "use cached sector where present, self-improving as the cache fills" is
  actually **self-degrading**: every newly cached sector silently swallows more idea
  flow. Rejected.
- Bounded live FMP calls were also rejected — they buy correct resolution of a field
  whose *specification* is the defect, at the cost of touching the rate-limit path this
  build was explicitly designed to avoid.

**Accepted asymmetry:** a ticker wrongly landing in `ZERO_EXPOSURE` costs a slightly
noisier idea list. A real idea wrongly buried in `ADJACENT` is never seen at all. Bias
toward letting things fall through to `ZERO_EXPOSURE`.

**Known and accepted limitation:** ETF look-through is top-10 holdings only (documented
floor in `CLAUDE.md`), so leg 3a systematically under-catches. That is consistent with
the bias above and is not a bug to fix in v1.

**v2 reconsideration, only if `ZERO_EXPOSURE` proves too noisy in practice:** the useful
granularity is **sub-industry / named-competitor**, not sector — "direct competitor of a
held name" is informative, "also an industrial" is not. Log it that way. Do **not** log
this as a gap pending the FMP sector migration; re-adding sector as specified would make
the output worse, not better.

Have Gemini return the field but **overwrite it with the Python lookup**, and log any
disagreement. That gives a free running audit of how often the model gets it wrong.

**Real-world benchmark, 2026-08-02.** The Spotify aggregate digest now emits its own
LLM-generated relevance tags in a "Weighty Moments" section. On its first edition it got
**2 of 4 wrong** — tagging both `META` and `APO` as ZERO-EXPOSURE when both are held
(~2.2% each). The APO case delivered a named negative view on a live 2.21% position while
reporting it as not owned. This is not a hypothetical failure mode; it is the observed
base rate for LLM-assigned relevance on this exact task. **Do not let anyone "simplify"
by trusting the model's tag.**

**Prompt constraints for the Gemini call:**
- `fragment` must be verbatim and present in the supplied window — **validate this in
  Python and drop any candidate that fails**. This is the single most important guard
  against fabricated quotes.
- No price targets, no forecasts, no buy/sell language in `why_it_matters` (repo hard
  rule 4).
- Do not use `SAFETY_PREAMBLE` in the prompt — `ask_gemini()` auto-prepends it.
- Reject anything from sponsor reads, ads, or show logistics.

---

## Step 2b — Extraction is a cached step, NOT an export-time call

**Resolved 2026-08-02. Do not implement `build_moments_md()` as a per-window Gemini
call at export time, and do not gate that behavior behind a flag.**

`export_ai_briefing.py` documents a no-network-calls invariant. A `--moments {off,live}`
flag would preserve that only conditionally — the guarantee degrades to "no network
unless asked." Worse, the underlying shape is wrong on its own terms:

- **Transcripts are immutable once written, so their moments are immutable too.**
  Re-extracting the same windows on every export is repeated work with no new input.
- **It is nondeterministic.** The same transcript can yield different fragments across
  runs, so `podcasts.md` stops being diffable for unchanged inputs. That contradicts the
  repo's bundle-immutability discipline more deeply than the network call does.
- **Cost.** A 7-day window is ~10-20 transcripts x up to 40 windows — several hundred
  Gemini calls per daily export, redoing yesterday's work every morning.

### The split

| Concern | Where | Why |
|---|---|---|
| **Extraction** — windowing + Gemini fragment selection | New `tasks/extract_moments.py`, cached to `data/moments/{transcript_stem}.moments.json` | Expensive, position-**independent**, immutable given the transcript |
| **Relevance tagging** — HELD / THESIS_ON_FILE / ADJACENT / ZERO_EXPOSURE | Computed fresh at export from the cached moments | Cheap Python lookup, position-**dependent** |

**Relevance must NOT be written to the cache.** The position set is mutable — a moment
cached as `ZERO_EXPOSURE` in June may be `HELD` today (SKHY is the live example). Caching
the tag would silently rot. `MomentCandidate.relevance` is populated at read time, every
time.

### `tasks/extract_moments.py`

- Header block per repo standard.
- Iterates `data/podcast_transcripts/*.txt`; **skips any transcript with an existing
  `.moments.json`** — idempotent, so the ~148-file backfill happens once, deliberately,
  and daily runs process only the 2-5 new transcripts.
- `--force` to re-extract a named transcript (cue-list tuning), `--limit N` to bound a
  backfill run.
- Writes cached moments **without** the `relevance` field.
- Standalone CLI: `python manager.py extract-moments`. Wire into `manager.py morning`
  **after STEP 4 (podcast sync), before STEP 9 (export)** so new transcripts have
  moments by the time the export reads them.
- Failure is non-fatal: log and continue. A Gemini failure on one transcript must not
  break the morning pipeline.

Net effect: `export_ai_briefing.py` gains **no network calls and no new flag**, and its
existing docstring invariant stands unmodified.

---

## Step 3 — Render into `podcasts.md`

New `## High-Signal Moments` block, emitted by a `build_moments_md()` in
`export_ai_briefing.py` and appended by `build_podcasts_md()`.

**`build_moments_md()` is pure filesystem** — it reads `data/moments/*.json`, filters to
the `--days` window, applies the relevance lookup, ranks, and renders. No Gemini, no
network, no flag.

- Cap at **8 per day total**, split across the two subsections below.
- **`ZERO_EXPOSURE` moments get their own subsection**, `### Zero-Exposure Ideas`, so
  idea generation is not buried under confirmation of things already owned. This is the
  point of the whole build; do not let a ranking function bury it.

**Two rank orders, not one — the value of a moment type inverts with relevance.**

| Subsection | Rank order (highest first) |
|---|---|
| `### Zero-Exposure Ideas` | `position_disclosure` > `specific_claim` > `reversal` > `non_consensus` > `disagreement` |
| Main (HELD / THESIS_ON_FILE / ADJACENT) | `reversal` > `disagreement` > `non_consensus` > `specific_claim` > `position_disclosure` |

Rationale, so this is not "simplified" later into a single list:

- **`position_disclosure` is about the speaker's book, not Bill's.** A manager naming
  their largest position in a name Bill has zero exposure to is a conviction stake with
  their own money — the highest-value idea signal in the set. The same disclosure about
  a name Bill already holds is confirmation fodder and ranks last. One type, opposite
  value, determined entirely by the relevance tag.
- **`specific_claim` ranks second in zero-exposure** because a valuation fact on a
  non-held name ("trading at 4.5x," "capex guide cut") is the literal trigger pattern
  behind the SKHY and IBM entries.
- **`reversal` ranks first in the main section** because someone exiting a name Bill
  holds is a direct challenge to a thesis on file — the highest-value drift signal.

Implement as two static ordered lists keyed by subsection. Do **not** add conditional
scoring logic inside a single ranker.
- Each line: fragment in quotes, source episode, moment type, tickers, relevance tag.
- If zero moments clear the bar, print `(no high-signal moments in window)` — never pad.

**Follow existing conventions:** `to_ascii()` on all output, respect the `--days`
window, and stamp the block with the composite hash it was built against.

---

## Step 4 — Optional, separable: persist timestamps going forward

Three-line change in `tasks/weekly_podcast_sync.py` (~line 56):

```python
segments = [{"start": s.start, "dur": s.duration, "text": s.text}
            for s in YouTubeTranscriptApi().fetch(args.video_id)]
full_text = " ".join(s["text"] for s in segments)
# also write segments as {stem}.segments.json alongside the .txt
```

Keep writing the flat `.txt` unchanged so nothing downstream breaks
(`idea_generator.py`, `podcast_fetcher.py`). Then `char_offset` can be upgraded to a
real timestamp **for new episodes only**.

**Do this only after Steps 1–3 are working.** It is an enhancement, not a dependency.

---

## Post-build verification checklist

Demand literal stdout/stderr. **Do not accept a self-reported PASS table** — Gemini CLI
has a documented pattern of fabricating them.

- [ ] `find_windows()` unit tests pass, including: overlapping-window merge, the
      `specific_claim` ticker-proximity requirement, and a negative test proving a
      sponsor read does not match
- [ ] Ticker matcher does **not** match `CEO`, `GDP`, `AI`, `ETF`, `CPI`, `IPO`
- [ ] Run over the full existing corpus (~148 transcripts); report windows-per-transcript
      distribution. Investigate any transcript yielding >40
- [ ] **Verbatim validation demonstrated:** show at least one candidate correctly dropped
      because `fragment` was not found in the source window
- [ ] Relevance tags spot-checked by hand against the live position set (min. 5)
- [ ] Python-vs-Gemini relevance disagreement rate logged
- [ ] **`ZERO_EXPOSURE` share of total moments reported.** If it is under ~20%, the
      `ADJACENT` legs are over-catching and the build is failing its primary purpose —
      report rather than tune silently
- [ ] Leg 3b (thesis-body mention) demonstrated: show one moment correctly tagged
      `ADJACENT` via a competitor named in a thesis file, with the matching file named
- [ ] **All five `moment_type` values round-trip** — each of the five appears in at
      least one validated candidate across the corpus run. A category that never fires
      means its cue is broken; report rather than deleting the category
- [ ] Both rank orders verified distinct: confirm `position_disclosure` sorts **first**
      in `### Zero-Exposure Ideas` and **last** in the main section
- [ ] `## High-Signal Moments` renders in `podcasts.md` with a populated
      `### Zero-Exposure Ideas` subsection
- [ ] `PodcastStrategy` output is byte-identical to a pre-build run — this build must not
      perturb the existing path
- [ ] **`export_ai_briefing.py` makes zero network calls.** Demonstrate by running the
      export with network disabled (or with the Gemini key unset) and showing it
      completes with the `## High-Signal Moments` block populated from cache
- [ ] **No `--moments` flag exists.** The no-network invariant is structural, not opted
      into; confirm the existing docstring required no weakening
- [ ] **Idempotency:** re-running `extract-moments` immediately performs zero Gemini
      calls and leaves every `.moments.json` byte-identical
- [ ] **Relevance is absent from the cache files** — grep `data/moments/*.json` and show
      no `relevance` key is persisted
- [ ] **Relevance recomputes on position change:** take a cached moment mentioning a
      newly-opened position and show it renders as `HELD`, not the tag it would have had
      at extraction time
- [ ] Extraction failure on one transcript logs and continues without breaking
      `manager.py morning`
- [ ] No writes to `Target_Allocation`; no Schwab endpoints touched; no new vendor added
- [ ] `state.md` and `CHANGELOG.md` updated
- [ ] `PORTFOLIO_SHEET_SCHEMA.md` untouched (no new tabs in v1)

---

## Explicit non-goals

- Do **not** modify `PodcastStrategy`, `analyze_podcast()`, or the STEP 4 subprocess path
  (except the optional Step 4 above)
- Do **not** add a `--moments` flag to `export_ai_briefing.py`, and do **not** weaken its
  no-network-calls docstring — see Step 2b
- Do **not** call Gemini from `build_moments_md()` or from anything else inside the
  export path
- Do **not** persist `relevance` into `data/moments/*.json` — it is position-dependent
  and must be recomputed at read time
- Do **not** promote moments to any Sheet tab in v1 — markdown only
- Do **not** merge with `idea_generator` — if overlap looks material, report it as a
  design question first (Step 0.9)
- Do **not** score for general memorability, quotability, or narrative quality
- Do **not** let an LLM select windows
