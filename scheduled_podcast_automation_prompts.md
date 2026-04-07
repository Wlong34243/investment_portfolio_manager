# Scheduled Podcast Automation — Implementation Prompts
# Target: Claude Code or Gemini CLI
# Prerequisite: podcast_pipeline_prompts.md (Prompts 1–6) must be complete first.
# Run these 4 prompts sequentially. Each is self-contained.

## Overview

This is the **"last mile"** of the Podcast Automation Pipeline. The core pipeline
(transcript → Gemini → AI_Suggested_Allocation) was built in `podcast_pipeline_prompts.md`.
This document adds two things:

1. **Batch Orchestrator** — a wrapper script that uses YouTube RSS feeds to auto-detect
   the newest episode from each tracked podcast channel, then calls
   `tasks/weekly_podcast_sync.py` for each one.
2. **GitHub Actions Cron** — a workflow that runs the batch orchestrator every Friday
   at 5:00 PM EST (10:00 PM UTC), fully unattended.

When complete, Bill's Saturday morning workflow becomes: open Streamlit → check
AI_Suggested_Allocation tab → new strategy is already there.

---

## Architecture Diagram

```text
┌──────────────────────────────────────────────────────────────┐
│  GitHub Actions (Friday 5:00 PM EST)                         │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  batch_podcast_sync.py                                 │  │
│  │                                                        │  │
│  │  For each channel in PODCAST_CHANNELS:                 │  │
│  │    1. Fetch YouTube RSS feed (no API key needed)       │  │
│  │    2. Extract latest video_id from XML                 │  │
│  │    3. Check dedup log (skip if already processed)      │  │
│  │    4. Shell out to weekly_podcast_sync.py --live        │  │
│  └──────────────┬─────────────────────────────────────────┘  │
│                 │                                            │
│                 ▼                                            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  weekly_podcast_sync.py (existing — no changes)        │  │
│  │    1. Download transcript (youtube-transcript-api)     │  │
│  │    2. Send to Gemini (analyze_podcast)                 │  │
│  │    3. Write to AI_Suggested_Allocation tab             │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

1. **RSS over YouTube Data API.** YouTube provides a free, keyless RSS feed for every
   channel at `https://www.youtube.com/feeds/videos.xml?channel_id={ID}`. No OAuth,
   no quota, no GCP console setup. The feed returns the 15 most recent uploads — more
   than enough to find the latest episode.

2. **Standard library only for RSS parsing.** We use `urllib.request` + `xml.etree.ElementTree`
   instead of adding `feedparser` as a dependency. The YouTube RSS feed is well-structured
   XML with a predictable namespace. No reason to add a dependency for 15 lines of parsing.

3. **Dedup via processed_videos.json.** A simple JSON file at `data/processed_videos.json`
   tracks which video IDs have already been processed. This prevents re-running the same
   episode if the cron fires before the next episode drops. The file is committed to the
   repo so state persists across Actions runs.

4. **Shell out to existing script.** The batch orchestrator calls `weekly_podcast_sync.py`
   via `subprocess.run()` rather than importing its internals. This keeps the two scripts
   decoupled and means `weekly_podcast_sync.py` remains usable standalone for ad-hoc runs.

5. **`--live` flag passed through.** The batch orchestrator has its own `--live` flag that
   gates whether it passes `--live` to `weekly_podcast_sync.py`. Default is dry-run.
   GitHub Actions workflow passes `--live` explicitly.

6. **One podcast per run wins.** Since `AI_Suggested_Allocation` uses a clear-and-replace
   write pattern, running multiple podcasts in sequence means the last one wins. This is
   fine for now — the Future Enhancement for multi-podcast consensus will merge them.
   The batch script processes channels in order and logs each run.

---

## Pre-flight Checklist

Before running these prompts, confirm:
- [ ] `tasks/weekly_podcast_sync.py` exists and works
      (`python tasks/weekly_podcast_sync.py --help` prints usage)
- [ ] `utils/agents/podcast_analyst.py` exists
      (`python -c "from utils.agents.podcast_analyst import analyze_podcast; print('OK')"`)
