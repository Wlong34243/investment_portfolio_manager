"""
New Idea Screener — evaluates candidate tickers against Bill's styles.

Reads the composite bundle (market + vault), takes a user-supplied list
of tickers, pre-computes fundamental and market context in Python,
and passes the context to Gemini for style-fit analysis.
"""

import json
import logging
import sys

logger = logging.getLogger(__name__)
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict

import typer
import yfinance as yf
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add project root to path
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from agents.schemas.new_idea_schema import NewIdeaScreenerOutput
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle
from utils.gemini_client import ask_gemini_composite
from utils import fmp_client
from utils.formatters import dicts_to_markdown_table

app = typer.Typer(help="New Idea Screener Agent")
console = Console()

def compute_style_weights(holdings: List[dict], thesis_docs: Dict[str, dict]) -> Dict[str, float]:
    """Computes aggregate style weights from current holdings."""
    style_values = {}
    total_market_val = 0.0
    
    for h in holdings:
        ticker = h["ticker"]
        val = h.get("market_value", 0.0)
        total_market_val += val
        
        doc = thesis_docs.get(ticker, {})
        style_raw = (doc.get("style") or "").lower()
        
        style_code = "OTHER"
        if "garp" in style_raw or "boring" in style_raw:
            style_code = "GARP"
        elif "thematic" in style_raw or "theme" in style_raw:
            style_code = "THEME"
        elif "fund" in style_raw or "etf" in style_raw:
            style_code = "ETF"
        elif "developed international" in style_raw: style_code = "FUND"
        elif "emerging market" in style_raw: style_code = "FUND"
        
        style_values[style_code] = style_values.get(style_code, 0.0) + val
        
    if total_market_val == 0:
        return {}
        
    return {k: round(v / total_market_val, 3) for k, v in style_values.items()}

