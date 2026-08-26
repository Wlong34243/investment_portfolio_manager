# Build: Vault Sync YAML Hardening

**Repo:** `C:\Dev\Investment_Portfolio` (authoritative).
**Author:** Chief Architect (Cursor, 2026-08-11)
**Executor:** Claude Code / Gemini CLI
**Prompt version:** 1.0.0
**Incident:** 2026-08-11 morning STEP 6 — `Vault sync failed: found duplicate key "triggers"` on `NOW_thesis.md`. One hand-edited frontmatter aborted gather for every ticker; zero files synced.

Standing conventions: archive-before-overwrite; dry run → verify → `--live`; never write `Target_Allocation`; no price targets, forecasts or buy/sell language in any output. Extend `CHANGELOG.md` and `state.md` — do not create new root markdown files.

---

## HARD CONSTRAINTS — read before anything else

1. **Soft-skip, do not auto-repair.** When frontmatter is unparseable under ruamel, skip that ticker’s thesis read (style falls back as today), accumulate the error, continue. **Do not invent merge logic for duplicate YAML keys.** Bill fixes the file; the pipeline reports it.
2. **Do not raise `logs/HEALTH_FAILURE.flag` for YAML parse failures.** That sentinel’s remediation text is Schwab-login (`python manager.py login` / `schwab_emergency_reauth.bat`) and the dashboard/briefing treat it as auth/health degradation. Polluting it for thesis YAML would mislead. Surface via STEP 6 `warn` + console + lint only.
3. **Do not unify PyYAML vs ruamel across the vault in this pass.** Note the reader/writer split in `state.md`; full unification is a later batch.
4. **Do not wire lint as a morning hard gate.** `lint_theses.py` stays report-only (exit 0).
5. **Do not touch Schwab, Sheets schema, trigger-type classification, or `export_ai_briefing.py`.**

---

## Why this is fragile (context for the executor)

```
pm morning STEP 6
  → gather_thesis_sync_data()          # NO per-ticker catch
    → ThesisManager.get_frontmatter()  # strict ruamel, NO try/except
      → duplicate key "triggers"       # raises
        → entire gather aborts
          → Vault Sync fail — zero files synced
```

Contrast: `tasks/write_thesis_updates.py` already has per-ticker `try/except` (errors counter). Too late — gather never returned.

Reader/writer split: `utils/thesis_reader.py` `load_frontmatter()` uses PyYAML and falls back to flat on error, so analysis surfaces stay quiet while the write path dies. That asymmetry is the defect class.

`NOW_thesis.md` was fixed 2026-08-11 (single `triggers: { trigger_type: ceiling_only }`). Do not re-break it.

---

## Step 0 — Verification gate

Report PASS/FAIL with **literal stdout/stderr**. Stop on any discrepancy — do not adapt silently.

| # | Assertion |
|---|---|
| 0.1 | `vault/theses/NOW_thesis.md` frontmatter has **exactly one** `triggers:` key. Confirm with `rg -n "^triggers:" vault/theses/NOW_thesis.md` (expect one hit). Content must be `trigger_type: ceiling_only`. |
| 0.2 | Live vault: `rg -n "^triggers:" vault/theses/*_thesis.md` — no live file other than a false positive may show two `triggers:` lines inside the same `---` frontmatter block. Report any offender. |
| 0.3 | `utils/thesis_utils.py` `ThesisManager.get_frontmatter()` (~line 39–43) calls `self.yaml.load(...)` with **no** try/except. |
| 0.4 | `core/thesis_sync_data.py` `gather_thesis_sync_data()` (~143–145) constructs `ThesisManager` and calls `get_frontmatter()` inside the holdings loop with **no** per-ticker catch around that call. Return type is `Dict[str, TickerSyncPayload]`. |
| 0.5 | `tasks/write_thesis_updates.py` `write_thesis_updates()` already wraps each ticker in `try/except` and increments `report["errors"]` (~173–175). |
| 0.6 | Callers of `gather_thesis_sync_data(` that must be updated after a return-shape change: `manager.py` `vault_sync` (~705), `vault_sync_status` (~730), `morning` STEP 6 (~1707); `core/thesis_sync_data.py` `__main__` (~271); `tasks/write_thesis_updates.py` `__main__` (~181). Confirm each with grep. |
| 0.7 | `tasks/lint_theses.py` uses `extract_frontmatter_flat` via `_frontmatter()` — flat per-line parse; cannot detect duplicate YAML keys. |
| 0.8 | `tasks/health.py` `write_failure_sentinel()` remediation string contains `python manager.py login` (Schwab-auth centric). Do not call it from vault sync. |

