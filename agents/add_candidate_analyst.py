"""
Add-Candidate Analyst — identifies current holdings for potential adds.

Reads the composite bundle (market + vault), filters candidates,
pre-computes sizing in Python, and passes the context to Gemini
for qualitative ranking and scaling plan generation.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add project root to path
_HERE = Path(__file__).parent.resolve()
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from agents.schemas.add_candidate_schema import AddCandidateOutput
from core.composite_bundle import load_composite_bundle
from core.bundle import load_bundle
from core.vault_bundle import load_vault_bundle
from utils.gemini_client import ask_gemini_composite
from utils.formatters import dicts_to_markdown_table

app = typer.Typer(help="Add-Candidate Analyst Agent")
console = Console()

def parse_scaling_state(doc: dict) -> str:
    """
    Infers position state from the vault document.
    Priority:
    1. scaling_state field from the bundle (extracted from next_step:)
    2. HTML comment current_position: ...
    3. Content scan for "starter" | "half" | "full"
    """
    # 1. scaling_state from bundle
    raw_state = (doc.get("scaling_state") or "").lower()
    if any(s in raw_state for s in ["starter", "half", "full"]):
        for s in ["starter", "half", "full"]:
            if s in raw_state:
                return s
                
    # 2. Content scan
    content = (doc.get("content") or "").lower()
    
    # Check for HTML comment
    import re
    comment_match = re.search(r"current_position:\s*(\w+)", content)
    if comment_match:
        val = comment_match.group(1).lower()
        if val in ["starter", "half", "full"]:
            return val
            
    # Naive scan
    if "starter" in content: return "starter"
    if "half" in content: return "half"
    if "full" in content: return "full"
    
    return "unknown"

@app.command()
def analyze(
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
    """Analyze current holdings for potential add candidates."""
    
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
    total_value = market["total_value"]
    dry_powder = market.get("cash_manual", 0.0)
    today = datetime.now(timezone.utc)
    
    thesis_docs = {doc["ticker"]: doc for doc in vault["documents"] if doc.get("doc_type") == "thesis"}
    
    candidates_raw = []
    excluded = []
    
    for h in holdings:
        ticker = h["ticker"]
        # Skip cash
        if ticker in config.CASH_TICKERS:
            continue
            
        doc = thesis_docs.get(ticker, {})
        
        # Style filtering
        # Note: mapping verbose style to short code for filtering
        # style codes: GARP | THEME | FUND | ETF
        style_raw = (doc.get("style") or "").lower()
        style_code = "UNKNOWN"
        if "garp" in style_raw or "boring" in style_raw:
            style_code = "GARP"
        elif "thematic" in style_raw or "theme" in style_raw:
            style_code = "THEME"
        elif "fund" in style_raw or "etf" in style_raw:
            style_code = "ETF" # or FUND? prompt says STYLE codes are always GARP, THEME, FUND, ETF
        
        if "developed international" in style_raw: style_code = "FUND"
        if "emerging market" in style_raw: style_code = "FUND"
            
        if style_code == "UNKNOWN" or style_code not in ["GARP", "THEME", "FUND", "ETF"]:
            excluded.append({"ticker": ticker, "reason": "non_style_bucket"})
            continue
            
        # Rotation priority filter
        rp_raw = (doc.get("rotation_priority") or "").lower()
        if "high" in rp_raw:
            excluded.append({"ticker": ticker, "reason": "rotation_candidate"})
            continue
            
        # Thesis status filter
        # next_step is captured in scaling_state in vault_bundle
        scaling_state_raw = (doc.get("scaling_state") or "").lower()
        if "broken" in scaling_state_raw:
            excluded.append({"ticker": ticker, "reason": "broken_thesis"})
            continue
            
        # Weight drift
        current_weight = h.get("weight_pct", 0.0)
        target_weight = 0.0 # We don't have Target_Allocation in the bundle yet?
        # Re-reading prompt 5-J: weight_vs_target_pct = current_weight_pct - target_weight_pct
        # If target_weight is unknown, we assume 0 for now or skip overweight check?
        # Actually, let's assume if it's over 10% of portfolio it's overweight as a safeguard.
        already_overweight = current_weight > config.SINGLE_POSITION_WARN_PCT
        if already_overweight:
            excluded.append({"ticker": ticker, "reason": "overweight"})
            continue
            
        # Staleness
        # vault_bundle doesn't have last_reviewed_date as a structured field yet?
        # Wait, I should check VaultDocument again.
        # core/vault_bundle.py: VaultDocument has no last_reviewed_date.
        # But frontmatter parsing in framework_selector.py does.
        # Actually, vault_bundle.py DOES NOT use it.
        # I'll just look for a date in the content or Review Log.
        staleness_days = 0
        stale_flag = False
        import re
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", doc.get("content") or "")
        if date_match:
            try:
                last_date = datetime.strptime(date_match.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                staleness_days = (today - last_date).days
                stale_flag = staleness_days > config.ADD_CANDIDATE_STALE_THRESHOLD_DAYS
            except:
                pass
                
        # Max starter add size
        style_pct = config.ADD_CANDIDATE_STYLE_PCT.get(style_code, 0.015)
        max_starter_add_usd = dry_powder * style_pct
        # Apply cap
        max_starter_add_usd = min(max_starter_add_usd, dry_powder * config.ADD_CANDIDATE_MAX_STARTER_PCT)
        
        # Position state
        pos_state = parse_scaling_state(doc)
        
        candidates_raw.append({
            "ticker": ticker,
            "style": style_code,
            "rotation_priority": rp_raw.split()[0] if rp_raw else "unknown",
            "current_weight_pct": current_weight,
            "target_weight_pct": 0.0, # Placeholder
            "weight_vs_target_pct": current_weight, # Placeholder
            "position_state": pos_state,
            "thesis_status": scaling_state_raw or "intact",
            "stale_flag": stale_flag,
            "staleness_days": staleness_days,
            "max_starter_add_usd": round(max_starter_add_usd, 2),
            "thesis_excerpt": (doc.get("content") or "")[:400]
        })

    # 5. Build context for Gemini
    # Markdown optimization (Task 4)
    candidates_table = dicts_to_markdown_table(candidates_raw)
    excluded_table = dicts_to_markdown_table(excluded)
    
    agent_context_text = (
        f"Portfolio Summary:\n"
        f"- Total Value: ${total_value:,.2f}\n"
        f"- Dry Powder: ${dry_powder:,.2f}\n"
        f"- Position Count: {len(holdings)}\n\n"
        f"Investment Styles:\n{json.dumps(styles_json, indent=2)}\n\n"
        f"Potential Candidates:\n{candidates_table}\n\n"
        f"Excluded Positions:\n{excluded_table}\n\n"
        f"composite_hash: {composite.get('composite_hash', 'unknown')}"
    )
    
    # 6. Load system prompt
    prompt_path = _HERE / "prompts" / "add_candidate_system.txt"
    system_instruction = prompt_path.read_text(encoding="utf-8")
    
    # 7. LLM Call
    user_prompt = f"Review these potential add candidates and produce a ranked list with scaling plans.\n\nContext:\n{agent_context_text}"
    
    console.print(f"[cyan]Calling Gemini for {len(candidates_raw)} potential candidates...[/]")
    result: AddCandidateOutput | None = ask_gemini_composite(
        prompt=user_prompt,
        composite_bundle_path=bundle_path,
        response_schema=AddCandidateOutput,
        system_instruction=system_instruction,
        max_tokens=16000
    )
    
    if not result:
        console.print("[red]ERROR: Gemini returned no result.[/]")
        raise typer.Exit(1)
        
    # 8. Output Summary
    table = Table(title="Add-Candidate Analysis")
    table.add_column("Rank", justify="right")
    table.add_column("Ticker", style="bold")
    table.add_column("Style")
    table.add_column("Starter Add ($)")
    table.add_column("Priority")
    
    for c in result.candidates[:10]: # Top 10 in table
        table.add_row(
            str(c.rank),
            c.ticker,
            c.style,
            f"{c.starter_add_size_usd:,.2f}",
            c.rotation_priority
        )
    console.print(table)
    
    # 9. Write to Sheets if --live
    if live:
        from utils.sheet_readers import get_gspread_client
        client = get_gspread_client()
        ss = client.open_by_key(config.PORTFOLIO_SHEET_ID)
        ws = ss.worksheet(config.TAB_AGENT_OUTPUTS)
        
        # Fingerprint: bundle_hash[:12]|ticker|add_candidate|rank
        new_rows = []
        for c in result.candidates:
            fp = f"{result.bundle_hash[:12]}|{c.ticker}|add_candidate|{c.rank}"
            
            # Row mapping: Timestamp, Agent, Hash, Ticker, ...
            # Reusing the rebuy_analyst column pattern where possible
            new_rows.append([
                result.generated_at,
                "add_candidate_analyst",
                result.bundle_hash,
                c.ticker,
                c.style,
                str(c.thesis_status),
                c.position_state,
                f"Rank: {c.rank} | Add Size: ${c.starter_add_size_usd:,.2f}",
                c.rotation_priority,
                f"{c.stale_flag} ({c.staleness_days}d)",
                c.add_case,
                c.trigger_suggestion,
                fp
            ])
            
        if new_rows:
            ws.append_rows(new_rows, value_input_option="USER_ENTERED")
            console.print(f"[green]SUCCESS: Wrote {len(new_rows)} rows to {config.TAB_AGENT_OUTPUTS}[/]")

if __name__ == "__main__":
    app()
