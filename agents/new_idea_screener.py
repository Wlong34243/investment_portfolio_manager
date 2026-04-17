"""
New Idea Screener — evaluates candidate tickers against Bill's styles.

Reads the composite bundle (market + vault), takes a user-supplied list
of tickers, pre-computes fundamental and market context in Python,
and passes the context to Gemini for style-fit analysis.
"""

import json
import logging
import sys
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
from utils.fmp_client import get_fundamentals

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
    
    # 0. Validation
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        console.print("[red]ERROR: No tickers provided.[/]")
        raise typer.Exit(1)
        
    if len(ticker_list) > config.NEW_IDEA_MAX_CANDIDATES_PER_RUN:
        console.print(f"[red]ERROR: Ticker list exceeds maximum of {config.NEW_IDEA_MAX_CANDIDATES_PER_RUN}.[/]")
        raise typer.Exit(1)

    # Banner
    if live:
        console.print(Panel.fit(
            "[bold white on red] LIVE MODE — Sheet writes enabled [/]",
            border_style="red",
        ))
    else:
        console.print(Panel.fit(
            "[bold black on yellow] DRY RUN — No Sheet writes. Use --live to enable. [/]",
            border_style="yellow",
        ))

    # 1. Resolve bundle
    if bundle == "latest":
        candidates = sorted(
            Path("bundles").glob("composite_bundle_*.json"),
            key=lambda p: p.stat().st_mtime,
        )
        if not candidates:
            console.print("[red]ERROR: No composite bundles found.[/]")
            raise typer.Exit(1)
        bundle_path = candidates[-1]
    else:
        bundle_path = Path(bundle)

    # 2. Load composite
    composite = load_composite_bundle(bundle_path)
    market = load_bundle(Path(composite["market_bundle_path"]))
    vault = load_vault_bundle(Path(composite["vault_bundle_path"]))
    
    # 3. Load styles.json
    styles_path = Path("agents/styles.json")
    if styles_path.exists():
        styles_json = json.loads(styles_path.read_text(encoding="utf-8"))
    else:
        styles_json = {}

    # 4. Pre-compute
    holdings = market["positions"]
    holdings_map = {h["ticker"]: h for h in holdings}
    total_value = market["total_value"]
    dry_powder = market.get("cash_manual", 0.0)
    
    thesis_docs = {doc["ticker"]: doc for doc in vault["documents"] if doc.get("doc_type") == "thesis"}
    style_weights = compute_style_weights(holdings, thesis_docs)
    
    parsed_notes = {}
    if notes:
        try:
            parsed_notes = json.loads(notes)
        except:
            console.print("[yellow]⚠ Could not parse --notes JSON string. Ignoring.[/]")

    candidates_pre = []
    
    for ticker in ticker_list:
        with console.status(f"[cyan]Fetching data for {ticker}..."):
            # Market data from yfinance (fast_info is an object — use getattr, not .get())
            try:
                fi = yf.Ticker(ticker).fast_info
                current_price = getattr(fi, "last_price", 0.0) or 0.0
                high_52w = getattr(fi, "year_high", 0.0) or 0.0
                low_52w = getattr(fi, "year_low", 0.0) or 0.0

                discount_from_52w_high_pct = ((high_52w - current_price) / high_52w * 100) if high_52w > 0 else 0.0
                price_52w_range_position_pct = ((current_price - low_52w) / (high_52w - low_52w) * 100) if (high_52w - low_52w) > 0 else 0.0
            except Exception as e:
                console.print(f"[yellow]⚠ yfinance error for {ticker}: {e}[/]")
                current_price = high_52w = low_52w = discount_from_52w_high_pct = price_52w_range_position_pct = 0.0

            # Fundamental data — new ideas aren't in the bundle so call live.
            # get_fundamentals() uses three-tier: yfinance → FMP cache (rate-limited).
            try:
                fundamentals = get_fundamentals(ticker)
                pe_fwd        = fundamentals.get("forward_pe")
                pe_trailing   = fundamentals.get("trailing_pe")
                revenue_growth_yoy = fundamentals.get("revenue_growth")
                gross_margin  = fundamentals.get("gross_margin")
                market_cap    = fundamentals.get("market_cap")
            except Exception as e:
                console.print(f"[yellow]⚠ fundamentals error for {ticker}: {e}[/]")
                pe_fwd = pe_trailing = revenue_growth_yoy = gross_margin = market_cap = None

            # Overlap check
            already_held = ticker in holdings_map
            current_weight_pct = holdings_map.get(ticker, {}).get("weight_pct", 0.0)

            # Data gaps
            raw_data = {
                "pe_fwd": pe_fwd,
                "pe_trailing": pe_trailing,
                "market_cap": market_cap,
            }
            data_gaps = [k for k, v in raw_data.items() if v is None]
            
            # Sizing
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
                "data_gaps": data_gaps,
                "user_note": parsed_notes.get(ticker, ""),
                "starter_size_usd": round(starter_size_usd, 2)
            })

    # 5. Build context for Gemini
    agent_context = {
        "portfolio_state": {
            "total_value_usd": total_value,
            "dry_powder_available_usd": dry_powder,
            "position_count": len(holdings),
            "style_weights": style_weights,
        },
        "styles": styles_json,
        "current_holdings_tickers": [h["ticker"] for h in holdings],
        "candidates": candidates_pre,
        "bundle_hash": composite.get("composite_hash", "unknown")
    }
    
    # 6. Load system prompt
    prompt_path = _HERE / "prompts" / "new_idea_system.txt"
    system_instruction = prompt_path.read_text(encoding="utf-8")
    
    # 7. LLM Call
    user_prompt = f"Evaluate these candidate tickers and assign verdicts.\n\nContext:\n{json.dumps(agent_context, indent=2)}"
    
    console.print(f"[cyan]Calling Gemini for {len(candidates_pre)} candidates...[/]")
    result: NewIdeaScreenerOutput | None = ask_gemini_composite(
        prompt=user_prompt,
        composite_bundle_path=bundle_path,
        response_schema=NewIdeaScreenerOutput,
        system_instruction=system_instruction,
        max_tokens=16000
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
    
    # 9. Write to Sheets if --live
    if live:
        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_AGENT_OUTPUTS)
        
        # Fingerprint: bundle_hash[:12]|ticker|new_idea
        new_rows = []
        for v in result.verdicts:
            fp = f"{result.bundle_hash[:12]}|{v.ticker}|new_idea"
            
            signal_type = "new_idea_fit" if v.verdict == "fit" else "new_idea_screen"
            action = f"Fit: {v.style_assignment}" if v.verdict == "fit" else v.verdict.replace("_", " ").title()
            
            new_rows.append([
                result.generated_at,
                "new_idea_screener",
                result.bundle_hash,
                v.ticker,
                v.style_assignment or "N/A",
                signal_type,
                action,
                v.fit_rationale[:500],
                v.scale_step_note or "N/A",
                "watch" if v.verdict == "fit" else "info",
                str(v.data_gaps_impact),
                "", # user note?
                fp
            ])
            
        if new_rows:
            ws.append_rows(new_rows, value_input_option="USER_ENTERED")
            console.print(f"[green]SUCCESS: Wrote {len(new_rows)} rows to {config.TAB_AGENT_OUTPUTS}[/]")

if __name__ == "__main__":
    app()
