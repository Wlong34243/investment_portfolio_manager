"""Tax surface formatting helpers for Sheet delivery."""

from tasks.build_crosshairs import CrosshairItem, format_tax_compact, is_trim_side_crosshair


def _item(**kwargs) -> CrosshairItem:
    reason = kwargs.pop("reason_code", "NEAR_TRIM")
    return CrosshairItem(ticker="MU", reason_code=reason, rank_score=0.0, **kwargs)


def test_add_row_no_tax_compact():
    item = _item(reason_code="NEAR_ADD")
    assert format_tax_compact(item) == ""
    assert not is_trim_side_crosshair(item)


def test_trim_row_tax_compact():
    item = _item(days_to_lt=77, wash_window_open=True, est_tax_cost_low=0, est_tax_cost_high=1038)
    text = format_tax_compact(item)
    assert "77d→LT" in text
    assert "wash open" in text
    assert "est $0" in text
    assert len(text) <= 40


def test_decision_view_cf_rules_use_grid_range():
    """gspread_formatting rejects plain A1 strings in ConditionalFormatRule.ranges."""
    from gspread_formatting import (
        BooleanCondition, BooleanRule, CellFormat, Color, ConditionalFormatRule, GridRange,
    )

    class _Ws:
        id = 1

    ws = _Ws()
    amber_fmt = CellFormat(backgroundColor=Color(1.0, 0.95, 0.80))
    rule = ConditionalFormatRule(
        ranges=[GridRange.from_a1_range("L3:L17", ws)],
        booleanRule=BooleanRule(
            condition=BooleanCondition("NOT_BLANK", []),
            format=amber_fmt,
        ),
    )
    assert rule.ranges[0].startColumnIndex == 11