def run_new_idea_screener(
    bundle_path: Path,
    run_id: str,
    run_ts: str,
    ticker_list: Optional[List[str]] = None,
    notes: Optional[dict] = None,
    dry_run: bool = True,
) -> tuple[Optional[NewIdeaScreenerOutput], list[list]]:
    """
    Runner for the New Idea Screener. 
    Returns (result_object, sheet_rows).
    If ticker_list is empty/None, returns (None, []) to signify nothing to do.
    """
    if not ticker_list:
        logger.info("New Idea Screener: No tickers provided. Skipping.")
        return None, []

    # 1. Load composite
    composite = load_composite_bundle(bundle_path)
    market = load_bundle(Path(composite["market_bundle_path"]))
    vault = load_vault_bundle(Path(composite["vault_bundle_path"]))
    composite_hash = composite["composite_hash"]
    
    # 2. Load styles.json
    styles_path = Path(__file__).parent / "styles.json"
    styles_json = json.loads(styles_path.read_text(encoding="utf-8")) if styles_path.exists() else {}

    # 3. Pre-compute
    holdings = market["positions"]
    holdings_map = {h["ticker"]: h for h in holdings}
    total_value = market["total_value"]
    dry_powder = market.get("cash_manual", 0.0)
    
    thesis_docs = {doc["ticker"]: doc for doc in vault["documents"] if doc.get("doc_type") == "thesis"}
    style_weights = compute_style_weights(holdings, thesis_docs)
    
    candidates_pre = []
    for ticker in ticker_list:
        # Market data from yfinance
        try:
            yf_ticker = yf.Ticker(ticker)
            info = yf_ticker.fast_info
            current_price = info.get("lastPrice", 0.0)
            high_52w = info.get("yearHigh", 0.0)
            low_52w = info.get("yearLow", 0.0)
            
            discount_from_52w_high_pct = ((high_52w - current_price) / high_52w * 100) if high_52w > 0 else 0.0
            price_52w_range_position_pct = ((current_price - low_52w) / (high_52w - low_52w) * 100) if (high_52w - low_52w) > 0 else 0.0
        except Exception as e:
            logger.warning("yfinance error for %s: %s", ticker, e)
            current_price = high_52w = low_52w = discount_from_52w_high_pct = price_52w_range_position_pct = 0.0

        # Fundamental data from FMP
        try:
            profile = fmp_client.get_company_profile(ticker)
            metrics = fmp_client.get_key_metrics(ticker)
            financials = fmp_client.get_financial_statements(ticker)
            
            pe_fwd = metrics.get("pe_ratio")
            pe_trailing = pe_fwd
            revenue_growth_yoy = financials.get("operating_income")
            gross_margin = metrics.get("roe")
            market_cap = profile.get("market_cap")
        except Exception as e:
            logger.warning("FMP error for %s: %s", ticker, e)
            pe_fwd = pe_trailing = revenue_growth_yoy = gross_margin = market_cap = None

        already_held = ticker in holdings_map
        current_weight_pct = holdings_map.get(ticker, {}).get("weight_pct", 0.0)

        # Data gaps
        raw_data = {"pe_fwd": pe_fwd, "pe_trailing": pe_trailing, "market_cap": market_cap}
        gaps = [k for k, v in raw_data.items() if v is None]
        
        starter_size_usd = dry_powder * config.NEW_IDEA_STARTER_SIZE_PCT
        starter_size_usd = min(starter_size_usd, dry_powder * config.NEW_IDEA_MAX_STARTER_PCT)

        candidates_pre.append({
            "ticker": ticker,
            "already_held": already_held,
            "current_weight_pct": current_weight_pct,
            "discount_from_52w_high_pct": round(discount_from_52w_high_pct, 2),
            "price_52w_range_position_pct": round(price_52w_range_position_pct, 2),
            "pe_fwd": pe_fwd,
            "pe_trailing": pe_trailing,
            "revenue_growth_yoy": revenue_growth_yoy,
            "gross_margin": gross_margin,
            "market_cap": market_cap,
            "data_gaps": gaps,
            "user_note": (notes or {}).get(ticker, ""),
            "starter_size_usd": round(starter_size_usd, 2)
        })

    # 4. Build context and call Gemini
    candidates_table = dicts_to_markdown_table(candidates_pre)
    agent_context_text = (
        f"Portfolio State:\n- Total Value: ${total_value:,.2f}\n- Dry Powder: ${dry_powder:,.2f}\n"
        f"- Position Count: {len(holdings)}\n- Style Weights: {json.dumps(style_weights, indent=2)}\n\n"
        f"Investment Styles:\n{json.dumps(styles_json, indent=2)}\n\n"
        f"New Ideas for Evaluation:\n{candidates_table}\n\n"
        f"bundle_hash: {composite_hash}"
    )
    
    prompt_path = Path(__file__).parent / "prompts" / "new_idea_system.txt"
    system_instruction = prompt_path.read_text(encoding="utf-8")
    user_prompt = f"Evaluate these candidate tickers and assign verdicts.\n\nContext:\n{agent_context_text}"
    
    result: NewIdeaScreenerOutput | None = ask_gemini_composite(
        prompt=user_prompt,
        composite_bundle_path=bundle_path,
        response_schema=NewIdeaScreenerOutput,
        system_instruction=system_instruction,
        max_tokens=16000
    )
    
    if not result:
        return None, []

    # 5. Transform to sheet rows (compact format handled by analyze_all)
    # If run through analyze-all, return the standard 11-column rows.
    # Note: signal mapping matches the other agents (verdict fit -> WATCH/ADD)
    sheet_rows = []
    for v in result.verdicts:
        action = f"Fit: {v.style_assignment}" if v.verdict == "fit" else v.verdict.replace("_", " ").title()
        signal_type = "new_idea_fit" if v.verdict == "fit" else "new_idea_screen"
        
        sheet_rows.append([
            run_id, run_ts, result.bundle_hash[:16], AGENT_NAME,
            signal_type, v.ticker, action[:120],
            v.fit_rationale[:600],
            v.scale_step_note or "N/A",
            "watch" if v.verdict == "fit" else "info",
            "TRUE" if dry_run else "FALSE"
        ])
    
    return result, sheet_rows

