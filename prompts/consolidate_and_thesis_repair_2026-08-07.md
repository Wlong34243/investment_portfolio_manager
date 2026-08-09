# Repo Consolidation + Thesis Repair — 2026-08-07

**Role:** Claude Code / Gemini CLI, executing locally.
**Authoritative repo:** `C:\Dev\Investment_Portfolio`. **This is decided, not under review.**
**Tree to retire:** `C:\Users\WLong\Investment_Portfolio`, if present.

Bill runs everything out of `C:\Dev` from now on. The second tree goes. The only open
question is whether anything in it needs salvaging first — salvage, then retire, in this run.
Do not come back asking whether to consolidate.

Steps run in order — **Step 0 and Step 1 gate everything else.** If Step 0 finds a discrepancy
against what is asserted below, STOP and report rather than adapting silently.

Standing rules from `CLAUDE.md` apply throughout:
- Read-only on brokerage. Never write to the Google Sheet. Never write `Target_Allocation`.
- Archive-before-overwrite on every thesis write.
- **Do not invent thesis prose.** Where a judgment is missing, write `[BILL]` and stop.
- Dry run → verify → `--live`. Never skip the dry run.
- Extend existing docs (`CLAUDE.md`, `state.md`, `CHANGELOG.md`); do not create parallel ones.
- Deliver exactly what is asked. No unrequested scope.

---

## Step 0 — Verification gate

Confirm each of the following against actual file state. Report a PASS/FAIL table with
literal command output. **Do not accept your own summary as evidence.**

| # | Assertion to verify |
|---|---|
| 0.1 | `C:\Dev\Investment_Portfolio` exists and is a git repo (`git rev-parse --show-toplevel`). |
| 0.2 | Does `C:\Users\WLong\Investment_Portfolio` exist? If yes: is it a git repo, what is its HEAD, and is it the same remote (`Wlong34243/investment-portfolio-manager`)? |
| 0.3 | `vault/theses/PWR_thesis.md` exists in Dev, contains `STATUS: SCAFFOLD only (2026-08-07)`, and every prose section is `[BILL]`. |
| 0.4 | `vault/theses/VST_thesis.md` `next_step` already begins `[BILL — confirm]` and references bundle `6c531c97`. (Already repaired — confirm, do not redo.) |
| 0.5 | `grep -l "current_allocation: 0.00%" vault/theses/*_thesis.md` returns **zero** files. (Already repaired — confirm, do not redo.) |
| 0.6 | `GOOG_thesis.md` and `UNH_thesis.md` each contain a bare `priority:` line under `## Rotation Priority`. (Already repaired — confirm, do not redo.) |
| 0.7 | `vault/theses/VRT_thesis.md` `next_step` already begins `**[BILL] Position is now 68 shares / 3.14%` and the sleeve line reads `= 10.23% of book`. (Already repaired — confirm, do not redo.) |
| 0.8 | `vault/theses/KRE_thesis.md` still exists and KRE is absent from the latest bundle's positions. |
| 0.9 | `data/spotify_digests/` contains no `allocation-2026-08-07.txt` and `.ingested.json` has no entry for it. |
| 0.10 | `data/spotify_digests/.ingested.json` `output_path` values point at `C:\Users\WLong\Investment_Portfolio\...`. |
| 0.11 | `logs/morning_auto.log` mtime is 2026-07-27 while `exports/` contains three bundles dated 2026-08-07. |
| 0.12 | `ET_thesis.md` contains `Domestic AI/Data-Center Gas Demand (added 2026-08-07)` and `ES_thesis.md` contains `ISO-NE natural gas input costs`. (Already repaired — confirm, do not redo.) |
| 0.13 | A pre-edit `.bak` exists for VRT, ET and ES at `*_thesis.md.bak.2026-08-07T10-31-35.*`, and each still contains its OLD text (VRT: `Hold 30 shares` and `6.86% of book`; ET/ES: the new lines absent). Prior state is recoverable — confirm, do not re-create. |

