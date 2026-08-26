"""
Standalone thesis-file lint: reports drift-detection hazards in vault/theses/
without touching anything. Read-only, no writes, no Sheets access, no network.

Checks (per file):
  1. Stale prose weight   -- a prose current-allocation claim that disagrees
                             with <!-- region:position_state -->, the sole
                             machine-readable source of truth for weight.
  2. Duplicate state values -- a `priority:`/`next_step:` value present in
                             more than one section (the GLD failure mode:
                             a file that can answer the same question twice
                             will eventually answer it two different ways).
  3. Combined headers     -- "## Scaling State & Priority" or similar,
                             which parses today only by regex accident
                             (extract_section() matches on a prefix).
  4. Unresolved [BILL] placeholders -- informational, not a failure. They
                             are deliberate: Bill's decisions, not ours.
  5. Stale review dates   -- last_reviewed older than 90 days.
  6. Unparseable frontmatter under ruamel -- same loader as ThesisManager /
                             vault sync. Catches duplicate YAML keys that the
                             flat-line parser silently misses (NOW 2026-08-11).

This is a report, not a gate: it always exits 0. Wiring any of this into
export_ai_briefing.py's preflight is deliberately deferred to a later batch,
after that exporter survives its first unattended run.

Usage:
    python tasks/lint_theses.py [--vault vault/theses]
"""

import argparse
import glob
import os
import re
import sys
from datetime import datetime

# Allow `python tasks/lint_theses.py` from repo root
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

STALENESS_DAYS = 90

