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
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

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
four documents: this prompt, `portfolio.md` (positions, tax lots, recent
rotations, stamped with a data fingerprint), `podcasts.md` (summaries of the
investment podcasts he follows, most recent first), and `theses.md` (a digest of
his written investment thesis for each position, with style tags and size
ceilings).

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
   with what he has recently been doing per the transaction logs.

6. **Current events check.** If you have web access, look up current news for
   his foreign and EM holdings (currency moves, policy, geopolitics) and for
   any position where the podcasts hint at a live situation. Cite sources. If
   you do not have web access, list the specific questions he should check.

7. **The obvious move.** End with a short section titled "The obvious move":
   the single most coherent next action (or deliberate non-action) given
   everything above, in plain language, followed by the two or three open
   questions he should resolve before acting.

## Ground rules

- Be candid and specific. He wants pushback, not validation.
- Anchor every claim to a ticker, weight, or source. No generic market
  commentary.
- Respect his style: small steps, rotations not liquidations, strategic cash is
  intentional and not idle money.
- All data in portfolio.md is read-only truth as of its fingerprint timestamp.
  If something looks wrong or internally inconsistent, flag it rather than
  silently working around it.
"""


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


def build_portfolio_md(bundle):
    md = bundle.get("_market_data", {})
    positions = md.get("positions", [])
    tax_lots = md.get("tax_lots", [])
    rotations = bundle.get("recent_rotations", [])

    lines = []
    lines.append("# Portfolio — %s" % bundle.get("timestamp_utc", "unknown"))
    lines.append("")
    lines.append("composite_hash: %s" % bundle.get("composite_hash", "unknown"))
    lines.append("bundle_timestamp_utc: %s" % bundle.get("timestamp_utc", "unknown"))
    lines.append("total_value: %s" % md.get("total_value", "unknown"))
    lines.append("")

    lines.append("## Positions")
    lines.append("")
    lines.append("| Ticker | Market Value | Weight % | Cost Basis | Unrealized G/L $ | Unrealized G/L % | Asset Class |")
    lines.append("|---|---|---|---|---|---|---|")

    sorted_positions = sorted(
        positions, key=lambda p: p.get("market_value", 0) or 0, reverse=True
    )
    for p in sorted_positions:
        mv = p.get("market_value", 0) or 0
        cb = p.get("cost_basis", 0) or 0
        gl_dollar = mv - cb
        gl_pct = (gl_dollar / cb * 100.0) if cb else 0.0
        lines.append(
            "| %s | %.2f | %.2f | %.2f | %.2f | %.2f | %s |"
            % (
                p.get("ticker", ""),
                mv,
                p.get("weight_pct", 0) or 0,
                cb,
                gl_dollar,
                gl_pct,
                p.get("asset_class", ""),
            )
        )

    lines.append("")
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


def parse_summary_date(filename):
    m = re.match(r"^(\d{4}-\d{2}-\d{2})_", filename)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


def build_podcasts_md(days):
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

    lines = []
    start_date = today.strftime("%Y-%m-%d")
    if selected:
        oldest = min(d for d, _ in selected).strftime("%Y-%m-%d")
    else:
        oldest = start_date
    lines.append(
        "# Podcast Summaries — %s to %s (%d files)" % (oldest, start_date, len(selected))
    )
    lines.append("")

    bodies = []
    for _, path in selected:
        with open(path, "r", encoding="utf-8") as f:
            bodies.append(f.read().strip())

    if bodies:
        lines.append("\n\n---\n\n".join(bodies))
    else:
        lines.append("(no podcast summaries found in the selected date range)")

    return to_ascii("\n".join(lines) + "\n")


def extract_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = text[m.end():]
    fm = {}
    for line in fm_text.splitlines():
        km = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if km:
            key = km.group(1)
            val = km.group(2).strip().strip("'\"")
            fm[key] = val
    return fm, body


def strip_regions(text):
    return re.sub(r"<!--\s*region:.*?endregion:.*?-->", "", text, flags=re.DOTALL)


def extract_section(body, heading):
    pattern = r"^##\s+" + re.escape(heading) + r".*?\n(.*?)(?=^##\s|\Z)"
    m = re.search(pattern, body, re.DOTALL | re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip()


def first_paragraph(section_text):
    if not section_text:
        return None
    parts = re.split(r"\n\s*\n", section_text.strip())
    return parts[0].strip() if parts else None


def extract_key_value(section_text, key):
    if not section_text:
        return None
    m = re.search(r"^" + re.escape(key) + r":\s*(.*)$", section_text, re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip()


def build_theses_md(styles_path):
    lines = []

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

    thesis_files = sorted(glob.glob(os.path.join("vault", "theses", "*_thesis.md")))
    for path in thesis_files:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        fm, body = extract_frontmatter(raw)
        body = strip_regions(body)

        ticker = fm.get("ticker") or os.path.basename(path).replace("_thesis.md", "")
        style = fm.get("style", "(missing)")
        last_reviewed = fm.get("last_reviewed", "(missing)")

        scaling_section = extract_section(body, "Scaling State")
        next_step = extract_key_value(scaling_section, "next_step")
        if next_step is None:
            next_step = "(missing)"

        rotation_section = extract_section(body, "Rotation Priority")
        priority = extract_key_value(rotation_section, "priority")
        if priority is None:
            priority = "(missing)"

        core_section = extract_section(body, "Core Thesis")
        core_para = first_paragraph(core_section)
        if core_para is None:
            core_para = "(missing)"

        lines.append(
            "### %s — style: %s | scaling: %s | priority: %s | reviewed: %s"
            % (ticker, style, next_step, priority, last_reviewed)
        )
        lines.append(core_para)
        lines.append("")

    return to_ascii("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Export AI portfolio briefing package.")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--out", type=str, default="exports")
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

    portfolio_md = build_portfolio_md(bundle)
    podcasts_md = build_podcasts_md(args.days)
    theses_md = build_theses_md(os.path.join("data", "styles.json"))
    prompt_md = PROMPT_PAYLOAD.replace("{DATE}", now.strftime("%Y-%m-%d"))

    submit_me_md = "\n\n---\n\n".join([prompt_md, portfolio_md, podcasts_md, theses_md])

    file_map = {
        "prompt.md": prompt_md,
        "portfolio.md": portfolio_md,
        "podcasts.md": podcasts_md,
        "theses.md": theses_md,
        "SUBMIT_ME.md": submit_me_md,
    }

    sizes = {}
    for name, content in file_map.items():
        path = os.path.join(pkg_dir, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        sizes[name] = os.path.getsize(path)

    manifest = {
        "composite_hash": bundle.get("composite_hash"),
        "bundle_path": bundle_path,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "days_window": args.days,
        "files": sizes,
    }
    manifest_path = os.path.join(pkg_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
    sizes["manifest.json"] = os.path.getsize(manifest_path)

    print("Package: %s" % pkg_dir)
    for name, size in sizes.items():
        print("  %s: %d bytes" % (name, size))

    try:
        os.startfile(os.path.abspath(pkg_dir))
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
