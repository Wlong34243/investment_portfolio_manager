# Prompt: Make Vault Framework Material Visible to the Bundle

> **STATUS: not built; declined 2026-08-26.** Frameworks stay offline until a concrete consumer exists. Wiring April 2026 framework JSON into every composite would inflate theme weight without a decision surface that reads it. Do not implement. Archived under `prompts/archive/`.

**Created:** 2026-08-01
**Target executor:** Claude Code or Gemini CLI, run locally in the repo
**Scope:** one function in `core/vault_bundle.py`, one dataclass field comment, one test
**Estimated change:** ~15 lines
**Do NOT touch:** `core/bundle.py`, `core/composite_bundle.py`, thesis loading, hashing logic

---

## The problem

`vault/research/` and `vault/frameworks/` hold curated framework material, all dated
2026-04-13. Most of it has never reached an agent.

**Audited 2026-08-01:**

```
vault/frameworks/  (2 files — NEITHER is read; the directory is not in the file map)
  Macro_super_cycle_framework.md          6,757 b
  joys_of_compounding_framework.json      8,376 b

vault/research/    (8 files — only the 3 .md files are read)
  Macro_super_cycle_framework.md          6,757 b   LOADED
  Macro_super_cycle_frameworkPT2.md       4,725 b   LOADED
  RotationAgent.md                        4,651 b   LOADED
  100bangers.json                         1,718 b   INVISIBLE
  Macro_super_cycle_framework.json        2,282 b   INVISIBLE
  joys_of_compounding.json                4,083 b   INVISIBLE
  morning_starMay12.json                  5,037 b   INVISIBLE
  sector_specific.json                    3,786 b   INVISIBLE

vault/transcripts/ (0 files)
```

Two independent causes, both in `core/vault_bundle.py`:

1. **`_discover_vault_files()` (line ~224)** globs `RESEARCH_DIR.glob("*.md")`. JSON files in
   `vault/research/` are never discovered.
2. **`FRAMEWORKS_DIR` does not exist.** The constants block (line ~35) defines `THESES_DIR`,
   `TRANSCRIPTS_DIR` and `RESEARCH_DIR` only, and `_discover_vault_files()` returns a
   three-key dict. `vault/frameworks/` is not scanned at all.

Net: **7 of 10 curated files are invisible.** There is also a duplicate —
`Macro_super_cycle_framework.md` exists byte-identical in both directories, so a naive fix
that scans both would ingest the same document twice and inflate its weight in any
theme-extraction pass.

---

## Step 0 — Verification gate

Confirm before writing code. If any item differs, STOP and report.

1. `core/vault_bundle.py` defines `VAULT_DIR`, `THESES_DIR`, `TRANSCRIPTS_DIR`,
   `RESEARCH_DIR` in a constants block near line 35, and `MAX_FILE_BYTES = 512 * 1024`.
2. `_discover_vault_files()` returns a dict with exactly the keys `theses`, `transcripts`,
   `research`, using globs `*_thesis.md`, `*.md`, `*.md` respectively.
3. `build_vault_bundle()` iterates `files["transcripts"]` and `files["research"]` in a
   section commented `# 4. Load transcripts and research`, calling
   `_load_vault_document(path, <doc_type>)`.
4. `VaultDocument.doc_type` is documented as `"thesis" | "transcript" | "research"`.
5. `_load_vault_document()` reads with `path.read_text(encoding="utf-8", errors="replace")`
   and applies `_parse_thesis_fields()` only when `doc_type == "thesis"`.
6. Re-run the file audit above and confirm the counts still match. If files have been added
   or removed since 2026-08-01, report the new counts before proceeding.

---

## The change

### 1. Add the frameworks directory constant

Beside the existing three:

```python
FRAMEWORKS_DIR = VAULT_DIR / "frameworks"
```

### 2. Widen discovery to include JSON, and add frameworks

`_discover_vault_files()` should return four keys. Research and frameworks both accept
`.md` and `.json`; theses and transcripts are unchanged.

Requirements:

