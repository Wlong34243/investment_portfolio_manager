# Build Prompt: Idea Generator — Source Clustering + Spotify Aggregate Ingestion

**Author:** Claude (chat), 2026-08-13
**Executor:** Cursor / Grok 4.5
**Prompt version:** 1.1.0 (audited against the repo 2026-08-13 after v1.0.0;
see "Audit corrections" below — v1.0.0 contained one instruction that would have
made the report worse, do not execute a v1.0.0 copy if one is in circulation)
**Severity:** Medium — no wrong numbers reach Bill, but the agent's output is
misleading by construction on multi-name-per-source days, currently blind to one
entire source category, and emits at least one ticker as a portfolio "overlap"
that Bill does not hold.

## Audit corrections applied in v1.1.0

Recorded so the executor knows which parts were re-verified rather than assumed:

1. **Primary-ticker selection no longer prefers un-held names.** v1.0.0 said to
   prefer a ticker the investor doesn't hold. Combined with `_sort_key()`
   (`idea_generator.py:203-217`), which sorts candidates with an empty
   `current_holdings_overlap` into group 0 — the top of the report — that would
   have promoted the already-held-adjacent financing cluster to the head of the
   list. It currently sorts correctly into group 2. See Step 3.1.
2. **Glob claim corrected.** v1.0.0 claimed a naive glob would pick up
   `verification/`. It does not: `Path('data/podcast_summaries').glob('*Spotify_Podcast_Aggregate*.md')`
   is non-recursive and returns exactly the 5 digests; only `rglob` returns 12
   and pulls in sidecars. Also `data/podcast_summaries/archive/` **does not
   exist** — only `verification/` does.
3. **A 2026-08-13 aggregate exists and already has a sidecar.** See Background #5.
4. **New in-scope bug found during audit:** `current_holdings_overlap` emits
   non-held tickers. See Step 3.4.
5. **Prompt-size risk checked and dismissed** — no token-budget change needed.
   See Background #8.

## Objective

Two related defects in `utils/agents/idea_generator.py`, found by inspecting the
2026-08-13 `ideas_*.md` report against its own source transcripts:

1. **No source clustering.** One On The Tape episode (2026-08-12, Sonali Basak)
   named six counterparties in a single $500B Nvidia financing consortium — APO
   (already held), BLK, BN, BX, GS, KKR. The generator emitted five near-identical
   candidates, one per ticker, each repeating the same thesis paragraph and the
   same `Overlaps with: APO` caveat. This is the "one source, one theme" violation
   the podcast-summary pipeline already guards against for the Spotify aggregate
   (`prompt.md` rule 9 / `CLAUDE.md`) — the idea generator has no equivalent rule.
2. **The Spotify aggregate digest is never read.** `TRANSCRIPTS_DIR` in
   `idea_generator.py:56` points only at `data/podcast_transcripts/` (raw YouTube
   transcripts). `data/podcast_summaries/*Spotify_Podcast_Aggregate*.md` — which
   carries its own "Actionable ideas" section (e.g. the 2026-08-12 edition: VST
   add, NOW watch, ES watch) — is invisible to this agent. Separately, that
   digest's own claims have already been fact-checked by a human-in-the-loop
   verification pass (`data/podcast_summaries/verification/*_VERIFIED_*.md`,
   produced by the morning-brief scheduled task) and at least one claim behind
   today's bad cluster was flagged **CONTRADICTED** there — the "Nvidia becomes
   the lender, absorbs credit risk" framing is inverted; the deal structure
   actually shifts financing risk off Nvidia's balance sheet. Feeding the raw
   digest without its sidecar risks generating candidates from claims already
   known to be wrong.

Fix both in one pass — they interact. If the aggregate is added as a source
without also handling clustering and episode/aggregate overlap, it reproduces
defect #1 through a second door (the aggregate cites episodes that are often
*also* separately ingested as standalone transcripts in the same window).

