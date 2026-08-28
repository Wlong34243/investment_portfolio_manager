"""
Local read-mostly Command Center UI (FastAPI + Jinja).

Desk cockpit at `/` — sidebar shell, header strip, Tier 0 routine launcher.
CLI owns mutations. Write routes gated by UI_WRITE_ROUTE_ALLOWLIST.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

from ui import format as desk_fmt

templates.env.filters["pct"] = desk_fmt.fmt_pct
templates.env.filters["money"] = desk_fmt.fmt_money
templates.env.filters["money_range"] = desk_fmt.fmt_money_range
templates.env.filters["days"] = desk_fmt.fmt_days
templates.env.filters["hash8"] = desk_fmt.fmt_hash8
templates.env.filters["dt"] = desk_fmt.fmt_dt
templates.env.filters["dist_pct"] = desk_fmt.fmt_dist_pct
templates.env.filters["polarity_class"] = desk_fmt.fmt_polarity_class
templates.env.filters["pct_pts"] = desk_fmt.fmt_pct_points
templates.env.filters["delta_bar_width"] = desk_fmt.delta_bar_width

UI_WRITE_ROUTE_ALLOWLIST: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/ask"),
    ("POST", "/run/{routine_id}"),
})

app = FastAPI(title="Investment Portfolio — Local Command Center", docs_url=None, redoc_url=None)
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _store():
    from core.store import get_store

    return get_store()


def _page_ctx(page: str, **extra: Any) -> dict[str, Any]:
    from ui.header_context import assemble_header

    ctx = {"page": page, "header": assemble_header()}
    ctx.update(extra)
    return ctx


def _render(
    request: Request, template: str, ctx: dict[str, Any], *, status_code: int = 200
) -> HTMLResponse:
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)


@app.get("/", response_class=HTMLResponse)
def cockpit(request: Request):
    from ui.cockpit import assemble_cockpit

    ctx = _page_ctx("cockpit", **assemble_cockpit())
    return _render(request, "cockpit.html", ctx)


@app.get("/positions", response_class=HTMLResponse)
def positions(request: Request):
    from ui.positions_page import assemble_positions

    ctx = _page_ctx("positions", **assemble_positions())
    return _render(request, "positions.html", ctx)


@app.get("/decision", response_class=HTMLResponse)
def decision(request: Request):
    from ui.crosshairs_table import assemble_decision

    store = _store()
    header = ""
    if hasattr(store, "get_decision_header"):
        header = store.get_decision_header() or ""
    ctx = _page_ctx("decision", **assemble_decision(), decision_header=header)
    return _render(request, "decision.html", ctx)


@app.get("/tax", response_class=HTMLResponse)
def tax(request: Request):
    from ui.tax_page import assemble_tax

    store = _store()
    ctx = _page_ctx("tax", **assemble_tax(store))
    return _render(request, "tax.html", ctx)


@app.get("/rotations", response_class=HTMLResponse)
def rotations(request: Request):
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/judgment/rotations", status_code=302)


@app.get("/judgment", response_class=HTMLResponse)
@app.get("/judgment/rotations", response_class=HTMLResponse)
@app.get("/judgment/lifecycle", response_class=HTMLResponse)
def judgment(request: Request):
    from ui.judgment_page import assemble_judgment

    path = request.url.path
    if path.endswith("/rotations"):
        section, page = "rotations", "judgment_rotations"
    elif path.endswith("/lifecycle"):
        section, page = "lifecycle", "judgment_lifecycle"
    else:
        section, page = "overview", "judgment"
    ctx = _page_ctx(page, **assemble_judgment(section=section))
    return _render(request, "judgment.html", ctx)


@app.get("/precommit", response_class=HTMLResponse)
def precommit(request: Request):
    from ui.precommit_page import assemble_precommit

    ctx = _page_ctx("precommit", **assemble_precommit())
    return _render(request, "precommit.html", ctx)


@app.get("/runs", response_class=HTMLResponse)
def runs_page(request: Request):
    from ui.runner import list_ui_runs
    from ui.routines import LAUNCHABLE_ROUTINES, routine_duration_hint

    groups: dict[str, list] = defaultdict(list)
    for r in LAUNCHABLE_ROUTINES.values():
        view = {
            "id": r.id,
            "label": r.label,
            "description": r.description,
            "args": r.args,
            "writes_banner": r.writes_banner,
            "confirm_name": r.confirm_name,
            "long_run_warning": r.long_run_warning,
            "duration_hint": routine_duration_hint(r),
            "timeout_sec": r.timeout_sec,
        }
        groups[r.group].append(view)
    ctx = _page_ctx(
        "runs",
        routine_groups=dict(groups),
        history=list_ui_runs(30),
    )
    return _render(request, "runs.html", ctx)


class RunRequest(BaseModel):
    args: dict[str, Any] = {}
    confirm_name: str | None = None


@app.post("/run/{routine_id}")
def run_routine(routine_id: str, body: RunRequest) -> dict[str, Any]:
    from ui.runner import start_run

    run_id, err = start_run(
        routine_id,
        body.args or {},
        confirm_name=body.confirm_name,
    )
    if err:
        return {"error": err}
    return {"run_id": run_id}


@app.get("/run/{run_id}/stream")
def run_stream(run_id: int):
    from ui.runner import stream_run

    return StreamingResponse(stream_run(run_id), media_type="text/event-stream")


@app.get("/position/{ticker}", response_class=HTMLResponse)
def position_story(request: Request, ticker: str):
    from ui.position_story import assemble_position_story

    ctx, _rs = assemble_position_story(ticker)
    if ctx.get("not_found"):
        return _render(
            request,
            "position_not_found.html",
            _page_ctx(
                "position",
                ticker=ctx["ticker"],
                held_tickers=ctx.get("held_tickers", []),
            ),
            status_code=404,
        )
    ctx.update(_page_ctx("position"))
    return _render(request, "position_story.html", ctx)


@app.get("/search", response_class=HTMLResponse)
def corpus_search_page(
    request: Request,
    q: str = "",
    ticker: list[str] = Query(default=[]),
    source_type: list[str] = Query(default=[]),
    since: str = "",
    until: str = "",
    preset: str = "",
    limit: int = 25,
    offset: int = 0,
):
    from ui.corpus_search import assemble_search

    ctx = assemble_search(
        q=q,
        tickers=ticker,
        source_types=source_type,
        since=since or None,
        until=until or None,
        preset=preset or None,
        limit=limit,
        offset=offset,
    )
    ctx.update(_page_ctx("search"))
    return _render(request, "search.html", ctx)


@app.get("/doc/{doc_id}", response_class=HTMLResponse)
def corpus_doc_reader(request: Request, doc_id: int, chunk: int | None = None):
    from ui.corpus_search import assemble_doc

    ctx = assemble_doc(doc_id, chunk_id=chunk)
    if ctx is None:
        return _render(
            request,
            "position_not_found.html",
            _page_ctx("search", ticker=f"doc:{doc_id}", held_tickers=[]),
            status_code=404,
        )
    ctx.update(_page_ctx("search"))
    return _render(request, "doc_reader.html", ctx)


@app.get("/ask", response_class=HTMLResponse)
def ask_form(request: Request, q: str = "", answer: str = ""):
    ctx = _page_ctx("ask", question=q, answer=answer)
    return _render(request, "ask.html", ctx)


@app.post("/ask", response_class=HTMLResponse)
def ask_submit(request: Request, question: str = ""):
    from core.analyst.run import run_ask, write_report

    q = (question or "").strip()
    if not q:
        ctx = _page_ctx("ask", question="", answer="Enter a question.")
        return _render(request, "ask.html", ctx)
    result = run_ask(q, dry_run=False)
    write_report(result, dry_run=False)
    answer = result.get("answer") or result.get("reason") or ""
    val = result.get("validation")
    if val and val.fabricated_tokens:
        answer += f"\n\n**VALIDATION_FAILED** — fabricated: {val.fabricated_tokens}"
    ctx = _page_ctx(
        "ask",
        question=q,
        answer=answer,
        status=result.get("status"),
    )
    return _render(request, "ask.html", ctx)


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
