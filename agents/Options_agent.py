"""
Options Yield Agent — Premium Selling, Volatility Scanner, & Tail Risk Management.

Evaluates options chain data (from Schwab API) to identify mispriced 
premiums based on Relative Volatility Rank (RVR), Greeks, and Expected Value.

Usage:
    python utils/agents/options_agent.py --live
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

import config
from core.composite_bundle import load_composite_bundle, resolve_latest_bundles
from utils.gemini_client import ask_gemini_composite
from utils.sheet_readers import get_gspread_client
from utils.sheet_writers import append_agent_outputs

app = typer.Typer(help="Options Yield Agent")
console = Console()

AGENT_OUTPUTS_TAB = "AI_Suggested_Allocation"

# Define the Pydantic Schema for this agent's output
class YieldCandidate(BaseModel):
    ticker: str
    strategy_type: str = Field(description="e.g., 'Cash-Secured Put', 'Covered Call', 'Vertical Spread'")
    strike_price: float
    expiration_date: str
    relative_volatility_rank: int = Field(description="The calculated rank from 1 to 10.")
    delta: float = Field(description="The Delta of the selected strike.")
    expected_value_analysis: str = Field(description="Break-even point and probability analysis of closing above break-even.")
    tail_risk_stop_loss: str = Field(description="The exact price level to place a stop-loss to prevent catastrophic tail risk.")
    volatility_skew_analysis: str = Field(description="Brief analysis of the skew across strikes/months.")
    final_recommendation: str = Field(description="Strictly one of: 'EXECUTE', 'WATCHLIST', 'REJECT'")
    fundamental_reason: str = Field(description="Explanation of why the premium is statistically cheap/expensive and justifies the risk.")

class OptionsYieldResponse(BaseModel):
    bundle_hash: str
    analysis_timestamp_utc: str
    yield_opportunities: list[YieldCandidate]

SYSTEM_INSTRUCTION = """
ROLE DEFINITION
You are an institutional algorithmic options trader focused exclusively on selling premium 
(Yield Generation). You do not predict stock direction; you trade mathematical mispricings 
in Implied Volatility (IV) using strict Expected Value and Risk frameworks.

PART 1: THE VOLATILITY & GREEKS GATES
Evaluate the options chain data provided in the market bundle:
1. Volatility Rank: ONLY initiate premium-selling strategies when the Relative Volatility Rank is high (6 to 10). Reject Ranks 1 to 4.
2. Delta: For Cash-Secured Puts, target Delta between 0 and -0.50. For Covered Calls, target Delta < 0.50.
3. Theta/DTE: Maximize time decay by strictly selecting options with 60 days or fewer until expiration.
4. Gamma Risk: Avoid holding short options deep ITM inside the 14-DTE window.

PART 2: EXPECTED VALUE & TAIL RISK (NAKED PUTS)
Before recommending an execution, you MUST calculate the mathematical expectation:
1. Calculate the exact break-even point (Strike Price minus Premium Collected).
2. Because the reward-to-risk ratio on a naked put is heavily skewed toward risk, you MUST define a strict stop-loss. Calculate how far the stock must drop to generate an open loss equal to the maximum profit potential, and set that as the `tail_risk_stop_loss`.

PART 3: VOLATILITY SKEW
When evaluating vertical spreads, target relative mispricing by selling higher-volatility (expensive) options and buying lower-volatility (cheap) options to define tail risk.

CRITICAL INSTRUCTIONS:
Read the `natenberg_options_framework.json` from the vault bundle for deep context on these rules.
If the underlying asset lacks high IV or the tail risk is mathematically unjustifiable, classify the opportunity as 'REJECT'.
Output your evaluation strictly matching the requested JSON schema.
"""

@app.command()
def run_agent(live: bool = typer.Option(False, "--live", help="Execute live writes to Google Sheets")):
    """Run the Options Yield agent over the composite bundle chains."""
    console.print(f"[bold cyan]Starting Options Yield Agent (Live={live})[/bold cyan]")
    
    # 1. Resolve and Load the Immutable Bundle
    market_path, vault_path = resolve_latest_bundles()
    composite = load_composite_bundle(market_path, vault_path)
    
    # Check if options chain data exists in the bundle (Phase 6 feature)
    if "options_chains" not in composite.get("market_data", {}):
        console.print("[yellow]Warning: No options_chains data found in market bundle. Ensure Schwab /chains endpoint is active.[/yellow]")
    
    # 2. AI Reasoning Phase
    console.print("[bold blue]Querying Gemini with composite bundle and Kaeppel Volatility/Probability rules...[/bold blue]")
    result = ask_gemini_composite(
        system_instruction=SYSTEM_INSTRUCTION,
        composite_bundle=composite,
        response_schema=OptionsYieldResponse
    )
    
    if not result:
        console.print("[bold red]Failed to get a response from Gemini.[/bold red]")
        raise typer.Exit(1)
        
    console.print("[bold green]Analysis complete. Preparing to write outputs...[/bold green]")

    # 3. Sandbox Write Phase
    if live:
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)

        new_rows = []
        for opp in result.yield_opportunities:
            # Unique fingerprint for deduplication
            fp = f"{result.bundle_hash[:12]}|{opp.ticker}|options_yield|{opp.strategy_type}|{opp.strike_price}"
                
            new_rows.append([
                datetime.now(timezone.utc).isoformat(),
                "options_agent",
                result.bundle_hash,
                opp.ticker,
                "N/A", # Paradigm phase
                f"Vol Rank: {opp.relative_volatility_rank}/10 | Delta: {opp.delta}",
                f"Stop Loss @ {opp.tail_risk_stop_loss}", 
                opp.final_recommendation,
                "N/A", # Rotation priority
                "N/A", # Confidence
                f"Break-Even: {opp.expected_value_analysis}",
                opp.volatility_skew_analysis,
                fp
            ])

        if new_rows:
            # Task 4: Centralized Writer (Append pattern)
            headers = [
                "Run Timestamp", "Agent", "Bundle Hash", "Ticker",
                "Paradigm Phase", "Action", "Rationale", "Rec",
                "Priority", "Confidence", "Math", "Skew", "Fingerprint"
            ]
            append_agent_outputs(ss, new_rows, headers)
            console.print(f"[bold green]Analysis complete.[/bold green]")
        else:
            console.print("[yellow]No new unique yield analyses to write.[/yellow]")
    else:
        console.print("[yellow]DRY RUN active. Skipping write to Google Sheets.[/yellow]")
        for opp in result.yield_opportunities:
            console.print(Panel(
                f"Ticker: {opp.ticker}\n"
                f"Strategy: {opp.strategy_type} @ {opp.strike_price} (Exp: {opp.expiration_date})\n"
                f"Rank: {opp.relative_volatility_rank}/10 | Delta: {opp.delta}\n"
                f"Break-Even Math: {opp.expected_value_analysis}\n"
                f"Required Stop Loss: {opp.tail_risk_stop_loss}\n"
                f"Recommendation: {opp.final_recommendation}", 
                title="Yield Opportunity Screen"
            ))

if __name__ == "__main__":
    app()