# Prompt: Move the Repo Out of Google Drive, Publish Analysis Files Into It

**Created:** 2026-08-03
**Target executor:** Claude Code, run locally on Bill's Windows machine
**Scope:** filesystem migration + one path fix + one new publish step
**Risk level:** HIGH — this moves a live repo containing an unbacked-up 129 MB `.git`

---

## The problem, and the actual goal

`C:\Users\WLong\Investment_Portfolio` is inside **Google Drive File Stream**. Verified
2026-08-03: 106 `desktop.ini` files carrying
`IconResource=C:\Program Files\Google\Drive File Stream\128.0.0.0\GoogleDriveFS.exe`,
including three inside `.git`.

Drive File Stream keeps file content as **online-only placeholders**. Explorer shows the
correct name and byte size while the bytes are not on disk. That is why briefing exports in
`exports\ai_briefing_2026-08-03_093602\` appear blank when opened — they are dehydrated, not
empty. Corroborating evidence: in the 2026-08-01 export folders every `.md` is stamped
08-01 while `desktop.ini` is stamped 08-02 10:59, i.e. Drive re-walked the folder a day
after the pipeline wrote it.

**Bill's actual intent was never to sync the repo.** He wanted the *analysis outputs*
readable on his other devices. Syncing the whole working directory was the means, and it is
the wrong means: it put a live git repo, a 40 MB `bundles/` directory, and a pipeline that
writes hundreds of `.bak` files per run inside a sync client.

**Target state:** repo fully local, and a small publish step that pushes only the analysis
markdown into Drive.

---

## Step 0 — Verification gate

Run all of these and paste literal output. If any item differs from the expectation, STOP
and report rather than adapting.

1. `git -C C:\Users\WLong\Investment_Portfolio remote -v`
   → expect `origin  https://github.com/Wlong34243/investment_portfolio_manager.git`
2. `git log -1 --format="%h %ad %s" --date=short`
   → expect `ecaffb1 2026-07-31 feat: briefing integrity hardening ...`
3. `git status --porcelain | Measure-Object -Line`
   → expect ~266 changed paths. **Record the exact number.**
4. `git ls-files | Select-String desktop.ini | Measure-Object -Line`
   → expect **0**. `desktop.ini` is already in `.gitignore` at line 91, so git is clean of
   the Drive artifacts. If this is not 0, STOP.
5. `Select-String -Path *.bat,**\*.py -Pattern "C:\\Users\\WLong\\Investment_Portfolio"`
   → expect exactly one hit: `make_ai_briefing.bat:2`. `morning_auto.bat` uses
   `cd /d "%~dp0"` and is path-independent. If other hits appear, list them.
6. Confirm `scripts/backup_to_drive.py` exists and read it. **If it already implements a
   Drive copy path, extend it in Phase 4 rather than writing a new module** — repo
   convention is extend, don't proliferate.
7. Identify the Drive root letter (typically `G:\My Drive`). Record it.

---

## Phase 1 — Safety. Nothing is moved in this phase.

Blast-radius order: verify, back up, then act.

### 1a. Check for existing corruption

```
git -C C:\Users\WLong\Investment_Portfolio fsck --full
```

A repo that has lived in a sync client for months may already be damaged. **If fsck reports
anything beyond dangling objects, STOP and report before touching anything.** Dangling blobs
and commits are normal; missing or corrupt objects are not.

### 1b. HYDRATE EVERYTHING — the single most important step

**This is where data loss happens.** Copying a dehydrated placeholder yields a zero-byte
file. Before any copy:

- Google Drive for desktop → right-click `Investment_Portfolio` → **Offline access →
  Available offline**
- Wait for the Drive tray icon to report sync complete. This will take a while; the folder
  is roughly 200 MB across `.git` (129 MB), `bundles/` (40 MB), `data/` (14 MB),
  `exports/` (8.4 MB), `vault/` (3.6 MB).
- Verify hydration is real, not assumed:

```powershell
Get-ChildItem -Recurse -File C:\Users\WLong\Investment_Portfolio |
  Where-Object { $_.Attributes -match 'Offline' -or $_.Attributes -match 'RecallOnDataAccess' } |
  Measure-Object
```

