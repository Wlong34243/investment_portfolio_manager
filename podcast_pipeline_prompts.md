# Podcast Automation Pipeline — Implementation Prompts
# Target: Claude Code or Gemini CLI 3 Pro
# Run prompts 1–6 sequentially. Each prompt is self-contained.

## Overview
Build an "Idea Generation Engine" that pulls YouTube transcripts from institutional
finance podcasts, sends them to Gemini via `ask_gemini()` with Pydantic schema
enforcement, and writes the extracted allocation strategy to a new
`AI_Suggested_Allocation` tab in the Portfolio Sheet.

## Key Design Decisions

1. **Separate tab — never touch Target_Allocation.** AI writes to
   `AI_Suggested_Allocation`. Bill reviews and manually promotes to
   `Target_Allocation` if accepted. The Rebalancing page can display both
   side-by-side.

2. **DRY_RUN defaults to True in the CLI script** via its own `--live` flag
   (independent of `config.DRY_RUN` which is currently `False`). This prevents
   accidental Sheet writes on first run.

3. **SAFETY_PREAMBLE is auto-prepended.** `ask_gemini()` already prepends
   `SAFETY_PREAMBLE` to every `system_instruction` (see gemini_client.py L43-45).
   The podcast agent must NOT duplicate it.

4. **`response.parsed` returns a Pydantic instance.** When `response_schema` is
   passed, `ask_gemini()` returns the Pydantic model directly (not a dict). Call
   `.model_dump()` on the return value to get a serializable dict.

5. **Model name comes from `config.GEMINI_MODEL`.** Currently set to
   `gemini-3.1-pro-preview`. Do not hardcode model strings anywhere.

6. **Asset classes use standard GICS sectors (open-ended).** Instead of locking to
   a fixed enum, the AI is anchored to standard GICS sector names (Technology,
   Healthcare, Utilities, Industrials, Materials, Real Estate, etc.) plus
   macro categories (Fixed Income, Cash, International, Broad Market). This lets
   the AI surface displacement opportunities in sectors Bill has zero exposure to
   — the whole point of an idea generation engine. The sandbox tab keeps this safe.

---

## Pre-flight Checklist

Before running these prompts, confirm:
- [ ] `utils/gemini_client.py` exists with `ask_gemini()` signature:
      `ask_gemini(prompt, system_instruction=None, json_mode=False, max_tokens=2000, response_schema=None)`
- [ ] `SAFETY_PREAMBLE` is defined in `utils/gemini_client.py` (auto-prepended — do not duplicate in agents)
- [ ] `config.py` has `GEMINI_MODEL`, `PORTFOLIO_SHEET_ID`, `DRY_RUN`, and `TAB_*` constants
- [ ] `google-genai>=1.70.0` is installed (`pip show google-genai`)
- [ ] At least one existing agent in `utils/agents/` can be used as a pattern reference

---

## Prompt 1 of 6: Add tab constant and column schema to config.py

```text
Read config.py fully before making changes.

Add the following to config.py. Place the new tab constant directly after the
existing TAB_LOGS line (around line 79). Place the column list and col_map in
a new section after the existing GL_COL_MAP block.

1. New tab constant:

TAB_AI_SUGGESTED_ALLOCATION = "AI_Suggested_Allocation"

2. New column list:

AI_SUGGESTED_ALLOCATION_COLUMNS = [
    'Date',
    'Source',
    'Asset Class',
    'Asset Strategy',
    'Target %',
    'Min %',
    'Max %',
    'Confidence',
    'Notes',
    'Executive Summary',
    'Fingerprint',
]

3. New column map:

AI_SUGGESTED_ALLOCATION_COL_MAP = {
    'date': 'Date',
    'source': 'Source',
    'asset_class': 'Asset Class',
    'asset_strategy': 'Asset Strategy',
    'target_pct': 'Target %',
    'min_pct': 'Min %',
    'max_pct': 'Max %',
    'confidence': 'Confidence',
    'notes': 'Notes',
    'executive_summary': 'Executive Summary',
    'fingerprint': 'Fingerprint',
}

Do NOT modify any existing constants or reorder existing code. Append-only changes.

Verify: `python -c "import config; print(config.TAB_AI_SUGGESTED_ALLOCATION)"` prints
"AI_Suggested_Allocation".
```

