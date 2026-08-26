"""
tasks/detect_undocumented_changes.py — Read-only decision-capture detector.

Compares the briefing being built against the most recent prior briefing's
portfolio.md and emits findings for undocumented entries/exits/resizes.
Never writes Trade_Log, Holdings, Target_Allocation, or Sheets.
"""

from __future__ import annotations

import glob
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parent.parent

CASH = {"CASH_MANUAL"}
WEIGHT_PP_THRESHOLD = 0.50
RELATIVE_PCT_THRESHOLD = 0.25  # 25% relative
MAX_FINDINGS = 5

_POS_ROW_RE = re.compile(
    r"^\|\s*([A-Z][A-Z0-9./-]*)\s*\|\s*[^|]*\|\s*[^|]*\|\s*([0-9.]+)\s*\|"
)
_REVIEW_DATE_RE = re.compile(r"^\s*-\s*(\d{4}-\d{2}-\d{2})\b")
_TXN_DATE_RE = re.compile(r"^\s*-\s*(\d{4}-\d{2}-\d{2})\s*:")


def _parse_portfolio_weights(portfolio_md: str) -> dict[str, float]:
    """Parse ## Positions table → ticker -> weight %."""
    out: dict[str, float] = {}
    in_positions = False
    for line in portfolio_md.splitlines():
        if line.startswith("## Positions"):
            in_positions = True
            continue
        if in_positions and line.startswith("## "):
            break
        if not in_positions:
            continue
        m = _POS_ROW_RE.match(line)
        if not m:
            continue
        ticker = m.group(1).strip().upper()
        if ticker in CASH or ticker == "TICKER":
            continue
        try:
            out[ticker] = float(m.group(2))
        except ValueError:
            continue
    return out


