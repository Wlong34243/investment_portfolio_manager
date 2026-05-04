# Weekly Workflow — Tying It All Together

## Monday morning (5 minutes): Health & Sync
```bash
python manager.py health
python manager.py snapshot --live
python manager.py sync transactions --live
python manager.py dashboard refresh --live
```

## Monday morning (3 minutes): Rapid Scan
Open the Google Sheet. Review:
- **Decision_View**: Check for high-severity action signals.
- **Valuation_Card**: Identify positions in colored Trim/Add zones.
- **Tax_Control**: Review Est Tax liability and available Offset Capacity.

## Midweek: Deep Reasoning (if triggered)
If a position hits an action zone or a rotation is needed:
```bash
python manager.py export deep-dive <TICKER> --question "..."
# OR
python manager.py export rotation --sell <X> --buy <Y> --size partial
```
1. Paste the generated `prompt.md` to Claude, Gemini, or Perplexity.
2. Attach `context.json` and relevant files from `theses/`.
3. Review the LLM's structured reasoning.
4. If action is taken, record it manually in your Decision Journal.

## Saturday morning (20 minutes): Thesis Maintenance
```bash
python manager.py export thesis-health
```
1. Review stale or violated theses identified by the LLM.
2. Backfill missing thesis files or update stale trim/add targets.
3. Refresh the vault and composite bundle:
```bash
python manager.py vault snapshot --live
python manager.py bundle composite --live
```

## First Saturday of Month: Monthly Retrospective (30 minutes)
```bash
python manager.py trade review --live
python manager.py export rotation-retrospective --last-n 20
```
1. Package recent trade history and post-hoc attribution.
2. Paste to Claude or Gemini 2.0.
3. Identify timing biases or style drift in recent rotations.
4. Record key "lessons learned" in your Decision Journal.