If Step 0 finds NOW still has duplicate `triggers:`, fix that one file first (keep the non-empty `ceiling_only` block; delete `triggers: {}`), then continue. Do not invent a general auto-fixer.

---

## Step 1 — Safe frontmatter API on `ThesisManager`

**File:** `utils/thesis_utils.py`

Add an explicit safe API so callers can distinguish “no frontmatter” from “broken YAML”:

```python
def get_frontmatter_safe(self) -> tuple[Optional[Dict], Optional[str]]:
    """
    Returns (data, error_message).
    - (None, None)     — no frontmatter block present
    - (dict, None)     — parsed OK
    - (None, str)      — frontmatter present but unparseable under ruamel
    """
```

Implementation notes:
- Reuse the same `self.yaml` / `FRONTMATTER_PATTERN` as `get_frontmatter()`.
- Catch ruamel duplicate-key and other load exceptions; put `str(exc)` (or a short message including ticker/path if available) in the error string.
- Keep `get_frontmatter()` as a thin wrapper: return the dict on success, `None` when absent **or** broken (preserve today’s “falsy on miss” callers), but prefer new code to call `get_frontmatter_safe()`.
- **Do not** soften `update_frontmatter` / `update_triggers`. A broken file should still fail hard on write; `write_thesis_updates` already isolates per ticker.

Stop and report the new signature before Step 2.

---

## Step 2 — Per-ticker isolation in `gather_thesis_sync_data`

**File:** `core/thesis_sync_data.py`

1. Change the return so callers get both payloads and parse errors. Preferred shape:

   ```python
   class ThesisSyncGatherResult(BaseModel):
       payloads: Dict[str, TickerSyncPayload]
       parse_errors: List[dict]  # [{"ticker": "NOW", "error": "..."}, ...]
   ```

   Or return `tuple[Dict[str, TickerSyncPayload], List[dict]]`. Pick one and use it everywhere. Do not leave a silent dual API.

2. Around the `ThesisManager` / frontmatter read (~143–145):
   - Call `get_frontmatter_safe()`.
   - On `(None, err)` with err set: append to `parse_errors`, leave `fm = None`, continue the loop (style falls back to `ticker_strategies.json` / defaults exactly as when the thesis file is missing or has no style).
   - Still include the ticker in `payloads` when holdings data exists — the position is real; only the thesis YAML read failed. Downstream write will then hit `update_frontmatter` and land in `write_thesis_updates`’s per-ticker except (error counted). That is acceptable: gather no longer aborts the whole vault.
   - Optional refinement (preferred if cheap): if frontmatter parse failed, **omit** that ticker from `payloads` (skip write entirely) and only report via `parse_errors`. Rationale: writing would fail anyway and a partial region update is worse than leaving the file untouched. **Choose omit-from-payloads.** Document the choice in the Step 2 report.

3. Empty holdings still returns empty payloads + empty parse_errors (same early return as today, adapted to the new shape).

4. Update `__main__` in this file to unpack the new return.

Stop and report before Step 3. Do not change morning yet.

---

## Step 3 — Update all gather callers + morning STEP 6 warn

**Files:** `manager.py`, `tasks/write_thesis_updates.py` (`__main__` only)

### 3a. `vault sync` and `vault sync-status`

Unpack the new return. If `parse_errors` non-empty, print each ticker + error in yellow/red before the normal report/table. Do not abort the command solely because of parse_errors when other payloads exist.

### 3b. `morning` STEP 6 (~1700–1721)

```
payloads / parse_errors = gather...
if parse_errors:
    print each: "Thesis frontmatter unparseable: {ticker}: {error}"
if payloads:
    report = write_thesis_updates(...)
    if parse_errors or report.get('errors', 0) > 0:
        step_results.append(("Vault Sync", "warn"))
    else:
        step_results.append(("Vault Sync", "pass"))
else:
    if parse_errors:
        # every held thesis broken, or only errors and nothing to write
        step_results.append(("Vault Sync", "warn"))
    else:
        step_results.append(("Vault Sync", "pass"))  # "No vault sync data"
```

Rules:
- Keep the outer `try/except` for unexpected failures → `"fail"`.
- Do **not** abort later morning steps when STEP 6 is `warn`.
- Do **not** call `write_failure_sentinel`.

### 3c. `write_thesis_updates.py` `__main__`

Unpack new return; ignore parse_errors or print them — dry-run helper only.

Stop and report. No live morning run required in this step.

