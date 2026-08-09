# Build: Typed Trim/Add Triggers

**Repo:** `C:\Dev\Investment_Portfolio` (authoritative).

**Problem.** 27 of 39 positions have no trim or add level. The pipeline can only express one
kind of trigger — a price — and a single price band is the wrong instrument for a book
containing GARP compounders, thematic single names, ETFs, and deep cyclicals.

**Goal.** Introduce a `trigger_type` concept end-to-end, then assign a type and band per
position. **Plumbing first, classification second.** Do not classify 39 positions against a
schema that has not been proven to survive the bundle.

Standing conventions: archive-before-overwrite; dry run → verify → `--live`; never write
`Target_Allocation`; no price targets, forecasts or buy/sell language in any output.

---

## Why not analyst price targets (settled, do not revisit)

Consensus price targets **ratchet** — analysts revise up after price rises, so a trim pegged to
consensus rises with the stock and structurally cannot fire. `VST_thesis.md` is the live proof:
`price_trim_above: consensus_price_target`, and the level has never been actionable. The median
target also sits ~10–15% above spot at all times, making it closer to a constant than a signal.
**Do not build any trigger that reads a sell-side price target.**

## Why not one metric for everything (settled)

Forward P/E and PEG both fail in the same direction on cyclicals, which are a large part of this
book. MU's forward P/E is ~6 with 300%+ revenue growth, giving a PEG near zero — both metrics
scream cheap at what `MU_thesis.md` itself calls *"a peak-cycle artifact of scarcity, not a
structural moat."* A trigger that contradicts its own thesis file is worse than no trigger.

---

## Step 0 — Verification gate

Report PASS/FAIL with literal output. Stop on any discrepancy.

