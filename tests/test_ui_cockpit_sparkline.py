"""Cockpit sparkline assembly."""

from ui.sparkline import sparkline_from_bars, sparkline_from_values


def test_sparkline_from_bars_tail():
    bars = [{"close": 100 + i} for i in range(40)]
    sp = sparkline_from_bars(bars, tail=30)
    assert sp is not None
    assert len(sp["values"]) == 30
    assert sp["lo"] == 110
    assert sp["hi"] == 139


def test_sparkline_insufficient_data():
    assert sparkline_from_bars([{"close": 1.0}]) is None


def test_sparkline_from_values_tail():
    values = [float(100 + i) for i in range(40)]
    sp = sparkline_from_values(values, tail=30)
    assert sp is not None
    assert len(sp["values"]) == 30
    assert sp["lo"] == 110.0
    assert sp["hi"] == 139.0
