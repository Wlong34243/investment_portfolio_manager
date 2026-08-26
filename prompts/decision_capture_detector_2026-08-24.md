# Decision Capture Detector — 2026-08-24

**Sequence: 2 of 3.** Requires `prompts/doctrine_layer_2026-08-24.md` to have completed
(this prompt reuses `utils/doctrine_reader.py`'s soft-fail parse pattern and the sixth
bundle slot). Do not start until Step 5 of that prompt is signed off.

## Why this exists

`pm journal rotation` already exists and takes six required flags
(`--sold --bought --proceeds --type --bet --thesis`). The most recent `Trade_Log` entry is
**2026-08-03**. The JPIE sell-down of 2026-08-21 → 08-24 is not in it, and JPIE went to a
zero position with no exit record — caught only because `manifest.json` preflight happened
to flag the orphaned thesis file.

The capture tool is not missing. It is too expensive to use at the moment the reasoning is
fresh, and cheap to skip. Meanwhile Bill reconstructs eight decisions' worth of rationale
in a single paragraph when asked directly — as he did on 2026-08-24.

**So the thing to automate is the detector, not the capture form.** The bundle already
diffs state; the JPIE preflight is proof the mechanism exists. Generalise it, surface the
gaps in the morning brief, and let Bill answer in prose.

**Non-goals.** No new CLI capture UI. No form. No natural-language parsing of Bill's
answers into structured fields — a human writes the files after he answers. No writes to
`Trade_Log`, `Trade_Log_Staging`, `Holdings_Current` or `Target_Allocation` from this
detector; it is read-only and reports.

---

## STEP 0 — Verification gate

- **a)** `tasks/export_ai_briefing.py` emits `preflight_issues` in `manifest.json`, and the
  2026-08-24 bundle contains exactly one entry:
  `"SKIPPED JPIE: thesis exists in vault/theses/ but the position is not held in this bundle. Archive it or confirm the exit."`
  Locate the code that produces it. **That is the seed** — this prompt generalises it.
- **b)** `exports/ai_briefing_*` directories are timestamped and sortable, and at least two
  exist with `portfolio.md` position tables (2026-08-21 and 2026-08-24 both do).
- **c)** `vault/theses/*_thesis.md` files carry a `## Review Log` section with dated
  bullets, and a `<!-- region:transaction_log -->` region. Confirm both on a sample of five.
- **d)** `manager.py` has a `journal` Typer group with `promote` and `rotation` commands.
  `journal rotation` writes to `config.TAB_TRADE_LOG` and requires `--live` to do so.
- **e)** `utils/doctrine_reader.py` exists (built by prompt 1 of 3).
- **f)** `config.TRADE_LOG_STAGING_COLUMNS` includes `Implicit_Bet` and `Thesis_Brief`.

If (a) does not resolve to a single identifiable code path, STOP — the generalisation
target is wrong and the design needs revisiting before code.

---

## STEP 1 — Define the three detectors (SIGN-OFF GATE)

Build `tasks/detect_undocumented_changes.py`. It compares the bundle being generated
against the most recent **prior** bundle and emits findings. Read-only.

| Code | Condition | Seed |
|---|---|---|
| `NEW_POSITION_NO_THESIS` | Ticker present now, absent in prior bundle, and no `vault/theses/<T>_thesis.md` on disk | new |
| `EXITED_POSITION_LIVE_THESIS` | Ticker absent now, present in prior bundle, thesis file still live | **generalise the existing JPIE preflight** |
| `MATERIAL_RESIZE_NO_REVIEW` | Weight moved past threshold, and the thesis `## Review Log` has no entry dated on/after the first day of the move | new |

**Threshold proposal for `MATERIAL_RESIZE_NO_REVIEW` — present at a gate and STOP:**

- Trigger when **both** `abs(Δ weight_pct) >= 0.50pp` **and** `abs(Δ relative) >= 25%`.
  Requiring both keeps a 0.6% position doubling from firing on 0.6pp, and keeps QQQM
  drifting 0.5pp on market moves alone from firing at 5% relative.
- Compare against the **prior bundle**, not a rolling window — a slow drift that never
  clears the bar in one day should not accumulate into a false finding.
