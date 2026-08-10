"""
Level-coverage check: cross-references held positions against thesis
frontmatter (price_trim_above / price_add_below / last_reviewed) to report
which positions have no Trim level, no Add level, or a stale review.

A blank level and a level that's simply far from price render identically as
nothing in the command center's "near your levels" view -- this makes the
gap itself visible instead of silent. Deliberately standalone (filesystem
only, no Sheets/network) so both build_command_center.py and
tasks/export_ai_briefing.py can call it without new coupling.
"""

import glob
import os
import re
from datetime import datetime, timezone

DEFAULT_STALENESS_DAYS = 90
THESES_DIR = os.path.join("vault", "theses")

# trigger_type -> (trim field, add field). `ceiling_only` has no valuation
# band; the style ceiling governs, so it needs neither field to be "covered".
#
# trigger_type is PRIMARY, not exclusive: a thesis file's `triggers:` block
# may carry populated band fields for more than one type at once (e.g. both
# price_trim_above/price_add_below and fwd_pe_trim_above/fwd_pe_add_below —
# see XOM, GILD). Only the declared trigger_type's pair counts toward
# coverage here; the rest ride along in vault_bundle.py's triggers dict as
# secondary, uncounted data rather than being discarded. Decided 2026-08-09
# (prompts/trigger_types_2026-08-09.md Step 2) specifically so a cyclical
# name whose *existing* trigger isn't earnings-multiple-based (XOM's price
# band) doesn't get forced into price_to_book for a problem it doesn't have.
TRIGGER_TYPE_FIELDS = {
    "price": ("price_trim_above", "price_add_below"),
    "fwd_pe": ("fwd_pe_trim_above", "fwd_pe_add_below"),
    # Distinct from fwd_pe, not a synonym: yfinance/FMP don't expose a real
    # historical *forward* P/E series (it's an analyst-estimate snapshot,
    # not a backfillable time series), only historical trailing EPS. A band
    # built from trailing history and evaluated against a live forward P/E
    # reading is silently miscalibrated -- the gap between trailing and
    # forward P/E varies by company (2-4x seen across APO/NOW/AVGO/NVDA/AAPL
    # in this book) and would leave some positions permanently reading
    # "cheap" and unable to trim, the same failure mode as consensus_price_target
    # (see prompt's "why not analyst price targets"), just self-inflicted
    # instead of inherited. Added 2026-08-09, Bill's catch. Band on trailing,
    # trigger on trailing -- never cross the two.
    "trailing_pe": ("trailing_pe_trim_above", "trailing_pe_add_below"),
    "discount_from_high": ("trim_below_discount_pct", "add_above_discount_pct"),
    "price_to_book": ("pb_trim_above", "pb_add_below"),
    "ceiling_only": (None, None),
}
DEFAULT_TRIGGER_TYPE = "price"  # backwards-compat inference: no `trigger_type` key -> price


def _frontmatter_field(content, key):
    """First `key: value` line anywhere in the file (top-level or nested
    under `triggers:`), tolerant of quotes, leading indentation, and a
    trailing `# comment` (thesis triggers are commented liberally, e.g.
    `price_trim_above:   # set once position is sized`, which is a blank
    value, not a value of "# set once position is sized").

    Whitespace around the value is matched with `[ \\t]*`, not `\\s*` --
    `\\s` also matches newlines, so on a blank value (`key:` with nothing
    after it) `\\s*` would swallow the line break and the capture group
    would grab the *next* line's `key: value` text as if it belonged to
    this key. That silently turned "unset" into a truthy garbage string
    for any thesis with two consecutive blank trigger fields (found
    2026-08-09 affecting AMZN, ES, ETN, PWR, SKHY, SNOW)."""
    m = re.search(
        r"^[ \t]*" + re.escape(key) + r":[ \t]*['\"]?([^\n'\"]*)['\"]?[ \t]*$",
        content,
        re.MULTILINE,
    )
    if not m:
        return None
    val = m.group(1).split("#", 1)[0].strip()
    return val or None


def _declared_trigger_type(content):
    """Position's trigger_type, inferred as `price` when absent (Step 1
    backwards-compat requirement: a file with price_trim_above and no
    trigger_type behaves exactly as before this concept existed)."""
    declared = _frontmatter_field(content, "trigger_type")
    if declared and declared in TRIGGER_TYPE_FIELDS:
        return declared
    return DEFAULT_TRIGGER_TYPE


def compute_level_coverage(held_tickers, staleness_days=DEFAULT_STALENESS_DAYS, theses_dir=THESES_DIR):
    held = sorted(set(held_tickers or []))
    now = datetime.now(timezone.utc)

    thesis_by_ticker = {}
    for path in glob.glob(os.path.join(theses_dir, "*_thesis.md")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        ticker = _frontmatter_field(content, "ticker") or os.path.basename(path).replace("_thesis.md", "")
        thesis_by_ticker[ticker] = content

    no_trim, no_add, stale, no_thesis = [], [], [], []
    trigger_type_by_ticker = {}
    # type -> {"total": n, "covered": n}; "covered" means a complete band for
    # the declared type, or ceiling_only (no band needed -- the style ceiling
    # governs). Kept separate from no_trim/no_add above, which stay
    # price-shaped for backwards compat with format_footer_line().
    coverage_by_type = {}

    def _bump_type(trigger_type, covered):
        bucket = coverage_by_type.setdefault(trigger_type, {"total": 0, "covered": 0})
        bucket["total"] += 1
        if covered:
            bucket["covered"] += 1

    for ticker in held:
        content = thesis_by_ticker.get(ticker)
        if content is None:
            no_thesis.append(ticker)
            no_trim.append(ticker)
            no_add.append(ticker)
            stale.append(ticker)
            trigger_type_by_ticker[ticker] = None
            _bump_type("no_thesis", covered=False)
            continue

        trigger_type = _declared_trigger_type(content)
        trigger_type_by_ticker[ticker] = trigger_type
        trim_field, add_field = TRIGGER_TYPE_FIELDS[trigger_type]

        if trigger_type == "ceiling_only":
            has_trim, has_add = True, True
        else:
            has_trim = bool(_frontmatter_field(content, trim_field))
            has_add = bool(_frontmatter_field(content, add_field))

        if not has_trim:
            no_trim.append(ticker)
        if not has_add:
            no_add.append(ticker)
        _bump_type(trigger_type, covered=has_trim and has_add)

        last_reviewed = _frontmatter_field(content, "last_reviewed")
        is_stale = True
        if last_reviewed:
            try:
                dt = datetime.strptime(last_reviewed[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                is_stale = (now - dt).days > staleness_days
            except ValueError:
                is_stale = True
        if is_stale:
            stale.append(ticker)

    total = len(held)
    return {
        "total_positions": total,
        "trim_covered": total - len(no_trim),
        "add_covered": total - len(no_add),
        "no_trim_level": no_trim,
        "no_add_level": no_add,
        "stale_review": sorted(stale),
        "staleness_threshold_days": staleness_days,
        "no_thesis": sorted(no_thesis),
        "trigger_type_by_ticker": trigger_type_by_ticker,
        "coverage_by_type": coverage_by_type,
    }


def format_footer_line(coverage):
    total = coverage["total_positions"]
    return "Levels: %d/%d trim, %d/%d add, %d stale" % (
        coverage["trim_covered"], total, coverage["add_covered"], total, len(coverage["stale_review"]),
    )
