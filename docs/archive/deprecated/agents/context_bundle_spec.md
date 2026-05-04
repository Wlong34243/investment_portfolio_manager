# Context Bundle Specification

Every buy-list agent reads the same structured context bundle. The CLI assembles this
bundle deterministically in Python before invoking any agent. Agents never browse or
fetch — they reason over what they're given.

This is the "LLMs synthesize, APIs calculate" rule applied to data gathering:
**Python gathers, LLM reasons.**

---

## Bundle Structure

The bundle is a single JSON object passed to the agent as part of the user message
(not the system prompt — the system prompt stays stable, the bundle varies per run).

```json
{
  "bundle_version": "1.0",
  "generated_at": "2026-04-08T22:30:00Z",
  "generated_by": "rebuy_analyst.py",

  "portfolio_state": {
    "total_value": 480000,
    "cash_position": 86400,
    "cash_pct": 18.0,
    "dry_powder_available": 86400,
    "position_count": 52,
    "style_mix": {
      "GARP": 0.32,
      "THEME": 0.11,
      "FUND": 0.15,
      "ETF": 0.24,
      "BROAD_INDEX": 0.08,
      "BONDS": 0.05,
      "CASH": 0.18
    },
    "notes": "Bill is specifically building dry powder for an expected pullback. Cash is strategic, not indecision."
  },

  "styles": {
    // Full contents of config/styles.json inlined here.
    // Agents anchor against this for every classification decision.
  },

  "holdings": [
    {
      "ticker": "UNH",
      "current_weight_pct": 9.0,
      "target_weight_pct": 10.0,
      "market_value": 43309,
      "cost_basis": 38000,
      "unrealized_gl_pct": 14.0,
      "style": "GARP",
      "rotation_priority": "low",
      "thesis_status": "intact",
      "last_thesis_review": "2026-03-15",
      "thesis_file_excerpt": "...first 500 chars of _thesis.md..."
    }
    // ... full list
  ],

  "recent_rotations": [
    {
      "date": "2026-03-20",
      "type": "dry_powder",
      "sold": [
        {"ticker": "EEM", "proceeds": 12000, "original_thesis_brief": "EM exposure via broad basket"},
        {"ticker": "VTI", "proceeds": 25000, "original_thesis_brief": "Broad US market ballast"}
      ],
      "bought": [{"ticker": "CASH", "amount": 37000}],
      "implicit_bet": "Pullback within 3 months will offer better entry points than current levels",
      "redeployment_triggers": []
    }
    // ... last 90 days
  ],

  "thesis_files": {
    // Per-ticker full thesis file contents, keyed by ticker.
    // Only for tickers relevant to the current agent's task
    // (e.g., Re-buy Analyst only needs files for recently-sold tickers +
    //  any existing holdings in those names).
    "UNH": "...full contents of thesis_files/UNH/_thesis.md...",
    "EEM": "...or a placeholder if no thesis file exists yet..."
  },

  "agent_specific_context": {
    // Varies per agent. See individual agent prompts for what each expects.
  }
}
```

---

## Assembly Rules

1. **Deterministic.** Same inputs produce the same bundle. No randomness, no LLM calls
   during assembly.

2. **Minimal but sufficient.** Don't dump the whole portfolio history into every bundle.
   Each agent gets what it needs for its specific task. The Re-buy Analyst needs recent
   rotations + thesis files for sold tickers. The Add-Candidate Analyst needs current
   holdings + their thesis files. Don't mix.

3. **Token budget.** Target ~8K tokens per bundle. If thesis files are long, excerpt them
   with a clear marker. Never silently truncate.

4. **Stale data is flagged, not hidden.** If a holding's `last_thesis_review` is older
   than 120 days, include a `stale: true` flag on that holding. The agent should be told
   to note this in its output.

5. **Missing thesis files are explicit.** If a ticker has no `_thesis.md` file, the bundle
   says so explicitly (`"thesis_file_excerpt": null, "has_thesis": false`) rather than
   omitting the field. The agent should surface "this ticker needs a backfilled thesis"
   in its output.

---

## Python Assembly Function (pseudo-code)

```python
def assemble_context_bundle(agent_name: str, config: Config) -> dict:
    """
    Assembles the context bundle for a given agent.
    Reads from: Google Sheets (Holdings_Current, Trade_Log),
                Vault (thesis files),
                config/styles.json
    Returns: dict matching Bundle Structure above.
    """
    bundle = {
        "bundle_version": "1.0",
        "generated_at": datetime.utcnow().isoformat(),
        "generated_by": agent_name,
        "portfolio_state": _read_portfolio_state(),
        "styles": _read_styles_json(),
    }

    if agent_name == "rebuy_analyst":
        bundle["recent_rotations"] = _read_recent_rotations(days=90, type="dry_powder")
        bundle["thesis_files"] = _read_thesis_files(
            tickers=_extract_sold_tickers(bundle["recent_rotations"])
        )
        bundle["holdings"] = _read_holdings_minimal()  # Just the ticker list

    elif agent_name == "add_candidate_analyst":
        bundle["holdings"] = _read_holdings_full()
        bundle["thesis_files"] = _read_thesis_files(
            tickers=[h["ticker"] for h in bundle["holdings"]]
        )
        bundle["recent_rotations"] = _read_recent_rotations(days=30)  # Just for context

    elif agent_name == "new_idea_screener":
        bundle["holdings"] = _read_holdings_minimal()
        bundle["agent_specific_context"] = {
            "candidate_names": config.get("screener_candidates", [])
        }

    elif agent_name == "list_coherence_checker":
        bundle["holdings"] = _read_holdings_minimal()
        bundle["agent_specific_context"] = {
            "draft_buy_list": _read_buy_list_draft()
        }

    return bundle
```

---

## Safety Preamble Integration

Every agent receives the SAFETY_PREAMBLE from the existing gemini_client
(auto-prepended — do not duplicate in agent prompts). The preamble already
establishes:
- No auto-trading
- Output is JSON-parseable suggestions, not executable decisions
- All suggestions are candidates for Bill's review, not recommendations
- Dry run is the default

The agent-specific system prompts below layer on top of that preamble.
