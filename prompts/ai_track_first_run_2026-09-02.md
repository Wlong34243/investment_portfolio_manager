# AI-track first run — walk the nine channels, decide which survive, then schedule

**Created:** 2026-09-02
**Executor:** Claude Code, in `C:\Dev\Investment_Portfolio`.
**Type:** one-time evaluation with a sign-off gate, followed by a scheduled-task install.
**Context:** The nine `track: "ai"` channels in `data/podcast_channels.json` have **never produced a
brief.** They were blocked by the 2026-08-31 YouTube IpBlocked incident and have not been walked
since it cleared. The entire AI track is currently carried by the Spotify `ai-dispatch` path
(STEP 4d), which is working — three briefs in three days.

> **Why these are not in `morning_auto.bat`.** The morning run calls `pm ingest podcasts`, which
> passes `track="finance"`. That is deliberate: nine more Gemini calls on the pre-market critical
> path, for content with no market-open deadline, and — more importantly — nine more transcript
> fetches from the same IP in the same burst window. Doubling that burst is precisely what produced
> the IpBlocked incident. The AI walk gets its own schedule and shares the morning's lock file so the
> two can never overlap.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```powershell
cd C:\Dev\Investment_Portfolio

# 0.1 — the nine channels, and that they are enabled
python -c "from utils.channel_registry import load_channels as L; [print(c['name'], c['channel_id'], c['enabled']) for c in L('ai')]"

# 0.2 — zero briefs from them today (dispatch briefs are a different path)
dir data\ai_briefs\*.md
python -c "import json;d=json.load(open('data/processed_videos.json'));print('ai dedup entries:', sum(1 for v in d.values() if v.get('track')=='ai'))"

# 0.3 — is YouTube answering this IP at all? ONE request.
python manager.py podcast fetch wMl6c_r0ubw
```

**Expected at 0.2:** three `*_AI_Dispatch_*.md` files (08-31, 09-01, 09-02) and **0** AI dedup
entries. **If 0.3 returns `IpBlocked`, STOP** — the block is back and nothing below will work. Do not
retry it in a loop; each attempt extends the window.

---

## Step 1 — Dry run. No Gemini calls, no writes.

```powershell
python manager.py podcast batch --track ai --max-per-channel 1
```

This walks nine RSS feeds and prints a plan line per channel. **Report the full output verbatim**,
then fill in this table — one row per channel:

| Channel | Feed resolved? | Newest video title | Words | Verdict |
|---|---|---|---|---|

`Verdict` is one of:

- **KEEP** — the feed is the right channel and the newest upload is AI-technical content.
- **WRONG CHANNEL** — the feed title or recent uploads are not the channel Bill named. Two are
  already suspected: **Matthew Berman** (`UCuar6bhYQon68ppqmU-wYXA`) previously resolved to a feed
  of Steve Kimock Band videos, and **Fireship** resolved as "Beyond Fireship". Confirm or clear both.
- **NOISE** — right channel, but the recent uploads are not AI-technical (Fireship's general
  developer content, for example). Candidate for `title_filter`, not deletion.
- **NO TRANSCRIPT** — the plan line reports the word count as unavailable *and* a manual
  `pm podcast fetch <id>` fails. Some channels ship no captions at all.
- **DEAD** — `Could not fetch videos`: the channel ID does not resolve.

The plan line's word count now reads from cached transcripts only and does **not** fetch, so a
`word count unavailable` on a first walk is expected and is not a failure.

**MID-PROMPT SIGN-OFF GATE. STOP HERE.** Present the table to Bill. He decides per row: keep,
disable, or add a `title_filter`. **Do not proceed to Step 2 on your own judgment**, and do not run
anything with `--live` before he has answered. A channel he disables is
`"enabled": false` in `data/podcast_channels.json` with the reason recorded in its `notes` field —
never deleted from the file.

---

## Step 2 — First live walk (only after sign-off)

```powershell
python manager.py podcast batch --track ai --max-per-channel 1 --live
```

One Gemini call per surviving channel, throttled 4–6s between transcript fetches. Expect this to take
a couple of minutes and to *look* stalled between channels — that is the throttle, and it is the
thing standing between you and another IP block.

Then report:

```powershell
dir data\ai_briefs\*.md
dir data\podcast_transcripts\ai\*.txt
python -c "import json;d=json.load(open('data/processed_videos.json'));print(sum(1 for v in d.values() if v.get('track')=='ai'),'ai entries')"
```

**Read the actual briefs, not just the filenames.** For each one report in one line: headline,
`novelty`, and whether the claims are AI-technical or generic commentary. This is the evidence that
decides whether the AI YouTube track is worth keeping at all — the Spotify dispatch already covers
this ground daily, and if these nine channels produce nine `novelty: commentary` briefs restating the
same news, the honest recommendation is to disable most of them.

**If the walk aborts with exit code 3**, YouTube is rate-limiting again. Report it and stop. Do not
re-run. The circuit breaker did its job by stopping at the first blocked channel instead of firing
eight more.

---

## Step 3 — Idempotency check

Run the exact Step 2 command again.

Must report `SKIP — already processed` for every channel and make **zero** Gemini calls. If it
re-analyses, **do not install the scheduled task** — a weekly job that re-pays for the same videos
is worse than no job.

---

## Step 4 — Install the schedule (only after Steps 2 and 3 pass)

`ai_track_auto.bat` is already in the repo root. It mirrors `morning_auto.bat`: venv activation, log
rotation, `logs\last_run_ai_track.json`, and it **shares `logs\pipeline.lock`** so the AI walk can
never overlap the morning finance walk — the two must not fetch transcripts from the same IP at the
same time.

Register it for **Sunday 18:00**, well clear of the weekday 07:45 morning window:

```powershell
schtasks /create /tn "AITrackWeekly" ^
  /tr "C:\Dev\Investment_Portfolio\ai_track_auto.bat" ^
  /sc weekly /d SUN /st 18:00 ^
  /rl LIMITED /f
```

Verify:

```powershell
schtasks /query /tn "AITrackWeekly" /v /fo LIST | findstr /C:"Task To Run" /C:"Schedule" /C:"Next Run Time" /C:"Status"
```

Then fire it once by hand and paste the log:

```powershell
schtasks /run /tn "AITrackWeekly"
timeout /t 90
type logs\ai_track_auto.log
type logs\last_run_ai_track.json
```

Expect `exit_code: 0` and every channel reporting `SKIP — already processed` (Step 2 consumed
today's videos). A run that reports work done here means dedup is broken.

---

## Documentation to update on completion

- **`state.md`** — dated entry: the per-channel verdict table from Step 1, which channels were
  disabled and why, and whether the nine YouTube channels earn their keep against the Spotify
  dispatch path.
- **`CHANGELOG.md`** — dated entry for `ai_track_auto.bat` + `AITrackWeekly`.
- **`CLAUDE.md`** — under Podcast & Third-Party Source Ingestion, one line: AI track runs weekly via
  `AITrackWeekly`, not in the morning pipeline, and shares `logs\pipeline.lock` with it.

## Out of scope — do not do

- Do not add the AI track to `morning_auto.bat` or to `pm ingest podcasts`. The `track="finance"`
  argument in `ingest_podcasts_cmd` is load-bearing.
- Do not raise `--max-per-channel` above 1 on the first live walk. Backfill is a separate decision
  once you know the channels are worth backfilling.
- Do not delete a channel from `data/podcast_channels.json`. Disable it with a reason.
- Do not touch the Spotify `ai-dispatch` path (STEP 4d). It works and is unrelated.
- Do not retry a `RequestBlocked` / `IpBlocked` failure. Report and stop.
