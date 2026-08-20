# Build Prompt: Valuation Drift Monitor — Agent v1

**Author:** Claude (Chief Architect), 2026-08-20
**Executor:** Claude Code or Gemini CLI
**Prompt version:** 1.0.0
**Type:** New agent. Sell-side signal generation.

**Purpose:** track how the fundamentals of current holdings have moved relative to their thesis baseline. Thesis files are drift anchors; this agent is the instrument that reads the drift. It surfaces *what changed*, never *what to do*.

**Why this is the highest-value item of the three:** it is the only one that produces something Bill cannot currently see at all. The other two fix wrong or lost data; this creates new signal on the side of the book that is chronically under-instrumented — exits.

---

## Sequencing — read first, this one has a hash consequence

This agent requires FMP fundamentals in the **market bundle**. Adding fields to the bundle **changes `bundle_hash` and every downstream `composite_hash` by construction.**

That collides with the store migration's `bundle-parity` check, which diffs Sheets-sourced vs SQLite-sourced bundles expecting `MATCH`.

**Rule:** do not land the bundle schema change during the Phase 1 streak window. Either:
- land it **before** Phase 1 dual-write begins, so parity runs against the new schema throughout; or
- land it **after** Phase 2 cutover completes and parity has been resolved.

Two hash-lineage breaks at once is an unnecessary audit problem. Record the schema-change break in `CHANGELOG.md` with the last pre-change `composite_hash` either way.

---

## Scope boundary

**In scope:** extending `utils/fmp_client.py`, adding a fundamentals block to `core/bundle.py`, `utils/agents/valuation_drift.py`, `prompts/valuation_drift.md`, output to `agent_outputs/valuation_drift/`.

**Out of scope:** new vendors (hard rule — extend `utils/fmp_client.py`, nothing else), Alpha Spread, the store migration, any Sheets tab. v1 writes local markdown only, per the agent output convention for new agents.

**Alpha Spread decision:** skip the subscription. FMP already provides the DCF and relative-valuation data this agent needs. Revisit only if FMP proves insufficient against real output.

---

## Step 0 — Verification gate (paste RAW stdout under each)

- [ ] **What `fmp_client.py` already fetches**

```text
rg -n "def |endpoint|/api/v3|/stable" utils/fmp_client.py
```

- [ ] **Whether fundamentals already reach the bundle**

```text
rg -n "fmp|fundamental|pe_ratio|peg|forward" core/bundle.py core/composite_bundle.py
# Expected: absent or thin. If already present, STOP and report — the plan assumes greenfield.
```

- [ ] **Thesis frontmatter shape — what baseline fields exist today**

```text
ls vault/theses/ | head -5
python -c "from pathlib import Path; import itertools; [print(p.name, '---'); print(p.read_text(encoding='utf-8')[:1200]) for p in itertools.islice(Path('vault/theses').glob('*.md'), 2)]"
# Paste raw. Identify whether an entry-date valuation baseline exists anywhere.
```

- [ ] **Bundle hashing call site**

```text
rg -n "sha256|canonical|sort_keys|def .*hash" core/bundle.py
```

- [ ] **Composite schema enforcement**

```text
rg -n "bundle_hash|composite_hash|ask_gemini_composite" utils/gemini_client.py
```

If fundamentals already exist in the bundle, **STOP** and report before building.

---

## The baseline problem — resolve before building

Drift requires a baseline, and **the baseline probably does not exist in machine-readable form.** Thesis files are prose plus numeric regions; they were not written to capture forward P/E at entry.

Three options. Pick one and state it before writing code — do not silently assume:

| Option | Baseline | Cost | Honesty |
|---|---|---|---|
| **A. Snapshot-forward** | First run writes today's fundamentals as `baseline_YYYY-MM-DD` per position. Drift accrues from now. | Trivial | Truthful. Zero signal on day one; real signal in a quarter |
| **B. Reconstruct from entry date** | Pull historical fundamentals at first-purchase date from FMP | Moderate; FMP historical coverage varies by field | Genuine entry baseline where data exists; gaps must be marked `UNAVAILABLE`, never interpolated |
| **C. Manual backfill** | Bill states the baseline per position | High human cost across 35 positions | Most accurate, least likely to happen |

**Recommendation: A for v1.** It ships this week and starts accruing. Add B for the positions that matter later if the output proves useful. Do not build B first for all 35 — that is spec-before-output.

---

## Fields to track (v1 — keep it small)

| Field | Source |
|---|---|
| Forward P/E | FMP |
| Trailing P/E | FMP |
| PEG | FMP |
| EV/EBITDA | FMP |
| Price/Sales | FMP |
| Gross margin trend (last 4 quarters) | FMP |
| FCF trend (last 4 quarters) | FMP |
| Revenue growth (YoY) | FMP |
| Net debt / EBITDA | FMP |

Every field is nullable. `UNAVAILABLE` is a valid value and must render as such. **Never interpolate, estimate, or carry forward a stale figure as current.**

---

## Hard output constraints

`SAFETY_PREAMBLE` is auto-prepended by `ask_gemini()` — **do not duplicate it in `prompts/valuation_drift.md`.**

The agent output must contain **none of the following**:
- Price targets
- Market predictions
- Buy / sell / trim / add recommendations
- Analyst opinion or consensus ratings
- Fair-value estimates presented as conclusions

It **must** contain:
- The measured change, per field, baseline → current, with both dates
- The thesis file's stated expectation where one exists, quoted or referenced by section
- Where the two diverge, stated as a fact: *"multiple expanded 40% since baseline; thesis names re-rating as the return driver"*
- `bundle_hash` / `composite_hash` stamped in the output schema
- Explicit `UNAVAILABLE` markers

Bill decides. The agent measures.

---

## Output

`agent_outputs/valuation_drift/valuation_drift_{YYYY-MM-DD}_{hash_prefix}.md`

Local markdown, per the v1 convention for new agents. Promote to a Sheets tab only after the format has stabilised against real output.

CLI: `python manager.py agent valuation-drift [--ticker TICKER] [--bundle-path PATH] [--dry-run]`

---

## Post-build verification checklist (raw stdout required)

- [ ] `rg -n "import requests|http" utils/agents/valuation_drift.py` — **no matches.** Agents never fetch (hard rule 2). Python gathers, LLM reasons.
- [ ] `python manager.py refresh bundle --dry-run` — fundamentals block present, nulls rendered as `UNAVAILABLE`
- [ ] Bundle hash before vs after the schema change — both recorded in `CHANGELOG.md`
- [ ] `python manager.py agent valuation-drift --dry-run` — runs, output contains `composite_hash`
- [ ] `--ticker AVGO` — single-position output correct against a hand check of one field
- [ ] `rg -in "price target|we recommend|should sell|should buy|fair value is|our estimate" agent_outputs/valuation_drift/*.md` — **no matches**
- [ ] `rg -n "SAFETY_PREAMBLE" prompts/valuation_drift.md` — no matches (not duplicated)
- [ ] Baseline option chosen is stated in the output header, so a reader knows whether day-one drift is real or definitionally zero
- [ ] A position with missing FMP coverage renders `UNAVAILABLE`, not a fabricated number
- [ ] `git diff --stat` — no new vendor client added; `utils/fmp_client.py` extended