- [ ] `AI_Suggested_Allocation` tab exists in the Portfolio Sheet with 11 column headers
- [ ] `config.py` has `TAB_AI_SUGGESTED_ALLOCATION` constant
- [ ] `youtube-transcript-api` is in `requirements.txt`
- [ ] You have the YouTube Channel IDs for your target podcasts
      (find via: view page source on the channel page, search for `channel_id`)

---

## Prompt 1 of 4: Create the Batch Orchestrator

```text
Read these files before writing code:
- tasks/weekly_podcast_sync.py  (the existing single-video orchestrator)
- config.py  (for project structure reference)
- requirements.txt  (to confirm no new deps needed)

Create: tasks/batch_podcast_sync.py

Module docstring:

    # Batch Podcast Sync — Scheduled Orchestrator
    #
    # Finds the newest episode for each tracked podcast channel via YouTube RSS,
    # checks against a local dedup log, and runs weekly_podcast_sync.py for new episodes.
    #
    # Usage:
    #   python tasks/batch_podcast_sync.py              # Dry run — detect episodes, no Sheet writes
    #   python tasks/batch_podcast_sync.py --live        # Live — detect + process + write to Sheet
    #
    # Called by: .github/workflows/podcast_sync.yml (weekly cron)
    # Can also be run manually from the terminal.

Implementation:

1. Imports — standard library only:
   - import subprocess, sys, os, json, logging
   - import urllib.request
   - import xml.etree.ElementTree as ET
   - from datetime import datetime

2. sys.path setup (same pattern as weekly_podcast_sync.py):
   sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

3. Logging setup:
   logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
   logger = logging.getLogger(__name__)

4. Constants:

   PODCAST_CHANNELS = {
       "Forward Guidance": "UCbX0o5nB5X4H6zG1yW6T_Nw",
       "The Compound": "UC7bE6r_K4vXw-8G7d2tO_hQ",
   }

   DEDUP_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "processed_videos.json")

   # YouTube Atom feed namespace
   YT_NS = "http://www.youtube.com/xml/schemas/2015"
   ATOM_NS = "http://www.w3.org/2005/Atom"

5. Dedup helpers:

   def load_processed_videos() -> dict:
       """Load the dedup log. Returns dict of {video_id: {channel, title, processed_at}}."""
       if os.path.exists(DEDUP_FILE):
           with open(DEDUP_FILE, "r") as f:
               return json.load(f)
       return {}

   def save_processed_videos(data: dict) -> None:
       """Write the dedup log. Creates data/ directory if needed."""
       os.makedirs(os.path.dirname(DEDUP_FILE), exist_ok=True)
       with open(DEDUP_FILE, "w") as f:
           json.dump(data, f, indent=2)

6. RSS fetch function:

   def get_latest_video(channel_id: str) -> tuple[str, str] | tuple[None, None]:
       """
       Fetch the YouTube RSS feed for a channel and return (video_id, title)
       for the most recent upload. Returns (None, None) on failure.
       """
       feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
       try:
           with urllib.request.urlopen(feed_url, timeout=15) as response:
               xml_data = response.read()
           root = ET.fromstring(xml_data)

           # Find the first <entry> element (most recent video)
           entry = root.find(f"{{{ATOM_NS}}}entry")
           if entry is None:
               return None, None

           # Extract video ID from <yt:videoId>
           video_id_elem = entry.find(f"{{{YT_NS}}}videoId")
           title_elem = entry.find(f"{{{ATOM_NS}}}title")

           video_id = video_id_elem.text if video_id_elem is not None else None
           title = title_elem.text if title_elem is not None else "Unknown Title"

           return video_id, title
       except Exception as e:
           logger.error(f"Failed to fetch RSS for channel {channel_id}: {e}")
           return None, None

7. Main function:

   def main():
       import argparse
       parser = argparse.ArgumentParser(description="Batch podcast sync via YouTube RSS")
       parser.add_argument("--live", action="store_true",
                           help="Enable Sheet writes (passes --live to weekly_podcast_sync.py)")
       args = parser.parse_args()

       mode = "LIVE" if args.live else "DRY RUN"
       logger.info(f"=== Batch Podcast Sync — {mode} ===")

       processed = load_processed_videos()
       results = {"processed": [], "skipped": [], "failed": []}

       for channel_name, channel_id in PODCAST_CHANNELS.items():
           logger.info(f"Checking: {channel_name} ({channel_id})")

           video_id, title = get_latest_video(channel_id)
           if video_id is None:
               logger.warning(f"  Could not fetch latest video for {channel_name}")
               results["failed"].append(channel_name)
               continue

           logger.info(f"  Latest: '{title}' (ID: {video_id})")

           # Dedup check
           if video_id in processed:
               logger.info(f"  SKIP — already processed on {processed[video_id]['processed_at']}")
               results["skipped"].append(channel_name)
               continue

           # Build the command
           script_path = os.path.join(os.path.dirname(__file__), "weekly_podcast_sync.py")
           cmd = [
               sys.executable, script_path,
               video_id,
               "--source-name", f"{channel_name}: {title}",
           ]
           if args.live:
               cmd.append("--live")

           logger.info(f"  Running: {' '.join(cmd)}")

           # Execute
           result = subprocess.run(cmd, capture_output=True, text=True)

           if result.returncode == 0:
               logger.info(f"  SUCCESS for {channel_name}")
               if result.stdout:
                   # Print last 5 lines of output (summary)
                   for line in result.stdout.strip().split("\n")[-5:]:
                       logger.info(f"    {line}")

               # Record in dedup log
               processed[video_id] = {
                   "channel": channel_name,
                   "title": title,
                   "processed_at": datetime.now().isoformat(),
               }
           else:
               logger.error(f"  FAILED for {channel_name} (exit code {result.returncode})")
               if result.stderr:
                   for line in result.stderr.strip().split("\n")[-5:]:
                       logger.error(f"    {line}")
               results["failed"].append(channel_name)
               continue

           results["processed"].append(channel_name)

       # Save dedup log (even in dry-run, so we remember what we've seen)
       save_processed_videos(processed)

       # Summary
       logger.info("=== Summary ===")
       logger.info(f"  Processed: {results['processed'] or 'None'}")
       logger.info(f"  Skipped (already done): {results['skipped'] or 'None'}")
       logger.info(f"  Failed: {results['failed'] or 'None'}")

8. Entry point:
   if __name__ == "__main__":
       main()

Verify:
- `python tasks/batch_podcast_sync.py --help` shows usage
- `python tasks/batch_podcast_sync.py` runs in dry-run, prints RSS results
  (requires internet access)
```

