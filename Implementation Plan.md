 Implementation Plan — Simplifying CLI Administration & Documentation for a Single Periodic User

We want to simplify the administration of this program and verify that the documentation is optimized for a single periodic user (Bill). 

Bill is a CPA who operates this system locally on Windows, periodically running syncs, checking metrics, and invoking the AI Idea Generator. The current setup requires multiple CLI commands, virtual environment activation, and navigating to Python scripts in subdirectories, which introduces friction for a periodic user.

To address this, we propose:
1. **Adding first-class commands to `manager.py`**:
   - `pm login`: Wire the emergency Schwab OAuth reauthentication flow.
   - `pm backup`: Wire the Google Drive backup functionality.
2. **Enhancing `pm morning`**:
   - Automatically run `vault sync` (to update local theses), `vault snapshot`, and `bundle composite` as the final steps when `--live` is used, ensuring a single command achieves a 100% synchronized state.
3. **Providing Windows automation scripts (`.bat` files)**:
   - `run_morning_sync.bat`: Runs the daily/weekly routine, handles virtual environment activation, runs `pm morning --live`, and pauses to display the summary.
   - `run_idea_generator.bat`: Runs `pm agent ideas` and automatically opens the generated markdown report in the default system editor/browser.
   - `schwab_emergency_reauth.bat`: Directly runs `pm login` to re-auth Schwab credentials.
4. **Simplifying and verifying documentation**:
   - Update `README.md`, `CLI_CHEATSHEET.md`, `CLI_MANUAL.md`, and `portfolio_manager_user_docs.html` to prioritize the simplified batch script double-click workflow.

---

## User Review Required

> [!IMPORTANT]
> **Automatic Local Updates during Morning Sync**
> By default, `pm morning --live` will now also run `pm vault sync --live`, `pm vault snapshot`, and `pm bundle composite` at the end. This keeps your local thesis files and composite bundles updated automatically. We will provide flags (e.g. `--skip-vault-sync` and `--skip-composite`) to disable this behavior if needed.

> [!NOTE]
> **Windows Batch Files**
> The three `.bat` files will be placed in the project root. They will automatically locate Python in the `.venv` directory (or use the active `python` in the shell) and run the commands, pausing at the end so you can view the results.

---

## Proposed Changes

### CLI Core

#### [MODIFY] [manager.py](file:///C:/Users/WLong/Investment_Portfolio/manager.py)
- Import `run_reauth` from `scripts/schwab_manual_reauth.py` and expose it as a top-level command `pm login` (or `pm login` under an `auth` sub-app if preferred, but a direct top-level `pm login` is simplest).
- Import `backup` from `scripts/backup_to_drive.py` and expose it as `pm backup`.
- Modify the `morning` command:
  - Add parameters `skip_vault_sync: bool = False` and `skip_composite: bool = False`.
  - At the end of the `morning` command (Step 6), if not skipped, run:
    - Step 7: Vault Sync (runs the same logic as `pm vault sync` with the same `live` status).
    - Step 8: Vault Snapshot (runs the same logic as `pm vault snapshot`).
    - Step 9: Composite Bundle (runs the same logic as `pm bundle composite`).
  - Update `_morning_summary` to include these steps in the final summary panel.

### Automation Scripts

#### [NEW] [run_morning_sync.bat](file:///C:/Users/WLong/Investment_Portfolio/run_morning_sync.bat)
Create a batch script in the root directory that:
1. Navigates to the project directory.
2. Locates and activates the virtual environment (`.venv\Scripts\activate.bat` or fallback).
3. Executes `pm morning --live`.
4. Pauses the terminal.

#### [NEW] [run_idea_generator.bat](file:///C:/Users/WLong/Investment_Portfolio/run_idea_generator.bat)
Create a batch script in the root directory that:
1. Navigates to the project directory.
2. Locates and activates the virtual environment.
3. Executes `pm agent ideas`.
4. Dynamically finds the latest markdown file in `agent_outputs/ideas/` and opens it in the default system editor/browser (using `start` command).
5. Pauses the terminal.

#### [NEW] [schwab_emergency_reauth.bat](file:///C:/Users/WLong/Investment_Portfolio/schwab_emergency_reauth.bat)
Create a batch script in the root directory that:
1. Navigates to the project directory.
2. Locates and activates the virtual environment.
3. Executes `pm login`.
4. Pauses the terminal.

### Documentation Updates

#### [MODIFY] [README.md](file:///C:/Users/WLong/Investment_Portfolio/README.md)
- Update the Quick Start section to highlight the new double-clickable `.bat` files for Windows users, simplifying the setup to a single step.

#### [MODIFY] [CLI_CHEATSHEET.md](file:///C:/Users/WLong/Investment_Portfolio/CLI_CHEATSHEET.md)
- Add the new `pm login` and `pm backup` commands.
- Highlight the `.bat` files as the recommended way to execute daily/weekly workflows.

#### [MODIFY] [CLI_MANUAL.md](file:///C:/Users/WLong/Investment_Portfolio/CLI_MANUAL.md)
- Document the new commands (`pm login`, `pm backup`).
- Update the `pm morning` section to explain the newly integrated Vault Sync and Composite Bundle building steps.

#### [MODIFY] [portfolio_manager_user_docs.html](file:///C:/Users/WLong/Investment_Portfolio/portfolio_manager_user_docs.html)
- Update the user manuals to reflect the simplified workflow:
  1. Update data: Double-click `run_morning_sync.bat`.
  2. Research and ideas: Double-click `run_idea_generator.bat`.
  3. Re-auth: Double-click `schwab_emergency_reauth.bat` or run `pm login`.

---

## Verification Plan

### Automated Tests
- Test that syntax is correct and CLI commands compile:
  ```bash
  python -m py_compile manager.py
  ```
- Run a dry-run morning sequence to ensure no crashes:
  ```bash
  pm morning
  ```
- Run the new commands in dry-run to ensure they load:
  ```bash
  pm login --help
  pm backup --help
  ```

### Manual Verification
- Execute `run_morning_sync.bat` (dry-run mode first, then live if needed).
- Execute `run_idea_generator.bat` to verify that the Idea Generator runs and the markdown report is opened automatically.
- Check that the local HTML docs load correctly and reflect the simplified instructions.