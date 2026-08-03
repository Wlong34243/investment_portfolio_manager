# Build Prompt: Moment Extraction v2 — Fragment Context & Yield Fix

**For:** Claude Code, working in this repo
**Created:** 2026-08-02
**Depends on:** `prompts/moment_extraction_2026-08-02.md` (v1, shipped and working)
**Status:** v1 is mechanically correct. This fixes an output-quality defect in the v1 *spec*.

---

## What v1 got right — do not touch these

Audited 2026-08-02 against the live build. All four hard invariants hold:

- No `--moments` flag on `export_ai_briefing.py`; the no-network docstring stands
- No Gemini or network calls anywhere in the export path
- `relevance` is **not** persisted; `gemini_relevance_guess` is cached separately and the
  authoritative tag is computed at read time. **This design is correct — keep it.**
- Cache is idempotent; `PodcastStrategy` path untouched

**This is a targeted fix, not a rebuild.** Do not refactor working code.

---

## The defect

Across 66 cached transcripts: **19 moments total, 52 transcripts (79%) yielding zero.**
Only 3 `ZERO_EXPOSURE` — 15.8%, below the 20% floor v1's own checklist named as the
failure threshold. `ADJACENT` is 47% of guesses.

**Root cause is the v1 spec's `fragment` constraint of <=15 words verbatim.**
Conversational speech does not carry a complete claim in fifteen words. Real output:

| Cached fragment | Problem |
|---|---|
| `"And we bought it in January"` | Bought *what*? Referent is in the prior sentence |
| `"So I think the number on 2027 is likely closer to 1.5 trillion."` | The number of *what*? |
| `"I own two software stocks."` | Does not say which |
| `"I disagree. So maybe everyone's just looking in the wrong spot."` | About *what*? |

The verbatim rule is the correct anti-hallucination guard and it is working — a real
fabricated-fragment drop was demonstrated. **It simply cannot also be the payload.**

Corroborating evidence that the model understands the window fine and only the *fragment
selection* is starved: the cached `why_it_matters` values are consistently more
informative than the fragments they describe. Example, same record:

- `fragment`: `"what is happening to forward guidance is really what is the driver"`
- `why_it_matters`: `"The speaker claims forward guidance is the primary driver of stock
  prices, explaining the high valuations for AI and semiconductor stocks."`

The comprehension is there. The quote is what is unusable.

### Secondary defect — false positives with no portfolio hook

Three of nineteen have empty `tickers_touched` and no held-name reference:

- `"when we bought a big great property in Myrtle Beach, South Carolina"` — tagged
  **HELD**, from a hotel private-equity discussion. No relationship to the book.
- `"I'm more trying to predict like what are the humans going to do?"` — tagged
  `non_consensus` + `ZERO_EXPOSURE`
- `"People used to think that humans were you know you can't kind of make more humans"` —
  tagged `reversal`; it is philosophical musing about AI, not a position change

### Tertiary — `speaker` is not populating

Every cached record carries `speaker: "unknown"`. The v1 spec called for a `>>` turn index
(e.g. `"turn_47"`). Either the marker is absent from these transcripts or the index is not
being computed. Diagnose; if `>>` markers genuinely are not present in the corpus, say so
and drop the field rather than shipping a column that is always `"unknown"`.

---

## Step 0 — Diagnostic gate. Run this BEFORE changing anything.

The fix differs depending on where the loss occurs, and this has not been measured.

Write a throwaway diagnostic (do not commit it) that, over the 66 transcripts already
cached, reports per transcript:

1. **Windows found** by `find_windows()` — note the real signature is
   `find_windows(transcript, cues: list[dict], radius=1200, ticker_aliases=None)` and
   `cues` must be the **flattened list from `load_cues()`**, not the raw
   `moment_cues.json` dict.
2. **Windows sent to Gemini**
3. **Candidates returned**
4. **Candidates dropped**, split by reason: verbatim-validation failure, empty fragment,
   schema/parse failure, model returned nothing

Then report totals and this ratio:

> **If windows/transcript is high (>10) and survivors are ~0.3 — the judge is
> over-rejecting. Fix the prompt, not the cues.**
> **If windows/transcript is near zero — the cue list is too tight. Fix
> `moment_cues.json`, not the prompt.**

**STOP and report the numbers before proceeding.** Do not tune both levers at once — you
will not know which one worked.

