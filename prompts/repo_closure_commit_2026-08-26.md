# Prompt: Repo Closure — Commit the 2026-08-26 Hygiene Pass and the Uncommitted Shipped Work

**Repo:** `C:\Dev\Investment_Portfolio` (authoritative)
**Created:** 2026-08-26 · **Revised:** 2026-08-26 after a correct Step 0 stop (see note below)
**Executor:** Claude Code or Gemini CLI, run locally in the repo
**Type:** Version control only. No code changes. No Sheets writes. No `--live` anything.

All decisions in this prompt are made. Execute it; do not stop for sign-off.

> **Revision note — the previous gate numbers were measured wrong, and the executor was right
> to stop.** They came from a Linux shell reading this tree over a mount, where `core.autocrlf`
> is unset. Git there compared CRLF working files against the LF index and reported 189 phantom
> line-ending diffs (287 total vs 98 real). On this machine `core.autocrlf=true` (system
> gitconfig) converts on read, so those diffs do not exist. **There is no line-ending problem in
> this repo.** The normalization commit and `.gitattributes` are removed from the plan entirely.
> The tree did not move: 73 M + 25 D = the 98 files in `git diff`, and the untracked count went
> 36 → 37 only because this prompt file itself is new.
>
> **All expectations below are measured on Windows.** Do not run this gate through a mount or
> container — the numbers will not match.

---

## Why this exists

The 2026-08-26 hygiene pass is on disk and not in git. Worse, so is a large volume of
*shipped feature work*: `vault/doctrine.md`, `utils/doctrine_reader.py`, `utils/price_history.py`,
`utils/market_calendar.py`, `tasks/detect_undocumented_changes.py`, `tasks/build_income_tracking.py`,
`tasks/build_flow_ledger.py` and ~14 prompt files from 08-11 through 08-25 are **untracked**.

HEAD is `df8d938`. The doctrine layer, typed-trigger Crosshairs, decision-capture detector,
price-history router and market calendar exist only as unversioned files on one machine.

**Job: make git history match the shipped state, in four reviewable commits.**

### Non-goals

- Do not implement anything in `prompts/archive/` — declined by decision 2026-08-26.
- Do not implement any section of `prompts/schwab_signal_layer_PROPOSAL_2026-08-25.md`.
- Do not run `manager.py morning`, any `--live` command, or any Sheets write.
- Do not add `.gitattributes` or run `git add --renormalize`.
- Do not edit source to fix anything you notice. Report it in Step 5 and stop.
- Do not create root-level markdown. Extend `CHANGELOG.md` only.
- Do not run `git add -A`. Every commit here is path-scoped.
- Do not push.

---

## Step 0 — Verification gate

Run these. Paste **literal stdout/stderr**. No PASS table.

```
cd /d C:\Dev\Investment_Portfolio
git rev-parse --abbrev-ref HEAD
git log --oneline -3
git status --porcelain=v1
git diff --shortstat
git diff --ignore-all-space --shortstat
dir .git\index.lock
git config core.autocrlf
dir .gitattributes
```

**If any line disagrees, STOP and report — do not adapt.**

| Check | Expected |
|---|---|
| Branch | `cursor/portfolio-manager-launcher` |
| HEAD | `df8d938` |
| Status | ~73 `M`, ~25 `D`, ~37 `??` — about 135 porcelain lines |
| `git diff --shortstat` | `98 files changed` |
| `git diff --ignore-all-space --shortstat` | `98 files changed` — **must equal the line above** |
| `.git/index.lock` | present, 0 bytes |
| `core.autocrlf` | `true` (from `C:/Program Files/Git/etc/gitconfig`) |
| `.gitattributes` | does not exist |

The two shortstats matching is the check that matters: it proves no line-ending noise is in
play and that every dirty file is dirty for a real reason. **If they diverge, stop** — something
changed the EOL handling and this plan's assumptions no longer hold.

**Clear the stale lock** — a mounted Linux shell created it and could not unlink it. Every git
write fails until it is gone:

```
del .git\index.lock
```

If `del` fails, git is unusable in this tree. Stop and report.

---

## Step 1 — Ignore rules and untrack the `.bak` residue

