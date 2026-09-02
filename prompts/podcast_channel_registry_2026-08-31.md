# Podcast channel registry — 10 hardcoded channels become 23 across two tracks

**Created:** 2026-08-31
**Executor:** Cursor (Agent mode). Claude Code / Gemini CLI also acceptable.
**Prompt 1 of 4.** **Depends on:** nothing.
**Gates:** prompts 2, 3 and 4 — all three read the registry this prompt creates.
**Source:** Bill, 2026-08-31 — four finance channels to add, nine AI-advancement channels to start a
second track.

> `PODCAST_CHANNELS` is a dict literal inside `tasks/batch_podcast_sync.py` whose own comment admits
> the names are placeholders pending a first live run. It holds 10 entries. It is about to hold 23,
> across two tracks that need different downstream treatment. That is the moment it stops being a
> constant and becomes a data file.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement → **STOP and report.**

```bash
# 0.1 — the registry as it exists today
grep -n "PODCAST_CHANNELS" -A 16 tasks/batch_podcast_sync.py
python -c "import sys; sys.path.insert(0,'.'); from tasks.batch_podcast_sync import PODCAST_CHANNELS as P; print(len(P)); print(sorted(P))"

# 0.2 — every consumer of that name (the shim in Step 4 must satisfy all of them)
grep -rn "PODCAST_CHANNELS" --include=*.py . | grep -v __pycache__

# 0.3 — dedup log: shape and size. Do NOT reset this file.
python -c "import json;d=json.load(open('data/processed_videos.json'));print(len(d));k=next(iter(d));print(k, d[k])"

# 0.4 — transcript fetch dependency is present
python -c "import youtube_transcript_api as y; print('youtube-transcript-api', getattr(y,'__version__','?'))"

# 0.5 — RSS reachable, and the Atom shape the resolver will parse
python - <<'PY'
import urllib.request, xml.etree.ElementTree as ET
u="https://www.youtube.com/feeds/videos.xml?channel_id=UCkrwgzhIBKccuDsi_SvZtnQ"
x=urllib.request.urlopen(u,timeout=15).read()
r=ET.fromstring(x)
print("feed title:", r.find("{http://www.w3.org/2005/Atom}title").text)
print("entries:", len(r.findall("{http://www.w3.org/2005/Atom}entry")))
PY

# 0.6 — the purge that governs data/podcast_summaries/ (matters in prompt 2)
grep -n "KEEP_DAYS" utils/podcast_digest.py
grep -n "PURGE_DEFAULT_DAYS_PODCASTS" config.py
ls data/podcast_summaries/*.md | wc -l
ls data/podcast_transcripts/ | wc -l
```

**Expected at 0.1 (verified 2026-08-31):** 10 channels — Forward Guidance, The Compound, BG2 Pod,
Capital Allocators, Chat With Traders, On The Tape, CNBC Television, Top Traders Unplugged, Invest
Like The Best, On Investing (the last carrying `title_filter`). **Expected at 0.2:** two consumers —
`tasks/batch_podcast_sync.py` itself and `manager.py` (`@podcast_app.command("batch")`, which imports
the name directly). If a third consumer exists, name it and stop.

**If 0.5 fails, STOP.** No network to YouTube's feed endpoint means nothing downstream works and the
problem is not this prompt's to solve.

---

## Design decisions, already made — do not relitigate

**The registry moves to `data/podcast_channels.json`.** A 23-entry table with a per-entry track,
maintained by Bill, does not belong in a task module's import block. JSON, not YAML — the repo already
reads `data/styles.json`, `data/ticker_aliases.json`, `data/watchlist.json` this way.

**Channel ID is the primary key. The handle is metadata.** Handles are renamed by their owners (this
is not hypothetical — `@DaveShap` has been renamed more than once). An `@handle` in a registry is a
key that silently stops resolving. The `UC…` ID is permanent.

**`track` is a string enum, not a boolean.** `"finance" | "ai"`. A boolean `is_ai` forecloses the
third track that will eventually exist.

