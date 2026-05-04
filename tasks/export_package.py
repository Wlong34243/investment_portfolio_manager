"""
tasks/export_package.py — Primitives for generating context packages for external LLMs.
"""

import json
import shutil
import hashlib
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import config

def create_package_dir(scenario: str) -> Path:
    """
    Creates a new package directory under exports/ with a timestamp and short hash.
    Format: {scenario}_{YYYYMMDD_HHMMSS}_{short_hash}/
    """
    if not config.EXPORTS_DIR.exists():
        config.EXPORTS_DIR.mkdir(parents=True)
        
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Short hash based on timestamp to ensure uniqueness and identifiable path
    short_hash = hashlib.md5(f"{scenario}_{ts}".encode()).hexdigest()[:8]
    pkg_name = f"{scenario}_{ts}_{short_hash}"
    pkg_dir = config.EXPORTS_DIR / pkg_name
    pkg_dir.mkdir()
    return pkg_dir

def write_manifest(
    pkg_dir: Path, 
    scenario: str, 
    composite_hash: str, 
    prompt_template_version: str, 
    extra_metadata: Dict[str, Any] = None
):
    """Writes manifest.json to the package directory."""
    manifest = {
        "scenario": scenario,
        "timestamp": datetime.now().isoformat(),
        "composite_hash": composite_hash,
        "prompt_template_version": prompt_template_version,
        "metadata": extra_metadata or {}
    }
    with open(pkg_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)

def write_readme(pkg_dir: Path, scenario: str, summary_text: str, paste_instructions: str):
    """Writes README.md to the package directory."""
    content = f"""# Export Package: {scenario}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Summary
{summary_text}

## How to use this package

1. **Open Claude.ai, Gemini, or Perplexity.**
2. **Copy the contents of `prompt.md`** and paste as your first message.
3. **Attach (or paste) the context.json** and relevant files in `theses/`.
4. **Ask the LLM for its structured response** per the prompt.
5. **Save your conversation** — nothing about this package is tracked anywhere 
   else unless you choose to update `Decision_Journal` manually afterward.

## Metadata
{paste_instructions}
"""
    with open(pkg_dir / "README.md", "w", encoding="utf-8") as f:
        f.write(content)

def copy_thesis_files(pkg_dir: Path, tickers: List[str]):
    """Copies relevant thesis markdown files from vault/theses/ to pkg_dir/theses/."""
    theses_src = Path("vault/theses")
    theses_dest = pkg_dir / "theses"
    
    if not theses_dest.exists():
        theses_dest.mkdir()
        
    for ticker in tickers:
        src_file = theses_src / f"{ticker}_thesis.md"
        if src_file.exists():
            shutil.copy(src_file, theses_dest / f"{ticker}_thesis.md")
        else:
            # Create a placeholder or note that thesis is missing
            with open(theses_dest / f"{ticker}_thesis_MISSING.txt", "w") as f:
                f.write(f"No thesis file found for {ticker} in vault/theses/")

def write_context_json(pkg_dir: Path, context_dict: Dict[str, Any], filename: str = "context.json"):
    """Writes context.json to the package directory."""
    with open(pkg_dir / filename, "w", encoding="utf-8") as f:
        json.dump(context_dict, f, indent=4)

def write_prompt_markdown(pkg_dir: Path, content: str, filename: str = "prompt.md"):
    """Writes prompt.md to the package directory."""
    with open(pkg_dir / filename, "w", encoding="utf-8") as f:
        f.write(content)
