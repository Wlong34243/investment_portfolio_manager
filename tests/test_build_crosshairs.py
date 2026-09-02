"""Tests for tasks/build_crosshairs.py trim role + rank modifiers."""

from __future__ import annotations

import pytest

from tasks.build_crosshairs import (
    CrosshairItem,
    REASON_NEAR_TRIM,
    W_CEILING_HEADROOM,
    W_UNREALIZED_LOSS,
    _BUCKET_DOCTRINE_HOLD,
    _BUCKET_NEAR,
    _apply_doctrine_downgrades,
    _apply_trim_roles,
    _trim_rank_modifiers,
    _trim_trigger_role,
    holdings_unrealized_pct_fraction_to_pct_points,
    holdings_weight_fraction_to_pct_points,
)

# Real Holdings_Current row shape — Weight and Unrealized G/L % are fractions after sheet read.
GLD_HROW_SHEET = {"Weight": 0.011, "Unrealized G/L %": -0.017}


def test_holdings_weight_fixture_matches_sheet_contract():
    raw = GLD_HROW_SHEET["Weight"]
    assert raw < 1.0
    assert holdings_weight_fraction_to_pct_points(raw) == pytest.approx(1.1, abs=0.01)


def test_gld_headroom_pinned_after_normalization():
    penalty, suffix = _trim_rank_modifiers("GLD", GLD_HROW_SHEET)
    assert "headroom 0.14" in suffix
    assert penalty == pytest.approx(
        W_CEILING_HEADROOM * (1.0 - 1.1 / 8.0) + W_UNREALIZED_LOSS,
        abs=0.001,
    )


def test_unrealized_display_uses_pct_points_not_fraction():
    _, suffix = _trim_rank_modifiers("GLD", GLD_HROW_SHEET)
    assert "unrealized -1.7%" in suffix
    assert "-0.0%" not in suffix


def test_holdings_unrealized_pct_normalization():
    assert holdings_unrealized_pct_fraction_to_pct_points(-0.017) == pytest.approx(-1.7, abs=0.01)


def test_trim_rank_modifiers_headroom_ordering_differs_by_weight(monkeypatch):
    """After D1, lower headroom must increase penalty vs a fuller position."""
    monkeypatch.setattr("tasks.build_crosshairs._style_size_ceiling_pct", lambda _t: 8.0)
    _, suffix_low = _trim_rank_modifiers("A", {"Weight": 0.011, "Unrealized G/L %": 0.05})
    _, suffix_high = _trim_rank_modifiers("B", {"Weight": 0.056, "Unrealized G/L %": 0.05})
    p_low, _ = _trim_rank_modifiers("A", {"Weight": 0.011, "Unrealized G/L %": 0.05})
    p_high, _ = _trim_rank_modifiers("B", {"Weight": 0.056, "Unrealized G/L %": 0.05})
    assert p_low > p_high
    assert "headroom 0.14" in suffix_low
    assert "headroom 0.70" in suffix_high


def test_trim_rank_modifiers_missing_ceiling_zero_penalty():
    penalty, suffix = _trim_rank_modifiers("XXX", {"Weight": 0.01})
    assert penalty == 0.0
    assert suffix == ""


def test_apply_trim_roles_informational_reranks(monkeypatch):
    monkeypatch.setattr(
        "tasks.build_crosshairs._trim_trigger_role",
        lambda t: "informational" if t == "GLD" else "binding",
    )
    item = CrosshairItem(
        ticker="GLD",
        reason_code=REASON_NEAR_TRIM,
        rank_score=_BUCKET_NEAR + 0.01,
        dist_trim=-0.006,
        rationale="price 402; trim 400; ->Trim -0.6%",
    )
    out = _apply_trim_roles([item])
    assert len(out) == 1
    assert out[0].override_tag == "TRIM_INFORMATIONAL"
    assert out[0].rank_score >= _BUCKET_DOCTRINE_HOLD
    assert "trim_trigger_role: informational" in out[0].rationale


def test_doctrine_precedence_over_trim_informational(monkeypatch):
    from utils import doctrine_reader

    class Rule:
        id = "tax_hold_runners"
        summary = "doctrine hold"

    def fake_downgrade(_doc, ticker, reason):
        if ticker == "GLD" and reason == REASON_NEAR_TRIM:
            return Rule()
        return None

    monkeypatch.setattr(doctrine_reader, "load_doctrine", lambda: object())
    monkeypatch.setattr(doctrine_reader, "downgrade_rule", fake_downgrade)

    item = CrosshairItem(
        ticker="GLD",
        reason_code=REASON_NEAR_TRIM,
        rank_score=_BUCKET_NEAR + 0.01,
        dist_trim=-0.006,
        rationale="->Trim -0.6%",
    )
    downgraded = _apply_doctrine_downgrades([item])[0]
    assert downgraded.override_tag == "HOLD_TAX"
    monkeypatch.setattr(
        "tasks.build_crosshairs._trim_trigger_role",
        lambda t: "informational",
    )
    reranked = _apply_trim_roles([downgraded])[0]
    assert reranked.override_tag == "HOLD_TAX"
    assert reranked.rank_score >= _BUCKET_DOCTRINE_HOLD


def test_trim_trigger_role_default_binding():
    assert _trim_trigger_role("ZZZZ") == "binding"
