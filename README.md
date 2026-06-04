# Investment Portfolio Manager

Headless Python CLI for managing a ~$550K Schwab portfolio through Google Sheets. APIs compute locally; LLMs reason externally via exportable context packages.

## Windows Quick Start (Recommended)

For a single periodic user, you can manage the entire application using the double-clickable batch files in the root folder:
1. **`run_morning_sync.bat`**: Runs the entire morning routine (health checks, updates holdings, syncs transactions, pulls podcasts, syncs results to local theses, and builds the composite bundle).
2. **`run_idea_generator.bat`**: Runs the Idea Generator agent and opens the latest report automatically.
3. **`schwab_emergency_reauth.bat`**: Authenticates or re-authenticates Schwab tokens when they expire.

## CLI Quick Start (Alternative)

Install the `pm` shortcut once (requires the repo's virtualenv to be active):

    pip install -e .

Then run any command with `pm`:

    pm morning --live
    pm login
    pm backup
    pm agent ideas

Open the Google Sheet. Look at Decision_View, Valuation_Card, Tax_Control.

## Documentation

- [User manual](portfolio_manager_user_docs.html) — full workflow
- [Sheet schema](PORTFOLIO_SHEET_SCHEMA.md) — cell-level truth
- [Conventions](CLAUDE.md) — for future devs
- [Changelog](CHANGELOG.md) — phase-by-phase history
- [Architecture notes](docs/architecture/) — the "why" behind the "what"

## Non-goals

Not a robo-advisor. Not an auto-trader. Not a backtest. Not a web app.
