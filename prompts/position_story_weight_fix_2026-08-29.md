# Position Story weight/headroom fix + BTC thesis correction

**Created:** 2026-08-29
**Executor:** Cursor (Agent mode).
**Depends on:** Desk Cockpit / Judgment build (1529d6d, f8a36b2); audit 2026-08-29.
**Scope:** (A) fix weight + headroom on `/position/{ticker}`; (B) update `vault/theses/BTC_thesis.md`
with Bill's stated thesis and documented pre-2026 history. No new surfaces.

> **Audit finding (2026-08-29).** `/positions` normalizes retrieval weight to percentage points;
> `ui/position_story.py` does not. UNH shows **Weight: +0.0%** and **~+5.0% headroom** when
> real values are **~3.6%** and **~+0.4%**. Template-only fix is insufficient — headroom math
> uses the same unconverted fraction.

---

## Step 0 — Verification gate

Paste literal stdout. Any disagreement ⇒ **STOP and report**.

```powershell
# 0.1 — position_story uses raw weight; positions_page normalizes
rg -n "weight|headroom|weight_to_pct" ui/position_story.py ui/positions_page.py ui/templates/position_story.html

# 0.2 — filter contract
rg -n "def fmt_pct|def fmt_pct_points|def weight_to_pct" ui/format.py

# 0.3 — live mismatch (desk up): UNH on both pages
# Expected TODAY (pre-fix): /positions ~3.6% wt; /position/UNH ~0.0% wt, ~+5% headroom
curl.exe -s http://127.0.0.1:8765/position/UNH | findstr /i "Weight headroom"
curl.exe -s http://127.0.0.1:8765/positions | findstr /i "UNH"

# 0.4 — BTC transaction history (audit: 2026-02-06 sell exists)
# Expected: sell row in Transactions for BTC; thesis file omits it today
rg -n "2026-02|February|first-time|re-entry" vault/theses/BTC_thesis.md
```

---

## Part A — Weight + headroom fix

### Root cause

| Layer | Behavior |
|---|---|
| `core/retrieval` `holdings_current` | `weight` as stored — fraction (~`0.036`) |
| `ui/positions_page.py:52–54` | If `wt <= 1.0`, multiply by 100 → points |
| `ui/position_story.py:245–246` | Raw fraction; `headroom = ceiling - weight` → wrong by ~100× |
| `position_story.html:8–11` | `pct_pts` on fraction → **+0.0%** display |

Ceiling from thesis/styles.json is already in **points** (e.g. UNH `4.0`). Weight must match.

### Fix (do not deviate)

**1. Add shared helper** — `ui/format.py`:

```python
def weight_to_pct_points(wt: Any) -> Optional[float]:
    """Store/retrieval weight → percentage points (3.6 not 0.036). Same heuristic as positions_page."""
    v = _f(wt)
    if v is None:
        return None
    if v < 1.5:
        return v * 100.0 if v <= 1.0 else v
    return v
```

**2. `ui/position_story.py`** — after reading holdings row:

```python
from ui.format import weight_to_pct_points

weight = weight_to_pct_points(_safe_float(holdings_row.get("weight")))
headroom = (ceiling - weight) if ceiling is not None and weight is not None else None
```

**3. `ui/positions_page.py`** — replace inline `if wt < 1.5:` block with `weight_to_pct_points()`.

**4. Template** — keep `weight|pct_pts`, `headroom|pct_pts`, `ceiling|pct_pts` (all points after Python fix). No template change required if normalization is correct.

### Tests (required)

New `tests/test_position_story_weight.py`:

| Case | Input weight | Ceiling | Expected headroom |
|---|---|---|---|
| UNH-like | `0.035975` | `4.0` | ~`0.4` (points) |
| Already points | `3.6` | `4.0` | `0.4` |
| None ceiling (ballast) | `0.008` | suppressed | no headroom in ctx |

