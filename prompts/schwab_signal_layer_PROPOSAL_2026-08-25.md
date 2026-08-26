# PROPOSAL — Schwab Signal Layer and Interactivity

> **⚠️ THIS IS A DECISION DOCUMENT, NOT A BUILD PROMPT.**
> No Step 0 gate, no verification checklist, no CLI spec — deliberately.
> Nothing here is authorised. If you are an executing agent: **do not implement any part
> of this file.** Each item below becomes a real prompt file only after Bill picks it.
>
> **Revised 2026-08-25.** Two items (§1 quote-field widening, §5 the streaming exclusion
> line) have been promoted into authorised prompts and are marked ✅ in place. They are
> retained here for their reasoning only — act on them from Phase 1 and Phase 2, never
> from this file. Items §2, §3, §4 and §6 remain unauthorised.
>
> **2026-08-26 hygiene:** Remaining §§ stay unauthorized. Incomplete proposal items are
> presumed not useful as a build backlog — do not promote unless Bill authorizes a new
> prompt file. Streaming already declined in `CLAUDE.md` What NOT to Do.

**Created:** 2026-08-25
**Context:** Phases 1–4 (`schwab_data_expansion`, `price_history_migration`,
`cash_income_truth`, `risk_metrics_market_calendar`) consume the Schwab endpoints with
clear, immediate uses. This file covers the remainder: what is left in the API, what it
would actually buy, and — for three of the five — why the answer is probably no.

---

## The remaining surface, scored

| Capability | What it would feed | Cost | Verdict |
|---|---|---|---|
| **Quote-field widening** | `fetch_quotes()` extracts 6 fields from a payload carrying ~50 | Hours | **Do it** — fold into a Phase 1 follow-up |
| **`get_movers`** | Idea Generator universe beyond held names | Days | **Worth a trial** — bounded, cheap to throw away |
| **`get_instruments` SEARCH/REGEX** | Ticker/CUSIP resolution, corporate-action detection | Days | **Conditional** — only if symbol drift actually bites |
| **Option chains → IV** | Dislocation scanner enrichment | 1–2 weeks | **Defer** — real signal, poor cost ratio right now |
| **Streaming (all services)** | Nothing this architecture consumes | Weeks + ongoing | **No** |

---

## 1. Quote-field widening — the cheapest thing on this list

`fetch_quotes()` (`utils/schwab_client.py` ~line 736) pulls `lastPrice`, `bidPrice`,
`askPrice`, `totalVolume`, `netPercentChange`. The Schwab quote payload also carries
52-week high/low, P/E, dividend yield and amount, net change, extended-hours quote and
volume, quote timestamps, exchange, and volatility.

Two of those are already being sourced elsewhere at higher cost and lower reliability:

- **52-week high/low** — `dislocation_scan.py` computes drawdown-from-52w-high from
  yfinance bars. Schwab reports it directly in a call the system already makes daily.
- **Dividend yield** — `fetch_positions()` sets `'Dividend Yield': 0.0` with the comment
  *"Filled by enrichment"*, and enrichment goes to yfinance/FMP. Schwab supplies it in
  the same quote response.

Widening the extraction is a dict-key change; rewiring consumers onto it is a separate,
riskier change. Conflating the two was a defect in the first draft of this file.

> ### ✅ PROMOTED — no longer a proposal, revised 2026-08-25
>
> This item has been split and moved into authorised prompts. **Do not act on it from
> this file.**
>
> - **Extraction** → `schwab_data_expansion_2026-08-25.md`, **Step 3b**. Adds the
>   columns; rewires nothing; verification rows 15–18.
> - **Consumer rewiring** → `price_history_migration_2026-08-25.md`, **tier 8**
>   (8a `dislocation_scan` 52-week high, 8b `fetch_positions` dividend yield), gated
>   and committed separately, after the seven bar consumers.
>
> The real-time-vs-delayed question is Step 3b item 4: a delayed feed is fine for every
> use above, but must be labelled, not assumed.

---

## 2. `get_movers` — a bounded experiment for the Idea Generator

Every input to the idea pipeline is inward-facing: own holdings, own theses, podcasts,
the hand-maintained watchlist, and FMP's biggest-losers screen. `get_movers` adds
`$SPX` / `$DJI` / `$COMPX` / NYSE / NASDAQ top-ten by volume, trades, or percent change,
free with the existing auth.

The honest case **for**: it is a daily, deterministic, zero-marginal-cost sample of
market attention from outside the existing corpus. Zero-exposure areas are where new
ideas live, and this is the only proposed input that systematically surfaces names the
system has never seen.

The honest case **against**: top-ten-by-percent-change is a low-quality universe. It is
dominated by microcaps, biotech binaries and squeezes — the opposite of GARP-by-intuition
or Boring Fundamentals. Without a market-cap and liquidity floor it is noise, and FMP's
biggest-losers screen already does a similar job with a `$10B` floor
(`DISLOCATION_MIN_MARKET_CAP`).

**If built:** market-cap floor reusing the existing constant, dedup against current
holdings and the watchlist, feed as a clearly-labelled distinct source into the Idea
Generator, and **evaluate after 20 trading days on one question — did any name from this
source survive to a thesis file?** If none did, delete it. Fire-fire-aim: it is cheap to
try and cheap to throw away, which is exactly the profile this repo's philosophy says to
try.

---

## 3. `get_instruments` SEARCH / SYMBOL_REGEX — conditional

