"""
Local read-mostly Command Center UI (FastAPI + Jinja/HTMX).

Serves KPIs, Decision/Crosshairs, Tax Control, and Rotation Review from
PortfolioStore (SQLite-primary when populated). CLI owns mutations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="Investment Portfolio — Local Command Center", docs_url=None, redoc_url=None)


def _store():
    from core.store import get_store

    return get_store()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    store = _store()
    snap = store.status()
    holdings = store.get_holdings_current()
    top = []
    if not holdings.empty:
        df = holdings.copy()
        ticker_col = "Ticker" if "Ticker" in df.columns else "ticker"
        mv_col = "Market Value" if "Market Value" in df.columns else None
        wt_col = None
        for c in ("Weight %", "Weight", "weight_pct"):
            if c in df.columns:
                wt_col = c
                break
        if mv_col:
            df[mv_col] = __import__("pandas").to_numeric(df[mv_col], errors="coerce").fillna(0)
            df = df.sort_values(mv_col, ascending=False)
        for _, row in df.head(10).iterrows():
            top.append({
                "ticker": row.get(ticker_col, ""),
                "mv": float(row[mv_col]) if mv_col else 0,
                "wt": float(row[wt_col]) if wt_col and row.get(wt_col) == row.get(wt_col) else None,
            })
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "snap": snap,
            "top": top,
            "page": "home",
        },
    )


@app.get("/decision", response_class=HTMLResponse)
def decision(request: Request):
    store = _store()
    items = store.get_crosshairs_items()
    header = ""
    if hasattr(store, "get_decision_header"):
        header = store.get_decision_header() or ""
    return templates.TemplateResponse(
        "decision.html",
        {"request": request, "items": items, "header": header, "page": "decision"},
    )


@app.get("/tax", response_class=HTMLResponse)
def tax(request: Request):
    store = _store()
    metrics = store.get_tax_control_metrics()
    lots = store.get_tax_control_lots()
    lots_records = lots.to_dict(orient="records") if not lots.empty else []
    return templates.TemplateResponse(
        "tax.html",
        {
            "request": request,
            "metrics": metrics,
            "lots": lots_records[:50],
            "lot_count": len(lots_records),
            "page": "tax",
        },
    )


@app.get("/rotations", response_class=HTMLResponse)
def rotations(request: Request):
    store = _store()
    rr = store.get_rotation_review()
    records = rr.to_dict(orient="records") if not rr.empty else []
    return templates.TemplateResponse(
        "rotations.html",
        {
            "request": request,
            "rows": records[:100],
            "count": len(records),
            "page": "rotations",
        },
    )


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    snap = _store().status()
    return {
        "backend": snap.backend,
        "position_count": snap.position_count,
        "total_market_value": snap.total_market_value,
        "notes": snap.notes,
        "updated_at": snap.updated_at,
    }