---

## Prompt 2 of 4: Create the GitHub Actions Workflow

```text
Create: .github/workflows/podcast_sync.yml

Contents:

name: Weekly Podcast Sync

on:
  schedule:
    # 10:00 PM UTC every Friday = 5:00 PM EST / 6:00 PM EDT
    - cron: '0 22 * * 5'
  workflow_dispatch:
    # Manual trigger from GitHub UI for testing

jobs:
  sync_podcasts:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          # Need write access to commit processed_videos.json back
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run batch podcast sync (LIVE)
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GCP_SERVICE_ACCOUNT_JSON: ${{ secrets.GCP_SERVICE_ACCOUNT_JSON }}
        run: python tasks/batch_podcast_sync.py --live

      - name: Commit dedup log
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/processed_videos.json
          git diff --staged --quiet || git commit -m "chore: update processed_videos.json [skip ci]"
          git push

Verify:
- File exists at .github/workflows/podcast_sync.yml
- YAML is valid (no tab characters, proper indentation)
- `workflow_dispatch` is present for manual testing
```

---

## Prompt 3 of 4: Handle GCP Credentials in GitHub Actions

```text
Read these files before writing code:
- utils/sheet_readers.py  (how get_gspread_client() loads credentials)
- config.py  (any credential path references)

The existing app loads GCP credentials from .streamlit/secrets.toml (on Streamlit Cloud)
or from a local service_account.json file. In GitHub Actions, neither exists.

We need to support a third credential source: the GCP_SERVICE_ACCOUNT_JSON environment
variable, which contains the entire service account JSON as a string.

Modify: utils/sheet_readers.py

In the get_gspread_client() function, add a credential resolution chain:

    def get_gspread_client():
        """
        Returns an authorized gspread client. Credential resolution order:
        1. GCP_SERVICE_ACCOUNT_JSON env var (GitHub Actions — JSON string)
        2. .streamlit/secrets.toml (Streamlit Cloud)
        3. service_account.json file (local development)
        """
        import os, json
        from google.oauth2.service_account import Credentials

        SCOPES = ["https://spreadsheets.google.com/feeds",
                   "https://www.googleapis.com/auth/drive"]

        # Option 1: Environment variable (GitHub Actions)
        env_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
        if env_json:
            info = json.loads(env_json)
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            return gspread.authorize(creds)

        # Option 2: Streamlit secrets (Streamlit Cloud)
        try:
            import streamlit as st
            if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
                info = dict(st.secrets["gcp_service_account"])
                creds = Credentials.from_service_account_info(info, scopes=SCOPES)
                return gspread.authorize(creds)
        except Exception:
            pass

        # Option 3: Local file
        creds = Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
        return gspread.authorize(creds)

IMPORTANT: Do NOT remove any existing imports or break the current Streamlit Cloud path.
The env var path is additive — it runs first only when the env var is present.

Verify:
- App still works locally (Option 3)
- App still works on Streamlit Cloud (Option 2)
- Setting GCP_SERVICE_ACCOUNT_JSON env var and running weekly_podcast_sync.py works (Option 1)
```

