# Why-Cards — decision capture at the desk — 2026-09-01

**Handoff target:** Claude Code or Gemini CLI.
**Premise (standing, 2026-09-01):** innovate and automate; correction and discipline
come from scrutinising real signals in use. Ship the minimum loop. The classifier stays
deliberately dumb until Bill has answered real cards.

---

## Why this exists

Bill's original intent for this system was a tool that *follows along and asks
"why did you do this?"*. What exists instead is: passive triggers that fire
mechanically, a precommit journal that only works when he declares ahead, and
reconstruction after the fact.

**Most of the asking machinery is already built and wired to nothing.**

`tasks/detect_undocumented_changes.py` runs inside every `export_ai_briefing`
(line ~1463), diffs today's holdings against the prior briefing, and emits findings
that **already carry a written question**:

```python
"question": f"What was the decision behind resizing {t} "
            f"({prior_w:.2f}% -> {cur_w:.2f}%)?"
```

Findings land in `manifest.json` under `undocumented_changes.findings`.
**No page in `ui/` reads that key.** The detector has been asking into a void.

Separately, `core/journal/reconcile.load_unreconciled_clusters()` already finds
`Trade_Log` / `Trade_Log_Staging` rows with blank `Implicit_Bet`. Also surfaced nowhere.

---

## The two lanes — do not merge them

These have different sources, different answer surfaces, and different suppression
behaviour. Building one card for both is the mistake this section exists to prevent.

| | **Lane A — Position card** | **Lane B — Rotation card** |
|---|---|---|
| Source | `manifest.json` → `undocumented_changes.findings` | `core/journal/reconcile.load_unreconciled_clusters()` |
| Unit | one ticker, one briefing-to-briefing window | one rotation cluster (sell/buy basket) |
| Question | already written by the detector; use it verbatim | "what was the substitution thesis for this basket?" |
| Answer lands | **thesis file Review Log** | **`Trade_Log.Implicit_Bet` / `Thesis_Brief`** |
| Self-suppresses? | **Yes, by design — but broken today.** `MATERIAL_RESIZE_NO_REVIEW` is suppressed once a Review Log entry exists on/after the move (`_review_log_dates`, line ~278). The parser currently over-suppresses in 39/41 theses — **Step 0.5 must land first.** | Yes — blank-bet filter stops matching once written. |
| Provenance stamp | n/a (thesis is a living document) | `Rationale_Provenance = reconstructed_after` |

Lane A answered into `Trade_Log` would leave the finding firing forever, because the
detector's own suppression reads the thesis, not the log. That is not a preference —
it is already encoded in the detector.

**Authorised 2026-09-01:** Lane B writes `Trade_Log` **directly**. No staging hop, no
promotion ceremony. See the launch-policy amendment in Step 5.

**Provenance is not negotiable.** A card answered after the fill is
`reconstructed_after`, the same grade as a reconstruction. Only `core/journal/precommit`
produces `declared_before`. Do not upgrade a card answer, do not add a new provenance
value, do not let a same-day answer claim a higher grade. Judgment Engine Unit C
calibration depends on this staying honest.

---

## Step 0 — Verification gate

Report literal findings. **If any item differs, STOP and report.**

1. Newest `exports/ai_briefing_*/manifest.json` contains key `undocumented_changes`
   with subkeys `compared_against` and `findings`. Print the newest one in full.
   **`findings: []` is NOT a clean baseline.** See Step 0.5 — the resize detector is
   currently unreachable. Do not treat an empty list as evidence the detector works.
2. Print the full finding dict schema emitted by `detect_undocumented_changes` for each
   of `NEW_POSITION_NO_THESIS`, `EXITED_POSITION_LIVE_THESIS`, `MATERIAL_RESIZE_NO_REVIEW`.
   Confirm every one carries `code`, `ticker`, `detail`, `question`.
3. `core/journal/reconcile.load_unreconciled_clusters()` imports and runs read-only.
   Print `len()` and one sanitised cluster.
4. Print `UI_WRITE_ROUTE_ALLOWLIST` from `ui/app.py` — expected **exact set equality**
   with `{("POST", "/ask"), ("POST", "/run/{routine_id}")}`.
5. Print the `Trade_Log` header row. Confirm `Implicit_Bet`, `Thesis_Brief`,
   `Proposed_Bet`, `Rationale_Provenance`, `Rationale_Evidence`, `Trade_Log_ID`,
   `Fingerprint` all exist and report their column letters.
