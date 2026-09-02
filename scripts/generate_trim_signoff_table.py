"""Generate trim-level sign-off table for Prompt 1 Step 2 (stdout only, no writes)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tasks.build_crosshairs import (
    REASON_NEAR_TRIM,
    _style_size_ceiling_pct,
    _trim_trigger_role,
    holdings_unrealized_pct_fraction_to_pct_points,
    holdings_weight_fraction_to_pct_points,
    produce_crosshairs,
    resolve_trigger_type,
)
from utils.level_coverage import TRIGGER_TYPE_FIELDS, compute_level_coverage
from utils.thesis_reader import THESES_DIR, load_frontmatter

_DIRECTIVE_PHRASES = [
    "will not trim",
    "won't trim",
    "do not trim",
    "not a trim candidate",
]


def _directive_quote(text: str) -> str:
    body = text or ""
    for line in body.splitlines():
        low = line.lower()
        for p in _DIRECTIVE_PHRASES:
            if p in low:
                words = line.strip().split()
                return " ".join(words[:15])
    return ""


def _trim_level_from_fm(fm: dict, trigger_type: str) -> str:
    triggers = fm.get("triggers") if isinstance(fm.get("triggers"), dict) else {}
    trim_field, _add_field = TRIGGER_TYPE_FIELDS.get(trigger_type, ("price_trim_above", "price_add_below"))
    val = triggers.get(trim_field)
    if val not in (None, "", []):
        return str(val)
    return ""


def _tickers_with_trim_level(held_tickers: list[str], level_coverage: dict) -> list[str]:
    no_trim = set(level_coverage.get("no_trim_level") or [])
    return sorted(t for t in held_tickers if t not in no_trim)


def main() -> None:
    result = produce_crosshairs(read_sheets_if_needed=True)
    by_ticker = {item.ticker: item for item in result.items}
    held_rows = {}
    try:
        import config
        from tasks.build_command_center import _read_records
        from tasks.build_crosshairs import _holdings_map, _valuation_map
        from utils.sheet_readers import get_gspread_client

        ss = get_gspread_client().open_by_key(config.PORTFOLIO_SHEET_ID)
        holdings_rows = _read_records(ss, config.TAB_HOLDINGS_CURRENT)
        val_rows = _read_records(ss, config.TAB_VALUATION_CARD)
        held_rows = _holdings_map(holdings_rows)
        val_map = _valuation_map(val_rows)
        held_tickers = sorted(held_rows.keys())
        level_coverage = compute_level_coverage(held_tickers)
    except Exception as e:
        print(f"Sheet read failed: {e}", file=sys.stderr)
        sys.exit(1)

    rows: list[tuple] = []
    for ticker in _tickers_with_trim_level(held_tickers, level_coverage):
        path = THESES_DIR / f"{ticker}_thesis.md"
        text = path.read_text(encoding="utf-8")
        fm = load_frontmatter(text) or {}
        vdata = val_map.get(ticker, {})
        trigger_type = resolve_trigger_type(ticker, vdata, level_coverage)
        trim_level = _trim_level_from_fm(fm, trigger_type)
        item = by_ticker.get(ticker)
        hrow = held_rows.get(ticker) or {}

        if item is not None and item.dist_trim is not None:
            dist_trim = f"{item.dist_trim:+.1%}"
            rank_score = item.rank_score
            reason = item.reason_code
            override = item.override_tag or ""
        elif item is not None:
            dist_trim = "not in band"
            rank_score = item.rank_score
            reason = item.reason_code
            override = item.override_tag or ""
        else:
            dist_trim = "not in band"
            rank_score = 9999.0
            reason = ""
            override = ""

        weight_pp = holdings_weight_fraction_to_pct_points(hrow.get("Weight"))
        unreal_pp = holdings_unrealized_pct_fraction_to_pct_points(hrow.get("Unrealized G/L %"))
        ceiling = _style_size_ceiling_pct(ticker)
        headroom = ""
        if weight_pp is not None and ceiling:
            headroom = f"{min(weight_pp / ceiling, 1.0):.2f}"

        quote = _directive_quote(text)
        rows.append(
            (
                rank_score,
                ticker,
                trigger_type,
                trim_level,
                dist_trim,
                f"{weight_pp:.2f}" if weight_pp is not None else "",
                ceiling,
                headroom,
                f"{unreal_pp:.1f}" if unreal_pp is not None else "",
                quote or "—",
                _trim_trigger_role(ticker),
                reason,
                override,
            )
        )

    rows.sort(key=lambda r: r[0])
    hdr = (
        "rank_score | Ticker | trigger_type | trim | dist_trim | weight% | ceiling% | "
        "headroom | unrealized% | directive | role | reason | override"
    )
    print(hdr)
    print("-" * len(hdr))
    for rank, t, tt, trim, dist, w, c, h, u, q, role, reason, override in rows:
        rank_disp = f"{rank:.4f}" if rank < 9999 else "—"
        print(
            f"{rank_disp} | {t} | {tt} | {trim} | {dist} | {w} | {c} | {h} | {u} | {q} | "
            f"{role} | {reason or '—'} | {override or '—'}"
        )


if __name__ == "__main__":
    main()
