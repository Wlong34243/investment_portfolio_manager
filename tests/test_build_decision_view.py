"""Decision_View dry-run must not crash on numeric tax cells."""

from __future__ import annotations

from tasks.build_crosshairs import CrosshairItem
from tasks.build_decision_view import _print_dry_run


def test_print_dry_run_accepts_int_tax_cells():
    item = CrosshairItem(
        ticker="GILD",
        reason_code="NEAR_TRIM",
        rank_score=100.0,
        mv=9365.0,
        wt=0.016,
        price=146.34,
        trim=140.0,
        dist_trim=-0.043,
        rationale="price trim",
        days_to_lt=42,
        est_tax_cost_low=1200.0,
        est_tax_cost_high=3400.0,
    )
    _print_dry_run("CROSSHAIRS — test", [item])
