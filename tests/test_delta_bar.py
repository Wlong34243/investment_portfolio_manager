"""Delta bar width calibration."""

from ui.format import delta_bar_width


def test_delta_bar_width_calibration():
    assert abs(delta_bar_width(-0.007) - 1.75) < 0.01
    assert abs(delta_bar_width(-0.15) - 37.5) < 0.01
    assert delta_bar_width(-0.4) == 50.0