If any of 0.4–0.7 or 0.12 come back FAIL (i.e. the work was NOT already done), stop and
report — the assumptions behind Steps 4 and 5 are wrong.

**Provenance note on 0.13.** The VRT/ET/ES edits were made directly by Bill at ~11:50 on
2026-08-07, not through the pipeline's archive-before-overwrite path. The `.bak` files that
cover them were produced incidentally by the 10:31 `write_thesis_updates` sync, which ran
before those edits. The outcome is correct — prior state is recoverable — but do not cite
this as evidence the convention was followed. If 0.13 fails, snapshot the three live files
to `*.bak.MANUAL_2026-08-07` before touching anything else, and say so.

---

## Step 1 — Salvage, then retire the second tree (BLOCKS EVERYTHING ELSE)

First because work done in the wrong tree is wasted, and because the Users tree may hold a
PWR thesis Bill remembers writing.

1. If `C:\Users\WLong\Investment_Portfolio` does not exist: record that, skip to 1.5, and treat
   the stale `.ingested.json` paths as a leftover from a move that already happened.
2. If it exists, inventory it — **read-only, before touching anything**:
   - `git log -1` for each tree; divergence both directions (`git log --oneline Dev..Users`, reverse).
   - Untracked/modified files in the Users tree that do not exist in Dev.
   - **Diff these directories** and list every file present in Users but not Dev:
     `vault/theses/`, `data/podcast_summaries/`, `data/spotify_digests/`, `agent_outputs/`,
     `prompts/`, `bundles/`, `logs/`.
   - **Search for a real PWR thesis:** `grep -ril "quanta\|ticker: PWR" <users-tree>` and list
     `vault/theses/PWR*`. This is the single most valuable thing Step 1 can find.
3. **Salvage.** Copy anything unique and non-derived into Dev. Rules:
   - A non-scaffold `PWR_thesis.md` lands at `vault/theses/PWR_thesis.md.FROM_USERS_TREE` —
     do **not** overwrite the Dev scaffold. Report the diff so Bill picks.
   - Any other thesis file that differs: copy as `<TICKER>_thesis.md.FROM_USERS_TREE`, never
     overwrite. Report a one-line diff summary per file.
   - Podcast summaries, digests and prompt files unique to Users: copy in directly.
   - **Do not** copy derived artifacts — `bundles/`, `exports/`, `__pycache__/`, `*.bak`,
     `data/fmp_cache/`, `data/etf_holdings_cache/`. They regenerate.
   - If nothing unique is found, say so explicitly and move on.
4. **Retire it in this run.** After salvage completes and Step 7's Dev-side verification
   passes: `git bundle create archive/users_tree_2026-08-07.bundle --all` from inside the Users
   tree (so its history is recoverable), then rename the directory to
   `Investment_Portfolio.RETIRED_2026-08-07`. Do not `rm -rf` — Bill deletes it himself once a
   clean morning run has come out of Dev. Report the bundle path and its size.
5. Fix the stale paths: rewrite `output_path` values in
   `data/spotify_digests/.ingested.json` to the `C:\Dev\Investment_Portfolio\...` root.
   Back the file up first. The three sha256 keys and `ingested_at` values must be preserved
   byte-for-byte — they are the dedup ledger and Guard 1.
6. Grep the Dev tree for any other hardcoded `C:\Users\WLong\Investment_Portfolio` or
   `~/Investment_Portfolio` path (`config.py`, `*.bat`, `scripts/`, Task Scheduler XML if
   present). Report each with its file and line. Fix only the ones that are configuration;
   flag anything that looks like it belongs to the RE Property Manager and leave it alone.
   **Every path in the Dev tree should point at Dev when this step finishes** — a retired tree
   that something still references is worse than two live trees.

---

## Step 2 — Why STEP 4b missed today's Spotify digest