# Phrasing variants for a prose claim about *current* allocation weight.
# Deliberately anchored to "current"/"currently"/"is" framings, not to
# every percentage in the file -- a target weight, a ceiling, or a trigger
# level is not a claim about the present state and must not be flagged.
_WEIGHT_CLAIM_RE = re.compile(
    r"(?:current(?:ly)?\s+allocation|current(?:ly)?|allocation\s+is|position\s+is)"
    r"\D{0,15}?(\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

_COMBINED_HEADER_RE = re.compile(
    r"^##\s+(Scaling State\s*(?:&|and)\s*(?:Rotation\s+)?Priority.*|"
    r"Rotation Priority\s*(?:&|and)\s*Scaling State.*)$",
    re.IGNORECASE | re.MULTILINE,
)


def _frontmatter(text):
    from utils.thesis_reader import extract_frontmatter_flat
    return extract_frontmatter_flat(text)


def _region_weight_pct(text):
    m = re.search(
        r"<!--\s*region:position_state\s*-->.*?\*\*Current Allocation:\*\*\s*([0-9.]+)%",
        text, re.DOTALL,
    )
    return float(m.group(1)) if m else None


def _line_number(text, char_offset):
    return text.count("\n", 0, char_offset) + 1


def lint_file(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    fm, body = _frontmatter(text)
    ticker = fm.get("ticker") or os.path.basename(path).replace("_thesis.md", "")
    findings = []
    # `body` starts after the frontmatter block, so a line number computed
    # against `body` alone undercounts every line by the frontmatter's own
    # length. Offset every reported line number back to real file line
    # numbers via this.
    fm_offset = len(text) - len(body)

    def _file_line(pos_in_body):
        return _line_number(text, fm_offset + pos_in_body)

    # 1. Stale prose weight
    region_weight = _region_weight_pct(body)
    fm_weight = None
    if fm.get("current_allocation"):
        try:
            fm_weight = float(fm["current_allocation"].rstrip("%"))
        except ValueError:
            pass
    authoritative = region_weight if region_weight is not None else fm_weight

    if authoritative is not None:
        # Region spans are machine-written and legitimately restate the same
        # figure -- exclude matches inside them, but scan for line numbers
        # against the original `body` (not a stripped copy) so reported
        # line numbers are usable.
        region_spans = [
            (m.start(), m.end())
            for m in re.finditer(r"<!--\s*region:.*?endregion:.*?-->", body, re.DOTALL)
        ]

        def _in_region(pos):
            return any(start <= pos < end for start, end in region_spans)

        for m in _WEIGHT_CLAIM_RE.finditer(body):
            if _in_region(m.start()):
                continue
            # A negative percentage ("~-5.9%") is structurally never a
            # current-weight claim in this vault's convention -- it's
            # almost always an unrealized G/L% mention sitting next to the
            # word "currently". \D{0,15}? doesn't capture the sign, so check
            # the raw slice immediately before the digits.
            prefix = body[max(0, m.start(1) - 2):m.start(1)]
            if "-" in prefix:
                continue
            claimed = float(m.group(1))
            if abs(claimed - authoritative) > 0.05:
                line_no = _file_line(m.start())
                findings.append(
                    "STALE WEIGHT (line %d): prose claims %.2f%%, "
                    "region:position_state says %.2f%%"
                    % (line_no, claimed, authoritative)
                )

    # 2. Duplicate state values (priority: / next_step: in >1 section)
    for key in ("priority", "next_step"):
        key_variant = key.replace("_", "[ _]")
        pattern = re.compile(
            r"^\s*(?:[-*]\s*)?\**\s*(?:" + key_variant + r")\s*\**\s*:\s*(.+)$",
            re.IGNORECASE | re.MULTILINE,
        )
        hits = [m for m in pattern.finditer(body) if m.group(1).strip()]
        if len(hits) > 1:
            lines = ", ".join(str(_file_line(h.start())) for h in hits)
            findings.append(
                "DUPLICATE '%s:' value on lines %s -- file can answer the "
                "same question more than one way" % (key, lines)
            )

    # 3. Combined headers
    for m in _COMBINED_HEADER_RE.finditer(body):
        line_no = _file_line(m.start())
        findings.append(
            "COMBINED HEADER (line %d): '## %s' -- parses today only by "
            "regex accident (extract_section matches on a heading prefix)"
            % (line_no, m.group(1).strip())
        )

    # 4. Unresolved [BILL] placeholders (informational)
    bill_count = len(re.findall(r"\[BILL\]", body))

    # 5. Stale review date
    stale_review = None
    last_reviewed = fm.get("last_reviewed")
    if last_reviewed:
        try:
            dt = datetime.strptime(last_reviewed[:10], "%Y-%m-%d")
            age_days = (datetime.now() - dt).days
            if age_days > STALENESS_DAYS:
                stale_review = age_days
        except ValueError:
            pass
    if stale_review is not None:
        findings.append(
            "STALE REVIEW: last_reviewed is %d days old (> %d day threshold)"
            % (stale_review, STALENESS_DAYS)
        )

    # 6. Frontmatter must parse under the same ruamel path as vault sync
    try:
        from pathlib import Path as _Path
        from utils.thesis_utils import ThesisManager
        _data, fm_err = ThesisManager(_Path(path)).get_frontmatter_safe()
        if fm_err is not None:
            findings.append("UNPARSEABLE FRONTMATTER: %s" % fm_err)
    except Exception as e:
        findings.append("UNPARSEABLE FRONTMATTER: %s" % e)

    return {
        "ticker": ticker,
        "path": path,
        "findings": findings,
        "bill_count": bill_count,
    }


def main():
    parser = argparse.ArgumentParser(description="Standalone thesis-file lint (read-only, report-only).")
    parser.add_argument("--vault", type=str, default="vault/theses")
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(args.vault, "*_thesis.md")))
    if not files:
        print("No thesis files found under %s" % args.vault)
        return

    total_findings = 0
    total_bill = 0
    files_with_findings = 0

    print("=== Thesis Lint: %d file(s) under %s ===\n" % (len(files), args.vault))

    for path in files:
        result = lint_file(path)
        total_bill += result["bill_count"]
        if result["findings"]:
            files_with_findings += 1
            total_findings += len(result["findings"])
            print("%s (%s):" % (result["ticker"], path))
            for f in result["findings"]:
                print("  - %s" % f)
        if result["bill_count"]:
            print("%s: %d unresolved [BILL] placeholder(s) (informational)"
                  % (result["ticker"], result["bill_count"]))

    print(
        "\n--- Summary: %d file(s) with findings, %d finding(s) total, "
        "%d unresolved [BILL] placeholder(s) across the vault ---"
        % (files_with_findings, total_findings, total_bill)
    )
    print("Report only -- exit 0 regardless of findings.")


if __name__ == "__main__":
    main()
