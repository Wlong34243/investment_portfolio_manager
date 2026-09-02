"""Print EQT frontmatter blank-field sign-off table (stdout only — no writes)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.thesis_reader import load_frontmatter

TICKER = "EQT"
THESIS_PATH = ROOT / "vault" / "theses" / f"{TICKER}_thesis.md"

SIGNOFF_FIELDS = (
    ("style", "style"),
    ("framework_preference", "framework_preference"),
    ("triggers.trigger_type", "triggers", "trigger_type"),
    ("triggers.entry_price", "triggers", "entry_price"),
    ("triggers.price_add_below", "triggers", "price_add_below"),
    ("triggers.price_trim_above", "triggers", "price_trim_above"),
    ("triggers.style_size_ceiling_pct", "triggers", "style_size_ceiling_pct"),
)


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (int, float)) and float(value) == 0.0:
        return True
    return False


def _field_value(fm: dict, spec: tuple) -> object:
    if len(spec) == 2:
        return fm.get(spec[1])
    triggers = fm.get(spec[1]) if isinstance(fm.get(spec[1]), dict) else {}
    return triggers.get(spec[2])


def main() -> None:
    if not THESIS_PATH.is_file():
        print(f"Missing thesis: {THESIS_PATH}", file=sys.stderr)
        raise SystemExit(1)

    fm = load_frontmatter(THESIS_PATH.read_text(encoding="utf-8"))
    rows: list[tuple[str, str, str]] = []
    for spec in SIGNOFF_FIELDS:
        label = spec[0]
        value = _field_value(fm, spec)
        if _is_blank(value):
            display = "" if value is None else str(value)
            rows.append((label, display, "BLANK — Bill to fill"))

    print(f"EQT frontmatter sign-off — {THESIS_PATH.name}")
    print(f"Position context: current_allocation {fm.get('current_allocation', '?')}")
    print()
    print(f"{'Field':<36} {'Current':<16} {'Status'}")
    print("-" * 72)
    for field, current, status in rows:
        print(f"{field:<36} {current:<16} {status}")
    print()
    print(f"{len(rows)} blank field(s). Bill decides style key and trigger type; agents do not invent bands.")


if __name__ == "__main__":
    main()
