# Prompt: Spotify Studio Digest Ingestion (STEP 4b)

**Created:** 2026-08-01
**Target executor:** Claude Code or Gemini CLI, run locally in the repo
**Scope:** one new task module, one config block, one new pipeline step, one test file
**Do NOT touch:** `morning_auto.bat`, `tasks/batch_podcast_sync.py`, `tasks/podcast_fetcher.py`, `core/bundle.py`

---

## Why this is not a `morning_auto.bat` change

The original request was to "update the morning bat to pull the week's transcripts."
`morning_auto.bat` is a 30-line unattended wrapper whose only real line is
`python manager.py morning --live`. It contains no pipeline logic. The podcast phase
lives at **STEP 4** in `manager.py`, which shells out to `tasks/batch_podcast_sync.py`.

The new ingestion belongs beside that step as **STEP 4b**, not inside the batch script
and not in the `.bat`. `morning_auto.bat` requires no edit at all.

---

## Step 0 — Verification gate (do this before writing any code)

Confirm each of the following with `view` / `ls`. If any differs, STOP and report rather
than adapting silently.

1. `manager.py` STEP 4 exists at roughly line 1440, is guarded by `if not skip_podcasts:`,
   shells out via `subprocess.run` with a 600s timeout, appends to `step_results`, and is
   **non-fatal** — it catches `Exception` and records `"warn"`.
2. `utils/agents/podcast_analyst.py` defines `SectorTarget` and `PodcastStrategy` Pydantic
   models and an `analyze_podcast(transcript, source_name)` function that already branches
   on `is_stax = "STAX" in source_name.upper()` to swap `role_instruction`.
3. `data/podcast_summaries/` exists and contains files named
   `YYYY-MM-DD_<Source>_<Title>.md`, including four hand-ingested files matching
   `*Spotify_Podcast_Aggregate*`.
4. `tasks/export_ai_briefing.py` contains `parse_summary_date()` (regex
   `^(\d{4}-\d{2}-\d{2})_`) and `podcast_signal()` (drops a summary whose Sector
   Allocations table has a single catch-all `Broad Market` row, or contains the string
   `No actionable thesis`).
5. `utils/hygiene.py` `purge_obsolete_data()` takes `days_podcasts` defaulting to
   `config.PURGE_DEFAULT_DAYS_PODCASTS`. **Record that value** — it determines whether
   ingested digests survive to the next briefing.
6. The source folder exists and is readable:
   `C:\Users\WLong\AppData\Local\Studio by Spotify Labs\.studio\artifacts\transcripts`
   Files are named `allocation-YYYY-MM-DD.txt`. Confirm the current contents.

---

## What the source files actually are (audited 2026-08-01)

The folder currently holds **two** files, not a broad transcript universe:

```
allocation-2026-07-31.txt   11,029 bytes   35 lines   1,667 words
allocation-2026-08-01.txt    7,474 bytes   23 lines   1,201 words
```

Format characteristics, all confirmed by inspection:

- Plain UTF-8 prose. **No title, no date, no episode list, no metadata inside the file.**
- The only date is in the filename.
- The only title is the show name, which is constant ("The Allocation").
- Body is finished editorial prose, ~1,200-1,700 words, already synthesized.

**These are not transcripts.** They are third-party daily digests that already summarize
a pool of episodes. This distinction drives every design decision below.

---

## Design constraints (non-negotiable)

### 1. Do not re-summarize the digest

Decision logged in `state.md` on 2026-07-26: the Spotify aggregate is ingested **as a
single first-class source in its own voice**, not decomposed into constituent episodes
and not re-summarized. Rationale on record: decomposition made one digest appear as three
agreeing sources during theme extraction, and discarded the aggregate's own synthesis.

Therefore the generated summary's `## Executive Summary` section is **the source prose
itself**, lightly reflowed. It is NOT a Gemini summary of a summary.

### 2. Gemini's only job is the Sector Allocations table

Reuse `analyze_podcast()` but add a third `role_instruction` branch alongside the existing
STAX branch. The new branch must state that the input is an already-synthesized
third-party aggregate, that percentages are to be **inferred from the digest's stated
emphasis** rather than extracted as published figures, and that the digest's own
unresolved tensions must be preserved as separate rows rather than averaged into one.

Take `target_allocations` from the result. Discard `executive_summary` — the source prose
replaces it.

### 3. Verification is manual and must be visibly absent, not silently missing

Hard rule: agents never browse or fetch. The VERIFICATION footer in the four hand-ingested
files required web search plus the current position set, and it is where the real value
sits — it caught a wrong Meta capex range, an inverted Alphabet framing, and a misattributed
FOMC meeting.

