# Desk lifecycle follow-on — core index move + live sidecar backfill launcher

**Created:** 2026-08-29
**Executor:** Cursor (Agent mode).
**Depends on:** `prompts/desk_redesign_phase2_2026-08-28.md` (shipped + fixups 2026-08-28).
**Scope:** (1) move lifecycle disk-index helpers out of `ui/` so CLI does not import UI;
(2) register a Tier-1 live backfill routine with typed confirmation. No new surfaces.

> **Policy note (Bill, 2026-08-29).** Phase 2 kept `judge-lifecycle-missing-json` dry-run only
> on purpose. This prompt **reopens** that call: add a **sibling** live routine, do **not**
> upgrade the dry-run card in place. Batch `--live` stays behind typed routine-id confirmation.

---

## Step 0 — Verification gate

Paste literal stdout for every command. Any disagreement ⇒ **STOP and report** — do not adapt.

```bash
# 0.1 — CLI currently imports UI for backfill listing
# Expected: one hit on "from ui.judgment_artifacts import list_lifecycle_missing_json"
rg -n "list_lifecycle_missing_json|list_lifecycle_artifacts|parse_lifecycle_ticker" \
  ui/judgment_artifacts.py manager.py ui/judgment_page.py tests/test_judgment_page_glob.py

# 0.2 — OUTPUT_DIR lives in both writer + UI reader today
# Expected: core/judgment/artifacts.py and ui/judgment_artifacts.py both define or use OUTPUT_DIR
rg -n "OUTPUT_DIR" core/judgment/artifacts.py ui/judgment_artifacts.py

# 0.3 — dry-run routine only; five live IDs
# Expected: one "judge-lifecycle-missing-json" block without --live in argv;
# UI_APPROVED_LIVE_IDS has exactly five members
rg -n "judge-lifecycle-missing-json|UI_APPROVED_LIVE_IDS" ui/routines.py
rg -n "UI_APPROVED_LIVE_IDS|test_ui_approved_live" tests/test_ui_cockpit.py

# 0.4 — dry-run CLI still works (expected: table with action=run rows, no writes)
.\.venv\Scripts\python.exe manager.py judge lifecycle --missing-json
```

---

## Part 1 — Move lifecycle index to `core/judgment/`

### Problem

`manager.py` imports `list_lifecycle_missing_json` from `ui/` — CLI depends on the UI layer.

### Target layout

| Module | Owns |
|---|---|
| **`core/judgment/lifecycle_index.py`** (new) | Disk index: glob, ticker parse, dedupe, sidecar load, `list_lifecycle_artifacts`, `list_lifecycle_missing_json` |
| **`core/judgment/artifacts.py`** | Keep `OUTPUT_DIR` + sidecar **writers** (`write_sidecar`, `campaign_to_sidecar`, …) |
| **`ui/judgment_artifacts.py`** | Thin UI layer: re-export index helpers for any stray imports; keep `load_lifecycle_for_ticker`, `load_artifact_bundle`, `newest_artifact` |

### Move (verbatim logic, new home)

From `ui/judgment_artifacts.py` → `core/judgment/lifecycle_index.py`:

- Import `OUTPUT_DIR` from `core.judgment.artifacts` (single source — do not redefine)
- `_LIFECYCLE_TICKER_RE` / `parse_lifecycle_ticker`
- `_load_json_sidecar`
- `list_lifecycle_artifacts`
- `list_lifecycle_missing_json`

### Import rewires

| Caller | New import |
|---|---|
| `manager.py` | `from core.judgment.lifecycle_index import list_lifecycle_missing_json` |
| `ui/judgment_page.py` | `from core.judgment.lifecycle_index import list_lifecycle_artifacts` (or via UI re-export) |
| `ui/judgment_artifacts.py` | Re-export `parse_lifecycle_ticker`, `list_lifecycle_artifacts`, `list_lifecycle_missing_json` from core |
| `tests/test_judgment_page_glob.py` | Monkeypatch `core.judgment.lifecycle_index` / shared `OUTPUT_DIR` so fixtures still work |

### Structural guard (add)

```python
# tests/test_manager_no_ui_judgment_import.py
from pathlib import Path

def test_manager_does_not_import_ui_judgment_artifacts():
    text = Path("manager.py").read_text(encoding="utf-8")
    assert "ui.judgment_artifacts" not in text
```