- Sort deterministically. Bundle hashing depends on stable ordering — sort the combined
  `.md` + `.json` list by filename, not by extension then filename.
- **De-duplicate by content hash across `research` and `frameworks`.** Compute SHA-256 of
  the file bytes during discovery; if the same hash appears in both directories, keep the
  `research` copy and drop the `frameworks` one. Log the drop. This is not hypothetical —
  `Macro_super_cycle_framework.md` is currently duplicated.
- Do not recurse into subdirectories.
- Ignore `desktop.ini` and any dotfile.

### 3. Load frameworks in `build_vault_bundle()`

Extend the `# 4. Load transcripts and research` block to also iterate `files["frameworks"]`
with `doc_type="framework"`. Follow the existing pattern exactly, including the
`vault_skip_log` append on `doc.skipped`.

### 4. Update the `doc_type` contract

`VaultDocument.doc_type` becomes `"thesis" | "transcript" | "research" | "framework"`.
Update the inline comment. Grep for any consumer that switches on `doc_type` and confirm a
new value does not break it — check `core/composite_bundle.py`,
`tasks/export_ai_briefing.py`, and `utils/agents/`. **If any consumer enumerates doc_types
exhaustively, report it rather than silently adding a branch.**

### 5. JSON handling — read as text, do not parse

`_load_vault_document()` must treat `.json` exactly as it treats `.md`: read as UTF-8 text,
hash the text, store the raw string in `content`. **Do not `json.loads()` it.** The bundle's
job is to carry the document to the LLM, and the LLM reads JSON fine as text. Parsing adds
a failure mode (a malformed file would raise inside bundle assembly) for no benefit.

Confirm `_parse_thesis_fields()` is not applied — it is already gated on
`doc_type == "thesis"`, so this should hold automatically. Verify it does.

---

## Non-goals

- Do not convert the `.json` files to `.md`. Leave the source material untouched.
- Do not change `MAX_FILE_BYTES` — the largest file is 8,376 bytes, nowhere near the cap.
- Do not delete the duplicate `Macro_super_cycle_framework.md` from `vault/frameworks/`.
  De-duplicate at read time and report it; deleting a file is Bill's call.
- Do not add frameworks to the thesis coverage checks in `utils/level_coverage.py`.
- Do not change bundle schema version unless a consumer actually breaks — if one does,
  report before bumping.

---

## Post-build verification checklist

Demand literal stdout. Do not accept a reported PASS.

- [ ] `python -c "from core.vault_bundle import _discover_vault_files as d; f=d(); print({k: len(v) for k,v in f.items()})"`
      prints 4 keys, with `research` = 8 and `frameworks` = 1 (2 minus the deduped duplicate).
- [ ] The dedup fires and is logged, naming `Macro_super_cycle_framework.md`.
- [ ] Build a vault bundle and confirm document count rises by exactly 6 (5 research JSONs
      + 1 framework JSON) versus a pre-change run.
- [ ] Every previously-invisible file appears with non-null `content` and a real
      `content_hash` — specifically `100bangers.json`, `sector_specific.json`,
      `joys_of_compounding.json`, `morning_starMay12.json`,
      `Macro_super_cycle_framework.json`, `joys_of_compounding_framework.json`.
- [ ] No document has `skipped=True`.
- [ ] Running discovery twice returns identical ordering (hash stability).
- [ ] A deliberately malformed `.json` dropped into `vault/research/` is ingested as text
      without raising. Delete it afterward.
- [ ] `python manager.py morning` (dry run) completes through STEP 7 with the larger vault
      bundle, and STEP 8 composite assembly succeeds.
- [ ] `git diff --stat` shows changes confined to `core/vault_bundle.py` plus any new test.

---

## Follow-on, not part of this build

`vault/transcripts/` is empty and `TRANSCRIPTS_DIR` is scanned on every build for nothing.
Either wire it to something or drop it. Note it in `state.md`; do not act on it here.

Once this lands, `vault/research/` becomes the correct home for durable framework and
screening material — the material that is specific to Bill, absent from the web, and stable
enough not to rot. Adding to that directory is then a real upgrade to agent context, which
it currently is not.
