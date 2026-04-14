"""
Thesis Screener Agent — Gautam Baid Framework.

Evaluates management quality, candor, and capital stewardship from earnings
transcripts and cross-references them against your original investment theses.

Usage:
    python utils/agents/thesis_screener.py --live
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Add project root to path so config is importable
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent.parent
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

app = typer.Typer(help="Thesis Screener Agent")
console = Console()

AGENT_OUTPUTS_TAB = "AI_Suggested_Allocation"

# Define the Pydantic Schema for the AI's Output
class ManagementEvaluation(BaseModel):
    ticker: str
    linguistic_candor_score: str = Field(description="Evaluation of FOG, restructuring abuse, and owning mistakes.")
    capital_stewardship_score: str = Field(description="Evaluation of ROIC focus, buyback prudence, and M&A discipline.")
    alignment_score: str = Field(description="Evaluation of skin in the game, insider buying, and salary structures.")
    red_flags_identified: List[str] = Field(description="Any behavioral red flags, fad-chasing, or governance issues.")
    inner_scorecard_assessment: str = Field(description="Does leadership exhibit an inner or outer scorecard?")
    thesis_alignment_warning: str = Field(description="Does the current management behavior threaten the original core_thesis or trigger an exit_condition?")
    pre_mortem_behavioral_check: str = Field(description="Check against WYSIATI, Disposition Effect, Action Bias, Anchoring, Envy, and Hyperbolic Discounting. Are we downgrading prematurely due to bias?")
    final_recommendation: str = Field(description="Strictly one of: 'MAINTAIN_CONVICTION', 'WATCHLIST_DOWNGRADE', 'THESIS_VIOLATED'")

class ThesisScreenerResponse(BaseModel):
    bundle_hash: str
    analysis_timestamp_utc: str
    evaluations: list[ManagementEvaluation]

SYSTEM_INSTRUCTION = """
ROLE DEFINITION
You are an elite AI qualitative analyst and thesis screener. Your job is to evaluate corporate 
management teams by reading between the lines of earnings transcripts, news, and shareholder letters.
You evaluate companies based strictly on Gautam Baid's "The Joys of Compounding" framework.

PART 1: THE MANAGEMENT SCORING RUBRIC
You must evaluate the transcripts in the market bundle against these four pillars:
1. Linguistic Candor: Penalize "FOG" (meaningless platitudes) and the abuse of "restructuring". Reward explicitly quantifying mistakes.
2. Capital Stewardship: Reward rational ROIC/ROI discussions and prudent share buybacks. Penalize empire-building M&A.
3. Skin in the Game: Look for low salaries, high stock ownership, and "cluster-buys".
4. Red Flags: Search for stock price obsession, fad-chasing buzzwords, and questionable governance.

PART 2: INNER VS OUTER SCORECARD
Assess whether the CEO operates on an Inner Scorecard (focused on internal standards and doing the right thing) or an Outer Scorecard (obsessed with Wall Street validation and appearances).

PART 3: THESIS ALIGNMENT
Compare your management evaluation against the original `_thesis.md` file provided in the vault bundle for that specific ticker. 
Does the management's recent behavior invalidate the `core_thesis`? Does it trigger any of the user's predefined `exit_conditions`?

PART 4: BEHAVIORAL GUARDRAILS (THE PRE-MORTEM)
Before you ever recommend 'WATCHLIST_DOWNGRADE' or 'THESIS_VIOLATED', you MUST run the decision through the 6 Behavioral Guardrails:
1. WYSIATI: Are you overreacting to a vivid short-term earnings miss while the long-term base rate is fine?
2. Disposition Effect: Are you recommending a sell just to lock in a mental profit (cutting the flowers)?
3. Action Bias: Is this downgrade just "action for action's sake" during market volatility?
4. Anchoring Bias: Are you anchoring to the original purchase price rather than future earning power?
5. Envy/Social Proof: Are you rotating out of a boring compounder to chase a fad?
6. Hyperbolic Discounting: Are you punishing a company for depressing short-term earnings to build a massive long-term moat (e.g., heavy R&D)?

CRITICAL INSTRUCTIONS:
Read the `joys_of_compounding_framework.json` from the vault bundle for deep context.
If management triggers severe red flags (fad-chasing, outer scorecard obsession) that violate the original thesis, you must classify the recommendation as 'THESIS_VIOLATED'.
If your downgrade is blocked by a behavioral guardrail, default to 'MAINTAIN_CONVICTION'.
Output your evaluation strictly matching the requested JSON schema.
"""

@app.command()
def run_agent(live: bool = typer.Option(False, "--live", help="Execute live writes to Google Sheets")):
    """Run the Thesis Screener agent over the composite bundle."""
    console.print(f"[bold cyan]Starting Thesis Screener Agent (Live={live})[/bold cyan]")
    
    # 1. Resolve and Load the Immutable Bundle
    market_path, vault_path = resolve_latest_bundles()
    composite = load_composite_bundle(market_path, vault_path)
    
    # 2. AI Reasoning Phase
    console.print("[bold blue]Querying Gemini with composite bundle and Qualitative Management rules...[/bold blue]")
    result = ask_gemini_composite(
        system_instruction=SYSTEM_INSTRUCTION,
        composite_bundle=composite,
        response_schema=ThesisScreenerResponse
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
        for eval_obj in result.evaluations:
            # Unique fingerprint for deduplication
            fp = f"{result.bundle_hash[:12]}|{eval_obj.ticker}|thesis_screener|{eval_obj.final_recommendation}"
            if fp in existing_fps:
                continue
                
            red_flags_str = ", ".join(eval_obj.red_flags_identified) if eval_obj.red_flags_identified else "None"
            
            new_rows.append([
                datetime.now(timezone.utc).isoformat(),
                "thesis_screener",
                result.bundle_hash,
                eval_obj.ticker,
                "N/A", # Paradigm phase
                f"Scorecard: {eval_obj.inner_scorecard_assessment[:40]}...",
                "N/A", # Stop loss
                eval_obj.final_recommendation,
                "N/A", # Rotation priority
                f"Pre-Mortem: {eval_obj.pre_mortem_behavioral_check[:40]}...", # Replacing Confidence placeholder
                eval_obj.thesis_alignment_warning,
                f"Red Flags: {red_flags_str}",
                fp
            ])

        if new_rows:
            ws.append_rows(new_rows, value_input_option="USER_ENTERED")
            console.print(f"[bold green]Successfully wrote {len(new_rows)} thesis evaluations to {AGENT_OUTPUTS_TAB}.[/bold green]")
        else:
            console.print("[yellow]No new unique thesis analyses to write (deduplicated).[/yellow]")
    else:
        console.print("[yellow]DRY RUN active. Skipping write to Google Sheets.[/yellow]")
        for eval_obj in result.evaluations[:3]:
            flags = ", ".join(eval_obj.red_flags_identified) if eval_obj.red_flags_identified else "None"
            console.print(Panel(
                f"Ticker: {eval_obj.ticker}\n"
                f"Recommendation: {eval_obj.final_recommendation}\n"
                f"Candor: {eval_obj.linguistic_candor_score}\n"
                f"Stewardship: {eval_obj.capital_stewardship_score}\n"
                f"Pre-Mortem Check: {eval_obj.pre_mortem_behavioral_check}\n"
                f"Thesis Warning: {eval_obj.thesis_alignment_warning}", 
                title="Management Evaluation"
            ))

if __name__ == "__main__":
    app()