---

## Fix 0 — Cue recall. ADDED 2026-08-02 after the Step 0 diagnostic. Do this FIRST.

Diagnostic result: **0.41 windows/transcript, 50/66 transcripts finding zero.** That is
~27 windows producing 19 moments — **the judge is accepting ~70% and is not the problem.**
All loss is at windowing.

**The v1 caution "do not tune both levers at once" is hereby discharged.** It existed to
protect attribution while the failing stage was unknown. The diagnostic has identified it.
Attribution is now preserved by *instrumentation* (below), not by serialization.

### 0a — The ticker-proximity gate is a structural bug, not a tuning parameter

Corpus evidence, 147 transcripts:

| Symbol | Hits | Name | Hits |
|---|---|---|---|
| `NVDA` | **0** | Nvidia | 27 |
| `AMZN` | **0** | Amazon | 23 |
| `MSFT` | **0** | Microsoft | 17 |
| `AAPL` | **0** | Apple | 36 |

Spoken podcasts use company names, never tickers. `ticker_aliases.json` covers this — but
**only for the 37 held positions.** Therefore `specific_claim`'s "ticker within ~120 chars"
requirement can only fire adjacent to a name Bill already owns.

**This structurally prevents ZERO_EXPOSURE discovery — the build's primary purpose.**
Confirmation: Floor & Decor surfaced only via `"I own"` (no proximity gate), never via a
valuation claim.

Throttling evidence: `"capex"` appears in **33** transcripts and `"trading at"` in **22**,
yet `specific_claim` produced **6** moments.

Required changes:

1. **Expand `ticker_aliases.json` well beyond held names.** At minimum the S&P 500 by
   company name; ideally S&P 500 + Nasdaq 100 + common ADRs. Held-only aliases make
   zero-exposure discovery impossible by construction. Generate the list programmatically
   and commit it; do not hand-curate 500 entries.
2. **Relax proximity from ~120 chars to sentence-or-clause scope**, or to the full window.
3. **Add a fallback proper-noun heuristic** for names outside the alias list: a
   capitalized multi-word token adjacent to a valuation term is a candidate ticker
   reference. Let the judge resolve it — the Python layer only needs to decide the window
   is worth *looking* at. Windowing is a recall stage; precision is the judge's job.

### 0b — Five cue patterns match nothing corpus-wide

Zero hits across 147 transcripts: `"we exited"`, `"I've changed my mind"`,
`"I was wrong about"`, `"nobody is talking about"`, `"the thing people miss"`.

These are written-English phrasings. Replace/supplement with spoken variants — e.g.
`"turns out I was wrong"`, `"I kind of changed my mind"`, `"we got out of"`, `"we're out of"`,
`"nobody's talking about"`, `"what people are missing"`, `"I used to think"`,
`"I don't think that anymore"`. Benchmark: `"I own"` hits 14 transcripts and carried most
of v1's output because it is how people actually speak.

Keep the dead patterns in the file — they cost nothing and may hit a future transcript.

### 0c — Instrumentation, so both levers can move in one pass

`extract_moments.py` must log and persist per run:

- `windows_found` per transcript (pre-Gemini — moves **only** with Fix 0)
- `windows_sent` and `candidates_returned` (acceptance rate — moves **only** with the judge)
- `dropped_by_reason`: verbatim-fail, empty-fragment, no-portfolio-hook (moves **only**
  with Fix 2)

Because each stage has an independently observable metric, Fix 0 and Fixes 1-3 can ship
together without confounding. **Report all three metric groups in the checklist.**

### 0d — Guardrail

Fix 0 raises recall and will raise Gemini spend per transcript. v1's guardrail stands: if
any transcript exceeds ~40 windows, log a warning and truncate to the 40 highest-density
windows. **Validate Fix 0 against a 10-transcript sample and report the new
windows/transcript figure before backfilling anything.**

---

## Fix 1 — Add a `context` field (the primary precision fix)

Extend `MomentCandidate`:

```python
    fragment: str    # <=15 words, VERBATIM — provenance anchor, unchanged
    context: str     # 400-800 chars of VERBATIM transcript centered on the fragment
```

- `context` is **sliced in Python from the source transcript**, not generated by Gemini.
  It cannot hallucinate because the model never writes it.