## Background — what's already confirmed (verify still true in Step 0, don't re-derive)

1. `idea_generator.py` schema (`Candidate` Pydantic model, line 24) has a single
   `ticker: str` field — no way to represent "these N tickers are one theme"
   today. `_sort_key()` and `write_idea_report()` both assume one candidate = one
   ticker.
2. `load_transcripts()` (line 59) globs `data/podcast_transcripts/*.txt|.md|.text`
   by mtime within `since_days`. It has no knowledge of `data/podcast_summaries/`
   at all.
3. Spotify aggregate filenames: `data/podcast_summaries/<date>_Spotify_Podcast_Aggregate_<Slug>.md`.
   Distinguish them from same-folder single-episode Gemini summaries (also
   `<date>_<Show>_<Title>.md`) by the literal substring `Spotify_Podcast_Aggregate`
   in the filename — do not try to distinguish by content shape, the folder mixes
   both and this is the reliable signal already used elsewhere in the codebase.
   **Verified 2026-08-13:** a non-recursive `Path.glob()` on that pattern returns
   5 digests and no sidecars; `rglob()` returns 12 and does pull in
   `verification/`. Use `glob()`, not `rglob()`, and do not add subdirectory
   exclusion logic — there is nothing to exclude. `data/podcast_summaries/archive/`
   does not currently exist (only `verification/` does), though
   `ingest_spotify_digests.py` names it as a future output path.
4. Every Spotify aggregate carries its own `source_sha256` in a `PROVENANCE:`
   footer line (regex: `source_sha256:\s*([0-9a-f]{64})`) and a `## Cited
   Episodes` section listing `- <Show>: <Title>` lines. Both are already
   plain-text in the file — no need to recompute the hash or call
   `ingest_spotify_digests.py` again.
5. Verification sidecars live at
   `data/podcast_summaries/verification/<digest_basename>_VERIFIED_<YYYY-MM-DD>.md`.
   Three states exist on disk right now, and the loader must handle all three:
   - **Single sidecar** — e.g. the 2026-08-13 digest
     (`..._AI_s_Fundamental_Strength_Confronts_the_Fed_s_Growth_Trap_VERIFIED_2026-08-13.md`,
     `source_sha256` `835d21b7…`, 5 CONFIRMED / 3 OVERSTATED / 2 CONTRADICTED /
     2 UNVERIFIABLE). The normal case.
   - **Base + delta chain** — the 2026-08-12 digest has `_VERIFIED_2026-08-12.md`
     (11 claims) plus `_VERIFIED_2026-08-13.md`, which states explicitly that the
     prior sidecar "is authoritative and is not superseded — this file records
     only what changed." **Both must be loaded, in ascending date order.** The
     delta reverses one verdict from the base (a GOOG move attribution), so
     reading only the newest or only the oldest gives a wrong answer.
   - **Unreconciled duplicates** — the 2026-08-10 digest has
     `_VERIFIED_2026-08-10.md` and `_VERIFIED_2026-08-11.md` with the same
     `source_sha256` and *divergent* content, and nothing marks either as base or
     delta. Pre-existing defect, not created by this prompt, but it makes the
     lookup ambiguous and is why Step 1 runs first.

   **Timing note (verified 2026-08-13):** the 08-13 digest was written at 09:11
   and its sidecar later the same morning — *after* the 08:47 briefing export and
   after the morning-brief scheduled task had already run and recorded "no
   aggregate was published for 2026-08-13." Do not treat the newest digest as
   fixed at the time the bundle was built; resolve digests and sidecars at
   agent-run time, from disk.
6. CLI entry point: `manager.py agent_app.command("ideas")` at `manager.py:2166`,
   flags `--since-days`, `--bundle-path`, `--dry-run`, `--skip-ingest`. Preserve
   this signature — do not add new required flags.
