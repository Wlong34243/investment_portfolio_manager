# Changelog

Every entry must include a **Status** line describing what is currently safe to run.

## [2026-04-05] — Performance Accuracy & Behavioral Insights

### added
- **Wash Sale Impact:** New "Wash Sale Activity" section in Tax Hub surfacing disallowed losses by ticker.
- **Behavioral Analytics:** Added "Disposition Effect" detection to flag if winners are being sold faster than losers.
- **Import Reconciliation:** Auto-compare new CSV uploads against session state to show added/removed tickers immediately.
- **Import Audit Trail:** Sidebar history tracking for the last 5 ingestion events in the current session.

### fixed
- **Contribution Modeling:** Upgraded growth projections from annual lump-sum to monthly compounding for significantly better accuracy.
- **Return Disclaimer:** Added methodology clarification for simple price returns vs TWR to manage planning expectations.

**Status: Production ready. Projections and tax analytics are more precise. UI provides better feedback on data changes.**

## [2026-04-05] — Production Hardening & UI Refactor
...