---

## Prompt 4 of 4: Update requirements.txt, .gitignore, and CHANGELOG.md

```text
1. Check requirements.txt — ensure 'youtube-transcript-api' is present.
   If missing, add it alphabetically. Do NOT add feedparser (we use stdlib).

2. Check .gitignore — ensure 'data/processed_videos.json' is NOT in .gitignore.
   This file must be committed so GitHub Actions can track dedup state across runs.
   If there is a blanket 'data/' ignore rule, add an exception:
       !data/processed_videos.json

3. Add to the TOP of CHANGELOG.md:

## [Unreleased] — Scheduled Podcast Automation

### Added
- `tasks/batch_podcast_sync.py` — Batch orchestrator: YouTube RSS → episode detection
  → dedup check → calls `weekly_podcast_sync.py` for new episodes
- `.github/workflows/podcast_sync.yml` — GitHub Actions cron: runs every Friday at
  5:00 PM EST, commits dedup log back to repo
- `data/processed_videos.json` — Dedup log tracking which video IDs have been processed
- GCP credential resolution chain in `utils/sheet_readers.py`: env var → Streamlit
  secrets → local file (enables GitHub Actions without Streamlit)

### Architecture Decision
Batch orchestrator shells out to `weekly_podcast_sync.py` via subprocess rather than
importing internals. This keeps the single-video CLI usable for ad-hoc runs and the
batch script focused on episode detection + dedup. Last podcast processed wins the
AI_Suggested_Allocation tab (clear-and-replace pattern). Multi-podcast consensus is
a future enhancement.

**Status:** Dry-run by default. GitHub Actions workflow passes --live explicitly.
```

---

## Post-Build Verification

```bash
# 1. Batch orchestrator works
python tasks/batch_podcast_sync.py --help
python tasks/batch_podcast_sync.py          # Dry run — should fetch RSS, print latest episodes

# 2. Dedup log created
cat data/processed_videos.json              # Should exist after first run (may be empty {})

# 3. GitHub Actions workflow is valid YAML
python -c "import yaml; yaml.safe_load(open('.github/workflows/podcast_sync.yml'))"

# 4. Credential chain works (test env var path)
export GCP_SERVICE_ACCOUNT_JSON='<paste your service account JSON here>'
python -c "from utils.sheet_readers import get_gspread_client; c = get_gspread_client(); print('OK')"
unset GCP_SERVICE_ACCOUNT_JSON

# 5. Full end-to-end dry run
python tasks/batch_podcast_sync.py          # Should find latest episodes, print strategies

# 6. Full end-to-end live run (when ready)
python tasks/batch_podcast_sync.py --live   # Writes to AI_Suggested_Allocation
```

