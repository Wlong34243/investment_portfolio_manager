"""Render monitoring cockpit as static HTML for Drive publish (phone-readable)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

OUT_DIR = Path("agent_outputs") / "command_center"
TEMPLATES = Path("ui") / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def render_chart_spec_static(spec) -> str:
    """Shared ChartSpec → SVG path for static mirror parity (prompt 4 checklist 14b)."""
    from ui.charts import render_chart_svg

    return render_chart_svg(spec)


def render_static_cockpit(*, live: bool = False) -> dict[str, Any]:
    """
    Write static HTML pages from PortfolioStore into agent_outputs/command_center/.
    These are published to Drive via publish_analysis globs — multi-device monitoring.
    """
    from core.store import get_store

    store = get_store()
    snap = store.status()
    holdings = store.get_holdings_current()
    top = []
    if not holdings.empty:
        import pandas as pd

        df = holdings.copy()
        ticker_col = "Ticker" if "Ticker" in df.columns else "ticker"
        mv_col = "Market Value" if "Market Value" in df.columns else None
        if mv_col:
            df[mv_col] = pd.to_numeric(df[mv_col], errors="coerce").fillna(0)
            df = df.sort_values(mv_col, ascending=False)
        for _, row in df.head(10).iterrows():
            top.append({
                "ticker": row.get(ticker_col, ""),
                "mv": float(row[mv_col]) if mv_col else 0,
                "wt": None,
            })

    items = store.get_crosshairs_items()
    header = ""
    if hasattr(store, "get_decision_header"):
        header = store.get_decision_header() or ""
    metrics = store.get_tax_control_metrics()
    lots = store.get_tax_control_lots()
    lots_records = lots.to_dict(orient="records") if not lots.empty else []
    rr = store.get_rotation_review()
    rr_records = rr.to_dict(orient="records") if not rr.empty else []

    env = _env()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pages = {
        "index.html": env.get_template("home.html").render(
            request=None, snap=snap, top=top, page="home", generated=generated
        ),
        "decision.html": env.get_template("decision.html").render(
            request=None, items=items, header=header, page="decision", generated=generated
        ),
        "tax.html": env.get_template("tax.html").render(
            request=None,
            metrics=metrics,
            lots=lots_records[:50],
            lot_count=len(lots_records),
            page="tax",
            generated=generated,
        ),
        "rotations.html": env.get_template("rotations.html").render(
            request=None,
            rows=rr_records[:100],
            count=len(rr_records),
            page="rotations",
            generated=generated,
        ),
    }

    # Static nav: rewrite FastAPI paths to relative HTML files
    rewrites = {
        'href="/"': 'href="index.html"',
        'href="/decision"': 'href="decision.html"',
        'href="/tax"': 'href="tax.html"',
        'href="/rotations"': 'href="rotations.html"',
    }

    result: dict[str, Any] = {"live": live, "files": [], "out_dir": str(OUT_DIR)}
    if not live:
        result["dry_run"] = True
        result["would_write"] = list(pages.keys())
        return result

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, html in pages.items():
        for a, b in rewrites.items():
            html = html.replace(a, b)
        # Strip hx-get polling (no server)
        html = html.replace('hx-get="/api/status"', "")
        path = OUT_DIR / name
        path.write_text(html, encoding="utf-8")
        result["files"].append(str(path))
        logger.info("wrote %s", path)

    result["dry_run"] = False
    return result
