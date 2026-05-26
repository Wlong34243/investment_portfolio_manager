# Idea Generator v1 — Verification Results

**Run date:** 2026-05-26  
**Bundle used:** `composite_bundle_2026-04-27T154809Z_a536e9fcae22.json` (auto-detected latest)

---

## Step 0: Gate Check

| Gate | Result | Notes |
|------|--------|-------|
| `core/composite_bundle.py` has `build_composite_bundle()` | PASS | Present and working |
| `utils/gemini_client.py` has `ask_gemini_composite()` | PASS | Pydantic schema enforcement confirmed |
| `vault/transcripts/` exists and has transcripts | **FAIL** | Directory exists but is empty — no transcripts ingested yet |
| `data/styles.json` parseable with 4 style definitions | PASS | Keys: GARP, THEME, FUND, ETF |
| Most recent composite bundle is loadable | PASS | April 27 composite verified; hash recomputed correctly |

**Decision:** Proceeding despite Gate 3 failure. The code handles the empty-transcript case gracefully (returns empty candidates + informative note). The infrastructure is the v1 deliverable.

---

## Verification Checklist

- [x] Command ran without errors
- [x] Output file written to `agent_outputs/ideas/`
- [x] Bundle hash in output matches the bundle hash on disk (`a536e9fc...`)
- [ ] Candidate count is reasonable (more than 0, fewer than 50) — **N/A: no transcripts**
- [ ] At least one candidate has a style classification other than "Unclear" — **N/A: no transcripts**
- [ ] At least one candidate has portfolio relationship beyond "new exposure" — **N/A: no transcripts**
- [ ] No candidate contains a price target or explicit buy/sell language — **N/A: no transcripts**
- [x] Markdown is readable when opened in a viewer — report structure confirmed
- [ ] First 2-3 candidates pasted below — **N/A: no transcripts**

---

## First-Run Output (Empty Case)

Since `vault/transcripts/` is empty, the agent correctly short-circuits before calling Gemini
and returns a structured empty response with an actionable note:

```
Report written: agent_outputs\ideas\ideas_2026-05-26_a536e9fc.md
0 candidate(s) across 0 transcript(s) in 1.0s
Notes: No new transcripts found within the last 7 days in vault/transcripts/.
       Run 'pm ingest podcasts' to fetch new transcripts, then re-run this command.
```

The generated markdown at `agent_outputs/ideas/ideas_2026-05-26_a536e9fc.md`:
- Has the correct report header with timestamp
- Contains the full composite bundle hash
- Shows "No actionable candidates found" placeholder
- Surfaces the note pointing to `pm ingest podcasts`

---

## Performance Notes

- **Run time (empty case):** ~1 second (no LLM call — short-circuits on empty transcripts)
- **Token usage:** 0 (no Gemini call made)
- **LLM path verified:** Not yet — requires at least one transcript to exercise the full pipeline

---

## Path to First Real Run

1. Run `pm ingest podcasts` (or `python manager.py ingest podcasts`) to populate `vault/transcripts/`
2. Run `python manager.py agent ideas` — will now call Gemini with the transcript content
3. Or test manually: drop any `.txt` file into `vault/transcripts/` and run `python manager.py agent ideas --since-days 30`

To test with older transcripts already on disk (if any exist), use:
```
python manager.py agent ideas --since-days 365
```

---

## Likely v2 Refinements

Based on the implementation and what the output structure will look like once transcripts are available:

**If too many candidates (>20):**
- Add a minimum quality filter: require `style_fit != "Unclear"` to appear in the report
- Add recency bias: weight transcripts from the last 3 days more heavily in the prompt

**If too few candidates (<3 across multiple transcripts):**
- Broaden "actionable" definition in `prompts/idea_generator.md` — current spec is fairly strict
- Add explicit note to the prompt that multi-episode mentions of the same ticker count once per transcript

**If style classification is unreliable (mostly "Unclear"):**
- Add few-shot examples to `prompts/idea_generator.md` showing a concrete GARP, Thematic, BoringFundamentals, and SectorETF classification
- The style definitions section in the prompt has examples from the portfolio — may need richer descriptions

**If overlap detection is weak (portfolio_relationship always "new exposure"):**
- Expand the composite bundle context window: currently all theses are included (`include_vault_context=True`), but the positions list may be truncating
- Consider adding a holdings summary block explicitly to the user prompt (top 10 positions by weight)

**If transcripts repeat the same names across episodes:**
- Deduplicate candidates by ticker before writing — keep the highest-confidence occurrence
- Add a `mention_count: int` field to `Candidate` to surface repeat signals

**If the report is hard to read at volume:**
- Add a summary table at the top: ticker | style_fit | relationship category
- Consider a `--top-n` flag to limit to N candidates

**Candidate for next agent:** drift-monitor — watches for thesis language mismatch between current thesis files and recent market/fundamental changes. Will use the same composite bundle path.