| # | Assertion |
|---|---|
| 0.1 | `utils/level_coverage.py` checks **only** `price_trim_above` / `price_add_below` (~lines 60–63), so any non-price trigger is currently reported as a missing level. |
| 0.2 | `core/vault_bundle.py` defines `triggers` as a fixed two-key dict `{"price_trim_above": None, "price_add_below": None}` (~lines 56, 117), and carries **two** parsing strategies — a fenced ```yaml block and nested frontmatter. Confirm which strategy each live thesis file actually hits, and report the split. |
| 0.3 | `tasks/export_ai_briefing.py` (~line 872) documents that its flat per-line frontmatter parser cannot see keys nested under `triggers:`. Confirm still true. |
| 0.4 | `tasks/build_command_center.py` writes to `config.TAB_DASHBOARD` (`0_DASHBOARD`) via **clear-and-rebuild in a single batch_update**, and sources `Trim`/`Add` from the **Valuation_Card** tab, not from thesis files directly. Report the full chain: thesis → ? → Valuation_Card → 0_DASHBOARD. |
| 0.5 | Current trigger coverage. Expect: both price levels on GILD, GLD, GOOG, JPIE, UNH, XOM; trim-only on AVGO, COF, ET, META, NVDA; `fwd_pe` bands on GILD, GOOG, META, UNH, VRT, XOM; VST's trim is the non-numeric string `consensus_price_target`. Report actual. |
| 0.6 | Composite bundle hashing includes the vault bundle, so a `triggers` schema change alters composite hashes going forward. Confirm, and confirm nothing pins a historical hash that would break. |

---

## Step 1 — Schema and parser (plumbing only, no classification)

1. Define the trigger types. Start with exactly these five; do not invent more:

   | `trigger_type` | Band fields | Distance semantics |
   |---|---|---|
   | `price` | `price_trim_above`, `price_add_below` | % from spot to level |
   | `fwd_pe` | `fwd_pe_trim_above`, `fwd_pe_add_below` | % from current forward P/E to band edge |
   | `discount_from_high` | `trim_below_discount_pct`, `add_above_discount_pct` | percentage points from current discount-off-52w-high |
   | `price_to_book` | `pb_trim_above`, `pb_add_below` | % from current P/B to band edge |
   | `ceiling_only` | none | no valuation trigger; the style ceiling governs |

2. **Backwards compatibility is mandatory.** A file with `price_trim_above` and no
   `trigger_type` must behave exactly as today, inferred as `price`. Prove this — the six
   currently-covered positions must produce byte-identical Command Center output before and
   after this step.

3. Extend `core/vault_bundle.py` to carry the full `triggers` dict rather than a fixed two-key
   shape. Preserve both parsing strategies. **Report the parse-strategy split from 0.2** — if
   files are split across two formats, that is a latent hazard and should be recorded in
   `state.md`, not silently normalized in this build.

4. Extend `utils/level_coverage.py` to count a position as covered when it has a **complete band
   for its declared type**, or is `ceiling_only`. Report coverage by type, not just a total.

5. Do **not** touch classification, Command Center, or the dashboard in this step. Stop and
   report. The schema must round-trip through the bundle before anything depends on it.

---

## Step 2 — Propose a type per position (analysis, no writes)

Produce a table for Bill's sign-off. **Propose; do not assign.**

For each of the 39 positions: ticker, style, current weight, proposed `trigger_type`, and a
one-line reason. Suggested logic, to be argued with rather than applied mechanically:

- **ETFs** (QQQM, VTI, VEA, XBI, XLF, IFRA, COWZ, EMXC, BBJP, EWZ, GLD, JEPI, JPIE) →
  `ceiling_only`. A multiple band on a fund is weak or meaningless. **Exception:** JPIE already
  has working price levels tied to a historical NAV range — leave it `price`.
- **GARP** → `fwd_pe`, banded against the name's own history.
- **THEME** → `ceiling_only` in most cases. These are position-size bets, not valuation bets,
  and the ceiling already governs. Where a THEME name has a genuine valuation anchor, argue for it.
- **FUND** (Boring Fundamentals, bought on fear-driven discounts) → `discount_from_high`.
  The thesis is about price dislocation, so the trigger should be too.
- **Cyclicals** → `price_to_book`, **not** a multiple band.

**Cyclicality cuts across the four styles and is not captured by them.** Flag every position
where the cyclical read overrides the style default, and say so explicitly. Candidates to
examine at minimum: MU, SKHY, COF, VST, XOM, RRC, EWZ. This tension is itself a finding —
record it in `state.md` whether or not the taxonomy changes.

Do not compute bands yet.

---

## Step 3 — Compute bands (after sign-off on types)

For each position with a numeric type, derive the band from **its own history**, never from a
peer group or an analyst estimate:

- Pull the trailing 3–5 year distribution of the relevant metric.
- Propose band edges at roughly the 25th / 75th percentile, and **show the full distribution**
  (min, p25, median, p75, max, current) so Bill can see what the band is made of.
- State the observation count and window. A band computed from 18 months is not the same claim
  as one from five years — label it.
- Where history is too short to be meaningful (MU, RRC, PWR, SKHY are likely cases), say so and
  propose `ceiling_only` instead of a thin band. **Do not manufacture a band from insufficient data.**

Output a proposal table. **Bill accepts, overrides or rejects per row.** Nothing is written to a
thesis file without that.

---

## Step 4 — Write to thesis files (only what Bill approved)

- Archive-before-overwrite, `.bak` per file, proven by grep to hold pre-edit content.
- Write `trigger_type` and the band fields into the `triggers:` block.
- Add a one-line Review Log entry per file recording the band, its source window, and that it
  was derived from the position's own history.
- Leave every existing `[BILL]` placeholder untouched.
- **`VST`: replace `consensus_price_target` with a real type.** It is the one position whose
  trigger is currently unusable by construction.

---

## Step 5 — Surface it

1. **Valuation_Card / Command Center chain.** Per 0.4, `build_command_center.py` reads
   `Trim`/`Add` from `Valuation_Card`. Whatever populates that tab must learn the new types.
   Make the distance calculation **generic — "% to trigger"** — so the existing `→Trim %` /
   `→Add %` columns work regardless of the underlying metric. Add a `Trigger_Type` column so a
   reader can tell what a given percentage is measuring; a `→Trim %` that silently means "P/E
   distance" on one row and "price distance" on the next is a trap.

2. **`0_DASHBOARD` is the Command Center tab.** It is rebuilt clear-and-rebuild in a single
   `batch_update` by `build_command_center.py`. **Anything added must be built into that grid
   construction** — content written to the tab by any other path is erased on the next
   `pm morning`. This also applies to the rotation-attribution block specced in
   `prompts/commit_recover_dashboard_2026-08-09.md`; if that block was added separately, fix it
   here and say so.

3. **Export bundle.** `tasks/export_ai_briefing.py` must surface the typed triggers in the
   briefing. Note the parser limitation from 0.3 — if the flat per-line parser still cannot see
   nested keys, fix that rather than working around it.

---

## Step 6 — Verification

Literal output for each.

- [ ] Step 0 table, including the parse-strategy split and the full Valuation_Card chain.
- [ ] **Backwards-compat proof:** Command Center output for the six currently-covered positions
      byte-identical before and after Step 1. Paste the diff (expected: empty).
- [ ] Coverage-by-type report from the extended `level_coverage.py`.
- [ ] Type-proposal table, and Bill's sign-off recorded before Step 3.
- [ ] Band-proposal table showing full distributions and observation counts.
- [ ] Positions where insufficient history forced `ceiling_only` — listed, with the reason.
- [ ] `.bak` per edited thesis, proven pre-edit by grep.
- [ ] `pm morning` dry run completes; `0_DASHBOARD` renders with `Trigger_Type` visible.
- [ ] Composite hash before/after, with a note that the change is expected and why.
- [ ] `state.md` and `CHANGELOG.md` updated, including the cyclicality-vs-style-taxonomy finding.

## Out of scope

- No sell-side price targets, in any form.
- Do not change `data/styles.json` or the four-style taxonomy. Record the cyclicality tension;
  do not resolve it here.
- Do not assign a type or band without Bill's sign-off.
- Do not manufacture a band from insufficient history.
- Do not resolve any `[BILL]` placeholder.
