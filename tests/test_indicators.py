import math

import numpy as np
import pytest
from affine import Affine

from src import indicators as ind

YEARS = [2016, 2017, 2018]


def test_built_counts_cumulative_by_unit():
    first_year = np.array([[2016, 2017, 0, -1],
                           [2018, 2018, 2017, 2016]])
    labels = np.array([[0, 0, 0, 0],
                       [1, 1, 1, -1]])
    built, land = ind.built_counts(first_year, labels, 2, YEARS)
    assert built.tolist() == [[1, 2, 2],     # unit 0: 2016, then 2017
                              [0, 1, 3]]     # unit 1: 2017, then two in 2018
    assert land.tolist() == [3, 3]           # -1 (outside the zone) and label -1 not counted


def test_built_counts_ignores_years_after_the_period():
    first_year = np.array([[2019, 2016]])
    built, _ = ind.built_counts(first_year, np.zeros((1, 2), dtype=int), 1, YEARS)
    assert built.tolist() == [[1, 1, 1]]


def test_unit_sums():
    values = np.array([[1.0, 2.0], [3.0, 4.0]])
    labels = np.array([[0, 1], [1, -1]])
    assert ind.unit_sums(values, labels, 2).tolist() == [1.0, 5.0]
    mask = np.array([[True, False], [True, True]])
    assert ind.unit_sums(values, labels, 2, mask).tolist() == [1.0, 3.0]


def grid(shape, fill=0):
    return np.full(shape, fill, dtype=np.int16)


def test_footprint_fringe_and_enclosed_hole():
    built = np.zeros((9, 9), dtype=bool)
    built[1, 1:8] = built[7, 1:8] = built[1:8, 1] = built[1:8, 7] = True  # a ring of buildings
    observed = np.ones_like(built)
    fp = ind.urban_footprint(built, observed, pixel_size=10, fringe_m=10, max_hole_ha=1)
    assert fp[4, 4]          # enclosed open space (25 px = 0.25 ha < 1 ha)
    assert fp[0, 4]          # fringe, 10 m from a building
    fp_small = ind.urban_footprint(built, observed, pixel_size=10, fringe_m=10, max_hole_ha=0.01)
    assert not fp_small[4, 4]  # hole too large to be filled
    assert fp_small[2, 4]      # but still in the fringe


def test_footprint_hole_open_to_the_sea_is_not_filled():
    built = np.zeros((9, 9), dtype=bool)
    built[1, 1:8] = built[7, 1:8] = built[1:8, 1] = built[1:8, 7] = True
    observed = np.ones_like(built)
    observed[4, 4] = False   # a pixel outside the zone (sea) inside the ring
    fp = ind.urban_footprint(built, observed, pixel_size=10, fringe_m=10, max_hole_ha=1)
    assert not fp[4, 4] and not fp[3, 4] and fp[2, 4]


def test_growth_types():
    first_year = grid((5, 12))
    first_year[2, 0:3] = 2016   # existing block
    first_year[2, 3] = 2018     # next to it: inside the 10 m fringe -> densification
    first_year[2, 5:7] = 2018   # new patch touching the footprint (fringe ends at col 3) ...
    first_year[2, 4] = 2018     # ... through this pixel -> col 4..6 is one patch: extension
    first_year[2, 10] = 2017    # isolated -> leapfrog
    first_year[0, 0] = 2016     # built before the period: no growth type
    types = ind.growth_types(first_year, 2016, 2018, pixel_size=10, fringe_m=10, max_hole_ha=0, radius_m=10, min_share=0)
    assert types[2, 3] == ind.DENSIFICATION
    assert types[2, 4] == types[2, 5] == types[2, 6] == ind.EXTENSION
    assert types[2, 10] == ind.LEAPFROG
    assert types[2, 0] == types[0, 0] == ind.NO_GROWTH
    # Outside the period: built in 2018 is not new for 2016 -> 2017
    assert ind.growth_types(first_year, 2016, 2017, 10, 10, 0, 10, 0)[2, 5] == ind.NO_GROWTH


def test_growth_types_diagonal_contact_is_extension():
    first_year = grid((4, 4))
    first_year[0, 0] = 2016
    first_year[1, 1] = first_year[2, 2] = 2017   # touches the block diagonally (no fringe)
    types = ind.growth_types(first_year, 2016, 2017, pixel_size=10, fringe_m=0, max_hole_ha=0, radius_m=10, min_share=0)
    assert types[1, 1] == types[2, 2] == ind.EXTENSION


def test_built_share_in_circle():
    built = np.zeros((5, 5), dtype=bool)
    built[2, 2] = True
    observed = np.ones_like(built)
    share = ind.built_share_in_circle(built, observed, radius_px=1)   # 5-pixel cross
    assert share[2, 2] == pytest.approx(1 / 5)
    assert share[0, 0] == pytest.approx(0, abs=1e-6)
    observed[1, 2] = observed[3, 2] = False                            # sea left out
    assert ind.built_share_in_circle(built, observed, 1)[2, 2] == pytest.approx(1 / 3)


def test_growth_next_to_a_village_is_leapfrog():
    first_year = grid((7, 30))
    first_year[1:6, 1:6] = 2016     # dense block: urban
    first_year[3, 25] = 2016        # one isolated building: rural, outside the footprint
    first_year[3, 26] = 2018        # new building next to it -> leapfrog, not densification
    first_year[3, 7] = 2018         # next to the dense block -> densification
    types = ind.growth_types(first_year, 2016, 2018, pixel_size=10, fringe_m=20,
                             max_hole_ha=0, radius_m=30, min_share=0.25)
    assert types[3, 7] == ind.DENSIFICATION
    assert types[3, 26] == ind.LEAPFROG


def test_direction_ring_labels():
    # 4 x 4 grid of 10 m pixels, centre in the middle of the grid
    transform = Affine(10, 0, 0, 0, -10, 40)
    direction, ring = ind.direction_ring_labels((4, 4), transform, (20, 20), ring_width=15)
    assert direction[0, 2] == 0     # pixel centre (25, 35): north-north-east -> N
    assert direction[0, 3] == 1     # (35, 35): north-east
    assert direction[3, 0] == 5     # (5, 5): south-west
    assert direction[1, 3] == 2     # (35, 25): east-north-east -> E
    assert ring[1, 1] == 0 and ring[0, 0] == 1   # 7.1 m and 21.2 m from the centre


def test_cell_areas_m2():
    areas = ind.cell_areas_m2(top_lat=1.0, res_deg=1.0, n_rows=2)
    side = 2 * math.pi * ind.EARTH_RADIUS_M / 360
    assert areas[0] == pytest.approx(side ** 2, rel=1e-3)   # near the equator: ~ a square
    assert areas[0] == pytest.approx(areas[1])              # symmetric around the equator
    north = ind.cell_areas_m2(top_lat=61.0, res_deg=1.0, n_rows=1)[0]
    assert north == pytest.approx(side ** 2 * math.cos(math.radians(60.5)), rel=1e-3)


def test_sdg_11_3_1():
    # Built-up area and population both double: ratio 1
    assert ind.sdg_11_3_1(100, 200, 1000, 2000) == pytest.approx(1)
    # Built-up area x4, population x2: the city spreads out, ratio 2
    assert ind.sdg_11_3_1(100, 400, 1000, 2000) == pytest.approx(2)
    assert math.isnan(ind.sdg_11_3_1(100, 200, 1000, 900))   # population falling
    assert math.isnan(ind.sdg_11_3_1(0, 200, 1000, 2000))