`config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR` resolves to
`%LOCALAPPDATA%\Studio by Spotify Labs\.studio\artifacts\transcripts` (`config.py:576`).
Bill confirms `allocation-2026-08-07.txt` is present there. `tasks/ingest_spotify_digests.py`
globs `allocation-*.txt` from that directory. It did not ingest.

1. Run the dry run and capture literal stdout:
   `python tasks/ingest_spotify_digests.py --days 7`
2. Diagnose against the actual candidate filter. Check, in this order:
   - Does the glob resolve? Print the expanded `SPOTIFY_STUDIO_TRANSCRIPTS_DIR` and its listing.
   - `SPOTIFY_DIGEST_WINDOW_DAYS = 7` — is 2026-08-07 inside the window as computed?
   - `SPOTIFY_DIGEST_MIN_WORDS = 400` — word count of the file. (It is a long transcript, so
     this should pass; confirm rather than assume.)
   - `FILENAME_RE = ^allocation-(\d{4}-\d{2}-\d{2})\.txt$` — exact filename match, including
     no trailing whitespace or `.txt.txt`.
   - Guard 1 (seed ledger) and Guard 2 (`VERIFICATION: PENDING` collision guard) — is either
     falsely suppressing it? Note the 08-02 digest's footer was rewritten with a completed
     verification block, which may interact with Guard 2. Report if so; do not "fix" Guard 2
     without flagging the design implication — per `state.md` 2026-08-01 that string is
     load-bearing.
   - Whether the task was reading the Users tree's `.ingested.json` rather than Dev's.
3. Report the root cause. **Then, only after Bill confirms, run with `--live`.**
4. Once ingested, regenerate the verification sidecar bound to the real source hash. A
   provisional sidecar written from a chat paste is at
   `data/podcast_summaries/verification/allocation-2026-08-07_VERIFIED_2026-08-07.md` —
   it carries `source_sha256: UNAVAILABLE`. Replace that field and the header note; the
   findings in it are researched and cited, so **preserve the body**.

---

## Step 3 — PWR thesis: write Bill's prose to disk, fix the style key only

**Status change since this prompt was drafted.** Bill has supplied the thesis prose (a
Stephanie Link-sourced framework, same pattern as the IBM initiation recorded in `state.md`
2026-07-27). It is NOT yet on disk — `vault/theses/PWR_thesis.md` still reads `style: TBD`
with all `[BILL]` placeholders.

**Bill's text is saved verbatim at `prompts/inputs/PWR_thesis_BILL_2026-08-07.md`.** That file
is the input, not the output. Transcribe from it; the only permitted deviations are the two
frontmatter fields in item 2 below and the additions in items 5 and 6.

**Your job is transcription plus one mechanical fix. Do not edit, condense, rewrite or
"improve" any thesis prose.** Core Thesis, Bull Case, Key Risks, Exit Conditions, `next_step`
and `priority` are Bill's judgment and are transcribed verbatim.

1. Archive-before-overwrite, then write Bill's text to `vault/theses/PWR_thesis.md`.
   Preserve the existing `<!-- region:* -->` blocks — `position_state`,
   `transaction_log`, `realized_gl` and `change_log` are sync-managed and must not be
   hand-edited.