Test `weight_to_pct_points` directly and/or `assemble_position_story` context with mocked retrieval tables.

Optional render smoke: `/position/UNH` must not contain `Weight: +0.0%` when weight > 0.

Refactor guard: `positions_page` and `position_story` must import the **same** helper — no duplicated heuristic.

### Part A verification — paste stdout

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_position_story_weight.py tests/test_ui_position_ballast.py tests/test_ui_position_route.py -q
# Browser: /position/UNH — Weight ~3.6%, headroom ~+0.4% (parity with /positions row)
# /position/JEPI — no ceiling/headroom block (ballast)
```

**Stop after Part A green before Part B thesis edits.**

---

## Part B — BTC thesis update (Bill-authored content)

### Problem

Two gaps in `vault/theses/BTC_thesis.md`:

1. **History:** Position Story surfaced **2026-02-06 Sell, −10 shares @ $30.60** (live Transactions).
   Current lot = 30 shares bought Aug 2026 → arithmetic implies a **prior position fully exited
   in February**, then **re-entry ~6.5 months later** — not a first-time exposure. Neither the
   2026-08-27 scaffold nor the 2026-08-28 Motley Fool redraft mentions this.

2. **Thesis voice:** Bill supplied his own investment thesis (2026-08-29) — a **store-of-value /
   digital monetary commodity** framing. That **supersedes** the file's current "regulatory
   event optionality from Motley Fool source" draft in `## Core Thesis` and related sections.
   Bill's words replace the drafted-from-source prose; verification table and Motley Fool
   research inputs may move to an archive subsection or Review Log — do not delete audit trail.

### Sign-off gate (mandatory — do not write until Bill accepts)

Before editing `BTC_thesis.md`, present this proposal table in chat and **wait for accept/override**:

| Section | Action |
|---|---|
| `## Core Thesis` + bull/bear/invalidate | **Replace** with Bill's thesis (Appendix A below) — his voice, not paraphrased shorter |
| `## Known Facts` | **Add** Feb 2026 exit + Aug 2026 re-entry from Transactions; fix "first appears bundle" narrative |
| `## Review Log` | **Append** 2026-08-29 entry: history correction + thesis voice change |
| Motley Fool / Clarity Act sections | **Archive** under `## Research Inputs (superseded 2026-08-29)` — keep verification table |
| Frontmatter `[BILL]` fields | **Unchanged** unless Bill overrides in sign-off (style, ceiling, levels still open) |
| `trigger_type: price` | **Keep** — still correct for non-earnings proxy |
| `framework_preference: macro_hedge_v1` | **Keep** unless Bill assigns style in sign-off |
| `<!-- region:transaction_log -->` | **Populate** on next sync or manual one-liner noting Feb sell + Aug buy |

### History facts to record (verified sources)

- **2026-02-06:** Sell, −10 shares, $30.60 (Transactions tab / Position Story — verify literal before write).
- **2026-08-25/26 window:** Buy 30 shares @ ~$34.995 → current lot (bundle + thesis Known Facts).
- **Narrative:** Re-entry after full exit, not inaugural exposure. Do not invent why Bill sold in February.

### Appendix A — Bill's thesis (paste verbatim into Core Thesis block after sign-off)

Bill supplied the following on 2026-08-29. Use as the authoritative `## Core Thesis` body and
supporting sections (`## The bull case` through `## Practical conclusion`). Preserve markdown
structure and external links. Do **not** add price targets, buy/sell recommendations, or
allocation advice beyond what Bill wrote.

---

## BTC thesis

**Bitcoin is a high-volatility, non-yielding monetary asset whose long-run upside depends on broader adoption as a globally liquid, credibly scarce store of value—while its downside depends on that adoption stalling, regulation becoming hostile, or demand proving mainly speculative.**