**Handles are resolved once, by Python, and the result is pinned.** Not looked up at run time. A
resolution that happens on every run is a network dependency and a rename that changes the feed under
you without a diff. Resolve, print the table, write it, review it, commit it.

**`PODCAST_CHANNELS` stays importable.** `manager.py` imports the name directly. The shim in Step 4
rebuilds the identical `{name: {"channel_id": …, "title_filter": …}}` shape from the JSON, filtered to
`track == "finance"`, so today's CLI behaviour is byte-identical after this prompt. Prompt 3 is what
teaches the callers about tracks.

**The four finance videos Bill named are backfilled through the existing path, unchanged.** They are
finance-track content; `weekly_podcast_sync.py` already handles them correctly. Step 6.

---

## The 13 new channels

Bill supplied these. **Three carry an ID he gave; ten carry only a handle. Nothing here is verified —
Step 1 resolves and prints, Bill reviews, then it is written.** Do not paste an unresolved ID into the
registry file by hand.

### Track `finance` (4 new → 14 total)

| Name | Given as | Note |
|---|---|---|
| Excess Returns Clips | `UCr5lgfnWV8bp23qWQGHZRlg` | **Check this.** The main *Excess Returns* channel is `UCPYvx_y92dvI1PSdiho0ALw`. A separate clips channel is plausible; confirm the resolver returns a feed title containing "Clips". A clips channel also means short videos — see `min_words` below. |
| Goldman Sachs | `@GoldmanSachs` | High upload volume, much of it non-investment corporate content. Candidate for `title_filter` after one live run. |
| Moonshots Highlights | `@MoonshotsHighlights` | Highlights channel — same short-video caveat as Excess Returns Clips. |
| Fundstrat | `@fundstratcapital` (Bill's note hedges: "or associated networks") | **Most likely to resolve wrong.** Tom Lee content appears under several Fundstrat-affiliated channels. Print the feed title and the three most recent episode titles before accepting. |

### Track `ai` (9 new)

| Name | Given as | Note |
|---|---|---|
| Google DeepMind | `@googledeepmind` | |
| IBM Technology | `@IBMTechnology` | |
| OpenAI | `@OpenAI` | |
| Two Minute Papers | `@TwoMinutePapers` (legacy `user/keeroyz`) | Legacy `user/` URLs still resolve; the resolver must handle `/@handle`, `/user/`, and `/channel/`. |
| Yannic Kilcher | `UCZHmQk67mSJgfCCTn7xBfew` | |
| AI Explained | `UCNJ1Ymd5yFuUPtn21xtRbbw` | |
| Matthew Berman | `UCuar6bhYQon68ppqmU-wYXA` | |
| David Shapiro | `@DaveShap` | **Expect this to fail or resolve to a renamed channel.** Report what it resolves to; do not guess. |
| Fireship | `@Fireship` | Mostly non-AI developer content. Ships with `title_filter` disabled but flagged in `notes` as the first candidate if signal-to-noise is poor. |

---

## Step 1 — `scripts/resolve_youtube_channels.py` (one-shot, dry-run by default)

Takes a list of handles/IDs, resolves each to a canonical channel ID, verifies the ID by fetching its
Atom feed, and prints a review table. **Writes nothing without `--live`.**

Resolution order per input:

1. Input already matches `^UC[A-Za-z0-9_-]{22}$` → treat as an ID, skip to verification.
2. Input is `@handle` → `GET https://www.youtube.com/@<handle>` and extract the ID with
   `re.search(r'"(?:channelId|externalId)"\s*:\s*"(UC[A-Za-z0-9_-]{22})"', html)`.
3. Input is `user/<name>` → same fetch against `https://www.youtube.com/user/<name>`.

Send a browser `User-Agent`; YouTube returns a consent interstitial to a bare urllib UA. Rate-limit to
one request per 2 seconds. On any non-200 or no regex match, record `UNRESOLVED` — **do not fall back
to a search endpoint and do not guess.**

Verification for every resolved ID — fetch `https://www.youtube.com/feeds/videos.xml?channel_id=<id>`
and print the feed `<title>` plus the three most recent entry titles.

Required stdout, one row per channel:

```
NAME                    INPUT                    RESOLVED_ID                 FEED_TITLE              LATEST_3
Excess Returns Clips    UCr5lgfnWV8bp23qWQGHZRlg  UCr5lgfnWV8bp23qWQGHZRlg   <actual>                <3 titles>
David Shapiro           @DaveShap                 UNRESOLVED                  —                       —
```

**Mid-prompt sign-off gate. STOP here and present the table.** Bill accepts, overrides or rejects per
row. Two things he is checking: that `FEED_TITLE` is the channel he meant, and that `LATEST_3` looks
like the content he wants ingested. Do not proceed to Step 2 on your own judgment. An `UNRESOLVED`
row is not a blocker for the other 22 — it is written as `"enabled": false` with the failure recorded
in `notes`.

---

## Step 2 — `data/podcast_channels.json`

Written by Step 1 under `--live`, after sign-off. Schema, one object per channel:

```json
{
  "schema_version": 1,
  "generated_at": "2026-08-31T00:00:00",
  "channels": [
    {
      "name": "Forward Guidance",
      "channel_id": "UCkrwgzhIBKccuDsi_SvZtnQ",
      "handle": null,
      "track": "finance",
      "enabled": true,
      "title_filter": null,
      "min_words": null,
      "added": "2026-04-01",
      "notes": "migrated from PODCAST_CHANNELS dict"
    }
  ]
}
```

Field rules:

- `name` — flows into the `Source` column in Sheets for finance-track rows. Keep the existing 10
  names byte-identical or you orphan every historical row in `AI_Suggested_Allocation`.
- `track` — `"finance"` or `"ai"`. No other value; the loader raises on anything else.
- `enabled` — `false` skips the channel entirely. `UNRESOLVED` rows land here.
- `title_filter` — preserved semantics from today's dict (substring, case-insensitive). Only
  `On Investing` uses it at migration time.
- `min_words` — **new, nullable.** Skip an episode whose transcript is shorter than this. Exists for
  the two clips/highlights channels, where a 90-second clip produces a transcript too thin to summarise
  but still burns a Gemini call and a dedup entry. Set it to `null` at migration; prompt 3 is where it
  is enforced, and Bill sets the value after seeing real word counts.

**Order the file: all 14 finance entries, then all 9 AI entries.** It is a file Bill edits by hand.

---

## Step 3 — `utils/channel_registry.py`

```python
def load_channels(track: str | None = None, enabled_only: bool = True) -> list[dict]
def channels_as_legacy_dict(track: str = "finance") -> dict
```

`load_channels` reads the JSON, validates every entry (`channel_id` matches the `UC…` pattern,
`track` in `{"finance","ai"}`, `name` non-empty and unique), and **raises on a malformed file rather
than silently returning a short list.** A registry that quietly drops a channel is a pipeline that
quietly stops ingesting a source — the failure mode that kept `logs/morning_auto.log` silent for a
month.

`channels_as_legacy_dict` returns exactly today's `{name: {"channel_id", "title_filter"}}` shape.

No caching. The file is read once per run, it is 23 entries.

---

## Step 4 — Shim `tasks/batch_podcast_sync.py`

Replace the dict literal with:

```python
from utils.channel_registry import channels_as_legacy_dict
PODCAST_CHANNELS = channels_as_legacy_dict(track="finance")
```

Delete the placeholder-names comment block — it is answered by Step 1. **Change nothing else in this
file.** The fork by track is prompt 3; this prompt ends with behaviour identical to today plus four
more finance channels.

---

## Step 5 — Dedup log gains `track`

`data/processed_videos.json` records gain a `"track"` key on write. **Do not backfill, do not reset,
do not rewrite existing records** — 200+ entries with no `track` key are finance by definition, and
readers treat a missing key as `"finance"`. The file is the only thing standing between a re-run and a
duplicate Gemini bill.

---

## Step 6 — Backfill the four videos Bill named

Finance track, existing path, one at a time. Dry run first, read the JSON, then `--live`:

```bash
python tasks/weekly_podcast_sync.py dACEL8cjfsw --source-name "Excess Returns Clips: <actual title>"
python tasks/weekly_podcast_sync.py gZweef8LX7M --source-name "Goldman Sachs: <actual title>"
python tasks/weekly_podcast_sync.py qQfUbo7Ldc0 --source-name "Moonshots Highlights: <actual title>"
python tasks/weekly_podcast_sync.py v-MNUzWmmok --source-name "Fundstrat: <actual title>"
```

Take `<actual title>` from the resolver's feed output or from `pm podcast fetch <id>`; do not invent
one. `gZweef8LX7M` is reported by Bill as Ken Griffin on AI, US–China tensions and US data centers —
confirm against the feed rather than trusting the note.

**Two of these will probably fail, and that is information, not an error to work around.** Clips and
highlights channels often carry auto-captions only, or none; `YouTubeTranscriptApi` raises and the
script exits 1. Record which video IDs failed and why. If a clips channel cannot produce transcripts
at all, that channel belongs at `"enabled": false` and Bill should be told, not worked around with a
scraper.

After a successful `--live` run, add each video ID to `data/processed_videos.json` with its track so
the next batch run does not reprocess it.

---

## Verification checklist

**Paste literal stdout. An agent-reported PASS table is not evidence.**

| # | Check | Command / expected |
|---|---|---|
| 1 | Registry parses | `python -c "from utils.channel_registry import load_channels as L; print(len(L()), len(L('finance')), len(L('ai')))"` → `23 14 9` (fewer if rows are disabled — state which) |
| 2 | Legacy shape unchanged | `python -c "from utils.channel_registry import channels_as_legacy_dict as D; print(D()['On Investing'])"` → includes `title_filter: 'On Investing'` |
| 3 | Original 10 intact | diff the 10 migrated `name`/`channel_id` pairs against the Step 0.1 output — byte-identical |
| 4 | Import still works | `python -c "from tasks.batch_podcast_sync import PODCAST_CHANNELS as P; print(len(P))"` → 14 |
| 5 | CLI unchanged | `python manager.py podcast batch` (no `--live`) — completes, dry run, checks 14 finance channels, **zero AI channels** |
| 6 | Bad track raises | temporarily set one entry to `"track": "macro"`, reload, confirm a raised error naming the entry; revert |
| 7 | Duplicate ID raises | temporarily duplicate a `channel_id`, confirm raise; revert |
| 8 | Dedup log untouched | `python -c "import json;print(len(json.load(open('data/processed_videos.json'))))"` — same count as Step 0.3 (plus any Step 6 backfills) |
| 9 | Backfill result | for each of the four video IDs: the summary file written, or the literal traceback showing why not |
| 10 | Tests | `python -m pytest tests/ -q` |

---

## Documentation to update on completion

- **`CLAUDE.md`** — the `tasks/batch_podcast_sync.py` row in Key Files gains "reads
  `data/podcast_channels.json`"; add `utils/channel_registry.py`. Under Podcast & Third-Party Source
  Ingestion, Path 1 gains a sentence that the channel set is a registry file with a `track` field and
  that only `track: finance` reaches the allocation summariser.
- **`state.md`** — dated entry with the real resolved-channel table from Step 1, including
  every `UNRESOLVED`.
- **`CHANGELOG.md`** — dated entry.
- **`docs/claude_project_instructions.md`** — the Research and idea generation section now needs the
  registry sentence; Bill maintains this file.

## Out of scope — do not build

- Any AI-track summariser. Prompt 2. Adding the 9 AI channels to the registry does **not** mean they
  can be processed yet — `enabled: true` on an AI row is harmless because prompt 1 leaves every caller
  filtered to `track == "finance"`.
- Multi-episode backfill, `--since`, `--max-per-channel`. Prompt 3.
- Corpus indexing of anything new. Prompt 4.
- A YouTube Data API key, `yt-dlp`, or any new dependency. RSS + `youtube-transcript-api` already do
  this job and are already installed.
- Touching `utils/agents/podcast_analyst.py`. Prompt 2 adds a sibling; it does not edit this one.
