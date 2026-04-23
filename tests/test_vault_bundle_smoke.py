"""Smoke test for core/vault_bundle.py triggers extraction."""
import json
from pathlib import Path
import pytest
import yaml

from core.vault_bundle import (
    build_vault_bundle, write_vault_bundle, load_vault_bundle,
    VaultDocument, _parse_thesis_fields
)

@pytest.fixture
def temp_vault(tmp_path, monkeypatch):
    """Setup a temporary vault directory structure."""
    vault = tmp_path / "vault"
    theses = vault / "theses"
    transcripts = vault / "transcripts"
    research = vault / "research"
    
    theses.mkdir(parents=True)
    transcripts.mkdir()
    research.mkdir()
    
    monkeypatch.setattr("core.vault_bundle.VAULT_DIR", vault)
    monkeypatch.setattr("core.vault_bundle.THESES_DIR", theses)
    monkeypatch.setattr("core.vault_bundle.TRANSCRIPTS_DIR", transcripts)
    monkeypatch.setattr("core.vault_bundle.RESEARCH_DIR", research)
    monkeypatch.setattr("core.vault_bundle.VAULT_BUNDLE_DIR", tmp_path / "bundles")
    
    return {
        "vault": vault,
        "theses": theses,
        "bundles": tmp_path / "bundles"
    }

def test_parse_triggers_populated():
    content = """# UNH
## Quantitative Triggers
```yaml
triggers:
  price_add_below: 480.0
  price_trim_above: 640.5
```
"""
    parsed = _parse_thesis_fields(content)
    assert parsed["triggers"]["price_add_below"] == 480.0
    assert parsed["triggers"]["price_trim_above"] == 640.5

def test_parse_triggers_null():
    content = """# UNH
## Quantitative Triggers
```yaml
triggers:
  price_add_below: null
  price_trim_above: null
```
"""
    parsed = _parse_thesis_fields(content)
    assert parsed["triggers"]["price_add_below"] is None
    assert parsed["triggers"]["price_trim_above"] is None

def test_parse_triggers_missing_block():
    content = """# UNH
No triggers here.
"""
    parsed = _parse_thesis_fields(content)
    assert parsed["triggers"] == {"price_add_below": None, "price_trim_above": None}

def test_parse_triggers_malformed_yaml():
    content = """# UNH
## Quantitative Triggers
```yaml
triggers:
  price_add_below: [unclosed bracket
```
"""
    parsed = _parse_thesis_fields(content)
    # Should have a __parse_error__ sentinel
    assert "__parse_error__" in parsed["triggers"]
    assert parsed["triggers"]["price_add_below"] is None

def test_vault_bundle_with_triggers(temp_vault):
    # 1. Populated
    (temp_vault["theses"] / "AAPL_thesis.md").write_text("""# AAPL
## Quantitative Triggers
```yaml
triggers:
  price_add_below: 150.0
  price_trim_above: 200.0
```
""")
    # 2. Nulls
    (temp_vault["theses"] / "MSFT_thesis.md").write_text("""# MSFT
## Quantitative Triggers
```yaml
triggers:
  price_add_below: null
  price_trim_above: null
```
""")
    # 3. Missing block
    (temp_vault["theses"] / "GOOG_thesis.md").write_text("""# GOOG
No block.
""")
    # 4. Malformed
    (temp_vault["theses"] / "TSLA_thesis.md").write_text("""# TSLA
## Quantitative Triggers
```yaml
triggers:
  : malformed
```
""")

    bundle = build_vault_bundle()
    
    # AAPL should have triggers
    aapl = next(d for d in bundle.documents if d["ticker"] == "AAPL")
    assert aapl["triggers"] == {"price_add_below": 150.0, "price_trim_above": 200.0}
    
    # MSFT should have nulls
    msft = next(d for d in bundle.documents if d["ticker"] == "MSFT")
    assert msft["triggers"] == {"price_add_below": None, "price_trim_above": None}
    
    # GOOG should have nulls
    goog = next(d for d in bundle.documents if d["ticker"] == "GOOG")
    assert goog["triggers"] == {"price_add_below": None, "price_trim_above": None}
    
    # TSLA should have nulls + entry in skip log
    tsla = next(d for d in bundle.documents if d["ticker"] == "TSLA")
    assert tsla["triggers"] == {"price_add_below": None, "price_trim_above": None}
    assert any("Trigger parse error in TSLA_thesis.md" in log for log in bundle.vault_skip_log)

def test_vault_hash_stability(temp_vault):
    (temp_vault["theses"] / "AAPL_thesis.md").write_text("# AAPL")
    
    bundle1 = build_vault_bundle()
    bundle2 = build_vault_bundle()
    
    assert bundle1.vault_hash == bundle2.vault_hash
    
    # Change content
    (temp_vault["theses"] / "AAPL_thesis.md").write_text("# AAPL v2")
    bundle3 = build_vault_bundle()
    assert bundle3.vault_hash != bundle1.vault_hash
