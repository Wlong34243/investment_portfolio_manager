"""
scripts/backup_to_drive.py — Archives the project and uploads it to Google Drive.

Usage:
    python scripts/backup_to_drive.py [--name "my_backup.zip"] [--folder_id "ID"]
"""

import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Optional

import typer
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Import local auth logic
import sys
_ROOT = Path(__file__).parent.parent
sys.path.append(str(_ROOT))

from utils.sheet_readers import get_gspread_client

app = typer.Typer()

# Directories to exclude from the zip
EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "ENV",
    "exports",
    "bundles",
    "data/fmp_cache",
    ".schwab",
    "Books",
}

# Files to exclude from the zip
EXCLUDE_FILES = {
    "service_account.json",
    ".env",
    "token_accounts.json",
    "token_market.json",
}

def get_drive_service():
    """Builds a Drive service using the existing auth logic."""
    # sheet_readers.get_gspread_client() already handles the resolution
    client = get_gspread_client()
    creds = client.auth
    return build('drive', 'v3', credentials=creds)

def zip_project(output_path: Path):
    """Zips the project directory, respecting exclusions."""
    project_root = _ROOT
    
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(project_root):
            rel_path = Path(root).relative_to(project_root)
            
            # Skip excluded directories
            if any(part in EXCLUDE_DIRS for part in rel_path.parts):
                continue
            
            # Check if current directory name is in EXCLUDE_DIRS
            if rel_path.name in EXCLUDE_DIRS:
                continue

            for file in files:
                if file in EXCLUDE_FILES or file.endswith(".log"):
                    continue
                
                # Also skip the output zip itself if it's in the project root
                file_path = Path(root) / file
                if file_path == output_path:
                    continue
                
                zipf.write(file_path, rel_path / file)

@app.command()
def backup(
    name: Optional[str] = typer.Option(None, help="Name of the zip file in Drive."),
    folder_id: Optional[str] = typer.Option(None, help="ID of the Drive folder to upload to.")
):
    """Archives the project and uploads it to Google Drive."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = name or f"Investment_Portfolio_Backup_{ts}.zip"
    
    typer.echo(f"🚀 Starting backup: {backup_name}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_local_path = Path(tmpdir) / backup_name
        
        typer.echo("📦 Archiving project (excluding secrets and temp files)...")
        zip_project(zip_local_path)
        
        typer.echo("☁️ Uploading to Google Drive...")
        service = get_drive_service()
        
        file_metadata = {'name': backup_name}
        if folder_id:
            file_metadata['parents'] = [folder_id]
            
        media = MediaFileUpload(
            str(zip_local_path),
            mimetype='application/zip',
            resumable=True
        )
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        typer.echo(f"✅ Backup successful!")
        typer.echo(f"📄 File ID: {file.get('id')}")
        typer.echo(f"🔗 Link: {file.get('webViewLink')}")

# --- Publish analysis outputs (small, stable, phone-readable) --------------
# Distinct from backup(): backup() zips and API-uploads the whole project as
# a dated snapshot. This is a live, one-way filesystem mirror of just the
# analysis markdown into a Drive File Stream-mounted folder (G:\My Drive\...
# on this machine, not a repo path), so Bill can read it on a phone without
# the repo itself living inside any sync client.
ANALYSIS_PUBLISH_GLOBS = [
    "agent_outputs/ai_briefing_analysis/*.md",
    "agent_outputs/ideas/*.md",
    "agent_outputs/dislocation_scan/*.md",
]
DEFAULT_ANALYSIS_DEST = r"G:\My Drive\Portfolio_Analysis"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def publish_analysis(dest_dir: Optional[str] = None, live: bool = False) -> dict:
    """
    One-way, newest-wins copy of agent_outputs/{ai_briefing_analysis,ideas,
    dislocation_scan}/*.md into a Drive-synced folder. Never deletes at the
    destination -- Bill may be reading a file on his phone when this runs.
    Skips a file whose destination copy already has an identical SHA-256.
    Dry-run by default; pass live=True to actually copy.

    Degrades to a warning (never raises) when the Drive destination isn't
    reachable -- e.g. Drive letter not mounted on some future machine --
    so this can be called from the morning pipeline as a non-fatal step.
    """
    dest_root = Path(dest_dir or os.getenv("PORTFOLIO_ANALYSIS_DRIVE_DIR", DEFAULT_ANALYSIS_DEST))
    result = {"considered": [], "copied": [], "skipped": [], "warn": None}

    if not dest_root.parent.exists():
        result["warn"] = f"Drive destination parent not found: {dest_root.parent}"
        return result

    if live:
        dest_root.mkdir(parents=True, exist_ok=True)

    for pattern in ANALYSIS_PUBLISH_GLOBS:
        for src_path in sorted(_ROOT.glob(pattern)):
            result["considered"].append(str(src_path.relative_to(_ROOT)))
            dest_path = dest_root / src_path.name
            if dest_path.exists() and _sha256(dest_path) == _sha256(src_path):
                result["skipped"].append(src_path.name)
                continue
            if live:
                shutil.copy2(src_path, dest_path)
            result["copied"].append(src_path.name)

    return result


@app.command("publish-analysis")
def publish_analysis_command(
    live: bool = typer.Option(False, "--live", help="Actually copy files. Default: DRY RUN."),
):
    """Publish agent_outputs analysis markdown to a Drive-synced folder for reading on other devices."""
    result = publish_analysis(live=live)
    if result["warn"]:
        typer.echo(f"WARN: {result['warn']}")
        raise typer.Exit(code=0)
    mode = "LIVE" if live else "DRY RUN"
    typer.echo(f"[{mode}] considered {len(result['considered'])}, "
               f"copied {len(result['copied'])}, skipped {len(result['skipped'])} (identical hash).")
    for name in result["copied"]:
        typer.echo(f"  copied: {name}")


if __name__ == "__main__":
    app()
