# AI Dispatch — acceptance test before the first unattended morning run

**Created:** 2026-08-31
**Executor:** Bill, in an external PowerShell window (not Cursor's integrated terminal).
**Type:** one-time acceptance gate. **Not** a recurring task.
**Applies to:** `tasks/ingest_ai_dispatch.py`, morning STEP 4d, `pm podcast ingest-ai-dispatch`.

> **STEP 4d is already wired into the morning routine.** It sits inside
> `@app.command("morning")` (`manager.py` ~2649), and `morning_auto.bat` runs
> `python manager.py morning --live` at ~07:45 via Task Scheduler. Nothing needs to be
> scheduled. This file exists to answer one question before that unattended run happens:
> *does STEP 4d work, and does it fail safely if it doesn't?*

---

## Run these, in order, in an external PowerShell

```powershell
cd C:\Dev\Investment_Portfolio

# 1. Dry run — analyses the dispatch, prints the brief, writes NOTHING
python manager.py podcast ingest-ai-dispatch

# 2. Live — writes the brief, corpus copy, and ledger entry
python manager.py podcast ingest-ai-dispatch --live

# 3. Regression — nothing else broke
python -m pytest tests/ -q
```

---

## What each step must show

**Step 1 — dry run.** Must print `Analyzing ai-dispatch-2026-08-31.txt (2376 words) as
'AI Dispatch: 2026-08-31'...` then a brief whose `headline` reflects the actual content
(double-blind evals / recursive memory / the Cursor split) — not a generic AI summary.
Then `--- DRY RUN --- would write data/ai_briefs/...`.

**Confirm nothing was written:**

```powershell
dir data\ai_briefs          # must not exist, or be empty
dir data\ai_dispatches      # must not exist
```

**If the brief names a ticker as an implication, STOP.** `validate_brief()` should have
rejected it. That is a real defect, not a tuning issue — report the literal output.

**Step 2 — live.** Must print `SUCCESS: wrote data/ai_briefs/2026-08-31_AI_Dispatch_<slug>.md`.
Then:

```powershell
dir data\ai_briefs                                    # .md + .json pair
type data\ai_dispatches\.ingested.json                # one sha256 entry
findstr /C:"AI_BRIEF_VERIFICATION: PENDING" data\ai_briefs\*.md
findstr /C:"PROVENANCE" data\ai_briefs\*.md
```

Both `findstr` calls must hit. The brief's `**Source file:**` line must name
`ai-dispatch-2026-08-31.txt`, **not** a youtube.com URL — that is the `source_ref`
parameter doing its job.

**Step 3 — pytest.** Baseline. If something fails, check whether it failed before today's
changes (`git stash` is not needed — the `.bak.2026-08-31T*` copies are on disk).

---

## The idempotency check — the one that matters for tomorrow

Run step 2 **again**:

```powershell
python manager.py podcast ingest-ai-dispatch --live
```

Must report `Skipped (already done): ['ai-dispatch-2026-08-31.txt']`, make **zero** Gemini
calls, and leave `data/ai_briefs/` unchanged. This is what stops the 07:45 run from
re-analysing and re-billing the same dispatch every morning for the rest of the week.

**If it re-analyses, do not let the unattended run happen** — the sha256 ledger is not
working and every morning will pay for the same file.

---

## Then confirm the morning path itself

```powershell
python manager.py morning
```

Dry run. The step table must include a **`AI Dispatch (0 new)`** row with status `pass`
(0 because step 2 already ingested today's file). A `warn` row is acceptable only if the
Studio folder is genuinely absent; anything else, read the printed error.

**This is the real acceptance criterion.** `pm podcast ingest-ai-dispatch` working in
isolation does not prove STEP 4d works inside `morning`.

---

## Downstream, once a brief exists

```powershell
python manager.py corpus index --live      # ai_brief + ai_dispatch counts rise
python manager.py ai index --live          # no longer REFUSES — brief_count >= 1
```

`pm ai index --live` refusing with `REFUSED: 0 briefs found` before this point is correct
behaviour, not a bug. After step 2 it should write, with `ingestion_state: "ok"`, and the
cockpit AI panel should leave the `no_briefs` state for the first time.

---

## What to do if step 1 fails

| Symptom | Meaning |
|---|---|
| `Studio directory not found` | `config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR` does not resolve on this machine. The folder is hidden — `.studio` needs *Show hidden items* — but Python does not care about Explorer's view setting, so this means the path or `SPOTIFY_STUDIO_DIR` env var is wrong |
| `No ai-dispatch-*.txt in ...` | Filename does not match. The pattern is exactly `ai-dispatch-YYYY-MM-DD.txt`, optionally one lowercase letter suffix (`...-31b.txt`) |
| `SKIP (unparseable name, NOT ingested)` | Named like a dispatch but the date does not parse. Deliberate: reported and counted as failed rather than dropped silently — the bug that swallowed `allocation-2026-08-07b.txt` |
| `SKIP (too short, N words)` | Below the 300-word floor. Today's file is 2,376 words, so this means a truncated write |
| `REJECTED — validator violations` | The analyst produced a ticker implication or allocation language. Not written, not deduped, retryable. Report the violation lines verbatim |

---

## Not built, and deliberately

- **No new scheduled task.** STEP 4d already runs inside the 07:45 job. A second scheduler
  entry would double-run it; the ledger makes that a no-op rather than a duplicate, but it
  is still two Gemini calls' worth of process startup for nothing.
- **No daily pytest.** A test suite belongs in a pre-commit or a manual gate, not in an
  unattended pre-market job where a failure has nowhere useful to go.
- **No recurring health check yet.** If you want one, the right shape is a read-only check
  that reports *whether today's dispatch was ingested* by reading
  `data/ai_dispatches/.ingested.json` — not a command that re-runs ingestion to find out.
  Separate, small, and not written until asked.