### Part 1 verification — paste stdout

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_judgment_page_glob.py tests/test_ui_no_inline_judgment.py tests/test_manager_no_ui_judgment_import.py -q
.\.venv\Scripts\python.exe manager.py judge lifecycle --missing-json
# Expect: same table shape as Step 0.4; exit 0; still no new .json if dry-run
```

**Stop after Part 1 green.** Part 2 is independent and may be a separate commit.

---

## Part 2 — Live backfill launcher

### Problem

Dry-run routine exists; backfill still requires a terminal `--live`. One-click from `/runs` is wanted, with ceremony matching other Tier-1 writes.

### Design (do not deviate)

**Keep** existing routine unchanged:

| id | tier | argv |
|---|---|---|
| `judge-lifecycle-missing-json` | 0 | `manager.py judge lifecycle --missing-json` |

**Add** sibling:

| id | tier | argv |
|---|---|---|
| `judge-lifecycle-missing-json-live` | 1 | `manager.py judge lifecycle --missing-json --live` |

### Registry block (exact intent)

```python
_reg(_routine(
    "judge-lifecycle-missing-json-live",
    "Judgment — backfill missing sidecars (live)",
    ("manager.py", "judge", "lifecycle", "--missing-json", "--live"),
    1,
    "Recompute lifecycle campaigns missing JSON sidecars.",
    timeout_sec=7200,  # match judge-lifecycle-all; ~2.5 min × N
    long_run_warning="Runs ~2–3 min per ticker. Do not close the console dock.",
    writes_banner="Writes: agent_outputs/judgment/*.md + .json; SQLite judgment_campaign registry",
    confirm_name=True,  # type routine id — same ceremony as dashboard/tax refresh
    group="REVIEW",
))
```

**Also:**

1. Add `"judge-lifecycle-missing-json-live"` to `UI_APPROVED_LIVE_IDS`.
2. Update dry-run routine description to point at the live sibling on Runs.
3. Update `ui/templates/judgment.html` "no JSON" chip hover / note to name the live routine or link `/runs`.

Do **not** put a live batch backfill button on Position Story. Keep per-ticker `judge-lifecycle` there.

`tests/test_ui_cockpit.py::test_ui_approved_live_routines_exact_set` will fail until the frozenset is updated — that is the guard working. Fix the expected set; do not weaken the test.

### Docs (Part 2)

- `CLAUDE.md` — Desk UI launch policy: sixth approved `--live` routine (sandbox writes only). Update Key Files `ui/routines.py` line if it still says "five".
- `CHANGELOG.md` — one dated entry covering Part 1 + Part 2 (or two bullets under one date).
- `state.md` — extend the Desk redesign Phase 2 line; note live backfill launchable with typed confirmation.

### Part 2 verification — paste stdout / observations

| # | Check | Expect |
|---|---|---|
| 1 | Launch dry-run from `/runs` | Table in console; **no** new `.json` files |
| 2 | Launch live **without** typing id | Refused with confirm message |
| 3 | Launch live **with** typed `judge-lifecycle-missing-json-live` | SSE streams; `.json` count increases (or all already present → green "All … have JSON") |
| 4 | Pipeline lock held | Refused (same as other routines) |
| 5 | `pytest tests/test_ui_cockpit.py::test_ui_approved_live_routines_exact_set -q` | Green |
| 6 | `pytest tests/test_manager_no_ui_judgment_import.py tests/test_judgment_page_glob.py -q` | Still green after Part 2 |

**Do not report a PASS table you did not produce.**

---

## Sequencing

```
Part 1 (refactor)  →  pytest + dry-run CLI  →  optional commit
Part 2 (launcher)  →  frozenset test + browser smoke  →  optional commit
```

Do not commit unless Bill asks.

---

## Out of scope

- Retrofitting `--live` onto `judge lifecycle --ticker` / `--all` CLI paths
- Moving `load_lifecycle_for_ticker` / Position Story assembly into core
- Auto-run backfill on morning pipeline
- Per-ticker live backfill button on Position Story (batch shape is wrong there)
- Chart library, light theme, Tier 1/2 expansion beyond this one routine

---

## Effort

| Part | Touch | Time |
|---|---|---|
| 1 — core move | ~4 files, 1 new module, 1 structural test | ~30 min |
| 2 — live launcher | `routines.py`, judgment template copy, CLAUDE/CHANGELOG/state, frozenset test | ~20 min |
