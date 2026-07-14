"""
utils/agent_signals.py — Shared Agent_Outputs reader.

Extracted from tasks/build_decision_view.py so both build_decision_view.py and
tasks/build_command_center.py can depend on it without importing each other.
"""

import pandas as pd

ACTION_SEVERITIES = {"action", "alert", "data_quality"}


def get_latest_agent_outputs(ws_agent) -> pd.DataFrame:
    """
    Reads Agent_Outputs and returns signals from the LATEST run only.

    Handles both legacy 11-col format (run_id, run_ts, ...) and
    compact 10-col format (run_date, run_id_short, ...) written by analyze-all.
    """
    all_values = ws_agent.get_all_values()
    if len(all_values) < 2:
        return pd.DataFrame()

    # Detect header row
    header_row_idx = -1
    for i, row in enumerate(all_values[:5]):
        if 'agent' in [str(h).strip().lower() for h in row]:
            header_row_idx = i
            break

    if header_row_idx == -1:
        return pd.DataFrame()

    headers = [str(h).strip().lower() for h in all_values[header_row_idx]]
    data = all_values[header_row_idx + 1:]

    df = pd.DataFrame(data, columns=headers)
    if df.empty:
        return pd.DataFrame()

    # Normalize column aliases
    rename_map = {
        "run_date":      "run_ts",
        "run_id_short":  "run_id",
        "signal":        "signal_type",
        "narrative":     "rationale",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Filter to LATEST run only
    df["run_ts_dt"] = pd.to_datetime(df["run_ts"], errors="coerce")
    if not df["run_ts_dt"].dropna().empty:
        latest_ts = df["run_ts_dt"].max()
        # Get one of the run_ids from the latest timestamp
        latest_run_id = df[df["run_ts_dt"] == latest_ts]["run_id"].iloc[0]
        df = df[df["run_id"] == latest_run_id]
        print(f"  [OK] Filtering to latest agent run: {latest_run_id} ({latest_ts})")

    return df