---

## Prompt 2 of 6: Add the new tab to the Portfolio Sheet creator

```text
Read create_portfolio_sheet.py and config.py before making changes.

In create_portfolio_sheet.py, add the new tab to the SCHEMA dict:

    "AI_Suggested_Allocation": [
        "Date", "Source", "Asset Class", "Asset Strategy",
        "Target %", "Min %", "Max %", "Confidence", "Notes",
        "Executive Summary", "Fingerprint"
    ],

Also add "AI_Suggested_Allocation" to the TABS_TO_FREEZE list.

Then run the script:
    python create_portfolio_sheet.py

Verify: The script should print "Tab 'AI_Suggested_Allocation' already exists.
Skipping creation." on subsequent runs. If it creates the tab, confirm the header
row matches the 11 columns above.

Do NOT modify any existing tab schemas in the SCHEMA dict.
```

---

## Prompt 3 of 6: Update PORTFOLIO_SHEET_SCHEMA.md

```text
Read PORTFOLIO_SHEET_SCHEMA.md before making changes.

Add a new section for the AI_Suggested_Allocation tab. Place it immediately AFTER
the Target_Allocation section and BEFORE the Risk_Metrics section. Use this exact
markdown:

---

### Tab: AI_Suggested_Allocation
**Purpose:** AI-generated allocation suggestions from podcast analysis. Bill reviews
and manually promotes to Target_Allocation when accepted. App writes; Bill decides.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Date | Date | `2026-04-05` | When the analysis was generated |
| B | Source | String | `Forward Guidance EP 412` | Podcast name + episode identifier |
| C | Asset Class | String | `Technology` | Standard GICS sector or macro category (e.g., Technology, Utilities, Industrials, Materials, Real Estate, Fixed Income, Cash). AI may introduce new standard sectors for displacement opportunities. |
| D | Asset Strategy | String | `Defensive AI beneficiaries` | Thesis behind this allocation |
| E | Target % | Float | `25` | Suggested allocation. All rows must sum to 100 |
| F | Min % | Float | `20` | Lower drift band |
| G | Max % | Float | `30` | Upper drift band |
| H | Confidence | String | `High` | High / Medium / Low |
| I | Notes | String | `Capex cycle favors...` | Supporting rationale from transcript |
| J | Executive Summary | String | `Risk-off rotation...` | Same across all rows in a batch |
| K | Fingerprint | String | `2026-04-05\|Forward Guidance EP 412\|Technology` | Dedup key |

**Row 1:** Headers (frozen)
**Row 2+:** Latest AI analysis. Previous data cleared before each new write.
**Write pattern:** Clear data rows, write fresh batch. Archived to Logs tab before overwrite.

Also add a new entry to the Fingerprint Formats table:

| `AI_Suggested_Allocation` | `date\|source\|asset_class` | One row per sector per podcast analysis. |

Do NOT modify any existing tab documentation.
```

---

## Prompt 4 of 6: Create the Podcast Analyst Agent

