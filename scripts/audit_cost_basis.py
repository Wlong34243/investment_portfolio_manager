"""Audit and update cost basis values in thesis files against RealCostBasis.txt."""
import re
from pathlib import Path

THESES_DIR = Path("vault/theses")
REAL_BASIS_FILE = THESES_DIR / "RealCostBasis.txt"


def parse_real_basis():
    real_basis = {}
    for line in REAL_BASIS_FILE.read_text().splitlines():
        m = re.match(r'\|\s*\*\*([A-Z0-9_\\]+)\*\*\s*\|\s*([\d.]+)', line)
        if m:
            ticker = m.group(1).replace("\\", "_")
            real_basis[ticker] = m.group(2)
    return real_basis


def find_cost_basis_line(lines):
    """Return (line_index, line_text) for the Cost basis line inside ## Entry Context."""
    in_entry = False
    for i, line in enumerate(lines):
        if line.strip() == "## Entry Context":
            in_entry = True
            continue
        if in_entry and line.strip().startswith("##"):
            break
        if in_entry and re.search(r"[Cc]ost\s*[Bb]asis\s*:", line):
            return i, line
    return None, None


def audit():
    real_basis = parse_real_basis()
    mismatches = []
    in_sync = []
    skipped = []

    for md in sorted(THESES_DIR.glob("*_thesis.md")):
        ticker = md.name.split("_")[0].upper()
        if ticker not in real_basis:
            skipped.append(f"{ticker} (not in RealCostBasis.txt)")
            continue

        content = md.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        idx, line_text = find_cost_basis_line(lines)

        if idx is None:
            skipped.append(f"{ticker} (no Cost basis line in Entry Context)")
            continue

        m = re.search(r"\$\s*~?\s*(\d[\d,]*(?:\.\d+)?)", line_text)
        if not m:
            skipped.append(f"{ticker} (no dollar amount in: {line_text.strip()[:60]})")
            continue

        current = m.group(1).replace(",", "")
        expected = real_basis[ticker]
        if current == expected:
            in_sync.append(ticker)
        else:
            mismatches.append((ticker, current, expected, idx, line_text))

    return mismatches, in_sync, skipped


def update_files(mismatches, dry_run=True):
    for ticker, current, expected, idx, line_text in mismatches:
        md = THESES_DIR / f"{ticker}_thesis.md"
        content = md.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        old_line = lines[idx]
        # Replace the numeric value after $, preserving ~ prefix and surrounding text
        new_line = re.sub(
            r"(\$\s*~?\s*)\d[\d,]*(?:\.\d+)?",
            lambda m: m.group(1) + expected,
            old_line,
            count=1,
        )
        lines[idx] = new_line

        if dry_run:
            print(f"  [dry] {ticker}: {old_line.strip()[:70]}")
            print(f"         -> {new_line.strip()[:70]}")
        else:
            md.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"  [done] {ticker}: ${current} -> ${expected}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()

    mismatches, in_sync, skipped = audit()

    print(f"In sync:      {len(in_sync)}")
    print(f"Need update:  {len(mismatches)}")
    print(f"Skipped:      {len(skipped)}")
    print()

    if mismatches:
        print("Changes" + (" (DRY RUN):" if not args.live else ":"))
        update_files(mismatches, dry_run=not args.live)

    if skipped:
        print("\nSkipped:")
        for s in skipped:
            print(f"  {s}")
