# Dual-track batch sync — one RSS walk, two destinations, and a backfill that can reach past today

**Created:** 2026-08-31
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 3 of 4.** **Depends on:** prompt 1 (registry) and prompt 2 (AI analyst + `ai_track_sync.py`).
**Gates:** prompt 4 has no code dependency on this, but has no input without it.

> Two facts about the current orchestrator shape this prompt. It processes **exactly one video per
> channel per run** — the newest entry in the feed — so a channel that posts twice between runs loses
> an episode permanently, and a newly added channel starts from today with no history. And it routes
> every channel to `weekly_podcast_sync.py`, which is now the wrong destination for nine of them.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — prompts 1 and 2 landed
python -c "from utils.channel_registry import load_channels as L; print(len(L('finance')), len(L('ai')))"
ls tasks/ai_track_sync.py utils/agents/ai_research_analyst.py
python -c "from utils.agents.ai_research_analyst import validate_brief; print('validator OK')"

# 0.2 — the one-video-per-run behaviour, in the code
grep -n "for entry in entries" -A 12 tasks/batch_podcast_sync.py

# 0.3 — how many entries the feed actually offers (the backfill ceiling)
python - <<'PY'
import urllib.request, xml.etree.ElementTree as ET
A="{http://www.w3.org/2005/Atom}"; Y="{http://www.youtube.com/xml/schemas/2015}"
u="https://www.youtube.com/feeds/videos.xml?channel_id=UCbzQ_YWf9RsBP9ATbmv5kxQ"
r=ET.fromstring(urllib.request.urlopen(u,timeout=15).read())
e=r.findall(A+"entry"); print("entries:", len(e))
for x in e[:3]:
    print(" ", x.find(Y+"videoId").text, x.find(A+"published").text, x.find(A+"title").text[:60])
PY

# 0.4 — dedup log, before
python -c "import json;d=json.load(open('data/processed_videos.json'));print(len(d))"

# 0.5 — the two CLI entry points that must keep working
grep -n "@podcast_app.command(\"batch\")" -A 20 manager.py
grep -n "ingest_podcasts_cmd\|podcast_batch" manager.py

# 0.6 — where the morning pipeline calls STEP 4
grep -rn "batch_podcast_sync\|STEP 4" pipeline.py manager.py | head
```

**Expected at 0.3:** 15 entries, each with `videoId`, `published` and `title`. **That 15 is the hard
ceiling on backfill.** The Atom feed is the only source this build uses, so history deeper than the
last 15 uploads is unreachable — say so plainly rather than reaching for a scraper or an API key.

---

## Design decisions, already made — do not relitigate

**One orchestrator, forked at the destination.** Not two batch scripts. The RSS walk, the dedup log,
the logging and the summary table are identical for both tracks; only the subprocess target differs.
Duplicating the orchestrator means two places to fix the next dedup bug.

**Default remains one video per channel.** `--max-per-channel` defaults to `1`, so a bare
`pm podcast batch` behaves exactly as it does today. Backfill is opt-in and explicit.

**The AI track does not join the morning pipeline.** `manager.py morning` runs before market open on
a clock that already contends for a lock, and each AI episode costs a transcript download plus a
Gemini call. AI capability news has no market-open deadline. The AI track runs on its own schedule —
`pm podcast batch --track ai` — and Bill decides the cadence. Weekly is the suggestion; the prompt
does not install a scheduled task.

**Dedup stays a single file keyed by video ID.** Not one file per track. A video ID is globally
unique and a channel could plausibly move tracks; two files would let the same video be processed
twice. The `track` value is stored on the record, not in the filename.

**Failures do not poison the dedup log.** Today a non-zero exit skips the dedup write, which is
correct and must be preserved. A brief that fails `validate_brief()` is a failure by the same rule —
the video stays un-deduped and is retried on the next run after a prompt fix.

---

## Step 1 — Registry-driven walk with a track fork

Rewrite the channel loop in `tasks/batch_podcast_sync.py`:

```python
for cfg in load_channels(track=args.track):        # track=None → both
    ...
    if cfg["track"] == "finance":
        script = "weekly_podcast_sync.py"
    else:
        script = "ai_track_sync.py"
```

Keep everything else: the `title_filter` semantics, the per-episode immediate dedup save (its comment
explains exactly why — a mid-run timeout must not discard completed episodes), the last-5-lines stdout
echo on success, the last-10-lines echo on failure, and the four-bucket summary.

New flags:

| Flag | Default | Meaning |
|---|---|---|
| `--track {finance,ai,all}` | `all` | Which registry rows to walk |
| `--max-per-channel N` | `1` | Process up to N unprocessed entries per channel, oldest-first |
| `--since YYYY-MM-DD` | none | Ignore feed entries published before this date |
| `--channel NAME` | none | Restrict to one registry entry, repeatable. For debugging a single source |
| `--live` | off | Unchanged |

**Oldest-first within a channel.** `get_latest_video` returns newest-first today because it returns
one. When processing several, reverse them — a mid-run timeout should leave the *newest* episodes
unprocessed, since those are the ones the next run will find at the top of the feed anyway.

Replace `get_latest_video` with `get_recent_videos(channel_id, title_filter=None, since=None,
limit=1) -> list[tuple[video_id, title, published]]`. **Keep `get_latest_video` as a thin wrapper**
that returns the first result or `(None, None)` — `manager.py`'s `podcast_batch` imports it by name,
and prompt 1's checklist item 5 established that path works.

## Step 2 — `min_words` enforcement

Prompt 1 added a nullable `min_words` per channel; prompt 2 put a hard 300-word floor in
`ai_track_sync.py`. Wire the registry value through as an argument (`--min-words`) to both subprocess
targets, falling back to each script's own floor when the registry value is null.

The finance path has **no** floor today. Give it one via the same flag, defaulting to null so
behaviour is unchanged — the two clips channels added in prompt 1 are the reason the knob exists, and
Bill sets the value after seeing the word counts checklist item 6 prints.

## Step 3 — Dedup records

```json
{
  "<video_id>": {
    "channel": "Google DeepMind",
    "title": "…",
    "track": "ai",
    "published": "2026-08-29T14:02:11+00:00",
    "processed_at": "2026-08-31T09:14:02"
  }
}
```

`published` is new and comes from the feed — it is what makes `--since` meaningful on a re-run.
**Existing records are not migrated.** A record with no `track` is finance; a record with no
`published` is simply not eligible for a `--since` comparison and is skipped as already-processed,
which is the correct outcome anyway.

## Step 4 — CLI

`manager.py`'s `podcast_batch` gains `--track`, `--max-per-channel`, `--since` and `--channel`,
passed straight through. Its docstring changes to name both tracks.

`ingest_podcasts_cmd` (`pm ingest podcasts`, which `pm ingest all` calls) **passes
`track="finance"` explicitly.** This is the line that keeps the morning pipeline's cost and runtime
unchanged. Do not leave it defaulting to `all`.

## Step 5 — Backfill run

After the checklist passes, one operator run per track. Dry run, read the plan, then `--live`:

```bash
# what would be processed, no calls, no writes
python manager.py podcast batch --track ai --max-per-channel 3 --since 2026-08-01