Append to `.gitignore`:

```
# Generated / local-only
data/schwab_price_cache/
morningstar.pdf
vault/theses/*.bak
```

Then drop the three already-tracked `.bak` files from the index:

```
git rm --cached vault/theses/ET_thesis.md.bak vault/theses/PWR_thesis.md.bak vault/theses/VRT_thesis.md.bak
```

**`--cached` is mandatory.** It removes them from the index only; all 39 `.bak` files stay on
disk untouched. Never run bare `git rm` here. CLAUDE.md Hard Rule 7 — a `.bak` taken after an
edit is not a backup — is why these are write-pipeline residue rather than history.

`archive/prompts_files.zip` **is** committed, in Commit 1. It was inventoried as an archive item.

---

## Step 2 — Four `state.md` corrections (authorized; they land in Commit 4)

Each is a claim in `state.md` contradicted by files on disk. Apply as exact replacements. Do not
rewrite surrounding prose. If a target string is not found verbatim, **stop and report** rather
than fuzzy-matching.

**2.1 — Phase 4 live writes (line ~57).** Replace:

> `**`--live` Sheet writes still require Bill sign-off.**`

with:

> `**`--live` Sheet writes completed** — Income_Tracking 2026-08-25, Risk_Metrics 2026-08-25 and 2026-08-26. Evidence: `data/Income_Tracking_bak_20260825T143819Z.csv`, `data/Risk_Metrics_bak_20260826T161115Z.csv`. `build_risk_metrics.main()` returns at `if not live` *before* the archive step, so a `_bak_` CSV exists only after a live write.`

**2.2 — Moment backfill (line ~241).** Replace the whole bullet beginning
`- **Moment extraction backfill is 76/147 transcripts**` with:

> `- ~~**Moment extraction backfill is 76/147 transcripts**~~ — **COMPLETE, verified 2026-08-26.** 234 transcripts in `data/podcast_transcripts/`, 234 `.moments.json` in `data/moments/`, all `schema_version: 2` (zero files fail the v2 check). No further `extract-moments` run needed.`

**2.3 — trigger_types stop point (line ~332).** Replace:

> `Stopped per the prompt's own gate: Step 2's type-proposal table is drafted and awaiting Bill's sign-off before Step 3 (band computation) or Step 4 (writes to thesis files) proceed.`

with:

> `Steps 3 and 4 subsequently completed the same day: all 38 live theses carry a `trigger_type` key with a dated 2026-08-09 Review Log entry (verified 2026-08-26).`

**2.4 — trigger_types bands (line ~335).** Replace:

> `(proposals only, nothing written to any thesis file)`

with:

> `(computed as proposals; written to the thesis files the same day — see the correction in the entry above)`

---

## Step 3 — Dry run

For each commit below, print the exact staging list and nothing else:

```
git add --dry-run -- <paths>
```

Confirm no path appears in two commits, and no path outside the listed prefixes appears at all.

---

## Step 4 — The commits, in this order

**Commit 1 — repo hygiene**

Paths: `.gitignore`, the three `git rm --cached` removals, `prompts/` (including this file),
`docs/archive/root_notes_2026-08-26/`, `archive/one_shot_scripts_2026-08-26/`,
`archive/vault_frameworks_dup_2026-08-26/`, `archive/prompts_files.zip`,
`vault/frameworks/`, the deleted root notes, the `scripts/` deletions.

```
chore: 2026-08-26 repo hygiene — archive declined prompts and obsolete notes

- Incomplete prompts -> prompts/archive/ with declined stamps
  (surface_attribution, vault_framework_visibility, commit_recover_dashboard)
- PWR thesis input -> prompts/archive/inputs/
- Root one-shot notes -> docs/archive/root_notes_2026-08-26/
- Dated one-shot scripts -> archive/one_shot_scripts_2026-08-26/
- Byte-identical vault/frameworks duplicates -> archive/vault_frameworks_dup_2026-08-26/
  (vault/research/ Macro copy is the one that loads; unchanged)
- Signal-layer proposal retained as a decision log; remaining sections unauthorized
- Ignore price cache and thesis .bak residue; untrack the three tracked .bak files

No code changes. Incomplete prompts are declined, not deferred.
```