The task must therefore write a literal placeholder:

```
*VERIFICATION: PENDING (manual). This digest has not been fact-checked. Treat every
specific figure as unconfirmed until a verification pass replaces this line.*
```

Never write a fabricated verification block. Never omit the line.

### 4. Provenance stamp is mandatory and fixed

Reuse the exact wording already in the four hand-ingested files, plus a machine field:

```
*PROVENANCE: This is a third-party Spotify podcast-aggregate digest, ingested as its own
source in its own voice. It is NOT a transcript of a single episode and was NOT produced
by the YouTube fetcher. Allocation percentages are inferred from the aggregate's stated
emphasis, not figures it published. Ingested automatically from Spotify Studio artifacts;
source_sha256: <hash>.*
```

---

## Implementation

### A. `config.py` — add a block

```python
# --- Spotify Studio digest ingestion (STEP 4b) ---
SPOTIFY_STUDIO_TRANSCRIPTS_DIR = os.getenv(
    "SPOTIFY_STUDIO_DIR",
    os.path.join(
        os.path.expanduser("~"),
        "AppData", "Local", "Studio by Spotify Labs",
        ".studio", "artifacts", "transcripts",
    ),
)
SPOTIFY_DIGEST_WINDOW_DAYS = 7
SPOTIFY_DIGEST_MIN_WORDS = 400          # below this, treat as truncated and skip
SPOTIFY_DIGEST_SOURCE_LABEL = "Spotify Podcast Aggregate"
```

Path contains spaces and is user-specific. Build it with `os.path.join`, never string
concatenation, and never hard-code the username.

### B. `tasks/ingest_spotify_digests.py` — new module

Header block required (purpose / inputs / outputs / dependencies), per repo convention.

```
main(days=config.SPOTIFY_DIGEST_WINDOW_DAYS, live=False)
```

Behavior:

1. **Folder missing or unreadable → return cleanly with a warn code.** This is a local
   application directory that can disappear on a Studio update. It must never raise into
   the morning pipeline.
2. Glob `allocation-*.txt`. Parse the date from the filename with
   `^allocation-(\d{4}-\d{2}-\d{2})\.txt$`. Skip non-matching names rather than guessing.
3. Keep files whose date is within `days` of today.
4. For each kept file, compute `sha256` of the raw bytes. Maintain a ledger at
   `data/spotify_digests/.ingested.json` mapping `sha256 -> {filename, ingested_at, output_path}`.
   **If the hash is already in the ledger, skip.** This makes reruns idempotent and is the
   only dedup mechanism — do not dedup on filename, since Studio may rewrite a file in place.
5. Skip and warn if word count `< SPOTIFY_DIGEST_MIN_WORDS`.
6. Copy the raw source to `data/spotify_digests/allocation-YYYY-MM-DD.txt` so the corpus
   owns a copy independent of the Studio app.
7. Call `analyze_podcast(body, source_name="Spotify Podcast Aggregate: <date>")` to get
   `target_allocations` only.
8. **Derive the title/slug.** Not present in the file. Ask Gemini in the same call for a
   6-10 word title capturing the lead idea, via an added optional field on the schema, OR
   derive from the first sentence. Prefer the Gemini field. Slugify to
   `Title_Case_With_Underscores`, strip non-alphanumerics, cap at 60 chars.
9. Write `data/podcast_summaries/<YYYY-MM-DD>_Spotify_Podcast_Aggregate_<Slug>.md` in the
   established format, in this exact section order:
   - `# Spotify Financial Podcast Aggregate: <Title>`
   - `**Date:** YYYY-MM-DD`
   - `## Executive Summary` — the source prose
   - `## Sector Allocations` — markdown table with the exact existing column headers:
     `| Asset Class | Strategy | Target % | Range | Confidence | Notes |`
   - `---`
   - PROVENANCE block (with `source_sha256`)
   - VERIFICATION PENDING placeholder
10. **Archive-before-overwrite.** If the target path exists, copy it to
    `data/podcast_summaries/archive/` with a timestamp suffix before writing.
11. `live=False` prints the plan and writes nothing — including no ledger update.
12. Return `{"ingested": [...], "skipped": [...], "failed": [...]}`.

### B.2 — Collision mitigation: seed the ledger before the first live run

The four hand-ingested aggregates in `data/podcast_summaries/` carry completed VERIFICATION
footers and portfolio hooks. Two of them (2026-07-31, 2026-08-01) correspond to source files
still sitting in the Studio folder. A naive first `--live` run would regenerate both and
overwrite hand work with `VERIFICATION: PENDING` stubs.

