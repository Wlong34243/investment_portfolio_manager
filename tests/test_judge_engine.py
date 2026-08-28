"""Judgment Engine tests — prompt 10."""

from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from core.judgment.calibration import build_calibration, format_calibration_markdown
from core.judgment.lifecycle import Campaign, Leg, build_campaign_from_transactions, format_campaign_markdown
from core.judgment.rotations import aggregate_rotations, format_rotations_markdown
from core.judgment.run import run_calibration, run_rotations
from tasks.compute_rotation_attribution import PRICE_SOURCE_FROZEN_BOUNDARY


def _sample_rows():
  return [
      {
          "Trade_Log_ID": "1",
          "Date": "2026-08-03",
          "Status": "OK",
          "Coverage_Pct": 0.95,
          "Rotation_Type": "rebalance",
          "Implicit_Bet": "test",
          "Rationale_Provenance": "",
          "Residual_Pair_30d": 0.02,
          "Residual_Pair_90d": 0.03,
          "Residual_Pair_180d": 0.04,
      },
      {
          "Trade_Log_ID": "2",
          "Date": "2026-08-03",
          "Status": "SUPERSEDED_BY: 1",
          "Coverage_Pct": 0.95,
          "Residual_Pair_30d": 0.01,
      },
      {
          "Trade_Log_ID": "3",
          "Date": "2025-01-01",
          "Status": "WEIGHTS_UNRECONCILED",
          "Coverage_Pct": 0.5,
          "Residual_Pair_30d": -0.5,
      },
  ]


def test_judge_n_disclosure():
    agg = aggregate_rotations(_sample_rows())
    text = format_rotations_markdown(agg)
    assert f"included={agg.included_n}" in text
    assert f"excluded={agg.excluded_n}" in text
    assert "N=" in text or "N too small" in text


def test_judge_small_n_suppressed():
    rows = [
        {
            "Trade_Log_ID": "x",
            "Date": "2026-01-01",
            "Status": "OK",
            "Coverage_Pct": 1.0,
            "Residual_Pair_30d": 0.01,
        }
    ]
    agg = aggregate_rotations(rows)
    assert "N too small" in format_rotations_markdown(agg)


def test_judge_superseded_excluded():
    agg = aggregate_rotations(_sample_rows())
    text = format_rotations_markdown(agg)
    assert agg.excluded_n >= 2
    assert "excluded=" in text
    assert agg.exclusion_breakdown.get("superseded", 0) >= 1


def test_judge_rotations_date_spans_in_header():
    rows = [
        {
            "Trade_Log_ID": "a",
            "Date": "2026-01-26",
            "Status": "OK",
            "Coverage_Pct": 1.0,
            "Residual_Pair_30d": 0.01,
        },
        {
            "Trade_Log_ID": "b",
            "Date": "2025-04-14",
            "Status": "WEIGHTS_UNRECONCILED",
            "Coverage_Pct": 0.5,
            "Residual_Pair_30d": -0.1,
        },
    ]
    agg = aggregate_rotations(rows)
    text = format_rotations_markdown(agg)
    assert "Included spans:" in text
    assert "2026-01-26" in text
    assert "Excluded spans:" in text
    assert "2025-04-14" in text


def test_judge_lifecycle_counterfactual():
    txns = [
        {"trade_date": "2026-08-07", "action": "Buy", "shares": 5, "price": 100.0, "net_amount": -500},
        {"trade_date": "2026-08-14", "action": "Buy", "shares": 5, "price": 110.0, "net_amount": -550},
    ]
    with patch("core.judgment.lifecycle._price_on", return_value=120.0):
        camp = build_campaign_from_transactions("TEST", txns)
    assert camp is not None
    assert camp.first_buy_price == 100.0
    # DWR: cost 1050, value 10*120=1200 => ~14.3%
    assert camp.dollar_weighted_return_pct is not None
    assert camp.dollar_weighted_return_pct > 0.1
    # Single entry: 120/100 - 1 = 20%
    assert camp.single_entry_return_pct == pytest.approx(0.2)


def test_judge_lifecycle_open_campaign():
    txns = [
        {"trade_date": "2026-08-07", "action": "Buy", "shares": 5, "price": 100.0, "net_amount": -500},
    ]
    with patch("core.judgment.lifecycle._price_on", return_value=105.0):
        camp = build_campaign_from_transactions("OPEN", txns)
    text = format_campaign_markdown(camp)
    assert camp.is_open
    assert "OPEN" in text
    assert "Scaling — legs vs buy-once" in text
    assert "Single-entry counterfactual" in text


def test_judge_lifecycle_degenerate_dwr_suppressed():
    """Heavy trims can collapse the net invested base — DWR must not print a ratio."""
    txns = [
        {"trade_date": "2025-01-01", "action": "Buy", "shares": 100, "price": 100.0, "net_amount": -10000},
        {"trade_date": "2025-06-01", "action": "Sell", "shares": 95, "price": 150.0, "net_amount": 14250},
        {"trade_date": "2025-07-01", "action": "Buy", "shares": 10, "price": 110.0, "net_amount": -1100},
    ]
    with patch("core.judgment.lifecycle._price_on", return_value=120.0):
        camp = build_campaign_from_transactions("DEGEN", txns)
    assert camp is not None
    assert camp.dwr_degenerate
    assert camp.dollar_weighted_return_pct is None
    text = format_campaign_markdown(camp)
    assert "n/a — invested base degenerate" in text
    assert "11,988" not in text
    assert "Scaling — legs vs buy-once" in text
    assert camp.scaling_delta_pct is not None


def test_judge_lifecycle_scaling_headline_order():
    txns = [
        {"trade_date": "2026-08-07", "action": "Buy", "shares": 5, "price": 100.0, "net_amount": -500},
        {"trade_date": "2026-08-14", "action": "Buy", "shares": 5, "price": 110.0, "net_amount": -550},
    ]
    with patch("core.judgment.lifecycle._price_on", return_value=120.0):
        camp = build_campaign_from_transactions("TEST", txns)
    text = format_campaign_markdown(camp)
    assert text.index("Single-entry counterfactual") < text.index("Time-weighted return")
    assert "Delta (legs minus buy-once)" in text
    assert "Denominator note" in text


def test_judge_calibration_blank():
    body, _ = run_calibration()
    assert "PENDING" in body
    assert "reconstructed_after" in body
    assert "GATE NOT MET" in body or "Hygiene gate" in body
    assert "partial calibration table" in body.lower() or "does not populate" in body.lower()


def test_judge_provenance_banner():
    result = build_calibration()
    text = format_calibration_markdown(result)
    assert "reconstructed_after" in text


def test_judge_no_recommendation():
    body, _, _ = run_rotations()
    lowered = body.lower()
    for word in ("you should", "consider trimming", "tighten", "retire this trigger"):
        assert word not in lowered


def test_judge_no_llm():
    root = Path("core/judgment")
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "gemini" not in alias.name.lower()
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "gemini" not in node.module.lower()


def test_judge_does_not_write_rotation_review():
    root = Path("core/judgment")
    text = "\n".join(p.read_text(encoding="utf-8") for p in root.glob("*.py"))
    forbidden = ("attribute_row", "safe_execute", "batch_update", "ws.update", "replace_decision_view")
    for token in forbidden:
        assert token not in text