2. **`style:` — Bill has decided: `THEME`. Ceiling 3.0%.** Set it; do not re-open the question.
   Bill's draft had `style: Infrastructure / Quality Growth`, which is not a key in
   `data/styles.json` (only `GARP` 9.0, `THEME` 3.0, `FUND` 5.0, `ETF` 8.0), so PWR was
   excluded from the Style Size Ceiling Check in `export_ai_briefing.py` — the precise gap the
   file was created to close.

   Make both edits so the frontmatter is internally consistent:
   - `style: THEME`
   - `triggers.style_size_ceiling_pct: 3.0`

   Consequences to report, not to act on:
   - PWR at **1.47%** against a 3.0% ceiling has **1.53% of headroom** — no breach. It becomes
     the **ninth** THEME name and takes the sleeve from 18.27% to **19.74%** of book. Three of
     the other eight are already in breach (VST 3.55, VRT 3.14, MELI 3.04).
   - The `<!-- region:sizing -->` block currently renders `Style: None` / `Size Ceiling: 0.00%`.
     That block is sync-managed — do NOT hand-edit it. Confirm the next sync run rewrites it to
     `THEME` / `3.00%`, and if it does not, that is a `core/thesis_sync_data.py` finding to
     report rather than patch around.
   - Per-ticker overrides are an established pattern (XOM 5.0 and ETN 3.0 are both THEME with
     explicit values; GOOG documents a 9.0 hard cap against a 6% working soft cap). If Bill
     later wants PWR on something other than the 3.0% default, that is a one-line frontmatter
     change, not a `styles.json` change.

   **One documentation consistency task.** `styles.json` defines THEME as "Thematic
   Specialists — buying market position over company quality," while Bill's `## Style` section
   reads "Quality Growth / Infrastructure" and his Bull Case argues company quality explicitly
   ("Strong Earnings & Operational Execution," "high-quality industrial"). Both are Bill's and
   both stay. Add one sentence under `## Style`, in his voice or marked `[BILL]`, recording
   *why* THEME was chosen — so the next reader does not re-open a decision that is already
   made. Do not alter the Bull Case.

   **Do not modify `data/styles.json` in this run.**

3. **Flag, do not change, these three mechanical details:**
   - `framework_preference: AI Power Infrastructure & Electrification` is free text. Other
     files use keys that resolve against `vault/frameworks/` (e.g. `lynch_garp_v1`,
     `joys_of_compounding`). Confirm whether anything consumes this field; if it does, the
     value will not resolve.
   - `priority: Medium-High` — no other thesis uses that value. Free-text priorities do exist
     and parse via the fallback, so this is cosmetic, but note it against the two preflight
     warnings already logged for GOOG and UNH.
   - `entry_price`, `price_add_below` and `price_trim_above` are all empty, so PWR will keep
     appearing in `level_coverage.no_trim_level` and `no_add_level`. That is Bill's choice to
     make; just confirm it is deliberate rather than an oversight, since the file otherwise
     reads as finished.