Useful for CUSIP↔symbol resolution and for detecting ticker changes, mergers and
delistings before they present as a mysterious data gap.

The condition: has symbol drift actually caused a problem? `config.ISSUER_ALIASES`
already handles GOOGL→GOOG and SKHY→000660.KS by hand, which suggests the manual approach
is holding. **Build this only after a real incident, not in anticipation of one.**

---

## 4. Option chains → implied volatility — defer, with a specific reason

Options data has genuine non-trading uses that respect every hard rule: IV rank as a
stress signal on held names, IV skew as a directional-positioning read, and
earnings-implied move as context for the earnings-proximity column already on the
Command Center.

Why defer anyway:

- The build is real — chain retrieval, IV-rank history (which needs its own stored
  series, since rank is meaningless without one), and interpretation rules.
- IV rank is a *timing* signal, and this system is deliberately not a timing system.
  Scaling in and out in small steps does not obviously improve with an IV overlay.
- It edges toward market prediction. IV skew as a *fact* is fine; IV skew narrated as
  "the market expects" is Hard Rule 4 territory, and the line is thinner than it looks.

**Revisit if:** Bill starts writing covered calls or cash-secured puts, at which point
chain data stops being a signal overlay and becomes position data — a different and much
stronger case.

---

## 5. Streaming — no

WebSocket Level 1/2, order books, `ACCT_ACTIVITY`, screener streams.

Against, decisively:

- The system is a daily batch pipeline whose outputs are a Sheet, a briefing bundle and a
  static cockpit. Nothing downstream consumes sub-daily latency.
- Streaming requires a supervised long-running process. `DailyWake` has never
  successfully fired since 2026-07-27 and the morning pipeline is effectively manual-only
  — the operational maturity for a persistent daemon is not there, and the fix for that
  is a Task Scheduler change, not a second always-on component.
- It contradicts the reproducibility rationale behind "Python gathers, LLMs reason." A
  hash-stamped snapshot is re-runnable; a stream is not. When a number turns out wrong,
  a stream cannot tell you whether the data changed or the reasoning did.
- `ACCT_ACTIVITY` is the one arguably useful service — same-session fill capture — and
  `get_transactions` already covers it by the next morning, which is when the pipeline
  runs anyway.

**Recommendation: close this off explicitly.** A line in `CLAUDE.md`'s "What NOT to Do"
costs nothing and stops this being rediscovered every few months, the same way the MCP
and auto-trading lines already do.

> ### ✅ PROMOTED — no longer a proposal, revised 2026-08-25
>
> The exact line to add is now carried verbatim in
> `schwab_data_expansion_2026-08-25.md` → *Documentation to update on completion*, so it
> ships with Phase 1's doc pass. **Do not add it from this file.**
>
> It is a standing decision rather than a build consequence, so Bill may equally apply it
> by hand at any time; Phase 1 instructs the executor to skip it if already present.

---

## 6. On "a more interactive and smart app"

Worth separating two things that sound alike.

**Interactive** is a UI property. The surfaces that exist today are `ui/app.py`
(FastAPI + HTMX, `pm ui serve`, debug-only localhost) and
`pm store publish-cockpit --live --publish` (static HTML mirrored to Drive for phone
access). More Schwab data does not make either more interactive; it makes them denser.
The interactivity gap, if there is one, is a UI question — filtering, drill-down,
what-if on a Crosshairs row — and it should be scoped as a UI prompt against
`PortfolioStore`, not smuggled in behind a data-expansion phase.

**Smart** is a data property, and that is what Phases 1–4 actually buy:

| Question the system cannot answer today | What makes it answerable | Phase |
|---|---|---|
| "Is my cash figure complete?" | Full `currentBalances` + `liquidationValue` reconciliation | 3 |
| "How much did I earn in income, by position, TTM?" | Typed `DIVIDEND_OR_INTEREST` transactions | 3 |
| "Did the portfolio grow, or did I just deposit money?" | `Cash_Flows` ledger | 3 |
| "What is this position's beta, vol, drawdown?" | Bars → `Risk_Metrics` | 1, 4 |
| "Is today's data actually stale, or was the market closed?" | Trading calendar | 4 |
| "Are my two memory positions correlated?" | Correlation matrix from bars | 4 |

That last row connects to an open question already on record: MU (GARP, 9% ceiling) plus
SKHY (THEME, 3% ceiling) is one memory/HBM bet governed by two ceilings, with nothing
measuring combined exposure. A correlation matrix does not resolve the taxonomy defect,
but it **measures** it for the first time — and measurement is the honest precondition
for deciding whether a third ceiling is needed.

One deliberate omission: **none of these phases proposes an agent.** The four hard rules
about AI sandboxing hold regardless, and none of this needs an LLM. The system gets
smarter here by gathering better, not by reasoning more.

---

## Suggested decision order

1. ~~Fold quote-field widening into Phase 1.~~ **Done 2026-08-25** — split into Phase 1
   Step 3b (extraction) and Phase 2 tier 8 (consumers). Nothing left to decide here.
2. ~~Add the streaming exclusion to `CLAUDE.md`'s What NOT to Do.~~ **Done 2026-08-25** —
   verbatim text now lives in Phase 1's documentation section.
3. **After Phase 4 ships** — decide on `get_movers` as a 20-day experiment with a
   pre-committed kill criterion.
4. **Only on a real incident** — `get_instruments` SEARCH.
5. **Only if the strategy changes** — option chains.
6. **Separately, if wanted** — a UI prompt for the cockpit, scoped as UI, not data.
