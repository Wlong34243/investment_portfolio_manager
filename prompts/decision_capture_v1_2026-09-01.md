# Decision Capture v1 — build prompt

**Handoff target:** Cursor.
**Design doc:** `docs/architecture/07_decision_as_first_class_record.md` — read it first,
in full. This prompt implements sections "The primitive", "Two surfaces, one loop", and
sequence steps 1–3. **Step 4 (deriving triggers from decisions) is OUT OF SCOPE.**

**Standing premise:** innovate and automate; correction comes from scrutinising real
signals in use. Ship first values, do not tune. But see "The firing proof" below — the
one thing this repo has proven it gets wrong is shipping detectors that cannot fire.

---

## The firing proof — non-negotiable, applies to every step

On 2026-09-01 two detectors were found structurally unable to fire, and both had
passed review:

- `MATERIAL_RESIZE_NO_REVIEW` — `_review_log_dates` returned the same transaction dates
  it was being compared against, so its suppression was unconditionally true.
- `lint_theses` check 5 (stale review > 90 days) — the morning sync stamps
  `last_reviewed` on all 41 theses daily, so the input is overwritten before it is read.

A ranker term was also found to be a silent no-op because its test fixture used
different units from production.

**Therefore, for every check, detector, filter or scoring term added by this prompt you
must demonstrate, with literal output, both that it fires on a real or fixture positive
AND that it stays silent on a real or fixture negative.** "Tests pass" is not that
demonstration. A term that cannot be shown to change an outcome is not done.

Fixtures for anything fed by Google Sheets must be built from a real row's shape **and
units** (`Weight` is a fraction in `Holdings_Current` col Q; `*_pct` fields are
percentage points), with one pinned known-value assertion.

---

## Step 0 — Verification gate

**First action, before any code:** run the suite and paste the literal summary line.
Baseline as of 2026-09-01 was `9 failed, 210 passed`. Record what you actually get.
Every later run is diffed against your captured number, not against this document.

Then confirm and report. **STOP on any mismatch — do not adapt silently.**

1. `docs/architecture/07_decision_as_first_class_record.md` exists and you have read it.
2. `tasks/ingest_ai_dispatch.py` exists. Print its dedup-ledger path, its `--live` gate,
   and its output directory. This is the pattern to copy in Step 2.
3. `vault/decisions/` and `data/decision_proposals/` do **not** exist yet.
4. Print the frontmatter key list across live theses (`vault/theses/*_thesis.md`,
   excluding `.bak*`). Confirm `last_ratified` appears **zero** times and
   `last_reviewed` appears **41** times.
5. Print `lint_theses.py` check 5's current implementation and the field it reads.
6. Print `UI_WRITE_ROUTE_ALLOWLIST` from `ui/app.py` as it currently stands.
7. Confirm `ui/why_cards.py` exists (the why-card lane shipped 2026-09-01). The
   assertion card in Step 4 lives beside it, not inside it.

---

## Step 1 — The decision record

Create `core/decisions/` with:

- `schema.py` — a dataclass matching the schema in the design doc §"Schema" exactly.
  Field names are the contract; do not rename, do not add fields, do not drop
  `unencodable_conditions`.
- `validate.py` — `validate(record) -> list[str]` returning human-readable errors.
  Required: `id` matches `^\d{4}-\d{2}-\d{2}_[A-Z0-9]+_[a-z0-9_]+$`; `decided_on` is a
  real date not in the future; `scope` in `{position, portfolio}`; `tickers` non-empty
  when scope is position; `conditions.operator` in `{all, any}`; every leg has
  `metric`/`comparator`/`value`; `status` in the four allowed values; `provenance` in
  `{extracted, authored_at_desk}`.
- `store.py` — read/write for both locations:
  - `data/decision_proposals/<id>.json` — **quarantine.** Machine-writable.
  - `vault/decisions/<id>.md` — **binding.** YAML frontmatter + the assertion as body
    prose. Written by **exactly one** caller: desk ratification (Step 4).
    `store.py` must refuse to write here unless passed an explicit
    `ratification=True` argument, and must never overwrite an existing file.

Reject any record whose `status` is `ratified` on the proposals path, and any whose
status is not `ratified` on the vault path.

## Step 2 — Ingest path for proposals

`tasks/ingest_decision_proposals.py`, modelled directly on `tasks/ingest_ai_dispatch.py`.

- Reads a drop file `decision-proposals-YYYY-MM-DD.json` from the same artifacts
  directory `ingest_ai_dispatch` reads (`config.SPOTIFY_STUDIO_TRANSCRIPTS_DIR`).
- sha256 dedup ledger at `data/decision_proposals/.ingested.json`.
- Dry run by default; writes only under `--live`.
- Validates every record through `core/decisions/validate.py`. **A file with any
  invalid record is rejected whole** — do not partially ingest.
- Forces `status: proposed` and `provenance: extracted` on ingest regardless of what
  the drop file claims. The drop file cannot self-promote.
- Writes only to `data/decision_proposals/`. It must be impossible for this script to
  write to `vault/` — assert it in a test.