6. Confirm `ThesisManager` (`utils/thesis_utils.py`) can append to a thesis Review Log
   section without disturbing frontmatter or `<!-- region:* -->` markers. If it cannot,
   **stop** — Lane A needs that capability before it can be written.

---

## Step 0.5 — BLOCKING: repair `_review_log_dates` before building anything

**Do not build Lane A until this is fixed and proven. Verified 2026-09-01.**

`_review_log_dates()` locates `## Review Log` and reads to the next markdown H2:

```python
nxt = re.search(r"\n## ", chunk)
if nxt:
    chunk = chunk[: nxt.start()]
```

In **39 of 41 live theses, `## Review Log` is the last H2 in the file.** There is no
next H2, so `chunk` runs to EOF and swallows the `<!-- region:transaction_log -->`
block that follows it. Those bullets are shaped `- 2026-08-21: Buy 1.0 @ $420.56`,
which `_REVIEW_DATE_RE` (`^\s*-\s*(\d{4}-\d{2}-\d{2})\b`) matches exactly.

Measured across the live vault: **506 parsed "review dates", of which 411 are
transactions.** GLD alone returns 9, of which 6 are fills.

**The consequence is total, not partial.** In `MATERIAL_RESIZE_NO_REVIEW`:

```python
txns = _txn_dates_in_window(text, window_start, window_end)   # reads region:transaction_log
if not txns:            -> suppress_market_move ; continue
review_dates = _review_log_dates(text)                        # ALSO reads region:transaction_log
first_move   = min(txns)
has_review   = any(d >= first_move for d in review_dates)     # min(txns) is IN review_dates
if has_review:          -> suppress_reviewed ; continue
```

`first_move` is by construction a member of `review_dates`, so `has_review` is
**unconditionally True**. No transaction in window → suppressed as a market move.
Transaction in window → suppressed as reviewed. **`MATERIAL_RESIZE_NO_REVIEW` is
unreachable in both branches**, and has been since the transaction_log region was
introduced.

Resizes are the dominant shape of Bill's activity — risk management here is
small-step scaling in and out, not binary entries and exits. The detector is blind
on exactly the behaviour it was built to question. This is the root cause of the
"nothing ever asks me why" gap, not a missing UI.

### The fix

Bound the chunk at the **first `<!-- region:` marker as well as** the next H2 —
whichever comes first. Region markers are the machine-readable boundary; an H2 alone
is not sufficient and never was.

Do **not** "fix" this by reordering thesis files, moving `## Review Log`, or adding a
trailing H2 to 39 files. The parser is wrong; the files are fine.

### Proof required before proceeding (literal stdout)

1. Per-thesis table: parsed review-date count before and after, all 41 rows.
   Expect total 506 → 95.
2. Re-run `detect_for_export` against the two most recent briefing pairs and paste
   the findings list before and after the fix.
3. A unit test in `tests/test_detect_undocumented_changes.py` (new file) with a
   fixture thesis whose `## Review Log` is the final H2 and is followed by a
   transaction_log region — asserting the transaction dates are **not** returned.
4. State plainly whether `MATERIAL_RESIZE_NO_REVIEW` fires for any real ticker after
   the fix. If it still fires for none, **stop and report** — the suppression has a
   second cause and Lane A is still pointed at a dead source.

### Then re-baseline

`undocumented_changes.findings` in the newest manifest must be regenerated after the
fix. Prompt 2's Step 0 item 1 and every "empty panel" verification below refer to the
**post-fix** baseline, not to the 2026-09-01 `[]`.

---

## Step 1 — Lane A: position cards on the cockpit

- New assembly module `ui/why_cards.py`. Read the newest manifest's
  `undocumented_changes.findings`. Disk read only — no Sheets, no network, no recompute.
- Render on `/` beneath Crosshairs as **"Open questions (N)"**. Empty list → render
  nothing at all, not an empty panel.
- One card per finding: ticker (linking to `/position/{ticker}`), the `code` as a
  labelled chip, `detail` as body text, `question` as the prompt verbatim, and a
  free-text answer box.
- `POST /why/position` writes an appended Review Log entry to
  `vault/theses/{ticker}_thesis.md` via `ThesisManager`, dated today, with Bill's text
  verbatim. Archive-before-overwrite. Never rewrite an existing entry.
- Bump `last_reviewed` in frontmatter to today on successful write.

---

## Step 2 — Lane B: rotation cards

- Same module. Source: `load_unreconciled_clusters()`.
- Render on `/judgment/rotations` (not the cockpit — this is a backlog, not a daily prompt).
- `POST /why/rotation` writes `Implicit_Bet` (and `Thesis_Brief` when supplied) onto the
  matched `Trade_Log` row, plus `Rationale_Provenance = reconstructed_after` and
  `Rationale_Evidence = "desk why-card <ISO timestamp>"`.