7. Rule 2 in `CLAUDE.md` ("Agents never browse or fetch. Python gathers; LLMs
   reason.") governs this whole prompt: the episode/aggregate overlap detection
   and the sidecar verdict pairing must happen in Python before the prompt is
   assembled, not be left for Grok to infer from a wall of concatenated text.
8. **Prompt-size risk was measured and is not a concern — do not change
   `max_tokens` or add truncation.** The current 7-day transcript window is
   **42 files / 939 KB**. All five aggregates on disk total 69 KB and all
   sidecars 64 KB; a realistic run adds one aggregate plus its sidecar chain,
   roughly **27 KB, under 3% of existing input**. `max_tokens=16000`
   (`idea_generator.py:115`) is an *output* cap and is unrelated.
9. **`current_holdings_overlap` is currently emitting tickers Bill does not
   hold.** In `ideas_2026-08-13_994a17dc.md`, CVX lists `Overlaps with: XOM, XLE`
   — **XLE is not a position** (confirmed absent from
   `exports/ai_briefing_2026-08-13_084734/portfolio.md`); BN lists `IFRA`, which
   is held. The field is documented in `prompts/idea_generator.md` as "only
   tickers that genuinely overlap," and a reader reasonably takes it as "things
   you own." Fixed in Step 3.4.

## Step 0 — Verification gate

Confirm before writing any code:

- [ ] `idea_generator.py:56` `TRANSCRIPTS_DIR` — confirm it is still only
      `data/podcast_transcripts/`.
- [ ] `Candidate` schema — confirm `ticker: str` is still singular, no
      `related_tickers` or equivalent field exists.
- [ ] Diff the two 2026-08-10 sidecars
      (`data/podcast_summaries/verification/2026-08-10_Spotify_Podcast_Aggregate_AI_Supercycle_Constrained_by_Watts_Wafers_and_Tokens_VERIFIED_2026-08-10.md`
      vs `..._VERIFIED_2026-08-11.md`). Paste the diff. Confirm both carry the
      same `source_sha256`.
- [ ] List every file currently in `data/podcast_summaries/verification/` with
      its `source_sha256` and verified-date, so Step 1's reconciliation has a
      complete picture, not just the one pair named above. Classify each as
      single / base+delta / unreconciled-duplicate per Background #5.
- [ ] Confirm the glob behaviour in Background #3 empirically: print the count
      and paths from `glob()` vs `rglob()` on the aggregate pattern. If `glob()`
      returns anything from `verification/`, STOP — Background #3 is wrong and
      the loader design in Step 2 needs revisiting.
- [ ] Confirm `XLE` is absent from
      `exports/ai_briefing_2026-08-13_084734/portfolio.md` (Background #9) and
      print the full held-ticker list that Step 3.4's validation will use.

If Step 0 finds anything materially different from the above (e.g. the schema
already has multi-ticker support, or a third divergent sidecar exists), STOP and
report — do not adapt silently.

---

## Step 1 — Reconcile the duplicate 2026-08-10 sidecars

This is a prerequisite, not optional cleanup: Step 2's loader needs one sidecar
(or one ordered chain of base+delta sidecars) per `source_sha256`, and right now
that invariant is broken for one digest.

1. Diff the two files. Determine which is the superset (more claims checked,
   more sources cited) — do not assume chronological order means superset.
2. Keep the superset as the canonical `_VERIFIED_2026-08-10.md`. Archive the
   other to `data/podcast_summaries/verification/archive/` (create the directory
   if missing) with its original filename intact — do not delete, do not rename
   in a way that loses the original verified-date.
3. Add a one-paragraph rule to `CLAUDE.md` under "Podcast & Third-Party Source
   Ingestion": a digest whose `source_sha256` already has a sidecar is not
   re-verified from scratch; a same-day or later re-check writes a **delta**
   sidecar (naming the prior file explicitly, recording only what changed) rather
   than a second full pass. This is the pattern the 2026-08-12/2026-08-13 pair
   already follows correctly — codify it so the 2026-08-10 duplication doesn't
   recur.
4. **Do not edit any digest's own `VERIFICATION: PENDING (manual)` footer line.**
   Per `state.md` (2026-08-01) the Spotify ingestion path uses that exact string
   as a ledger-independent collision guard; rewriting it breaks re-ingestion
   detection.

---

## Step 2 — Add the Spotify aggregate as a source, with sidecar pairing and episode-overlap detection

All in `utils/agents/idea_generator.py` unless noted.

1. **New loader, `load_spotify_aggregates(since_days)`.** Non-recursive
   `Path('data/podcast_summaries').glob('*Spotify_Podcast_Aggregate*.md')` — see
   Background #3; do **not** use `rglob()` and do **not** write subdirectory
   exclusion logic. Select by the same window convention
   `export_ai_briefing.py::build_podcasts_md()` already uses for this folder —
   **filename date via `parse_summary_date()`, not mtime** (sidecars are written
   days later and must not affect the digest's own window membership; reuse that
   helper rather than reimplementing the date parse). For each selected digest:
   - Extract `source_sha256` via the `PROVENANCE:` regex in Background #4.
   - Extract the `## Cited Episodes` list (Background #4).
   - Find matching sidecar(s): every file in `verification/` (post Step-1
     reconciliation) whose filename starts with the digest's basename. If more
     than one (base + delta chain), concatenate all of them in ascending
     verified-date order — do not pick only the newest, the delta files
     explicitly depend on the base for full context (see the 2026-08-13 delta's
     own framing).
   - Verify the sidecar's recorded `source_sha256` matches the digest's own. If
     it does not match, treat as **no sidecar found** (log a warning) rather than
     pairing incorrectly.
   - If no sidecar exists at all, still include the digest — do not block on
     missing verification — but mark it in the assembled prompt block as
     `[UNVERIFIED — no sidecar found]` so the LLM instructions (Step 3) can
     react.
2. **Episode/aggregate overlap detection.** For each digest's `## Cited
   Episodes` entries, fuzzy-match against the filenames already returned by
   `load_transcripts()` for the same run (show name + title substring match,
   case-insensitive; YouTube transcript filenames are
   `<date>_<Show>_<Title>_<videoID>.txt`). Build a list of `(cited_episode,
   matching_transcript_filename)` pairs. This list gets passed into the prompt
   in Step 3 — Python does the matching, the LLM does not infer it.
3. **Wire into `run_idea_generator()`.** Add the aggregate blocks (each paired
   with its sidecar text, or the `[UNVERIFIED]` tag) to `transcript_blocks`
   alongside the existing transcript blocks, clearly labeled as a distinct source
   type (e.g. `--- SPOTIFY AGGREGATE: <filename> ---` / `--- VERIFICATION SIDECAR
   FOR ABOVE ---`) so the LLM can tell an aggregate from a raw transcript. Add the
   digest filenames to `transcripts_analyzed` in the output schema so the report
   header accounts for them.
4. **Do not change `since_days` default or add a new CLI flag** — the aggregate
   window should follow the same `--since-days` value already passed for
   transcripts, per Background #6.

---

## Step 3 — Candidate clustering (the original bug)

1. **Schema change in `Candidate`:** add
   `related_tickers: list[str] = []` — "other tickers named in the same source as
   co-participants in the same deal, program, or structural theme; empty if this
   candidate is a standalone idea." Keep `ticker` as the single primary ticker —
   do not overload it into a comma-joined string; downstream code (`_sort_key`,
   overlap logic) assumes a single symbol.

   **Primary-ticker selection rule — read this carefully, the obvious rule is
   wrong.** Pick the participant the source spent the most words on, or the one
   with the clearest standalone thesis. **Do NOT prefer a ticker the investor
   doesn't already hold.** `_sort_key()` (`idea_generator.py:203-217`) sorts
   candidates with an empty `current_holdings_overlap` into group 0, the top of
   the report. Choosing an un-held primary and pushing the held one into
   `related_tickers` would move an already-owned-adjacent cluster to the head of
   the list — the opposite of correct. In the 2026-08-13 report the financing
   cluster correctly sorts into group 2 (overlap/rotation); it must stay there.

2. **Overlap must survive clustering.** Any ticker in `related_tickers` that is
   a current holding MUST also appear in `current_holdings_overlap`, regardless
   of which participant became primary. Enforce this in Python after the LLM
   returns — do not rely on the model to remember. Concretely: if the consortium
   cluster comes back with `ticker="BLK"` and `related_tickers=["APO","BN","BX","GS","KKR"]`,
   then `current_holdings_overlap` must contain `APO`, so `_sort_key()` still
   places it in group 2.
3. **Update `prompts/idea_generator.md`** (the system instruction, not this
   file) with an explicit clustering rule, e.g.:

   > If a transcript or digest names multiple tickers as co-participants in the
   > same deal, financing structure, program, or one-sentence structural theme
   > (example: six named counterparties in one financing consortium), emit **one**
   > candidate. Set `ticker` to the participant the source discussed most
   > substantively, and list the rest in `related_tickers`. Do not pick the
   > primary based on whether the investor already owns it — if he owns one of
   > the participants, name that in `portfolio_relationship` and include it in
   > `current_holdings_overlap`, but let the source's emphasis decide the primary.
   > Do not emit one candidate per named participant. This does not apply to
   > tickers that merely appear in the same episode discussing genuinely separate
   > ideas — only to tickers presented as the same thesis.
   >
   > If a Spotify aggregate digest is paired with a `[VERIFICATION SIDECAR]`
   > block, and a claim underlying a candidate's thesis is marked CONTRADICTED or
   > OVERSTATED in that sidecar, do not build a candidate on the contradicted
   > framing. You may still surface the underlying idea using the sidecar's
   > corrected fact, but say so explicitly in `notable_concerns`
   > (e.g. "digest framed this as X; verification sidecar corrects this to Y").
   > If a digest has no paired sidecar (`[UNVERIFIED]`), say so in
   > `notable_concerns` rather than treating the claim as fact.
   >
   > If a cited episode inside a Spotify aggregate is also separately provided to
   > you as a full transcript in this same batch (you will be told which pairs
   > this applies to), treat the transcript as the primary source for that theme
   > and the aggregate as commentary on it — do not generate two candidates for
   > the same underlying idea, one sourced to each.

4. **Validate `current_holdings_overlap` against the bundle — new, found during
   audit (Background #9).** After the LLM returns, drop any ticker in
   `current_holdings_overlap` that is not an actual position in the composite
   bundle already loaded by `run_idea_generator()`. Today's report claims CVX
   `Overlaps with: XOM, XLE` — **XLE is not held**, and presenting it as an
   overlap misrepresents the book to a reader scanning for what he owns. Log
   each dropped ticker at INFO so a systematic model error stays visible rather
   than being silently cleaned up. Sector/thematic *context* the model wants to
   convey (e.g. "the energy sector broadly") belongs in
   `portfolio_relationship` prose, not in a field that reads as a holdings list.
   Add a matching line to `prompts/idea_generator.md` under the existing
   `current_holdings_overlap guidance` section: **only tickers currently held in
   the bundle; never a sector proxy the investor does not own.**

5. **Update `write_idea_report()`** to render `related_tickers` when present
   (e.g. `**Related tickers (same source):** BN, BX, GS, KKR  ` under the
   `Overlaps with` line) and to render the `[UNVERIFIED]` / sidecar-correction
   framing if `notable_concerns` carries it — no schema change needed there,
   `notable_concerns` already exists.

---

## Step 4 — Regression test against today's actual bad output

Use the real 2026-08-12 On The Tape transcript and the real 2026-08-13 report
(`agent_outputs/ideas/ideas_2026-08-13_*.md`) as the acceptance case — this bug
is already reproduced in a file on disk, no synthetic fixture needed.

1. Run the updated agent against the same transcript window that produced
   today's report (`--dry-run`, do not overwrite the existing report).
2. Confirm BLK/BN/BX/GS/KKR collapse into a single candidate with `ticker` set
   to whichever the model picks as primary and `related_tickers` holding the
   other four.
3. **Confirm the collapsed cluster still sorts into group 2, not group 0** —
   i.e. `APO` is present in `current_holdings_overlap` and the candidate does
   not appear at the top of the report. This is the specific regression the
   v1.0.0 instruction would have introduced; prove it with the rendered report
   ordering, not by inspecting the schema.
4. Confirm `XLE` no longer appears in any `current_holdings_overlap`, and that
   the INFO log records it as dropped.
5. Confirm both Spotify aggregates in the window (2026-08-12 and 2026-08-13)
   appear in `transcripts_analyzed`, and that their sidecars pair correctly:
   the 08-12 digest must load **both** `_VERIFIED_2026-08-12.md` and
   `_VERIFIED_2026-08-13.md` in that order (base + delta), the 08-13 digest its
   single `_VERIFIED_2026-08-13.md`. Paste the assembled blocks — do not assert.
6. Confirm any candidate touching the Nvidia financing framing reflects the
   sidecar's CONTRADICTED verdict rather than the raw digest's inverted "Nvidia
   becomes the lender" framing.
7. Confirm the Forward Guidance / Darius Dale overlap produces **one** market
   theme, not two. Note this episode is cited by **both** the 08-12 and 08-13
   aggregates *and* exists as a standalone transcript
   (`2026-08-12_Forward_Guidance_The_Growth_Strategy_Trapping_The_Fed_Darius_Dale_vvMTOKRR0SE.txt`)
   — a three-way collision, and the strongest available test of the
   episode-primary / aggregate-commentary rule.

---

## Step 5 — Verification

Literal stdout/stderr for each — do not accept a self-reported PASS table.

- [ ] Step 0 findings, pasted — including the `glob()` vs `rglob()` counts and
      the held-ticker list.
- [ ] Diff from Step 1, and confirmation of which file was kept vs. archived.
- [ ] `CLAUDE.md` delta-sidecar rule, pasted as added.
- [ ] `python manager.py agent ideas --dry-run --since-days 7` full console
      output, run against the current transcript/digest corpus.
- [ ] The assembled `transcript_blocks` for the On The Tape source, showing the
      digest + paired sidecar block as actually passed to the model — not a
      description of it.
- [ ] Rendered report excerpt showing the collapsed BLK/BN/BX/GS/KKR candidate
      **and its position in the report ordering** (Step 4.3).
- [ ] Before/after list of every ticker dropped from `current_holdings_overlap`
      by the Step 3.4 validator, with the INFO log lines.
- [ ] Confirmation that a transcript-only run (no aggregates in window) still
      produces byte-identical candidate content to before this change, for any
      candidate not touching a clustered or aggregate-sourced idea —
      backwards-compat proof, not just "looks fine."
- [ ] `state.md` and `CHANGELOG.md` updated.

## Out of scope

- No price targets, no buy/sell recommendations — `notable_concerns` and
  `style_fit_reasoning` stay descriptive, per existing agent design.
- Do not touch `export_ai_briefing.py`'s existing Spotify-aggregate handling for
  the morning-brief pipeline — this prompt only changes the idea generator's
  inputs.
- Do not build automatic verdict-based filtering that silently drops candidates
  without the `notable_concerns` explanation — Bill reads the concern, not a
  suppressed line count.
- Do not resolve the six/three-account ceiling-denominator open question or any
  other standing `CLAUDE.md` Open Question — unrelated to this fix.
