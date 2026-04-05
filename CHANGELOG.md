# Changelog

Every entry must include a **Status** line describing what is currently safe to run.

## [2026-04-05] — Performance Accuracy & Data Recovery

### fix: Performance Graphs & Snapshot Recovery
**What changed:**
- **Resolved "0.0" Date Bug:** Fixed a case-sensitivity issue in `utils/sheet_readers.py` that was causing the `Date` column in snapshots to be incorrectly converted to a float (0.0), which broke all performance graphs.
- **Snapshot Hardening:** Updated `pipeline.py` to ensure dates and fingerprints are strictly cast to strings before writing to Google Sheets, preventing data corruption.
- **Data Recovery:** Surgically cleaned the corrupted `Daily_Snapshots` sheet and successfully backfilled historical data points from the `Holdings_History` tab.

**Status: Production ready. Performance graphs (Portfolio vs Benchmark and Value History) are now fully operational. Data integrity hardened.**

## [2026-04-05] — Stabilization & Performance
...
