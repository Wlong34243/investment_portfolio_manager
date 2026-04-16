"""
100-Bagger Screener Agent — Christopher Mayer Framework.

Evaluates potential portfolio additions against strict ROIC, Growth, 
Gross Margin, and Market Cap thresholds to identify extreme compounders.

Usage:
    python agents/bagger_screener_agent.py --live
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path so config is importable
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import typer
from rich.console import Console
from rich.panel import Panel
from pydantic import BaseModel, Field
from typing import List, Optional

import config
from core.composite_bundle import load_composite_bundle, resolve_latest_bundles
from utils.gemini_client import ask_gemini_composite
from utils.sheet_readers import get_gspread_client

app = typer.Typer(help="100-Bagger Screener Agent")
console = Console()

AGENT_OUTPUTS_TAB = "AI_Suggested_Allocation"

class ScalingState(BaseModel):
    next_step: str = Field(description="The next action for the asset, e.g., 'hold', 'hold / reinvest dividends'")

class RotationPriority(BaseModel):
    priority: str = Field(description="The rotation priority level, e.g., 'low', 'medium', 'high', 'very low'")

class InvestmentThesis(BaseModel):
    # Header Metadata
    ticker: str
    header_style: Optional[str] = Field(None, alias="style")
    framework_preference: Optional[str] = None
    entry_date: Optional[str] = None
    last_reviewed: Optional[str] = None

    # Core Text Fields
    style: str = Field(description="The expanded investment style, e.g., 'GARP / Cash Flow Compounder'")
    core_thesis: str = Field(description="The primary argument for owning the asset.")
    entry_context: str = Field(description="Details on the cost basis and valuation at entry.")
    
    # Bulleted Lists
    bull_case: List[str] = Field(description="A list of bull case arguments and catalysts.")
    key_risks: List[str] = Field(description="A list of potential risks and headwinds.")
    
    # Nested State/Priority Fields
    scaling_state: ScalingState
    rotation_priority: RotationPriority
    
    # Management & Review
    exit_conditions: List[str] = Field(description="A list of specific conditions that would trigger a sale.")
    review_log: List[str] = Field(description="A list of historical review notes and dates.")

# Define the Pydantic Schema for this agent's output
class BaggerCandidate(BaseModel):
    ticker: str
    acorn_evaluation: str = Field(description="Analysis of Market Cap vs the $1B threshold.")
    roic_evaluation: str = Field(description="Evaluation of ROIC/ROE against the 18-20% threshold.")
    growth_evaluation: str = Field(description="Analysis of top-line revenue growth vs the 10% threshold.")
    margin_evaluation: str = Field(description="Analysis of Gross Margins (targeting 50%+).")
    dividend_evaluation: str = Field(description="Check for 0% payout / share repurchase prioritization.")
    final_recommendation: str = Field(description="Strictly one of: 'STRONG_BUY', 'WATCHLIST', 'REJECT'")
    fundamental_reason: str = Field(description="One sentence summarizing why this is or isn't a 100-bagger candidate.")
    quantitative_summary: str = Field(description="A short string summarizing the metrics, e.g. 'Cap: $500M, ROIC: 22%, Grwth: 15%'")

class BaggerScreenerResponse(BaseModel):
    bundle_hash: str
    analysis_timestamp_utc: str
    candidates_analyzed: list[BaggerCandidate]

SYSTEM_INSTRUCTION = """
ROLE DEFINITION
You are an elite AI stock screener designed to identify "100-Baggers" — companies capable of 
returning 100 times their initial investment over the next 15 to 25 years. You operate strictly 
on the quantitative principles defined by Christopher Mayer's research.

PART 1: THE QUANTITATIVE GATE (HARD RULES)
Evaluate the fundamental data provided in the market bundle against these non-negotiable thresholds:

1. The "Acorn" Principle (Market Cap):
   - Rule: Market Cap MUST be < $1 Billion (ideally around $500M).
   - Rationale: Massive companies cannot geometrically multiply a hundredfold.

2. Compounding Efficiency (ROIC / ROE):
   - Rule: ROIC or ROE MUST be >= 18% to 20%, sustained over 4 to 5 consecutive years.
   - Rationale: Proves the company can take profits and constantly reinvest at a high rate of return.

3. Top-Line Revenue Growth:
   - Rule: MUST be >= 10% sustained annual sales growth.
   - Rationale: High ROE without top-line growth goes nowhere. Growth is required.

4. Gross Margins (The Moat Indicator):
   - Rule: MUST be structurally high and persistent vs peers (e.g., > 50%).
   - Rationale: Mathematical proof of a moat; shows unique value competitors cannot undercut.

5. The Dividend Leak:
   - Rule: Target a 0% Dividend Payout.
   - Rationale: Dividends are a leak. Management must utilize excess free cash flow to aggressively buy back stock or reinvest internally.

CRITICAL INSTRUCTIONS:
Read the fundamental and market data from the provided composite bundle.
If a company fails the Acorn (Market Cap > $2B), ROIC (< 15%), or Growth (< 10%) tests, aggressively classify it as 'REJECT'. 
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
    console.print("[bold blue]Querying Gemini with composite bundle and Christopher Mayer quantitative rules...[/bold blue]")
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
                f"ROIC: {c.roic_evaluation[:50]}...",
                "N/A", # Stop loss not applicable here
                c.final_recommendation,
                "N/A", # Rotation priority not applicable
                "N/A", # Confidence placeholder
                c.fundamental_reason,
                c.quantitative_summary,
                fp
            ])

        if new_rows:
            ws.append_rows(new_rows, value_input_option="USER_ENTERED")
            console.print(f"[bold green]Successfully wrote {len(new_rows)} bagger candidates to {AGENT_OUTPUTS_TAB}.[/bold green]")
        else:
            console.print("[yellow]No new unique candidate analyses to write (deduplicated).[/yellow]")
    else:
        console.print("[yellow]DRY RUN active. Skipping write to Google Sheets.[/yellow]")
        for candidate in result.candidates_analyzed:
            console.print(Panel(
                f"Ticker: {candidate.ticker}\n"
                f"Recommendation: {candidate.final_recommendation}\n"
                f"Acorn Check: {candidate.acorn_evaluation}\n"
                f"Growth & ROIC: {candidate.quantitative_summary}\n"
                f"Reason: {candidate.fundamental_reason}", 
                title="Bagger Candidate Screen"
            ))

if __name__ == "__main__":
    app()