Document the drop-file contract in the module docstring: a JSON array of records, the
exact fields, and the statement that the emitting Cowork task never writes the repo
directly.

## Step 3 — Candidate gatherer (Python gathers; LLMs reason)

`tasks/gather_decision_candidates.py` — **read-only, deterministic, no LLM, no network.**

Scans `vault/theses/*_thesis.md` (excluding `.bak*`) and emits candidate sites where
reasoning exists that the schema cannot currently hold:

- YAML frontmatter **comments** containing a conjunction or condition
  (` and `, ` + `, `unless`, `only if`, `both`) — e.g. XOM's
  `# harvest if multiple + oil both rich`.
- Review Log entries containing directive phrasing (reuse `lint_theses` check 7's
  phrase list — import it, do not duplicate it).
- Frontmatter values whose comment records a revision (`raised from`, `lowered from`,
  `changed from`) — e.g. GOOG's `price_trim_above: 450.00 # raised from $395`.
- Any `trigger_type: ceiling_only` whose Review Log gives a *temporary* reason
  (`revisit`, `pending`, `until`) — e.g. AMZN.

Output JSON to stdout: `{file, line, ticker, category, quote, current_frontmatter_key}`.
This is the input the Cowork task reasons over. **It proposes nothing and writes
nothing.**

Expected non-empty on the live vault. If it returns zero candidates, it is broken —
XOM, GOOG and AMZN are known positives. Paste the literal run.

## Step 4 — Assertion card on the cockpit

New `ui/assertion_cards.py` (beside `ui/why_cards.py`, not inside it).

- Loads `data/decision_proposals/*.json` with `status == proposed`.
- Renders on `/` under **"Is this what we're saying? (N)"**, above the why-cards panel.
  Empty → render nothing at all.
- Each card shows: the `assertion` prose, the `conditions` legs in plain language, any
  `unencodable_conditions` called out explicitly as **not evaluated**, what it
  `overrides`, the `falsifier`, and `source_ref` as a link.
- **Signal-implicated rows first.** If the proposal's tickers appear in today's
  Crosshairs, sort those to the top and label them. Do not render all proposals as one
  flat queue — abandonment is this surface's failure mode.
- Three actions per card: **Confirm**, **Correct** (free-text, becomes the assertion),
  **Reject** (free-text reason).

`POST /decision/ratify` in `ui/app.py`:
- Write banner + `ui_runs` row before execution, same convention as the why routes.
  **No typed-id confirmation** — this is a card meant to be answered often.
- Confirm/Correct → `store.py` writes `vault/decisions/<id>.md` with
  `ratification=True`, `status: ratified`, `ratified_on: today`; proposal JSON updated
  to `ratified`.
- Reject → proposal updated to `rejected` with the reason. **Nothing enters `vault/`.**
- Set `last_ratified: <today>` in the frontmatter of each affected thesis via
  `ThesisManager`, archive-before-overwrite. **Do not touch `last_reviewed`.**
- Extend `UI_WRITE_ROUTE_ALLOWLIST` to exact set equality including
  `("POST", "/decision/ratify")`, and update the `CLAUDE.md` line asserting that set.

## Step 5 — Make check 5 able to fire

- Add `last_ratified` to the thesis frontmatter contract (documented in
  `PORTFOLIO_SHEET_SCHEMA.md` or the thesis schema section, wherever frontmatter is
  specified — do not create a new doc).
- Repoint `lint_theses.py` check 5 at `last_ratified`. Absent → report as
  "never ratified", which is the correct state for all 41 today.
- Leave `last_reviewed` alone and add a one-line comment where it is read stating that
  it records **last synced**, not last reviewed.
- Firing proof required: paste check 5 output showing all 41 as never-ratified, then
  ratify one proposal and paste it again showing 40.

## Step 6 — Documentation

`CHANGELOG.md`, `state.md`, and the `CLAUDE.md` launch-policy/allowlist lines only.
Archive before edit, prove pre-edit content by grep. **No new root-level markdown.**

---

## Verification checklist — literal stdout/stderr only

An agent-reported PASS table is not accepted.

1. Pre-change `pytest` summary line (Step 0) and post-change summary line, side by side.
   Name every failure that is not in your captured baseline.
2. `python tasks/gather_decision_candidates.py` — full output. Must include XOM, GOOG
   and AMZN. If any is missing, say which and why.
3. Ingest a fixture drop file **dry run**, paste output; then `--live`, paste output;
   then re-run `--live` and show the sha256 ledger **suppresses** it. Firing proof.
4. Feed a drop file containing one invalid record; paste the whole-file rejection.
5. Show `ingest_decision_proposals.py` cannot write `vault/` — paste the test.
6. Cockpit with zero proposals renders **no** panel; paste the rendered region.
7. Ratify one proposal live. Paste: the new `vault/decisions/<id>.md`, the thesis diff
   showing `last_ratified` added and `last_reviewed` **unchanged**, and the `ui_runs` row.
8. Reject one proposal. Paste the proposal JSON and prove `vault/decisions/` did not grow.
9. `lint_theses` check 5 before and after that ratification (41 → 40).
10. `git status --porcelain`.