**Expected: 0.** If any file still carries `Offline` or `RecallOnDataAccess`, hydration is
incomplete. Do not proceed.

### 1c. Get an off-machine copy

There are ~266 uncommitted paths and the last commit is 2026-07-31. Most of that is
generated churn (`.bak` thesis files, new bundles, new exports) which is gitignored or
disposable, but confirm before assuming.

```
git status --porcelain > C:\temp\pre_move_status.txt
git add -A && git commit -m "chore: checkpoint before Drive extraction 2026-08-03"
git push origin main
```

If the push fails, STOP. An off-machine copy is a precondition for the move, not a nicety.

---

## Phase 2 — Move

Destination: `C:\dev\Investment_Portfolio` (outside every sync client — not Drive, not
OneDrive, not Dropbox).

**Copy, do not move.** The Drive copy stays until the local one is verified working.

```powershell
robocopy "C:\Users\WLong\Investment_Portfolio" "C:\dev\Investment_Portfolio" /E /COPY:DAT /R:2 /W:2 /XF desktop.ini /LOG:C:\temp\robocopy.log
```

`/XF desktop.ini` drops all 106 Drive artifacts in transit.

### Verify the copy before trusting it

- File count matches, excluding `desktop.ini`:

```powershell
(Get-ChildItem -Recurse -File "C:\Users\WLong\Investment_Portfolio" -Exclude desktop.ini).Count
(Get-ChildItem -Recurse -File "C:\dev\Investment_Portfolio").Count
```

- **Zero-byte check — this catches a failed hydration after the fact:**

```powershell
Get-ChildItem -Recurse -File C:\dev\Investment_Portfolio | Where-Object Length -eq 0 | Select FullName
```

Compare against the same query on the source. Any file that is 0 bytes at the destination
but non-zero at the source means hydration failed. STOP.

- Git integrity at the destination:

```
git -C C:\dev\Investment_Portfolio fsck --full
git -C C:\dev\Investment_Portfolio status
git -C C:\dev\Investment_Portfolio log -1
```

`status` must show the same state as the source, and `log -1` the same commit hash.

---

## Phase 3 — Repoint everything

### 3a. Code

`make_ai_briefing.bat` line 2 — the only hardcoded path in the repo:

```
cd /d C:\Users\WLong\Investment_Portfolio    →    cd /d "%~dp0"
```

Use `%~dp0` rather than the new literal path so this never breaks again. Confirm no other
`.bat` or `.py` hardcodes the old path.

### 3b. Windows Task Scheduler

`morning_auto.bat` runs ~7:45 AM. Update the task's **Start in** field to
`C:\dev\Investment_Portfolio` and the action path to the new `morning_auto.bat`. The script
body needs no change — it already uses `%~dp0`.

### 3c. Claude scheduled tasks

Two tasks reference the old path inside their prompts:

