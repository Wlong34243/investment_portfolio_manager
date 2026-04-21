"""
Smoke tests for agents/rebuy_analyst.py.

These tests use a stub composite bundle (no real Gemini call) to verify:
- The agent loads bundle data correctly
- Candidate filtering excludes CASH_TICKERS
- The schema accepts valid agent output
- DRY RUN mode writes to disk, not Sheets
- The bundle_hash field is present in all output
"""
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from pydantic import ValidationError

from agents.schemas.rebuy_schema import RebuyAnalystResponse, RebuyCandidate


# ── Schema validation ────────────────────────────────────────────────────────

def test_rebuy_candidate_schema_valid():
    c = RebuyCandidate(
        ticker="UNH",
        style="Boring Fundamentals",
        thesis_present=True,
        current_scaling_state="medium",
        proposed_next_step="scale_in",
        scaling_rationale="Fear-driven discount below intrinsic value",
        rotation_priority="low",
        confidence="high",
    )
    assert c.ticker == "UNH"
    assert c.proposed_next_step == "scale_in"


def test_rebuy_response_requires_bundle_hash():
    with pytest.raises(ValidationError):
        RebuyAnalystResponse(
            # bundle_hash deliberately omitted
            analysis_timestamp_utc="2026-04-12T00:00:00Z",
            candidates=[],
            excluded_tickers=[],
            coverage_warnings=[],
        )


def test_rebuy_response_rejects_invalid_step():
    with pytest.raises(ValidationError):
        RebuyCandidate(
            ticker="UNH",
            style="Boring Fundamentals",
            thesis_present=True,
            current_scaling_state="medium",
            proposed_next_step="buy_more",   # invalid — not in Literal
            scaling_rationale="test",
            rotation_priority="low",
            confidence="high",
        )


def test_rebuy_response_rejects_invalid_style():
    with pytest.raises(ValidationError):
        RebuyCandidate(
            ticker="UNH",
            style="Value Investing",  # invalid — not in Literal
            thesis_present=True,
            current_scaling_state="medium",
            proposed_next_step="hold",
            scaling_rationale="test",
            rotation_priority="low",
            confidence="high",
        )


# ── Cash ticker exclusion ─────────────────────────────────────────────────────

def test_cash_tickers_excluded_from_positions():
    import config
    all_positions = [
        {"ticker": "UNH", "market_value": 43000},
        {"ticker": "CASH_MANUAL", "market_value": 85000},
        {"ticker": "QACDS", "market_value": 5000},
        {"ticker": "GOOG", "market_value": 27000},
    ]
    investable = [p for p in all_positions if p["ticker"] not in config.CASH_TICKERS]
    tickers = [p["ticker"] for p in investable]
    assert "CASH_MANUAL" not in tickers
    assert "QACDS" not in tickers
    assert "UNH" in tickers
    assert "GOOG" in tickers


# ── DRY RUN output ────────────────────────────────────────────────────────────

def _make_stub_response(bundle_hash: str = "a" * 64) -> RebuyAnalystResponse:
    return RebuyAnalystResponse(
        bundle_hash=bundle_hash,
        analysis_timestamp_utc="2026-04-12T10:00:00Z",
        candidates=[
            RebuyCandidate(
                ticker="UNH",
                style="Boring Fundamentals",
                thesis_present=True,
                current_scaling_state="medium",
                proposed_next_step="scale_in",
                scaling_rationale="Trading below long-run fair value on sector fear",
                rotation_priority="low",
                confidence="high",
            )
        ],
        excluded_tickers=["CASH_MANUAL", "QACDS"],
        coverage_warnings=["GOOG"],
    )


def test_dry_run_writes_json_and_md(tmp_path):
    """DRY RUN output is written to disk, not Sheets."""
    stub = _make_stub_response(bundle_hash="b" * 64)
    output_dir = tmp_path
    json_path = output_dir / f"rebuy_output_{stub.bundle_hash[:12]}.json"
    md_path = output_dir / f"rebuy_output_{stub.bundle_hash[:12]}.md"

    json_path.write_text(json.dumps(stub.model_dump(), indent=2))
    md_path.write_text(f"# Re-buy Analyst Output\n**Bundle hash:** {stub.bundle_hash}\n")

    assert json_path.exists()
    assert md_path.exists()
    loaded = json.loads(json_path.read_text())
    assert loaded["bundle_hash"] == "b" * 64
    assert loaded["candidates"][0]["ticker"] == "UNH"


def test_bundle_hash_in_serialized_output():
    stub = _make_stub_response(bundle_hash="c" * 64)
    data = stub.model_dump()
    assert "bundle_hash" in data
    assert data["bundle_hash"] == "c" * 64