---

## GitHub Setup (Manual — One-Time)

After pushing the generated files to GitHub, complete these steps in the browser:

### Step 1: Add Repository Secrets
1. Go to `github.com/Wlong34243/investment-portfolio-manager`
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Add two **Repository secrets**:

| Secret Name | Value |
|---|---|
| `GEMINI_API_KEY` | Your Gemini API key from Google AI Studio |
| `GCP_SERVICE_ACCOUNT_JSON` | The entire contents of your `service_account.json` file (paste the full JSON) |

### Step 2: Verify Workflow Registered
1. Go to the **Actions** tab in your repo
2. You should see "Weekly Podcast Sync" in the left sidebar
3. If it doesn't appear, check that the YAML file is at exactly
   `.github/workflows/podcast_sync.yml` (note the `.github` directory with a dot)

### Step 3: Manual Test Run
1. In the **Actions** tab, click "Weekly Podcast Sync"
2. Click **"Run workflow"** → select `main` branch → click the green button
3. Watch the run logs. You should see:
   - RSS feeds fetched successfully
   - Transcript downloaded
   - Gemini analysis printed
   - Rows written to AI_Suggested_Allocation
   - Dedup log committed back to repo
4. Open your Google Sheet → check `AI_Suggested_Allocation` tab for new rows

### Step 4: Confirm Cron is Active
After the manual test succeeds, the cron will fire automatically every Friday at
10:00 PM UTC (5:00 PM EST). You can verify the next scheduled run in the Actions tab.

---

## Adding New Podcasts

To add a new podcast channel to the rotation:

1. Go to the YouTube channel page
2. View page source (Ctrl+U), search for `channel_id` or `channelId`
3. Copy the 24-character ID (starts with `UC`)
4. Open `tasks/batch_podcast_sync.py`
5. Add the channel to the `PODCAST_CHANNELS` dictionary:
   ```python
   PODCAST_CHANNELS = {
       "Forward Guidance": "UCbX0o5nB5X4H6zG1yW6T_Nw",
       "The Compound": "UC7bE6r_K4vXw-8G7d2tO_hQ",
       "Macro Voices": "UC_NEW_CHANNEL_ID_HERE",  # ← add here
   }
   ```
6. Commit and push. The next Friday cron run will pick it up automatically.

---

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| RSS fetch returns None | Channel ID is wrong or channel has no public uploads | Verify channel ID on youtube.com |
| Transcript unavailable | Video has no captions (live streams, music) | Skip — the script handles this gracefully |
| Gemini returns None | API key invalid or quota exceeded | Check GEMINI_API_KEY secret in GitHub |
| Sheet write fails | GCP_SERVICE_ACCOUNT_JSON malformed | Re-paste the full JSON into GitHub Secrets |
| Same episode processes twice | processed_videos.json not committed | Check the "Commit dedup log" step in Actions |
| Actions workflow not visible | YAML in wrong directory | Must be `.github/workflows/` (with dot prefix) |

---

## Future Enhancements (Not in this build)

- **Multi-podcast consensus** — run N podcasts, merge allocations weighted by
  source_quality into a blended strategy before writing to the tab
- **Episode filtering** — skip non-podcast uploads (shorts, clips, trailers)
  using video duration from RSS metadata
- **Notification on failure** — GitHub Actions can send Slack/email on job failure
- **AI_Suggested_Allocation_History** — archive tab for historical AI suggestions
  (currently archived to Logs tab only)
- **Configurable channel list** — move PODCAST_CHANNELS to Config tab in Google Sheet
  so Bill can add/remove channels without code changes
