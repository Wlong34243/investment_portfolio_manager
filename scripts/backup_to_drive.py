"""
scripts/backup_to_drive.py — Archives the project and uploads it to Google Drive.

Usage:
    python scripts/backup_to_drive.py [--name "my_backup.zip"] [--folder_id "ID"]
"""

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

if __name__ == "__main__":
    app()
