"""
One-time utility: add YAML frontmatter to existing thesis files.

Idempotent: skips files that already have frontmatter. Infers ticker
from filename (<TICKER>_thesis.md). Leaves style and
framework_preference blank unless overridden via STYLE_OVERRIDES.

Usage:
    python scripts/add_thesis_frontmatter.py --dry-run
    python scripts/add_thesis_frontmatter.py --live
"""
import argparse
import re
from pathlib import Path

THESIS_DIR = Path("vault/theses")

# Explicit style + framework overrides for known tickers.
# Leave others blank — fill in during review.
STYLE_OVERRIDES = {
    "UNH": ("garp", "lynch_garp_v1"),
    # Add more as calibration proceeds.
}


def has_frontmatter(text: str) -> bool:
    lines = text.splitlines()
    return bool(lines) and lines[0].strip() == "---"


def build_frontmatter(ticker: str) -> str:
    style, framework = STYLE_OVERRIDES.get(ticker, ("", ""))
    return (
        f"---\n"
        f"ticker: {ticker}\n"
        f"style: {style}\n"
        f"framework_preference: {framework}\n"
        f"entry_date:\n"
        f"last_reviewed:\n"
        f"---\n\n"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Add YAML frontmatter to thesis files that don't have it."
    )
    parser.add_argument("--live", action="store_true", help="Write changes to disk")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    if not args.live and not args.dry_run:
        print("Specify --dry-run or --live")
        return

    live = args.live and not args.dry_run

    pattern = re.compile(r"^([A-Z][A-Z0-9.\-]{0,9})_thesis\.md$")
    updated = 0
    skipped = 0

    for path in sorted(THESIS_DIR.glob("*_thesis.md")):
        m = pattern.match(path.name)
        if not m:
            continue
        ticker = m.group(1).upper()
        text = path.read_text(encoding="utf-8", errors="replace")
        if has_frontmatter(text):
            skipped += 1
            continue
        new_text = build_frontmatter(ticker) + text
        if live:
            path.write_text(new_text, encoding="utf-8")
        updated += 1
        print(f"{'[live]' if live else '[dry]'} {path.name}: added frontmatter "
              f"(style={STYLE_OVERRIDES.get(ticker, ('',''))[0] or 'blank'})")

    print(f"\nSummary: {updated} updated, {skipped} already had frontmatter")


if __name__ == "__main__":
    main()
