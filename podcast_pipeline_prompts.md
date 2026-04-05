# Podcast Automation Pipeline — Implementation Prompts

## Overview
Build an "Idea Generation Engine" that pulls YouTube transcripts from institutional finance podcasts, uses Gemini 3 to extract a macro thesis and suggested allocation strategy, and writes it to a **new** `AI_Suggested_Allocation` tab in the Portfolio Sheet.

**Key design decisions baked into these prompts:**
- AI suggestions write to `AI_Suggested_Allocation` (new tab), **never** to `Target_Allocation` (Bill's manual targets). The Rebalancing page displays both side-by-side.
- `DRY_RUN` gate follows the existing `config.DRY_RUN` pattern — console output only until Bill verifies.
- Before overwriting, the script archives the previous AI suggestion with a timestamp.
- Asset class enum expanded to match Bill's actual portfolio sectors (Technology, Energy, Healthcare, Financials, International, Broad Market, Fixed Income, Cash, Alternatives, Crypto-Adjacent).
- Pydantic schema enforces `response_schema` via the existing `ask_gemini()` function in `utils/gemini_client.py`.
- `SAFETY_PREAMBLE` included in all AI prompts per project convention.

---

## Pre-flight: Read before executing

Before running these prompts, confirm:
1. `utils/gemini_client.py` exists with `ask_gemini()` and `SAFETY_PREAMBLE` (upgraded to Pydantic `response_schema` support per April 5 changes).
2. `config.py` has `GEMINI_MODEL`, `PORTFOLIO_SHEET_ID`, `DRY_RUN`, and tab name constants.
3. The `google-genai` SDK is installed (already in `requirements.txt`).

---

## Prompt 1 of 6: Add new tab constant and schema to config.py

```
Read config.py and PORTFOLIO_SHEET_SCHEMA.md before making changes.

Add the following to config.py:

1. A new tab name constant below the existing TAB_* constants:
   TAB_AI_SUGGESTED_ALLOCATION = "AI_Suggested_Allocation"

2. A new column list for the AI suggestions tab:
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

3. A column map for the AI suggestions tab:
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

Do NOT modify any existing constants. Append only.
```

---

## Prompt 2 of 6: Add the new tab to the Portfolio Sheet

```
Read create_portfolio_sheet.py and config.py before making changes.

Add the new AI_Suggested_Allocation tab to the SCHEMA dict in create_portfolio_sheet.py:

    "AI_Suggested_Allocation": [
        "Date", "Source", "Asset Class", "Asset Strategy",
        "Target %", "Min %", "Max %", "Confidence", "Notes",
        "Executive Summary", "Fingerprint"
    ],

Also add "AI_Suggested_Allocation" to the TABS_TO_FREEZE list.

Then run the script to create the tab:
    python create_portfolio_sheet.py

Verify the tab was created and has the correct headers. If the tab already exists, the script should skip it (existing behavior).

Do NOT modify any existing tab schemas.
```

---

## Prompt 3 of 6: Update PORTFOLIO_SHEET_SCHEMA.md

```
Read PORTFOLIO_SHEET_SCHEMA.md before making changes.

Add a new section for the AI_Suggested_Allocation tab after the Target_Allocation section. Use this exact content:

---

### Tab: AI_Suggested_Allocation
**Purpose:** AI-generated allocation suggestions from podcast analysis. Bill reviews these and manually promotes to Target_Allocation if accepted. App writes; Bill decides.

| Column | Header | Type | Example | Notes |
|--------|--------|------|---------|-------|
| A | Date | Date | `2026-04-05` | When the analysis was generated |
| B | Source | String | `Forward Guidance EP 412` | Podcast name + episode |
| C | Asset Class | String | `Technology` | Must be one of: Technology, Energy, Healthcare, Financials, International, Broad Market, Fixed Income, Cash, Alternatives, Crypto-Adjacent |
| D | Asset Strategy | String | `Defensive AI beneficiaries` | The thesis behind this allocation |
| E | Target % | Float | `25` | Suggested allocation percentage |
| F | Min % | Float | `20` | Lower band |
| G | Max % | Float | `30` | Upper band |
| H | Confidence | String | `High` | High / Medium / Low — model's self-assessed confidence |
| I | Notes | String | `Podcast emphasized AI capex cycle...` | Supporting rationale from transcript |
| J | Executive Summary | String | `Risk-off rotation into...` | One per batch (same value across all rows in a batch) |
| K | Fingerprint | String | `2026-04-05\|Forward Guidance EP 412\|Technology` | Dedup key |

**Row 1:** Headers (frozen)
**Row 2+:** One batch per podcast analysis. Previous batch archived before overwrite.
**Write pattern:** Clear data rows and rewrite with latest analysis. Archive previous batch to AI_Suggested_Allocation_History (future enhancement) or log to Logs tab.

Do NOT modify any existing tab documentation.
```

---

## Prompt 4 of 6: Create the Podcast Analyst Agent

```
Read the following files before writing any code:
- utils/gemini_client.py (for ask_gemini signature, SAFETY_PREAMBLE, response_schema pattern)
- utils/agents/thesis_screener.py (for existing Pydantic agent pattern)
- config.py (for GEMINI_MODEL, constants)

Create a new file at utils/agents/podcast_analyst.py with the following:

1. Pydantic schemas:

class SectorTarget(BaseModel):
    asset_class: str — Must be one of: Technology, Energy, Healthcare, Financials, International, Broad Market, Fixed Income, Cash, Alternatives, Crypto-Adjacent. Use Field(description=...) to document this constraint.
    asset_strategy: str — Brief thesis description (e.g., "Defensive AI beneficiaries")
    target_pct: float — Target allocation %. All targets across the list must sum to 100.
    min_pct: float — Lower drift band (usually target - 5)
    max_pct: float — Upper drift band (usually target + 5)
    confidence: str — "High", "Medium", or "Low"
    notes: str — Rationale extracted from the podcast

class PodcastStrategy(BaseModel):
    executive_summary: str — 2-3 sentence macro thesis
    target_allocations: List[SectorTarget]
    thesis_screener_prompts: List[str] — 1-2 sentence thesis seeds for downstream agents
    source_quality: str — "High" / "Medium" / "Low" — how actionable was this podcast

2. The analyze_podcast function:

def analyze_podcast(transcript: str, source_name: str = "Unknown Podcast") -> dict:
    """
    Pass a raw podcast transcript to Gemini and extract a structured allocation strategy.
    Returns the Pydantic model as a dict (model_dump()).
    """
    
    The system_instruction must include:
    - SAFETY_PREAMBLE (imported from utils.gemini_client)
    - Role: "You are a Chief Investment Officer parsing an institutional strategy discussion."
    - Explicit instruction to IGNORE: sponsor reads, day-trading advice, short-term options flow, meme stock hype, and crypto speculation without institutional backing.
    - Explicit instruction to EXTRACT: the core 6-to-12 month macro thesis, sector rotation consensus, and risk positioning.
    - Constraint: target_pct values across all SectorTarget entries MUST sum to exactly 100.
    - Constraint: Use ONLY these asset classes: Technology, Energy, Healthcare, Financials, International, Broad Market, Fixed Income, Cash, Alternatives, Crypto-Adjacent.
    - Constraint: If the podcast does not contain actionable allocation guidance, return a single-row allocation with asset_class="Broad Market", target_pct=100, and confidence="Low", with notes explaining why.

    Call ask_gemini() with response_schema=PodcastStrategy.
    
    Return the .model_dump() of the parsed response.

Follow the exact patterns used in existing agents (thesis_screener.py, macro_monitor.py) for imports, error handling, and logging.
Add a module-level docstring explaining this agent's purpose.
```

---

## Prompt 5 of 6: Create the Orchestrator Script

```
Read the following files before writing any code:
- utils/agents/podcast_analyst.py (the agent you just created)
- utils/sheet_readers.py (for get_gspread_client)
- pipeline.py (for sanitize_dataframe_for_sheets, write_pipeline_log patterns)
- config.py (for DRY_RUN, PORTFOLIO_SHEET_ID, TAB_AI_SUGGESTED_ALLOCATION, tab constants)

Create a new file at tasks/weekly_podcast_sync.py with the following behavior:

1. Accept command-line arguments:
   - Required: YouTube video ID (positional arg)
   - Optional: --source-name "Forward Guidance EP 412" (defaults to "Unknown Podcast")
   - Optional: --dry-run flag (overrides config.DRY_RUN to True)

2. Transcript download:
   - Use youtube_transcript_api.YouTubeTranscriptApi.get_transcript(video_id)
   - Combine all segments into a single string: " ".join([seg["text"] for seg in transcript])
   - Print transcript length (word count) to console for context window awareness
   - If transcript exceeds 12,000 words, print a warning but proceed (Gemini 3 handles it)

3. AI analysis:
   - Call analyze_podcast(transcript, source_name) from utils.agents.podcast_analyst
   - Validate that target_pct values sum to 100 (±0.5 tolerance). If not, print ERROR and exit.
   - Pretty-print the full JSON strategy to console (always, regardless of DRY_RUN)

4. DRY_RUN gate:
   - If DRY_RUN (from flag or config.DRY_RUN): print "DRY RUN — no Sheet writes" and exit.
   - If NOT DRY_RUN, proceed to Sheet write.

5. Sheet write (only when DRY_RUN is False):
   a. Open the Portfolio Sheet via get_gspread_client() and config.PORTFOLIO_SHEET_ID
   b. Get the AI_Suggested_Allocation worksheet
   c. Archive step: Read current data rows (if any). Log them to the Logs tab with source="Podcast_Sync" and message="Archived previous AI suggestion before overwrite" and the previous source name in Details.
   d. Clear all data rows (preserve header row 1)
   e. Build rows from the strategy output:
      - Each SectorTarget becomes one row
      - Date = today's date (YYYY-MM-DD)
      - Source = source_name argument
      - Executive Summary = same value across all rows (from strategy.executive_summary)
      - Fingerprint = f"{date}|{source_name}|{asset_class}"
   f. Sanitize all values for Sheets (native Python types, no numpy)
   g. Write via ws.update("A2", rows) — batch write, not append_rows
   h. time.sleep(1.0) after write
   i. Log success to Logs tab via write_pipeline_log

6. Error handling:
   - Wrap the entire script in try/except
   - Print clear error messages for: missing youtube-transcript-api, invalid video ID, API errors, transcript not available
   - Never crash silently

7. Entry point:
   if __name__ == "__main__":
       import argparse
       # ... parse args and run

Include a module-level docstring with usage examples:
    # Usage:
    # DRY RUN (default):  python tasks/weekly_podcast_sync.py dQw4w9WgXcQ --source-name "Forward Guidance EP 412"
    # LIVE WRITE:         python tasks/weekly_podcast_sync.py dQw4w9WgXcQ --source-name "Forward Guidance EP 412" --no-dry-run
```

---

## Prompt 6 of 6: Update requirements.txt and CHANGELOG.md

```
1. Add 'youtube-transcript-api' to requirements.txt. Place it alphabetically. Do not remove or reorder existing entries.

2. Add a new entry to the TOP of CHANGELOG.md:

## [Unreleased] — Podcast Automation Pipeline

### Added
- `utils/agents/podcast_analyst.py` — Gemini-powered podcast transcript analysis agent with Pydantic schema enforcement
- `tasks/weekly_podcast_sync.py` — CLI orchestrator: YouTube transcript → Gemini analysis → AI_Suggested_Allocation tab
- `AI_Suggested_Allocation` tab in Portfolio Sheet — AI-generated allocation suggestions (separate from Bill's manual Target_Allocation)
- `youtube-transcript-api` dependency

### Changed
- `config.py` — Added TAB_AI_SUGGESTED_ALLOCATION, AI_SUGGESTED_ALLOCATION_COLUMNS, AI_SUGGESTED_ALLOCATION_COL_MAP
- `create_portfolio_sheet.py` — Added AI_Suggested_Allocation tab to SCHEMA
- `PORTFOLIO_SHEET_SCHEMA.md` — Documented AI_Suggested_Allocation tab schema

### Architecture Decision
AI suggestions write to a SEPARATE tab (AI_Suggested_Allocation), never to Target_Allocation. This preserves Bill's manual targets as the authoritative allocation. The Rebalancing page can display both for comparison. Bill manually promotes AI suggestions to Target_Allocation if accepted.

**Status:** DRY_RUN=True by default. Safe to deploy. No Sheet writes until explicitly toggled.
```

---

## Post-Build Verification Checklist

After running all 6 prompts, verify:

- [ ] `python -c "from utils.agents.podcast_analyst import analyze_podcast; print('Import OK')"` — no import errors
- [ ] `python tasks/weekly_podcast_sync.py --help` — shows usage, arguments
- [ ] `python tasks/weekly_podcast_sync.py <any_video_id> --source-name "Test"` — DRY_RUN prints JSON, no Sheet writes
- [ ] Target_Allocation tab is UNTOUCHED — still contains Bill's manual entries (or is empty if not yet populated)
- [ ] AI_Suggested_Allocation tab exists with correct headers
- [ ] `youtube-transcript-api` is in requirements.txt
- [ ] CHANGELOG.md has the new entry with Status line

## Gemini CLI Peer Review (G-Review)

After all prompts are executed and verified, run:

```bash
gemini --all-files -p "Review the new podcast automation pipeline (utils/agents/podcast_analyst.py, tasks/weekly_podcast_sync.py, and changes to config.py, create_portfolio_sheet.py, PORTFOLIO_SHEET_SCHEMA.md). Check for: 1) Consistency with existing agent patterns, 2) Proper use of ask_gemini and SAFETY_PREAMBLE, 3) Schema alignment with the new AI_Suggested_Allocation tab, 4) Safety gaps — can this pipeline ever write to Target_Allocation? 5) Error handling completeness."
```

---

## Future Enhancements (Not in this build)

- **AI_Suggested_Allocation_History tab** — append-only archive of all past AI suggestions with timestamps
- **Rebalancing page integration** — display AI suggestions alongside Target_Allocation with a "What changed" diff view
- **Scheduled execution** — GitHub Actions cron job to run weekly against a list of podcast video IDs
- **Multi-podcast consensus** — run multiple podcasts, weight by source quality, and merge into a consensus allocation
- **Ticker-level suggestions** — extend SectorTarget to include specific ticker recommendations within each asset class