- Match on `Trade_Log_ID`; verify `Fingerprint` still matches before writing.
  **If the fingerprint has moved, refuse the write and surface the mismatch** — do not
  write to a row that changed under you.
- Single-batch gspread write with fingerprint dedup (Hard Rule 6). Never cell-by-cell.
- Post-write read-back verification before reporting success to the browser.

---

## Step 3 — Write banner + `ui_runs` row

Both routes are UI writes. Apply the existing desk convention: **write banner shown
before submission, `ui_runs` row written before execution.**

**No typed-id confirmation on either route.** Typed confirmation is reserved for
clear-and-rebuild routines. A card Bill is meant to answer daily must cost one keystroke
or he will stop answering it, and the loop dies. This is a deliberate departure —
record it in the amendment.

---

## Step 4 — SIGN-OFF GATE (stop and present; write nothing)

Before enabling live writes, run both lanes in dry-run and present:

- every Lane A finding that would render, with its question text as Bill will read it
- every Lane B cluster that would render, with the row it would write to
- the exact diff each would produce on one worked example per lane

Bill accepts / overrides / rejects **per lane**. Do not flip `--live` on either lane
before its own sign-off.

---

## Step 5 — Documentation (after the code lands, not before)

Amend `CLAUDE.md` **Desk UI launch policy** — extend, do not restructure the table.
Back up first; prove pre-edit content by grep (Hard Rule 7); summarise the diff.

Add to the "UI may launch" column, with this rationale recorded inline:

> **Bill's own authored rationale on an already-executed fill** — `POST /why/position`
> (thesis Review Log) and `POST /why/rotation` (`Trade_Log.Implicit_Bet` /
> `Thesis_Brief` / rationale columns), written **directly, no staging hop**
> (authorised 2026-09-01).
>
> This is an exception to "promotion to authoritative surfaces stays CLI-only", and it
> is judged against the governing sentence rather than against registry precedent: the
> policy already permits *"Bill's own authored input"*, and a rationale string is
> authored input. It creates no trade row, alters no financial fact, and is
> broker-derived in no part. `journal promote`, Schwab sync and the morning pipeline
> stay CLI-only and are unaffected.

Also extend `UI_WRITE_ROUTE_ALLOWLIST` to exact set equality with:
`{("POST", "/ask"), ("POST", "/run/{routine_id}"), ("POST", "/why/position"), ("POST", "/why/rotation")}`
— and update the CLAUDE.md line that asserts the old set, or the doc lies.

Update `state.md` and `CHANGELOG.md`. Create no new root markdown.

---

## Post-build verification checklist

**Literal stdout/stderr only. An agent-reported "PASS" table is not accepted.**

1. Step 0.5 proof items 1–4, in full.
2. Cockpit with zero findings renders **no** panel. Paste the rendered HTML region.
   (Zero findings must be a *post-fix* zero, not the pre-fix artefact.)
2. Force one finding of each Lane A code (fixture manifest is fine). Paste the rendered
   card text and confirm `question` appears **verbatim** from the detector.
3. Answer one Lane A card live. Paste: the thesis file diff, and a re-run of
   `detect_undocumented_changes` showing that finding **now suppressed**. This is the
   proof the loop closes.
4. Answer one Lane B card live. Paste the `Trade_Log` row before and after, showing
   `Rationale_Provenance = reconstructed_after`.
5. Attempt a Lane B write against a deliberately mismatched fingerprint. Paste the refusal.
6. Paste the `ui_runs` rows written by both.
7. `git status --porcelain` and `pytest` summary line, both pasted.

---

## Do not

- Do not build Lane A before Step 0.5 lands and is proven.
- Do not repair `_review_log_dates` by editing thesis files.
- Do not merge the two lanes into one card.
- Do not write Lane A answers into `Trade_Log`.
- Do not create `Trade_Log` rows from a holdings-weight diff. A finding is a weight
  observation, not a trade. Rows come from broker transactions via `derive_rotations`.
- Do not stamp any card answer `declared_before`.
- Do not add a typed-confirmation gate to either route.
- Do not clear-and-rebuild `Precommitments` or touch `journal promote`.
- Do not classify or route Bill's answer to doctrine automatically. Doctrine is
  manual-only. A "make this a standing rule" promotion path is a **later** prompt,
  after Bill has answered real cards and we can see what the answers look like.
