"""Position Story weight normalization — parity with /positions."""

import pytest

from ui.format import weight_to_pct_points


def test_weight_fraction_to_points():
    assert weight_to_pct_points(0.035975) == 3.5975


def test_weight_already_points():
    assert weight_to_pct_points(3.6) == 3.6


def test_weight_none():
    assert weight_to_pct_points(None) is None


def test_headroom_math_unh_like():
    weight = weight_to_pct_points(0.035975)
    ceiling = 4.0
    headroom = ceiling - weight
    assert 0.3 < headroom < 0.5


def test_headroom_math_already_points():
    weight = weight_to_pct_points(3.6)
    headroom = 4.0 - weight
    assert headroom == pytest.approx(0.4)