The investable version is not "BTC replaces all money." It is: **a relatively small but growing share of global savings, collateral, and reserve assets may seek exposure to an asset with a fixed issuance schedule, portable self-custody, and no central issuer.** Bitcoin's original design was peer-to-peer electronic cash, but the strongest contemporary investment case is closer to "digital monetary commodity" or "digital gold." [bitcoin](https://bitcoin.org/bitcoin.pdf)

## The bull case

1. **Credible scarcity**
   - Bitcoin's protocol targets a maximum supply of 21 million BTC and reduces issuance over time through halvings.
   - Unlike fiat currencies, bank deposits, or most financial assets, issuance is not governed by a central bank, corporation, or commodity producer responding to price.
   - The key distinction is not merely that supply is limited; it is that the rules are broadly visible, rule-based, and expensive for the network's economic participants to change.

2. **A monetary asset suited to the internet**
   - BTC can be transferred globally, settled without a traditional banking intermediary, divided into very small units, and held directly by its owner.
   - It combines some attributes of gold—scarcity and no issuer—with native digital transferability and verifiability.
   - This makes it potentially useful for cross-border savings, capital mobility, collateral, and reserve diversification, especially where local money or banking systems are weak.

3. **Network effects and liquidity**
   - Bitcoin has the longest operating history, largest recognition, deepest liquidity, and broadest infrastructure among cryptoassets.
   - The investment thesis strengthens as more holders, custodians, exchanges, payment rails, derivatives markets, miners, regulated investment products, and corporate or sovereign allocators participate.
   - A store-of-value asset does not need universal adoption. It only needs a meaningful and persistent share of global wealth to choose it as a savings vehicle. Fidelity frames this as Bitcoin's "aspirational store of value" case. [fidelitydigitalassets](https://www.fidelitydigitalassets.com/research-and-insights/bitcoin-investment-thesis-bitcoin-aspirational-store-value-system)

4. **Asymmetric portfolio exposure**
   - If BTC remains a niche speculative asset, it can decline severely.
   - If it becomes a recognized reserve-style asset alongside gold, sovereign debt, and other stores of value, its market capitalization could rise substantially from a lower base.
   - That creates a potential asymmetric payoff—but only for an allocation small enough that a major drawdown does not impair the overall portfolio.

5. **Macro optionality**
   - BTC may benefit when investors worry about currency debasement, capital controls, banking fragility, geopolitical fragmentation, or the long-run credibility of sovereign debt and monetary policy.
   - It should not be described as a reliable short-term inflation hedge: its trading behavior is often dominated by liquidity, risk appetite, leverage, and market positioning. The macro case is better thought of as a **long-duration hedge against monetary-system uncertainty**, not a month-to-month CPI trade.

## The bear case

| Risk | Why it matters | What would validate it |
|---|---|---|
| No intrinsic cash flow | BTC produces no earnings, dividends, coupon, or contractual claim on assets | Investors continue valuing it primarily as a trade rather than a durable monetary asset |
| Extreme volatility | Large drawdowns can force selling, undermine institutional use, and make adoption psychologically difficult | Volatility stays persistently too high for reserve or collateral use |
| Store-of-value competition | Gold, short-duration government debt, stablecoins, other crypto networks, and future digital money compete for savings demand | BTC's share of crypto and alternative-store-of-value demand erodes |
| Regulatory and custody risk | Access often relies on exchanges, ETFs, banks, miners, and custodians even if the protocol itself is decentralized | Major jurisdictions restrict ownership, on/off-ramps, custody, mining, or institutional distribution |
| Security-budget transition | Over time Bitcoin relies increasingly on transaction fees rather than new issuance to pay miners | Hashrate/security weaken materially, or fee economics fail to support robust network security |
| Concentration and leverage | Whales, ETF flows, derivatives liquidations, and leverage can amplify price moves | Market structure remains dominated by reflexive flows rather than organic adoption |
| Narrative failure | "Digital gold" is not guaranteed; money is a social and institutional convention | Adoption fails to expand through multiple economic cycles |

