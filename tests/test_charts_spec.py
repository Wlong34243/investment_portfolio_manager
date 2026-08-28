"""ChartSpec construction is deterministic."""

from datetime import date

from ui.charts import ChartMarker, ChartSpec, build_chart_spec, render_chart_svg


def test_chart_spec_deterministic_svg():
    bars = [
        {"bar_date": "2026-08-26", "close": 100.0},
        {"bar_date": "2026-08-27", "close": 102.0},
        {"bar_date": "2026-08-28", "close": 101.0},
    ]
    txns = [
        {
            "trade_date": "2026-08-27",
            "action": "BUY",
            "shares": 10,
            "price": 102.0,
            "net_amount": -1020.0,
        }
    ]
    spec = build_chart_spec(
        bars=bars,
        transactions=txns,
        signals=[],
        open_lots=[],
        rotation_txn_dates=set(),
        as_of=date(2026, 8, 28),
        width=400,
        height=200,
    )
    svg1 = render_chart_svg(spec)
    svg2 = render_chart_svg(spec)
    assert svg1 == svg2
    assert "<svg" in svg1
    assert len(spec.markers) == 1
    assert spec.markers[0].txn_index == 0


def test_static_and_live_chart_path_match():
    from core.store.publish_static import render_chart_spec_static

    spec = ChartSpec(
        width=200,
        height=100,
        dates=("2026-01-01", "2026-01-02"),
        closes=(10.0, 11.0),
        cost_basis=(10.0, 10.5),
        markers=(
            ChartMarker(x_index=0, y=10.0, side="buy", size=6.0, txn_index=0),
        ),
        signals=(),
        lot_bands=(),
        today_index=1,
    )
    assert render_chart_svg(spec) == render_chart_spec_static(spec)