def _pkg_stamp(name: str) -> Optional[datetime]:
    # ai_briefing_YYYY-MM-DD_HHMMSS
    m = re.match(r"ai_briefing_(\d{4}-\d{2}-\d{2})_(\d{6})", name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y-%m-%d%H%M%S")
    except ValueError:
        return None


def find_prior_briefing(
    exports_dir: str | Path = "exports",
    *,
    current_pkg: Optional[str] = None,
) -> Optional[Path]:
    """Most recent prior ai_briefing_* dir that has portfolio.md."""
    root = Path(exports_dir)
    if not root.is_dir():
        return None
    candidates: list[tuple[datetime, Path]] = []
    for p in root.iterdir():
        if not p.is_dir() or not p.name.startswith("ai_briefing_"):
            continue
        if current_pkg and p.name == current_pkg:
            continue
        stamp = _pkg_stamp(p.name)
        if stamp is None:
            continue
        if not (p / "portfolio.md").is_file():
            continue
        candidates.append((stamp, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    # If current_pkg stamp is known, pick the newest strictly older
    if current_pkg:
        cur = _pkg_stamp(current_pkg)
        if cur is not None:
            older = [(s, p) for s, p in candidates if s < cur]
            if older:
                return older[0][1]
    return candidates[0][1]


def _thesis_path(ticker: str) -> Path:
    return _ROOT / "vault" / "theses" / f"{ticker}_thesis.md"


def _thesis_exists(ticker: str) -> bool:
    return _thesis_path(ticker).is_file()


def _read_thesis(ticker: str) -> Optional[str]:
    p = _thesis_path(ticker)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return None


def _extract_region(text: str, name: str) -> str:
    pat = re.compile(
        rf"<!-- region:{name} -->\s*\n(.*?)<!-- endregion:{name} -->",
        re.DOTALL,
    )
    m = pat.search(text or "")
    return m.group(1) if m else ""


def _review_log_dates(text: str) -> list[str]:
    body = text or ""
    idx = body.find("## Review Log")
    if idx < 0:
        return []
    chunk = body[idx + len("## Review Log"):]
    # Stop at next markdown H2 (do not bleed into transaction_log regions).
    nxt = re.search(r"\n## ", chunk)
    if nxt:
        chunk = chunk[: nxt.start()]
    dates: list[str] = []
    for line in chunk.splitlines():
        m = _REVIEW_DATE_RE.match(line)
        if m:
            dates.append(m.group(1))
    return dates


def _txn_dates_in_window(text: str, start: str, end: str) -> list[str]:
    """Buy/sell dates in transaction_log inside [start, end] inclusive (YYYY-MM-DD)."""
    region = _extract_region(text or "", "transaction_log")
    hits: list[str] = []
    for line in region.splitlines():
        m = _TXN_DATE_RE.match(line)
        if not m:
            continue
        d = m.group(1)
        if start <= d <= end and re.search(r"\b(Buy|Sell)\b", line, re.I):
            hits.append(d)
    return hits


def _scaling_hint(text: str) -> str:
    if not text:
        return "(no thesis)"
    m = re.search(r"next_step:\s*(.+)", text)
    if m:
        return m.group(1).strip()[:80]
    return "(missing)"


def _relative_delta(prior: float, current: float) -> Optional[float]:
    if prior == 0:
        return None if current == 0 else float("inf")
    return abs(current - prior) / abs(prior)


def detect_undocumented_changes(
    *,
    current_weights: dict[str, float],
    prior_weights: Optional[dict[str, float]],
    prior_pkg_name: Optional[str],
    current_date: str,
    prior_date: Optional[str],
    warning: Optional[str] = None,
) -> dict[str, Any]:
    """
    Core detector. current_weights/prior_weights are ticker -> weight %.
    Returns undocumented_changes manifest block.
    """
    findings: list[dict[str, Any]] = []
    suppress_log: list[dict[str, Any]] = []

    if prior_weights is None:
        return {
            "compared_against": None,
            "warning": warning or "No prior briefing available — undocumented_changes empty.",
            "findings": [],
            "suppress_log": [],
        }

    cur_set = set(current_weights) - CASH
    pri_set = set(prior_weights) - CASH
    window_start = prior_date or current_date
    window_end = current_date

    # NEW_POSITION_NO_THESIS
    for t in sorted(cur_set - pri_set):
        if not _thesis_exists(t):
            findings.append({
                "code": "NEW_POSITION_NO_THESIS",
                "ticker": t,
                "detail": (
                    f"Present at {current_weights[t]:.2f}% now; absent in prior. "
                    f"No vault/theses/{t}_thesis.md."
                ),
                "question": f"Why was {t} entered, and what is the working thesis?",
                "_sort": window_end,
            })

    # EXITED_POSITION_LIVE_THESIS
    for t in sorted(pri_set - cur_set):
        if _thesis_exists(t):
            text = _read_thesis(t) or ""
            findings.append({
                "code": "EXITED_POSITION_LIVE_THESIS",
                "ticker": t,
                "detail": (
                    f"Held {prior_weights[t]:.2f}% on prior ({prior_pkg_name}), "
                    f"absent now. Thesis live, scaling state "
                    f"{_scaling_hint(text)!r}."
                ),
                "question": (
                    f"Completed exit for {t}, or a step in the reduce path that zeroed out?"
                ),
                "_sort": window_end,
            })

    # MATERIAL_RESIZE_NO_REVIEW
    for t in sorted(cur_set & pri_set):
        prior_w = prior_weights[t]
        cur_w = current_weights[t]
        d_pp = abs(cur_w - prior_w)
        rel = _relative_delta(prior_w, cur_w)
        if d_pp < WEIGHT_PP_THRESHOLD:
            continue
        if rel is None or rel < RELATIVE_PCT_THRESHOLD:
            continue

        text = _read_thesis(t)
        if text is None:
            # No thesis — exit/new detectors cover extremes; skip resize
            continue

        txns = _txn_dates_in_window(text, window_start, window_end)
        if not txns:
            suppress_log.append({
                "ticker": t,
                "decision": "suppress_market_move",
                "delta_pp": round(d_pp, 4),
                "rel": None if rel == float("inf") else round(rel, 4),
                "prior_wt": prior_w,
                "current_wt": cur_w,
                "txn_in_window": [],
            })
            continue

        review_dates = _review_log_dates(text)
        # Need a Review Log entry on/after first day of the move (= earliest txn
        # in window, else prior_date).
        first_move = min(txns) if txns else window_start
        has_review = any(d >= first_move for d in review_dates)
        if has_review:
            suppress_log.append({
                "ticker": t,
                "decision": "suppress_reviewed",
                "delta_pp": round(d_pp, 4),
                "rel": round(rel, 4),
                "first_move": first_move,
                "review_dates": review_dates[:5],
            })
            continue

        findings.append({
            "code": "MATERIAL_RESIZE_NO_REVIEW",
            "ticker": t,
            "detail": (
                f"Weight {prior_w:.2f}% -> {cur_w:.2f}% "
                f"(d {cur_w - prior_w:+.2f}pp, rel {rel:.0%}). "
                f"Txn in window on {', '.join(txns)}; no Review Log on/after {first_move}."
            ),
            "question": (
                f"What was the decision behind resizing {t} "
                f"({prior_w:.2f}% -> {cur_w:.2f}%)?"
            ),
            "_sort": first_move,
        })
        suppress_log.append({
            "ticker": t,
            "decision": "emit_resize",
            "delta_pp": round(d_pp, 4),
            "rel": round(rel, 4),
            "txn_in_window": txns,
        })

    findings.sort(key=lambda f: f.get("_sort", ""), reverse=True)
    capped = findings[:MAX_FINDINGS]
    overflow = len(findings) > MAX_FINDINGS

    clean: list[dict[str, Any]] = []
    for f in capped:
        clean.append({
            "code": f["code"],
            "ticker": f["ticker"],
            "detail": f["detail"],
            "question": f["question"],
        })

    block: dict[str, Any] = {
        "compared_against": prior_pkg_name,
        "findings": clean,
        "suppress_log": suppress_log,
    }
    if warning:
        block["warning"] = warning
    if overflow:
        block["system"] = (
            f"SYSTEM: {len(findings)} undocumented_changes findings "
            f"(cap {MAX_FINDINGS}) — detector likely miscalibrated."
        )
    return block


def detect_for_export(
    *,
    current_portfolio_md: str,
    exports_dir: str | Path = "exports",
    current_pkg_name: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> dict[str, Any]:
    """High-level helper used by export_ai_briefing."""
    current_weights = _parse_portfolio_weights(current_portfolio_md)
    current_date = (generated_at or datetime.now().strftime("%Y-%m-%d"))[:10]

    prior = find_prior_briefing(exports_dir, current_pkg=current_pkg_name)
    if prior is None:
        return detect_undocumented_changes(
            current_weights=current_weights,
            prior_weights=None,
            prior_pkg_name=None,
            current_date=current_date,
            prior_date=None,
        )

    try:
        prior_md = (prior / "portfolio.md").read_text(encoding="utf-8")
    except OSError as e:
        return detect_undocumented_changes(
            current_weights=current_weights,
            prior_weights=None,
            prior_pkg_name=None,
            current_date=current_date,
            prior_date=None,
            warning=f"Failed to read prior portfolio.md: {e}",
        )

    prior_weights = _parse_portfolio_weights(prior_md)
    stamp = _pkg_stamp(prior.name)
    prior_date = stamp.strftime("%Y-%m-%d") if stamp else None
    return detect_undocumented_changes(
        current_weights=current_weights,
        prior_weights=prior_weights,
        prior_pkg_name=prior.name,
        current_date=current_date,
        prior_date=prior_date,
    )


if __name__ == "__main__":
    import json
    import sys

    # CLI: python tasks/detect_undocumented_changes.py [current_pkg] [prior_pkg]
    exports = _ROOT / "exports"
    args = sys.argv[1:]
    if len(args) >= 1:
        cur_dir = exports / args[0]
    else:
        # newest
        dirs = sorted(
            [p for p in exports.glob("ai_briefing_*") if (p / "portfolio.md").is_file()],
            key=lambda p: _pkg_stamp(p.name) or datetime.min,
            reverse=True,
        )
        cur_dir = dirs[0] if dirs else None
    if cur_dir is None or not cur_dir.is_dir():
        print("No current briefing found", file=sys.stderr)
        sys.exit(1)

    cur_md = (cur_dir / "portfolio.md").read_text(encoding="utf-8")
    if len(args) >= 2:
        prior_dir = exports / args[1]
        prior_md = (prior_dir / "portfolio.md").read_text(encoding="utf-8")
        stamp = _pkg_stamp(prior_dir.name)
        block = detect_undocumented_changes(
            current_weights=_parse_portfolio_weights(cur_md),
            prior_weights=_parse_portfolio_weights(prior_md),
            prior_pkg_name=prior_dir.name,
            current_date=(_pkg_stamp(cur_dir.name) or datetime.now()).strftime("%Y-%m-%d"),
            prior_date=stamp.strftime("%Y-%m-%d") if stamp else None,
        )
    else:
        block = detect_for_export(
            current_portfolio_md=cur_md,
            exports_dir=exports,
            current_pkg_name=cur_dir.name,
            generated_at=(_pkg_stamp(cur_dir.name) or datetime.now()).isoformat(),
        )
    print(json.dumps(block, indent=2))
