from tasks.export_package import create_package_dir, write_manifest, write_prompt_markdown, write_readme, write_context_json, copy_thesis_files
from pathlib import Path
import json

def test_primitives():
    print("Testing export package primitives...")
    pkg_dir = create_package_dir("test-scenario")
    print(f"Created package dir: {pkg_dir}")
    
    write_manifest(pkg_dir, "test-scenario", "test_hash_123", "v1.0.0", {"test": True})
    write_prompt_markdown(pkg_dir, "# Test Prompt\nThis is a test prompt content.")
    write_readme(pkg_dir, "test-scenario", "Test summary", "Test paste instructions")
    write_context_json(pkg_dir, {"positions": [{"ticker": "AAPL", "weight": 0.05}]})
    
    # Test thesis copy (assuming AAPL doesn't exist, should create MISSING file)
    copy_thesis_files(pkg_dir, ["AAPL", "UNH"])
    
    print(f"Package {pkg_dir.name} populated.")
    return pkg_dir

if __name__ == "__main__":
    pkg_dir = test_primitives()
    print(f"\nNow run: python manager.py export inspect {pkg_dir}")