Do not solve this by deletion after the fact. Solve it with **two independent guards**, so
the failure mode cannot recur for any future hand-ingested digest either.

**Guard 1 — backfill mode (`--seed-ledger`).**

Add a mode that writes ledger entries without generating any summaries:

```
pm podcast ingest-spotify --seed-ledger [--live]
```

For each `allocation-YYYY-MM-DD.txt` in the Studio folder, check whether
`data/podcast_summaries/` already contains a file matching
`<same-date>_Spotify_Podcast_Aggregate_*.md`. If it does, write the source file's sha256
into the ledger with `{"source": "manual", "output_path": <existing file>}` and generate
nothing. This is idempotent and safe to re-run.

**This must be run once, with `--live`, before STEP 4b is ever enabled.** After it runs, the
existing hash-dedup in step 4 skips those two files permanently — no collision, no archive,
no manual judgment call about which copy survives.

**Guard 2 — never overwrite a verified file.**

Independent of the ledger, before writing any summary: if the target path exists AND its
contents do **not** contain the literal string `VERIFICATION: PENDING`, treat it as
hand-verified. Skip it, log a warning naming the file, and record the hash in the ledger so
it is not retried. A completed verification block is the marker of human work and outranks
anything the task would generate.

Guard 1 prevents the collision. Guard 2 makes the collision harmless if Guard 1 was skipped,
the ledger is lost, or a digest is hand-verified in the future after being auto-ingested.

### B.3 — Length-asymmetry and double-count mitigation

Two distinct problems, one of which is worse than originally scoped.

**Problem A, length.** A 1,700-word unsummarized digest sits alongside ~2,000-character
Gemini summaries of single episodes. A model asked to extract recurring themes across ~26
summaries can weight by volume of text rather than by number of independent sources.

**Problem B, double counting — this is the more serious one.** The aggregate discusses
episodes that are *also independently ingested by the YouTube fetcher*. Verified against the
2026-07-31 aggregate: it cites Forward Guidance/Hou, The Compound TCAF 253, Top Traders/
Goodspeed, On The Tape/Elliott, and Capital Allocators/Hochfelder — **every one of which has
its own summary file in the same corpus window.** A theme therefore appears twice: once in
its source episode and once in the aggregate's commentary on that episode.

This is the exact failure the 2026-07-26 decision was meant to prevent — "decomposition made
one digest appear as three agreeing sources" — arriving through a different door. Not
decomposing the aggregate solved half the problem; the constituents show up on their own
anyway.

**Mitigation, three parts:**

1. **Emit a machine-readable cross-reference.** Add `cited_sources: List[str]` to the Pydantic
   schema used for the aggregate branch (show name plus guest where stated, e.g.
   `"Forward Guidance: Steve Hou"`). Write it into the generated file as a
   `## Cited Episodes` section immediately after `## Sector Allocations`. Gemini extracts
   this reliably from the prose; do not attempt regex matching against filenames.

2. **Add a hard rule to the briefing prompt** in `tasks/export_ai_briefing.py`. Proposed
   wording, to be reviewed before insertion:

   > **One source is one source, regardless of length.** The Spotify aggregate runs 4-8x
   > longer than an episode summary because it synthesizes many episodes, not because it
   > carries more conviction. Do not weight a theme by how much text supports it. Further:
   > the aggregate lists the episodes it draws on under `## Cited Episodes`, and those
   > episodes are frequently ingested separately in the same window. Where an aggregate and
   > a cited episode both appear, treat the **episode** as the primary source for that theme
   > and the aggregate as commentary on it. Count the theme once. An aggregate agreeing with
   > an episode it is summarizing is not corroboration.

3. **Leave the corpus-wide asymmetry visible rather than silently corrected.** Do not truncate
   or re-summarize the digest to equalize length — that breaks the 2026-07-26 decision. The
   fix is instructing the consumer, not shrinking the source.

Note this mitigation improves the four existing hand-ingested files only if `## Cited Episodes`
is backfilled into them. That is a separate manual task, not part of this build.

### C. `manager.py` — add STEP 4b

Insert immediately after STEP 4, before STEP 5 (Refreshing Dashboard). Renumber nothing —
call it "STEP 4b" so downstream log parsers and the health sentinel keep working.

Mirror STEP 4's contract exactly:

- guarded by the existing `if not skip_podcasts:`
- wrapped in `try/except Exception`
- appends `("Spotify Digests (n new)", "pass" | "warn" | "skip")` to `step_results`
- **non-fatal in all cases** — a Studio folder that does not exist on a given machine must
  degrade to `warn`, never abort the morning run

