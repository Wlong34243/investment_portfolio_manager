# Gemini Peer Review Request — Spotify Digest Double-Count Mitigation

**Date:** 2026-08-01
**Requested by:** Bill, via Claude Code
**Run with:** Gemini CLI, from the repo root, with file-system access (this is not a copy-paste-into-chat package — read files directly).

---

## Why this checkpoint exists

Claude Code just built STEP 4b of `pm morning`: automated ingestion of the daily Spotify Studio "Allocation" digest (`tasks/ingest_spotify_digests.py`), per `prompts/spotify_digest_ingestion_2026-08-01.md`. Per this project's own convention (`CLAUDE.md` → "Gemini peer review"), this build's one open design question — flagged in the build prompt itself as unresolved — gets a second, independent set of eyes before STEP 4b is flipped to `--live` in `morning_auto.bat`'s daily run.

You have full repo access. Don't take anything below on faith — re-derive it from the code, and push back if you disagree.

---

## Step 0 — Orient yourself

1. Read `CLAUDE.md` and `state.md`.
2. Read `prompts/spotify_digest_ingestion_2026-08-01.md` in full — it is the build spec and contains the full rationale this checkpoint is scoped to (see especially sections B.3 and the "Gemini peer review checkpoint" at the bottom).
3. Read one hand-ingested example end to end: `data/podcast_summaries/2026-08-01_Spotify_Podcast_Aggregate_Earnings_Split_And_The_Physical_Ceiling.md`. Note its length (~1,700 words of preserved source prose) against a typical single-episode Gemini summary (~2,000 characters) elsewhere in the same directory.
4. Run `git status`. This session's changes are scoped to: `config.py`, `utils/agents/podcast_analyst.py`, `tasks/ingest_spotify_digests.py` (new), `manager.py`, `tasks/export_ai_briefing.py`, `.gitignore`, `CHANGELOG.md`, `state.md`. `data/podcast_summaries/` is gitignored so its contents won't show as changes.

---

## Section A — What this session built (primary review target)

| File | What changed and why |
|---|---|
| `tasks/ingest_spotify_digests.py` | New. Ingests `allocation-YYYY-MM-DD.txt` from the local Studio app folder, dedups by sha256, skips sub-400-word files, writes `data/podcast_summaries/<date>_Spotify_Podcast_Aggregate_<Slug>.md`. Executive Summary is the source prose itself, lightly reflowed — never re-summarized (2026-07-26 decision). |
| `utils/agents/podcast_analyst.py` | New `is_aggregate` branch in `analyze_podcast()`: Gemini's only job for this source type is the Sector Allocations table, a `suggested_title`, and `cited_sources` (shows/guests the digest names). |
| `tasks/export_ai_briefing.py` | New Hard Rule #9 in `PROMPT_PAYLOAD`: "one source is one source, regardless of length" — instructs the downstream briefing LLM not to weight a theme by text volume, and to treat an aggregate's commentary on a cited episode as non-independent corroboration of that episode. |

---

## Section B — The one question

The corpus ingests a third-party weekly aggregate at full length (~1,700 words, its own prose preserved) alongside ~2,000-character Gemini summaries of single episodes. The aggregate also comments on episodes that are separately ingested in the same window — verified against the 2026-07-31 edition specifically: it names Forward Guidance/Hou, The Compound TCAF 253, Top Traders/Goodspeed, On The Tape/Elliott, and Capital Allocators/Hochfelder, and every one of those has its own independently-ingested summary file in the same corpus window. A theme can therefore appear twice: once in its source episode, once in the aggregate's commentary on that episode. This is the same failure the 2026-07-26 decision (ingest the aggregate as one voice, don't decompose it) was meant to prevent, arriving through a different door.

Mitigation currently shipped is instruction-side only: a `## Cited Episodes` cross-reference (from the new `cited_sources` schema field) plus Hard Rule #9 above.

**Argue both sides of one question: is instruction-side de-duplication sufficient, or does theme extraction need a structural fix** — for example a short bounded `## Themes` block that extraction reads instead of the full prose, with the prose retained for depth? Address specifically whether a model asked to find recurring themes across ~26 summaries in one context window can be relied on to follow a counting rule that runs directly against the raw text volume in front of it, versus simply being more persuaded by whichever source said the same thing at greater length.

Note one asymmetry worth weighing explicitly: the mitigation only improves the *four already hand-ingested* editions if `## Cited Episodes` is backfilled into them — the build prompt explicitly scoped that backfill out as a separate manual task. So for some unknown number of upcoming briefings, the newly-ingested editions will carry the cross-reference and the four historical ones won't. Is that transition period a real risk, or immaterial given the 7-day briefing window?

---

## What to produce

A direct answer to the question above — not a survey of options. If you land on "instruction-side is sufficient for now," name the condition under which you'd revisit that (e.g., a specific failure observed in a real briefing). If you land on "needs a structural fix," specify what changes concretely: which file, which function, what the bounded `## Themes` block would contain and who writes it (Gemini at ingestion time, or a second deterministic pass). Keep it to the one question — this is a scoped checkpoint, not a full-session review.