- Center on `char_offset`; snap outward to sentence boundaries where cheap.
- Validate that `fragment` is a substring of `context`. If not, drop the candidate — this
  is a stronger version of the existing verbatim check and subsumes it.
- Keep `why_it_matters` — it is working.

**Cache schema version.** Add a top-level `schema_version: 2` to each cache file, and have
`extract_moments.py` treat any file lacking it as stale and eligible for re-extraction.
Without this the 66 existing files silently persist without `context`.

---

## Fix 2 — Drop moments with no portfolio hook

In the Python post-processing, after relevance resolution, drop any candidate where **all**
of the following hold:

- `tickers_touched` is empty, **and**
- no held ticker or company alias appears in `context`, **and**
- `moment_type` is not `reversal` (a genuine macro reversal can be portfolio-relevant
  without naming a ticker — but see below)

For a ticker-less `reversal` to survive, require that `context` contain at least one macro
term from a small configurable list in `moment_cues.json` (`rates`, `inflation`,
`the Fed`, `credit`, `recession`, `the long end`, etc.). Musings about humanity do not
clear that bar; a Fed-path reversal does.

Expected effect on the current corpus: removes 3-4 of 19.

---

## Fix 3 — Render `context` in `podcasts.md`

In the `## High-Signal Moments` block, each entry becomes:

- **Line 1:** the verbatim `fragment` in quotes — the hook
- **Line 2:** `why_it_matters` — the model's read
- **Line 3, indented/blockquoted:** a trimmed `context` excerpt, ~200-300 chars, so the
  claim is legible without opening the transcript
- **Line 4:** source episode, moment type, tickers, relevance tag

Keep both rank orders and the 8/day cap unchanged.

---

## Do NOT run the remaining 81 transcripts yet

Schema v2 means the 66 already cached must be re-extracted regardless. Extracting the
remaining 81 under v1 buys data that will be discarded. Sequence:

1. Step 0 diagnostic → report
2. Fixes 1-3
3. Re-extract a **10-transcript sample** and inspect output by hand
4. Only after that sample looks usable, backfill the rest at Bill's chosen pace via
   `--limit`

---

## Post-build verification checklist

Literal stdout/stderr. No self-reported PASS tables.

- [x] ~~Step 0 diagnostic reported before tuning.~~ **Done 2026-08-02:** 0.41
      windows/transcript, 50/66 zero, ~70% judge acceptance. Verdict: cue-list recall.
- [x] ~~Only one lever tuned.~~ **Superseded** — see Fix 0. Both levers ship together;
      attribution preserved by per-stage instrumentation (Fix 0c).
- [ ] **Fix 0c metrics reported in all three groups** — `windows_found`,
      acceptance rate, `dropped_by_reason` — so each fix's effect is separately attributable
- [ ] **`ticker_aliases.json` expanded beyond held names** and generated
      programmatically; show the entry count before and after
- [ ] **Zero-exposure discovery proven possible:** demonstrate one `specific_claim`
      window firing on a company Bill does **not** hold. Under v1 this was structurally
      impossible — this single test is the point of Fix 0
- [ ] New `windows_found` per transcript reported against the 0.41 baseline
- [ ] No transcript exceeds the ~40-window truncation guardrail without logging it
- [ ] `context` is Python-sliced from source — show the code path proving Gemini never
      writes it
- [ ] `fragment in context` validation demonstrated, including one real drop
- [ ] `schema_version: 2` present; a v1 file is correctly detected as stale
- [ ] Ticker-less-moment filter demonstrated on the Myrtle Beach hotel record
      specifically — it must not survive
- [ ] `speaker` either populates with real turn indices or is removed with a stated reason
- [ ] **10-transcript re-extraction sample pasted in full for human review.** This is the
      real acceptance test — unit tests cannot tell you whether a moment is worth reading
- [ ] Yield reported: moments/transcript and `ZERO_EXPOSURE` share. Compare against v1's
      0.3 and 15.8% baselines
- [ ] Export still makes zero network calls; still no `--moments` flag
- [ ] `state.md` / `CHANGELOG.md` updated

---

## Non-goals

- Do not rebuild v1. The architecture, caching split, and read-time relevance resolution
  are correct.
- Do not relax the verbatim rule on `fragment` — add context alongside it.
- Do not let Gemini generate `context`.
- Do not widen cues and loosen the judge in the same pass.