**Commit 2 — untracked shipped modules**

Paths: `vault/doctrine.md`, `utils/doctrine_reader.py`, `utils/price_history.py`,
`utils/market_calendar.py`, `tasks/detect_undocumented_changes.py`,
`tasks/build_income_tracking.py`, `tasks/build_flow_ledger.py`,
`scripts/reconcile_price_history_2026-08-25.py`, `vault/theses/QXO_thesis.md`,
`vault/theses/archive/ES_thesis.md`, `vault/theses/archive/JPIE_thesis.md`.

```
feat: land 2026-08 build wave — doctrine, decision capture, price history, calendars

Built and in service since 2026-08-11..08-25; never committed.
```

**Commit 3 — modified spine, tasks, utils**

Paths: `config.py`, `manager.py`, `pipeline.py`, `core/`, `tasks/`, `utils/`.

**Before committing, print `git diff --stat` for these paths and paste it.** If a diff does not
correspond to a dated prompt in `prompts/`, stop and ask.

```
feat: typed triggers, Crosshairs feed, briefing and store changes

Working-tree changes accumulated across the 2026-08 prompts.
See prompts/ for the per-build specs.
```

**Commit 4 — docs and vault content**

Paths: `CLAUDE.md`, `state.md`, `CHANGELOG.md`, `PORTFOLIO_SHEET_SCHEMA.md`, `CLI_MANUAL.md`,
`CLI_CHEATSHEET.md`, `docs/sheets_hand_edit_inventory.md`, `vault/theses/`,
`.devcontainer/devcontainer.json`.

```
docs: sync CLAUDE.md, state.md, CHANGELOG.md, schema to shipped state

Includes four state.md corrections verified against disk 2026-08-26:
Phase 4 live writes completed; moment backfill complete (234/234, schema v2);
trigger_types Steps 3-4 landed 2026-08-09 (38/38 theses carry trigger_type).
```

---

## Step 5 — Verification

**Literal stdout required. An agent-reported PASS table is not evidence.**

```
git log --oneline -5
git status --porcelain=v1
git show --stat HEAD~3
git show --stat HEAD~2
git show --stat HEAD~1
git show --stat HEAD
git ls-files vault/theses/ | findstr .bak
dir vault\theses\*.bak
findstr /C:"76/147" state.md
findstr /C:"still require Bill sign-off" state.md
python -c "import utils.doctrine_reader, utils.price_history, utils.market_calendar; print('imports ok')"
python manager.py --help
```

| # | Check | Pass condition |
|---|---|---|
| 1 | Working tree | `git status --porcelain` empty |
| 2 | Commits | Exactly 4, in the order above |
| 3 | No cross-contamination | No file in more than one commit's `--stat` |
| 4 | No generated artifacts | `data/schwab_price_cache/` and `morningstar.pdf` absent from every `--stat` |
| 5 | `.bak` untracked, not deleted | `git ls-files` returns nothing; `dir` still lists 39 files |
| 6 | state.md corrections applied | both `findstr` searches return nothing |
| 7 | Imports resolve | `imports ok` printed |
| 8 | CLI loads | `manager.py --help` exits 0 |
| 9 | Nothing implemented | `git log -p` contains no new code matching `surface_attribution`, `vault_framework`, or signal-layer sections |

---

## Step 6 — Report

1. Literal Step 0 output
2. Four commit SHAs, one line each
3. The Step 5 table with literal evidence under each row
4. Anything you noticed and did not touch — one line each, no recommendations

Then stop.

---

## Traps

- **`.git/index.lock` regenerates** if a mounted or sandboxed shell runs git here. Check for it
  after any failure before assuming a real git error.
- **Do not measure this repo's git state from a mount.** `core.autocrlf` differs there and every
  count will be wrong. That is what caused the first Step 0 stop.
- **`state.md` is lowercase.** A reference to `STATE.md` breaks on case-sensitive filesystems.
- **`desktop.ini` files** are present in most directories. Leave them exactly as they are.
- **`git rm` without `--cached` deletes from disk.** Step 1 requires `--cached`.
