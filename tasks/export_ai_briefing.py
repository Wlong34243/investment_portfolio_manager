"""
Standalone AI Briefing exporter.

Assembles a dated package of markdown files (portfolio, podcasts, theses,
prompt, and a combined SUBMIT_ME.md) for manual upload into an external
frontier LLM (Claude.ai, Gemini, ChatGPT) to run a portfolio-vs-podcast
synthesis.

Deliberately standalone: no imports from manager.py, no network calls, no
Sheets access. Writes ONLY under exports/.

Usage:
    python tasks/export_ai_briefing.py [--days 14] [--out exports]
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# Running as `python tasks/export_ai_briefing.py` puts tasks/ on sys.path[0],
# not the repo root — so `from utils...` fails. Morning STEP 9 uses that
# invocation. Mirror manager.py: pin the project root first.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_ASCII_REPLACEMENTS = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "--",
    "‘": "'", "’": "'", "‚": "'",
    "“": '"', "”": '"', "„": '"',
    "→": "->", "←": "<-", "↔": "<->",
    "…": "...", "·": "*", "•": "*",
}


def to_ascii(text):
    """Sanitize arbitrary source text to plain ASCII (Windows console/cp1252 safe)."""
    if text is None:
        return text
    if not isinstance(text, str):
        return text
    for src, dst in _ASCII_REPLACEMENTS.items():
        text = text.replace(src, dst)
    normalized = unicodedata.normalize("NFKD", text)
    return normalized.encode("ascii", "ignore").decode("ascii")

PROMPT_PAYLOAD = """# Portfolio Analysis Briefing — {DATE}

