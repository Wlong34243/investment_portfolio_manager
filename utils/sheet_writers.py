"""
utils/sheet_writers.py — Shared Google Sheets writer functions.
"""

import time
import logging
from typing import List
import config

logger = logging.getLogger(__name__)

def safe_execute(func, *args, **kwargs):
    retries = 5
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if "429" in str(e) and i < retries - 1:
                wait = (i + 1) * 10
                logger.warning(f"Quota exceeded (429), waiting {wait}s before retry {i+1}/{retries}...")
                time.sleep(wait)
            else:
                raise e

def archive_and_overwrite_agent_outputs(
    ss, 
    new_rows: List[List], 
    run_ts: str, 
    headers: List[str]
) -> bool:
    """
    Shared logic with exponential backoff retries to handle API quota limits.
    1. Copy existing rows from Agent_Outputs to Agent_Outputs_Archive with archived_at.
    2. Overwrite Agent_Outputs with new_rows in a single batch call.
    """
    try:
        existing_tabs = {ws.title for ws in ss.worksheets()}

        # --- Get or create Agent_Outputs ---
        if config.TAB_AGENT_OUTPUTS not in existing_tabs:
            ws_out = safe_execute(ss.add_worksheet, title=config.TAB_AGENT_OUTPUTS, rows=2000, cols=len(headers) + 1)
            time.sleep(1.0)
            existing_rows = []
        else:
            ws_out = safe_execute(ss.worksheet, config.TAB_AGENT_OUTPUTS)
            existing_rows = safe_execute(ws_out.get_all_values)

        # --- Archive existing rows ---
        if len(existing_rows) > 1:  # more than just header
            if config.TAB_AGENT_OUTPUTS_ARCHIVE not in existing_tabs:
                ws_arc = safe_execute(ss.add_worksheet,
                    title=config.TAB_AGENT_OUTPUTS_ARCHIVE,
                    rows=10000,
                    cols=len(headers) + 2,
                )
                time.sleep(1.0)
                arc_headers = ["archived_at"] + existing_rows[0]
                safe_execute(ws_arc.update, range_name="A1", values=[arc_headers], value_input_option="USER_ENTERED")
                time.sleep(0.5)
            else:
                ws_arc = safe_execute(ss.worksheet, config.TAB_AGENT_OUTPUTS_ARCHIVE)

            archive_rows = [[run_ts] + row for row in existing_rows[1:]]
            if archive_rows:
                safe_execute(ws_arc.append_rows, archive_rows, value_input_option="USER_ENTERED")
                time.sleep(1.0)
            logger.info(f"Archived {len(archive_rows)} existing row(s) to {config.TAB_AGENT_OUTPUTS_ARCHIVE}.")

        # --- Overwrite Agent_Outputs with new data ---
        safe_execute(ws_out.clear)
        time.sleep(1.0)
        all_data = [headers] + new_rows
        safe_execute(ws_out.update, range_name="A1", values=all_data, value_input_option="USER_ENTERED")
        time.sleep(1.0)
        logger.info(f"LIVE — wrote {len(new_rows)} row(s) to {config.TAB_AGENT_OUTPUTS} (single batch).")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update Agent_Outputs: {e}")
        return False

def append_agent_outputs(
    ss, 
    new_rows: List[List], 
    headers: List[str]
) -> bool:
    """
    Appends new rows to Agent_Outputs without clearing existing data.
    Uses fingerprints to deduplicate if the last column is 'Fingerprint'.
    """
    try:
        existing_tabs = {ws.title for ws in ss.worksheets()}

        if config.TAB_AGENT_OUTPUTS not in existing_tabs:
            ws_out = safe_execute(ss.add_worksheet, title=config.TAB_AGENT_OUTPUTS, rows=2000, cols=len(headers) + 1)
            time.sleep(1.0)
            safe_execute(ws_out.update, range_name="A1", values=[headers], value_input_option="USER_ENTERED")
            existing_fps = set()
        else:
            ws_out = safe_execute(ss.worksheet, config.TAB_AGENT_OUTPUTS)
            all_vals = safe_execute(ws_out.get_all_values)
            if not all_vals:
                safe_execute(ws_out.update, range_name="A1", values=[headers], value_input_option="USER_ENTERED")
                existing_fps = set()
            else:
                # Assuming last column is Fingerprint
                fp_idx = -1 
                existing_fps = {row[fp_idx] for row in all_vals[1:] if len(row) > 0}

        to_append = [r for r in new_rows if r[-1] not in existing_fps]
        
        if to_append:
            safe_execute(ws_out.append_rows, to_append, value_input_option="USER_ENTERED")
            logger.info(f"Appended {len(to_append)} unique row(s) to {config.TAB_AGENT_OUTPUTS}.")
        else:
            logger.info("No new unique rows to append.")
            
        return True
    except Exception as e:
        logger.error(f"Failed to append Agent_Outputs: {e}")
        return False