```text
Read these files before writing code:
- utils/gemini_client.py  (exact ask_gemini signature and return behavior)
- utils/agents/thesis_screener.py  (reference pattern for agent structure)
- config.py  (constants)

CRITICAL NOTES about ask_gemini():
- SAFETY_PREAMBLE is ALREADY prepended automatically to every system_instruction
  by ask_gemini() (gemini_client.py line 43-45). Do NOT include SAFETY_PREAMBLE
  in the system_instruction string you pass in — it will be duplicated.
- When response_schema is provided, ask_gemini() returns a Pydantic model instance
  (via response.parsed), NOT a dict. Call .model_dump() to serialize.
- Default max_tokens is 2000. For this agent, pass max_tokens=4000 since a full
  10-sector allocation with notes can exceed 2000 tokens.

Create: utils/agents/podcast_analyst.py

Contents:

1. Module docstring explaining purpose: "Extracts macro allocation strategy from
   podcast transcripts using Gemini with Pydantic schema enforcement."

2. Imports: BaseModel, Field, List from pydantic/typing. ask_gemini from
   utils.gemini_client. logging.

3. Pydantic schemas:

   class SectorTarget(BaseModel):
       asset_class: str = Field(description="The macro asset class or standard GICS sector (e.g., Technology, Utilities, Industrials, Materials, Real Estate, Fixed Income, Cash). You MAY introduce a new standard sector if a strong valuation displacement opportunity is presented.")
       asset_strategy: str = Field(description="Brief thesis, e.g. 'Defensive AI beneficiaries'")
       target_pct: float = Field(description="Target allocation %. All targets must sum to 100.")
       min_pct: float = Field(description="Lower drift band, usually target_pct - 5")
       max_pct: float = Field(description="Upper drift band, usually target_pct + 5")
       confidence: str = Field(description="High, Medium, or Low")
       notes: str = Field(description="Rationale extracted from podcast")

   class PodcastStrategy(BaseModel):
       executive_summary: str = Field(description="2-3 sentence macro thesis")
       target_allocations: List[SectorTarget]
       thesis_screener_prompts: List[str] = Field(description="1-2 sentence thesis seeds for downstream agents")
       source_quality: str = Field(description="High / Medium / Low — how actionable was this content")

4. Function:

   def analyze_podcast(transcript: str, source_name: str = "Unknown Podcast") -> dict | None:
       """
       Send transcript to Gemini, extract structured allocation strategy.
       Returns dict (model_dump) on success, None on failure.
       """

       system_instruction = (
           "You are a Chief Investment Officer parsing an institutional strategy discussion.\n\n"
           "IGNORE: sponsor reads, day-trading advice, short-term options flow, meme stock hype, "
           "crypto speculation without institutional backing, and advertisements.\n\n"
           "EXTRACT: the core 6-to-12 month macro thesis, sector rotation consensus, "
           "and risk positioning.\n\n"
           "CONSTRAINTS:\n"
           "- target_pct values across all SectorTarget entries MUST sum to exactly 100.\n"
           "- Use standard GICS sectors or macro asset categories (e.g., Technology, "
           "Healthcare, Energy, Financials, Industrials, Utilities, Materials, "
           "Real Estate, Consumer Discretionary, Consumer Staples, Communication Services, "
           "International, Broad Market, Fixed Income, Cash). You MAY introduce a sector "
           "the investor currently has zero exposure to if the podcast presents a strong "
           "valuation displacement opportunity — that is the purpose of this analysis.\n"
           "- If the podcast lacks actionable allocation guidance, return a single "
           "SectorTarget with asset_class='Broad Market', target_pct=100, confidence='Low', "
           "and notes explaining why.\n"
           f"- Source: {source_name}"
       )

       prompt = f"Analyze this podcast transcript and extract a target allocation strategy:\n\n{transcript}"

       result = ask_gemini(
           prompt=prompt,
           system_instruction=system_instruction,
           response_schema=PodcastStrategy,
           max_tokens=4000,
       )

       if result is None:
           logging.error(f"Podcast analysis failed for: {source_name}")
           return None

       return result.model_dump()

Verify: `python -c "from utils.agents.podcast_analyst import analyze_podcast, PodcastStrategy; print('OK')"` — no import errors.
```

---

## Prompt 5 of 6: Create the Orchestrator Script