4. **One calibration note to surface to Bill — his number checks out, and its implication is
   worth stating.** The Key Risks section names tech capex "dropping toward $500B annually"
   as the impairment trigger. Big Four 2026 planned capex is roughly **$630B** (some counts
   $690–725B), against **$388B actual in 2025**. So $500B is a genuine threshold — roughly
   20–30% below plan — but it still sits **~29% above 2025 actual**, meaning the trigger fires
   on a sharp deceleration in growth rather than on an absolute decline. Sources:
   [Data Center Richness](https://datacenterrichness.substack.com/p/hyperscalers-plan-630-billion-in),
   [CNBC](https://www.cnbc.com/2026/02/06/google-microsoft-meta-amazon-ai-cash.html),
   [Futurum](https://futurumgroup.com/insights/ai-capex-2026-the-690b-infrastructure-sprint/).
   Record this in the Review Log as a calibration note. **Do not change the threshold.**

5. **Add source provenance.** The thesis is Stephanie Link-sourced but carries no date or
   program for where the framework came from. The IBM precedent in `state.md` has the same
   gap. Add a one-line `**Source:**` note under the STATUS banner with whatever attribution
   Bill supplies; if he supplies none, write `[BILL] — source date/program not recorded`.

6. **Add the look-through line**, since `VRT_thesis.md` does sleeve math and PWR is now in
   that sleeve: PWR is a top-10 IFRA holding (0.07% indirect per bundle `6c531c97`), so total
   PWR exposure floor is **1.54%** against a 1.47% direct position, and IFRA itself is held at
   1.90%. Facts only — no sizing recommendation.

## Step 4 — `VRT_thesis.md` — VERIFY ONLY, already repaired

Bill made this edit himself at ~11:50 on 2026-08-07. **Do not rewrite it.** Confirm the
following and report PASS/FAIL with the literal lines pasted:

- `next_step` reads `**[BILL] Position is now 68 shares / 3.14% — in breach of the 3.00%
  ceiling**`, references bundle `6c531c97`, names the stale figures it replaces, and infers no
  new scaling state.
- The sleeve line reads `VST 3.55%, IFRA 1.90%, ETN 1.64%, VRT 3.14% = 10.23% of book` and is
  marked as corrected against bundle `6c531c97`.
- The ETN rotation-destination logic survives, with ETN headroom updated to `~1.36%`.

**One thing the repair opened that is not yet closed.** The corrected file now carries a
`[BILL — VST's own headroom figure ... needs re-check]` note: VST at 3.55% is over its own
3.00% ceiling, which may disqualify it as a rotation destination. That is a live open question
in the file. Leave it as `[BILL]`; do not resolve it. Report that it exists so it is not lost.

**Not in this file, worth one line in your report:** PWR joins this sleeve as of Step 3
(THEME, 1.47%). The sleeve paragraph does not mention it. Whether to add PWR to that sentence
is Bill's call — flag it, do not edit it in.

---

## Step 5 — Small outstanding items

1. **`vault/theses/KRE_thesis.md`** — preflight: thesis exists but position not held. Its
   `last_reviewed` is being touched by the sync (2026-08-03), so it is not inert. **Do not
   guess.** Report the file's current `next_step`, any realized G/L history in it, and the
   date of the last KRE transaction in the log region. Propose archive-vs-record-the-exit and
   let Bill choose. If Step 1 finds a KRE position in the Users tree, say so.
2. **`vault/theses/ET_thesis.md` — VERIFY ONLY, already repaired.** Bill added the domestic
   AI/data-center gas demand line himself at ~11:50 on 2026-08-07. Confirm it cites the
   2026-07-26 ILTB episode, and confirm it deliberately **excludes** the episode's own volume
   figures with a pointer to
   `data/podcast_summaries/verification/allocation-2026-08-07_VERIFIED_2026-08-07.md`.
   That exclusion is the point — the 12–15 Bcf/d upside case runs 2–2.5x published forecasts
   (East Daley 4.2–6.1; S&P Global base 3, upside ~6). **Do not add the figure back.**
3. **`vault/theses/ES_thesis.md` — VERIFY ONLY, already repaired.** Bill added the ISO-NE
   natural gas input-cost line to Key Risks at ~11:50 on 2026-08-07. Confirm `next_step` is
   still `[CONFIRM] hold the seed` and was NOT resolved as a side effect.
4. **NVDA forward P/E discrepancy.** Command Center reports **17.2**; GuruFocus reports
   **24.46** for the same date. Trace which field `tasks/enrich_*.py` / `utils/fmp_client.py`
   is populating and on what basis (next-FY vs NTM vs current-FY). Report the finding; change
   nothing without Bill's sign-off — this feeds the ADD/TRIM signal logic.

---

## Step 6 — Pipeline and scheduler

1. **`logs/morning_auto.log` last written 2026-07-27 11:12 with a FAIL**, yet three bundles
   were exported 2026-08-07 and no `logs/HEALTH_FAILURE.flag` exists. Determine whether
   `morning_auto.bat` is still the execution path or whether its output redirect is broken.
   **Report findings. Do not modify the Task Scheduler entry** — Bill will, once he knows
   which tree it points at (Step 1).
2. **Schwab token.** Command Center reported `AUTH REQUIRED` at 2026-08-07 09:40 while
   `tasks/health.py` raised no flag. `state.md:167` already records that these two checks are
   unreconciled — this is a **second observation of a known issue**, so append to that entry
   rather than creating a new one. Bill runs `python manager.py login` himself; your job is to
   confirm both signals agree afterward.
3. **Stale AGENT SIGNALS.** The Command Center `Signal` column is populated from agent run
   `cbc10a99` dated **2026-04-20** — 109 days stale — and reads as current. It still lists AMD,
   SNPS, PPA, IREN, CRWV, IGV, which are not held. Propose (do not implement) either a
   staleness stamp rendered next to the column or suppression past N days. This is a display
   decision; put the options to Bill.

---

## Step 7 — Verification checklist

The build is not done until every line passes with **literal stdout/stderr pasted**. An
agent-reported PASS table is not acceptable.

- [ ] Step 0 table reported, with 0.4/0.5/0.6 confirmed already-done and not redone.
- [ ] Users tree inventoried, salvage complete, `git bundle` created, directory renamed to
      `Investment_Portfolio.RETIRED_2026-08-07`. Paste the bundle path and `ls` of the rename.
- [ ] Users-tree PWR search run; result reported either way.
- [ ] No remaining `C:\Users\WLong\Investment_Portfolio` reference anywhere in the Dev tree.
      Paste the grep proving it.
- [ ] `.ingested.json` paths repointed to `C:\Dev`; three sha256 keys and `ingested_at`
      values byte-identical to the backup (`diff` the JSON keys and prove it).
- [ ] Root cause of the STEP 4b miss identified and stated in one sentence.
- [ ] `python tasks/ingest_spotify_digests.py --days 7` dry-run output pasted.
- [ ] `PWR_thesis.md` contains Bill's prose transcribed verbatim — diff his supplied text
      against the written file and prove they match. No prose was edited or "improved".
- [ ] `PWR_thesis.md` `style:` resolves to a real `data/styles.json` key and
      `triggers.style_size_ceiling_pct` matches it. PWR appears in the Style Size Ceiling
      Check of a fresh export — paste that table row.
- [ ] `data/styles.json` was NOT modified this run.
- [ ] `VRT_thesis.md` verified, not rewritten. The `[BILL — VST headroom]` open question is
      reported and left unresolved. Paste the `next_step` and sleeve lines.
- [ ] `ET_thesis.md` and `ES_thesis.md` verified, not rewritten. ET still excludes the
      12–15 Bcf/d figure; ES `next_step` is still `[CONFIRM] hold the seed`. Paste both.
- [ ] `.bak` exists for every thesis whose content changed today — including VRT, ET and ES,
      whose coverage comes from the 10:31 sync snapshot rather than from the edit itself
      (see Step 0 provenance note). List each `.bak` with its timestamp and prove by `grep`
      that it holds the pre-edit text, not a copy of the current file. **A `.bak` that matches
      the live file is not a backup — it is the failure this checklist exists to catch.**
- [ ] `PWR_thesis.md` has a `.bak` created by this run before it was overwritten.
- [ ] `python manager.py morning` **dry run** completes; paste the summary panel.
- [ ] `python tasks/lint_theses.py` run; paste output. New findings triaged, not auto-fixed.
- [ ] Nothing was written to the Google Sheet. State this explicitly.
- [ ] `state.md` Recent Decisions Log and `CHANGELOG.md` updated with a dated entry for this
      pass. Do not create a new markdown file at repo root.

---

## Out of scope — do not do these

- Do not `rm -rf` the Users tree. Bundle and rename only — Bill deletes it himself.
- Do not overwrite any Dev thesis file with a Users-tree version. Copy alongside, report, let
  Bill pick.
- Do not write, edit, condense or "improve" investment thesis prose for PWR or any other
  ticker. PWR's prose is Bill's and is transcribed verbatim.
- Do not pick PWR's style bucket, and do not add a fifth bucket to `data/styles.json`.
- Do not resolve any `[BILL]` or `[CONFIRM]` placeholder.
- Do not touch the 08-02 digest's `VERIFICATION` footer line.
- Do not modify Task Scheduler.
- Do not add a new vendor before extending `utils/fmp_client.py`.
- Do not fold the ~19 loose root markdown files into `CHANGELOG.md` this pass — it is a known
  doc gap but it is not what was asked.