Call `main()` in-process (it is a plain function, unlike `batch_podcast_sync`'s argparse
entry point — no subprocess needed).

### D. `manager.py` — add a standalone command

Under the existing `podcast_app` Typer group:

```
pm podcast ingest-spotify [--days 7] [--live]
```

so the ingestion can be run and inspected independently of the morning pipeline.

### E. Purge interaction

Confirm the Step 0 value of `PURGE_DEFAULT_DAYS_PODCASTS`. If it would delete
`data/podcast_summaries/*Spotify_Podcast_Aggregate*` files sooner than the briefing
export's own window uses them, **report the conflict — do not change the purge default.**
The ledger under `data/spotify_digests/` must be excluded from purge regardless.

---

## Explicit non-goals

- Do not write to `Target_Allocation`, `AI_Suggested_Allocation`, or any Sheet tab.
- Do not fetch, browse, or verify any claim in the digest.
- Do not decompose the digest into per-episode files.
- Do not modify the existing YouTube transcript path.
- Do not add portfolio hooks — that pass needs the live position set and stays manual.
- Do not edit `morning_auto.bat`.

---

## Post-build verification checklist

The build is not done until every line passes.

- [ ] `pm podcast ingest-spotify --days 7` (no `--live`) prints a plan and writes zero files.
- [ ] `pm podcast ingest-spotify --seed-ledger --live` runs FIRST, writes two ledger entries
      marked `"source": "manual"`, and generates zero summary files.
- [ ] After seeding, `pm podcast ingest-spotify --days 7 --live` ingests **nothing** — both
      current source files are already in the ledger. The hand-ingested 2026-07-31 and
      2026-08-01 aggregates are byte-identical afterward (diff them to confirm).
- [ ] Guard 2 works independently: delete the ledger, re-run `--live`, and confirm both files
      are still skipped with a warning naming them, because neither contains
      `VERIFICATION: PENDING`.
- [ ] Guard 2 does not over-trigger: a target file that DOES contain `VERIFICATION: PENDING`
      is overwritten normally, with archive-before-overwrite firing.
- [ ] Drop a synthetic `allocation-2026-08-02.txt` into the Studio folder and confirm a new
      file is generated end to end, then that a rerun ingests nothing.
- [ ] Generated files contain a `## Cited Episodes` section listing show + guest.
- [ ] Re-running `--live` immediately ingests nothing (ledger dedup works).
- [ ] Each generated file's Sector Allocations table has more than one distinct asset class,
      so `podcast_signal()` in `export_ai_briefing.py` keeps it rather than withholding it.
- [ ] `parse_summary_date()` returns the correct date for each generated filename.
- [ ] Generated files contain the literal string `VERIFICATION: PENDING`.
- [ ] Generated files contain `source_sha256:` followed by a 64-char hex string.
- [ ] Renaming the Studio folder and running the morning pipeline yields
      `Spotify Digests` → `warn`, and STEP 5 onward still runs to completion.
- [ ] A zero-byte and a 100-word `allocation-*.txt` are both skipped with a warning.
- [ ] `python manager.py morning` (dry) completes with STEP 4b present in the step table.
- [ ] `to_ascii()` in the export path does not mangle the generated files — check for
      smart quotes and em dashes in Studio output specifically.

---

## Gemini peer review checkpoint

Before flipping STEP 4b to `--live` in `morning_auto.bat`'s daily run, produce
`GEMINI_REVIEW_REQUEST.md` covering one question:

> The corpus ingests a third-party weekly aggregate at full length (~1,700 words, its own
> prose preserved) alongside ~2,000-character Gemini summaries of single episodes. The
> aggregate also comments on episodes that are separately ingested in the same window.
> Mitigation currently proposed is instruction-side only: a `## Cited Episodes` cross-
> reference plus a briefing-prompt rule that one source counts once and the episode
> outranks the aggregate's commentary on it.
>
> Argue both sides of one question: is instruction-side de-duplication sufficient, or does
> theme extraction need a structural fix — for example a short bounded `## Themes` block that
> extraction reads instead of the full prose, with the prose retained for depth? Address
> specifically whether a model asked to find recurring themes across ~26 summaries can be
> relied on to follow a counting rule that runs against the raw text volume in front of it.

Both risks this checkpoint originally covered now have mitigations in section B.2 and B.3.
The open question is whether B.3's instruction-side approach holds under load, which is a
design judgment worth a second opinion before STEP 4b runs daily.