You are analyzing the portfolio of a self-directed investor (Bill). Attached are
these documents: this prompt, `doctrine.md` (standing portfolio constraints —
Bill's own writing, authoritative on what he will and will not do),
`portfolio.md` (positions, tax lots, recent rotations, stamped with a data
fingerprint), `podcasts.md` (summaries of the investment podcasts he follows,
most recent first), and `theses.md` (a digest of his written investment thesis
for each position, with style tags and size ceilings).

When `doctrine.md` is present it **outranks inference from the trade log** on
Bill's constraints. Do not invent constraints that are not in that file. When a
Crosshairs or valuation signal conflicts with doctrine (e.g. a NEAR_TRIM on a
ticker listed under `tax_hold_runners`), treat the doctrine as decisive context,
not as something to litigate away.

## Who you are working for

Bill runs a ~$550-600K Schwab portfolio across four self-defined styles:
1. GARP-by-intuition — undervalued companies whose products he understands
2. Thematic Specialists — buying market position over company quality
3. Boring Fundamentals — durable businesses bought on fear-driven discounts
4. Sector/Thematic ETFs — macro expressions, with broad index and bond ETFs as ballast

His risk management is small-step scaling in and out — never binary entries or
exits. His unit of analysis is the rotation: a linked sell-buy pair with an
implicit substitution thesis. He carries strategic cash intentionally. He knows
the thesis behind every position; your job is drift control and synthesis, not
discovery.

## What to produce, in order

1. **Theme extraction.** Identify the recurring investment themes across the
   podcast summaries. For each theme, name which sources support it and — this
   matters — where sources DISAGREE with each other. Do not average away
   disagreements; state them as tensions and say which resolution would require
   the least change to this portfolio.

2. **Holdings map.** For each major theme, list Bill's actual exposure on both
   sides of it, with tickers and current weights from portfolio.md. Include
   indirect exposure (e.g., a broad ETF that concentrates the same names as his
   single-stock positions).

3. **Coherence checks.** Find places where his positions, recent rotations, or
   recent buys work against each other or against a theme he appears to be
   acting on. Example of the expected caliber: selling a semiconductor-equipment
   stock while averaging down into an EM ETF whose top holdings are 40%
   semiconductor names is self-cancelling. Check ETF look-through overlap
   explicitly.

4. **Rotation candidates.** Where the evidence supports it, propose small-step
   rotations (sell-buy pairs) consistent with his styles. For every candidate,
   show the tax math from portfolio.md: computed unrealized gain/loss per
   position, whether losses offset gains within the pair, and wash-sale timing
   constraints. Holding periods are unknown in the data — say so and tell him to
   verify short-term vs long-term before executing.

5. **Thesis drift flags.** Compare what is currently happening (from the
   podcasts and from current news) against the written theses in theses.md.
   Flag any thesis whose risk section omits the risk that is actually biting
   right now, and any position whose scaling state (e.g., "hold") conflicts
   with what he has recently been doing per the per-position transaction logs
   listed under each thesis in theses.md. Where a thesis shows "scaling:
   (missing)", say so rather than inferring a scaling state from the prose.
   The `Recent Rotations` table in portfolio.md is a manually maintained log
   of intentional rotations, not a complete transaction record, and it lags —
   the per-position transaction logs are the authoritative record of activity.

6. **Current events check.** Search the web for current news on his foreign and
   EM holdings (currency moves, policy, geopolitics) and on any position where
   the podcasts hint at a live situation. Cite every source with a link. Do this
   before writing sections 1-5, not after — current news changes what counts as
   a drift flag. If you genuinely have no web access, say so explicitly at the
   top of your response and list the specific questions he should check himself.

7. **The obvious move.** End with a short section titled "The obvious move":
   the single most coherent next action (or deliberate non-action) given
   everything above, in plain language, followed by the two or three open
   questions he should resolve before acting.

## Undocumented changes (from manifest.json)

If `manifest.json` contains an `undocumented_changes.findings` list that is
non-empty, render it as a short **question block near the top** of your reply
(before theme extraction). Rules:

- One line per finding: ticker, what changed, then the `question` field verbatim.
  No surrounding prose. Do not speculate about the answer.
- Cap at five. If the block carries a SYSTEM miscalibration line, print that
  single line instead of listing more than five.
- If the findings list is empty or absent, omit this section entirely — do not
  write "no findings today".
- Route answers (for Bill, not for you to invent): Review Log for
  entry/exit/resize rationale; `pm journal rotation` for sell-funding-buy;
  `vault/doctrine.md` for standing constraints that govern future decisions
  generally rather than one position.

## Ground rules

- Be candid and specific. He wants pushback, not validation.
- Anchor every claim to a ticker, weight, or source. No generic market
  commentary.
- Respect his style: small steps, rotations not liquidations.
- All data in portfolio.md is read-only truth as of its fingerprint timestamp.
  If something looks wrong or internally inconsistent, flag it rather than
  silently working around it.
- Do not state a number that is not in these files or in a source you cite.
  In particular: no ETF constituent weights, no sector percentages for any
  fund, no forward P/E, no price targets. If a claim needs data that is not
  here, write it as a question for Bill instead of an assertion.

### The governing principle

Bill is the authoritative source on Bill's decisions. The vault and the log are
lagging records of those decisions, not evidence against them.

Where the files and the observed trades disagree, the default inference is
"the file is stale," NOT "the behavior is incoherent." Report the gap as a
documentation task naming the specific file and section to update. Do not
narrate it as a discipline failure, an identity crisis, or a contradiction Bill
needs to resolve about himself. He already knows why he traded; he needs to know
which file doesn't say so yet.

### Hard rules (each exists because the 2026-07-26 briefing violated it)

1. Cash is now sourced from Schwab account balances across the three allowlisted
   accounts and reconciles to Schwab's own liquidationValue. A cash percentage
   computed against the bundle total is therefore meaningful *for those three
   accounts*. It is still not Bill's total liquidity — three further accounts
   are out of scope, and strategic dry powder may sit outside Schwab entirely.
   State the scope whenever citing a cash figure; do not extrapolate to net worth.
   CASH_MANUAL remains the synthetic row ticker name (do not rename).

2. Do not relitigate the role of an established position. JEPI is held for low
   beta; that is settled. For any position whose thesis states a role, describe
   drift WITHIN that role — never argue the role itself is mistaken. Explaining
   an instrument's basic mechanics back to Bill is noise; he is a CPA/CISA who
   selected it deliberately.

3. Style size ceilings apply only to SECTOR_ETF, GARP, THEME and FUND — never to
   ballast/core holdings. JEPI, JPIE, VTI, COWZ and VEA are ballast or core
   foundational exposure and have no meaningful ceiling. Until styles.json is
   split, SUPPRESS ceiling BREACH flags for those tickers rather than reporting
   them. A ceiling flag on a ballast position is a taxonomy bug surfacing as a
   false recommendation, and it crowds out the ceiling signals that matter.

4. Check for an offsetting leg before calling anything drift. Before flagging a
   sale as drift, inconsistency, or self-cancellation, scan every other
   position's transaction log for buys of comparable size within +/-3 days. A
   sell funding a buy is a rotation — Bill's declared unit of analysis — and
   must be reported as one, with the substitution thesis named.
   (Missed case: 2026-07-20 EMXC -100sh ~$9.25K -> BBJP +125sh ~$9.18K, same
   day, both legs present in the bundle.)

5. A sale at a loss, or against the thesis's stated direction, is presumptively
   a conviction change. Do not describe it as a data artifact, an error to
   reconcile, or evidence of undisciplined trading. Bill exits when conviction
   breaks — including at a loss, including weeks after buying. Correct output:
   "this trade implies the thesis changed; the file still says X."
   (Missed case: NOW, sold on lost conviction that it survives the AI
   transition intact; flagged as a suspect data sequence.)

6. Do not moralize about process. No commentary on whether rules were followed,
   whether discipline lapsed, whether behavior is "the worst of both," or
   whether one of two stories "must be wrong." Deliver the finding, name the
   file to update, stop. Candor and pushback are wanted on ANALYSIS — the read
   of a theme, a risk a thesis omits, a tax consequence not priced — not on
   Bill's adherence to his own conventions.

7. Separate tax facts from behavioral narrative. Wash-sale windows, disallowed
   losses and unrealized G/L are objective and always in scope regardless of the
   above. State them cleanly, without judgment about the trade that created them.

8. Rank flags by whether Bill can act on them. An export-time flag reflecting a
   taxonomy gap, a stale file, or missing data is a SYSTEM finding — group those
   separately from portfolio findings. Never lead with one, and never build
   "The obvious move" on one.

9. One source is one source, regardless of length. The Spotify aggregate runs
   4-8x longer than an episode summary because it synthesizes many episodes,
   not because it carries more conviction. Do not weight a theme by how much
   text supports it. Further: the aggregate lists the episodes it draws on
   under "## Cited Episodes", and those episodes are frequently ingested
   separately in the same window. Where an aggregate and a cited episode both
   appear, treat the episode as the primary source for that theme and the
   aggregate as commentary on it. Count the theme once. An aggregate agreeing
   with an episode it is summarizing is not corroboration.
"""


def _level_coverage():
    """Import lazily so a missing utils/level_coverage.py degrades to None
    rather than crashing the whole export. This module is run as a script
    (python tasks/export_ai_briefing.py), so sys.path[0] is tasks/, not the
    repo root -- same fix as build_lookthrough()'s utils/etf_holdings import."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from utils.level_coverage import compute_level_coverage
        return compute_level_coverage
    except ImportError:
        return None


def find_newest_bundle():
    candidates = glob.glob(os.path.join("bundles", "composite_bundle_*.json"))
    if not candidates:
        print("ERROR: no composite_bundle_*.json files found under bundles/")
        sys.exit(1)

    def ts_key(path):
        name = os.path.basename(path)
        m = re.search(r"composite_bundle_(\d{4}-\d{2}-\d{2}T\d{6}Z)_", name)
        if m:
            return m.group(1)
        return name

    candidates.sort(key=ts_key)
    return candidates[-1]


def check_bundle_age(bundle):
    ts_str = bundle.get("timestamp_utc")
    if not ts_str:
        return
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return
    age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    if age_hours > 24:
        print("WARNING: bundle is %.1f hours old" % age_hours)


def build_portfolio_md(bundle, style_map=None, styles=None, lookthrough_mode="cache", ceiling_overrides=None):
    md = bundle.get("_market_data", {})
    positions = md.get("positions", [])
    tax_lots = md.get("tax_lots", [])
    rotations = bundle.get("recent_rotations", [])
    style_map = style_map or {}
    styles = styles or {}
    ceiling_overrides = ceiling_overrides or {}

    lines = []
    lines.append("# Portfolio — %s" % bundle.get("timestamp_utc", "unknown"))
    lines.append("")
    lines.append("composite_hash: %s" % bundle.get("composite_hash", "unknown"))
    lines.append("bundle_timestamp_utc: %s" % bundle.get("timestamp_utc", "unknown"))
    lines.append("total_value: %s" % md.get("total_value", "unknown"))
    lines.append("")

    lines.append("## Positions")
    lines.append("")
    lines.append("| Ticker | Style | Market Value | Weight % | Cost Basis | Unrealized G/L $ | Unrealized G/L % | Asset Class |")
    lines.append("|---|---|---|---|---|---|---|---|")

    sorted_positions = sorted(
        positions, key=lambda p: p.get("market_value", 0) or 0, reverse=True
    )
    for p in sorted_positions:
        mv = p.get("market_value", 0) or 0
        cb = p.get("cost_basis", 0) or 0
        ticker = p.get("ticker", "")
        gl_dollar = mv - cb
        gl_pct = (gl_dollar / cb * 100.0) if cb else 0.0
        lines.append(
            "| %s | %s | %.2f | %.2f | %.2f | %.2f | %.2f | %s |"
            % (
                ticker,
                style_map.get(ticker, "-"),
                mv,
                p.get("weight_pct", 0) or 0,
                cb,
                gl_dollar,
                gl_pct,
                p.get("asset_class", ""),
            )
        )

    lines.append("")
    lines.extend(build_ceiling_check(sorted_positions, style_map, styles, ceiling_overrides))
    lines.extend(build_lookthrough(sorted_positions, style_map, lookthrough_mode))
    lines.append("## Tax Lots")
    lines.append("")
    lines.append(
        "Holding periods are unknown in this export; verify short-term vs long-term "
        "before acting on any tax math."
    )
    lines.append("")
    lines.append("| Ticker | Quantity | Cost/Share | Total |")
    lines.append("|---|---|---|---|")
    for lot in tax_lots:
        lines.append(
            "| %s | %s | %s | %s |"
            % (
                lot.get("ticker", ""),
                lot.get("quantity", ""),
                lot.get("cost_basis_per_share", ""),
                lot.get("cost_basis_total", ""),
            )
        )

    lines.append("")
    lines.append("## Recent Rotations")
    lines.append("")

    staleness = rotation_staleness(rotations, bundle.get("timestamp_utc"))
    if staleness is not None:
        lines.append(
            "**Staleness warning:** the most recent logged rotation is %d days older "
            "than this bundle. `Trade_Log` is not a complete transaction record -- it "
            "is a manually maintained log of intentional rotations, and it lags. Do "
            "NOT treat the absence of a rotation here as evidence that nothing "
            "happened. Per-position transaction logs under each thesis in `theses.md` "
            "are the authoritative record of recent activity." % staleness
        )
        lines.append("")

    if not rotations:
        lines.append("(no rotations logged)")
        lines.append("")
    else:
        lines.append("| Date | Sell_Ticker | Buy_Ticker | Thesis_Brief | Rotation_Type |")
        lines.append("|---|---|---|---|---|")
        for r in rotations:
            lines.append(
                "| %s | %s | %s | %s | %s |"
                % (
                    r.get("Date", ""),
                    r.get("Sell_Ticker", ""),
                    r.get("Buy_Ticker", ""),
                    r.get("Thesis_Brief", ""),
                    r.get("Rotation_Type", ""),
                )
            )

    return to_ascii("\n".join(lines) + "\n")


def build_lookthrough(positions, style_map, mode="cache"):
    """ETF look-through concentration.

    The positions table reports direct weights only. With ~50% of the book in
    funds, single-name exposure is systematically understated -- holding NVDA
    directly AND inside QQQM is one concentration, reported as two smaller ones.
    This section does that arithmetic from real holdings data so the analyst
    never has to guess constituent weights.

    mode: "off"     - skip entirely
          "cache"   - use cached holdings only, never hit the network
          "refresh" - allow network fetch to refresh the cache
    """
    lines = ["## ETF Look-Through (single-name concentration)", ""]
    if mode == "off":
        lines.append(
            "Look-through was disabled for this export. **Do not estimate ETF "
            "constituent weights from memory** -- if a concentration claim needs "
            "fund holdings, write it as a question instead."
        )
        lines.append("")
        return lines

    # This module is run as a script (python tasks/export_ai_briefing.py), so
    # sys.path[0] is tasks/, not the repo root. Put the repo root on the path
    # before reaching for utils/.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from utils.etf_holdings import compute_lookthrough
    except ImportError as e:
        lines.append("(utils/etf_holdings.py unavailable: %s -- look-through skipped)" % e)
        lines.append("")
        return lines

    etf_tickers = [
        p.get("ticker") for p in positions
        if style_map.get(p.get("ticker", "")) == "ETF"
    ]
    etf_tickers = [t for t in etf_tickers if t]
    if not etf_tickers:
        lines.append("(no ETF-tagged positions)")
        lines.append("")
        return lines

    rows, resolved, unresolved = compute_lookthrough(
        positions, etf_tickers, use_network=(mode == "refresh")
    )

    if not rows:
        lines.append(
            "No holdings data was available for any ETF in this book, so no "
            "look-through math could be done. **Do not estimate fund constituent "
            "weights from memory.** Treat every ETF as opaque and write "
            "concentration questions rather than concentration claims."
        )
        lines.append("")
        return lines

    lines.append(
        "Direct position weight plus indirect weight held inside ETFs. Sourced "
        "from each fund's published top-10 holdings, so **every figure below is a "
        "floor** -- true exposure is at least this much and probably more, because "
        "holdings past the top 10 are not counted. Only names with some indirect "
        "exposure are listed."
    )
    lines.append("")
    lines.append("| Symbol | Direct % | Indirect % (via ETFs) | Total % (floor) | Sources |")
    lines.append("|---|---|---|---|---|")
    for r in rows[:25]:
        lines.append(
            "| %s | %.2f | %.2f | %.2f | %s |"
            % (r["symbol"], r["direct_pct"], r["indirect_pct"], r["total_pct"], r["via"])
        )
    lines.append("")
    lines.append("Funds resolved: %s" % (", ".join(resolved) if resolved else "none"))
    if unresolved:
        lines.append("")
        lines.append(
            "Funds with NO holdings data available (treat as opaque, do not guess "
            "their contents): %s" % ", ".join(unresolved)
        )
    lines.append("")
    return lines


def rotation_staleness(rotations, bundle_ts):
    """Days between the newest logged rotation and the bundle timestamp, or None."""
    if not rotations or not bundle_ts:
        return None
    dates = []
    for r in rotations:
        d = str(r.get("Date", "")).strip()[:10]
        try:
            dates.append(datetime.strptime(d, "%Y-%m-%d").date())
        except ValueError:
            continue
    if not dates:
        return None
    try:
        ref = datetime.strptime(bundle_ts, "%Y-%m-%dT%H:%M:%SZ").date()
    except ValueError:
        return None
    gap = (ref - max(dates)).days
    return gap if gap > 30 else None


def build_ceiling_check(positions, style_map, styles, ceiling_overrides=None):
    """Deterministic size-ceiling breach table.

    The ceilings ship in theses.md but nothing ever checked them, and the join
    required to check them by hand (ticker -> style -> ceiling) is exactly the
    kind of step a model skips or fumbles. Compute it here instead.

    ceiling_overrides (ticker -> %) takes precedence over the style default
    when present -- a thesis file's own style_size_ceiling_pct (e.g. META's
    4.0, deliberately below the GARP default of 9.0) is a manual, per-ticker
    decision and must not be silently replaced by the style-wide number.
    """
    lines = ["## Style Size Ceiling Check", ""]
    if not styles or not style_map:
        lines.append("(styles.json or thesis style map unavailable -- check skipped)")
        lines.append("")
        return lines

    ceiling_overrides = ceiling_overrides or {}
    breaches, near, totals, unmapped = [], [], {}, []
    for p in positions:
        ticker = p.get("ticker", "")
        weight = p.get("weight_pct", 0) or 0
        style = style_map.get(ticker)
        if not style:
            if not p.get("is_cash") and ticker not in ("CASH_MANUAL",):
                unmapped.append(ticker)
            continue
        totals[style] = totals.get(style, 0.0) + weight
        override = ceiling_overrides.get(ticker)
        ceiling = override if override is not None else (styles.get(style) or {}).get("size_ceiling_pct")
        if ceiling is None:
            continue
        if weight > ceiling:
            breaches.append((ticker, style, weight, ceiling))
        elif weight >= ceiling * 0.85:
            near.append((ticker, style, weight, ceiling))

    lines.append("Computed at export time from position weights and thesis style tags.")
    lines.append("")
    lines.append("| Ticker | Style | Weight % | Ceiling % | Status |")
    lines.append("|---|---|---|---|---|")
    for t, s, w, c in breaches:
        lines.append("| %s | %s | %.2f | %.2f | BREACH |" % (t, s, w, c))
    for t, s, w, c in near:
        lines.append("| %s | %s | %.2f | %.2f | near ceiling |" % (t, s, w, c))
    if not breaches and not near:
        lines.append("| - | - | - | - | no breaches, nothing within 15% of a ceiling |")
    lines.append("")

    lines.append("| Style | Aggregate Weight % |")
    lines.append("|---|---|")
    for s, w in sorted(totals.items(), key=lambda kv: -kv[1]):
        lines.append("| %s | %.2f |" % (s, w))
    lines.append("")

    if unmapped:
        lines.append(
            "Positions with no thesis style tag (excluded from the check above): %s"
            % ", ".join(sorted(unmapped))
        )
        lines.append("")
    return lines


def parse_summary_date(filename):
    m = re.match(r"^(\d{4}-\d{2}-\d{2})_", filename)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def podcast_signal(text):
    """(has_signal, title) for one podcast summary.

    A summary carries no allocation signal when its Sector Allocations table
    resolves to a single catch-all 'Broad Market' row, or is explicitly tagged
    'No actionable thesis'. Those entries are pure noise for theme extraction --
    worse than noise, because a model told to find recurring themes will
    manufacture them out of episode titles.
    """
    m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = m.group(1).strip() if m else "(untitled)"

    if "No actionable thesis" in text:
        return False, title

    classes = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells or cells[0] in ("Asset Class", ""):
            continue
        classes.append(cells[0])

    if not classes:
        return False, title
    if set(classes) <= {"Broad Market"}:
        return False, title
    return True, title


ZERO_EXPOSURE_MOMENT_ORDER = [
    "position_disclosure", "specific_claim", "reversal", "non_consensus", "disagreement",
]
MAIN_MOMENT_ORDER = [
    "reversal", "disagreement", "non_consensus", "specific_claim", "position_disclosure",
]
MOMENTS_CAP_PER_DAY = 8
ZERO_EXPOSURE_SHARE_WARN_PCT = 20.0


def build_moments_md(days, positions, composite_hash="unknown"):
    """'## High-Signal Moments' block for podcasts.md.

    Pure filesystem: reads data/moments/*.moments.json (written by
    tasks/extract_moments.py), resolves relevance fresh against the live
    position/thesis set, ranks, and renders. No Gemini call, no network,
    no flag -- see prompts/moment_extraction_2026-08-02.md Step 2b. Do not
    add a live-extraction path here; that invariant is the point.
    """
    from utils.agents.moment_extractor import (
        load_cached_moments, resolve_relevance, rehydrate_cached_moment,
        build_thesis_body_index, build_lookthrough_symbols, passes_portfolio_hook_filter,
    )
    from utils.moment_windows import load_ticker_aliases, load_macro_terms

    today = datetime.now().date()
    cached = load_cached_moments()

    held_tickers = {p["ticker"].upper() for p in positions if p.get("ticker")} - {"CASH_MANUAL"}
    thesis_bodies = build_thesis_body_index()
    thesis_tickers = set(thesis_bodies.keys())
    lookthrough_symbols = build_lookthrough_symbols(positions, use_network=False)
    ticker_aliases = load_ticker_aliases()
    macro_terms = load_macro_terms()

    zero_bucket, main_bucket = [], []
    disagreements = 0
    resolved_count = 0
    no_hook_dropped = 0

    for raw in cached:
        d = parse_summary_date(raw.get("source_episode", ""))
        if d is None:
            continue
        age_days = (today - d).days
        if not (0 <= age_days <= days):
            continue

        relevance, _detail = resolve_relevance(
            raw.get("tickers_touched", []), held_tickers, thesis_tickers,
            lookthrough_symbols, ticker_aliases, thesis_bodies,
        )

        try:
            candidate = rehydrate_cached_moment(raw, relevance)
        except Exception:
            # Stale (pre-context, v1) cache entry -- not yet re-extracted
            # under the current schema. Excluded from both the render and
            # the reported stats below rather than counted as a real
            # resolution, since it can't be rendered either way.
            continue

        resolved_count += 1
        guess = raw.get("gemini_relevance_guess")
        if guess is not None and guess != relevance:
            disagreements += 1

        # Fix 2: drop moments with no discernible relationship to the book
        # at all -- not even ZERO_EXPOSURE. A private hotel-investing
        # anecdote with no ticker and no held-name mention doesn't belong
        # in either subsection.
        if not passes_portfolio_hook_filter(candidate, held_tickers, ticker_aliases, macro_terms):
            no_hook_dropped += 1
            continue

        if relevance == "ZERO_EXPOSURE":
            zero_bucket.append(candidate)
        else:
            main_bucket.append(candidate)

    zero_bucket.sort(key=lambda c: ZERO_EXPOSURE_MOMENT_ORDER.index(c.moment_type)
                      if c.moment_type in ZERO_EXPOSURE_MOMENT_ORDER else 99)
    main_bucket.sort(key=lambda c: MAIN_MOMENT_ORDER.index(c.moment_type)
                      if c.moment_type in MAIN_MOMENT_ORDER else 99)

    # Round-robin the two ranked queues into an 8-total cap, starting with
    # zero-exposure, so a naive cap can never silently bury the section
    # this build exists to populate.
    picks_zero, picks_main = [], []
    zi = mi = 0
    turn = "zero"
    while len(picks_zero) + len(picks_main) < MOMENTS_CAP_PER_DAY and (
        zi < len(zero_bucket) or mi < len(main_bucket)
    ):
        if turn == "zero" and zi < len(zero_bucket):
            picks_zero.append(zero_bucket[zi]); zi += 1
        elif turn == "main" and mi < len(main_bucket):
            picks_main.append(main_bucket[mi]); mi += 1
        elif zi < len(zero_bucket):
            picks_zero.append(zero_bucket[zi]); zi += 1
        elif mi < len(main_bucket):
            picks_main.append(main_bucket[mi]); mi += 1
        turn = "main" if turn == "zero" else "zero"

    total_in_window = len(zero_bucket) + len(main_bucket)
    zero_share_pct = (len(zero_bucket) / total_in_window * 100.0) if total_in_window else 0.0

    CONTEXT_EXCERPT_CHARS = 280

    def _render_entry(c):
        tickers = ", ".join(c.tickers_touched) if c.tickers_touched else "(none)"
        context_excerpt = (c.context or "").strip()
        if len(context_excerpt) > CONTEXT_EXCERPT_CHARS:
            context_excerpt = context_excerpt[:CONTEXT_EXCERPT_CHARS].rstrip() + "..."
        return "\n".join([
            '- "%s"' % c.fragment,
            "  %s" % c.why_it_matters,
            "  > %s" % context_excerpt,
            "  %s, %s, tickers: %s, relevance: %s" % (
                c.source_episode, c.moment_type, tickers, c.relevance,
            ),
        ])

    lines = ["## High-Signal Moments", "", "composite_hash: %s" % composite_hash]
    if total_in_window:
        lines.append(
            "%d moment(s) in the last %d day(s) -- %d zero-exposure (%.0f%% share), "
            "%d dropped for no portfolio hook. Python-vs-Gemini relevance disagreement: %d/%d."
            % (total_in_window, days, len(zero_bucket), zero_share_pct, no_hook_dropped,
               disagreements, resolved_count)
        )
        if zero_share_pct < ZERO_EXPOSURE_SHARE_WARN_PCT:
            lines.append(
                "WARNING: zero-exposure share is under %.0f%% -- the ADJACENT legs may be "
                "over-catching and this build may be failing its primary purpose. Reported, "
                "not auto-tuned." % ZERO_EXPOSURE_SHARE_WARN_PCT
            )
    else:
        lines.append("0 moments cached in the last %d day(s)." % days)
    lines.append("")

    lines.append("### Zero-Exposure Ideas")
    lines.append("")
    if picks_zero:
        for c in picks_zero:
            lines.append(_render_entry(c))
            lines.append("")
    else:
        lines.append("(no high-signal moments in window)")
        lines.append("")

    lines.append("### Portfolio-Relevant Moments")
    lines.append("")
    if picks_main:
        for c in picks_main:
            lines.append(_render_entry(c))
            lines.append("")
    else:
        lines.append("(no high-signal moments in window)")
        lines.append("")

    return to_ascii("\n".join(lines) + "\n")


def build_podcasts_md(days, positions=None, composite_hash="unknown"):
    today = datetime.now().date()
    files = glob.glob(os.path.join("data", "podcast_summaries", "*.md"))
    selected = []
    for path in files:
        name = os.path.basename(path)
        d = parse_summary_date(name)
        if d is None:
            continue
        age_days = (today - d).days
        if 0 <= age_days <= days:
            selected.append((d, path))

    selected.sort(key=lambda t: t[0], reverse=True)

    kept, dropped = [], []
    for d, path in selected:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read().strip()
        has_signal, title = podcast_signal(text)
        if has_signal:
            kept.append((d, text))
        else:
            dropped.append(title)

    lines = []
    start_date = today.strftime("%Y-%m-%d")
    if kept:
        oldest = min(d for d, _ in kept).strftime("%Y-%m-%d")
    else:
        oldest = start_date
    lines.append(
        "# Podcast Summaries — %s to %s (%d files)" % (oldest, start_date, len(kept))
    )
    lines.append("")

    if dropped:
        lines.append(
            "%d of %d summaries in this window were withheld because they carry no "
            "sector-allocation signal (a single catch-all 'Broad Market' row, or an "
            "explicit 'No actionable thesis' tag). They are excluded so that theme "
            "extraction is not run against empty tables. Withheld: %s"
            % (len(dropped), len(selected), "; ".join(dropped))
        )
        lines.append("")

    bodies = [text for _, text in kept]
    if bodies:
        lines.append("\n\n---\n\n".join(bodies))
    else:
        lines.append("(no podcast summaries with allocation signal in the selected date range)")

    podcasts_md = to_ascii("\n".join(lines) + "\n")
    moments_md = build_moments_md(days, positions or [], composite_hash=composite_hash)
    return podcasts_md + "\n---\n\n" + moments_md


def extract_frontmatter(text):
    """Top-level frontmatter keys only. Delegates to thesis_reader (strips # comments)."""
    from utils.thesis_reader import extract_frontmatter_flat
    return extract_frontmatter_flat(text)


def strip_regions(text):
    return re.sub(r"<!--\s*region:.*?endregion:.*?-->", "", text, flags=re.DOTALL)


def extract_region(text, name):
    """Pull the raw contents of a single <!-- region:NAME --> block."""
    pattern = (
        r"<!--\s*region:" + re.escape(name) + r"\s*-->(.*?)<!--\s*endregion:"
        + re.escape(name) + r"\s*-->"
    )
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        return None
    return m.group(1).strip()


CITATION_MARKER_RE = re.compile(r"\[(?:file|web):\d+\]")


def strip_citation_markers(text):
    """Remove [file:N] / [web:N] provenance markers left over from thesis drafting.

    Those markers point at source documents that are NOT shipped in the briefing
    package, so an external model either hallucinates their contents or hedges
    around them. Strip at export; the vault file keeps them.
    """
    if not text:
        return text, 0
    n = len(CITATION_MARKER_RE.findall(text))
    if not n:
        return text, 0
    cleaned = CITATION_MARKER_RE.sub("", text)
    cleaned = re.sub(r"[ \t]+([.,;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip(), n


def build_style_map():
    """ticker -> style taxonomy key from thesis frontmatter (shared reader)."""
    from utils.thesis_reader import style_map_from_vault
    return style_map_from_vault()


CEILING_OVERRIDE_RE = re.compile(r"style_size_ceiling_pct:\s*([0-9.]+)")


def build_ceiling_overrides():
    """ticker -> manually-set size-ceiling override (%), read from the
    frontmatter's `triggers:` block. extract_frontmatter()'s flat, per-line
    parser can't see this key -- it's nested under `triggers:`, and that
    parser only matches unindented top-level lines -- so this regexes the
    raw frontmatter block directly instead. Ticker with no override present
    is simply absent from the returned dict; caller falls back to the style
    default. See prompts/schwab_account_scope_fix_2026-08-03.md Deliverable 3."""
    overrides = {}
    for path in sorted(glob.glob(os.path.join("vault", "theses", "*_thesis.md"))):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            continue
        fm, _ = extract_frontmatter(raw)
        ticker = fm.get("ticker") or os.path.basename(path).replace("_thesis.md", "")
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
        if not m:
            continue
        override_m = CEILING_OVERRIDE_RE.search(m.group(1))
        if override_m:
            try:
                overrides[ticker] = float(override_m.group(1))
            except ValueError:
                pass
    return overrides


def load_styles(styles_path):
    if not os.path.exists(styles_path):
        return {}
    with open(styles_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_section(body, heading):
    pattern = r"^##\s+" + re.escape(heading) + r".*?\n(.*?)(?=^##\s|\Z)"
    m = re.search(pattern, body, re.DOTALL | re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip()


def extract_section_any(body, headings):
    """Try each heading spelling in order, return the first section found."""
    for heading in headings:
        section = extract_section(body, heading)
        if section is not None:
            return section, heading
    return None, None


def first_paragraph(section_text):
    if not section_text:
        return None
    parts = re.split(r"\n\s*\n", section_text.strip())
    return parts[0].strip() if parts else None


def extract_key_value(section_text, key):
    """Pull a `key: value` line out of a section.

    Tolerant of a leading list marker (`-`/`*`), bold wrapping around the
    label (`**Next step:**`), a `_`/` ` separator (`next_step` or
    `Next step`), and case. Only the label is normalized -- whatever markdown
    the value itself carries is returned untouched, matching the pre-fix
    behavior for plain `key: value` lines.
    """
    if not section_text:
        return None
    key_variant = key.replace("_", "[ _]")
    label_pattern = re.compile(r"^(?:" + key_variant + r")\s*:\s*(.*)$", re.IGNORECASE)
    for raw_line in section_text.splitlines():
        line = raw_line.strip()
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\*\*([^*]+?)\*\*", r"\1", line)
        m = label_pattern.match(line)
        if m:
            value = m.group(1).strip()
            if value:
                return value
    return None


def extract_state_field(body, heading, key):
    """Resolve a `key:`-style field (Scaling State/next_step, Rotation
    Priority/priority) with a three-way disclosure state instead of a single
    silent '(missing)'.

    Returns (display_value, state) where state is one of:
      "ok"     - key found, value used as-is
      "prose"  - key not found but the section has prose; first paragraph
                 used as a fallback value, tagged so it's visibly a fallback
      "empty"  - section exists but has no usable content
      "absent" - the heading itself is not present in the file
    """
    section = extract_section(body, heading)
    if section is None:
        return "(missing)", "absent"
    if not section.strip():
        return "(missing)", "empty"
    value = extract_key_value(section, key)
    if value:
        return value, "ok"
    prose = first_paragraph(section)
    if prose:
        return "(prose) " + prose, "prose"
    return "(missing)", "empty"


def extract_recent_entries(body, heading, n):
    """Last n top-level `- ` list entries from a section (oldest-first logs
    like Review Log are written chronologically, so "most recent" is the
    tail, not the head)."""
    section = extract_section(body, heading)
    if not section:
        return None
    entries, current = [], []
    for line in section.splitlines():
        if re.match(r"^- ", line):
            if current:
                entries.append("\n".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        entries.append("\n".join(current))
    if not entries:
        return None
    return entries[-n:]


# Sections shipped in full at each --thesis-detail level. "minimal" ships
# none of these (just the Core Thesis first paragraph, as before the
# 2026-07-29 fix). "standard" is the default. "full" adds the context
# sections that are informative but not drift-control inputs.
STANDARD_FULL_SECTIONS = [
    ("Key Risks", ["Key Risks"]),
    ("Exit Conditions", ["Hard Exit Conditions", "Exit Conditions"]),
]
FULL_EXTRA_SECTIONS = [
    ("Bull Case", ["Bull Case", "Bull Case Drivers"]),
    ("Origin", ["Origin"]),
    ("Why This Fits My Portfolio", ["Why This Fits My Portfolio"]),
]
REVIEW_LOG_RECENT_N = 3


def _state_preflight_message(ticker, heading, key, state):
    if state == "absent":
        return "%s: no '## %s' section." % (ticker, heading)
    if state == "prose":
        return (
            "%s: %s is prose, not '%s:' -- parsed by fallback, consider "
            "normalizing." % (ticker, heading, key)
        )
    if state == "empty":
        return "%s: '## %s' section is empty." % (ticker, heading)
    return None


def build_doctrine_md(issues=None):
    """Load vault/doctrine.md for the briefing package. Absent → preflight, no file."""
    issues = issues if issues is not None else []
    path = Path("vault") / "doctrine.md"
    if not path.is_file():
        issues.append(
            "SYSTEM: vault/doctrine.md missing — doctrine.md omitted from this package."
        )
        return None
    try:
        return to_ascii(path.read_text(encoding="utf-8"))
    except OSError as e:
        issues.append("SYSTEM: failed to read vault/doctrine.md: %s" % e)
        return None


def build_theses_md(styles_path, held_tickers=None, issues=None, detail="standard", provenance=None):
    lines = []
    held = set(held_tickers or [])
    issues = issues if issues is not None else []
    covered = set()
    markers_stripped_by_ticker = {}
    omitted_sections_seen = set()

    if os.path.exists(styles_path):
        with open(styles_path, "r", encoding="utf-8") as f:
            styles = json.load(f)
        lines.append("## Style size ceilings")
        lines.append("")
        lines.append("| Style | Size Ceiling % | Description |")
        lines.append("|---|---|---|")
        for style, info in styles.items():
            lines.append(
                "| %s | %s | %s |"
                % (style, info.get("size_ceiling_pct", ""), info.get("description", ""))
            )
        lines.append("")
    else:
        lines.append("(styles.json not found)")
        lines.append("")

    disclosure_placeholder_index = len(lines)
    lines.append("")  # filled in after the loop, once omissions are known

    thesis_files = sorted(glob.glob(os.path.join("vault", "theses", "*_thesis.md")))
    for path in thesis_files:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        fm, body_raw = extract_frontmatter(raw)
        body = strip_regions(body_raw)

        ticker = fm.get("ticker") or os.path.basename(path).replace("_thesis.md", "")

        # Coverage gate: never ship a thesis for a position that is not held.
        # A stale thesis reads as a live position to any downstream reader.
        if held and ticker not in held:
            issues.append(
                "SKIPPED %s: thesis exists in vault/theses/ but the position is not "
                "held in this bundle. Archive it or confirm the exit." % ticker
            )
            continue
        covered.add(ticker)

        style = fm.get("style", "(missing)")
        last_reviewed = fm.get("last_reviewed", "(missing)")

        next_step, scaling_state = extract_state_field(body, "Scaling State", "next_step")
        msg = _state_preflight_message("%s" % ticker, "Scaling State", "next_step", scaling_state)
        if msg:
            issues.append(msg)

        priority, priority_state = extract_state_field(body, "Rotation Priority", "priority")
        msg = _state_preflight_message("%s" % ticker, "Rotation Priority", "priority", priority_state)
        if msg:
            issues.append(msg)

        core_section = extract_section(body, "Core Thesis")
        if core_section is None:
            # Doc gap, not an abort — the briefing exists to surface these.
            issues.append(
                "SYSTEM %s: no '## Core Thesis' section -- update vault/theses/%s_thesis.md"
                % (ticker, ticker)
            )
            core_full = "(missing)"
        elif detail == "minimal":
            core_full = first_paragraph(core_section) or "(missing)"
        else:
            core_full = core_section
        core_full, n_markers = strip_citation_markers(core_full)
        if n_markers:
            markers_stripped_by_ticker[ticker] = markers_stripped_by_ticker.get(ticker, 0) + n_markers

        lines.append(
            "### %s — style: %s | scaling: %s | priority: %s | reviewed: %s"
            % (ticker, style, next_step, priority, last_reviewed)
        )
        if detail in ("standard", "full"):
            try:
                from utils.thesis_reader import get_pattern
                pat = get_pattern(raw)
            except Exception:
                pat = None
            if pat:
                comp = pat.get("comp")
                note = pat.get("note")
                extra = ""
                if comp:
                    extra += f" | comp: {comp}"
                if note:
                    note_s = str(note).strip().replace("\n", " ")
                    if len(note_s) > 120:
                        note_s = note_s[:117] + "..."
                    extra += f" | {note_s}"
                lines.append(f"**Pattern:** `{pat.get('name')}`{extra}")
        lines.append("**Core Thesis**")
        lines.append(core_full)
        lines.append("")

        if detail in ("standard", "full"):
            for label, heading_variants in STANDARD_FULL_SECTIONS:
                section, _ = extract_section_any(body, heading_variants)
                if section is None:
                    continue
                section, n = strip_citation_markers(section)
                if n:
                    markers_stripped_by_ticker[ticker] = markers_stripped_by_ticker.get(ticker, 0) + n
                lines.append("**%s**" % label)
                lines.append(section)
                lines.append("")

            lines.append("**Scaling State**")
            lines.append(
                extract_section(body, "Scaling State") or "(missing)"
            )
            lines.append("")

            lines.append("**Rotation Priority**")
            lines.append(
                extract_section(body, "Rotation Priority") or "(missing)"
            )
            lines.append("")

            recent_log = extract_recent_entries(body, "Review Log", REVIEW_LOG_RECENT_N)
            if recent_log:
                lines.append("**Review Log (%d most recent)**" % len(recent_log))
                lines.append("\n".join(recent_log))
                lines.append("")

        if detail == "full":
            for label, heading_variants in FULL_EXTRA_SECTIONS:
                section, _ = extract_section_any(body, heading_variants)
                if section:
                    lines.append("**%s**" % label)
                    lines.append(section)
                    lines.append("")
        elif detail == "standard":
            for label, heading_variants in FULL_EXTRA_SECTIONS:
                section, _ = extract_section_any(body, heading_variants)
                if section:
                    omitted_sections_seen.add(label)
        # minimal: everything past the core paragraph is omitted
        if detail == "minimal":
            for label, heading_variants in STANDARD_FULL_SECTIONS + FULL_EXTRA_SECTIONS + [
                ("Scaling State (full section)", ["Scaling State"]),
                ("Rotation Priority (full section)", ["Rotation Priority"]),
                ("Review Log", ["Review Log"]),
            ]:
                section, _ = extract_section_any(body, heading_variants)
                if section:
                    omitted_sections_seen.add(label)

        # Per-position transaction log. This lives in a <!-- region:transaction_log -->
        # block that strip_regions() used to delete before export, which left the
        # prompt asking the model to check scaling state "per the transaction logs"
        # with no transaction logs in the package.
        txns = extract_region(body_raw, "transaction_log")
        if txns:
            entries = [l.strip() for l in txns.splitlines() if l.strip().startswith("-")]
            if entries:
                lines.append("Recent transactions (%s):" % ticker)
                lines.extend(entries)
                lines.append("")

    uncovered = sorted(held - covered - {"CASH_MANUAL"})
    if uncovered:
        # SYSTEM (not BLOCKING): a missing thesis is exactly the kind of finding
        # the morning briefing is supposed to report. Aborting the export hid the
        # signal and left an empty exports/ folder (makedirs-then-exit).
        issues.append(
            "SYSTEM: held positions with no thesis file: %s -- create "
            "vault/theses/{TICKER}_thesis.md for each"
            % ", ".join(uncovered)
        )
        # Ship an explicit section so SUBMIT_ME / Cowork briefs see the gap
        # without digging in manifest.json.
        gap = [
            "",
            "## Documentation gaps (SYSTEM)",
            "",
            "Held positions with no thesis file. Treat as documentation tasks, "
            "not portfolio incoherence:",
            "",
        ]
        for t in uncovered:
            gap.append("- **%s** -> create `vault/theses/%s_thesis.md`" % (t, t))
        gap.append("")
        # Insert after the style-ceilings block / disclosure placeholder area:
        # disclosure is at disclosure_placeholder_index; put gaps just after it.
        insert_at = disclosure_placeholder_index + 1
        lines[insert_at:insert_at] = gap
    if markers_stripped_by_ticker and provenance is not None:
        provenance["stripped_markers"] = {t: n for t, n in sorted(markers_stripped_by_ticker.items())}

    included = ["Core Thesis"]
    if detail in ("standard", "full"):
        included += ["Key Risks", "Exit Conditions", "Scaling State", "Rotation Priority",
                     "Review Log (%d most recent)" % REVIEW_LOG_RECENT_N]
    if detail == "full":
        included += ["Bull Case", "Origin", "Why This Fits My Portfolio"]
    omitted = sorted(omitted_sections_seen - set(included))
    disclosure = (
        "Sections included per position (--thesis-detail=%s): %s. "
        "Sections omitted at export: %s. "
        "Transaction logs show only the most recent entries per position (capped "
        "by the vault sync writer) and are NOT complete position history; a "
        "capped log states so inline as '(showing N most recent of M)'."
        % (detail, ", ".join(included), ", ".join(omitted) if omitted else "(none)")
    )
    lines[disclosure_placeholder_index] = disclosure

    return to_ascii("\n".join(lines) + "\n")


def _cleanup_empty_pkg_dir(pkg_dir: str) -> None:
    """Remove a package dir that never got real content.

    Google Drive File Stream often drops a desktop.ini into a new folder
    within seconds, so treat 'only desktop.ini' as empty too — otherwise
    morning leaves husk dirs like exports/ai_briefing_* with nothing usable.
    """
    try:
        if not os.path.isdir(pkg_dir):
            return
        names = [n for n in os.listdir(pkg_dir) if n.lower() != "desktop.ini"]
        if names:
            return
        for n in os.listdir(pkg_dir):
            try:
                os.remove(os.path.join(pkg_dir, n))
            except OSError:
                pass
        os.rmdir(pkg_dir)
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Export AI portfolio briefing package.")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--out", type=str, default="exports")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Export even if preflight reports blocking issues.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not pop open the package folder when done (for automated runs).",
    )
    parser.add_argument(
        "--lookthrough",
        choices=["off", "cache", "refresh"],
        default="cache",
        help=(
            "ETF look-through concentration. 'cache' (default) uses cached fund "
            "holdings only; 'refresh' fetches from yfinance to refresh the cache; "
            "'off' skips the section."
        ),
    )
    parser.add_argument(
        "--thesis-detail",
        choices=["full", "standard", "minimal"],
        default="standard",
        help=(
            "How much of each thesis file to ship in theses.md. 'standard' "
            "(default) ships Core Thesis, Key Risks, Exit Conditions, Scaling "
            "State, Rotation Priority, and the 3 most recent Review Log entries. "
            "'full' adds Bull Case/Origin/Why This Fits My Portfolio. 'minimal' "
            "reproduces the pre-2026-07-29 behavior (Core Thesis first paragraph "
            "only) for size-constrained runs."
        ),
    )
    args = parser.parse_args()

    bundle_path = find_newest_bundle()
    with open(bundle_path, "r", encoding="utf-8") as f:
        bundle = json.load(f)

    check_bundle_age(bundle)

    now = datetime.now()
    pkg_name = "ai_briefing_%s" % now.strftime("%Y-%m-%d_%H%M%S")
    pkg_dir = os.path.join(args.out, pkg_name)
    suffix = 2
    while os.path.exists(pkg_dir):
        pkg_dir = os.path.join(args.out, "%s_%d" % (pkg_name, suffix))
        suffix += 1
    os.makedirs(pkg_dir)

    try:
        issues = []
        provenance = {}
        styles_path = os.path.join("data", "styles.json")
        styles = load_styles(styles_path)
        style_map = build_style_map()
        ceiling_overrides = build_ceiling_overrides()

        positions = bundle.get("_market_data", {}).get("positions", [])
        held_tickers = {p.get("ticker") for p in positions if p.get("ticker")}

        compute_level_coverage = _level_coverage()
        level_coverage = (
            compute_level_coverage(held_tickers - {"CASH_MANUAL"})
            if compute_level_coverage else None
        )

        portfolio_md = build_portfolio_md(
            bundle, style_map=style_map, styles=styles, lookthrough_mode=args.lookthrough,
            ceiling_overrides=ceiling_overrides,
        )
        podcasts_md = build_podcasts_md(
            args.days, positions=positions, composite_hash=bundle.get("composite_hash", "unknown")
        )
        theses_md = build_theses_md(
            styles_path, held_tickers=held_tickers, issues=issues, detail=args.thesis_detail, provenance=provenance
        )
        prompt_md = PROMPT_PAYLOAD.replace("{DATE}", now.strftime("%Y-%m-%d"))
        doctrine_md = build_doctrine_md(issues=issues)

        blocking = [i for i in issues if i.startswith("BLOCKING")]
        if issues:
            print("\n--- Preflight ---")
            for i in issues:
                print("  %s" % i)
            print("--- end preflight ---\n")
        if blocking and not args.force:
            print(
                "ABORTED: %d blocking issue(s) above. Fix them, or re-run with --force "
                "to export anyway." % len(blocking)
            )
            _cleanup_empty_pkg_dir(pkg_dir)
            sys.exit(1)

        # Prepend staleness banner if degraded health sentinel is present
        from tasks.health import read_failure_sentinel
        sentinel = read_failure_sentinel()
        if sentinel:
            banner = (
                "=========================================================================\n"
                "WARNING: PORTFOLIO DATA IS DEGRADED AND STALE (CRITICAL HEALTH FAILURE)\n"
                f"Failing checks since (UTC): {sentinel.get('timestamp_utc', 'N/A')}\n"
            )
            for fc in sentinel.get("failing_checks", []):
                banner += f"  - {fc.get('label', fc.get('name', 'Unknown'))}: {fc.get('detail', '')}\n"
            banner += f"Remediation: {sentinel.get('remediation', 'N/A')}\n"
            banner += "=========================================================================\n\n"
            banner = to_ascii(banner)

            portfolio_md = banner + portfolio_md
            theses_md = banner + theses_md
            if doctrine_md is not None:
                doctrine_md = banner + doctrine_md

        submit_parts = [prompt_md]
        if doctrine_md is not None:
            submit_parts.append(doctrine_md)
        submit_parts.extend([portfolio_md, podcasts_md, theses_md])
        submit_me_md = "\n\n---\n\n".join(submit_parts)
        if sentinel:
            # Prepend to the composite file too
            submit_me_md = banner + submit_me_md

        file_map = {
            "prompt.md": prompt_md,
            "portfolio.md": portfolio_md,
            "podcasts.md": podcasts_md,
            "theses.md": theses_md,
            "SUBMIT_ME.md": submit_me_md,
        }
        if doctrine_md is not None:
            file_map = {
                "prompt.md": prompt_md,
                "doctrine.md": doctrine_md,
                "portfolio.md": portfolio_md,
                "podcasts.md": podcasts_md,
                "theses.md": theses_md,
                "SUBMIT_ME.md": submit_me_md,
            }

        sizes = {}
        hashes = {}
        for name, content in file_map.items():
            path = os.path.join(pkg_dir, name)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            sizes[name] = os.path.getsize(path)
            with open(path, "rb") as f:
                hashes[name] = hashlib.sha256(f.read()).hexdigest()

        SIZE_WARN_BYTES = 250_000
        if sizes.get("SUBMIT_ME.md", 0) > SIZE_WARN_BYTES:
            print(
                "WARNING: SUBMIT_ME.md is %d bytes (> %d byte guideline). Consider "
                "--thesis-detail minimal or --lookthrough off for this run."
                % (sizes["SUBMIT_ME.md"], SIZE_WARN_BYTES)
            )

        from tasks.detect_undocumented_changes import detect_for_export
        # Banner lines (if any) are not Positions table rows — parse is safe on portfolio_md.
        undocumented = detect_for_export(
            current_portfolio_md=portfolio_md,
            exports_dir=args.out,
            current_pkg_name=os.path.basename(pkg_dir),
            generated_at=now.strftime("%Y-%m-%dT%H:%M:%S"),
        )

        manifest = {
            "composite_hash": bundle.get("composite_hash"),
            "bundle_path": bundle_path,
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "days_window": args.days,
            "days_window_applies_to": "podcast summaries only",
            "thesis_detail": args.thesis_detail,
            "level_coverage": level_coverage,
            "provenance": provenance,
            "files": sizes,
            "file_sha256": hashes,
            "preflight_issues": issues,
            "undocumented_changes": {
                k: v for k, v in undocumented.items() if k != "suppress_log"
            },
        }
        # suppress_log stays out of the shipped manifest (CLI detector retains it).
        manifest_path = os.path.join(pkg_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, indent=2)
        sizes["manifest.json"] = os.path.getsize(manifest_path)

        print("Package: %s" % pkg_dir)
        for name, size in sizes.items():
            print("  %s: %d bytes" % (name, size))

        if not args.no_open:
            try:
                os.startfile(os.path.abspath(pkg_dir))
            except Exception:
                pass

        sys.exit(0)
    except SystemExit:
        raise
    except Exception:
        _cleanup_empty_pkg_dir(pkg_dir)
        raise


if __name__ == "__main__":
    main()