- **Suppress when the move is explained by market action rather than a trade.** Cross-check
  the thesis `<!-- region:transaction_log -->` for a buy or sell dated inside the window. No
  transaction ⇒ the weight moved because price moved ⇒ not a decision ⇒ no finding. Getting
  this wrong makes the detector noise on every volatile day; it is the single most important
  filter in this prompt.

Ask Bill to confirm both thresholds and the market-move suppression before implementing.

---

## STEP 2 — Emit into the manifest

Add a `undocumented_changes` block to `manifest.json` (sibling of `preflight_issues`, not
merged into it — preflight is about export integrity, this is about decision records):

```json
"undocumented_changes": {
  "compared_against": "ai_briefing_2026-08-21_084524",
  "findings": [
    {"code": "EXITED_POSITION_LIVE_THESIS", "ticker": "JPIE",
     "detail": "Held 0.84% on 2026-08-21, absent 2026-08-24. Thesis live, scaling state '[INFERRED] reduce'.",
     "question": "Completed exit or a step in the reduce path that zeroed out?"}
  ]
}
```

Keep the existing JPIE `preflight_issues` entry as-is — it serves the export-integrity
purpose. Duplication between the two blocks is acceptable and preferable to changing
preflight semantics.

Each finding carries a **`question`** field: one plain-language question Bill can answer in
prose. Write questions that cannot be answered from the data — if the bundle already knows
the answer, it is not a finding.

---

## STEP 3 — Surface in the morning brief

Add a short section to `PROMPT_PAYLOAD` in `tasks/export_ai_briefing.py` instructing the
reasoning model to render `undocumented_changes` as a **question block**, and to render
nothing when the list is empty.

Rules for that instruction text:

- Each finding gets **one line**: ticker, what changed, the question. No prose around it.
- **Do not speculate about the answer.** Naming a likely rationale invites confirmation
  rather than recall, and the governing principle in `CLAUDE.md` applies directly: the
  files lag Bill's decisions and are not evidence against them. A finding is a documentation
  gap, never a discipline observation.
- Empty list renders as nothing at all — not "no findings today". A recurring empty section
  trains the eye to skip the region where the real ones will appear.
- Cap at **five** findings, ranked newest-change-first. More than five means the detector is
  miscalibrated; say so as a single SYSTEM line instead of listing them.

---

## STEP 4 — Close the loop back to the files

The detector reports. A human writes. Document the path explicitly in the prompt payload so
the answer does not evaporate a second time:

| Answer type | Destination |
|---|---|
| Why a position was entered/exited/resized | `<T>_thesis.md` `## Review Log`, dated, Bill's words |
| A sell funding a buy | `pm journal rotation --bet "<Bill's words>"`, DRY RUN then `--live` |
| A standing constraint | `vault/doctrine.md` (prompt 1 of 3) — **not** a thesis file |

The third row is the one that keeps getting mis-filed. Route-to-doctrine when the statement
governs future decisions generally rather than one position.

---

## Verification checklist

**Literal stdout for every item.**

1. Run the detector against the 2026-08-24 bundle with 2026-08-21 as prior — paste full
   JSON output. **Must produce exactly one `EXITED_POSITION_LIVE_THESIS` finding for JPIE.**
2. Same run — confirm **zero** `MATERIAL_RESIZE_NO_REVIEW` findings for VST, VRT, META,
   AVGO and MU. All five moved materially on price in that window with no trades; if any
   fires, the market-move suppression in Step 1 is broken. Paste the suppression decision
   for each.
3. Synthetic test: fabricate a prior bundle where QQQM is 8.00% and current is 10.50% with
   **no** transaction-log entry in the window — must **not** fire. Paste output.
4. Same synthetic, but **with** a transaction-log entry — **must** fire. Paste output.
5. Synthetic new position with no thesis file — must fire `NEW_POSITION_NO_THESIS`.
6. Run with the prior bundle deleted/unavailable — must degrade to an empty
   `undocumented_changes` block with a warning, not raise. Paste output.
7. Full `python manager.py morning --dry-run` — paste `manifest.json` showing both
   `preflight_issues` and `undocumented_changes` present and independent.
8. Confirm zero writes to `Trade_Log`, `Trade_Log_Staging`, `Holdings_Current`,
   `Target_Allocation`, `0_DASHBOARD` — paste the write log.

## Update on completion

`state.md`, `CLAUDE.md` (Morning pipeline table — new task file), `CHANGELOG.md`.
