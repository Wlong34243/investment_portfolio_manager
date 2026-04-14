"""
100-Bagger Screener Agent — Christopher Mayer Framework.

Evaluates potential portfolio additions against strict ROIC, Growth, 
and Insider Ownership thresholds to identify extreme compounders.

Usage:
    python agents/bagger_screener_agent.py --live
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project root to path so config is importable
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import typer
from rich.console import Console
from rich.panel import Panel
from pydantic import BaseModel, Field

import config
# Assuming a generic schema exists or create one here for the screener
from core.composite_bundle import load_composite_bundle, resolve_latest_bundles
from utils.gemini_client import ask_gemini_composite
from utils.sheet_readers import get_gspread_client

app = typer.Typer(help="100-Bagger Screener Agent")
console = Console()

AGENT_OUTPUTS_TAB = "AI_Suggested_Allocation"

# Define the Pydantic Schema for this specific agent's output
class BaggerCandidate(BaseModel):
    ticker: str
    roic_score: str = Field(description="Evaluation of the 5-year average ROIC vs the 15% threshold.")
    moat_evaluation: str = Field(description="Evaluation of gross margins and competitive advantage.")
    skin_in_the_game: str = Field(description="Analysis of insider ownership and founder presence.")
    twin_engine_potential: str = Field(description="Assessment of current valuation multiple vs future earnings growth.")
    final_recommendation: str = Field(description="Strictly one of: 'STRONG_BUY', 'WATCHLIST', 'REJECT'")
    fundamental_reason: str = Field(description="One sentence summarizing why this is or isn't a 100-bagger candidate.")

class BaggerScreenerResponse(BaseModel):
    bundle_hash: str
    analysis_timestamp_utc: str
    candidates_analyzed: list[BaggerCandidate]

SYSTEM_INSTRUCTION = """
ROLE DEFINITION
You are an elite AI stock screener designed to identify "100-Baggers" — companies capable of 
returning 100 times their initial investment over the next 15 to 25 years. You operate strictly 
on the principles of Christopher Mayer and the 'Coffee-Can Portfolio'.

PART 1: THE QUANTITATIVE GATE (HARD RULES)
Evaluate the fundamental data provided in the market bundle against these thresholds:
1. Return on Invested Capital (ROIC): Must average > 15%. This is non-negotiable.
2. Gross Margins: Must be > 30%, indicating pricing power and a durable economic moat.
3. Revenue Growth: Must be organic and > 10% annually.
4. Dividends: Punish companies with high dividend payouts; cash must be reinvested internally.

PART 2: THE QUALITATIVE TREASURE
If the candidate survives the quantitative gate, evaluate its management:
1. Skin in the Game: Insider ownership should ideally exceed 10%. Favor founder-led businesses.
2. Share Repurchases: Reward companies that opportunistically buy back their own stock, increasing per-share value.

PART 3: THE TWIN ENGINES
Evaluate the current valuation multiple (P/E or EV/EBITDA). A 100-bagger requires both earnings 
growth AND multiple expansion. Do not overpay for growth.

CRITICAL INSTRUCTIONS:
Read the `100_baggers_framework.json` from the vault bundle for deep context.
If a company fails the ROIC or Margin tests, aggressively classify it as 'REJECT'. 
Output your evaluation strictly matching the requested JSON schema.
"""

@app.command()
def run_agent(live: bool = typer.Option(False, "--live", help="Execute live writes to Google Sheets")):
    """Run the 100-Bagger screener over candidates in the composite bundle."""
    console.print(f"[bold cyan]Starting 100-Bagger Screener Agent (Live={live})[/bold cyan]")
    
    # 1. Resolve and Load the Immutable Bundle
    market_path, vault_path = resolve_latest_bundles()
    composite = load_composite_bundle(market_path, vault_path)
    
    # 2. AI Reasoning Phase
    console.print("[bold blue]Querying Gemini with composite bundle and Christopher Mayer prompt...[/bold blue]")
    result = ask_gemini_composite(
        system_instruction=SYSTEM_INSTRUCTION,
        composite_bundle=composite,
        response_schema=BaggerScreenerResponse
    )
    
    if not result:
        console.print("[bold red]Failed to get a response from Gemini.[/bold red]")
        raise typer.Exit(1)
        
    console.print("[bold green]Analysis complete. Preparing to write outputs...[/bold green]")

    # 3. Sandbox Write Phase
    if live:
        client = get_gspread_client()
        sheet = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = sheet.worksheet(AGENT_OUTPUTS_TAB)
        
        # Fetch existing fingerprints to dedup
        all_vals = ws.get_all_values()
        fp_col_idx = 12 
        existing_fps = {row[fp_col_idx] for row in all_vals[1:] if len(row) > fp_col_idx}

        new_rows = []
        for c in result.candidates_analyzed:
            # Unique fingerprint for deduplication
            fp = f"{result.bundle_hash[:12]}|{c.ticker}|bagger_screener|{c.final_recommendation}"
            if fp in existing_fps:
                continue
                
            new_rows.append([
                datetime.now(timezone.utc).isoformat(),
                "bagger_screener_agent",
                result.bundle_hash,
                c.ticker,
                "N/A", # Paradigm phase not applicable here
                f"ROIC: {c.roic_score[:50]}...",
                "N/A", # Stop loss not applicable here
                c.final_recommendation,
                "N/A", # Rotation priority not applicable
                c.skin_in_the_game, 
                c.fundamental_reason,
                c.twin_engine_potential,
                fp
            ])

        if new_rows:
            ws.append_rows(new_rows, value_input_option="USER_ENTERED")
            console.print(f"[bold green]Successfully wrote {len(new_rows)} bagger candidates to {AGENT_OUTPUTS_TAB}.[/bold green]")
        else:
            console.print("[yellow]No new unique candidate analyses to write (deduplicated).[/yellow]")
    else:
        console.print("[yellow]DRY RUN active. Skipping write to Google Sheets.[/yellow]")
        for candidate in result.candidates_analyzed[:2]:
            console.print(Panel(f"Ticker: {candidate.ticker}\nRecommendation: {candidate.final_recommendation}\nReason: {candidate.fundamental_reason}", title="Bagger Candidate Screen"))

if __name__ == "__main__":
    app()