@app.command()
def analyze(
    tickers: str = typer.Option(
        ...,
        "--tickers",
        help="Comma-separated list of candidate tickers to evaluate.",
    ),
    notes: Optional[str] = typer.Option(
        None,
        "--notes",
        help="JSON string mapping tickers to user notes (e.g. '{\"NVDA\": \"AI play\"}').",
    ),
    bundle: str = typer.Option(
        "latest",
        "--bundle",
        help="Composite bundle path or 'latest' to use most recent.",
    ),
    live: bool = typer.Option(
        False, "--live",
        help="Write output to Agent_Outputs Sheet tab. Default: dry run.",
    ),
):
    """Evaluate new investment ideas against portfolio context."""
    
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        console.print("[red]ERROR: No tickers provided.[/]")
        raise typer.Exit(1)
        
    if len(ticker_list) > config.NEW_IDEA_MAX_CANDIDATES_PER_RUN:
        console.print(f"[red]ERROR: Ticker list exceeds maximum of {config.NEW_IDEA_MAX_CANDIDATES_PER_RUN}.[/]")
        raise typer.Exit(1)

    # Banner
    if live:
        console.print(Panel.fit("[bold white on red] LIVE MODE — Sheet writes enabled [/]", border_style="red"))
    else:
        console.print(Panel.fit("[bold black on yellow] DRY RUN — No Sheet writes. [/]", border_style="yellow"))

    # 1. Resolve bundle
    if bundle == "latest":
        candidates = sorted(Path("bundles").glob("composite_bundle_*.json"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            console.print("[red]ERROR: No composite bundles found.[/]")
            raise typer.Exit(1)
        bundle_path = candidates[-1]
    else:
        bundle_path = Path(bundle)

    run_id = str(uuid.uuid4())[:8]
    run_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    parsed_notes = {}
    if notes:
        try:
            parsed_notes = json.loads(notes)
        except:
            console.print("[yellow]⚠ Could not parse --notes JSON string. Ignoring.[/]")

    result, sheet_rows = run_new_idea_screener(
        bundle_path=bundle_path,
        run_id=run_id,
        run_ts=run_ts,
        ticker_list=ticker_list,
        notes=parsed_notes,
        dry_run=not live
    )

    if not result:
        console.print("[red]ERROR: Gemini returned no result.[/]")
        raise typer.Exit(1)
        
    # 8. Output Summary
    table = Table(title="New Idea Screen")
    table.add_column("Ticker", style="bold")
    table.add_column("Verdict")
    table.add_column("Style")
    table.add_column("Starter ($)")
    table.add_column("Notes")
    
    for v in result.verdicts:
        v_color = "green" if v.verdict == "fit" else "red" if v.verdict == "no_fit" else "yellow"
        table.add_row(
            v.ticker,
            f"[{v_color}]{v.verdict}[/]",
            v.style_assignment or "N/A",
            f"{v.starter_size_usd:,.2f}" if v.starter_size_usd else "N/A",
            v.fit_rationale[:100] + "..." if len(v.fit_rationale) > 100 else v.fit_rationale
        )
    console.print(table)
    console.print(f"\n[bold]Portfolio Note:[/] {result.portfolio_note}")
    
    if live and sheet_rows:
        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_AGENT_OUTPUTS)
        ws.append_rows(sheet_rows, value_input_option="USER_ENTERED")
        console.print(f"[green]SUCCESS: Wrote {len(sheet_rows)} rows to {config.TAB_AGENT_OUTPUTS}[/]")

if __name__ == "__main__":
    app()

if __name__ == "__main__":
    app()