- `portfolio-morning-brief` (weekdays 8:20 AM) — references
  `C:\Users\WLong\Investment_Portfolio` in several places including STEP 2c
  (`data\watchlist.json`) and STEP 4 (`exports\ai_briefing_*\manifest.json`,
  `agent_outputs\ai_briefing_analysis\`)
- `daily-news-brief` (7:00 AM) — check whether it references the path

Their `SKILL.md` files live under
`C:\OneDrive-Personal\OneDrive\Documents\Claude\Scheduled\<task>\SKILL.md`.
Update every occurrence of the old path.

> **Note, out of scope:** those SKILL.md files are themselves inside **OneDrive** — a second
> sync client. Same dehydration failure mode applies. Flag it for Bill; do not act on it in
> this build.

### 3d. Cowork / Claude folder access

Bill will need to re-point his connected folder from
`C:\Users\WLong\Investment_Portfolio` to `C:\dev\Investment_Portfolio`. Manual step, note it
in the handoff.

---

## Phase 4 — Publish analysis files to Drive (the original goal)

Now give Bill what he actually wanted, without the repo in the sync path.

**Publish set — small and stable:**

```
agent_outputs/ai_briefing_analysis/*.md    192 KB
agent_outputs/ideas/*.md                   188 KB
agent_outputs/dislocation_scan/*.md         16 KB
```

~400 KB total. Everything else stays local: `bundles/` (40 MB), `exports/` (8.4 MB, and
`SUBMIT_ME.md` is a 279 KB paste artifact with no value on a phone), `.git`, `data/`,
`vault/`.

**Destination:** a Drive folder that contains *only* published output, e.g.
`G:\My Drive\Portfolio_Analysis\`. Never point this at the repo.

**Implementation:**

- First read `scripts/backup_to_drive.py`. If it already has a working Drive path, extend
  it with a `publish_analysis()` function rather than creating a new module.
- One-way copy, newest-wins, never delete at the destination. Bill may open these on a
  phone; a destructive sync could remove a file he is reading.
- Skip a file whose destination copy has an identical SHA-256.
- Add as **STEP 12** at the end of `manager.py morning`, after the dislocation scan.
- Follow the STEP 4 contract: wrapped in `try/except Exception`, appends to `step_results`,
  and **non-fatal** — a missing Drive letter on some future machine must degrade to `warn`,
  never abort the pipeline.
- Standalone command for testing: `pm publish analysis [--live]`.
- Dry-run by default, per hard rule 3.

---

## Phase 5 — Decommission the Drive copy

**Only after Phase 2 verification passed, Phase 3 is done, and one full `manager.py morning
--live` has run clean from `C:\dev\`.**

1. Run the morning pipeline from the new location. Confirm a fresh bundle and export appear
   under `C:\dev\Investment_Portfolio\`.
2. Open three export `.md` files from the new location and confirm they render with content.
3. Leave the Drive copy untouched for **one week** as a fallback.
4. After that week, remove it — and remove it via the Drive web interface or by turning off
   sync for that folder, **not** by deleting the local mirror while sync is active, which
   would propagate the deletion to Drive.

---

## Non-goals

- Do not rewrite git history or run `git gc --aggressive` during the migration.
- Do not delete `bundles/` or `exports/` to save space. Separate decision.
- Do not change the archive-before-overwrite `.bak` behavior, even though it is the main
  churn source. Separate decision.
- Do not move the Claude `Scheduled\` folder out of OneDrive. Flag only.
- Do not add `exports/SUBMIT_ME.md` to the publish set.

---

## Post-build verification checklist

Literal output required for each. Do not accept a reported PASS.

- [ ] `git fsck --full` clean at both source and destination.
- [ ] Zero-byte file count at destination equals zero-byte count at source.
- [ ] File counts match excluding `desktop.ini`; `desktop.ini` count at destination is 0.
- [ ] `git log -1` returns the same commit hash at both locations.
- [ ] `git push origin main` succeeded before the move; GitHub shows the checkpoint commit.
- [ ] `Select-String -Path C:\dev\Investment_Portfolio\*.bat -Pattern "C:\\Users\\WLong"`
      returns nothing.
- [ ] `manager.py morning` (dry) completes from `C:\dev\` through all steps.
- [ ] `manager.py morning --live` produces a fresh bundle and export under `C:\dev\`, and
      three sampled export `.md` files open with visible content.
- [ ] `pm publish analysis` (dry) lists ~7 analysis files and writes nothing.
- [ ] `pm publish analysis --live` populates `G:\My Drive\Portfolio_Analysis\`; the files
      open with content on a second device.
- [ ] Re-running publish copies nothing (hash dedup works).
- [ ] Renaming the Drive destination and running `morning` yields `warn`, and the pipeline
      still completes.
- [ ] Windows Task Scheduler shows the updated Start in path; a manual "Run" succeeds and
      appends to `C:\dev\Investment_Portfolio\logs\morning_auto.log`.

---

## Known blocker, unrelated to this migration

`logs\morning_auto.log` last wrote **2026-07-27 11:12** and ended in a critical health
failure: `schwab_token_market FAIL — Market token missing from GCS`,
`schwab_token_accounts FAIL`, `schwab_api_positions FAIL — Schwab client returned None`.
Health gates at STEP 0, so the unattended pipeline has not completed in seven days.

Fix that first or the Phase 5 live-run verification cannot pass:
`python manager.py login`, or `schwab_emergency_reauth.bat`. Tokens are *missing from GCS*
rather than expired, so also confirm the Cloud Function keep-alive is still deployed and
running on its 25-minute cadence.
