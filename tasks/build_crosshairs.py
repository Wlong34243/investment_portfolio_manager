"""
tasks/build_crosshairs.py — Ranked Crosshairs producer (facts only).

One list feeds two renderers:
  - 0_DASHBOARD top 5 (build_command_center)
  - Decision_View full list (build_decision_view)

Sources: Valuation_Card Trim/Add distances, dislocation scan payload,
utils/level_coverage filesystem gaps. No Agent_Outputs. No buy/sell prose.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config
from utils.level_coverage import compute_level_coverage, TRIGGER_TYPE_FIELDS, DEFAULT_TRIGGER_TYPE

NEAR_BAND_PCT = 0.20  # include NEAR_* when |dist| <= 20% or already through level
TOP_N_DASHBOARD = 5

# NEAR_TRIM rank modifiers (first values; correct from observed output — do not tune pre-ship)
W_CEILING_HEADROOM = 0.05
W_UNREALIZED_LOSS = 0.05

REASON_NEAR_TRIM = "NEAR_TRIM"
REASON_NEAR_ADD = "NEAR_ADD"
REASON_DISLOCATION = "DISLOCATION"
REASON_MISSING_LEVEL = "MISSING_LEVEL"

# trigger_type -> (Valuation_Card column holding the live "current" reading,
# short label for rationale strings, trim direction, add direction).
# Trim/add *field names* (fwd_pe_trim_above, pb_add_below, ...) live in
# utils.level_coverage.TRIGGER_TYPE_FIELDS -- not duplicated here; this map
# is purely about which live metric a NEAR_* evaluation compares against.
#
# direction "rises_through": the band fires once current >= level.
# direction "falls_through": the band fires once current <= level.
# discount_from_high is inverted vs every other type: a *small* discount
# means the price is near its 52w high (-> trim), a *large* discount is the
# buying opportunity (-> add). See prompts/typed_trigger_crosshairs_2026-08-24.md.
METRIC_MAP = {
    "price":             ("Price", "price", "rises_through", "falls_through"),
    "fwd_pe":            ("Forward P/E (yf)", "fwd P/E", "rises_through", "falls_through"),
    "trailing_pe":       ("Trailing P/E", "trailing P/E", "rises_through", "falls_through"),
    "price_to_book":     ("P/B", "P/B", "rises_through", "falls_through"),
    "discount_from_high": ("Discount from 52w High %", "discount", "falls_through", "rises_through"),
}

# "Discount from 52w High %" is written by build_valuation_card.py as a raw
# fraction (e.g. 0.279) and round-trips through the Sheet with a PERCENT
# format; read_gsheet_robust()/coerce_sheet_numeric_series() divides any
# "%"-suffixed cell by 100 again on the way back in, so this reads back as
# 0.279, not 27.9. The thesis-stored trim_below_discount_pct /
# add_above_discount_pct are plain percentage points (IBM: 2.0 / 11.9) --
# without this *100 correction, discount_from_high could never compare
# correctly against its own declared levels.
_METRIC_SCALE = {"discount_from_high": 100.0}

# Sort buckets (lower rank_score = higher on the list)
_BUCKET_NEAR = 0
_BUCKET_DISLOC_HELD = 100
_BUCKET_DISLOC_OTHER = 200
_BUCKET_MISSING = 300
_BUCKET_DOCTRINE_HOLD = 400  # doctrine / add-suspended — visible, ranked out of CC top 5


@dataclass
class CrosshairItem:
    ticker: str
    reason_code: str
    rank_score: float
    mv: Optional[float] = None
    wt: Optional[float] = None
    price: Optional[float] = None
    trim: Optional[float] = None
    add: Optional[float] = None
    dist_trim: Optional[float] = None
    dist_add: Optional[float] = None
    rationale: str = ""
    trigger_type: str = "price"
    # override_tag: HOLD_TAX (doctrine), ADD_SUSPENDED (thesis), TRIM_INFORMATIONAL (thesis trim role)
    override_tag: Optional[str] = None
    doctrine_reason: str = ""
    doctrine_downgraded: bool = False
    # Prompt 9 tax surface (3a/3b/3c measurement). ESTIMATE only; no 3d bound yet.
    days_to_lt: Optional[int] = None
    wash_window_open: bool = False
    wash_disallow_through: Optional[str] = None
    is_tax_hold_runner: bool = False
    # Bound fields reserved — stay None until doctrine method+effective date (Step 2).
    est_tax_cost_low: Optional[float] = None
    est_tax_cost_high: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CrosshairsResult:
    items: list[CrosshairItem]
    as_of: str
    warnings: list[str] = field(default_factory=list)
    dislocation_path: Optional[str] = None

    @property
    def header_line(self) -> str:
        base = f"CROSSHAIRS — as of {self.as_of} — {len(self.items)} items"
        if self.warnings:
            return base + " — SYSTEM: " + "; ".join(self.warnings)
        return base

    def top(self, n: int = TOP_N_DASHBOARD) -> list[CrosshairItem]:
        return self.items[:n]


def _safe_float(val) -> Optional[float]:
    try:
        if val in (None, "", "—"):
            return None
        f = float(val)
        return f if f == f else None  # NaN check
    except (TypeError, ValueError):
        return None


def _safe_float_nonzero(val) -> Optional[float]:
    f = _safe_float(val)
    return f if f else None


def holdings_weight_fraction_to_pct_points(raw) -> Optional[float]:
    """Holdings_Current.Weight (col Q) → percentage points for *_pct comparisons.

    The sheet stores portfolio weight as a fraction (0.0115 = 1.15%).
    Thesis ``style_size_ceiling_pct`` and similar fields are percentage points
    (8.0 = 8%). Always multiply by 100 — no runtime unit guess.

    See PORTFOLIO_SHEET_SCHEMA.md Holdings_Current col Q.
    """
    v = _safe_float(raw)
    if v is None:
        return None
    return v * 100.0


def holdings_unrealized_pct_fraction_to_pct_points(raw) -> Optional[float]:
    """Holdings_Current ``Unrealized G/L %`` (col K) → percentage points for display.

    After ``read_gsheet_robust`` the cell round-trips as a fraction (-0.017 = -1.7%).
    Penalty comparison uses the raw fraction (sign is scale-invariant); this helper
    is for rationale strings and sign-off columns only.
    """
    v = _safe_float(raw)
    if v is None:
        return None
    return v * 100.0


def resolve_trigger_type(
    ticker: str,
    vdata: dict,
    level_coverage: Optional[dict] = None,
) -> str:
    """Declared trigger_type for one ticker: Val_Card 'Trigger Type' column
    first, else level_coverage's trigger_type_by_ticker map, else price
    (backwards-compat default -- matches DEFAULT_TRIGGER_TYPE)."""
    vt = str(vdata.get("Trigger Type") or "").strip()
    if vt in TRIGGER_TYPE_FIELDS:
        return vt
    tbt = (level_coverage or {}).get("trigger_type_by_ticker") or {}
    tt = tbt.get(ticker)
    if tt in TRIGGER_TYPE_FIELDS:
        return tt
    return DEFAULT_TRIGGER_TYPE


def _typed_dist(current: float, level: float, direction: str) -> float:
    """Signed distance, same sign convention the original price formulas
    used: <=0 means already through the level, positive means still
    approaching. 'rises_through' fires once current >= level; 'falls_through'
    fires once current <= level."""
    if direction == "rises_through":
        return (level - current) / current
    return (current - level) / level


def _fmt_metric(trigger_type: str, value: float) -> str:
    if trigger_type == "price":
        return f"${value:.2f}"
    if trigger_type == "discount_from_high":
        return f"{value:.1f}%"
    return f"{value:.2f}"


def format_level(trigger_type: str, value: Optional[float]) -> str:
    """Render a Trim/Add level for display without assuming dollars for a
    non-price trigger_type. Used by Command Center / Decision_View renderers."""
    if value is None:
        return "—"
    return _fmt_metric(trigger_type, value)


def is_trim_side_crosshair(item: CrosshairItem) -> bool:
    """Trim-side signals only — tax facts are noise on add/dislocation rows."""
    return (
        item.reason_code == REASON_NEAR_TRIM
        or item.override_tag == "HOLD_TAX"
        or item.doctrine_downgraded
    )


def format_wash_window_column(item: CrosshairItem) -> str:
    if not is_trim_side_crosshair(item):
        return ""
    if item.wash_window_open and item.wash_disallow_through:
        return f"OPEN through {item.wash_disallow_through}"
    if item.wash_window_open:
        return "OPEN"
    return ""


def format_tax_compact(item: CrosshairItem) -> str:
    """Compact tax cell for 0_DASHBOARD crosshairs top-5 (~40 chars)."""
    if not is_trim_side_crosshair(item):
        return ""
    parts: list[str] = []
    if item.days_to_lt is not None:
        parts.append(f"{item.days_to_lt}d→LT")
    if item.wash_window_open:
        parts.append("wash open")
    if item.est_tax_cost_low is not None or item.est_tax_cost_high is not None:
        lo = item.est_tax_cost_low if item.est_tax_cost_low is not None else 0.0
        hi = item.est_tax_cost_high if item.est_tax_cost_high is not None else lo
        parts.append(f"est ${lo:,.0f}–{hi:,.0f}")
    text = " · ".join(parts)
    return text if len(text) <= 40 else text[:37] + "..."


def resolve_typed_metric(trigger_type: str, hrow: dict, vdata: dict) -> dict:
    """
    Current reading, trim/add levels (already declared-type per
    build_valuation_card.py), and signed distances for one ticker's declared
    trigger_type. ceiling_only or an unknown type returns all-None fields --
    no fallback substitution across types, ever (a missing/non-numeric live
    metric skips NEAR_*, it never borrows another type's reading).
    """
    price = _safe_float(hrow.get("Price")) or None
    out = {
        "trigger_type": trigger_type, "price": price, "current": None,
        "trim": None, "add": None, "dist_trim": None, "dist_add": None,
    }
    spec = METRIC_MAP.get(trigger_type)
    if spec is None:  # ceiling_only, or a type this map doesn't (yet) cover
        return out

    metric_col, _label, trim_dir, add_dir = spec
    if trigger_type == "price":
        current = price
    else:
        current = _safe_float(vdata.get(metric_col))
        scale = _METRIC_SCALE.get(trigger_type)
        if current is not None and scale:
            current *= scale
    out["current"] = current
    if current is None:
        return out

    trim = _safe_float_nonzero(vdata.get("Trim Target"))
    add = _safe_float_nonzero(vdata.get("Add Target"))
    out["trim"] = trim
    out["add"] = add
    if trim:
        out["dist_trim"] = _typed_dist(current, trim, trim_dir)
    if add:
        out["dist_add"] = _typed_dist(current, add, add_dir)
    return out


def _today_utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def find_todays_dislocation_json() -> Optional[str]:
    """Return path to a same-calendar-day (UTC) dislocation JSON, else None."""
    exports = Path(config.EXPORTS_DIR)
    if not exports.is_dir():
        return None
    today = _today_utc_date()
    candidates = sorted(exports.glob("dislocation_scan_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in candidates:
        # Filename: dislocation_scan_2026-08-10T133000Z.json
        name = path.name
        if today in name:
            return str(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            ts = str(payload.get("timestamp_utc", ""))
            if ts.startswith(today):
                return str(path)
        except (OSError, json.JSONDecodeError):
            continue
    return None


def load_dislocation_payload(path: Optional[str] = None) -> tuple[Optional[dict], Optional[str]]:
    path = path or find_todays_dislocation_json()
    if not path:
        return None, None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return payload, path
    except (OSError, json.JSONDecodeError):
        return None, path


def ensure_dislocation_payload(
    *,
    run_if_missing: bool = True,
    live: bool = False,
) -> tuple[Optional[dict], Optional[str]]:
    """
    Prefer today's scan on disk. If missing and run_if_missing, run dislocation_scan.
    """
    payload, path = load_dislocation_payload()
    if payload is not None:
        return payload, path
    if not run_if_missing:
        return None, None
    from tasks.dislocation_scan import run_scan

    result = run_scan(live=live)
    return result["payload"], result["json_path"]


def _holdings_map(holdings_rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    cash = set(getattr(config, "CASH_TICKERS", ()) or ())
    for row in holdings_rows or []:
        ticker = str(row.get("Ticker", "")).strip()
        if not ticker or ticker in cash:
            continue
        out[ticker] = row
    return out


def _valuation_map(valuation_rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in valuation_rows or []:
        ticker = str(row.get("Ticker", "")).strip()
        if ticker:
            out[ticker] = row
    return out


def _near_candidates(
    held: dict[str, dict],
    val_map: dict[str, dict],
    near_band: float,
    level_coverage: Optional[dict] = None,
) -> list[CrosshairItem]:
    items: list[CrosshairItem] = []
    for ticker, hrow in held.items():
        vdata = val_map.get(ticker, {})
        trigger_type = resolve_trigger_type(ticker, vdata, level_coverage)
        if trigger_type == "ceiling_only":
            continue  # no valuation band -- the style ceiling governs, not this

        m = resolve_typed_metric(trigger_type, hrow, vdata)
        if m["current"] is None:
            continue  # live metric missing/non-numeric -- skip, never fall back to a different metric

        label = METRIC_MAP.get(trigger_type, (None, trigger_type))[1]
        mv = _safe_float(hrow.get("Market Value"))
        wt = _safe_float(hrow.get("Weight"))

        candidates: list[tuple[str, float, str]] = []
        dist_trim, dist_add = m["dist_trim"], m["dist_add"]
        # Through trim (current has crossed the level) => dist <= 0; else within band
        if dist_trim is not None and (dist_trim <= 0 or abs(dist_trim) <= near_band):
            facts = (
                f"{label} {_fmt_metric(trigger_type, m['current'])}; "
                f"trim {_fmt_metric(trigger_type, m['trim'])}; ->Trim {dist_trim:+.1%}"
            )
            candidates.append((REASON_NEAR_TRIM, _BUCKET_NEAR + abs(dist_trim), facts))
        if dist_add is not None and (dist_add <= 0 or abs(dist_add) <= near_band):
            facts = (
                f"{label} {_fmt_metric(trigger_type, m['current'])}; "
                f"add {_fmt_metric(trigger_type, m['add'])}; ->Add {dist_add:+.1%}"
            )
            candidates.append((REASON_NEAR_ADD, _BUCKET_NEAR + abs(dist_add), facts))

        if not candidates:
            continue
        # Prefer the closer band edge; keep both facts in rationale when both fire.
        # One valuation NEAR_* row per ticker -- the declared type's band only,
        # never a second row from a secondary/unused band on the same thesis.
        candidates.sort(key=lambda c: c[1])
        reason, score, primary = candidates[0]
        if reason == REASON_NEAR_TRIM:
            mod, rank_suffix = _trim_rank_modifiers(ticker, hrow)
            score += mod
            if rank_suffix:
                primary = primary + rank_suffix
        rationale = primary
        if len(candidates) > 1:
            rationale = primary + " | also " + candidates[1][2]

        override_tag: Optional[str] = None
        doctrine_reason = ""
        doctrine_downgraded = False
        if reason == REASON_NEAR_TRIM:
            try:
                from utils.doctrine_reader import downgrade_rule, load_doctrine
                rule = downgrade_rule(load_doctrine(), ticker, REASON_NEAR_TRIM)
            except Exception:
                rule = None
            if rule is not None:
                dist_for_rank = abs(dist_trim) if dist_trim is not None else 0.0
                score = _BUCKET_DOCTRINE_HOLD + dist_for_rank
                override_tag = "HOLD_TAX" if rule.id == "tax_hold_runners" else rule.id.upper()
                doctrine_reason = rule.summary
                doctrine_downgraded = True  # downgrade_rule only returns downgrade_informational
                rationale = rationale + " | doctrine: " + rule.summary
        elif reason == REASON_NEAR_ADD and _add_triggers_suspended(ticker):
            # Policy (b): keep on Decision_View, re-rank out of CC top 5 — same
            # bucket as doctrine HOLD_TAX. Do not drop the row (a).
            dist_for_rank = abs(dist_add) if dist_add is not None else 0.0
            score = _BUCKET_DOCTRINE_HOLD + dist_for_rank
            override_tag = "ADD_SUSPENDED"
            doctrine_reason = "add_triggers_suspended in thesis frontmatter"
            doctrine_downgraded = False  # thesis frontmatter, not doctrine
            rationale = rationale + " | add_triggers_suspended: true"

        items.append(CrosshairItem(
            ticker=ticker,
            reason_code=reason,
            rank_score=score,
            mv=mv,
            wt=wt,
            price=m["price"],
            trim=m["trim"],
            add=m["add"],
            dist_trim=dist_trim,
            dist_add=dist_add,
            rationale=rationale,
            trigger_type=trigger_type,
            override_tag=override_tag,
            doctrine_reason=doctrine_reason,
            doctrine_downgraded=doctrine_downgraded,
        ))
    return items


def _dislocation_candidates(
    payload: Optional[dict],
    held: dict[str, dict],
    val_map: dict[str, dict],
    level_coverage: Optional[dict] = None,
) -> list[CrosshairItem]:
    if not payload:
        return []
    flagged = [r for r in (payload.get("results") or []) if r.get("flagged")]
    # Prefer larger drawdown / more extreme 5d as tie-break within bucket
    def _severity(r: dict) -> float:
        dd = abs(_safe_float(r.get("drawdown_52w")) or 0.0)
        d5 = abs(_safe_float(r.get("return_5d")) or 0.0)
        return -(dd + d5)

    flagged = sorted(flagged, key=_severity)
    items: list[CrosshairItem] = []
    for i, r in enumerate(flagged):
        ticker = str(r.get("ticker", "")).strip()
        if not ticker:
            continue
        classification = str(r.get("classification", "") or "unknown")
        is_held = ticker in held
        bucket = _BUCKET_DISLOC_HELD if is_held else _BUCKET_DISLOC_OTHER
        hrow = held.get(ticker, {})
        vdata = val_map.get(ticker, {})
        price = _safe_float(hrow.get("Price")) or _safe_float(r.get("price"))
        # Unheld names have no thesis -- default "price" is harmless since
        # trim/add will be empty for them anyway (no Val_Card row). Held
        # names use their declared type so trim/add aren't read as dollars
        # when the band is actually a P/E, P/B or discount %.
        trigger_type = resolve_trigger_type(ticker, vdata, level_coverage) if is_held else "price"
        if trigger_type == "ceiling_only":
            trim = add = dist_trim = dist_add = None
        else:
            synth_hrow = dict(hrow)
            synth_hrow["Price"] = price
            m = resolve_typed_metric(trigger_type, synth_hrow, vdata)
            trim, add, dist_trim, dist_add = m["trim"], m["add"], m["dist_trim"], m["dist_add"]
        dd = _safe_float(r.get("drawdown_52w"))
        d5 = _safe_float(r.get("return_5d"))
        pe = _safe_float(r.get("forward_pe"))
        parts = [f"source={classification}"]
        if dd is not None:
            parts.append(f"52w drawdown {dd:.1%}")
        if d5 is not None:
            parts.append(f"5d {d5:+.1%}")
        if pe is not None:
            parts.append(f"fwd P/E {pe:.1f}")
        items.append(CrosshairItem(
            ticker=ticker,
            reason_code=REASON_DISLOCATION,
            rank_score=bucket + i * 0.01,
            mv=_safe_float(hrow.get("Market Value")),
            wt=_safe_float(hrow.get("Weight")),
            price=price,
            trim=trim,
            add=add,
            dist_trim=dist_trim,
            dist_add=dist_add,
            rationale="; ".join(parts),
            trigger_type=trigger_type,
        ))
    return items


def _missing_level_candidates(
    coverage: dict,
    held: dict[str, dict],
    val_map: dict[str, dict],
) -> list[CrosshairItem]:
    no_trim = set(coverage.get("no_trim_level") or [])
    no_add = set(coverage.get("no_add_level") or [])
    no_thesis = set(coverage.get("no_thesis") or [])
    types = coverage.get("trigger_type_by_ticker") or {}
    tickers = sorted(no_trim | no_add | no_thesis)
    items: list[CrosshairItem] = []
    for i, ticker in enumerate(tickers):
        # ceiling_only with both "covered" won't appear in no_trim/no_add
        gaps = []
        if ticker in no_thesis:
            gaps.append("no thesis file")
        else:
            tt = types.get(ticker) or "price"
            if ticker in no_trim:
                gaps.append(f"no trim level ({tt})")
            if ticker in no_add:
                gaps.append(f"no add level ({tt})")
        if not gaps:
            continue
        hrow = held.get(ticker, {})
        vdata = val_map.get(ticker, {})
        price = _safe_float(hrow.get("Price"))
        trim = _safe_float_nonzero(vdata.get("Trim Target"))
        add = _safe_float_nonzero(vdata.get("Add Target"))
        dist_trim = (trim - price) / price if trim and price else None
        dist_add = (price - add) / add if add and price else None
        items.append(CrosshairItem(
            ticker=ticker,
            reason_code=REASON_MISSING_LEVEL,
            rank_score=_BUCKET_MISSING + i * 0.01,
            mv=_safe_float(hrow.get("Market Value")),
            wt=_safe_float(hrow.get("Weight")),
            price=price,
            trim=trim,
            add=add,
            dist_trim=dist_trim,
            dist_add=dist_add,
            rationale="SYSTEM: " + "; ".join(gaps),
        ))
    return items


def _add_triggers_suspended(ticker: str) -> bool:
    """True when thesis frontmatter sets add_triggers_suspended: true."""
    from utils.thesis_reader import THESES_DIR, load_frontmatter

    path = THESES_DIR / f"{ticker}_thesis.md"
    if not path.is_file():
        return False
    try:
        fm = load_frontmatter(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    val = fm.get("add_triggers_suspended")
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "yes", "1")
    return False


def _trim_trigger_role(ticker: str) -> str:
    """Return trim_trigger_role from nested frontmatter triggers; default binding."""
    from utils.thesis_reader import THESES_DIR, load_frontmatter

    path = THESES_DIR / f"{ticker}_thesis.md"
    if not path.is_file():
        return "binding"
    try:
        fm = load_frontmatter(path.read_text(encoding="utf-8"))
    except Exception:
        return "binding"
    triggers = fm.get("triggers") if isinstance(fm.get("triggers"), dict) else {}
    role = triggers.get("trim_trigger_role")
    if role is None:
        return "binding"
    s = str(role).strip().lower()
    if s == "informational":
        return "informational"
    return "binding"


def _style_size_ceiling_pct(ticker: str) -> Optional[float]:
    from utils.thesis_reader import THESES_DIR, load_frontmatter

    path = THESES_DIR / f"{ticker}_thesis.md"
    if not path.is_file():
        return None
    try:
        fm = load_frontmatter(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    triggers = fm.get("triggers") if isinstance(fm.get("triggers"), dict) else {}
    return _safe_float(triggers.get("style_size_ceiling_pct"))


def _trim_rank_modifiers(ticker: str, hrow: dict) -> tuple[float, str]:
    """Rank penalty + rationale suffix for NEAR_TRIM only. Never changes dist_trim."""
    penalty = 0.0
    parts: list[str] = []
    wt = holdings_weight_fraction_to_pct_points(hrow.get("Weight"))
    ceiling = _style_size_ceiling_pct(ticker)
    if wt is not None and ceiling is not None and ceiling > 0:
        headroom = min(wt / ceiling, 1.0)
        penalty += W_CEILING_HEADROOM * (1.0 - headroom)
        parts.append(f"headroom {headroom:.2f}")
    unreal_frac = _safe_float(hrow.get("Unrealized G/L %"))
    if unreal_frac is not None and unreal_frac < 0:
        penalty += W_UNREALIZED_LOSS
        unreal_display = holdings_unrealized_pct_fraction_to_pct_points(unreal_frac)
        if unreal_display is not None:
            parts.append(f"unrealized {unreal_display:.1f}%")
    suffix = f" | rank: {', '.join(parts)}" if parts else ""
    return penalty, suffix


def _apply_doctrine_downgrades(items: list[CrosshairItem]) -> list[CrosshairItem]:
    """
    After merge: if a ticker has NEAR_TRIM in play (primary or merged extra) and
    doctrine says downgrade_informational, force reason_code=NEAR_TRIM, rank into
    the HOLD bucket, and stamp override_tag + doctrine_downgraded. DISLOCATION / other facts stay in
    rationale. NEAR_ADD is never downgraded here.
    """
    try:
        from utils.doctrine_reader import downgrade_rule, load_doctrine
        doctrine = load_doctrine()
    except Exception:
        return items

    out: list[CrosshairItem] = []
    for item in items:
        near_in_play = (
            item.reason_code == REASON_NEAR_TRIM
            or "NEAR_TRIM:" in (item.rationale or "")
        )
        if not near_in_play:
            out.append(item)
            continue
        rule = downgrade_rule(doctrine, item.ticker, REASON_NEAR_TRIM)
        if rule is None:
            out.append(item)
            continue
        dist_for_rank = abs(item.dist_trim) if item.dist_trim is not None else 0.0
        tag = "HOLD_TAX" if rule.id == "tax_hold_runners" else rule.id.upper()
        rationale = item.rationale or ""
        if "doctrine:" not in rationale:
            rationale = rationale + " | doctrine: " + rule.summary
        # If DISLOCATION (or other) was primary, keep that fact visible.
        if item.reason_code != REASON_NEAR_TRIM:
            rationale = (
                f"{REASON_NEAR_TRIM} (doctrine-hold) | was {item.reason_code}: "
                + rationale
            )
        out.append(CrosshairItem(**{
            **item.to_dict(),
            "reason_code": REASON_NEAR_TRIM,
            "rank_score": _BUCKET_DOCTRINE_HOLD + dist_for_rank,
            "override_tag": tag,
            "doctrine_reason": rule.summary,
            "doctrine_downgraded": True,
            "rationale": rationale,
        }))
    out.sort(key=lambda x: (x.rank_score, x.ticker))
    return out


def _apply_add_suspensions(items: list[CrosshairItem]) -> list[CrosshairItem]:
    """
    Policy (b): thesis frontmatter add_triggers_suspended: true keeps NEAR_ADD
    on Decision_View but re-ranks into the doctrine HOLD bucket (>=400) so it
    drops out of the Command Center top 5 — same pattern as HOLD_TAX.
    Policy (a) drop-entirely rejected for consistency with that path.
    """
    out: list[CrosshairItem] = []
    for item in items:
        near_add_in_play = (
            item.reason_code == REASON_NEAR_ADD
            or "NEAR_ADD:" in (item.rationale or "")
            or "->Add " in (item.rationale or "")
        )
        if not near_add_in_play or not _add_triggers_suspended(item.ticker):
            out.append(item)
            continue
        if item.override_tag == "ADD_SUSPENDED" and item.rank_score >= _BUCKET_DOCTRINE_HOLD:
            out.append(item)
            continue
        # If primary is something else (e.g. DISLOCATION) but NEAR_ADD is in
        # rationale only, leave primary ranking alone — suspension binds the
        # add-band signal, not every fact on the ticker.
        if item.reason_code != REASON_NEAR_ADD:
            out.append(item)
            continue
        dist_for_rank = abs(item.dist_add) if item.dist_add is not None else 0.0
        rationale = item.rationale or ""
        if "add_triggers_suspended" not in rationale:
            rationale = rationale + " | add_triggers_suspended: true"
        out.append(CrosshairItem(**{
            **item.to_dict(),
            "rank_score": _BUCKET_DOCTRINE_HOLD + dist_for_rank,
            "override_tag": "ADD_SUSPENDED",
            "doctrine_reason": "add_triggers_suspended in thesis frontmatter",
            "doctrine_downgraded": False,
            "rationale": rationale,
        }))
    out.sort(key=lambda x: (x.rank_score, x.ticker))
    return out


def _apply_trim_roles(items: list[CrosshairItem]) -> list[CrosshairItem]:
    """
    Policy (b): trim_trigger_role: informational keeps NEAR_TRIM on Decision_View
    but re-ranks into the doctrine HOLD bucket (>=400). Never drops rows.
    Doctrine downgrade wins — no-op when rank_score >= _BUCKET_DOCTRINE_HOLD.
    """
    out: list[CrosshairItem] = []
    for item in items:
        near_trim_in_play = (
            item.reason_code == REASON_NEAR_TRIM
            or "NEAR_TRIM:" in (item.rationale or "")
            or "->Trim " in (item.rationale or "")
        )
        if not near_trim_in_play or _trim_trigger_role(item.ticker) != "informational":
            out.append(item)
            continue
        if item.rank_score >= _BUCKET_DOCTRINE_HOLD:
            out.append(item)
            continue
        if item.reason_code != REASON_NEAR_TRIM:
            out.append(item)
            continue
        dist_for_rank = abs(item.dist_trim) if item.dist_trim is not None else 0.0
        rationale = item.rationale or ""
        if "trim_trigger_role: informational" not in rationale:
            rationale = rationale + " | trim_trigger_role: informational"
        out.append(CrosshairItem(**{
            **item.to_dict(),
            "rank_score": _BUCKET_DOCTRINE_HOLD + dist_for_rank,
            "override_tag": "TRIM_INFORMATIONAL",
            "doctrine_downgraded": False,
            "rationale": rationale,
        }))
    out.sort(key=lambda x: (x.rank_score, x.ticker))
    return out


def _merge_by_ticker(groups: list[list[CrosshairItem]]) -> list[CrosshairItem]:
    """One row per ticker; keep best (lowest) rank_score; append other reason facts."""
    best: dict[str, CrosshairItem] = {}
    extras: dict[str, list[str]] = {}
    for group in groups:
        for item in group:
            t = item.ticker
            if t not in best:
                best[t] = item
                continue
            if item.rank_score < best[t].rank_score:
                extras.setdefault(t, []).append(f"{best[t].reason_code}: {best[t].rationale}")
                best[t] = item
            else:
                extras.setdefault(t, []).append(f"{item.reason_code}: {item.rationale}")
    out = []
    for t, item in best.items():
        if extras.get(t):
            item = CrosshairItem(**{**item.to_dict(), "rationale": item.rationale + " | " + " | ".join(extras[t])})
        out.append(item)
    out.sort(key=lambda x: (x.rank_score, x.ticker))
    return out


def produce_crosshairs(
    *,
    holdings_rows: Optional[list[dict]] = None,
    valuation_rows: Optional[list[dict]] = None,
    dislocation_payload: Optional[dict] = None,
    dislocation_path: Optional[str] = None,
    level_coverage: Optional[dict] = None,
    near_band_pct: float = NEAR_BAND_PCT,
    extra_warnings: Optional[list[str]] = None,
    read_sheets_if_needed: bool = True,
) -> CrosshairsResult:
    """
    Build the ranked Crosshairs list. Callers that already hold Sheet rows
    should pass them; otherwise this opens the Sheet when read_sheets_if_needed.
    """
    warnings: list[str] = list(extra_warnings or [])

    if (holdings_rows is None or valuation_rows is None) and read_sheets_if_needed:
        from utils.sheet_readers import get_gspread_client
        from tasks.build_command_center import _read_records

        try:
            client = get_gspread_client()
            ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
            if holdings_rows is None:
                holdings_rows = _read_records(ss, config.TAB_HOLDINGS_CURRENT)
            if valuation_rows is None:
                valuation_rows = _read_records(ss, config.TAB_VALUATION_CARD)
                if not valuation_rows:
                    warnings.append("Valuation_Card unreadable or empty")
        except Exception as e:
            warnings.append(f"Sheet read failed: {e}")
            holdings_rows = holdings_rows or []
            valuation_rows = valuation_rows or []

    holdings_rows = holdings_rows or []
    valuation_rows = valuation_rows or []
    held = _holdings_map(holdings_rows)
    val_map = _valuation_map(valuation_rows)

    if not valuation_rows:
        if "Valuation_Card unreadable or empty" not in warnings:
            warnings.append("Valuation_Card unreadable or empty")

    if level_coverage is None:
        try:
            level_coverage = compute_level_coverage(list(held.keys()))
        except Exception as e:
            warnings.append(f"level_coverage failed: {e}")
            level_coverage = {
                "no_trim_level": [],
                "no_add_level": [],
                "no_thesis": [],
                "trigger_type_by_ticker": {},
            }

    if dislocation_payload is None:
        dislocation_payload, dislocation_path = load_dislocation_payload(dislocation_path)
        if dislocation_payload is None:
            warnings.append("no same-day dislocation scan on disk")

    near = _near_candidates(held, val_map, near_band_pct, level_coverage=level_coverage)
    disloc = _dislocation_candidates(dislocation_payload, held, val_map, level_coverage=level_coverage)
    missing = _missing_level_candidates(level_coverage, held, val_map)
    items = _apply_add_suspensions(
        _apply_trim_roles(
            _apply_doctrine_downgrades(_merge_by_ticker([near, disloc, missing]))
        )
    )
    items = _annotate_tax_surface(items)

    as_of = datetime.now().strftime("%Y-%m-%d %H:%M")
    return CrosshairsResult(
        items=items,
        as_of=as_of,
        warnings=warnings,
        dislocation_path=dislocation_path,
    )


def _annotate_tax_surface(items: list[CrosshairItem]) -> list[CrosshairItem]:
    """Attach 3a/3b/3c measurement to trim-side rows. Never fails the list."""
    try:
        from core.tax.surface import annotate_ticker
    except Exception:
        return items
    out: list[CrosshairItem] = []
    for it in items:
        trim_side = (
            it.reason_code == REASON_NEAR_TRIM
            or it.override_tag == "HOLD_TAX"
            or it.doctrine_downgraded
        )
        if not trim_side:
            out.append(it)
            continue
        try:
            ann = annotate_ticker(it.ticker)
            it.days_to_lt = ann.days_to_lt
            it.wash_window_open = ann.wash_window_open
            it.wash_disallow_through = (
                ann.wash_windows[0].disallow_through.isoformat() if ann.wash_windows else None
            )
            it.is_tax_hold_runner = ann.is_tax_hold_runner
            if ann.relief and ann.relief.has_range:
                it.est_tax_cost_low = ann.relief.best_case_tax
                it.est_tax_cost_high = ann.relief.worst_case_tax
        except Exception:
            pass
        out.append(it)
    return out


def print_dry_run(result: CrosshairsResult, top_n: int = TOP_N_DASHBOARD) -> None:
    print(result.header_line)
    if result.dislocation_path:
        print(f"  dislocation: {result.dislocation_path}")
    print(f"{'Rank':<5} {'Ticker':<8} {'Reason':<16} {'Score':>8} {'Doctrine':<10}  Rationale")
    for i, item in enumerate(result.items, 1):
        mark = "*" if i <= top_n else " "
        tag = item.override_tag or ""
        print(
            f"{mark}{i:<4} {item.ticker:<8} {item.reason_code:<16} "
            f"{item.rank_score:8.3f} {tag:<10}  {item.rationale}"
        )
    print(f"{len(result.items)} items; top {top_n} marked *. DRY RUN — no Sheet writes.")


def main(live: bool = False, ensure_scan: bool = False) -> CrosshairsResult:
    """
    Standalone: build and print Crosshairs. Does not write Sheets.
    --ensure-scan runs dislocation if no same-day artifact.
    """
    payload, path = None, None
    if ensure_scan:
        payload, path = ensure_dislocation_payload(run_if_missing=True, live=live)
    result = produce_crosshairs(dislocation_payload=payload, dislocation_path=path)
    print_dry_run(result)
    return result


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Build ranked Crosshairs list (stdout only).")
    p.add_argument("--live", action="store_true", help="Passed through to dislocation scan if --ensure-scan.")
    p.add_argument("--ensure-scan", action="store_true", help="Run dislocation if no same-day JSON.")
    args = p.parse_args()
    main(live=args.live, ensure_scan=args.ensure_scan)