The central bear rebuttal is simple: **scarcity alone does not create value.** Beanie Babies were scarce; value requires durable demand. BTC's long-term value must be supported by increasing willingness to hold it, accept it, custody it, or use it as collateral.

## What would prove it right

Your thesis should be judged against observable milestones, not price targets alone:

- A rising share of long-term, non-speculative ownership rather than leverage-driven trading.
- Deepening global liquidity and resilient trading across venues and jurisdictions.
- Continued security: strong hashrate, distributed mining, and no material protocol compromise.
- Growing institutional infrastructure: qualified custody, derivatives, accounting clarity, lending/collateral acceptance, and regulated access.
- Measurable adoption in savings, treasury management, remittances, and cross-border settlement.
- BTC retaining its relative dominance as the primary non-sovereign monetary cryptoasset.
- Resilience through severe risk-off periods, political pressure, and market drawdowns.

A healthy thesis does **not** require BTC to become a daily medium of exchange everywhere. It requires it to become sufficiently trusted as a monetary reserve asset for a persistent minority of global capital.

## What breaks the thesis

Treat these as invalidation criteria:

- A credible technical or cryptographic failure that compromises ownership, issuance rules, or settlement finality.
- Sustained loss of liquidity, security, or developer/miner participation.
- Structural regulatory restrictions across major capital markets that materially reduce legal access and institutional ownership.
- A superior competing asset meaningfully captures the "neutral, scarce digital reserve asset" role.
- The market repeatedly fails to show durable demand beyond liquidity cycles and speculative leverage.
- Political consensus changes the 21 million cap or other core monetary rules in a way that damages confidence in Bitcoin's credibility.

## Practical conclusion

A concise investment view:

> **BTC is a venture-style position in the monetization of a decentralized digital commodity.** Its core advantage is credible scarcity combined with global, bearer-style digital transferability. Its value rises if more investors and institutions treat it as a long-term reserve asset; it falls if that social consensus, access, security, or relative dominance weakens. Because BTC has no cash flows and can suffer very large drawdowns, position sizing and custody discipline matter more than conviction alone.

The most defensible portfolio framing is therefore: **small, deliberate, long-horizon exposure; no leverage; explicit rebalancing rules; and a willingness to own zero if your invalidation criteria are met.** The case is inherently probabilistic, not a certainty or a guaranteed hedge.

---

### Part B verification

| # | Check | Expect |
|---|---|---|
| 1 | Review Log | 2026-08-29 entry documents Feb exit + re-entry + thesis voice change |
| 2 | Known Facts | Feb 2026 sell recorded; Aug 2026 buy as re-entry |
| 3 | No Motley Fool voice in Core Thesis | Bill's store-of-value framing is primary |
| 4 | Instrument section | Unchanged — still Grayscale Mini Trust ETF, share vs BTC price warning |
| 5 | `[BILL]` markers | Still present on style, ceiling, levels unless Bill removed in sign-off |

Archive before overwrite: copy `BTC_thesis.md` → `vault/theses/archive/` or `.bak` with timestamp per Hard Rule 7.

---

## Docs (last step)

- `CHANGELOG.md` — one dated entry: Part A fix + Part B BTC thesis (if shipped).
- `state.md` — one line under Desk or thesis notes if Part B shipped.

Do **not** update `README.md` / `CLI_MANUAL.md` in this prompt — separate doc pass.

---

## Sequencing

```
Part A (code)  →  pytest + browser UNH parity  →  commit optional
Sign-off gate  →  Bill accepts proposal table
Part B (thesis) →  archive + edit BTC_thesis.md  →  commit optional
```

Do not commit unless Bill asks.

---

## Out of scope

- Changing retrieval to emit weight in points globally
- Auto-syncing thesis history from Transactions (manual + `write_thesis_updates` on next run)
- README / CLI manual refresh
- Setting BTC style, ceiling, or trigger levels without Bill sign-off
- Price targets or allocation recommendations in thesis edits