```text
Read these files before writing code:
- utils/agents/podcast_analyst.py  (the agent from Prompt 4)
- utils/sheet_readers.py  (for get_gspread_client)
- pipeline.py  (for write_pipeline_log, sanitize patterns)
- config.py  (DRY_RUN, PORTFOLIO_SHEET_ID, TAB_AI_SUGGESTED_ALLOCATION, TAB_LOGS)

Create: tasks/weekly_podcast_sync.py

Module docstring with usage examples:

    # Podcast Automation Pipeline — Orchestrator
    #
    # Usage:
    #   python tasks/weekly_podcast_sync.py VIDEO_ID --source-name "Forward Guidance EP 412"
    #   python tasks/weekly_podcast_sync.py VIDEO_ID --source-name "The Compound" --live
    #
    # Default: DRY RUN (prints JSON, no Sheet writes)
    # Use --live to enable Sheet writes.

Implementation:

1. sys.path setup — add the project root to sys.path so imports work when
   running from the tasks/ directory:
       import sys, os
       sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

2. Argument parsing (argparse):
   - Positional: video_id (str) — YouTube video ID
   - Optional: --source-name (str, default="Unknown Podcast")
   - Optional: --live (store_true) — when present, enables Sheet writes.
     Without this flag, the script always runs in dry-run mode regardless
     of config.DRY_RUN.

3. Transcript download:
   - from youtube_transcript_api import YouTubeTranscriptApi
   - transcript_segments = YouTubeTranscriptApi.get_transcript(video_id)
   - full_text = " ".join([seg["text"] for seg in transcript_segments])
   - Print: f"Transcript loaded: {len(full_text.split())} words"
   - If word count > 12000, print warning: "WARNING: Transcript exceeds
     12,000 words. Gemini can handle it but results may lose focus on
     earlier segments."

4. AI analysis:
   - from utils.agents.podcast_analyst import analyze_podcast
   - strategy = analyze_podcast(full_text, source_name=args.source_name)
   - If strategy is None: print "ERROR: Gemini returned no result" and sys.exit(1)
   - Validate: sum of target_pct across strategy["target_allocations"].
     If abs(total - 100.0) > 0.5: print "ERROR: Allocations sum to {total}%,
     expected 100%" and sys.exit(1)
   - Pretty-print full strategy JSON (json.dumps with indent=2). Always,
     regardless of dry-run state.

5. Dry-run gate:
   - If NOT args.live:
       print("\n--- DRY RUN COMPLETE --- No Sheet writes. Use --live to write.")
       sys.exit(0)
   - If args.live: print("\n--- LIVE MODE --- Writing to Sheet...")

6. Sheet write (only when --live):
   a. from utils.sheet_readers import get_gspread_client
   b. import config, time
   c. from datetime import datetime
   d. client = get_gspread_client()
   e. spreadsheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
   f. ws = spreadsheet.worksheet(config.TAB_AI_SUGGESTED_ALLOCATION)

   g. Archive: Read existing data rows (ws.get_all_values()[1:]).
      If any rows exist, log to Logs tab:
        - Get logs worksheet: ws_logs = spreadsheet.worksheet(config.TAB_LOGS)
        - Append one row: [timestamp, "INFO", "Podcast_Sync",
          f"Archived {len(existing_rows)} rows before overwrite",
          f"Previous source: {existing_rows[0][1] if existing_rows else 'N/A'}"]
        - time.sleep(1.0)

   h. Clear data rows (preserve header): ws.batch_clear(["A2:K1000"])
      time.sleep(1.0)

   i. Build rows from strategy:
      today = datetime.now().strftime("%Y-%m-%d")
      rows = []
      for sector in strategy["target_allocations"]:
          fingerprint = f"{today}|{args.source_name}|{sector['asset_class']}"
          rows.append([
              today,
              args.source_name,
              str(sector["asset_class"]),
              str(sector["asset_strategy"]),
              float(sector["target_pct"]),
              float(sector["min_pct"]),
              float(sector["max_pct"]),
              str(sector["confidence"]),
              str(sector["notes"]),
              str(strategy["executive_summary"]),
              fingerprint,
          ])

   j. Batch write: ws.update(f"A2:K{1 + len(rows)}", rows,
      value_input_option="USER_ENTERED")
      time.sleep(1.0)

   k. Print: f"SUCCESS: Wrote {len(rows)} allocation rows to AI_Suggested_Allocation"

7. Error handling — wrap the entire main() in try/except:
   - ImportError for youtube_transcript_api:
     print "ERROR: youtube-transcript-api not installed. Run: pip install youtube-transcript-api"
   - Exception for transcript download:
     print f"ERROR: Could not download transcript for {video_id}: {e}"
   - General Exception: print traceback, sys.exit(1)

8. Entry point:
   if __name__ == "__main__":
       main()

Verify:
- `python tasks/weekly_podcast_sync.py --help` shows usage
- `python tasks/weekly_podcast_sync.py dQw4w9WgXcQ --source-name "Test"` runs
  dry-run, prints JSON or Gemini error (depending on API key availability)
```

