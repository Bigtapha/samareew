import math

import numpy as np
import pytest

from src import crosscheck as cc


def test_roof_share_inside():
    roof = np.array([[50, 50], [0, 100]], dtype=np.uint8)
    ours = np.array([[True, False], [False, True]])
    inside = np.ones_like(ours)
    assert cc.roof_share_inside(roof, ours, inside) == pytest.approx(150 / 200)
    inside[1, 1] = False   # outside the zone: ignored on both sides
    assert cc.roof_share_inside(roof, ours, inside) == pytest.approx(50 / 100)
    assert math.isnan(cc.roof_share_inside(np.zeros((2, 2)), ours, inside))


def test_confirmed_uses_the_window():
    roof = np.zeros((5, 5), dtype=np.uint8)
    roof[2, 2] = 54                       # one house, 54 % of a pixel
    mask = cc.confirmed(roof, window_px=3, min_roof_pct=5)
    assert mask[1, 1] and mask[2, 3]      # neighbours: 54 / 9 = 6 %
    assert not mask[0, 0]                 # two pixels away
    assert not cc.confirmed(roof, 3, 7)[1, 1]


def test_confirmation_rates():
    conf = np.array([True, True, False, False])
    groups = {"a": np.array([True, True, True, False]), "empty": np.zeros(4, dtype=bool)}
    rates = cc.confirmation_rates(conf, groups)
    assert rates["a"] == pytest.approx(200 / 3)
    assert math.isnan(rates["empty"])


def test_block_mean_drops_partial_blocks():
    a = np.arange(25).reshape(5, 5)
    out = cc.block_mean(a, 2)
    assert out.shape == (2, 2)
    assert out[0, 0] == pytest.approx((0 + 1 + 5 + 6) / 4)


def test_cell_correlation():
    ours = np.zeros((4, 4), dtype=bool)
    ours[:2, :2] = True
    roof = np.where(ours, 30, 0)
    inside = np.ones((4, 4), dtype=bool)
    assert cc.cell_correlation(ours, roof, inside, 2) == pytest.approx(1)
    assert math.isnan(cc.cell_correlation(ours, np.zeros((4, 4)), inside, 2))
    inside[3, 3] = False   # the bottom-right cell is no longer used
    assert cc.cell_correlation(ours, roof, inside, 2) == pytest.approx(1)


def test_growth_rates():
    assert cc.growth_pct(100, 150) == pytest.approx(50)
    assert cc.annual_growth_pct(100, 121, 2) == pytest.approx(10)
    assert math.isnan(cc.growth_pct(0, 10))