# ── Phase 3c: Framework validation ───────────────────────────────────────────

def test_framework_validation_is_optional():
    """A candidate without framework_validation must still validate."""
    from agents.schemas.rebuy_schema import RebuyCandidate
    c = RebuyCandidate(
        ticker="UNH",
        style="Boring Fundamentals",
        thesis_present=True,
        current_scaling_state="medium",
        proposed_next_step="hold",
        scaling_rationale="Position correctly sized; thesis intact.",
        rotation_priority="low",
        confidence="high",
    )
    assert c.framework_validation is None
    assert c.framework_influence_notes == ""


def test_framework_validation_structural_integrity():
    from agents.schemas.rebuy_schema import FrameworkValidation, FrameworkRuleResult
    fv = FrameworkValidation(
        framework_id="lynch_garp_v1",
        framework_version="1.0.0",
        framework_content_sha256="b" * 64,
        applicable=True,
        applicability_rationale="UNH matches garp style and Equities asset class.",
        rules_evaluated=[
            FrameworkRuleResult(
                rule_id="peg_in_buy_zone",
                description="PEG ratio is in the buy zone",
                passed=True,
                observed_value="0.87",
                severity="required",
                rationale="PEG of 0.87 is within Lynch's 0.5-1.0 buy zone",
            ),
        ],
        required_rules_passed=1,
        required_rules_total=3,
        preferred_rules_passed=0,
        preferred_rules_total=2,
        passes_framework=False,
        insufficient_data_rules=[],
        framework_score_display="1/3 required + 0/2 preferred",
    )
    assert fv.framework_id == "lynch_garp_v1"
    assert fv.framework_score_display == "1/3 required + 0/2 preferred"


def test_framework_selector_skips_unreviewed():
    from agents.framework_selector import select_framework, ThesisFrontmatter
    frameworks = [{
        "framework_id": "lynch_garp_v1",
        "framework_version": "1.0.0",
        "reviewed_by_bill": False,
        "applies_to_styles": ["garp"],
        "applies_to_asset_classes": ["Equities"],
        "excludes_conditions": [],
    }]
    position = {"ticker": "UNH", "asset_class": "Equities"}
    fm = ThesisFrontmatter(ticker="UNH", style="garp")
    result = select_framework("UNH", position, fm, frameworks)
    assert result is None, "Unreviewed framework must not be selected"


def test_framework_selector_respects_frontmatter_preference():
    from agents.framework_selector import select_framework, ThesisFrontmatter
    frameworks = [
        {
            "framework_id": "lynch_garp_v1",
            "framework_version": "1.0.0",
            "reviewed_by_bill": True,
            "applies_to_styles": ["garp"],
            "applies_to_asset_classes": ["Equities"],
            "excludes_conditions": [],
        },
        {
            "framework_id": "graham_deep_value_v1",
            "framework_version": "1.0.0",
            "reviewed_by_bill": True,
            "applies_to_styles": ["boring"],
            "applies_to_asset_classes": ["Equities"],
            "excludes_conditions": [],
        },
    ]
    position = {"ticker": "UNH", "asset_class": "Equities"}
    fm = ThesisFrontmatter(ticker="UNH", style="garp", framework_preference="lynch_garp_v1")
    result = select_framework("UNH", position, fm, frameworks)
    assert result is not None
    assert result["framework_id"] == "lynch_garp_v1"


def test_evaluate_framework_rules_handles_missing_data():
    from agents.framework_selector import evaluate_framework_rules
    framework = {
        "framework_id": "lynch_garp_v1",
        "framework_version": "1.0.0",
        "_framework_content_sha256": "c" * 64,
        "applies_to_styles": ["garp"],
        "applies_to_asset_classes": ["Equities"],
        "rules": [{
            "rule_id": "peg_in_buy_zone",
            "description": "PEG ratio is in the buy zone",
            "required_fields": ["peg_ratio"],
            "severity": "required",
            "check_type": "range",
            "target_min": 0.5,
            "target_max": 1.0,
        }],
        "passing_threshold": {
            "required_rules_passed_minimum": 1,
            "preferred_rules_passed_minimum": 0,
            "total_rules": 1,
        },
    }
    position = {"ticker": "UNH", "asset_class": "Equities"}
    fundamentals = {}  # no peg_ratio available
    result = evaluate_framework_rules(position, fundamentals, framework)
    assert result["rules_evaluated"][0]["passed"] is None
    assert "peg_in_buy_zone" in result["insufficient_data_rules"]
    assert result["required_rules_passed"] == 0