---

## Prompt 6 of 6: Update requirements.txt and CHANGELOG.md

```text
1. Add 'youtube-transcript-api' to requirements.txt. Insert it in alphabetical
   order among existing entries. Do not remove or reorder any existing packages.

2. Add a new entry to the TOP of CHANGELOG.md (before any existing entries):

## [Unreleased] — Podcast Automation Pipeline

### Added
- `utils/agents/podcast_analyst.py` — Gemini-powered podcast transcript analyzer
  with Pydantic schema (PodcastStrategy, SectorTarget)
- `tasks/weekly_podcast_sync.py` — CLI: YouTube transcript → Gemini → AI_Suggested_Allocation tab
- `AI_Suggested_Allocation` tab in Portfolio Sheet — AI suggestions kept separate from
  Bill's manual Target_Allocation
- `youtube-transcript-api` dependency

### Changed
- `config.py` — Added TAB_AI_SUGGESTED_ALLOCATION, AI_SUGGESTED_ALLOCATION_COLUMNS,
  AI_SUGGESTED_ALLOCATION_COL_MAP
- `create_portfolio_sheet.py` — Added AI_Suggested_Allocation to SCHEMA and TABS_TO_FREEZE
- `PORTFOLIO_SHEET_SCHEMA.md` — Documented AI_Suggested_Allocation tab schema and fingerprint

### Architecture Decision
AI suggestions write to AI_Suggested_Allocation (new tab), never to Target_Allocation.
Target_Allocation remains Bill's manual-only authoritative allocation. The Rebalancing
page can display both for comparison. Bill promotes AI suggestions manually.

**Status:** Script defaults to DRY RUN (--live flag required for Sheet writes). Safe to deploy.
```

---

## Post-Build Verification

```bash
# 1. Import checks
python -c "import config; print(config.TAB_AI_SUGGESTED_ALLOCATION)"
python -c "from utils.agents.podcast_analyst import analyze_podcast; print('OK')"
python tasks/weekly_podcast_sync.py --help

# 2. Dry-run test (needs valid YouTube ID and Gemini API key)
python tasks/weekly_podcast_sync.py VIDEO_ID --source-name "Test Run"

# 3. Confirm Target_Allocation untouched
# Open Google Sheet → Target_Allocation tab → verify no changes

# 4. Confirm AI_Suggested_Allocation tab exists with 11 column headers
```

## Gemini CLI Peer Review

After all prompts pass verification:

```bash
gemini -p "Review the new podcast pipeline files: utils/agents/podcast_analyst.py,
tasks/weekly_podcast_sync.py, and changes to config.py, create_portfolio_sheet.py,
PORTFOLIO_SHEET_SCHEMA.md. Check: 1) Does podcast_analyst.py follow the same pattern
as thesis_screener.py? 2) Is SAFETY_PREAMBLE duplicated (it should NOT be — ask_gemini
prepends it automatically)? 3) Can this pipeline ever write to Target_Allocation?
4) Are all column maps and fingerprint formats consistent with PORTFOLIO_SHEET_SCHEMA.md?
5) Does the --live flag properly gate Sheet writes?"
```

---

## Future Enhancements (Not in this build)

- **Rebalancing page integration** — side-by-side display of Target_Allocation vs
  AI_Suggested_Allocation with diff highlighting
- **Multi-podcast consensus** — run N podcasts, weight by source_quality, merge into
  a blended allocation
- **Scheduled execution** — GitHub Actions weekly cron with a list of podcast channel IDs
- **Ticker-level suggestions** — extend SectorTarget with specific ticker picks per sector
- **AI_Suggested_Allocation_History** — append-only archive tab for historical AI suggestions
