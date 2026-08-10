"""
utils/thesis_reader.py — Single source of truth for reading vault thesis files.

All analysis surfaces (briefing, vault bundle style, dislocation, lint,
level_coverage helpers) should go through this module so style, triggers,
and scalar values agree.

- Frontmatter: YAML via PyYAML (comments stripped by the YAML parser).
- Flat-line fallback strips trailing `#...` on scalars (export_ai_briefing
  legacy path and any non-YAML consumer).
- Style taxonomy: frontmatter `style` key (GARP/THEME/FUND/ETF), not `## Style` prose.
- Triggers: nested `triggers:` block with declared `trigger_type` field pairs
  aligned to utils.level_coverage.TRIGGER_TYPE_FIELDS.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

from utils.level_coverage import DEFAULT_TRIGGER_TYPE, TRIGGER_TYPE_FIELDS

THESES_DIR = Path("vault") / "theses"
STYLE_TAXONOMY = frozenset({"GARP", "THEME", "FUND", "ETF"})

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_SCALAR_COMMENT_RE = re.compile(r"\s+#.*$")


def strip_scalar_comment(value: Any) -> Any:
    """Strip a trailing `# comment` from a scalar string value."""
    if not isinstance(value, str):
        return value
    cleaned = _SCALAR_COMMENT_RE.sub("", value).strip().strip("'\"")
    return cleaned


def extract_frontmatter_flat(text: str) -> tuple[dict, str]:
    """
    Flat per-line frontmatter parse (top-level keys only).
    Strips trailing `#...` from values — fixes MU style / ETN cost_basis pollution.
    Nested `triggers:` keys are NOT captured here; use load_frontmatter() / get_triggers().
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_text = m.group(1)
    body = text[m.end():]
    fm: dict = {}
    for line in fm_text.splitlines():
        km = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if km:
            key = km.group(1)
            val = strip_scalar_comment(km.group(2).strip().strip("'\""))
            fm[key] = val
    return fm, body


def load_frontmatter(text: str) -> dict:
    """Full YAML frontmatter (nested triggers included). Empty dict if missing/unparseable."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    if not _YAML_AVAILABLE:
        flat, _ = extract_frontmatter_flat(text)
        return flat
    try:
        data = _yaml.safe_load(m.group(1)) or {}
        if not isinstance(data, dict):
            return {}
        # Normalize top-level string scalars (defense if a loader preserved comments)
        out = {}
        for k, v in data.items():
            out[k] = strip_scalar_comment(v) if isinstance(v, str) else v
        return out
    except Exception:
        flat, _ = extract_frontmatter_flat(text)
        return flat


def read_thesis_text(path: Path | str) -> Optional[str]:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def thesis_path_for_ticker(ticker: str, theses_dir: Path | str = THESES_DIR) -> Path:
    return Path(theses_dir) / f"{ticker.upper()}_thesis.md"


def get_style(text: str | None = None, *, path: Path | str | None = None) -> Optional[str]:
    """Canonical investment-style taxonomy key from frontmatter `style:`."""
    if text is None and path is not None:
        text = read_thesis_text(path)
    if not text:
        return None
    fm = load_frontmatter(text)
    style = fm.get("style")
    if style is None:
        return None
    style = str(style).strip()
    # First token if someone wrote "GARP / Defensive"
    token = style.split()[0].split("/")[0].strip() if style else ""
    if token.upper() in STYLE_TAXONOMY:
        return token.upper()
    # Preserve non-taxonomy only if clean single token (shouldn't happen for live files)
    return token or None


def get_triggers(text: str | None = None, *, path: Path | str | None = None) -> dict:
    """Return the nested triggers dict (may be empty)."""
    if text is None and path is not None:
        text = read_thesis_text(path)
    if not text:
        return {}
    fm = load_frontmatter(text)
    raw = fm.get("triggers") or {}
    return raw if isinstance(raw, dict) else {}


def declared_trigger_type(triggers: dict | None) -> str:
    tt = (triggers or {}).get("trigger_type")
    if tt and str(tt).strip() in TRIGGER_TYPE_FIELDS:
        return str(tt).strip()
    return DEFAULT_TRIGGER_TYPE


def _safe_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = strip_scalar_comment(str(v)).replace("%", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def resolve_band_levels(triggers: dict | None) -> dict:
    """
    Resolve trim/add levels for the declared trigger_type.

    Returns:
      trigger_type, trim_field, add_field, trim_level, add_level,
      price_trim_above, price_add_below (always the price pair if present —
      secondary data for Val_Card backwards compat).
    """
    trigs = triggers or {}
    ttype = declared_trigger_type(trigs)
    trim_field, add_field = TRIGGER_TYPE_FIELDS.get(ttype, (None, None))

    trim_level = _safe_float(trigs.get(trim_field)) if trim_field else None
    add_level = _safe_float(trigs.get(add_field)) if add_field else None

    return {
        "trigger_type": ttype,
        "trim_field": trim_field,
        "add_field": add_field,
        "trim_level": trim_level,
        "add_level": add_level,
        "price_trim_above": _safe_float(trigs.get("price_trim_above")),
        "price_add_below": _safe_float(trigs.get("price_add_below")),
        # For Valuation_Card / Crosshairs price-distance math: only emit
        # price-denominated levels into Trim Target / Add Target.
        "valuation_trim": (
            trim_level if ttype == "price" else _safe_float(trigs.get("price_trim_above"))
        ),
        "valuation_add": (
            add_level if ttype == "price" else _safe_float(trigs.get("price_add_below"))
        ),
    }


def style_map_from_vault(theses_dir: Path | str = THESES_DIR) -> dict[str, str]:
    """ticker -> taxonomy style for all live thesis files."""
    out: dict[str, str] = {}
    root = Path(theses_dir)
    for path in sorted(root.glob("*_thesis.md")):
        text = read_thesis_text(path)
        if text is None:
            continue
        fm = load_frontmatter(text)
        ticker = str(fm.get("ticker") or path.name.replace("_thesis.md", "")).upper()
        style = get_style(text)
        if style:
            out[ticker] = style
    return out
