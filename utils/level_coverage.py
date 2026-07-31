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


def _frontmatter_field(content, key):
    """First `key: value` line anywhere in the file (top-level or nested
    under `triggers:`), tolerant of quotes, leading indentation, and a
    trailing `# comment` (thesis triggers are commented liberally, e.g.
    `price_trim_above:   # set once position is sized`, which is a blank
    value, not a value of "# set once position is sized")."""
    m = re.search(r"^\s*" + re.escape(key) + r":\s*['\"]?([^\n'\"]*)['\"]?\s*$", content, re.MULTILINE)
    if not m:
        return None
    val = m.group(1).split("#", 1)[0].strip()
    return val or None


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

    for ticker in held:
        content = thesis_by_ticker.get(ticker)
        if content is None:
            no_thesis.append(ticker)
            no_trim.append(ticker)
            no_add.append(ticker)
            stale.append(ticker)
            continue

        if not _frontmatter_field(content, "price_trim_above"):
            no_trim.append(ticker)
        if not _frontmatter_field(content, "price_add_below"):
            no_add.append(ticker)

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
    }


def format_footer_line(coverage):
    total = coverage["total_positions"]
    return "Levels: %d/%d trim, %d/%d add, %d stale" % (
        coverage["trim_covered"], total, coverage["add_covered"], total, len(coverage["stale_review"]),
    )
