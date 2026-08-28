"""Decision page crosshair row parity."""

from ui.crosshairs_table import crosshair_row


def test_crosshair_row_has_formatted_fields():
    row = crosshair_row(
        {
            "ticker": "UNH",
            "reason_code": "NEAR_TRIM",
            "dist_trim": -0.066,
            "days_to_lt": 77,
            "est_tax_cost_low": 0,
            "est_tax_cost_high": 1038,
        },
        rank=1,
    )
    assert row["signal"] == "NEAR_TRIM"
    assert row["dist_display"]
    assert "%" in row["dist_display"]
    assert row["est_tax_display"]
    assert "est" in row["est_tax_display"]