# then, once the plan looks right
python manager.py podcast batch --track ai --max-per-channel 3 --since 2026-08-01 --live
```

Nine channels × up to 3 episodes is up to 27 Gemini calls. **Run it once, read the output, and stop
before widening.** If the briefs from Fireship or Goldman Sachs are mostly noise, the fix is
`title_filter` or `enabled: false` in the registry, not a bigger backfill.

**Mid-prompt sign-off gate.** Present the dry-run plan table — channel, video ID, published date,
title, destination script — before the `--live` run. Bill accepts, overrides or rejects per row.

---

## Verification checklist

**Paste literal stdout. An agent-reported PASS table is not evidence.**

| # | Check | Command / expected |
|---|---|---|
| 1 | Today's behaviour preserved | `python manager.py podcast batch` — walks 14 finance + 9 AI, one video each, dry run, zero writes |
| 2 | Morning path unchanged in cost | `python manager.py ingest podcasts` — output names **finance channels only**; zero AI channels checked |
| 3 | Track filter | `python manager.py podcast batch --track ai` — exactly the 9 AI channels |
| 4 | Destination fork | in the `--track ai` output, every `Running:` line names `ai_track_sync.py`; in `--track finance`, `weekly_podcast_sync.py` |
| 5 | Backfill depth | `--track ai --max-per-channel 3 --since 2026-08-01` — up to 3 rows per channel, none published before the date |
| 6 | Word counts surfaced | the dry-run plan prints each candidate's transcript word count, so `min_words` can be set from evidence |
| 7 | Oldest-first | within one channel's rows, `published` ascends |
| 8 | `get_latest_video` shim | `python -c "from tasks.batch_podcast_sync import get_latest_video as g; print(g('UCbzQ_YWf9RsBP9ATbmv5kxQ'))"` → a `(video_id, title)` tuple |
| 9 | Dedup not reset | count before/after a dry run — identical to Step 0.4 |
| 10 | Dedup gains track on live | after the Step 5 live run, `python -c "import json;d=json.load(open('data/processed_videos.json'));print([v for v in d.values() if v.get('track')=='ai'][:2])"` |
| 11 | Failure leaves it retryable | force one channel to fail (temporary bad `channel_id`); confirm the video ID is **absent** from the dedup log afterwards |
| 12 | Validator failure = failure | force `validate_brief` to reject; confirm the orchestrator counts it as failed and does not dedup it |
| 13 | Rerun is a no-op | rerun Step 5's live command — every row reports `SKIP — already processed`, zero Gemini calls |
| 14 | Tests | `python -m pytest tests/ -q` |

Checks 11 and 12 are the ones that matter most. A dedup log that records failures as successes is a
pipeline that silently stops ingesting a channel — the failure mode that kept `morning_auto.log`
silent from 2026-07-27 to 2026-08-28.

---

## Documentation to update on completion

- **`CLAUDE.md`** — the `tasks/batch_podcast_sync.py` row gains "registry-driven, two tracks, forks to
  `weekly_podcast_sync.py` or `ai_track_sync.py`". Under Podcast & Third-Party Source Ingestion, state
  that the AI track is **not** in the morning pipeline and why. Under Known Issues, record the 15-entry
  Atom ceiling as a permanent bound on backfill depth.
- **`state.md`** — dated entry with the real backfill counts per channel and the word-count table.
- **`CLI_MANUAL.md` / `CLI_CHEATSHEET.md`** — the new flags. Both are flagged in `CLAUDE.md` as
  freshness-unverified; check them while you are in there.
- **`CHANGELOG.md`** — dated entry.

## Out of scope — do not build

- A scheduled task for the AI track. Bill installs it once he has seen a run's cost and output.
- Corpus registration, the analysis run, verification sidecars. Prompt 4.
- Any attempt to reach past the 15-entry feed ceiling — no scraping, no `yt-dlp`, no Data API key.
  If Bill wants deeper history that is a separate decision with a separate prompt.
- Parallelism. 23 channels sequentially is fine, and concurrent Gemini calls would need rate-limit
  handling this build does not have.
- Touching `weekly_podcast_sync.py`'s internals. It receives one new optional flag and is otherwise
  untouched.