---

## Do not

- Do not implement trigger derivation from decisions. Out of scope; step 4 of the doc.
- Do not let any path other than desk ratification write `vault/decisions/`.
- Do not let the Cowork drop file set its own `status` or `provenance`.
- Do not drop `unencodable_conditions` from the schema because nothing consumes it yet.
- Do not rename `last_reviewed` or change what writes it.
- Do not modify `tasks/build_crosshairs.py`, the why-card lane, `journal promote`,
  `Target_Allocation`, or any Schwab path.
- Do not add a typed-confirmation gate to `/decision/ratify`.
- Do not stamp any record `declared_before`. Precommit remains the only source.


---
---

# AMENDMENT A — 2026-09-01, before the first drop file

Found by running `gather_decision_candidates.py` (22 candidates, correct) and reviewing
the worked XOM example. **Both items below must land before any proposal is ingested
`--live`.** A fabricated field that reaches `vault/decisions/` via ratification is
permanent; these are cheap now and unfixable later.

## A1 — `decided_on` must be nullable. Most decisions in the vault are undated.

The schema requires `decided_on` and validates it as a real date. Measured against the
live gatherer output, only **1 of 4 candidate categories** carries a date:

| category | dated in source? |
|---|---|
| `review_log_directive` (GLD) | yes — `- 2026-08-14:` |
| `yaml_comment_conjunction` (XOM, META, GOOG) | **no** |
| `frontmatter_revision` (GOOG, UNH) | **no** |
| `ceiling_only_temporary` (AMZN, APO, LLY, MU) | Review Log dated, but the date belongs to the *trigger_type* change, not the rule |

The worked XOM example stamps `decided_on: 2026-08-09`, borrowed from a Review Log entry
about `trigger_type`. The harvest rule in the comment is undated. That is an invented
date presented as a recorded one — precisely what this architecture exists to prevent.

**Change:**
- `decided_on` accepts `null`.
- Add `decided_on_status: known | unknown` (required).
- Validator: if `decided_on_status == known`, `decided_on` must be a real non-future
  date; if `unknown`, `decided_on` must be `null`. Reject any record that sets a date
  while claiming `unknown`, or vice versa.
- The extractor may set `known` **only** when the date is literally adjacent to the
  quoted prose. Never borrow a date from elsewhere in the file.
- The assertion card prompts for the date when `unknown`. Bill is the authority on when
  he decided; ratification is where that gets supplied, not extraction.

## A2 — `assertion` is verbatim. Paraphrase gets its own field.

The design doc says *"Bill's words, verbatim where extracted."* The worked XOM example
reads `"Harvest only if multiple and oil are both rich — not on multiple alone."` Bill
wrote `harvest if multiple + oil both rich`. The rest is the model's inference — and it
is also **wrong on its own terms**: the encoded legs are price and fwd_pe, so the
clause should say "not on price alone." A paraphrase that misdescribes its own
conditions is worse than no paraphrase.

**Change:**
- `assertion` — verbatim source text only. Validator rejects a record whose `assertion`
  is not a substring of the file at `source_ref` (normalising whitespace). This is a
  hard, mechanical check; do not soften it to a similarity score.
- Add `proposed_restatement` — the model's plain-language reading, clearly labelled as
  model output in the card UI.
- On **Confirm**, `proposed_restatement` is discarded. On **Correct**, Bill's edited text
  is stored as `restatement` with `restatement_author: bill`. The model's words never
  become the record without him retyping them.

## A3 — gatherer precision (report only, do not fix yet)

`_CONJUNCTION_RE` matches a bare `+`, so reason-lists match as conjunctions —
e.g. XOM `style_size_ceiling_pct: 5.0 # cyclical + geopolitical + ESG/reg risk`,
and META L15/L19. Roughly 5–7 of 22 are noise. **Leave it.** A candidate generator
should over-produce; Cowork is the filter and Bill is the gate. Tightening the regex
now risks losing true positives before anyone has seen a month of output. Record this
in `state.md` as a known characteristic, not a bug.

## A4 — the `--file` override and repo fixture: yes

Add `--file <path>` to `ingest_decision_proposals.py` for local testing, and a fixture at
`data/fixtures/decision-proposals-sample.json`. Constraints: `--file` still runs the full
validator, still forces `status: proposed` / `provenance: extracted`, still writes the
sha256 ledger, and still cannot write `vault/`. It changes the source path only.

Do **not** use the design-doc GLD example as the smoke-test record — it was authored in
prose by hand and round-trips the model's own output, which tests nothing. Use the
fixture for path testing, and the real Cowork drop file for loop testing.

## Verification for this amendment

1. Record with `decided_on_status: known` and a null date — paste the rejection.
2. Record with `decided_on_status: unknown` and a date set — paste the rejection.
3. Record whose `assertion` is not a substring at `source_ref` — paste the rejection.
4. Record with a verbatim assertion — paste the acceptance, and the stored
   `proposed_restatement` alongside it.
5. Ratify with **Correct**; paste the resulting `vault/decisions/` file showing
   `restatement_author: bill` and no trace of `proposed_restatement`.