---

## Step 4 — Lint: frontmatter must parse under ruamel

**File:** `tasks/lint_theses.py`

Add check **6** (update the module docstring Checks list):

- Extract the frontmatter block with the same `---` regex pattern `ThesisManager` uses (or instantiate `ThesisManager` / share a tiny helper — prefer calling `ThesisManager(path).get_frontmatter_safe()` so lint and sync cannot drift).
- On error: append a finding like  
  `UNPARSEABLE FRONTMATTER: {error}`  
  Include line number when the exception message carries one (ruamel duplicate-key messages usually do).
- Stay report-only; `main()` still exits 0.
- Do not remove existing checks 1–5.

Update the module docstring’s “Checks (per file)” list to include item 6.

---

## Step 5 — Docs

1. **`CHANGELOG.md`** — under `[Unreleased]` or a dated `## [2026-08-11] — Vault sync YAML hardening` section:
   - Incident: duplicate `triggers` on NOW aborted STEP 6 gather for all tickers.
   - Fix: `get_frontmatter_safe`, per-ticker isolation + `parse_errors` from gather, morning STEP 6 warn, lint ruamel check.
   - Explicit: does **not** raise `HEALTH_FAILURE.flag`.

2. **`state.md`** — short Known Issues / fixed-fragility note:
   - Reader (`thesis_reader` / PyYAML + flat fallback) vs writer (`ThesisManager` / strict ruamel) disagree on malformed frontmatter; this pass hardens the write path only; unification deferred.
   - NOW duplicate-`triggers` incident 2026-08-11 fixed in-file the same day.

No new root markdown. No plan-file edits.

---

## Mid-prompt sign-off (before any `--live` morning)

Present a one-row confirmation table and wait only if something unexpected appeared in Steps 1–4. Otherwise proceed to verification.

| Item | Choice locked by this prompt |
|---|---|
| Bad YAML behavior | Omit ticker from payloads; report in `parse_errors` |
| Auto-merge duplicates | **No** |
| HEALTH_FAILURE for YAML | **No** |
| Lint as morning gate | **No** |

---

## Post-build verification checklist

Demand **literal stdout/stderr**. Do not accept an agent-reported PASS table without output.

| # | Check | How |
|---|---|---|
| V1 | NOW still has one `triggers:` | `rg -n "^triggers:" vault/theses/NOW_thesis.md` |
| V2 | Synthetic duplicate-key fixture | Copy any live thesis to a **temp path outside the live vault** (or a throwaway under `vault/theses/_fixture_dup_triggers_thesis.md` that is deleted after). Give it two `triggers:` keys in frontmatter. |
| V3 | `get_frontmatter_safe` on the fixture | Returns `(None, <error mentioning duplicate / triggers>)`. Paste stdout. |
| V4 | Gather isolation | Invoke gather in a way that includes the fixture ticker **or** temporarily point a held ticker’s path at the fixture under a unit-style call. Expect: fixture ticker in `parse_errors`, other tickers still present in `payloads`. Paste a summary (`len(payloads)`, `parse_errors`). **Delete the fixture before any `--live` sync.** |
| V5 | Lint flags the fixture | `python tasks/lint_theses.py --vault <dir containing fixture>` shows `UNPARSEABLE FRONTMATTER`. Paste the finding line. Delete fixture after. |
| V6 | Call sites compile | `python -c "from core.thesis_sync_data import gather_thesis_sync_data; ..."` unpacks the new return without error. `python manager.py vault sync --help` and `python manager.py morning --help` still work. |
| V7 | No HEALTH_FAILURE wiring | `rg -n "write_failure_sentinel|HEALTH_FAILURE" core/thesis_sync_data.py tasks/write_thesis_updates.py` — no new hits from this batch. Morning STEP 6 block must not call the sentinel. |
| V8 | Docs | CHANGELOG + state.md updated; no new root `*.md`. |

If V4 cannot be exercised without touching Sheets, a pure unit-style script that constructs `ThesisManager` on the fixture and simulates the gather branch (safe API + omit-from-payloads) is acceptable — say so and paste that script’s stdout. Do not run `pm morning --live` solely to verify this; dry paths are enough.

---

## Out of scope (do not do)

- Auto-repairing or merging duplicate YAML keys
- Unifying PyYAML and ruamel vault-wide
- Making `lint_theses` fail morning or exit non-zero
- Touching Schwab clients, Sheets writers, trigger classification, or briefing exporter
- Re-opening the NOW thesis body / review log beyond confirming frontmatter has one `triggers:` block
